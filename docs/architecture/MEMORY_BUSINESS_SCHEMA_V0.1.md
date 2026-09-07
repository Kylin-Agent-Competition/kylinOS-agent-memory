# 记忆业务对象与字段命名初稿

- **版本**：v0.1
- **状态**：DRAFT
- **用途**：D1–D2 能力对照
- **冻结门槛**：D3 Gate 前不得视为冻结协议；须经 D/E Reviewer 审查，并待基线文档（赛题原文、总体架构 SOP、官方 SDK 与 OS Agent 能力边界）导入仓库、官方 AI 助手真实事件结构经麒麟 VM 取证后，方可冻结为 v1.0
- **依据来源**：
  - `README.md`（项目定位、技术路线、责任轨道 A–E、当前阶段与明确未完成项）
  - 各模块 `README.md`（`memory-service/`、`cpp-bridge/`、`memory-client/`、`os-agent-integration/`、`evaluation/`、`datasets/`）中的职责边界与当前状态
  - `docs/baseline/README.md` 第 02 项「总体架构、团队分工与标准开发 SOP v1.1」（当前状态：**待人工导入**；本稿 source_type 七值规范集合、event_type 层级区分与六档冲突优先级依据 SOP v1.1 规格回填，待 SOP 实体文件导入后复核）
  - `docs/project-management/REQUIREMENT_TRACEABILITY_MATRIX.md`（赛题要求与项目交付追踪矩阵 v0.1，REQ-01 至 REQ-07）
  - `datasets/ANNOTATION_GUIDELINE_V0.1.md`（数据标注与安全边界规范 v0.1 DRAFT，业务术语对齐与标注字段参照）
- **局限声明**：
  - 赛题原文、总体架构 SOP、官方 SDK 与 OS Agent 能力边界基线文档尚未导入仓库（`docs/baseline/README.md` 均标注「待人工导入」）
  - SOP v1.1 实体文件尚未导入仓库（`docs/baseline/README.md` 第 02 项）；本稿 source_type 七值规范集合、event_type 消息粒度层级区分与六档冲突优先级为按 SOP v1.1 任务规格回填，待 SOP 实体文件导入后须逐项复核
  - 架构设计审查报告（Copilot 独立审查报告）尚未导入仓库（`docs/baseline/README.md` 第 05 项，状态「待人工导入」），本稿无法核对其建议，待导入后须追加复核
  - 官方 AI 助手真实 Tool/Turn/Context 事件结构尚未取得麒麟 VM 证据（C 轨道 `os-agent-integration/` 当前仅建立目录和职责边界，尚无生产实现）
  - 官方偏好模型与宿主能力均未确认
  - 因此本稿中涉及以上来源的字段，验证状态均标注 `UNVERIFIED`、`PARTIAL` 或 `待对应轨道确认`，不得视为已确认契约
- **用户隔离约定**：
  - 本稿区分 `user_id` 与 `actor_id` 两个概念：**`user_id`** 表示数据归属与用户隔离键，是跨会话检索、偏好/知识/冲突/遗忘范围限定的业务硬约束；**`actor_id`** 表示事件的实际发起者（用户/系统/Tool），多个 actor 可能同属一个 user
  - 五个核心业务对象（MemorySourceEvent、Preference、Knowledge、Conflict、ForgetPlan）均须具备直接的 `user_id` 业务字段，用于用户级数据隔离
  - `user_id` 和 `actor_id` 的取值**禁止由模型/LLM 生成**，必须来自宿主侧业务事件或外部输入
- **权威层级与兼容性声明**（2026-09-03 增补）：本稿继续保持 v0.1 `DRAFT` 历史初稿状态。`KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md` 与 `D3_MEMORY_BUSINESS_CONTRACT_V1.md` 当前均为 `CANDIDATE_FOR_FREEZE`，其中 Canonical v1 承载本轮统一业务语义裁定候选与拟议权威关系。在非作者 D Reviewer 批准、对应 PR 合并并完成后续团队冻结治理之前，不建立“Canonical 候选自动覆盖本稿或 D3”的团队级权威关系；本稿继续作为 compatibility / 来源参照。Canonical v1 完成团队级冻结后，再按最终批准的权威层级处理跨文档冲突。本声明不改变本稿 DRAFT 状态与「冻结为 v1.0 的条件」。

---

## 一、命名规则

本稿统一采用以下命名规则，覆盖全部业务对象和字段。

| 规则 | 说明 | 示例 |
|------|------|------|
| 业务对象名 | PascalCase | `MemorySourceEvent`、`Preference`、`Knowledge`、`Conflict`、`ForgetPlan` |
| 字段名 | 英文 `snake_case` | `event_id`、`source_type`、`preference_scope` |
| 时间字段 | 以 `_at` 结尾 | `created_at`、`updated_at`、`captured_at`、`executed_at`、`occurred_at` |
| 标识字段 | 以 `_id` 结尾 | `event_id`、`session_id`、`preference_id` |
| 布尔字段 | 使用 `is_`、`has_`、`should_` 或 `requires_` 前缀 | `is_active`、`has_structured_payload`、`should_decay`、`requires_embedding` |
| 枚举型字段 | 以 `_type`、`_status`、`_mode`、`_scope` 或 `_strategy` 结尾 | `source_type`、`resolution_status`、`forget_mode` |
| 用户归属 | `user_id` 字段用于数据归属与用户隔离；`actor_id` 字段用于事件实际发起者 | `user_id`（归属）、`actor_id`（发起者） |

### 禁用的公共字段名

以下无明确业务含义的字段名不得用于任何业务对象：

- `data`
- `info`
- `value1` / `value2`
- `flag` / `flags`
- `extra` / `extra_data`（如需扩展字段，使用具体业务含义命名，如 `extracted_entities`、`tool_metadata`）

---

## 二、候选枚举

以下多组候选枚举定义业务含义层的取值范围，各轨道在各自技术实现层可扩展但不得偏离业务语义。

每项枚举的验证状态标记规则：
- **`VERIFIED`**：已有权威来源确认；
- **`UNVERIFIED`**：依赖官方 SDK/宿主能力，当前未取得证据；
- **`PARTIAL`**：部分候选值已确认，其他待定。

### 2.1 source_type（来源类型）

关联 REQ-01 多源数据。

**依据**：SOP v1.1 §6.1 规范集合（待人工导入），本稿按任务规格回填七值。`source_type` 定义事件来源大类，与消息粒度的 `event_type`（枚举 2.2）处于不同层级，二者不得混用。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `chat` | 用户对话消息（含单轮或多轮 Turn） | UNVERIFIED | 依赖 C 轨道确认宿主对话通道与消息结构 |
| `tool_result` | 官方 AI 助手 Tool 执行结果 | UNVERIFIED | 依赖 C 轨道在麒麟 VM 取证官方 Tool 调用格式 |
| `manual_config` | 用户手动配置（偏好设置、系统配置等显式配置） | UNVERIFIED | 依赖 C 轨道确认宿主配置获取通道 |
| `recollect` | 系统触发或用户发起的主动回忆/追溯 | UNVERIFIED | 依赖 C 轨道确认宿主回忆或回溯触发机制 |
| `file` | 文件操作事件（创建、修改、删除、搜索等） | UNVERIFIED | 依赖 C 轨道确认宿主文件事件通知能力 |
| `meeting` | 会议/协作场景事件 | UNVERIFIED | 依赖 C 轨道确认宿主会议/协作集成能力 |
| `voice` | 语音交互事件 | UNVERIFIED | 依赖 C 轨道确认宿主语音通道集成能力 |

**注意**：对话消息粒度 `user_message`、`agent_response`、`system_message` 不再作为 `source_type` 候选值；其语义由 `event_type`（枚举 2.2）承载并用于区分单条消息的具体角色。

### 2.2 event_type（事件消息粒度类型）

关联 REQ-01 多源数据。

**说明**：`event_type` 表达事件在消息/交互层面的粒度角色，与 `source_type`（来源大类）处于不同层级。一个 `source_type=chat` 的事件可包含多条 `event_type` 为 `user_message` 或 `agent_response` 的子记录。二者关系为：`source_type` 定义「数据从何而来」，`event_type` 定义「该数据在交互中的具体角色」。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `user_message` | 用户直接发出的消息 | UNVERIFIED | 依赖 C 轨道确认宿主消息通道与来源角色 |
| `agent_response` | 官方 AI 助手生成的回复 | UNVERIFIED | 依赖 C 轨道确认宿主回复结构 |
| `system_message` | 系统级消息（桌面状态通知、窗口焦点变更等） | UNVERIFIED | 依赖官方 SDK 确认宿主提供的系统消息能力 |

**验证状态说明**：`event_type` 候选值依据 SOP v1.1 规范回填。本稿与标注规范 (`ANNOTATION_GUIDELINE_V0.1.md`) 当前 `source_type` 术语存在跨文档差异，列为技术债（见 `TECHNICAL_DEBT_REGISTER.md`），由独立任务处理。

### 2.3 source_business_status（来源事件业务结果状态）

关联 REQ-01 多源数据。

