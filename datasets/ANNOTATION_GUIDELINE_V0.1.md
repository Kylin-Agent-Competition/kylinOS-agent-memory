# 数据标注与安全边界规范

- **版本**：v0.1
- **状态**：DRAFT
- **用途**：开发集与标注规则初稿，为后续数据建设、Gold Label 规则、安全边界与开发集分类提供统一标准
- **冻结门槛**：D3 Gate 前不得视为最终标注规范；须经 D/E Reviewer 审查，且需与导入后的比赛方案、总体架构 SOP、数据查找选型与质量审计手册对齐后方可冻结为 v1.0
- **依据来源**：
  - `README.md`（项目定位、当前阶段、六类评测数据方向）
  - `docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md`（业务对象与枚举定义）
  - `docs/project-management/REQUIREMENT_TRACEABILITY_MATRIX.md`（REQ-01 至 REQ-07）
  - `datasets/README.md`（三类数据划分与禁止提交内容）
- **局限声明**：
  - 「数据查找选型与质量审计手册」属基线文档，当前标注「待人工导入」，无法在本任务内阅读原稿；本规范据此记录为冻结 v1.0 的前置条件之一
  - 官方 AI 助手真实 Tool/Turn/Context 事件结构尚未取得麒麟 VM 证据（C 轨道 `os-agent-integration/` 当前仅建立目录和职责边界），Tool Result 标注字段均为 DRAFT 语义，标注为 UNVERIFIED
  - 封存测试集尚未制作、尚未锁定哈希；本规范仅建立规则，不可声称测试集已封存
- **本次修订说明**（v0.1 修订，2026-07-30）：本稿已完成与修订后 `MEMORY_BUSINESS_SCHEMA_V0.1.md`（含 v0.1 修订）的字段对齐，主要变更包括：引入 `user_id`/`actor_id` 用户隔离；`confidence` 更名为 `confidence_score`；`evidence_turn_ids` 更名为 `evidence_event_ids`；偏好增加 `memory_status`/`should_persist` 字段，候选判定改用 `memory_status=candidate`；知识增加 `knowledge_type` 枚举；精准遗忘字段重命名为 `target_selector`/`resolved_target_ids`；新增 Tool 成功但不形成长期记忆及跨用户正向/负向案例。标注规范状态不变（v0.1 DRAFT），不对齐审计手册或 Copilot 审查报告（二者于基线文档中均「待人工导入」，已记录为冻结 v1.0 前置条件 HD-ANNO-01/HD-SCHEMA-11），`expression_type` 术语终选待 HD-SCHEMA-14。

---

## 一、术语对齐

本规范与 `docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md` 共用业务术语。关键术语如下：

| 术语 | 含义 | 对应业务对象 |
|------|------|-------------|
| 偏好 | 用户对系统行为的个性化要求，可为显式或隐式 | `Preference` |
| 知识 | 经过抽取和归一化的结构化信息条目 | `Knowledge` |
| Tool Result | 官方 AI 助手 Tool 调用执行后返回的结果事件 | `MemorySourceEvent.source_type=tool_result` |
| 冲突 | 两条或多条知识/偏好之间的语义或事实不一致 | `Conflict` |
| 精准遗忘 | 按指定粒度仅删除目标记忆条目，不波及无关数据 | `ForgetPlan` |
| 端到端会话 | 跨多 Turn 的完整对话序列，包含多类数据融合 | 多对象联合 |
| 开发集分类 | 将单一样本按业务语义归类到偏好/知识/Tool Result 等维度的标签体系 | 标注规则层 |
| Gold Label | 经人工规则与双人复核确定的最终标注标签，是该样本在评测中的标准答案 | 标注规则层 |

---

## 二、六类评测数据

本规范定义六类评测数据，与赛题核心需求对齐。每类数据独立定义其标注对象、标注字段、Gold Label 规则和示例模板。

### 2.1 偏好（Preference）

**对应 REQ**：REQ-02 偏好动态捕捉。

**标注对象**：从单条或多条 `MemorySourceEvent` 中提取的偏好片段。一个对话 Turn 可包含零条、一条或多条偏好标注。

**标注字段**：

| 字段 | 含义 | 取值说明 |
|------|------|---------|
| `user_id` | 数据归属用户标识（用户隔离键） | string，required，来自宿主侧业务事件，`*禁止模型生成`；如 `"user_demo_01"` |
| `preference_key` | 偏好键名（业务语义标识） | 英文 snake_case，如 `language_pref`、`search_sort_order` |
| `preference_value` | 偏好值 | 字符串，如 `"zh-CN"`、`"by_modified_desc"` |
| `expression_type` | 偏好表达类型 | 同 Schema 枚举 2.4：`explicit`（显式声明）/ `implicit`（隐式表达）/ `inferred`（推断/候选表达）。注意：原 `candidate` 语义已迁移至 `memory_status=candidate` 表达；`inferred` 与 `candidate` 术语对应，终选待 HD-SCHEMA-14 |
| `scope` | 作用域 | 同 Schema 枚举 2.8：`global` / `topic` / `tool` / `session` / `time_window` |
| `confidence_score` | 置信度评分（0.0–1.0） | 人工标注。显式声明 → 0.9–1.0；隐式推断 → 0.5–0.8；边界争议 → 记录原因 |
| `memory_status` | 记忆生命周期状态 | 同 Schema 枚举 2.7：`active` / `superseded` / `deprecated` / `expired` / `removed` / `candidate`。候选判断阶段使用 `memory_status=candidate`，不再通过 `expression_type=candidate` 表达 |
| `is_temporary` | 是否为临时要求 | `true` / `false`；若为 true，必须注明临时范围（如「仅本次会话」「仅当前 Turn」）。`is_temporary=true` 或 `should_persist=false` 时，`memory_status` 必须为 `candidate` |
| `should_persist` | 是否应持久化为正式偏好 | `true` / `false`；`false` 时等同临时要求，不产生正式长期偏好，`memory_status=candidate` |
| `evidence_event_ids` | 支撑该偏好的事件 ID 列表 | 如 `["evt_20260730_a1b2c3", "evt_20260729_d4e5f6"]`；依据 Schema 以事件 ID 为业务证据链 |
| `source_turn_ids` | 支撑该偏好的 Turn ID 列表（可选） | 如 `["turn_01", "turn_03"]`；保留对话内 Turn 粒度溯源，与 `evidence_event_ids` 正交，不承载业务依据语义 |
| `annotator` | 标注人标识 | 如 `"reviewer_e_01"` |
| `annotated_at` | 标注时间 | ISO 8601 时间戳 |

**Gold Label 规则**：
- 偏好标签由人工根据会话上下文判定：标注人 A 初标，标注人 B 复核，争议提交 Reviewer 裁决。
- LLM 仅用于辅助生成候选表达（如从自然语言中提取候选 key-value 对），不得独立决定最终偏好标签。
- 复核记录必须包含：复核人、复核时间、是否同意初标、不同意时的修改建议和理由。
- **候选与正式区分**：`expression_type=inferred` 的偏好条目或 `is_temporary=true` / `should_persist=false` 的条目，在置信度达标且经行为验证/人工复核确认前，`memory_status` 保持 `candidate`，不晋升为正式偏好（`memory_status=active`）。候选条目不参与用户级偏好检索链路，也不参与偏好冲突判定。

