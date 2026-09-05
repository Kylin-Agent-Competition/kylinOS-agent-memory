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
    # ADR-017：业务 knowledge identity 与检索 identity 分离。version 仍是内容/
    # 索引版本，row_revision 才是所有写入的 optimistic CAS token。
    Column("knowledge_id", String, nullable=True),
    Column("row_revision", Integer, nullable=True),
    Column("knowledge_type", String, nullable=True),
    Column("conditions", Text, nullable=True),
    Column("topic_key", String, nullable=True),
    Column("lifecycle_eligibility", String, nullable=True),
    Column("memory_status", String, nullable=True),
    Column("memory_type", String, nullable=True),
    Column("evidence_tier", String, nullable=True),
    Column("last_accessed_at", String, nullable=True),
    Column("access_count", Integer, nullable=True),
    CheckConstraint("entry_type IN ('preference','knowledge','tool_result','behavior')", name="ck_memory_entries_entry_type"),
    CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_entries_confidence"),
    CheckConstraint("row_revision IS NULL OR row_revision >= 1", name="ck_memory_entries_row_revision"),
    CheckConstraint("access_count IS NULL OR access_count >= 0", name="ck_memory_entries_access_count"),
    CheckConstraint("memory_status IS NULL OR memory_status IN ('active','superseded','deprecated','expired','removed','candidate')", name="ck_memory_entries_memory_status"),
    CheckConstraint("memory_type IS NULL OR memory_type IN ('short_term','medium_term','long_term','ephemeral')", name="ck_memory_entries_memory_type"),
    CheckConstraint("evidence_tier IS NULL OR evidence_tier IN ('user_explicit_config_latest','user_confirmed','tool_execution_result','consistent_behavior_multiple','behavior_inference_single','model_inference')", name="ck_memory_entries_evidence_tier"),
    CheckConstraint("knowledge_type IS NULL OR knowledge_type IN ('workflow','case','template','fact','constraint','failure_experience')", name="ck_memory_entries_knowledge_type"),
    CheckConstraint("lifecycle_eligibility IS NULL OR lifecycle_eligibility IN ('eligible','legacy_unmapped','evidence_unmapped')", name="ck_memory_entries_lifecycle_eligibility"),
)

# ADR-017：关系、冲突与生命周期的 SQLite 真源。关系端点显式带类型，禁止把
# source_event 和 knowledge 的 opaque ID 混为一谈；证据只用结构化 relation 表达。
memory_relation = Table(
    "memory_relation", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, nullable=False),
    Column("relation_id", String, nullable=False),
    Column("relation_type", String, nullable=False),
    Column("left_endpoint_type", String, nullable=False),
    Column("left_endpoint_id", String, nullable=False),
    Column("right_endpoint_type", String, nullable=False),
    Column("right_endpoint_id", String, nullable=False),
    Column("is_primary", Integer, nullable=False, server_default="0"),
    Column("created_at", String, nullable=False),
    CheckConstraint("relation_type IN ('version','evidence','derived')", name="ck_memory_relation_type"),
    CheckConstraint("left_endpoint_type IN ('knowledge','source_event')", name="ck_memory_relation_left_type"),
    CheckConstraint("right_endpoint_type IN ('knowledge','source_event')", name="ck_memory_relation_right_type"),
    CheckConstraint("is_primary IN (0,1)", name="ck_memory_relation_primary"),
    CheckConstraint("relation_type = 'evidence' OR is_primary = 0", name="ck_memory_relation_primary_kind"),
    CheckConstraint("left_endpoint_id <> right_endpoint_id OR left_endpoint_type <> right_endpoint_type", name="ck_memory_relation_not_self"),
    sqlite_autoincrement=True,
)

