# D8-D 知识关系/冲突/生命周期持久化契约规划（草案 v0.1）

- **编制日期**：2026-09-01
- **编制人**：opencode（D 轨开发 Agent）
- **状态**：DRAFT v0.1 — 待 D 决策 + Reviewer E 确认后转正式契约（ADR-017/018 流程）
- **对照基线**：main @ `79411f1`（PR #98 D6-D 合并后）；`docs/day8/day8-e-business-acceptance-v1.md`（D8E，Conflict/ConflictResolutionPolicy/LifecyclePolicy 均 `NOT_PERSISTENCE / NOT_EXECUTION`）；`docs/day8/03_d8b_task_card.md`（D8B，SQLite 为关系/状态/版本/冲突真源）；`deliverables/D4_DB_INITIAL_DESIGN_FREEZE_20260817.md`（FRZ-DB-001）；`deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-007）；`docs/adr/013-source-events-table.md`、`014-event-ingest-method.md`（D6-D 契约，编号占用先例）；`docs/day10/16_d10d_forget_contract_plan_v0.3.md`（D10-D 契约，ADR-015/016 预留）；Day11 跨轨需求清单（D-REQ-02/03/04，P0）

---

## 〇、前置依据（跨轨清单与既有语义）

**Day11 跨轨需求清单（2026-09-01，D 轨 P0）**：

| 需求 | 内容 | 优先级 |
|---|---|---|
| D-REQ-02 | 实现 D8D `memory_relation` 持久化（Schema/Migration/Repository/UoW/Outbox/query API/user isolation/version relation/evidence relation） | P0 |
| D-REQ-03 | 实现 D8D `memory_conflict` 持久化（conflict 表/candidates/conflict type/resolution status/involved refs/selected winner/resolution/evidence/timestamps/user isolation） | P0 |
| D-REQ-04 | 实现生命周期持久化与执行 Worker（memory_status 持久化/TTL/promotion/demotion/expired/superseded/deprecated/removed/Outbox/index sync；candidate→active→superseded/deprecated/expired/removed；SQLite 原子提交；B 检索同步；重启后状态一致；不依赖遗留布尔字段作为最终真源） | P0/P1 |

**既有语义（消费真源，不复制）**：
- **E 轨 Domain**：`domain/conflict.py::Conflict`（D3 §5.4 字段落地）、`domain/knowledge.py::Knowledge`（13 结构化字段 + `memory_status`/`source_event_id`）、`domain/enums.py`（`MemoryStatus` 六值 / `ConflictType` 五值 / `ResolutionStatus` 六值 / `KnowledgeType` 六值，均冻结）
- **E 轨 Policy**：`service/conflict_resolution_policy.py::ConflictResolutionPolicy`（`ConflictSide`/`ConflictDecision`：action=keep_left/keep_right/coexist/defer/reject + reason_code + winner_id）、`service/lifecycle_policy.py::LifecyclePolicy`（`LifecycleSnapshot`/`LifecycleAction` 六值：promote/demote/expire/archive_request/hold/reject + `PolicyConfig`）——均明确 `NOT_PERSISTENCE / NOT_EXECUTION`，**持久化与执行由 D 轨承担**
- **B 轨 D8B**：`retrieval/contracts.py` 的 `RetrievalFilter`/`RetrievalCandidate` 已消费 `memory_status`/`relation_ids`/`version_ids`/`required_relation_ids`/`conflict_state`；`retrieval/fusion.py::TruthRecord` 为 SQLite 回源真值接缝；明确「B 轨不实现 D 轨 `memory_relation`/`memory_conflict` 表、Migration、Repository、Outbox 或事务策略」

---

## 一、背景与目标（台账 R4x / D8-D）

