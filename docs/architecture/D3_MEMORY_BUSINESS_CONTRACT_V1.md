# Day3 记忆业务契约 v1 候选

- **版本**：v1
- **状态**：`CANDIDATE_FOR_FREEZE`
- **阶段定位**：Day3 / Gate 0 / E 轨道业务契约候选
- **作者轨道**：E（记忆业务、安全、数据集与业务指标）
- **Reviewer 轨道**：D（IPC、SQLite、Outbox、虚拟机成品化与发布）
- **冻结为团队基线条件**：**只有非作者 D Reviewer 批准且 PR 合并后，本文档方可视为团队冻结基线**。本文件的 `CANDIDATE_FOR_FREEZE` 状态仅表示 E 轨道单方面提出的 v1 候选语义集合，不代表已被团队批准、不代表 D3 Gate 通过、不代表任何宿主行为或实现能力已被验证。
- **Canonical 候选关系声明（2026-09-03 增补）**：本文件继续保持 `CANDIDATE_FOR_FREEZE`；`KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md` 当前同样保持 `CANDIDATE_FOR_FREEZE`，承载本轮 R-1..R-6 统一业务语义裁定候选。在非作者 D Reviewer 批准且对应 PR 合并、Canonical 完成后续团队冻结治理之前，不建立“Canonical 候选自动覆盖本文件”的团队级权威关系。本文件继续承载七类业务概念、对象关系、字段处置和业务规则。本声明**不改变**「十二、12.2 升级为团队冻结基线」的 8 项条件。
- **用途**：集中承载 E 轨道在 Day3 可单方面冻结的记忆业务语义（七类业务概念、对象关系、字段含义、版本与生命周期规则），并对依赖 C/D/B/A 真实证据的宿主或实现事实保持 `DEFERRED`/`UNVERIFIED`/`PENDING_*`，不替其他轨道虚构实现契约。
- **本文件不是**：SQLite 物理 Schema、Migration、Vector Collection Schema、C++ 结构体、IPC Payload、错误码或 Provider 接口。上述技术实现层事项见「九、不可冻结项清单」，全部 `DEFERRED` 或 `待对应轨道确认`。

---

## 一、依据来源与局限声明

### 1.1 依据来源（仓库内已核验文件）

| 编号 | 来源 | 路径 | 仓库状态 |
|------|------|------|----------|
| S-01 | Day1 记忆业务 Schema v0.1 DRAFT（修订2，2026-07-30） | `docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md` | SOURCE_VERIFIED（在库） |
| S-02 | Day1 标注规范 v0.1 DRAFT（修订2，2026-07-31） | `datasets/ANNOTATION_GUIDELINE_V0.1.md` | SOURCE_VERIFIED（在库） |
| S-03 | Day2 事件契约冻结前检查表 v0.1 DRAFT（2026-08-07） | `docs/architecture/D2_EVENT_CONTRACT_PRE_FREEZE_CHECKLIST_V0.1.md` | SOURCE_VERIFIED（在库） |
| S-04 | Day2 业务验收案例集 v0.1 DRAFT（G0-E-01..14） | `datasets/GATE0_BUSINESS_ACCEPTANCE_CASES_V0.1.json` | SOURCE_VERIFIED（在库） |
| S-05 | Day2 E Gate0 业务预审报告 v0.1（2026-08-08，Gate 结论 `BLOCKED`） | `docs/project-management/D2_E_GATE0_BUSINESS_REVIEW.md` | SOURCE_VERIFIED（在库） |
| S-06 | 赛题要求与项目交付追踪矩阵 v0.1 DRAFT（修订2，2026-07-31） | `docs/project-management/REQUIREMENT_TRACEABILITY_MATRIX.md` | SOURCE_VERIFIED（在库） |
| S-07 | 证据索引 v1.1 | `evidence/index.yaml` | SOURCE_VERIFIED（在库） |
| S-08 | 技术债务登记表（仅 TD-001..004） | `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` | SOURCE_VERIFIED（在库） |
| S-09 | 基线文档清单 | `docs/baseline/README.md` | SOURCE_VERIFIED（在库；01–06 全部「待人工导入」） |
| S-10 | A 轨道 Provider v1 契约草稿（骨架已建，接口未编码、端到端未验证） | `docs/day3/06_provider_contract_v1.md` | SOURCE_VERIFIED（前向草稿，**非冻结契约**） |
| S-11 | D3-B 检索契约 v1（PR #20 Review 返工中） | `docs/day3/08_vector_retrieval_contract_v1.md` | SOURCE_VERIFIED（**D3-B 冻结候选，状态 `FROZEN_CANDIDATE`，未冻结**） |
| S-12 | D3-B 检索契约审查矩阵（状态 `REWORK`） | `docs/day3/09_retrieval_contract_review_matrix.md` | SOURCE_VERIFIED（**REWORK，未冻结**） |
| S-13 | 模块 README（memory-service / cpp-bridge / memory-client / os-agent-integration） | 各模块 `README.md` | SOURCE_VERIFIED（均「仅建立目录和职责边界，尚无生产实现」） |

### 1.2 局限声明

- **基线 DOCX 未导入**：赛题原文、总体架构 SOP v1.1、官方 SDK 与 OS Agent 能力边界（01–04）、架构设计审查报告（05）、15 天 75 项施工台账（06）当前**均未被 Git 仓库跟踪**，`docs/baseline/` 目录下不存在实体文件。本文件不得声称已从实体 DOCX 独立核验任何字段语义。
- **C 轨真实宿主取证缺位**：`MemoryContext`/`ToolExecutionEvent`/`TurnFinalizedEvent` 真实宿主事件结构在当前仓库不可见，全部 `C_D2_EVIDENCE_MISSING`（见 S-05、S-07）。本文件涉及上述对象的内容均为**业务候选语义**，不是官方 SDK 原生字段，也不是已批准协议。
- **D 轨关键证据未闭合**：真实 Kaiming Hook `BLOCKED`、KYSEC 最小授权 `UNVERIFIED`、幂等/取消/断线重连 `UNTESTED`/`NOT_FOUND`、deadline 超时语义 `PARTIAL`、标准回退未补跑（见 S-05 第六节）。
- **SOP v1.1 未终审**：`source_type` 七值、`event_type` 三值、六档冲突优先级、`expression_type` 归一结果均为按任务规格回填，待 SOP v1.1 实体文件导入后逐项复核（对应 HD-SCHEMA-15/HD-D2E-04）。
- **证据状态口径**：本文件遵循追踪矩阵第五节双轴口径——业务侧 `PENDING`/`UNVERIFIED`/`PARTIAL`/`CANDIDATE_FOR_FREEZE`；SDK 能力侧 `UNTESTED`/`SOURCE_VERIFIED`/`ABI_VERIFIED`/`HOST_VERIFIED`/`PARTIAL`/`NOT_FOUND`/`BLOCKED`/`DEFERRED`/`PENDING_C_CONFIRMATION`/`PENDING_D_CONFIRMATION`/`UNVERIFIED`。**无真实银河麒麟宿主证据的事项一律不得标 `HOST_VERIFIED`**。
- 本文件引用既有宿主证据（如 UDS Echo Spike `HOST_VERIFIED`、Embedding 调用 `HOST_VERIFIED`）仅为**来源引用**，不是本文件新取得的 Runtime 证据；本任务 `runtime_required=false`，不新增 Runtime 验证。

---

## 二、来源到冻结决策追踪表

> 追踪对象：Day1 业务 Schema、Day1 标注规范、Day2 冻结前检查表、Day2 业务验收案例集、Day2 业务预审报告（五项必备来源），以及本契约引用到的辅助来源。

