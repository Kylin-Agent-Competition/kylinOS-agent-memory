"""PR-2 turn.finalized 测试：ADR-010（写链路 / 幂等指纹 / 错误路径 / Upsert / resolver）"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from datetime import datetime, timezone

import pytest

from db.engine import create_db_engine, init_schema
from db import repositories as repo
from gateway import protocol as proto
from gateway.handlers import register_default_handlers, register_turn_finalized_handler
from gateway.registry import HandlerRegistry
from gateway.server import UDSGatewayServer
from service.source_resolver import InMemorySourceResolver, ResolvedContent


def _wait_socket(path, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path):
            return
        time.sleep(0.05)
    raise TimeoutError(f"socket not ready: {path}")


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
        assert payload["occurred_at"] == "2026-08-27T10:00:00+00:00"


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


def test_turn_finalized_resolver_miss_internal_error(gw_turn_finalized):
    """resolver 未命中（返回 None）→ INTERNAL_ERROR（safe，不编造正文）。"""
    payload = _valid_payload()
    payload["metadata"]["source_reference"] = "ref://missing/XXX"
    payload["metadata"]["turn_id"] = "H-MISS"
    resp = _request(gw_turn_finalized["sock"], _base("turn.finalized", payload))
    assert resp["status"] == "error"
    assert resp["error_code"] == "INTERNAL_ERROR"
    # 未落库（失败请求不写 turns）
    with gw_turn_finalized["engine"].connect() as conn:
        row = conn.execute(
            repo.turns.select().where(repo.turns.c.host_turn_id == "H-MISS")
        ).first()
        assert row is None


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
