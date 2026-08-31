# Day9E 检索 Corpus 与 Query 候选集 v1（D9_RETRIEVAL_DATASET_V1）

- **版本**：v1
- **状态**：`D9_RETRIEVAL_DATASET_V1`（候选集，**非 Gold、非回归集、非封存测试集、未人工双人复核、未锁定哈希**）
- **阶段定位**：Day9 / E 轨道 / 检索评测 Corpus 与 Query 候选集（供 B 轨 Recall/MRR/nDCG 评测与人工标注复核的样本层载体；本任务本身不执行任何评测、不产出任何分数）
- **作者轨道**：E（记忆业务、安全、数据集与业务指标）
- **配套文件**：
  - `D9_RETRIEVAL_CORPUS_V1.jsonl`（检索语料候选行，≥60 条）
  - `D9_RETRIEVAL_QUERYSET_CANDIDATE_V1.jsonl`（查询候选行，≥36 条）
  - `test_d9_retrieval_dataset.py`（候选集验证测试）
- **任务性质声明**：本任务为纯数据集 + 文档 + 标准库测试任务（`runtime_required=false`、`runtime_commands=[]`），不产生 Runtime 结论，不更新 `evidence/index.yaml`，不声明任何评测结果。

---

## 一、用途

本候选集为 Day9E 检索评测的**样本层载体**，目标是提供可人工双人复核的检索语料（Corpus）与查询候选（Query）：

1. **正向召回覆盖**：六类 `knowledge_type` 均有合法可检索正解行，供 `positive_retrieval` 查询承载正确召回；
2. **危险近似候选**：与正解语义相近但业务上不可召回的干扰行（expired / superseded / candidate / removed / unresolved conflict / cross-user / 旧 version），用于探测检索是否误召回；
3. **负向 guardrail**：`relevant_ids` 为空但带 `guardrail_reason` 的护栏查询，覆盖 D9 Gold policy 七类业务边界；
4. **boundary**：语义未定（PENDING 项）样本，单列待语义确认后重新归类。

本候选集**不是**最终评测结果，不含任何分数或结论。

---

## 二、数据来源声明

所有内容为**合成/脱敏**，强调以下约束：

- 不含任何真实用户数据、真实账户、手机号、身份证、私钥、API Key、Token 或密码正文。
- 用户 ID 使用合成格式 `user_demo_d9e_a` / `user_demo_d9e_b`，均为虚构。
- 敏感正文一律用 `[REDACTED_*]` 占位（如 `[REDACTED_TOKEN]`、`[REDACTED_PATH]`），不出现真实敏感正文。
- 凭据占位格式沿用既有纪律：`sk-demo-PLACEHOLDER-*`、`api_key=fake-PLACEHOLDER-*`、`password=PLACEHOLDER-*`、`token=PLACEHOLDER-*`。
- **禁止**出现 `sk-live-*`、`sk-prod-*`、`-----BEGIN RSA PRIVATE KEY-----`、`AKIA[0-9A-Z]{16}` 等真实凭据模式。

### 与 D6 来源关系（重要）

本候选集的条目**独立构造**，仅**复用 D6 多源开发集的场景构造与错误归因思想**（如生命周期语义错误码 `LIFE-002`（过期当作活跃）、`LIFE-003`（candidate 被声称 verified 跳过复核）、`LIFE-004`（未复核候选被当作正式知识）），并在 `rationale` / `notes` 中按需引用 D6 错误码作归因参考。

**本候选集与 D6 均保持非 Gold 定位：**
- `D6_MULTISOURCE_DEVSET_V1.jsonl` 仍是 `DEVSET_V1`（非 Gold），不因被本候选集引用思想而升级为 Gold；
- 本候选集也不因引用 D6 错误码而升级为 Gold。
- 本候选集**不是**把 D6 DEVSET_V1 改名冒充 Gold；两者条目、schema 与用途均不同（D6 为多源准入错误归因开发集，本候选集为知识检索语料/查询集）。

---

## 三、非 Gold / 候选声明

本候选集定位：

- **不是**最终 Gold Label 集；
- **不是**回归集；
- **不是**封存测试集；
- **尚未**人工双人复核、**尚未**切分、**尚未**锁定 SHA-256 哈希；
- 任何记录的 `annotation_status` 仅使用 `candidate` / `pending_review`，**不含** `reviewed` / `sealed`；
- 不产生任何评测结果、分数或指标结论。

后续必须经**人工双人复核、语义确认、切分与封存**流程（见「九、后续流程」）后，方可升级为正式 Gold / 回归 / 封存子集。在此之前不得把本候选集描述为最终 Gold、回归集或封存测试集。

