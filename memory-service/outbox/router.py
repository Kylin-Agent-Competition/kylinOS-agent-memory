"""router.py — D9D Outbox 统一消费路由

按 `event_type` 注册/分发 Outbox 消费者，替代单一 consumer 回调：

    memory.upserted → index consumer（Vector/Index upsert）
    forget.executed  → deletion consumer（cache invalidation → delete/rebuild）
    unknown          → 抛 UnknownEventTypeError（Worker 按失败/重试/DL 处理，可观测）

路由表使用冻结常量（repositories.EVENT_MEMORY_UPSERTED / EVENT_FORGET_EXECUTED）
与 D11A EVENT_DELETION 对齐，不新增 event_type 枚举值（红线：契约不变）。

HIGH-01（路由真源）：路由真源是 Outbox 独立列 `outbox.event_type`，而非 payload 内嵌
`event_type`（`repo.enqueue_outbox()` 写入独立列，payload 不自动携带）。因此
`route(event_type, payload)` 显式接收 DB 列事件类型；若 payload 同时含 `event_type`，
则与 DB 列做一致性校验，不一致抛 ValueError fail-closed（防路由错乱）。

Router 本身可调用（route(event_type, payload)），可直接作为 OutboxWorker.consumer 注入。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Outbox 消费回调类型：(event_type, payload) → 成功返回 None，失败抛异常
EventConsumer = Callable[[str, Dict[str, Any]], None]

# 摘要签名密钥默认（注入参数默认值，仅用于 L1 测试；真实接线由调用方注入受控 key）
_DEFAULT_KEY_ID = "d9d-internal"
_DEFAULT_DIGEST_KEY = b"kylin-memory-d9d-internal"


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
            consumer: 回调（(event_type, payload) → None/异常）。

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

    def route(self, event_type: str, payload: Dict[str, Any]) -> None:
        """按 event_type（DB 列真源）分发到对应消费者。

        Args:
            event_type: Outbox 事件类型（来自 `outbox.event_type` 独立列，真源）。
            payload: Outbox 事件 payload（不要求含 event_type 字段）。

        Raises:
            UnknownEventTypeError: event_type 未注册。
            ValueError: payload 内嵌 event_type 与 DB 列不一致（fail-closed）。
        """
        embedded = payload.get("event_type")
        if embedded is not None and str(embedded) != event_type:
            raise ValueError(
                f"outbox event_type 与 payload 不一致: db={event_type!r} payload={embedded!r}"
            )
        consumer = self._routes.get(event_type)
        if consumer is None:
            raise UnknownEventTypeError(f"unknown outbox event_type: {event_type!r}")
        logger.info("Outbox 路由分发 type=%s", event_type)
        consumer(event_type, payload)


def build_outbox_router(
    *,
    vector_provider: Optional[Any] = None,
    embedding_service: Optional[Any] = None,
    digest_key_id: str = _DEFAULT_KEY_ID,
    digest_key: bytes = _DEFAULT_DIGEST_KEY,
) -> OutboxRouter:
    """构造生产 Outbox 路由（app.py 注入点）。

    依赖未接线（None）时对应消费者不注册——该事件类型走 UnknownEventTypeError
    → Worker 失败/重试/DL（真实结果，不假装成功；producer 由 D8D 接线后补齐）。

    Args:
        vector_provider: VectorProvider 实现（memory.upserted → index consumer；
            forget.executed → deletion consumer 组合消费中的 Vector delete）。
        embedding_service: EmbeddingService 实例（forget.executed → cache invalidation）。
        digest_key_id / digest_key: 请求摘要签名密钥（注入参数，默认值仅用于 L1 测试；
            真实接线时必须由调用方注入受控 key，与 provider 的 digest_keys 对齐，
            否则真实 SqliteVectorProvider 将稳定返回 DIGEST_KEY_UNAVAILABLE）。
    """
    from db import repositories as repo
    from outbox.deletion_consumer import build_forget_consumer
    from outbox.index_consumer import build_index_consumer

    router = OutboxRouter()
    if vector_provider is not None:
        router.register(
            repo.EVENT_MEMORY_UPSERTED,
            build_index_consumer(
                vector_provider,
                digest_key_id=digest_key_id,
                digest_key=digest_key,
            ),
        )
    if embedding_service is not None:
        router.register(
            repo.EVENT_FORGET_EXECUTED,
            build_forget_consumer(
                embedding_service,
                vector_provider=vector_provider,
                digest_key_id=digest_key_id,
                digest_key=digest_key,
            ),
        )
    return router
