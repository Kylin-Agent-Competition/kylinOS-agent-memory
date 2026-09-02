"""20260901_add_forget_plan — ADR-015：精准遗忘持久化（FRZ-DB-001 扩展）

契约来源：docs/adr/015-forget-persistence.md（v1，D 已决策 + Reviewer E 已签署 2026-09-02）
  - 新增 forget_plan / forget_audit 两表（DDL 逐字段对齐 ADR-015 §冻结 DDL）
  - outbox 只增 nullable priority 列（DEFAULT 0）+ 部分索引 idx_outbox_priority
    + aggregate_type CHECK 值域扩展 'turn','memory' → 'turn','memory','forget'（D1 决策）
  - 既有表/列/索引/触发器/FTS5 只增不改；downgrade 对称回滚（重建保留数据）

版本链：001_initial_schema → 20260826_add_trace_id → 20260831_preference_versions →
20260831_add_source_events → 20260901_d10b_vector_ledger → 20260901_add_forget_plan (head)
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import CheckConstraint, Column, Integer, String, text


revision = "20260901_add_forget_plan"
down_revision = "20260901_d10b_vector_ledger"
branch_labels = None
depends_on = None


# outbox 重建（SQLite 不支持原地改 CHECK / 删列，需 CREATE→COPY→DROP→RENAME 保留数据）
_OUTBOX_UPGRADE_SQL = (
    "CREATE TABLE _outbox_d10d_new ("
    "id INTEGER NOT NULL PRIMARY KEY, "
    "aggregate_type VARCHAR NOT NULL, "
    "aggregate_id VARCHAR NOT NULL, "
    "event_type VARCHAR NOT NULL, "
    "payload TEXT NOT NULL, "
    "attempts INTEGER NOT NULL DEFAULT 0, "
    "next_retry_at VARCHAR, "
    "last_error TEXT, "
    "created_at VARCHAR NOT NULL, "
    "priority INTEGER DEFAULT 0, "
    "CONSTRAINT ck_outbox_aggregate_type CHECK "
    "(aggregate_type IN ('turn','memory','forget'))"
    ")"
)
_OUTBOX_UPGRADE_COPY = (
    "INSERT INTO _outbox_d10d_new "
    "(id, aggregate_type, aggregate_id, event_type, payload, attempts, "
    "next_retry_at, last_error, created_at, priority) "
    "SELECT id, aggregate_type, aggregate_id, event_type, payload, attempts, "
    "next_retry_at, last_error, created_at, 0 FROM outbox"
)
_OUTBOX_DOWNGRADE_SQL = (
    "CREATE TABLE _outbox_d10d_old ("
    "id INTEGER NOT NULL PRIMARY KEY, "
    "aggregate_type VARCHAR NOT NULL, "
    "aggregate_id VARCHAR NOT NULL, "
    "event_type VARCHAR NOT NULL, "
    "payload TEXT NOT NULL, "
    "attempts INTEGER NOT NULL DEFAULT 0, "
    "next_retry_at VARCHAR, "
    "last_error TEXT, "
    "created_at VARCHAR NOT NULL, "
    "CONSTRAINT ck_outbox_aggregate_type CHECK "
    "(aggregate_type IN ('turn','memory'))"
    ")"
)
_OUTBOX_DOWNGRADE_COPY = (
    "INSERT INTO _outbox_d10d_old "
    "(id, aggregate_type, aggregate_id, event_type, payload, attempts, "
    "next_retry_at, last_error, created_at) "
    "SELECT id, aggregate_type, aggregate_id, event_type, payload, attempts, "
    "next_retry_at, last_error, created_at FROM outbox"
)


def _rebuild_outbox_upgrade() -> None:
    """outbox 增 priority 列 + aggregate_type CHECK 扩展（保留数据）。"""
    bind = op.get_bind()
    bind.execute(text(_OUTBOX_UPGRADE_SQL))
    bind.execute(text(_OUTBOX_UPGRADE_COPY))
    bind.execute(text("DROP TABLE outbox"))
    bind.execute(text("ALTER TABLE _outbox_d10d_new RENAME TO outbox"))
    # DROP 旧表连带删除 idx_outbox_pending，需对称重建
    bind.execute(text(
        "CREATE INDEX idx_outbox_pending ON outbox(next_retry_at) WHERE attempts <= 3"
    ))
    bind.execute(text(
        "CREATE INDEX idx_outbox_priority ON outbox(priority, next_retry_at) WHERE priority = 1"
    ))


def _rebuild_outbox_downgrade() -> None:
    """outbox 撤销 priority 列 + CHECK 值域（保留数据；含 forget 行则 CHECK 拒绝，fail-closed）。"""
    bind = op.get_bind()
    bind.execute(text(_OUTBOX_DOWNGRADE_SQL))
    bind.execute(text(_OUTBOX_DOWNGRADE_COPY))
    bind.execute(text("DROP TABLE outbox"))
    bind.execute(text("ALTER TABLE _outbox_d10d_old RENAME TO outbox"))
    bind.execute(text(
        "CREATE INDEX idx_outbox_pending ON outbox(next_retry_at) WHERE attempts <= 3"
    ))


def upgrade() -> None:
    # ── forget_plan（ADR-015 冻结 DDL） ──
    op.create_table(
        "forget_plan",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String, nullable=False),
        Column("forget_plan_id", String, nullable=False),
        Column("forget_mode", String, nullable=False),
        Column("target_selector", String, nullable=True),
        Column("target_type", String, nullable=False),
        Column("target_id", String, nullable=True),
        Column("target_session_id", String, nullable=True),
        Column("target_topic", String, nullable=True),
        Column("target_time_range", String, nullable=True),
        Column("resolved_target_ids", String, nullable=True),
        Column("selection_hash", String, nullable=True),
        Column("status", String, nullable=False),
        Column("requires_confirmation", Integer, nullable=False, server_default="1"),
        Column("is_cascade", Integer, nullable=False, server_default="0"),
        Column("delete_mode", String, nullable=False, server_default="soft"),
        Column("has_vector_cleanup", Integer, nullable=False, server_default="0"),
        Column("confirmation_token", String, nullable=True),
        Column("token_expires_at", String, nullable=True),
        Column("affected_count", Integer, nullable=True),
        Column("executed_count", Integer, nullable=True),
        Column("executed_at", String, nullable=True),
        Column("rollback_plan_id", String, nullable=True),
        Column("created_at", String, nullable=False),
        Column("updated_at", String, nullable=False),
        CheckConstraint(
            "forget_mode IN ('single_item','session','topic','time_window','full_reset')",
            name="ck_forget_plan_forget_mode",
        ),
        CheckConstraint(
            "target_type IN ('knowledge','preference','event','all')",
            name="ck_forget_plan_target_type",
        ),
        CheckConstraint(
            "status IN ('pending','previewing','awaiting_confirmation','executing','completed','failed','rolled_back')",
            name="ck_forget_plan_status",
        ),
        CheckConstraint("delete_mode IN ('soft','hard')", name="ck_forget_plan_delete_mode"),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "uq_forget_plan_user_plan", "forget_plan", ["user_id", "forget_plan_id"], unique=True
    )
    op.create_index("idx_forget_plan_user_created", "forget_plan", ["user_id", "created_at"])

    # ── forget_audit（ADR-015 冻结 DDL，最小审计零正文） ──
    op.create_table(
        "forget_audit",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("audit_id", String, nullable=False),
        Column("forget_plan_id", String, nullable=False),
        Column("user_id", String, nullable=False),
        Column("forget_mode", String, nullable=False),
        Column("target_type", String, nullable=True),
        Column("delete_mode", String, nullable=False),
        Column("is_cascade", Integer, nullable=False, server_default="0"),
        Column("affected_count", Integer, nullable=True),
        Column("selection_hash", String, nullable=True),
        Column("confirmation_ref", String, nullable=True),
        Column("status", String, nullable=False),
        Column("result_code", String, nullable=True),
        Column("trace_id", String, nullable=True),
        Column("sensitivity_max", String, nullable=True),
        Column("created_at", String, nullable=False),
        Column("executed_at", String, nullable=True),
        CheckConstraint(
            "forget_mode IN ('single_item','session','topic','time_window','full_reset')",
            name="ck_forget_audit_forget_mode",
        ),
        CheckConstraint(
            "target_type IN ('knowledge','preference','event','all')",
            name="ck_forget_audit_target_type",
        ),
        CheckConstraint(
            "status IN ('pending','previewing','awaiting_confirmation','executing','completed','failed','rolled_back')",
            name="ck_forget_audit_status",
        ),
        CheckConstraint("delete_mode IN ('soft','hard')", name="ck_forget_audit_delete_mode"),
        sqlite_autoincrement=True,
    )
    op.create_index("idx_forget_audit_user_created", "forget_audit", ["user_id", "created_at"])

    # ── outbox：priority 列 + 部分索引 + aggregate_type CHECK 扩展 ──
    _rebuild_outbox_upgrade()


def downgrade() -> None:
    """对称回滚：outbox 撤销 priority/CHECK 扩展（保留数据）→ DROP 两表。"""
    _rebuild_outbox_downgrade()
    op.drop_index("idx_forget_audit_user_created", table_name="forget_audit")
    op.drop_table("forget_audit")
    op.drop_index("idx_forget_plan_user_created", table_name="forget_plan")
    op.drop_index("uq_forget_plan_user_plan", table_name="forget_plan")
    op.drop_table("forget_plan")
