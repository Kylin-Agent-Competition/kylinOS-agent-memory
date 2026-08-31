# Day9E 检索 Gold 与指标语义 v1 候选（D9_RETRIEVAL_GOLD_SPEC_V1）

- **版本**：v1
- **状态**：`CANDIDATE_FOR_FREEZE`
- **阶段定位**：Day9 / E 轨道 / 检索评测 Gold 与指标语义增量规范（TD-036 E 侧书面冻结输入）
- **作者轨道**：E（记忆业务、安全、数据集与业务指标）
- **Reviewer 轨道**：D（IPC、SQLite、Outbox、虚拟机成品化与发布）
- **上位基线**：`evaluation/D3_GOLD_LABEL_AND_METRICS_SPEC_V1.md`（`CANDIDATE_FOR_FREEZE`）。本文件**只在 D3 基线之上做 Day9 检索评测增量澄清，不重写 D3 既有 Gold 业务定义**。
- **配套文件**：
  - `evaluation/D9_RETRIEVAL_GOLD_POLICY_V1.json`（机器可读策略契约，版本化、fail-fast）
  - `evaluation/test_d9_retrieval_gold_spec.py`（策略与规范验证测试）
- **冻结为团队基线条件**：**只有非作者 D Reviewer 批准且对应 PR 合并后，本文档方可视为团队冻结基线**（对齐 D3 第十五章口径）。`CANDIDATE_FOR_FREEZE` 仅表示 E 轨道提出的 v1 候选语义集合，**不代表已被 D 批准、不代表 D3/Day9 Gate 通过、不代表任何指标已满足阈值、不代表任何宿主行为或实现能力已被验证**。
- **本文件冻结的是评测定义，不是已取得的评测结果**：不含任何虚构分数、延迟或结果结论；所有当前结果状态一律 `PENDING` / `UNVERIFIED`。
- **任务性质声明**：本任务为纯文档 + JSON + 标准库测试任务（`runtime_required=false`、`runtime_commands=[]`）。L0/L1 本地静态检查与单元测试结果**不得**被表述为银河麒麟宿主验证结论。

---

## 一、定位、范围与依赖关系

### 1.1 目的

为 TD-036（空 Gold 查询的 Recall/MRR/nDCG 剔除与聚合口径未冻结）提供 **E 轨书面冻结输入**：M2 三项指标（Recall@K、MRR、nDCG）的有效查询集合、空 Gold 查询处理规则、negative_guardrail 角色及版本化评测元数据。本文件同时是 **PR #76** 关联技术债的 E 轨口径依赖。

### 1.2 边界（本文件不做的事）

- **不修改 B 轨检索实现**：`memory-service/retrieval/**`（含 `evaluation.py`）不在本任务范围；B 轨对空 Gold 记满分、把空 Gold 混入分母等现行行为的修正，由后续 B 轨任务按其职责完成，本文件仅提供口径输入。
- **不自行关闭 TD-036**：TD-036 保持 `Open`，其关闭条件（含 B 统一三项指标有效分母与聚合、记录有效查询数与剔除数量/原因、覆盖空集/混合集/全空集）由 B 轨任务按 TD 登记行执行。
- **不重写 D3**：D3 已定义的 Gold Label 判定、OFFICIAL_REQUIREMENT 指标口径、TEAM_DEFINED 统计细节、双向追踪与 FREEZE_BLOCKERS 一并沿用。

### 1.3 引用锚点（D3 已核验原文）

- D3 第四章 M2 无效样本处理：「无正解（Gold Label 判定为「不应形成记忆」）的查询不进入分母」。
- D3 第四章 M2 无效样本处理：「命中 S-01..S-09 的查询样本剔除并单列」。
- D3 第五章约束：统计细节「一律标记 `TEAM_DEFINED`（非 OFFICIAL_REQUIREMENT）」。
- D3 第五章登记：TD-06（M2/M4 的 K 值与命中判定规则，`TEAM_DEFINED`，责任 B）、TD-07（数据集切分比例与抽样种子，`TEAM_DEFINED`，责任 B/E）。

---

## 二、评测角色划分（三类）