**注意**：本枚举仅定义来源事件在业务层面的执行结果，不涉及 Memory Service 内部处理流水线状态。后者见枚举 2.4 `processing_status`，为技术候选，不视为已冻结业务枚举。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `raw` | 原始事件，尚未判定业务结果 | PARTIAL | 事件初始状态，业务含义层已确认 |
| `completed` | 事件执行完成（含成功和失败，具体通过 `execution_status` 进一步细分） | PARTIAL | 事件生命周期已结束 |
| `success` | 事件执行成功 | UNVERIFIED | 依赖 C 轨道确认宿主 Tool/操作状态语义 |
| `partial` | 事件部分成功（如批量操作中部分项成功） | UNVERIFIED | 依赖 C 轨道确认宿主批量操作返回结构 |
| `failed` | 事件执行失败 | UNVERIFIED | 依赖 C 轨道确认宿主错误码体系 |
| `cancelled` | 事件被用户或系统取消 | UNVERIFIED | 依赖 C 轨道确认宿主取消机制 |
| `timeout` | 事件执行超时 | UNVERIFIED | 依赖 C 轨道确认宿主超时阈值与通知 |
| `ignored` | 已忽略（经敏感过滤或规则过滤） | PARTIAL | 待 E 确认敏感过滤与忽略策略 |

### 2.4 processing_status（内部处理流水线状态）

关联 REQ-01、REQ-04。

**注意**：本枚举为**技术候选**，`extracting`/`embedded`/`stored` 等值描述 Memory Service 内部处理阶段，**不视为已冻结业务枚举**。具体状态值和状态机条件由 A/B/D 轨道在 D2 确认。`processing_status` 与 `source_business_status`（枚举 2.3）语义正交：一个事件可能有业务上 `success` 但处理流水线中仍处于 `extracting`。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `pending` | 待处理 | PARTIAL | 事件已入库但尚未进入处理流水线 |
| `extracting` | 抽取处理中 | PARTIAL | A 轨道抽取 Provider 内部状态，待 A 确认 |
| `extracted` | 抽取完成 | PARTIAL | A 轨道抽取完成标记，待 A 确认 |
| `embedded` | 已生成 Embedding 向量 | PARTIAL | 待 A/B 确认 Embedding 流程状态管理 |
| `stored` | 已持久化至 SQLite 结构化真源 | PARTIAL | 待 D 确认持久化状态跟踪需求 |

### 2.5 expression_type（偏好表达类型）

关联 REQ-02 偏好动态捕捉。

**说明**：`expression_type` 归一为 `explicit`（显式）与 `implicit`（隐式）两值。旧稿中的 `inferred` 不再作为 `expression_type` 候选值；候选/推断状态由 `memory_status=candidate`（见枚举 2.8）或 `PreferenceCandidate` 对象 / `preference_stage` 等生命周期字段表达。`candidate` 不是表达类型值，而是生命周期状态。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `explicit` | 显式表达 | UNVERIFIED | 用户以直接、不含糊的文字表达偏好（如「以后都使用中文」），或通过手动配置面板、设置界面显式指定 |
| `implicit` | 隐式表达 | UNVERIFIED | 从用户反复行为或选择倾向推断的偏好（需 ≥2 个 Turn 的行为证据）；模型辅助推断但尚未复核的候选偏好通过 `memory_status=candidate` 表达，不归入 `expression_type` 取值 |

**与标注规范的关系**：标注规范 `ANNOTATION_GUIDELINE_V0.1.md` 修订2（2026-07-31）已同步归一为 `explicit`/`implicit` 二值、`candidate` 不作表达类型值（由 `memory_status=candidate` 表达），与本稿一致，原「标注规范当前使用 explicit/implicit/candidate 三值」的过时描述作废（由 day12-e-01 修正，见 `KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md` R-2）。`candidate` 在本稿中通过 `memory_status` 表达候选生命周期，语义等价但不复用为 `expression_type` 取值。

### 2.6 knowledge_type（知识子类型）

关联 REQ-03 知识整合与冲突。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `workflow` | 工作流/操作习惯知识 | UNVERIFIED | 用户使用系统的操作序列、路径偏好或流程习惯 |
| `case` | 案例/场景知识 | UNVERIFIED | 特定场景下的用户决策、处理方式或经验记录 |
| `template` | 模板/格式知识 | UNVERIFIED | 用户对文档格式、输出结构、报告模板等定制化要求 |
| `fact` | 事实性知识 | UNVERIFIED | 可验证的客观信息，如系统配置、文件位置、工具参数 |
| `constraint` | 约束/规则知识 | UNVERIFIED | 用户在特定情境下的限制条件或强制规则 |
| `failure_experience` | 失败经验知识 | UNVERIFIED | Tool 执行失败、操作出错或受阻的记录，用于避免重复失败路径 |

**与 `primary_category` 的关系**：`primary_category` 保留为开放业务分类标签（如「文件操作」「系统设置」），用于语义检索和元数据过滤；**`primary_category` 不得替代 `knowledge_type`**。`knowledge_type` 是本稿定义的稳定业务枚举，用于知识结构化和冲突判定等核心业务逻辑。

### 2.7 memory_type（记忆类型）

关联 REQ-06 短中长期流转。

**注意**：本枚举仅定义业务语义上的短/中/长期区分，不冻结存储分层边界、流转阈值、回收策略等技术实现。存储分层设计由 D 轨道在 D3 Gate 前确认。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `short_term` | 短期记忆 | UNVERIFIED | 对应当前会话或短时间窗口内的即时上下文，流转边界 `待 D 确认` |
| `medium_term` | 中期记忆 | UNVERIFIED | 对应跨会话但仍属活跃阶段的记忆，流转条件 `待 D 确认` |
| `long_term` | 长期记忆 | UNVERIFIED | 对应经巩固后的稳定知识或持久偏好，归档策略 `待 D 确认` |
| `ephemeral` | 瞬态记忆 | UNVERIFIED | 对应单次 Tool 调用或临时上下文，生命周期不超出当前 Turn，待 E 确认业务必要性 |

### 2.8 memory_status（记忆生命周期状态）

关联 REQ-06 短中长期流转，REQ-05 精准遗忘。

**注意**：本枚举提供统一的记忆生命周期候选值，避免 Prefence 使用 `is_active`/`should_decay`、Knowledge 使用 `is_outdated`/`superseded_by_id` 等多布尔字段互相矛盾。`memory_status` 是本轮拟议统一生命周期业务真值；既有布尔字段（`is_active`、`is_outdated` 等）过渡保留，待 D/E 统一为 `memory_status` 后在 v1.0 中移除（本轮拟议统一语义见 `KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md` R-3；当前为 Canonical 候选裁定，待非作者 D Reviewer 批准并完成团队冻结后生效为团队级权威关系）。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `active` | 当前有效 | PARTIAL | 偏好正在使用，知识未被替代或过时 |
| `superseded` | 已被替代 | UNVERIFIED | 新版本已覆盖旧条目，通过 `previous_version_id` 或 `superseded_by_id` 回溯 |
| `deprecated` | 已弃用但保留 | UNVERIFIED | 已不再使用但保留用于审计和历史参照 |
| `expired` | 已过期 | UNVERIFIED | 有效期已过或衰减至阈值以下 |
| `removed` | 已移除/遗忘 | UNVERIFIED | 经 ForgetPlan 执行遗忘后标记，具体移除方式（标记删除/物理删除）待 D 确认 |
| `candidate` | 待复核候选 | UNVERIFIED | 临时要求、推断偏好等尚未确认其正式记忆资格的条目 |

### 2.9 preference_scope（偏好作用域）

关联 REQ-02 偏好动态捕捉。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `global` | 全局偏好 | UNVERIFIED | 跨会话、跨主题的通用偏好 |
| `topic` | 主题级偏好 | UNVERIFIED | 限定于特定知识或交互主题 |
| `tool` | 工具级偏好 | UNVERIFIED | 限定于特定 Tool 的调用行为偏好 |
| `session` | 会话级偏好 | UNVERIFIED | 限定于当前会话的临时偏好调整 |
| `time_window` | 时间窗口偏好 | UNVERIFIED | 特定时间段内的偏好（如工作日/非工作日） |

### 2.10 sensitivity（敏感度等级）

关联 REQ-05 敏感过滤与精准遗忘。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `none` | 无敏感信息 | PARTIAL | 业务含义层已确认 |
| `low` | 低敏感（如通用主题偏好） | UNVERIFIED | 待 E 定义敏感度分级标准 |
| `medium` | 中敏感（如工具使用偏好） | UNVERIFIED | 待 E 定义敏感度分级标准 |
| `high` | 高敏感（如个人身份、隐私内容） | UNVERIFIED | 待 E 定义敏感度分级标准 |
| `critical` | 严重敏感（如密钥、密码、证件号） | UNVERIFIED | 待 E 定义识别规则与强制过滤策略 |

### 2.11 conflict_type（冲突类型）

