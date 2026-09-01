"""deletion_consumer.py — D9D forget.executed → deletion consumer

消费 `forget.executed` Outbox 事件，复用 D11A `embedding/outbox_consumer.py`
的 payload 处理（cache invalidation → delete/rebuild 语义）。

行为（D-REQ-05；TD-A-D10-CACHE-INVALIDATION）：
  - 复用 D11A `_handle_deletion_payload`（不改既有行为，只引用复用）
  - `embedding_service.invalidator is None` → 真实失败（RuntimeError，不假装成功）
  - payload 缺 event_id / 非法枚举 → ValueError（Worker 退避/进 DL）
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from db import repositories as repo
from embedding.embedding_service import EmbeddingService
from embedding.outbox_consumer import _handle_deletion_payload

logger = logging.getLogger(__name__)

# Outbox 消费回调类型：payload dict → 成功返回 None，失败抛异常
EventConsumer = Callable[[Dict[str, Any]], None]


def build_forget_consumer(embedding_service: EmbeddingService) -> EventConsumer:
    """构造 forget.executed → deletion 消费者。

    Args:
        embedding_service: EmbeddingService 实例（含已接线的 CacheInvalidator）。

    Returns:
        consumer 回调（payload dict → None/异常）。

    Payload 格式（对齐 D11A deletion payload 与任务卡 §4.1）：
        {
            "event_id": str,
            "user_id": str,
            "target_type": str (TargetType 枚举名),
            "content_hashes": list[str],
            "content_fingerprints": list[str],
            "forget_mode": str (ForgetMode 枚举名),
        }
    """
    if embedding_service.invalidator is None:
        logger.warning(
            "CacheInvalidator 未接线（invalidator is None），"
            "forget.executed 消费者将真实失败（不假装成功）"
        )

    def _consumer(payload: Dict[str, Any]) -> None:
        event_type = payload.get("event_type", "")
        if event_type != repo.EVENT_FORGET_EXECUTED:
            raise ValueError(
                f"forget consumer expected {repo.EVENT_FORGET_EXECUTED!r}, got {event_type!r}"
            )
        _handle_deletion_payload(payload, embedding_service)

    return _consumer
