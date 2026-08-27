"""20260826_add_trace_id — ADR-011：turns/memory_entries 新增 nullable trace_id/host_turn_id 列

契约来源：docs/adr/011-trace-id-columns.md（D 决策 + Reviewer E 签署 2026-08-27）
  - turns 增 `trace_id VARCHAR NULL` + `host_turn_id VARCHAR NULL`（部分唯一索引，
    ADR-010 Upsert 匹配键 (session_id, host_turn_id)）
  - memory_entries 增 `trace_id VARCHAR NULL`
  - outbox 不改表：trace_id 写入 payload JSON（checklist 5.4）
  - 命名：YYYYMMDD_<description>.py（ADR-007）；revision 独立，down_revision=001
  - downgrade：遵守「禁止删除列」红线（ADR-007）——表重建/重命名回滚，
    不得 ALTER DROP COLUMN

downgrade 细节（ADR-011 决策节）：
  1. 新建同构旧 schema 表（按 001 定义，不含 trace_id / host_turn_id）
  2. INSERT INTO 新表（显式列清单，丢弃新增列）
  3. DROP TABLE 旧表（其附加触发器随之移除）
  4. ALTER TABLE 新表 RENAME TO 旧表名 + 重建冻结索引
  5. memory_entries 重建后重建 4 个 FTS5 同步触发器并回填 memory_fts

SQLite 说明：迁移执行时 FK 默认 OFF（env.py 未开启 foreign_keys），
重建被引用表（turns）时 DROP 旧表不触发 FK 检查；显式 PRAGMA 保证不依赖连接默认值。
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy import CheckConstraint

# ── revision 元数据（ADR-007 / ADR-011：独立 revision，链 001 → 20260826_add_trace_id） ──
revision = "20260826_add_trace_id"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增 nullable 列 + 部分唯一索引（向后兼容，既有行不受影响）。"""
    # 每条 ALTER 单一列（SQLite 限制；nullable 新增列标准支持）
    op.add_column("turns", Column("trace_id", String, nullable=True))
    op.add_column("turns", Column("host_turn_id", String, nullable=True))
    op.add_column("memory_entries", Column("trace_id", String, nullable=True))

    # 部分唯一索引：ADR-010 Upsert 匹配键（SQLite 多 NULL 允许，非空才唯一）
    op.create_index(
        "idx_turns_host_turn_id",
        "turns",
        ["session_id", "host_turn_id"],
        unique=True,
        sqlite_where=text("host_turn_id IS NOT NULL"),
    )


def downgrade() -> None:
    """表重建回滚（禁 DROP COLUMN，ADR-007 红线）。

    顺序：先 turns（父表被 memory_entries FK 引用，重建其本身不破坏引用名），
    再 memory_entries（含 FTS 触发器重建 + 回填）。
    """
    op.execute("PRAGMA foreign_keys=OFF")

    # ── 1. turns 重建（去掉 trace_id / host_turn_id） ──
    op.create_table(
        "turns_new",
        Column("id", Integer, primary_key=True),
        Column("session_id", String, ForeignKey("conversations.session_id"), nullable=False),
        Column("turn_index", Integer, nullable=False),
        Column("original_user_text", Text, nullable=False),
        Column("model_request", Text, nullable=True),
        Column("model_response", Text, nullable=True),
        Column("is_end", Integer, nullable=False, server_default="0"),
        Column("created_at", String, nullable=False),
    )
    op.execute(
        """
        INSERT INTO turns_new
            (id, session_id, turn_index, original_user_text,
             model_request, model_response, is_end, created_at)
        SELECT id, session_id, turn_index, original_user_text,
               model_request, model_response, is_end, created_at
        FROM turns
        """
    )
    op.drop_table("turns")
    op.rename_table("turns_new", "turns")
    op.create_index("idx_turns_session", "turns", ["session_id", "turn_index"])

    # ── 2. memory_entries 重建（去掉 trace_id；触发器随 DROP 移除） ──
    op.create_table(
        "memory_entries_new",
        Column("id", Integer, primary_key=True),
        Column("user_id", String, nullable=False),
        Column("entry_type", String, nullable=False),
        Column("content", Text, nullable=False),
        Column("source_turn_id", Integer, ForeignKey("turns.id"), nullable=True),
        Column("confidence", Float, nullable=False, server_default="0.0"),
        Column("version", Integer, nullable=False, server_default="1"),
        Column("is_deleted", Integer, nullable=False, server_default="0"),
        Column("created_at", String, nullable=False),
        Column("updated_at", String, nullable=False),
        CheckConstraint(
            "entry_type IN ('preference','knowledge','tool_result','behavior')",
            name="ck_memory_entries_entry_type",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_entries_confidence"),
    )
    op.execute(
        """
        INSERT INTO memory_entries_new
            (id, user_id, entry_type, content, source_turn_id,
             confidence, version, is_deleted, created_at, updated_at)
        SELECT id, user_id, entry_type, content, source_turn_id,
               confidence, version, is_deleted, created_at, updated_at
        FROM memory_entries
        """
    )
    op.drop_table("memory_entries")
    op.rename_table("memory_entries_new", "memory_entries")
    op.create_index("idx_memory_user_type", "memory_entries", ["user_id", "entry_type"])
    op.create_index("idx_memory_deleted", "memory_entries", ["is_deleted"])

    # ── 3. FTS5 触发器重建 + 回填（先清空再按当前行重灌，保证 FTS 与正文一致） ──
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
    op.execute("DELETE FROM memory_fts")
    op.execute(
        """
        INSERT INTO memory_fts(rowid, content, entry_type, user_id)
        SELECT id, content, entry_type, user_id FROM memory_entries WHERE is_deleted = 0
        """
    )

    op.execute("PRAGMA foreign_keys=ON")