| 角色 | 定义 | 是否进入 M2 正式分母 | 报告方式 |
|------|------|----------------------|----------|
| `positive_retrieval` | `relevant_ids` 非空且至少含一条有效正解（可检索、已验证的事实知识条目）的正式检索查询 | **是**（进入 Recall/MRR/nDCG 三项正式分母与聚合） | 按 `knowledge_type`、`primary_category` 拆分子集报告 |
| `negative_guardrail` | `relevant_ids` 为空（no-answer/拒绝类）或命中业务/安全边界的查询：已遗忘/removed、expired、superseded、candidate、unresolved conflict、cross-user、禁止敏感召回 | **否**（单列） | 计数 + 剔除原因，作为防伪护栏，不得计为满分 |
| `boundary` | 语义未定样本：标注规范 §4.1 争议裁决前、`PENDING_*` 待确认项（含 `PENDING_B_CONFIRMATION` 等） | **否**（单列） | 单列 boundary 子集，待语义确认后重新归类 |

> 角色判定顺序：先判 `boundary`（语义未定则退出正式评测）→ 再判 `negative_guardrail`（无正解或命中边界则单列）→ 其余为 `positive_retrieval`。三类角色合计构成查询全集；**只有 `positive_retrieval` 进入三项指标正式分母**。

---

## 三、空 Gold（empty relevant_ids）规则

### 3.1 规则定义

**D9-EMPTY-GOLD-01**：查询 `relevant_ids` 为空（Gold Label 判定为「不应形成记忆」/无正解）时，该查询**不得进入 Recall/MRR/nDCG 三项指标的任何正式分母与分子**，且**不得解释为满分或其他默认值**。与 D3 第四章 M2 无效样本处理「无正解（Gold Label 判定为「不应形成记忆」）的查询不进入分母」一致。

### 3.2 三项指标分母口径

| 指标 | 正式分母规定 |
|------|--------------|
| Recall@K | `excluded`（空 Gold 查询不进入分母） |
| MRR | `excluded`（空 Gold 查询不进入分母） |
| nDCG | `excluded`（空 Gold 查询不进入分母） |

### 3.3 禁止解释

空 Gold 查询**不得**：

1. 计为 Recall=1.0 / nDCG=1.0 满分或 MRR 等效最高分；
2. 计入 Recall/MRR/nDCG 任一正式分母与聚合；
3. 因环境异常等原因被默认为 0 或 1（对齐 D3「不得默认为 0 或 1」）。

### 3.4 必报字段

每次正式评测必须报告：`valid_query_count`（进入正式分母的有效查询数）、`excluded_query_count`（剔除查询数量）、`exclusion_reason`（剔除原因，按 negative_guardrail / boundary / 环境异常分类）。

---

## 四、negative_guardrail 业务边界（七类）

| category_id | 依据（D3 / 标注规范 / 安全契约） | guardrail_expectation |
|-------------|-------------------------------|----------------------|
| `removed_or_forgotten` | `memory_status=removed`；精准遗忘执行后（D3 第九章 9.4）已遗忘条目不得再被检索返回 | 已遗忘/removed 条目不得作为查询正解；相关查询单列并记录剔除原因 |
| `expired` | `memory_status=expired`；临时偏好/临时知识过期后不再作为有效记忆（D3 第六章 6.3） | expired 条目不得作为正解；仅含过期正解的查询不得进入正式分母 |
| `superseded` | `memory_status=superseded`；被替代条目保留仅用于审计与回溯（D3 第八章 8.2） | superseded 条目不得作为当前知识正解；相关查询单列排除 |
| `candidate` | `memory_status=candidate`；未经人工复核/证据确认（模型自述、LLM 候选）不得升级为已验证正解（D3 第七章 7.3、标注规范 §4.1/§4.2） | candidate 条目不得进入正式检索正解集合；相关查询排除并单列 |
| `unresolved_conflict` | 标注规范 §4.1 争议裁决前冲突双方保持 `memory_status=candidate`（D3 第八章 8.2） | 未裁决冲突条目不得作为正解；相关查询单列待裁决后处置 |
| `cross_user` | 跨 `user_id` 读取/检索一律拒绝并标记 `isolation_violation=true`、`sensitivity=critical`（S-08、SEC-UI-05、D3 第九章 9.2 / 第十章） | 跨用户条目不得作为任何用户查询的正解；相关查询单列并记录隔离边界 |
| `sensitive_recall_prohibited` | 命中 S-01..S-09 强制不形成记忆（D3 第七章/第十章、SEC-SENS）；敏感原文不得出现在评测记录 | 敏感内容不得被召回为正解；相关查询剔除并单列，记录仅用脱敏占位或 ID 引用 |

