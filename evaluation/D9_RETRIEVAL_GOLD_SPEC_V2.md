# Day9E 检索 Gold 与指标语义 v2（D9_RETRIEVAL_GOLD_SPEC_V2）

- **版本**：v2
- **状态**：`CANDIDATE_FOR_FREEZE`
- **阶段定位**：Day9 / E 轨道 / 检索评测 Gold 与指标语义增量规范（TD-036 E 侧书面冻结输入）；**吸收 B 轨 2026-08-31 对 PR #88 的正式裁决，升级自 v1 候选**
- **作者轨道**：E（记忆业务、安全、数据集与业务指标）
- **Reviewer 轨道**：D（IPC、SQLite、Outbox、虚拟机成品化与发布）
- **上位基线**：`evaluation/D3_GOLD_LABEL_AND_METRICS_SPEC_V1.md`（`CANDIDATE_FOR_FREEZE`）。本文件**只在 D3 基线之上做 Day9 检索评测增量澄清，不重写 D3 既有 Gold 业务定义**。
- **配套文件**：
  - `evaluation/D9_RETRIEVAL_GOLD_POLICY_V2.json`（机器可读策略契约，`policy_version=v2`，版本化、fail-fast）
  - `evaluation/test_d9_retrieval_gold_spec.py`（策略与规范验证测试，只针对 v2）
- **前序版本**：v1 候选文件（`D9_RETRIEVAL_GOLD_SPEC_V1.md` / `D9_RETRIEVAL_GOLD_POLICY_V1.json`）**已由本 v2 替换移除**，不保留为最终有效策略；v1→v2 演进说明见「十六、变更记录」，Git 历史保留 v1 演进。
- **冻结为团队基线条件**：**只有非作者 D Reviewer 批准且对应 PR 合并后，本文档方可视为团队冻结基线**（对齐 D3 第十五章口径）。`CANDIDATE_FOR_FREEZE` 仅表示 E 轨道在 B 轨 2026-08-31 PR #88 裁决之上提出的 v2 候选语义集合，**不代表已被 D 批准、不代表 D3/Day9 Gate 通过、不代表任何指标已满足阈值、不代表任何宿主行为或实现能力已被验证**。
- **本文件冻结的是评测定义，不是已取得的评测结果**：不含任何虚构分数、延迟或结果结论；所有当前结果状态一律 `PENDING` / `UNVERIFIED`。
- **任务性质声明**：本任务为纯文档 + JSON + 标准库测试任务（`runtime_required=false`、`runtime_commands=[]`）。L0/L1 本地静态检查与单元测试结果**不得**被表述为银河麒麟宿主验证结论。

---

## 一、定位、范围与依赖关系

### 1.1 目的

为 TD-036（空 Gold 查询的 Recall/MRR/nDCG 剔除与聚合口径未冻结）提供 **E 轨书面冻结输入**：M2 三项指标（Recall@K、MRR、nDCG）的有效查询集合、空 Gold 查询处理规则、retrieval_ref 序列化判定键、negative_guardrail 角色与 guardrail violation 统计口径、冻结的评测配置（`d9-retrieval-eval-config/v1`）、conflict_state 评测归一化语义及版本化评测元数据。本文件同时是 **PR #76** 关联技术债的 E 轨口径依赖，并吸收 **PR #88** 的 B 轨裁决。

### 1.2 边界（本文件不做的事）

- **不修改 B 轨检索实现**：`memory-service/retrieval/**`（含 `evaluation.py`、`fusion.py`、`contracts.py`）不在本任务范围；本任务只冻结 E 轨评测语义，不修改 B 轨实现，由 B 轨任务按其职责完成实现侧处置。
- **不自行关闭 TD-036**：TD-036 保持 `Open`，其关闭条件（含 B 统一三项指标有效分母与聚合、记录有效查询数与剔除数量/原因、覆盖空集/混合集/全空集）由 B 轨任务按 TD 登记行执行。
- **不重写 D3**：D3 已定义的 Gold Label 判定、OFFICIAL_REQUIREMENT 指标口径、TEAM_DEFINED 统计细节、双向追踪与 FREEZE_BLOCKERS 一并沿用。
- **不修改数据集三件**：`D9_RETRIEVAL_CORPUS_V1.jsonl`、`D9_RETRIEVAL_QUERYSET_CANDIDATE_V1.jsonl`、`D9_RETRIEVAL_DATASET_README_V1.md` 不在本任务修改范围；queryset 候选的 `relevant_ids`/`near_miss_refs` 升级为 retrieval_ref 属后续独立数据集任务，本文件不暗示已升级。