| 来源 | 文件（仓库内状态） | 版本/日期 | 本契约采用/沿用/不越过 | 待决责任轨道 |
|------|--------------------|-----------|------------------------|--------------|
| Day1 业务 Schema | `docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md`（SOURCE_VERIFIED） | v0.1 DRAFT / 修订2 2026-07-30 | 沿用五原始业务对象（MemorySourceEvent/Preference/Knowledge/Conflict/ForgetPlan）字段语义与 13 组候选枚举，作为 E 可冻结业务语义的来源基准；**不越过**其技术实现边界（第四章 4.5 不冻结清单） | E（业务语义）；D/E（过渡字段移除、captured_at/collected_at） |
| Day1 标注规范 | `datasets/ANNOTATION_GUIDELINE_V0.1.md`（SOURCE_VERIFIED） | v0.1 DRAFT / 修订2 2026-07-31 | 沿用 `expression_type` 归一为 `explicit`/`implicit` 二值（`inferred` 归一为 `implicit`，`candidate` 不作表达类型值）；沿用 Tool Result `execution_status` 语义与敏感边界 S-01..S-09；**不越过**其冻结门槛（第十章） | E（标注语义）；C（Tool 取证回填） |
| Day2 冻结前检查表 | `docs/architecture/D2_EVENT_CONTRACT_PRE_FREEZE_CHECKLIST_V0.1.md`（SOURCE_VERIFIED） | v0.1 DRAFT / 2026-08-07 | 沿用三个派生对象（MemoryContext/ToolExecutionEvent/TurnFinalizedEvent）**候选字段语义**与失败/取消/超时/部分执行业务规则，但一律保持候选状态；**不越过**其「非已冻结协议」声明与第十三章阻塞项 | C/D（派生对象取证与协议草案） |
| Day2 业务验收案例集 | `datasets/GATE0_BUSINESS_ACCEPTANCE_CASES_V0.1.json`（SOURCE_VERIFIED） | v0.1 DRAFT / 2026-08-07 | 沿用 G0-E-01..14 的业务验收场景与禁止结果，作为本契约业务规则（原文隔离、敏感过滤、遗忘排除、跨用户隔离、Tool 四态、幂等、终结唯一性、授权、模型自述）的案例化依据；案例集本身为设计稿，**不构成 Runtime 证据** | C/D/E（案例在麒麟执行） |
| Day2 业务预审报告 | `docs/project-management/D2_E_GATE0_BUSINESS_REVIEW.md`（SOURCE_VERIFIED） | v0.1 DRAFT / 2026-08-08（Gate 结论 `BLOCKED`） | 沿用其「D3 冻结最低条件未满足」结论与 HD-D2E-B01..B07 阻塞项，完整登记至本文件「十、FREEZE_BLOCKERS」；**不得为完成 Day3 删除阻断项** | C/D/E/安全渠道（补证） |
| 追踪矩阵 | `docs/project-management/REQUIREMENT_TRACEABILITY_MATRIX.md`（SOURCE_VERIFIED） | v0.1 DRAFT / 修订2 2026-07-31 | 沿用 REQ-01..07 业务能力归属与双轴证据状态口径；REQ-01..07 当前全 `PENDING`，四项性能指标全 `UNVERIFIED` | B/E（评测）；D/E（计划对齐） |
| 证据索引 | `evidence/index.yaml`（SOURCE_VERIFIED） | v1.1 | 仅引用既有证据状态（Embedding HOST_VERIFIED、Vector HOST_VERIFIED 但 `merge_qualified=false`、真实 Hook BLOCKED、KYSEC UNVERIFIED、C 三对象 `C_D2_EVIDENCE_MISSING`），不作为本文件新增 Runtime 证据 | 各轨道 |
| A Provider 契约草稿 | `docs/day3/06_provider_contract_v1.md`（SOURCE_VERIFIED） | 2026-08-03 前后，骨架已建 | **不越过**：该草稿为前向草稿、接口未编码、端到端未验证；其 `TurnFinalizedEvent`/`PreferenceCandidate.scope` 与 Schema 存在字段简化差异（见「九、跨文档冲突登记」），不得引用为已冻结事实 | A（实现）；C/D/E（字段对齐） |
| D3-B 检索契约 | `docs/day3/08_vector_retrieval_contract_v1.md` + `09_retrieval_contract_review_matrix.md`（SOURCE_VERIFIED） | 2026-08-03 / PR #20 Review 返工中，09 状态 `REWORK` | **不越过**：本文件仅将 08/09 的 `DEFERRED_CROSS_TRACK` 项（memory_status 检索集合、sensitivity 可见范围、full reset 授权等）作为 E 待决输入登记，不把 08/09 当作已冻结事实 | B（PR #20 返工）；D/E（跨轨待决） |
| 基线文档清单 | `docs/baseline/README.md`（SOURCE_VERIFIED） | 当前 | 明确 01–06 基线文档「待人工导入」，本文件不虚标其存在 | 团队/E（人工导入） |

**追踪结论**：本文件全部冻结决策均源自上述在库文件；凡依赖 C 真实宿主取证或 D 真实 IPC/KYSEC/持久化证据的事实，凡当前 `main` 证据不足者，一律标记 `PENDING_C_CONFIRMATION`、`PENDING_D_CONFIRMATION`、`DEFERRED` 或 `UNVERIFIED`，**不得写成 `HOST_VERIFIED` 或「官方字段已确认」**。

---

## 三、七类业务概念定义与边界

本节定义 E 轨道在 Day3 可单方面冻结的七类业务概念。其中 `Evidence` 与 `Lifecycle` 仅作为**业务概念/子结构**定义（承载证据链与生命周期语义），**本文件不设计任何数据库表**；SQL 类型、索引、唯一约束、外键与迁移方式一律 `待 D 确认`（见「九、不可冻结项清单」）。

### 3.1 MemorySourceEvent（来源事件）

- **业务含义**：来自官方 AI 助手或系统环境的单次信息输入事件，是多源记忆采集的最初入口，业务上是 `Preference` 与 `Knowledge` 的**上游来源**（二者通过 `source_event_id`/`evidence_event_ids` 关联回本对象）。对应 REQ-01 多源数据。
- **边界**：定义「事件从何而来（`source_type`）」「在交互中的角色（`event_type`）」「业务结果（`source_business_status`）」与「内部处理阶段（`processing_status`，技术候选）」四个正交语义；`user_id`（数据归属）与 `actor_id`（实际发起者）语义边界见「七、7.1」。
- **E 可冻结部分**：字段命名、业务含义、来源规则（`*禁止模型生成`）、必填性候选、敏感过滤红线。
- **DEFERRED 部分**：宿主字段是否真实存在、`turn_id`/`tool_call_id`/`occurred_at`/`user_id`/`actor_id` 的宿主映射（`PENDING_C_CONFIRMATION`）；`raw_payload_ref` 存储形态、ID 生成策略（`PENDING_D_CONFIRMATION`）；`source_type` 七值宿主覆盖（`PENDING_C_CONFIRMATION` + SOP 导入复核）。

### 3.2 Preference（偏好）

- **业务含义**：从用户行为中提取的显式或隐式偏好，以 key-value 结构承载，支持置信度、作用域、临时/正式边界与版本化，是 Memory Service 提供个性化上下文的核心载体。对应 REQ-02 偏好动态捕捉。
- **边界**：`expression_type` 仅 `explicit`/`implicit` 二值；候选/推断状态通过 `memory_status=candidate` 表达，**不占用表达类型取值**；`is_temporary=true` 或 `should_persist=false` 时不得晋升为正式长期偏好。
- **E 可冻结部分**：preference_key/value 业务语义、作用域五值、临时/正式边界、版本化回溯语义、`memory_status` 优先。
- **DEFERRED 部分**：`confidence_score` 量化方法（待 A/E，HD-SCHEMA-03）；衰减函数（待 A/E）；`preference_key`/`preference_value` 具体 schema 依赖官方 AI 助手偏好模型（`UNVERIFIED`，待 C）；版本化 SQLite 实现（待 D）。

### 3.3 Knowledge（结构化知识）

- **业务含义**：经过抽取和归一化后的结构化知识条目，是语义检索与 RRF 排序的最小知识单元。对应 REQ-03 知识整合与冲突、REQ-04 端侧 Embedding 与轻量检索。
- **边界**：`knowledge_type` 六值为稳定业务枚举，`primary_category` 为开放业务分类标签，二者**不可相互替代**；`content_summary` 为可检索字段且须经敏感过滤。
- **E 可冻结部分**：`knowledge_type` 六值语义、`source_event_id` 关联、`primary_category` 定位、`memory_status` 优先。
- **DEFERRED 部分**：`content_ref` 存储形态（待 D）；`requires_embedding` 向量承载/索引结构（待 B）；`access_count`/`last_accessed_at` 统计窗口与精度（待 D）；`confidence_score` 量化（待 A/E）。

### 3.4 Evidence（证据引用，业务概念/子结构）

- **业务含义**：支撑 `Preference`/`Knowledge`/`Conflict` 条目的可审计证据链语义。本概念**不新增独立业务对象**，以子结构形式承载于上述对象，至少包含：来源事件引用（`source_event_id`/`evidence_event_ids`）、版本引用（`version`/`previous_version_id`/`superseded_by_id`）、来源定位引用（`source_reference`，非原始载荷）与来源大类（`source_type`）。
- **业务规则**（E 可冻结）：
  1. 证据引用必须是**业务事件或系统生成**的标识，禁止 LLM 伪造证据 ID。
  2. 高敏正文（`sensitivity=critical`）不得以明文进入引用或摘要，仅可写入脱敏占位或仅 ID 引用（S-01..S-04、S-08）。
  3. 引用字段（`raw_payload_ref`/`content_ref`/`source_reference`）的**存储形态**（内联/外部分片/文件引用）`待 D 确认`，本契约不冻结。
- **边界**：Evidence 不定义表结构、不定义引用表、不定义外键——均属 D 轨道 SQLite/存储层职责。

### 3.5 Conflict（冲突）