1. **关系真源缺失**：B 轨 D8B 已按 `relation_ids` 做确定性硬过滤，但默认主线缺 D 轨关系真源表——目前只能验证结构化真值接缝，**不能声明完整数据库链路**（D8B 任务卡「已知跨轨依赖」）。
2. **冲突真源缺失**：E 轨 `Conflict` Domain + `ConflictResolutionPolicy` 已冻结业务语义（含 `resolution_status` 六值与 `DecisionAction` 五值），但**不落库**；D8E 明确 `NOT_PERSISTENCE`。B 轨检索需「unresolved conflict 默认排除、fail-closed」——无持久化则无法可靠回源。
3. **生命周期状态未持久化**：E 轨 `LifecyclePolicy` 仅输出 `LifecycleAction` 计划（`NOT_EXECUTION`）；`memory_status` 六值目前只在 D7D 偏好版本表有承载，**知识/通用记忆无状态真源**；D8B 检索要求 `memory_status` 硬过滤 + 唯一 current。

**交付边界（D 轨）**：`memory_relation` + `memory_conflict` 表 + 生命周期状态承载 + 执行 Worker（消费 LifecyclePolicy 决策）+ 迁移 + Repository + 查询 API + 测试。不接 Vector 清理（TD-033 未完成），不改 IPC envelope。

---

## 二、范围与禁止修改范围

### 允许修改
- `memory-service/db/schema.py`（新增 `memory_relation` / `memory_conflict` 表；生命周期状态承载按 D-3 决策——`memory_entries` 增列或独立表；既有表定义不动）
- `memory-service/db/repositories.py`（新增关系/冲突/生命周期 Repository 函数）
- `memory-service/db/uow.py`（如需事务封装，复用现有模式）
- `migrations/versions/YYYYMMDD_add_memory_relation_conflict.py`（新增迁移，ADR-007 命名，对齐当前唯一 Alembic head）
- `memory-service/service/`（可选新增 lifecycle 执行 Worker，消费 E 轨 `LifecyclePolicy` 决策；不复制/重建 Policy）
- 新增测试 `memory-service/tests/test_relation_conflict_lifecycle_d8d.py`
- 契约文档（本文档 + ADR-017/018 + 冻结文档回写）

### 禁止修改（红线）
- 不修改冻结 FRZ-IPC-001~007 既有字段/错误码/envelope（如需 IPC 方法走 ADR-018 新增）
- 不修改 FRZ-DB-001 既有 5 张表定义（新表/新列为新增，走 ADR-017）
- 不修改 `pipeline/`、`providers/`、`security/`、`service/candidate_governance.py`、`service/conflict_resolution_policy.py`、`service/lifecycle_policy.py`、`gateway/`、`embedding/`、`retrieval/`、`observability/` 既有实现
- **不实现冲突检测算法**（contradiction/temporal_inconsistency 判定阈值属 B/上游能力，HD-SCHEMA-04；本版只持久化已判定/已决策结果）
- **不重写/复制** E 轨 Domain/Policy（`Conflict`/`ConflictResolutionPolicy`/`LifecyclePolicy`/枚举均复用）
- 不接 Vector 清理（TD-033 未完成）；不把 WSL/Mock 结果当宿主证据；L2 未执行不写「已支持」

---

## 三、输入契约（复用 E 轨 Domain，不复制真源）

### 3.1 复用字段（Conflict，D3 §5.4 / `domain/conflict.py`）
| 字段 | 类型 | 说明 |
|---|---|---|
| `conflict_id` | NonEmptyStr | 冲突唯一 ID |
| `user_id` | NonEmptyStr | **隔离键，禁止模型生成**（D3 §7.10） |
| `conflict_type` | ConflictType | 五值枚举（contradiction/temporal_inconsistency/source_conflict/preference_conflict/scope_ambiguity） |
| `left_knowledge_id` / `right_knowledge_id` | NonEmptyStr | 冲突双方（no_self_conflict 校验，D3 §5.4） |
| `conflict_summary` | NonEmptyStr | 冲突摘要（**脱敏**，见 §四.2 红线） |
| `resolution_status` | ResolutionStatus | 六值枚举（detected/analyzing/resolved_auto/resolved_manual/deferred/unresolvable） |
| `is_auto_resolvable` | bool | DEFERRED 判定标准待 B/E；本版仅持久化 |
| `detected_at` | AwareDatetime | 检测时间 |
| `involved_knowledge_ids` | Optional[List[str]] | 多知识冲突 ID |
| `resolution_strategy` | Optional[str] | DEFERRED，不冻结为枚举 |
| `resolution_confidence` | Optional[ConfidenceScore] | [0,1] 边界校验 |
| `resolved_at` / `resolved_by` | Optional | 已解决时必填（D3 §5.4 resolution_consistency） |