关联 REQ-03 知识整合与冲突。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `contradiction` | 逻辑矛盾 | UNVERIFIED | 两条知识在同一话题上给出互斥结论 |
| `temporal_inconsistency` | 时间不一致 | UNVERIFIED | 同主题的旧知识与新知识存在矛盾 |
| `source_conflict` | 来源冲突 | UNVERIFIED | 不同来源对同一事实给出不同版本 |
| `preference_conflict` | 偏好冲突 | UNVERIFIED | 多条偏好对同一偏好 key 给出冲突取值 |
| `scope_ambiguity` | 作用域歧义 | UNVERIFIED | 同一条知识在不同上下文中有不同解释 |

### 2.12 resolution_status（冲突消解状态）

关联 REQ-03 知识整合与冲突。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `detected` | 已检测到冲突 | PARTIAL | 业务含义层已确认 |
| `analyzing` | 冲突分析中 | PARTIAL | 业务含义层已确认 |
| `resolved_auto` | 已自动消解 | UNVERIFIED | 待 B 确认自动消解规则与阈值 |
| `resolved_manual` | 已人工消解 | UNVERIFIED | 待确认人工交互通道是否在范围内 |
| `deferred` | 暂缓处理 | UNVERIFIED | 待 B/E 确认暂缓策略 |
| `unresolvable` | 无法消解 | UNVERIFIED | 待 B/E 确认无法消解的判定标准 |

### 2.13 forget_mode（遗忘模式/粒度）

关联 REQ-05 精准遗忘。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `single_item` | 单条遗忘 | PARTIAL | 业务含义层已确认，对应指定 `target_id` 的单一记忆条目 |
| `session` | 会话级遗忘 | UNVERIFIED | 删除指定会话范围内的全部相关联记忆 |
| `topic` | 主题级遗忘 | UNVERIFIED | 删除指定主题/类别下的全部相关联记忆 |
| `time_window` | 时间窗口遗忘 | UNVERIFIED | 删除指定时间范围内的全部相关联记忆 |
| `full_reset` | 全量重置 | UNVERIFIED | 删除用户的全部记忆（含 Vector），待 E 确认业务安全边界 |

---

## 三、核心业务对象字段初稿

每个对象独立一章节，逐字段以表格呈现，每行包含以下七列：

| 列名 | 说明 |
|------|------|
| 字段名 | 英文 snake_case |
| 中文含义 | 该字段的业务语义 |
| 候选类型 | 业务层建议类型（`string`、`integer`、`float`、`boolean`、`timestamp`、`list[string]` 等），非最终技术类型 |
| 必填性 | `required`、`optional` 或 `conditional` |
| 来源 | `业务事件`、`系统生成`、`外部输入` 或 `派生计算`；标注 **`*禁止模型生成`** 的字段不得由 LLM/模型生成其取值 |
| 验证状态 | 当前该字段定义的确认程度 |
| 虚构示例 | 脱敏合成数据，不含任何真实用户信息 |

### 3.1 MemorySourceEvent（来源事件对象）

**对应 REQ**：REQ-01 多源数据。

**业务含义**：表示来自官方 AI 助手或系统环境的单次信息输入事件，是多源记忆采集的最初入口。`MemorySourceEvent` 在业务上是 `Preference` 和 `Knowledge` 的上游来源，二者通过 `source_event_id` 关联回本对象。**主要字段新增 `user_id`（用户归属）和 `occurred_at`（事件在宿主侧实际发生时间）**；对 `raw_payload_ref` 和 `content_summary` 新增敏感过滤规则说明。

| 字段名 | 中文含义 | 候选类型 | 必填性 | 来源 | 验证状态 | 虚构示例 |
|--------|---------|---------|--------|------|---------|----------|
| `event_id` | 事件全局唯一标识 | `string` | required | 系统生成 | PARTIAL | `"evt_20260730_a1b2c3"` |
| `user_id` | 数据归属用户标识（用户隔离键） | `string` | required | 业务事件 `*禁止模型生成` | UNVERIFIED | `"user_demo_01"` |
| `actor_id` | 行为主体标识（事件实际发起者：用户/系统/Tool） | `string` | required | 业务事件 `*禁止模型生成` | UNVERIFIED | `"user_default"` |
| `source_type` | 来源类型（见枚举 2.1） | `string` | required | 系统生成 | UNVERIFIED | `"tool_result"` |
| `schema_version` | 事件契约版本号 | `string` | required | 系统生成 | PARTIAL | `"0.1"` |
| `trace_id` | 跨服务追踪标识（用于关联上游宿主、Memory Service 和各轨道的请求链路） | `string` | optional | 业务事件 | UNVERIFIED | `"trc_20260730_a1b2c3"` |
| `event_type` | 事件消息粒度类型（见枚举 2.2；定义消息角色，与 `source_type`（来源大类）处于不同层级） | `string` | required | 业务事件 | UNVERIFIED | `"user_message"` |
| `source_reference` | 来源记录定位引用（记录定位/游标/脱敏引用，**非原始载荷**；用于定位来源记录，与 `raw_payload_ref` 的载荷引用区分） | `string` | conditional | 业务事件/系统生成 | UNVERIFIED | `"ref://sessions/sess_d4e5f6/turn_07"` |
| `consent_scope` | 本事件数据使用与遗忘同意范围标注 | `string` | required | 外部输入/业务事件 | UNVERIFIED | `"memory_only"` |
| `idempotency_key` | 接入幂等与去重键（用于接入侧去重和重放保护，**不可由 `event_id` 替代其业务语义**） | `string` | required | 业务事件/系统生成 | UNVERIFIED | `"idem_20260730_a1b2c3"` |
| `source_business_status` | 来源事件业务结果状态（见枚举 2.3） | `string` | required | 系统生成 | PARTIAL | `"raw"` |
| `processing_status` | 内部处理流水线状态（见枚举 2.4，技术候选，待 A/B/D 在 D2 确认） | `string` | optional | 系统生成 | PARTIAL | `"pending"` |
| `memory_type` | 记忆类型（见枚举 2.7） | `string` | conditional | 派生计算 | UNVERIFIED | `"short_term"` |
| `occurred_at` | 事件在宿主侧实际发生时间 | `timestamp` | required | 业务事件 `*禁止模型生成` | UNVERIFIED | `"2026-07-30T14:29:55+08:00"` |
| `captured_at` | 事件捕获入库时间 | `timestamp` | required | 系统生成 | PARTIAL | `"2026-07-30T14:30:00+08:00"` |
| `session_id` | 所属会话标识 | `string` | required | 业务事件 | UNVERIFIED | `"sess_d4e5f6"` |
| `raw_payload_ref` | 原始载荷引用（摘要或索引引用，不存真实内容；**高敏正文不得以明文进入引用存储**） | `string` | optional | 系统生成 | UNVERIFIED | `"ref://events/evt_20260730_a1b2c3/raw"` |
| `content_summary` | 事件内容简要摘要（**须经敏感过滤，高敏正文不得以明文进入摘要**） | `string` | optional | 派生计算 | UNVERIFIED | `"用户通过文件管理器搜索了近期文档"` |
| `turn_id` | 所属对话 Turn 标识（**触发条件**：`event_type` 为 `user_message`、`agent_response` 且宿主提供了 Turn 边界时必填，其余情况 optional） | `string` | conditional | 业务事件 | UNVERIFIED | `"turn_07"` |
| `tool_call_id` | 关联的 Tool 调用标识（**触发条件**：`source_type` 为 `tool_result` 时必填，其余情况为 N/A） | `string` | conditional | 业务事件 | UNVERIFIED | `"tool_file_search_v2_001"` |
| `sensitivity` | 敏感度等级（见枚举 2.10） | `string` | required | 派生计算 | UNVERIFIED | `"low"` |
| `is_sensitive_matched` | 是否命中敏感过滤规则 | `boolean` | required | 派生计算 | UNVERIFIED | `false` |
| `payload_security_checked` | 上游 Raw Payload 安全检查是否已实际执行并通过（*禁止 LLM 生成*、*禁止普通业务输入自行控制*；`source_type=tool_result` 且为 `false` 时必须 fail-close，不进入 Extraction） | `boolean` | required | 系统生成 / 上游安全过滤组件 | UNVERIFIED | `false` |
| `requires_embedding` | 是否需要生成 Embedding 向量 | `boolean` | required | 派生计算 | UNVERIFIED | `true` |
| `has_structured_payload` | 是否包含可抽取的结构化载荷 | `boolean` | optional | 派生计算 | UNVERIFIED | `true` |
| `language_tag` | 内容语言标记（BCP 47） | `string` | optional | 派生计算 | PARTIAL | `"zh-CN"` |

