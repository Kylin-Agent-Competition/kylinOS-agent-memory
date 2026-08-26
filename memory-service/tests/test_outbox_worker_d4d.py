"""D4D Outbox Worker 测试：FR-DB-004 / 附录 B（成功 / 退避 / Dead Letter / 幂等清理）"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import func, select

from db import repositories as repo
from db.engine import create_db_engine, init_schema
from outbox.worker import OutboxWorker


@pytest.fixture()
def engine(tmp_path):
    eng = create_db_engine(str(tmp_path / "ow.db"))
    init_schema(eng)
    yield eng
    eng.dispose()


def _enqueue(engine, *, aggregate_id="1", next_retry_at=None):
    with engine.begin() as conn:
        return repo.enqueue_outbox(
            conn,
            aggregate_type="turn",
            aggregate_id=aggregate_id,
            event_type=repo.EVENT_TURN_FINALIZED,
            payload={"turn_id": aggregate_id},
            next_retry_at=next_retry_at or datetime.now(timezone.utc).isoformat(),
        )


def _count(engine):
    with engine.connect() as conn:
        return conn.execute(
            select(func.count()).select_from(repo.outbox)
        ).scalar()


def test_worker_consumes_success(engine):
    _enqueue(engine)
    seen = []

    def consumer(payload):
        seen.append(payload)

    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3, consumer=consumer)
    w._poll_once()
    assert seen == [{"turn_id": "1"}]
    assert _count(engine) == 0  # 成功 → DELETE
    w.stop()


def test_worker_no_consumer_retries(engine):
    # Vector 接入未确认（R-9）：无 consumer → 失败路径（attempts+1 + 退避）
    _enqueue(engine)
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3, consumer=None)
    w._poll_once()
    with engine.connect() as conn:
        row = conn.execute(repo.outbox.select()).mappings().first()
        assert row["attempts"] == 1
        assert row["next_retry_at"] is not None
        assert "no consumer registered" in row["last_error"]
        # 退避 = now + 2^1 * 30s
        next_retry = datetime.fromisoformat(row["next_retry_at"])
        expected_min = datetime.now(timezone.utc) + timedelta(seconds=60 - 5)
        assert next_retry > expected_min
    w.stop()


def test_worker_dead_letter_after_max_retries(engine):
    # 预置 attempts=3（已达 max）且 next_retry_at 已到期 → 再失败 → Dead Letter
    eid = _enqueue(engine)
    with engine.begin() as conn:
        repo.mark_outbox_failure(
            conn, outbox_id=eid, attempts=3,
            next_retry_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            last_error="prev",
        )
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3, consumer=None)
    w._poll_once()
    with engine.connect() as conn:
        row = conn.execute(repo.outbox.select()).mappings().first()
        assert row["attempts"] == 4
        assert row["next_retry_at"] is None  # Dead Letter
    assert w.metrics()["dead_letters"] == 1
    assert _count(engine) == 1  # 不丢事件
    w.stop()


def test_worker_cleans_expired_idempotency(engine):
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        repo.write_idempotency_cache(conn, user_id="u1", session_id="s1", idempotency_key="old", response={})
        conn.execute(
            repo.idempotency_cache.update().where(
                repo.idempotency_cache.c.idempotency_key == "old"
            ).values(expires_at=(now - timedelta(hours=1)).isoformat())
        )
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3)
    w._poll_once()  # 无 pending 事件，但顺带清理过期幂等缓存
    with engine.connect() as conn:
        remaining = conn.execute(
            select(func.count()).select_from(repo.idempotency_cache)
        ).scalar()
    assert remaining == 0
    w.stop()


def test_worker_metrics_backlog(engine):
    _enqueue(engine, aggregate_id="a")
    _enqueue(engine, aggregate_id="b")
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3)
    m = w.metrics()
    assert m["backlog"] == 2
    assert m["oldest_pending_created_at"] is not None
    w.stop()


def test_worker_start_stop_lifecycle(engine):
    _enqueue(engine)
    w = OutboxWorker(engine, poll_interval_s=1, max_retries=3, consumer=lambda p: None)
    w.start()
    w.start()  # 幂等：已启动忽略
    # 等待消费
    deadline = datetime.now(timezone.utc) + timedelta(seconds=5)
    while _count(engine) > 0 and datetime.now(timezone.utc) < deadline:
        import time

        time.sleep(0.1)
    w.stop()
    assert _count(engine) == 0