memory_conflict = Table(
    "memory_conflict", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, nullable=False), Column("conflict_id", String, nullable=False),
    Column("conflict_type", String, nullable=False),
    Column("left_knowledge_id", String, nullable=False), Column("right_knowledge_id", String, nullable=False),
    Column("conflict_summary", Text, nullable=False), Column("involved_present", Integer, nullable=False),
    Column("resolution_status", String, nullable=False), Column("is_auto_resolvable", Integer, nullable=False, server_default="0"),
    Column("detected_at", String, nullable=False), Column("resolution_strategy", String, nullable=True),
    Column("resolution_confidence", Float, nullable=True), Column("resolved_at", String, nullable=True),
    Column("resolved_by", String, nullable=True), Column("winner_id", String, nullable=True),
    Column("decision_action", String, nullable=True), Column("reason_code", String, nullable=True),
    Column("created_at", String, nullable=False), Column("updated_at", String, nullable=False),
    CheckConstraint("left_knowledge_id <> right_knowledge_id", name="ck_memory_conflict_not_self"),
    CheckConstraint("conflict_type IN ('contradiction','temporal_inconsistency','source_conflict','preference_conflict','scope_ambiguity')", name="ck_memory_conflict_type"),
    CheckConstraint("resolution_status IN ('detected','analyzing','resolved_auto','resolved_manual','deferred','unresolvable')", name="ck_memory_conflict_status"),
    CheckConstraint("decision_action IS NULL OR decision_action IN ('keep_left','keep_right','coexist','defer','reject')", name="ck_memory_conflict_action"),
    CheckConstraint("is_auto_resolvable IN (0,1)", name="ck_memory_conflict_auto"),
    CheckConstraint("involved_present IN (0,1)", name="ck_memory_conflict_involved"),
    CheckConstraint("resolution_confidence IS NULL OR (resolution_confidence >= 0 AND resolution_confidence <= 1)", name="ck_memory_conflict_confidence"),
    sqlite_autoincrement=True,
)

memory_conflict_member = Table(
    "memory_conflict_member", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True), Column("user_id", String, nullable=False),
    Column("conflict_id", String, nullable=False), Column("knowledge_id", String, nullable=False),
    Column("ordinal", Integer, nullable=False), Column("role", String, nullable=False), Column("created_at", String, nullable=False),
    CheckConstraint("ordinal >= 0", name="ck_memory_conflict_member_ordinal"),
    CheckConstraint("role IN ('left','right','involved')", name="ck_memory_conflict_member_role"),
    sqlite_autoincrement=True,
)

memory_lifecycle_receipt = Table(
    "memory_lifecycle_receipt", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True), Column("user_id", String, nullable=False),
    Column("evaluation_id", String, nullable=False), Column("evaluation_fingerprint", String, nullable=False),
    Column("knowledge_id", String, nullable=False), Column("memory_entry_id", Integer, nullable=False),
    Column("evaluated_revision", Integer, nullable=False), Column("version_id", String, nullable=False),
    Column("policy_config_hash", String, nullable=False), Column("evaluated_at", String, nullable=False),
    Column("action", String, nullable=False), Column("reason_code", String, nullable=False),
    Column("target_memory_type", String, nullable=True), Column("target_memory_status", String, nullable=True),
    Column("applied", Integer, nullable=False), Column("created_at", String, nullable=False),
    CheckConstraint("evaluated_revision >= 1", name="ck_lifecycle_receipt_revision"),
    CheckConstraint("action IN ('promote','demote','expire','archive_request','hold','reject')", name="ck_lifecycle_receipt_action"),
    CheckConstraint("applied IN (0,1)", name="ck_lifecycle_receipt_applied"),
    sqlite_autoincrement=True,
)

