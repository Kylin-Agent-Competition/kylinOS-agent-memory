"""D9D index_sync_lag 指标口径测试（D-REQ-06，P2）

口径（任务卡 §4.2 冻结）：
    index_sync_lag = latest committed memory change timestamp −
                     latest successfully indexed timestamp
缺数据（空库/未消费）→ None（不伪造 0）；backlog=0 全部消费 → 收敛为 0。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from db import repositories as repo
from db.engine import create_db_engine, init_schema
from outbox.router import OutboxRouter
from outbox.worker import OutboxWorker

_DIGEST = "hmac-sha256:k1:" + "a" * 64


@pytest.fixture()
def engine(tmp_path):
    eng = create_db_engine(str(tmp_path / "lag.db"))
    init_schema(eng)
    yield eng
    eng.dispose()


def _insert_memory(engine, *, user_id="u1", created_at=None, updated_at=None):
    now = created_at or datetime.now(timezone.utc).isoformat()
    updated = updated_at or now
    with engine.begin() as conn:
        repo.insert_memory_entry(
            conn,
            user_id=user_id,
            entry_type="preference",
            content={"key": "k"},
        )
        conn.execute(
            repo.memory_entries.update()
            .where(repo.memory_entries.c.user_id == user_id)
            .values(created_at=now, updated_at=updated)
        )


def _upsert_payload(event_id="evt_1"):
    return {
        "event_type": repo.EVENT_MEMORY_UPSERTED,
        "event_id": event_id,
        "trace_id": "trc",
        "memory_id": "mem_1",
        "version_id": "v_1",
        "user_id": "u1",
        "vector": [0.1, 0.2],
        "object_type": "preference",
        "index_text_hash": _DIGEST,
    }


def _count(engine):
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(repo.outbox)).scalar()


def test_metrics_no_data_returns_none(engine):
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3)
    m = w.metrics()
    # 空库且未消费 → index_sync_lag 缺数据 → None（不伪造 0）
    assert m["index_sync_lag"] is None
    assert m["index_sync_lag_seconds"] is None
    w.stop()


def test_metrics_memory_present_but_not_consumed_returns_none(engine):
    _insert_memory(engine)
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3)
    m = w.metrics()
    # 有 memory 变更但未消费（_last_indexed_ts=None）→ 仍 None
    assert m["index_sync_lag"] is None
    assert m["index_sync_lag_seconds"] is None
    w.stop()


def _enqueue_with_created(engine, *, payload, created_at):
    with engine.begin() as conn:
        eid = repo.enqueue_outbox(
            conn,
            aggregate_type="memory",
            aggregate_id=str(payload.get("event_id", "")),
            event_type=repo.EVENT_MEMORY_UPSERTED,
            payload=payload,
            next_retry_at=created_at.isoformat(),
        )
        conn.execute(
            repo.outbox.update().where(repo.outbox.c.id == eid).values(created_at=created_at.isoformat())
        )
    return eid


def test_metrics_converges_zero_after_full_consumption(engine, monkeypatch):
    monkeypatch.setattr(repo, "cleanup_expired_idempotency", lambda *a, **k: 0)
    ts = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    _insert_memory(engine, created_at=ts.isoformat())
    _enqueue_with_created(engine, payload=_upsert_payload(), created_at=ts)

    class _Recorder:
        def upsert(self, request):
            from retrieval.contracts import (
                Outcome,
                ProviderResult,
                VectorUpsertResult,
            )
            result = VectorUpsertResult(
                accepted_count=1, upserted_count=1, unchanged_count=0,
                index_generation=request.index_generation,
                applied_watermark=request.source_watermark,
                outcome=Outcome.APPLIED,
            )
            return ProviderResult(
                ok=True, value=result, provider="fake", request_id=request.request_id,
                elapsed_ms=0, completed_at=datetime.now(timezone.utc),
            )

    from outbox.index_consumer import build_index_consumer

    provider = _Recorder()
    router = OutboxRouter()
    router.register(repo.EVENT_MEMORY_UPSERTED, build_index_consumer(provider))
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3, consumer=router.route)
    w._poll_once()  # 消费成功（记录 last_indexed_ts）
    assert _count(engine) == 0  # backlog=0

    m = w.metrics()
    # 同库时间戳自洽：memory 变更时间 == 成功消费 outbox.created_at → lag=0
    assert m["backlog"] == 0
    assert m["index_sync_lag_seconds"] == 0.0
    w.stop()


def test_metrics_lag_positive_when_memory_newer_than_indexed(engine, monkeypatch):
    monkeypatch.setattr(repo, "cleanup_expired_idempotency", lambda *a, **k: 0)
    mem_ts = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    outbox_ts = datetime(2026, 9, 1, 9, 59, 0, tzinfo=timezone.utc)
    _insert_memory(engine, created_at=mem_ts.isoformat())
    _enqueue_with_created(engine, payload=_upsert_payload(), created_at=outbox_ts)

    class _Recorder:
        def upsert(self, request):
            from retrieval.contracts import (
                Outcome,
                ProviderResult,
                VectorUpsertResult,
            )
            result = VectorUpsertResult(
                accepted_count=1, upserted_count=1, unchanged_count=0,
                index_generation=request.index_generation,
                applied_watermark=request.source_watermark,
                outcome=Outcome.APPLIED,
            )
            return ProviderResult(
                ok=True, value=result, provider="fake", request_id=request.request_id,
                elapsed_ms=0, completed_at=datetime.now(timezone.utc),
            )

    from outbox.index_consumer import build_index_consumer

    router = OutboxRouter()
    router.register(repo.EVENT_MEMORY_UPSERTED, build_index_consumer(_Recorder()))
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3, consumer=router.route)
    w._poll_once()
    m = w.metrics()
    # memory 变更(10:00) − 已索引(9:59) = 60s
    assert m["index_sync_lag_seconds"] == 60.0
    w.stop()


def test_repositories_latest_memory_change_ts(engine):
    # 空表 → None
    with engine.connect() as conn:
        assert repo.latest_memory_change_ts(conn) is None
    _insert_memory(engine, created_at="2026-09-01T10:00:00+00:00")
    with engine.connect() as conn:
        assert repo.latest_memory_change_ts(conn) == "2026-09-01T10:00:00+00:00"
