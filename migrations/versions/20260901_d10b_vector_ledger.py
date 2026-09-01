"""D10-B：Vector 代次、索引项与幂等回执账本。

SQLite 保存 Vector 派生索引的路由、精确删除结果与重建回执；真实向量仍在
可重建的 Vector Collection 中。每个作用域通过部分唯一索引最多有一个 serving
代次，因而重建失败不会替换原路由。
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Column, Integer, String, Text, text


revision = "20260901_d10b_vector_ledger"
down_revision = "20260831_add_source_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vector_index_generations",
        Column("scope_id", String, primary_key=True),
        Column("generation", String, primary_key=True),
        Column("collection_name", String, nullable=False, unique=True),
        Column("status", String, nullable=False),
        Column("schema_version", String, nullable=True),
        Column("source_snapshot_id", String, nullable=True),
        Column("source_watermark", Text, nullable=True),
        Column("record_digest", String, nullable=True),
        Column("record_count", Integer, nullable=False, server_default="0"),
        Column("is_serving", Integer, nullable=False, server_default="0"),
        Column("last_error", String, nullable=True),
        Column("created_at", String, nullable=True),
        Column("activated_at", String, nullable=True),
    )
    op.create_index(
        "uq_vector_generation_serving_scope",
        "vector_index_generations",
        ["scope_id"],
        unique=True,
        sqlite_where=text("is_serving = 1"),
    )
    op.create_table(
        "vector_index_entries",
        Column("scope_id", String, primary_key=True),
        Column("generation", String, primary_key=True),
        Column("user_id", String, primary_key=True),
        Column("memory_entry_id", Integer, primary_key=True),
        Column("version_id", String, primary_key=True),
        Column("is_active", Integer, nullable=False, server_default="1"),
    )
    op.create_index(
        "idx_vector_index_entries_active",
        "vector_index_entries",
        ["scope_id", "generation", "user_id", "is_active"],
    )
    op.create_table(
        "vector_index_receipts",
        Column("scope_id", String, primary_key=True),
        Column("user_id", String, primary_key=True),
        Column("operation", String, primary_key=True),
        Column("generation", String, primary_key=True),
        Column("idempotency_key", String, primary_key=True),
        Column("payload_hash", String, nullable=False),
        Column("result_json", Text, nullable=False),
        Column("created_at", String, nullable=False),
    )


def downgrade() -> None:
    bind = op.get_bind()
    generation_count = bind.execute(text("SELECT count(*) FROM vector_index_generations")).scalar_one()
    entry_count = bind.execute(text("SELECT count(*) FROM vector_index_entries")).scalar_one()
    receipt_count = bind.execute(text("SELECT count(*) FROM vector_index_receipts")).scalar_one()
    if generation_count or entry_count or receipt_count:
        raise RuntimeError("拒绝回退：D10-B Vector 账本已有数据，禁止静默删除")
    op.drop_table("vector_index_receipts")
    op.drop_index("idx_vector_index_entries_active", table_name="vector_index_entries")
    op.drop_table("vector_index_entries")
    op.drop_index("uq_vector_generation_serving_scope", table_name="vector_index_generations")
    op.drop_table("vector_index_generations")
