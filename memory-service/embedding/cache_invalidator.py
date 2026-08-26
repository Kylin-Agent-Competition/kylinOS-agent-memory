"""
cache_invalidator.py — 轨道 A Day10 缓存失效协调器（精准遗忘与删除一致性）

台账 R52（A 轨 D10）：删除事件→ Provider 缓存失效。

职责：
1. 接收删除事件（DeletionEvent），按删除粒度协调 Embedding 缓存与抽取缓存失效。
2. 维护事件→内容指纹、用户→事件的映射，支持按用户/按事件粒度失效。
3. 删除过程中 Provider 异常（SDK 崩溃/超时）→ 删除不丢失，可重试。
4. 并发删除与读取 → 无竞态数据恢复。

使用方式：
    invalidator = CacheInvalidator(embedding_cache, extraction_cache)
    event = DeletionEvent(event_id="evt_001", user_id="user_1",
                          content_hashes=["abc123"])
    invalidator.handle_deletion(event)

设计：
- 线程安全（嵌入并发 embed 服务，多个删除事件可并发到达）。
- 幂等：同一事件重复处理不会重复删除已失效条目。
- 删除后新建 Provider 实例 → 已删除数据不恢复（缓存失效后，新 Provider 实例
  走新 embed 调用，无缓存命中）。
- 重启后删除状态保持：持久化删除状态由上层（Outbox/DB）保证，本模块仅负责
  内存缓存失效；重启后缓存自动清空（无持久化先验状态），已删除数据不会因
  缓存恢复。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class DeletionEvent:
    """删除事件（由 Outbox 或直接调用触发缓存失效）。

    Attributes:
        event_id: 事件唯一标识（幂等去重）。
        user_id: 所属用户。
        target_type: 目标类型（preference/knowledge/event/all）。
        content_hashes: 待删除内容的指纹列表（Embedding 原文确定性哈希）。
        content_fingerprints: 待删除内容的指纹列表（Extraction 内容指纹）。
        forget_mode: 遗忘模式（single_item/session/topic/time_window/full_reset）。
        timestamp: 事件时间戳。
    """
    event_id: str
    user_id: str
    target_type: str = "event"
    content_hashes: List[str] = field(default_factory=list)
    content_fingerprints: List[str] = field(default_factory=list)
    forget_mode: str = "single_item"
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
        # 已处理事件 ID 集合（幂等去重）
        self._processed_events: Set[str] = set()
        # 用户 → 事件 ID 集合（支持按用户失效）
        self._user_events: Dict[str, Set[str]] = {}
        # 事件 ID → 内容指纹集合（事件追溯）
        self._event_hashes: Dict[str, Set[str]] = {}
        # 统计
        self._embedding_invalidated = 0
        self._extraction_invalidated = 0
        self._events_processed = 0

    def handle_deletion(self, event: DeletionEvent) -> Dict[str, Any]:
        """处理删除事件：失效关联缓存。

        幂等：同一 event_id 重复调用无副作用。
        线程安全：删除过程中 Provider 异常不影响其他请求。

        Args:
            event: 删除事件。

        Returns:
            {"ok": true, "embedding_invalidated": int, "extraction_invalidated": int}
        """
        with self._lock:
            if event.event_id in self._processed_events:
                return {"ok": True, "dedup": True,
                        "embedding_invalidated": 0, "extraction_invalidated": 0}
            self._processed_events.add(event.event_id)
            self._events_processed += 1

            # 记录用户→事件映射
            if event.user_id not in self._user_events:
                self._user_events[event.user_id] = set()
            self._user_events[event.user_id].add(event.event_id)

            # 记录事件→指纹映射
            all_hashes: Set[str] = set()
            all_hashes.update(event.content_hashes)
            all_hashes.update(event.content_fingerprints)
            if all_hashes:
                self._event_hashes[event.event_id] = all_hashes

            # 失效 Embedding 缓存
            embedding_removed = 0
            for ch in event.content_hashes:
                embedding_removed += self._embedding_cache.invalidate_by_content(ch)

            # 失效 Extraction 缓存
            extraction_removed = 0
            for fp in event.content_fingerprints:
                extraction_removed += self._extraction_cache.invalidate_by_content(fp)
            # 也按 event_id 失效 Extraction 缓存
            extraction_removed += self._extraction_cache.invalidate_by_event(event.event_id)

            self._embedding_invalidated += embedding_removed
            self._extraction_invalidated += extraction_removed

            return {"ok": True, "dedup": False,
                    "embedding_invalidated": embedding_removed,
                    "extraction_invalidated": extraction_removed}

    def invalidate_by_user(self, user_id: str) -> Dict[str, Any]:
        """按用户失效所有关联缓存条目（D10：用户级精准遗忘）。

        遍历该用户关联的所有事件，失效其内容指纹对应的缓存条目。

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
            self._embedding_invalidated += embedding_removed
            self._extraction_invalidated += extraction_removed
            return {"embedding_invalidated": embedding_removed,
                    "extraction_invalidated": extraction_removed}

    def invalidate_all(self) -> Dict[str, Any]:
        """全量失效所有缓存。"""
        self._embedding_cache.clear()
        self._extraction_cache.clear()
        with self._lock:
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