### 2.2 知识（Knowledge）

**对应 REQ**：REQ-03 知识整合与冲突、REQ-04 端侧 Embedding 与轻量检索。

**标注对象**：从 `MemorySourceEvent` 中抽取的结构化知识条目。一个事件可产生零条或多条知识标注。

**标注字段**：

| 字段 | 含义 | 取值说明 |
|------|------|---------|
| `user_id` | 数据归属用户标识（用户隔离键） | string，required，来自宿主侧业务事件，`*禁止模型生成`；如 `"user_demo_01"` |
| `knowledge_summary` | 知识内容摘要 | 一句话概括，如「用户每月底整理一次文件目录」 |
| `knowledge_type` | 知识子类型 | 同 Schema 枚举 2.5：`workflow`（工作流/操作习惯）/ `case`（案例/场景）/ `template`（模板/格式）/ `fact`（事实性）/ `constraint`（约束/规则）/ `failure_experience`（失败经验）。必须填写，不得以 `primary_category` 替代 |
| `primary_category` | 主分类标签（开放业务分类） | 如「文件操作」「系统设置」「开发习惯」；**不可替代 `knowledge_type`**，用于语义检索和元数据过滤 |
| `confidence_score` | 置信度评分（0.0–1.0） | 人工标注 |
| `source_type` | 来源类型 | 同 Schema 枚举 2.1 |
| `is_outdated` | 是否已过时（过渡字段） | `true` / `false`；待 D/E 统一为 `memory_status` 后在 v1.0 中移除 |
| `memory_status` | 记忆生命周期状态 | 同 Schema 枚举 2.7：`active` / `superseded` / `deprecated` / `expired` / `removed` / `candidate` |
| `extracted_entities` | 抽取的实体列表 | 如 `["文件管理器", "月末", "目录整理"]` |
| `evidence_event_ids` | 支撑该知识的事件 ID 列表 | 如 `["evt_001", "evt_002"]` |
| `annotator` | 标注人标识 | 同偏好 |
| `annotated_at` | 标注时间 | ISO 8601 |

### 2.3 Tool Result（Tool 结果）

**对应 REQ**：REQ-01 多源数据。

**标注对象**：单次 Tool 调用返回的结果事件。标注的核心是判定该 Tool Result 是否应形成记忆（偏好/知识）、应标记为失败不形成记忆、还是仅作为瞬态上下文。

**标注字段**：

| 字段 | 含义 | 取值说明 |
|------|------|---------|
| `tool_call_id` | Tool 调用标识 | 如 `"tool_file_search_v2_001"` |
| `tool_name` | Tool 名称 | 如 `"file_search"` |
| `execution_status` | 执行状态 | `success` / `partial` / `failure` / `timeout` |
| `should_form_memory` | 是否应形成记忆 | `true` / `false` |
| `memory_type_if_formed` | 若形成记忆，为何种类型 | `preference` / `knowledge` / `ephemeral` / `N/A` |
| `failure_tag` | 若不应形成记忆，原因为何 | `tool_failure` / `transient_context` / `sensitive_content` / `user_aborted` / `N/A` |
| `annotator` | 标注人标识 | 同偏好 |
| `annotated_at` | 标注时间 | ISO 8601 |

**关键规则**：
- Tool 执行失败（`execution_status=failure` 或 `timeout`）时，`should_form_memory` 必须为 `false`，`failure_tag` 必须标注 `tool_failure`。
- Tool 执行成功但结果仅为瞬态上下文（如一次性查询当前时间、一次性状态探测、单次查询结果），`should_form_memory` 可为 `false`，`failure_tag` 标注 `transient_context`。此类反例已追加至 §六 案例库（正例7）。
- 不得将 Tool 成功但属瞬态上下文的结果错误标注为 Knowledge 或 Preference 条目。

**验证状态**：UNVERIFIED（官方 AI 助手真实 Tool 调用格式与返回结构尚未取得麒麟 VM 证据，C 轨道尚未集成。本规范定义的 Tool Result 标注字段均为 DRAFT 语义层占位，D3 Gate 前需 C 轨道取证后回填。）

### 2.4 冲突（Conflict）

**对应 REQ**：REQ-03 知识整合与冲突。

**标注对象**：存在逻辑矛盾、时间不一致或来源冲突的知识/偏好条目对。标注人应标注冲突双方、冲突类型和消解建议。

**标注字段**：

| 字段 | 含义 | 取值说明 |
|------|------|---------|
| `user_id` | 数据归属用户标识（用户隔离键） | string，required，派生自冲突涉及的条目，`*禁止模型生成` |
| `left_item_id` | 冲突左方条目 ID | 如 `"pref_001"` |
| `right_item_id` | 冲突右方条目 ID | 如 `"pref_002"` |
| `conflict_type` | 冲突类型 | 同 Schema 枚举 2.10 |
| `conflict_description` | 冲突描述 | 自然语言，解释矛盾所在 |
| `recommended_resolution` | 消解建议 | `keep_left` / `keep_right` / `merge` / `flag_for_review` / `keep_higher_confidence` |
| `annotator` | 标注人标识 | 同偏好 |
| `annotated_at` | 标注时间 | ISO 8601 |

### 2.5 精准遗忘（Forget）

**对应 REQ**：REQ-05 敏感过滤与精准遗忘。

**标注对象**：用户明确表达的遗忘请求。标注的核心是确认遗忘目标精确范围、确认流程（先预览再确认）、执行后的验证证据。

**标注字段**：

| 字段 | 含义 | 取值说明 |
|------|------|---------|
| `user_id` | 数据归属用户标识（用户隔离键） | string，required，来自宿主侧业务事件，`*禁止模型生成` |
| `forget_request_turn_id` | 用户提出遗忘请求的 Turn ID | 如 `"turn_11"`；可选保留 Turn 粒度溯源，与 `evidence_event_ids` 正交 |
| `target_selector` | 用户输入的遗忘目标选择器（原始描述） | 自然语言，如「忘掉我上周关于 Python 项目的所有内容」；对应 Schema `target_selector` |
| `forget_mode` | 遗忘粒度 | 同 Schema 枚举 2.12 |
| `resolved_target_ids` | 系统解析后的目标 ID 列表 | 如 `["kn_003", "pref_005"]`；必须经预览确认后方可执行删除，`*禁止模型生成` |
| `affected_count` | 实际影响的记录数量 | integer，`*禁止模型生成`，由系统在执行后产出；标注阶段可填写预期值 |
| `preview_provided` | 执行前是否提供了预览 | `true` / `false` |
| `user_confirmed` | 用户是否确认执行 | `true` / `false` |
| `requires_confirmation` | 是否需要用户确认后执行 | `true` / `false`；`*禁止模型生成`最终决策 |
| `execution_verified` | 遗忘执行后验证是否通过 | `true` / `false` / `N/A` |
| `hard_delete` | 是否为硬删除（不留明文残留） | `true` / `false` |
| `annotator` | 标注人标识 | 同偏好 |
| `annotated_at` | 标注时间 | ISO 8601 |

