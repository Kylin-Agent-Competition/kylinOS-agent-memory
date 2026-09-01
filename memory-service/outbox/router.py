"""router.py — D9D Outbox 统一消费路由

按 `event_type` 注册/分发 Outbox 消费者，替代单一 consumer 回调：

    memory.upserted → index consumer（Vector/Index upsert）
    forget.executed  → deletion consumer（cache invalidation → delete/rebuild）
    unknown          → 抛 UnknownEventTypeError（Worker 按失败/重试/DL 处理，可观测）

路由表使用冻结常量（repositories.EVENT_MEMORY_UPSERTED / EVENT_FORGET_EXECUTED）
与 D11A EVENT_DELETION 对齐，不新增 event_type 枚举值（红线：契约不变）。

Router 本身是可调用对象（route(payload)），可直接作为 OutboxWorker.consumer 注入。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Outbox 消费回调类型：payload dict → 成功返回 None，失败抛异常
EventConsumer = Callable[[Dict[str, Any]], None]


class UnknownEventTypeError(Exception):
    """路由未注册的 event_type（Worker 按失败/重试/DL 处理）。

    语义：未知事件类型不静默吞掉，日志 ERROR 可观测（D-REQ-05 路由图）。
    """


class OutboxRouter:
    """按 event_type 注册/分发的统一消费路由。"""

    def __init__(self) -> None:
        self._routes: Dict[str, EventConsumer] = {}

    def register(self, event_type: str, consumer: EventConsumer) -> None:
        """注册 event_type → consumer。

        Args:
            event_type: Outbox 事件类型（冻结常量，如 memory.upserted）。
            consumer: 回调（payload dict → None/异常）。

        Raises:
            ValueError: event_type 为空或重复注册（覆盖注册会掩盖既有消费语义，
                故重复注册直接失败以暴露接线错误）。
        """
        if not event_type:
            raise ValueError("event_type 不能为空")
        if event_type in self._routes:
            raise ValueError(f"event_type 重复注册: {event_type!r}")
        self._routes[event_type] = consumer

    def has_route(self, event_type: str) -> bool:
        return event_type in self._routes

    def registered_types(self) -> frozenset[str]:
        return frozenset(self._routes)

    def route(self, payload: Dict[str, Any]) -> None:
        """按 payload 的 event_type 分发到对应消费者。

        Args:
            payload: Outbox 事件 payload（必须含 event_type 字段）。

        Raises:
            UnknownEventTypeError: event_type 缺失或未注册。
        """
        event_type = payload.get("event_type", "")
        consumer = self._routes.get(event_type)
        if consumer is None:
            raise UnknownEventTypeError(f"unknown outbox event_type: {event_type!r}")
        logger.info("Outbox 路由分发 type=%s", event_type)
        consumer(payload)


def build_outbox_router(
    *,
    vector_provider: Optional[Any] = None,
    embedding_service: Optional[Any] = None,
) -> OutboxRouter:
    """构造生产 Outbox 路由（app.py 注入点）。

    依赖未接线（None）时对应消费者不注册——该事件类型走 UnknownEventTypeError
    → Worker 失败/重试/DL（真实结果，不假装成功；producer 由 D8D 接线后补齐）。

    Args:
        vector_provider: VectorProvider 实现（memory.upserted → index consumer）。
        embedding_service: EmbeddingService 实例（forget.executed → deletion consumer）。
    """
    from db import repositories as repo
    from outbox.deletion_consumer import build_forget_consumer
    from outbox.index_consumer import build_index_consumer

    router = OutboxRouter()
    if vector_provider is not None:
        router.register(repo.EVENT_MEMORY_UPSERTED, build_index_consumer(vector_provider))
    if embedding_service is not None:
        router.register(repo.EVENT_FORGET_EXECUTED, build_forget_consumer(embedding_service))
    return router