### 3.2 复用决策结果（ConflictResolutionPolicy，`service/conflict_resolution_policy.py`）
| 字段 | 类型 | 说明 |
|---|---|---|
| `decision_action` | DecisionAction | keep_left / keep_right / coexist / defer / reject |
| `reason_code` | str | 固定 reason_code（evidence_tier_priority / latest_explicit_config_wins / same_tier_undecidable / scope_distinguishable / cross_user_blocked / invalid_input 等） |
| `winner_id` | Optional[str] | 仅 keep_left / keep_right 非空（获胜侧 knowledge_id） |

> **边界**：`ConflictDecision` 为 E 轨 Policy 输出，D 轨**只持久化结果**，不重算；冲突检测（生成 Conflict）属 B/上游能力，本版 Repository 提供写入接口供上游调用。

### 3.3 复用生命周期输入（LifecyclePolicy，`service/lifecycle_policy.py`）
| 字段 | 类型 | 说明 |
|---|---|---|
| `LifecycleSnapshot` | model | knowledge_id/user_id/memory_type/memory_status/evidence_tier/confidence_score/access_count/last_accessed_at/created_at/updated_at |
| `LifecycleAction` | enum | promote / demote / expire / archive_request / hold / reject |
| `PolicyConfig` | model | promote/demote/expire/archive 阈值（全部必填，无默认值；正式冻结值由部署侧注入） |

> **边界**：D 轨执行 Worker **消费** LifecyclePolicy 决策（`evaluate(snapshot, now, config) → LifecycleAction`），将 action 持久化为 memory_status 变化 + 记录原因；不修改 Policy 本身、不把 7/30/90 天等阈值硬编码为业务常量。

### 3.4 复用知识字段（Knowledge，`domain/knowledge.py`）
`knowledge_id` / `user_id` / `knowledge_type`（六值）/ `memory_status`（六值）/ `source_event_id`（关联 `source_events.event_id`，D6-D）/ `primary_category` / 13 结构化字段（conditions/evidence/steps/...，全 Optional）。

---

## 四、DB 表设计（新增 2~3 表，FRZ-DB-001 扩展）

### 4.1 `memory_relation`（知识关系真源）

```sql
CREATE TABLE memory_relation (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             TEXT    NOT NULL,          -- 隔离键，禁止模型生成
    relation_id         TEXT    NOT NULL,          -- 关系唯一 ID（宿主生成）
    relation_type       TEXT    NOT NULL,          -- version / evidence / derived（D-1 冻结值域）
    left_knowledge_id   TEXT    NOT NULL,          -- 关系左侧（如被派生/旧版本）
    right_knowledge_id  TEXT    NOT NULL,          -- 关系右侧（如派生源/新版本）
    evidence            TEXT,                      -- 结构化引用（R3 系统可信来源，非正文；可空）
    created_at          TEXT    NOT NULL,
    CHECK (relation_type IN ('version','evidence','derived'))
);
```

**索引**：`UNIQUE(user_id, relation_id)`（计划级唯一 + 跨用户隔离）；`(user_id, left_knowledge_id)`；`(user_id, right_knowledge_id)`。

**语义**：`relation_type='version'` 表达版本派生（right 由 left 演进）；`'evidence'` 表达证据来源（right 由 left 支撑，如 knowledge↔source_event 的证据链，left/right 可为 knowledge_id 或 event_id 命名空间区分——D-1 冻结）；`'derived'` 表达业务派生。**relation_id 不泄露到普通 UI explanation**（B 轨要求）。

