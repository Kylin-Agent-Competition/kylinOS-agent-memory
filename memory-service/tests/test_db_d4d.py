"""D4D 数据库层测试：FRZ-DB-001/003/005、附录 A/B（引擎 / DAO / UoW / 幂等 / Outbox）"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from db import repositories as repo
from db.engine import create_db_engine, init_schema, is_locked_error
from db.schema import FTS5_DDL, memory_entries
from db.uow import UnitOfWork


@pytest.fixture()
def engine(tmp_path):
    eng = create_db_engine(str(tmp_path / "test.db"))
    init_schema(eng)
    yield eng
    eng.dispose()


# ── FR-DB-003 连接与 PRAGMA ──


def test_wal_mode(engine):
    with engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
    assert mode == "wal"


def test_foreign_keys_on(engine):
    with engine.connect() as conn:
        fk = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
    assert fk == 1


def test_init_schema_idempotent(tmp_path):
    """init_schema() 二次调用不得崩溃（触发器幂等，修复 L2 补录根因）。

    修复前：FTS_TRIGGERS_DDL 四条 CREATE TRIGGER 无条件执行，二次调用即
    `sqlite3.OperationalError: trigger memory_fts_ai already exists`。
    修复后：DDL 使用 `CREATE TRIGGER IF NOT EXISTS`，重复调用静默通过。
    """
    eng = create_db_engine(str(tmp_path / "idem.db"))
    init_schema(eng)  # 第一次
    init_schema(eng)  # 第二次：修复前崩溃，修复后应无异常
    # 触发器仍只有一个实例（未重复创建）
    with eng.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master "
            "WHERE type='trigger' AND name LIKE 'memory_fts_%'"
        ).all()
    names = sorted(r[0] for r in rows)
    assert names == ["memory_fts_ad", "memory_fts_ai", "memory_fts_au_content", "memory_fts_au_deleted"]
    eng.dispose()


def test_tables_exist(engine):
    with engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).all()
        }
    assert {"conversations", "turns", "memory_entries", "outbox", "idempotency_cache", "memory_fts"} <= tables


def test_frozen_indexes_exist(engine):
    with engine.connect() as conn:
        idxs = {
            r[0]
            for r in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).all()
        }
    assert {"idx_turns_session", "idx_memory_user_type", "idx_memory_deleted", "idx_outbox_pending", "idx_idempotency_expires"} <= idxs


# ── FRZ-DB-001 约束 ──


def test_entry_type_check_constraint(engine):
    with pytest.raises(Exception):
        with engine.begin() as conn:
            repo.insert_memory_entry(conn, user_id="u1", entry_type="invalid_type", content={"x": 1})


def test_idempotency_composite_pk(engine):
    with engine.begin() as conn:
        repo.write_idempotency_cache(conn, user_id="u1", session_id="s1", idempotency_key="k1", response={"ok": 1})
        # 复合 PK (user_id, session_id, idempotency_key)：同三元组重复插入冲突
        with pytest.raises(Exception):
            repo.write_idempotency_cache(conn, user_id="u1", session_id="s1", idempotency_key="k1", response={"ok": 2})
        # 不同 user_id 允许
        repo.write_idempotency_cache(conn, user_id="u2", session_id="s1", idempotency_key="k1", response={"ok": 3})


# ── DAO CRUD ──


def test_turn_with_outbox_same_transaction_commit(engine):
    with UnitOfWork(engine) as uow:
        result = uow.save_turn_with_outbox(
            user_id="u1", session_id="s1", turn_index=1,
            original_user_text="你好", model_request="<injected>你好</injected>", is_end=1,
        )
        turn_id = result["turn_id"]
    assert turn_id > 0
    with engine.connect() as conn:
        turn = repo.get_turn(conn, turn_id=turn_id)
        assert turn["original_user_text"] == "你好"
        assert turn["is_end"] == 1
        pending = repo.claim_pending_outbox(conn, now_iso=datetime.now(timezone.utc).isoformat(), max_retries=3)
        assert len(pending) == 1
        assert pending[0]["aggregate_type"] == "turn"
        assert pending[0]["event_type"] == repo.EVENT_TURN_FINALIZED


def test_uow_rollback_atomic(engine):
    # 业务写 + Outbox 入队同事务：中途异常 → 全部回滚
    with pytest.raises(RuntimeError):
        with UnitOfWork(engine) as uow:
            uow.save_turn_with_outbox(
                user_id="u1", session_id="s2", turn_index=1, original_user_text="x"
            )
            raise RuntimeError("boom")
    with engine.connect() as conn:
        assert repo.get_conversation(conn, session_id="s2") is None
        pending = repo.claim_pending_outbox(conn, now_iso=datetime.now(timezone.utc).isoformat(), max_retries=3)
        assert len(pending) == 0


def test_memory_entry_soft_delete_fts_sync(engine):
    with engine.begin() as conn:
        eid = repo.insert_memory_entry(
            conn, user_id="u1", entry_type="knowledge", content={"text": "银河麒麟桌面系统"}, confidence=0.9
        )
    # FTS 命中：unicode61 将连续中文视为单个 token，用完整 token 匹配（真实语义）
    with engine.connect() as conn:
        hit = conn.exec_driver_sql(
            "SELECT count(*) FROM memory_fts WHERE memory_fts MATCH '银河麒麟桌面系统'"
        ).scalar()
        assert hit == 1
    # 乐观锁软删除
    with engine.begin() as conn:
        affected = repo.soft_delete_memory_entry(conn, entry_id=eid, user_id="u1", current_version=1)
        assert affected == 1
    # 软删除后 FTS 不再命中（冻结文档 §2.4 软删除同步）
    with engine.connect() as conn:
        hit = conn.exec_driver_sql(
            "SELECT count(*) FROM memory_fts WHERE memory_fts MATCH '银河麒麟桌面系统'"
        ).scalar()
        assert hit == 0
        # 审计/恢复数据源保留 is_deleted=1 记录
        row = conn.execute(
            memory_entries.select().where(memory_entries.c.id == eid)
        ).mappings().first()
        assert row["is_deleted"] == 1
        assert row["version"] == 2


def test_memory_entry_optimistic_lock_conflict(engine):
    with engine.begin() as conn:
        eid = repo.insert_memory_entry(conn, user_id="u1", entry_type="preference", content={"k": "v"})
    # 版本不匹配 → 0 行受影响（调用方重试或放弃）
    with engine.begin() as conn:
        affected = repo.soft_delete_memory_entry(conn, entry_id=eid, user_id="u1", current_version=99)
        assert affected == 0


# ── 附录 A 幂等 ──


def test_idempotent_hit_returns_cache(engine):
    calls = {"n": 0}

    def business():
        calls["n"] += 1
        return {"result": calls["n"]}

    with UnitOfWork(engine) as uow:
        r1, from_cache1 = uow.execute_idempotent(
            user_id="u1", session_id="s1", idempotency_key="k1", business_fn=business
        )
    with UnitOfWork(engine) as uow:
        r2, from_cache2 = uow.execute_idempotent(
            user_id="u1", session_id="s1", idempotency_key="k1", business_fn=business
        )
    assert r1 == {"result": 1}
    assert r2 == {"result": 1}  # 同 key 重复请求返回第一次响应
    assert from_cache1 is False
    assert from_cache2 is True
    assert calls["n"] == 1  # 副作用仅执行一次


def test_idempotent_expired_ttl_reexecute(engine):
    calls = {"n": 0}

    def business():
        calls["n"] += 1
        return {"result": calls["n"]}

    with UnitOfWork(engine) as uow:
        # 写一个已过期缓存（expires_at 在过去）
        from datetime import datetime, timedelta, timezone
        past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        repo.write_idempotency_cache(
            uow.conn, user_id="u1", session_id="s1", idempotency_key="k1",
            response={"result": 0},
        )
        uow.conn.execute(
            repo.idempotency_cache.update().where(
                repo.idempotency_cache.c.idempotency_key == "k1"
            ).values(expires_at=past)
        )
    with UnitOfWork(engine) as uow:
        r, from_cache = uow.execute_idempotent(
            user_id="u1", session_id="s1", idempotency_key="k1", business_fn=business
        )
    assert from_cache is False
    assert r == {"result": 1}


def test_idempotent_concurrent_conflict_returns_first(engine):
    # 模拟并发双写：先手工占用三元组，再执行 → IntegrityError 兜底回查（不视为错误）
    with engine.begin() as conn:
        repo.write_idempotency_cache(
            conn, user_id="u1", session_id="s1", idempotency_key="k9", response={"result": "first"}
        )
    with UnitOfWork(engine) as uow:
        r, from_cache = uow.execute_idempotent(
            user_id="u1", session_id="s1", idempotency_key="k9", business_fn=lambda: {"result": "second"}
        )
    assert from_cache is True
    assert r == {"result": "first"}


# ── 附录 B Outbox 失败路由 ──


def test_outbox_retry_backoff(engine):
    with engine.begin() as conn:
        eid = repo.enqueue_outbox(
            conn, aggregate_type="turn", aggregate_id="1", event_type=repo.EVENT_TURN_FINALIZED,
            payload={"turn_id": 1}, next_retry_at=datetime.now(timezone.utc).isoformat(),
        )
    now = datetime.now(timezone.utc)
    # 第一次失败：attempts 0→1，next_retry_at = now + 2^1 * 30s = +60s
    with engine.begin() as conn:
        repo.mark_outbox_failure(
            conn, outbox_id=eid, attempts=1,
            next_retry_at=(now + timedelta(seconds=60)).isoformat(), last_error="embed failed",
        )
    with engine.connect() as conn:
        row = conn.execute(repo.outbox.select().where(repo.outbox.c.id == eid)).mappings().first()
        assert row["attempts"] == 1
        assert row["last_error"] == "embed failed"
        # 未到 next_retry_at 不取
        pending = repo.claim_pending_outbox(
            conn, now_iso=now.isoformat(), max_retries=3
        )
        assert len(pending) == 0
        pending2 = repo.claim_pending_outbox(
            conn, now_iso=(now + timedelta(seconds=61)).isoformat(), max_retries=3
        )
        assert len(pending2) == 1


def test_outbox_dead_letter_after_max_retries(engine):
    with engine.begin() as conn:
        eid = repo.enqueue_outbox(
            conn, aggregate_type="turn", aggregate_id="2", event_type=repo.EVENT_TURN_FINALIZED,
            payload={"turn_id": 2}, next_retry_at=datetime.now(timezone.utc).isoformat(),
        )
        # attempts 已到 3（max_retries）后再次失败 → Dead Letter
        repo.mark_outbox_dead_letter(conn, outbox_id=eid, attempts=4, last_error="still failing")
    with engine.connect() as conn:
        row = conn.execute(repo.outbox.select().where(repo.outbox.c.id == eid)).mappings().first()
        assert row["next_retry_at"] is None  # 保留记录（不丢事件）
        assert row["last_error"] == "still failing"
        # 不再被轮询
        pending = repo.claim_pending_outbox(
            conn, now_iso=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), max_retries=3
        )
        assert len(pending) == 0


def test_cleanup_expired_idempotency(engine):
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        repo.write_idempotency_cache(conn, user_id="u1", session_id="s1", idempotency_key="old", response={})
        conn.execute(
            repo.idempotency_cache.update().where(
                repo.idempotency_cache.c.idempotency_key == "old"
            ).values(expires_at=(now - timedelta(hours=1)).isoformat())
        )
        repo.write_idempotency_cache(conn, user_id="u1", session_id="s1", idempotency_key="fresh", response={})
    with engine.begin() as conn:
        cleaned = repo.cleanup_expired_idempotency(conn, now_iso=now.isoformat())
    assert cleaned == 1
    with engine.connect() as conn:
        remaining = conn.execute(
            repo.idempotency_cache.select().where(repo.idempotency_cache.c.idempotency_key == "fresh")
        ).first()
        assert remaining is not None


# ── 用户隔离 ──


def test_list_memory_entries_user_isolation(engine):
    with engine.begin() as conn:
        repo.insert_memory_entry(conn, user_id="u1", entry_type="preference", content={"a": 1})
        repo.insert_memory_entry(conn, user_id="u2", entry_type="preference", content={"b": 2})
    with engine.connect() as conn:
        rows_u1 = repo.list_memory_entries(conn, user_id="u1")
        rows_u2 = repo.list_memory_entries(conn, user_id="u2")
    assert len(rows_u1) == 1 and rows_u1[0]["content"].startswith("{")
    assert len(rows_u2) == 1
    assert json.loads(rows_u1[0]["content"]) == {"a": 1}


# ── busy 错误识别（FR-DB-003：SQLITE_BUSY → 降级，不阻塞聊天） ──


def test_is_locked_error_recognizes_operational():
    from sqlalchemy.exc import OperationalError

    exc = OperationalError("stmt", {}, Exception("database is locked"))
    assert is_locked_error(exc)
    assert not is_locked_error(ValueError("x"))
