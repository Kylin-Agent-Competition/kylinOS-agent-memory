"""D9D Outbox Router + Index/Deletion Consumer 测试（D-REQ-05）

覆盖：
  1. 路由注册/分发/未知类型失败/重复注册/event_type 一致性校验（HIGH-01）
  2. index consumer：构造 VectorUpsertRequest → provider.upsert 成功 / 缺字段 / provider 失败
     / payload 不含 event_type 仍正确路由（HIGH-01）/ trace_id 确定性 fallback（非阻断 1）
  3. forget consumer：invalidator 未接线真实失败 / vector_provider 未接线真实失败（HIGH-02）
     / 组合消费成功（cache + vector delete）/ vector delete 失败不得 ACK（HIGH-02）
  4. worker 集成：成功删除 / 未知重试 / 失败进 Dead Letter
     / _last_indexed_ts 仅 memory.upserted 推进（MEDIUM-02）
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from db import repositories as repo
from db.engine import create_db_engine, init_schema
from embedding.embedding_service import EmbeddingService
from outbox.deletion_consumer import build_forget_consumer
from outbox.index_consumer import build_index_consumer
from outbox.router import OutboxRouter, UnknownEventTypeError, build_outbox_router
from outbox.worker import OutboxWorker
from retrieval.contracts import (
    Outcome,
    ProviderResult,
    RetrievalError,
    RetrievalErrorCode,
    VectorDeleteResult,
    VectorUpsertResult,
)

_DIGEST = "hmac-sha256:k1:" + "a" * 64


class FakeVectorProvider:
    """L1 记录型 VectorProvider 替身（只验证 consumer 构造/调用语义，非宿主行为）。"""

    def __init__(self, *, fail_upsert: bool = False, fail_delete: bool = False):
        self.calls = []
        self.delete_calls = []
        self.fail_upsert = fail_upsert
        self.fail_delete = fail_delete

    def upsert(self, request):
        self.calls.append(request)
        if self.fail_upsert:
            return ProviderResult(
                ok=False,
                error=RetrievalError(
                    code=RetrievalErrorCode.PROVIDER_UNAVAILABLE,
                    message="provider unavailable",
                    retryable=True,
                    stage="provider",
                    provider="fake",
                ),
                provider="fake",
                request_id=request.request_id,
                elapsed_ms=0,
                completed_at=datetime.now(timezone.utc),
            )
        result = VectorUpsertResult(
            accepted_count=1,
            upserted_count=1,
            unchanged_count=0,
            index_generation=request.index_generation,
            applied_watermark=request.source_watermark,
            outcome=Outcome.APPLIED,
        )
        return ProviderResult(
            ok=True,
            value=result,
            provider="fake",
            request_id=request.request_id,
            elapsed_ms=0,
            completed_at=datetime.now(timezone.utc),
        )

    def delete(self, request):
        self.delete_calls.append(request)
        if self.fail_delete:
            return ProviderResult(
                ok=False,
                error=RetrievalError(
                    code=RetrievalErrorCode.PROVIDER_UNAVAILABLE,
                    message="provider unavailable",
                    retryable=True,
                    stage="provider",
                    provider="fake",
                ),
                provider="fake",
                request_id=request.request_id,
                elapsed_ms=0,
                completed_at=datetime.now(timezone.utc),
            )
        result = VectorDeleteResult(
            matched_count=1,
            deleted_count=1,
            index_generation=request.index_generation,
            applied_watermark=request.source_watermark,
            outcome=Outcome.APPLIED,
        )
        return ProviderResult(
            ok=True,
            value=result,
            provider="fake",
            request_id=request.request_id,
            elapsed_ms=0,
            completed_at=datetime.now(timezone.utc),
        )


def _upsert_payload(**overrides):
    payload = {
        # HIGH-01：payload 不要求含 event_type（DB 列是真源）；测试默认不含以覆盖真实 envelope
        "event_id": "evt_1",
        "trace_id": "trc_1",
        "memory_id": "mem_1",
        "version_id": "v_1",
        "user_id": "u1",
        "vector": [0.1, 0.2],
        "object_type": "preference",
        "index_text_hash": _DIGEST,
    }
    payload.update(overrides)
    return payload


def _forget_payload(**overrides):
    payload = {
        "event_id": "forget_1",
        "user_id": "u1",
        "forget_plan_id": "plan_1",
        "resolved_target_ids": ["mem_1"],
        "version_ids": ["v_1"],
        "selection_hash": _DIGEST,
        "target_type": "event",
        "content_hashes": ["h1"],
        "content_fingerprints": ["fp1"],
        "forget_mode": "single_item",
    }
    payload.update(overrides)
    return payload


class _ExtractionCacheStub:
    def clear(self):
        return None

    def invalidate_by_content(self, fp):
        return 0

    def invalidate_by_event(self, eid):
        return 0


# ── 1. 路由 ──


def test_router_register_and_dispatch():
    router = OutboxRouter()
    seen = []
    router.register(repo.EVENT_MEMORY_UPSERTED, lambda et, p: seen.append((et, p)))
    router.route(repo.EVENT_MEMORY_UPSERTED, {"x": 1})
    assert seen == [(repo.EVENT_MEMORY_UPSERTED, {"x": 1})]


def test_router_unknown_event_type_raises():
    router = OutboxRouter()
    with pytest.raises(UnknownEventTypeError):
        router.route("no.such", {})


def test_router_missing_event_type_raises():
    # 未注册类型（即使 payload 有 event_type）→ UnknownEventTypeError
    router = OutboxRouter()
    with pytest.raises(UnknownEventTypeError):
        router.route("no.such", {"event_type": "no.such"})


def test_router_duplicate_register_rejected():
    router = OutboxRouter()
    router.register(repo.EVENT_MEMORY_UPSERTED, lambda et, p: None)
    with pytest.raises(ValueError):
        router.register(repo.EVENT_MEMORY_UPSERTED, lambda et, p: None)


def test_router_payload_event_type_mismatch_fails_closed():
    """HIGH-01：payload 内嵌 event_type 与 DB 列不一致 → ValueError fail-closed。"""
    router = OutboxRouter()
    router.register(repo.EVENT_MEMORY_UPSERTED, lambda et, p: None)
    with pytest.raises(ValueError):
        router.route(
            repo.EVENT_MEMORY_UPSERTED,
            {"event_type": repo.EVENT_FORGET_EXECUTED},
        )


def test_router_payload_event_type_match_ok():
    """HIGH-01：payload 内嵌 event_type 与 DB 列一致 → 正常路由。"""
    router = OutboxRouter()
    seen = []
    router.register(repo.EVENT_MEMORY_UPSERTED, lambda et, p: seen.append(et))
    router.route(repo.EVENT_MEMORY_UPSERTED, {"event_type": repo.EVENT_MEMORY_UPSERTED})
    assert seen == [repo.EVENT_MEMORY_UPSERTED]


def test_build_outbox_router_no_providers_has_no_routes():
    router = build_outbox_router()
    assert not router.has_route(repo.EVENT_MEMORY_UPSERTED)
    assert not router.has_route(repo.EVENT_FORGET_EXECUTED)


def test_build_outbox_router_registers_with_provider_and_service():
    router = build_outbox_router(vector_provider=FakeVectorProvider())
    assert router.has_route(repo.EVENT_MEMORY_UPSERTED)


# ── 2. index consumer ──


def test_index_consumer_success_calls_provider():
    provider = FakeVectorProvider()
    consumer = build_index_consumer(provider)
    consumer(repo.EVENT_MEMORY_UPSERTED, _upsert_payload())
    assert len(provider.calls) == 1
    req = provider.calls[0]
    assert req.user_id == "u1"
    assert req.records[0].memory_id == "mem_1"
    assert req.records[0].version_id == "v_1"
    assert req.records[0].object_type.value == "preference"
    assert req.trace_id == "trc_1"


def test_index_consumer_missing_field_raises():
    provider = FakeVectorProvider()
    consumer = build_index_consumer(provider)
    with pytest.raises(ValueError):
        consumer(repo.EVENT_MEMORY_UPSERTED, _upsert_payload(user_id=None))


def test_index_consumer_provider_failure_raises():
    provider = FakeVectorProvider(fail_upsert=True)
    consumer = build_index_consumer(provider)
    with pytest.raises(RuntimeError):
        consumer(repo.EVENT_MEMORY_UPSERTED, _upsert_payload())


def test_index_consumer_wrong_event_type_raises():
    provider = FakeVectorProvider()
    consumer = build_index_consumer(provider)
    with pytest.raises(ValueError):
        consumer(repo.EVENT_FORGET_EXECUTED, _upsert_payload())


def test_index_consumer_payload_without_event_type_routes():
    """HIGH-01：DB event_type=memory.upserted、payload 不含 event_type → 正确路由消费。"""
    provider = FakeVectorProvider()
    consumer = build_index_consumer(provider)
    consumer(repo.EVENT_MEMORY_UPSERTED, {"event_id": "evt_no_type", "memory_id": "m",
                                           "version_id": "v", "user_id": "u",
                                           "vector": [0.1], "object_type": "preference",
                                           "index_text_hash": _DIGEST})
    assert len(provider.calls) == 1


def test_index_consumer_trace_id_fallback():
    """非阻断 1：payload 缺 trace_id → 确定性 fallback（outbox:{event_id}）。"""
    provider = FakeVectorProvider()
    consumer = build_index_consumer(provider)
    consumer(repo.EVENT_MEMORY_UPSERTED, _upsert_payload(trace_id=None))
    assert provider.calls[0].trace_id == "outbox:evt_1"


# ── 3. forget consumer ──


def _embedding_service():
    class _FakeProvider:
        def start(self):
            pass

        def close(self):
            pass

        def get_dimension(self):
            return 768

        def embed(self, text, *, timeout_ms=5000):
            raise AssertionError("forget consumer 不应触发 embed")

    svc = EmbeddingService(provider=_FakeProvider())
    svc.start()
    return svc


def test_forget_consumer_invalidator_none_fails():
    svc = _embedding_service()
    consumer = build_forget_consumer(svc, vector_provider=FakeVectorProvider())
    with pytest.raises(RuntimeError):
        consumer(repo.EVENT_FORGET_EXECUTED, _forget_payload())
    svc.close()


def test_forget_consumer_vector_provider_none_fails():
    """HIGH-02：vector_provider 未接线 → forget.executed 真实失败（不得 ACK）。"""
    svc = _embedding_service()
    svc.set_cache_invalidator(_ExtractionCacheStub())
    consumer = build_forget_consumer(svc, vector_provider=None)
    with pytest.raises(RuntimeError):
        consumer(repo.EVENT_FORGET_EXECUTED, _forget_payload())
    svc.close()


def test_forget_consumer_composed_success():
    """HIGH-02：cache invalidation + Vector delete 全部成功 → 返回成功。"""
    svc = _embedding_service()
    svc.set_cache_invalidator(_ExtractionCacheStub())
    provider = FakeVectorProvider()
    consumer = build_forget_consumer(svc, vector_provider=provider)
    consumer(repo.EVENT_FORGET_EXECUTED, _forget_payload())
    assert len(provider.delete_calls) == 1
    req = provider.delete_calls[0]
    assert req.user_id == "u1"
    assert req.selector.memory_ids == ["mem_1"]
    assert req.selector.version_ids == ["v_1"]
    assert req.selector.confirmation_ref == "forget_1"
    svc.close()


def test_forget_consumer_vector_delete_failure_raises():
    """HIGH-02：cache 成功 + Vector deletion 失败 → 抛异常（Worker 不得 DELETE → retry/DL）。"""
    svc = _embedding_service()
    svc.set_cache_invalidator(_ExtractionCacheStub())
    provider = FakeVectorProvider(fail_delete=True)
    consumer = build_forget_consumer(svc, vector_provider=provider)
    with pytest.raises(RuntimeError):
        consumer(repo.EVENT_FORGET_EXECUTED, _forget_payload())
    assert len(provider.delete_calls) == 1
    svc.close()


def test_forget_consumer_wrong_event_type_raises():
    svc = _embedding_service()
    consumer = build_forget_consumer(svc, vector_provider=FakeVectorProvider())
    with pytest.raises(ValueError):
        consumer(repo.EVENT_MEMORY_UPSERTED, _forget_payload())
    svc.close()


# ── 4. worker 集成 ──


@pytest.fixture()
def engine(tmp_path):
    eng = create_db_engine(str(tmp_path / "d9d.db"))
    init_schema(eng)
    yield eng
    eng.dispose()


def _count(engine):
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(repo.outbox)).scalar()


def _enqueue(engine, *, event_type, payload, created_at=None):
    with engine.begin() as conn:
        return repo.enqueue_outbox(
            conn,
            aggregate_type="memory",
            aggregate_id=str(payload.get("event_id", "")),
            event_type=event_type,
            payload=payload,
            next_retry_at=created_at or datetime.now(timezone.utc).isoformat(),
        )


def test_worker_success_delete_with_router(engine, monkeypatch):
    # 隔离本环境无关的过期幂等清理（Windows 自带 pysqlite 无 DELETE...LIMIT 支持）
    monkeypatch.setattr(repo, "cleanup_expired_idempotency", lambda *a, **k: 0)
    # payload 不含 event_type（真实 Outbox envelope：event_type 在 DB 列）
    _enqueue(engine, event_type=repo.EVENT_MEMORY_UPSERTED, payload=_upsert_payload())
    router = OutboxRouter()
    provider = FakeVectorProvider()
    router.register(repo.EVENT_MEMORY_UPSERTED, build_index_consumer(provider))
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3, consumer=router.route)
    w._poll_once()
    assert _count(engine) == 0  # 成功 → DELETE
    assert w.metrics()["processed"] == 1
    assert len(provider.calls) == 1
    w.stop()


def test_worker_unknown_event_retries(engine, monkeypatch):
    monkeypatch.setattr(repo, "cleanup_expired_idempotency", lambda *a, **k: 0)
    _enqueue(engine, event_type=repo.EVENT_MEMORY_UPSERTED, payload=_upsert_payload())
    router = OutboxRouter()  # 未注册 memory.upserted → UnknownEventTypeError → 重试
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3, consumer=router.route)
    w._poll_once()
    with engine.connect() as conn:
        row = conn.execute(repo.outbox.select()).mappings().first()
        assert row["attempts"] == 1
        assert row["next_retry_at"] is not None
        assert "unknown outbox event_type" in row["last_error"]
    w.stop()


def test_worker_provider_failure_goes_dead_letter(engine, monkeypatch):
    monkeypatch.setattr(repo, "cleanup_expired_idempotency", lambda *a, **k: 0)
    eid = _enqueue(engine, event_type=repo.EVENT_MEMORY_UPSERTED, payload=_upsert_payload())
    with engine.begin() as conn:
        repo.mark_outbox_failure(
            conn, outbox_id=eid, attempts=3,
            next_retry_at=(datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=1)).isoformat(),
            last_error="prev",
        )
    router = OutboxRouter()
    router.register(repo.EVENT_MEMORY_UPSERTED, build_index_consumer(FakeVectorProvider(fail_upsert=True)))
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3, consumer=router.route)
    w._poll_once()
    with engine.connect() as conn:
        row = conn.execute(repo.outbox.select()).mappings().first()
        assert row["attempts"] == 4
        assert row["next_retry_at"] is None  # Dead Letter
    assert w.metrics()["dead_letters"] == 1
    w.stop()


def test_worker_forget_vector_failure_retries_not_delete(engine, monkeypatch):
    """HIGH-02：cache 成功 + Vector delete 失败 → Outbox 不得 DELETE → retry。"""
    monkeypatch.setattr(repo, "cleanup_expired_idempotency", lambda *a, **k: 0)
    _enqueue(engine, event_type=repo.EVENT_FORGET_EXECUTED, payload=_forget_payload())
    svc = _embedding_service()
    svc.set_cache_invalidator(_ExtractionCacheStub())
    router = OutboxRouter()
    router.register(
        repo.EVENT_FORGET_EXECUTED,
        build_forget_consumer(svc, vector_provider=FakeVectorProvider(fail_delete=True)),
    )
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3, consumer=router.route)
    w._poll_once()
    assert _count(engine) == 1  # 未删除
    with engine.connect() as conn:
        row = conn.execute(repo.outbox.select()).mappings().first()
        assert row["attempts"] == 1
        assert "forget vector delete failed" in row["last_error"]
    w.stop()
    svc.close()


def test_worker_last_indexed_ts_only_memory_upserted(engine, monkeypatch):
    """MEDIUM-02：非索引事件成功后 _last_indexed_ts 不推进（同一 worker 依次消费）。"""
    monkeypatch.setattr(repo, "cleanup_expired_idempotency", lambda *a, **k: 0)

    def _enqueue_with_created(event_type, payload, created_at_iso):
        with engine.begin() as conn:
            eid = repo.enqueue_outbox(
                conn,
                aggregate_type="memory",
                aggregate_id=str(payload.get("event_id", "")),
                event_type=event_type,
                payload=payload,
                next_retry_at=created_at_iso,
            )
            conn.execute(
                repo.outbox.update()
                .where(repo.outbox.c.id == eid)
                .values(created_at=created_at_iso)
            )
        return eid

    # 同一 router 注册两类事件：memory.upserted → index；forget.executed → 组合消费
    svc = _embedding_service()
    svc.set_cache_invalidator(_ExtractionCacheStub())
    router = OutboxRouter()
    router.register(repo.EVENT_MEMORY_UPSERTED, build_index_consumer(FakeVectorProvider()))
    router.register(
        repo.EVENT_FORGET_EXECUTED,
        build_forget_consumer(svc, vector_provider=FakeVectorProvider()),
    )
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3, consumer=router.route)

    # memory.upserted @ 10:00 成功（created_at 列也置 10:00）
    _enqueue_with_created(
        repo.EVENT_MEMORY_UPSERTED,
        _upsert_payload(event_id="evt_indexed"),
        "2026-09-01T10:00:00+00:00",
    )
    w._poll_once()
    assert w._last_indexed_ts == "2026-09-01T10:00:00+00:00"

    # 非索引事件 forget.executed @ 10:10 成功（组合消费成功）
    _enqueue_with_created(
        repo.EVENT_FORGET_EXECUTED,
        _forget_payload(event_id="evt_forget"),
        "2026-09-01T10:10:00+00:00",
    )
    w._poll_once()
    assert w._last_indexed_ts == "2026-09-01T10:00:00+00:00"  # 保持 10:00，不推进
    assert _count(engine) == 0  # 两事件均成功消费
    w.stop()
    svc.close()
