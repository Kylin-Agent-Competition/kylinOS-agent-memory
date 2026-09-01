"""D9D Outbox Router + Index/Deletion Consumer 测试（D-REQ-05）

覆盖：
  1. 路由注册/分发/未知类型失败/重复注册
  2. index consumer：构造 VectorUpsertRequest → provider.upsert 成功 / 缺字段 / provider 失败
  3. forget consumer：invalidator 未接线真实失败 / 成功
  4. worker 集成：成功删除 / 未知重试 / 失败进 Dead Letter
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
    VectorUpsertResult,
)

_DIGEST = "hmac-sha256:k1:" + "a" * 64


class FakeVectorProvider:
    """L1 记录型 VectorProvider 替身（只验证 consumer 构造/调用语义，非宿主行为）。"""

    def __init__(self, *, fail: bool = False):
        self.calls = []
        self.fail = fail

    def upsert(self, request):
        self.calls.append(request)
        if self.fail:
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


def _upsert_payload(**overrides):
    payload = {
        "event_type": repo.EVENT_MEMORY_UPSERTED,
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
    router.register(repo.EVENT_MEMORY_UPSERTED, lambda p: seen.append(p))
    router.route({"event_type": repo.EVENT_MEMORY_UPSERTED, "x": 1})
    assert seen == [{"event_type": repo.EVENT_MEMORY_UPSERTED, "x": 1}]


def test_router_unknown_event_type_raises():
    router = OutboxRouter()
    with pytest.raises(UnknownEventTypeError):
        router.route({"event_type": "no.such"})


def test_router_missing_event_type_raises():
    router = OutboxRouter()
    with pytest.raises(UnknownEventTypeError):
        router.route({"other": 1})


def test_router_duplicate_register_rejected():
    router = OutboxRouter()
    router.register(repo.EVENT_MEMORY_UPSERTED, lambda p: None)
    with pytest.raises(ValueError):
        router.register(repo.EVENT_MEMORY_UPSERTED, lambda p: None)


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
    consumer(_upsert_payload())
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
        consumer(_upsert_payload(user_id=None))


def test_index_consumer_provider_failure_raises():
    provider = FakeVectorProvider(fail=True)
    consumer = build_index_consumer(provider)
    with pytest.raises(RuntimeError):
        consumer(_upsert_payload())


def test_index_consumer_wrong_event_type_raises():
    provider = FakeVectorProvider()
    consumer = build_index_consumer(provider)
    with pytest.raises(ValueError):
        consumer({"event_type": repo.EVENT_FORGET_EXECUTED})


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
    consumer = build_forget_consumer(svc)
    with pytest.raises(RuntimeError):
        consumer({
            "event_type": repo.EVENT_FORGET_EXECUTED,
            "event_id": "forget_1",
            "user_id": "u1",
            "target_type": "event",
            "content_hashes": ["h1"],
            "content_fingerprints": ["fp1"],
            "forget_mode": "single_item",
        })
    svc.close()


def test_forget_consumer_success_with_invalidator():
    svc = _embedding_service()
    svc.set_cache_invalidator(_ExtractionCacheStub())
    consumer = build_forget_consumer(svc)
    consumer({
        "event_type": repo.EVENT_FORGET_EXECUTED,
        "event_id": "forget_2",
        "user_id": "u1",
        "target_type": "event",
        "content_hashes": ["h1"],
        "content_fingerprints": ["fp1"],
        "forget_mode": "single_item",
    })
    svc.close()


def test_forget_consumer_wrong_event_type_raises():
    svc = _embedding_service()
    consumer = build_forget_consumer(svc)
    with pytest.raises(ValueError):
        consumer({"event_type": repo.EVENT_MEMORY_UPSERTED})
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
    router.register(repo.EVENT_MEMORY_UPSERTED, build_index_consumer(FakeVectorProvider(fail=True)))
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3, consumer=router.route)
    w._poll_once()
    with engine.connect() as conn:
        row = conn.execute(repo.outbox.select()).mappings().first()
        assert row["attempts"] == 4
        assert row["next_retry_at"] is None  # Dead Letter
    assert w.metrics()["dead_letters"] == 1
    w.stop()