---

## 四、Corpus 字段规范

`D9_RETRIEVAL_CORPUS_V1.jsonl` 每行为一个合法 JSON 对象，必填字段如下：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `memory_id` | string | 非空；格式 `d9c-{NNN}` | 记忆逻辑对象标识；同一 memory_id 可含多版本行（行主键为 `(memory_id, version_id)`）；`knowledge_id` 与之 1:1 同值（候选约定，见 §六） |
| `version_id` | string | 非空；`(memory_id, version_id)` 组合全局唯一；格式 `d9c-{NNN}-v{N}` | 版本号；同一 memory_id 可多版本 |
| `knowledge_id` | string | 非空；与 `memory_id` 同值 | 候选约定（见 §六） |
| `user_id` | string | ∈ 合成用户集 `{user_demo_d9e_a, user_demo_d9e_b}` | 归属用户 |
| `object_type` | string | 恒 `knowledge` | 对齐 `ObjectType.KNOWLEDGE` |
| `memory_type` | string enum | ∈ {`short_term`,`medium_term`,`long_term`,`ephemeral`} | 对齐 `MemoryType` 四值 |
| `knowledge_type` | string enum | ∈ KnowledgeType 六值 | 见 §五 |
| `primary_category` | string | 开放业务分类标签；非空 | 不可替代 `knowledge_type` |
| `content_summary` | string | 非空；合成/脱敏 | 知识内容概述（用于检索匹配的语义载体） |
| `source_event_id` | string | 非空 | 来源事件；合成，如 `d9evt-{NNN}` |
| `memory_status` | string enum | ∈ MemoryStatus 六值 | 见 §五 |
| `sensitivity` | string enum | ∈ 五值 `{none,low,medium,high,critical}` | D3 五级；`high/critical` 正文仅 `[REDACTED_*]` 占位 |
| `conflict_state` | string enum | ∈ {`none`,`resolved`,`unresolved`} | **候选约定**（无冻结枚举，见 §六） |
| `is_current` | boolean | 每 memory_id 恰一条 `true` | 对齐 `TruthRecord`「每个 memory_id 唯一一个 True」 |
| `relation_ids` | array[string] | 可为空数组；元素非空 | knowledge 关联关系 ID（合成） |
| `distractor_tag` | string\|null | `null` 或 D9 七类 + `stale_version` | 危险近似标记（见 §五） |
| `notes` | string | 可为空 | 备注 |

### 行属性一致性（测试强制）

| `distractor_tag` | 强制相符的行属性 |
|------|------|
| `removed_or_forgotten` | `memory_status=removed` |
| `expired` | `memory_status=expired` |
| `superseded` | `memory_status=superseded`（若 `stale_version` 则还需 `is_current=false`） |
| `candidate` | `memory_status=candidate` |
| `unresolved_conflict` | `conflict_state=unresolved` |
| `cross_user` | 行对其归属用户本身是合法的 active 行；但对目标查询用户不可召回 |
| `sensitive_recall_prohibited` | `sensitivity ∈ {high, critical}` 且正文仅 `[REDACTED_*]` 占位 |
| `stale_version` | `is_current=false` 且 `memory_status=superseded` |

### 正向可检索行（positive-answerable）

**positive-answerable** 行定义为同时满足：`memory_status=active`、`is_current=true`、`conflict_state != "unresolved"`、`sensitivity ∈ {none,low,medium}`。这些行可作为 `positive_retrieval` 查询的 `relevant_ids` 引用。

---

## 五、枚举来源与 D9 Gold 角色

### 5.1 knowledge_type 六值（权威来源 `memory-service/domain/enums.py::KnowledgeType`，D3 §5.6 冻结）

`workflow` / `case` / `template` / `fact` / `constraint` / `failure_experience`

### 5.2 memory_status 六值（`MemoryStatus`，D3 §5.6 冻结）

`active` / `superseded` / `deprecated` / `expired` / `removed` / `candidate`

### 5.3 memory_type 四值（`memory-service/pipeline/schemas.py::MemoryType`）

`short_term` / `medium_term` / `long_term` / `ephemeral`

### 5.4 sensitivity 五值（D3 业务契约五级，分级标准 HD-ANNO-05 待终审）

`none` / `low` / `medium` / `high` / `critical`

### 5.5 评测角色三角色（来源 `D9_RETRIEVAL_GOLD_POLICY_V1.json` / `D9_RETRIEVAL_GOLD_SPEC_V1.md`）

