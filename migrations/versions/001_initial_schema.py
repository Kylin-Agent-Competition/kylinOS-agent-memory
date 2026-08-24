"""001_initial_schema — D4D 基线迁移（ADR-007 命名：001_initial_schema.py）

契约来源：deliverables/D4_DB_INITIAL_REQUIREMENTS_20260817.md §FR-DB-001
  5 张核心表 + 4 冻结索引 + 1 辅助索引 + FTS5 memory_fts + 触发器
  列名/类型/约束逐字段对齐冻结文档；idempotency_cache 为复合 PK（ADR-006）。
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import CheckConstraint, Column, Float, ForeignKey, Index, Integer, String, Text, text

# ── revision 元数据（ADR-007：基线固定 001_initial_schema.py） ──
revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── conversations ──
    op.create_table(
        "conversations",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String, nullable=False),
        Column("session_id", String, nullable=False, unique=True),
        Column("started_at", String, nullable=False),  # ISO8601 UTC
        Column("ended_at", String, nullable=True),
        sqlite_autoincrement=True,
    )

    # ── turns ──
    op.create_table(
        "turns",
        Column("id", Integer, primary_key=True),
        Column("session_id", String, ForeignKey("conversations.session_id"), nullable=False),
        Column("turn_index", Integer, nullable=False),
        Column("original_user_text", Text, nullable=False),
        Column("model_request", Text, nullable=True),
        Column("model_response", Text, nullable=True),
        Column("is_end", Integer, nullable=False, server_default="0"),
        Column("created_at", String, nullable=False),
    )

    # ── memory_entries ──
    op.create_table(
        "memory_entries",
        Column("id", Integer, primary_key=True),
        Column("user_id", String, nullable=False),
        Column("entry_type", String, nullable=False),
        Column("content", Text, nullable=False),  # JSON 文本
        Column("source_turn_id", Integer, ForeignKey("turns.id"), nullable=True),
        Column("confidence", Float, nullable=False, server_default="0.0"),  # ∈ [0,1]
        Column("version", Integer, nullable=False, server_default="1"),  # 乐观锁
        Column("is_deleted", Integer, nullable=False, server_default="0"),
        Column("created_at", String, nullable=False),
        Column("updated_at", String, nullable=False),
        CheckConstraint("entry_type IN ('preference','knowledge','tool_result','behavior')", name="ck_memory_entries_entry_type"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_entries_confidence"),
    )

    # ── outbox ──
    op.create_table(
        "outbox",
        Column("id", Integer, primary_key=True),
        Column("aggregate_type", String, nullable=False),
        Column("aggregate_id", String, nullable=False),
        Column("event_type", String, nullable=False),
        Column("payload", Text, nullable=False),  # JSON 文本
        Column("attempts", Integer, nullable=False, server_default="0"),
        Column("next_retry_at", String, nullable=True),  # ISO8601 UTC
        Column("last_error", Text, nullable=True),
        Column("created_at", String, nullable=False),
        CheckConstraint("aggregate_type IN ('turn','memory')", name="ck_outbox_aggregate_type"),
    )

    # ── idempotency_cache（复合 PK，ADR-006 冻结 §2.2.5） ──
    op.create_table(
        "idempotency_cache",
        Column("user_id", String, primary_key=True),
        Column("session_id", String, primary_key=True),
        Column("idempotency_key", String, primary_key=True),
        Column("response", Text, nullable=False),  # JSON 文本（缓存响应）
        Column("created_at", String, nullable=False),
        Column("expires_at", String, nullable=False),  # TTL=24h
    )

    # ── 索引（4 冻结 + 1 辅助，冻结文档 §2.3） ──
    op.create_index("idx_turns_session", "turns", ["session_id", "turn_index"])
    op.create_index("idx_memory_user_type", "memory_entries", ["user_id", "entry_type"])
    op.create_index("idx_memory_deleted", "memory_entries", ["is_deleted"])
    op.create_index(
        "idx_outbox_pending",
        "outbox",
        ["next_retry_at"],
        sqlite_where=text("attempts <= 3"),  # 与 outbox.max_retries=3 配套
    )
    op.create_index("idx_idempotency_expires", "idempotency_cache", ["expires_at"])

    # ── FTS5（冻结文档 §2.4）+ 同步触发器 ──
    op.execute(
        "CREATE VIRTUAL TABLE memory_fts USING fts5("
        "content, entry_type, user_id UNINDEXED, tokenize='unicode61')"
    )
    # 幂等契约（与 db/schema.py FTS_TRIGGERS_DDL 单一真相一致，详见 TD 关联）：
    # `IF NOT EXISTS` 保证重复执行建库/迁移脚本时不冲突（alembic 按 revision id
    # 记录，不校验内容，修改安全且不改变冻结语义）。
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS memory_fts_ai AFTER INSERT ON memory_entries BEGIN
            INSERT INTO memory_fts(rowid, content, entry_type, user_id)
            VALUES (new.id, new.content, new.entry_type, new.user_id);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS memory_fts_au_content AFTER UPDATE ON memory_entries
        WHEN old.is_deleted = 0 AND new.is_deleted = 0
             AND (old.content IS NOT new.content
                  OR old.entry_type IS NOT new.entry_type
                  OR old.user_id IS NOT new.user_id)
        BEGIN
            DELETE FROM memory_fts WHERE rowid = old.id;
            INSERT INTO memory_fts(rowid, content, entry_type, user_id)
            VALUES (new.id, new.content, new.entry_type, new.user_id);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS memory_fts_au_deleted AFTER UPDATE ON memory_entries
        WHEN old.is_deleted = 0 AND new.is_deleted = 1
        BEGIN
            DELETE FROM memory_fts WHERE rowid = old.id;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS memory_fts_ad AFTER DELETE ON memory_entries BEGIN
            DELETE FROM memory_fts WHERE rowid = old.id;
        END
        """
    )


def downgrade() -> None:
    """完整回滚（每个迁移必须有 downgrade，FR-DB-002）。"""
    op.execute("DROP TRIGGER IF EXISTS memory_fts_ai")
    op.execute("DROP TRIGGER IF EXISTS memory_fts_au_content")
    op.execute("DROP TRIGGER IF EXISTS memory_fts_au_deleted")
    op.execute("DROP TRIGGER IF EXISTS memory_fts_ad")
    op.execute("DROP TABLE IF EXISTS memory_fts")
    op.drop_index("idx_idempotency_expires", table_name="idempotency_cache")
    op.drop_index("idx_outbox_pending", table_name="outbox")
    op.drop_index("idx_memory_deleted", table_name="memory_entries")
    op.drop_index("idx_memory_user_type", table_name="memory_entries")
    op.drop_index("idx_turns_session", table_name="turns")
    op.drop_table("idempotency_cache")
    op.drop_table("outbox")
    op.drop_table("memory_entries")
    op.drop_table("turns")
    op.drop_table("conversations")
