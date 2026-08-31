# Day8E 业务验收与跨轨接线说明（v1）

> 文档任务编号：`day8-e-05-business-acceptance-doc-v1`
> 轨道：E（记忆业务 / 安全 / 数据集与业务指标）
> `runtime_required=false`（本批次为 E 轨纯 Python Business Core，不涉及银河麒麟 Runtime 系统依赖）
> 文档版本：v1；生成日期：2026-08-27

## 1. 范围与验证状态声明（先读）

- 本批次（day8-e-01 ~ day8-e-04 + 本文档）为 **E 轨纯 Python Business Core**，全部为无状态、纯函数式业务决策与 Domain 结构化承载，**不涉及 systemd、UDS、D-Bus、SDK、权限、进程等系统依赖**。
- **L2（银河麒麟 Runtime Test）对本批次为 N/A**，本文档 **不标 HOST_VERIFIED**。D8-A（知识抽取）的 HOST_VERIFIED/E4 证据为既有证据条目（`D8-A-KNOWLEDGE-EXTRACTION`，tested_commit `95fcad8`），本文档仅引用其结论，不重复、不替代其证据。
- **L3（干净快照全链路验收）状态：`PENDING_INTEGRATION`**。Day8E Business Core 尚未与 D 轨（SQLite/TTL/Outbox）、B 轨（冲突候选发现/检索）、C 轨（QML/Hook）实际接线，且未在银河麒麟真实环境完成端到端验收，不得推进 L3，不得宣称 Day8 整体集成完成。
- 本批次**不声明** D 轨 SQLite/TTL Worker、B 轨冲突检测/检索、C 轨 QML 已完成。
- 未执行的性能验收、麒麟 Runtime 验收或 QML 验收**一律不写成 PASS**。

## 2. Day8E 四项代码/测试交付及业务边界

| 原子任务 | 交付文件 | 职责边界标记 | 业务边界（明确不做） |
|---|---|---|---|
| `day8-e-01` 知识 Domain 结构化承载 | `memory-service/domain/knowledge.py`（新增 13 个 `Optional[str]` 结构化字段）、`memory-service/service/candidate_governance.py::_build_knowledge`（1:1 同名直传）；测试 `memory-service/tests/test_knowledge_domain_mapping_d8e.py` | Domain/治理承载（`NOT_PERSISTENCE` / `NOT_EXTRACTION`） | 不写 SQLite/Vector/FTS5；不实现抽取算法；不生成/覆盖 `source_event_id`；不做冲突消解、遗忘执行、检索 |
| `day8-e-02` 冲突六档裁决策略 | `memory-service/service/conflict_resolution_policy.py`（`EvidenceTier` 六值、`DecisionAction` 五值、`ConflictResolutionPolicy`）；测试 `memory-service/tests/test_conflict_resolution_policy_d8e.py` | 纯业务裁决策略（`NOT_PERSISTENCE` / `NOT_DETECTION`） | **不实现冲突候选发现、语义相似度、向量相似度、contradiction/temporal_inconsistency 检测阈值**（属 B/上游能力，HD-SCHEMA-04）；不写 SQLite `memory_conflict` 持久化/事务/Outbox/Vector/FTS5 |
| `day8-e-03` 生命周期策略 | `memory-service/service/lifecycle_policy.py`（`LifecycleAction` 六值、`PolicyConfig`、`LifecycleSnapshot`、`LifecyclePolicy`）；测试 `memory-service/tests/test_lifecycle_policy_d8e.py` | 纯业务决策计划（`NOT_PERSISTENCE` / `NOT_EXECUTION`） | **不写 SQLite、不执行存储迁移/删除/归档/Vector 重建**；不依赖 `is_active` / `is_outdated` / `should_decay` 过渡字段做最终决策（`LifecycleSnapshot` 不含这些字段，`extra="forbid"` 拒绝传入） |
| `day8-e-04` 跨阶段业务回归 | `memory-service/tests/test_knowledge_conflict_lifecycle_flow_d8e.py` | 跨阶段业务回归（Day6 准入 → Day8A 抽取 → Day5 治理 → Day8E 冲突 → Day8E 生命周期，真实业务函数调用，无 Mock） | 不验证 SQLite/Vector/FTS5/IPC/systemd/D-Bus/麒麟 Runtime；不验证 A/B/C/D 轨实现细节、语义相似度检测阈值或持久化执行 |

