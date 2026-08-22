"""schema.py — D4D SQLAlchemy 2.0 Core 表定义（FRZ-DB-001，DDL 逐字段对齐）

契约来源：deliverables/D4_DB_INITIAL_REQUIREMENTS_20260817.md §FR-DB-001
  - 5 张核心表 + 4 冻结索引 + 1 辅助索引 + FTS5 memory_fts
  - 列名/类型/约束不得偏离冻结文档
  - idempotency_cache 使用复合 PK (user_id, session_id, idempotency_key)（ADR-006）
  - FTS5 触发器（INSERT/UPDATE/DELETE）同步 memory_entries ↔ memory_fts

本模块同时被以下两处引用，保证单一真相：
  - migrations/env.py 的 target_metadata（Alembic autogenerate/对比）
  - db/engine.py 的 create_all（测试/开发快速建库）
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

# 所有迁移/建表共享同一 metadata（Alembic env.py 也引用它）
metadata = MetaData()

conversations = Table(
    "conversations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, nullable=False),
    Column("session_id", String, nullable=False, unique=True),
    Column("started_at", String, nullable=False),  # ISO8601 UTC
    Column("ended_at", String, nullable=True),
    sqlite_autoincrement=True,
)

turns = Table(
    "turns",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("session_id", String, ForeignKey("conversations.session_id"), nullable=False),
    Column("turn_index", Integer, nullable=False),
    Column("original_user_text", Text, nullable=False),
    Column("model_request", Text, nullable=True),
    Column("model_response", Text, nullable=True),
    Column("is_end", Integer, nullable=False, default=0),
    Column("created_at", String, nullable=False),  # ISO8601 UTC
)

memory_entries = Table(
    "memory_entries",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", String, nullable=False),
    Column(
        "entry_type",
        String,
        nullable=False,
    ),
    Column("content", Text, nullable=False),  # JSON 文本
    Column("source_turn_id", Integer, ForeignKey("turns.id"), nullable=True),
    Column("confidence", Float, nullable=False, default=0.0),  # ∈ [0,1]
    Column("version", Integer, nullable=False, default=1),  # 乐观锁
    Column("is_deleted", Integer, nullable=False, default=0),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    CheckConstraint("entry_type IN ('preference','knowledge','tool_result','behavior')", name="ck_memory_entries_entry_type"),
    CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_entries_confidence"),
)

outbox = Table(
    "outbox",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("aggregate_type", String, nullable=False),
    Column("aggregate_id", String, nullable=False),
    Column("event_type", String, nullable=False),
    Column("payload", Text, nullable=False),  # JSON 文本
    Column("attempts", Integer, nullable=False, default=0),
    Column("next_retry_at", String, nullable=True),  # ISO8601 UTC
    Column("last_error", Text, nullable=True),
    Column("created_at", String, nullable=False),
    CheckConstraint("aggregate_type IN ('turn','memory')", name="ck_outbox_aggregate_type"),
)

idempotency_cache = Table(
    "idempotency_cache",
    metadata,
    # 复合主键（ADR-006，冻结 §2.2.5 回写）
    Column("user_id", String, primary_key=True),
    Column("session_id", String, primary_key=True),
    Column("idempotency_key", String, primary_key=True),
    Column("response", Text, nullable=False),  # JSON 文本（缓存响应）
    Column("created_at", String, nullable=False),
    Column("expires_at", String, nullable=False),  # TTL=24h
)

# ── 索引（4 冻结 + 1 辅助，冻结文档 §2.3） ──
idx_turns_session = Index("idx_turns_session", turns.c.session_id, turns.c.turn_index)
idx_memory_user_type = Index("idx_memory_user_type", memory_entries.c.user_id, memory_entries.c.entry_type)
idx_memory_deleted = Index("idx_memory_deleted", memory_entries.c.is_deleted)
idx_outbox_pending = Index(
    "idx_outbox_pending",
    outbox.c.next_retry_at,
    sqlite_where=outbox.c.attempts <= 3,  # 与 outbox.max_retries=3 配套（需求 §2.2）
)
idx_idempotency_expires = Index("idx_idempotency_expires", idempotency_cache.c.expires_at)

# ── FTS5（冻结文档 §2.4） ──
FTS5_DDL = (
    "CREATE VIRTUAL TABLE memory_fts USING fts5("
    "content, entry_type, user_id UNINDEXED, tokenize='unicode61')"
)

# FTS 同步触发器（软删除语义：is_deleted 0→1 时自动从 FTS5 删除对应记录）
# 说明：SQLite 触发器内 FTS5 'delete' 命令与 JSON 中文内容不兼容（实测 SQL logic
# error，SQLite 3.37），统一改用 `DELETE FROM memory_fts WHERE rowid = old.id`
# （实验验证方式 B/C 可用）。UPDATE 场景拆分为两个 WHEN 子句触发器。
# 幂等契约（TD 关联：init_schema() 二次调用）：全部使用 `IF NOT EXISTS`，
# 保证同一触发器在重复调用 init_schema()/create_all 时不冲突（SQLite 原生支持，
# 不改变冻结语义）。engine.py::init_schema() 依赖此契约。
FTS_TRIGGERS_DDL = [
    # INSERT：新记录入 FTS
    """
    CREATE TRIGGER IF NOT EXISTS memory_fts_ai AFTER INSERT ON memory_entries BEGIN
        INSERT INTO memory_fts(rowid, content, entry_type, user_id)
        VALUES (new.id, new.content, new.entry_type, new.user_id);
    END
    """,
    # UPDATE（内容变化，非软删除）：先删旧再插新
    """
    CREATE TRIGGER IF NOT EXISTS memory_fts_au_content AFTER UPDATE ON memory_entries
    WHEN old.is_deleted = 0 AND new.is_deleted = 0 AND old.content IS NOT new.content
    BEGIN
        DELETE FROM memory_fts WHERE rowid = old.id;
        INSERT INTO memory_fts(rowid, content, entry_type, user_id)
        VALUES (new.id, new.content, new.entry_type, new.user_id);
    END
    """,
    # UPDATE（软删除 0→1）：只删 FTS，不插回（MATCH 不再命中，冻结文档 §2.4）
    """
    CREATE TRIGGER IF NOT EXISTS memory_fts_au_deleted AFTER UPDATE ON memory_entries
    WHEN old.is_deleted = 0 AND new.is_deleted = 1
    BEGIN
        DELETE FROM memory_fts WHERE rowid = old.id;
    END
    """,
    # DELETE：物理删除同步删 FTS
    """
    CREATE TRIGGER IF NOT EXISTS memory_fts_ad AFTER DELETE ON memory_entries BEGIN
        DELETE FROM memory_fts WHERE rowid = old.id;
    END
    """,
]