### 1.3 引用锚点（D3 已核验原文）

- D3 第四章 M2 无效样本处理：「无正解（Gold Label 判定为「不应形成记忆」）的查询不进入分母」。
- D3 第四章 M2 无效样本处理：「命中 S-01..S-09 的查询样本剔除并单列」。
- D3 第五章约束：统计细节「一律标记 `TEAM_DEFINED`（非 OFFICIAL_REQUIREMENT）」。
- D3 第五章登记：TD-06（M2/M4 的 K 值与命中判定规则，`TEAM_DEFINED`，责任 B）、TD-07（数据集切分比例与抽样种子，`TEAM_DEFINED`，责任 B/E）。

---

## 二、评测角色划分（三类）

| 角色 | 定义 | 是否进入 M2 正式分母 | 报告方式 |
|------|------|----------------------|----------|
| `positive_retrieval` | `relevant_refs` 非空且至少含一条有效正解（可检索、已验证的事实知识条目，ref 键为 `retrieval_ref=(memory_id, version_id)`）的正式检索查询 | **是**（进入 Recall/MRR/nDCG 三项正式分母与聚合） | 按 `knowledge_type`、`primary_category` 拆分子集报告 |
| `negative_guardrail` | `relevant_refs` 为空（no-answer/拒绝类）或命中业务/安全边界的查询：已遗忘/removed、expired、superseded、deprecated、candidate、unresolved conflict、cross-user、禁止敏感召回（八类） | **否**（单列） | 计数 + 剔除原因 + guardrail violation 统计，作为防伪护栏，不得计为满分 |
| `boundary` | 语义未定样本：标注规范 §4.1 争议裁决前、`PENDING_*` 待确认项（含 `PENDING_B_CONFIRMATION` 等） | **否**（单列） | 单列 boundary 子集，待语义确认后重新归类 |

> 角色判定顺序：先判 `boundary`（语义未定则退出正式评测）→ 再判 `negative_guardrail`（无正解或命中边界则单列）→ 其余为 `positive_retrieval`。三类角色合计构成查询全集；**只有 `positive_retrieval` 进入三项指标正式分母**。`deprecated` 经 B 轨 2026-08-31 PR #88 裁决已脱离 boundary，归入 `negative_guardrail`（见第六章）。

---

## 三、空 Gold（empty relevant_refs）规则

### 3.1 规则定义

**D9-EMPTY-GOLD-01**：查询 `relevant_refs` 为空（Gold Label 判定为「不应形成记忆」/无正解）时，该查询**不得进入 Recall/MRR/nDCG 三项指标的任何正式分母与分子**，且**不得解释为满分或其他默认值**。与 D3 第四章 M2 无效样本处理「无正解（Gold Label 判定为「不应形成记忆」）的查询不进入分母」一致。

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

每次正式评测必须报告：`valid_query_count`（进入正式分母的有效查询数）、`excluded_query_count`（剔除查询数量）、`exclusion_reason`（剔除原因，按 negative_guardrail / boundary / 环境异常分类）。该规则在 v2 中**逐字沿用 v1**，未因裁决改变。

---

## 四、序列化判定键：retrieval_ref

### 4.1 版本级判定键（本任务冻结）

正式 Gold / near-miss / 检索返回结果的**序列化判定键**冻结为：

- **`retrieval_ref = (memory_id, version_id)`**：用于 Gold 正解、near-miss 引用与检索返回结果的序列化与匹配判定。

**完整校验键**冻结为：

- **`(user_id, memory_id, version_id)`**：用于含用户隔离维度的完整校验（跨用户校验、数据唯一性核验）。

### 4.2 适用范围

`retrieval_ref` 契约至少覆盖以下四类序列化对象：`relevant_refs`、`forbidden_refs`、`semantic_near_miss_refs`、`retrieval_returned_results`。

### 4.3 废弃语义

`relevant_ids` / `near_miss_refs` 的 **memory_id-only** 语义**不再作为正式 Gold v2 契约**。任何正式评测的 Gold 正解、near-miss 引用与检索返回结果判定必须携带 `(memory_id, version_id)` 版本级引用（memory_id-only 仅可作为候选约定或数据集演进期的过渡形态，不构成 v2 冻结契约）。

### 4.4 数据集现状如实声明