**关键规则**：
- 精准遗忘必须先预览再确认：系统在遗忘执行前必须向用户展示受影响的条目列表，获得确认后方可执行。
- 硬删除（`hard_delete=true`）时，被删除内容不得在 SQLite 正文、Vector 索引、FTS5 全文索引或缓存中留存可检索的明文残留。
- 遗忘以业务对象级别的 `resolved_target_ids` 为精准范围，不得按模糊关键词或时间窗口粗略删除后声称「已精准遗忘」。

### 2.6 端到端会话（End-to-End Session）

**对应 REQ**：REQ-06 短中长期流转。

**标注对象**：一个完整的多 Turn 会话序列，标注其整体记忆流转路径（短期→中期→长期）、会话中形成的全部偏好/知识/冲突/Tool Result 条目，以及会话结束后的记忆回收策略。

**标注字段**：

| 字段 | 含义 | 取值说明 |
|------|------|---------|
| `user_id` | 数据归属用户标识（用户隔离键） | string，required，来自宿主侧业务事件，`*禁止模型生成` |
| `session_id` | 会话标识 | 如 `"sess_e2e_001"` |
| `turn_count` | 会话 Turn 总数 | 整数 |
| `formed_preferences` | 会话中形成的偏好条目 ID 列表 | 如 `["pref_001", "pref_002"]` |
| `formed_knowledge` | 会话中形成的知识条目 ID 列表 | 如 `["kn_001"]` |
| `conflicts_detected` | 会话中检测到的冲突 ID 列表 | 如 `["cfl_001"]` |
| `tool_results` | 会话中 Tool Result 事件 ID 列表 | 如 `["evt_tool_001", "evt_tool_002"]` |
| `forget_requests` | 会话中的遗忘请求 ID 列表 | 如 `["fgp_001"]` |
| `short_term_items` | 会话级短期记忆条目 ID | 如 `["pref_001"]` |
| `medium_term_candidates` | 跨会话后应流转为中期记忆的条目 ID | 如 `["kn_001"]` |
| `long_term_candidates` | 多会话巩固后应流转为长期记忆的条目 ID | 如 `["pref_002"]` |
| `annotator` | 标注人标识 | 同偏好 |
| `annotated_at` | 标注时间 | ISO 8601 |

---

## 三、开发集分类

开发集标注时，每个样本应归属到以下七类之一（或标记为不形成记忆）。分类是标注流程的前置步骤，用于确定后续需要填写的标注字段集合。

| 分类 | 定义 | 判定要点 | 示例概要 |
|------|------|---------|---------|
| **明确偏好** | 用户以直接、不含糊的文字表达的对系统行为的偏好要求 | 明确说出「我希望……」「以后都用……」「设置默认为……」等指令性表达；文本无歧义 | 用户说「以后回复都用中文」|
| **隐式偏好** | 用户未直接声明，但通过反复行为、问句模式或选择倾向可推断的偏好 | 需从≥2 个 Turn 的行为模式推断；置信度 0.5–0.8；标注人必须在复核记录中写明推断逻辑 | 用户连续三次选择「按日期倒序」而非默认排序 |
| **临时要求** | 用户明确提出但限定于当前会话或当前 Turn 的临时性偏好/指令 | 含有「这次」「现在」「当前」「就这一次」等限定词；`is_temporary=true`；必须注明临时范围 | 用户说「这次把字体调大就行，下次不用」|
| **长期偏好** | 经多会话巩固、用户未撤销且置信度持续偏高的持久偏好 | 跨≥2 个会话出现；未被后续行为否定；`scope` 为 `global` 或 `topic` | 用户在所有会话中均偏好暗色主题 |
| **偏好更新** | 用户对已存在偏好的 key 给出新的 value，或意图变更已有偏好 | 与历史偏好存在同一 `preference_key` 不同 `preference_value`；标注人必须关联旧偏好 ID | 用户曾设置排序为「按名称」，后改为「按修改日期」|
| **偏好撤销** | 用户明确或隐式地要求取消某条已有偏好 | 含「不用了」「取消」「还原默认」等表达；或长期偏好被行为否定（≥3 次违背） | 用户说「不用再帮我自动保存了」|
| **不应形成记忆** | 该 Turn 的内容不应被抽取为任何偏好或知识条目 | 包含以下任一项：(a) 纯闲聊/问候；(b) Tool 执行失败的内容；(c) 命中敏感过滤的内容；(d) 用户明确要求不记录的内容；(e) 临时且无复用价值的一次性指令 | 用户说「帮我查一下现在几点了」（一次性查询，Tool Result 为实时时间） |

---

## 四、Gold Label 与复核规则

### 4.1 Gold Label 确定流程

1. **标注人 A 初标**：阅读会话全文（含所有 Turn、Tool Result、用户消息和系统回复），按本规范七类开发集分类确定归属，填写对应标注字段，记录初标时间。
2. **标注人 B 复核**：独立阅读同份会话，逐条比对标注人 A 的标签。
   - 同意：记录「同意」、复核时间和复核人。
   - 不同意：记录「不同意」、修改建议、理由和修改后的标签候选。
3. **争议裁决**：标注人 A、B 无法达成一致时，提交 Reviewer（D/E 轨道 Reviewer）裁决。裁决记录必须包含：争议点、裁决理由、最终标签、裁决人和裁决时间。
4. **Gold Label 锁定**：经复核一致或裁决确定后的标签即为 Gold Label，录入标注库，锁定后不得单方面修改。如需修改，必须重新走复核流程并记录变更原因。

### 4.2 LLM 使用边界

- **允许**：使用 LLM 对自然语言 Turn 内容进行辅助分析，生成候选的 `preference_key`、`preference_value` 或 `knowledge_summary` 表达。
- **禁止**：LLM 独立决定最终 Gold Label；LLM 替代标注人 A 或标注人 B 的初标/复核角色；LLM 在无人干预的情况下对标注结果进行「批量修正」。
- **所有 LLM 生成的候选输出**必须在标注记录中标记为 `memory_status=candidate`（候选），并记录模型名称、调用时间、Prompt 摘要，供复核人审查。

### 4.3 复核证据要求

每次复核必须保留以下证据（与 `.local-agent-workflow/rules/runtime-validation.md` 证据保留精神一致）：

- 当前 Git commit SHA
- 工作区是否存在未提交修改（`git status --short`）
- 复核人标识
- 复核时间（ISO 8601）
- 复核结论（同意 / 不同意）
- 不同意的具体条目编号和理由
- 争议裁决记录（如适用）

---

## 五、安全边界与敏感标注

### 5.1 敏感内容类型与识别要点

标注人在标注过程中如发现任一 Turn 内容包含以下类型，必须记录并标记为敏感，不得将对应内容写入任何标注字段的文本值（仅可写入脱敏后的概要或仅用 ID 引用）。

