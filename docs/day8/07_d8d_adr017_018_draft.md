# ADR-017/018 草案：关系/冲突/生命周期持久化与只读查询方法（D8-D，FRZ-DB-001 / FRZ-IPC-007 扩展）

- **日期**：2026-09-02
- **状态**：DRAFT — D 决策草案，Reviewer E 待签；正式生效 = NO
- **责任轨道**：D（持久化 / IPC）；E（业务语义、安全与冻结补审）
- **适用范围**：FRZ-DB-001 additive 扩展（ADR-017）；FRZ-IPC-007 additive 扩展（ADR-018）
- **权威依据**：`docs/day8/05_d8d_relation_conflict_lifecycle_contract_plan_v0.1.md`（实际内容 v0.3，PR #101 Reviewer E PASS）、`docs/day8/03_d8b_task_card.md`、`docs/day8/05_d8c_task_card.md`、`docs/day8/day8-e-business-acceptance-v1.md`、ADR-005/006/007/010/013/014、FRZ-DB-001~005、FRZ-IPC-001~007
- **编号占用**：ADR-015/019 已用于 D10-D；ADR-016 由 D7-C 预留；ADR-017/018 由 D8-D 预留

> 本文件只提交可实施的契约决策，不提交 Runtime 实现，不产生 L1/L2/HOST_VERIFIED 事实。Reviewer E 签署前不得据此修改冻结文档或启动依赖实现；签署后须以独立治理 commit 回写 canonical freeze，再进入 D8-D build。

---

## 〇、决策摘要

### ADR-017（DB）推荐方案 A

1. 新增 `memory_relation`、`memory_conflict`、`memory_conflict_member`、`memory_lifecycle_receipt` 四表。
2. `memory_entries` additive 增列 `knowledge_id`、`row_revision`、`knowledge_type`、`conditions`、`lifecycle_eligibility`、`memory_status`、`memory_type`、`evidence_tier`、`last_accessed_at`、`access_count`；`knowledge_type/conditions` 是 ADR-018 受控投影的 SQLite 真源，不从未冻结的正文 JSON shape 临时解析。
3. 冻结身份映射：
   - `knowledge_id` = E 轨 `Knowledge.knowledge_id`，由可信业务入口生成并持久化；
   - `memory_id` = `memory_entries.id` 的 canonical 十进制字符串；
   - `version_id` = `'v' + memory_entries.version`；既有 B 轨 Vector snapshot/provider 已按此生成版本；新增 `memory_entries.row_revision` 专用于 optimistic CAS，生命周期元数据变化不得改变检索版本身份；
   - Repository 回源必须以 `(user_id, memory_id, version_id)` 三元组精确匹配，不允许仅按 `memory_id` 命中旧版本请求。
4. legacy 行无法证明 `knowledge_id` 或 `evidence_tier` 时保持 NULL，由迁移一次性写入 `lifecycle_eligibility='legacy_unmapped'`；禁止从正文 JSON、行号或随机值猜测。
5. Lifecycle Worker 只消费完整 SQLite 快照；任一必需真源缺失即 fail-closed 跳过并记录结构化原因，不调用 Policy、不制造默认值。
6. Outbox Producer 与业务变更同事务写入；继续复用 `aggregate_type='memory'`，新增事件类型，不扩展既有 aggregate CHECK；Consumer 不在本 ADR 实现。

### ADR-018（IPC）推荐方案 A

1. FRZ-IPC-007 新增只读方法 `knowledge.detail`、`conflict.compare`、`lifecycle.status`。
2. 三方法复用 FRZ-IPC-001~006 的长度前缀 JSON、envelope、deadline 与错误码，不修改既有字段。
3. production 默认不注册，状态为 `CANDIDATE / BLOCKED_BY_TRUSTED_IDENTITY_AND_D8D_PERSISTENCE`。
4. ACTIVE 前必须有独立可信宿主身份；仅 `lifecycle.status` 保留声明型 `payload.user_id` 兼容字段，且必须在任何 DB/cache 查询前与可信身份 fail-closed 比对。
5. 跨用户 read 与不存在统一返回 scoped 空结果，不暴露对象是否属于其他用户。

---

# 第一部分 ADR-017：关系、冲突、生命周期与身份映射（FRZ-DB-001 扩展）

## 1. 背景

E 轨已冻结 `Conflict`、`ConflictResolutionPolicy`、`LifecyclePolicy` 的纯业务语义，但明确 `NOT_PERSISTENCE / NOT_EXECUTION`。B 轨 `TruthRecord` 以 `(user_id, memory_id, version_id)` 回源，C 轨候选查询方法以 `memory_id` 调用；当前 SQLite `memory_entries` 无 `knowledge_id`，无法把 E 轨 `knowledge_id` 与 B/C 轨身份稳定关联。

ADR-017 必须同时解决：

- relation/conflict 结构化字段无损持久化；自由文本 `conflict_summary` 采用本 ADR 的安全系统码投影，不持久化调用方原文；
- endpoint ownership 与 scoped read；
- `knowledge_id ↔ memory_id/version_id` production mapping；
- `LifecycleSnapshot` 全字段 SQLite 真源；
- legacy 数据 backfill、downgrade 与 Outbox Producer 边界。

## 2. 身份映射冻结

### 2.1 Canonical mapping

| 业务标识 | SQLite 真源 | 编码规则 | 约束 |
|---|---|---|---|
| `knowledge_id` | `memory_entries.knowledge_id` | 非空 opaque string，不解析、不由模型生成 | 新 knowledge 写必填；`UNIQUE(user_id, knowledge_id)`（仅非 NULL） |
| `memory_id` | `memory_entries.id` | canonical 十进制字符串；禁止前导零、符号、小数 | 必须可严格 round-trip 为正整数 PK |
| `version_id` | `'v' || memory_entries.version` | `^v[1-9][0-9]*$`，例如 `v1` | 当前内容/索引版本；与既有 Vector snapshot/provider 同源 |
| `row_revision` | `memory_entries.row_revision` | SQLite positive integer（不进入 IPC/Vector ID） | 仅用于 optimistic CAS；迁移后所有业务 CAS 改用此列 |