上述四项交付共同形成 Day8E Business Core 的完整业务闭环：**结构化承载 → 冲突裁决 → 生命周期决策 → 跨阶段一致性回归**，但均终止于"决策/计划/承载"层，所有写库、检测、执行与检索均属其他轨道后续接线（见 §8）。

## 3. 六类知识结构化字段与 Candidate→Domain 无损承载

### 3.1 六类知识（权威来源：`domain/enums.py::KnowledgeType`，六值冻结）

`fact` / `workflow` / `case` / `template` / `constraint` / `failure_experience`

与 `providers/extraction_provider.py::KnowledgeCategory`（六值 `Literal`）逐字对齐，与架构 TABLE 21（FactMemory / ProcedureMemory→workflow / CaseMemory / TemplateMemory / ConstraintMemory / FailureMemory）语义一致。`primary_category` 为开放业务分类标签，**不得替代** `knowledge_type`。

### 3.2 13 个结构化字段按类别归属（`domain/knowledge.py`，全部 `Optional[str]`，默认 None，向后兼容）

| 类别 | 字段 |
|---|---|
| 通用 | `conditions`（适用条件）、`evidence`（R3 系统可信来源证据，非 LLM 自述） |
| workflow | `steps`（步骤/流程）、`expected_result`（期望结果） |
| case | `problem`（问题）、`outcome`（结果）、`reproducible`（是否复现） |
| template | `template_body`（模板正文）、`parameters`（参数） |
| constraint | `priority`（优先级） |
| failure_experience | `failure_reason`（失败原因）、`avoid_condition`（避免条件）、`alternative`（替代方案） |

### 3.3 Candidate→Domain 无损承载关系

- `KnowledgeCandidate`（`extraction_provider.py`，六类结构化字段 v0.2）→ `domain.Knowledge`：`candidate_governance.py::_build_knowledge` 对 13 个字段 **1:1 同名直传、无转换、无改写**（`knowledge_id`/`user_id`/`source_event_id` 等核心字段仍走既有规则：`user_id` 来自 `ctx`、`source_event_id` 直接相等、`knowledge_type` 六值同源）。
- `content_summary` 仍仅承载 `fact` 文本（可检索摘要），**不拼接结构化字段伪装无损承载**。
- 治理输出恒定约束（B2 保持）：`memory_status` 恒为 `MemoryStatus.CANDIDATE`、`requires_embedding=True`（候选将来需嵌入），候选不因高 confidence 或高证据档位自动提升。
- 无损承载一致性由 `test_knowledge_domain_mapping_d8e.py` 以字段进出 Domain 一致性测试验证。

## 4. 六档冲突优先级与 Tool>Model 规则

### 4.1 EvidenceTier 六档（`conflict_resolution_policy.py`，声明顺序即优先级 1→6，数值越小优先级越高）

| 档位 | 枚举成员 | 取值字符串 | 语义 |
|---|---|---|---|
| Tier 1 | `USER_EXPLICIT_CONFIG_LATEST` | `user_explicit_config_latest` | 用户最新显式配置（最高） |
| Tier 2 | `USER_CONFIRMED` | `user_confirmed` | 用户明确确认 |
| Tier 3 | `TOOL_EXECUTION_RESULT` | `tool_execution_result` | 真实 Tool 执行结果 |
| Tier 4 | `CONSISTENT_BEHAVIOR_MULTIPLE` | `consistent_behavior_multiple` | 多次一致行为 |
| Tier 5 | `BEHAVIOR_INFERENCE_SINGLE` | `behavior_inference_single` | 单次行为推断 |
| Tier 6 | `MODEL_INFERENCE` | `model_inference` | 模型自身推测（最低，**不得覆盖 Tier 1–5 任何来源**） |

与 `docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md` §7.5、`MEMORY_BUSINESS_SCHEMA_V0.1.md` §3.4 六档定义一致。

### 4.2 DecisionAction 五值与 reason_code 固定集合

`DecisionAction` 五值：`keep_left` / `keep_right` / `coexist` / `defer` / `reject`。

`ConflictResolutionPolicy.resolve()` 的固定 reason_code 集合（6 值，不拼接任何用户正文）：