### 4.2 `memory_conflict`（冲突真源）

```sql
CREATE TABLE memory_conflict (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id               TEXT    NOT NULL,          -- 隔离键，禁止模型生成
    conflict_id           TEXT    NOT NULL,
    conflict_type         TEXT    NOT NULL,          -- 五值（D3 §5.6）
    left_knowledge_id     TEXT    NOT NULL,
    right_knowledge_id    TEXT    NOT NULL,
    conflict_summary      TEXT,                      -- 脱敏摘要（红线：不含用户原文/敏感正文）
    resolution_status     TEXT    NOT NULL,          -- 六值（D3 §5.6）
    is_auto_resolvable     INTEGER NOT NULL DEFAULT 0,
    detected_at           TEXT    NOT NULL,
    resolution_strategy   TEXT,                      -- DEFERRED，不冻结枚举
    resolution_confidence REAL,                      -- [0,1]
    resolved_at           TEXT,
    resolved_by           TEXT,                      -- 解决执行方标识，禁止模型生成
    winner_id             TEXT,                      -- 决策结果：获胜侧 knowledge_id
    decision_action       TEXT,                      -- keep_left/keep_right/coexist/defer/reject
    reason_code           TEXT,                      -- 固定 reason_code（E 轨 Policy 输出）
    created_at            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL,
    CHECK (conflict_type IN ('contradiction','temporal_inconsistency','source_conflict','preference_conflict','scope_ambiguity')),
    CHECK (resolution_status IN ('detected','analyzing','resolved_auto','resolved_manual','deferred','unresolvable')),
    CHECK (decision_action IN ('keep_left','keep_right','coexist','defer','reject'))
);
```

**索引**：`UNIQUE(user_id, conflict_id)`；`(user_id, left_knowledge_id)`；`(user_id, right_knowledge_id)`；`(user_id, resolution_status)`（B 轨「未解决默认排除」快速路径）。

**红线**：`conflict_summary` **不落用户正文原文**（只落脱敏摘要/结构化引用；敏感正文零残留——验收含 Sentinel 扫描，参照 D10-D §九 审计零正文模式）。

### 4.3 生命周期状态承载（D-3 决策，二选一）

**方案 A（推荐）**：`memory_entries` 增 nullable `memory_status` 列（六值 CHECK）+ `last_accessed_at`/`access_count`（可空观察事实）+ 索引 `(user_id, memory_status)`。
- 优点：与 B 轨 `memory_status` 检索直接对齐；避免第三张表 JOIN；D8B 回源复核即查即用
- 需走 ADR-017 变更控制（FRZ-DB-001 扩展）

**方案 B**：独立 `memory_lifecycle` 表（knowledge_id 主键 + 状态快照）。
- 优点：不动既有 memory_entries
- 缺点：检索需 JOIN；状态真源与正文分离增加一致性风险；D8B 回源路径变长

> **决策倾向**：方案 A（memory_entries 增列）。知识版本链（`version_id` 检索）是否复用 D7D `memory_items/memory_versions` 模式或独立 `knowledge_versions` 表，列入 D-1/D-3 待 D/E 确认（D8B 已消费 `version_id` 但 D 轨无知识版本真源）。

### 4.4 迁移
- 文件：`migrations/versions/YYYYMMDD_add_memory_relation_conflict.py`（ADR-007 命名，独立 revision）
- 版本链：`... → 20260831_add_source_events（D6-D）→ YYYYMMDD_add_memory_relation_conflict`（**以实现时 `alembic heads` 真实链路为准，禁止多 head**，参照 D6-D/D10-D 先例）
- downgrade：DROP TABLE（新表无既有数据依赖）

---

## 五、关键决策点（待 D 决策 / Reviewer E 确认）

