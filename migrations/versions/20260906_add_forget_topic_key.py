"""Add the structured topic key used by D13D Forget topic execution."""

from __future__ import annotations

from alembic import op
from sqlalchemy import Column, String, text


revision = "20260906_add_forget_topic_key"
down_revision = "20260902_add_memory_relation_conflict"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("memory_entries", Column("topic_key", String, nullable=True))
    op.create_index(
        "idx_memory_entries_user_topic_active",
        "memory_entries",
        ["user_id", "topic_key"],
        sqlite_where=text("entry_type='knowledge' AND is_deleted=0 AND topic_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_memory_entries_user_topic_active", table_name="memory_entries")
    op.drop_column("memory_entries", "topic_key")