| 编号 | 敏感类型 | 识别要点 | 标注处理 |
|------|---------|---------|---------|
| S-01 | API Key | 特征前缀（`sk-`、`api-` 等）、高熵字符串、常见服务商 Key 模式 | 标记 `sensitivity=critical`；标注字段填 `[REDACTED_API_KEY]`；强制不形成记忆 |
| S-02 | Token | JWT 特征（三段 Base64，`eyJ` 开头）、Bearer Token、OAuth Token | 标记 `sensitivity=critical`；标注字段填 `[REDACTED_TOKEN]`；强制不形成记忆 |
| S-03 | 密码 | 明文密码字符串、含「密码」「password」上下文的赋值操作 | 标记 `sensitivity=critical`；标注字段填 `[REDACTED_PASSWORD]`；强制不形成记忆 |
| S-04 | 私钥 | PEM 头尾标记（`-----BEGIN` / `-----END`）、`.pem` `.key` 文件内容 | 标记 `sensitivity=critical`；标注字段填 `[REDACTED_PRIVATE_KEY]`；强制不形成记忆 |
| S-05 | 身份证号 | 18 位数字组合（含末位 X）、地址/生日等关联上下文 | 标记 `sensitivity=high`；标注字段填 `[REDACTED_ID_NUMBER]`；不写入记忆 |
| S-06 | 手机号 | 11 位手机号码模式、国家代码前缀、通讯录关联上下文 | 标记 `sensitivity=high`；标注字段填 `[REDACTED_PHONE]`；不写入记忆 |
| S-07 | 敏感路径 | 绝对路径含 `/etc/shadow`、`~/.ssh/`、系统关键目录、用户私密目录 | 标记 `sensitivity=high`；标注字段填 `[REDACTED_PATH]`；路径原文不写入记忆 |
| S-08 | 跨用户数据 | 数据内容不属于当前 `user_id`（如包含另一用户的聊天记录、偏好、操作日志） | 标记 `sensitivity=critical`；标注字段仅记录 `sensitivity=critical` 与 `isolation_violation=true`；正文不写入、不进入可检索索引 |
| S-09 | 硬删除正文 | 经 `ForgetPlan` 执行硬删除的条目内容 | 已完成硬删除的正文不得在 SQLite、Vector、FTS5、日志、导出文件和备份中留存明文可检索残留。标注记录仅保留 `forget_plan_id` 和遗忘执行时间戳，不保留正文 |

### 5.2 敏感过滤标注字段

对于含敏感内容的 Turn，标注人应填写以下字段：

| 字段 | 含义 | 取值说明 |
|------|------|---------|
| `sensitivity_level` | 敏感度等级 | `none` / `low` / `medium` / `high` / `critical`（同 Schema 枚举 2.9） |
| `sensitive_type` | 敏感类型编号 | 如 `S-01`、`S-03`（如含多种则记录多项） |
| `should_ignore` | 是否应忽略该 Turn | `true` / `false`。含 S-01 至 S-04 或 S-08 的 Turn 必须标记 `true` |
| `redacted_summary` | 脱敏后摘要 | 不包含任何敏感原文的简要描述，如「用户粘贴了一段 API Key」 |

### 5.3 跨用户隔离

- 开发集、回归集和封存集的每个会话必须有明确的 `user_id` 绑定。`user_id` 是用户级数据隔离的硬约束，所有核心业务对象（Preference、Knowledge、Conflict、ForgetPlan）和端到端会话均须具备 `user_id` 字段。
- `user_id` 的取值**禁止由模型/LLM 生成**，必须来自宿主侧业务事件或外部输入。
- 区分 `user_id`（数据归属与隔离键）与 `actor_id`（事件实际发起者）：同一 `user_id` 下可能有多个 `actor_id`（如系统代用户执行操作），但数据归属始终以 `user_id` 为准。
- 一个会话内不得出现两个不同的 `user_id`（跨用户数据属构造错误，需标记 `isolation_violation=true` 且 `sensitivity=critical`）。
- **评测要求**：
  - **正向隔离测试（同用户）**：同 `user_id` 的用户应可召回自己的全部偏好、知识条目；可更新或删除自己名下的记忆。案例见 §六 正例 8。
  - **负向隔离测试（跨用户）**：不同 `user_id` 的用户**必须无法**读取、更新或删除其他用户的偏好、知识条目或遗忘计划。任何跨用户操作尝试必须被标记为 `isolation_violation=true`、`sensitivity=critical`，且操作方不得获取任何实际数据。案例见 §六 反例 6。
- 隔离验证由 E 轨道 Runtime Test 覆盖（对应 REQ-05、REQ-07）。

---

## 六、案例库

以下案例全部使用虚构占位内容，不包含任何真实用户数据、密钥或个人信息。

### 6.1 正例（Positive Examples，≥5）

#### 正例 1：明确偏好——以后使用中文

**场景**：用户 `user_demo` 在与官方 AI 助手的对话中明确表达了语言偏好。

**会话片段**（虚构）：
```
Turn 01 | user_demo: 「以后都使用中文回复我。」
Turn 01 | agent_response: 「好的，我会从现在开始使用中文与您交流。」

Turn 05 | user_demo: 「帮我整理一下上周的会议纪要。」
Turn 05 | agent_response: 「好的，以下是您上周的会议纪要整理……」（使用中文回复）
```

**标注**：
- 分类：明确偏好
- `user_id`: `"user_demo_01"`
- `preference_key`: `language_pref`
- `preference_value`: `"zh-CN"`
- `expression_type`: `explicit`
- `scope`: `global`
- `confidence_score`: `0.95`
- `is_temporary`: `false`
- `should_persist`: `true`
- `memory_status`: `active`
- `evidence_event_ids`: `["evt_20260730_turn01_fs", "evt_20260730_turn05_fs"]`
- `source_turn_ids`: `["turn_01"]`
- `annotator`: `"annotator_demo_a"`
- `annotated_at`: `"2026-07-30T10:00:00+08:00"`

**Gold Label 判定依据**：
- 用户 Turn 01 直接声明「以后都……」，表达方式不含歧义，`expression_type=explicit`。
- Turn 05 中助手使用中文回复，表明偏好已生效且用户未否定。

---

#### 正例 2：不同场景偏好可以共存

**场景**：用户 `user_demo` 在不同场景下给出不同的排序偏好，两条偏好可共存。

**会话片段**（虚构）：
```
Turn 01 | user_demo: 「在文件管理器里，我偏好按修改日期倒序排列。」

Turn 03 | user_demo: 「在邮件客户端里，我偏好按发件人排序。」
```

**标注**：
- `user_id`: `"user_demo_01"`
- 偏好评注 1（Turn 01）：
  - `preference_key`: `file_search_sort_order`
  - `preference_value`: `"by_modified_desc"`
  - `scope`: `tool`（限定于文件管理 Tool）
- 偏好评注 2（Turn 03）：
  - `preference_key`: `mail_sort_order`
  - `preference_value`: `"by_sender"`
  - `scope`: `tool`（限定于邮件 Tool）

**Gold Label 判定依据**：
- 两条偏好作用于不同 Tool/Domain（文件管理 vs. 邮件），key 不同，scope 不同，不存在冲突。`Conflict` 对象无需生成。

---

#### 正例 3：Tool 失败不得形成成功知识

**场景**：用户 `user_demo_01` 请求 Tool 执行文件搜索，Tool 返回失败。

