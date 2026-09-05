"""D4D 数据库层测试：FRZ-DB-001/003/005、附录 A/B（引擎 / DAO / UoW / 幂等 / Outbox）"""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timedelta, timezone

import pytest

from db import repositories as repo
from db.engine import create_db_engine, has_alembic_version, init_schema, is_locked_error
from db.schema import memory_entries
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


def test_db_file_permission_0600(tmp_path):
    """D6-D MEDIUM-02：DB 创建后显式收紧 0600（仅属主可读写）。

    任务卡红线：不修改 chmod 失败不阻断语义（无权限环境仅 warning）；
    本用例验证正常路径下 DB 文件权限为 0600（POSIX；Windows 平台无 posix 权限跳过）。
    """
    if not hasattr(os, "chmod") or os.name == "nt":
        pytest.skip("POSIX file mode 不适用于当前平台")
    db_path = tmp_path / "perm_check.db"
    eng = create_db_engine(str(db_path))
    # SQLite 惰性建文件：首次连接触发 connect 事件（其中收紧 0600）
    with eng.connect():
        pass
    eng.dispose()
    mode = stat.S_IMODE(os.stat(db_path).st_mode)
    assert mode == 0o600


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


def test_has_alembic_version_false_after_init_schema(tmp_path):
    """PR#52 Issue 6：init_schema（create_all）不产生 alembic_version 表。

    alembic_version 是 Alembic 迁移的唯一真源标记；create_all 路径不得伪装成
    "已迁移"。生产模式启动校验依赖此区分——init_schema 后应为 False，
    手动建表（等价 alembic upgrade head 落表）后为 True。
    """
    eng = create_db_engine(str(tmp_path / "av_check.db"))
    init_schema(eng)
    assert has_alembic_version(eng) is False
    # 等价 alembic upgrade head 落表后的标记表
    with eng.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
    assert has_alembic_version(eng) is True
    eng.dispose()


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
        turn = repo.get_turn(conn, turn_id=turn_id, user_id="u1")
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
        assert repo.get_conversation(conn, session_id="s2", user_id="u1") is None
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
        # ADR-017：内容/索引版本保持不变；业务写入的 CAS token 是 row_revision。
        assert row["version"] == 1
        assert row["row_revision"] == 2


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


def test_cleanup_expired_idempotency_respects_limit_and_keeps_fresh_rows(engine):
    """清理 DAO 只删除最早到期的限定行，不依赖 SQLite DELETE...LIMIT 扩展。"""
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        for key, offset_minutes in (("expired-3", -3), ("expired-2", -2), ("expired-1", -1)):
            repo.write_idempotency_cache(
                conn, user_id="u1", session_id="s1", idempotency_key=key, response={}
            )
            conn.execute(
                repo.idempotency_cache.update()
                .where(repo.idempotency_cache.c.idempotency_key == key)
                .values(expires_at=(now + timedelta(minutes=offset_minutes)).isoformat())
            )
        repo.write_idempotency_cache(
            conn, user_id="u1", session_id="s1", idempotency_key="fresh", response={}
        )

    with engine.begin() as conn:
        assert repo.cleanup_expired_idempotency(conn, now_iso=now.isoformat(), limit=2) == 2
    with engine.connect() as conn:
        keys = set(conn.execute(
            repo.idempotency_cache.select().with_only_columns(repo.idempotency_cache.c.idempotency_key)
        ).scalars())
    assert keys == {"expired-1", "fresh"}


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


# ── PR#52 审查修复回归 ──


def test_get_turn_user_isolation(engine):
    """PR#52 Issue 2：get_turn/get_conversation 必须强制 user_id 过滤（跨用户隔离）。"""
    with UnitOfWork(engine) as uow:
        result = uow.save_turn_with_outbox(
            user_id="u1", session_id="iso-s1", turn_index=1, original_user_text="秘密原文"
        )
        turn_id = result["turn_id"]
    with engine.connect() as conn:
        assert repo.get_turn(conn, turn_id=turn_id, user_id="u1") is not None
        assert repo.get_turn(conn, turn_id=turn_id, user_id="u2") is None
        assert repo.get_conversation(conn, session_id="iso-s1", user_id="u1") is not None
        assert repo.get_conversation(conn, session_id="iso-s1", user_id="u2") is None


def test_fts_update_syncs_entry_type_and_user_id(engine):
    """PR#52 Issue 11：UPDATE entry_type/user_id（content 不变）也应刷新 FTS 索引。"""
    with engine.begin() as conn:
        eid = repo.insert_memory_entry(
            conn, user_id="u1", entry_type="preference", content={"text": "偏好A"}
        )
        conn.execute(
            memory_entries.update()
            .where(memory_entries.c.id == eid)
            .values(entry_type="knowledge", user_id="u2")
        )
    with engine.connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT entry_type, user_id FROM memory_fts WHERE rowid = ?", (eid,)
        ).first()
    assert row is not None
    assert row[0] == "knowledge"
    assert row[1] == "u2"
