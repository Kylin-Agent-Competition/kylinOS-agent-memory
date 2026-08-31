"""outbox_consumer.py — D11A Outbox → CacheInvalidator 消费桥接

关闭 TD-A-D10-CACHE-INVALIDATION：将 Outbox 删除事件接入 CacheInvalidator。

使用方式：
    from embedding.outbox_consumer import build_deletion_consumer
    consumer = build_deletion_consumer(embedding_service)
    worker = OutboxWorker(engine, consumer=consumer)

consumer 回调签名：payload dict → None（成功）或抛异常（重试/Dead Letter）。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from embedding.cache_invalidator import CacheInvalidator, DeletionEvent, ForgetMode, TargetType
from embedding.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

# Outbox 事件类型常量
EVENT_DELETION = "memory.deletion"

# Outbox 消费回调类型：payload dict → 成功返回 None，失败抛异常
EventConsumer = Callable[[Dict[str, Any]], None]


def build_deletion_consumer(
    embedding_service: EmbeddingService,
) -> EventConsumer:
    """构造 Outbox 删除事件消费者。

    Args:
        embedding_service: EmbeddingService 实例（含已接线的 CacheInvalidator）。

    Returns:
        consumer 回调（payload dict → None/异常）。

    Payload 格式：
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
            "删除事件 consumer 将始终失败"
        )
    else:
        logger.info(
            "Outbox 删除事件 consumer 已注册（invalidator 已就绪）"
        )

    def _consumer(payload: Dict[str, Any]) -> None:
        event_type = payload.get("event_type", "")
        if event_type == EVENT_DELETION or event_type == "deletion":
            _handle_deletion_payload(payload, embedding_service)
        else:
            raise ValueError(f"unknown outbox event_type: {event_type!r}")

    return _consumer


def _handle_deletion_payload(
    payload: Dict[str, Any],
    embedding_service: EmbeddingService,
) -> None:
    """处理删除事件 payload。"""
    if embedding_service.invalidator is None:
        raise RuntimeError(
            "CacheInvalidator not initialized — call set_extraction_provider() first"
        )

    event_id = payload.get("event_id", "")
    if not event_id:
        raise ValueError("deletion payload missing event_id")

    user_id = payload.get("user_id", "")
    content_hashes = payload.get("content_hashes") or []
    content_fingerprints = payload.get("content_fingerprints") or []

    target_type_str = payload.get("target_type", "event")
    try:
        target_type = TargetType(target_type_str)
    except ValueError:
        target_type = TargetType.EVENT

    forget_mode_str = payload.get("forget_mode", "single_item")
    try:
        forget_mode = ForgetMode(forget_mode_str)
    except ValueError:
        forget_mode = ForgetMode.SINGLE_ITEM

    event = DeletionEvent(
        event_id=event_id,
        user_id=user_id,
        target_type=target_type,
        content_hashes=content_hashes,
        content_fingerprints=content_fingerprints,
        forget_mode=forget_mode,
    )

    result = embedding_service.handle_deletion_event(event)
    if not result.get("ok"):
        logger.error(
            "删除事件处理失败: event_id=%s result=%s", event_id, result
        )
        raise RuntimeError(f"deletion event failed: {result.get('error', 'unknown')}")

    logger.info(
        "删除事件处理完成: event_id=%s embedding_invalidated=%d "
        "extraction_invalidated=%d dedup=%s",
        event_id,
        result.get("embedding_invalidated", 0),
        result.get("extraction_invalidated", 0),
        result.get("dedup", False),
    )