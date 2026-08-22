"""D4D Gateway 端到端测试：FRZ-IPC-001~007（UDS 服务器 / 路由 / 错误码 / TIMEOUT / 停止拒绝）"""

from __future__ import annotations

import json
import os
import socket
import threading
import time

import pytest

from db.engine import create_db_engine, init_schema
from gateway import protocol as proto
from gateway.handlers import register_default_handlers
from gateway.registry import HandlerRegistry
from gateway.server import UDSGatewayServer


@pytest.fixture()
def gateway(tmp_path):
    eng = create_db_engine(str(tmp_path / "gw.db"))
    init_schema(eng)
    registry = HandlerRegistry()
    register_default_handlers(registry)
    sock = str(tmp_path / "memory.sock")
    server = UDSGatewayServer(sock, registry, engine=eng, default_deadline_ms=5000)
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    _wait_socket(sock)
    yield server, sock
    server.stop()


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


# ── 路由（FRZ-IPC-007） ──


def test_echo_ok(gateway):
    _server, sock = gateway
    resp = _request(sock, _base("echo", {"hello": "world"}))
    assert resp["status"] == "ok"
    assert resp["data"] == {"echo": {"hello": "world"}}
    assert resp["protocol_version"] == "1.0"
    assert resp["request_id"] == "req-1"


def test_health_ok(gateway):
    _server, sock = gateway
    resp = _request(sock, _base("health"))
    assert resp["status"] == "ok"
    assert resp["data"]["db"] == "ok"
    assert "echo" in resp["data"]["methods"]


def test_memory_retrieve_empty_context(gateway):
    # 主链未接入：真实空上下文（非假数据）
    _server, sock = gateway
    resp = _request(sock, _base("memory.retrieve", {"query": "我的偏好"}))
    assert resp["status"] == "ok"
    assert resp["data"]["context"] == []


def test_memory_store_unsupported(gateway):
    _server, sock = gateway
    resp = _request(sock, _base("memory.store", {"text": "x"}, idempotency_key="uuid-1"))
    assert resp["status"] == "error"
    assert resp["error_code"] == "UNSUPPORTED_METHOD"


def test_unknown_method_unsupported(gateway):
    _server, sock = gateway
    resp = _request(sock, _base("kaiming.custom.analyze"))
    assert resp["status"] == "error"
    assert resp["error_code"] == "UNSUPPORTED_METHOD"


# ── 协议错误（FRZ-IPC-001/002/003/006） ──


def test_bad_protocol_version(gateway):
    _server, sock = gateway
    msg = _base("echo")
    msg["protocol_version"] = "9.9"
    resp = _request(sock, msg)
    assert resp["status"] == "error"
    assert resp["error_code"] == "PROTOCOL_ERROR"


def test_missing_field_invalid_request(gateway):
    _server, sock = gateway
    msg = {"protocol_version": "1.0", "request_id": "r", "method": "echo"}
    resp = _request(sock, msg)
    assert resp["status"] == "error"
    assert resp["error_code"] == "INVALID_REQUEST"


def test_invalid_json_packet_protocol_error(gateway):
    _server, sock = gateway
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(5)
        s.connect(sock)
        bad = b"{broken"
        s.sendall(len(bad).to_bytes(4, "big") + bad)
        buf = s.recv(65536)
    resp, _ = proto.decode_packet(buf)
    assert resp["status"] == "error"
    assert resp["error_code"] == "PROTOCOL_ERROR"


# ── deadline（FRZ-IPC-004） ──


def test_deadline_timeout(gateway):
    _server, sock = gateway
    # 注册慢 handler：处理 0.5s > deadline 100ms → TIMEOUT（FRZ-IPC-004 §4.2）
    import time as _time

    def _slow_handler(payload, ctx):
        _time.sleep(0.5)
        return {"slow": True}

    _server._registry.register("slow.method", _slow_handler)
    resp = _request(sock, _base("slow.method", deadline_ms=100))
    assert resp["status"] == "error"
    assert resp["error_code"] == "TIMEOUT"


def test_deadline_not_exceeded_ok(gateway):
    # 处理时间 < deadline → 正常返回（不误报 TIMEOUT）
    _server, sock = gateway
    resp = _request(sock, _base("echo", {"x": 1}, deadline_ms=2000))
    assert resp["status"] == "ok"


# ── 停止后拒绝新请求（H3 防御） ──


def test_stop_rejects_after_shutdown(tmp_path):
    eng = create_db_engine(str(tmp_path / "gw2.db"))
    init_schema(eng)
    registry = HandlerRegistry()
    register_default_handlers(registry)
    sock = str(tmp_path / "memory2.sock")
    server = UDSGatewayServer(sock, registry, engine=eng)
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    _wait_socket(sock)
    server.stop()
    # 停止后连接应被拒绝或立即关闭
    time.sleep(0.2)
    with pytest.raises(OSError):
        _request(sock, _base("echo"), timeout=2.0)


def test_stop_unlinks_socket(tmp_path):
    """stop() 必须 unlink socket 文件（TD-IPC-001 回归）。

    修复前：stop() 只 close server sock，socket 文件残留；麒麟/Linux 下
    停后 connect() 仍成功、请求被 ECONNRESET 拒绝（vfy_uds.py 6.7 观测）。
    修复后：stop() unlink socket 文件 → 停后文件不存在、connect() 立即失败。
    """
    eng = create_db_engine(str(tmp_path / "gw_unlink.db"))
    init_schema(eng)
    registry = HandlerRegistry()
    register_default_handlers(registry)
    sock = str(tmp_path / "unlink.sock")
    server = UDSGatewayServer(sock, registry, engine=eng)
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    _wait_socket(sock)
    assert os.path.exists(sock)
    server.stop()
    # socket 文件已删除（修复点）
    assert not os.path.exists(sock)
    # 停后 connect 立即失败（无残留文件可连）
    with pytest.raises(OSError):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(sock)
    # stop 幂等：再次调用不抛错（文件已不存在）
    server.stop()
