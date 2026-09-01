"""20260831_add_source_events — ADR-013：多源事件持久化表 source_events（FRZ-DB-001 扩展）

契约来源：docs/adr/013-source-events-table.md（v5，D 决策 + Reviewer E 签署 2026-08-31，PASS_WITH_DEBT）
  - 35 列（NormalizedEvent 业务投影 + 2 去重标记列 dedup_group/duplicate_of）
  - 5 索引：全局 UNIQUE(event_id) + (user_id, created_at) + (user_id, content_fingerprint)
    + (user_id, dedup_group) + (user_id, processing_status)
  - 5 CHECK：consent_scope / source_business_status / sensitivity / admission_decision / processing_status
  - downgrade：DROP TABLE（新表无既有数据依赖，可整表回滚；ADR-013 决策）
  - 命名：YYYYMMDD_<description>.py（ADR-007）

版本链：001_initial_schema → 20260826_add_trace_id → 20260831_preference_versions →
20260831_add_source_events。注：ADR-013 草案标注 down_revision="20260826_add_trace_id"
系契约先行时未计入已合入的 D7D 迁移 20260831_preference_versions（PR #90）；为避免产生
多 head 破坏 `alembic upgrade head` 线性链，本迁移 down_revision 对齐当前唯一 head
20260831_preference_versions，链仍为单一线性链。
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import CheckConstraint, Column, Integer, String, Text

# ── revision 元数据（ADR-007 / ADR-013） ──
revision = "20260831_add_source_events"
down_revision = "20260831_preference_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增 source_events 表（35 列 + 5 CHECK + 5 索引）。"""
    op.create_table(
        "source_events",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String, nullable=False),          # 隔离键，禁止正文推断
        Column("event_id", String, nullable=False),          # 事件级全局唯一键（宿主生成）
        Column("actor_id", String, nullable=False),
        Column("session_id", String, nullable=False),
        Column("turn_id", String, nullable=True),
        Column("tool_call_id", String, nullable=True),
        Column("source_type", String, nullable=False),       # 七值枚举
        Column("event_type", String, nullable=False),        # 三值枚举
        Column("schema_version", String, nullable=False),
        Column("trace_id", String, nullable=True),
        Column("source_reference", String, nullable=True),   # 受控引用，非正文
        Column("raw_payload_ref", String, nullable=True),    # 受控引用，非正文（敏感/安全类强制 NULL）
        Column("content_summary", Text, nullable=True),      # 脱敏摘要，非原文（敏感/安全类强制 NULL）
        Column("idempotency_key", String, nullable=False),
        Column("consent_scope", String, nullable=False),     # 授权字段
        Column("source_business_status", String, nullable=False),  # 八值
        Column("sensitivity", String, nullable=False),       # 五级
        Column("is_sensitive_matched", Integer, nullable=False, server_default="0"),
        Column("should_ignore", Integer, nullable=False, server_default="0"),
        Column("payload_security_checked", Integer, nullable=False, server_default="0"),
        Column("memory_type", String, nullable=True),
        Column("requires_embedding", Integer, nullable=False, server_default="1"),
        Column("has_structured_payload", Integer, nullable=False, server_default="0"),
        Column("language_tag", String, nullable=True),
        Column("occurred_at", String, nullable=False),       # aware UTC ISO8601（identity 组成）
        Column("captured_at", String, nullable=False),       # aware UTC ISO8601
        Column("content_fingerprint", String, nullable=True),  # 敏感/未授权事件持久化 NULL
        Column("dedup_group", String, nullable=True),        # 指纹去重组（含 user scope）
        Column("duplicate_of", Integer, nullable=True),      # 首次同指纹事件 id（软引用，无 FK）
        Column("admission_decision", String, nullable=False),
        Column("admission_reason_code", String, nullable=False),
        Column("processing_status", String, nullable=False, server_default="pending"),
        Column("created_at", String, nullable=False),
        Column("updated_at", String, nullable=False),
        CheckConstraint(
            "consent_scope IN ('memory_only','memory_and_analytics','none')",
            name="ck_source_events_consent_scope",
        ),
        CheckConstraint(
            "source_business_status IN ('raw','completed','success','partial','failed','cancelled','timeout','ignored')",
            name="ck_source_events_source_business_status",
        ),
        CheckConstraint(
            "sensitivity IN ('none','low','medium','high','critical')",
            name="ck_source_events_sensitivity",
        ),
        CheckConstraint(
            "admission_decision IN ('allow_extraction','audit_only','reject')",
            name="ck_source_events_admission_decision",
        ),
        CheckConstraint(
            "processing_status IN ('pending','extracting','extracted','embedded','stored')",
            name="ck_source_events_processing_status",
        ),
        sqlite_autoincrement=True,
    )

    op.create_index("uq_source_events_event", "source_events", ["event_id"], unique=True)
    op.create_index("idx_source_events_user_created", "source_events", ["user_id", "created_at"])
    op.create_index("idx_source_events_fingerprint", "source_events", ["user_id", "content_fingerprint"])
    op.create_index("idx_source_events_dedup_group", "source_events", ["user_id", "dedup_group"])
    op.create_index("idx_source_events_status", "source_events", ["user_id", "processing_status"])


def downgrade() -> None:
    """DROP TABLE（新表无既有数据依赖，可整表回滚；无列删除红线问题，ADR-013）。"""
    op.drop_index("idx_source_events_status", table_name="source_events")
    op.drop_index("idx_source_events_dedup_group", table_name="source_events")
    op.drop_index("idx_source_events_fingerprint", table_name="source_events")
    op.drop_index("idx_source_events_user_created", table_name="source_events")
    op.drop_index("uq_source_events_event", table_name="source_events")
    op.drop_table("source_events")
