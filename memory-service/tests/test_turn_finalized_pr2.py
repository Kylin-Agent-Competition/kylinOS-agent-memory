"""PR-2 turn.finalized 测试：ADR-010（写链路 / 幂等指纹 / 错误路径 / Upsert / resolver）"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from datetime import datetime, timezone

import pytest

from db.engine import create_db_engine, init_schema
from db import repositories as repo
from db.uow import UnitOfWork
from gateway import protocol as proto
from gateway.handlers import register_default_handlers, register_turn_finalized_handler
from gateway.protocol import RequestValidationError
from gateway.registry import HandlerRegistry, RequestContext
from gateway.server import UDSGatewayServer
from observability.request_context import clear_request_context, get_request_context
from outbox.worker import OutboxWorker
from service.source_resolver import InMemorySourceResolver, ResolvedContent


def _wait_socket(path, timeout=5.0):
    deadline = time.monotonic() + timeout
    last_err = None
    while time.monotonic() < deadline:
        if os.path.exists(path):
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.settimeout(0.5)
                    s.connect(path)
                return
            except OSError as exc:
                last_err = exc
        time.sleep(0.05)
    raise TimeoutError(f"socket not ready: {path} (last: {last_err})")


def _request(sock_path: str, msg: dict, timeout: float = 5.0) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(sock_path)
        s.sendall(proto.encode(msg))
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            try:
                resp, _rest = proto.decode_packet(buf)
                return resp
            except proto.IncompletePacket:
                continue


def _base(method: str, payload=None, **kw):
    msg = {
        "protocol_version": "1.0",
        "request_id": kw.get("request_id", "req-1"),
        "trace_id": kw.get("trace_id", "trc-1"),
        "method": method,
        "deadline_ms": kw.get("deadline_ms", 2000),
        "payload": payload if payload is not None else {},
    }
    if "idempotency_key" in kw:
        msg["idempotency_key"] = kw["idempotency_key"]
    return msg


def _valid_payload(**over):
    payload = {
        "metadata": {
            "schema_version": "1.0",
            "event_id": "evt-1",
            "user_id": "u1",
            "session_id": "s1",
            "turn_id": "H-1",
            "idempotency_key": "idem-1",
            "occurred_at": "2026-08-27T10:00:00+00:00",
            "collected_at": "2026-08-27T10:00:01+00:00",
            "source_reference": "ref://turn/H-1",
        },
        "is_final": True,
        "finalized_at": "2026-08-27T10:00:02+00:00",
        "final_message_id": "m-1",
        "finalization_reason": "normal",
        "stop_reason": "end_turn",
        "tool_call_ids": ["tc-1", "tc-2"],
    }
    _deep_merge(payload, over)
    return payload


def _deep_merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


@pytest.fixture()
def gw_turn_finalized(tmp_path):
    """test profile：显式注册 turn.finalized + in-memory resolver（activation A+B）。"""
    eng = create_db_engine(str(tmp_path / "gw_pr2.db"))
    init_schema(eng)
    registry = HandlerRegistry()
    register_default_handlers(registry)
    resolver = InMemorySourceResolver(
        {"ref://turn/H-1": ResolvedContent(original_user_text="银河麒麟桌面系统测试")}
    )

    def _uow_factory():
        from db.uow import UnitOfWork
        return UnitOfWork(eng)

    register_turn_finalized_handler(registry, uow_factory=_uow_factory, resolver=resolver)
    sock = str(tmp_path / "memory_pr2.sock")
    server = UDSGatewayServer(sock, registry, engine=eng, default_deadline_ms=5000)
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    _wait_socket(sock)
    yield {"server": server, "sock": sock, "engine": eng, "resolver": resolver}
    server.stop()


@pytest.fixture()
def gw_default(tmp_path):
    """production profile：默认注册（不含 turn.finalized → UNSUPPORTED_METHOD）。"""
    eng = create_db_engine(str(tmp_path / "gw_default_pr2.db"))
    init_schema(eng)
    registry = HandlerRegistry()
    register_default_handlers(registry)
    sock = str(tmp_path / "memory_default_pr2.sock")
    server = UDSGatewayServer(sock, registry, engine=eng, default_deadline_ms=5000)
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    _wait_socket(sock)
    yield {"server": server, "sock": sock, "engine": eng}
    server.stop()


# ── production 默认不注册（activation A+B） ──


def test_turn_finalized_unsupported_in_default_profile(gw_default):
    """production 默认路由不注册 turn.finalized → UNSUPPORTED_METHOD（FRZ-IPC-007）。"""
    resp = _request(gw_default["sock"], _base("turn.finalized", _valid_payload()))
    assert resp["status"] == "error"
    assert resp["error_code"] == "UNSUPPORTED_METHOD"


# ── 成功写链路（Gateway → UoW → SQLite + Outbox 同事务） ──


def test_turn_finalized_insert_ok(gw_turn_finalized):
    sock = gw_turn_finalized["sock"]
    resp = _request(sock, _base("turn.finalized", _valid_payload()))
    assert resp["status"] == "ok"
    assert resp["data"]["host_turn_id"] == "H-1"
    assert resp["data"]["db_turn_id"] > 0
    assert resp["data"]["conversation_id"] > 0

    # 落库校验：turns 行 + trace_id/host_turn_id + original_user_text（resolver 解析）
    with gw_turn_finalized["engine"].connect() as conn:
        row = conn.execute(
            repo.turns.select().where(repo.turns.c.host_turn_id == "H-1")
        ).mappings().first()
        assert row is not None
        assert row["trace_id"] == "trc-1"  # envelope 顶级唯一真源
        assert row["host_turn_id"] == "H-1"
        assert row["original_user_text"] == "银河麒麟桌面系统测试"
        assert row["turn_index"] == 1  # 服务端计算 1+MAX
        assert row["is_end"] == 1
        # Outbox 入队 + payload 携带 trace_id/host_turn_id（checklist 5.4）
        pending = repo.claim_pending_outbox(
            conn, now_iso=datetime.now(timezone.utc).isoformat(), max_retries=3
        )
        assert len(pending) == 1
        payload = json.loads(pending[0]["payload"])
        assert payload["trace_id"] == "trc-1"
        assert payload["host_turn_id"] == "H-1"
        assert payload["refinalize"] is False
        # M3.4：outbox payload 时间戳经 _canonical_ts 规范化（UTC 毫秒）
        assert payload["occurred_at"] == "2026-08-27T10:00:00.000+00:00"


def test_turn_finalized_outbox_worker_preserves_event_context(gw_turn_finalized):
    """真实写链路的 Outbox consumer 收到 trace_id/event_id，处理后上下文清空。"""
    trace_id = "trc-outbox-context"
    event_id = "evt-outbox-context"
    payload = _valid_payload()
    payload["metadata"]["event_id"] = event_id
    payload["metadata"]["idempotency_key"] = "idem-outbox-context"
    payload["metadata"]["turn_id"] = "H-OUTBOX-CONTEXT"
    payload["metadata"]["source_reference"] = "ref://turn/H-1"

    response = _request(
        gw_turn_finalized["sock"],
        _base("turn.finalized", payload, trace_id=trace_id),
    )
    assert response["status"] == "ok"

    seen_context = []

    def consumer(_payload):
        seen_context.append(get_request_context())

    worker = OutboxWorker(gw_turn_finalized["engine"], consumer=consumer)
    worker._poll_once()
    worker.stop()

    assert seen_context == [
        {
            "request_id": "",
            "trace_id": trace_id,
            "method": "outbox:turn.finalized",
            "event_id": event_id,
        }
    ]
    assert get_request_context() == {
        "request_id": "",
        "trace_id": "",
        "method": "",
        "event_id": "",
    }


# ── 幂等（ADR-010：三元组 + 指纹 wrapper/unwrap） ──


def test_turn_finalized_idempotent_replay(gw_turn_finalized):
    """相同三元组 + 相同指纹重投 → 返回首次响应，不重复落库（缓存命中）。"""
    sock = gw_turn_finalized["sock"]
    r1 = _request(sock, _base("turn.finalized", _valid_payload()))
    r2 = _request(sock, _base("turn.finalized", _valid_payload()))
    assert r1["status"] == "ok" and r2["status"] == "ok"
    assert r1["data"] == r2["data"]
    with gw_turn_finalized["engine"].connect() as conn:
        cnt = conn.execute(
            repo.turns.select().where(repo.turns.c.host_turn_id == "H-1")
        ).all()
        assert len(cnt) == 1  # 不重复落库


def test_turn_finalized_idempotent_conflict(gw_turn_finalized):
    """相同三元组 + 不同指纹（同 key 不同 payload）→ INVALID_REQUEST（ADR-010）。"""
    sock = gw_turn_finalized["sock"]
    r1 = _request(sock, _base("turn.finalized", _valid_payload()))
    assert r1["status"] == "ok"
    # 同 idempotency_key（idem-1）但业务语义不同（不同 event_id）
    conflict = _valid_payload()
    conflict["metadata"]["event_id"] = "evt-999"
    r2 = _request(sock, _base("turn.finalized", conflict))
    assert r2["status"] == "error"
    assert r2["error_code"] == "INVALID_REQUEST"


def test_turn_finalized_idempotency_key_merge(gw_turn_finalized):
    """idempotency_key 权威合并：envelope 顶级 → payload.metadata；不一致 → INVALID_REQUEST。"""
    sock = gw_turn_finalized["sock"]
    payload = _valid_payload()
    # envelope 顶级 key 与 metadata key 不一致 → INVALID_REQUEST
    resp = _request(sock, _base("turn.finalized", payload, idempotency_key="env-key-diff"))
    assert resp["status"] == "error"
    assert resp["error_code"] == "INVALID_REQUEST"
    # envelope 顶级 key 与 metadata key 一致 → OK（以 envelope 为权威）
    resp2 = _request(
        sock, _base("turn.finalized", _valid_payload(event_id="evt-2"), idempotency_key="idem-1")
    )
    assert resp2["status"] == "ok"


# ── 校验错误路径（INVALID_REQUEST） ──


@pytest.mark.parametrize(
    "mutate,desc",
    [
        (lambda p: p.pop("metadata"), "缺 metadata"),
        (lambda p: p["metadata"].pop("event_id"), "缺 event_id"),
        (lambda p: p["metadata"].__setitem__("schema_version", "2.0"), "schema_version 主版本 != 1"),
        (lambda p: p["metadata"].__setitem__("schema_version", "abc"), "schema_version 非法"),
        (lambda p: p.__setitem__("is_final", False), "is_final 必须显式 true"),
        (lambda p: p.pop("finalized_at"), "缺 finalized_at"),
        (lambda p: p["metadata"].__setitem__("occurred_at", "not-a-date"), "occurred_at 非法时间戳"),
        (lambda p: p["metadata"].__setitem__("trace_id", "trc-999"), "payload trace_id != envelope"),
        (lambda p: p.__setitem__("tool_call_ids", ["a", "a"]), "tool_call_ids 重复"),
        (lambda p: p.__setitem__("retry_of_turn_id", "H-1"), "retry_of_turn_id == turn_id"),
        (lambda p: p["metadata"].__setitem__("turn_id", 123), "turn_id 非字符串"),
    ],
)
def test_turn_finalized_invalid_payload(gw_turn_finalized, mutate, desc):
    payload = _valid_payload()
    mutate(payload)
    resp = _request(gw_turn_finalized["sock"], _base("turn.finalized", payload))
    assert resp["status"] == "error", desc
    assert resp["error_code"] == "INVALID_REQUEST", desc


# ── resolver 失败（INTERNAL_ERROR，禁止编造正文） ──


def test_turn_finalized_resolver_miss_internal_error(gw_turn_finalized, caplog):
    """resolver 未命中（返回 None）→ INTERNAL_ERROR（safe，不编造正文）。"""
    payload = _valid_payload()
    source_reference = "ref://missing/private-user-content"
    payload["metadata"]["source_reference"] = source_reference
    payload["metadata"]["turn_id"] = "H-MISS"
    with caplog.at_level(logging.WARNING, logger="service.source_resolver"):
        resp = _request(gw_turn_finalized["sock"], _base("turn.finalized", payload))
    assert resp["status"] == "error"
    assert resp["error_code"] == "INTERNAL_ERROR"
    assert source_reference not in caplog.text
    assert "resolver 未命中受控 source_reference，调用方按 INTERNAL_ERROR 处理" in caplog.text
    # M6.6：失败请求零副作用——无 Turn / 无 Outbox / 无幂等缓存半成品
    with gw_turn_finalized["engine"].connect() as conn:
        row = conn.execute(
            repo.turns.select().where(repo.turns.c.host_turn_id == "H-MISS")
        ).first()
        assert row is None
        pending = repo.claim_pending_outbox(
            conn, now_iso=datetime.now(timezone.utc).isoformat(), max_retries=3
        )
        assert len(pending) == 0
        cached = repo.get_idempotency_cache(
            conn, user_id="u1", session_id="s1", idempotency_key="idem-1"
        )
        assert cached is None


# ── Upsert：重投/refinalize 更新同一条（保持首次值） ──


def test_turn_finalized_refinalize_upsert(gw_turn_finalized):
    """同 (session_id, host_turn_id) 二次写入 → UPDATE 同一条，不重复计数。"""
    sock = gw_turn_finalized["sock"]
    r1 = _request(sock, _base("turn.finalized", _valid_payload()))
    assert r1["status"] == "ok"
    first_db_id = r1["data"]["db_turn_id"]

    # 模拟 refinalize：同 turn 不同 event_id（新 idempotency_key，避免幂等命中）
    ref = _valid_payload(
        event_id="evt-ref",
        finalized_at="2026-08-27T10:01:00+00:00",
    )
    ref["metadata"]["idempotency_key"] = "idem-ref"
    ref["metadata"]["event_id"] = "evt-ref"
    r2 = _request(sock, _base("turn.finalized", ref))
    assert r2["status"] == "ok"
    assert r2["data"]["db_turn_id"] == first_db_id  # 更新同一条

    with gw_turn_finalized["engine"].connect() as conn:
        rows = conn.execute(
            repo.turns.select().where(repo.turns.c.host_turn_id == "H-1")
        ).mappings().all()
        assert len(rows) == 1
        row = rows[0]
        # turn_index / original_user_text 保持首次值（ADR-010 字段矩阵）
        assert row["turn_index"] == 1
        assert row["original_user_text"] == "银河麒麟桌面系统测试"
        # outbox 再次入队（refinalize:true）
        pending = repo.claim_pending_outbox(
            conn, now_iso=datetime.now(timezone.utc).isoformat(), max_retries=3
        )
        refinalized = [json.loads(p["payload"]) for p in pending if p["payload"]]
        assert any(x.get("refinalize") is True for x in refinalized)


# ═══════════════════════════════════════════════════════════════════════════
# PR#65 Rework 修复测试（T1/T3/T4/T8/T9：B1 + 热修）
# 直接调用 handler（不经 UDS），Windows/VM 均可运行；UDS 全链路由
# gw_turn_finalized fixture 覆盖（VM L2）。
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def handler_env(tmp_path):
    """直接注册 turn.finalized handler 并返回调用包装器（跨用户/校验逻辑测试）。"""
    eng = create_db_engine(str(tmp_path / "handler_env_pr2.db"))
    init_schema(eng)
    registry = HandlerRegistry()
    register_default_handlers(registry)
    resolver = InMemorySourceResolver(
        {
            "ref://turn/H-1": ResolvedContent(original_user_text="银河麒麟桌面系统测试"),
            "ref://turn/H-2": ResolvedContent(original_user_text="用户 B 的正文"),
        }
    )

    def _uow_factory():
        return UnitOfWork(eng)

    register_turn_finalized_handler(registry, uow_factory=_uow_factory, resolver=resolver)

    def _invoke(payload, *, trace_id="trc-1", idem_key=None):
        h = registry.route("turn.finalized")
        ctx = RequestContext(
            request_id="req-d",
            trace_id=trace_id,
            method="turn.finalized",
            deadline_ms=5000,
            idempotency_key=idem_key,
        )
        return h(payload, ctx)

    yield {"engine": eng, "invoke": _invoke, "registry": registry}
    clear_request_context()


# ── T1 跨用户 A/B 竞争（B1） ──


def _payload_for(user_id, session_id, host_turn_id, event_id, idem_key, source_ref):
    p = _valid_payload()
    p["metadata"].update(
        {
            "user_id": user_id,
            "session_id": session_id,
            "turn_id": host_turn_id,
            "event_id": event_id,
            "idempotency_key": idem_key,
            "source_reference": source_ref,
        }
    )
    return p


def test_t1_cross_user_session_pollution_blocked(handler_env):
    """B1 T1：A（uA/s1/H-1）成功 → B（uB/s1/H-1，新 idem key）→ INVALID_REQUEST。

    断言：
      - B 得到 INVALID_REQUEST；
      - 错误 message 固定英文，不含 A 的 conversation_id/db_turn_id；
      - A 的 turn 未变；无新增 Turn/Outbox/幂等缓存行。
    """
    env = handler_env["engine"]
    invoke = handler_env["invoke"]

    # A 首次写入成功
    resp_a = invoke(
        _payload_for("uA", "s1", "H-1", "evt-A1", "idem-A", "ref://turn/H-1"),
        trace_id="trc-A",
    )
    assert resp_a["db_turn_id"] > 0
    assert resp_a["conversation_id"] > 0
    conv_a = resp_a["conversation_id"]
    turn_a = resp_a["db_turn_id"]

    # B 复用 uA 的 session_id（同 s1/H-1，新 idempotency_key）→ INVALID_REQUEST
    with pytest.raises(RequestValidationError) as ei:
        invoke(
            _payload_for("uB", "s1", "H-1", "evt-B1", "idem-B", "ref://turn/H-2"),
            trace_id="trc-B",
        )
    msg = str(ei.value)
    assert "ownership" in msg or "conflict" in msg  # 固定英文 safe_message
    # 不回显 A 的 conversation_id / db_turn_id
    assert str(conv_a) not in msg
    assert str(turn_a) not in msg

    # A 的 turn 未变
    with env.connect() as conn:
        rows = conn.execute(
            repo.turns.select().where(repo.turns.c.host_turn_id == "H-1")
        ).mappings().all()
        assert len(rows) == 1
        assert rows[0]["original_user_text"] == "银河麒麟桌面系统测试"
        # B 的 ref://turn/H-2 未被写入
        b_rows = conn.execute(
            repo.turns.select().where(repo.turns.c.host_turn_id == "H-2")
        ).mappings().all()
        assert len(b_rows) == 0
        # 无新增 outbox（A 的 1 条保留）
        pending = repo.claim_pending_outbox(
            conn, now_iso=datetime.now(timezone.utc).isoformat(), max_retries=3
        )
        assert len(pending) == 1
        # B 的 idempotency 缓存未写入
        cached_b = repo.get_idempotency_cache(
            conn, user_id="uB", session_id="s1", idempotency_key="idem-B"
        )
        assert cached_b is None


def test_t1_find_turn_by_host_user_scoped(handler_env):
    """B1 定位项：find_turn_by_host 强制 user join——B 查不到 A 的 turn。"""
    env = handler_env["engine"]
    invoke = handler_env["invoke"]
    invoke(
        _payload_for("uA", "s1", "H-1", "evt-A1", "idem-A", "ref://turn/H-1"),
        trace_id="trc-A",
    )
    with env.connect() as conn:
        found_a = repo.find_turn_by_host(
            conn, session_id="s1", host_turn_id="H-1", user_id="uA"
        )
        found_b = repo.find_turn_by_host(
            conn, session_id="s1", host_turn_id="H-1", user_id="uB"
        )
        assert found_a is not None
        assert found_b is None  # B 无法命中 A 的 turn → 走 INSERT/resolver/B 自己会话


def test_t1_conversation_ownership_dao_layer(handler_env):
    """B1 DAO 层防御：uB 直接 upsert uA 的 session → ConversationOwnershipError。"""
    env = handler_env["engine"]
    with UnitOfWork(env) as uow:
        cid = repo.upsert_conversation(uow.conn, user_id="uA", session_id="s1")
        assert cid > 0
    with pytest.raises(repo.ConversationOwnershipError):
        with UnitOfWork(env) as uow:
            repo.upsert_conversation(uow.conn, user_id="uB", session_id="s1")


# ── T3 并发 IntegrityError 幂等回查（fingerprint compare + unwrap） ──


def test_t3_concurrent_integrity_idempotency_unwrap(handler_env):
    """T3：预占三元组缓存后再次执行 → 回查走指纹比对，返回首次响应。

    模拟并发双写：直接写缓存（另一请求已完成），同三元组不同指纹 → 冲突；
    同指纹 → 回查命中返回首次缓存（不执行业务副作用）。
    """
    env = handler_env["engine"]
    first = {"db_turn_id": 42, "host_turn_id": "H-3", "conversation_id": 9, "ok": "first"}

    # 预占缓存：fingerprint A
    with UnitOfWork(env) as uow:
        repo.write_idempotency_cache(
            uow.conn,
            user_id="uA", session_id="s3", idempotency_key="idem-3",
            response=repo._wrap_response(first, "fp-A"),
        )

    # 不同指纹（fp-B）→ IdempotencyConflictError（走指纹比对）
    with pytest.raises(repo.IdempotencyConflictError):
        with UnitOfWork(env) as uow:
            uow.execute_idempotent(
                user_id="uA", session_id="s3", idempotency_key="idem-3",
                business_fn=lambda: {"db_turn_id": 999, "ok": "second"},
                request_fingerprint="fp-B",
            )

    # 同指纹（fp-A）→ 回查返回首次缓存，from_cache=True
    with UnitOfWork(env) as uow:
        resp, from_cache = uow.execute_idempotent(
            user_id="uA", session_id="s3", idempotency_key="idem-3",
            business_fn=lambda: {"db_turn_id": 999, "ok": "second"},
            request_fingerprint="fp-A",
        )
    assert from_cache is True
    assert resp == first  # 首次响应 unwrap 还原


# ── T4 指纹一致 unwrap 首次响应（_unwrap_response 层单测） ──


def test_t4_unwrap_response_fingerprint():
    """T4：_unwrap_response 指纹一致返回首次响应；不一致抛 IdempotencyConflictError。"""
    first = {"db_turn_id": 1, "conversation_id": 1}
    wrapped = repo._wrap_response(first, "fp-X")
    stored = json.dumps(wrapped)
    # 指纹一致 → 首次响应
    assert repo._unwrap_response(stored, "fp-X") == first
    # 指纹不一致 → 冲突
    with pytest.raises(repo.IdempotencyConflictError):
        repo._unwrap_response(stored, "fp-OTHER")
    # legacy 无 wrapper 的缓存行 → 直接返回（向后兼容）
    legacy = json.dumps(first)
    assert repo._unwrap_response(legacy, None) == first


# ── T9 M3 边界 / 严格 major.minor / 非空 ID / 带时区时间 ──


def test_t9_schema_version_strict_major_minor(handler_env):
    """M3.2：schema_version 必须严格 `1.<整数>`；1.0.0/1./1.abc → INVALID_REQUEST。"""
    for bad in ("1.0.0", "1.", "1.abc", "2.0", ""):
        p = _payload_for("uA", "s1", "H-T", "evt-T", "idem-T", "ref://turn/H-1")
        p["metadata"]["schema_version"] = bad
        with pytest.raises(RequestValidationError) as ei:
            handler_env["invoke"](p)
        assert "schema_version" in str(ei.value)


def test_t9_reject_blank_ids(handler_env):
    """M3.1：必填 ID/引用 空串/纯空白 → INVALID_REQUEST。"""
    for field in ("event_id", "user_id", "session_id", "turn_id", "idempotency_key", "source_reference"):
        for bad in ("", " ", "   "):
            p = _payload_for("uA", "s1", "H-T", "evt-T", "idem-T", "ref://turn/H-1")
            p["metadata"][field] = bad
            with pytest.raises(RequestValidationError):
                handler_env["invoke"](p)


def test_t9_reject_timezone_missing(handler_env):
    """M3.3：无时区时间 / 纯日期 → INVALID_REQUEST。"""
    for field in ("occurred_at", "collected_at"):
        p = _payload_for("uA", "s1", "H-T", "evt-T", "idem-T", "ref://turn/H-1")
        p["metadata"][field] = "2026-08-27T10:00:00"  # 无时区
        with pytest.raises(RequestValidationError):
            handler_env["invoke"](p)
    # 纯日期
    p = _payload_for("uA", "s1", "H-T", "evt-T", "idem-T", "ref://turn/H-1")
    p["metadata"]["occurred_at"] = "2026-08-27"
    with pytest.raises(RequestValidationError):
        handler_env["invoke"](p)


def test_t9_equivalent_time_fingerprint_idempotent(handler_env):
    """M3.5：等价时间表达（+00:00 / Z / +08:00 → 同指纹）幂等命中返回首次响应。"""
    invoke = handler_env["invoke"]
    env = handler_env["engine"]

    p1 = _payload_for("uA", "s1", "H-T9", "evt-T9", "idem-T9", "ref://turn/H-1")
    r1 = invoke(p1, trace_id="trc-A")
    assert r1["db_turn_id"] > 0

    # 等价表达：同一时刻 +08:00（finalized_at 换成 +08:00 表达同一绝对时刻）
    p2 = _payload_for("uA", "s1", "H-T9", "evt-T9", "idem-T9", "ref://turn/H-1")
    p2["metadata"]["occurred_at"] = "2026-08-27T18:00:00+08:00"
    p2["metadata"]["collected_at"] = "2026-08-27T18:00:01+08:00"
    p2["finalized_at"] = "2026-08-27T18:00:02+08:00"
    r2 = invoke(p2, trace_id="trc-B")
    # plus Z 表达
    p3 = _payload_for("uA", "s1", "H-T9", "evt-T9", "idem-T9", "ref://turn/H-1")
    p3["metadata"]["occurred_at"] = "2026-08-27T10:00:00Z"
    p3["metadata"]["collected_at"] = "2026-08-27T10:00:01Z"
    p3["finalized_at"] = "2026-08-27T10:00:02Z"
    r3 = invoke(p3, trace_id="trc-C")

    # 幂等命中 → 返回首次响应
    assert r2 == r1
    assert r3 == r1
    # 不重复落库
    with env.connect() as conn:
        rows = conn.execute(
            repo.turns.select().where(repo.turns.c.host_turn_id == "H-T9")
        ).mappings().all()
        assert len(rows) == 1


def test_t9_error_safe_message_no_leak(handler_env):
    """M3.6：错误 message 固定英文，不泄漏原始输入值（恶意 payload 不回显）。"""
    p = _payload_for("uA", "s1", "H-T", "evt-T", "idem-T", "ref://turn/H-1")
    p["metadata"]["session_id"] = "  "  # blank → INVALID_REQUEST
    p["metadata"]["event_id"] = "MALICIOUS-evt"
    with pytest.raises(RequestValidationError) as ei:
        handler_env["invoke"](p)
    msg = str(ei.value)
    # 固定英文 safe_message，不回显任何原始输入值
    assert "MALICIOUS-evt" not in msg
    assert "ref://turn/H-1" not in msg
    assert "H-T" not in msg


# ── T8 validation profile 正向写（M6：load_resolver_from_json → 真实落库） ──


def test_t8_load_resolver_from_json_and_write(tmp_path, handler_env):
    """M6：JSON sources → resolver → turn.finalized 正向落库 original_user_text + Outbox。"""
    from service.source_resolver import load_resolver_from_json

    sources = tmp_path / "sources.json"
    sources.write_text(
        json.dumps(
            {
                "ref://turn/J-1": {
                    "original_user_text": "来自 JSON 的原文",
                    "model_request": {"role": "user", "content": "你好"},
                    "model_response": {"role": "assistant", "content": "收到"},
                }
            }
        ),
        encoding="utf-8",
    )
    resolver = load_resolver_from_json(str(sources))
    assert resolver is not None
    resolved = resolver.resolve("ref://turn/J-1")
    assert resolved is not None
    assert resolved.original_user_text == "来自 JSON 的原文"

    # 用 JSON resolver 注册新 handler（模拟 app.main --validation-sources 路径）
    registry = handler_env["registry"]
    eng = handler_env["engine"]

    def _uow_factory():
        return UnitOfWork(eng)

    # 重新注册（覆盖 resolver）
    register_turn_finalized_handler(registry, uow_factory=_uow_factory, resolver=resolver)
    invoke = handler_env["invoke"]

    p = _payload_for("uA", "s2", "J-1", "evt-J", "idem-J", "ref://turn/J-1")
    resp = invoke(p, trace_id="trc-J")
    assert resp["db_turn_id"] > 0

    with eng.connect() as conn:
        row = conn.execute(
            repo.turns.select().where(repo.turns.c.host_turn_id == "J-1")
        ).mappings().first()
        assert row is not None
        assert row["original_user_text"] == "来自 JSON 的原文"
        pending = repo.claim_pending_outbox(
            conn, now_iso=datetime.now(timezone.utc).isoformat(), max_retries=3
        )
        assert len(pending) >= 1