**标注说明**：
- `user_id` 与 `actor_id` 的语义区分见头部「用户隔离约定」；二者均禁止由模型生成，必须来自宿主侧业务事件。`user_id` 是用户级数据隔离的硬约束，`actor_id` 描述事件实际发起者（同一 `user_id` 下可能有多个 `actor_id`，如系统代用户执行操作）。
- `occurred_at` 与 `captured_at` 区分：前者是事件在宿主侧的实际发生时间，后者是系统捕获入库时间，二者可能存在传输/处理延迟。`occurred_at` 禁止由模型生成。
- `source_business_status` 描述来源事件的业务结果，`processing_status` 描述 Memory Service 内部处理阶段，二者语义正交。`event_status` 字段被拆分为此二字段，不再作为单一字段使用。
- **`source_reference` 与 `raw_payload_ref` 区分**：`source_reference` 用于定位来源记录（如会话 Turn 引用、游标、脱敏指针），其目标是描述「事件来自哪里」的位置信息；`raw_payload_ref` 指向受控原始载荷或脱敏载荷，其目标是数据内容本身。同一事件可同时拥有二者，但语义不得混同。
- **`idempotency_key` 业务语义**：`idempotency_key` 用于接入侧幂等与去重，确保同一业务触发不被重复处理；`event_id` 是事件全局标识，不可替代 `idempotency_key` 的去重业务语义。`idempotency_key` **不属模型生成字段**，应由业务事件或系统在接入层生成。
- **`event_type` 与 `source_type` 层级说明**：`source_type` 定义事件来源大类（「数据从何而来」），`event_type` 定义事件的消息粒度角色（「该数据在交互中的具体角色」）。二者处于不同层级，不得混用。例如：`source_type=chat`、`event_type=user_message` 表示来自对话大类中的一条用户消息。
- `turn_id` 与 `tool_call_id` 的存在性依赖官方 AI 助手真实事件结构，当前 C 轨道尚未取得麒麟 VM 证据 → `UNVERIFIED`，D3 Gate 前待 C 轨道取证回填。二者已按触发条件标明 conditional 语义。
- `raw_payload_ref` 的具体存储形态（内联摘要 vs. 外部引用 vs. 分片存储）待 D 确认，本稿不冻结 → `待 D 轨道确认`。
- `memory_type` 与 `processing_status` 的具体状态机条件与流转规则待 A/E/D 后续 Detail Design 确认，本稿仅定义候选值范围。
- **敏感载荷红线**：`raw_payload_ref` 引用目标和 `content_summary` 必须遵守敏感过滤规则。高敏正文（`sensitivity=critical`，如 API Key/Token/密码/私钥/跨用户数据）**不得以明文**进入引用存储或摘要，仅可写入脱敏占位或仅 ID 引用。

### 3.2 Preference（偏好对象）

**对应 REQ**：REQ-02 偏好动态捕捉。

**业务含义**：表示从用户行为中提取的显式或隐式偏好，以 key-value 结构承载，支持置信度评分、衰减策略和激活状态管理，是 Memory Service 向官方 AI 助手提供个性化上下文的核心载体。**主要新增 `user_id`（用户归属）、`expression_type`（偏好表达类型）、`is_temporary`/`should_persist`（临时要求与正式偏好边界）、`version`/`previous_version_id`（版本化）和 `memory_status`（统一生命周期）。**

| 字段名 | 中文含义 | 候选类型 | 必填性 | 来源 | 验证状态 | 虚构示例 |
|--------|---------|---------|--------|------|---------|----------|
| `preference_id` | 偏好全局唯一标识 | `string` | required | 系统生成 | PARTIAL | `"pref_20260730_x9y0z1"` |
| `user_id` | 数据归属用户标识（用户隔离键） | `string` | required | 业务事件 `*禁止模型生成` | UNVERIFIED | `"user_demo_01"` |
| `expression_type` | 偏好表达类型（见枚举 2.5） | `string` | required | 派生计算 | UNVERIFIED | `"explicit"` |
| `preference_scope` | 偏好作用域（见枚举 2.9） | `string` | required | 派生计算 | UNVERIFIED | `"topic"` |
| `preference_key` | 偏好键名（业务语义标识） | `string` | required | 业务事件 | UNVERIFIED | `"file_search_sort_order"` |
| `preference_value` | 偏好值 | `string` | required | 业务事件 | UNVERIFIED | `"by_modified_desc"` |
| `confidence_score` | 置信度评分（0.0–1.0） | `float` | required | 派生计算 | UNVERIFIED | `0.85` |
| `memory_status` | 记忆生命周期状态（见枚举 2.8，优先字段） | `string` | required | 派生计算 | UNVERIFIED | `"active"` |
| `is_active` | 当前是否激活（**过渡字段**：待 D/E 统一为 `memory_status` 后在 v1.0 中移除） | `boolean` | required | 系统生成 | PARTIAL | `true` |
| `is_temporary` | 是否为临时要求（`true` 时不得产生正式长期偏好，仅属候选判断阶段） | `boolean` | required | 派生计算 | UNVERIFIED | `false` |
| `should_persist` | 是否应持久化为正式偏好（`false` 时等同 `is_temporary=true`，不晋升为正式长期偏好） | `boolean` | required | 派生计算 | UNVERIFIED | `true` |
| `should_decay` | 是否应随时间衰减（**过渡字段**：待 D/E 统一为 `memory_status` 后在 v1.0 中移除） | `boolean` | required | 派生计算 | UNVERIFIED | `false` |
| `decay_after_at` | 衰减生效时间（过期后置信度下降或失效） | `timestamp` | conditional | 派生计算 | UNVERIFIED | `"2026-08-30T00:00:00+08:00"` |
| `evidence_event_ids` | 依据来源事件 ID 列表 | `list[string]` | required | 系统生成 | UNVERIFIED | `["evt_20260730_a1b2c3", "evt_20260729_d4e5f6"]` |
| `version` | 偏好版本号（用于版本化回溯） | `integer` | required | 系统生成 | UNVERIFIED | `1` |
| `previous_version_id` | 上一版本偏好 ID（用于回溯，初始版本为 null） | `string` | optional | 系统生成 | UNVERIFIED | `null` |
| `created_at` | 创建时间 | `timestamp` | required | 系统生成 | PARTIAL | `"2026-07-30T14:30:00+08:00"` |
| `updated_at` | 最后更新时间 | `timestamp` | required | 系统生成 | PARTIAL | `"2026-07-30T15:00:00+08:00"` |
| `requires_confirmation` | 是否需要用户显式确认 | `boolean` | required | 派生计算 | UNVERIFIED | `false` |
| `extracted_entities` | 关联的实体列表（用于语义关联） | `list[string]` | optional | 派生计算 | UNVERIFIED | `["文件管理器", "排序方式", "修改日期"]` |

**标注说明**：
- **临时要求与正式偏好边界**：`is_temporary=true` 或 `should_persist=false` 时，该偏好条目**不得**产生正式长期偏好。临时要求仅属候选判断阶段（对应 `memory_status=candidate`），不会被用户级偏好检索链路返回，也不参与偏好冲突判定。临时要求的生命周期限定于当前会话或指定时间窗口，到期后自动标记 `memory_status=expired`。
- `confidence_score` 的量化方法（基于频率/时序/行为模式加权）和具体阈值由 A/E 在 Embedding 提取 Provider 设计阶段确认，本稿仅定义字段语义 → `待 A/E 确认`。
- `decay_after_at` 与 `should_decay` 的具体衰减函数（线性/指数/阶梯）待 A/E 在偏好模型选型 ADR 中确认，本稿不冻结算法 → `待 A/E 确认`。
- `preference_key` 和 `preference_value` 的具体 schema 取决于官方 AI 助手偏好模型，当前官方模型未提供 → `UNVERIFIED`。
- **版本化业务要求**：偏好每次更新时 `version` 递增，`previous_version_id` 指向上一版本的 `preference_id`，形成可回溯的版本链。具体 SQLite 实现（如版本号生成策略、并发控制、历史版本保留策略）标记 `待 D 确认`，本稿不冻结存储实现。
- **`memory_status` 优先**：`memory_status` 是正式生命周期状态的唯一优先字段；`is_active` 和 `should_decay` 过渡保留，待 D/E 在 v1.0 中统一为 `memory_status` 后移除这些布尔字段。
- **候选/推断偏好说明**：经模型辅助推断但尚未经行为验证或人工复核的候选偏好，不由独立的 `expression_type` 值表达，而通过 `memory_status=candidate` 表达其候选生命周期状态。待置信度达标且经复核确认后，`memory_status` 晋升为 `active`，成为正式偏好。此设计替代了旧稿中 `expression_type=inferred` 的表达方式，避免将表达类型与生命周期状态混同。

### 3.3 Knowledge（结构化知识对象）

**对应 REQ**：REQ-03 知识整合与冲突、REQ-04 端侧 Embedding 与轻量检索。

**业务含义**：表示经过抽取和归一化后的结构化知识条目，是语义检索和 RRF 排序的最小知识单元。本对象仅定义业务字段，不冻结 SQLite 存储布局、Vector 索引结构和 FTS5 分词策略。**主要新增 `user_id`（用户归属）、`knowledge_type`（知识子类型）和 `memory_status`（统一生命周期）。**