当前 `D9_RETRIEVAL_CORPUS_V1.jsonl` 每行已含 `version_id`（主键 `(memory_id, version_id)`）；但 queryset 候选的 `relevant_ids`/`near_miss_refs` 仍为 **memory_id-only 候选约定**（dataset README 自我声明为候选、非冻结契约）。queryset 升级为 `retrieval_ref` 属**后续独立数据集任务**，本规范不暗示其已升级；正式评测消费 queryset 前必须完成该升级。

---

## 五、negative_guardrail 业务边界（八类）

| category_id | 依据（D3 / 标注规范 / 安全契约 / B 轨裁决） | guardrail_expectation |
|-------------|-------------------------------|----------------------|
| `removed_or_forgotten` | `memory_status=removed`；精准遗忘执行后（D3 第九章 9.4）已遗忘条目不得再被检索返回 | 已遗忘/removed 条目不得作为查询正解；相关查询单列并记录剔除原因 |
| `expired` | `memory_status=expired`；临时偏好/临时知识过期后不再作为有效记忆（D3 第六章 6.3） | expired 条目不得作为正解；仅含过期正解的查询不得进入正式分母 |
| `superseded` | `memory_status=superseded`；被替代条目保留仅用于审计与回溯（D3 第八章 8.2） | superseded 条目不得作为当前知识正解；相关查询单列排除 |
| `deprecated` | **B 轨 2026-08-31 PR #88 裁决**：deprecated 在 standard Memory Context 中归入 negative_guardrail，不再作为 boundary / `PENDING_B_CONFIRMATION` 待确认项 | deprecated 条目在 standard Memory Context 检索中不得被召回为正解（不进入标准 M2 正式分母）；仅显式 history/audit 模式可访问；相关查询单列并记录剔除原因（专项语义见第六章） |
| `candidate` | `memory_status=candidate`；未经人工复核/证据确认（模型自述、LLM 候选）不得升级为已验证正解（D3 第七章 7.3、标注规范 §4.1/§4.2） | candidate 条目不得进入正式检索正解集合；相关查询排除并单列 |
| `unresolved_conflict` | 标注规范 §4.1 争议裁决前冲突双方保持 `memory_status=candidate`（D3 第八章 8.2） | 未裁决冲突条目不得作为正解；相关查询单列待裁决后处置 |
| `cross_user` | 跨 `user_id` 读取/检索一律拒绝并标记 `isolation_violation=true`、`sensitivity=critical`（S-08、SEC-UI-05、D3 第九章 9.2 / 第十章） | 跨用户条目不得作为任何用户查询的正解；相关查询单列并记录隔离边界；violation query/item count 与 rate 必须为 0 |
| `sensitive_recall_prohibited` | 命中 S-01..S-09 强制不形成记忆（D3 第七章/第十章、SEC-SENS）；敏感原文不得出现在评测记录 | 敏感内容不得被召回为正解；相关查询剔除并单列，记录仅用脱敏占位或 ID 引用；violation query/item count 与 rate 必须为 0 |

> 这些边界样本**不得伪装成 Recall=1.0**：它们不是「应命中零条后被判正确」的负样本，而是**不参与正式指标计算**的护栏样本。任何评测不得以空 Gold 或边界样本制造满分记录；guardrail violation 统计口径见第七章。

---

## 六、deprecated 专项语义（B 轨裁决落地）

### 6.1 裁决来源

B 轨 2026-08-31 对 PR #88 的正式裁决（经任务卡 `day9-e-rw-01-gold-policy-v2-b-adjudication-v1` 传入）明确：`memory_status=deprecated` 在 standard Memory Context 中归入 `negative_guardrail`。

### 6.2 语义冻结

1. **standard Memory Context**：deprecated 条目归入 negative_guardrail，检索**不得召回为正解**，不进入标准 M2 正式分母与聚合；
2. **访问边界**：deprecated 条目**仅显式 history/audit 模式可访问**（审计与回溯用途）；
3. **不再属于 boundary**：v1 中「`memory_status=deprecated` 的检索集合语义待 B 确认」的 boundary/PENDING 项已解除，deprecated 从第十章的 boundary 子集移出。

### 6.3 实现侧关系（仅引用、不修改）

`memory-service/service/retrieval_business_policy.py` 的 docstring 对 V1 的引用（逐字表述「deprecated 在 D9 Gold 中列为 boundary…后续 B 轨冻结时通过 POLICY_VERSION 升版调整」）在 v2 落地后**已过时**，属遗留待更新项（见第十四章依赖登记），本任务不修改该模块。

---

## 七、guardrail violation 统计口径

### 7.1 触发定义

