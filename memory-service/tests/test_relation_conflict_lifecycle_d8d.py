"""D8D SQLite persistence contracts: isolation, provenance, conflict and lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from db import repositories as repo
from db.engine import create_db_engine, init_schema
from db.schema import outbox
from service.conflict_resolution_policy import EvidenceTier
from service.lifecycle_policy import PolicyConfig
from service.lifecycle_worker import evaluate_lifecycle


def _event(conn, *, user_id: str, event_id: str, source_type: str = "manual_config", status: str = "success") -> None:
    now = datetime.now(timezone.utc).isoformat()
    repo.insert_source_event(
        conn, user_id=user_id, event_id=event_id, actor_id="host", session_id=f"s-{event_id}",
        turn_id=None, tool_call_id=None, source_type=source_type, event_type="user_message",
        schema_version="1", trace_id=None, source_reference="ref", raw_payload_ref=None,
        content_summary=None, idempotency_key=f"idem-{event_id}", consent_scope="memory_only",
        source_business_status=status, sensitivity="none", is_sensitive_matched=0,
        should_ignore=0, payload_security_checked=1, memory_type=None, requires_embedding=0,
        has_structured_payload=1, language_tag="zh-CN", occurred_at=now, captured_at=now,
        content_fingerprint=None, dedup_group=None, duplicate_of=None,
        admission_decision="allow_extraction", admission_reason_code="accepted",
        processing_status="stored", created_at=now, updated_at=now,
    )


@pytest.fixture()
def conn(tmp_path):
    engine = create_db_engine(str(tmp_path / "d8d.db"))
    init_schema(engine, fts=False)
    with engine.begin() as connection:
        yield connection


def _knowledge(conn, *, user_id: str = "u1", knowledge_id: str = "k1", event_id: str = "e1"):
    _event(conn, user_id=user_id, event_id=event_id)
    return repo.insert_knowledge_entry(
        conn, user_id=user_id, knowledge_id=knowledge_id, knowledge_type="fact",
        source_event_id=event_id, content={"safe": "metadata"}, confidence=0.9,
    )


def test_knowledge_provenance_relation_and_cross_user_scoping(conn):
    created = _knowledge(conn)
    assert created["memory_id"] == "1"
    assert created["version_id"] == "v1"
    assert created["evidence_tier"] == "user_explicit_config_latest"
    edges = repo.list_relations(conn, user_id="u1", knowledge_id="k1")
    assert len(edges) == 1 and edges[0]["is_primary"] == 1
    assert repo.get_relation_by_id(conn, user_id="u2", relation_id=edges[0]["relation_id"]) is None
    with pytest.raises(ValueError, match="not owned"):
        repo.insert_relation(conn, user_id="u2", relation_id="cross", relation_type="derived", left_endpoint_type="knowledge", left_endpoint_id="k1", right_endpoint_type="knowledge", right_endpoint_id="k1b")
    emitted = conn.execute(
        select(outbox.c.event_type, outbox.c.payload).where(
            outbox.c.aggregate_id == "k1"
        )
    ).mappings().all()
    assert len(emitted) == 1
    assert emitted[0]["event_type"] == repo.EVENT_MEMORY_RELATION_CHANGED
    assert "metadata" not in emitted[0]["payload"]


def test_failed_tool_only_writes_evidence_unmapped_failure_experience(conn):
    _event(conn, user_id="u1", event_id="failed", source_type="tool_result", status="failed")
    with pytest.raises(ValueError, match="failure_experience"):
        repo.insert_knowledge_entry(conn, user_id="u1", knowledge_id="bad", knowledge_type="fact", source_event_id="failed", content={}, confidence=0.5)
    item = repo.insert_knowledge_entry(conn, user_id="u1", knowledge_id="failure", knowledge_type="failure_experience", source_event_id="failed", content={}, confidence=0.5)
    assert item["evidence_tier"] is None
    assert item["lifecycle_eligibility"] == "evidence_unmapped"
    assert repo.get_lifecycle_memory(conn, user_id="u1", knowledge_id="failure") is None


def test_conflict_is_sanitized_member_round_trip_and_unresolved_is_fail_closed(conn):
    _knowledge(conn, knowledge_id="left", event_id="e-left")
    _knowledge(conn, knowledge_id="right", event_id="e-right")
    _knowledge(conn, knowledge_id="extra", event_id="e-extra")
    repo.insert_conflict(conn, user_id="u1", conflict_id="c1", conflict_type="contradiction", left_knowledge_id="left", right_knowledge_id="right", resolution_status="detected", is_auto_resolvable=False, detected_at=datetime.now(timezone.utc).isoformat(), involved_knowledge_ids=["extra", "extra"])
    conflict = repo.get_conflict_by_id(conn, user_id="u1", conflict_id="c1")
    assert conflict and conflict["conflict_summary"] == "conflict:contradiction"
    assert "user original secret" not in str(conflict)
    assert repo.resolve_conflict_state(conn, user_id="u1", knowledge_id="left") == "unresolved"
    assert repo.get_conflict_by_id(conn, user_id="u2", conflict_id="c1") is None
    assert repo.update_conflict_resolution(conn, user_id="u1", conflict_id="c1", resolution_status="resolved_auto", decision_action="keep_left", winner_id="left", reason_code="evidence_tier_priority", resolved_at=datetime.now(timezone.utc).isoformat(), resolved_by="policy") == 1
    assert repo.resolve_conflict_state(conn, user_id="u1", knowledge_id="left") == "resolved"


def test_lifecycle_expire_keeps_index_version_and_replay_is_idempotent(conn):
    _knowledge(conn)
    row = repo.get_lifecycle_memory(conn, user_id="u1", knowledge_id="k1")
    assert row is not None
    assert repo.update_lifecycle_memory(conn, user_id="u1", knowledge_id="k1", expected_row_revision=row["row_revision"], memory_status="active") == 1
    config = PolicyConfig(
        promote_min_confidence=1.0, promote_min_access_count=99, promote_min_age=timedelta(days=999),
        promote_required_evidence_tier=EvidenceTier.USER_CONFIRMED, demote_inactivity_period=timedelta(days=999),
        demote_max_access_count=0, demote_max_confidence=0.0, expire_after_age=timedelta(0), archive_after_expired=timedelta(days=1),
    )
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    result = evaluate_lifecycle(conn, user_id="u1", knowledge_id="k1", evaluation_id="eval-1", policy_config=config, now=now)
    assert result["action"] == "expire" and result["applied"] is True
    current = repo.get_lifecycle_memory(conn, user_id="u1", knowledge_id="k1")
    assert current["memory_status"] == "expired"
    assert current["version"] == 1  # lifecycle CAS must not change vector/retrieval identity
    replay = evaluate_lifecycle(conn, user_id="u1", knowledge_id="k1", evaluation_id="eval-1", policy_config=config, now=now)
    assert replay["status"] == "replayed"
    with pytest.raises(ValueError, match="immutable input"):
        evaluate_lifecycle(conn, user_id="u1", knowledge_id="k1", evaluation_id="eval-1", policy_config=config, now=now + timedelta(seconds=1))


def test_forget_uses_row_revision_after_lifecycle_mutation(conn):
    created = _knowledge(conn)
    row = repo.get_lifecycle_memory(conn, user_id="u1", knowledge_id="k1")
    assert row is not None
    assert repo.update_lifecycle_memory(
        conn,
        user_id="u1",
        knowledge_id="k1",
        expected_row_revision=row["row_revision"],
        memory_status="active",
    ) == 1
    executed, version_ids = repo.soft_delete_resolved_targets(
        conn,
        user_id="u1",
        target_type="knowledge",
        resolved_target_ids=[created["memory_id"]],
        forget_plan_id="plan-d8d-row-revision",
    )
    assert (executed, version_ids) == (1, [])
    deleted = repo._get_memory_entry(conn, entry_id=int(created["memory_id"]), user_id="u1")
    assert deleted is not None and deleted["is_deleted"] == 1


def test_archive_rescan_replays_first_disposition_without_duplicate_outbox(conn):
    _knowledge(conn)
    row = repo.get_lifecycle_memory(conn, user_id="u1", knowledge_id="k1")
    assert row is not None
    assert repo.update_lifecycle_memory(
        conn,
        user_id="u1",
        knowledge_id="k1",
        expected_row_revision=row["row_revision"],
        memory_status="expired",
    ) == 1
    config = PolicyConfig(
        promote_min_confidence=1.0, promote_min_access_count=99, promote_min_age=timedelta(days=999),
        promote_required_evidence_tier=EvidenceTier.USER_CONFIRMED, demote_inactivity_period=timedelta(days=999),
        demote_max_access_count=0, demote_max_confidence=0.0, expire_after_age=timedelta(days=999),
        archive_after_expired=timedelta(0),
    )
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    first = evaluate_lifecycle(conn, user_id="u1", knowledge_id="k1", evaluation_id="archive-1", policy_config=config, now=now)
    second = evaluate_lifecycle(conn, user_id="u1", knowledge_id="k1", evaluation_id="archive-2", policy_config=config, now=now)
    assert first["action"] == "archive_request"
    assert second["status"] == "archive_replayed"
    archive_events = conn.execute(
        select(func.count()).select_from(outbox).where(
            outbox.c.event_type == repo.EVENT_MEMORY_LIFECYCLE_ARCHIVE_REQUESTED
        )
    ).scalar_one()
    assert archive_events == 1
