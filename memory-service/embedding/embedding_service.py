"""
embedding_service.py — 轨道 A Day5 最小垂直链路 Service 层

将 Day4 的真实 EmbeddingProvider 接入最小链路：
- 接收 UDS + 长度前缀 JSON 协议请求（embed）
- 调用 EmbeddingProvider（进程级单例，真实 SDK 调用）
- 不可用时返回结构化错误 + 真实降级（明确空向量）

设计要点：
1. 所有对外方法返回 dict（JSON 可序列化），不抛异常到调用方。
2. 错误结构化：{"ok": false, "error": {"code": "...", "message": "..."}}
3. 降级：Provider 可用但调用失败时，返回明确空向量 + degraded 标记
   （区别于"无固定样例假实现"——空向量是明确语义，不是假数据）。
4. Bridge 调用在独立线程池执行（Day5 第 3 条：不阻塞聊天线程）。
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any, Dict, List, Optional

from providers import (
    EmbeddingProvider,
    EmbeddingResult,
    ProviderError,
    ProviderErrorCode,
)
from embedding.protocol import PROTOCOL_VERSION, ProtocolError, parse_envelope

# Bridge 调用统一放线程池：SDK embed 可能耗时（IPC），不阻塞聊天线程（Day5-3）
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embed-bridge")
_executor_shutdown = False  # shutdown 标记：submit 前若已关闭则惰性重建


def shutdown_executor() -> None:
    """关闭 Bridge 线程池（进程/服务停止时释放资源，审查报告 #3）。

    幂等；关闭后再 submit 会惰性重建（见 _submit_bridge），保持进程级单例语义。
    """
    global _executor, _executor_shutdown
    if _executor_shutdown:
        return
    _executor.shutdown(wait=False)
    _executor_shutdown = True


def _submit_bridge(fn, *args, **kwargs):
    """提交 Bridge 调用到线程池；若已 shutdown 则重建后提交（幂等重启语义）。"""
    global _executor, _executor_shutdown
    if _executor_shutdown:
        _executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="embed-bridge")
        _executor_shutdown = False
    return _executor.submit(fn, *args, **kwargs)

# 架构 4.4 方法名（总体架构文档 TABLE 15 风格：memory.*）
_METHODS = {
    "memory.embed",
    "memory.embed_batch",
    "memory.ping",
    "memory.health",
}


class EmbeddingService:
    """Embedding 最小垂直链路 Service。

    职责：协议解码 → Provider 调用 → 结构化响应（含降级）。
    不持有 Provider 生命周期（由调用方/进程级单例管理）。
    """

    def __init__(self, provider: Optional[EmbeddingProvider] = None) -> None:
        # Day4 Provider 是进程级单例：不传则内部创建（共享 Bridge/session）
        self._provider = provider if provider is not None else EmbeddingProvider()
        self._started = False

    # ── 生命周期 ──

    def start(self) -> None:
        """启动 Service：确保 Provider 就绪。幂等。"""
        if self._started:
            return
        self._provider.start()
        self._started = True

    def close(self) -> None:
        """释放引用。幂等。"""
        self._provider.close()
        self._started = False

    # ── 对外接口（UDS 协议处理入口，架构 4.4 envelope） ──

    def handle_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """协议分发入口（架构 4.4 IPC 契约 envelope 格式）。

        Args:
            req: 长度前缀 JSON 解码后的 envelope dict：
                {"protocol_version": "1.0", "request_id": "...", "trace_id": "...",
                 "method": "memory.embed", "deadline_ms": 5000,
                 "payload": {"text": "..."}}

        Returns:
            响应 envelope：protocol_version/method + request_id/trace_id（回显）
            + ok/result|error（含降级标记）。
        """
        try:
            method, payload, request_id, trace_id, _deadline = parse_envelope(
                req, expected_methods=_METHODS)
        except ProtocolError as exc:
            return self._envelope_error(
                "ERR_PROTOCOL", str(exc), req, method="unknown")

        if method == "memory.embed":
            body = self.embed(payload.get("text", ""),
                              timeout_ms=payload.get("timeout_ms", 5000))
        elif method == "memory.embed_batch":
            body = self.embed_batch(payload.get("texts", []),
                                    timeout_ms=payload.get("timeout_ms", 30000))
        elif method == "memory.ping":
            body = {"ok": True, "result": "pong"}
        elif method == "memory.health":
            body = self.health()
        else:  # pragma: no cover - parse_envelope 已校验 method
            body = self._error("ERR_INVALID_REQUEST", f"unknown method: {method!r}")

        return self._envelope(body, method, request_id, trace_id)

    # ── 健康检查（架构 TABLE 15: memory.health） ──

    def health(self) -> Dict[str, Any]:
        """返回服务分项健康状态（不触发 SDK 调用，只读状态）。

        Returns:
            {"ok": true, "result": {"service": "ok|stopped",
                                     "provider": "ready|stopped",
                                     "bridge_loaded": bool,
                                     "bridge_has_session": bool,
                                     "degraded": false}}
        """
        bridge = getattr(self._provider, "_bridge", None)
        return {
            "ok": True,
            "result": {
                "service": "ok" if self._started else "stopped",
                "provider": "ready" if self._started else "stopped",
                "bridge_loaded": bool(getattr(bridge, "loaded", False))
                if bridge is not None else False,
                "bridge_has_session": bool(getattr(bridge, "has_session", False))
                if bridge is not None else False,
                "degraded": False,
            },
        }

    # ── 核心操作 ──

    def embed(self, text: str, *, timeout_ms: int = 5000) -> Dict[str, Any]:
        """单条文本向量化（真实 SDK 调用，降级安全）。

        Returns:
            {"ok": true, "result": {"vector": [...], "dimension": 768, "l2_norm": 1.0}}
            {"ok": false, "error": {"code": "...", "message": "..."}}
            {"ok": true, "result": {"vector": [], "dimension": 0, "degraded": true},
             "degraded": true}   # 真实降级：明确空向量
        """
        if not isinstance(text, str):
            return self._error(ProviderErrorCode.ERR_INVALID_TEXT.name,
                               f"text must be str, got {type(text).__name__}")

        try:
            # Day5-3: Bridge 调用放线程池，不阻塞聊天线程
            fut = _submit_bridge(self._provider.embed, text, timeout_ms=timeout_ms)
            try:
                result = fut.result(timeout=timeout_ms / 1000.0 + 1.0)
            except FutureTimeout:
                # 超时：返回结构化错误；尽力取消任务（线程池中的任务可能无法中断，
                # 但调用方线程立即获得控制权，不阻塞聊天线程）。
                # [TD-A-005-01] 主动超时中断未实现：fut.cancel() 对已运行任务无效，
                # 精确中断需 Bridge 内部定时器（Day6+ 跟踪）。
                fut.cancel()
                return self._error(ProviderErrorCode.ERR_TIMEOUT.name,
                                   "embed timed out (Bridge 未返回)")
        except ProviderError as exc:
            # Provider 不可用/失败 → 结构化错误 + 真实降级（明确空向量）
            return self._degrade(exc.code, str(exc))
        except Exception as exc:  # noqa: BLE001 - 任何异常都结构化返回
            return self._degrade(ProviderErrorCode.ERR_UNKNOWN.name,
                                 f"unexpected error: {type(exc).__name__}: {exc}")

        return {
            "ok": True,
            "result": {
                "vector": result.vector,
                "dimension": result.dimension,
                "l2_norm": result.l2_norm,
            },
        }

    def embed_batch(self, texts: List[str], *, timeout_ms: int = 30000) -> Dict[str, Any]:
        """批量文本向量化（顺序调用）。"""
        if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
            return self._error(ProviderErrorCode.ERR_INVALID_TEXT.name,
                               "texts must be list[str]")

        results: List[Dict[str, Any]] = []
        for t in texts:
            r = self.embed(t, timeout_ms=timeout_ms)
            if not r.get("ok") or r.get("degraded"):
                # 任一条失败/降级 → 整体失败（结构化错误）。
                # batch 语义：要么全部真实向量，要么整体失败——单条空向量
                # 对批量索引无意义，降级只在单条 embed 场景保留（聊天优先）。
                return self._error(
                    r.get("degraded_reason", {}).get("code", "ERR_EMBED_FAILED"),
                    r.get("degraded_reason", {}).get(
                        "message", "embed_batch degraded/failed"))
            results.append(r["result"])
        return {"ok": True, "result": results}

    # ── 辅助 ──

    @staticmethod
    def _envelope(body: Dict[str, Any], method: str,
                  request_id: Optional[str], trace_id: Optional[str]) -> Dict[str, Any]:
        """把业务响应包进架构 4.4 envelope（回显 request_id/trace_id）。"""
        env = {"protocol_version": PROTOCOL_VERSION, "method": method, **body}
        if request_id is not None:
            env["request_id"] = request_id
        if trace_id is not None:
            env["trace_id"] = trace_id
        return env

    @staticmethod
    def _envelope_error(code: str, message: str, req: Dict[str, Any],
                        method: str) -> Dict[str, Any]:
        """协议层错误响应（含可回显的 request_id/trace_id）。"""
        env = {
            "protocol_version": PROTOCOL_VERSION,
            "method": method,
            "ok": False,
            "error": {"code": code, "message": message},
        }
        if req.get("request_id"):
            env["request_id"] = req["request_id"]
        if req.get("trace_id"):
            env["trace_id"] = req["trace_id"]
        return env

    @staticmethod
    def _error(code: str, message: str) -> Dict[str, Any]:
        """结构化错误响应。"""
        return {"ok": False, "error": {"code": code, "message": message}}

    @staticmethod
    def _degrade(code: Any, message: str) -> Dict[str, Any]:
        """真实降级：明确空向量 + degraded 标记。

        语义：Embedding 不可用时返回空向量（dimension=0），
        上层（检索/记忆）据此跳过向量匹配——不是假数据，是明确降级。
        """
        # code 可能是 ProviderErrorCode 枚举，统一转字符串
        code_str = code.name if isinstance(code, ProviderErrorCode) else str(code)
        return {
            "ok": True,
            "degraded": True,
            "result": {
                "vector": [],
                "dimension": 0,
                "l2_norm": 0.0,
                "degraded": True,
            },
            "degraded_reason": {"code": code_str, "message": message},
        }
