"""
embedding_service.py — 轨道 A Day5 最小垂直链路 Service 层（Day9 增强）

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

Day9 增强（台账 R47）：
5. 查询缓存：EmbeddingQueryCache（LRU，键=模型维度+内容指纹，深拷贝，
   空向量不缓存），架构 TABLE 29 "Embedding（查询）≤180ms：缓存"。
6. 积压指标：EmbeddingBacklogTracker（backlog / oldest_pending_age /
   告警阈值），health 分项返回，供诊断页与评测。
7. 请求合并：EmbeddingCoalescer（相同文本并发请求共享一次 Provider 调用，
   后台批量合并候选）。
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any, Dict, List, Optional

from providers import (
    EmbeddingProvider,
    EmbeddingResult,
    ProviderError,
    ProviderErrorCode,
)
from embedding.embedding_cache import EmbeddingCoalescer, EmbeddingQueryCache
from embedding.cache_invalidator import CacheInvalidator, DeletionEvent, ForgetMode, TargetType
from embedding.embedding_metrics import EmbeddingBacklogTracker
from observability.json_logging import sanitize_message
from embedding.protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    build_error_envelope,
    parse_envelope,
)

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
# ALIGN-004：embedding 子服务方法域（memory.embed/embed_batch/ping/health）与
# FRZ-IPC-007 顶层路由（echo/health/memory.retrieve）分属不同服务边界；
# 子服务方法域经 ADR-008 承认，Phase 2 统一 Gateway（app/api/gateway.py）时合并路由。
_METHODS = {
    "memory.embed",
    "memory.embed_batch",
    "memory.ping",
    "memory.health",
}

# ADR-005 §错误码映射表：内部 ERR_* 码 → FRZ-IPC-002 冻结 5 枚举（对外）。
# 内部业务方法（embed/embed_batch）可保留内部码，对外 envelope 层统一映射；
# 未知码兜底 INTERNAL_ERROR（对外不泄露内部错误细节）。
_ERROR_CODE_MAP = {
    "ERR_PROTOCOL": "PROTOCOL_ERROR",
    "ERR_INVALID_REQUEST": "INVALID_REQUEST",
    "ERR_INVALID_TEXT": "INVALID_REQUEST",
    "ERR_TIMEOUT": "TIMEOUT",
    "ERR_UNKNOWN": "INTERNAL_ERROR",
    "ERR_EMBED_FAILED": "INTERNAL_ERROR",
    "ERR_SERVICE_STOPPED": "INTERNAL_ERROR",
    "ERR_SDK_NOT_LOADED": "INTERNAL_ERROR",
    "ERR_SDK_ERROR": "INTERNAL_ERROR",
    "ERR_SESSION_FAILED": "INTERNAL_ERROR",
    "ERR_MODEL_INVALID": "INTERNAL_ERROR",
    "ERR_CONFIG_CONFLICT": "INTERNAL_ERROR",
    "ERR_SESSION_DESTROYED": "INTERNAL_ERROR",
    "ERR_FATAL_FAILURE": "INTERNAL_ERROR",
}

# FRZ-IPC-002 冻结 5 枚举（对外稳定错误码域）
_FROZEN_ERROR_CODES = {
    "UNSUPPORTED_METHOD",
    "INVALID_REQUEST",
    "PROTOCOL_ERROR",
    "INTERNAL_ERROR",
    "TIMEOUT",
}


def map_error_code(code: str) -> str:
    """内部错误码 → FRZ-IPC-002 冻结枚举（幂等：冻结码原样返回）。

    - 已是冻结 5 枚举（PROTOCOL_ERROR/INVALID_REQUEST/TIMEOUT/INTERNAL_ERROR/UNSUPPORTED_METHOD）
      时原样返回，避免二次映射；
    - 内部码（ERR_*）按 ADR-005 §错误码映射表转换；
    - 未知码兜底 INTERNAL_ERROR（对外不泄露内部错误细节）。
    """
    if code in _FROZEN_ERROR_CODES:
        return code
    return _ERROR_CODE_MAP.get(code, "INTERNAL_ERROR")


class _SdkMissingProvider:
    """[TD-A-005-09 已解决] SDK 缺失降级 provider（EmbeddingProvider 构造失败的兜底）。

    - start/close: no-op（不尝试加载 SDK）
    - embed: 抛 ERR_SDK_NOT_LOADED → EmbeddingService 层转为真实降级（空向量+degraded）
    - get_dimension: 返回 0（无缓存键命中；D9 缓存 getattr 探测兼容）
    - _bridge: None → health() 的 bridge_loaded=false
    """

    def start(self) -> None:
        pass

    def close(self) -> None:
        pass

    def get_dimension(self) -> int:
        return 0

    def embed(self, text: str, *, timeout_ms: int = 5000) -> EmbeddingResult:
        raise ProviderError(ProviderErrorCode.ERR_SDK_NOT_LOADED,
                            "Embedding SDK 缺失（kylin_embedding 模块不可用）")


class EmbeddingService:
    """Embedding 最小垂直链路 Service。

    职责：协议解码 → Provider 调用 → 结构化响应（含降级）。
    不持有 Provider 生命周期（由调用方/进程级单例管理）。
    """

    def __init__(self, provider: Optional[EmbeddingProvider] = None) -> None:
        # Day4 Provider 是进程级单例：不传则内部创建（共享 Bridge/session）
        # [TD-A-005-09 已解决] 构造失败（SDK 缺失/损坏）→ 兜底降级 provider：
        # 无 SDK 时 UDS server 可启动，embed → ok+degraded 空向量，
        # health → bridge_loaded=false（不再构造即抛 RuntimeError 崩溃）
        if provider is not None:
            self._provider = provider
            self._sdk_missing = False
        else:
            try:
                self._provider = EmbeddingProvider()
                self._sdk_missing = False
            except ProviderError as exc:
                # [Review #6 已修复] ERR_CONFIG_CONFLICT（so_path 冲突）是配置错误，
                # 不是 SDK 缺失——必须上抛（调用方明确知道配置冲突），不降级兜底。
                if exc.code == ProviderErrorCode.ERR_CONFIG_CONFLICT:
                    raise
                self._provider = _SdkMissingProvider()
                self._sdk_missing = True
            except Exception:  # noqa: BLE001 - SDK 缺失/初始化异常 → 降级兜底
                self._provider = _SdkMissingProvider()
                self._sdk_missing = True
        self._started = False
        # Day9：查询缓存 / 积压追踪 / 请求合并（可注入以便测试）
        self._cache = EmbeddingQueryCache()
        self._backlog = EmbeddingBacklogTracker()
        self._coalescer = EmbeddingCoalescer()
        # D10：缓存失效协调器（精准遗忘与删除一致性）
        # 通过 set_extraction_provider() 或 set_cache_invalidator() 接线
        self._invalidator: Optional[CacheInvalidator] = None
        # [TABLE 29 降级策略] 短文本阈值：积压告警时超过此长度的文本跳过
        # embed，直接返回结构化降级（避免长文本拖慢整个队列）。
        # 默认 256 字符：覆盖绝大部分短查询场景。
        self._max_short_text_length = 256
        # D11A：错误追踪（health 分项返回）
        self._error_lock = threading.Lock()
        self._last_error: Optional[str] = None
        self._last_error_code: Optional[str] = None
        self._last_error_time: Optional[float] = None
        self._error_count = 0

    # ── 生命周期 ──

    def start(self) -> None:
        """启动 Service：确保 Provider 就绪。幂等。

        [TD-A-005-09 已解决] 真实"so 缺失"场景（kylin_embedding 模块在但
        .so 动态库被移走）：EmbeddingProvider.start() 抛 ERR_SDK_NOT_LOADED
        （BridgeSoNotFoundError）——捕获并切换降级 provider，server 仍可启动
        （embed → ok+degraded 空向量；health → bridge_loaded=false）。
        """
        if self._started:
            return
        try:
            self._provider.start()
        except ProviderError as exc:
            if exc.code == ProviderErrorCode.ERR_SDK_NOT_LOADED:
                # .so 缺失/不可加载：降级兜底（服务可启动，返回结构化降级）
                self._provider = _SdkMissingProvider()
                self._sdk_missing = True
            else:
                raise
        self._started = True

    def close(self) -> None:
        """释放引用。幂等。"""
        self._provider.close()
        self._started = False

    # ── 对外暴露（D9：评测/诊断页使用） ──

    @property
    def cache(self) -> EmbeddingQueryCache:
        return self._cache

    @property
    def backlog(self) -> EmbeddingBacklogTracker:
        return self._backlog

    @property
    def coalescer(self) -> EmbeddingCoalescer:
        return self._coalescer

    @property
    def invalidator(self) -> Optional[CacheInvalidator]:
        return self._invalidator

    def set_cache_invalidator(self, extraction_cache: Any) -> None:
        """设置缓存失效协调器（D10：对接删除事件入口）。

        Args:
            extraction_cache: PreferenceExtractionCache 实例。
        """
        self._invalidator = CacheInvalidator(self._cache, extraction_cache)

    def set_extraction_provider(self, extraction_provider: Any) -> None:
        """从 ExtractionProvider 接入真实抽取缓存（D10 REWORK：真实接线路径）。

        Args:
            extraction_provider: ExtractionProvider 实例，使用其 _cache。
        """
        ext_cache = getattr(extraction_provider, "_cache", None)
        if ext_cache is not None:
            self._invalidator = CacheInvalidator(self._cache, ext_cache)

    def handle_deletion_event(self, event: DeletionEvent) -> Dict[str, Any]:
        """处理删除事件：失效关联缓存（D10：精准遗忘入口）。

        Args:
            event: 删除事件（含待删除内容指纹）。

        Returns:
            失效结果统计。
        """
        if self._invalidator is None:
            return {"ok": False, "error": "cache invalidator not initialized"}
        return self._invalidator.handle_deletion(event)

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
            # 按语义分类映射：UNSUPPORTED_METHOD / INVALID_REQUEST / PROTOCOL_ERROR
            return self._envelope_error(exc.code, str(exc), req)

        if method == "memory.embed":
            body = self.embed(payload.get("text", ""),
                              timeout_ms=payload.get("timeout_ms", 5000))
        elif method == "memory.embed_batch":
            body = self.embed_batch(payload.get("texts", []),
                                    timeout_ms=payload.get("timeout_ms", 30000))
        elif method == "memory.ping":
            body = {"ok": True, "result": {"pong": True}}
        elif method == "memory.health":
            body = self.health()
        else:  # pragma: no cover - parse_envelope 已校验 method
            body = self._error("ERR_INVALID_REQUEST", f"unknown method: {method!r}")

        return self._envelope(body, request_id, trace_id)

    # ── 健康检查（架构 TABLE 15: memory.health） ──

    def health(self) -> Dict[str, Any]:
        """返回服务分项健康状态（不触发 SDK 调用，只读状态）。

        Day9 增强：新增 backlog / oldest_pending_age / 告警状态 + 缓存统计
        （架构 TABLE 36 可观测性 + 台账 D9 backlog 告警阈值）。

        D11A 增强：新增 model_info / provider_lifecycle / error_details
        （台账 D11A 任务②：Embedding 健康状态与错误详情）。

        Returns:
            {"ok": true, "result": {"service": "ok|stopped",
                                     "provider": "ready|stopped",
                                     "provider_lifecycle": str,
                                     "bridge_loaded": bool,
                                     "bridge_has_session": bool,
"backlog": {...},
                                      "cache": {...},
                                      "cache_invalidator": {...},
                                      "model": {"name": str, "dimension": int,
                                                 "loaded": bool, "ondevice": bool},
                                      "errors": {"count": int, "last_code": str,
                                                  "last_message": str, "last_time_seconds_ago": float},
                                      "degraded": bool,
                                      "sdk_missing": bool}}
        """
        bridge = getattr(self._provider, "_bridge", None)
        backlog = self._backlog.snapshot()

        model_info = {}
        try:
            mi = getattr(self._provider, "model_info", None)
            if callable(mi):
                m = mi()
                model_info = {
                    "name": m.name,
                    "dimension": m.dimension,
                    "loaded": m.loaded,
                    "ondevice": m.ondevice,
                }
        except Exception:
            model_info = {"name": "", "dimension": 0, "loaded": False, "ondevice": False}

        lifecycle_name = "N/A"
        try:
            lc = getattr(self._provider, "lifecycle", None)
            if callable(lc):
                lifecycle_name = lc()
        except Exception:
            lifecycle_name = "N/A"

        with self._error_lock:
            err_count = self._error_count
            err_code = self._last_error_code or ""
            err_msg = (self._last_error or "")[:200]
            err_time = self._last_error_time
        last_error_time_ago = -1.0
        if err_time is not None:
            last_error_time_ago = round(time.monotonic() - err_time, 2)

        return {
            "ok": True,
            "result": {
                "service": "ok" if self._started else "stopped",
                "provider": "ready" if self._started else "stopped",
                "provider_lifecycle": lifecycle_name,
                "bridge_loaded": bool(getattr(bridge, "loaded", False))
                if bridge is not None else False,
                "bridge_has_session": bool(getattr(bridge, "has_session", False))
                if bridge is not None else False,
"backlog": {
                    **backlog,
                    "thresholds": self._backlog.thresholds,
                },
                "cache": self._cache.stats,
                "cache_invalidator": self._invalidator.stats
                if self._invalidator is not None else {},
                "model": model_info,
                "errors": {
                    "count": err_count,
                    "last_code": err_code,
                    "last_message": err_msg,
                    "last_time_seconds_ago": last_error_time_ago,
                },
                # [Review #7 已修复] degraded 反映 SDK 缺失状态（不再恒 false）
                "degraded": bool(getattr(self, "_sdk_missing", False)),
                "sdk_missing": bool(getattr(self, "_sdk_missing", False)),
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

        # Day9 查询缓存：键 = 模型维度 + 原文确定性哈希（维度变化自动失效）
        # 维度获取：真实 EmbeddingProvider 有 get_dimension()；D5 既有测试的
        # FakeProvider 无该方法 → 用 getattr 探测，缺省 0（维度 0 的缓存键与
        # 真实维度不同，天然隔离，不影响旧测试路径）。
        # Review 修复：get_dimension() 首次调用可能触发 embed("")（IPC 副作用）
        # 且 Provider 未就绪/已关闭时抛 ProviderError——必须包在 try 内，
        # 不得穿透 D5 "所有方法返回 dict 永不抛异常" 契约。
        try:
            get_dim = getattr(self._provider, "get_dimension", None)
            dimension = get_dim() if callable(get_dim) else 0
        except ProviderError as exc:
            # Provider 未就绪/已关闭：不查缓存，走 Provider 调用（由其降级保护）
            dimension = 0
        except Exception:  # noqa: BLE001 - 维度探测失败不阻断 embed
            dimension = 0
        cache_key = self._cache.make_key(text, dimension)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return {"ok": True, "result": cached, "cache_hit": True}

        # D10 REWORK HIGH-3：捕获代次，Provider 返回后检查，stale 结果不传播
        gen = self._cache.generation

        # Day9 请求合并：相同原文的并发请求共享一次 Provider 调用
        coalesce_key = cache_key[2]
        existing, was_merged = self._coalescer.get_or_create(coalesce_key)
        if was_merged and existing is not None:
            seq = self._backlog.enter()
            try:
                try:
                    result = existing.result(timeout=timeout_ms / 1000.0 + 1.0)
                except FutureTimeout:
                    self._track_error(ProviderErrorCode.ERR_TIMEOUT,
                                      "embed coalesced wait timed out")
                    return self._error(ProviderErrorCode.ERR_TIMEOUT.name,
                                       "embed coalesced wait timed out")
                except ProviderError as exc:
                    self._track_error(exc.code, f"coalesced embed failed: {exc}")
                    return self._degrade(exc.code, f"coalesced embed failed: {exc}")
                except Exception as exc:
                    self._track_error(ProviderErrorCode.ERR_UNKNOWN,
                                      f"coalesced embed failed: {type(exc).__name__}: {exc}")
                    return self._degrade(ProviderErrorCode.ERR_UNKNOWN.name,
                                         f"coalesced embed failed: {type(exc).__name__}: {exc}")
                result_dict = {
                    "vector": result.vector,
                    "dimension": result.dimension,
                    "l2_norm": result.l2_norm,
                }
                write_ok = self._cache.set(cache_key, result_dict, generation=gen)
                if not write_ok:
                    self._track_error(ProviderErrorCode.ERR_UNKNOWN,
                                      "stale coalesced result discarded after deletion")
                    return self._degrade(ProviderErrorCode.ERR_UNKNOWN.name,
                                         "stale coalesced result discarded after deletion")
                return {"ok": True, "result": result_dict, "coalesced": True}
            finally:
                self._backlog.leave(seq)

        # [TABLE 29 降级策略] 短文本保护：积压告警时超过阈值的文本跳过
        # embed，直接返回结构化降级（避免长文本耗时拖慢队列）。
        backlog_snap = self._backlog.snapshot()
        if (backlog_snap.get("backlog_alert") or backlog_snap.get("oldest_alert")):
            if len(text) > self._max_short_text_length:
                reason = (f"text too long ({len(text)} > {self._max_short_text_length}) "
                          f"in degraded mode (backlog={backlog_snap['backlog']}, "
                          f"oldest={backlog_snap['oldest_pending_age_seconds']:.2f}s)")
                self._track_error(ProviderErrorCode.ERR_TIMEOUT, reason)
                return self._degrade(ProviderErrorCode.ERR_TIMEOUT.name, reason)

        # Day9 积压追踪：进入队列（处理完成/失败/超时后 leave）
        seq = self._backlog.enter()
        try:
            return self._embed_uncached(text, timeout_ms, cache_key,
                                        coalesce_key=coalesce_key,
                                        generation=gen)
        finally:
            self._backlog.leave(seq)

    def _embed_uncached(self, text: str, timeout_ms: int,
                        cache_key, *, coalesce_key: str,
                        generation: Optional[int] = None) -> Dict[str, Any]:
        """未命中缓存的 embed：实际 Provider 调用。

        D10 REWORK HIGH-3：捕获 generation，set() 失败时返回降级。
        """
        fut = None
        try:
            fut = _submit_bridge(self._provider.embed, text, timeout_ms=timeout_ms)
            self._coalescer.register(coalesce_key, fut)
            try:
                result = fut.result(timeout=timeout_ms / 1000.0 + 1.0)
            except FutureTimeout:
                fut.cancel()
                self._track_error(ProviderErrorCode.ERR_TIMEOUT,
                                  "embed timed out (Bridge 未返回)")
                return self._error(ProviderErrorCode.ERR_TIMEOUT.name,
                                   "embed timed out (Bridge 未返回)")
        except ProviderError as exc:
            self._track_error(exc.code, str(exc))
            return self._degrade(exc.code, str(exc))
        except Exception as exc:
            msg = f"unexpected error: {type(exc).__name__}: {exc}"
            self._track_error(ProviderErrorCode.ERR_UNKNOWN, msg)
            return self._degrade(ProviderErrorCode.ERR_UNKNOWN.name, msg)
        finally:
            if fut is not None:
                self._coalescer.release(coalesce_key, fut)

        result_dict = {
            "vector": result.vector,
            "dimension": result.dimension,
            "l2_norm": result.l2_norm,
        }
        write_ok = self._cache.set(cache_key, result_dict, generation=generation)
        if not write_ok:
            self._track_error(ProviderErrorCode.ERR_UNKNOWN,
                              "stale embed result discarded after deletion")
            return self._degrade(ProviderErrorCode.ERR_UNKNOWN.name,
                                 "stale embed result discarded after deletion")
        return {"ok": True, "result": result_dict}

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
        return {"ok": True, "result": {"vectors": results}}

    # ── 辅助 ──

    def _track_error(self, code: Any, message: str) -> None:
        """记录错误追踪信息（health 分项返回）。线程安全。"""
        code_str = code.name if isinstance(code, ProviderErrorCode) else str(code)
        safe_msg = sanitize_message(message)
        with self._error_lock:
            self._last_error = safe_msg
            self._last_error_code = code_str
            self._last_error_time = time.monotonic()
            self._error_count += 1

    @staticmethod
    def _envelope(body: Dict[str, Any],
                  request_id: Optional[str], trace_id: Optional[str]) -> Dict[str, Any]:
        """把内部业务响应（ok/result/error/degraded）转换为 FRZ-IPC-006 冻结 envelope。

        成功：{protocol_version, request_id, trace_id, status:"ok", data, server_ts}
        失败：{protocol_version, request_id, trace_id, status:"error", data:{}, error_code, message, server_ts}
        内部 error.code 经 ADR-005 §错误码映射表映射到 FRZ-IPC-002 冻结枚举。
        """
        base = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id or "",
            "trace_id": trace_id or "",
            "server_ts": datetime.now(timezone.utc).isoformat(),
        }
        if body.get("ok"):
            # 成功（含 degraded：ok=true + 空向量，真实降级结果）。
            # data 恒为 object（FRZ-IPC-006 §6.2）；降级时并入 degraded_reason，
            # 避免 degraded_reason 在新 envelope 路径被静默丢失。
            data = dict(body.get("result") or {})
            if body.get("degraded"):
                data.setdefault("degraded", True)
                if body.get("degraded_reason"):
                    data["degraded_reason"] = body["degraded_reason"]
            return {**base, "status": "ok", "data": data}
        error = body.get("error") or {}
        return {
            **base,
            "status": "error",
            "data": {},
            "error_code": map_error_code(error.get("code", "ERR_UNKNOWN")),
            "message": error.get("message", ""),
        }

    @staticmethod
    def _envelope_error(code: str, message: str, req: Dict[str, Any]) -> Dict[str, Any]:
        """协议层错误响应（FRZ-IPC-006 冻结 envelope + FRZ-IPC-002 冻结错误码）。

        与 server.py 共用 build_error_envelope 单一实现，避免两套逻辑漂移。
        """
        if not isinstance(req, dict):
            req = {}
        return build_error_envelope(
            map_error_code(code),
            message,
            request_id=req.get("request_id", ""),
            trace_id=req.get("trace_id", ""),
        )

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
