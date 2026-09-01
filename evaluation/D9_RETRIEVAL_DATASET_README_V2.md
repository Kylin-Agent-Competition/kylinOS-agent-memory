# Day9E 检索 Corpus 与 Query 候选集 v2（D9_RETRIEVAL_DATASET_V2）

- **版本**：v2
- **状态**：`D9_RETRIEVAL_DATASET_V2`（候选集，**非 Gold、非回归集、非封存测试集、未人工双人复核、未锁定哈希**）
- **阶段定位**：Day9 / E 轨道 / 检索评测 Corpus 与 Query 候选集（供 B 轨 Recall/MRR/nDCG 评测与人工标注复核的样本层载体；本数据集本身不执行任何评测、不产出任何分数）
- **作者轨道**：E（记忆业务、安全、数据集与业务指标）
- **消费的 Gold 契约**：`evaluation/D9_RETRIEVAL_GOLD_POLICY_V2.json` 与 `evaluation/D9_RETRIEVAL_GOLD_SPEC_V2.md`（`policy_version=v2`，吸收 B 轨 2026-08-31 对 PR #88 的正式裁决）。本候选集**消费 v2 契约、不重新定义任何 Gold 规则**。
- **配套文件**：
  - `D9_RETRIEVAL_CORPUS_V2.jsonl`（检索语料候选行，62 行）
  - `D9_RETRIEVAL_QUERYSET_CANDIDATE_V2.jsonl`（查询候选行，33 条）
  - `D9_RETRIEVAL_DATASET_README_V1.md`（v1 候选说明，已随 V1 三件经 `git rm` 清理提交从当前 PR HEAD 删除，Git 历史保留演进，见「十、与 V1 的关系与清理状态」）
  - `test_d9_retrieval_dataset.py`（候选集验证测试，只验证 V2 契约）
- **任务性质声明**：本任务为纯数据集 + 文档 + 标准库测试任务（`runtime_required=false`、`runtime_commands=[]`），不产生 Runtime 结论，不更新 `evidence/index.yaml`，不声明任何评测结果。

---

## 一、用途

本候选集为 Day9E 检索评测的**样本层载体**，目标是提供可人工双人复核的检索语料（Corpus）与查询候选（Query）：

1. **正向召回覆盖**：六类 `knowledge_type` 均有合法可检索正解版本行，供 `positive_retrieval` 查询承载正确召回；
2. **危险近似候选（版本级）**：与正解语义相近但业务上不可召回的干扰**版本行**（expired / superseded / deprecated / candidate / removed / unresolved conflict / cross-user / 旧 stale version），用于探测检索是否误召回；
3. **负向 guardrail（八类）**：`relevant_refs` 为空但带 `guardrail_reason` 的护栏查询，覆盖 D9 Gold policy v2 八类业务边界；其中 `deprecated` 为 B 轨 2026-08-31 PR #88 裁决从 boundary 移入的新增类别（standard Memory Context 禁召回、仅显式 history/audit 模式可访问）；
4. **boundary**：`boundary` 角色仍保留在 Policy schema，但本数据集 v2 **不强制为覆盖 quota 人工制造 boundary 样本**；只有真实 PENDING retrieval semantics 才允许加入。当前 v2 无 boundary 样本（原 d9q-033/034/035/036 属参数/治理类问题，已从 QuerySet 删除，**不得用治理问题填充检索 Gold**）。

本候选集**不是**最终评测结果，不含任何分数或结论。

---

## 二、数据来源声明

所有内容为**合成/脱敏**，强调以下约束：

- 不含任何真实用户数据、真实账户、手机号、身份证、私钥、API Key、Token 或密码正文。
- 用户 ID 使用合成格式 `user_demo_d9e_a` / `user_demo_d9e_b`，均为虚构。
- 敏感正文一律用 `[REDACTED_*]` 占位（如 `[REDACTED_TOKEN]`、`[REDACTED_PATH]`），不出现真实敏感正文。
- 凭据占位格式沿用既有纪律：`sk-demo-PLACEHOLDER-*`、`api_key=fake-PLACEHOLDER-*`、`password=PLACEHOLDER-*`、`token=PLACEHOLDER-*`。
- **禁止**出现 `sk-live-*`、`sk-prod-*`、`-----BEGIN RSA PRIVATE KEY-----`、`AKIA[0-9A-Z]{16}` 等真实凭据模式。
- `memory_id` / `version_id` / `knowledge_id` / `query_id` 均为合成标识，不含真实生产标识。

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
- 任何记录的 `annotation_status` 仅使用 `candidate` / `pending_review`，**不升级**为已复核/已封存状态；
- 不产生任何评测结果、分数或指标结论。