**会话片段**（虚构）：
```
Turn 02 | user_demo: 「帮我找一下昨天的设计文档 v3。」
Turn 02 | tool_result: execution_status=failure, tool_name=file_search, error_message="索引未就绪，搜索失败"
```

**标注**：
- Tool Result 标注：
  - `tool_call_id`: `"tool_file_search_v2_002"`
  - `execution_status`: `failure`
  - `should_form_memory`: `false`
  - `failure_tag`: `tool_failure`
- 不应形成任何 Knowledge 或 Preference 条目。

**Gold Label 判定依据**：
- Tool 执行失败，结果中不包含可采信的知识信息。不得将「用户搜索过设计文档 v3」或「设计文档 v3 存在」等未经验证的推论标注为 Knowledge。

---

#### 正例 4：偏好更新

**场景**：用户 `user_demo` 在早期会话中设置了排序偏好，但在后期会话中修改了该偏好。

**会话 A 片段**（虚构）：
```
Turn 01 | user_demo: 「以后文件列表默认按名称排序。」
```

**会话 B 片段**（虚构）：
```
Turn 07 | user_demo: 「改一下，文件列表还是按修改日期排吧。」
```

**标注**：
- `user_id`: `"user_demo_01"`
- 旧偏好（会话 A）：
  - `preference_key`: `file_list_sort_order`
  - `preference_value`: `"by_name"`
  - `memory_status`: `superseded`（被后续更新覆盖）
- 新偏好（会话 B）：
  - 分类：偏好更新
  - `preference_key`: `file_list_sort_order`
  - `preference_value`: `"by_modified_desc"`
  - `memory_status`: `active`
  - 关联旧偏好 ID：`"pref_001"`

**Gold Label 判定依据**：
- 同一 `preference_key` 出现新 value，且用户明确使用「改一下」表达变更意图。旧偏好标记为 `memory_status=superseded`，不删除但失效。

---

#### 正例 5：精准遗忘——先预览再确认

**场景**：用户 `user_demo` 要求遗忘某次会话中的记忆，系统先展示预览再执行。

**会话片段**（虚构）：
```
Turn 11 | user_demo: 「忘掉我上周二关于项目排期的所有讨论。」

Turn 11 | agent_response: 「以下是与『上周二项目排期』相关的记忆条目预览：
  1. [kn_003] 项目排期截止日为 2026-08-15
  2. [kn_004] 前端模块由张三负责
  3. [pref_005] 排期讨论时偏好使用甘特图视图
  共 3 条。确认遗忘后将无法恢复，是否继续？」

Turn 12 | user_demo: 「确认，全部忘掉。」

Turn 12 | agent_response: 「已遗忘 3 条相关记忆。」
```

**标注**：
- `user_id`: `"user_demo_01"`
- 遗忘计划标注：
  - `forget_request_turn_id`: `"turn_11"`
  - `target_selector`: `"上周二关于项目排期的所有讨论"`
  - `forget_mode`: `session`（以时间范围限定，目标 session 内全部相关条目）
  - `resolved_target_ids`: `["kn_003", "kn_004", "pref_005"]`
  - `affected_count`: `3`
  - `preview_provided`: `true`
  - `user_confirmed`: `true`
  - `requires_confirmation`: `true`
  - `execution_verified`: `true`
  - `hard_delete`: `true`

**Gold Label 判定依据**：
- 遗忘流程完整：请求（Turn 11）→ 预览（Turn 11）→ 用户确认（Turn 12）→ 执行（Turn 12）。
- 预览中准确列出了受影响条目，用户在知晓后果后确认执行。

---

#### 正例 6：隐式偏好——通过反复行为推断

**场景**：用户 `user_demo` 在多个会话中持续选择同一种操作，但从未明确声明偏好。

**会话片段**（虚构）：
```
会话 A, Turn 04 | agent_response: 「查询到 15 个结果，默认按相关性排序。是否需要调整？」
会话 A, Turn 05 | user_demo: 「按日期倒序。」

会话 B, Turn 02 | agent_response: 「搜索结果已返回。要按什么顺序看？」
会话 B, Turn 03 | user_demo: 「最新的在前面。」

会话 C, Turn 06 | agent_response: 「排序方式？」
会话 C, Turn 07 | user_demo: 「从最近到最早。」
```

**标注**：
- 分类：隐式偏好
- `user_id`: `"user_demo_01"`
- `preference_key`: `search_sort_order`
- `preference_value`: `"by_date_desc"`
- `expression_type`: `implicit`
- `confidence_score`: `0.75`（跨 3 个会话、3 次一致行为，但非显式声明）
- `is_temporary`: `false`
- `should_persist`: `true`
- `memory_status`: `active`
- `evidence_event_ids`: `["evt_turn05_sessA", "evt_turn03_sessB", "evt_turn07_sessC"]`
- `source_turn_ids`: `["turn_05_sessA", "turn_03_sessB", "turn_07_sessC"]`

**Gold Label 判定依据**：
- ≥2 个 Turn 且跨 ≥1 个会话，行为模式一致。置信度 0.75 反映「未显式声明但有充分行为证据」。

---

#### 正例 7：Tool 调用成功但不应形成长期记忆（一次性查询）

**场景**：用户 `user_demo_01` 请求查询当前时间，Tool 返回成功，但结果属瞬态上下文，不应形成任何长期记忆。

**会话片段**（虚构）：
```
Turn 03 | user_demo: 「现在几点了？」
Turn 03 | tool_result: execution_status=success, tool_name=system_clock, result="当前时间：2026-07-30 14:35:22 CST"
Turn 03 | agent_response: 「现在是 2026 年 7 月 30 日下午 2 点 35 分。」
Turn 04 | user_demo: 「好的，谢谢。」
```

**标注**：
- `user_id`: `"user_demo_01"`
- Tool Result 标注：
  - `tool_call_id`: `"tool_system_clock_003"`
  - `tool_name`: `"system_clock"`
  - `execution_status`: `success`
  - `should_form_memory`: `false`
  - `memory_type_if_formed`: `N/A`
  - `failure_tag`: `transient_context`
- 不应形成任何 Knowledge 或 Preference 条目。

**Gold Label 判定依据**：
- Tool 虽然执行成功（`execution_status=success`），但返回结果是实时时间，属于一次性查询、无复用价值的瞬态上下文。将「用户查询过当前时间」标注为 Knowledge 条目会导致长期记忆中积累无意义的一次性交互记录，且可能被错误检索为与时间相关的事实知识。
- 此类边界案例的关键判据：**结果是否具有跨会话复用价值**；若不具有，`should_form_memory=false`，`failure_tag=transient_context`。

---

#### 正例 8：跨用户正向隔离——同用户可召回自己的记忆

**场景**：用户 `user_demo_01` 在跨会话检索中成功召回自己在历史会话中建立的偏好和知识条目。验证同 `user_id` 下的记忆可见性。

**会话 A 片段**（虚构）：
```
Turn 01 | user_demo_01: 「以后所有代码注释都用英文写。」
Turn 01 | agent_response: 「好的，已记住：代码注释使用英文。」
```

