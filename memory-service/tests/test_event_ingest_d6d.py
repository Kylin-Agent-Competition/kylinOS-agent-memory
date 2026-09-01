"""D6-D event.ingest 测试：ADR-013/014 v5 契约落地（写链路 / 幂等 / identity / 敏感 / 隔离 / 迁移）。

覆盖（契约规划 v0.5 §八 + ADR-014 §评测影响）：
- 正常落库（ALLOW_EXTRACTION，processing_status=pending）
- event_id 幂等重放（duplicate_reason=idempotent_replay，落库行数不变）
- immutable identity 组成 / 污染回归（换 actor_id / occurred_at → conflict；换 idempotency_key/session_id → replay）
- consent_scope=none → REJECT（consent_not_granted）
- 高敏 request_fingerprint 安全占位 + 敏感内容四路 NULL（HIGH-01 / HIGH-03）
- trusted identity cache-bypass（HIGH-01）
- 请求级幂等冲突（同三元组 + 不同 fingerprint → INVALID_REQUEST）
- 指纹去重（保留事件 + duplicate_of/dedup_group 标记 + 消费资格谓词）
- 跨用户 event_id fail-close（MEDIUM-03）
- schema_version / trace_id 校验（MEDIUM-04）
- 普通质量型 AUDIT_ONLY 保留脱敏摘要（MEDIUM-07）
- 迁移 upgrade head 幂等 + downgrade 回滚
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from db.engine import create_db_engine, init_schema
from db import repositories as repo
from db.uow import UnitOfWork
from gateway.handlers import (
    _event_ingest_request_fingerprint,
    register_default_handlers,
    register_event_ingest_handler,
)
from gateway.protocol import RequestValidationError
from gateway.registry import HandlerRegistry, RequestContext, UnsupportedMethodError
from observability.request_context import clear_request_context
from pipeline.pipeline import EventPipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "migrations"


def _payload(**over):
    """构造合法 event.ingest flat payload（默认 chat + user_message → ALLOW_EXTRACTION）。"""
    now = datetime.now(timezone.utc)
    p = {
        "schema_version": "0.1",
        "event_id": "evt-1",
        "user_id": "u1",
        "actor_id": "a1",
        "session_id": "s1",
        "idempotency_key": "idem-1",
        "source_type": "chat",
        "event_type": "user_message",
        "turn_id": "T-1",
        "occurred_at": (now - timedelta(hours=1)).isoformat(),
        "captured_at": now.isoformat(),
        "content_summary": "用户偏好深色主题",
        "consent_scope": "memory_only",
    }
    p.update(over)
    return p


class _TrustedIdentity:
    """可变 trusted host identity（production ACTIVE 硬门禁模拟，cache-bypass 测试）。"""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id


@pytest.fixture()
def env(tmp_path):
    """test profile：显式注册 event.ingest（trusted_identity=None = 声明自洽）。"""
    eng = create_db_engine(str(tmp_path / "d6d.db"))
    init_schema(eng)
    registry = HandlerRegistry()
    register_default_handlers(registry)

    def _uow_factory():
        return UnitOfWork(eng)

    register_event_ingest_handler(registry, uow_factory=_uow_factory)

    def invoke(payload, *, trace_id="trc-1", idem_key=None):
        h = registry.route("event.ingest")
        ctx = RequestContext(
            request_id="req-1",
            trace_id=trace_id,
            method="event.ingest",
            deadline_ms=5000,
            idempotency_key=idem_key,
        )
        return h(payload, ctx)

    yield {"engine": eng, "invoke": invoke, "registry": registry}
    clear_request_context()


@pytest.fixture()
def env_trusted(tmp_path):
    """production ACTIVE profile：注入可变 trusted identity，供 cache-bypass 回归。"""
    eng = create_db_engine(str(tmp_path / "d6d_trusted.db"))
    init_schema(eng)
    registry = HandlerRegistry()
    register_default_handlers(registry)
    trusted = _TrustedIdentity("u1")

    def _uow_factory():
        return UnitOfWork(eng)

    register_event_ingest_handler(registry, uow_factory=_uow_factory, trusted_identity=trusted)

    def invoke(payload, *, trace_id="trc-1", idem_key=None):
        h = registry.route("event.ingest")
        ctx = RequestContext(
            request_id="req-1",
            trace_id=trace_id,
            method="event.ingest",
            deadline_ms=5000,
            idempotency_key=idem_key,
        )
        return h(payload, ctx)

    yield {"engine": eng, "invoke": invoke, "trusted": trusted}
    clear_request_context()


def _rows(engine, *, user_id="u1"):
    with engine.connect() as conn:
        return repo.list_source_events(conn, user_id=user_id, limit=100)


def _row_by_event_id(engine, *, user_id="u1", event_id):
    with engine.connect() as conn:
        return repo.get_source_event_by_event_id(conn, user_id=user_id, event_id=event_id)


# ── activation（production 默认不注册） ──


def test_event_ingest_not_registered_by_default():
    """production 默认路由不含 event.ingest → UNSUPPORTED_METHOD（ADR-014 activation A+B）。"""
    registry = HandlerRegistry()
    register_default_handlers(registry)
    with pytest.raises(UnsupportedMethodError):
        registry.route("event.ingest")


# ── 正常落库（ALLOW_EXTRACTION，processing_status=pending） ──


def test_ingest_ok_allows_extraction(env):
    resp = env["invoke"](_payload())
    assert resp["admission_decision"] == "allow_extraction"
    assert resp["duplicate"] is False
    assert resp["duplicate_reason"] is None
    assert resp["source_event_id"] > 0

    row = _row_by_event_id(env["engine"], event_id="evt-1")
    assert row is not None
    assert row["processing_status"] == "pending"
    assert row["admission_decision"] == "allow_extraction"
    assert row["content_summary"] == "用户偏好深色主题"
    assert row["content_fingerprint"] is not None
    assert row["duplicate_of"] is None
    assert row["dedup_group"] is not None  # 组聚合键（head 亦落 dedup_group）
    assert row["trace_id"] == "trc-1"  # envelope 顶级唯一真源


# ── event_id 幂等重放 / identity 组成 / 污染回归 ──


def test_ingest_idempotent_replay(env):
    """同 event_id + 同 identity，换 idempotency_key（绕过请求级缓存）→ 幂等重放。"""
    payload = _payload(event_id="evt-replay")
    r1 = env["invoke"](payload)
    payload2 = dict(payload)
    payload2["idempotency_key"] = "idem-2"
    r2 = env["invoke"](payload2)
    assert r1["source_event_id"] > 0
    assert r2["duplicate"] is True
    assert r2["duplicate_reason"] == "idempotent_replay"
    assert r2["source_event_id"] == r1["source_event_id"]
    assert r2["admission_decision"] == r1["admission_decision"]
    assert r2["admission_reason_code"] == r1["admission_reason_code"]
    assert len(_rows(env["engine"])) == 1  # 落库行数不变


def test_ingest_identity_not_polluted_by_request_fields(env):
    """无正文事件换 idempotency_key/session_id 重投 → 判 replay 而非 conflict（HIGH-01/D-10）。"""
    p1 = _payload(event_id="evt-nc", idempotency_key="idem-A", content_summary=None)
    env["invoke"](p1)

    p2 = dict(p1)
    p2["idempotency_key"] = "idem-B"  # 请求级字段变化
    p2["session_id"] = "s2"  # 请求级字段变化
    r2 = env["invoke"](p2)
    assert r2["duplicate"] is True
    assert r2["duplicate_reason"] == "idempotent_replay"
    assert len(_rows(env["engine"])) == 1


def test_ingest_identity_collision_actor(env):
    """同 event_id 换 actor_id → EventIdentityConflict → INVALID_REQUEST（identity 含 actor）。"""
    p1 = _payload(event_id="evt-x")
    env["invoke"](p1)
    p2 = dict(p1)
    p2["idempotency_key"] = "idem-2"
    p2["actor_id"] = "a2"
    with pytest.raises(RequestValidationError):
        env["invoke"](p2)


def test_ingest_identity_collision_occurred_at(env):
    """同 event_id 换 occurred_at → EventIdentityConflict → INVALID_REQUEST（identity 含时间）。"""
    p1 = _payload(event_id="evt-t")
    env["invoke"](p1)
    p2 = dict(p1)
    p2["idempotency_key"] = "idem-2"
    p2["occurred_at"] = "2026-08-31T11:00:00+00:00"
    with pytest.raises(RequestValidationError):
        env["invoke"](p2)


# ── consent_scope=none 前置 REJECT ──


def test_consent_none_reject(env):
    resp = env["invoke"](_payload(consent_scope="none"))
    assert resp["admission_decision"] == "reject"
    assert resp["admission_reason_code"] == "consent_not_granted"

    row = _row_by_event_id(env["engine"], event_id="evt-1")
    assert row["processing_status"] == "pending"
    assert row["content_fingerprint"] is None  # HIGH-03
    assert row["content_summary"] is None
    assert row["raw_payload_ref"] is None
    assert row["dedup_group"] is None
    assert row["duplicate_of"] is None


# ── 高敏 request_fingerprint 安全占位 + 敏感四路 NULL（HIGH-01 / HIGH-03） ──


def test_sensitive_request_fingerprint_placeholder_and_null(env):
    content = "连接信息 api_key=sk-demo-abcdefghijklmnopqrstuvwxyz123456 已配置（虚构攻击样本）"
    payload = _payload(event_id="evt-sens", sensitivity="none", content_summary=content)
    resp = env["invoke"](payload)
    assert resp["admission_decision"] == "reject"

    with env["engine"].connect() as conn:
        row = repo.get_source_event_by_event_id(conn, user_id="u1", event_id="evt-sens")
        assert row["sensitivity"] == "critical"  # ① Pipeline 判 sensitive 并升级
        assert row["is_sensitive_matched"] == 1
        assert row["content_fingerprint"] is None  # ④ HIGH-03
        assert row["content_summary"] is None
        assert row["raw_payload_ref"] is None
        assert row["dedup_group"] is None
        assert row["duplicate_of"] is None

        cached = repo.get_idempotency_cache(
            conn, user_id="u1", session_id="s1", idempotency_key="idem-1"
        )
        wrapped = json.loads(cached["response"])
        stored_fp = wrapped["_request_fingerprint"]

    # ③ 幂等缓存指纹不含由敏感正文直接派生的确定性 SHA-256
    sensitive_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert stored_fp != sensitive_sha
    assert sensitive_sha not in stored_fp

    # ② request_fingerprint 内容身份取固定安全占位 <SENSITIVE-OMITTED>
    result = EventPipeline().process(payload)
    assert result.event.is_sensitive_matched
    fp = _event_ingest_request_fingerprint(method="event.ingest", event=result.event, result=result)
    assert fp == stored_fp
    assert fp != _unsafe_fingerprint(result.event)


def _unsafe_fingerprint(event) -> str:
    """复算「无占位」指纹（内容身份 = 归一化敏感正文），证明安全占位确实生效。"""
    content_identity = repo.event_content_identity(
        content_summary=event.content_summary,
        raw_payload_ref=event.raw_payload_ref,
    )
    fields = {
        "event_id": event.event_id,
        "user_id": event.user_id,
        "actor_id": event.actor_id,
        "session_id": event.session_id,
        "source_type": event.source_type.value,
        "event_type": event.event_type.value,
        "occurred_at": event.occurred_at.astimezone(timezone.utc).isoformat(timespec="milliseconds"),
        "event_content_identity": content_identity,
        "consent_scope": event.consent_scope.value,
        "source_business_status": event.source_business_status.value,
    }
    canon = {k: (v if v is not None else "<absent>") for k, v in fields.items()}
    canonical = json.dumps(canon, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"event.ingest\n{canonical}".encode("utf-8")).hexdigest()


# ── trusted identity cache-bypass（HIGH-01） ──


def test_trusted_identity_cache_bypass(env_trusted):
    env = env_trusted
    payload = _payload(user_id="u1", event_id="evt-cb", idempotency_key="idem-cb")
    r1 = env["invoke"](payload)
    assert r1["admission_decision"] == "allow_extraction"  # 首次成功，缓存已写入

    # 已有 cache response，但 trusted identity mismatch → 在幂等查找前 fail-close
    env["trusted"].user_id = "u-other"
    with pytest.raises(RequestValidationError) as ei:
        env["invoke"](payload)
    assert "trusted identity mismatch" in str(ei.value)


# ── 请求级幂等冲突（同三元组 + 不同 fingerprint → INVALID_REQUEST） ──


def test_request_idempotency_conflict(env):
    """同三元组 + 不同 request_fingerprint → IdempotencyConflictError（server 层转 INVALID_REQUEST）。"""
    env["invoke"](_payload(event_id="evt-a", idempotency_key="idem-shared"))
    with pytest.raises(repo.IdempotencyConflictError):
        env["invoke"](_payload(event_id="evt-b", idempotency_key="idem-shared"))


# ── 指纹去重（保留事件 + 标记 + 消费资格谓词） ──


def test_fingerprint_dedup_mark_and_eligible(env):
    r1 = env["invoke"](_payload(event_id="evt-a", idempotency_key="idem-a"))
    assert r1["duplicate"] is False

    r2 = env["invoke"](_payload(event_id="evt-b", idempotency_key="idem-b"))
    assert r2["duplicate"] is True
    assert r2["duplicate_reason"] == "content_duplicate"
    assert r2["duplicate_of"] == r1["source_event_id"]

    head = _row_by_event_id(env["engine"], event_id="evt-a")
    dup = _row_by_event_id(env["engine"], event_id="evt-b")
    assert head["duplicate_of"] is None
    assert dup["duplicate_of"] == head["id"]
    assert head["dedup_group"] == dup["dedup_group"]  # 同组聚合键一致
    assert "u1" in head["dedup_group"]  # 含 user scope（MEDIUM-05）

    # 消费资格谓词：仅 head（pending + allow_extraction + duplicate_of IS NULL）可进抽取
    with env["engine"].connect() as conn:
        eligible = repo.find_pending_eligible(conn, user_id="u1")
    assert {e["event_id"] for e in eligible} == {"evt-a"}


# ── 跨用户 event_id fail-close（MEDIUM-03） ──


def test_cross_user_event_id_fail_close(env):
    env["invoke"](_payload(user_id="uA", event_id="evt-shared", idempotency_key="idem-A"))
    with pytest.raises(RequestValidationError):
        env["invoke"](_payload(user_id="uB", event_id="evt-shared", idempotency_key="idem-B"))

    # 不回读/不返回他人事件；B 查询不到 A 的事件
    assert _row_by_event_id(env["engine"], user_id="uB", event_id="evt-shared") is None
    assert _row_by_event_id(env["engine"], user_id="uA", event_id="evt-shared") is not None


# ── schema_version / trace_id 校验 ──


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.pop("schema_version"),
        lambda p: p.__setitem__("schema_version", "0.2"),
        lambda p: p.__setitem__("schema_version", "1.0"),
        lambda p: p.__setitem__("schema_version", "not-a-version"),
    ],
)
def test_schema_version_invalid(env, mutate):
    p = _payload()
    mutate(p)
    with pytest.raises(RequestValidationError):
        env["invoke"](p)


def test_trace_id_mismatch(env):
    p = _payload(trace_id="trc-999")
    with pytest.raises(RequestValidationError):
        env["invoke"](p, trace_id="trc-1")


def test_idempotency_key_merge_conflict(env):
    """envelope 顶级 idempotency_key 与 payload 不一致 → INVALID_REQUEST（ADR-014 合并规则）。"""
    with pytest.raises(RequestValidationError):
        env["invoke"](_payload(), idem_key="env-key-diff")


# ── 普通质量型 AUDIT_ONLY 保留脱敏摘要（MEDIUM-07） ──


def test_audit_only_preserves_content_summary(env):
    resp = env["invoke"](
        _payload(
            source_type="recollect",
            event_type="system_message",
            content_summary="用户提到喜欢蓝色",
        )
    )
    assert resp["admission_decision"] == "audit_only"
    row = _row_by_event_id(env["engine"], event_id="evt-1")
    assert row["processing_status"] == "pending"  # 不落 extracting
    assert row["content_summary"] == "用户提到喜欢蓝色"  # 非敏感不强制清空
    assert row["content_fingerprint"] is not None


# ── 迁移（alembic upgrade head 幂等 + downgrade 回滚） ──


def _run_alembic(db_path: str, *args: str) -> subprocess.CompletedProcess:
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


@pytest.fixture()
def mig_db(tmp_path):
    return tmp_path / "d6d-migrate.db"


def test_migration_upgrade_creates_source_events(mig_db):
    result = _run_alembic(mig_db, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(str(mig_db))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    cols = {r[1] for r in conn.execute("PRAGMA table_info(source_events)")}
    revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    conn.close()

    assert "source_events" in tables
    assert {
        "uq_source_events_event",
        "idx_source_events_user_created",
        "idx_source_events_fingerprint",
        "idx_source_events_dedup_group",
        "idx_source_events_status",
    } <= indexes
    assert {"id", "event_id", "content_fingerprint", "dedup_group", "duplicate_of"} <= cols
    assert revision == "20260831_add_source_events"


def test_migration_downgrade_rolls_back_source_events(mig_db):
    assert _run_alembic(mig_db, "upgrade", "head").returncode == 0
    result = _run_alembic(mig_db, "downgrade", "20260831_preference_versions")
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(str(mig_db))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "source_events" not in tables
    assert _run_alembic(mig_db, "upgrade", "head").returncode == 0


def test_migration_global_unique_event_id(mig_db):
    """UNIQUE(event_id) 全局唯一：跨用户复用 event_id → IntegrityError（ADR-013）。"""
    assert _run_alembic(mig_db, "upgrade", "head").returncode == 0
    conn = sqlite3.connect(str(mig_db))
    base = (
        "INSERT INTO source_events (user_id, event_id, actor_id, session_id, source_type, "
        "event_type, schema_version, idempotency_key, consent_scope, source_business_status, "
        "sensitivity, occurred_at, captured_at, admission_decision, admission_reason_code, "
        "processing_status, created_at, updated_at) VALUES "
        "('u1', 'evt-dup', 'a1', 's1', 'chat', 'user_message', '0.1', 'idem-1', "
        "'memory_only', 'raw', 'none', '2026-08-31T10:00:00+00:00', '2026-08-31T10:00:01+00:00', "
        "'allow_extraction', 'ok', 'pending', '2026-08-31T10:00:02+00:00', '2026-08-31T10:00:02+00:00')"
    )
    conn.execute(base)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(base.replace("'u1'", "'u2'"))
    conn.close()


# ── 冻结 L1 验收补充（Review #98 REWORK MEDIUM-01：请求级重放 / 同事务回滚 / 并发 dedup head / CHECK 对照） ──


def test_request_idempotency_same_fingerprint_cache_replay(env):
    """同三元组 + 同 request_fingerprint → cache replay，且不得重复业务副作用（ADR-014 v5）。

    冻结场景 1：same triple + same request fingerprint → 命中 idempotency_cache 返回首次结果，
    business_fn 不再执行 → source_events 行数不变、幂等缓存仍仅一行。
    """
    payload = _payload(event_id="evt-replay-fp", idempotency_key="idem-fp")
    r1 = env["invoke"](payload)
    assert r1["duplicate"] is False
    assert len(_rows(env["engine"])) == 1

    # 同 payload 再次提交（同三元组 + 同 fingerprint）→ 命中缓存，返回首次结果
    r2 = env["invoke"](payload)
    assert r2["source_event_id"] == r1["source_event_id"]
    assert r2["admission_decision"] == r1["admission_decision"]
    assert r2["admission_reason_code"] == r1["admission_reason_code"]
    assert r2["duplicate"] is False
    assert r2["duplicate_reason"] is None
    assert len(_rows(env["engine"])) == 1  # 未重复业务副作用

    # 缓存仅一行，且存储的指纹 = 同 payload 重算的 privacy-safe request_fingerprint
    with env["engine"].connect() as conn:
        cached = repo.get_idempotency_cache(
            conn, user_id="u1", session_id="s1", idempotency_key="idem-fp"
        )
        assert cached is not None
        wrapped = json.loads(cached["response"])
        assert "_request_fingerprint" in wrapped
        cached_fp = wrapped["_request_fingerprint"]
        assert isinstance(cached_fp, str) and len(cached_fp) == 64

        result = EventPipeline().process(payload)
        fp = _event_ingest_request_fingerprint(method="event.ingest", event=result.event, result=result)
        assert fp == cached_fp


def test_event_ingest_atomic_rollback_with_idempotency_cache(env):
    """source_events 写入与 idempotency_cache 写入同事务：business 失败 → 整体回滚（ADR-013 HIGH-02）。

    冻结场景 2：UoW.execute_idempotent 单事务内，source_event INSERT 后业务失败 → 事务回滚，
    source_events 与 idempotency_cache 均不得残留（不拆两个事务）。
    """
    eng = env["engine"]

    def _insert_then_fail(uow):
        repo.insert_source_event(
            uow.conn,
            user_id="u1",
            event_id="evt-atomic",
            actor_id="a1",
            session_id="s1",
            turn_id=None,
            tool_call_id=None,
            source_type="chat",
            event_type="user_message",
            schema_version="0.1",
            trace_id="trc-atomic",
            source_reference=None,
            raw_payload_ref=None,
            content_summary="用户偏好深色主题",
            idempotency_key="idem-atomic",
            consent_scope="memory_only",
            source_business_status="raw",
            sensitivity="none",
            is_sensitive_matched=0,
            should_ignore=0,
            payload_security_checked=1,
            memory_type=None,
            requires_embedding=1,
            has_structured_payload=0,
            language_tag=None,
            occurred_at="2026-08-31T10:00:00+00:00",
            captured_at="2026-08-31T10:00:01+00:00",
            content_fingerprint="fp-atomic",
            dedup_group=None,
            duplicate_of=None,
            admission_decision="allow_extraction",
            admission_reason_code="ok",
            processing_status="pending",
            created_at="2026-08-31T10:00:02+00:00",
            updated_at="2026-08-31T10:00:02+00:00",
        )
        raise RuntimeError("simulated downstream failure")

    with pytest.raises(RuntimeError):
        with UnitOfWork(eng) as uow:
            uow.execute_idempotent(
                user_id="u1",
                session_id="s1",
                idempotency_key="idem-atomic",
                business_fn=lambda: _insert_then_fail(uow),
                request_fingerprint="fp-req-atomic",
            )

    with eng.connect() as conn:
        # 业务写入已回滚：source_events 无行
        assert repo.get_source_event_by_event_id(conn, user_id="u1", event_id="evt-atomic") is None
        # 幂等缓存未写入：同事务回滚
        assert repo.get_idempotency_cache(
            conn, user_id="u1", session_id="s1", idempotency_key="idem-atomic"
        ) is None


def test_dedup_head_concurrent_atomic(env):
    """两个不同 event_id、同 fingerprint 并发提交 → 仅一个 dedup head（ADR-013 MEDIUM-04）。

    冻结场景 3：find_dedup_group_head + insert_source_event 同 UoW / 单写锁 / 事务原子绑定，
    并发下 `duplicate_of IS NULL` 仅一行，另一行 duplicate_of = 首次行 id。
    """
    import threading

    content = "并发去重：仅一个组首事件"
    results: dict = {}
    errors: list = []

    def _worker(event_id: str, idem_key: str) -> None:
        try:
            results[event_id] = env["invoke"](
                _payload(event_id=event_id, idempotency_key=idem_key, content_summary=content)
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=_worker, args=("evt-c1", "idem-c1")),
        threading.Thread(target=_worker, args=("evt-c2", "idem-c2")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    rows = _rows(env["engine"])
    assert len(rows) == 2  # 两行均存在（保留事件 + 标记去重）

    heads = [r for r in rows if r["duplicate_of"] is None]
    dups = [r for r in rows if r["duplicate_of"] is not None]
    assert len(heads) == 1  # 仅一个 dedup head
    assert len(dups) == 1
    assert dups[0]["duplicate_of"] == heads[0]["id"]
    assert heads[0]["dedup_group"] == dups[0]["dedup_group"]
    # 消费资格谓词：仅 head 可进抽取（D9-D MEDIUM-02）
    with env["engine"].connect() as conn:
        eligible = {e["event_id"] for e in repo.find_pending_eligible(conn, user_id="u1")}
    assert eligible == {heads[0]["event_id"]}


def test_migration_check_constraints_source_events(mig_db):
    """migration schema 对照覆盖冻结 CHECK 约束（ADR-013：5 CHECK 值域 + 强制执行）。

    冻结场景 4：upgrade 后 CREATE TABLE 包含 5 个冻结 CHECK 值域；非法值插入被拒绝，
    合法值可插入（CHECK 非仅文档声明）。
    """
    assert _run_alembic(mig_db, "upgrade", "head").returncode == 0
    conn = sqlite3.connect(str(mig_db))
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='source_events'"
    ).fetchone()
    create_sql = row[0]

    # 5 个冻结 CHECK 值域（ADR-013 DDL 草案 §决策）
    assert "consent_scope IN ('memory_only','memory_and_analytics','none')" in create_sql
    assert (
        "source_business_status IN "
        "('raw','completed','success','partial','failed','cancelled','timeout','ignored')" in create_sql
    )
    assert "sensitivity IN ('none','low','medium','high','critical')" in create_sql
    assert "admission_decision IN ('allow_extraction','audit_only','reject')" in create_sql
    assert "processing_status IN ('pending','extracting','extracted','embedded','stored')" in create_sql

    # 强制执行：合法值可插入；非法 processing_status → CHECK 拒绝（IntegrityError）
    base = (
        "INSERT INTO source_events (user_id, event_id, actor_id, session_id, source_type, "
        "event_type, schema_version, idempotency_key, consent_scope, source_business_status, "
        "sensitivity, occurred_at, captured_at, admission_decision, admission_reason_code, "
        "processing_status, created_at, updated_at) VALUES "
        "('u1', 'evt-check-ok', 'a1', 's1', 'chat', 'user_message', '0.1', 'idem-ok', "
        "'memory_only', 'raw', 'none', '2026-08-31T10:00:00+00:00', '2026-08-31T10:00:01+00:00', "
        "'allow_extraction', 'ok', 'pending', '2026-08-31T10:00:02+00:00', '2026-08-31T10:00:02+00:00')"
    )
    conn.execute(base)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            base.replace("'pending'", "'bogus_status'").replace("'evt-check-ok'", "'evt-check-bad'")
        )
    conn.close()