| # | 决策点 | 推荐方案 | 备选 | 理由 |
|---|---|---|---|---|
| D-1 | `relation_type` 值域与知识版本链 | **version/evidence/derived 三值**；知识版本链复用 D7D `memory_items/memory_versions` 模式（独立 `knowledge_versions`）或 `memory_relation(relation_type='version')` 承载，待 D/E 冻结 | 更多 relation_type / JSON 列 | 对齐 B 轨 `relation_ids`/`version_id` 消费；版本真源须唯一 current（D7D 先例） |
| D-2 | conflict 落库字段 | **E 轨 Conflict 全字段 + Decision 结果列**（decision_action/reason_code/winner_id） | 仅存 Conflict 不含 Decision | 决策结果必须可审计回源（D8E 要求「E conflict policy 可以产生可持久化决策结果」） |
| D-3 | 生命周期状态承载 | **方案 A：`memory_entries.memory_status` 增列** | 独立 `memory_lifecycle` 表 | 与 B 轨检索直接对齐、无 JOIN；ADR-017 扩展 |
| D-4 | 执行 Worker 范围 | **本版实现消费 LifecyclePolicy 的执行 Worker**（PROMOTE/DEMOTE/EXPIRE/ARCHIVE_REQUEST → memory_status 原子变更 + 记录）；TTL 阈值经 PolicyConfig 注入 | 仅持久化不执行（登记 TD） | D-REQ-04 要求「执行 Worker」；PolicyConfig 注入避免硬编码 |
| D-5 | 查询 API 形态 | **Repository 函数优先**（`get_relations`/`get_conflicts`/`get_lifecycle_status`，user 隔离 + fail-closed）；IPC 方法（knowledge.detail/conflict.compare/lifecycle.status）若需走 ADR-018，对齐 C 轨 D8-C 候选（PR #97） | 仅 Repository | 契约先行本版冻结 Repository 边界；IPC 形态与 C 轨 D8-C 对齐后由 ADR-018 立项 |
| D-6 | 与 B 轨检索接线 | **本版提供 SQLite 回源真值查询**（`resolve_conflict_state(knowledge_id)` 等），B 轨 `TruthRecord` 接缝消费；unresolved conflict 默认排除由 B 轨 filter 执行 | 本版不接 | D8B 已声明「SQLite 为真源、B 不实现 D 轨表」→ 接线是 D8D 验收项 |
| D-7 | `conflict_summary` 脱敏 | **只落脱敏摘要/结构化引用，禁止用户原文**（Sentinel 验收，参照 D10-D） | 落原文 | 安全红线（D3 §4.1 原文隔离 + 冲突摘要可能含敏感正文） |
| D-8 | Outbox 接线范围 | **本版不接 Outbox consumer**（TD-D4D-001 保持 Open）；关系/冲突/生命周期变更如产生事件，仅登记 TD | 接 Outbox | Outbox consumer 接线统一在 D9D（D-REQ-05）处理 |

---

## 六、错误语义（复用冻结域，不新增错误码）

| 场景 | 行为 | 映射 |
|---|---|---|
| 跨用户访问 relation/conflict/lifecycle | 拒绝 | `INVALID_REQUEST`（Repository user 过滤 + UNIQUE(user_id, x_id)） |
| 关系/冲突不存在 | 返回空结果（真实） | 正常路径，不假装 |
| 非法 relation_type / conflict_type / resolution_status | 拒绝写入 | `INVALID_REQUEST`（Schema CHECK + Repository 校验） |
| 冲突双方同 knowledge_id | 拒绝 | `INVALID_REQUEST`（D3 §5.4 no_self_conflict，Domain 已校验，D 不重复实现但落库前复验） |
| SQLITE_BUSY | `DatabaseLockedError` 降级 | FR-DB-003 既有语义 |
| 生命周期状态非法流转（如 removed→active） | fail-closed 拒绝 | `INVALID_REQUEST`（E 轨 LifecyclePolicy 已 fail-closed；D 执行层不得绕过） |

---

## 七、测试规划

### L0
- `python3 -m compileall memory-service/db memory-service/service memory-service/tests/test_relation_conflict_lifecycle_d8d.py`
- Ruff `--select F,E9`；`git diff --check`