后续必须经**人工双人复核、语义确认、切分与封存**流程（见「十一、后续流程」）后，方可升级为正式 Gold / 回归 / 封存子集。在此之前不得把本候选集描述为最终 Gold、回归集或封存测试集。

---

## 四、Corpus 字段规范

`D9_RETRIEVAL_CORPUS_V2.jsonl` 每行为一个合法 JSON 对象，必填字段如下：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `memory_id` | string | 非空；格式 `d9c-{NNN}` | 记忆逻辑对象标识；同一 memory_id 可含多版本行（行主键为 `(memory_id, version_id)`） |
| `version_id` | string | 非空；`(memory_id, version_id)` 组合全局唯一；格式 `d9c-{NNN}-v{N}` | 版本号；同一 memory_id 可多版本，每条可检索/干扰版本均可被 `(memory_id, version_id)` 唯一定位 |
| `knowledge_id` | string | 非空；格式 `d9k-{NNN}`；**必须与 `memory_id` 不同值** | **相互独立的合成标识**：同一 memory 各版本共享同一 d9k 值；与生产 knowledge_id 的映射关系见「五、映射契约」 |
| `user_id` | string | ∈ 合成用户集 `{user_demo_d9e_a, user_demo_d9e_b}` | 归属用户 |
| `object_type` | string | 恒 `knowledge` | 对齐 `ObjectType.KNOWLEDGE` |
| `memory_type` | string enum | ∈ {`short_term`,`medium_term`,`long_term`,`ephemeral`} | 对齐 `MemoryType` 四值 |
| `knowledge_type` | string enum | ∈ KnowledgeType 六值 | 见 §六 |
| `primary_category` | string | 开放业务分类标签；非空 | 不可替代 `knowledge_type` |
| `content_summary` | string | 非空；合成/脱敏 | 知识内容概述（用于检索匹配的语义载体） |
| `source_event_id` | string | 非空 | 来源事件；合成，如 `d9evt-{NNN}` |
| `memory_status` | string enum | ∈ MemoryStatus 六值 | 见 §六；v2 新增 `deprecated` 干扰行（`d9c-057`） |
| `sensitivity` | string enum | ∈ 五值 `{none,low,medium,high,critical}` | D3 五级；`high/critical` 正文仅 `[REDACTED_*]` 占位 |
| `conflict_state` | string enum | ∈ {`none`,`resolved`,`unresolved`} | **评测归一化字段**（见 §六） |
| `is_current` | boolean | 每 memory_id 恰一条 `true` | 对齐 `TruthRecord`「每个 memory_id 唯一一个 True」 |
| `relation_ids` | array[string] | 可为空数组；元素非空 | knowledge 关联关系 ID（合成） |
| `distractor_tag` | string\|null | `null` 或 D9 干扰标记 | 危险近似标记（见 §六） |
| `notes` | string | 可为空 | 备注 |

### 行属性一致性（测试强制）

| `distractor_tag` | 强制相符的行属性 |
|------|------|
| `removed_or_forgotten` | `memory_status=removed` |
| `expired` | `memory_status=expired` |
| `superseded` | `memory_status=superseded`（若 `stale_version` 则还需 `is_current=false`） |
| `deprecated` | `memory_status=deprecated`（v2 新增取值；B 轨 2026-08-31 PR #88 裁决：standard Memory Context 禁召回、仅显式 history/audit 模式可访问） |
| `candidate` | `memory_status=candidate` |
| `unresolved_conflict` | `conflict_state=unresolved` |
| `cross_user` | 行对其归属用户本身是合法的 active 行；但对目标查询用户不可召回 |
| `sensitive_recall_prohibited` | `sensitivity ∈ {high, critical}` 且正文仅 `[REDACTED_*]` 占位 |
| `stale_version` | `is_current=false` 且 `memory_status=superseded` |

### 正向可检索版本行（positive-answerable）