**会话 B 片段**（虚构，数天后）：
```
Turn 01 | user_demo_01: 「帮我写个函数，功能是读取配置文件。」
Turn 03 | agent_response（基于 memory_service 返回的偏好）: 「根据您的偏好，注释将使用英文。以下是代码……（英文注释）」
```

**标注**：
- 会话 A 偏好标注：
  - `user_id`: `"user_demo_01"`
  - `preference_key`: `code_comment_language`
  - `preference_value`: `"en"`
  - `expression_type`: `explicit`
  - `confidence_score`: `0.95`
  - `memory_status`: `active`
- 会话 B 检索验证：
  - 检索请求 `user_id`: `"user_demo_01"`，查询偏好相关记忆（`preference_scope=tool` 或按 `preference_key` 过滤）
  - 预期：返回 `code_comment_language=en`（同用户召回成功）
  - 实际 agent_response 中的英文注释已证实偏好生效
- `isolation_violation`: `false`

**Gold Label 判定依据**：
- 同 `user_id` 下的偏好/知识条目应在跨会话检索中可见，且可正确参与记忆融合与响应生成。此案例验证正向隔离正确性：用户可以看到并受益于自己的历史偏好。

---

### 6.2 反例（Negative Examples，≥5）

#### 反例 1：临时三句话不形成长期偏好

**场景**：用户 `user_demo` 在一次短暂的问答中给出了临时的格式要求，但明确限定仅本次有效。

**会话片段**（虚构）：
```
Turn 08 | user_demo: 「这次汇报的摘要，你帮我用英文写，因为客户是外籍。」
Turn 08 | agent_response: 「好的，以下是英文摘要……」
Turn 09 | user_demo: 「谢谢，后面还是用中文就行。」
```

**标注**：
- 不应形成长期偏好 `language_pref=en`。
- 分类：不应形成记忆（`failure_tag=transient_context`，临时一次性指令）
- 理由：Turn 08 含「这次」「因为客户」表明是临时需求，Turn 09 明确回归中文。两个 Turn 联合判定为不应形成长期 `language_pref=en` 偏好。

**Gold Label 判定依据**：
- Turn 08 出现了可能被误标注为 `language_pref=en` 的文本，但 Turn 09 立刻撤销了该临时要求。使用 LLM 仅看 Turn 08 可能会错误标注为偏好更新，人工复核时结合 Turn 09 上下文应判定为不应形成记忆。

---

#### 反例 2：Tool 失败形成成功知识的错误标注

**场景**：用户 `user_demo` 请求 Tool 检查系统更新，Tool 返回失败。

**会话片段**（虚构）：
```
Turn 05 | user_demo: 「检查系统是否有可用的安全更新。」
Turn 05 | tool_result: execution_status=failure, tool_name=system_update_check, error_message="网络不可达：无法连接更新服务器"
```

**错误标注示例（反例）**：
- 错误地标注了：`Knowledge` 条目 `"系统当前无可用安全更新"`（Tool 未返回成功结果，该结论不存在依据）。
- 正确标注：`should_form_memory=false`，`failure_tag=tool_failure`。不生成任何 Knowledge 条目。

**Gold Label 判定依据**：
- Tool 失败时不得从错误信息或默认假设中推断任何知识。`"系统当前无可用安全更新"` 是从缺失结果中做出的推断，在业务上严重错误。

---

#### 反例 3：闲聊不形成偏好

**场景**：用户 `user_demo` 与助手进行了纯社交性的寒暄。

**会话片段**（虚构）：
```
Turn 01 | user_demo: 「早上好！」
Turn 01 | agent_response: 「早上好！今天有什么可以帮您的？」
Turn 02 | user_demo: 「天气真不错。」
Turn 02 | agent_response: 「确实，适合出门走走。」
```

**错误标注示例（反例）**：
- 错误地标注了：偏好 `greeting_style=casual` 或知识 `"用户喜欢谈论天气"`（内容为纯社交寒暄，不具有业务/偏好意义）。
- 正确标注：分类为「不应形成记忆」。理由：内容为纯问候/闲聊，无偏好表达、无可抽取知识、无 Tool 调用。

---

#### 反例 4：偏好撤销被忽略

**场景**：用户 `user_demo` 之前设置了自动保存偏好，后来明确撤销。

**会话 A 片段**（虚构）：
```
Turn 03 | user_demo: 「以后编辑文档每五分钟自动保存一次。」
```

**会话 C 片段**（虚构）：
```
Turn 10 | user_demo: 「不用再自动保存了，我自己手动存。」
```

**错误标注示例（反例）**：
- 错误地仅保留了旧偏好 `auto_save_interval=5min` 且 `memory_status=active`，忽略了 Turn 10 的撤销。
- 正确标注：Turn 10 应生成偏好撤销标注，旧偏好 `auto_save_interval` 标记 `memory_status=superseded`，并记录撤销来源 Turn ID。

---

#### 反例 5：安全敏感内容被标注为知识

**场景**：用户 `user_demo` 在对话中粘贴了一段 Token。

**会话片段**（虚构）：
```
Turn 07 | user_demo: 「帮我用这个 Token 调一下 API：eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJkZW1vIn0.abc123」
```

**错误标注示例（反例）**：
- 错误地标注了：Knowledge 条目 `"用户使用 Token eyJhbGciOi..."` 或 Preference 条目 `"api_token=eyJhbGciOi..."`（敏感内容被写入了标注字段，且未标记 `sensitivity=critical`）。
- 正确标注：`sensitivity_level=critical`，`sensitive_type=S-02`，`should_ignore=true`，`redacted_summary="用户粘贴了一段 Bearer Token 请求 API 调用"`。不形成任何 Knowledge 或 Preference 条目。

---

#### 反例 6：跨用户负向隔离——其他用户不可读取、更新或删除

**场景**：用户 `user_demo_02` 尝试读取、更新和删除 `user_demo_01` 的偏好和知识条目，系统必须全部拒绝并标记隔离违规。

**假设前提**：
- `user_demo_01` 在历史会话中建立了以下记忆条目：
  - 偏好：`preference_key=language_pref`, `preference_value=zh-CN`, `user_id=user_demo_01`
  - 知识：`knowledge_summary="用户每月底整理一次文件目录"`, `user_id=user_demo_01`

**尝试 1：跨用户读取**
```
Turn 01 | user_demo_02: 「我的语言偏好是什么？」
```
- **错误行为**（反例）：系统返回 `user_demo_01` 的偏好 `language_pref=zh-CN`，造成跨用户数据泄露。
- **正确行为**：系统仅为 `user_demo_02` 检索 `user_id=user_demo_02` 的记忆，不返回 `user_demo_01` 的条目。如 `user_demo_02` 无对应记忆，返回空或 `not_found`。

**尝试 2：跨用户更新**
```
Turn 02 | user_demo_02: 「把语言偏好改成英文。」
```
- **错误行为**（反例）：系统更新了 `user_id=user_demo_01` 下 `language_pref` 的值为 `en`。
- **正确行为**：系统仅允许更新 `user_id=user_demo_02` 下的条目。若 `user_demo_02` 下无 `language_pref` 条目，操作不应影响 `user_demo_01` 的数据；可新建 `user_demo_02` 自己的偏好，但不覆盖他人。