### L1（pytest，WSL2）
| 用例 | 覆盖 |
|---|---|
| relation 写入 + 按 left/right/user 查询 + 跨用户 fail-close | 关系真源 |
| relation_type 非法值拒绝；version relation 唯一 current 校验（如采纳） | 关系校验 |
| conflict 全生命周期落库：detected → resolved_auto/manual（含 Decision 结果列） | 冲突持久化 |
| unresolved conflict 查询（B 轨排除路径：`resolution_status != resolved_*`） | 冲突消费 |
| cross-user conflict 不可构造（UNIQUE(user_id, conflict_id) + Repository 隔离） | 隔离 |
| `conflict_summary` 不含用户原文（Sentinel 扫描） | 安全 |
| lifecycle：`memory_status` 六值落库 + 非法值拒绝；执行 Worker 消费 LifecyclePolicy 决策 → 状态原子变更（promote/demote/expire/archive_request/hold） | 生命周期 |
| removed/expired 不自动恢复 active（fail-closed，复用 E 轨 Policy 断言） | 红线 |
| 迁移 upgrade/downgrade 往返 + schema 对照（含新表 CHECK/索引） | 迁移 |
| 重启后状态一致（落库行仍可查） | 持久性 |

### L2（麒麟 VM，人工操作清单，不声称已执行）
- `alembic upgrade head` + `.schema` 对照（memory_relation/memory_conflict 表 + 索引 + CHECK）
- 真实 CLI/Repository 调用：relation/conflict 写入 + 查询 + 跨用户拒绝
- lifecycle 状态变更后检索结果符合预期（B 轨回源）
- 服务重启后数据存在

---

## 八、技术债关联

| TD | 处置 |
|---|---|
| TD-031（多 current 顺序依赖，D8B 提及） | 本版通过 version relation / current 唯一约束闭合（D-1 冻结后） |
| TD-D4D-001（Outbox consumer 未接线） | 保持 Open（D-8：本版不接） |
| TD-033（Vector bridge 重编译） | 保持 Open（不接 Vector 清理） |
| 新增候选 TD | 知识版本链独立表（若 D-1 决策走 memory_relation 则无）；lifecycle 执行 Worker 阈值配置化（PolicyConfig 注入，默认值登记） |

---

## 九、签署与落地流程

1. **本文件（契约规划 v0.1）入库** ← 本 PR：跨轨需求 D-REQ-02/03/04 前置
2. **ADR-017**（memory_relation/memory_conflict 表 + memory_entries.memory_status 扩展，FRZ-DB-001 扩展）+ **ADR-018**（如需 IPC 查询方法，FRZ-IPC-007 扩展，对齐 C 轨 D8-C 候选）提交 D 决策
3. Reviewer E（谢嘉然）签署 ADR
4. 回写冻结文档（FRZ-DB-001 / FRZ-IPC-007）
5. 任务卡定稿 → 代码实现（Schema/Migration/Repository/执行 Worker/查询 API/L1 测试）
6. 实现 + L0/L1 → PR → 麒麟 L2 证据 → 台账 R4x（D8-D）勾选

---

## 十、待澄清缺口

1. **D-1 relation_type 值域 + 知识版本链**：`version` relation 与 D7D `memory_items/memory_versions` 模式的关系——知识版本是否复用 D7D 表模式（独立 `knowledge_versions`）还是以 `memory_relation(relation_type='version')` 承载？B 轨 `version_id` 检索需唯一 current 真源
2. **D-5 IPC 方法形态**：knowledge.detail / conflict.compare / lifecycle.status（C 轨 D8-C 候选，PR #97）是否在本版 ADR-018 立项为受控 handler，还是仅 Repository API
3. **生命周期执行 Worker 触发方式**：轮询（复用 OutboxWorker 调度）vs 事件驱动；TTL 阈值默认值（PolicyConfig 注入，不硬编码）
4. **conflict 检测上游**：本版只持久化已判定/已决策结果；B 轨冲突检测（HD-SCHEMA-04）时序与 D8D 写入口对齐