服务端解析 `memory_id` 时必须满足：`parsed > 0` 且 `str(parsed) == input`。`version_id` 必须满足 `^v[1-9][0-9]*$`。不满足时返回 `INVALID_REQUEST`，不得宽松归一化。

Repository 的 canonical resolver：

```text
resolve_knowledge_identity(user_id, memory_id, version_id?)
  -> SELECT memory_entries
       WHERE user_id = :user_id
         AND id = :parsed_memory_id
         AND entry_type = 'knowledge'
         AND knowledge_id IS NOT NULL
         [AND ('v' || CAST(version AS TEXT)) = :version_id]
```

- 跨用户、非 knowledge、未映射、版本不匹配均返回 scoped not-found；
- write/endpoint ownership 校验必须把未映射视为 `INVALID_REQUEST`，不得自动补 ID；
- `knowledge_id` 不是 `memory_id` 的别名，禁止比较两者字符串相等；
- `version_id` 是内容/索引身份，不声明为不可变历史表 ID。本 ADR 不新增知识历史版本表，不宣称已提供旧版本正文回放；`relation_type='version'` 只表达两个独立 knowledge identity 的 supersession 关系。
- 新 knowledge INSERT 由 Repository 写 `version=1,row_revision=1`。未来正文或其他索引身份变更必须经独立受控 API 同时令 `version += 1,row_revision += 1` 并触发索引更新；生命周期/访问统计/软删除只推进 `row_revision`，不得推进 `version`。
- 已核对 `main@6e9394b`（PR #121）的 B 轨 current-version 语义和真实代码路径：`sqlite_vector_snapshot.py` 读取 `memory_entries.version`，`sqlite_vector_provider.py` 输出 `v{source_version}`；SQLite hydration 再以精确 `(user_id,memory_id,version_id)` 构造 `TruthRecord` 并由 SQLite 真源给出 `is_current`。因此本 ADR 保持 `memory_entries.version` 为内容/索引版本，新增独立 `row_revision` 解除 CAS 耦合；Repository 不接受 Provider 自称 current，也不把缺失/陈旧版本改写为 `v1`，且无需修改 `retrieval/` 即与 PR #121 对齐。

### 2.2 Legacy mapping

迁移不得从 `memory_entries.content` JSON、`source_turn_id`、行号哈希或随机 UUID 推导 legacy `knowledge_id`/`evidence_tier`。原因是这些来源不能证明 E 轨身份或证据档位，强行 backfill 会制造 provenance。

对迁移前已有 knowledge 行：

| 字段 | backfill |
|---|---|
| `knowledge_id` | NULL（unmapped） |
| `row_revision` | 迁移时既有 `version` 的正整数值（保持旧 optimistic token 可平滑切换） |
| `lifecycle_eligibility` | `legacy_unmapped` |
| `memory_status` | `is_deleted=1 → removed`；否则 `candidate` |
| `memory_type` | `short_term` |
| `evidence_tier` | NULL（unknown，不伪造为任一六档） |
| `knowledge_type` / `conditions` | NULL（不从既有 `content` JSON 猜测） |
| `last_accessed_at` / `access_count` | NULL |

legacy unmapped 行仍可按既有 `memory_entries.id` 读取/遗忘，但不得进入 relation/conflict endpoint、Lifecycle Worker、ADR-018 详情查询或 B 轨 conflict truth 接线。后续如需认领，必须经独立、可审计的 reconciliation API 在同一事务提供可信 `knowledge_id + evidence_tier` 并把 eligibility 改为 `eligible`；普通 INSERT/UPDATE 无权写 `legacy_unmapped`。

## 3. Schema

### 3.1 `memory_entries` additive columns

```sql
ALTER TABLE memory_entries ADD COLUMN knowledge_id TEXT;
ALTER TABLE memory_entries ADD COLUMN row_revision INTEGER;
UPDATE memory_entries SET row_revision = version WHERE row_revision IS NULL;
ALTER TABLE memory_entries ADD COLUMN knowledge_type TEXT;
ALTER TABLE memory_entries ADD COLUMN conditions TEXT;
ALTER TABLE memory_entries ADD COLUMN lifecycle_eligibility TEXT;
ALTER TABLE memory_entries ADD COLUMN memory_status TEXT;
ALTER TABLE memory_entries ADD COLUMN memory_type TEXT;
ALTER TABLE memory_entries ADD COLUMN evidence_tier TEXT;
ALTER TABLE memory_entries ADD COLUMN last_accessed_at TEXT;
ALTER TABLE memory_entries ADD COLUMN access_count INTEGER;

CREATE UNIQUE INDEX uq_memory_entries_user_knowledge
ON memory_entries(user_id, knowledge_id)
WHERE entry_type = 'knowledge' AND knowledge_id IS NOT NULL;

CREATE INDEX idx_memory_entries_user_status
ON memory_entries(user_id, memory_status);

CREATE INDEX idx_memory_entries_user_type
ON memory_entries(user_id, memory_type);
```

值域：

- `memory_status`：`active/candidate/superseded/deprecated/expired/removed`；
- `memory_type`：`short_term/medium_term/long_term/ephemeral`；
- `evidence_tier`：`user_explicit_config_latest/user_confirmed/tool_execution_result/consistent_behavior_multiple/behavior_inference_single/model_inference`；
- `knowledge_type`：`workflow/case/template/fact/constraint/failure_experience`；
- `lifecycle_eligibility`：`eligible/legacy_unmapped/evidence_unmapped`；
- `version`：既有 positive integer，正式定义为内容/索引版本；`version_id` 由 Repository 严格编码为 `v{version}`；
- `row_revision`：NULL（仅迁移过程中）或 positive integer；迁移完成后所有行均非空；
- `access_count`：NULL 或 `>= 0`。

SQLite 既有表无法直接追加跨列 conditional NOT NULL CHECK。迁移采用「nullable additive column + 同事务 `row_revision=version` backfill + legacy backfill + DB trigger/Repository 双门禁」；在对外恢复 writer 前必须确认 `row_revision IS NULL` 行数为 0：

