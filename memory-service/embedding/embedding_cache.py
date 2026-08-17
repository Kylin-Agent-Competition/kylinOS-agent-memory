"""
embedding_cache.py — 轨道 A Day9 Embedding 查询缓存

台账 R47（A 轨 D9）：查询缓存 + 后台批量合并候选 + backlog 与
oldest_pending_age 告警阈值。

设计（复用 Day7 PreferenceExtractionCache 模式，架构 TABLE 29 延迟预算
"Embedding（查询）≤180ms：缓存、短文本、服务不可用时仅结构化召回"）：

1. LRU 查询缓存：键 = 模型维度 + 原文确定性哈希（sha256 原文 UTF-8）。
   - 原文哈希（不经 casefold/空白折叠）：不同文本绝不共享键——
     "Hello" 与 "hello"、"a b" 与 "ab" 是不同向量，必须不同键
     （Review 修复：content_fingerprint 的归一化指纹会串键交叉污染）。
   - 模型维度：不同模型/维度变化时缓存自动失效（版本变更安全）。
   - 深拷贝返回：调用方修改 vector 不影响缓存（防污染，同 D7）。
   - TTL/容量可配；空结果（降级空向量）不缓存（避免缓存降级态）。
2. 命中/未命中统计：hits/misses/size/evictions，供可观测性（TABLE 36）与评测。
3. 后台批量合并候选：服务端合并"相同原文文本的并发请求"（request coalescing）——
   同一原文的并发 embed 共享一次 Provider 调用，降低重复 SDK 调用。

确定性：同一输入 → 同一缓存键；同一 Provider 输出 → 同一缓存结果。
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

# 缓存键结构：kind + 模型维度 + 原文确定性哈希
# 维度参与键：SDK/模型版本变化导致维度变化时，缓存自动失效（Day9 防串键）
EmbeddingCacheKey = Tuple[str, int, str]

_MISS = object()  # 未命中哨兵（None 表示未命中；缓存值恒为 EmbeddingResult 字典）


def raw_text_hash(text: str) -> str:
    """原文确定性哈希（sha256 原文 UTF-8，**不做任何归一化**）。

    Embedding 缓存/合并键必须区分所有不同文本（"Hello" vs "hello" 是不同
    向量）；content_fingerprint 的归一化指纹用于事件判重（语义等价可合并），
    不适用于向量缓存键——Review 修复（交叉污染风险）。
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingQueryCache:
    """LRU Embedding 查询缓存（键 = 维度 + 内容指纹）。

    - 深拷贝：调用方修改 vector 不影响缓存。
    - 空向量（降级结果）不缓存：降级态不应被缓存放大（真实降级每次都要发生）。
    - TTL 可选；容量满时淘汰最久未用（LRU）。
    - 线程安全（embed 服务多连接并发）。
    """

    def __init__(self, capacity: int = 512,
                 ttl_seconds: Optional[float] = None) -> None:
        assert capacity > 0, "cache capacity must be > 0"
        self._capacity = capacity
        self._ttl = ttl_seconds
        self._data: "OrderedDict[EmbeddingCacheKey, Tuple[float, Dict[str, Any]]]" = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._lock = threading.Lock()

    @staticmethod
    def make_key(text: str, dimension: int) -> EmbeddingCacheKey:
        """缓存键：模型维度 + 原文确定性哈希（维度变化自动失效，D9 版本变更安全）。"""
        return ("embed", dimension, raw_text_hash(text))

    def get(self, key: EmbeddingCacheKey) -> Optional[Dict[str, Any]]:
        """按缓存键取结果；None = 未命中（不含"缓存了空结果"——空结果不缓存）。

        返回深拷贝（调用方修改 vector 不影响缓存）。
        """
        with self._lock:
            entry = self._data.get(key, _MISS)
            if entry is _MISS:
                self._misses += 1
                return None
            ts, result = entry
            if self._ttl is not None and (time.monotonic() - ts) > self._ttl:
                del self._data[key]
                self._misses += 1
                return None
            self._hits += 1
            self._data.move_to_end(key)
            return {k: (list(v) if isinstance(v, list) else v)
                    for k, v in result.items()}

    def set(self, key: EmbeddingCacheKey, result: Dict[str, Any]) -> None:
        """写入缓存（深拷贝存储）。

        空向量（degraded）结果不缓存：真实降级每次都要发生，避免缓存放大降级态。
        """
        vector = result.get("vector") or []
        if not vector:
            return
        with self._lock:
            self._data[key] = (time.monotonic(),
                               {k: (list(v) if isinstance(v, list) else v)
                                for k, v in result.items()})
            self._data.move_to_end(key)
            while len(self._data) > self._capacity:
                self._data.popitem(last=False)
                self._evictions += 1

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    @property
    def stats(self) -> Dict[str, int]:
        """缓存统计（size/hits/misses/evictions）。"""
        with self._lock:
            return {"size": len(self._data),
                    "hits": self._hits,
                    "misses": self._misses,
                    "evictions": self._evictions}


# ── 请求合并（request coalescing，D9 后台批量合并候选） ──

class EmbeddingCoalescer:
    """相同文本并发请求合并（后台批量合并候选）。

    语义：同一内容指纹的 embed 请求并发到达时，只发一次 Provider 调用，
    其余请求等待同一 Future 的结果（共享一次 SDK 调用）。

    - 单例 per-service；线程安全。
    - 合并窗口：请求在 Provider 调用返回前到达才合并；返回后新请求走缓存。
    - 失败传播：Provider 失败时所有等待者收到同一错误（不重复调用）。
    """

    def __init__(self) -> None:
        self._inflight: Dict[str, Any] = {}  # 原文哈希 -> Future
        self._lock = threading.Lock()
        self._merged = 0  # 被合并的请求数（统计）

    def get_or_create(self, key: str) -> Tuple[Optional[Any], bool]:
        """返回 (existing_future, True) 若已有同键在途请求；否则 (None, False)。

        Args:
            key: 合并键（原文确定性哈希，与缓存键同源；不同文本绝不合并）。

        Returns:
            (future_or_None, was_merged)
            - was_merged=True：调用方应等待 future（不发起 Provider 调用）
            - was_merged=False：调用方应发起 Provider 调用并把 future 注册
        """
        with self._lock:
            fut = self._inflight.get(key)
            if fut is not None and not fut.done():
                self._merged += 1
                return fut, True
            return None, False

    def register(self, key: str, future: Any) -> None:
        """注册新发起的 Provider 调用 future（供后续并发请求合并）。"""
        with self._lock:
            self._inflight[key] = future

    def release(self, key: str, future: Any) -> None:
        """Provider 调用结束：若仍指向该 future 则移除（防悬挂）。"""
        with self._lock:
            if self._inflight.get(key) is future:
                del self._inflight[key]

    @property
    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {"inflight": len(self._inflight), "merged": self._merged}