# D10-B：Vector 代次与索引项账本。SQLite 是删除结果、重建激活和幂等回执的
# 持久化真源；Vector Engine 仅承载可重建的派生向量，不承担业务授权判断。
vector_index_generations = Table(
    "vector_index_generations",
    metadata,
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

vector_index_entries = Table(
    "vector_index_entries",
    metadata,
    Column("scope_id", String, primary_key=True),
    Column("generation", String, primary_key=True),
    Column("user_id", String, primary_key=True),
    Column("memory_entry_id", Integer, primary_key=True),
    Column("version_id", String, primary_key=True),
    Column("is_active", Integer, nullable=False, server_default="1"),
)

vector_index_receipts = Table(
    "vector_index_receipts",
    metadata,
    Column("scope_id", String, primary_key=True),
    Column("user_id", String, primary_key=True),
    Column("operation", String, primary_key=True),
    Column("generation", String, primary_key=True),
    Column("idempotency_key", String, primary_key=True),
    Column("payload_hash", String, nullable=False),
    Column("result_json", Text, nullable=False),
    Column("created_at", String, nullable=False),
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
    CheckConstraint(
        "preference_scope IN ('global', 'topic', 'tool', 'session', 'time_window')",
        name="ck_memory_items_preference_scope",
    ),
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
    CheckConstraint(
        "memory_status IN ('active', 'superseded', 'deprecated', 'expired', 'removed', 'candidate')",
        name="ck_memory_versions_memory_status",
    ),
    sqlite_autoincrement=True,
)

# D7D 操作回执：CREATE/UPDATE/ROLLBACK 写入对应版本；NO_OP 则指向既有 current。
# 因而每次请求均占用幂等键和证据指纹，却不为相同值新增无意义业务版本。
memory_version_receipts = Table(
    "memory_version_receipts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("memory_item_id", Integer, ForeignKey("memory_items.id"), nullable=False),
    Column("memory_version_id", Integer, ForeignKey("memory_versions.id"), nullable=False),
    Column("operation_kind", String, nullable=False),
    Column("preference_value", Text, nullable=False),
    Column("memory_status", String, nullable=False),
    Column("evidence_fingerprint", String, nullable=False),
    Column("idempotency_key", String, nullable=True),
    Column("request_fingerprint", String, nullable=False),
    Column("created_at", String, nullable=False),
    CheckConstraint(
        "operation_kind IN ('write', 'no_op', 'rollback')",
        name="ck_memory_version_receipts_operation_kind",
    ),
    CheckConstraint(
        "memory_status IN ('active', 'superseded', 'deprecated', 'expired', 'removed', 'candidate')",
        name="ck_memory_version_receipts_memory_status",
    ),
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
    # ADR-015（D 已决策 + Reviewer E 已签署 2026-09-02）：nullable priority 列，
    # DEFAULT 0（普通索引任务）；forget.* 删除类事件 = 1；预留 2 = urgent。
    # 历史行 NULL 与 0 语义统一为 0（迁移重建时显式回填 0）。
    Column("priority", Integer, nullable=True, server_default="0"),
    CheckConstraint("aggregate_type IN ('turn','memory','forget')", name="ck_outbox_aggregate_type"),
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

# ADR-013（v5，D 决策 + Reviewer E 签署 2026-08-31）：多源事件持久化表（FRZ-DB-001 扩展）。
# 35 列 + 5 CHECK + 5 索引；敏感/security reject/consent reject 事件 content_fingerprint 持久化
# NULL（HIGH-03）；processing_status 首次落库一律 'pending'（MEDIUM-01）；dedup_group 含 user scope。
source_events = Table(
    "source_events",
    metadata,
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

# ADR-015（v1，D 已决策 + Reviewer E 已签署 2026-09-02）：精准遗忘持久化（FRZ-DB-001 扩展）。
# forget_plan = 遗忘计划持久化行（D 轨实体）；forget_audit = 最小审计（零正文）。
# selector 明文生命周期（HIGH-01）：Preview 完成后 target_selector/target_topic 清除或置
# 安全占位（<CLEARED>）；selection_hash 由结构化 resolved_target_ids 派生（非正文）。
forget_plan = Table(
    "forget_plan",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, nullable=False),          # 隔离键，禁止模型生成
    Column("forget_plan_id", String, nullable=False),   # 计划唯一 ID（宿主生成）
    Column("forget_mode", String, nullable=False),      # 五值枚举（冻结）
    Column("target_selector", String, nullable=True),   # 明文生命周期，Preview 后清除/占位
    Column("target_type", String, nullable=False),      # 四值枚举
    Column("target_id", String, nullable=True),         # 模式条件字段（互斥）
    Column("target_session_id", String, nullable=True),
    Column("target_topic", String, nullable=True),      # 可能承载自然语言正文（HIGH-01）
    Column("target_time_range", String, nullable=True),
    Column("resolved_target_ids", String, nullable=True),  # JSON 数组（preview 产物，禁止模型生成）
    Column("selection_hash", String, nullable=True),    # Preview/Selection 稳定 Hash（非正文）
    Column("status", String, nullable=False),           # v0.2 冻结状态机
    Column("requires_confirmation", Integer, nullable=False, server_default="1"),
    Column("is_cascade", Integer, nullable=False, server_default="0"),
    Column("delete_mode", String, nullable=False, server_default="soft"),
    Column("has_vector_cleanup", Integer, nullable=False, server_default="0"),
    Column("confirmation_token", String, nullable=True),  # 确认凭据 SHA-256 哈希（明文不落库）
    Column("token_expires_at", String, nullable=True),    # 凭据 TTL（默认 300s）
    Column("affected_count", Integer, nullable=True),     # = len(resolved_target_ids)
    Column("executed_count", Integer, nullable=True),     # 实际执行成功数量
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

forget_audit = Table(
    "forget_audit",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("audit_id", String, nullable=False),          # 审计唯一 ID
    Column("forget_plan_id", String, nullable=False),
    Column("user_id", String, nullable=False),
    Column("forget_mode", String, nullable=False),       # 五值
    Column("target_type", String, nullable=True),        # 四值
    Column("delete_mode", String, nullable=False),       # soft / hard
    Column("is_cascade", Integer, nullable=False, server_default="0"),
    Column("affected_count", Integer, nullable=True),
    Column("selection_hash", String, nullable=True),     # 非正文
    Column("confirmation_ref", String, nullable=True),   # 凭据非敏感引用/Hash（不得存原 Token）
    Column("status", String, nullable=False),
    Column("result_code", String, nullable=True),
    Column("trace_id", String, nullable=True),           # 追踪链（非正文）
    Column("sensitivity_max", String, nullable=True),
    Column("created_at", String, nullable=False),
    Column("executed_at", String, nullable=True),        # 遗忘动作实际执行时间（终态必填）
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
uq_memory_entries_user_knowledge = Index(
    "uq_memory_entries_user_knowledge", memory_entries.c.user_id, memory_entries.c.knowledge_id,
    unique=True, sqlite_where=(memory_entries.c.entry_type == "knowledge") & memory_entries.c.knowledge_id.isnot(None),
)
idx_memory_entries_user_status = Index("idx_memory_entries_user_status", memory_entries.c.user_id, memory_entries.c.memory_status)
idx_memory_entries_user_lifecycle_type = Index("idx_memory_entries_user_lifecycle_type", memory_entries.c.user_id, memory_entries.c.memory_type)
idx_memory_entries_user_topic_active = Index(
    "idx_memory_entries_user_topic_active",
    memory_entries.c.user_id,
    memory_entries.c.topic_key,
    sqlite_where=(memory_entries.c.entry_type == "knowledge")
    & (memory_entries.c.is_deleted == 0)
    & memory_entries.c.topic_key.isnot(None),
)
uq_memory_relation_user_relation = Index("uq_memory_relation_user_relation", memory_relation.c.user_id, memory_relation.c.relation_id, unique=True)
idx_memory_relation_left = Index("idx_memory_relation_left", memory_relation.c.user_id, memory_relation.c.left_endpoint_type, memory_relation.c.left_endpoint_id)
idx_memory_relation_right = Index("idx_memory_relation_right", memory_relation.c.user_id, memory_relation.c.right_endpoint_type, memory_relation.c.right_endpoint_id)
uq_memory_relation_canonical_evidence = Index(
    "uq_memory_relation_canonical_evidence", memory_relation.c.user_id, memory_relation.c.left_endpoint_id, memory_relation.c.right_endpoint_id,
    unique=True, sqlite_where=(memory_relation.c.relation_type == "evidence") & (memory_relation.c.left_endpoint_type == "knowledge") & (memory_relation.c.right_endpoint_type == "source_event"),
)
uq_memory_relation_primary_evidence = Index(
    "uq_memory_relation_primary_evidence", memory_relation.c.user_id, memory_relation.c.left_endpoint_id,
    unique=True, sqlite_where=(memory_relation.c.relation_type == "evidence") & (memory_relation.c.left_endpoint_type == "knowledge") & (memory_relation.c.right_endpoint_type == "source_event") & (memory_relation.c.is_primary == 1),
)
uq_memory_relation_version_successor = Index(
    "uq_memory_relation_version_successor", memory_relation.c.user_id, memory_relation.c.left_endpoint_id,
    unique=True, sqlite_where=(memory_relation.c.relation_type == "version") & (memory_relation.c.left_endpoint_type == "knowledge"),
)
uq_memory_conflict_user_conflict = Index("uq_memory_conflict_user_conflict", memory_conflict.c.user_id, memory_conflict.c.conflict_id, unique=True)
idx_memory_conflict_left = Index("idx_memory_conflict_left", memory_conflict.c.user_id, memory_conflict.c.left_knowledge_id)
idx_memory_conflict_right = Index("idx_memory_conflict_right", memory_conflict.c.user_id, memory_conflict.c.right_knowledge_id)
idx_memory_conflict_status = Index("idx_memory_conflict_status", memory_conflict.c.user_id, memory_conflict.c.resolution_status)
uq_memory_conflict_member_ordinal = Index("uq_memory_conflict_member_ordinal", memory_conflict_member.c.user_id, memory_conflict_member.c.conflict_id, memory_conflict_member.c.ordinal, unique=True)
idx_memory_conflict_member_knowledge = Index("idx_memory_conflict_member_knowledge", memory_conflict_member.c.user_id, memory_conflict_member.c.knowledge_id)
uq_lifecycle_receipt_evaluation = Index("uq_lifecycle_receipt_evaluation", memory_lifecycle_receipt.c.user_id, memory_lifecycle_receipt.c.evaluation_id, unique=True)
uq_lifecycle_archive_once = Index(
    "uq_lifecycle_archive_once", memory_lifecycle_receipt.c.user_id, memory_lifecycle_receipt.c.knowledge_id,
    memory_lifecycle_receipt.c.version_id, memory_lifecycle_receipt.c.action, memory_lifecycle_receipt.c.reason_code,
    unique=True, sqlite_where=memory_lifecycle_receipt.c.action == "archive_request",
)
uq_vector_generation_serving_scope = Index(
    "uq_vector_generation_serving_scope",
    vector_index_generations.c.scope_id,
    unique=True,
    sqlite_where=vector_index_generations.c.is_serving == 1,
)
idx_vector_index_entries_active = Index(
    "idx_vector_index_entries_active",
    vector_index_entries.c.scope_id,
    vector_index_entries.c.generation,
    vector_index_entries.c.user_id,
    vector_index_entries.c.is_active,
)
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
idx_memory_versions_status = Index(
    "idx_memory_versions_status",
    memory_versions.c.memory_item_id,
    memory_versions.c.memory_status,
)
uq_memory_version_receipts_idempotency = Index(
    "uq_memory_version_receipts_idempotency",
    memory_version_receipts.c.memory_item_id,
    memory_version_receipts.c.idempotency_key,
    unique=True,
    sqlite_where=memory_version_receipts.c.idempotency_key.isnot(None),
)
uq_memory_version_receipts_evidence = Index(
    "uq_memory_version_receipts_evidence",
    memory_version_receipts.c.memory_item_id,
    memory_version_receipts.c.evidence_fingerprint,
    unique=True,
)
idx_outbox_pending = Index(
    "idx_outbox_pending",
    outbox.c.next_retry_at,
    sqlite_where=outbox.c.attempts <= 3,  # 与 outbox.max_retries=3 配套（需求 §2.2）
)
# ADR-015：删除类事件优先级部分索引（forget.* priority=1 优先于普通索引任务）
idx_outbox_priority = Index(
    "idx_outbox_priority",
    outbox.c.priority,
    outbox.c.next_retry_at,
    sqlite_where=outbox.c.priority == 1,
)
idx_idempotency_expires = Index("idx_idempotency_expires", idempotency_cache.c.expires_at)

# ADR-013：source_events 5 索引（全局唯一 event_id + 时间线 + 指纹 + 去重组 + 状态）
uq_source_events_event = Index(
    "uq_source_events_event",
    source_events.c.event_id,
    unique=True,
)
idx_source_events_user_created = Index(
    "idx_source_events_user_created",
    source_events.c.user_id,
    source_events.c.created_at,
)
idx_source_events_fingerprint = Index(
    "idx_source_events_fingerprint",
    source_events.c.user_id,
    source_events.c.content_fingerprint,
)
idx_source_events_dedup_group = Index(
    "idx_source_events_dedup_group",
    source_events.c.user_id,
    source_events.c.dedup_group,
)
idx_source_events_status = Index(
    "idx_source_events_status",
    source_events.c.user_id,
    source_events.c.processing_status,
)

# ADR-015：forget 两表索引（计划级唯一 + 时间线审计）
uq_forget_plan_user_plan = Index(
    "uq_forget_plan_user_plan",
    forget_plan.c.user_id,
    forget_plan.c.forget_plan_id,
    unique=True,
)
idx_forget_plan_user_created = Index(
    "idx_forget_plan_user_created",
    forget_plan.c.user_id,
    forget_plan.c.created_at,
)
idx_forget_audit_user_created = Index(
    "idx_forget_audit_user_created",
    forget_audit.c.user_id,
    forget_audit.c.created_at,
)

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
    CREATE TRIGGER IF NOT EXISTS memory_versions_bu_immutable
    BEFORE UPDATE ON memory_versions
    WHEN NEW.preference_value IS NOT OLD.preference_value
      OR NEW.evidence_fingerprint IS NOT OLD.evidence_fingerprint
      OR NEW.idempotency_key IS NOT OLD.idempotency_key
      OR NEW.request_fingerprint IS NOT OLD.request_fingerprint
      OR NEW.created_at IS NOT OLD.created_at
      OR NEW.previous_version_id IS NOT OLD.previous_version_id
      OR NEW.rollback_of_version_id IS NOT OLD.rollback_of_version_id
      OR (NEW.is_current IS NOT OLD.is_current AND NOT (
            OLD.is_current = 1 AND NEW.is_current = 0 AND NEW.memory_status = 'superseded'
            AND EXISTS (
                SELECT 1 FROM memory_versions AS successor_version
                WHERE successor_version.memory_item_id = OLD.memory_item_id
                  AND successor_version.previous_version_id = OLD.id
                  AND successor_version.version = OLD.version + 1
                  AND successor_version.is_current = 0
            )
         ) AND NOT (
            OLD.is_current = 0 AND NEW.is_current = 1
            AND NEW.previous_version_id IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM memory_versions AS previous_version
                WHERE previous_version.id = NEW.previous_version_id
                  AND previous_version.memory_item_id = NEW.memory_item_id
                  AND previous_version.is_current = 0
                  AND previous_version.memory_status = 'superseded'
            )
         ))
      OR (NEW.memory_status IS NOT OLD.memory_status AND NOT (
            OLD.is_current = 1 AND NEW.is_current = 0 AND NEW.memory_status = 'superseded'
            AND EXISTS (
                SELECT 1 FROM memory_versions AS successor_version
                WHERE successor_version.memory_item_id = OLD.memory_item_id
                  AND successor_version.previous_version_id = OLD.id
                  AND successor_version.version = OLD.version + 1
                  AND successor_version.is_current = 0
            )
         ))
    BEGIN
        SELECT RAISE(ABORT, 'memory_versions 历史字段不可原地修改');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_versions_bd_immutable
    BEFORE DELETE ON memory_versions
    BEGIN
        SELECT RAISE(ABORT, 'memory_versions 历史不可删除');
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
        UPDATE memory_versions SET is_current = 1
        WHERE id = (
            SELECT successor_version.id
            FROM memory_versions AS successor_version
            WHERE successor_version.memory_item_id = NEW.memory_item_id
              AND successor_version.previous_version_id = OLD.id
              AND successor_version.version = OLD.version + 1
              AND successor_version.is_current = 0
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_version_receipts_bi_consistency
    BEFORE INSERT ON memory_version_receipts
    WHEN NOT EXISTS (
        SELECT 1 FROM memory_versions
        WHERE memory_versions.id = NEW.memory_version_id
          AND memory_versions.memory_item_id = NEW.memory_item_id
          AND memory_versions.preference_value = NEW.preference_value
          AND memory_versions.memory_status = NEW.memory_status
    )
    BEGIN
        SELECT RAISE(ABORT, '操作回执必须与同一 memory item 的版本值和状态一致');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_version_receipts_bu_immutable
    BEFORE UPDATE ON memory_version_receipts
    BEGIN
        SELECT RAISE(ABORT, 'memory_version_receipts 回执不可修改');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_version_receipts_bd_immutable
    BEFORE DELETE ON memory_version_receipts
    BEGIN
        SELECT RAISE(ABORT, 'memory_version_receipts 回执不可删除');
    END
    """,
]
