"""
embedding_metrics.py — 轨道 A Day9 Embedding 积压指标与告警阈值

台账 R47（A 轨 D9）：backlog 与 oldest_pending_age 告警阈值 →
Embedding 吞吐基线 + 积压治理策略。

架构 TABLE 36（可观测性）一致性指标：index_sync_lag / outbox_backlog；
本模块为 Embedding 侧请求积压指标（服务级，供 health/诊断页/评测）：

- backlog：当前待处理的 Embedding 请求队列深度（0 = 无积压）
  - 语义：EmbeddingService 内排队等待 Provider 的请求数
- oldest_pending_age：队列中最老请求的等待时长（秒）
  - 语义：从请求进入队列到被处理的时间；超阈值说明吞吐跟不上
- 告警阈值（台账 D9 交付物）：
  - backlog_warn：backlog 超过该值 → 积压告警（建议限流/降级为结构化召回）
  - oldest_warn：oldest_pending_age 超过该值（秒）→ 吞吐告警（建议扩容/缓存）

阈值语义（架构 TABLE 29 延迟预算：Embedding 查询 ≤180ms）：
- 若请求排队超过 180ms 则必然拖慢查询 → oldest_warn 默认 0.2s
- backlog_warn 默认 32（并发连接数上限的合理倍数）

线程安全：嵌入并发 embed 服务，用锁保护计数器。
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional


class EmbeddingBacklogTracker:
    """Embedding 请求积压追踪（backlog / oldest_pending_age / 告警）。"""

    def __init__(self, *, backlog_warn: int = 32,
                 oldest_warn_seconds: float = 0.2) -> None:
        assert backlog_warn > 0
        assert oldest_warn_seconds > 0
        self._backlog_warn = backlog_warn
        self._oldest_warn = oldest_warn_seconds
        self._lock = threading.Lock()
        self._pending: Dict[int, float] = {}  # 请求序号 -> 入队时间（monotonic）
        self._seq = 0
        # 告警计数（供可观测性）
        self._backlog_alerts = 0
        self._oldest_alerts = 0

    # ── 入队/出队 ──

    def enter(self) -> int:
        """请求进入队列：返回请求序号（调用方在处理完成时传给 leave）。"""
        with self._lock:
            self._seq += 1
            self._pending[self._seq] = time.monotonic()
            return self._seq

    def leave(self, seq: int) -> None:
        """请求处理完成（或失败/超时）：移出队列。"""
        with self._lock:
            self._pending.pop(seq, None)

    # ── 指标 ──

    def snapshot(self) -> Dict[str, object]:
        """当前积压快照：backlog / oldest_pending_age / 告警状态。

        Returns:
            {"backlog": int, "oldest_pending_age_seconds": float,
             "backlog_alert": bool, "oldest_alert": bool}
        """
        with self._lock:
            now = time.monotonic()
            pending = list(self._pending.values())
            backlog = len(pending)
            oldest = (now - min(pending)) if pending else 0.0
            backlog_alert = backlog > self._backlog_warn
            oldest_alert = oldest > self._oldest_warn
            if backlog_alert:
                self._backlog_alerts += 1
            if oldest_alert:
                self._oldest_alerts += 1
            return {
                "backlog": backlog,
                "oldest_pending_age_seconds": round(oldest, 4),
                "backlog_alert": backlog_alert,
                "oldest_alert": oldest_alert,
            }

    @property
    def thresholds(self) -> Dict[str, object]:
        """告警阈值（台账 D9 交付物，供配置/诊断页展示）。"""
        return {
            "backlog_warn": self._backlog_warn,
            "oldest_warn_seconds": self._oldest_warn,
        }

    @property
    def alert_counts(self) -> Dict[str, int]:
        with self._lock:
            return {
                "backlog_alerts": self._backlog_alerts,
                "oldest_alerts": self._oldest_alerts,
            }

    def reset(self) -> None:
        with self._lock:
            self._pending.clear()
            self._seq = 0
            self._backlog_alerts = 0
            self._oldest_alerts = 0
