# Day3 Gold Label 与评测口径 v1 候选

- **版本**：v1
- **状态**：`CANDIDATE_FOR_FREEZE`
- **阶段定位**：Day3 / Gate 0 / E 轨道 Gold Label 与评测口径候选
- **作者轨道**：E（记忆业务、安全、数据集与业务指标）
- **Reviewer 轨道**：D（IPC、SQLite、Outbox、虚拟机成品化与发布）
- **冻结为团队基线条件**：**只有非作者 D Reviewer 批准且 PR 合并后，本文档方可视为团队冻结基线**。本文件的 `CANDIDATE_FOR_FREEZE` 状态仅表示 E 轨道单方面提出的 v1 候选评测口径语义集合，**不代表已被 D 批准、不代表 D3 Gate 通过、不代表任何指标已达标、不代表任何宿主行为或实现能力已被验证**。
- **用途**：把比赛四项官方性能指标、Day1 标注规范（v0.1 DRAFT）、Day2 Gate 0 业务验收案例集（G0-E-01..14）以及 Day3 业务契约与安全验收契约 v1 候选，映射为**可重复计算评测口径 + Gold Label 判定规则 + 证据边界**，为后续偏好提取、知识检索、冲突处理、精准遗忘与性能评测冻结判定规则和证据边界。
- **本文件冻结的是评测定义，不是已取得的评测结果**：本文件定义 Gold Label 判定规则、计算口径、无效样本规则、聚合方式与证据要求；**不含任何虚构的准确率、召回率、延迟、冲突正确率分数或 PASS 结论**。所有当前结果状态一律 `PENDING` / `UNVERIFIED`。
- **本文件不是**：实际评测数据集、Gold Label 样本文件、评测脚本、评测报告或性能达标声明。上述产物属后续独立任务（见「十四、FREEZE_BLOCKERS」与本文件「七、知识 Gold Label 判定规则」相关约束）。
- **本任务性质声明**：本任务为纯 Markdown 评测规范任务（`runtime_required=false`、`runtime_commands=[]`）。L0/L1 的 `python3 -m pytest --version` 仅作为控制器允许的**本地工具可用性探测**，**不是评测执行证据**；本文件不得把该探测结果表述为正式评测已执行。

---

## 一、依据来源与局限声明

### 1.1 依据来源（仓库内已核验文件）

| 编号 | 来源 | 路径 | 仓库状态 |
|------|------|------|----------|
| R-01 | 赛题要求与项目交付追踪矩阵 v0.1 DRAFT（修订2，2026-07-31），第九节「比赛性能指标追踪」 | `docs/project-management/REQUIREMENT_TRACEABILITY_MATRIX.md` | SOURCE_VERIFIED（在库；四项指标全 `UNVERIFIED`） |
| R-02 | Day1 标注规范 v0.1 DRAFT（修订2，2026-07-31） | `datasets/ANNOTATION_GUIDELINE_V0.1.md` | SOURCE_VERIFIED（在库） |
| R-03 | Day2 业务验收案例集 v0.1 DRAFT（G0-E-01..14） | `datasets/GATE0_BUSINESS_ACCEPTANCE_CASES_V0.1.json` | SOURCE_VERIFIED（在库；`document_status=DRAFT`，全部 `BLOCKED`/`UNTESTED`） |
| R-04 | Day3 记忆业务契约 v1 候选 | `docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md` | SOURCE_VERIFIED（在库，`CANDIDATE_FOR_FREEZE`） |
| R-05 | Day3 记忆安全验收契约 v1 候选 | `docs/architecture/D3_MEMORY_SECURITY_ACCEPTANCE_V1.md` | SOURCE_VERIFIED（在库，`CANDIDATE_FOR_FREEZE`） |
| R-06 | Evaluation 模块 README | `evaluation/README.md` | SOURCE_VERIFIED（在库；「仅建立目录和职责边界，尚无评测代码或指标」） |
| R-07 | 项目 README | `README.md` | SOURCE_VERIFIED（在库；业务代码尚未开始） |

### 1.2 局限声明（如实登记，不虚标）

- **基线 DOCX 未导入**：赛题原文、总体架构 SOP v1.1、官方 SDK 与 OS Agent 能力边界等基线文档（01–06）当前均未被 Git 仓库跟踪，`docs/baseline/` 目录下无实体文件。四项指标的**目标值与阈值**以追踪矩阵第九节与业务契约第十一节为据（来源「比赛方案及项目需求基线，待导入权威基线复核」），**待 D3 Gate 前人工导入权威基线后全文复核**（HD-D2E-B05）。
- **C 轨真实宿主取证缺位**：`MemoryContext`/`ToolExecutionEvent`/`TurnFinalizedEvent` 真实宿主事件结构在当前仓库不可见，全部 `C_D2_EVIDENCE_MISSING`（HD-D2E-B04）。Tool Result 标注字段均为 DRAFT 语义层占位，`UNVERIFIED`。
- **D 轨关键证据未闭合**：真实 Kaiming Hook `BLOCKED`（HD-D2E-B01）、KYSEC 最小授权 `UNVERIFIED`（HD-D2E-B02）、幂等/取消/断线重连 `UNTESTED`/`NOT_FOUND`、deadline 超时语义 `PARTIAL`、回退基线 `PARTIAL`（HD-D2E-B03）。
- **B 轨检索契约未冻结**：`docs/day3/08_vector_retrieval_contract_v1.md`（`FROZEN_CANDIDATE`）与 `09_retrieval_contract_review_matrix.md`（`REWORK`）未冻结；RRF k 值、`memory_status` 检索集合、冲突判定阈值（HD-SCHEMA-04/HD-SCHEMA-08）待 B 确认 → 本文件相关口径标注 `PENDING_B_CONFIRMATION`。
- **封存集尚未建立**：封存测试集尚未制作、尚未锁定 SHA-256 哈希（标注规范第七章）；本文件只定义 Gold Label 规则，**不可声称任何数据集已封存、任何复核已完成**。
- **双人复核流程为规则、当前未执行**：标注规范 §4.1 定义了双人复核流程，但当前尚无标注样本产出，流程未实际执行，不得声称其已执行。
- **证据状态口径**：本文件遵循追踪矩阵第五节双轴口径——业务侧 `PENDING`/`UNVERIFIED`/`PARTIAL`/`CANDIDATE_FOR_FREEZE`；SDK/实现侧 `UNTESTED`/`SOURCE_VERIFIED`/`ABI_VERIFIED`/`HOST_VERIFIED`/`PARTIAL`/`NOT_FOUND`/`BLOCKED`/`DEFERRED`/`PENDING_C_CONFIRMATION`/`PENDING_D_CONFIRMATION`/`PENDING_B_CONFIRMATION`/`PENDING_E_CONFIRMATION`/`UNVERIFIED`。**无真实银河麒麟宿主证据的事项一律不得标 `HOST_VERIFIED`/`PASS`**。