- 迁移对当时存在的 knowledge PK 一次性写 `lifecycle_eligibility='legacy_unmapped'`；迁移完成后触发器禁止 INSERT/普通 UPDATE 把任何行写成 `legacy_unmapped`；
- 所有 entry_type 的新 INSERT 都必须写 positive `row_revision`（初始为 1），所有 optimistic writer 都只以该列比较/递增；`version` 不再承担 CAS；
- 新 INSERT 后 `entry_type='knowledge'` 时，`knowledge_id/row_revision/knowledge_type/memory_status/memory_type/lifecycle_eligibility` 必须非空，且 `version >= 1,row_revision >= 1`；`conditions` 允许 NULL，但只能由通过 Domain 校验的 `Knowledge.conditions` 写入；eligibility 为 `eligible` 时 `evidence_tier` 必须非空，为 `evidence_unmapped` 时 `evidence_tier` 必须 NULL；
- legacy 行只允许保持 `legacy_unmapped`，或由专用 reconciliation UoW 一次性改为 `eligible`；任何其他转换拒绝；
- 非 knowledge 行仅允许 knowledge 专属列（`knowledge_id/knowledge_type/conditions/lifecycle_eligibility/memory_status/memory_type/evidence_tier/last_accessed_at/access_count`）为 NULL；既有 `version` 与新增 `row_revision` 对所有 entry_type 始终 required positive；
- `is_deleted=1` 与 `memory_status!='removed'` 的新写入拒绝；进入 `removed` 时同步置 `is_deleted=1`。迁移后 `memory_status` 是生命周期最终真源，`is_deleted` 仅为兼容字段。

触发器/Repository 必须覆盖 direct SQL 负路径：迁移后任意新行缺/非法 `row_revision`、新 knowledge 缺 `knowledge_id/knowledge_type`、`version/row_revision < 1`、伪造 `legacy_unmapped`、`eligible + evidence_tier=NULL`、`evidence_unmapped + evidence_tier!=NULL` 均 MUST FAIL。迁移后现有 `soft_delete_memory_entry` 等 optimistic write 必须从 `version` CAS 切换到 `row_revision`；遗漏任何 writer 视为 Gate fail。`knowledge.detail.knowledge_type/conditions` 只读取上述结构化列；禁止用 `json.loads(memory_entries.content).get(...)` 作为这两个响应字段的真源。

### 3.1.1 `evidence_tier` 唯一 ingress mapping

Repository 不接受 payload/LLM/Knowledge Domain 直接指定 `evidence_tier`。它只读取 `Knowledge.source_event_id` 指向的同用户 `source_events` 真源，并先执行不可绕过的准入谓词：事件必须存在、属于同一 `user_id`，且 `admission_decision == 'allow_extraction'`；缺失、跨用户、未知 decision、`reject` 或 `audit_only` 均 fail-closed 拒绝 Knowledge 写入，不得降级成 `evidence_unmapped`，更不得升级为 eligible evidence。只有通过该门禁后才按下表继续派生：

| source_events 真源 | evidence_tier | eligibility |
|---|---|---|
| `admission_decision='allow_extraction'` 且 `source_type='manual_config'` 且 `source_business_status IN ('success','completed')` | `user_explicit_config_latest` | `eligible` |
| `admission_decision='allow_extraction'` 且 `source_type='tool_result'` 且 `source_business_status IN ('success','completed')` | `tool_execution_result` | `eligible` |
| `admission_decision='allow_extraction'` 且 `source_business_status IN ('failed','cancelled','timeout','ignored')` | 不落 knowledge | 写入拒绝 |
| `admission_decision='allow_extraction'` 的其他来源/状态组合 | NULL | `evidence_unmapped` |

`user_confirmed/consistent_behavior_multiple/behavior_inference_single/model_inference` 当前没有已冻结的持久化证明，不得由 D8-D 猜测。未来启用必须通过新的跨轨契约明确可信事实与聚合窗口。`evidence_unmapped` knowledge 可持久化为 candidate，但不得进入 Lifecycle Worker 或 ConflictResolutionPolicy 自动裁决。`admission_reason_code/consent_scope/sensitivity/is_sensitive_matched/should_ignore/payload_security_checked` 继续由已冻结 SourceAdmission 产生并审计；D8-D 不重新解释它们，也不得绕过 `admission_decision` 的最终门禁。

新 Knowledge 的 provenance 采用单一结构化真源：在验证并读取上述 `source_events` 行后，Repository 必须在**同一 UoW**写入 Knowledge 及一条 canonical `memory_relation(relation_type='evidence', is_primary=1, left=Knowledge.knowledge_id, right=Knowledge.source_event_id)`；任一写入失败则整体回滚。`evidence_tier` 派生与后续审计只回查这条 primary relation 指向的同用户 `source_events` 行，`knowledge.detail.evidence[]` 则投影 primary 与后续受控追加的 supporting relations；不允许另从 `content` 或 Domain 自由文本 `evidence` 恢复 provenance。幂等重放复用既有 canonical relation，不重复造边；每个 knowledge 恰有一条 primary evidence relation，同一 `(user_id, knowledge_id, source_event_id)` 也只允许一条 evidence relation。

### 3.2 `memory_relation`

```sql
CREATE TABLE memory_relation (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             TEXT    NOT NULL,
    relation_id         TEXT    NOT NULL,
    relation_type       TEXT    NOT NULL,
    left_endpoint_type  TEXT    NOT NULL,
    left_endpoint_id    TEXT    NOT NULL,
    right_endpoint_type TEXT    NOT NULL,
    right_endpoint_id   TEXT    NOT NULL,
    is_primary          INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT    NOT NULL,
    CHECK (relation_type IN ('version','evidence','derived')),
    CHECK (left_endpoint_type IN ('knowledge','source_event')),
    CHECK (right_endpoint_type IN ('knowledge','source_event')),
    CHECK (is_primary IN (0, 1)),
    CHECK (relation_type = 'evidence' OR is_primary = 0),
    CHECK (left_endpoint_id <> right_endpoint_id OR left_endpoint_type <> right_endpoint_type),
    UNIQUE (user_id, relation_id)
);

CREATE UNIQUE INDEX uq_memory_relation_canonical_evidence
ON memory_relation(user_id, left_endpoint_id, right_endpoint_id)
WHERE relation_type = 'evidence'
  AND left_endpoint_type = 'knowledge'
  AND right_endpoint_type = 'source_event';

CREATE UNIQUE INDEX uq_memory_relation_primary_evidence
ON memory_relation(user_id, left_endpoint_id)
WHERE relation_type = 'evidence'
  AND left_endpoint_type = 'knowledge'
  AND right_endpoint_type = 'source_event'
  AND is_primary = 1;
```