- **业务含义**：两条或多条知识/偏好条目之间的语义或事实不一致记录，用于驱动冲突消解流程。对应 REQ-03。
- **边界**：`conflict_type` 五值为业务语义层；`contradiction` 与 `temporal_inconsistency` 的**判定阈值算法**属 B 轨道实现层（本文件不冻结，登记 `REJECTED` 处置与 `待 B` 待决，见第六节）；`resolution_status`/`resolution_strategy`/`resolution_confidence`/`resolved_by` 的**最终值不得由模型生成**，必须由消解规则引擎或系统计算产出。
- **作用域共存规则**（E 可冻结）：两条条目 `preference_scope`/`knowledge_type`/`primary_category` 等作用域字段不同时，优先判定为**可共存**而非冲突；仅在作用域相同或高度重叠时进入冲突判定。
- **六档冲突优先级**（E 可冻结，依据 Schema §3.4，待 SOP v1.1 导入复核）：见「七、7.5」。

### 3.6 Lifecycle（生命周期，业务概念）

- **业务含义**：统一记忆生命周期语义，对应 REQ-05/REQ-06。以 `memory_status` 六值（`active`/`superseded`/`deprecated`/`expired`/`removed`/`candidate`）为**唯一优先字段**，替代多布尔字段（`is_active`/`is_outdated`/`should_decay`）互相矛盾的问题。
- **边界**：`memory_status` 是正式生命周期状态的唯一优先字段；既有布尔字段**过渡保留**，待 D/E 统一为 `memory_status` 后在 v1.0 中移除（决策记录见 HD-SCHEMA-13）。`memory_type`（short/medium/long/ephemeral）仅定义业务语义上的短/中/长期区分，**不冻结存储分层边界、流转阈值、回收策略**（待 D，HD-SCHEMA-07）。
- **E 可冻结部分**：`memory_status` 六值业务语义、布尔字段→`memory_status` 的迁移方向、`candidate` 不晋升规则。
- **DEFERRED 部分**：短/中/长期流转阈值与存储分层（待 D）；衰减策略（待 A/E）；`ephemeral` 业务必要性（待 E）。

### 3.7 ForgetPlan（遗忘计划）

- **业务含义**：一次有计划、可追踪的遗忘操作，覆盖单条、会话级、主题级、时间窗口级与全量重置粒度。对应 REQ-05 敏感过滤与精准遗忘。
- **业务规则**（E 可冻结）：
  1. **先预览再确认**：系统解析 `target_selector` → 生成 `resolved_target_ids` → 展示受影响条目预览 → 用户确认 → 执行删除。
  2. **禁止模型生成**：`resolved_target_ids`、`requires_confirmation` 最终判定、`affected_count` 最终值、整体删除执行决策均由遗忘规则引擎或系统计算产出。
  3. 遗忘以业务对象级别的 `resolved_target_ids` 为精准范围，不得按模糊关键词或时间窗口粗略删除后声称「已精准遗忘」（标注规范 §2.5）。
  4. 硬删除（`hard_delete=true`）时，正文不得在 SQLite、Vector、FTS5、日志、导出与备份中留存可检索明文残留（S-09）。
- **DEFERRED 部分**：`is_cascade` 级联范围（待 E，HD-SCHEMA-06）；`has_vector_cleanup` 的 Vector 同步删除策略（待 B，HD-SCHEMA-05）；`forget_mode=full_reset` 安全边界（待 E/D，HD-SCHEMA-06）；`status` 执行状态与回滚在 SQLite 事务模型中的可行性（待 D）。

---

## 四、MemoryContext / ToolExecutionEvent / TurnFinalizedEvent 与业务对象的关系

> **重要声明**：`MemoryContext`、`ToolExecutionEvent`、`TurnFinalizedEvent` 是 Day2 检查表定义的**业务候选对象**，**不是 E 轨道可单方面冻结的宿主原生结构或 IPC 物理格式**。它们是否为官方 AI 助手真实结构、字段是否与宿主一致，必须由 C 轨道在麒麟 VM 取证（`PENDING_C_CONFIRMATION`）；IPC 线格式与承载方式必须由 D 轨道协议草案冻结（`PENDING_D_CONFIRMATION`）。本文件仅说明它们与业务对象的**输入/承载关系**。

### 4.1 关系总览

| 候选对象 | 与业务对象的关系 | 承载/输入方向 | 证据状态 |
|----------|------------------|---------------|----------|
| `MemorySourceEvent`（业务对象） | 是 `Preference`/`Knowledge` 的上游来源；`Preference` 经 `evidence_event_ids`、`Knowledge` 经 `source_event_id` 关联回来源 | 业务对象真源输入 | 字段语义可冻结；宿主映射 `PENDING_C_CONFIRMATION` |
| `ToolExecutionEvent`（派生候选） | 单次 Tool 调用执行结果事件，衍生 `source_type=tool_result` 来源；是形成/不形成知识（`should_form_memory`）的判定载体 | 承载 Tool 结果 → 可形成 `Preference`/`Knowledge`/失败经验 | `PENDING_C_CONFIRMATION`（C 取证真实 Tool 结构） |
| `TurnFinalizedEvent`（派生候选） | 单个 Turn 收尾事件，承载 Turn 边界、停止原因、重试与幂等语义（`retry_of_turn_id`）；关联上游 `ToolExecutionEvent.tool_call_ids` | 承载 Turn 收尾 → 触发来源事件入库与候选提取 | `PENDING_C_CONFIRMATION`（C 取证 Turn 边界/重试机制） |
| `MemoryContext`（派生候选） | Memory Service 组装后注入 `model_request` 的上下文承载对象；`selected_memory_ids` 注入前必须回源 SQLite 当前版本并复核 `user_id`、状态、有效期、敏感与冲突状态 | 输出承载（注入模型请求） | `PENDING_C_CONFIRMATION` + `PENDING_D_CONFIRMATION` |

### 4.2 明确不冒充的边界

- 三个派生对象的全部字段均为**候选建议**（D2 检查表第三至七章），当前证据状态统一 `UNTESTED`/`C_D2_EVIDENCE_MISSING`（见 S-05 第五节、S-07）。
- `TurnFinalizedEvent` 的 A Provider 草稿 dataclass 字段（`session_id`/`user_text`/`assistant_text`/`tool_results`/`source` 三值/`occurred_at`/`collected_at`）较 Schema 分层显著简化，属**前向草稿**，不得引用为已确认结构（见「九、跨文档冲突登记」第 5 项）。
- `execution_status` 的 `cancelled`/`partial` 是否入 D3 正式候选，须 E/B/D 复核（HD-D2E-05），本文件仅按候选规则描述（见「七、7.8」）。
- `MemoryContext` 是否允许跨 Turn 复用（`context_version` 升级策略）待 C/D 决策（HD-D2E-06），本文件不冻结。

---

## 五、Day1 候选字段逐项处置状态

> 处置状态含义：
> - **`FROZEN_BUSINESS_SEMANTIC`**：E 轨道可单方面冻结的业务语义层（字段命名、业务含义、来源规则、必填性候选、禁止模型生成规则）。此冻结**不代表宿主字段已确认、不代表技术实现已定**。
> - **`REVISED`**：Day1 候选字段经 E 复核后表述需要修订，修订后的业务语义仍属可冻结范围。
> - **`DEFERRED`**：依赖 C/D/B/A 真实证据或技术实现确认未到，本契约不冻结，保持待确认。
> - **`REJECTED`**：Day1 候选中已被后续修订否决，或 E 轨道不可冻结的项。

### 5.1 MemorySourceEvent（来源事件，对应 REQ-01）