**Top-K 检索返回结果中出现任一 forbidden ref**（命中第五章 negative_guardrail_scope 中任一类别对应的 `retrieval_ref` / `memory_id`）时：

- 该 query 计 **1 次** `guardrail_violation_query_count`（同一 query 内重复命中不重复累计 query 计数）；
- 同时**逐条累计** `guardrail_violation_item_count`。

### 7.2 必报字段与派生口径

每次正式评测的护栏统计必须报告：

| 字段 | 含义 |
|------|------|
| `guardrail_violation_query_count` | 出现违规的查询数（query 粒度，命中任一 forbidden ref 计 1 次） |
| `guardrail_violation_item_count` | 违规返回条目数（item 粒度，逐条累计） |
| `guardrail_violation_query_rate` | 违规查询比例（query rate） |
| `guardrail_violation_item_rate` | 违规条目比例（item rate） |
| 按类别拆分 | 对八类禁止类别逐一拆分 query/item count 与 rate（`per_category_breakdown_required=true`） |

### 7.3 critical 零值约束

- **`cross_user` 与 `sensitive_recall_prohibited`** 两类的 violation query/item count 与 rate **必须为 0**，**任一非零必须标记为 critical**；
- 其余禁止类别（`removed_or_forgotten` / `expired` / `superseded` / `deprecated` / `candidate` / `unresolved_conflict`）的 violation count/rate **目标值同样为 0**（目标 0，非 critical 门槛）。

### 7.4 分母口径与独立性

- 本统计**独立于 Recall/MRR/nDCG 正式分母**（正式分母仅 `positive_retrieval` 进入），不改变空 Gold 规则（D9-EMPTY-GOLD-01）；
- rate 分母建议口径（B 轨裁决未明示，为**本任务建议、待 Reviewer 确认后随本契约冻结**）：query rate = `guardrail_violation_query_count` / 参与护栏统计的查询总数；item rate = `guardrail_violation_item_count` / 同批 Top-K 返回条目总数。

---

## 八、评测配置冻结（d9-retrieval-eval-config/v1）

### 8.1 冻结取值

| 参数 | 冻结取值 | 说明 |
|------|----------|------|
| `config_version` | `d9-retrieval-eval-config/v1` | 评测配置版本标识 |
| `k`（Recall@K 的 K） | `10` | Recall@10 |
| `top_k` | `10` | Top-K 检索结果窗口 |
| `rrf_k` | `60` | RRF 聚合 k 值 |
| `top_k == k` | **相等**（`top_k_equals_recall_k=true`） | 明确 `top_k == Recall@K`，二者为同一值的两种表述 |
| `origin` | `TEAM_DEFINED` | 团队约定，非比赛官方要求 |
| `official_requirement` | `false` | 不得描述为比赛官方要求 |

### 8.2 来源与性质

- 取值来自 **B 轨 2026-08-31 PR #88 裁决冻结**；`origin=TEAM_DEFINED`，对齐 D3 第五章「统计细节一律标记 TEAM_DEFINED（非 OFFICIAL_REQUIREMENT）」；
- 与 B 轨实现现状一致（`memory-service/retrieval/evaluation.py` 现行默认 `top_k=10`、`rrf_k=60`）仅作为**事实旁证**，不构成修改依据；本任务不修改 B 轨代码。

---

## 九、conflict_state 评测归一化语义

### 9.1 合法取值与定位

- `conflict_state = {none, resolved, unresolved}` **仅属 evaluation normalization field（评测归一化字段）**；
- **NOT production shared enum**：不新增生产 Enum，不进入生产共享枚举契约。

### 9.2 与生产检索的关系

- 生产检索**继续依赖既有 unresolved 硬过滤**（`memory-service/retrieval` 既有行为：`conflict_state == "unresolved"` 硬过滤），本任务不修改该实现；
- 评测记录中的 `conflict_state` 仅用于评测归一化与统计归类，**不改变生产检索的 conflict 过滤语义**。

---

## 十、boundary 子集（单列）

以下样本语义未定，**不进入任何正式分母**，单列报告：

- 标注规范 §4.1 争议裁决前的样本；
- `PENDING_*` 待确认项：`PENDING_B_CONFIRMATION`、`PENDING_E_CONFIRMATION`、`PENDING_D_CONFIRMATION` 等（对齐 D3 第三章/第八章）；
- 其他 `TEAM_DEFINED` 参数取值冻结前相关的语义歧义样本（含第十一章未冻结参数）。