> 这些边界样本**不得伪装成 Recall=1.0**：它们不是「应命中零条后被判正确」的负样本，而是**不参与正式指标计算**的护栏样本。任何评测不得以空 Gold 或边界样本制造满分记录。

---

## 五、boundary 子集（单列）

以下样本语义未定，**不进入任何正式分母**，单列报告：

- 标注规范 §4.1 争议裁决前的样本；
- `PENDING_*` 待确认项：`PENDING_B_CONFIRMATION`、`PENDING_E_CONFIRMATION`、`PENDING_D_CONFIRMATION` 等（对齐 D3 第三章/第八章）；
- `memory_status=deprecated` 的检索集合语义待 B 确认（HD-SCHEMA-04、D3-B 检索契约 08/09 `REWORK`）—— 在 B 冻结前按边界处理，不冻结其检索行为；
- 其他 `TEAM_DEFINED` 参数取值冻结前相关的语义歧义样本。

---

## 六、TEAM_DEFINED 参数边界

延续 D3 第五章约束：「以下统计细节比赛原文未规定，如需要由团队约定，**一律标记 `TEAM_DEFINED`（非 OFFICIAL_REQUIREMENT）**」。本文件明确以下参数为**团队自定义**，**不得描述为比赛官方要求**，取值冻结前一律 `PENDING`（本任务只冻结标记与边界，不冻结取值）：

| 参数 | D3 登记 | 当前取值 | origin |
|------|---------|----------|--------|
| K（Recall@K 的 K 值）与命中判定规则 | D3 第五章 TD-06（责任 B，关联 `PENDING_B_CONFIRMATION`） | `PENDING` | `TEAM_DEFINED` |
| Top-K 检索结果窗口 | D3 第四章 M2 命中判定 | `PENDING` | `TEAM_DEFINED` |
| RRF k 值 | D3 第四章 M2 聚合方式（待 B 确认，HD-SCHEMA-04） | `PENDING` | `TEAM_DEFINED` |
| 统计方法（p50/p95/mean/max 等） | D3 第五章 TD-01（责任 B/D） | `PENDING` | `TEAM_DEFINED` |
| 数据集切分比例与抽样种子 | D3 第五章 TD-07（责任 B/E） | `PENDING` | `TEAM_DEFINED` |

---

## 七、B 轨后续实现要求（E 轨书面输入，不修改代码）

E 轨口径冻结后，B 轨任务应（对齐 TD-036 关闭条件与 PR #76 关联技术债处置）在 `memory-service/retrieval/evaluation.py` 中统一三项指标（Recall/MRR/nDCG）的有效分母与聚合，并至少：

1. 空 Gold（`relevant_ids` 为空）查询**不进入**三项指标正式分母，**不默认记满分**；
2. 记录 `valid_query_count`（有效查询数）、`excluded_query_count`（剔除数量）与 `exclusion_reason`（剔除原因）；
3. 验证场景覆盖**空集、混合集、全空集**三种形态（对齐 TD-036 关闭条件）。

本文件只提出上述口径要求，**不实现任何指标计算逻辑**；实现细节（聚合顺序、并行统计等）由 B 轨任务自行决定。

---

## 八、版本化评测元数据

每条正式评测记录**至少**包含以下字段（对齐 D3 第十二章，可扩展但不得发明与既有契约冲突的字段名）：

