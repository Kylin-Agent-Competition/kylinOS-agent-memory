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
    Column("is_end", Integer, nullable=False, server_default="0"),
    Column("created_at", String, nullable=False),  # ISO8601 UTC
    # ADR-011（2026-08-27 签署）：nullable 追踪列，trace_id 为 IPC envelope 唯一真源；
    # host_turn_id 为 ADR-010 Upsert 匹配键（部分唯一索引见下）
    Column("trace_id", String, nullable=True),
    Column("host_turn_id", String, nullable=True),
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
    Column("confidence", Float, nullable=False, server_default="0.0"),  # ∈ [0,1]
    Column("version", Integer, nullable=False, server_default="1"),  # 乐观锁
    Column("is_deleted", Integer, nullable=False, server_default="0"),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    # ADR-011：nullable 追踪列（trace_id 来自 IPC envelope，非正文）
    Column("trace_id", String, nullable=True),
    CheckConstraint("entry_type IN ('preference','knowledge','tool_result','behavior')", name="ck_memory_entries_entry_type"),
    CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_entries_confidence"),
)

# D7D：稳定记忆项与不可变版本历史。`memory_entries` 保持既有通用记忆表职责；
# 偏好版本链使用独立表，避免以 UPDATE 覆盖历史正文。一个 item 对应一个
# (user_id, preference_key, preference_scope) 链，版本表的部分唯一索引保证只有一个
# current 真值，供 D7B 的 current-version 过滤安全消费。
memory_items = Table(
    "memory_items",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, nullable=False),
    Column("preference_key", String, nullable=False),
    Column("preference_scope", String, nullable=False),
    # current_version_id 由同一 UoW 在新版本插入后更新；不设物理 FK 以避免
    # memory_items ↔ memory_versions 的 SQLite 循环建表/回退依赖。
    Column("current_version_id", Integer, nullable=True),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    sqlite_autoincrement=True,
)

memory_versions = Table(
    "memory_versions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("memory_item_id", Integer, ForeignKey("memory_items.id"), nullable=False),
    Column("version", Integer, nullable=False),
    Column("previous_version_id", Integer, ForeignKey("memory_versions.id"), nullable=True),
    Column("rollback_of_version_id", Integer, ForeignKey("memory_versions.id"), nullable=True),
    Column("preference_value", Text, nullable=False),
    Column("memory_status", String, nullable=False),
    Column("evidence_fingerprint", String, nullable=False),
    Column("idempotency_key", String, nullable=True),
    Column("request_fingerprint", String, nullable=False),
    Column("is_current", Integer, nullable=False, server_default="1"),
    Column("created_at", String, nullable=False),
    CheckConstraint("version >= 1", name="ck_memory_versions_version"),
    CheckConstraint("is_current IN (0, 1)", name="ck_memory_versions_current"),
    sqlite_autoincrement=True,
)