固定 endpoint 组合：

| relation_type | left | right | 方向语义 |
|---|---|---|---|
| `version` | knowledge | knowledge | left 被 right supersede；right 为较新 identity |
| `derived` | knowledge | knowledge | right 由 left 派生 |
| `evidence` | knowledge | source_event | left knowledge 由 right event 支撑 |

其他组合一律 `INVALID_REQUEST`。Repository 必须在同一事务内验证所有 endpoint 属于 `user_id`：knowledge 经 `memory_entries.knowledge_id`，source_event 经 `source_events.event_id`。本表不提供任何自由文本 evidence 列；证据只通过 `relation_type='evidence'` 的结构化 source_event endpoint 表达。Knowledge ingress 建立的 `is_primary=1` relation 是 `Knowledge.source_event_id → SQLite provenance` 的唯一 canonical 真源；后续独立、受控的 provenance API 只能增加 `is_primary=0` supporting evidence，不能替换 primary 或据此静默重算既有 `evidence_tier`。

索引：

- `(user_id, left_endpoint_type, left_endpoint_id)`；
- `(user_id, right_endpoint_type, right_endpoint_id)`；
- version 关系对同一 left identity 最多一个 current successor：部分唯一索引 `(user_id, left_endpoint_id) WHERE relation_type='version' AND left_endpoint_type='knowledge'`。

### 3.3 `memory_conflict`

```sql
CREATE TABLE memory_conflict (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id               TEXT    NOT NULL,
    conflict_id           TEXT    NOT NULL,
    conflict_type         TEXT    NOT NULL,
    left_knowledge_id     TEXT    NOT NULL,
    right_knowledge_id    TEXT    NOT NULL,
    conflict_summary      TEXT    NOT NULL,
    involved_present      INTEGER NOT NULL,
    resolution_status     TEXT    NOT NULL,
    is_auto_resolvable    INTEGER NOT NULL DEFAULT 0,
    detected_at           TEXT    NOT NULL,
    resolution_strategy   TEXT,
    resolution_confidence REAL,
    resolved_at           TEXT,
    resolved_by           TEXT,
    winner_id             TEXT,
    decision_action       TEXT,
    reason_code           TEXT,
    created_at            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL,
    CHECK (left_knowledge_id <> right_knowledge_id),
    CHECK (conflict_type IN ('contradiction','temporal_inconsistency','source_conflict','preference_conflict','scope_ambiguity')),
    CHECK (resolution_status IN ('detected','analyzing','resolved_auto','resolved_manual','deferred','unresolvable')),
    CHECK (decision_action IS NULL OR decision_action IN ('keep_left','keep_right','coexist','defer','reject')),
    CHECK (is_auto_resolvable IN (0,1)),
    CHECK (involved_present IN (0,1)),
    CHECK (resolution_confidence IS NULL OR (resolution_confidence >= 0 AND resolution_confidence <= 1)),
    UNIQUE (user_id, conflict_id)
);
```

Repository 在落库前复验：

- left/right knowledge 均存在且属于同一 user；
- `resolved_auto/resolved_manual` 必须有 `resolved_at + resolved_by`；
- `keep_left/keep_right` 必须有 winner，且 winner 等于对应侧；其他 action 的 winner 必须为 NULL；
- `conflict_summary` 不接受调用方自由文本：Repository 根据 `conflict_type` 生成固定系统码 `conflict:<conflict_type>`（例如 `conflict:contradiction`），只含 allowlisted ASCII；Domain 中传入的自由文本 summary 不落库、不入日志、不入 Outbox；
- 不实现冲突检测算法，只持久化上游已判定 Domain 与 Policy Decision。

索引：`(user_id, left_knowledge_id)`、`(user_id, right_knowledge_id)`、`(user_id, resolution_status)`。

### 3.4 `memory_conflict_member`

```sql
CREATE TABLE memory_conflict_member (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT    NOT NULL,
    conflict_id  TEXT    NOT NULL,
    knowledge_id TEXT    NOT NULL,
    ordinal      INTEGER NOT NULL,
    role         TEXT    NOT NULL,
    created_at   TEXT    NOT NULL,
    CHECK (ordinal >= 0),
    CHECK (role IN ('left','right','involved')),
    UNIQUE (user_id, conflict_id, ordinal),
    FOREIGN KEY (user_id, conflict_id)
      REFERENCES memory_conflict(user_id, conflict_id)
      ON DELETE CASCADE
);
```

left 固定 ordinal=0，right 固定 ordinal=1，额外 involved 从 2 开始保持 Domain 输入顺序。`involved_present=0` 表示 Domain 值为 None；`involved_present=1` 且无 involved 行表示空列表；有行时按 ordinal 无损保存顺序、重复项以及与 left/right 重合项。仅 `(user_id, conflict_id, ordinal)` 唯一，不对 knowledge_id 去重。Repository 在 ADR 持久化边界把 involved 数量限制为 0..32，超限 `INVALID_REQUEST`；范围内保证 None/empty/duplicate/order round-trip。主表与成员表同一事务写入；成员 knowledge ownership 全量复验。

### 3.5 `memory_lifecycle_receipt`

