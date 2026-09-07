# ADR-017：关系、冲突与生命周期持久化

- **状态**：✅ 已采纳（PR #122 契约草案已签署；本 canonical write-back 待 Reviewer E 最终一致性确认）
- **日期**：2026-09-02
- **责任轨道**：D（持久化 / IPC）；E（业务语义、安全与冻结审查）
- **Reviewer**：E（`lovezy0730-create`），PR #122 HEAD `c6ecbae` `APPROVED`（2026-09-02）
- **决策版本**：`d8d-adr017-v1`
- **适用范围**：FRZ-DB-001 additive 扩展
- **能力状态**：设计/契约已冻结；Runtime、Migration、L1/L2/HOST_VERIFIED 尚未因此获得完成性背书
- **批准依据 / 不可变契约附件**：`docs/day8/07_d8d_adr017_018_draft.md` 第一部分（PR #122 批准 HEAD `c6ecbae`）。该文件头部的 `DRAFT / 正式生效=NO` 是提交时历史状态；PR #122 APPROVE 已批准其契约内容，当前 canonical 生效状态以本 ADR、FRZ write-back 及 Reviewer E 最终一致性确认为准。

## 背景

E 轨已经冻结 `Conflict`、`ConflictResolutionPolicy` 与 `LifecyclePolicy` 的业务语义，但不承担持久化或执行。现有 SQLite 缺少稳定的 `knowledge_id ↔ memory_id/version_id` 映射、关系/冲突结构化真源、生命周期回执与独立 CAS revision，无法安全接入 B/C/E 轨。

## 决策

采纳批准草案方案 A：

- 新增 `memory_relation`、`memory_conflict`、`memory_conflict_member`、`memory_lifecycle_receipt` 四张表。
- `memory_entries` additive 增列 `knowledge_id`、`row_revision`、`knowledge_type`、`conditions`、`lifecycle_eligibility`、`memory_status`、`memory_type`、`evidence_tier`、`last_accessed_at`、`access_count`。
- SQLite 继续是身份、状态、关系、冲突、生命周期回执与当前版本的唯一结构化真源。

### 身份与版本

- `knowledge_id`：可信业务入口生成的 opaque ID，存于 `memory_entries.knowledge_id`；按 `(user_id, knowledge_id)` 唯一。
- `memory_id`：`memory_entries.id` 的 canonical 十进制字符串，必须满足正整数严格 round-trip。
- `version_id`：`v{memory_entries.version}`；`memory_entries.version` 保持内容/索引版本，与既有 Vector snapshot/provider 路径一致。
- `row_revision`：新增 positive integer，仅用于 optimistic CAS；迁移以当时 `version` 值回填，之后所有 optimistic writer 必须改用 `row_revision`。
- 生命周期、访问统计和 soft delete 只推进 `row_revision`，不得推进 `version/version_id`；正文或索引身份变化才同时推进 `version` 与 `row_revision`。
- Repository 回源必须精确匹配 `(user_id, memory_id, version_id)`；Provider 不得自称 current，缺失或旧版本不得被改写为 `v1`。

### Legacy 与结构化投影真源

- 迁移不得从 `memory_entries.content`、行号、哈希或随机值猜测 legacy `knowledge_id`、`knowledge_type`、`conditions` 或 `evidence_tier`。
- 无可信映射的既有 knowledge 标为 `legacy_unmapped`；不得进入 ADR-018、Lifecycle Worker 或 conflict truth。
- `knowledge_type/conditions` 只读新增结构化列；禁止从未冻结的通用 `content` JSON shape 临时解析响应字段。

### SourceAdmission 与 provenance

- Knowledge ingress 必须先验证同用户 `source_events` 且 `admission_decision='allow_extraction'`；`reject/audit_only` 不得写 Knowledge 或升级 evidence tier。
- 继续保持 E 轨对象类型边界：`failed` 只允许 `failure_experience` Knowledge，并以 `evidence_tier=NULL / lifecycle_eligibility='evidence_unmapped'` 保守持久化；`failed + 其他 KnowledgeType`、`partial + Knowledge`、`cancelled/timeout/ignored + Knowledge` 均拒绝。
- `manual_config + success/completed` 映射 `user_explicit_config_latest`；`tool_result + success/completed` 映射 `tool_execution_result`。其他没有已冻结 evidence-tier 真源的合法 Knowledge 为 `evidence_unmapped`。
- 新 Knowledge 与唯一 `is_primary=1` 的 canonical evidence relation 必须在同一 UoW 原子写入；primary relation 指向 `Knowledge.source_event_id`，是 evidence tier 与审计的可恢复 provenance 真源。
- supporting evidence relation 必须 `is_primary=0`，不得替换 primary 或静默重算既有 evidence tier；关系表不存自由文本 evidence。

### Relation、Conflict 与 Lifecycle

- relation endpoint 类型、方向、所有权与 user scope 按批准草案 §3.2 冻结；`derived` 表示 right knowledge 由 left knowledge 派生。
- conflict 主表与成员表同事务写入；`involved_present + ordinal` 无损保存 None/empty/顺序/重复语义；额外 involved 上限 32。
- `conflict_summary` 不接受调用方自由文本，只持久化固定系统码 `conflict:<conflict_type>`。
- Lifecycle Worker 仅消费完整 `eligible` SQLite snapshot；缺失任何必需真源即 fail-closed，不调用 Policy、不造默认值。
- `evaluation_id` 与首次 `evaluated_at` 共同构成 immutable logical evaluation identity；同 ID 重试必须复用首次时间戳。
- receipt fingerprint、replay/conflict、archive semantic dedup、mutation CAS 与 CAS miss 全事务回滚按批准草案 §3.5/§4 冻结。
- Outbox Producer 与业务 mutation 同事务；复用 `aggregate_type='memory'`，只新增事件类型。`hold/reject` 无 Outbox；Consumer 不在本 ADR 范围。

## 安全与实现门禁

- 所有关系、冲突、回执和查询必须先按 trusted user scope 过滤，禁止跨用户存在性侧信道。
- 自由文本正文、conditions 原文、evidence 原文、conflict 原文不得进入 Outbox、日志或审计旁路。
- Migration、Repository、UoW、Worker 与 tests 必须逐项实现批准草案 §14.3；任一既有 writer 仍以 `memory_entries.version` 做 CAS 即 Gate fail。
- 本 ADR 不授权冲突检测算法、Vector cleanup consumer、TTL 常量或不可逆历史版本表。

## 回滚

经后续 ADR 撤销时，先移除所有 Repository/UoW/Worker/IPC 使用点，再以新迁移删除四张新增表、索引和 additive columns。不得修改已发布历史迁移；含业务数据的 downgrade 必须显式 fail-closed 或先完成受审计导出。

## 签署与证据

- D 决策：采用方案 A。
- Reviewer E：PR #122 HEAD `c6ecbae`，`ADR-017: APPROVED`。
- 审查结论：HIGH/MEDIUM open = 0；Repository Baseline Check PASS。
- 证据边界：PR #122 APPROVE 覆盖契约草案并授权进入 canonical write-back；本次 write-back 尚待 Reviewer E 最终一致性确认。Runtime、Migration、L1、L2 与麒麟宿主证据仍须在后续 D8-D Build 单独产生。