| 字段 | 处置 | 理由 / 说明 |
|------|------|-------------|
| `event_id` | FROZEN_BUSINESS_SEMANTIC | 事件全局唯一标识语义冻结；ID 生成策略（UUID v4/v7/纳秒时间戳）`待 D`（HD-SCHEMA-09） |
| `user_id` | FROZEN_BUSINESS_SEMANTIC | 数据归属与用户隔离键，`*禁止模型生成`；宿主字段是否存在`PENDING_C_CONFIRMATION`（HD-SCHEMA-12） |
| `actor_id` | FROZEN_BUSINESS_SEMANTIC | 事件实际发起者，`*禁止模型生成`；宿主映射`PENDING_C_CONFIRMATION` |
| `source_type` | FROZEN_BUSINESS_SEMANTIC | 七值业务语义冻结；宿主覆盖待 C 取证 + SOP 导入复核（HD-SCHEMA-15/16） |
| `schema_version` | FROZEN_BUSINESS_SEMANTIC | 事件契约版本号语义冻结；D UDS 承载`PENDING_D_CONFIRMATION` |
| `trace_id` | FROZEN_BUSINESS_SEMANTIC | 跨服务追踪语义冻结；与 UDS 请求头关联`PENDING_D_CONFIRMATION` |
| `event_type` | FROZEN_BUSINESS_SEMANTIC | 三值消息粒度角色语义冻结；与 `source_type` 分层；宿主消息角色`PENDING_C_CONFIRMATION` |
| `source_reference` | FROZEN_BUSINESS_SEMANTIC | 来源记录定位引用（非原始载荷）语义冻结；存储形态`PENDING_D_CONFIRMATION` |
| `consent_scope` | FROZEN_BUSINESS_SEMANTIC | 同意范围标注语义冻结；E 终审同意模型`DEFERRED`（案例 G0-E-13） |
| `idempotency_key` | REVISED | 修订2 补入禁止模型生成清单；接入侧幂等去重，**不可由 `event_id` 替代**；D UDS 幂等机制`PENDING_D_CONFIRMATION` |
| `source_business_status` | FROZEN_BUSINESS_SEMANTIC | 业务结果状态八值语义冻结（raw/completed PARTIAL，其余 UNVERIFIED）；宿主状态语义`PENDING_C_CONFIRMATION` |
| `processing_status` | REVISED | 明确定位为**技术候选**，不视为已冻结业务枚举；状态机条件待 A/B/D |
| `memory_type` | DEFERRED | 短/中/长分层边界与流转条件待 D（HD-SCHEMA-07）；`ephemeral` 业务必要性待 E |
| `occurred_at` | FROZEN_BUSINESS_SEMANTIC | 宿主侧实际发生时间，`*禁止模型生成`；宿主时间字段`PENDING_C_CONFIRMATION` |
| `captured_at` | FROZEN_BUSINESS_SEMANTIC | 捕获入库时间语义属于 E 轨内部 `FROZEN_BUSINESS_SEMANTIC`；本轮 Canonical v1 R-1 **候选裁定**提出 `captured_at` 为 Canonical 事件捕获时间字段、`collected_at` 为 legacy transport alias，transport→business 必经 Adapter/Mapping；该统一裁定待 D Reviewer 确认并完成团队冻结，transport 层采纳/更名仍属 C/D 实现 handoff（TD-060） |
| `session_id` | FROZEN_BUSINESS_SEMANTIC | 所属会话语义冻结；宿主会话结构`PENDING_C_CONFIRMATION` |
| `raw_payload_ref` | FROZEN_BUSINESS_SEMANTIC | 原始载荷引用语义 + 敏感红线冻结；存储形态`PENDING_D_CONFIRMATION` |
| `content_summary` | FROZEN_BUSINESS_SEMANTIC | 内容摘要 + 敏感过滤语义冻结 |
| `turn_id` | DEFERRED | 依赖 C 宿主 Turn 边界取证（conditional 触发条件已定义） |
| `tool_call_id` | DEFERRED | 依赖 C 宿主 Tool 调用结构取证（`source_type=tool_result` 时必填） |
| `sensitivity` | FROZEN_BUSINESS_SEMANTIC | 五级业务语义冻结；分级标准待 E 终审（HD-ANNO-05）；终判不得模型覆写 |
| `is_sensitive_matched` | FROZEN_BUSINESS_SEMANTIC | 是否命中敏感过滤规则语义冻结 |
| `requires_embedding` | FROZEN_BUSINESS_SEMANTIC | 是否需要 Embedding 语义冻结；向量承载/索引结构`PENDING_B_CONFIRMATION` |
| `has_structured_payload` | FROZEN_BUSINESS_SEMANTIC | 是否含可抽取结构化载荷语义冻结 |
| `language_tag` | FROZEN_BUSINESS_SEMANTIC | BCP 47 语言标记语义冻结 |

### 5.2 Preference（偏好，对应 REQ-02）

| 字段 | 处置 | 理由 / 说明 |
|------|------|-------------|
| `preference_id` | FROZEN_BUSINESS_SEMANTIC | 偏好全局唯一标识语义冻结；ID 生成策略`待 D` |
| `user_id` | FROZEN_BUSINESS_SEMANTIC | 数据归属隔离键，`*禁止模型生成` |
| `expression_type` | FROZEN_BUSINESS_SEMANTIC | `explicit`/`implicit` 二值（修订2 已归一）；待 SOP v1.1 导入后终审（HD-SCHEMA-14） |
| `preference_scope` | FROZEN_BUSINESS_SEMANTIC | 五值业务语义冻结；A Provider 草稿 `scope` 取值差异见冲突登记第 5 项 |
| `preference_key` | FROZEN_BUSINESS_SEMANTIC | 偏好键名业务语义冻结；具体 schema 依赖官方偏好模型`UNVERIFIED` |
| `preference_value` | FROZEN_BUSINESS_SEMANTIC | 偏好值业务语义冻结；具体 schema 依赖官方偏好模型`UNVERIFIED` |
| `confidence_score` | DEFERRED | 量化方法（频率/时序/行为模式加权）待 A/E（HD-SCHEMA-03） |
| `memory_status` | FROZEN_BUSINESS_SEMANTIC | 统一生命周期优先字段；D/E 过渡字段移除决策（HD-SCHEMA-13） |
| `is_active` | REVISED | **过渡字段**：待 D/E 统一为 `memory_status` 后移除 |
| `is_temporary` | FROZEN_BUSINESS_SEMANTIC | 临时要求边界语义冻结 |
| `should_persist` | FROZEN_BUSINESS_SEMANTIC | 是否持久化为正式偏好语义冻结 |
| `should_decay` | REVISED | **过渡字段**；衰减函数待 A/E |
| `decay_after_at` | DEFERRED | 衰减生效时间语义冻结；衰减策略/函数待 A/E（HD-SCHEMA-03） |
| `evidence_event_ids` | FROZEN_BUSINESS_SEMANTIC | 证据事件 ID 链语义冻结（Evidence 子结构） |
| `version` | FROZEN_BUSINESS_SEMANTIC | 版本化回溯语义冻结；SQLite 实现`待 D` |
| `previous_version_id` | FROZEN_BUSINESS_SEMANTIC | 版本链回溯语义冻结；SQLite 实现`待 D` |
| `created_at` | FROZEN_BUSINESS_SEMANTIC | 创建时间语义冻结 |
| `updated_at` | FROZEN_BUSINESS_SEMANTIC | 更新时间语义冻结 |
| `requires_confirmation` | FROZEN_BUSINESS_SEMANTIC | 是否需要用户显式确认语义冻结 |
| `extracted_entities` | FROZEN_BUSINESS_SEMANTIC | 实体列表语义冻结；抽取输出格式待 A |

### 5.3 Knowledge（结构化知识，对应 REQ-03/REQ-04）

| 字段 | 处置 | 理由 / 说明 |
|------|------|-------------|
| `knowledge_id` | FROZEN_BUSINESS_SEMANTIC | 知识条目全局唯一标识语义冻结 |
| `user_id` | FROZEN_BUSINESS_SEMANTIC | 数据归属隔离键，`*禁止模型生成` |
| `knowledge_type` | FROZEN_BUSINESS_SEMANTIC | 六值稳定业务枚举；不得以 `primary_category` 替代 |
| `memory_type` | DEFERRED | 分层边界/流转条件待 D（HD-SCHEMA-07） |
| `memory_status` | FROZEN_BUSINESS_SEMANTIC | 统一生命周期优先字段 |
| `source_event_id` | FROZEN_BUSINESS_SEMANTIC | 关联 `MemorySourceEvent.event_id`（来源链） |
| `content_summary` | FROZEN_BUSINESS_SEMANTIC | 可检索摘要 + 敏感过滤语义冻结 |
| `content_ref` | DEFERRED | 完整内容引用存储形态待 D |
| `primary_category` | FROZEN_BUSINESS_SEMANTIC | 开放业务分类标签，**不可替代 `knowledge_type`** |
| `language_tag` | FROZEN_BUSINESS_SEMANTIC | BCP 47 语言标记语义冻结 |
| `confidence_score` | DEFERRED | 量化模型待 A/E |
| `requires_embedding` | FROZEN_BUSINESS_SEMANTIC | 是否需要 Embedding 语义冻结；向量承载结构`待 B` |
| `is_outdated` | REVISED | **过渡字段**：待 D/E 统一为 `memory_status` 后移除 |
| `superseded_by_id` | FROZEN_BUSINESS_SEMANTIC | 替代回溯语义冻结 |
| `created_at` | FROZEN_BUSINESS_SEMANTIC | 创建时间语义冻结 |
| `updated_at` | FROZEN_BUSINESS_SEMANTIC | 更新时间语义冻结 |
| `access_count` | DEFERRED | 统计窗口与精度待 D |
| `last_accessed_at` | DEFERRED | 统计窗口与精度待 D |
| `extracted_entities` | FROZEN_BUSINESS_SEMANTIC | 实体列表语义冻结；抽取输出格式待 A |

### 5.4 Conflict（冲突，对应 REQ-03）