```sql
CREATE TABLE memory_lifecycle_receipt (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id               TEXT    NOT NULL,
    evaluation_id         TEXT    NOT NULL,
    evaluation_fingerprint TEXT   NOT NULL,
    knowledge_id          TEXT    NOT NULL,
    memory_entry_id       INTEGER NOT NULL,
    evaluated_revision    INTEGER NOT NULL,
    version_id            TEXT    NOT NULL,
    policy_config_hash    TEXT    NOT NULL,
    evaluated_at          TEXT    NOT NULL,
    action                TEXT    NOT NULL,
    reason_code           TEXT    NOT NULL,
    target_memory_type    TEXT,
    target_memory_status  TEXT,
    applied               INTEGER NOT NULL,
    created_at            TEXT    NOT NULL,
    CHECK (evaluated_revision >= 1),
    CHECK (action IN ('promote','demote','expire','archive_request','hold','reject')),
    CHECK (applied IN (0,1)),
    UNIQUE (user_id, evaluation_id)
);

CREATE UNIQUE INDEX uq_lifecycle_archive_once
ON memory_lifecycle_receipt(user_id, knowledge_id, version_id, action, reason_code)
WHERE action = 'archive_request';
```

`evaluation_id` 由可信 scheduler/CLI 为一次逻辑评估生成并在重试时复用，不得由 LLM 生成。`evaluated_at` 是该 logical evaluation identity 的 immutable input：首次尝试生成后，scheduler/CLI 对同一 `evaluation_id` 的所有重试必须复用首次时间戳，不得用重试墙钟时间重算。`evaluation_fingerprint` = SHA-256(JCS(`user_id, knowledge_id, memory_entry_id, evaluated_revision, version_id, evaluated_at, policy_config_hash`))；其中 `version_id` 是评估时由 `memory_entries.version` 编码出的 `vN`。同 `(user_id,evaluation_id)` 且同 `evaluated_at`/同 fingerprint 返回首次 receipt，不重复 Policy/mutation/outbox；同 evaluation_id 携带新的 `evaluated_at` 或任何其他 fingerprint 输入变化均直接 `INVALID_REQUEST`。同一 knowledge/version/action/reason 的 archive request 只产生一次 receipt/outbox；后续 scheduler 重扫返回首次 disposition receipt。

## 4. Lifecycle execution

### 4.1 Snapshot eligibility

Worker 只选择：

```text
entry_type='knowledge'
AND knowledge_id IS NOT NULL
AND knowledge_type IS NOT NULL
AND version >= 1
AND row_revision >= 1
AND lifecycle_eligibility='eligible'
AND memory_status IS NOT NULL
AND memory_type IS NOT NULL
AND evidence_tier IS NOT NULL
AND EXISTS (exactly one same-user is_primary=1 evidence relation
            whose source_event admission_decision='allow_extraction')
```

`confidence_score` 复用 `memory_entries.confidence`；`created_at/updated_at/access_count/last_accessed_at` 均从同一 SQLite row 读取。`policy_config_hash` 对 PolicyConfig 的字段名排序 JCS 计算（timedelta 统一为整数微秒）；PolicyConfig 本身不含秘密。快照构造与状态更新在同一 UoW 内重新校验 row revision，防止 stale decision 覆盖并发更新。

### 4.2 Decision mapping

| action | 原子持久化 | Outbox |
|---|---|---|
| promote/demote | `memory_type=target_memory_type`，`row_revision += 1`；`version`/`version_id` 不变 | `memory.lifecycle.changed` |
| expire | `memory_status='expired'`，`row_revision += 1`；`version`/`version_id` 不变 | `memory.lifecycle.changed` |
| archive_request | 业务行不变；写 receipt | `memory.lifecycle.archive_requested` |
| hold/reject | 业务行不变；仅写 receipt | 无 Outbox |

mutation SQL 固定为以下两类（列名不可动态来自外部输入）：

```sql
-- promote / demote
UPDATE memory_entries
SET memory_type = :target_memory_type,
    row_revision = :evaluated_revision + 1,
    updated_at = :now
WHERE user_id = :user_id
  AND id = :memory_entry_id
  AND row_revision = :evaluated_revision
  AND version = :evaluated_version;

-- expire
UPDATE memory_entries
SET memory_status = 'expired',
    row_revision = :evaluated_revision + 1,
    updated_at = :now
WHERE user_id = :user_id
  AND id = :memory_entry_id
  AND row_revision = :evaluated_revision
  AND version = :evaluated_version;
```

固定事务顺序：先查 `(user_id,evaluation_id)` replay/conflict → 读 row + 构造 snapshot → 调用 Policy 一次 → mutation action 执行 CAS → 插入 receipt → 必要时入 Outbox → commit。仅 `rowcount=1` 时 mutation action 才能插入 receipt + Outbox；`rowcount=0` 必须回滚本次所有副作用，重新读取一次并返回 structured CAS miss，禁止用旧 decision 重试 UPDATE。archive/hold/reject 不执行 row UPDATE，以 receipt 唯一键保证 replay 幂等；archive 另由部分唯一索引阻止不同 evaluation_id 重复产生同一 disposition。

Conflict reason_code 为 NULL（尚无 Decision）或 E 轨六值：`invalid_input/cross_user_blocked/scope_distinguishable/evidence_tier_priority/latest_explicit_config_wins/same_tier_undecidable`。Lifecycle receipt reason_code 只允许 E 轨十三值：`invalid_input/candidate_requires_confirmation/superseded_no_auto_recovery/deprecated_no_auto_recovery/expired_pending_archive/removed_cold_data/expired_cold_data/age_threshold_reached/inactivity_threshold/low_usage_threshold/confidence_decay_threshold/credible_evidence_threshold/no_threshold_met`。未知 reason_code 拒绝持久化。

removed/expired/superseded/deprecated/candidate 不得自动恢复 active。PolicyConfig 由调用方显式注入；ADR 不冻结 7/30/90 天常量。Worker 提供可调用函数与简单 CLI/scheduler seam，不引入新进程框架。

## 5. Outbox Producer

继续使用既有 `aggregate_type='memory'`，不修改 aggregate CHECK。新增事件类型：

- `memory.relation.changed`
- `memory.conflict.changed`
- `memory.lifecycle.changed`
- `memory.lifecycle.archive_requested`