| reason_code | 触发语义 |
|---|---|
| `evidence_tier_priority` | 跨档证据优先级决胜（高档保留，低档被替代） |
| `latest_explicit_config_wins` | 仅 Tier 1 同档，按可信时间事实 `recorded_at` 取最新显式配置 |
| `scope_distinguishable` | 两侧作用域均可区分且不等 → COEXIST 共存 |
| `same_tier_undecidable` | 同档且无法依据已冻结规则决胜 → DEFER（不得用 confidence/自由推理强行决胜） |
| `cross_user_blocked` | 跨 `user_id` 输入 → REJECT（fail-closed） |
| `invalid_input` | 非 `ConflictSide` 输入 → REJECT（fail-closed 前置） |

### 4.3 可审查示例

- **真实 Tool 事实高于模型自述**：左 `evidence_tier=tool_execution_result`（Tier 3，真实 Tool 成功结果）vs 右 `evidence_tier=model_inference`（Tier 6）→ `KEEP_LEFT` / reason `evidence_tier_priority`，winner 为 Tier 3 侧（B1 门控在冲突层的落地：真实 Tool 事实永不输给模型自述）。
- **用户显式来源高于模型推测**：左 `user_explicit_config_latest`（Tier 1）vs 右 `model_inference`（Tier 6）→ `KEEP_LEFT` / reason `evidence_tier_priority`（Tier 6 不可能覆盖 Tier 1–5，代码逻辑自动保证）。
- **Tier 1 同档时间决胜**：两侧均为 `user_explicit_config_latest` 且 `recorded_at` 均为可信时间事实（`AwareDatetime`，非模型生成）→ 较新侧 `KEEP_LEFT`/`KEEP_RIGHT` / reason `latest_explicit_config_wins`；时间相等或任一侧缺失 → `DEFER` / `same_tier_undecidable`。
- **同档非 Tier 1 不可决**：两侧同为 `consistent_behavior_multiple`（Tier 4）→ `DEFER` / `same_tier_undecidable`，不依据 confidence 强行决胜。
- **作用域可区分**：两侧 scope 均非 None 且不等 → `COEXIST` / `scope_distinguishable`。
- **跨用户 fail-closed**：`left.user_id != right.user_id` → `REJECT` / `cross_user_blocked`。

### 4.4 B1 门控（Tool 事实优先，抽取层）

- rules 路径按 Tool 状态分派：`success` → 六类成功知识（置信度 0.85，架构 TABLE 17 真实 Tool 成功=高）；`failure` → **仅** `failure_experience`（0.6，中可信）；`cancelled` / `timeout` / `partial` → skip（不形成成功知识）。
- LLM 路径无真实 success Tool evidence 时整体拒绝并 audit，reason 固定为 `no-success-tool-evidence`（`extraction_provider.py`）。
- 事件级准入（`security/source_admission.py`）：`SourceAdmissionDecision` 三值 `allow_extraction`/`audit_only`/`reject`；`ExtractionKind` 三值 `preference`/`success_knowledge`/`failure_experience`；`failed` → 仅 `{FAILURE_EXPERIENCE}`，`cancelled`/`timeout` → REJECT。

## 5. MemoryType 与 MemoryStatus 两维度区分及生命周期决策语义

### 5.1 两维度正交

- **MemoryType（记忆分层，`pipeline/schemas.py` 四值冻结）**：`short_term` / `medium_term` / `long_term` / `ephemeral`。表示记忆存放的分层/时效分类，经 E/D 统一语义后与生命周期节律协同，但本身**不是**生命周期状态。
- **MemoryStatus（生命周期状态，`domain/enums.py` 六值冻结，唯一优先真源）**：`active` / `superseded` / `deprecated` / `expired` / `removed` / `candidate`。**无 `ARCHIVED` 取值**。

两个维度正交：一个知识条目可同时具有 `memory_type=medium_term` 与 `memory_status=candidate`（如 Day8E 治理输出恒 CANDIDATE 的候选条目），不可互相替代表述。

### 5.2 promote / demote / expire / archive_request 语义（`lifecycle_policy.py`）

