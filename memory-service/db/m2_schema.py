"""M2 Main→Data durable import registry schema.

The existing ``idempotency_cache`` is a 24h request cache and is intentionally
not reused here.  These tables retain the first successful import acceptance
snapshot for as long as the production identity/audit record is retained.

This module attaches the M2 tables to ``db.schema.metadata`` without changing
legacy table definitions.  Production creation is still owned by Alembic; the
shared metadata is used by tests/development ``init_schema`` and autogenerate.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, Integer, String, Table, Text

from db.schema import metadata


main_to_data_import_registry = Table(
    "main_to_data_import_registry",
    metadata,
    Column("user_id", String, primary_key=True),
    Column("idempotency_key", String, primary_key=True),
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
    CheckConstraint("accepted_version >= 1", name="ck_m2_import_accepted_version"),
    CheckConstraint("result_status = 'accepted'", name="ck_m2_import_result_status"),
    CheckConstraint(
        "accepted_memory_status IN ('active','superseded','deprecated','expired','removed','candidate')",
        name="ck_m2_import_accepted_status",
    ),
)


main_to_data_manifest_registry = Table(
    "main_to_data_manifest_registry",
    metadata,
    Column("user_id", String, primary_key=True),
    Column("source_manifest_sha256", String, primary_key=True),
    Column("data_record_id", String, primary_key=True),
    Column("canonical_request_sha256", String, nullable=False),
    Column("idempotency_key", String, nullable=False),
    Column("receipt_json", Text, nullable=False),
    Column("created_at", String, nullable=False),
)