**positive-answerable** 版本行定义为同时满足：`memory_status=active`、`is_current=true`、`conflict_state != "unresolved"`、`sensitivity ∈ {none,low,medium}`。这些版本行可作为 `positive_retrieval` 查询的 `relevant_refs` / `semantic_near_miss_refs` 引用（以完整校验键 `(user_id, memory_id, version_id)` 精确命中）。

---

## 五、映射契约（PENDING_D_CONFIRMATION）

1. **`knowledge_id` ↔ `memory_id` 生产映射仍 `PENDING_D_CONFIRMATION`**：v1 曾以候选约定声明 `knowledge_id ≡ memory_id`（1:1 同值）；v2 **不再声明任何 1:1 等同共享契约**。v2 的 `knowledge_id` 使用相互独立的合成标识 `d9k-{NNN}`，其与 memory_id 的对应关系仅供本测试数据集承载数据，**不等同于生产映射已冻结**。正式生产映射需 D 轨冻结后另立任务校准，届时测试的 `d9k-` 格式断言随新契约升版。
2. **`formal_mapping_status=PENDING_D_CONFIRMATION`**：本数据集明确登记生产映射状态为待 D 确认，不宣称 equality。
3. **`conflict_state` 取值集 `{none, resolved, unresolved}`**：属 evaluation normalization 字段（对齐 Gold Policy v2 `conflict_state_semantics`），NOT production shared enum。
4. **`distractor_tag` 与 retrieval_ref 三桶引用**：本候选集专用评测字段，属评测归因层，不进入生产契约。
5. 本候选集**只承载知识检索语料**（`object_type=knowledge`），不含 preference 语料；如需扩展另立任务。

---

## 六、枚举与引用契约（对齐 Gold Policy v2）

### 6.1 knowledge_type 六值（权威来源 `memory-service/domain/enums.py::KnowledgeType`，D3 §5.6 冻结）

`workflow` / `case` / `template` / `fact` / `constraint` / `failure_experience`

### 6.2 memory_status 六值（`MemoryStatus`，D3 §5.6 冻结）

`active` / `superseded` / `deprecated` / `expired` / `removed` / `candidate`

### 6.3 memory_type 四值（`memory-service/pipeline/schemas.py::MemoryType`）

`short_term` / `medium_term` / `long_term` / `ephemeral`

### 6.4 sensitivity 五值（D3 业务契约五级）

`none` / `low` / `medium` / `high` / `critical`

### 6.5 评测角色三角色（来源 `D9_RETRIEVAL_GOLD_POLICY_V2.json`）

- `positive_retrieval`：`relevant_refs` 非空，进入 Recall/MRR/nDCG 正式分母；
- `negative_guardrail`：`relevant_refs` 为空或命中业务边界，单列不进入正式分母；
- `boundary`：语义未定（PENDING 项），单列不进入正式分母；v2 无 boundary 样本、不设配额，只有真实 PENDING retrieval semantics 才允许加入。

### 6.6 retrieval_ref 版本级引用契约（v2 冻结，替代 v1 memory_id-only）

对齐 Gold Policy v2 `retrieval_ref_schema`：

- **序列化键**：`retrieval_ref = (memory_id, version_id)`；
- **完整校验键**：`(user_id, memory_id, version_id)`；
- **适用对象**：`relevant_refs` / `forbidden_refs` / `semantic_near_miss_refs` / `retrieval_returned_results`；
- **废弃语义**：`relevant_ids` / `near_miss_refs` 的 memory_id-only 语义**不再作为正式契约**；本候选集 Query 已统一升级为三个 ref 数组，每个 ref 为对象且**恰好** `{memory_id, version_id}` 两个键（禁止 memory_id-only 字符串引用、禁止 ref 内添加额外扩展键）。

**三桶语义（测试强制）：**

- `relevant_refs`（仅 `positive_retrieval`）：每个 ref 精确命中同 user、`memory_status=active`、`is_current=true`、`conflict_state != "unresolved"`、`sensitivity ∈ {none,low,medium}`、无 `distractor_tag` 的**确切版本行**；
- `forbidden_refs`：每个 ref 精确命中对查询用户**业务不可召回**的确切版本行（用户不同，或 `memory_status ∈ {expired,superseded,removed,candidate,deprecated}`，或 `conflict_state=unresolved`，或 `is_current=false`，或 `sensitivity ∈ {high,critical}`，或带非空 `distractor_tag`）；跨用户 forbidden ref 必须解析到**另一个 user** 的 corpus 版本行并被判定为禁止；
- `semantic_near_miss_refs`：每个 ref 必须命中对查询用户**业务合法可召回**（即满足 positive-answerable 全部条件且属同 user）的**确切 current 版本行**，不计入 guardrail violation；
- 同一条查询内三桶 ref **两两不相交**。