**尝试 3：跨用户遗忘**
```
Turn 03 | user_demo_02: 「忘掉所有文件整理相关的记忆。」
```
- **错误行为**（反例）：系统在 `resolved_target_ids` 中包含了 `user_id=user_demo_01` 的知识条目 `"kn_file_organize_001"`，并执行了遗忘。
- **正确行为**：系统仅为 `user_demo_02` 解析 `target_selector`，`resolved_target_ids` 中**不得**包含任何 `user_id != user_demo_02` 的条目。

**标注**：
- 所有跨用户操作尝试：
  - `isolation_violation`: `true`
  - `sensitivity`: `critical`（对应 S-08 跨用户数据）
  - `should_ignore`: `true`
  - `redacted_summary`: `"user_B 尝试读取/更新/删除 user_A 的记忆，已被隔离策略拒绝"`

**Gold Label 判定依据**：
- `user_id` 是用户级数据隔离的硬约束。任何操作（读取、更新、删除、遗忘）必须以当前请求的 `user_id` 为过滤键，**绝对不得**跨越 `user_id` 边界。
- 此案例验证负向隔离正确性：跨用户操作必须被拒绝，且不会泄漏、篡改或删除其他用户的数据。隔离违规操作必须标记 `isolation_violation=true`、`sensitivity=critical`。

---

### 6.3 歧义/边界案例（Ambiguous / Boundary Cases，≥3）

#### 边界案例 1：模糊的临时性声明

**场景**：用户 `user_demo` 的表述同时含有「临时」和「长期」信号。

**会话片段**（虚构）：
```
Turn 04 | user_demo: 「平时我习惯用深色主题，但是今天演示用浅色的吧，演示完再说。」
```

**标注讨论**：
- 可能解读 A：`theme_pref=dark` 为长期偏好（`scope=global`，`is_temporary=false`），Turn 04 仅是一个临时例外，不应覆盖长期偏好。
- 可能解读 B：`theme_pref=light` 是当前有效偏好（`is_temporary=true`，范围=仅本次演示），且 Turn 04 末尾「演示完再说」暗示之后可能恢复。
- **建议处理**：标注为边界案例，记录两种解读。标注人 A/B 独立判定后提交 Reviewer 裁决。在裁决前标记两条偏好候选（`memory_status=candidate`），不锁定为 Gold Label。

**裁决要点**：
- 「平时我习惯用……」属于隐式偏好的历史证据陈述，应标注为 `theme_pref=dark` 偏好（`confidence_score` 0.7，因为本 Turn 不是偏好设置行为，而是偏好自述）。
- Turn 04 中的「演示用浅色的」属临时要求，`is_temporary=true`，不覆盖 `theme_pref=dark`。

**最终标签**：
- 长期偏好：`preference_key=theme_pref`, `preference_value=dark`, `expression_type=implicit`, `confidence_score=0.7`, `is_temporary=false`, `memory_status=active`
- 临时要求：标记为「不应形成记忆」(`failure_tag=transient_context`)，不影响长期偏好

---

#### 边界案例 2：Tool 部分成功的结果是否应形成记忆

**场景**：用户 `user_demo` 请求批量文件转换，Tool 返回部分成功。

**会话片段**（虚构）：
```
Turn 06 | user_demo: 「把这 5 个 docx 文件全部转成 pdf。」
Turn 06 | tool_result: execution_status=partial, tool_name=file_converter, converted_count=4, failed_count=1, failed_file="机密报告.docx", fail_reason="文件受密码保护，无法读取"
```

**标注讨论**：
- 可能解读 A：Tool 有 1 个文件失败，应视为整体失败，`should_form_memory=false`（失败容错策略偏保守）。
- 可能解读 B：4 个文件成功转换，应形成知识 `"文件转换功能可用"`，但不应形成关于失败文件内容的任何知识。
- **建议处理**：标注为边界案例，`should_form_memory=true`，但仅针对成功部分形成知识（如 `"用户使用过文件转换功能"`），不形成关于失败文件的知识。`failure_tag` 标记 `partial_success`（需扩展枚举）。

**裁决要点**：
- Tool 执行结果为 `partial`，不应等同于完全失败。可形成关于 Tool 使用的知识（`knowledge_summary="用户批量转换了 docx 文件为 pdf"`），但不得记录失败文件的文件名或内容。
- 失败文件的文件名「机密报告.docx」虽然在 Tool Result 中出现，但属于可能的敏感信息（文件名含义），标注时应脱敏为 `[REDACTED_FILENAME]`。

---

#### 边界案例 3：跨越会话的偏好行为不一致

**场景**：用户 `user_demo` 在会话 A 中偏好详细回复，在会话 B 中偏好简洁回复。

**会话 A 片段**（虚构）：
```
Turn 02 | user_demo: 「给我详细解释一下这个功能。」
Turn 03 | user_demo: 「再展开说说，越多细节越好。」
```

**会话 B 片段**（虚构）：
```
Turn 01 | user_demo: 「简短回答就行，别啰嗦。」
Turn 04 | user_demo: 「说重点。」
```

**标注讨论**：
- 两个会话中的 `response_style` 偏好冲突：会话 A → `detailed`，会话 B → `concise`。
- 可能解读 A：以最新偏好为准（`preference_value=concise`），旧偏好标记失效。
- 可能解读 B：用户在不同场景/话题下有不同的回复风格偏好，两条偏好可共存，但 `scope` 需区分（如 `scope=topic`，分别关联对应话题）。
- **建议处理**：标注为边界案例。不急于标记为冲突或覆盖，先检查两个会话的话题是否有差异。
  - 若会话 A 话题为「技术学习」，会话 B 话题为「快速查询」，则两条偏好可共存（`scope=topic`，分别关联不同话题）。
  - 若两个会话话题相同/无法区分，则判定为偏好更新（以最新值为准）。
- 同时生成 `Conflict` 条目记录该歧义，`resolution_status=deferred`，待更多证据后裁决。

**裁决要点**：
- 本案例的核心歧义在于「是否同一场景」。同一用户在不同需求场景下需要不同回复风格是合理的，不应强制二选一。
- 裁决方法：标注人分析两个会话的 `primary_category`（话题分类）。若话题不同，两条偏好可共存；若话题相同，按时间最新覆盖。

---

#### 边界案例 4（补充）：隐式撤销——长期不使用的偏好是否自动失效

**场景**：用户 `user_demo` 曾在 30 天前设置了某偏好，此后 30 天未再提及，且行为中未体现该偏好。

**标注讨论**：
- 可能解读 A：偏好未撤销（用户未说「不用了」），`memory_status=active`。
- 可能解读 B：30 天无证据可视为隐式撤销或衰减到期，`memory_status=expired`。
- **建议处理**：标注为边界案例。当前 v0.1 不冻结衰减阈值（衰减策略待 A/E 确认），标注人应在标注记录中注明「隐式撤销待衰减策略 ADR 确认」，当前标记 `memory_status=active` 并增加备注「无近期证据，待衰减模型判定」。

---

## 七、数据集三类用途差异