- `positive_retrieval`：`relevant_ids` 非空，进入 Recall/MRR/nDCG 正式分母；
- `negative_guardrail`：`relevant_ids` 为空或命中业务边界，单列不进入正式分母；
- `boundary`：语义未定（PENDING 项），单列不进入正式分母。

### 5.6 D9 七类 negative_guardrail 业务边界 + stale_version（危险近似）

直接复用 D9 policy `negative_guardrail_scope` 七类 category_id，另加本候选集用于「旧版本」干扰的 `stale_version`（语义=被替代的旧版本，`is_current=false`）：

`removed_or_forgotten` / `expired` / `superseded` / `candidate` / `unresolved_conflict` / `cross_user` / `sensitive_recall_prohibited` / `stale_version`

---

## 六、候选约定（PENDING 确认，非冻结契约）

以下为本数据集 v1 采用的**候选约定**，**不是**已冻结的共享生产契约，待对应轨道确认后可调整（调整不影响候选集建立）：

1. **`knowledge_id ≡ memory_id`（1:1 同值）**：仓库中尚无冻结映射（`candidate_governance.py` 仅见 `knowledge_id=entity_id`）。待 D 轨持久化层冻结后校准。
2. **`conflict_state` 取值集 `{none, resolved, unresolved}`**：仓库无冻结枚举（D1-B 检索草稿用 `"none"`，检索测试用 `"resolved"/"unresolved"`，D8B 要求「未解决项默认排除」）。`unresolved` 对齐 D8B 与 D9 gold `unresolved_conflict` 语义。
3. **`distractor_tag` 与 `near_miss_refs`**：本候选集专用评测字段，属评测归因层，不进入生产契约。
4. **`relevant_ids` / `near_miss_refs` 引用键为 `memory_id`**。
5. 本候选集**只承载知识检索语料**（`object_type=knowledge`），不含 preference 语料；如需扩展另立任务。

---

## 七、Query 字段规范

`D9_RETRIEVAL_QUERYSET_CANDIDATE_V1.jsonl` 每行为一个合法 JSON 对象：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `query_id` | string | 全局唯一；格式 `d9q-{NNN}` | 查询唯一标识 |
| `query` | string | 非空；合成/脱敏 | 查询文本 |
| `user_id` | string | ∈ 合成用户集 | 查询发起用户 |
| `evaluation_role` | string enum | ∈ {`positive_retrieval`,`negative_guardrail`,`boundary`} | 评测角色（D9 三角色） |
| `relevant_ids` | array[string] | `positive_retrieval` 非空；其余为空数组 | 引用 Corpus `memory_id` |
| `near_miss_refs` | array[string] | 可为空数组；元素引用存在的 Corpus 行、不在 `relevant_ids`、业务不可召回 | 危险近似干扰行引用 |
| `guardrail_category` | string\|null | 仅 `negative_guardrail` 必填，∈ D9 七类 | 护栏边界类别 |
| `guardrail_reason` | string\|null | `negative_guardrail` 必填非空 | 护栏剔除原因 |
| `boundary_reason` | string\|null | `boundary` 必填，引用 PENDING 事项 | 边界说明（如 `PENDING_B_CONFIRMATION` / 标注规范 §4.1 争议 / `TEAM_DEFINED` 参数） |
| `rationale` | string | 所有查询必填非空 | 判定依据说明，可引用 D9 policy 条目与 D6 错误码 |
| `annotation_status` | string enum | ∈ {`candidate`,`pending_review`} | 标注状态；不含 reviewed/sealed |
| `notes` | string | 可为空 | 备注 |

### 引用一致性规则（测试强制）

`relevant_ids` / `near_miss_refs` 均以 **memory_id（逻辑对象）** 为引用键。由于同一 memory_id 可含多版本行，引用解析语义为：**该 memory_id 下存在满足业务规则的行即可**（`relevant_ids`：存在 positive-answerable 行且该 memory_id 任何行均无 distractor_tag；`near_miss_refs`：存在对查询用户业务不可召回的行）。

- `positive_retrieval` 的每个 `relevant_ids` 引用须满足：该 memory_id 存在 `user_id` 与查询一致、`memory_status=active`、`is_current=true`、`conflict_state != "unresolved"`、`sensitivity ∈ {none,low,medium}` 且无 distractor_tag 的行。
- `negative_guardrail` / `boundary` 的 `relevant_ids` 必须为空数组 `[]`。
- `near_miss_refs` 的每个引用须存在、不在 `relevant_ids` 中、且该 memory_id 下存在对查询用户业务不可召回的行（命中以下之一：`memory_status ∈ {expired,superseded,removed,candidate}` / `conflict_state="unresolved"` / `user_id` 与查询用户不同 / `is_current=false` / `sensitivity ∈ {high,critical}` / 行带非空 `distractor_tag`）。