### 6.7 D9 negative_guardrail 八类业务边界

对齐 Gold Policy v2（v2 在 v1 七类基础上加入 `deprecated`，由 B 轨 2026-08-31 PR #88 裁决从 boundary 移入）：

`removed_or_forgotten` / `expired` / `superseded` / `deprecated` / `candidate` / `unresolved_conflict` / `cross_user` / `sensitive_recall_prohibited`

---

## 七、Query 字段规范

`D9_RETRIEVAL_QUERYSET_CANDIDATE_V2.jsonl` 每行为一个合法 JSON 对象：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `query_id` | string | 全局唯一；格式 `d9q-{NNN}` | 查询唯一标识 |
| `query` | string | 非空；合成/脱敏 | 查询文本 |
| `user_id` | string | ∈ 合成用户集 | 查询发起用户 |
| `evaluation_role` | string enum | ∈ {`positive_retrieval`,`negative_guardrail`,`boundary`} | 评测角色（D9 三角色；`boundary` 保留在 schema，v2 无样本） |
| `relevant_refs` | array[retrieval_ref] | `positive_retrieval` 非空；其余为空数组 | 版本级正解引用 |
| `forbidden_refs` | array[retrieval_ref] | 可为空数组 | 业务禁止版本引用 |
| `semantic_near_miss_refs` | array[retrieval_ref] | 可为空数组 | 业务合法但语义近似的 current 版本引用 |
| `guardrail_category` | string\|null | 仅 `negative_guardrail` 必填，∈ D9 八类 | 护栏边界类别 |
| `guardrail_reason` | string\|null | `negative_guardrail` 必填非空 | 护栏剔除原因 |
| `boundary_reason` | string\|null | `boundary` 必填，引用 PENDING 事项 | 边界说明（v2 无 boundary 样本，字段保留可空） |
| `rationale` | string | 所有查询必填非空 | 判定依据说明，可引用 D9 policy v2 条目、B 轨裁决与 D6 错误码 |
| `annotation_status` | string enum | ∈ {`candidate`,`pending_review`} | 标注状态；**不含**已复核/已封存状态 |
| `notes` | string | 可为空 | 备注 |

**禁现字段**：`relevant_ids` / `near_miss_refs` 为 v1 legacy 字段，本数据集任何记录出现即视作数据错误（测试失败）。

---

## 八、覆盖度（真实样本决定的最低覆盖，测试强制取下限）

### Corpus

- 总数 ≥ 62；
- positive-answerable 版本行六类 `knowledge_type` 各 ≥ 4；
- 干扰行：`removed_or_forgotten` / `expired` / `superseded` / `candidate` / `unresolved_conflict` / `cross_user` / `stale_version` 各 ≥ 2，`deprecated` 干扰行 ≥ 1；
- `user_id` ≥ 2（跨用户干扰与 B 用户自有正例）。

### Query

- 总数 ≥ 33；
- `positive_retrieval` ≥ 20：六类 `knowledge_type` 各 ≥ 3，其中 ≥ 1 条 user 为第二合成用户；
- `negative_guardrail` ≥ 13：**八类** category 各 ≥ 1，每条 ≥ 1 个 `forbidden_refs`；
- `boundary` **无配额**：仅当真实存在 PENDING retrieval semantics 样本时加入；不得为覆盖 quota 人工制造 boundary 样本；
- 版本级禁止引用形态覆盖九态：deprecated、removed、expired、superseded、candidate、unresolved、cross-user、sensitive、stale version；
- **不得用治理问题填充检索 Gold**：原 d9q-033/034/035/036 属参数/治理类问题，已从 v2 删除，不生成无业务意义的 filler query 补量。

---

## 九、B 轨裁决落地（2026-08-31 PR #88，经任务卡 day9-e-rw-01 传入）

