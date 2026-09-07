"""Add auditable trace identity to preference write receipts for D13D Safety."""

from __future__ import annotations

from alembic import op
from sqlalchemy import Column, String


revision = "20260906_add_preference_receipt_trace"
down_revision = "20260906_add_forget_topic_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("memory_version_receipts", Column("trace_id", String, nullable=True))


def downgrade() -> None:
    op.drop_column("memory_version_receipts", "trace_id")