---

## 二、术语对齐

以下术语与既有契约共用，**不重新发明**（引用标注规范 §一、业务契约 §三、安全契约 §三）：

| 术语 | 含义 | 来源对象/枚举 |
|------|------|--------------|
| Gold Label | 经人工规则与双人复核确定的最终标注标签，是该样本在评测中的标准答案 | 标注规范 §一 |
| 偏好 | 用户对系统行为的个性化要求，可为显式或隐式 | `Preference`；`expression_type` 仅 `explicit`/`implicit` 二值（`candidate` 不作表达类型值） |
| 知识 | 经过抽取和归一化的结构化信息条目 | `Knowledge`；`knowledge_type` 六值（workflow/case/template/fact/constraint/failure_experience） |
| Tool Result | 官方 AI 助手 Tool 调用执行后返回的结果事件 | `MemorySourceEvent.source_type=tool_result`；`execution_status` 候选含 success/partial/failure/timeout/cancelled（cancelled/partial 是否入正式候选待 E/B/D，HD-D2E-05） |
| 冲突 | 两条或多条知识/偏好之间的语义或事实不一致 | `Conflict`；`conflict_type` 同 Schema 枚举 2.11（判定阈值算法待 B，HD-SCHEMA-04） |
| 精准遗忘 | 按指定粒度仅删除目标记忆条目，不波及无关数据 | `ForgetPlan`；`forget_mode` 五值（single_item/session/topic/time_window/full_reset） |
| 生命周期 | 记忆统一生命周期语义 | `memory_status` 六值（active/superseded/deprecated/expired/removed/candidate）为唯一优先字段 |
| 敏感类型 | 命中即强制不形成记忆的敏感载荷类别 | S-01..S-09（标注规范 §5.1，**严格沿用，不改号不改义**） |
| 六档冲突优先级 | 冲突消解时来源可信度由高到低 | 业务契约 §7.5；第 6 档（模型推测）不得覆盖第 1–5 档 |
| 禁止模型生成字段 | 由宿主/规则引擎/系统计算产出、LLM 不得生成或覆写的字段 | 业务契约 §7.10 与安全契约 SEC-LLM 组 |

---

## 三、证据状态口径与当前事实

1. **四项比赛指标**（追踪矩阵第九节、业务契约第十一节）：当前全部 `UNVERIFIED`，未经真实评测环境执行，**不得解读为已达标**。
2. **G0-E-01..14 案例**：全部为设计稿，`current_status` 全部 `BLOCKED`/`UNTESTED`，`required_evidence_level` 全部 `HOST_VERIFIED`（目标，非当前状态）；本文件如实沿用，**不提升任何案例为 `HOST_VERIFIED`/`PASS`**。
3. **本文件涉及的 Gold Label 判定规则**：全部处于规则定义状态，**未在任何数据集上执行**，相关验证状态一律 `PENDING`/`UNVERIFIED`。
4. **`UNVERIFIED` 与 `HOST_VERIFIED` 为不同枚举体系**（业务/项目维度 vs SDK 能力维度），不得混为同一枚举；本文件不宣称任何 `HOST_VERIFIED`。

---

## 四、四项比赛基础指标 OFFICIAL_REQUIREMENT 口径

> 四项指标目标值与阈值**原样保留**（≥85% / ≥85% / ≤500ms / ≥88%），不得擅自降低或改写。目标值来源「比赛方案及项目需求基线（待导入权威基线复核）」（HD-D2E-B05）。每项指标定义七个要素：评测对象、样本纳入条件、分子/分母或公式、无效样本处理、聚合方式、输出字段、证据要求。**当前状态一律 `UNVERIFIED`**；涉及统计细节（p50/p95、warmup、重复次数等）见「五、TEAM_DEFINED 统计细节」。

### M1 偏好提取准确率 ≥85%（E 主责 / A 协作）

- **指标名称**：偏好提取准确率（Preference Extraction Accuracy）
- **目标值（OFFICIAL_REQUIREMENT）**：≥85%
- **评测对象**：偏好提取链路（事件 → 候选偏好提取 → `Preference` 条目）输出与「Preference Gold Label」（见第六章）的比对结果。
- **样本纳入条件**：偏好 Gold Label 样本集中的全部有效样本，包括：应形成正式偏好的正样本（显式长期/隐式）、应形成临时偏好的样本、以及**不应创建偏好的负样本**（闲聊、瞬态上下文、Tool 失败、敏感命中、临时撤销等，见第六章）。每个样本记录 `user_id`、上下文 Turn 序列、事件证据与 Gold Label 判定依据。
- **分子/分母或公式**：
  - 分子 = 系统输出与 Gold Label **完全一致**的样本数。完全一致定义：`preference_key`、`preference_value`、`scope`（`preference_scope`）一致；且 `expression_type`、`is_temporary`/`should_persist` 与 Gold Label 一致；正式/临时归属一致（`memory_status=active` 或 `candidate`/`expired` 语义一致）。
  - 分母 = 纳入的偏好样本总数（正样本 + 负样本）。
  - 准确率 = 分子 / 分母。负样本命中（系统正确未创建偏好）计入分子。
