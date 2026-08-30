"""
cache_invalidator.py — 轨道 A Day10 缓存失效协调器（精准遗忘与删除一致性）

台账 R52（A 轨 D10）：删除事件→ Provider 缓存失效。

职责：
1. 接收删除事件（DeletionEvent），按删除粒度协调 Embedding 缓存与抽取缓存失效。
2. 维护事件→内容指纹、用户→事件的映射，支持按用户/按事件粒度失效。
3. 删除过程中 Provider 异常（SDK 崩溃/超时）→ 删除不丢失，可重试。

使用方式：
    invalidator = CacheInvalidator(embedding_cache, extraction_cache)
    event = DeletionEvent(event_id="evt_001", user_id="user_1",
                          content_hashes=["abc123"])
    invalidator.handle_deletion(event)

设计：
- 线程安全（嵌入并发 embed 服务，多个删除事件可并发到达）。
- 幂等：同一事件重复处理不会重复删除已失效条目。
- 删除后新建 Provider 实例 → 已删除数据不恢复（tombstone 阻止 stale write-back）。
- 重启后删除状态保持：持久化删除状态由上层（Outbox/DB）保证，本模块仅负责
  内存缓存失效；重启后缓存自动清空（无持久化先验状态），已删除数据不会因
  缓存恢复。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from domain.enums import ForgetMode, TargetType


@dataclass
class DeletionEvent:
    """删除事件（由 Outbox 或直接调用触发缓存失效）。

    Attributes:
        event_id: 事件唯一标识（幂等去重）。
        user_id: 所属用户。
        target_type: 目标类型（复用 TargetType 枚举）。
        content_hashes: 待删除内容的指纹列表（Embedding 原文确定性哈希）。
        content_fingerprints: 待删除内容的指纹列表（Extraction 内容指纹）。
        forget_mode: 遗忘模式（复用 ForgetMode 枚举）。
        timestamp: 事件时间戳。
    """
    event_id: str
    user_id: str
    target_type: TargetType = TargetType.EVENT
    content_hashes: List[str] = field(default_factory=list)
    content_fingerprints: List[str] = field(default_factory=list)
    forget_mode: ForgetMode = ForgetMode.SINGLE_ITEM
    timestamp: float = field(default_factory=time.time)


class CacheInvalidator:
    """缓存失效协调器——按删除事件粒度失效 Embedding 与抽取缓存。

    线程安全：所有公共方法以锁保护。
    """

    def __init__(self,
                 embedding_cache: Any,
                 extraction_cache: Any) -> None:
        self._embedding_cache = embedding_cache
        self._extraction_cache = extraction_cache
        self._lock = threading.Lock()

        self._processed_events: Set[str] = set()
        self._user_events: Dict[str, Set[str]] = {}
        self._event_hashes: Dict[str, Set[str]] = {}

        self._embedding_invalidated = 0
        self._extraction_invalidated = 0
        self._events_processed = 0

    def handle_deletion(self, event: DeletionEvent) -> Dict[str, Any]:
        """处理删除事件：失效关联缓存。

        D10 REWORK：先执行全部失效操作，全部成功后再登记 processed。
        失败时不得留下错误的 completed/dedup 状态，相同 event_id 必须允许重试。

        Args:
            event: 删除事件。

        Returns:
            {"ok": true/false, "embedding_invalidated": int, "extraction_invalidated": int}
        """
        with self._lock:
            if event.event_id in self._processed_events:
                return {"ok": True, "dedup": True,
                        "embedding_invalidated": 0, "extraction_invalidated": 0}

        # 先执行失效操作（在锁外执行，避免持有锁期间调用外部 cache）
        try:
            # D10 REWORK MEDIUM：ForgetMode.FULL_RESET → invalidate_all
            if event.forget_mode == ForgetMode.FULL_RESET:
                self._embedding_cache.clear()
                self._extraction_cache.clear()
                embedding_removed = 0
                extraction_removed = 0
            else:
                embedding_removed = 0
                for ch in event.content_hashes:
                    embedding_removed += self._embedding_cache.invalidate_by_content(ch)

                extraction_removed = 0
                for fp in event.content_fingerprints:
                    extraction_removed += self._extraction_cache.invalidate_by_content(fp)
                extraction_removed += self._extraction_cache.invalidate_by_event(event.event_id)
        except Exception:
            # 失效失败：不标记 processed，允许重试
            return {"ok": False, "error": "invalidation failed",
                    "embedding_invalidated": 0, "extraction_invalidated": 0}

        # 全部成功后再登记 processed
        with self._lock:
            self._processed_events.add(event.event_id)
            self._events_processed += 1

            if event.user_id not in self._user_events:
                self._user_events[event.user_id] = set()
            self._user_events[event.user_id].add(event.event_id)

            all_hashes: Set[str] = set()
            all_hashes.update(event.content_hashes)
            all_hashes.update(event.content_fingerprints)
            if all_hashes:
                self._event_hashes[event.event_id] = all_hashes

            self._embedding_invalidated += embedding_removed
            self._extraction_invalidated += extraction_removed

            return {"ok": True, "dedup": False,
                    "embedding_invalidated": embedding_removed,
                    "extraction_invalidated": extraction_removed}

    def invalidate_by_user(self, user_id: str) -> Dict[str, Any]:
        """按用户失效已登记事件的关联缓存条目。

        注意：仅失效该用户已通过 handle_deletion() 登记过的内容哈希。
        不覆盖未登记过的缓存条目（Embedding cache key 不含 user_id，
        无法枚举该用户当前全部 cache entries）。

        Args:
            user_id: 用户 ID。

        Returns:
            {"embedding_invalidated": int, "extraction_invalidated": int}
        """
        with self._lock:
            event_ids = self._user_events.get(user_id, set())
            all_hashes: Set[str] = set()
            for eid in event_ids:
                all_hashes.update(self._event_hashes.get(eid, set()))
        embedding_removed = 0
        extraction_removed = 0
        for ch in all_hashes:
            embedding_removed += self._embedding_cache.invalidate_by_content(ch)
            extraction_removed += self._extraction_cache.invalidate_by_content(ch)
        for eid in event_ids:
            extraction_removed += self._extraction_cache.invalidate_by_event(eid)
        with self._lock:
            self._embedding_invalidated += embedding_removed
            self._extraction_invalidated += extraction_removed
        return {"embedding_invalidated": embedding_removed,
                "extraction_invalidated": extraction_removed}

    def invalidate_all(self) -> Dict[str, Any]:
        """全量失效所有缓存，清除全部内部状态。"""
        self._embedding_cache.clear()
        self._extraction_cache.clear()
        with self._lock:
            self._processed_events.clear()
            self._user_events.clear()
            self._event_hashes.clear()
            self._embedding_invalidated = 0
            self._extraction_invalidated = 0
            self._events_processed = 0
        return {"ok": True}

    @property
    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "embedding_invalidated": self._embedding_invalidated,
                "extraction_invalidated": self._extraction_invalidated,
                "events_processed": self._events_processed,
                "processed_events": len(self._processed_events),
                "tracked_users": len(self._user_events),
            }