| 字段名 | 中文含义 | 候选类型 | 必填性 | 来源 | 验证状态 | 虚构示例 |
|--------|---------|---------|--------|------|---------|----------|
| `knowledge_id` | 知识条目全局唯一标识 | `string` | required | 系统生成 | PARTIAL | `"kn_20260730_m3n4o5"` |
| `user_id` | 数据归属用户标识（用户隔离键） | `string` | required | 业务事件 `*禁止模型生成` | UNVERIFIED | `"user_demo_01"` |
| `knowledge_type` | 知识子类型（见枚举 2.6） | `string` | required | 派生计算 | UNVERIFIED | `"workflow"` |
| `memory_type` | 记忆类型（见枚举 2.7） | `string` | required | 派生计算 | UNVERIFIED | `"medium_term"` |
| `memory_status` | 记忆生命周期状态（见枚举 2.8，优先字段） | `string` | required | 派生计算 | UNVERIFIED | `"active"` |
| `source_event_id` | 来源事件标识，关联 `MemorySourceEvent.event_id` | `string` | required | 系统生成 | UNVERIFIED | `"evt_20260730_a1b2c3"` |
| `content_summary` | 知识内容摘要（可检索字段；**须经敏感过滤**） | `string` | required | 派生计算 | UNVERIFIED | `"用户频繁通过文件管理器按修改日期降序排列文件"` |
| `content_ref` | 完整内容引用（不冻结具体存储形态） | `string` | optional | 系统生成 | UNVERIFIED | `"ref://knowledge/kn_20260730_m3n4o5/full"` |
| `primary_category` | 主分类标签（**开放业务分类，不得替代 `knowledge_type`**） | `string` | optional | 派生计算 | UNVERIFIED | `"文件操作"` |
| `language_tag` | 内容语言标记（BCP 47） | `string` | optional | 派生计算 | PARTIAL | `"zh-CN"` |
| `confidence_score` | 置信度评分（0.0–1.0） | `float` | required | 派生计算 | UNVERIFIED | `0.72` |
| `requires_embedding` | 是否需要生成 Embedding 向量 | `boolean` | required | 派生计算 | UNVERIFIED | `true` |
| `is_outdated` | 是否已过时（**过渡字段**：待 D/E 统一为 `memory_status` 后在 v1.0 中移除） | `boolean` | required | 派生计算 | UNVERIFIED | `false` |
| `superseded_by_id` | 替代此条目的知识 ID | `string` | optional | 系统生成 | UNVERIFIED | `null` |
| `created_at` | 创建时间 | `timestamp` | required | 系统生成 | PARTIAL | `"2026-07-30T14:30:00+08:00"` |
| `updated_at` | 最后更新时间 | `timestamp` | required | 系统生成 | PARTIAL | `"2026-07-30T14:30:00+08:00"` |
| `access_count` | 累计被检索/使用的次数 | `integer` | optional | 派生计算 | PARTIAL | `3` |
| `last_accessed_at` | 最后被访问时间 | `timestamp` | optional | 系统生成 | PARTIAL | `"2026-07-30T16:00:00+08:00"` |
| `extracted_entities` | 抽取的实体列表 | `list[string]` | optional | 派生计算 | UNVERIFIED | `["文件管理器", "文件排序", "修改日期"]` |

**标注说明**：
- `primary_category` 保留为开放业务分类标签，用于语义检索和元数据过滤；**`knowledge_type` 是本稿定义的稳定业务枚举**，用于知识结构化和冲突判定等核心业务逻辑。二者不可相互替代。
- `content_ref` 不冻结具体存储形态（内联/外部分片/SQLite BLOB/文件系统引用），具体实现由 D 轨道在存储布局 ADR 中确认 → `待 D 确认`。
- `requires_embedding` 产生的 Embedding 向量是否在同一语义对象中承载还是分离为独立 Vector 索引条目，由 B 轨道在 Vector 索引设计阶段确认 → `待 B 确认`。（`README.md` 明确 Vector 非真源、可从 SQLite 重建。）
- `access_count` 与 `last_accessed_at` 的具体统计窗口和精度待 D 确认，本稿仅定义业务语义，不冻结实现细节 → `待 D 确认`。
- **`memory_status` 优先**：`memory_status` 是正式生命周期状态的唯一优先字段；`is_outdated` 过渡保留，待 D/E 在 v1.0 中统一为 `memory_status` 后移除。
- **敏感过滤**：`content_summary` 和 `content_ref` 引用的目标内容须经与 MemorySourceEvent 同等的敏感过滤规则处理。高敏正文不得以明文进入摘要或引用存储。

### 3.4 Conflict（冲突对象）

**对应 REQ**：REQ-03 知识整合与冲突。

**业务含义**：表示两条或多条知识条目之间检测到的语义或事实不一致，用于驱动冲突消解流程。本对象是业务层面的冲突记录，不冻结具体的消解算法、RRF 融合权重和存储布局。**主要新增 `user_id`（用户归属），并对最终消解结果字段标注「禁止由模型生成」。**

| 字段名 | 中文含义 | 候选类型 | 必填性 | 来源 | 验证状态 | 虚构示例 |
|--------|---------|---------|--------|------|---------|----------|
| `conflict_id` | 冲突全局唯一标识 | `string` | required | 系统生成 | PARTIAL | `"cfl_20260730_p7q8r9"` |
| `user_id` | 数据归属用户标识（用户隔离键） | `string` | required | 派生计算 `*禁止模型生成` | UNVERIFIED | `"user_demo_01"` |
| `conflict_type` | 冲突类型（见枚举 2.11） | `string` | required | 派生计算 | UNVERIFIED | `"temporal_inconsistency"` |
| `left_knowledge_id` | 冲突左方的知识条目 ID | `string` | required | 系统生成 | PARTIAL | `"kn_20260730_m3n4o5"` |
| `right_knowledge_id` | 冲突右方的知识条目 ID | `string` | required | 系统生成 | PARTIAL | `"kn_20260728_a1b2c3"` |
| `involved_knowledge_ids` | 涉及的全部知识条目 ID（用于多知识冲突） | `list[string]` | optional | 系统生成 | UNVERIFIED | `["kn_20260730_m3n4o5", "kn_20260728_a1b2c3"]` |
| `conflict_summary` | 冲突内容简要描述 | `string` | required | 派生计算 | UNVERIFIED | `"知识条目 kn_*_m3n4o5 表明用户偏好按修改日期排序，而 kn_*_a1b2c3 表明用户偏好按文件名排序"` |
| `resolution_status` | 消解状态（见枚举 2.12，**最终消解结果 `resolved_auto`/`resolved_manual`/`unresolvable` 不得由模型生成**） | `string` | required | 系统生成 | PARTIAL | `"detected"` |
| `resolution_strategy` | 消解策略（保留较新值/保留较高置信度/标记为冲突待确认/合并；**最终选择不得由模型生成**） | `string` | conditional | 派生计算 | UNVERIFIED | `"keep_higher_confidence"` |
| `is_auto_resolvable` | 是否可自动消解 | `boolean` | required | 派生计算 | UNVERIFIED | `true` |
| `resolution_confidence` | 消解结果的置信度（0.0–1.0；**最终值不得由模型生成**） | `float` | optional | 派生计算 | UNVERIFIED | `0.68` |
| `detected_at` | 冲突检测时间 | `timestamp` | required | 系统生成 | PARTIAL | `"2026-07-30T15:00:00+08:00"` |
| `resolved_at` | 冲突消解时间 | `timestamp` | conditional | 系统生成 | PARTIAL | `null` |
| `resolved_by` | 消解执行方标识（规则/模块/轨道标识，非自然人；**不得由模型生成**） | `string` | conditional | 系统生成 | UNVERIFIED | `"conflict_resolver_v1"` |

**标注说明**：
- `user_id` 从涉及的 Knowledge 条目派生获取，同属一个 `user_id` 下的冲突方为有效冲突。**不得由模型生成 `user_id`**。
- `conflict_type` 中 `contradiction`（逻辑矛盾）与 `temporal_inconsistency`（时间不一致）的判定阈值和判别逻辑由 B 轨道在冲突检测模块设计阶段确认 → `待 B 确认`。
- `resolution_strategy` 的具体策略集合和优先级排序待 B/E 在 ADR 中确认 → `待 B/E 确认`。
- `is_auto_resolvable` 的判定标准（置信度阈值/差异幅度/类型判定）待 B/E 确认 → `待 B/E 确认`。
- **冲突优先级六档定级**（依据 SOP v1.1，待人工导入后复核）：冲突消解时，不同来源可信度按以下优先级排序（由高到低），高优先级来源的信息覆盖低优先级来源的冲突主张；同等优先级来源之间如存在矛盾，标记为 `detected` 待进一步消解。
  1. **用户最新显式配置**：用户通过手动配置、设置面板或显式声明给出的最新偏好或事实。
  2. **用户明确确认**：系统询问后用户以肯定回复（如「是」「确认」「对」）明确确认的内容。
  3. **真实 Tool 执行结果**：Tool 在实际运行环境中返回的执行结果、输出或状态码。
  4. **多次一致行为**：来自 ≥2 个独立 Turn/事件的一致行为模式，且各次行为之间无矛盾。
  5. **单次行为推断**：从单次用户行为或单次事件中推断出的偏好或知识。
  6. **模型自身推测**：LLM 基于上下文推理得出的推测性结论，未经行为验证或 Tool 执行确认。