- **无效样本处理**：标注规范 §4.1 争议裁决前标记为 `memory_status=candidate` 的边界样本**不进入分母**，单列为边界子集报告；命中 S-01..S-09 的样本按「强制不形成记忆」处理——系统正确拒绝则计入正确（命中 S-01..S-04/S-08 的样本 `should_ignore=true`，从常规分母剔除并单列安全拒绝子集）。
- **聚合方式**：样本级宏平均（每个样本等权）；输出按 `expression_type`（explicit/implicit）、正式/临时、`preference_scope` 拆分子集报告。置信度量化模型（HD-SCHEMA-03）未定前，置信度相关判定保持 `PENDING_A_CONFIRMATION`/`PENDING_E_CONFIRMATION`，不冻结具体阈值。
- **输出字段**：`metric_name`、`metric_result`、`target_threshold`、`sample_count`、`correct_count`、`true_positive`、`true_negative`、`false_positive`、`false_negative`、`accuracy`、`subgroup_breakdown`、`gold_label_version`、`dataset_version`、`implementation_commit`、`environment`、`evidence_reference`。
- **证据要求**：评测脚本输出 + 样本集版本引用 + 复现命令与环境记录；在银河麒麟 V11 x86_64 真实环境执行时按 `runtime-validation.md` 保留环境探针、命令、exit code、stdout/stderr 与日志。当前状态 `UNVERIFIED`。

### M2 知识检索召回率 ≥85%（B 主责 / A 协作）

- **指标名称**：知识检索召回率（Knowledge Retrieval Recall）
- **目标值（OFFICIAL_REQUIREMENT）**：≥85%
- **评测对象**：知识检索链路（Vector + FTS5 + 应用层 RRF，`memory-service` 检索实现）针对知识 Gold Label 查询集的召回表现。
- **样本纳入条件**：知识 Gold Label 查询集——每条查询包含 `query`、`user_id`、期望命中的 `knowledge_id` 集合（Gold Label 正解）及上下文。仅纳入**已验证事实知识**（见第七章）对应的查询；已遗忘条目、敏感条目、瞬态上下文不进入正解集合。
- **分子/分母或公式**：
  - 分子 = 在检索结果 Top-K 中命中的 Gold Label 知识条目数（按 `knowledge_id` 判定）。
  - 分母 = 该查询 Gold Label 正解知识条目总数。
  - Recall@K = 分子 / 分母。
- **无效样本处理**：命中 S-01..S-09 的查询样本剔除并单列；无正解（Gold Label 判定为「不应形成记忆」）的查询不进入分母；因环境异常（检索服务不可用、超时中断）而未完成的样本剔除并记录原因，不得默认为 0 或 1。
- **聚合方式**：查询级平均（每条查询等权），输出 Recall@K 汇总与按 `knowledge_type`、`primary_category` 拆分子集。K 值、命中判定规则（是否 Top-K 包含即命中）为 `TEAM_DEFINED`，见第五章；RRF k 值与 `memory_status` 检索集合待 B（HD-SCHEMA-04、D3-B 检索契约 08/09 `REWORK`）→ 相关子项标 `PENDING_B_CONFIRMATION`。
- **输出字段**：`metric_name`、`metric_result`、`target_threshold`、`query_count`、`hits`、`recall_at_k`、`k_value`、`per_query_detail`、`gold_label_version`、`dataset_version`、`implementation_commit`、`environment`、`evidence_reference`。
- **证据要求**：评测脚本输出 + 查询集版本引用 + 复现命令与环境记录；L2 需在麒麟真实环境执行并保留日志。当前状态 `UNVERIFIED`。

### M3 知识检索响应时间 ≤500ms（B 主责 / D 协作）

- **指标名称**：知识检索响应时间（Knowledge Retrieval Latency）
- **目标值（OFFICIAL_REQUIREMENT）**：≤500ms
- **评测对象**：单次知识检索请求的端到端耗时——从检索请求进入（UDS 请求到达 Memory Service）到检索结果返回（含 Vector 查询、FTS5 查询、RRF 融合与结果组装，不含 Embedding 模型加载等一次性初始化）。
- **样本纳入条件**：标准查询集（与 M2 同源或子集，`TEAM_DEFINED`）在**目标环境（银河麒麟 V11 x86_64）**以规定统计口径执行 N 次（N 为 `TEAM_DEFINED`）。
- **分子/分母或公式**：单次响应时间 = 请求进入时刻到结果返回时刻的耗时；指标判定 = 按「五、TEAM_DEFINED 统计细节」约定的统计口径（如 p95/p50，均标 `TEAM_DEFINED`）计算的值 ≤ 500ms。
- **无效样本处理**：warmup 样本（次数 `TEAM_DEFINED`）剔除；因超时/中断/环境异常导致的不完整样本剔除并记录原因；冷启动（首次加载）样本单独报告，不混入稳态统计。
- **聚合方式**：按 `TEAM_DEFINED` 的 p50/p95/mean/max 聚合；输出分位数与样本数、重复次数、warmup 次数、并发度（单并发为默认，多并发为 `TEAM_DEFINED` 扩展项）。
- **输出字段**：`metric_name`、`metric_result`、`target_threshold_ms`、`statistics_method`（如 p95，`TEAM_DEFINED`）、`sample_count`、`warmup_count`、`repeat_count`、`p50_ms`、`p95_ms`、`mean_ms`、`max_ms`、`implementation_commit`、`environment`、`evidence_reference`。
- **证据要求**：麒麟 VM 日志（含请求/响应时间戳）、评测脚本输出、环境规格记录。**WSL 或 Mock 环境测量不得作为该指标证据**（对齐 `runtime-validation.md`）。当前状态 `UNVERIFIED`。

### M4 知识冲突处理正确率 ≥88%（B 主责 / E 协作）

- **指标名称**：知识冲突处理正确率（Conflict Handling Correctness）
- **目标值（OFFICIAL_REQUIREMENT）**：≥88%
- **评测对象**：冲突检测 + 消解链路（`conflict.py` 与消解规则引擎，B 实现）输出与「Conflict Gold Label」（见第八章）的比对结果。
- **样本纳入条件**：冲突 Gold Label 样本集——包含应检测为冲突的条目对（正样本）与**不应产生冲突的共存条目对**（负样本，作用域不同优先判定可共存，业务契约 §3.5）。每条样本记录冲突双方条目、`user_id`、`conflict_type` Gold Label、期望业务结果与版本追踪要求。
- **分子/分母或公式**：
  - 检测正确：系统检测结果与 Gold Label 冲突/非冲突判定一致。
  - 处理正确：检测正确的样本中，消解结果（期望业务结果：保留/替代/并存/待确认，见第八章）与 Gold Label 一致。
  - 正确率 = 检测正确且处理正确的样本数 / 纳入样本总数。