本规范承继 `datasets/README.md` 的三类数据划分：

| 维度 | 开发集 | 回归集 | 封存集 |
|------|--------|--------|--------|
| **主要用途** | 日常开发、单元测试、标注规则验证、分类器迭代 | CI 流水线自动回归、功能稳定性验证 | 正式评测、Gate 评审、性能基准 |
| **可修改性** | 可调整：新增/修正样本、更新标注、调整分类 | 相对稳定：修正标注错误需走变更记录，不得大幅增删样本 | 锁定：SHA-256 哈希锁定后**禁止任何修改**（含标注修正） |
| **标注质量要求** | 标注可迭代，允许部分边界案例暂标为 `memory_status=candidate` | 所有标注必须为 Gold Label（经复核一致） | 所有标注必须为 Gold Label + 封存审计记录 |
| **覆盖范围** | 覆盖六类数据全部七类开发集分类，优先覆盖正例和歧义案例 | 覆盖六类数据的关键正例与反例，确保回归覆盖核心路径 | 覆盖六类数据全部七类开发集分类，包含评测指标体系所需的全部维度 |
| **数据规模要求** | 不设下限，随开发迭代增长 | ≥ 100 条标注样本 | 待评测指标体系 ADR 确认后确定（当前未定） |
| **版本管理** | 跟随代码分支 | 跟随代码分支，标签化版本 | Git LFS 或独立存储，SHA-256 清单纳入仓库审计 |
| **当前状态** | **尚未建立**（本规范即为建立标准的第一步） | **尚未建立** | **尚未建立；封存测试集尚未制作、尚未锁定哈希；不得声称已封存** |

**当前如实记录**：
- 开发集：标注规范（本文档）已建立 DRAFT v0.1，但实际标注样本尚未生产。
- 回归集：尚未建立，计划在开发集积累 ≥ 200 条 Gold Label 样本后抽取子集建立回归集。
- 封存集：尚未建立，封存测试集制作与 SHA-256 哈希锁定属后续独立任务（对应 REQ-07），不在本任务范围。

---

## 八、未确认能力与人工决策待办

以下事项需在后续阶段由对应轨道确认，本 v0.1 DRAFT 如实记录当前已知的未确认项：

| 编号 | 事项 | 关联 REQ | 责任轨道 | 计划窗口 |
|------|------|---------|---------|---------|
| HD-ANNO-01 | 导入「数据查找选型与质量审计手册」至 `docs/baseline/`，用于复核并修订本规范中的标注字段与分类 | REQ-07 | 团队/E | D3 Gate 前 |
| HD-ANNO-02 | C 轨道在麒麟 VM 取证官方 AI 助手 Tool/Turn/Context 事件结构，回填 Tool Result 标注字段的 UNVERIFIED 状态 | REQ-01 | C | L2 取证窗口 |
| HD-ANNO-03 | E 确认偏好隐式撤销的衰减阈值（≥N 天无证据是否视为失效），并回填边界案例 4 的裁决规则 | REQ-02 | E | D3 Gate 前 |
| HD-ANNO-04 | A/E 确认置信度量化模型（0.0–1.0 的计算方法），回填本规范中标注人「置信度」字段的取值标准 | REQ-02 | A·E | D3 Gate 前 |
| HD-ANNO-05 | E 确认 `sensitivity` 五级分级的明确判定标准和分级规则，回填本规范安全边界章节 | REQ-05 | E | D3 Gate 前 |
| HD-ANNO-06 | 制作首批开发集标注样本（≥50 条），验证本规范的标注字段完整性和分类覆盖率 | REQ-07 | E | D3 Gate 前 |
| HD-ANNO-07 | 确认「数据查找选型与质量审计手册」中对标注流程的证据保留格式要求，如与本规范不一致则以手册为准 | REQ-07 | 团队/E | D3 Gate 前 |
| HD-ANNO-08 | 导入「架构设计审查报告（Copilot 独立审查报告）」至 `docs/baseline/`，用报告建议复核本规范全部字段与标注规则，记录差异并决策是否追加修订（对应 HD-SCHEMA-11） | REQ-01–07 | E | D3 Gate 前 |
| HD-ANNO-09 | E 确认 `expression_type` 最终术语选择（`inferred` v.s. `candidate`），统一本规范与业务 Schema（对应 HD-SCHEMA-14） | REQ-02 | E | D3 Gate 前 |

---

## 九、变更记录

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|---------|------|
| v0.1 | 2026-07-30 | DRAFT 初稿：建立六类评测数据标注字段、七类开发集分类、Gold Label 人工复核规则、安全边界（九类敏感类型）、正例 6 条、反例 5 条、歧义/边界案例 4 条、数据集三类用途差异与当前未封存如实记录。基于 schema v0.1、需求矩阵 v0.1 和 datasets/README.md 事实编写。 | E 轨道 |
| v0.1（修订） | 2026-07-30 | 标注规范与 Schema v0.1 修订对齐：引入 `user_id`/`actor_id` 用户隔离；`confidence` 更名为 `confidence_score`；`evidence_turn_ids` 更名为 `evidence_event_ids`，增加可选 `source_turn_ids`；偏好增加 `memory_status`/`should_persist`，候选判定改用 `memory_status=candidate`；知识增加 `knowledge_type` 枚举 2.5 六值；精准遗忘 `forget_target_description`→`target_selector`、`target_ids`→`resolved_target_ids`，新增 `affected_count`/`requires_confirmation`；开发集分类枚举引用号修正；§5.3 跨用户隔离增补 `user_id` 硬约束与正向/负向评测要点；案例库新增 Tool 成功不形成长期记忆反例（正例7）与跨用户正向（正例8）/负向（反例6）案例；更新 HD-ANNO-08/09 引用架构审查报告与 expression_type 术语终选。状态不变（v0.1 DRAFT），未声称测试集封存。 | E 轨道 |

---

## 十、冻结为 v1.0 的条件

以下条件**全部满足**后，本文档方可冻结为 v1.0 版本，成为数据标注与安全边界的正式基线：

1. 「数据查找选型与质量审计手册」已导入仓库，且本文档已与手册对齐
2. D3 Gate 经 D/E Reviewer 审查通过，且审查结论文档化
3. 八章「未确认能力与人工决策待办」中 HD-ANNO-01 至 HD-ANNO-09 均有明确决议
4. 开发集首批标注样本（≥50 条）已生产，覆盖六类数据和七类开发集分类，且至少 90% 已标记为 Gold Label
5. 安全边界中的敏感类型识别规则经过至少一轮安全测试验证
6. Tool Result 标注字段的 UNVERIFIED 状态经 C 轨道取证后回填为 VERIFIED 或 NOT_APPLICABLE
7. Evidence Reviewer 确认本文档中所有标注规则、字段和状态标注与当时实际证据等级一致

在满足以上条件之前，本文档不视为冻结基线，不得作为最终数据建设、评测或 Gate 评审判定的唯一依据。

---

> **本文档到此结束。后续版本将在 D3 Gate 审查后根据 D/E Reviewer 反馈、数据查找选型与质量审计手册导入、以及开发集首批样本标注实践反馈修订。**
