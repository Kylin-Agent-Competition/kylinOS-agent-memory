"""forgetting.py — D10D D-track preview resolver seam（确定性 scoped 解析）

D6 决策（19_d10d_impl_plan.md §四）：D 轨新增本组件，仅 single_item / session
提供真实确定性解析（user 限定、结构化 ID 输出、非正文）；topic / time_window /
full_reset 本期 fail-closed（F-11 DEFERRED）；event / all 目标本期 fail-closed
（source_events 无 is_deleted 列，D2 决策）。

真实结果，非 Mock/固定返回：零命中返回 []（契约 §八「目标条目不存在 → affected_count=0
正常路径」），不支持的作用域抛 UnsupportedForgetScopeError → INVALID_REQUEST。
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import and_, select

from db import repositories as repo
from db.schema import conversations, memory_entries, memory_items, turns


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


def resolve_forget_targets(
    conn,
    *,
    user_id: str,
    forget_mode: str,
    target_type: str,
    target_id: Optional[str],
    target_session_id: Optional[str],
) -> List[str]:
    """确定性 scoped 解析：single_item / session 限定 user，结构化 ID 输出。

    Returns:
        resolved_target_ids（去重后字符串列表；零命中返回 []，属合法 Preview）。

    Raises:
        repo.UnsupportedForgetScopeError: 本期不支持的 forget_mode / target_type 组合。
    """
    if forget_mode not in ("single_item", "session"):
        raise repo.UnsupportedForgetScopeError(f"unsupported forget_mode: {forget_mode}")
    if target_type not in ("knowledge", "preference"):
        raise repo.UnsupportedForgetScopeError(f"unsupported target_type: {target_type}")

    if forget_mode == "single_item":
        if target_type == "knowledge":
            resolved = _resolve_single_knowledge(conn, user_id=user_id, target_id=target_id)
        else:
            resolved = _resolve_single_preference(conn, user_id=user_id, target_id=target_id)
    else:  # session
        if target_type != "knowledge":
            # memory_items 无会话关联，session + preference 无法确定性解析 → fail-closed
            raise repo.UnsupportedForgetScopeError(
                "session-scoped resolution only supports target_type=knowledge"
            )
        resolved = _resolve_session_knowledge(
            conn, user_id=user_id, target_session_id=target_session_id
        )

    # 去重且保持稳定顺序（selection_hash 由排序派生，见 repo.compute_selection_hash）
    seen = set()
    result: List[str] = []
    for raw in resolved:
        if raw not in seen:
            seen.add(raw)
            result.append(raw)
    return result


__all__ = ["resolve_forget_targets"]