- **无效样本处理**：`resolution_strategy`/`is_auto_resolvable`/`resolution_confidence` 等最终策略待 B/E 确认（HD-SCHEMA-04，`PENDING_B_CONFIRMATION`/`PENDING_E_CONFIRMATION`）的样本**不计入处理正确判定**，单列 `PENDING_*` 子集报告；争议样本（标注规范 §4.1 裁决前）不进入分母。
- **聚合方式**：样本级准确率；输出检测正确率、处理正确率、按 `conflict_type` 与作用域拆分子集。
- **输出字段**：`metric_name`、`metric_result`、`target_threshold`、`sample_count`、`detection_correct`、`handling_correct`、`accuracy`、`subgroup_breakdown`、`pending_subset_count`、`gold_label_version`、`dataset_version`、`implementation_commit`、`environment`、`evidence_reference`。
- **证据要求**：评测脚本输出 + 样本集版本引用 + 复现命令；L2 需在麒麟真实环境执行。当前状态 `UNVERIFIED`。

---

## 五、TEAM_DEFINED 统计细节（非 OFFICIAL_REQUIREMENT）

> 以下统计细节**比赛原文未规定**，如需要由团队约定，**一律标记 `TEAM_DEFINED`（非 OFFICIAL_REQUIREMENT）**，并登记待定责任轨道。任何 `TEAM_DEFINED` 项在对应轨道确认前保持 `PENDING_*`，**不得在冻结前写成既定契约**。

| 编号 | 统计细节 | 当前默认/待定 | 责任轨道 | 标记 |
|------|----------|---------------|----------|------|
| TD-01 | M3 响应时间统计口径（p50 / p95 / 两者同时报告） | 待定；建议 p50 与 p95 同时报告 | B / D | `TEAM_DEFINED` |
| TD-02 | M3 warmup 次数（如 5 次） | 待定 | B / D | `TEAM_DEFINED` |
| TD-03 | M3 稳态重复次数（每查询 N 次） | 待定 | B / D | `TEAM_DEFINED` |
| TD-04 | M3 并发度（单并发为默认；多并发样本为扩展项） | 单并发默认 | B / D | `TEAM_DEFINED` |
| TD-05 | 查询集重置策略（每次查询前是否重置服务状态/冷启动 vs 热启动） | 待定 | B / D | `TEAM_DEFINED` |
| TD-06 | M2/M4 的 K 值（Recall@K 的 K）与命中判定规则（Top-K 包含即命中） | 待定（如 K=10） | B | `TEAM_DEFINED`（关联 `PENDING_B_CONFIRMATION`） |
| TD-07 | 数据集切分比例（开发集/回归集/封存集）与抽样种子（确定性复现） | 待定 | B / E | `TEAM_DEFINED` |
| TD-08 | 评测环境规格（CPU/内存/存储类型）与隔离要求（封存集哈希锁定后禁止修改） | 待定 | D / E | `TEAM_DEFINED` |
| TD-09 | 评测结果判定的一致口径（例如 M4 中 `PENDING_*` 子集的最终计入规则） | 待 B/E 确认 | B / E | `TEAM_DEFINED` |
| TD-10 | 语言/时区/日期规范化（BCP 47 `language_tag`、ISO 8601 时间） | 沿用既有契约，不新增 | E | `TEAM_DEFINED`（沿用既有字段） |

> **约束**：`TEAM_DEFINED` 项不得被引用为比赛官方要求；所有 `TEAM_DEFINED` 项冻结前须在评测记录元数据（第十二章）中登记实际取值，保证结果可复现。

---

## 六、Preference Gold Label 判定规则

> 与业务契约 §3.2/§7.9、标注规范 §2.1/§三/§4.1 对齐。**四条判定类别**：显式长期偏好、隐式偏好、一次性指令/临时偏好、不应创建偏好的负样本。所有规则为「规则定义」，当前验证状态 `PENDING`/`UNVERIFIED`。

### 6.1 显式长期偏好（Positive-Explicit）

- **判定依据**：用户以直接、不含糊的文字表达对系统行为的长期偏好要求（含「我希望……」「以后都用……」「设置默认为……」等指令性表达，文本无歧义）。
- **Gold Label 字段语义**：`expression_type=explicit`、`is_temporary=false`、`should_persist=true`、`memory_status=active`；`scope`（`preference_scope`）按语义取 `global`/`topic`/`tool`/`session`/`time_window` 之一；`confidence_score` 由人工标注（显式声明 → 0.9–1.0，置信度量化模型待 A/E，HD-SCHEMA-03）。
- **证据要求**：至少一条支撑事件的 `evidence_event_ids`；Gold Label 判定依据必须写明引用哪条用户声明文本。
- **案例引用**：标注规范正例 1（语言偏好）、正例 4（偏好更新）、正例 8（跨用户正向隔离）。

### 6.2 隐式偏好（Positive-Implicit）

- **判定依据**：用户未直接声明，但通过反复行为、问句模式或选择倾向可推断；**需从 ≥2 个 Turn（跨 ≥1 个会话）的一致行为模式推断**；标注人必须在复核记录中写明推断逻辑。
- **Gold Label 字段语义**：`expression_type=implicit`、`confidence_score` 0.5–0.8（人工标注）、`is_temporary=false`、`should_persist=true`；若行为证据充分且经人工复核确认可标 `memory_status=active`；**证据不足或未经复核的推断条目必须 `memory_status=candidate`，不晋升正式偏好**（标注规范 §2.1、业务契约 §7.4）。
- **禁止**：单次行为推断（六档优先级第 5 档）直接标为已确认长期偏好；以 LLM 推断独立决定最终标签。
- **案例引用**：标注规范正例 6（排序偏好隐式推断）、边界案例 3（跨会话行为不一致，先检查作用域差异）。

### 6.3 一次性指令 / 临时偏好（Temporary / One-Off）