| 裁决项 | v2 落地 |
|--------|---------|
| d9q-001 | 保留 canonical `(d9c-001, v1)` 为 current candidate relevant_ref；`(d9c-037, v1)`（superseded）入 `forbidden_refs`；`(d9c-037, v2)` 入 `semantic_near_miss_refs` 并保持 `pending_review`，等待人工确认是否晋升 relevant_ref |
| d9q-003 | 改写为明确「部署流程中，合并代码的上一步需要执行什么？」语义（workflow 上一步），目标 `(d9c-005, v1)` |
| d9q-007 | `(d9c-038, v2)` 是 active/current，**绝不能入 `forbidden_refs`**，保留则入 `semantic_near_miss_refs`；其 stale `(d9c-038, v1)` 作为 forbidden ref |
| d9q-010 | 保留 canonical `(d9c-019, v1)` 为 current candidate relevant_ref；`(d9c-039, v1)` 入 `forbidden_refs`；`(d9c-039, v2)` 入 `semantic_near_miss_refs` 并保持 `pending_review`，等待人工确认等价 Gold |
| d9q-016 | 改写为明确「合并代码前必须满足的强制准入条件是什么？」语义（constraint 强制准入），目标 `(d9c-029, v1)` |
| d9q-033/035/036 | 属参数/治理问题，**从 QuerySet 删除**（不设填充 quota） |
| d9q-034 | 语料不足，**从 QuerySet 删除** |
| deprecated 护栏 | Corpus 新增 1 条 deprecated 知识（`d9c-057-v1`）；Query 新增独立新 query_id `d9q-037`（**不复用被拒绝的 d9q-033**）询问其业务内容，`evaluation_role=negative_guardrail`、`guardrail_category=deprecated`、`forbidden_refs` 指向 `(d9c-057, v1)` |

---

## 十、与 V1 的关系与清理状态

1. **当前 PR 仅保留 V2 Dataset**：V2 为当前 PR 唯一保留的检索候选 Dataset；V1 三件（`D9_RETRIEVAL_CORPUS_V1.jsonl`、`D9_RETRIEVAL_QUERYSET_CANDIDATE_V1.jsonl`、`D9_RETRIEVAL_DATASET_README_V1.md`）已通过 `git rm` 清理提交序列从当前分支 HEAD（Reviewer D 审查基线 a6456fd 对应的清理序列）删除。
2. **删除为已提交状态**：V1 三件的删除已随清理提交进入当前 PR HEAD，不再存在于 PR 树；Git 历史保留 V1 演进记录，可追溯。`test_d9_retrieval_dataset.py` 只验证 V2 契约，**不读取 V1 文件**、不新增「V1 文件必须不存在」断言，V1 删除后测试不受影响。

---

## 十一、后续流程

1. **人工双人复核**（对齐标注规范 §4.1）：标注人 A 初标 → 标注人 B 复核 → 争议提交 Reviewer（D/E）裁决；`annotation_status` 从 `candidate`/`pending_review` 升级为已复核状态（本任务产物未执行此步）。
2. **语义确认（两项挂起的人工 Gold 确认，不阻塞本任务）**：d9q-001 的 `(d9c-037, v2)` 是否晋升 relevant_ref；d9q-010 的 `(d9c-039, v2)` 是否确认等价 Gold。V2 以 `semantic_near_miss_refs` + `annotation_status=pending_review` + `notes` 如实承载。
3. **映射确认**：`knowledge_id ↔ memory_id` 生产映射待 D 轨冻结（`formal_mapping_status=PENDING_D_CONFIRMATION`）。
4. **切分**（对齐 D3 TD-07）：开发 / 回归 / 封存子集。
5. **封存**：对封存子集锁定 SHA-256 哈希，锁定后禁止修改。
6. 以上步骤完成后由对应轨道另行建立正式 Gold / 回归 / 封存版本（独立任务），**本 `D9_RETRIEVAL_DATASET_V2` 不自我宣称已完成上述步骤**。

---

## 十二、测试

`test_d9_retrieval_dataset.py` 自包含（仅标准库 + pytest，不导入 memory-service），校验：

