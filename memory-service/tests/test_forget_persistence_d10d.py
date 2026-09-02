"""D10-D 精准遗忘持久化 L1 测试（ADR-015/019；契约 v0.3 §九；任务卡 §六 20 项）。

覆盖维度（对齐任务卡 §六）：
  A. 正向：forget_plan 落库 + preview 凭据（哈希 + selection_hash 绑定）；execute 软删 + 审计同事务
  B. 凭据/幂等：无效/过期/已消费 → INVALID_REQUEST 零副作用；幂等重放；幂等键复用冲突
  C. 隔离：跨用户 forget_plan/凭据 → INVALID_REQUEST；跨用户 affected_count=0
  D. Outbox priority：forget 事件优先于普通索引任务
  E. 软删 + FTS 同步；事务失败整体回滚；Gate 误删=0
  F. fail-closed：hard/cascade/full_reset/topic/time_window/event/all
  G. Gateway activation：未注册 → UNSUPPORTED_METHOD；preview→execute 端到端；trusted identity cache-bypass
  H. 安全：selector 明文生命周期（HIGH-01）；零正文 Sentinel；request_fingerprint 敏感占位
  I. 迁移：single head + upgrade/downgrade 往返 + schema 对照
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from db import repositories as repo
from db.engine import create_db_engine, init_schema
from db.uow import UnitOfWork
from app import build_parser
from gateway.forget_handlers import register_forget_handlers
from gateway.handlers import register_default_handlers
from gateway.protocol import RequestValidationError
from gateway.registry import HandlerRegistry, RequestContext, UnsupportedMethodError

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "migrations"

USER = "u1"
OTHER = "u2"


# ── 场景构造 ──


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload(**over) -> dict:
    p = {
        "forget_plan_id": "plan-1",
        "user_id": USER,
        "forget_mode": "single_item",
        "target_selector": "删除这条关于深色主题的偏好",
        "target_type": "knowledge",
        "target_id": "1",
        "requires_confirmation": True,
    }
    p.update(over)
    return p


class _TrustedIdentity:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id


@pytest.fixture()
def env(tmp_path):
    eng = create_db_engine(str(tmp_path / "d10d.db"))
    init_schema(eng)
    registry = HandlerRegistry()
    register_default_handlers(registry)

    def _uow_factory():
        return UnitOfWork(eng)

    register_forget_handlers(registry, uow_factory=_uow_factory)

    def invoke(method, payload, *, trace_id="trc-1", idem_key=None):
        h = registry.route(method)
        ctx = RequestContext(
            request_id="req-1",
            trace_id=trace_id,
            method=method,
            deadline_ms=5000,
            idempotency_key=idem_key,
        )
        return h(payload, ctx)

    yield {"engine": eng, "invoke": invoke, "registry": registry}
    eng.dispose()


@pytest.fixture()
def env_trusted(tmp_path):
    eng = create_db_engine(str(tmp_path / "d10d_trusted.db"))
    init_schema(eng)
    registry = HandlerRegistry()
    register_default_handlers(registry)
    trusted = _TrustedIdentity(USER)

    def _uow_factory():
        return UnitOfWork(eng)

    register_forget_handlers(registry, uow_factory=_uow_factory, trusted_identity=trusted)

    def invoke(method, payload, *, trace_id="trc-1", idem_key=None):
        h = registry.route(method)
        ctx = RequestContext(
            request_id="req-1",
            trace_id=trace_id,
            method=method,
            deadline_ms=5000,
            idempotency_key=idem_key,
        )
        return h(payload, ctx)

    yield {"engine": eng, "invoke": invoke, "trusted": trusted}
    eng.dispose()


def _seed_knowledge(engine, *, user_id=USER, content="深色主题偏好", entry_type="knowledge") -> int:
    with engine.begin() as conn:
        return repo.insert_memory_entry(
            conn, user_id=user_id, entry_type=entry_type, content={"value": content}
        )


def _seed_preference(engine, *, user_id=USER, key="theme", scope="global", value="dark") -> int:
    with engine.begin() as conn:
        repo.save_preference_version(
            conn,
            user_id=user_id,
            preference_key=key,
            preference_scope=scope,
            preference_value=value,
            memory_status="active",
            evidence_fingerprint=f"ev-{key}",
            idempotency_key=None,
            request_fingerprint=f"fp-{key}",
        )
        row = conn.exec_driver_sql(
            "SELECT id FROM memory_items WHERE user_id=? AND preference_key=? AND preference_scope=?",
            (user_id, key, scope),
        ).first()
    return int(row[0])


def _preview(env, payload=None, *, idem_key="preview-1"):
    return env["invoke"]("forget.preview", payload or _payload(), idem_key=idem_key)


# ── A. 正向 ──


def test_preview_persists_plan_and_credential_hash(env):
    entry_id = _seed_knowledge(env["engine"])
    resp = _preview(env, _payload(target_id=str(entry_id), target_type="knowledge"))
    assert resp["status"] == "awaiting_confirmation"
    assert resp["resolved_target_ids"] == [str(entry_id)]
    assert resp["affected_count"] == 1
    assert resp["requires_confirmation"] is True
    assert resp["delete_mode"] == "soft"
    # 凭据明文只回传一次，且非哈希
    assert isinstance(resp["confirmation_token"], str) and len(resp["confirmation_token"]) == 64
    assert resp["credential_ttl_seconds"] == repo.CONFIRMATION_TOKEN_TTL_SECONDS

    with env["engine"].connect() as conn:
        plan = repo.get_forget_plan_by_id(conn, user_id=USER, forget_plan_id="plan-1")
        assert plan is not None
        assert plan["status"] == "awaiting_confirmation"
        # 服务端只存 SHA-256 哈希，明文不落库
        assert plan["confirmation_token"] == repo.hash_confirmation_token(resp["confirmation_token"])
        assert plan["confirmation_token"] != resp["confirmation_token"]
        assert plan["selection_hash"] == repo.compute_selection_hash([str(entry_id)])
        assert plan["affected_count"] == 1

        cached = repo.get_idempotency_cache(
            conn, user_id=USER, session_id="", idempotency_key="preview-1"
        )
        assert cached is not None
        assert resp["confirmation_token"] not in cached["response"]
        cached_response = json.loads(cached["response"])["response"]
        assert "confirmation_token" not in cached_response
        assert cached_response["credential_replayable"] is False


def test_preview_idempotent_replay_does_not_reissue_credential(env):
    entry_id = _seed_knowledge(env["engine"])
    payload = _payload(target_id=str(entry_id), target_type="knowledge")
    first = _preview(env, payload, idem_key="preview-once")
    with pytest.raises(RequestValidationError, match="only returned once"):
        _preview(env, payload, idem_key="preview-once")

    with env["engine"].connect() as conn:
        cached = repo.get_idempotency_cache(
            conn, user_id=USER, session_id="", idempotency_key="preview-once"
        )
        assert first["confirmation_token"] not in cached["response"]


def test_execute_valid_credential_soft_deletes_and_audits(env):
    entry_id = _seed_knowledge(env["engine"])
    prev = _preview(env, _payload(target_id=str(entry_id), target_type="knowledge"))
    token = prev["confirmation_token"]

    resp = env["invoke"](
        "forget.execute",
        {"forget_plan_id": "plan-1", "user_id": USER, "confirmation_token": token},
        idem_key="execute-1",
    )
    assert resp["status"] == "completed"
    assert resp["executed_count"] == 1
    assert resp["affected_count"] == 1
    assert resp["executed_at"] is not None
    assert resp["audit_id"].startswith("fa_")

    with env["engine"].connect() as conn:
        # knowledge 软删（is_deleted=1）
        row = conn.exec_driver_sql(
            "SELECT is_deleted FROM memory_entries WHERE id=?", (entry_id,)
        ).first()
        assert row[0] == 1
        # 凭据已消费（置 NULL）+ 终态
        plan = repo.get_forget_plan_by_id(conn, user_id=USER, forget_plan_id="plan-1")
        assert plan["status"] == "completed"
        assert plan["confirmation_token"] is None
        assert plan["executed_count"] == 1
        # 审计落库（零正文，terminal 必填 executed_at）
        audit = conn.exec_driver_sql(
            "SELECT * FROM forget_audit WHERE forget_plan_id=?", ("plan-1",)
        ).fetchone()
        assert audit is not None
        assert audit[10] is not None  # executed_at 列


def test_execute_preference_uses_removed_status(env):
    item_id = _seed_preference(env["engine"])
    prev = _preview(
        env, _payload(target_id=str(item_id), target_type="preference", forget_plan_id="plan-pref")
    )
    assert prev["resolved_target_ids"] == [str(item_id)]
    resp = env["invoke"](
        "forget.execute",
        {"forget_plan_id": "plan-pref", "user_id": USER, "confirmation_token": prev["confirmation_token"]},
        idem_key="execute-pref-1",
    )
    assert resp["status"] == "completed"

    with env["engine"].connect() as conn:
        cur = repo.get_current_preference_version(
            conn, user_id=USER, preference_key="theme", preference_scope="global"
        )
        assert cur is None or cur["memory_status"] == "removed"


def test_preview_zero_hit_returns_affected_zero(env):
    _seed_knowledge(env["engine"])
    resp = _preview(env, _payload(target_id="999999", target_type="knowledge"))
    assert resp["status"] == "awaiting_confirmation"
    assert resp["resolved_target_ids"] == []
    assert resp["affected_count"] == 0


# ── B. 凭据 / 幂等 ──


def test_execute_invalid_credential_zero_side_effects(env):
    entry_id = _seed_knowledge(env["engine"])
    _preview(env, _payload(target_id=str(entry_id), target_type="knowledge"))
    with pytest.raises(RequestValidationError):
        env["invoke"](
            "forget.execute",
            {"forget_plan_id": "plan-1", "user_id": USER, "confirmation_token": "0" * 64},
            idem_key="execute-bad",
        )
    with env["engine"].connect() as conn:
        plan = repo.get_forget_plan_by_id(conn, user_id=USER, forget_plan_id="plan-1")
        assert plan["status"] == "awaiting_confirmation"  # 未消费、未执行
        assert plan["confirmation_token"] is not None


def test_execute_expired_credential_invalid(env):
    entry_id = _seed_knowledge(env["engine"])
    _preview(env, _payload(target_id=str(entry_id), target_type="knowledge"))
    # 手动回拨过期时间
    with env["engine"].begin() as conn:
        conn.exec_driver_sql(
            "UPDATE forget_plan SET token_expires_at=? WHERE forget_plan_id=?",
            ("2000-01-01T00:00:00+00:00", "plan-1"),
        )
    with pytest.raises(RequestValidationError):
        env["invoke"](
            "forget.execute",
            {"forget_plan_id": "plan-1", "user_id": USER, "confirmation_token": "1" * 64},
            idem_key="execute-exp",
        )


def test_execute_consumed_credential_cannot_replay_with_new_key(env):
    entry_id = _seed_knowledge(env["engine"])
    prev = _preview(env, _payload(target_id=str(entry_id), target_type="knowledge"))
    token = prev["confirmation_token"]
    env["invoke"](
        "forget.execute",
        {"forget_plan_id": "plan-1", "user_id": USER, "confirmation_token": token},
        idem_key="execute-r1",
    )
    # 同一凭据再次 execute（新幂等键，绕过缓存）→ 已消费 → INVALID_REQUEST
    with pytest.raises(RequestValidationError):
        env["invoke"](
            "forget.execute",
            {"forget_plan_id": "plan-1", "user_id": USER, "confirmation_token": token},
            idem_key="execute-r2",
        )


def test_execute_idempotent_replay_returns_first_result(env):
    entry_id = _seed_knowledge(env["engine"])
    prev = _preview(env, _payload(target_id=str(entry_id), target_type="knowledge"))
    token = prev["confirmation_token"]
    payload = {"forget_plan_id": "plan-1", "user_id": USER, "confirmation_token": token}
    r1 = env["invoke"]("forget.execute", payload, idem_key="execute-same")
    r2 = env["invoke"]("forget.execute", payload, idem_key="execute-same")
    assert r1["status"] == "completed"
    assert r2["status"] == "completed"
    assert r2["audit_id"] == r1["audit_id"]  # cache replay 返回首次结果

    with env["engine"].connect() as conn:
        count = conn.exec_driver_sql(
            "SELECT count(*) FROM forget_audit WHERE forget_plan_id=?", ("plan-1",)
        ).fetchone()[0]
        assert count == 1  # 不重复审计


def test_idempotency_key_reuse_different_payload_conflict(env):
    entry_id = _seed_knowledge(env["engine"])
    _preview(env, _payload(target_id=str(entry_id), target_type="knowledge"), idem_key="shared-key")
    with pytest.raises(repo.IdempotencyConflictError):
        _preview(
            env,
            _payload(forget_plan_id="plan-2", target_id=str(entry_id), target_type="knowledge"),
            idem_key="shared-key",
        )


# ── C. 隔离 ──


def test_cross_user_cannot_access_forget_plan(env):
    entry_id = _seed_knowledge(env["engine"], user_id=USER)
    _preview(env, _payload(target_id=str(entry_id), target_type="knowledge"))
    # 其他用户 execute 该计划 → 计划不存在于其归属 → INVALID_REQUEST
    with pytest.raises(RequestValidationError):
        env["invoke"](
            "forget.execute",
            {"forget_plan_id": "plan-1", "user_id": OTHER, "confirmation_token": "1" * 64},
            idem_key="execute-xu",
        )


def test_cross_user_zero_affected_count(env):
    entry_id = _seed_knowledge(env["engine"], user_id=OTHER)
    # 用户 B 的计划解析目标为用户 B 的数据；当前用户 u1 无法命中 B 的条目（隔离）
    _seed_knowledge(env["engine"], user_id=USER)  # u1 自己有一条
    resp = _preview(env, _payload(target_id=str(entry_id), target_type="knowledge", user_id=USER))
    assert resp["affected_count"] == 0  # 跨用户目标不进 resolved_target_ids
    assert resp["resolved_target_ids"] == []


def test_session_resolver_rejects_mismatched_memory_entry_owner(env):
    now = _now_iso()
    with env["engine"].begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO conversations(user_id, session_id, started_at) VALUES (?, ?, ?)",
            (USER, "session-owned-by-u1", now),
        )
        turn_id = conn.exec_driver_sql(
            "INSERT INTO turns(session_id, turn_index, original_user_text, is_end, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("session-owned-by-u1", 1, "source", 1, now),
        ).lastrowid
        polluted_entry_id = conn.exec_driver_sql(
            "INSERT INTO memory_entries(user_id, entry_type, content, source_turn_id, "
            "confidence, version, is_deleted, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (OTHER, "knowledge", '{"value":"other-user"}', turn_id, 1.0, 1, 0, now, now),
        ).lastrowid

    response = _preview(
        env,
        _payload(
            forget_mode="session",
            target_id=None,
            target_session_id="session-owned-by-u1",
            target_type="knowledge",
        ),
        idem_key="preview-session-isolation",
    )
    assert response["affected_count"] == 0
    assert str(polluted_entry_id) not in response["resolved_target_ids"]


# ── D. Outbox priority ──


def test_outbox_priority_forget_before_normal(env):
    with env["engine"].begin() as conn:
        # 普通任务先入队（priority=0，next_retry_at 更早）
        repo.enqueue_outbox(
            conn,
            aggregate_type="memory",
            aggregate_id="m1",
            event_type=repo.EVENT_MEMORY_UPSERTED,
            payload={"event_id": "e1"},
            next_retry_at="2026-09-01T00:00:00+00:00",
        )
        # forget 任务后入队（priority=1，next_retry_at 更晚）
        repo.enqueue_outbox(
            conn,
            aggregate_type="forget",
            aggregate_id="f1",
            event_type=repo.EVENT_FORGET_EXECUTED,
            payload={"event_id": "e2"},
            next_retry_at="2026-09-01T10:00:00+00:00",
            priority=repo.FORGET_PRIORITY,
        )
    with env["engine"].connect() as conn:
        claimed = repo.claim_pending_outbox(
            conn, now_iso="2026-09-02T00:00:00+00:00", max_retries=3, limit=10
        )
    assert claimed[0]["event_type"] == repo.EVENT_FORGET_EXECUTED  # 优先消费 forget


def test_outbox_null_priority_orders_as_zero(env):
    with env["engine"].begin() as conn:
        repo.enqueue_outbox(
            conn,
            aggregate_type="memory",
            aggregate_id="zero",
            event_type=repo.EVENT_MEMORY_UPSERTED,
            payload={"event_id": "zero"},
            next_retry_at="2026-09-01T10:00:00+00:00",
            priority=0,
        )
        conn.exec_driver_sql(
            "INSERT INTO outbox(aggregate_type, aggregate_id, event_type, payload, attempts, "
            "next_retry_at, created_at, priority) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                "memory",
                "null",
                repo.EVENT_MEMORY_UPSERTED,
                '{"event_id":"null"}',
                0,
                "2026-09-01T00:00:00+00:00",
                _now_iso(),
            ),
        )
    with env["engine"].connect() as conn:
        claimed = repo.claim_pending_outbox(
            conn, now_iso="2026-09-02T00:00:00+00:00", max_retries=3, limit=10
        )
    assert [row["aggregate_id"] for row in claimed] == ["null", "zero"]


# ── E. 软删 + FTS / 事务 / Gate ──


def test_soft_delete_removes_from_fts(env):
    entry_id = _seed_knowledge(env["engine"], content="独一无二的哨兵语句")
    with env["engine"].connect() as conn:
        hit = conn.exec_driver_sql(
            "SELECT rowid FROM memory_fts WHERE memory_fts MATCH ?", ("独一无二的哨兵语句",)
        ).fetchall()
        assert len(hit) >= 1  # 软删前 FTS 命中

    prev = _preview(env, _payload(target_id=str(entry_id), target_type="knowledge"))
    env["invoke"](
        "forget.execute",
        {"forget_plan_id": "plan-1", "user_id": USER, "confirmation_token": prev["confirmation_token"]},
        idem_key="execute-fts",
    )

    with env["engine"].connect() as conn:
        hit = conn.exec_driver_sql(
            "SELECT rowid FROM memory_fts WHERE memory_fts MATCH ?", ("独一无二的哨兵语句",)
        ).fetchall()
        assert len(hit) == 0  # FTS 触发器同步移除


def test_gate_no_false_delete_other_entries_unaffected(env):
    entry_a = _seed_knowledge(env["engine"], content="A")
    entry_b = _seed_knowledge(env["engine"], content="B")
    prev = _preview(env, _payload(target_id=str(entry_a), target_type="knowledge"))
    env["invoke"](
        "forget.execute",
        {"forget_plan_id": "plan-1", "user_id": USER, "confirmation_token": prev["confirmation_token"]},
        idem_key="execute-gate",
    )
    with env["engine"].connect() as conn:
        a = conn.exec_driver_sql("SELECT is_deleted FROM memory_entries WHERE id=?", (entry_a,)).fetchone()
        b = conn.exec_driver_sql("SELECT is_deleted FROM memory_entries WHERE id=?", (entry_b,)).fetchone()
        assert a[0] == 1  # 确认快照目标软删
        assert b[0] == 0  # 未在快照中的对象不受影响（误删=0）


def test_execute_transaction_rollback_on_failure(env):
    entry_id = _seed_knowledge(env["engine"])
    prev = _preview(env, _payload(target_id=str(entry_id), target_type="knowledge"))
    token = prev["confirmation_token"]

    # 直接经 UoW 注入失败：软删后抛异常 → 整体回滚
    eng = env["engine"]
    with pytest.raises(RuntimeError):
        with UnitOfWork(eng) as uow:
            uow.execute_idempotent(
                user_id=USER,
                session_id="",
                idempotency_key="execute-atomic",
                business_fn=lambda: _business_then_fail(uow, token),
                request_fingerprint="fp-atomic",
            )
    with env["engine"].connect() as conn:
        plan = repo.get_forget_plan_by_id(conn, user_id=USER, forget_plan_id="plan-1")
        assert plan["status"] == "awaiting_confirmation"  # 凭据未消费、未终态
        assert plan["confirmation_token"] is not None


def _business_then_fail(uow, token: str):
    resp, _ = uow.execute_forget_plan(
        user_id=USER,
        idempotency_key="execute-atomic",
        request_fingerprint="fp-atomic",
        forget_plan_id="plan-1",
        confirmation_token=token,
        trace_id="trc-1",
    )
    raise RuntimeError("simulated failure after execute" if resp else "noop")


# ── F. fail-closed ──


@pytest.mark.parametrize("mode", ["topic", "time_window", "full_reset"])
def test_unsupported_forget_mode_preview_fails_closed(env, mode):
    p = _payload(forget_mode=mode)
    # full_reset 不允许携带 target_id（Domain 校验）；topic/time_window 需 target_topic/target_time_range
    if mode == "topic":
        p["target_topic"] = "某个主题"
    elif mode == "time_window":
        p["target_time_range"] = "[start,end)"
    else:
        p.pop("target_id")
    with pytest.raises(RequestValidationError):
        _preview(env, p)


def test_hard_delete_execute_fails_closed(env):
    entry_id = _seed_knowledge(env["engine"])
    prev = _preview(env, _payload(target_id=str(entry_id), target_type="knowledge", delete_mode="hard"))
    # preview 成功（计划含 hard 标记），execute fail-closed（不降级软删后报成功）
    with pytest.raises(RequestValidationError):
        env["invoke"](
            "forget.execute",
            {"forget_plan_id": "plan-1", "user_id": USER, "confirmation_token": prev["confirmation_token"]},
            idem_key="execute-hard",
        )
    with env["engine"].connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT is_deleted FROM memory_entries WHERE id=?", (entry_id,)
        ).fetchone()
        assert row[0] == 0  # 未被软删（无副作用）


def test_cascade_execute_fails_closed(env):
    entry_id = _seed_knowledge(env["engine"])
    prev = _preview(env, _payload(target_id=str(entry_id), target_type="knowledge", is_cascade=True))
    with pytest.raises(RequestValidationError):
        env["invoke"](
            "forget.execute",
            {"forget_plan_id": "plan-1", "user_id": USER, "confirmation_token": prev["confirmation_token"]},
            idem_key="execute-cascade",
        )


def test_event_target_execute_fails_closed(env):
    _seed_knowledge(env["engine"])
    # event 目标本期 fail-closed：resolver 在 Preview 阶段即拒绝（source_events 无 is_deleted 列）
    with pytest.raises(RequestValidationError):
        _preview(env, _payload(target_type="event", target_id="e1"))


# ── G. Gateway activation ──


def test_forget_not_registered_by_default():
    registry = HandlerRegistry()
    register_default_handlers(registry)
    with pytest.raises(UnsupportedMethodError):
        registry.route("forget.preview")
    with pytest.raises(UnsupportedMethodError):
        registry.route("forget.execute")


def test_cli_parser_default_and_forget_profile_smoke():
    default_args = build_parser().parse_args([])
    explicit_args = build_parser().parse_args(["--register-forget-handlers"])
    assert default_args.register_forget_handlers is False
    assert explicit_args.register_forget_handlers is True


def test_preview_mode_selector_mutual_exclusion(env):
    # single_item 携带 target_session_id → Domain 互斥 → INVALID_REQUEST
    p = _payload(target_session_id="s-1")
    with pytest.raises(RequestValidationError):
        _preview(env, p)


# ── H. 安全 ──


def test_selector_plaintext_cleared_after_preview(env):
    entry_id = _seed_knowledge(env["engine"])
    sensitive = "SECRET-SENTINEL-删除这段敏感内容"
    _preview(env, _payload(target_id=str(entry_id), target_type="knowledge", target_selector=sensitive))
    with env["engine"].connect() as conn:
        plan = repo.get_forget_plan_by_id(conn, user_id=USER, forget_plan_id="plan-1")
        assert plan["target_selector"] == repo.CLEARED  # 明文已清除/占位
        assert sensitive not in (plan["target_selector"] or "")


def test_zero_content_sentinel_scan(env):
    entry_id = _seed_knowledge(env["engine"], content="SENTINEL-正文-独有")
    prev = _preview(
        env,
        _payload(
            target_id=str(entry_id),
            target_type="knowledge",
            target_selector="SENTINEL-选择器-独有",
        ),
    )
    env["invoke"](
        "forget.execute",
        {"forget_plan_id": "plan-1", "user_id": USER, "confirmation_token": prev["confirmation_token"]},
        idem_key="execute-sentinel",
    )
    sentinel = "SENTINEL-选择器-独有"
    with env["engine"].connect() as conn:
        # forget_plan / forget_audit / outbox payload 零正文（Sentinel 0 命中）
        plan = repo.get_forget_plan_by_id(conn, user_id=USER, forget_plan_id="plan-1")
        assert sentinel not in json.dumps(plan, ensure_ascii=False)
        audit_rows = conn.exec_driver_sql(
            "SELECT * FROM forget_audit WHERE forget_plan_id=?", ("plan-1",)
        ).fetchall()
        audit_text = json.dumps([list(r) for r in audit_rows], ensure_ascii=False)
        assert sentinel not in audit_text
        outbox_rows = conn.exec_driver_sql(
            "SELECT payload FROM outbox WHERE aggregate_type=?", ("forget",)
        ).fetchall()
        for (payload,) in outbox_rows:
            assert sentinel not in payload


def test_request_fingerprint_sensitive_placeholder(env):
    entry_id = _seed_knowledge(env["engine"])
    sensitive = "乘客身份证号 110101199001011234"
    _preview(
        env,
        _payload(target_id=str(entry_id), target_type="knowledge", target_selector=sensitive),
        idem_key="preview-fp-sens",
    )
    sensitive_sha = hashlib.sha256(sensitive.encode("utf-8")).hexdigest()
    from gateway.forget_handlers import _preview_request_fingerprint

    safe_fp = _preview_request_fingerprint(
        {
            "forget_plan_id": "plan-1",
            "user_id": USER,
            "forget_mode": "single_item",
            "target_type": "knowledge",
            "target_selector": sensitive,
            "target_id": str(entry_id),
            "target_session_id": None,
            "target_topic": None,
            "target_time_range": None,
            "requires_confirmation": True,
            "is_cascade": False,
            "delete_mode": "soft",
        }
    )
    with env["engine"].connect() as conn:
        cached = repo.get_idempotency_cache(
            conn, user_id=USER, session_id="", idempotency_key="preview-fp-sens"
        )
        assert cached is not None
        wrapped = json.loads(cached["response"])
        stored_fp = wrapped["_request_fingerprint"]
        assert sensitive_sha not in stored_fp  # 不由敏感正文派生确定性 hash
        assert stored_fp == safe_fp  # 指纹 = selector 以 <SENSITIVE-OMITTED> 占位的重算值
    # 反证：未经占位的指纹（直接用正文派生）与安全指纹不同
    unsafe_fields = {
        "forget_plan_id": "plan-1",
        "user_id": USER,
        "forget_mode": "single_item",
        "target_type": "knowledge",
        "target_selector": sensitive,  # 明文进入
        "target_id": str(entry_id),
        "target_session_id": None,
        "target_topic": None,
        "target_time_range": None,
        "requires_confirmation": True,
        "is_cascade": False,
        "delete_mode": "soft",
    }
    canon = {k: (v if v is not None else "<absent>") for k, v in unsafe_fields.items()}
    canonical = json.dumps(canon, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    unsafe_fp = hashlib.sha256(f"forget.preview\n{canonical}".encode("utf-8")).hexdigest()
    assert unsafe_fp != safe_fp


def test_trusted_identity_cache_bypass(env_trusted):
    env = env_trusted
    entry_id = _seed_knowledge(env["engine"])
    prev = _preview(env, _payload(target_id=str(entry_id), target_type="knowledge"), idem_key="preview-cb")
    assert prev["status"] == "awaiting_confirmation"

    # 变换 trusted identity → 幂等查找前 fail-close（cache-bypass）
    env["trusted"].user_id = OTHER
    with pytest.raises(RequestValidationError) as ei:
        _preview(env, _payload(target_id=str(entry_id), target_type="knowledge"), idem_key="preview-cb")
    assert "trusted identity mismatch" in str(ei.value)


# ── I. 迁移 ──


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["KYLIN_MEMORY_DB"] = str(db_path)
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(MIGRATIONS_DIR / "alembic.ini"), *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def test_migration_upgrade_creates_forget_tables_and_priority(tmp_path):
    db = tmp_path / "d10d-mig.db"
    r = _run_alembic(db, "upgrade", "head")
    assert r.returncode == 0, r.stderr

    conn = sqlite3.connect(str(db))
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    outbox_info = {row[1]: row for row in conn.execute("PRAGMA table_info(outbox)")}
    outbox_sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='outbox'").fetchone()[0]
    revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    conn.close()

    assert {"forget_plan", "forget_audit"} <= tables
    assert "uq_forget_plan_user_plan" in indexes
    assert "idx_forget_plan_user_created" in indexes
    assert "idx_forget_audit_user_created" in indexes
    assert "idx_outbox_priority" in indexes
    assert "priority" in outbox_info
    assert str(outbox_info["attempts"][4]) in {"0", "'0'", '"0"'}
    assert "'forget'" in outbox_sql  # aggregate_type CHECK 扩展
    assert revision == "20260901_add_forget_plan"


def test_migration_single_head(tmp_path):
    r = _run_alembic(tmp_path / "heads.db", "heads")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "20260901_add_forget_plan (head)"


def test_migration_downgrade_roundtrip(tmp_path):
    db = tmp_path / "d10d-rt.db"
    assert _run_alembic(db, "upgrade", "head").returncode == 0
    r = _run_alembic(db, "downgrade", "20260901_d10b_vector_ledger")
    assert r.returncode == 0, r.stderr
    conn = sqlite3.connect(str(db))
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    outbox_info = {row[1]: row for row in conn.execute("PRAGMA table_info(outbox)")}
    conn.close()
    assert "forget_plan" not in tables
    assert "forget_audit" not in tables
    assert str(outbox_info["attempts"][4]) in {"0", "'0'", '"0"'}
    assert _run_alembic(db, "upgrade", "head").returncode == 0
