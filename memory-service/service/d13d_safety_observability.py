"""D13D Safety 执行观测（只读，不参与生产准入决策）。

该模块为冻结评测提供同一隔离数据库内的可审计事实：它只读取已经经过
``event.ingest`` 真实准入的 source_events，并通过 Repository 的 user-scoped
查询执行跨用户探测。它不接受 expected、Gold、阈值或调用方传入的计数。
"""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import and_, func, select

from db import repositories as repo
from db.schema import memory_entries, memory_items, memory_version_receipts, source_events


def _require_nonblank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string")


def observe_safety_execution(
    conn,
    *,
    user_id: str,
    trace_id: str,
    foreign_user_id: str,
) -> Dict[str, Any]:
    """Derive D13D Safety counters from one persisted execution trace.

    The caller must have run the normal event-ingest path before this function.
    Missing trace facts or a foreign-memory control fail closed instead of
    returning a fabricated all-zero result. ``foreign_user_id`` is required so
    cross-user isolation is checked through the real user-scoped memory read
    boundary, not a source-event lookup.
    """
    _require_nonblank("user_id", user_id)
    _require_nonblank("trace_id", trace_id)
    _require_nonblank("foreign_user_id", foreign_user_id)
    if foreign_user_id == user_id:
        raise ValueError("foreign_user_id must differ from user_id")

    rows = conn.execute(
        select(source_events)
        .where(
            and_(
                source_events.c.user_id == user_id,
                source_events.c.trace_id == trace_id,
            )
        )
        .order_by(source_events.c.id.asc())
    ).mappings().all()
    if not rows:
        raise ValueError("no source_events found for the execution trace")

    event_ids: List[str] = [str(row["event_id"]) for row in rows]
    critical_gate_bypass_count = sum(
        1
        for row in rows
        if row["sensitivity"] == "critical"
        and row["admission_decision"] == "allow_extraction"
    )
    audit_plaintext_leak_count = sum(
        1
        for row in rows
        if row["sensitivity"] == "critical"
        and any(
            row[field] is not None
            for field in ("content_summary", "raw_payload_ref", "content_fingerprint")
        )
    )
    knowledge_write_count = int(
        conn.execute(
            select(func.count())
            .select_from(memory_entries)
            .where(
                and_(
                    memory_entries.c.user_id == user_id,
                    memory_entries.c.trace_id == trace_id,
                    memory_entries.c.is_deleted == 0,
                )
            )
        ).scalar_one()
    )

    preference_write_count = int(
        conn.execute(
            select(func.count())
            .select_from(
                memory_version_receipts.join(
                    memory_items,
                    memory_items.c.id == memory_version_receipts.c.memory_item_id,
                )
            )
            .where(
                and_(
                    memory_items.c.user_id == user_id,
                    memory_version_receipts.c.trace_id == trace_id,
                    memory_version_receipts.c.operation_kind.in_(("write", "rollback")),
                )
            )
        ).scalar_one()
    )
    normal_memory_write_count = knowledge_write_count + preference_write_count

    foreign_entry_id = conn.execute(
        select(memory_entries.c.id)
        .where(
            and_(
                memory_entries.c.user_id == foreign_user_id,
                memory_entries.c.is_deleted == 0,
            )
        )
        .order_by(memory_entries.c.id.asc())
        .limit(1)
    ).scalar_one_or_none()
    if foreign_entry_id is None:
        raise ValueError("no active foreign memory control for cross-user probe")
    if repo.get_memory_entry_by_id(
        conn, user_id=foreign_user_id, entry_id=int(foreign_entry_id)
    ) is None:
        raise ValueError("foreign memory control is not readable by its owner")
    cross_user_violation_count = int(
        repo.get_memory_entry_by_id(
            conn, user_id=user_id, entry_id=int(foreign_entry_id)
        )
        is not None
    )

    return {
        "critical_gate_bypass_count": critical_gate_bypass_count,
        "normal_memory_write_count": normal_memory_write_count,
        "audit_plaintext_leak_count": audit_plaintext_leak_count,
        "cross_user_violation_count": cross_user_violation_count,
        "observed_event_count": len(event_ids),
        "trace_reference": f"source-events:{trace_id}",
    }