> **注意**：v1 中「`memory_status=deprecated` … 待 B 确认」的 boundary 项**已由 B 轨裁决移除**，deprecated 归入第五章 negative_guardrail 第六类，此处不再列出。

---

## 十一、TEAM_DEFINED 未冻结参数边界

延续 D3 第五章约束：「以下统计细节比赛原文未规定，如需要由团队约定，**一律标记 `TEAM_DEFINED`（非 OFFICIAL_REQUIREMENT）**」。下列参数取值**尚未被任何裁决冻结**，维持 `PENDING`，本任务只登记标记与边界（`frozen=false`）：

| 参数 | D3 登记 | 当前取值 | origin | frozen |
|------|---------|----------|--------|--------|
| 统计方法（p50/p95/mean/max 等） | D3 第五章 TD-01（责任 B/D） | `PENDING` | `TEAM_DEFINED` | `false` |
| 数据集切分比例与抽样种子 | D3 第五章 TD-07（责任 B/E） | `PENDING` | `TEAM_DEFINED` | `false` |

> **已冻结的 `k` / `top_k` / `rrf_k` 已移入第八章评测配置冻结（`d9-retrieval-eval-config/v1`），不在本表重复登记**。裁决未覆盖 `statistics_method` / `dataset_split`，按「不自行扩张到未裁决事项」原则维持 `PENDING`。

---

## 十二、B 轨后续实现要求（E 轨书面输入，不修改代码）

E 轨口径冻结后，B 轨任务应（对齐 TD-036 关闭条件与 PR #76 关联技术债处置）在 `memory-service/retrieval/evaluation.py` 中统一三项指标（Recall/MRR/nDCG）的有效分母与聚合，并至少：

1. 空 Gold（`relevant_refs` 为空）查询**不进入**三项指标正式分母，**不默认记满分**；
2. 记录 `valid_query_count`（有效查询数）、`excluded_query_count`（剔除数量）与 `exclusion_reason`（剔除原因）；
3. 验证场景覆盖**空集、混合集、全空集**三种形态（对齐 TD-036 关闭条件）；
4. 按本章第八/第九章冻结的评测配置（`k=10`、`top_k=10`、`rrf_k=60`）与 conflict_state 归一化语义实施评测口径。

本文件只提出上述口径要求，**不实现任何指标计算逻辑**；实现细节（聚合顺序、并行统计等）由 B 轨任务自行决定。

---

## 十三、版本化评测元数据

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

## 十四、依赖与引用登记

- **技术债**：TD-036（`docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`，状态 `Open`）——本文件为该登记行「由 E 冻结空 Gold/应答无结果的正式口径」的 E 侧输入；**本文件不自行关闭 TD-036**，关闭由 B 轨任务按其关闭条件执行。
- **关联 PR / Issue**：PR #76（关联技术债登记）、Issue #79、**PR #88（B 轨裁决对象）**。本文件仅引用编号，不回写评审结果字样。
- **裁决来源**：B 轨 2026-08-31 对 PR #88 的正式裁决（经任务卡 `day9-e-rw-01-gold-policy-v2-b-adjudication-v1` 传入）。裁决文档不在仓库内，本文件如实标注来源形态，不虚构仓库文档路径。
- **上位基线**：D3 第四章 M2 口径、第五章 TEAM_DEFINED、第十二章元数据、第十五章冻结条件。
- **配套机器契约**：`evaluation/D9_RETRIEVAL_GOLD_POLICY_V2.json`（`policy_version=v2`），由 `evaluation/test_d9_retrieval_gold_spec.py` 强制校验；未知字段或非法角色 fail-fast，扩展须发 `policy_version=v3` 新任务，不原位放宽。
- **前序版本处置**：V1 候选两文件（`D9_RETRIEVAL_GOLD_SPEC_V1.md` / `D9_RETRIEVAL_GOLD_POLICY_V1.json`）已由本 v2 **替换移除**，不再作为最终 PR 树中的有效策略（Git 历史保留 v1 演进）。
- **遗留待更新项（后续独立任务，不在本任务范围）**：
  - `memory-service/service/retrieval_business_policy.py` docstring 中对 V1 spec 的引用（描述 deprecated 为 boundary）在 v2 落地后过时；
  - `evaluation/D9_RETRIEVAL_DATASET_README_V1.md` 对 V1 策略/规范文件的文档级引用。

---

## 十五、冻结与不可冻结声明

### 15.1 可冻结（本文件意图冻结的定义）