- **作用域差异判定**：当两条知识或偏好的 `preference_scope`/`knowledge_type`/`primary_category` 等作用域字段不同时，应优先判定为**可共存**而非冲突（如「文件操作」中的排序偏好与「浏览器」中的排序偏好分属不同作用域，不构成冲突）。仅在作用域相同或高度重叠的情况下，方进入冲突判定流程。
- **模型自身推测约束**：第 6 档「模型自身推测」**不得覆盖**第 1–5 档中任何高可信来源，也不得直接成为事实真源。模型推测仅可作为候选提示供用户确认，在用户确认前 `memory_status` 必须保持 `candidate`。
- **禁止模型生成规则**：`resolution_status` 的最终结果值（`resolved_auto`、`resolved_manual`、`unresolvable`）、`resolution_strategy` 的最终选择、`resolution_confidence` 的最终值和 `resolved_by` 的消解方标识**均不得由模型/LLM 生成**，必须由消解规则引擎或系统计算产出。

### 3.5 ForgetPlan（遗忘计划对象）

**对应 REQ**：REQ-05 敏感过滤与精准遗忘。

**业务含义**：表示一次有计划、可追踪的遗忘操作，覆盖单条记录、会话级、主题级、时间窗口级和全量重置等遗忘粒度。遗忘计划对象记录遗忘的目标范围、执行状态和级联清理要求，是本系统精准遗忘能力的核心业务记录。**主要新增 `user_id`（用户归属）、`target_selector`（用户输入选择器）和 `resolved_target_ids`（系统解析后的目标 ID 列表），并对最终删除决策标注「禁止由模型生成」。**

| 字段名 | 中文含义 | 候选类型 | 必填性 | 来源 | 验证状态 | 虚构示例 |
|--------|---------|---------|--------|------|---------|----------|
| `forget_plan_id` | 遗忘计划全局唯一标识 | `string` | required | 系统生成 | PARTIAL | `"fgp_20260730_s1t2u3"` |
| `user_id` | 数据归属用户标识（用户隔离键） | `string` | required | 外部输入 `*禁止模型生成` | UNVERIFIED | `"user_demo_01"` |
| `forget_mode` | 遗忘模式/粒度（见枚举 2.13） | `string` | required | 外部输入 | PARTIAL | `"single_item"` |
| `target_selector` | 用户输入的遗忘目标选择器（自然语言描述或条件表达式，如「忘掉上周二关于项目排期的所有内容」） | `string` | required | 外部输入 | UNVERIFIED | `"忘掉上周二关于项目排期的所有内容"` |
| `resolved_target_ids` | 系统解析后的目标 ID 列表（必须经预览确认后方可执行删除；**不得由模型生成**） | `list[string]` | optional | 派生计算/系统生成 | UNVERIFIED | `["kn_20260730_m3n4o5", "kn_20260728_a1b2c3"]` |
| `target_type` | 遗忘目标的业务类型（`knowledge`、`preference`、`event`、`all`） | `string` | required | 外部输入 | UNVERIFIED | `"knowledge"` |
| `target_id` | 精确遗忘的目标 ID（`forget_mode` 为 `single_item` 时必填，与 `target_selector` 互斥或由 `resolved_target_ids` 替代） | `string` | conditional | 外部输入 | PARTIAL | `"kn_20260730_m3n4o5"` |
| `target_session_id` | 目标会话 ID（`forget_mode` 为 `session` 时必填） | `string` | conditional | 外部输入 | UNVERIFIED | `"sess_d4e5f6"` |
| `target_topic` | 目标主题/分类（`forget_mode` 为 `topic` 时必填） | `string` | conditional | 外部输入 | UNVERIFIED | `"文件操作"` |
| `target_time_range` | 目标时间范围（`forget_mode` 为 `time_window` 时必填） | `string` | conditional | 外部输入 | UNVERIFIED | `"2026-07-01T00:00:00/2026-07-31T23:59:59"` |
| `created_at` | 遗忘计划创建时间 | `timestamp` | required | 系统生成 | PARTIAL | `"2026-07-30T16:00:00+08:00"` |
| `executed_at` | 实际执行时间 | `timestamp` | optional | 系统生成 | PARTIAL | `"2026-07-30T16:00:05+08:00"` |
| `status` | 执行状态（`pending`、`previewing`、`awaiting_confirmation`、`executing`、`completed`、`failed`、`rolled_back`） | `string` | required | 系统生成 | PARTIAL | `"completed"` |
| `is_cascade` | 是否级联清理关联记忆（如遗忘事件时同时清理其派生的 Knowledge/Preference） | `boolean` | required | 外部输入 | UNVERIFIED | `true` |
| `has_vector_cleanup` | 是否需要同步清理 Vector 索引 | `boolean` | required | 派生计算 | UNVERIFIED | `true` |
| `requires_confirmation` | 是否需要用户确认后执行（**最终决策不得由模型生成**） | `boolean` | required | 外部输入/系统生成 | UNVERIFIED | `false` |
| `affected_count` | 实际影响的记录数量（**不得由模型生成**） | `integer` | optional | 系统生成 | PARTIAL | `5` |
| `rollback_plan_id` | 回滚计划 ID（记录执行前快照的引用，用于失败回滚） | `string` | optional | 系统生成 | UNVERIFIED | `"rb_fgp_20260730_s1t2u3"` |

**标注说明**：
- `target_selector` 与 `resolved_target_ids` 的区分：前者是用户输入的遗忘目标原始描述（如自然语言表述），后者是系统解析后的精确目标 ID 列表。**遗忘必须遵循「先预览再确认」流程**：系统解析 `target_selector` 后生成 `resolved_target_ids`，向用户展示受影响的条目预览，用户确认后方可执行删除。`resolved_target_ids` 不得由模型/LLM 生成，必须由系统规则引擎解析。
- `target_id` 作为 `single_item` 模式的直接输入保留，但在需要语义解析的遗忘模式下，优先使用 `target_selector` → `resolved_target_ids` 路径。
- `status` 新增 `previewing`（预览生成中）和 `awaiting_confirmation`（等待用户确认）两个中间状态，完整体现遗忘确认流程。
- **禁止模型生成规则**：`resolved_target_ids`、`requires_confirmation` 的最终判定、`affected_count` 的最终值、以及整体删除决策**均不得由模型/LLM 生成**，必须由遗忘规则引擎或系统计算产出。
- `has_vector_cleanup` 对应的 Vector 索引同步删除策略（删除后立即重建 vs. 标记删除后延迟清理 vs. 定期全量重建）由 B 轨道在 Vector 索引设计 ADR 中确认，`README.md` 明确 Vector 可从 SQLite 真源重建 → `待 B 确认`。
- `is_cascade` 的级联范围（清理论据源事件时，是否必然清理其派生的全部 Knowledge 和 Preference）待 E 在安全与遗忘边界 ADR 中确认 → `待 E 确认`。
- `forget_mode` 的 `full_reset` 候选值仅描述业务语义，实际执行的安全边界（是否需要操作者权限验证、是否执行二次确认、是否保留审计日志）待 E/D 确认 → `待 E/D 确认`。

---

## 四、业务要求与技术实现边界

本稿属于记忆业务含义层 DRAFT，明确以下边界：

### 4.1 E 轨道职责

E 轨道在本稿中定义必须表达的业务含义：
- 业务对象的定义与字段语义；
- 候选枚举的业务取值范围；
- 字段间的业务关系与约束；
- 各轨道的反馈核对责任。

### 4.2 禁止模型生成字段清单

以下字段**严禁**由模型/LLM 生成其取值，必须由宿主侧业务事件、系统规则引擎或确定性的派生计算产出：

| 组别 | 字段 | 生成责任方 |
|------|------|-----------|
| 用户归属 | `user_id`（所有对象）、`actor_id`（MemorySourceEvent） | 宿主侧业务事件/外部输入 |
| 时间事实 | `occurred_at`（MemorySourceEvent） | 宿主侧业务事件 |
| 冲突最终结果 | `resolution_status`（`resolved_auto`/`resolved_manual`/`unresolvable`）、`resolution_strategy`、`resolution_confidence`、`resolved_by` | 消解规则引擎/系统计算 |
| 安全终判 | `sensitivity` 的最终定级（在敏感过滤规则引擎产出后，模型不得覆写） | 敏感过滤规则引擎 |
| 遗忘最终决策 | `resolved_target_ids`、`requires_confirmation` 最终判定、`affected_count` 最终值、整体删除执行决策 | 遗忘规则引擎/系统计算 |
| 幂等与去重 | `idempotency_key`（MemorySourceEvent） | 业务事件/系统生成（接入层） |

违反上述规则可能导致：用户隔离被破坏、虚构时间戳、虚假消解结果、安全等级被降级、或错误遗忘范围。各轨道在实现层必须确保这些字段的生成链路不经过 LLM 调用。

### 4.3 敏感载荷处理红线