outbox = Table(
    "outbox",
    metadata,
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

# ── 索引（4 冻结 + 1 辅助 + 1 ADR-011，冻结文档 §2.3） ──
idx_turns_session = Index("idx_turns_session", turns.c.session_id, turns.c.turn_index)
# ADR-011：部分唯一索引（ADR-010 Upsert 匹配键；SQLite 多 NULL 允许，非空才唯一）
idx_turns_host_turn_id = Index(
    "idx_turns_host_turn_id",
    turns.c.session_id,
    turns.c.host_turn_id,
    unique=True,
    sqlite_where=turns.c.host_turn_id.isnot(None),
)
idx_memory_user_type = Index("idx_memory_user_type", memory_entries.c.user_id, memory_entries.c.entry_type)
idx_memory_deleted = Index("idx_memory_deleted", memory_entries.c.is_deleted)
uq_memory_items_user_key_scope = Index(
    "uq_memory_items_user_key_scope",
    memory_items.c.user_id,
    memory_items.c.preference_key,
    memory_items.c.preference_scope,
    unique=True,
)
uq_memory_versions_item_version = Index(
    "uq_memory_versions_item_version",
    memory_versions.c.memory_item_id,
    memory_versions.c.version,
    unique=True,
)
uq_memory_versions_current = Index(
    "uq_memory_versions_current",
    memory_versions.c.memory_item_id,
    unique=True,
    sqlite_where=memory_versions.c.is_current == 1,
)
idx_memory_versions_idempotency = Index(
    "idx_memory_versions_idempotency",
    memory_versions.c.memory_item_id,
    memory_versions.c.idempotency_key,
    unique=True,
    sqlite_where=memory_versions.c.idempotency_key.isnot(None),
)
idx_memory_versions_evidence = Index(
    "idx_memory_versions_evidence",
    memory_versions.c.memory_item_id,
    memory_versions.c.evidence_fingerprint,
)
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
    # UPDATE（content / entry_type / user_id 任一变化且非软删除）：先删旧再插新
    # PR#52 Issue 11：原触发器仅在 content 变化时触发，entry_type/user_id 变更不刷新
    # FTS 索引，与「同步 memory_entries ↔ memory_fts」声明有差距；现扩展 WHEN 子句。
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

# D7D 版本链跨表约束。SQLite 无法以普通 CHECK 表达「引用版本必须属于同一
# memory item」或同步 current 指针，因此用触发器在数据库入口拒绝篡改，并将
# current 指针随版本状态切换原子同步。
VERSION_TRIGGERS_DDL = [
    """
    CREATE TRIGGER IF NOT EXISTS memory_versions_bi_chain
    BEFORE INSERT ON memory_versions
    WHEN (NEW.previous_version_id IS NULL AND NEW.version != 1)
      OR (NEW.previous_version_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM memory_versions AS previous_version
            WHERE previous_version.id = NEW.previous_version_id
              AND previous_version.memory_item_id = NEW.memory_item_id
              AND previous_version.version = NEW.version - 1
         ))
      OR (NEW.rollback_of_version_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM memory_versions AS rollback_version
            WHERE rollback_version.id = NEW.rollback_of_version_id
              AND rollback_version.memory_item_id = NEW.memory_item_id
         ))
    BEGIN
        SELECT RAISE(ABORT, '版本链引用必须属于同一 memory item');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_versions_bu_chain
    BEFORE UPDATE OF memory_item_id, version, previous_version_id, rollback_of_version_id ON memory_versions
    WHEN NEW.memory_item_id != OLD.memory_item_id
      OR (NEW.previous_version_id IS NULL AND NEW.version != 1)
      OR (NEW.previous_version_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM memory_versions AS previous_version
            WHERE previous_version.id = NEW.previous_version_id
              AND previous_version.memory_item_id = NEW.memory_item_id
              AND previous_version.version = NEW.version - 1
         ))
      OR (NEW.rollback_of_version_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM memory_versions AS rollback_version
            WHERE rollback_version.id = NEW.rollback_of_version_id
              AND rollback_version.memory_item_id = NEW.memory_item_id
         ))
      OR EXISTS (
            SELECT 1 FROM memory_versions AS child_version
            WHERE child_version.previous_version_id = OLD.id
              AND child_version.version != NEW.version + 1
         )
    BEGIN
        SELECT RAISE(ABORT, '版本链引用必须属于同一 memory item');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_items_bi_current_pointer
    BEFORE INSERT ON memory_items
    WHEN NEW.current_version_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM memory_versions
        WHERE memory_versions.id = NEW.current_version_id
          AND memory_versions.memory_item_id = NEW.id
          AND memory_versions.is_current = 1
    )
    BEGIN
        SELECT RAISE(ABORT, 'current_version 指针必须指向本 item 的 current 版本');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_items_bu_current_pointer
    BEFORE UPDATE OF current_version_id ON memory_items
    WHEN (NEW.current_version_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM memory_versions
            WHERE memory_versions.id = NEW.current_version_id
              AND memory_versions.memory_item_id = NEW.id
              AND memory_versions.is_current = 1
         ))
      OR (NEW.current_version_id IS NULL AND EXISTS (
            SELECT 1 FROM memory_versions
            WHERE memory_versions.memory_item_id = NEW.id
              AND memory_versions.is_current = 1
         ))
    BEGIN
        SELECT RAISE(ABORT, 'current_version 指针必须指向本 item 的 current 版本');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_versions_ai_current_pointer
    AFTER INSERT ON memory_versions
    WHEN NEW.is_current = 1
    BEGIN
        UPDATE memory_items SET current_version_id = NEW.id WHERE id = NEW.memory_item_id;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_versions_au_current_pointer_on
    AFTER UPDATE OF is_current ON memory_versions
    WHEN NEW.is_current = 1
    BEGIN
        UPDATE memory_items SET current_version_id = NEW.id WHERE id = NEW.memory_item_id;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_versions_au_current_pointer_off
    AFTER UPDATE OF is_current ON memory_versions
    WHEN OLD.is_current = 1 AND NEW.is_current = 0
    BEGIN
        UPDATE memory_items SET current_version_id = NULL
        WHERE id = NEW.memory_item_id AND current_version_id = OLD.id;
    END
    """,
]
