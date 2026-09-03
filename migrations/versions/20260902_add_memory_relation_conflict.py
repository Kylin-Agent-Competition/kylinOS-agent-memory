"""ADR-017: relation/conflict/lifecycle persistence and trusted knowledge mapping.

The migration is deliberately additive.  Legacy knowledge is marked
``legacy_unmapped`` instead of manufacturing an opaque knowledge id or evidence
tier from JSON content; it is therefore excluded from lifecycle automation.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import CheckConstraint, Column, Float, Integer, String, Text, text


revision = "20260902_add_memory_relation_conflict"
down_revision = "20260901_add_forget_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add first, then deterministically backfill legacy-safe values. SQLite cannot
    # add all required cross-column constraints in-place, so repository and DB
    # triggers provide the write gate after this one-time conversion.
    for column in (
        Column("knowledge_id", String, nullable=True), Column("row_revision", Integer, nullable=True),
        Column("knowledge_type", String, nullable=True), Column("conditions", Text, nullable=True),
        Column("lifecycle_eligibility", String, nullable=True), Column("memory_status", String, nullable=True),
        Column("memory_type", String, nullable=True), Column("evidence_tier", String, nullable=True),
        Column("last_accessed_at", String, nullable=True), Column("access_count", Integer, nullable=True),
    ):
        op.add_column("memory_entries", column)
    op.execute("UPDATE memory_entries SET row_revision = version WHERE row_revision IS NULL")
    op.execute("UPDATE memory_entries SET lifecycle_eligibility='legacy_unmapped', memory_status=CASE WHEN is_deleted=1 THEN 'removed' ELSE 'candidate' END, memory_type='short_term' WHERE entry_type='knowledge'")

    op.create_table(
        "memory_relation",
        Column("id", Integer, primary_key=True, autoincrement=True), Column("user_id", String, nullable=False),
        Column("relation_id", String, nullable=False), Column("relation_type", String, nullable=False),
        Column("left_endpoint_type", String, nullable=False), Column("left_endpoint_id", String, nullable=False),
        Column("right_endpoint_type", String, nullable=False), Column("right_endpoint_id", String, nullable=False),
        Column("is_primary", Integer, nullable=False, server_default="0"), Column("created_at", String, nullable=False),
        CheckConstraint("relation_type IN ('version','evidence','derived')", name="ck_memory_relation_type"),
        CheckConstraint("left_endpoint_type IN ('knowledge','source_event')", name="ck_memory_relation_left_type"),
        CheckConstraint("right_endpoint_type IN ('knowledge','source_event')", name="ck_memory_relation_right_type"),
        CheckConstraint("is_primary IN (0,1)", name="ck_memory_relation_primary"),
        CheckConstraint("relation_type = 'evidence' OR is_primary = 0", name="ck_memory_relation_primary_kind"),
        CheckConstraint("left_endpoint_id <> right_endpoint_id OR left_endpoint_type <> right_endpoint_type", name="ck_memory_relation_not_self"),
    )
    op.create_table(
        "memory_conflict",
        Column("id", Integer, primary_key=True, autoincrement=True), Column("user_id", String, nullable=False),
        Column("conflict_id", String, nullable=False), Column("conflict_type", String, nullable=False),
        Column("left_knowledge_id", String, nullable=False), Column("right_knowledge_id", String, nullable=False),
        Column("conflict_summary", Text, nullable=False), Column("involved_present", Integer, nullable=False),
        Column("resolution_status", String, nullable=False), Column("is_auto_resolvable", Integer, nullable=False, server_default="0"),
        Column("detected_at", String, nullable=False), Column("resolution_strategy", String), Column("resolution_confidence", Float),
        Column("resolved_at", String), Column("resolved_by", String), Column("winner_id", String),
        Column("decision_action", String), Column("reason_code", String), Column("created_at", String, nullable=False), Column("updated_at", String, nullable=False),
        CheckConstraint("left_knowledge_id <> right_knowledge_id", name="ck_memory_conflict_not_self"),
        CheckConstraint("conflict_type IN ('contradiction','temporal_inconsistency','source_conflict','preference_conflict','scope_ambiguity')", name="ck_memory_conflict_type"),
        CheckConstraint("resolution_status IN ('detected','analyzing','resolved_auto','resolved_manual','deferred','unresolvable')", name="ck_memory_conflict_status"),
        CheckConstraint("decision_action IS NULL OR decision_action IN ('keep_left','keep_right','coexist','defer','reject')", name="ck_memory_conflict_action"),
        CheckConstraint("is_auto_resolvable IN (0,1)", name="ck_memory_conflict_auto"), CheckConstraint("involved_present IN (0,1)", name="ck_memory_conflict_involved"),
        CheckConstraint("resolution_confidence IS NULL OR (resolution_confidence >= 0 AND resolution_confidence <= 1)", name="ck_memory_conflict_confidence"),
    )
    op.create_table(
        "memory_conflict_member",
        Column("id", Integer, primary_key=True, autoincrement=True), Column("user_id", String, nullable=False),
        Column("conflict_id", String, nullable=False), Column("knowledge_id", String, nullable=False),
        Column("ordinal", Integer, nullable=False), Column("role", String, nullable=False), Column("created_at", String, nullable=False),
        CheckConstraint("ordinal >= 0", name="ck_memory_conflict_member_ordinal"), CheckConstraint("role IN ('left','right','involved')", name="ck_memory_conflict_member_role"),
    )
    op.create_table(
        "memory_lifecycle_receipt",
        Column("id", Integer, primary_key=True, autoincrement=True), Column("user_id", String, nullable=False),
        Column("evaluation_id", String, nullable=False), Column("evaluation_fingerprint", String, nullable=False),
        Column("knowledge_id", String, nullable=False), Column("memory_entry_id", Integer, nullable=False), Column("evaluated_revision", Integer, nullable=False),
        Column("version_id", String, nullable=False), Column("policy_config_hash", String, nullable=False), Column("evaluated_at", String, nullable=False),
        Column("action", String, nullable=False), Column("reason_code", String, nullable=False), Column("target_memory_type", String), Column("target_memory_status", String),
        Column("applied", Integer, nullable=False), Column("created_at", String, nullable=False),
        CheckConstraint("evaluated_revision >= 1", name="ck_lifecycle_receipt_revision"), CheckConstraint("action IN ('promote','demote','expire','archive_request','hold','reject')", name="ck_lifecycle_receipt_action"), CheckConstraint("applied IN (0,1)", name="ck_lifecycle_receipt_applied"),
    )
    _indexes()
    # Direct SQL must not manufacture an eligible knowledge row or invalidate the
    # compatibility soft-delete projection.
    op.execute("""CREATE TRIGGER memory_entries_d8d_insert_gate BEFORE INSERT ON memory_entries
    WHEN NEW.version IS NULL OR NEW.version < 1 OR NEW.row_revision IS NULL OR NEW.row_revision < 1 OR
      (NEW.is_deleted=1 AND NEW.memory_status != 'removed') OR
      (NEW.entry_type != 'knowledge' AND (NEW.knowledge_id IS NOT NULL OR NEW.knowledge_type IS NOT NULL OR NEW.conditions IS NOT NULL OR NEW.lifecycle_eligibility IS NOT NULL OR NEW.memory_status IS NOT NULL OR NEW.memory_type IS NOT NULL OR NEW.evidence_tier IS NOT NULL OR NEW.last_accessed_at IS NOT NULL OR NEW.access_count IS NOT NULL)) OR
      (NEW.entry_type='knowledge' AND (NEW.knowledge_id IS NULL OR NEW.knowledge_type IS NULL OR NEW.memory_status IS NULL OR NEW.memory_type IS NULL OR NEW.lifecycle_eligibility NOT IN ('eligible','evidence_unmapped') OR (NEW.lifecycle_eligibility='eligible' AND NEW.evidence_tier IS NULL) OR (NEW.lifecycle_eligibility='evidence_unmapped' AND NEW.evidence_tier IS NOT NULL)))
    BEGIN SELECT RAISE(ABORT, 'd8d knowledge lifecycle gate'); END""")
    op.execute("""CREATE TRIGGER memory_entries_d8d_update_gate BEFORE UPDATE ON memory_entries
    WHEN NEW.version IS NULL OR NEW.version < 1 OR NEW.row_revision IS NULL OR NEW.row_revision < 1 OR
      (NEW.is_deleted=1 AND NEW.memory_status != 'removed') OR
      (NEW.entry_type != 'knowledge' AND (NEW.knowledge_id IS NOT NULL OR NEW.knowledge_type IS NOT NULL OR NEW.conditions IS NOT NULL OR NEW.lifecycle_eligibility IS NOT NULL OR NEW.memory_status IS NOT NULL OR NEW.memory_type IS NOT NULL OR NEW.evidence_tier IS NOT NULL OR NEW.last_accessed_at IS NOT NULL OR NEW.access_count IS NOT NULL)) OR
      (NEW.entry_type='knowledge' AND (
        (OLD.lifecycle_eligibility IN ('eligible','evidence_unmapped') AND NEW.lifecycle_eligibility NOT IN ('eligible','evidence_unmapped')) OR
        (OLD.lifecycle_eligibility IN ('eligible','evidence_unmapped') AND (NEW.knowledge_id IS NULL OR NEW.knowledge_type IS NULL OR NEW.memory_status IS NULL OR NEW.memory_type IS NULL)) OR
        (OLD.lifecycle_eligibility='legacy_unmapped' AND NEW.lifecycle_eligibility NOT IN ('legacy_unmapped','eligible')) OR
        (NEW.lifecycle_eligibility IN ('eligible','evidence_unmapped') AND (NEW.knowledge_id IS NULL OR NEW.knowledge_type IS NULL OR NEW.memory_status IS NULL OR NEW.memory_type IS NULL)) OR
        (NEW.lifecycle_eligibility='eligible' AND NEW.evidence_tier IS NULL) OR
        (NEW.lifecycle_eligibility='evidence_unmapped' AND NEW.evidence_tier IS NOT NULL)
      ))
    BEGIN SELECT RAISE(ABORT, 'd8d lifecycle update gate'); END""")


def _indexes() -> None:
    op.create_index("uq_memory_entries_user_knowledge", "memory_entries", ["user_id", "knowledge_id"], unique=True, sqlite_where=text("entry_type='knowledge' AND knowledge_id IS NOT NULL"))
    op.create_index("idx_memory_entries_user_status", "memory_entries", ["user_id", "memory_status"])
    op.create_index("idx_memory_entries_user_lifecycle_type", "memory_entries", ["user_id", "memory_type"])
    op.create_index("uq_memory_relation_user_relation", "memory_relation", ["user_id", "relation_id"], unique=True)
    op.create_index("idx_memory_relation_left", "memory_relation", ["user_id", "left_endpoint_type", "left_endpoint_id"])
    op.create_index("idx_memory_relation_right", "memory_relation", ["user_id", "right_endpoint_type", "right_endpoint_id"])
    op.create_index("uq_memory_relation_canonical_evidence", "memory_relation", ["user_id", "left_endpoint_id", "right_endpoint_id"], unique=True, sqlite_where=text("relation_type='evidence' AND left_endpoint_type='knowledge' AND right_endpoint_type='source_event'"))
    op.create_index("uq_memory_relation_primary_evidence", "memory_relation", ["user_id", "left_endpoint_id"], unique=True, sqlite_where=text("relation_type='evidence' AND left_endpoint_type='knowledge' AND right_endpoint_type='source_event' AND is_primary=1"))
    op.create_index("uq_memory_relation_version_successor", "memory_relation", ["user_id", "left_endpoint_id"], unique=True, sqlite_where=text("relation_type='version' AND left_endpoint_type='knowledge'"))
    op.create_index("uq_memory_conflict_user_conflict", "memory_conflict", ["user_id", "conflict_id"], unique=True)
    op.create_index("idx_memory_conflict_left", "memory_conflict", ["user_id", "left_knowledge_id"])
    op.create_index("idx_memory_conflict_right", "memory_conflict", ["user_id", "right_knowledge_id"])
    op.create_index("idx_memory_conflict_status", "memory_conflict", ["user_id", "resolution_status"])
    op.create_index("uq_memory_conflict_member_ordinal", "memory_conflict_member", ["user_id", "conflict_id", "ordinal"], unique=True)
    op.create_index("idx_memory_conflict_member_knowledge", "memory_conflict_member", ["user_id", "knowledge_id"])
    op.create_index("uq_lifecycle_receipt_evaluation", "memory_lifecycle_receipt", ["user_id", "evaluation_id"], unique=True)
    op.create_index("uq_lifecycle_archive_once", "memory_lifecycle_receipt", ["user_id", "knowledge_id", "version_id", "action", "reason_code"], unique=True, sqlite_where=text("action='archive_request'"))


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("memory_lifecycle_receipt", "memory_conflict_member", "memory_conflict", "memory_relation"):
        if bind.execute(text(f"SELECT count(*) FROM {table}")).scalar_one():
            raise RuntimeError("refuse D8D downgrade: persistence data exists")
    unsafe = bind.execute(text("SELECT count(*) FROM memory_entries WHERE knowledge_id IS NOT NULL OR evidence_tier IS NOT NULL OR lifecycle_eligibility='eligible'")).scalar_one()
    if unsafe:
        raise RuntimeError("refuse D8D downgrade: mapped knowledge exists")
    op.execute("DROP TRIGGER IF EXISTS memory_entries_d8d_update_gate")
    op.execute("DROP TRIGGER IF EXISTS memory_entries_d8d_insert_gate")
    for name, table in (("uq_lifecycle_archive_once", "memory_lifecycle_receipt"), ("uq_lifecycle_receipt_evaluation", "memory_lifecycle_receipt"), ("idx_memory_conflict_member_knowledge", "memory_conflict_member"), ("uq_memory_conflict_member_ordinal", "memory_conflict_member"), ("idx_memory_conflict_status", "memory_conflict"), ("idx_memory_conflict_right", "memory_conflict"), ("idx_memory_conflict_left", "memory_conflict"), ("uq_memory_conflict_user_conflict", "memory_conflict"), ("uq_memory_relation_version_successor", "memory_relation"), ("uq_memory_relation_primary_evidence", "memory_relation"), ("uq_memory_relation_canonical_evidence", "memory_relation"), ("idx_memory_relation_right", "memory_relation"), ("idx_memory_relation_left", "memory_relation"), ("uq_memory_relation_user_relation", "memory_relation"), ("idx_memory_entries_user_lifecycle_type", "memory_entries"), ("idx_memory_entries_user_status", "memory_entries"), ("uq_memory_entries_user_knowledge", "memory_entries")):
        op.drop_index(name, table_name=table)
    for table in ("memory_lifecycle_receipt", "memory_conflict_member", "memory_conflict", "memory_relation"):
        op.drop_table(table)
    for column in ("access_count", "last_accessed_at", "evidence_tier", "memory_type", "memory_status", "lifecycle_eligibility", "conditions", "knowledge_type", "row_revision", "knowledge_id"):
        op.drop_column("memory_entries", column)
