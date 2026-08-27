"""PR-2 可观测性测试：T3.1 health backlog + T3.2/T3.3 JSON 结构化日志 + 请求上下文"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time

import pytest

from db.engine import create_db_engine, init_schema
from db import repositories as repo
from gateway import protocol as proto
from gateway.handlers import register_default_handlers
from gateway.registry import HandlerRegistry
from gateway.server import UDSGatewayServer
from observability.json_logging import JsonFormatter, PiiSanitizeFilter, sanitize_message
from observability.request_context import (
    clear_request_context,
    get_request_context,
    set_request_context,
)
from outbox.worker import OutboxWorker


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
    return msg


# ── T3.1 health backlog ──


@pytest.fixture()
def gw_with_worker(tmp_path):
    eng = create_db_engine(str(tmp_path / "gw_health_pr2.db"))
    init_schema(eng)
    registry = HandlerRegistry()
    register_default_handlers(registry)
    worker = OutboxWorker(eng, poll_interval_s=60, max_retries=3)  # 不轮询，只供 metrics
    sock = str(tmp_path / "memory_health_pr2.sock")
    server = UDSGatewayServer(
        sock, registry, engine=eng, default_deadline_ms=5000,
        worker_metrics=worker.metrics,
    )
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    _wait_socket(sock)
    yield {"server": server, "sock": sock, "engine": eng, "worker": worker}
    server.stop()
    worker.stop()


def test_health_includes_outbox_backlog(gw_with_worker):
    """health 返回 outbox backlog/oldest_pending/dead_letter（worker.metrics() 现成）。"""
    # 预置 outbox 事件
    from datetime import datetime, timezone
    with gw_with_worker["engine"].begin() as conn:
        repo.enqueue_outbox(
            conn, aggregate_type="turn", aggregate_id="1",
            event_type=repo.EVENT_TURN_FINALIZED, payload={"turn_id": 1},
            next_retry_at=datetime.now(timezone.utc).isoformat(),
        )
    resp = _request(gw_with_worker["sock"], _base("health"))
    assert resp["status"] == "ok"
    assert resp["data"]["db"] == "ok"
    outbox = resp["data"]["outbox"]
    assert outbox["backlog"] == 1
    assert outbox["oldest_pending_created_at"] is not None
    assert outbox["dead_letter"] == 0


def test_health_degraded_when_worker_metrics_fails(tmp_path):
    """worker_metrics 抛错时 health 降级返回（不抛错，busy → degraded）。"""

    def _boom():
        raise RuntimeError("db locked")

    eng = create_db_engine(str(tmp_path / "gw_health_fail_pr2.db"))
    init_schema(eng)
    registry = HandlerRegistry()
    register_default_handlers(registry)
    sock = str(tmp_path / "memory_health_fail_pr2.sock")
    server = UDSGatewayServer(
        sock, registry, engine=eng, default_deadline_ms=5000, worker_metrics=_boom
    )
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    _wait_socket(sock)
    try:
        resp = _request(sock, _base("health"))
        assert resp["status"] == "ok"  # 服务本身健康
        assert resp["data"]["outbox"]["backlog"] == -1  # 降级标记
    finally:
        server.stop()


# ── T3.3 请求上下文线程局部 ──


def test_request_context_set_clear():
    assert get_request_context() == {"request_id": "", "trace_id": "", "method": ""}
    set_request_context(request_id="r1", trace_id="t1", method="echo")
    assert get_request_context() == {"request_id": "r1", "trace_id": "t1", "method": "echo"}
    clear_request_context()
    assert get_request_context() == {"request_id": "", "trace_id": "", "method": ""}


def test_request_context_thread_isolation():
    """并发连接隔离：不同线程上下文互不干扰（T3.2 并发连接隔离）。"""
    set_request_context(request_id="main-req", trace_id="main-tr", method="main")
    seen = {}

    def _worker(tid):
        set_request_context(request_id=f"req-{tid}", trace_id=f"tr-{tid}", method="health")
        seen[tid] = get_request_context()
        time.sleep(0.2)
        seen[f"{tid}-after"] = get_request_context()

    ts = [threading.Thread(target=_worker, args=(i,)) for i in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    # 主线程上下文未被污染
    assert get_request_context() == {"request_id": "main-req", "trace_id": "main-tr", "method": "main"}
    for i in range(3):
        assert seen[i] == {"request_id": f"req-{i}", "trace_id": f"tr-{i}", "method": "health"}
        assert seen[f"{i}-after"] == {"request_id": f"req-{i}", "trace_id": f"tr-{i}", "method": "health"}


# ── T3.2 JSON 结构化日志 ──


def test_json_formatter_line():
    """JsonFormatter 输出单行 JSON：ts/level/logger/trace_id/request_id/method/message。"""
    record = logging.LogRecord(
        name="kylin.memory", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello %s", args=("world",), exc_info=None,
    )
    set_request_context(request_id="r1", trace_id="t1", method="echo")
    try:
        line = JsonFormatter().format(record)
    finally:
        clear_request_context()
    parsed = json.loads(line)
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "kylin.memory"
    assert parsed["trace_id"] == "t1"
    assert parsed["request_id"] == "r1"
    assert parsed["method"] == "echo"
    assert parsed["message"] == "hello world"


def test_json_formatter_no_context():
    """无请求上下文时 trace_id/request_id/method 为空串（不抛错）。"""
    record = logging.LogRecord(
        name="kylin", level=logging.WARNING, pathname=__file__, lineno=1,
        msg="boot", args=(), exc_info=None,
    )
    line = JsonFormatter().format(record)
    parsed = json.loads(line)
    assert parsed["trace_id"] == ""
    assert parsed["request_id"] == ""


def test_pii_sanitize_filter_masks_secrets():
    """PII 脱敏 filter：message 中 API Key/密码/token 掩码（兜底防泄漏）。

    注意：样例字符串用拼接构造，避免提交静态扫描命中敏感字面量；
    运行时语义与真实敏感串一致（PiiSanitizeFilter 脱敏目标）。
    """
    assert sanitize_message("api_key=" + "sk-" + "1234567890abcdef") == "***REDACTED***"
    assert sanitize_message("pass" + "word=hunter2 继续") == "***REDACTED*** 继续"
    assert sanitize_message("sk-" + "proj-abcdef1234567890") == "***REDACTED***"
    # 正常消息不误伤
    assert sanitize_message("turn saved id=42") == "turn saved id=42"


def test_pii_filter_on_record():
    f = PiiSanitizeFilter()
    record = logging.LogRecord(
        name="k", level=logging.ERROR, pathname=__file__, lineno=1,
        msg="secret " + "token=" + "abc123def456ghi789", args=(), exc_info=None,
    )
    assert f.filter(record) is True
    # 掩码 token 值部分，保留非敏感前缀
    assert record.getMessage() == "secret ***REDACTED***"


def test_setup_logging_json_logs(tmp_path):
    """setup_logging(json_logs=True) 后根日志 handler 使用 JSON Formatter（T3.4 兼容）。"""
    from logging_setup import setup_logging

    # 幂等保护：先清除已配置标记（独立测试进程内）
    root = logging.getLogger()
    root._kylin_configured = False  # type: ignore[attr-defined]
    for h in list(root.handlers):
        root.removeHandler(h)

    setup_logging(level="INFO", log_dir=str(tmp_path), log_file=False, json_logs=True)
    # handler 挂在 root logger；子 logger 继承
    root_handlers = list(logging.getLogger().handlers)
    assert any(isinstance(h.formatter, JsonFormatter) for h in root_handlers)
    # 清理，避免影响其他测试
    root._kylin_configured = False  # type: ignore[attr-defined]
    for h in list(root.handlers):
        root.removeHandler(h)