- 三类评测角色（`positive_retrieval` / `negative_guardrail` / `boundary`）及各自是否进入 M2 正式分母；
- 空 Gold（empty `relevant_refs`）查询的处理规则与禁止解释（D9-EMPTY-GOLD-01，沿用 v1）；
- 序列化判定键 `retrieval_ref=(memory_id, version_id)` 与完整校验键 `(user_id, memory_id, version_id)`；
- negative_guardrail 八类业务边界及依据（含 deprecated 归入护栏杆）；
- guardrail violation 统计口径（query/item count、rate、按类别拆分、critical 零值约束）；
- 评测配置冻结：`d9-retrieval-eval-config/v1`（k=10、top_k=10、rrf_k=60、top_k==k、TEAM_DEFINED）；
- conflict_state 评测归一化语义（NOT production shared enum）；
- 未冻结 TEAM_DEFINED 参数登记（`statistics_method` / `dataset_split`，`PENDING`）；
- 版本化评测元数据字段清单。

### 15.2 不可冻结（本文件明确不声明）

- **任何评测结果**：不得声明任何指标已满足目标阈值、不得给出任何分数或延迟、不得声明任何评测已正式执行；
- **任何 Gold 数据已完成人工复核或已封存**（复核与封存流程按 D3 第十一章/第十四章执行，当前均未执行）；
- **任何宿主/真实麒麟环境验证结论**：L0/L1 本地检查结果不得表述为宿主验证结论；
- **任何以静态检查或 Mock 冒充正式结果的状态**：对齐 `runtime-validation.md` 的禁止降级规则。

---

## 十六、变更记录

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v2 | 2026-08-31 | 吸收 B 轨 2026-08-31 对 PR #88 的正式裁决（经任务卡 `day9-e-rw-01-gold-policy-v2-b-adjudication-v1` 传入），将检索 Gold/指标语义从 v1 候选升级为 v2：冻结版本级序列化判定键 `retrieval_ref=(memory_id, version_id)` 与完整校验键 `(user_id, memory_id, version_id)`，废弃 `relevant_ids`/`near_miss_refs` 的 memory_id-only 正式契约；`deprecated` 从 boundary 移入 negative_guardrail（第八类，standard Memory Context 禁召回、仅显式 history/audit 模式可访问、不进入标准 M2）；冻结 `evaluation_config=d9-retrieval-eval-config/v1`（k=10、top_k=10、rrf_k=60、top_k==k、TEAM_DEFINED）；新增 guardrail violation 统计口径（query/item count、rate、按类别拆分、cross_user/sensitive_recall_prohibited critical=0）；新增 conflict_state={none,resolved,unresolved} 仅属 evaluation normalization（NOT production shared enum，不新增生产 Enum）；`k/top_k/rrf_k` 从 TEAM_DEFINED 未冻结参数移入冻结配置。V1 候选两文件由本 v2 替换移除（Git 历史保留演进）。所有结果状态 `PENDING` / `UNVERIFIED`，无虚构分数。状态 `CANDIDATE_FOR_FREEZE`。 | E 轨道 |
| v1 | 2026-08-31 | 候选初稿（历史演进记录，对应已移除文件 `D9_RETRIEVAL_GOLD_SPEC_V1.md`）：以 D3 v1 候选为基线，新增三类评测角色及 M2 正式分母语义、空 Gold 规则（D9-EMPTY-GOLD-01）、negative_guardrail 七类边界、boundary 子集、TEAM_DEFINED 参数边界、B 轨后续验证场景要求与版本化评测元数据。该版本 deprecated 列为 boundary 待 B 确认，k/top_k/rrf_k 取值 `PENDING`，均已在 v2 按 B 轨裁决更新。 | E 轨道 |

---

## 结束声明

1. 本文件为检索评测**定义**的增量规范，不是已取得的评测结果。
2. 本文件延续 D3：所有指标当前 `UNVERIFIED`，不得解读为已满足目标阈值。
3. 本文件不含任何虚构分数或结果结论；不声明任何 Gold 数据已完成复核、已封存或任何宿主验证结论。
4. 本文件不修改 B 轨实现、不自行关闭 TD-036；仅提供 E 轨书面冻结输入供 B 轨修正使用；不声明任何正式 Gold 已复核、已封存、任何指标已满足目标阈值或任何宿主验证结论。

> **本文档到此结束。后续修订将在非作者 D Reviewer 审查与对应 PR 合并、相关 `PENDING_*` 项解除、B 轨按 TD-036 关闭条件实现并验证后进行。**