| LifecycleAction | 取值 | 语义 | 输出 |
|---|---|---|---|
| `PROMOTE` | `promote` | 提升记忆分层（仅 `short_term→medium_term`、`medium_term→long_term`） | 只输出目标 `MemoryType` 计划（`target_memory_type`），不直接写库 |
| `DEMOTE` | `demote` | 降级记忆分层（仅 `long_term→medium_term`、`medium_term→short_term`） | 只输出目标 `MemoryType` 计划，不直接写库 |
| `EXPIRE` | `expire` | 过期 | 只输出目标 `MemoryStatus` 计划（当前固定 `target_memory_status=EXPIRED`），不直接执行删除 |
| `ARCHIVE_REQUEST` | `archive_request` | **给 D 轨持久化层的处置请求（disposition/request）** | `target_memory_type`/`target_memory_status` 均为 None；**不新增 `MemoryStatus.ARCHIVED`**（`domain/enums.py` 六值冻结，不修改） |
| `HOLD` | `hold` | 保持现状（无可执行动作或需人工/确认信号） | — |
| `REJECT` | `reject` | fail-closed 拒绝（非法输入） | — |

- 决策以 `memory_status` 为**唯一优先生命周期真源**（`LifecycleSnapshot` 必须包含 `memory_status`；`is_active`/`is_outdated`/`should_decay` 过渡字段不在快照内，`extra="forbid"` 传入即 ValidationError）。
- fail-closed：CANDIDATE/SUPERSEDED/DEPRECATED/EXPIRED/REMOVED 不因高 confidence 或高证据档位自动恢复 ACTIVE；模型单独推测（`EvidenceTier.MODEL_INFERENCE`）不得触发自动长期化（`PolicyConfig` 校验 `promote_required_evidence_tier` 不得为 `MODEL_INFERENCE`）。
- 全部决策返回固定 `action` + 固定 reason_code，不拼接任何用户正文。

### 5.3 LifecycleAction 与 reason_code 权威集合（13 值）

| reason_code | 对应动作 |
|---|---|
| `invalid_input` | REJECT |
| `removed_cold_data` | ARCHIVE_REQUEST（REMOVED 终态冷数据） |
| `expired_cold_data` | ARCHIVE_REQUEST（已过期且超过 `archive_after_expired`） |
| `expired_pending_archive` | HOLD（已过期未达归档期） |
| `candidate_requires_confirmation` | HOLD（CANDIDATE 需确认，不自动提升） |
| `superseded_no_auto_recovery` | HOLD（SUPERSEDED 不自动恢复） |
| `deprecated_no_auto_recovery` | HOLD（DEPRECATED 不自动恢复） |
| `credible_evidence_threshold` | PROMOTE（可信证据阈值满足） |
| `age_threshold_reached` | EXPIRE（已达过期年龄） |
| `inactivity_threshold` | DEMOTE（不活跃期超限） |
| `low_usage_threshold` | DEMOTE（使用次数过低） |
| `confidence_decay_threshold` | DEMOTE（置信度衰减） |
| `no_threshold_met` | HOLD（无阈值命中） |

> 注：阈值（天数/次数/置信度）均为 `PolicyConfig` 显式注入，**未固化为不可配置业务常量**；测试中使用合成验证值，正式冻结值由部署侧注入。

## 6. 固定业务红线（可审查清单）

以下三条为本批次固定的业务红线，代码出处与行为如下：

1. **模型推测（Tier 6 `model_inference`）不得覆盖 Tier 1–5 任何可信来源**
   - 出处：`conflict_resolution_policy.py`（`EvidenceTier.MODEL_INFERENCE` 档位最低，`resolve()` 跨档比较自动保证高档保留）；`lifecycle_policy.py::PolicyConfig`（模型单独推测不得作为自动提升要求档）。
2. **`execution_status != success`（failure/cancelled/timeout/partial）不得形成成功知识**
   - 出处：`security/source_admission.py`（`failed` → 仅 `{FAILURE_EXPERIENCE}`；`cancelled`/`timeout` → REJECT；`partial` → 仅 preference）；`candidate_governance.py`（`failed_event_success_knowledge_forbidden`）；`extraction_provider.py`（`failure` 仅 `failure_experience`，`cancelled`/`timeout`/`partial` skip）；D3 §7.8。
3. **cross-user 与 high/critical sensitive 输入在准入/治理/冲突三阶段 fail-closed**
   - 出处：准入 `source_admission.py`（`user_id_mismatch`、`event_sensitive_high`/`event_sensitive_critical`）；治理 `candidate_governance.py`（`user_id_mismatch`、`event_sensitive_blocked`）；冲突 `conflict_resolution_policy.py`（`cross_user_blocked`）。三阶段一致拦截，冲突/生命周期新规则不得绕过安全门禁。