| 字段 | 处置 | 理由 / 说明 |
|------|------|-------------|
| `conflict_id` | FROZEN_BUSINESS_SEMANTIC | 冲突全局唯一标识语义冻结 |
| `user_id` | FROZEN_BUSINESS_SEMANTIC | 从涉及 Knowledge/Preference 派生，`*禁止模型生成` |
| `conflict_type` | FROZEN_BUSINESS_SEMANTIC | 五值业务语义冻结；`contradiction`/`temporal_inconsistency` **判定阈值算法**`REJECTED`（见下） |
| `left_knowledge_id` | FROZEN_BUSINESS_SEMANTIC | 冲突左方条目 ID 语义冻结 |
| `right_knowledge_id` | FROZEN_BUSINESS_SEMANTIC | 冲突右方条目 ID 语义冻结 |
| `involved_knowledge_ids` | FROZEN_BUSINESS_SEMANTIC | 多知识冲突 ID 列表语义冻结 |
| `conflict_summary` | FROZEN_BUSINESS_SEMANTIC | 冲突描述语义冻结 |
| `resolution_status` | FROZEN_BUSINESS_SEMANTIC | 六值语义冻结；最终结果值（resolved_auto/resolved_manual/unresolvable）禁止模型生成 |
| `resolution_strategy` | DEFERRED | 策略集合与优先级待 B/E 确认 |
| `is_auto_resolvable` | DEFERRED | 判定标准（置信度阈值/差异幅度）待 B/E |
| `resolution_confidence` | DEFERRED | 计算方式待 B/E；**最终值禁止模型生成** |
| `detected_at` | FROZEN_BUSINESS_SEMANTIC | 冲突检测时间语义冻结 |
| `resolved_at` | FROZEN_BUSINESS_SEMANTIC | 冲突消解时间语义冻结 |
| `resolved_by` | FROZEN_BUSINESS_SEMANTIC | 消解执行方标识，`*禁止模型生成` |
| `contradiction`/`temporal_inconsistency` 判定阈值算法 | REJECTED | **E 轨道不可冻结**：判别逻辑属 B 轨道冲突检测模块实现层，移交 `DEFERRED`（待 B，HD-SCHEMA-04） |

### 5.5 ForgetPlan（遗忘计划，对应 REQ-05）

| 字段 | 处置 | 理由 / 说明 |
|------|------|-------------|
| `forget_plan_id` | FROZEN_BUSINESS_SEMANTIC | 遗忘计划全局唯一标识语义冻结 |
| `user_id` | FROZEN_BUSINESS_SEMANTIC | 外部输入，`*禁止模型生成` |
| `forget_mode` | FROZEN_BUSINESS_SEMANTIC | 五值业务语义冻结；`full_reset` 安全边界待 E/D（HD-SCHEMA-06） |
| `target_selector` | FROZEN_BUSINESS_SEMANTIC | 用户输入选择器语义冻结 |
| `resolved_target_ids` | FROZEN_BUSINESS_SEMANTIC | 先预览再确认；`*禁止模型生成` |
| `target_type` | FROZEN_BUSINESS_SEMANTIC | `knowledge`/`preference`/`event`/`all` 业务语义冻结 |
| `target_id` | FROZEN_BUSINESS_SEMANTIC | `single_item` 模式直接输入语义冻结 |
| `target_session_id` | FROZEN_BUSINESS_SEMANTIC | `session` 模式目标语义冻结 |
| `target_topic` | FROZEN_BUSINESS_SEMANTIC | `topic` 模式目标语义冻结 |
| `target_time_range` | FROZEN_BUSINESS_SEMANTIC | `time_window` 模式目标语义冻结 |
| `created_at` | FROZEN_BUSINESS_SEMANTIC | 计划创建时间语义冻结 |
| `executed_at` | FROZEN_BUSINESS_SEMANTIC | 实际执行时间语义冻结 |
| `status` | FROZEN_BUSINESS_SEMANTIC | 七值执行状态（pending/previewing/awaiting_confirmation/executing/completed/failed/rolled_back）语义冻结 |
| `is_cascade` | DEFERRED | 级联范围待 E 确认（HD-SCHEMA-06） |
| `has_vector_cleanup` | DEFERRED | Vector 同步删除策略待 B（HD-SCHEMA-05） |
| `requires_confirmation` | FROZEN_BUSINESS_SEMANTIC | 最终判定 `*禁止模型生成` |
| `affected_count` | FROZEN_BUSINESS_SEMANTIC | 最终值 `*禁止模型生成` |
| `rollback_plan_id` | FROZEN_BUSINESS_SEMANTIC | 回滚计划引用语义冻结；回滚在 SQLite 事务模型可行性待 D |

### 5.6 13 组候选枚举处置

| 枚举（Schema 章节） | 处置 | 理由 / 说明 |
|---------------------|------|-------------|
| `source_type` 七值（2.1） | FROZEN_BUSINESS_SEMANTIC | 七值业务语义冻结；宿主覆盖`PENDING_C_CONFIRMATION` + SOP 导入复核（HD-SCHEMA-15/16）；`user_message` 等消息粒度不作为候选值（REJECTED 该项） |
| `event_type` 三值（2.2） | FROZEN_BUSINESS_SEMANTIC | 消息粒度角色三值语义冻结；与 `source_type` 分层 |
| `source_business_status` 八值（2.3） | FROZEN_BUSINESS_SEMANTIC | raw/completed/ignored PARTIAL，其余 UNVERIFIED；宿主状态语义`PENDING_C_CONFIRMATION` |
| `processing_status` 五值（2.4） | REVISED | **技术候选**，非冻结业务枚举；状态机待 A/B/D |
| `expression_type`（2.5） | FROZEN_BUSINESS_SEMANTIC | `explicit`/`implicit` 二值冻结；`inferred` 旧值 `REJECTED`；`candidate` 不作为表达类型值（由 `memory_status=candidate` 表达） |
| `knowledge_type` 六值（2.6） | FROZEN_BUSINESS_SEMANTIC | 六值业务语义冻结 |
| `memory_type` 四值（2.7） | FROZEN_BUSINESS_SEMANTIC | 短/中/长/ephemeral 业务语义冻结；分层边界/阈值`待 D`；`ephemeral` 必要性待 E |
| `memory_status` 六值（2.8） | FROZEN_BUSINESS_SEMANTIC | 统一生命周期优先字段 |
| `preference_scope` 五值（2.9） | FROZEN_BUSINESS_SEMANTIC | 五值业务语义冻结；与 A Provider 草稿 `scope` 差异见冲突登记第 5 项 |
| `sensitivity` 五值（2.10） | FROZEN_BUSINESS_SEMANTIC | 五级业务语义冻结；分级标准待 E 终审（HD-ANNO-05） |
| `conflict_type` 五值（2.11） | FROZEN_BUSINESS_SEMANTIC | 五值业务语义冻结；判定阈值算法待 B（HD-SCHEMA-04） |
| `resolution_status` 六值（2.12） | FROZEN_BUSINESS_SEMANTIC | 六值业务语义冻结；自动消解规则待 B |
| `forget_mode` 五值（2.13） | FROZEN_BUSINESS_SEMANTIC | 五值业务语义冻结；`full_reset` 安全边界待 E/D |

### 5.7 派生对象候选字段处置（统一）

| 派生对象 | 处置 | 理由 / 说明 |
|----------|------|-------------|
| 公共事件字段 14 项 | DEFERRED（语义候选沿用） | 与 Day1 Schema 语义一致者沿用为候选；本轮 Canonical v1 R-1 **候选裁定**提出 `captured_at` canonical / `collected_at` legacy transport alias，该统一关系待 D Reviewer 确认并完成团队冻结；transport 层采纳仍为 `PENDING_D_CONFIRMATION`；宿主/协议证据保持 `PENDING_C_CONFIRMATION`/`PENDING_D_CONFIRMATION` |
| `MemoryContext` 9 字段 | DEFERRED | `PENDING_C_CONFIRMATION` + `PENDING_D_CONFIRMATION`；`injection_status` 枚举、`context_version` 跨 Turn 复用待 C/D 决策 |
| `ToolExecutionEvent` 12 字段 | DEFERRED | `PENDING_C_CONFIRMATION`；`cancelled`/`partial` 是否入正式候选待 E/B/D 复核（HD-D2E-05） |
| `TurnFinalizedEvent` 7 字段 | DEFERRED | `PENDING_C_CONFIRMATION`；`stop_reason`/`finalization_reason` 枚举待 E 审 |

---

## 六、REJECTED 项汇总

| 被否决/不可冻结项 | 原来源 | 否决原因 | 替代方案 |
|-------------------|--------|----------|----------|
| `expression_type=inferred`（旧候选值） | Day1 Schema 旧稿 | 修订2 将 `inferred` 归一为 `implicit`，不作为独立枚举值 | 隐式推断偏好由 `memory_status=candidate` 表达生命周期 |
| `expression_type=candidate`（表达类型取值） | 标注规范旧术语 | `candidate` 是生命周期状态，不是表达类型值 | `memory_status=candidate`（Schema 枚举 2.8） |
| `event_status` 单一字段 | Day1 Schema 旧稿 | 已拆分为 `source_business_status`（业务结果）与 `processing_status`（内部流水线，技术候选）两个正交字段 | 枚举 2.3 + 枚举 2.4 |
| `source_type=user_message/agent_response/system_message`（作为来源类型候选值） | Day1 Schema 旧稿 | 消息粒度不再作为 `source_type` 候选值，其语义由 `event_type`（枚举 2.2）承载 | `source_type` 七值 + `event_type` 三值分层 |
| `contradiction`/`temporal_inconsistency` 判定阈值算法 | Day1 Schema 枚举 2.11 备注 | **E 轨道不可冻结**：判别逻辑属 B 轨道冲突检测模块实现层 | 移交 `待 B 确认`（HD-SCHEMA-04），登记 DEFERRED |

---