payload 仅含结构化标识和决策元数据：`user_id`、`memory_id`/`version_id`/`knowledge_id`、`relation_id`/`conflict_id`、`action`、固定 `reason_code`、`occurred_at`。禁止包含 `memory_entries.content`、用户原文、`conflict_summary` 或证据正文。

Producer 与业务 mutation 同事务提交。Consumer 不在 ADR-017 范围；未知事件由当前 router fail-closed 重试/Dead Letter，不得误报已同步 Vector/FTS。TD-D4D-001/TD-033 保持 Open，关闭需 D9D consumer + 真实全链路证据。

## 6. Migration / rollback

- migration 必须接实现时真实 `alembic heads`，禁止形成多 head；
- upgrade 顺序：add nullable columns → backfill safe lifecycle fields/eligibility/content version → create tables/indexes/triggers → enable Repository write gate；
- upgrade 不把 legacy NULL `knowledge_id/evidence_tier` 伪造为合法值；
- downgrade 前执行 data-loss guard：四张新表任一有数据，或新增列存在非 legacy-safe 数据时拒绝；
- 允许回滚时按依赖顺序删除 lifecycle receipt → member → conflict → relation → indexes/triggers → additive columns；
- rollback 不修改既有正文、FTS5 与 D7D/D10D 表。

## 7. ADR-017 rejected alternatives

1. `knowledge_id == memory_id == memory_entries.id`：拒绝，混淆 opaque Domain ID 与 SQLite PK。
2. 从 `content` JSON backfill `knowledge_id/evidence_tier`：拒绝，正文不是身份/证据真源且会制造 provenance。
3. 独立 `memory_lifecycle` 表：拒绝，增加 JOIN 与双真源风险。
4. 本版新增 `knowledge_versions`：拒绝扩大范围；`memory_entries.version`/`version_id=vN` 只表达当前内容/索引身份，历史正文版本需后续独立 ADR。
5. Outbox 新 aggregate_type：拒绝，无需为事件路由扩展既有 DB CHECK。

---

# 第二部分 ADR-018：知识详情、冲突对比、生命周期状态只读 IPC（FRZ-IPC-007 扩展）

## 8. Common contract

- 方法均为 read-only，不要求 idempotency_key，不产生业务副作用；
- envelope、长度前缀 JSON、`request_id/trace_id/deadline_ms`、`status/data/server_ts`、错误码沿用 FRZ-IPC-001~006；
- `payload` 必须是 object，未知字段拒绝（`extra=forbid`）；
- 三方法的 Repository `user_id` 唯一来源均为 `RequestContext.user_id`；validation/test profile 也必须显式注入 synthetic trusted identity，不允许降级为“无 trusted user”；
- 可信身份校验必须先于 DB 查询、缓存查询和 scoped lookup；`lifecycle.status.payload.user_id` 仅为 D8-C 兼容声明且保持必填，必须与 RequestContext.user_id 相等，不一致 `INVALID_REQUEST`；另外两方法不接受 payload.user_id；
- 业务 read 的 unknown/cross-user/unmapped/version-stale 均返回成功 scoped empty；非法类型/格式返回 `INVALID_REQUEST`；内部异常返回 `INTERNAL_ERROR` 且不泄漏 ID/正文。
- 所有 opaque ID 长度 1..128 UTF-8 bytes；`conflict_id/relation_id/knowledge_id/source_event_id` 超限拒绝。`memory_id/version_id` 另按 canonical 规则校验。
- 可展示自由文本仅 `conditions`：投影前执行系统 `IpcTextProjectionGate`（NFKC、拒绝控制字符、UTF-8 最大 256 bytes、复用 `pipeline.sensitive.detect_sensitivity`；任一敏感命中或异常即返回空数组并置 `conditions_redacted=true`）。调用方不得用布尔标志自证脱敏，Gate 不记录输入文本。

## 9. `knowledge.detail`

请求 payload：

```json
{
  "memory_id": "42",
  "version_id": "v3",
  "include_evidence": true,
  "include_conditions": true,
  "relation_limit": 25,
  "after_relation_created_at": null,
  "after_relation_id": null
}
```

- `memory_id` 必填；`version_id` 可选，提供时必须精确匹配；
- `include_evidence/include_conditions` 默认 true；
- `relation_limit` 为 strict integer（bool/float/string 均拒绝），默认 25，范围 1..25；relation cursor 两字段必须同时缺失或同时提供；排序固定为 `memory_relation.created_at ASC, relation_id ASC`，cursor 为 exclusive；
- scoped not-found 响应：`data = {"found": false}`（保持 FRZ-IPC-006 `data` 为 object）。

成功 `data`：

```json
{
  "found": true,
  "memory_id": "42",
  "version_id": "v3",
  "knowledge_id": "kn_opaque",
  "knowledge_type": "fact",
  "memory_status": "active",
  "memory_type": "short_term",
  "evidence_tier": "tool_execution_result",
  "conditions": [],
  "conditions_redacted": false,
  "evidence": [],
  "relation_ids": [],
  "next_relation_cursor": null,
  "conflict_state": "none",
  "created_at": "2026-09-02T00:00:00+00:00",
  "updated_at": "2026-09-02T00:00:00+00:00"
}
```

字段转换固定为：

| 字段 | include=false | 原值 None/空白 | 原值非空 |
|---|---|---|---|
| `conditions` | `[]`，redacted=false | `[]`，redacted=false | 通过 IpcTextProjectionGate → `[value]`；失败 → `[]`，redacted=true |
| `evidence` | `[]` | `[]` | 只投影当前 relation page 中 `memory_relation(type=evidence)` 的 `{relation_id, source_event_id, is_primary}` 结构化对象；绝不返回 Domain `evidence` 自由文本 |

`relation_ids[]` 与 `evidence[]` 是同一个 relation page 的两种受控投影：Repository 查询所有以当前 knowledge 为端点的 relation，按上述稳定顺序读取 `relation_limit+1`；`relation_ids[]` 返回本页全部 relation ID，`evidence[]` 仅返回其中以当前 knowledge 为 left endpoint 的 evidence relation。`next_relation_cursor` 只在过滤后确有下一条 relation 时返回 `{"created_at":"...","relation_id":"..."}`。客户端用 continuation 可无遗漏取得全部 relation/evidence；禁止只取前 N 条后静默丢弃，禁止重复或跳项。`include_evidence=false` 时 evidence 固定 `[]`，但 relation page/cursor 仍按相同顺序推进，避免同一请求形状产生不同 cursor 语义。