- `raw_payload_ref` 引用目标和 `content_summary` 必须遵守敏感过滤规则（参见 `datasets/ANNOTATION_GUIDELINE_V0.1.md` §五 安全边界与敏感标注）。
- 高敏正文（`sensitivity=critical`，如 API Key/Token/密码/私钥/跨用户数据，对应标注规范 S-01 至 S-04 及 S-08）**绝对不得以明文**进入引用存储或摘要，仅可写入脱敏占位（如 `[REDACTED_API_KEY]`）或仅 ID 引用。
- 敏感过滤发生在事件入库阶段（`source_business_status=ignored`），被标记为 `ignored` 的事件不得进入后续抽取和存储流水线。
- `sensitivity` 等级的最终判定由敏感过滤规则引擎产出，**模型不得覆写或降级**。

### 4.4 临时要求与正式偏好边界

- `is_temporary=true` 或 `should_persist=false` 的偏好条目**不得产生正式长期偏好**，其 `memory_status` 必须为 `candidate` 或 `expired`。
- 临时要求的生命周期限定于当前会话或指定时间窗口，到期后自动标记 `memory_status=expired`，不进入用户级偏好检索链路，也不参与偏好冲突判定。
- 经模型辅助推断但尚未经行为验证或人工复核的候选偏好，通过 `memory_status=candidate` 表达其候选生命周期状态，不归入 `expression_type` 取值。在置信度达标且经复核确认前，`memory_status` 保持 `candidate`，不晋升为正式偏好（`memory_status=active`）。
- 临时要求和候选偏好可通过审核流程提升为正式偏好，但需版本化记录晋升事件（新 `version`，`previous_version_id` 指向临时/候选条目）。

### 4.5 本稿不冻结的技术实现

以下技术实现层事项**不在本 v0.1 稿中冻结**，由对应轨道在各自技术设计阶段独立完成，仅需核对是否偏离本稿业务语义：

| 技术实现事项 | 责任轨道 | 计划冻结窗口 |
|-------------|---------|------------|
| IPC JSON Schema（UDS 消息结构） | D | D3–D5 |
| SQLite 数据库表结构与 schema 迁移 | D | D3–D5 |
| Vector 索引结构与 Collection 布局 | B | D4–D6 |
| FTS5 分词配置与索引策略 | B | D4–D6 |
| C++ 侧结构体定义（cpp-bridge/、memory-client/） | C/D | D4–D6 |
| 存储分层边界（short/medium/long 的时间/频率阈值） | D | D4–D6 |
| Embedding 向量维度与存储格式 | A | D4–D6 |
| RRF 融合权重与衰减函数 | B | D5–D7 |
| 冲突检测阈值与消解规则引擎 | B | D5–D7 |
| 遗忘级联规则与回滚审计机制 | E/D | D5–D7 |
| Preference 版本化 SQLite 实现 | D | D4–D6 |
| 敏感过滤规则引擎具体实现 | E | D5–D7 |

### 4.6 标注约定

凡涉及上述技术实现层且尚未确认的字段，本稿使用以下标注：

- **`待 D 确认`**：存储布局、持久化方案、UDS 协议映射相关字段
- **`待 B 确认`**：检索过滤、Vector 索引、RRF 排序、冲突判定阈值相关字段
- **`待 A 确认`**：Embedding Provider、抽取输出格式相关字段
- **`待 C 确认`**：官方 AI 助手事件结构、Tool/Turn 上下文相关字段
- **`待 E 确认`**：业务规则、安全边界、敏感度分级相关字段
- **`待 A/E 确认`** 或 **`待 B/E 确认`**：跨轨道公共决策涉及字段

---

## 五、反馈责任矩阵

本稿提交后，以下轨道须在 D3 Gate 审查前完成字段核对，并产出差异清单。

### 5.1 A 轨道（Embedding、抽取 Provider）

**核对内容**：
- `MemorySourceEvent.requires_embedding`、`content_summary` 是否覆盖 Embedding Provider 所需的输入语义单元
- `Knowledge.requires_embedding`、`content_summary`、`extracted_entities` 是否满足向量化输入的语义粒度要求
- `Preference.confidence_score`、`should_decay`、`decay_after_at` 的量化方法是否可落地为抽取 Provider 的输出格式
- `Knowledge.confidence_score` 的计算是否可纳入抽取 Provider 输出

**产出形式**：D3 审查前提交 A 轨道字段差异清单，逐字段给出「符合/需修订/需新增」标记及修订建议。

**当前状态**：`UNVERIFIED/PENDING`（A 轨道 Embedding Provider 尚未选型，抽取输出格式尚未确定）

### 5.2 B 轨道（Vector、FTS5、RRF、检索评测）

**核对内容**：
- `Knowledge` 的检索相关字段（`content_summary`、`extracted_entities`、`primary_category`、`knowledge_type`、`language_tag`）是否覆盖 FTS5 全文搜索和元数据过滤的业务需求
- `Conflict` 的冲突检测字段（`conflict_type`、`is_auto_resolvable`、`resolution_confidence`）是否支持应用层 RRF 排序与融合的业务边界
- `ForgetPlan.has_vector_cleanup`、`is_cascade` 是否对齐 Vector 索引清理和一致性保证策略
- `memory_type`（短/中/长期）在检索层的区分语义是否匹配 B 的召回边界设计

**产出形式**：D3 审查前提交 B 轨道字段差异清单，逐字段给出「符合/需修订/需新增」标记及修订建议。

**当前状态**：`UNVERIFIED/PENDING`（B 轨道 Vector 索引与 RRF 均未开始实现，检索过滤字段未设计）

### 5.3 C 轨道（OS Agent Hook、MemoryClient、Tool/Turn Adapter）

**核对内容**：
- `MemorySourceEvent.source_type`（七项候选值）、`event_type`（三项消息粒度值）、`turn_id`、`tool_call_id`、`session_id`、`actor_id`、`user_id`、`source_reference`、`consent_scope`、`idempotency_key`、`trace_id` 是否在真实官方 AI 助手 Tool/Turn/Context 事件中存在对应字段，字段语义是否一致
- `source_type` 七项候选值是否覆盖真实宿主可提供的全部事件类型
- `MemorySourceEvent.raw_payload_ref` 的事件封装方式是否与 C 的 Hook 数据流兼容
- `MemorySourceEvent.occurred_at` 在宿主事件中是否存在可直接取证的对应字段

**产出形式**：D3 审查前提交 C 轨道字段核对与取证计划，逐字段标注「已在 VM 取证确认 / 待 VM 取证 / 不存在对应宿主字段」，对不存在字段给出替代方案建议。

**当前状态**：`UNVERIFIED/PENDING`（官方 AI 助手真实事件结构尚未取得麒麟 VM 证据，全部 C 核对字段均处于 UNVERIFIED 状态）

### 5.4 D 轨道（IPC、SQLite、Outbox、成品化）

**核对内容**：
- 五个核心业务对象的持久化相关字段（`*_id`、`*_at`、状态字段）与 SQLite 存储布局的映射可行性
- `MemorySourceEvent.raw_payload_ref`、`Knowledge.content_ref` 等引用字段的持久化策略（内联/外部分片/文件系统引用）
- `ForgetPlan` 的遗忘执行状态和回滚方案在 SQLite 事务模型中的可行性
- 全部 `system_generated` 字段的 ID 生成策略和时间戳精度与 IPC 协议的兼容性
- `user_id` 用户隔离字段在 SQLite 索引、IPC 请求路由和检索过滤中的实现可行性
- Preference 版本化（`version`/`previous_version_id`）和 `memory_status` 在 SQLite schema 中的实现方案

**产出形式**：D3 审查前提交 D 轨道字段映射清单，逐字段给出「已纳入 IPC 协议 / 已纳入 SQLite schema 草案 / 需修订业务字段定义 / 需新增 IPC 字段」标记。

**当前状态**：`UNVERIFIED/PENDING`（D 轨道尚未开始 IPC JSON Schema 和 SQLite 表设计）

### 5.5 E 轨道（记忆业务、安全、数据集）

**核对内容**：
- `user_id` 用户隔离业务规则是否与标注规范和安全边界一致
- `expression_type`（explicit/implicit）与标注规范术语的对齐情况；`inferred` 已归一为 `implicit`，候选状态由 `memory_status=candidate` 表达，待标注规范同步更新
- `knowledge_type` 六项候选值是否覆盖全部业务场景（如不足，需补充）
- `memory_status` 统一生命周期候选值与标注规范中的状态对应关系
- 临时要求/正式偏好/候选偏好的边界规则是否与开发集分类一致
- 敏感载荷处理红线是否与标注规范 §五 安全边界完全对齐

**产出形式**：D3 审查前提交 E 轨道字段复核报告，逐项给出「已对齐/需修订」标记。

**当前状态**：`UNVERIFIED/PENDING`（E 轨道在 D3 Gate 前须完成本稿与标注规范的最终对齐）

---

## 六、未确认能力与人工决策待办

以下事项需团队成员在后续阶段人工决策，本 v0.1 DRAFT 仅如实记录当前已知的未确认项。

