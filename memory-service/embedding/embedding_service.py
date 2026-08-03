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

# Bridge 调用统一放线程池：SDK embed 可能耗时（IPC），不阻塞聊天线程（Day5-3）
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embed-bridge")


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

    # ── 对外接口（UDS 协议处理入口） ──

    def handle_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """协议分发入口：根据 request_type 分派。

        Args:
            req: 长度前缀 JSON 解码后的请求 dict。
                 {"type": "embed", "text": "..."}
                 {"type": "embed_batch", "texts": [...]}

        Returns:
            结构化响应 dict（JSON 可序列化）。
        """
        req_type = req.get("type")
        if req_type == "embed":
            return self.embed(req.get("text", ""), timeout_ms=req.get("timeout_ms", 5000))
        if req_type == "embed_batch":
            return self.embed_batch(req.get("texts", []), timeout_ms=req.get("timeout_ms", 30000))
        if req_type == "ping":
            return {"ok": True, "result": "pong"}
        return self._error("ERR_INVALID_REQUEST",
                           f"unknown request type: {req_type!r}")

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
            fut = _executor.submit(self._provider.embed, text, timeout_ms=timeout_ms)
            try:
                result = fut.result(timeout=timeout_ms / 1000.0 + 1.0)
            except FutureTimeout:
                # 超时：返回结构化错误；尽力取消任务（线程池中的任务可能无法中断，
                # 但调用方线程立即获得控制权，不阻塞聊天线程）
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
            if not r.get("ok"):
                return r  # 任一条失败 → 整体失败（结构化错误）
            results.append(r["result"])
        return {"ok": True, "result": results}

    # ── 辅助 ──

    @staticmethod
    def _error(code: str, message: str) -> Dict[str, Any]:
        """结构化错误响应。"""
        return {"ok": False, "error": {"code": code, "message": message}}

    @staticmethod
    def _degrade(code, message: str) -> Dict[str, Any]:
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