分页同时受真实编码 byte budget 约束：handler 按稳定顺序逐项加入 `relation_ids/evidence`，每加入一条 relation 后都调用既有 `gateway.protocol.encode()` 对**完整 response envelope**试编码。该函数对 UTF-8 JSON body 执行 `MAX_MSG_LEN=65536` 校验，返回值另含 4-byte length prefix；只有真实编码成功的条目才进入当前页。若下一条会超限，则当前页在上一条结束，并以最后已返回 relation 写 `next_relation_cursor`；不得截断字段、吞掉 relation 或返回假成功。若单条最大 128-byte ID relation 仍不能装入仅含基础详情的空页，则返回 `INTERNAL_ERROR` 并记录仅含结构化 ID 的审计事件。L1 必须以最大长度 ID 和大量 relation/evidence 证明：每个 JSON body 均不超过 65536 bytes，byte-budget 提前分页后 continuation 可无遗漏、无重复取回全部记录。

输出是受控投影：`knowledge_type/conditions` 分别只读 `memory_entries.knowledge_type/conditions`，关系证据只读 `memory_relation`；不直接返回或解析 `memory_entries.content`，不返回用户原文、Domain 自由文本 evidence、敏感 evidence 正文、内部 row dump 或其他用户标识。

## 10. `conflict.compare`

请求 payload：

```json
{
  "memory_id": "42",
  "version_id": "v3",
  "include_resolved": false,
  "limit": 25,
  "after_detected_at": null,
  "after_conflict_id": null
}
```

- `memory_id` 必填；`version_id` 可选精确匹配；`include_resolved` 默认 false；
- `limit` 为 strict integer（bool/float/string 均拒绝），默认 25，范围 1..25；
- cursor 两字段必须同时缺失或同时提供；排序固定 `detected_at DESC, conflict_id ASC`，cursor 为 exclusive；
- scoped not-found 或无冲突：`data = {"candidates": [], "next_cursor": null}`；仅过滤后真实存在下一项时返回下一 cursor。

成功 `data.candidates[]` 每项固定投影：

```json
{
  "conflict_id": "cf_opaque",
  "conflict_type": "contradiction",
  "resolution_status": "detected",
  "conflict_summary": "conflict:contradiction",
  "left_memory_id": "42",
  "right_memory_id": "57",
  "member_memory_ids": ["42", "57"],
  "decision_action": null,
  "winner_memory_id": null,
  "reason_code": null,
  "detected_at": "2026-09-02T00:00:00+00:00",
  "resolved_at": null
}
```

顶层响应固定为 `{"candidates": [...], "next_cursor": {"detected_at": "...", "conflict_id": "..."}|null}`。`conflict_summary` 只能是 ADR-017 固定系统码；普通调用方不返回 `knowledge_id`、`resolved_by` 或内部 evidence。Repository 限制单 conflict 最多 32 个 involved 输入（None/空/重复语义仍按 §3.4 无损保存）；超限写入拒绝。

分页同时受条数和真实编码 byte budget 约束：Repository 读取 `limit+1` 后，handler 按稳定顺序逐项投影，每加入一项都用既有 `gateway.protocol.encode()` 对完整 response envelope 试编码；该函数限制 UTF-8 JSON body 为 `MAX_MSG_LEN=65536`，4-byte length prefix 不计入 body 上限。只有真实编码成功的项才接受。若下一项会超限，则当前页在上一项结束并把最后已返回项写入 `next_cursor`，下一请求从该 cursor 后继续，禁止丢项/截断字段/返回假成功。若单项在已冻结 128-byte ID、32 involved 上限下仍不能装入空页，返回 `INTERNAL_ERROR` 并记录仅含结构化 ID 的审计事件；L1 必须证明最大长度 ID × 32 members 的单项可装入，以及 25 项因 byte budget 提前分页后能继续取得全部记录。

## 11. `lifecycle.status`

请求 payload：

```json
{
  "user_id": "declared-user-for-compatibility",
  "memory_id": "42",
  "memory_status": "active",
  "limit": 50,
  "after_memory_id": null
}
```

- `user_id` 为 D8-C 兼容声明字段且保持必填；不得作为可信身份，必须与 RequestContext.user_id 相等；
- `memory_id`、`memory_status`、`after_memory_id` 可选；
- `limit` 默认 50，范围 1..100；
- `limit`/cursor 均 strict；`memory_id` 与 `after_memory_id` 互斥；排序固定为 `memory_entries.id ASC`；`after_memory_id` 为 exclusive cursor；
- scoped empty：`data = {"items": [], "next_after_memory_id": null}`。

每个 `items[]`：

```json
{
  "memory_id": "42",
  "version_id": "v3",
  "memory_status": "active",
  "memory_type": "short_term",
  "evidence_tier": "tool_execution_result",
  "last_accessed_at": null,
  "access_count": 0,
  "created_at": "2026-09-02T00:00:00+00:00",
  "updated_at": "2026-09-02T00:00:00+00:00"
}
```

legacy/evidence-unmapped lifecycle-ineligible 行不出现在列表中。仅过滤后真实存在下一项时返回 `next_after_memory_id`，否则为 null；指定 `memory_id` 的单项查询永不返回 next cursor。

## 12. Activation gate

默认 registry 不注册 ADR-018 三方法，返回 `UNSUPPORTED_METHOD`。仅 validation/test profile 可显式注册用于 L1。production ACTIVE 必须同时满足：