## 7. Day7E 关系说明

Day7E（偏好侧业务能力）**不是** Day8E Business Core 的开发前置条件——本批次四项交付为独立可验收的知识侧纯业务核心。但**后续"偏好 + 知识"统一全链验收仍需 Day7E 与 C/D 集成**：偏好与知识的统一冲突裁决、统一生命周期极需在 D 轨持久化与 C 轨客户端真实接线后做端到端协同验收，届时以 Day7E 的偏好 Domain/策略与本批次知识侧策略在统一调度入口下联合验证。

## 8. D/C/B 后续接线项与 L3 PENDING_INTEGRATION

本批次明确**未完成**以下接线（属其他轨道，不声明完成）：

- **D 轨（持久化层）**：SQLite `memory_status` 状态迁移执行、`ARCHIVE_REQUEST` 处置落地（disposition 消费）、Outbox/Vector 消费、TTL Worker——**未完成**。
- **B 轨（冲突候选发现与检索）**：冲突候选发现、语义相似度检测阈值、FTS5/Vector 索引、应用层 RRF 融合——**未完成**。
- **C 轨（客户端与宿主集成）**：QML MemoryClient、Tool/Turn Adapter、OS Agent Hook 真实集成——**未完成**。

**L3 状态：`PENDING_INTEGRATION`**。含义：Day8E Business Core 尚未与上述 D/B/C 实际接线，且未在银河麒麟真实环境完成全链路验收；直到实际接线并完成真实环境验收后，方可推进 L3。本文档**不声明** Day8 整体集成完成。

### 8.1 跨轨接线约束（scope 规范化与时间输入，接线期责任划分）

以下两条为 B/C/D 后续接线时必须遵守的输入责任约束。二者均为**接线期责任划分说明**，不新增、不冻结任何新的共享枚举或 Runtime 契约，不修改任何既有类型签名与默认值。

#### 8.1.1 ConflictSide.scope：上游已规范化，策略仅精确比较

- `ConflictSide.scope`（`service/conflict_resolution_policy.py`，类型 `Optional[str]`，默认 `None`）是**上游（B/C/D 构造方）已完成 canonicalization 的业务 scope**。
- `ConflictResolutionPolicy.resolve()` 对 scope **仅做精确比较**（两侧均非 None 且 `!=` → `COEXIST` / `scope_distinguishable`），**不负责**自由字符串 normalization（无 trim、大小写折叠、同义归一或任何改写）。
- 因此 B（冲突候选发现）、C（客户端/Adapter）、D（持久化接线）在构造 `ConflictSide` 时**不得直接传入**模型原文、UI 展示文本或未规范化的 Topic/topic 等自由字符串；scope 的归一化责任在上游构造方（与 Preference 路径 `candidate.scope` 经 `PreferenceScope` 五值同源枚举校验入域的方式对齐，由上游显式归一后再传入）。
- 若上游传入未规范化字符串导致本应共存的两侧被判定为可区分（或反之），属上游接线缺陷，不由 Conflict Policy 兜底归一。

#### 8.1.2 LifecyclePolicy 时间输入：调用方 SHOULD 传 timezone-aware datetime

- `LifecyclePolicy.decide(snapshot, *, now)` 的调用方**应当（SHOULD）传入 timezone-aware datetime**（如 `datetime.now(timezone.utc)`）。
- 代码中 naive datetime 的处理（`lifecycle_policy.py`：`now.tzinfo is None` 时补 `timezone.utc` 后统一 `astimezone(timezone.utc)`）**仅为兼容行为，不是宿主时间解析规范**；接线代码不得依赖该兼容路径把宿主本地 naive 时间当作 UTC 语义输入，否则可能产生与调用方意图不符的年龄/不活跃时长计算。
- 本条不改变 `decide()` 既有签名与 fail-closed 语义（naive 输入仍被接受并按 UTC 处理），仅约束调用方输入质量。

## 9. TD-016 / TD-017 状态表述

依据 `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` 现状（**TD-016 状态为 Open、计划日期 2026-08-27；TD-017 状态为 In Progress（Closure Candidate）、计划日期 2026-09-10**）与管理规则（"代码合并 ≠ 技术债关闭；关闭需要对应 PR 的 Reviewer 确认验收标准达成"），本批次如实表述：