- **判定依据**：用户明确提出但限定于当前会话、当前 Turn 或指定时间窗口（含「这次」「现在」「当前」「就这一次」等限定词）。
- **Gold Label 字段语义**：`is_temporary=true` 或 `should_persist=false`；**`memory_status` 必须为 `candidate` 或 `expired`，不得为 `active`**（业务契约 §7.9）；必须注明临时范围。
- **不进入**：用户级偏好检索链路、偏好冲突判定（业务契约 §7.4）。
- **案例引用**：标注规范反例 1（「这次……下次不用」联合 Turn 判定）、边界案例 1（「演示用浅色」临时要求）。

### 6.4 不应创建偏好的负样本（Negative）

- **判定依据**：满足以下任一 → 不应创建任何偏好条目：(a) 纯闲聊/问候；(b) Tool 执行失败/取消/超时的内容；(c) 命中敏感过滤（S-01..S-09）；(d) 用户明确要求不记录；(e) 临时且无复用价值的一次性指令。
- **Gold Label 语义**：不产生 `Preference` 条目；若来自 Tool 上下文，`should_form_memory=false`、`failure_tag` 取 `tool_failure`/`transient_context`/`sensitive_content`/`user_aborted` 之一（标注规范 §2.3）。
- **负样本在评测中计入 M1 分母**（正确拒绝计入正确）。
- **案例引用**：标注规范反例 1/3/5、正例 7（一次性查询）。

---

## 七、Knowledge Gold Label 判定规则

> 与业务契约 §3.3/§7.8、安全契约 SEC-TOOL-01..07、标注规范 §2.2/§2.3 对齐。**核心红线：只有真实 Tool 执行证据或用户明确陈述允许形成已验证知识；无真实 Tool 证据的模型自述成功不得标为已验证事实知识**（G0-E-14、SEC-TOOL-07）。当前验证状态 `PENDING`/`UNVERIFIED`。

### 7.1 可沉淀知识（Positive）

- **判定依据**：知识来自真实业务事件——用户明确陈述的事实，或真实 Tool 执行成功（`execution_status=success`）且结果具有**跨会话复用价值**的结果。
- **Gold Label 字段语义**：`knowledge_type` 六值（`workflow`/`case`/`template`/`fact`/`constraint`/`failure_experience`）必填，不得以 `primary_category` 替代；`memory_status=active`（经人工复核确认）；`source_event_id`/`evidence_event_ids` 关联真实来源事件。
- **Tool 成功但瞬态上下文**（一次性查询，如「现在几点」）：`should_form_memory=false`、`failure_tag=transient_context`，**不得沉淀为知识**（标注规范正例 7）。
- **案例引用**：G0-E-05（真实 Tool 成功）、标注规范正例 3/7。

### 7.2 失败 / 取消 / 超时 Tool 结果（Negative-Forced）

- **判定依据**：`execution_status` 为 `failure`/`cancelled`/`timeout`（及 `partial` 中失败部分）时，**不得形成任何成功知识**；不得从失败信息、取消状态或超时状态推断成功或失败结论（业务契约 §7.8 红线：`execution_status != success` 不得形成成功知识）。
- **Gold Label 语义**：`should_form_memory=false`；`failure` 可沉淀**带条件的失败经验**（`knowledge_type=failure_experience`，须明确适用条件，G0-E-06）；`cancelled` 按取消处理，不形成完成事实（G0-E-07）；`timeout` 结果保持未知，不得冒充成功（G0-E-08）。
- **cancelled/partial 是否入 D3 正式候选**：待 E/B/D 复核（HD-D2E-05），本文件不冻结取值集合。
- **案例引用**：G0-E-06/07/08/09、标注规范正例 3、反例 2。

### 7.3 模型自述（Model Self-Report，不得标已验证知识）

- **判定依据**：模型文本声称 Tool 成功但**无真实 `ToolExecutionEvent` 证据**。
- **Gold Label 语义**：不得标为已验证事实或成功知识；仅可标记 `memory_status=candidate` 候选且**不得升级**（G0-E-14 禁止项 1/2/4；SEC-TOOL-07）；六档冲突优先级中第 6 档（模型推测）不得覆盖第 1–5 档高可信来源（业务契约 §7.5）。
- **案例引用**：G0-E-14。

---

## 八、Conflict Gold Label 判定规则

> 与业务契约 §3.5/§7.5、安全契约 SEC-LLM-04、标注规范 §2.4/边界案例 3 对齐。**具体消解策略（`resolution_strategy`/`is_auto_resolvable`/`resolution_confidence` 计算）由 B/E 轨道确认，本文件标 `PENDING_B_CONFIRMATION`/`PENDING_E_CONFIRMATION`，不自行发明**。当前验证状态 `PENDING`/`UNVERIFIED`。

### 8.1 何时构成冲突

- 两条或多条 `Preference`/`Knowledge` 条目在**作用域相同或高度重叠**（`preference_scope`/`knowledge_type`/`primary_category` 等作用域字段相同或高度重叠）前提下，存在逻辑矛盾、时间不一致或来源冲突。
- **作用域不同优先判定可共存**（业务契约 §3.5）：`preference_scope`/`knowledge_type`/`primary_category` 不同时，Gold Label 判定为**不构成冲突**，不产生 `Conflict` 对象（标注规范正例 2）。
- `conflict_type` 取值同 Schema 枚举 2.11（业务契约 §5.4 冻结五值业务语义）；`contradiction`/`temporal_inconsistency` 的**判定阈值算法**属 B 轨道实现层（`REJECTED` 于 E、`DEFERRED` 待 B，HD-SCHEMA-04）——本文件不冻结判定阈值，仅冻结「何时构成冲突」的业务判据。

### 8.2 期望业务结果（Gold Label 消解期望）

