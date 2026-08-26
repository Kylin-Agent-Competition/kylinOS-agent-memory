"""handlers.py — D4D 内置 handler（FRZ-IPC-007 路由表）

活跃方法：echo / health / memory.retrieve（真实空上下文，非假数据）
memory.store 未实现 → UNSUPPORTED_METHOD（Gate 0 预期）
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from db.engine import db_health_check
from gateway.protocol import ERROR_CODE_UNSUPPORTED_METHOD
from gateway.registry import HandlerRegistry, RequestContext

logger = logging.getLogger(__name__)


def echo_handler(payload: Dict[str, Any], ctx: RequestContext) -> Dict[str, Any]:
    """echo：回显 payload（调试/连通性验证，ECHO-003）。"""
    return {"echo": payload}


def health_handler(payload: Dict[str, Any], ctx: RequestContext) -> Dict[str, Any]:
    """health：服务状态 + DB 可达性探测（真实 SELECT 1）。"""
    engine = ctx.extras.get("engine")
    db_ok = db_health_check(engine) if engine is not None else False
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "unreachable",
        "methods": ctx.extras.get("methods", []),
    }


def memory_retrieve_handler(payload: Dict[str, Any], ctx: RequestContext) -> Dict[str, Any]:
    """memory.retrieve：返回真实空上下文（检索主链后续接入，禁止假数据）。"""
    # 契约：FR-FB-001 降级路径（L2 连接失败 / L1 超时）均返回空 context；
    # 主链未接入前返回真实空结果，不构造虚假记忆。
    # PR#52 Issue 1：日志禁止记录用户正文/PII（query 为用户对话正文）。
    # 只记 method/request_id，不落 query 内容（与 logging_setup 安全声明一致）。
    logger.info(
        "memory.retrieve method=%s request_id=%s（主链未接入，返回空上下文）",
        ctx.method,
        ctx.request_id,
    )
    return {"context": [], "degraded": False, "reason": "retrieval main chain pending"}


def memory_store_handler(payload: Dict[str, Any], ctx: RequestContext) -> Dict[str, Any]:
    """memory.store：未实现 → UNSUPPORTED_METHOD（FRZ-IPC-007，Gate 0 预期）。"""
    raise _UnsupportedStoreError()


class _UnsupportedStoreError(Exception):
    """memory.store 未实现（转 UNSUPPORTED_METHOD）。"""

    error_code = ERROR_CODE_UNSUPPORTED_METHOD


def register_default_handlers(registry: HandlerRegistry) -> None:
    """注册冻结路由表的默认 handler（echo/health/memory.retrieve/store）。"""
    registry.register("echo", echo_handler)
    registry.register("health", health_handler)
    registry.register("memory.retrieve", memory_retrieve_handler)
    registry.register("memory.store", memory_store_handler)
    # 供 health handler 使用（方法列表由 server 注入 extras）
    registry._methods_hint = list(registry.methods())  # type: ignore[attr-defined]