- **TD-016：保持 Open。** register 中计划日期为 2026-08-27（原登记日期恢复；PR #64 文档治理轮移除了模板占位符，未批准新的计划日期），关联 PR 保留 `PR #39 / PR #64`。本批次只要求 `lifecycle_policy` 以 `memory_status` 为真源（`LifecycleSnapshot` 强制携带、`extra="forbid"` 隔离过渡字段），**不实施** `is_active` / `should_decay` / `is_outdated` 过渡布尔字段的删除、派生或正交化迁移（该规划属 D/E 协同的正式 Lifecycle 状态机冻结，未在本批次实施）。关闭条件见 register ①–⑤。
- **TD-017：In Progress / Closure Candidate（pending D Reviewer）。** 13 个结构化字段 1:1 无损映射已实现（`domain/knowledge.py` + `candidate_governance.py::_build_knowledge`）且 `test_knowledge_domain_mapping_d8e.py` 已通过字段进出 Domain 一致性验证，**满足关闭的主要技术条件**；register 状态为 **In Progress**，需 D 主审核对 register 验收标准 ①–④ 全部达成后方可标记 Resolved。PR #64 文档治理轮仅同步本节表述与 register 状态的一致性，**不关闭 TD-017、不将其标记为 Resolved**。
  - 代码注释一致性说明：`domain/knowledge.py` 与 `candidate_governance.py` 代码注释当前表述为"TD-017 实现完成/技术关闭候选，待 D Reviewer 确认后正式关闭"，与 register 的 In Progress 状态语义一致；正式关闭以 register 状态 + D 主审确认为准。

## 10. 验证状态汇总

| 层级 | 状态 | 说明 |
|---|---|---|
| L0 | N/A | 本任务为纯文档任务，无新增代码，无 py_compile/ruff/type-check 目标 |
| L1 | 关联回归执行 | `python3 -m pytest memory-service/tests/test_knowledge_conflict_lifecycle_flow_d8e.py -q`（day8-e-04 既有跨阶段业务回归，期望退出码 0）。仅证明 WSL 纯 Python 业务一致性，不证明银河麒麟 Runtime 能力（不含 systemd/UDS/SDK/权限） |
| L2 | N/A | `runtime_required=false`；本批次不标 HOST_VERIFIED。D8-A 的 HOST_VERIFIED/E4 属既有证据条目，本批次不重复 |
| L3 | `PENDING_INTEGRATION` | 待 B/C/D 实际接线 + 真实环境验收完成 |

## 11. 验证证据基线（附）

- 本文档撰写时对应的 Day8E 四项测试文件均存在于 `memory-service/tests/`：`test_knowledge_domain_mapping_d8e.py`、`test_conflict_resolution_policy_d8e.py`、`test_lifecycle_policy_d8e.py`、`test_knowledge_conflict_lifecycle_flow_d8e.py`。
- 关联引用证据条目：`evidence/index.yaml` → `D8-A-KNOWLEDGE-EXTRACTION`（status `HOST_VERIFIED` / evidence_level `E4` / tested_commit `95fcad8`，source `evidence/l2-kylin-vm/day8_verify_latest.log`）。本文档对其结论仅作引用，不重复其证据。
- 本文档全部枚举值、reason_code、字段名与代码逐字一致（`domain/enums.py`、`pipeline/schemas.py`、`service/conflict_resolution_policy.py`、`service/lifecycle_policy.py`、`security/source_admission.py`、`providers/extraction_provider.py`、`domain/knowledge.py`、`service/candidate_governance.py`）；未杜撰新协议格式、常量或路径。

## 12. 已知限制与回滚

- **已知限制**：本批次业务决策均终止于"计划/请求"层；`ARCHIVE_REQUEST`、PROMOTE/DEMOTE/EXPIRE 的执行必须由 D 轨持久化层接线消费，未接线前不存在真实状态迁移；B 轨冲突候选发现与语义相似度阈值未实现，`ConflictResolutionPolicy` 仅在候选被发现后做裁决；C 轨 QML/Hook 未集成。
- **回滚方式**：删除本文件（`git rm docs/day8/day8-e-business-acceptance-v1.md` + commit）即回滚，不影响任何生产代码或测试。