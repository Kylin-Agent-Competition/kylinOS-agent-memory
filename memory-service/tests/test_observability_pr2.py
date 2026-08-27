"""PR-2 可观测性测试：T3.1 health backlog + T3.2/T3.3 JSON 结构化日志 + 请求上下文"""

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
from gateway import protocol as proto
from gateway.handlers import health_handler, register_default_handlers
from gateway.registry import HandlerRegistry, RequestContext
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
    empty = {"request_id": "", "trace_id": "", "method": "", "event_id": ""}
    assert get_request_context() == empty
    set_request_context(request_id="r1", trace_id="t1", method="echo", event_id="e1")
    assert get_request_context() == {
        "request_id": "r1", "trace_id": "t1", "method": "echo", "event_id": "e1",
    }
    clear_request_context()
    assert get_request_context() == empty


def test_request_context_event_id_backward_compat():
    """M4：不传 event_id 时保持向后兼容（默认空串），不影响既有 3 参数调用。"""
    empty = {"request_id": "", "trace_id": "", "method": "", "event_id": ""}
    assert get_request_context() == empty
    set_request_context(request_id="r1", trace_id="t1", method="echo")
    assert get_request_context() == {
        "request_id": "r1", "trace_id": "t1", "method": "echo", "event_id": "",
    }
    clear_request_context()
    assert get_request_context() == empty


def test_request_context_thread_isolation():
    """并发连接隔离：不同线程上下文互不干扰（T3.2 并发连接隔离）。"""
    set_request_context(request_id="main-req", trace_id="main-tr", method="main")
    seen = {}

    def _worker(tid):
        set_request_context(request_id=f"req-{tid}", trace_id=f"tr-{tid}", method="health", event_id=f"evt-{tid}")
        seen[tid] = get_request_context()
        time.sleep(0.2)
        seen[f"{tid}-after"] = get_request_context()

    ts = [threading.Thread(target=_worker, args=(i,)) for i in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    # 主线程上下文未被污染
    assert get_request_context() == {
        "request_id": "main-req", "trace_id": "main-tr", "method": "main", "event_id": "",
    }
    for i in range(3):
        assert seen[i] == {
            "request_id": f"req-{i}", "trace_id": f"tr-{i}",
            "method": "health", "event_id": f"evt-{i}",
        }
        assert seen[f"{i}-after"] == seen[i]


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


# ── T6 Worker 跨线程恢复 trace_id/event_id（M4） ──


def test_worker_restores_trace_event_and_clears(tmp_path):
    """Outbox Worker 处理事件时恢复 trace_id/event_id 线程上下文，事件后清空（M4）。"""
    eng = create_db_engine(str(tmp_path / "worker_ctx_pr2.db"))
    init_schema(eng)
    with eng.begin() as conn:
        repo.enqueue_outbox(
            conn, aggregate_type="turn", aggregate_id="1",
            event_type=repo.EVENT_TURN_FINALIZED,
            payload={"trace_id": "trc-W1", "event_id": "evt-W1", "turn_id": 1},
            next_retry_at=datetime.now(timezone.utc).isoformat(),
        )

    seen = {}

    def _consumer(payload):
        # Worker 处理回调内读取线程上下文
        seen["ctx"] = dict(get_request_context())
        seen["payload"] = payload

    worker = OutboxWorker(eng, poll_interval_s=60, max_retries=3, consumer=_consumer)
    try:
        worker._poll_once()  # 直接跑一轮（test seam；生产为独立线程）
    finally:
        worker.stop()

    assert seen["ctx"]["trace_id"] == "trc-W1"
    assert seen["ctx"]["event_id"] == "evt-W1"
    assert seen["ctx"]["method"] == "outbox:turn.finalized"
    # 事件处理结束 → 上下文已清空（防线程本地泄漏/串号）
    assert get_request_context() == {
        "request_id": "", "trace_id": "", "method": "", "event_id": "",
    }
    # 成功 → outbox 行已删除
    with eng.connect() as conn:
        pending = repo.claim_pending_outbox(
            conn, now_iso=datetime.now(timezone.utc).isoformat(), max_retries=3
        )
        assert len(pending) == 0


# ── T7 health data.status 真实业务值（M5） ──


def _call_health(engine, metrics_fn):
    """直接构造 RequestContext 调用 health_handler（不依赖 UDS）。"""
    ctx = RequestContext(
        request_id="r", trace_id="t", method="health", deadline_ms=1000,
        extras={"engine": engine, "methods": ["echo"], "worker_metrics": metrics_fn},
    )
    return health_handler({}, ctx)


def test_health_status_ok_all_green(tmp_path):
    """全绿：DB 可达 + worker_metrics 正常 → data.status == ok。"""
    eng = create_db_engine(str(tmp_path / "h_ok_pr2.db"))
    init_schema(eng)

    def _metrics():
        return {"backlog": 0, "dead_letter": 0, "oldest_pending_created_at": None}

    data = _call_health(eng, _metrics)
    assert data["status"] == "ok"
    assert data["db"] == "ok"
    assert data["outbox"]["backlog"] == 0


def test_health_status_degraded_when_metrics_raises(tmp_path):
    """metrics 抛错 → data.status == degraded + 哨兵 backlog=-1（M5）。"""
    eng = create_db_engine(str(tmp_path / "h_fail_pr2.db"))
    init_schema(eng)

    def _boom():
        raise RuntimeError("db locked")

    data = _call_health(eng, _boom)
    assert data["status"] == "degraded"
    assert data["outbox"]["backlog"] == -1


def test_health_status_degraded_when_sentinel_backlog(tmp_path):
    """metrics 返回哨兵 backlog=-1（busy）→ data.status == degraded（M5）。"""
    eng = create_db_engine(str(tmp_path / "h_sentinel_pr2.db"))
    init_schema(eng)

    def _sentinel():
        return {"backlog": -1, "dead_letter": -1, "oldest_pending_created_at": None}

    data = _call_health(eng, _sentinel)
    assert data["status"] == "degraded"
    assert data["outbox"]["backlog"] == -1


def test_health_status_degraded_when_no_worker(tmp_path):
    """无 worker_metrics（Worker 未注入/未启动）→ data.status == degraded（M5）。"""
    eng = create_db_engine(str(tmp_path / "h_noworker_pr2.db"))
    init_schema(eng)
    data = _call_health(eng, None)
    assert data["status"] == "degraded"
    assert data["db"] == "ok"
    assert "outbox" not in data


def test_health_status_degraded_when_db_unreachable():
    """DB 不可达 → data.status == degraded（无论 worker）。"""
    data = _call_health(None, None)
    assert data["status"] == "degraded"
    assert data["db"] == "unreachable"
