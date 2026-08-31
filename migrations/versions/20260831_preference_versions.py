"""20260831_preference_versions — D7D 偏好版本真源与不可变历史。

新增 memory_items / memory_versions，不修改既有 memory_entries 的通用职责。
部分唯一索引在数据库层保证每个 memory item 至多一个 current 版本；Repository
将旧版本标为非 current 后才插入新版本，所有步骤在同一 UnitOfWork 事务内完成。

回退安全：空版本表可回到上一 revision；一旦已有版本历史则拒绝回退，避免把
用户版本记录静默删除。
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, Text, text


revision = "20260831_preference_versions"
down_revision = "20260826_add_trace_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_items",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String, nullable=False),
        Column("preference_key", String, nullable=False),
        Column("preference_scope", String, nullable=False),
        Column("current_version_id", Integer, nullable=True),
        Column("created_at", String, nullable=False),
        Column("updated_at", String, nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "uq_memory_items_user_key_scope",
        "memory_items",
        ["user_id", "preference_key", "preference_scope"],
        unique=True,
    )
    op.create_table(
        "memory_versions",
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
    op.create_index(
        "uq_memory_versions_item_version", "memory_versions", ["memory_item_id", "version"], unique=True
    )
    op.create_index(
        "uq_memory_versions_current", "memory_versions", ["memory_item_id"], unique=True,
        sqlite_where=text("is_current = 1"),
    )
    op.create_index(
        "idx_memory_versions_idempotency", "memory_versions", ["memory_item_id", "idempotency_key"], unique=True,
        sqlite_where=text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "idx_memory_versions_evidence", "memory_versions", ["memory_item_id", "evidence_fingerprint"]
    )
    op.execute(
        """
        CREATE TRIGGER memory_versions_bi_chain
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
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_versions_bu_chain
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
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_items_bi_current_pointer
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
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_items_bu_current_pointer
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
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_versions_ai_current_pointer
        AFTER INSERT ON memory_versions
        WHEN NEW.is_current = 1
        BEGIN
            UPDATE memory_items SET current_version_id = NEW.id WHERE id = NEW.memory_item_id;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_versions_au_current_pointer_on
        AFTER UPDATE OF is_current ON memory_versions
        WHEN NEW.is_current = 1
        BEGIN
            UPDATE memory_items SET current_version_id = NEW.id WHERE id = NEW.memory_item_id;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_versions_au_current_pointer_off
        AFTER UPDATE OF is_current ON memory_versions
        WHEN OLD.is_current = 1 AND NEW.is_current = 0
        BEGIN
            UPDATE memory_items SET current_version_id = NULL
            WHERE id = NEW.memory_item_id AND current_version_id = OLD.id;
        END
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    version_count = bind.execute(text("SELECT count(*) FROM memory_versions")).scalar_one()
    item_count = bind.execute(text("SELECT count(*) FROM memory_items")).scalar_one()
    if version_count or item_count:
        raise RuntimeError("拒绝回退：memory_items 或 memory_versions 已含版本历史，禁止静默删除数据")

    op.execute("DROP TRIGGER IF EXISTS memory_versions_au_current_pointer_off")
    op.execute("DROP TRIGGER IF EXISTS memory_versions_au_current_pointer_on")
    op.execute("DROP TRIGGER IF EXISTS memory_versions_ai_current_pointer")
    op.execute("DROP TRIGGER IF EXISTS memory_items_bu_current_pointer")
    op.execute("DROP TRIGGER IF EXISTS memory_items_bi_current_pointer")
    op.execute("DROP TRIGGER IF EXISTS memory_versions_bu_chain")
    op.execute("DROP TRIGGER IF EXISTS memory_versions_bi_chain")
    op.drop_index("idx_memory_versions_evidence", table_name="memory_versions")
    op.drop_index("idx_memory_versions_idempotency", table_name="memory_versions")
    op.drop_index("uq_memory_versions_current", table_name="memory_versions")
    op.drop_index("uq_memory_versions_item_version", table_name="memory_versions")
    op.drop_table("memory_versions")
    op.drop_index("uq_memory_items_user_key_scope", table_name="memory_items")
    op.drop_table("memory_items")