## 七、E 轨道可冻结业务语义细则

### 7.1 user_id / actor_id 语义边界

- **`user_id`**：数据归属与用户隔离的**业务硬约束**。所有核心业务对象（Preference、Knowledge、Conflict、ForgetPlan）及端到端会话均须具备 `user_id`；跨用户检索、偏好/知识/冲突/遗忘范围一律以 `user_id` 为过滤键；**跨 `user_id` 的读取、更新、删除、遗忘一律拒绝**并标记 `isolation_violation=true`、`sensitivity=critical`（S-08；标注规范 §5.3 正向/负向隔离测试）。
- **`actor_id`**：事件的实际发起者（用户/系统/Tool），同一 `user_id` 下可有多个 `actor_id`（如系统代用户执行操作）。
- **二者均禁止由 LLM/模型生成**，必须来自宿主侧业务事件或外部输入（Schema §4.2）。违反后果：用户隔离被破坏、虚构归属。
- 宿主事件中 `user_id`/`actor_id` 字段是否存在及语义，`PENDING_C_CONFIRMATION`（HD-SCHEMA-12）；UDS 用户身份绑定 `PENDING_D_CONFIRMATION`（D2 检查表第七章）。

### 7.2 版本与回溯

- `Preference` 每次更新 `version` 递增，`previous_version_id` 指向上一版本 `preference_id`，形成可回溯版本链（Schema §3.2 版本化业务要求）。
- `Knowledge` 通过 `superseded_by_id` 标记被替代条目；旧条目保留用于审计与回溯，不物理删除（`memory_status=superseded`）。
- 版本化 SQLite 实现（版本号生成、并发控制、历史版本保留）`待 D 确认`；`id` 生成策略（UUID v4/v7/纳秒时间戳）`待 D`（HD-SCHEMA-09）。

### 7.3 证据引用与来源

- 证据链最小语义（Evidence 子结构）：`evidence_event_ids`/`source_event_id`（来源事件引用）、`source_reference`（来源定位引用，非原始载荷）、`source_type`（来源大类）、`version` 链（版本引用）。
- 只有**真实业务事件**可成为证据；模型自述不得伪造证据 ID 或冒充真实 Tool 证据。
- 证据引用存储形态（内联/外部分片/文件引用）`待 D 确认`；Vector 不保存最终授权真相，命中必须回源 SQLite（引用 D3-B 检索契约 08 §3 已确认事实，但 08 本身未冻结）。

### 7.4 生命周期（Lifecycle）

- `memory_status` 六值为唯一优先生命周期字段；`is_active`/`is_outdated`/`should_decay` 过渡保留，待 D/E 统一后移除（HD-SCHEMA-13）。
- `candidate` 状态不参与用户级偏好检索链路、不参与偏好冲突判定；经复核确认且置信度达标后晋升 `active`。
- 临时要求到期自动标记 `memory_status=expired`。
- 短/中/长期流转阈值、存储分层、回收策略 `待 D 确认`（HD-SCHEMA-07），本文件不冻结。

### 7.5 冲突与六档优先级

冲突消解时来源可信度由高到低（Schema §3.4，待 SOP v1.1 导入复核）：

1. **用户最新显式配置**（手动配置/设置面板/显式声明）
2. **用户明确确认**（系统询问后用户肯定回复）
3. **真实 Tool 执行结果**（Tool 实际运行返回的输出/状态码）
4. **多次一致行为**（≥2 个独立 Turn/事件的一致行为模式，各次无矛盾）
5. **单次行为推断**（从单次行为/事件推断）
6. **模型自身推测**（LLM 推理结论，未经行为验证或 Tool 确认）

**约束**：第 6 档不得覆盖第 1–5 档任何高可信来源，不得直接成为事实真源；模型推测仅可作为候选提示供用户确认，确认前 `memory_status` 必须保持 `candidate`。同等优先级来源之间如存在矛盾，标记 `detected` 待进一步消解。作用域不同优先判定可共存。

### 7.6 遗忘：先预览再确认

- 系统解析 `target_selector` → 生成 `resolved_target_ids` → 向用户展示受影响条目预览 → 用户确认 → 执行删除（Schema §3.5、标注规范 §2.5、正例 5）。
- `resolved_target_ids`、`requires_confirmation` 最终判定、`affected_count` 最终值、整体删除决策**均禁止模型生成**，由遗忘规则引擎或系统计算产出。
- 遗忘以 `resolved_target_ids` 为精准范围，不得模糊删除后声称已精准遗忘；硬删除不得留可检索明文残留（S-09）。
- 已遗忘记忆不得重新注入 MemoryContext 或检索返回（G0-E-03）；`forgotten_excluded_count` 统计口径待 D/E 确认。

### 7.7 敏感度与敏感载荷红线

- `sensitivity` 五级（none/low/medium/high/critical）业务语义冻结；分级标准与识别规则待 E 终审（HD-ANNO-05）。
- 高敏正文（`sensitivity=critical`，如 API Key/Token/密码/私钥/跨用户数据，S-01..S-04、S-08）**绝对不得以明文**进入引用存储或摘要，仅可写入脱敏占位（如 `[REDACTED_API_KEY]`）或仅 ID 引用。
- `sensitivity` 最终定级由敏感过滤规则引擎产出，**模型不得覆写或降级**（Schema §4.2 安全终判）。
- 敏感过滤发生在事件入库阶段（`source_business_status=ignored`），被标记 `ignored` 的事件不得进入后续抽取与存储流水线。

### 7.8 Tool 结果可信度业务规则

> 依据 D2 检查表第八节与标注规范 §2.3/§2.6，全部规则当前依赖 C 真实取证，证据状态 `UNTESTED`/`PENDING_C_CONFIRMATION`。**没有真实 Tool 证据时，不得把模型自述成功写成已验证知识**。

| 场景 | 业务处理规则 | 是否形成记忆 | 当前证据状态 |
|------|--------------|--------------|--------------|
| success | 仅真实 Tool 成功证据允许形成成功知识；成功但属瞬态上下文（一次性查询）不得形成长期记忆（标注规范正例 7） | 视复用价值 | `PENDING_C_CONFIRMATION` |
| failure | 不得从失败信息推断任何知识；`should_form_memory=false`；仅可沉淀带条件失败经验（`knowledge_type=failure_experience`，G0-E-06） | 否（失败经验可候选） | `PENDING_C_CONFIRMATION` |
| cancelled | 按取消处理，不形成成功知识；取消前已产生副作用须记录 `side_effect=true` 并评估 `rollback_required`（G0-E-07）；`cancelled` 是否入 D3 正式候选待 E/B/D 复核（HD-D2E-05） | 否 | `PENDING_C_CONFIRMATION` |
| timeout | 等同失败处理，结果保持未知，不得以超时冒充成功或推断失败（G0-E-08） | 否 | `PENDING_C_CONFIRMATION` |
| partial | 仅成功部分可形成知识；失败项敏感内容脱敏（`[REDACTED_FILENAME]`）；不得把 partial 整体视为完全成功或完全失败（G0-E-09）；`partial` 是否入 D3 正式候选待 E/B/D 复核 | 视成功部分 | `PENDING_C_CONFIRMATION` |
| side_effect | 有副作用的执行须记录副作用；副作用信息不得由模型自述 | 视情况 | `PENDING_C_CONFIRMATION` |
| rollback | 记录 `rollback_required`/`rollback_status`；**回滚不视为成功**，不得形成成功知识（G0-E-10）；SQLite 事务可行性待 D | 否 | `PENDING_D_CONFIRMATION` |
| 模型自述 | 不得把模型自述当真实 Tool 结果；六档优先级中模型推测为第 6 档，不得覆盖第 1–5 档高可信来源；自述仅可作为 `memory_status=candidate` 候选（G0-E-14） | 仅候选 | `PENDING_C_CONFIRMATION` |

**红线**：`execution_status != success`（含 failure/cancelled/timeout）不得形成成功知识；失败、取消、超时、部分执行、副作用、回滚在业务上必须分别处理，不得混为一类。

### 7.9 临时要求与正式偏好边界

- `is_temporary=true` 或 `should_persist=false` 的偏好条目不得产生正式长期偏好，`memory_status` 必须为 `candidate` 或 `expired`。
- 临时要求生命周期限定于当前会话或指定时间窗口，到期自动 `memory_status=expired`，不进入用户级偏好检索链路，不参与偏好冲突判定。
- 临时/候选偏好可通过审核流程晋升为正式偏好，但需版本化记录晋升事件（新 `version`，`previous_version_id` 指向临时/候选条目）。

### 7.10 禁止模型生成字段清单（E 冻结）