---

## 八、覆盖度配额（测试强制取下限）

### Corpus

- 总数 ≥ 60；
- positive-answerable 行六类 `knowledge_type` 各 ≥ 4；
- 干扰行：`expired` / `superseded` / `candidate` / `removed` / `unresolved_conflict` / `cross_user` / `stale_version` 各 ≥ 2；
- `user_id` ≥ 2（跨用户干扰与 B 用户自有正例）。

### Query

- 总数 ≥ 36；
- `positive_retrieval` ≥ 20：六类 `knowledge_type` 各 ≥ 3，其中 ≥ 1 条 user 为第二合成用户；
- `negative_guardrail` ≥ 12：七类 category 各 ≥ 1，每条 ≥ 1 个 `near_miss_refs`；
- `boundary` ≥ 4；
- 所有查询的 `near_miss_refs` 形态集合覆盖七种危险形态（expired、superseded、candidate、removed、unresolved conflict、cross-user、stale version）。

---

## 九、后续流程

1. **人工双人复核**（对齐标注规范 §4.1）：标注人 A 初标 → 标注人 B 复核 → 争议提交 Reviewer（D/E）裁决；`annotation_status` 从 `candidate`/`pending_review` 升级为 `reviewed`（本任务产物未执行此步）。
2. **语义确认**（对齐 D9 gold）：`PENDING_B_CONFIRMATION` 等边界事项确认后，boundary 样本重新归类。
3. **切分**（对齐 D3 TD-07）：开发 / 回归 / 封存子集。
4. **封存**：对封存子集锁定 SHA-256 哈希，锁定后禁止修改。
5. 以上步骤完成后由对应轨道另行建立正式 Gold / 回归 / 封存版本（独立任务），**本 `D9_RETRIEVAL_DATASET_V1` 不自我宣称已完成上述步骤**。

---

## 十、测试

`test_d9_retrieval_dataset.py` 自包含（仅标准库 + pytest，不导入 memory-service），校验：

- JSONL 逐行合法 JSON、必填字段完整、`memory_id` / `(memory_id,version_id)` / `query_id` 全局唯一且格式合法；
- 全部枚举合法（knowledge_type / memory_status / memory_type / sensitivity / conflict_state / object_type / evaluation_role / annotation_status / guardrail_category / distractor_tag）；
- 每 memory_id 恰一条 `is_current=true`；
- 六类 knowledge_type 正向覆盖、三角色均有样本、七类危险干扰在 Corpus 与 near_miss_refs 双层覆盖；
- `positive_retrieval` `relevant_ids` 非空且每个引用满足 Gold 规则；`negative_guardrail` 可为空但必须带 `guardrail_reason`；`boundary` 带 `boundary_reason`；
- 所有 `relevant_ids` / `near_miss_refs` 引用存在且业务状态符合规则；`relevant_ids` 不得引用非空 `distractor_tag` 行；
- 全文无真实凭据模式、无 reviewed/sealed 令牌；
- 非法 JSON / 重复 ID / 缺字段 / 未知枚举 / 覆盖不足 / 引用悬空时测试真实失败（硬断言、无 skip、无 xfail、无吞异常、无自动修正）。

---

## 十一、变更记录

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v1 | 2026-08-31 | 初稿：建立检索 Corpus 与 Query 候选集（Corpus ≥60 行、Query ≥36 条），复用 Day8E 六类 knowledge_type 业务语义与 Day9E Gold 三角色七类边界；覆盖正向召回、危险近似候选与负向 guardrail；标注候选约定（knowledge_id≡memory_id、conflict_state 三值）待冻结。产物为候选，未人工双人复核、未封存、未锁定哈希、不含评测结果。 | E 轨道 |

---

## 结束声明

1. 本候选集为检索评测**候选样本载体**，不是已取得的评测结果，不含分数或结论。
2. 本候选集未人工双人复核、未语义确认、未切分、未封存、未锁定哈希；`annotation_status` 仅 `candidate`/`pending_review`。
3. 本候选集约定了多处 PENDING 事项（knowledge_id≡memory_id、conflict_state 取值、distractor_tag、near_miss_refs），待 D/B 轨道确认，不得描述为冻结契约。
4. 本候选集仅复用 D6 的错误归因思想（LIFE-002/003/004 等），条目独立构造；D6 与本候选集均保持非 Gold。
5. 本任务不产生任何银河麒麟 Runtime 验证结论（`RUNTIME_NOT_REQUIRED`）。