| 期望结果 | 含义 | 对齐字段 |
|----------|------|----------|
| 保留（keep_left / keep_right） | 高可信来源条目保留，低可信条目标记失效/替代 | `recommended_resolution`（标注规范 §2.4）；`memory_status` 保留方 `active`、被替代方 `superseded` |
| 替代（supersede / 偏好更新） | 同一 key/事实的新值覆盖旧值，旧条目保留用于审计与回溯 | `superseded_by_id`/`version`/`previous_version_id`（业务契约 §7.2/§7.3） |
| 并存（coexist） | 作用域不同或可共存，不产生冲突 | 不产生 `Conflict` 对象（8.1 规则） |
| 待确认（flag_for_review / deferred） | 争议或证据不足，标记待人工裁决 | `resolution_status` 对应待决值；裁决前双方保持 `memory_status=candidate`（标注规范边界案例 3） |

- **版本追踪要求**：每次更新 `version` 递增、`previous_version_id` 指向上一版本；`Knowledge` 通过 `superseded_by_id` 标记被替代条目；旧条目保留不物理删除（业务契约 §7.2）。版本化 SQLite 实现 `待 D 确认`。
- **最终值禁止模型生成**：`resolution_status` 已决值（resolved_auto/resolved_manual/unresolvable 等）、`resolution_strategy`、`resolution_confidence`、`resolved_by` 由消解规则引擎/系统计算产出（业务契约 §7.10、SEC-LLM-04）；本文件当前无消解规则引擎证据 → `PENDING_B_CONFIRMATION` + `PENDING_E_CONFIRMATION`。
- **案例引用**：标注规范正例 4（偏好更新/替代）、正例 2（并存）、边界案例 3（跨会话不一致 → 先判作用域）。

---

## 九、Forget（精准遗忘）Gold Label 判定规则

> 与业务契约 §3.7/§7.6、安全契约 SEC-FORGET-01..05、标注规范 §2.5/正例 5/反例 6、G0-E-03 对齐。**底层遗忘实现未完成时，所有相关验证状态保持 `PENDING`/`UNVERIFIED`**。当前验证状态 `PENDING`/`UNVERIFIED`。

### 9.1 正确目标解析

- `target_selector`（用户原始描述）→ 系统解析生成 `resolved_target_ids`；**`resolved_target_ids` 由遗忘规则引擎/系统计算产出，`*禁止模型生成`**（业务契约 §7.10、SEC-FORGET-01）。
- Gold Label 判据：解析结果与人工标注的目标条目集合**完全一致**；不得按模糊关键词或时间窗口粗略删除后声称「已精准遗忘」（标注规范 §2.5）。

### 9.2 跨用户拒绝

- `resolved_target_ids` **仅含当前 `user_id` 条目**；任何跨用户解析或执行一律拒绝并标记 `isolation_violation=true`、`sensitivity=critical`（SEC-UI-05、SEC-FORGET-04、标注规范反例 6 尝试 3）。

### 9.3 Preview 与 Execute 一致性

- 先预览再确认再执行：`preview_provided=true` → `user_confirmed=true` → 执行（状态机 `pending→previewing→awaiting_confirmation→executing→completed/failed/rolled_back`，业务契约 §5.5 `status` 七值、SEC-FORGET-02）。
- Gold Label 判据：预览展示的受影响条目列表与最终执行删除的条目列表**一致**（含 `affected_count` 一致，最终值 `*禁止模型生成`）。

### 9.4 遗忘后不可再见（SQLite / 检索 / Context）

- 遗忘执行后（尤其 `hard_delete=true`）：SQLite 正文、Vector、FTS5、缓存、日志、导出与备份中**无可检索明文残留**（S-09、SEC-SENS-07）；重新检索不再返回、`MemoryContext` 不再注入已遗忘目标（G0-E-03 禁止项 1、SEC-FORGET-05）；`forgotten_excluded_count` 正确计数（统计口径待 D/E 确认）。
- `full_reset` 安全边界（HD-SCHEMA-06）与级联范围（`is_cascade`）待 E/D 确认；Vector 同步删除策略（`has_vector_cleanup`）待 B（HD-SCHEMA-05）。

### 9.5 当前状态

- 精准遗忘实现（SQLite 删除、Vector 清理、Context 排除）当前仓库**未实现**（`README.md` 明确未完成）；本文件全部 Forget Gold Label 规则验证状态 `PENDING`/`UNVERIFIED`，**不得声称已通过**。

---

## 十、跨用户与敏感边界

> 本节仅**引用既有规则**（安全契约 SEC-UI-01..07、SEC-SENS-01..07、标注规范 §5.1/§5.3），不重复发明、不弱化。

- **`user_id` 硬约束**：所有核心业务对象（Preference/Knowledge/Conflict/ForgetPlan）及端到端会话均须具备 `user_id`；跨 `user_id` 的读取、更新、删除、遗忘一律拒绝并标记 `isolation_violation=true`、`sensitivity=critical`（S-08）。
- **敏感类型 S-01..S-09**：严格沿用标注规范 §5.1 编号与语义；命中 S-01..S-04/S-08 的 Turn `should_ignore=true`；`sensitivity` 终判由敏感过滤规则引擎产出，**模型不得覆写或降级**（SEC-SENS-05）。
- **评测影响**：敏感样本进入 Gold Label 判定时按「强制不形成记忆」处理；敏感原文**不得**出现在本文件、标注字段、评测记录、日志或导出文件（仅可写脱敏占位或仅 ID 引用）。

---

## 十一、LLM 辅助与人工最终责任边界

> 严格沿用标注规范 §4.1/§4.2。当前验证状态 `PENDING`/`UNVERIFIED`（流程为规则，尚未在样本上执行）。

1. **允许**：LLM 对自然语言 Turn 内容进行辅助分析，生成候选的 `preference_key`/`preference_value`/`knowledge_summary` 表达；LLM 可用于候选标注、解释或一致性检查。
2. **禁止**：LLM 独立决定最终 Gold Label；LLM 替代标注人 A 或标注人 B 的初标/复核角色；LLM 在无人干预下对标注结果「批量修正」。
3. **候选标记**：所有 LLM 生成的候选输出必须标记 `memory_status=candidate`，并记录模型名称、调用时间、Prompt 摘要，供复核人审查（标注规范 §4.2）。
4. **人工最终责任**：Gold Label 最终标签**必须由人工**确定——标注人 A 初标 → 标注人 B 复核 → 争议提交 Reviewer（D/E）裁决 → 复核一致或裁决确定后锁定为 Gold Label；锁定后不得单方面修改，如需修改必须重新走复核流程并记录变更原因（标注规范 §4.1）。
5. **复核证据**：每次复核保留 Git commit SHA、工作区状态（`git status --short`）、复核人标识、复核时间（ISO 8601）、复核结论、不同意的条目编号与理由、争议裁决记录（标注规范 §4.3）。