| 组别 | 字段 | 生成责任方 |
|------|------|-----------|
| 用户归属 | `user_id`（所有对象）、`actor_id`（MemorySourceEvent） | 宿主侧业务事件/外部输入 |
| 时间事实 | `occurred_at`（MemorySourceEvent） | 宿主侧业务事件 |
| 冲突最终结果 | `resolution_status`（resolved_auto/resolved_manual/unresolvable）、`resolution_strategy`、`resolution_confidence`、`resolved_by` | 消解规则引擎/系统计算 |
| 安全终判 | `sensitivity` 最终定级（模型不得覆写） | 敏感过滤规则引擎 |
| 遗忘最终决策 | `resolved_target_ids`、`requires_confirmation` 最终判定、`affected_count` 最终值、整体删除执行决策 | 遗忘规则引擎/系统计算 |
| 幂等与去重 | `idempotency_key`（MemorySourceEvent） | 业务事件/系统生成（接入层） |

---

## 八、可冻结与不可冻结清单

### 8.1 E 轨内部业务语义状态（`FROZEN_BUSINESS_SEMANTIC`，不等于团队 `FROZEN`）

- 七类业务概念的定义与边界；
- 五原始业务对象全部字段的业务语义、来源规则与必填性候选；
- 13 组候选枚举的业务取值范围；
- `user_id`/`actor_id` 语义边界与用户隔离业务硬约束；
- 版本与回溯、证据引用、生命周期、敏感度、冲突六档优先级、遗忘先预览再确认、临时/正式偏好、Tool 结果可信度、禁止模型生成清单、敏感载荷红线等业务规则。

### 8.2 不可冻结项清单（全部 DEFERRED 或待对应轨道确认）

| 技术实现事项 | 责任轨道 | 计划冻结窗口 | 本文件状态 |
|-------------|---------|-------------|------------|
| SQLite 数据库表结构、schema 迁移、唯一约束、外键 | D | D3–D5 | DEFERRED（`PENDING_D_CONFIRMATION`） |
| Vector Collection Schema / 索引布局 | B | D4–D6 | DEFERRED（`PENDING_B_CONFIRMATION`） |
| FTS5 分词配置与索引策略 | B | D4–D6 | DEFERRED |
| C++ 侧结构体定义（cpp-bridge/、memory-client/） | C/D | D4–D6 | DEFERRED |
| IPC JSON Schema（UDS 消息结构）、`protocol_version`、`request_id`、错误码 | D | D3–D5 | DEFERRED（`PENDING_D_CONFIRMATION`） |
| 存储分层边界（short/medium/long 时间/频率阈值） | D | D4–D6 | DEFERRED（HD-SCHEMA-07） |
| Embedding 向量维度与存储格式 | A | D4–D6 | DEFERRED（`PENDING_A_CONFIRMATION`） |
| RRF 融合权重（k）与衰减函数 | B | D5–D7 | DEFERRED |
| 冲突检测阈值与消解规则引擎 | B | D5–D7 | DEFERRED（HD-SCHEMA-04） |
| 遗忘级联规则与回滚审计机制 | E/D | D5–D7 | DEFERRED（HD-SCHEMA-06） |
| Preference 版本化 SQLite 实现 | D | D4–D6 | DEFERRED |
| 敏感过滤规则引擎具体实现 | E | D5–D7 | DEFERRED（HD-ANNO-05） |
| `*_id` 全局唯一标识生成策略（UUID v4/v7 等） | D | D3–D5 | DEFERRED（HD-SCHEMA-09） |
| `processing_status` 状态机条件 | A/B/D | D3 起 | REVISED（技术候选，非冻结业务枚举） |
| `confidence_score` 量化模型与衰减策略 | A/E | D3 Gate 前 | DEFERRED（HD-SCHEMA-03） |
| 幂等/取消/断线重连机制与 deadline 超时语义 | D | D3 协议草案 | DEFERRED（D-05/06/07/08） |
| KYSEC 最小授权真实规则 | D | Gate 1 | DEFERRED（HD-D2E-B02） |

---

## 九、跨文档冲突登记

> 以下为实施本契约时核验到的跨文档差异/过时描述。**本文件不修改任何原文件**，仅登记差异、当前选择与待决责任轨道。

| 编号 | 冲突/差异描述 | 来源双方 | 当前选择（本契约立场） | 待决责任轨道 |
|------|---------------|----------|------------------------|--------------|
| C-01 | `expression_type` 取值：标注规范修订2（2026-07-31）已将 `expression_type` 归一为 `explicit`/`implicit` 二值，`candidate` 不作表达类型值；但 Schema §2.5 备注（约第 136 行）仍写「标注规范当前使用 explicit/implicit/candidate 三值」——**此描述已过时** | `datasets/ANNOTATION_GUIDELINE_V0.1.md`（修订2，§2.1）vs `docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md`（§2.5 备注） | 以标注规范修订2 为准：二值冻结；`candidate` 由 `memory_status=candidate` 表达。**处置（2026-09-03，day12-e-01）**：Schema §2.5 过时三值描述已由 day12-e-01 修正（见 `KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md` R-2）；HD-SCHEMA-14 的 SOP v1.1 导入后终审仍保留 | E（Schema §2.5 过时描述修正属 Schema 文件维护任务，需独立任务卡，本任务不修改 Schema） |
| C-02 | HD-SCHEMA-14 归属：是 `MEMORY_BUSINESS_SCHEMA_V0.1.md` 第六章「未确认能力与人工决策待办」条目，**不是** `TECHNICAL_DEBT_REGISTER.md` 中的 TD 条目（后者仅 TD-001..004） | Schema 第六章 vs 技术债登记表 | 引用时区分「Schema 待办」与「正式技术债登记」；本文件仅在 FREEZE_BLOCKERS 引用 HD-SCHEMA-14 为 Schema 待办 | E（文档维护） |
| C-03 | `captured_at` vs `collected_at`：Day1 Schema 用 `captured_at`（事件捕获入库时间），D2 检查表公共字段用 `collected_at`（事件捕获入库时间），两词语义是否等价未定 | Schema §3.1 vs D2 检查表第十一章字段差异记录区 | **业务裁决候选（2026-09-03，Canonical v1 R-1）**：本轮 E 轨提出 `captured_at` 为 Canonical 事件捕获时间字段、`collected_at` 为 legacy transport alias，业务语义一一对应，transport→business 必经 Adapter/Mapping；该裁决候选待 D Reviewer 确认并完成团队冻结。**C/D 实现 handoff 显式保留**：ADR-010 IPC metadata、D2 检查表候选公共字段、A Provider 草稿的 transport 层 `collected_at` 采纳/更名方案须书面冻结（不修改 `protocol_version`），登记 TD-060 | C/D（实现 handoff）+ E（语义候选已提出，待 D Reviewer 确认） |
| C-04 | `execution_status` 取值集合：标注规范 §2.3 为 `success`/`partial`/`failure`/`timeout` 四值；D2 检查表第五章新增 `cancelled` 候选；G0-E-07 验证 `cancelled`；`partial` 与 `failure` 业务边界见检查表第八节 | 标注规范 §2.3 vs D2 检查表第五/八章 vs 案例集 G0-E-07/09 | `cancelled`/`partial` 是否入 D3 正式候选待 E/B/D 复核（HD-D2E-05）；本文件按候选规则描述，不冻结取值集合 | E/B/D（HD-D2E-05） |
| C-05 | A Provider 契约草稿字段简化：`TurnFinalizedEvent` dataclass 字段（session_id/user_text/assistant_text/tool_results/source 三值/occurred_at/collected_at）较 Schema 分层显著简化；`PreferenceCandidate.scope` 用 `global`/`session`/`project` 与 Schema `preference_scope`（global/topic/tool/session/time_window）不一致 | `docs/day3/06_provider_contract_v1.md` vs Schema §3.2/§2.9 | 该草稿为**前向草稿、非冻结契约**；本文件以 Schema 业务语义为冻结基准，不引用草稿字段作为已确认结构 | A（实现字段对齐）；C/D/E（待架构文档补齐后复核） |
| C-06 | D3-B 检索契约（08/09）状态：08 标注「D3-B 冻结候选，PR #20 Review 返工中」，09 状态 `REWORK`；`DEFERRED_CROSS_TRACK` 项（memory_status 检索集合、sensitivity 可见范围、full reset 授权等）属 E 待决 | `docs/day3/08_vector_retrieval_contract_v1.md` + `09_retrieval_contract_review_matrix.md` | 本文件不把 08/09 当作已冻结事实引用，仅登记 E 待决输入与阻断状态 | B（PR #20 返工）；D/E（跨轨待决） |
| C-07 | Schema §2.3 枚举 2.3 说明与标注规范 §2.3 的 `execution_status` 术语范围差异（业务结果状态 vs Tool 执行状态） | Schema 枚举 2.3 vs 标注规范 §2.3 | 两处均为「业务结果」语义的候选表达，取值集合差异由 C-04 处理；本文件保持来源原样引用 | E/B/D（复核） |

---

## 十、FREEZE_BLOCKERS（冻结阻断项）

> 依据 D2 预审报告（S-05）最终 Gate 结论 `BLOCKED` 与 Schema 第六章待办（S-01）。**下列阻断项是 Day3 冻结的最低前置条件缺口；不得为了完成 Day3 而删除或弱化任何一项。** 本文件仅登记，关闭责任属对应轨道。

### 10.1 D2 预审报告阻塞项（HD-D2E-B01..B07）