| 编号 | 事项 | 关联 REQ | 责任轨道 | 计划窗口 |
|------|------|---------|---------|---------|
| HD-SCHEMA-01 | 导入赛题原文、总体架构 SOP、官方 SDK 与 OS Agent 能力边界基线至 `docs/baseline/`，用于复核全稿字段 | REQ-01–07 | 团队/E | D3 Gate 前 |
| HD-SCHEMA-02 | C 轨道在麒麟 VM 取证官方 AI 助手 Tool/Turn/Context 真实事件结构，回填 `MemorySourceEvent` 中 `user_id`、`actor_id`、`turn_id`、`tool_call_id`、`occurred_at` 等字段的 UNVERIFIED 状态 | REQ-01 | C | L2 取证窗口 |
| HD-SCHEMA-03 | A/E 确认 `Preference.confidence_score` 计算模型与 `should_decay`/`decay_after_at` 衰减策略的语义定义 | REQ-02 | A·E | D3 Gate 前 |
| HD-SCHEMA-04 | B 确认 `Conflict` 类型判定阈值（`contradiction` v.s. `temporal_inconsistency` 的判别逻辑）与 `is_auto_resolvable` 判定标准 | REQ-03 | B | D3 Gate 前 |
| HD-SCHEMA-05 | B 确认 Vector 索引与 SQLite 真源的一致性策略（增量更新/全量重建），回填 `ForgetPlan.has_vector_cleanup` 的实现可行性 | REQ-04 | B | D3 Gate 前 |
| HD-SCHEMA-06 | E 确认 `ForgetPlan.is_cascade` 的遗忘级联范围与 `forget_mode.full_reset` 的安全边界 | REQ-05 | E | D3 Gate 前 |
| HD-SCHEMA-07 | D 确认 `memory_type` 短/中/长期的分层边界（时间阈值/访问频率/重要性混合）和存储分层布局 | REQ-06 | D | D3 Gate 前 |
| HD-SCHEMA-08 | B 确认检索评测指标基线（Recall@K、MRR、NDCG），与 `Knowledge` 被检索字段的业务覆盖度对齐 | REQ-07 | B | D3 Gate 前 |
| HD-SCHEMA-09 | D 确认 `*_id` 全局唯一标识的生成策略（UUID v4/UUID v7/纳秒时间戳+随机数）与 IPC 协议的兼容性 | REQ-01–06 | D | D3 Gate 前 |
| HD-SCHEMA-10 | 是否将本文档链接入 `docs/architecture/README.md` 和 `docs/README.md` 的索引（独立维护任务，不在本任务范围） | — | 团队 | 后续维护 |
| HD-SCHEMA-11 | 导入架构设计审查报告（Copilot 独立审查报告）至 `docs/baseline/`，用报告建议复核本稿全部字段与约束，记录差异并决策是否追加修订 | REQ-01–07 | E | D3 Gate 前 |
| HD-SCHEMA-12 | C 轨道在麒麟 VM 取证时确认宿主事件中 `user_id`/`actor_id` 字段是否存在及语义，回填本稿用户隔离约定的可行性 | REQ-01 | C | L2 取证窗口 |
| HD-SCHEMA-13 | D/E 确认 `memory_status` 统一生命周期枚举与 SQLite 实现方案，决定是否在 v1.0 中移除 `is_active`/`is_outdated`/`should_decay` 等过渡布尔字段 | REQ-05、REQ-06 | D·E | D3 Gate 前 |
| HD-SCHEMA-14 | E 确认 `expression_type` 已按任务规格归一为 `explicit`/`implicit`，待 SOP v1.1 导入后终审；标注规范 `ANNOTATION_GUIDELINE_V0.1.md` 修订2（2026-07-31）已对齐二值（`candidate` 不作表达类型值），历史术语差异已消除（由 day12-e-01 修正，见 `KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md` R-2）；本项仅剩 SOP v1.1 导入后终审 | REQ-02 | E | D3 Gate 前 |
| HD-SCHEMA-15 | 导入 SOP v1.1「总体架构、团队分工与标准开发 SOP」实体文件至 `docs/baseline/`，逐项复核本稿按任务规格回填的 `source_type` 七值规范集合、`event_type` 消息粒度分层、六档冲突优先级与 `expression_type` 归一结果 | REQ-01–07 | 团队/E | D3 Gate 前 |
| HD-SCHEMA-16 | C 轨道在麒麟 VM 取证 `source_type` 七值（`chat`、`tool_result`、`manual_config`、`recollect`、`file`、`meeting`、`voice`）与 `event_type` 三值（`user_message`、`agent_response`、`system_message`）在宿主真实事件结构中的覆盖情况，回填验证状态 | REQ-01 | C | L2 取证窗口 |

---

## 七、版本与冻结门槛

### 变更记录

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|---------|------|
| v0.1 | 2026-07-30 | DRAFT 初稿，建立五核心业务对象字段初稿、命名规则、八组候选枚举、反馈责任矩阵和未确认能力清单。基于 README、各模块 README 和赛题追踪矩阵 v0.1 事实编写。所有涉及官方宿主能力的字段均如实标记 UNVERIFIED/PARTIAL。 | E 轨道 |
| v0.1（修订） | 2026-07-30 | 业务 Schema 用户隔离与字段一致性修复：新增 `user_id` 对所有核心对象的用户归属；区分 `user_id`/`actor_id` 语义；新增 `expression_type`、`knowledge_type`、`memory_status` 三组枚举；拆分来源业务状态与内部处理流水线状态；新增 `occurred_at`、`target_selector`、`resolved_target_ids` 等字段；Preference 新增版本化（`version`/`previous_version_id`）、临时边界（`is_temporary`/`should_persist`）；补敏感载荷红线、禁止模型生成字段清单、临时与正式偏好边界规则；conditional 字段写明触发条件。仍为 v0.1 DRAFT，未冻结任何技术实现。 | E 轨道 |
| v0.1（修订2） | 2026-07-30 | 对齐统一事件模型与冲突优先级基线（PR #10 审查修订）：`source_type` 替换为 SOP v1.1 七值规范集合（`chat`、`tool_result`、`manual_config`、`recollect`、`file`、`meeting`、`voice`）；新增 `event_type` 消息粒度枚举（`user_message`/`agent_response`/`system_message`）并说明与 `source_type` 的层级差异；`MemorySourceEvent` 新增 `schema_version`、`trace_id`、`event_type`、`source_reference`、`consent_scope`、`idempotency_key` 六个字段；明确 `source_reference` 与 `raw_payload_ref` 语义区分；`idempotency_key` 补入禁止模型生成清单；`expression_type` 归一为 `explicit`/`implicit`，移除 `inferred`，`candidate` 状态由 `memory_status` 表述；Conflict 标注完整引用六档冲突优先级与作用域可共存规则；枚举编号因新增 2.2 整体顺延。依据 SOP v1.1（待人工导入）按任务规格回填，待 SOP 实体文件导入后复核。仍为 v0.1 DRAFT。 | E 轨道 |
| v0.1（修订3） | 2026-09-03 | 权威层级与语义漂移收口候选（day12-e-01）：头部增补「权威层级与兼容性声明」，明确本稿继续保持 DRAFT/compatibility 来源参照状态，Canonical v1 与 D3 当前均为 `CANDIDATE_FOR_FREEZE`，团队级权威承接关系待 D Reviewer 批准、PR 合并并完成后续冻结治理后生效；§2.5 修正过时三值描述（标注规范修订2 已归一为 explicit/implicit 二值）；§2.8 追加 Canonical R-3 候选裁定引用；HD-SCHEMA-14 同步标注规范修订2 已对齐二值、仅剩 SOP v1.1 导入后终审。仍为 v0.1 DRAFT。 | E 轨道 |

### 冻结为 v1.0 的条件

以下条件**全部满足**后，本文档方可冻结为 v1.0 版本，成为记忆业务层的正式基线：

1. 赛题原文、总体架构 SOP、官方 SDK 与 OS Agent 能力边界基线文档已导入 `docs/baseline/`，且 `docs/baseline/README.md` 中六项文档状态更新为「已导入」
2. 架构设计审查报告（Copilot 独立审查报告）已导入 `docs/baseline/`，且本稿已根据报告建议完成复核和必要修订
3. D3 Gate 经 D/E Reviewer 审查通过，且审查结论文档化
4. A/B/C/D 各轨道字段差异清单已提交且全部闭合（差异项须有明确决议）
5. 官方 AI 助手真实 Tool/Turn/Context 事件结构经麒麟 VM 取证，C 轨道已回填 `MemorySourceEvent` 中 `user_id`、`actor_id`、`turn_id`、`tool_call_id`、`occurred_at` 等字段的验证状态
6. 六章「未确认能力与人工决策待办」中 HD-SCHEMA-01 至 HD-SCHEMA-16 均有明确决议
7. Evidence Reviewer 确认文档中所有字段的验证状态标注与当时实际证据等级一致
8. 本文档中各枚举章节中所有的「UNVERIFIED」标记在实际确认后更新为「VERIFIED」，或确认为不可能确认后标记为「NOT_APPLICABLE」
9. `memory_status` 统一生命周期枚举已被 D/E 确认，`is_active`/`is_outdated`/`should_decay` 等过渡布尔字段的移除决策已明确

在满足以上条件之前，本文档不视为冻结基线，不得作为最终技术实现的唯一依据。

---

> **本文档到此结束。后续版本将在 D3 Gate 审查后根据 A–E 轨道反馈修订。**
