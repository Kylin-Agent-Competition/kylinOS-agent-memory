"""TD-028：真实 IntegrityError 竞态回查分支测试（PR #65 登记缺口）。

背景：`UnitOfWork.execute_idempotent` 的 `except IntegrityError:` 分支（并发双写时
复合 PK/部分唯一索引兜底 → 回查缓存 → fingerprint 比对 → 返回首次响应）在
PR #65 合并时缺少真实触发测试（原 `test_t3_concurrent_integrity_idempotency_unwrap`
走「预写缓存 → 普通缓存命中」路径，未真正进入 except 分支）。

本文件用真实 SQLite 约束（idx_turns_host_turn_id 部分唯一索引 / idempotency_cache
复合 PK）受控触发 IntegrityError，覆盖 TD-028 验收标准 6 条。
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from db import repositories as repo
from db.engine import create_db_engine, init_schema
from db.uow import UnitOfWork


@pytest.fixture
def td028_env(tmp_path):
    """TD-028 专用：内存引擎 + 预置 conversation/turn 基线。"""
    eng = create_db_engine(str(tmp_path / "td028.db"))
    init_schema(eng)
    # 预置 conversation（turns.session_id 外键约束）
    with UnitOfWork(eng) as uow:
        repo.upsert_conversation(uow.conn, user_id="uA", session_id="s1")
        # 基线 turn：占用 (s1, H-1) 的部分唯一索引（模拟并发另一请求已落库）
        repo.insert_turn(
            uow.conn,
            session_id="s1",
            turn_index=1,
            original_user_text="TD-028 基线正文",
            host_turn_id="H-1",
        )
    yield {"engine": eng}
    # 无需清理（tmp_path 自动回收）


# ── 场景 1：fingerprint 一致 → 回查返回首次响应（from_cache=True） ──


def test_td028_race_fingerprint_match_returns_first(td028_env):
    """验收 1/2/3/4/6：首次缓存未命中；business_fn 内真实触发 IntegrityError
    （turns 部分唯一索引冲突）；进入 except 回查分支；fingerprint 一致时
    返回首次缓存响应；不产生重复 Turn/Outbox/幂等副作用。"""
    eng = td028_env["engine"]
    first = {"db_turn_id": 1, "host_turn_id": "H-1", "conversation_id": 1, "ok": "first"}

    with UnitOfWork(eng) as uow:
        def business_fn():
            # 模拟并发另一请求已完成：同三元组缓存已写入（fp-A）
            repo.write_idempotency_cache(
                uow.conn,
                user_id="uA",
                session_id="s1",
                idempotency_key="idem-1",
                response=repo._wrap_response(first, "fp-A"),
            )
            # 真实业务副作用：尝试插入同 (s1, H-1) turn → 撞部分唯一索引 → IntegrityError
            repo.insert_turn(
                uow.conn,
                session_id="s1",
                turn_index=2,
                original_user_text="TD-028 重复写入",
                host_turn_id="H-1",
            )
            return {"db_turn_id": 999, "ok": "second"}

        resp, from_cache = uow.execute_idempotent(
            user_id="uA",
            session_id="s1",
            idempotency_key="idem-1",
            business_fn=business_fn,
            request_fingerprint="fp-A",
        )

    # 进入 except IntegrityError 回查分支：返回首次缓存，未执行业务副作用
    assert from_cache is True
    assert resp == first
    # 无重复副作用：turns 仍 1 行；outbox 0；幂等缓存 1 行
    with UnitOfWork(eng) as uow:
        turns_n = len(uow.conn.execute(repo.select(repo.turns.c.id)).fetchall())
        outbox_n = len(uow.conn.execute(repo.select(repo.outbox.c.id)).fetchall())
        cache_n = len(uow.conn.execute(
            repo.select(repo.idempotency_cache.c.idempotency_key)
        ).fetchall())
    assert turns_n == 1, f"turns 应 1 行，实际 {turns_n}"
    assert outbox_n == 0, f"outbox 应 0 行，实际 {outbox_n}"
    assert cache_n == 1, f"幂等缓存应 1 行，实际 {cache_n}"


# ── 场景 2：fingerprint 不一致 → 安全拒绝（IdempotencyConflictError） ──


def test_td028_race_fingerprint_conflict_rejected(td028_env):
    """验收 5：回查缓存 fingerprint 不一致 → IdempotencyConflictError（安全拒绝），
    不产生重复副作用。"""
    eng = td028_env["engine"]
    first = {"db_turn_id": 1, "host_turn_id": "H-1", "conversation_id": 1, "ok": "first"}

    with pytest.raises(repo.IdempotencyConflictError):
        with UnitOfWork(eng) as uow:
            def business_fn():
                # 缓存已由「另一请求」以 fp-A 写入
                repo.write_idempotency_cache(
                    uow.conn,
                    user_id="uA",
                    session_id="s1",
                    idempotency_key="idem-1",
                    response=repo._wrap_response(first, "fp-A"),
                )
                # 真实触发 IntegrityError（同 (s1, H-1) 唯一索引冲突）
                repo.insert_turn(
                    uow.conn,
                    session_id="s1",
                    turn_index=2,
                    original_user_text="TD-028 冲突写入",
                    host_turn_id="H-1",
                )
                return {"db_turn_id": 999, "ok": "second"}

            uow.execute_idempotent(
                user_id="uA",
                session_id="s1",
                idempotency_key="idem-1",
                business_fn=business_fn,
                request_fingerprint="fp-B",  # 与缓存指纹 fp-A 不一致
            )

    # 无副作用残留：turns 1 行 / outbox 0 / 缓存 0 行。
    # 说明：本场景的 fp-A 缓存由 business_fn 在同一事务内写入；IdempotencyConflictError
    # 上抛后 UoW 整体 rollback，缓存随事务一并回滚 → 冲突请求不留下任何半写缓存
    # （不含 fp-B 覆盖、不含半成品），这是比「保留缓存」更强的无副作用语义。
    with UnitOfWork(eng) as uow:
        turns_n = len(uow.conn.execute(repo.select(repo.turns.c.id)).fetchall())
        outbox_n = len(uow.conn.execute(repo.select(repo.outbox.c.id)).fetchall())
        cache_n = len(uow.conn.execute(
            repo.select(repo.idempotency_cache.c.idempotency_key)
        ).fetchall())
    assert turns_n == 1, f"turns 应 1 行，实际 {turns_n}"
    assert outbox_n == 0, f"outbox 应 0 行，实际 {outbox_n}"
    assert cache_n == 0, f"冲突拒绝不得残留幂等缓存，实际 {cache_n}"


# ── 场景 3：回查无缓存 → 原样抛错（不吞异常） ──


def test_td028_race_no_cache_reraises(td028_env):
    """验收 3 补充：进入 except 分支但回查无有效缓存 → 重新抛出 IntegrityError，
    不假装成功、不产生半成品。"""
    eng = td028_env["engine"]

    with pytest.raises(IntegrityError):
        with UnitOfWork(eng) as uow:
            def business_fn():
                # 不写缓存（首次查询未命中，且无并发方提供缓存）：
                # 直接撞 turns 部分唯一索引 → 真实 IntegrityError
                repo.insert_turn(
                    uow.conn,
                    session_id="s1",
                    turn_index=2,
                    original_user_text="TD-028 无缓存冲突",
                    host_turn_id="H-1",
                )
                return {"db_turn_id": 999, "ok": "second"}

            uow.execute_idempotent(
                user_id="uA",
                session_id="s1",
                idempotency_key="idem-1",
                business_fn=business_fn,
                request_fingerprint="fp-A",
            )

    # 无副作用残留：turns 1 行 / outbox 0 / 缓存 0（失败不缓存）
    with UnitOfWork(eng) as uow:
        turns_n = len(uow.conn.execute(repo.select(repo.turns.c.id)).fetchall())
        outbox_n = len(uow.conn.execute(repo.select(repo.outbox.c.id)).fetchall())
        cache_n = len(uow.conn.execute(
            repo.select(repo.idempotency_cache.c.idempotency_key)
        ).fetchall())
    assert turns_n == 1
    assert outbox_n == 0
    assert cache_n == 0, "失败请求不得写入幂等缓存"