1. ADR-017/018 经 D 决策 + Reviewer E 签署并完成 canonical freeze 回写；
2. D8-D Migration/Repository/Worker/handler 实现通过 L0/L1；
3. RequestContext 已接独立 trusted host user identity，且 mismatch 在任何查询/cache 前 fail-close；
4. C 轨调用 payload 与本 ADR compatibility test 通过；
5. 麒麟 VM L2 验证真实 UDS 调用、跨用户 scoped read、重启后持久化与未注册默认态；
6. 未满足项在能力矩阵保持 `CANDIDATE/PARTIAL/UNVERIFIED`，不得写 `HOST_VERIFIED`。

## 13. ADR-018 rejected alternatives

1. 以 payload.user_id 直接授权查询：拒绝，声明值不是 trusted identity。
2. 跨用户对象返回 `INVALID_REQUEST/NOT_FOUND` 差异：拒绝，会泄漏可枚举对象存在性。
3. 直接返回 SQLite row/content JSON：拒绝，违反最小投影与原文隔离。
4. ADR 签署即默认注册 production handler：拒绝，持久化、身份映射与 L2 尚未完成。

---

## 十四、实现影响与测试门禁

### 14.1 允许修改（ADR 签署并完成 freeze write-back 后）

- `memory-service/db/schema.py`
- `memory-service/db/repositories.py`
- `memory-service/db/uow.py`
- 新 Alembic migration（接真实 head）
- 新 `memory-service/service/lifecycle_worker.py`
- 新 ADR-018 handler / explicit registry seam
- `memory-service/tests/test_relation_conflict_lifecycle_d8d.py`

### 14.2 禁止修改

- E 轨 `domain/conflict.py`、`domain/knowledge.py`、`domain/enums.py`
- `service/conflict_resolution_policy.py`、`service/lifecycle_policy.py`
- `retrieval/`、`embedding/`、`providers/`、既有 Gateway 方法语义
- 冲突检测算法、Vector cleanup consumer、TTL 数值常量

### 14.3 L0/L1

- migration single-head、upgrade/downgrade data-loss guard、schema/metadata 一致；
- canonical ID 正/负/边界测试（`1/v1` 合法，`01/+1/v01/v0` 拒绝），并断言 lifecycle row_revision 变化不改变 `memory_entries.version`/`version_id`；迁移把旧 version 复制到 row_revision，所有既有 CAS writer 改用 row_revision；
- direct SQL 门禁：新行缺 knowledge_type、伪造 `legacy_unmapped`、eligibility/evidence 不一致 MUST FAIL；legacy/evidence-unmapped 不进入 Worker/IPC/conflict truth；
- evidence_tier ingress：仅 `allow_extraction` 可继续映射；manual_config/tool success 两条正路；`tool_result + success + reject`、`manual_config + completed + audit_only`、失败/取消均拒绝写 Knowledge；其余已准入来源为 evidence_unmapped；payload/LLM 不得覆盖；
- 新 Knowledge 与唯一 `is_primary=1` canonical evidence relation 同 UoW 原子写入，失败整体回滚；重复 `(user,knowledge,source_event)` 不造第二条；evidence tier/audit 只由 primary relation 回查同用户 source_event，supporting relation 不静默改 tier；
- relation endpoint type/方向/ownership；relation 无自由文本列；conflict member 的 None/empty/duplicate/order round-trip 与 33 项超限拒绝；
- conflict summary 输入 Sentinel 不出现在 SQLite、日志、Outbox、IPC，持久化/响应只能是固定 `conflict:<type>`；
- LifecycleDecision 六 action、receipt replay/conflict、archive semantic dedup、两个并发 evaluation CAS 仅一方提交、CAS miss 全事务回滚、removed/expired 不恢复；同 evaluation_id + 同首次 evaluated_at 为 replay，同 evaluation_id + 新 evaluated_at 为 conflict，scheduler retry 复用 logical timestamp；
- Outbox Producer 同事务原子性与 payload 零正文；hold/reject 不产生 Outbox；
- ADR-018 payload extra-forbid、synthetic trusted identity 必填、mismatch 先于查询、scoped empty object、strict limit/cursor 与 `gateway.protocol.encode()` 65536-byte JSON body 边界；
- knowledge_type/conditions 结构化列真源、conditions/evidence 投影矩阵、IpcTextProjectionGate 敏感 Sentinel/控制字符/257-byte 拒绝；knowledge.detail 最大 ID × 大量 relation/evidence 的 byte-budget 提前分页及 continuation 全量无遗漏/无重复；
- `git diff --check`、ruff F/E9、compileall、敏感信息扫描、全量 pytest 不回退。

### 14.4 L2（签署/实现后，当前 NOT_TESTED）

- 麒麟 V11 `alembic upgrade head` 与 `.schema` 对照；
- 真实 SQLite relation/conflict/lifecycle 写读与服务重启一致；
- 真实 UDS 三方法、默认未注册态与 explicit validation profile；
- trusted host identity mismatch fail-closed、跨用户 scoped empty；
- Outbox 行真实产生；Consumer/Vector 同步仍按 TD 状态如实报告。

---

## 十五、签署与冻结流程

1. 本草案 PR：D 决策草案 + Reviewer E 审查；状态始终为“正式生效 = NO”。
2. Reviewer E 若 REWORK：只按最小返工集修订本草案，不夹带 Runtime 实现。
3. Reviewer E 明确 APPROVE 后：新增/更新 `docs/adr/017-*.md`、`docs/adr/018-*.md`，同一治理阶段回写 FRZ-DB-001、FRZ-IPC-007 与 `docs/adr/README.md`；该 commit 不夹带实现。
4. canonical write-back 后再次请求 Reviewer E 最终确认；最终 APPROVE + behind=0 后合并治理 PR。
5. 治理 PR 合并后，D8-D build 分支从最新 main 创建/同步并执行；不得从草案分支直接混入实现。

## 十六、当前限制

- 当前仅为文档决策草案，无 Runtime 代码、L1、L2 或 HOST_VERIFIED 事实；
- knowledge immutable history 不在本 ADR，`version_id='v' + memory_entries.version` 仅为当前内容/索引身份，独立 `memory_entries.row_revision` 仅为 CAS；
- legacy unmapped knowledge 不自动认领；
- Outbox Consumer、Vector cleanup、冲突检测、TTL 数值均不在范围；
- ADR-018 production handler 默认不注册。