| 编号 | 阻断项 | 影响范围 | 责任轨道 | 所需证据 / 解除条件 |
|------|--------|----------|----------|---------------------|
| HD-D2E-B01 | 真实 Kaiming Hook 阻断（闭源二进制、无源码、无签名权限、Socket 路径硬编码） | D 真实 UDS 可达性、真实 Hook 构建/安装/启动 | D（需人工决策路线） | Gate 1 获取 SDK 源码/签名权限，或降级方案（LD_PRELOAD/socat/SDK 合作） |
| HD-D2E-B02 | KYSEC 最小授权仅 ACL 模拟，未写真实规则 | D 授权边界 | D（需环境/权限协调） | KYSEC 开发者文档 + 测试环境授权 + 最小规则集验证 |
| HD-D2E-B03 | 回退基线未闭合（标准 rollback 未在麒麟执行、进程残留、原版完整恢复未证实） | D 安装与回退 | D | 补跑标准 rollback（`test_rollback.sh` 已入库），补齐前后 SHA/owner/mode/ACL/包版本对比与进程清理 |
| HD-D2E-B04 | C 真实 Context/Tool/Turn 取证缺位 | 三个派生对象字段与失败语义 | C | C 在麒麟 VM 完成真实宿主取证回填 |
| HD-D2E-B05 | 基线 DOCX（01–06）未导入 | 字段语义待权威基线终审 | 团队/E | 人工导入 `docs/baseline/` 并版本核验 |
| HD-D2E-B06 | 案例集 G0-E-01..14 全部为设计稿未执行 | C/D Day2 验收 | C/D/E | C/D 在真实环境执行对应案例（required_evidence_level 均为 `HOST_VERIFIED`） |
| HD-D2E-B07 | `evidence/gate0` 硬编码凭据风险（已识别 High/Critical，不输出明文） | 安全红线 | 安全渠道 | 按 SECURITY.md 密钥泄露流程处理（轮换 + 清理历史 + 通知 + 记录） |

### 10.2 Schema 关键待办（HD-SCHEMA-01..16 中与本契约强相关的项）

| 编号 | 待办 | 责任轨道 | 本契约依赖 |
|------|------|----------|------------|
| HD-SCHEMA-01 | 导入赛题原文/SOP/SDK 能力边界基线至 `docs/baseline/` | 团队/E | 全字段语义权威终审 |
| HD-SCHEMA-02 / 12 / 16 | C 麒麟 VM 取证宿主事件结构（user_id/actor_id/turn_id/tool_call_id/occurred_at、source_type 七值、event_type 三值） | C | `PENDING_C_CONFIRMATION` 字段回填 |
| HD-SCHEMA-03 | A/E 确认 `confidence_score` 计算模型与衰减策略 | A/E | Preference/Knowledge 字段 DEFERRED 解除 |
| HD-SCHEMA-04 | B 确认冲突判定阈值与 `is_auto_resolvable` 标准 | B | Conflict 算法项 REJECTED/DEFERRED 解除 |
| HD-SCHEMA-05 | B 确认 Vector 与 SQLite 真源一致性策略 | B | `has_vector_cleanup` DEFERRED 解除 |
| HD-SCHEMA-06 | E 确认遗忘级联范围与 `full_reset` 安全边界 | E | ForgetPlan `is_cascade`/`full_reset` DEFERRED 解除 |
| HD-SCHEMA-07 | D 确认短/中/长分层边界与存储布局 | D | `memory_type` DEFERRED 解除 |
| HD-SCHEMA-08 | B 确认检索评测指标基线（Recall@K、MRR、NDCG） | B | REQ-07 评测口径 |
| HD-SCHEMA-09 | D 确认 `*_id` 生成策略与 IPC 兼容性 | D | ID 生成 DEFERRED 解除 |
| HD-SCHEMA-11 / HD-ANNO-08 | 导入架构设计审查报告并复核 | E | 字段/规则复核输入 |
| HD-SCHEMA-13 | D/E 确认 `memory_status` 统一与过渡字段移除 | D/E | Lifecycle 过渡字段 REVISED 闭合 |
| HD-SCHEMA-14 | E 终审 `expression_type` 归一（待 SOP v1.1 导入） | E | `expression_type` FROZEN 语义的终审确认 |
| HD-SCHEMA-15 | 导入 SOP v1.1 实体文件复核 source_type 七值/event_type/六档优先级/expression_type | 团队/E | 冲突优先级与枚举的权威复核 |

### 10.3 小结：可冻结 vs 不可冻结

- **E 轨内部已收口语义（`FROZEN_BUSINESS_SEMANTIC`）**：E 轨道负责的业务语义、对象关系、字段含义、版本与生命周期规则、Tool 结果可信度业务原则、禁止模型生成清单、敏感载荷红线可在 E 轨内部标记为 `FROZEN_BUSINESS_SEMANTIC`；该标记仅表示 E 轨内部语义已收口，**不等于团队级 `FROZEN`，也不绕过 §12.2 的 Reviewer + merge 冻结门槛**。
- **不可冻结（保持 DEFERRED/UNVERIFIED/PENDING_*）**：C 宿主真实事件结构、D IPC 协议/持久化/KYSEC/回退、B 检索阈值/Vector 布局、A Embedding 实现细节、基线 DOCX 导入——上述实现事实必须由对应轨道取证/决策后才能冻结，本文件不代为闭合。

---

## 十一、性能指标声明

依据追踪矩阵第九节（S-06），以下四项比赛性能指标当前**全部 `UNVERIFIED`**，未经真实评测环境执行，**不得解读为已达标**。本文件不声称任何指标达成：

| 指标 | 目标值 | 评测责任 | 当前状态 |
|------|--------|----------|----------|
| 偏好提取准确率 | ≥85%（待导入权威基线复核） | E（主责）/ A（协作） | `UNVERIFIED` |
| 知识检索召回率 | ≥85%（待导入权威基线复核） | B（主责）/ A（协作） | `UNVERIFIED` |
| 检索响应时间 | ≤500ms（待导入权威基线复核） | B（主责）/ D（协作） | `UNVERIFIED` |
| 知识冲突处理正确率 | ≥88%（待导入权威基线复核） | B（主责）/ E（协作） | `UNVERIFIED` |

> 目标值本身来自比赛方案及项目需求基线，待 D3 Gate 前以导入后的权威基线全文复核。评测未执行、封存集未制作、哈希未锁定（标注规范第七章），本文件不做任何性能达标声明。

---

## 十二、变更记录与冻结为团队基线条件

### 12.1 变更记录

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v1 | 2026-08-09 | 候选初稿：基于 Day1 Schema（修订2）、Day1 标注规范（修订2）、Day2 冻结前检查表、Day2 业务验收案例集、Day2 E Gate0 业务预审报告与当前 main 可核验 A/B/C/D 材料，冻结 E 轨道业务语义 v1 候选（七类业务概念、对象关系、字段处置、业务规则）；登记 FREEZE_BLOCKERS 与跨文档冲突；性能指标保持 `UNVERIFIED`。状态 `CANDIDATE_FOR_FREEZE`。 | E 轨道 |
| v1（修订1） | 2026-09-03 | Canonical 业务语义候选收口（day12-e-01）：头部增补 Canonical 候选关系声明；§5.1 `captured_at`、§5.7 公共事件字段与 C-03 同步 R-1 候选裁定（`captured_at` canonical / `collected_at` legacy transport alias），并显式保留 C/D 实现 handoff TD-060；C-01 追加 Schema §2.5 过时描述处置。Canonical v1 与本文件当前均保持 `CANDIDATE_FOR_FREEZE`，不在 Reviewer+merge Gate 前建立未审核候选覆盖关系。 | E 轨道 |

### 12.2 升级为团队冻结基线（v1.0 冻结基线）的条件

以下条件**全部满足**后方可视为团队冻结基线：

1. **非作者 D Reviewer 批准**本文件（E 不批准 E 自己的变更）；
2. 本文件对应 PR 合并；
3. HD-D2E-B01..B07 阻断项均有明确处置（见第十章）；
4. HD-SCHEMA-01..16 关键待办经权威基线导入/对应轨道取证后闭合；
5. C 轨真实宿主取证回填（`PENDING_C_CONFIRMATION` 字段解除）；
6. D 轨 UDS/IPC 协议草案完成、KYSEC/回退/幂等/取消证据补齐（`PENDING_D_CONFIRMATION` 解除）；
7. 跨文档冲突登记（第九章）逐项闭合且有明确决议；
8. Evidence Reviewer 确认本文件所有证据状态标注与当时实际证据等级一致（无 `HOST_VERIFIED` 虚标）。

在满足以上条件之前，本文件保持 `CANDIDATE_FOR_FREEZE`，**不得作为 SQLite 物理 Schema、Migration、Vector Collection Schema、C++ 结构体、IPC Payload、错误码或 Provider 接口的唯一依据**。

---

> **本文档到此结束。后续修订将在 D Reviewer 审查、C 麒麟取证、D 协议草案、SOP v1.1 导入与基线 DOCX 导入后按 A–E 轨道反馈进行。**
