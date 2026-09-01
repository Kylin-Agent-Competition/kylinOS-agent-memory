"""index_consumer.py — D9D memory.upserted → Vector upsert 消费者

消费 `memory.upserted` Outbox 事件，构造 `VectorUpsertRequest`，调用
`retrieval.provider.VectorProvider.upsert()`（注入实现）。

行为（D-REQ-05；02 §11.3）：
  - payload 缺/非法字段 → ValueError（Worker 退避/进 DL）
  - provider.upsert() 返回非 ok → 抛异常（Worker 退避/进 DL）
  - 无真实 Vector provider 注入时由调用方保证（本骨架只消费注入的实现，
    不假装成功）
  - 日志只记录 event_id/trace_id/类型/错误摘要（sanitize_message），
    不记录 payload 正文/PII

安全：构造 VectorUpsertRequest 必须透传 payload 的 user_id；Vector 层硬过滤
由 provider 负责（本版不绕过，[02 §16.6] 跨用户隔离）。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict

from db import repositories as repo
from observability.json_logging import sanitize_message
from observability.request_context import get_request_context
from retrieval.contracts import (
    ObjectType,
    VectorRecord,
    VectorUpsertRequest,
    Watermark,
    WatermarkDomain,
    WatermarkKind,
    digest_from_canonical,
)
from retrieval.provider import VectorProvider

logger = logging.getLogger(__name__)

# Outbox 消费回调类型：payload dict → 成功返回 None，失败抛异常
EventConsumer = Callable[[Dict[str, Any]], None]

# 未显式提供时使用的派生元数据默认（骨架注入点，host 接线后可覆盖）
_DEFAULT_INDEX_GENERATION = "d9d-skeleton"
_DEFAULT_DEADLINE_MS = 5000
_DEFAULT_KEY_ID = "d9d-internal"


def _semantic_payload(request: VectorUpsertRequest) -> dict[str, Any]:
    """与 provider 幂等/摘要校验一致：剔除 request_id/trace_id/deadline_at/payload_hash。

    对齐 tests/retrieval/fakes.py 的 semantic_payload（VectorUpsertRequest 无 scope）。
    """
    return request.model_dump(
        mode="json",
        exclude={"request_id", "trace_id", "deadline_at", "payload_hash"},
    )


def _derive_index_generation(payload: Dict[str, Any], default: str) -> str:
    value = payload.get("index_generation")
    return value if isinstance(value, str) and value else default


def _derive_watermark(payload: Dict[str, Any]) -> Watermark:
    """从 payload 派生源水位；缺省用 0（单调整数），保证 provider 幂等比较可用。

    骨架注入点：真实 producer（D8D 接线）提供 source_watermark 后覆盖。
    """
    value = payload.get("source_watermark_value")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        wm_value = value
    else:
        wm_value = 0
    user_id = str(payload.get("user_id", ""))
    return Watermark(
        domain=WatermarkDomain(
            scope_id=f"user:{user_id}",
            stream="memory_upserted",
            partition="default",
            source_generation="v1",
        ),
        kind=WatermarkKind.MONOTONIC_INT,
        value=wm_value,
    )


def build_index_consumer(
    provider: VectorProvider,
    *,
    digest_key_id: str = _DEFAULT_KEY_ID,
    digest_key: bytes = b"kylin-memory-d9d-internal",
    index_generation: str = _DEFAULT_INDEX_GENERATION,
    deadline_ms: int = _DEFAULT_DEADLINE_MS,
) -> EventConsumer:
    """构造 memory.upserted → Vector upsert 消费者。

    Args:
        provider: 注入的 VectorProvider 实现（真实 provider 或 L1 fake）。
        digest_key_id / digest_key: 请求摘要签名密钥（provider 校验 payload_hash
            用；测试注入 fake 的默认 key）。
        index_generation: 未显式提供时的索引代次。
        deadline_ms: 构造请求的 deadline 预算。

    Returns:
        consumer 回调（payload dict → None/异常）。
    """

    def _consumer(payload: Dict[str, Any]) -> None:
        event_type = payload.get("event_type", "")
        if event_type != repo.EVENT_MEMORY_UPSERTED:
            raise ValueError(
                f"index consumer expected {repo.EVENT_MEMORY_UPSERTED!r}, got {event_type!r}"
            )

        trace_id = str(payload.get("trace_id", ""))
        event_id = str(payload.get("event_id", ""))

        user_id = payload.get("user_id")
        memory_id = payload.get("memory_id")
        version_id = payload.get("version_id")
        vector = payload.get("vector")
        object_type = payload.get("object_type")
        index_text_hash = payload.get("index_text_hash")

        missing = [
            name
            for name, value in (
                ("user_id", user_id),
                ("memory_id", memory_id),
                ("version_id", version_id),
                ("vector", vector),
                ("object_type", object_type),
                ("index_text_hash", index_text_hash),
            )
            if value is None
        ]
        if missing:
            raise ValueError(
                f"memory.upserted payload 缺字段: {', '.join(missing)} (event_id={event_id})"
            )

        request_id = str(payload.get("request_id") or uuid.uuid4().hex)
        idempotency_key = str(
            payload.get("idempotency_key") or f"memory:{memory_id}:{version_id}"
        )
        deadline_at = datetime.now(timezone.utc) + timedelta(milliseconds=deadline_ms)

        record = VectorRecord(
            memory_id=str(memory_id),
            version_id=str(version_id),
            user_id=str(user_id),
            vector=vector,
            object_type=ObjectType(str(object_type)),
            index_text_hash=str(index_text_hash),
        )
        # 先以占位摘要构造（payload_hash 是合法 Digest 格式），再以签名后的
        # payload_hash 复制最终请求（_semantic_payload 排除 payload_hash，占位不影响摘要）。
        placeholder_hash = "hmac-sha256:dummy:" + "0" * 64
        request = VectorUpsertRequest(
            request_id=request_id,
            trace_id=trace_id,
            user_id=str(user_id),
            deadline_at=deadline_at,
            idempotency_key=idempotency_key,
            payload_hash=placeholder_hash,
            index_generation=_derive_index_generation(payload, index_generation),
            source_watermark=_derive_watermark(payload),
            records=[record],
        )
        request = request.model_copy(
            update={
                "payload_hash": digest_from_canonical(
                    digest_key_id, digest_key, _semantic_payload(request)
                )
            }
        )

        result = provider.upsert(request)
        ctx = get_request_context()
        if not result.ok:
            err = result.error
            logger.error(
                "Index consumer 失败 event_id=%s trace_id=%s type=%s error=%s",
                event_id, trace_id or ctx.get("trace_id", ""), event_type,
                sanitize_message(f"{err.code.value if err else 'unknown'}: {err.message if err else 'unknown'}"),
            )
            raise RuntimeError(f"vector upsert failed: {err.code.value if err else 'unknown'}")
        logger.info(
            "Index consumer 完成 event_id=%s trace_id=%s type=%s accepted=%d",
            event_id, trace_id or ctx.get("trace_id", ""), event_type,
            result.value.accepted_count if result.value else 0,
        )

    return _consumer
