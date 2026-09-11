"""Add durable Main→Data M2 import identity registries.

The tables deliberately have no expires_at/TTL column.  They are production
identity/audit registries, not the existing 24h request idempotency cache.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import CheckConstraint, Column, Integer, PrimaryKeyConstraint, String, Text


revision = "20260911_main_to_data_m2_registry"
down_revision = "20260906_add_preference_receipt_trace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "main_to_data_import_registry",
        Column("user_id", String, nullable=False),
        Column("idempotency_key", String, nullable=False),
        Column("canonical_request_sha256", String, nullable=False),
        Column("data_record_id", String, nullable=False),
        Column("knowledge_id", String, nullable=False),
        Column("memory_id", String, nullable=False),
        Column("accepted_version", Integer, nullable=False),
        Column("accepted_version_id", String, nullable=False),
        Column("accepted_memory_status", String, nullable=False),
        Column("source_event_id", String, nullable=False),
        Column("result_status", String, nullable=False),
        Column("receipt_json", Text, nullable=False),
        Column("created_at", String, nullable=False),
        PrimaryKeyConstraint("user_id", "idempotency_key", name="pk_m2_import_registry"),
        CheckConstraint("accepted_version >= 1", name="ck_m2_import_accepted_version"),
        CheckConstraint("result_status = 'accepted'", name="ck_m2_import_result_status"),
        CheckConstraint(
            "accepted_memory_status IN ('active','superseded','deprecated','expired','removed','candidate')",
            name="ck_m2_import_accepted_status",
        ),
    )
    op.create_table(
        "main_to_data_manifest_registry",
        Column("user_id", String, nullable=False),
        Column("source_manifest_sha256", String, nullable=False),
        Column("data_record_id", String, nullable=False),
        Column("canonical_request_sha256", String, nullable=False),
        Column("idempotency_key", String, nullable=False),
        Column("receipt_json", Text, nullable=False),
        Column("created_at", String, nullable=False),
        PrimaryKeyConstraint(
            "user_id",
            "source_manifest_sha256",
            "data_record_id",
            name="pk_m2_manifest_registry",
        ),
    )


def downgrade() -> None:
    op.drop_table("main_to_data_manifest_registry")
    op.drop_table("main_to_data_import_registry")
