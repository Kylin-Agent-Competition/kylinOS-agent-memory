"""forgetting.py — D-track preview resolver seam（确定性 scoped 解析）

D13D P0-I2 extends the existing single-item/session resolver with three
approved scopes: structured topic_key, source-event occurred_at windows, and
a Memory-Service-only full reset. Source events remain immutable audit facts.

真实结果，非 Mock/固定返回：零命中返回 []（契约 §八「目标条目不存在 → affected_count=0
正常路径」），不支持的作用域抛 UnsupportedForgetScopeError → INVALID_REQUEST。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import and_, select

from db import repositories as repo
from db.schema import (
    conversations,
    memory_entries,
    memory_items,
    memory_relation,
    memory_versions,
    source_events,
    turns,
)


def _resolve_single_knowledge(
    conn, *, user_id: str, target_id: Optional[str]
) -> List[str]:
    if not target_id:
        return []
    try:
        entry_id = int(target_id)
    except (TypeError, ValueError):
        return []
    row = conn.execute(
        select(memory_entries.c.id).where(
            and_(
                memory_entries.c.id == entry_id,
                memory_entries.c.user_id == user_id,
                memory_entries.c.is_deleted == 0,
            )
        )
    ).scalar()
    return [str(entry_id)] if row is not None else []


def _resolve_single_preference(
    conn, *, user_id: str, target_id: Optional[str]
) -> List[str]:
    if not target_id:
        return []
    try:
        item_id = int(target_id)
    except (TypeError, ValueError):
        return []
    row = conn.execute(
        select(memory_items.c.id).where(
            and_(
                memory_items.c.id == item_id,
                memory_items.c.user_id == user_id,
            )
        )
    ).scalar()
    return [str(item_id)] if row is not None else []


def _resolve_session_knowledge(
    conn, *, user_id: str, target_session_id: Optional[str]
) -> List[str]:
    if not target_session_id:
        return []
    # memory_entries.source_turn_id → turns.session_id → conversations.user_id（跨用户隔离）
    rows = conn.execute(
        select(memory_entries.c.id)
        .join(turns, memory_entries.c.source_turn_id == turns.c.id)
        .join(conversations, turns.c.session_id == conversations.c.session_id)
        .where(
            and_(
                turns.c.session_id == target_session_id,
                conversations.c.user_id == user_id,
                memory_entries.c.user_id == user_id,
                memory_entries.c.is_deleted == 0,
            )
        )
        .order_by(memory_entries.c.id.asc())
    ).scalars().all()
    return [str(x) for x in rows]


def _resolve_topic_knowledge(
    conn, *, user_id: str, target_topic: Optional[str]
) -> List[str]:
    if not target_topic:
        return []
    rows = conn.execute(
        select(memory_entries.c.id)
        .where(
            and_(
                memory_entries.c.user_id == user_id,
                memory_entries.c.entry_type == "knowledge",
                memory_entries.c.topic_key == target_topic,
                memory_entries.c.is_deleted == 0,
            )
        )
        .order_by(memory_entries.c.id.asc())
    ).scalars().all()
    return [str(entry_id) for entry_id in rows]


def _parse_time_window(target_time_range: Optional[str]) -> Tuple[str, str]:
    if not target_time_range:
        raise repo.UnsupportedForgetScopeError("time_window requires target_time_range")
    try:
        payload = json.loads(target_time_range)
        start = datetime.fromisoformat(str(payload["from"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(payload["to"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise repo.UnsupportedForgetScopeError("invalid time_window range") from exc
    if start.tzinfo is None or end.tzinfo is None:
        raise repo.UnsupportedForgetScopeError("time_window requires timezone-aware bounds")
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    if start_utc >= end_utc:
        raise repo.UnsupportedForgetScopeError("time_window requires from < to")
    return start_utc.isoformat(), end_utc.isoformat()


def _resolve_time_window_knowledge(
    conn, *, user_id: str, target_time_range: Optional[str]
) -> List[str]:
    start, end = _parse_time_window(target_time_range)
    rows = conn.execute(
        select(memory_entries.c.id)
        .join(
            memory_relation,
            and_(
                memory_relation.c.user_id == memory_entries.c.user_id,
                memory_relation.c.left_endpoint_type == "knowledge",
                memory_relation.c.left_endpoint_id == memory_entries.c.knowledge_id,
                memory_relation.c.relation_type == "evidence",
                memory_relation.c.is_primary == 1,
            ),
        )
        .join(
            source_events,
            and_(
                source_events.c.user_id == memory_entries.c.user_id,
                source_events.c.event_id == memory_relation.c.right_endpoint_id,
            ),
        )
        .where(
            and_(
                memory_entries.c.user_id == user_id,
                memory_entries.c.entry_type == "knowledge",
                memory_entries.c.is_deleted == 0,
                source_events.c.occurred_at >= start,
                source_events.c.occurred_at < end,
            )
        )
        .distinct()
        .order_by(memory_entries.c.id.asc())
    ).scalars().all()
    return [str(entry_id) for entry_id in rows]


def _resolve_full_reset(conn, *, user_id: str) -> List[str]:
    knowledge_ids = conn.execute(
        select(memory_entries.c.id)
        .where(
            and_(
                memory_entries.c.user_id == user_id,
                memory_entries.c.entry_type == "knowledge",
                memory_entries.c.is_deleted == 0,
            )
        )
        .order_by(memory_entries.c.id.asc())
    ).scalars().all()
    preference_ids = conn.execute(
        select(memory_items.c.id)
        .join(memory_versions, memory_versions.c.id == memory_items.c.current_version_id)
        .where(
            and_(
                memory_items.c.user_id == user_id,
                memory_versions.c.is_current == 1,
                memory_versions.c.memory_status != "removed",
            )
        )
        .order_by(memory_items.c.id.asc())
    ).scalars().all()
    return [*(f"knowledge:{entry_id}" for entry_id in knowledge_ids), *(f"preference:{item_id}" for item_id in preference_ids)]


def resolve_forget_targets(
    conn,
    *,
    user_id: str,
    forget_mode: str,
    target_type: str,
    target_id: Optional[str],
    target_session_id: Optional[str],
    target_topic: Optional[str] = None,
    target_time_range: Optional[str] = None,
) -> List[str]:
    """Resolve approved scoped targets under a mandatory user filter.

    Returns:
        resolved_target_ids（去重后字符串列表；零命中返回 []，属合法 Preview）。

    Raises:
        repo.UnsupportedForgetScopeError: 本期不支持的 forget_mode / target_type 组合。
    """
    if forget_mode == "single_item":
        if target_type not in ("knowledge", "preference"):
            raise repo.UnsupportedForgetScopeError("single_item requires knowledge or preference")
        if target_type == "knowledge":
            resolved = _resolve_single_knowledge(conn, user_id=user_id, target_id=target_id)
        else:
            resolved = _resolve_single_preference(conn, user_id=user_id, target_id=target_id)
    elif forget_mode == "session":
        if target_type != "knowledge":
            # memory_items 无会话关联，session + preference 无法确定性解析 → fail-closed
            raise repo.UnsupportedForgetScopeError(
                "session-scoped resolution only supports target_type=knowledge"
            )
        resolved = _resolve_session_knowledge(
            conn, user_id=user_id, target_session_id=target_session_id
        )
    elif forget_mode == "topic":
        if target_type != "knowledge":
            raise repo.UnsupportedForgetScopeError("topic only supports knowledge")
        resolved = _resolve_topic_knowledge(conn, user_id=user_id, target_topic=target_topic)
    elif forget_mode == "time_window":
        if target_type != "knowledge":
            raise repo.UnsupportedForgetScopeError("time_window only supports knowledge")
        resolved = _resolve_time_window_knowledge(
            conn, user_id=user_id, target_time_range=target_time_range
        )
    elif forget_mode == "full_reset":
        if target_type != "all":
            raise repo.UnsupportedForgetScopeError("full_reset requires target_type=all")
        resolved = _resolve_full_reset(conn, user_id=user_id)
    else:
        raise repo.UnsupportedForgetScopeError(f"unsupported forget_mode: {forget_mode}")

    # 去重且保持稳定顺序（selection_hash 由排序派生，见 repo.compute_selection_hash）
    seen = set()
    result: List[str] = []
    for raw in resolved:
        if raw not in seen:
            seen.add(raw)
            result.append(raw)
    return result


__all__ = ["resolve_forget_targets"]
