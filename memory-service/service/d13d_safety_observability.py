"""D13D Safety 执行观测（只读，不参与生产准入决策）。

该模块为冻结评测提供同一隔离数据库内的可审计事实：它只读取已经经过
``event.ingest`` 真实准入的 source_events，并通过 Repository 的 user-scoped
查询执行跨用户探测。它不接受 expected、Gold、阈值或调用方传入的计数。
"""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import and_, func, select

from db import repositories as repo
from db.schema import memory_entries, source_events


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
    Missing trace facts fail closed instead of returning a fabricated all-zero
    result. ``foreign_user_id`` is required so cross-user isolation is checked
    through the same user-scoped Repository entry point used by the service.
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
    normal_memory_write_count = int(
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

    # Probe every persisted event through the Repository's mandatory user
    # filter. A non-null result would prove that this trace leaked across users.
    cross_user_violation_count = sum(
        1
        for event_id in event_ids
        if repo.get_source_event_by_event_id(
            conn, user_id=foreign_user_id, event_id=event_id
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