- JSONL 逐行合法 JSON、必填字段完整、`(memory_id, version_id)` / `query_id` 全局唯一且格式合法；
- 全部枚举合法（knowledge_type / memory_status / memory_type / sensitivity / conflict_state / object_type / evaluation_role / annotation_status / guardrail_category / distractor_tag）；
- retrieval_ref 对象恰好两键（memory_id + version_id）；禁现 `relevant_ids` / `near_miss_refs` legacy 字段；
- 每 memory_id 恰一条 `is_current=true`；`knowledge_id` 独立格式 `d9k-{NNN}` 且与 memory_id 不同值、同 memory 各版本共享同一 knowledge_id；
- 六类 knowledge_type 正向覆盖、四角色枚举稳定、八类危险干扰在 Corpus 与 forbidden_refs 双层覆盖（deprecated 新增在内）；
- `positive_retrieval` `relevant_refs` 非空且每个引用精确满足 Gold 规则；`forbidden_refs` 指向业务禁止版本（含跨用户与 stale/superseded 版本级禁止）；`semantic_near_miss_refs` 指向业务合法 current 版本；三桶两两不相交；
- 版本级禁止引用形态覆盖九态（deprecated、removed、expired、superseded、candidate、unresolved、cross-user、sensitive、stale version）；
- B 轨裁决锚定断言（d9q-001/003/007/010/016 版本拆分与问法改写、d9q-033/034/035/036 消失、新增 deprecated guardrail 查询）；
- 覆盖不足、引用悬空、禁现字段、伪状态令牌/真实凭据出现时测试真实失败（硬断言、无 skip、无 xfail、无吞异常、无自动修正）。

---

## 十三、变更记录

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v2 | 2026-08-31 | 升级检索 Corpus/Query 候选集为版本级 retrieval_ref（relevant_refs / forbidden_refs / semantic_near_miss_refs，每个 ref 含 memory_id + version_id），落地 B 轨 2026-08-31 PR #88 裁决：d9q-001/010 stale v1 与 current v2 拆分、d9q-003/016 问法改写、d9q-007 d9c-038-v2 不入 forbidden、删除 d9q-033/034/035/036；新增 deprecated 干扰行 d9c-057 与全新 query_id d9q-037 护栏样本；knowledge_id 改为独立合成标识 `d9k-{NNN}` 并声明生产映射 `formal_mapping_status=PENDING_D_CONFIRMATION`；覆盖配额改由真实样本决定（boundary 无配额、不得用治理问题填充检索 Gold）。创建 v2 时 V1 三件尚保留为构造输入与 Git 过渡（当时状态）；其后已由 `git rm` 清理提交从当前 PR HEAD 删除。产物为候选，未人工双人复核、未封存、未锁定哈希、不含评测结果。 | E 轨道 |
| v2 文档同步 | 2026-09-01 | 关闭 Reviewer D 二轮 MEDIUM-2：§10/配套文件/结束声明由执行前过渡表述同步为当前 HEAD 已清理状态（V1 三件已删除、V2 为当前 PR 唯一候选 Dataset）；不改动 V2 数据、Gold v2 契约与评测语义。 | E 轨道 |
| v1 | 2026-08-31 | 初稿：建立检索 Corpus 与 Query 候选集（Corpus 61 行、Query 36 条），引用键为 memory_id-only 候选约定（relevant_ids / near_miss_refs），knowledge_id≡memory_id 1:1 同值为候选约定，deprecated 当时列为 boundary 待 B 确认；以上均已在 v2 按 B 轨裁决与 Policy v2 升级。对应文件 `D9_RETRIEVAL_DATASET_README_V1.md` 由人工清理步骤移除（Git 历史保留演进）。 | E 轨道 |

---

## 结束声明

1. 本候选集为检索评测**候选样本载体**，不是已取得的评测结果，不含分数或结论。
2. 本候选集未人工双人复核、未语义确认、未切分、未封存、未锁定哈希；`annotation_status` 仅 `candidate`/`pending_review`。
3. 消费 Gold Policy/Spec v2 契约（含 B 轨 2026-08-31 PR #88 裁决），不重新定义任何 Gold 规则；`knowledge_id ↔ memory_id` 生产映射仍 `PENDING_D_CONFIRMATION`，不宣称 equality。
4. 本候选集仅复用 D6 的错误归因思想（LIFE-002/003/004 等），条目独立构造；D6 与本候选集均保持非 Gold。
5. V1 三件已通过 `git rm` 清理提交序列从当前 PR HEAD 删除，当前 PR 仅保留 V2 Dataset；Git 历史保留 V1 演进记录。
6. 本任务不产生任何银河麒麟 Runtime 验证结论（`RUNTIME_NOT_REQUIRED`）。