---

## 十二、最小评测记录元数据

> 每条评测记录**至少**包含以下字段，保证可追踪数据版本、实现 Commit、环境与证据。可扩展，但**不得发明与既有契约冲突的字段名**（对齐业务契约与标注规范字段语义）。

| 字段 | 含义 | 示例（虚构占位，非真实数据） |
|------|------|------------------------------|
| `case_id` | 样本/案例唯一标识 | `pref_case_0001`（虚构） |
| `dataset_version` | 使用的数据集版本标识 | `devset_v0.1_draft`（虚构，尚未建立） |
| `gold_label_version` | Gold Label 判定规则/标注版本 | `gold_label_v1_candidate` |
| `implementation_commit` | 被测实现的 Git commit SHA | `<PENDING>`（业务代码未实现） |
| `environment` | 执行环境描述（OS/版本/内核/工具版本） | `PENDING`（须为银河麒麟 V11 x86_64 或如实记录 WSL） |
| `metric_result` | 指标计算结果（数值或状态） | `<PENDING>`（虚构占位，非真实数据） |
| `evidence_reference` | 证据文件/日志/脚本输出引用 | `<PENDING>`（无评测执行） |

> 可扩展字段（`TEAM_DEFINED`）：`annotator`/`reviewer`（标注人/复核人）、`annotated_at`、`dataset_sha256`（封存集哈希，**当前未锁定**）、`sample_count`、`warmup_count`、`repeat_count`、`statistics_method`。**任何字段不得写入真实用户数据、密钥或未脱敏业务日志**。

---

## 十三、双向追踪表

> 本文件规则 ↔ 标注规范章节 ↔ G0-E 案例 ↔ 业务/安全契约章节 ↔ 追踪矩阵 REQ/指标。下表为可检索映射（规则定义层，非验证结果）。

| 本文件章节 | 标注规范（R-02） | G0-E 案例（R-03） | 业务契约（R-04） | 安全契约（R-05） | 追踪矩阵（R-01） |
|------------|------------------|-------------------|------------------|------------------|------------------|
| 四、M1 偏好提取准确率 | §2.1/§三/§四 | G0-E-01/02/04/14 | §3.2/§7.9/§十一 | SEC-UI/SEC-LLM | REQ-02；指标 1 |
| 四、M2 知识检索召回率 | §2.2/§2.3 | G0-E-05..09/14 | §3.3/§7.8/§十一 | SEC-TOOL | REQ-03/04；指标 2 |
| 四、M3 知识检索响应时间 | §2.2 | G0-E-05..09 | §十一 | SEC-TOOL | REQ-04；指标 3 |
| 四、M4 知识冲突处理正确率 | §2.4/边界案例 3 | G0-E-14 | §3.5/§7.5/§十一 | SEC-LLM-04 | REQ-03；指标 4 |
| 六、Preference Gold Label | §2.1/§三/§四/正例 1/4/6/8、反例 1/3/5、边界 1/3 | G0-E-01/02/04 | §3.2/§7.4/§7.9 | SEC-UI/SEC-SENS/SEC-LLM | REQ-02 |
| 七、Knowledge Gold Label | §2.2/§2.3/正例 3/7、反例 2 | G0-E-05..09/14 | §3.3/§7.8 | SEC-TOOL-01..07 | REQ-01/03/04 |
| 八、Conflict Gold Label | §2.4/边界案例 3 | G0-E-14 | §3.5/§7.2/§7.5 | SEC-LLM-04 | REQ-03 |
| 九、Forget Gold Label | §2.5/正例 5/反例 6 | G0-E-03/04 | §3.7/§7.6 | SEC-FORGET-01..05、SEC-UI-05 | REQ-05 |
| 十、跨用户与敏感边界 | §5.1/§5.3 | G0-E-01/02/03/04 | §7.1/§7.7 | SEC-UI、SEC-SENS | REQ-05/07 |
| 十一、LLM 责任边界 | §4.1/§4.2/§4.3 | G0-E-14 | §7.10 | SEC-LLM-01..08 | REQ-02/07 |
| 十二、评测记录元数据 | §4.3 | — | §7.10 | §2.1 | REQ-07 |

---

## 十四、FREEZE_BLOCKERS（冻结阻断项 / 不可冻结项）

> 完整沿用业务契约 §10（HD-D2E-B01..B07）与安全契约 §七，并登记本文件特有的不可冻结项。**本任务只登记不闭合**；不得为了完成 Day3 而删除或弱化任何一项。

