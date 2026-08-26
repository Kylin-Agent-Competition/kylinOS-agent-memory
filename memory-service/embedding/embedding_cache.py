from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Set, Tuple

EmbeddingCacheKey = Tuple[str, int, str]

_MISS = object()


def raw_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingQueryCache:
    """LRU Embedding 查询缓存。

    线程安全。D10 REWORK：generation 代次机制：
    - 每次失效/清空递增 `_generation`
    - set() 接受 generation 参数，不匹配时拒绝写入
    - 解决 stale write-back / FULL_RESET 旧请求恢复 / 永久 tombstone 三大问题
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
        self._generation = 0

    @staticmethod
    def make_key(text: str, dimension: int) -> EmbeddingCacheKey:
        return ("embed", dimension, raw_text_hash(text))

    @property
    def generation(self) -> int:
        return self._generation

    def get(self, key: EmbeddingCacheKey) -> Optional[Dict[str, Any]]:
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

    def set(self, key: EmbeddingCacheKey, result: Dict[str, Any],
            generation: Optional[int] = None) -> bool:
        """写入缓存。返回 True=成功，False=被 generation/tombstone 拒绝。

        Args:
            generation: 捕获时的代次。若提供且与当前代次不匹配，拒绝写入。
        """
        vector = result.get("vector") or []
        if not vector:
            return False
        with self._lock:
            if generation is not None and self._generation != generation:
                return False
            self._data[key] = (time.monotonic(),
                               {k: (list(v) if isinstance(v, list) else v)
                                for k, v in result.items()})
            self._data.move_to_end(key)
            while len(self._data) > self._capacity:
                self._data.popitem(last=False)
                self._evictions += 1
            return True

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._generation += 1
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    def invalidate_by_content(self, content_hash: str) -> int:
        removed = 0
        with self._lock:
            self._generation += 1
            keys_to_delete = [k for k in self._data if k[2] == content_hash]
            for k in keys_to_delete:
                del self._data[k]
                removed += 1
            return removed

    @property
    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {"size": len(self._data),
                    "hits": self._hits,
                    "misses": self._misses,
                    "evictions": self._evictions}


class EmbeddingCoalescer:
    def __init__(self) -> None:
        self._inflight: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._merged = 0

    def get_or_create(self, key: str) -> Tuple[Optional[Any], bool]:
        with self._lock:
            fut = self._inflight.get(key)
            if fut is not None and not fut.done():
                self._merged += 1
                return fut, True
            return None, False

    def register(self, key: str, future: Any) -> None:
        with self._lock:
            self._inflight[key] = future

    def release(self, key: str, future: Any) -> None:
        with self._lock:
            if self._inflight.get(key) is future:
                del self._inflight[key]

    @property
    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {"inflight": len(self._inflight), "merged": self._merged}