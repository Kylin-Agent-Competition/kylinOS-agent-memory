"""
cleaner.py — 轨道 A Day6 统一事件清洗器

职责（架构 6.2 第 1-2 步）：
1. Pydantic 校验：拒绝字段缺失、类型错误和未知高风险字段（MemorySourceEvent extra=forbid）。
2. 格式标准化：时间（occurred_at/captured_at → aware UTC ISO8601）、状态
   （source_business_status/processing_status 枚举归一）、Tool 参数结构、
   来源标识（source_type/event_type 层级归一）。

设计要点：
- 确定性：同一输入多次清洗结果完全一致（可重复、可测试）。
- 结构化错误：校验失败抛 EventValidationError(code, message)，不静默吞掉。
- 不落库、不写日志原文（敏感标记在 sensitive.py 完成）。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import ValidationError

from pipeline.schemas import (
    EventValidationError,
    MemorySourceEvent,
    NormalizedEvent,
    ProcessingStatus,
)

# 允许的 event_id / idempotency_key 格式（防注入/异常字符）
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-:.]{1,128}$")


class EventCleaner:
    """统一事件清洗器：raw dict → NormalizedEvent（确定性、结构化错误）。"""

    def clean(self, raw: Dict[str, Any]) -> NormalizedEvent:
        """清洗单个 raw 事件。

        Args:
            raw: 外部输入事件 dict（MemorySourceEvent 字段）。

        Returns:
            NormalizedEvent（时间/状态已标准化，processing_status=EXTRACTING）。

        Raises:
            EventValidationError: Pydantic 校验失败或标识字段格式非法。
        """
        if not isinstance(raw, dict):
            raise EventValidationError(
                "ERR_EVENT_NOT_DICT", f"raw event must be dict, got {type(raw).__name__}")

        # 1. 标识字段格式预检（防注入/异常字符）
        for field in ("event_id", "user_id", "actor_id", "idempotency_key", "session_id"):
            val = raw.get(field)
            if val is not None and not isinstance(val, str):
                raise EventValidationError(
                    "ERR_EVENT_ID_TYPE", f"{field} must be str, got {type(val).__name__}")
            if isinstance(val, str) and not _ID_PATTERN.match(val):
                raise EventValidationError(
                    "ERR_EVENT_ID_FORMAT",
                    f"{field} contains illegal chars: {val!r}")

        # 2. Pydantic 校验（拒绝缺失/类型错/未知字段）
        try:
            event = MemorySourceEvent.model_validate(raw)
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {}
            loc = ".".join(str(x) for x in first.get("loc", []))
            msg = first.get("msg", str(exc))
            raise EventValidationError(
                "ERR_EVENT_VALIDATION", f"{loc}: {msg}") from exc

        # 3. 状态标准化：source_business_status 由 raw 归一（枚举已由 Pydantic 保证）；
        #    processing_status 置 EXTRACTING（D3 契约五值：清洗完成进入抽取阶段）。
        status = ProcessingStatus.EXTRACTING

        # 4. 构建标准化输出（字段一一映射，extra=forbid 保证不丢字段）
        return NormalizedEvent(
            event_id=event.event_id,
            user_id=event.user_id,
            actor_id=event.actor_id,
            source_type=event.source_type,
            schema_version=event.schema_version,
            trace_id=event.trace_id,
            event_type=event.event_type,
            source_reference=event.source_reference,
            consent_scope=event.consent_scope,
            idempotency_key=event.idempotency_key,
            source_business_status=event.source_business_status,
            processing_status=status,
            memory_type=event.memory_type,
            occurred_at=event.occurred_at,
            captured_at=event.captured_at,
            session_id=event.session_id,
            raw_payload_ref=event.raw_payload_ref,
            content_summary=event.content_summary,
            turn_id=event.turn_id,
            tool_call_id=event.tool_call_id,
            sensitivity=event.sensitivity,
            is_sensitive_matched=event.is_sensitive_matched,
            should_ignore=event.should_ignore,
            requires_embedding=event.requires_embedding,
            has_structured_payload=event.has_structured_payload,
            language_tag=event.language_tag,
            content_fingerprint=None,  # 由 fingerprint.py 填充
        )

    def clean_many(self, raws: list[Dict[str, Any]]) -> list[NormalizedEvent]:
        """批量清洗（顺序，确定性）。单条失败抛 EventValidationError。"""
        return [self.clean(raw) for raw in raws]


def normalize_time(value: Any) -> datetime:
    """把 str/float/int/datetime 统一为 aware UTC datetime。

    支持 ISO8601（含 Z/±HH:MM）与 epoch 秒（int/float）。
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError as exc:
            raise EventValidationError(
                "ERR_TIME_FORMAT", f"invalid time string: {value!r}") from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    raise EventValidationError(
        "ERR_TIME_TYPE", f"unsupported time type: {type(value).__name__}")