| 编号 | 阻断项 / 不可冻结项 | 影响本文件的评测口径 | 责任轨道 | 所需证据 / 解除条件 |
|------|---------------------|----------------------|----------|---------------------|
| HD-D2E-B01 | 真实 Kaiming Hook 阻断 | M3 真实链路延迟无法验证 | D | Gate 1 获取 SDK 源码/签名权限或降级方案 |
| HD-D2E-B02 | KYSEC 最小授权仅 ACL 模拟 | 跨用户/授权评测的环境前提 | D | KYSEC 开发者文档 + 测试环境授权 |
| HD-D2E-B03 | 回退基线未闭合 | 无直接口径影响，但影响 L2/L3 环境可信度 | D | 补跑标准 rollback |
| HD-D2E-B04 | C 真实 Context/Tool/Turn 取证缺位 | Knowledge/Tool 四态 Gold Label 字段语义 `UNVERIFIED` | C | C 在麒麟 VM 完成真实宿主取证回填 |
| HD-D2E-B05 | 基线 DOCX（01–06）未导入 | 四项指标阈值与统计口径的权威终审 | 团队/E | 人工导入 `docs/baseline/` 并版本核验 |
| HD-D2E-B06 | 案例集 G0-E-01..14 全部为设计稿未执行 | 所有涉及案例的验证状态 `UNTESTED` | C/D/E | 在真实环境执行对应案例 |
| HD-SCHEMA-03 | `confidence_score` 量化与衰减策略未定 | M1/偏好 Gold Label 置信度区间 | A/E | A/E 确认量化模型 |
| HD-SCHEMA-04 | 冲突判定阈值与 `is_auto_resolvable` 未定 | M4、第八章 `resolution_strategy` 等 | B | B 确认（本文件标 `PENDING_B_CONFIRMATION`/`PENDING_E_CONFIRMATION`） |
| HD-SCHEMA-05 | Vector 与 SQLite 真源一致性策略未定 | M2 检索口径、9.4 遗忘后 Vector 清理 | B | B 确认 |
| HD-SCHEMA-06 | 遗忘级联范围与 `full_reset` 安全边界未定 | 9.2/9.4 Forget 规则 | E/D | E/D 确认 |
| HD-SCHEMA-07 | 短/中/长分层边界未定 | 无直接指标影响，但影响端到端评测样本划分 | D | D 确认 |
| HD-SCHEMA-08 | 检索评测指标基线（Recall@K、MRR、NDCG）未定 | M2 K 值等 `TEAM_DEFINED` 项 | B | B 确认 |
| HD-SCHEMA-09 | `*_id` 生成策略未定 | 评测记录 `case_id` 语义 | D | D 确认 |
| HD-SCHEMA-14/15 | `expression_type` 终审、SOP v1.1 导入复核 | 六档优先级与枚举权威复核 | E/团队 | SOP v1.1 导入 |
| HD-ANNO-01..09 | 标注规范待办（含封存集制作、首批样本 ≥50 条、双人复核执行） | 封存集未建立 → 任何正式评测未执行 | E 等 | 按标注规范第十章冻结条件逐项闭合 |
| 本文件特有 | 封存集尚未制作、尚未锁定 SHA-256 | 本文件只定义规则，不可标任何集已封存/已复核完成 | E/D | 后续独立任务制作并锁定 |

**小结（可冻结 vs 不可冻结）**：本文件可冻结的是**评测定义**（Gold Label 判定规则、计算口径、无效样本规则、聚合方式、证据要求、LLM/人工责任边界）；不可冻结的是所有**评测结果**（任何分数、延迟、PASS 结论）与依赖 C/D/B/A 真实取证/决策的实现细节（全部保持 `PENDING_*`/`UNVERIFIED`/`DEFERRED`）。

---

## 十五、变更记录与冻结为团队基线条件

### 15.1 变更记录

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v1 | 2026-08-09 | 候选初稿：基于追踪矩阵第九节（四项指标全 `UNVERIFIED`）、标注规范 v0.1 DRAFT（修订2）、G0-E-01..14 案例集、Day3 业务契约 v1 候选、Day3 安全验收契约 v1 候选与 evaluation/README 事实，形成 Gold Label 与评测口径 v1 候选。定义四项 OFFICIAL_REQUIREMENT 指标口径（七要素）并原样保留阈值；独立登记 TEAM_DEFINED 统计细节；覆盖 Preference/Knowledge/Conflict/Forget 四类 Gold Label 判定规则；明确 LLM 辅助与人工最终责任边界；定义最小评测记录元数据；建立双向追踪；登记 FREEZE_BLOCKERS。所有结果状态 `PENDING`/`UNVERIFIED`，无虚构分数。状态 `CANDIDATE_FOR_FREEZE`。 | E 轨道 |

### 15.2 升级为团队冻结基线（v1.0 冻结基线）的条件

以下条件**全部满足**后方可视为团队冻结基线：

1. **非作者 D Reviewer 批准**本文件（E 不批准 E 自己的变更）；
2. 本文件对应 PR 合并；
3. HD-D2E-B01..B07 阻断项均有明确处置（见第十四章）；
4. HD-SCHEMA/HD-ANNO 关键待办经权威基线导入/对应轨道取证后闭合（含 `PENDING_B_CONFIRMATION`/`PENDING_E_CONFIRMATION`/`PENDING_C_CONFIRMATION`/`PENDING_D_CONFIRMATION` 项解除）；
5. 权威基线（比赛原文/SOP/SDK 能力边界）导入后完成四项指标阈值与统计口径复核（HD-D2E-B05）；
6. 封存集制作并锁定 SHA-256 哈希；
7. 评测在银河麒麟 V11 x86_64 真实环境执行并回填证据（L2/L3）；
8. Evidence Reviewer 确认本文件所有证据状态标注与当时实际证据等级一致（无 `HOST_VERIFIED` 虚标、无虚构分数）。

在满足以上条件之前，本文件保持 `CANDIDATE_FOR_FREEZE`，**不得作为评测已执行、指标已达标或性能已达成结论的唯一依据**。

---

## 十六、结束声明（PENDING / UNVERIFIED，无虚构结果）

1. 本文件为**纯 Markdown 评测规范**：冻结的是评测定义（Gold Label 判定规则、计算口径、无效样本规则、聚合方式、证据要求、责任边界），**不是已取得的评测结果**。
2. 四项比赛指标（偏好提取准确率 ≥85%、知识检索召回率 ≥85%、知识检索响应时间 ≤500ms、知识冲突处理正确率 ≥88%）当前状态**全部 `UNVERIFIED`**；阈值原样保留，未经权威基线导入复核与真实环境评测，**不得解读为已达标**。
3. 本文件**不含任何虚构的准确率、召回率、延迟、冲突正确率分数或 PASS 结论**；所有当前结果状态 `PENDING`/`UNVERIFIED`，不标 `HOST_VERIFIED`/`PASS`。
4. 本任务 L0/L1 仅执行 `python3 -m pytest --version` 作为**本地工具可用性探测**，**不是评测执行证据**；文档不把该结果表述为正式评测已执行。
5. 标注规范已定义的**双人复核、封存集、泄漏防护规则**本文件继承一致；封存集尚未制作、尚未锁定哈希、复核流程尚未执行——**本文件不声称其已执行**。

---

> **本文档到此结束。后续修订将在 D Reviewer 审查、C 麒麟取证、D 协议草案、B 检索契约冻结、A/E 置信度与衰减策略确认、权威基线导入与封存集制作后按 A–E 轨道反馈进行。**