| 字段 | 含义 | 当前占位 |
|------|------|----------|
| `case_id` | 样本/案例唯一标识 | `PENDING` |
| `dataset_version` | 数据集版本 | `PENDING` |
| `gold_label_version` | Gold Label 判定规则/标注版本 | `PENDING` |
| `implementation_commit` | 被测实现 Git commit SHA | `PENDING` |
| `environment` | 执行环境描述 | `PENDING`（须为银河麒麟 V11 x86_64 或如实记录 WSL） |
| `metric_result` | 指标计算结果 | `PENDING` |
| `evidence_reference` | 证据文件/日志引用 | `PENDING` |
| `policy_version` | 本策略文件版本 | `PENDING` |

任何字段不得写入真实用户数据、密钥或未脱敏业务日志；结果可复现性要求同 D3：`TEAM_DEFINED` 项冻结前须在元数据中登记实际取值。

---

## 九、依赖与引用登记

- **技术债**：TD-036（`docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` 第 104 行，状态 `Open`）——本文件为该登记行「由 E 冻结空 Gold/应答无结果的正式口径」的 E 侧输入；**本文件不自行关闭 TD-036**，关闭由 B 轨任务按其关闭条件执行。
- **关联 PR / Issue**：PR #76（关联技术债登记）、Issue #79。本文件仅引用编号，不回写评审结果字样。
- **上位基线**：D3 第四章 M2 口径、第五章 TEAM_DEFINED、第十二章元数据、第十五章冻结条件。
- **配套机器契约**：`evaluation/D9_RETRIEVAL_GOLD_POLICY_V1.json`（`policy_version=v1`），由 `evaluation/test_d9_retrieval_gold_spec.py` 强制校验；未知字段或非法角色 fail-fast，扩展须发 `policy_version=v2` 新任务，不原位放宽。

---

## 十、冻结与不可冻结声明

### 10.1 可冻结（本文件意图冻结的定义）

- 三类评测角色（`positive_retrieval` / `negative_guardrail` / `boundary`）及各自是否进入 M2 正式分母；
- 空 Gold（empty `relevant_ids`）查询的处理规则与禁止解释；
- negative_guardrail 七类业务边界及依据；
- TEAM_DEFINED 参数边界（标记与登记，不含具体取值）；
- 版本化评测元数据字段清单。

### 10.2 不可冻结（本文件明确不声明）

- **任何评测结果**：不得声明任何指标已满足目标阈值、不得给出任何分数或延迟、不得声明任何评测已正式执行；
- **任何 Gold 数据已完成人工复核或已封存**（复核与封存流程按 D3 第十一章/第十四章执行，当前均未执行）；
- **任何宿主/真实麒麟环境验证结论**：L0/L1 本地检查结果不得表述为宿主验证结论；
- **任何以静态检查或 Mock 冒充正式结果的状态**：对齐 `runtime-validation.md` 的禁止降级规则。

---

## 十一、变更记录

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v1 | 2026-08-31 | 候选初稿：以 D3 v1 候选为基线，新增 Day9E 检索 Gold/指标增量语义——三类评测角色及 M2 正式分母语义、空 Gold 规则（D9-EMPTY-GOLD-01）、negative_guardrail 七类边界、boundary 子集、TEAM_DEFINED 参数边界、B 轨后续验证场景要求与版本化评测元数据；登记 PR #76 / TD-036 / Issue #79 依赖，不修改 B 轨实现。所有结果状态 `PENDING` / `UNVERIFIED`，无虚构分数。状态 `CANDIDATE_FOR_FREEZE`。 | E 轨道 |

---

## 结束声明

1. 本文件为检索评测**定义**的增量规范，不是已取得的评测结果。
2. 本文件延续 D3：所有指标当前 `UNVERIFIED`，不得解读为已满足目标阈值。
3. 本文件不含任何虚构分数或结果结论；不声明任何 Gold 数据已完成复核、已封存或任何宿主验证结论。
4. 本文件不修改 B 轨实现、不自行关闭 TD-036；仅提供 E 轨书面冻结输入供 B 轨修正使用。

> **本文档到此结束。后续修订将在非作者 D Reviewer 审查与对应 PR 合并、相关 `PENDING_*` 项解除、B 轨按 TD-036 关闭条件实现并验证后进行。**