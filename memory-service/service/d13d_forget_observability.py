"""Read-only D13D Forget execution observation.

This module deliberately sits outside ``forget.execute``.  It captures the
confirmed target set and automatically derived controls before execution, then
derives post-execution DB facts and binds two caller-supplied *real* retrieval
observations through the existing residual evaluator.  It neither accepts
Gold/expected values nor starts a vector engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

from sqlalchemy import and_, select

from db.schema import memory_entries, memory_items, memory_versions
from retrieval.contracts import Watermark
from retrieval.evaluation import (
    ForgetResidualPhase,
    ForgetResidualSample,
    evaluate_forget_residual,
)


_KINDS = frozenset({"knowledge", "preference"})


@dataclass(frozen=True)
class ForgetRetrievalObservation:
    """A real retrieval result and its provenance for one residual phase."""

    sample: ForgetResidualSample
    dataset_version: str
    source_snapshot_id: str
    source_watermark: Watermark


@dataclass(frozen=True)
class ForgetExecutionSnapshot:
    """Pre-execution facts captured without caller-provided survivor lists."""

    user_id: str
    foreign_user_id: str
    confirmed_target_ids: Tuple[str, ...]
    same_user_control_ids: Tuple[str, ...]
    foreign_user_control_ids: Tuple[str, ...]


def _canonical_ids(ids: Iterable[str]) -> Tuple[str, ...]:
    normalized = tuple(sorted(set(ids)))
    if not normalized:
        raise ValueError("confirmed_target_ids must not be empty")
    for target_id in normalized:
        kind, sep, raw_id = target_id.partition(":")
        if not sep or kind not in _KINDS or not raw_id.isdecimal() or int(raw_id) <= 0:
            raise ValueError("target IDs must be tagged knowledge:<id> or preference:<id>")
    return normalized


def _active_ids(conn, *, user_id: str, kinds: frozenset[str]) -> Tuple[str, ...]:
    result: list[str] = []
    if "knowledge" in kinds:
        result.extend(
            f"knowledge:{entry_id}"
            for entry_id in conn.execute(
                select(memory_entries.c.id).where(
                    and_(
                        memory_entries.c.user_id == user_id,
                        memory_entries.c.entry_type == "knowledge",
                        memory_entries.c.is_deleted == 0,
                    )
                )
            ).scalars()
        )
    if "preference" in kinds:
        result.extend(
            f"preference:{item_id}"
            for item_id in conn.execute(
                select(memory_items.c.id)
                .join(memory_versions, memory_versions.c.id == memory_items.c.current_version_id)
                .where(
                    and_(
                        memory_items.c.user_id == user_id,
                        memory_versions.c.is_current == 1,
                        memory_versions.c.memory_status != "removed",
                    )
                )
            ).scalars()
        )
    return tuple(sorted(result))


def capture_forget_execution_snapshot(
    conn,
    *,
    user_id: str,
    foreign_user_id: str,
    confirmed_target_ids: Iterable[str],
) -> ForgetExecutionSnapshot:
    """Capture DB truth immediately before a confirmed Forget execution.

    Controls are derived from active entities, rather than supplied by an
    adapter.  A same-kind foreign control must exist for every selected kind;
    otherwise the caller cannot claim cross-user observation and fails closed.
    """
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id must be a non-blank string")
    if not isinstance(foreign_user_id, str) or not foreign_user_id.strip():
        raise ValueError("foreign_user_id must be a non-blank string")
    if foreign_user_id == user_id:
        raise ValueError("foreign_user_id must differ from user_id")
    confirmed = _canonical_ids(confirmed_target_ids)
    kinds = frozenset(target_id.split(":", 1)[0] for target_id in confirmed)
    active_targets = set(_active_ids(conn, user_id=user_id, kinds=kinds))
    if not set(confirmed).issubset(active_targets):
        raise ValueError("confirmed target is not an active entity owned by user")
    same_user_controls = tuple(sorted(active_targets.difference(confirmed)))
    foreign_controls = _active_ids(conn, user_id=foreign_user_id, kinds=kinds)
    foreign_kinds = {target_id.split(":", 1)[0] for target_id in foreign_controls}
    if foreign_kinds != set(kinds):
        raise ValueError("missing same-kind foreign control for cross-user observation")
    return ForgetExecutionSnapshot(
        user_id=user_id,
        foreign_user_id=foreign_user_id,
        confirmed_target_ids=confirmed,
        same_user_control_ids=same_user_controls,
        foreign_user_control_ids=foreign_controls,
    )


def _residual_count(
    snapshot: ForgetExecutionSnapshot,
    observation: ForgetRetrievalObservation,
    phase: ForgetResidualPhase,
) -> int:
    if tuple(sorted(set(observation.sample.confirmed_target_ids))) != snapshot.confirmed_target_ids:
        raise ValueError("retrieval observation is not bound to confirmed targets")
    report = evaluate_forget_residual(
        [observation.sample],
        phase=phase,
        dataset_version=observation.dataset_version,
        source_snapshot_id=observation.source_snapshot_id,
        source_watermark=observation.source_watermark,
    )
    return report.residual_target_count


def observe_forget_execution(
    conn,
    *,
    snapshot: ForgetExecutionSnapshot,
    realtime_observation: ForgetRetrievalObservation,
    rebuild_observation: ForgetRetrievalObservation,
) -> Dict[str, int]:
    """Derive required D13D Forget facts after committed execution.

    Both retrieval observations are mandatory.  Their residual calculation is
    delegated to ``evaluate_forget_residual`` to keep DB observation separate
    from B-track retrieval algorithms.
    """
    if not isinstance(snapshot, ForgetExecutionSnapshot):
        raise TypeError("snapshot must be ForgetExecutionSnapshot")
    if not isinstance(realtime_observation, ForgetRetrievalObservation):
        raise ValueError("missing realtime retrieval observation")
    if not isinstance(rebuild_observation, ForgetRetrievalObservation):
        raise ValueError("missing rebuild retrieval observation")
    kinds = frozenset(target_id.split(":", 1)[0] for target_id in snapshot.confirmed_target_ids)
    active_owned = set(_active_ids(conn, user_id=snapshot.user_id, kinds=kinds))
    active_foreign = set(_active_ids(conn, user_id=snapshot.foreign_user_id, kinds=kinds))
    missed = len(set(snapshot.confirmed_target_ids).intersection(active_owned))
    wrongly_deleted = len(set(snapshot.same_user_control_ids).difference(active_owned))
    cross_user = len(set(snapshot.foreign_user_control_ids).difference(active_foreign))
    return {
        "missed_target_items": missed,
        "wrongly_deleted_items": wrongly_deleted,
        "cross_user_violation_count": cross_user,
        "residual_after_realtime_query": _residual_count(
            snapshot, realtime_observation, ForgetResidualPhase.REALTIME_DELETE
        ),
        "residual_after_full_rebuild": _residual_count(
            snapshot, rebuild_observation, ForgetResidualPhase.REBUILD
        ),
    }
