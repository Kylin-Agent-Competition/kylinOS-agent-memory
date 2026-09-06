"""deletion_consumer.py — D9D forget.executed → deletion consumer

消费 `forget.executed` Outbox 事件，组合消费（HIGH-02）：
  1. Cache Invalidation（复用 D11A `embedding/outbox_consumer.py` 的 payload 处理）
  2. Vector delete（`vector_provider.delete(VectorDeleteRequest)`，D10-B 已合并
     `SqliteVectorProvider.delete`）
  全部成功才返回成功（不得部分副作用成功即 ACK）；`vector_provider is None` 时
  forget.executed 真实失败（retry/DL，不假装成功）。

行为（D-REQ-05；TD-A-D10-CACHE-INVALIDATION；HIGH-02）：
  - `embedding_service.invalidator is None` → 真实失败（RuntimeError）
  - `vector_provider is None` → 真实失败（RuntimeError，Vector/FTS 删除未接线不得 ACK）
  - payload 缺 event_id / 非法枚举 → ValueError（Worker 退避/进 DL）
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from db import repositories as repo
from embedding.embedding_service import EmbeddingService
from embedding.outbox_consumer import _handle_deletion_payload
from observability.request_context import get_request_context
from retrieval.contracts import (
    ConfirmationMode,
    Digest,
    ResolvedBy,
    ResolvedDeleteSelector,
    SelectionMode,
    VectorDeleteRequest,
    Watermark,
    WatermarkDomain,
    WatermarkKind,
    digest_from_canonical,
)
from retrieval.provider import VectorProvider

logger = logging.getLogger(__name__)

# Outbox 消费回调类型：(event_type, payload) → 成功返回 None，失败抛异常（HIGH-01）
EventConsumer = Callable[[str, Dict[str, Any]], None]

# 未显式提供时使用的派生元数据默认（骨架注入点，host 接线后可覆盖）
_DEFAULT_INDEX_GENERATION = "d9d-skeleton"
_DEFAULT_DEADLINE_MS = 5000
_DEFAULT_KEY_ID = "d9d-internal"


def _derive_watermark(payload: Dict[str, Any]) -> Watermark:
    """从 payload 派生源水位；缺省用 0（单调整数）。"""
    value = payload.get("source_watermark_value")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        wm_value = value
    else:
        wm_value = 0
    user_id = str(payload.get("user_id", ""))
    return Watermark(
        domain=WatermarkDomain(
            scope_id=f"user:{user_id}",
            stream="forget_executed",
            partition="default",
            source_generation="v1",
        ),
        kind=WatermarkKind.MONOTONIC_INT,
        value=wm_value,
    )


def _build_delete_request(
    *,
    event_type: str,
    payload: Dict[str, Any],
    digest_key_id: str,
    digest_key: bytes,
    index_generation: str,
    deadline_ms: int,
) -> VectorDeleteRequest:
    """从 forget.executed payload 构造 VectorDeleteRequest（HIGH-02）。

    Payload 对齐 D10D 契约执行快照：
        user_id / forget_plan_id / resolved_target_ids / version_ids /
        selection_hash / preview_ref / preview_hash / event_id
    缺关键字段 → ValueError（Worker 退避/进 DL）。
    """
    event_id = str(payload.get("event_id", ""))
    user_id = payload.get("user_id")
    resolved_target_ids = payload.get("resolved_target_ids") or payload.get("memory_ids")
    version_ids = payload.get("version_ids")
    selection_hash = payload.get("selection_hash") or payload.get("preview_hash")

    missing = [
        name
        for name, value in (
            ("user_id", user_id),
            ("resolved_target_ids", resolved_target_ids),
            ("selection_hash", selection_hash),
        )
        if value is None
    ]
    if missing:
        raise ValueError(
            f"forget.executed payload 缺字段: {', '.join(missing)} (event_id={event_id})"
        )
    # G3（E 授权 #160）：接受 knowledge:/preference: tagged 目标，规范化成数字 memory id；
    # 未知 tag / 非数字 fail-closed。
    memory_ids = []
    for raw in resolved_target_ids:
        token = str(raw)
        if ":" in token:
            kind, _, num = token.partition(":")
            if kind not in ("knowledge", "preference") or not num.isdecimal():
                raise ValueError(
                    f"forget.executed 目标含未知 kind/非数字 id: {token!r} (event_id={event_id})"
                )
            memory_ids.append(num)
        else:
            memory_ids.append(token)
    if not memory_ids:
        raise ValueError(f"forget.executed resolved_target_ids 为空 (event_id={event_id})")
    if version_ids is None:
        raise ValueError(
            f"forget.executed version_ids 缺失（Vector 需按版本精确删除）(event_id={event_id})"
        )
    version_ids = [str(x) for x in version_ids]
    if len(version_ids) != len(memory_ids):
        raise ValueError(
            f"forget.executed version_ids 与 resolved_target_ids 长度不一致 "
            f"(event_id={event_id})"
        )

    preview_ref = str(payload.get("forget_plan_id") or payload.get("preview_ref") or event_id)
    preview_hash = Digest(selection_hash)
    request_id = str(payload.get("request_id") or uuid.uuid4().hex)
    idempotency_key = str(
        payload.get("idempotency_key")
        or f"forget:{preview_ref}:{','.join(memory_ids)}"
    )

    selector = ResolvedDeleteSelector(
        user_id=str(user_id),
        memory_ids=memory_ids,
        version_ids=version_ids,
        selection_mode=(
            SelectionMode.SINGLE_ITEM
            if len(memory_ids) == 1
            else SelectionMode.RESOLVED_BATCH
        ),
        selection_hash=Digest(selection_hash),
        resolved_by=ResolvedBy.DETERMINISTIC_RULE_ENGINE,
        preview_ref=preview_ref,
        preview_hash=preview_hash,
        confirmation_mode=ConfirmationMode.EXPLICIT,
        confirmation_ref=str(payload.get("confirmation_ref") or event_id),
    )

    request = VectorDeleteRequest(
        request_id=request_id,
        trace_id=str(payload.get("trace_id") or f"outbox:{event_id}"),
        user_id=str(user_id),
        deadline_at=datetime.now(timezone.utc) + timedelta(milliseconds=deadline_ms),
        idempotency_key=idempotency_key,
        payload_hash="hmac-sha256:dummy:" + "0" * 64,  # 占位，下方签名覆盖
        index_generation=(
            str(payload.get("index_generation"))
            if payload.get("index_generation")
            else index_generation
        ),
        source_watermark=_derive_watermark(payload),
        selector=selector,
    )
    canonical = request.model_dump(
        mode="json",
        exclude={"request_id", "trace_id", "deadline_at", "payload_hash"},
    )
    request = request.model_copy(
        update={"payload_hash": digest_from_canonical(digest_key_id, digest_key, canonical)}
    )
    return request


def build_forget_consumer(
    embedding_service: EmbeddingService,
    *,
    vector_provider: Optional[VectorProvider] = None,
    digest_key_id: str = _DEFAULT_KEY_ID,
    digest_key: bytes = b"kylin-memory-d9d-internal",
    index_generation: str = _DEFAULT_INDEX_GENERATION,
    deadline_ms: int = _DEFAULT_DEADLINE_MS,
) -> EventConsumer:
    """构造 forget.executed → 组合消费（Cache Invalidation + Vector delete）。

    Args:
        embedding_service: EmbeddingService 实例（含已接线的 CacheInvalidator）。
        vector_provider: VectorProvider 实现（Vector delete；None → 真实失败）。
        digest_key_id / digest_key: 请求摘要签名密钥（provider 校验 payload_hash 用）。
        index_generation / deadline_ms: 派生元数据默认。

    Returns:
        consumer 回调（(event_type, payload) → None/异常）。

    Payload 格式（对齐 D10D 契约执行快照）：
        {
            "event_id": str, "user_id": str,
            "resolved_target_ids": list[str], "version_ids": list[str],
            "selection_hash": str, "forget_plan_id": str,
            "target_type": str, "content_hashes": list[str],
            "content_fingerprints": list[str], "forget_mode": str,
        }
    """
    if embedding_service.invalidator is None:
        logger.warning(
            "CacheInvalidator 未接线（invalidator is None），"
            "forget.executed 消费者将真实失败（不假装成功）"
        )
    if vector_provider is None:
        logger.warning(
            "VectorProvider 未接线（vector_provider is None），"
            "forget.executed 消费者将真实失败（HIGH-02：Vector/FTS 删除未完成不得 ACK）"
        )

    def _consumer(event_type: str, payload: Dict[str, Any]) -> None:
        # HIGH-01：路由真源 = DB 列 event_type（显式传入），payload 内嵌值仅做一致性校验
        embedded = payload.get("event_type")
        if embedded is not None and str(embedded) != event_type:
            raise ValueError(
                f"forget consumer event_type 不一致: db={event_type!r} payload={embedded!r}"
            )
        if event_type != repo.EVENT_FORGET_EXECUTED:
            raise ValueError(
                f"forget consumer expected {repo.EVENT_FORGET_EXECUTED!r}, got {event_type!r}"
            )
        # 组合消费 Step 1：Cache Invalidation（D11A 既有处理，不改其行为）
        _handle_deletion_payload(payload, embedding_service)
        # 组合消费 Step 2：Vector delete（HIGH-02：未接线不得 ACK）
        if vector_provider is None:
            raise RuntimeError(
                "forget.executed 组合消费未完成：vector_provider 未接线 "
                "（Vector/FTS 删除未完成不得 ACK，HIGH-02）"
            )
        request = _build_delete_request(
            event_type=event_type,
            payload=payload,
            digest_key_id=digest_key_id,
            digest_key=digest_key,
            index_generation=index_generation,
            deadline_ms=deadline_ms,
        )
        result = vector_provider.delete(request)
        ctx = get_request_context()
        if not result.ok:
            err = result.error
            logger.error(
                "Forget consumer Vector delete 失败 event_id=%s trace_id=%s error=%s",
                payload.get("event_id", ""),
                payload.get("trace_id", "") or ctx.get("trace_id", ""),
                f"{err.code.value if err else 'unknown'}: {err.message if err else 'unknown'}",
            )
            raise RuntimeError(
                f"forget vector delete failed: {err.code.value if err else 'unknown'}"
            )
        logger.info(
            "Forget consumer 完成 event_id=%s deleted=%d matched=%d",
            payload.get("event_id", ""),
            result.value.deleted_count if result.value else 0,
            result.value.matched_count if result.value else 0,
        )

    return _consumer
