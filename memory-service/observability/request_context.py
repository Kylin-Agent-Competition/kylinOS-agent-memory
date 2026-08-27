"""request_context.py — 请求上下文线程局部（T3.3）

用途：Gateway `_dispatch` 设置/清理当前请求 ID（request_id/trace_id/method/
event_id），各层（gateway/DAO/Worker）日志经 JSON Formatter 自动携带，实现
checklist 6.4「同一 trace_id 在网关/DAO/Worker 日志可关联」。event_id 供
turn.finalized 业务事件与 Outbox Worker 跨线程关联（M4）。

实现：threading.local（每连接线程独立；连接处理线程为 daemon 线程，请求结束清理，
无跨请求泄漏）。与 asyncio 无关（UDS Gateway 为多线程阻塞模型）。
"""

from __future__ import annotations

import threading
from typing import Dict

_local = threading.local()


def set_request_context(
    *, request_id: str, trace_id: str, method: str, event_id: str = ""
) -> None:
    """设置当前线程请求上下文（连接线程处理每个请求时调用；event_id 默认空串向后兼容）。"""
    _local.request_id = request_id
    _local.trace_id = trace_id
    _local.method = method
    _local.event_id = event_id


def clear_request_context() -> None:
    """清理当前线程请求上下文（请求处理结束 finally 调用，防泄漏）。"""
    _local.request_id = ""
    _local.trace_id = ""
    _local.method = ""
    _local.event_id = ""


def get_request_context() -> Dict[str, str]:
    """读取当前线程请求上下文（JSON Formatter 注入用；无上下文返回空串）。"""
    return {
        "request_id": getattr(_local, "request_id", "") or "",
        "trace_id": getattr(_local, "trace_id", "") or "",
        "method": getattr(_local, "method", "") or "",
        "event_id": getattr(_local, "event_id", "") or "",
    }
