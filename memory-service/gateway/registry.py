"""registry.py — D4D Handler Registry（FRZ-IPC-007 路由表）

职责：
  - 方法 → handler 映射（注册/路由）
  - 未注册方法 → UNSUPPORTED_METHOD（冻结语义）
  - handler 签名：handler(payload: dict, ctx: RequestContext) -> dict（data 部分）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from gateway.protocol import ERROR_CODE_UNSUPPORTED_METHOD

logger = logging.getLogger(__name__)

# handler 类型：payload dict + ctx → data dict
Handler = Callable[[Dict[str, Any], "RequestContext"], Dict[str, Any]]


@dataclass
class RequestContext:
    """请求上下文（handler 可用的请求级信息）。"""

    request_id: str
    trace_id: str
    method: str
    deadline_ms: int
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)


class HandlerRegistry:
    """方法路由注册表（FRZ-IPC-007）。"""

    def __init__(self) -> None:
        self._handlers: Dict[str, Handler] = {}

    def register(self, method: str, handler: Handler) -> None:
        """注册 handler（重复注册覆盖并告警，防止静默覆盖）。"""
        if method in self._handlers:
            logger.warning("handler 重复注册，覆盖: %s", method)
        self._handlers[method] = handler

    def unregister(self, method: str) -> None:
        self._handlers.pop(method, None)

    def get(self, method: str) -> Optional[Handler]:
        return self._handlers.get(method)

    def route(self, method: str) -> Handler:
        """路由：未注册 → 抛 UnsupportedMethodError（Gateway 转 UNSUPPORTED_METHOD）。"""
        handler = self._handlers.get(method)
        if handler is None:
            raise UnsupportedMethodError(method)
        return handler

    def methods(self) -> list[str]:
        return sorted(self._handlers.keys())


class UnsupportedMethodError(Exception):
    """方法未注册（FRZ-IPC-007 → UNSUPPORTED_METHOD）。"""

    def __init__(self, method: str) -> None:
        super().__init__(f"unsupported method: {method}")
        self.method = method
        self.error_code = ERROR_CODE_UNSUPPORTED_METHOD
