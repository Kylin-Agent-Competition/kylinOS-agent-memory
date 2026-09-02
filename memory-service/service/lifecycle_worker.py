"""D8D persistence executor for the frozen, pure ``LifecyclePolicy``.

It deliberately owns no timer and no default thresholds.  A scheduler supplies a
stable ``evaluation_id``, timestamp and explicit PolicyConfig; retrying the same
logical evaluation returns its first receipt rather than re-evaluating it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import and_, insert, select

from db import repositories as repo
from db.schema import memory_lifecycle_receipt
from domain.enums import MemoryStatus
from pipeline.schemas import MemoryType
from service.conflict_resolution_policy import EvidenceTier
from service.lifecycle_policy import LifecycleAction, LifecyclePolicy, LifecycleSnapshot, PolicyConfig


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _policy_hash(config: PolicyConfig) -> str:
    data = config.model_dump(mode="json")
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _fingerprint(*, user_id: str, knowledge_id: str, entry_id: int, revision: int, version_id: str, evaluated_at: str, policy_hash: str) -> str:
    raw = {"user_id": user_id, "knowledge_id": knowledge_id, "memory_entry_id": entry_id, "evaluated_revision": revision, "version_id": version_id, "evaluated_at": evaluated_at, "policy_config_hash": policy_hash}
    return hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def evaluate_lifecycle(
    conn, *, user_id: str, knowledge_id: str, evaluation_id: str,
    policy_config: PolicyConfig, now: datetime,
) -> Dict[str, Any]:
    """Evaluate and persist exactly once, with a CAS-protected mutation.

    Unmapped or otherwise ineligible rows return a structured skipped result and
    never call policy; that is the ADR's no-default/no-provenance-invention rule.
    """
    if not isinstance(policy_config, PolicyConfig):
        raise TypeError("policy_config must be PolicyConfig")
    evaluated_at = _iso(now)
    existing = conn.execute(select(memory_lifecycle_receipt).where(and_(memory_lifecycle_receipt.c.user_id == user_id, memory_lifecycle_receipt.c.evaluation_id == evaluation_id))).mappings().first()
    policy_hash = _policy_hash(policy_config)
    # Replay must be checked before reading the mutable business row: a successful
    # first mutation advances row_revision, but that must not turn an otherwise
    # identical scheduler retry into a false idempotency conflict.
    if existing is not None:
        if existing["knowledge_id"] != knowledge_id or existing["evaluated_at"] != evaluated_at or existing["policy_config_hash"] != policy_hash:
            raise ValueError("evaluation_id replay has a different immutable input")
        return {"status": "replayed", "receipt": dict(existing)}
    row = repo.get_lifecycle_memory(conn, user_id=user_id, knowledge_id=knowledge_id)
    if row is None:
        return {"status": "skipped", "reason_code": "ineligible_or_not_found"}
    version_id = f"v{int(row['version'])}"
    fingerprint = _fingerprint(user_id=user_id, knowledge_id=knowledge_id, entry_id=int(row["id"]), revision=int(row["row_revision"]), version_id=version_id, evaluated_at=evaluated_at, policy_hash=policy_hash)
    snapshot = LifecycleSnapshot(
        knowledge_id=knowledge_id, user_id=user_id, memory_type=MemoryType(row["memory_type"]),
        memory_status=MemoryStatus(row["memory_status"]), evidence_tier=EvidenceTier(row["evidence_tier"]),
        confidence_score=float(row["confidence"]), access_count=row["access_count"],
        last_accessed_at=datetime.fromisoformat(row["last_accessed_at"]) if row["last_accessed_at"] else None,
        created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]),
    )
    decision = LifecyclePolicy(policy_config).decide(snapshot, now=now)
    action = decision.action.value
    applied = 0
    if decision.action in {LifecycleAction.PROMOTE, LifecycleAction.DEMOTE}:
        applied = repo.update_lifecycle_memory(conn, user_id=user_id, knowledge_id=knowledge_id, expected_row_revision=int(row["row_revision"]), memory_type=decision.target_memory_type.value if decision.target_memory_type else None)
    elif decision.action is LifecycleAction.EXPIRE:
        applied = repo.update_lifecycle_memory(conn, user_id=user_id, knowledge_id=knowledge_id, expected_row_revision=int(row["row_revision"]), memory_status="expired")
    if decision.action in {LifecycleAction.PROMOTE, LifecycleAction.DEMOTE, LifecycleAction.EXPIRE} and applied != 1:
        return {"status": "cas_miss", "reason_code": "stale_revision"}
    receipt_values = {"user_id": user_id, "evaluation_id": evaluation_id, "evaluation_fingerprint": fingerprint, "knowledge_id": knowledge_id, "memory_entry_id": int(row["id"]), "evaluated_revision": int(row["row_revision"]), "version_id": version_id, "policy_config_hash": policy_hash, "evaluated_at": evaluated_at, "action": action, "reason_code": decision.reason_code, "target_memory_type": decision.target_memory_type.value if decision.target_memory_type else None, "target_memory_status": decision.target_memory_status.value if decision.target_memory_status else None, "applied": applied, "created_at": repo._now_iso()}
    result = conn.execute(insert(memory_lifecycle_receipt).values(**receipt_values))
    if decision.action in {LifecycleAction.PROMOTE, LifecycleAction.DEMOTE, LifecycleAction.EXPIRE, LifecycleAction.ARCHIVE_REQUEST}:
        event_type = repo.EVENT_MEMORY_LIFECYCLE_ARCHIVE_REQUESTED if decision.action is LifecycleAction.ARCHIVE_REQUEST else repo.EVENT_MEMORY_LIFECYCLE_CHANGED
        repo._d8d_outbox(conn, aggregate_id=knowledge_id, event_type=event_type, payload={"user_id": user_id, "memory_id": str(row["id"]), "version_id": version_id, "knowledge_id": knowledge_id, "action": action, "reason_code": decision.reason_code, "occurred_at": evaluated_at})
    return {"status": "applied", "receipt_id": int(result.lastrowid), "action": action, "applied": bool(applied)}
