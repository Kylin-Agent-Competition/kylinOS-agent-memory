# 记忆业务对象与字段命名初稿

- **版本**：v0.1
- **状态**：DRAFT
- **用途**：D1–D2 能力对照
- **冻结门槛**：D3 Gate 前不得视为冻结协议；须经 D/E Reviewer 审查，并待基线文档（赛题原文、总体架构 SOP、官方 SDK 与 OS Agent 能力边界）导入仓库、官方 AI 助手真实事件结构经麒麟 VM 取证后，方可冻结为 v1.0
- **依据来源**：
  - `README.md`（项目定位、技术路线、责任轨道 A–E、当前阶段与明确未完成项）
  - 各模块 `README.md`（`memory-service/`、`cpp-bridge/`、`memory-client/`、`os-agent-integration/`、`evaluation/`、`datasets/`）中的职责边界与当前状态
  - `docs/project-management/REQUIREMENT_TRACEABILITY_MATRIX.md`（赛题要求与项目交付追踪矩阵 v0.1，REQ-01 至 REQ-07）
- **局限声明**：
  - 赛题原文、总体架构 SOP、官方 SDK 与 OS Agent 能力边界基线文档尚未导入仓库（`docs/baseline/README.md` 均标注「待人工导入」）
  - 官方 AI 助手真实 Tool/Turn/Context 事件结构尚未取得麒麟 VM 证据（C 轨道 `os-agent-integration/` 当前仅建立目录和职责边界，尚无生产实现）
  - 官方偏好模型与宿主能力均未确认
  - 因此本稿中涉及以上来源的字段，验证状态均标注 `UNVERIFIED`、`PARTIAL` 或 `待对应轨道确认`，不得视为已确认契约

---

## 一、命名规则

本稿统一采用以下命名规则，覆盖全部业务对象和字段。

| 规则 | 说明 | 示例 |
|------|------|------|
| 业务对象名 | PascalCase | `MemorySourceEvent`、`Preference`、`Knowledge`、`Conflict`、`ForgetPlan` |
| 字段名 | 英文 `snake_case` | `event_id`、`source_type`、`preference_scope` |
| 时间字段 | 以 `_at` 结尾 | `created_at`、`updated_at`、`captured_at`、`executed_at` |
| 标识字段 | 以 `_id` 结尾 | `event_id`、`session_id`、`preference_id` |
| 布尔字段 | 使用 `is_`、`has_`、`should_` 或 `requires_` 前缀 | `is_active`、`has_structured_payload`、`should_decay`、`requires_embedding` |
| 枚举型字段 | 以 `_type`、`_status`、`_mode`、`_scope` 或 `_strategy` 结尾 | `source_type`、`resolution_status`、`forget_mode` |

### 禁用的公共字段名

以下无明确业务含义的字段名不得用于任何业务对象：

- `data`
- `info`
- `value1` / `value2`
- `flag` / `flags`
- `extra` / `extra_data`（如需扩展字段，使用具体业务含义命名，如 `extracted_entities`、`tool_metadata`）

---

## 二、候选枚举

以下八组候选枚举定义业务含义层的取值范围，各轨道在各自技术实现层可扩展但不得偏离业务语义。

每项枚举的验证状态标记规则：
- **`VERIFIED`**：已有权威来源确认；
- **`UNVERIFIED`**：依赖官方 SDK/宿主能力，当前未取得证据；
- **`PARTIAL`**：部分候选值已确认，其他待定。

### 2.1 source_type（来源类型）

关联 REQ-01 多源数据。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `tool_result` | 官方 AI 助手 Tool 执行结果 | UNVERIFIED | 依赖 C 轨道在麒麟 VM 取证官方 Tool 调用格式 |
| `user_message` | 用户直接对话消息 | UNVERIFIED | 依赖 C 轨道确认宿主消息通道 |
| `agent_response` | 官方 AI 助手最终回复 | UNVERIFIED | 依赖 C 轨道确认宿主回复结构 |
| `system_context` | 系统上下文（桌面状态、窗口焦点等） | UNVERIFIED | 依赖官方 SDK 确认宿主提供的系统上下文能力 |
| `structured_knowledge` | 外部结构化知识注入 | UNVERIFIED | 依赖 E 定义知识注入业务协议 |
| `implicit_feedback` | 隐式反馈（用户操作推断） | UNVERIFIED | 依赖 C 轨道确认宿主埋点能力 |

### 2.2 event_status（事件状态）

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `raw` | 原始事件，尚未处理 | PARTIAL | 业务含义层已确认 |
| `extracting` | 抽取处理中 | PARTIAL | A 轨道抽取 Provider 内部状态，业务含义待 A 确认 |
| `extracted` | 抽取完成 | PARTIAL | A 轨道抽取 Provider 完成标记，业务含义待 A 确认 |
| `embedded` | 已生成 Embedding 向量 | PARTIAL | 待 A/B 确认 Embedding 流程状态管理 |
| `stored` | 已持久化至 SQLite 结构化真源 | PARTIAL | 待 D 确认持久化状态跟踪需求 |
| `failed` | 处理失败 | PARTIAL | 待 A 确认失败重试策略 |
| `ignored` | 已忽略（经敏感过滤或规则过滤） | PARTIAL | 待 E 确认敏感过滤与忽略策略 |

### 2.3 memory_type（记忆类型）

关联 REQ-06 短中长期流转。

**注意**：本枚举仅定义业务语义上的短/中/长期区分，不冻结存储分层边界、流转阈值、回收策略等技术实现。存储分层设计由 D 轨道在 D3 Gate 前确认。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `short_term` | 短期记忆 | UNVERIFIED | 对应当前会话或短时间窗口内的即时上下文，流转边界 `待 D 确认` |
| `medium_term` | 中期记忆 | UNVERIFIED | 对应跨会话但仍属活跃阶段的记忆，流转条件 `待 D 确认` |
| `long_term` | 长期记忆 | UNVERIFIED | 对应经巩固后的稳定知识或持久偏好，归档策略 `待 D 确认` |
| `ephemeral` | 瞬态记忆 | UNVERIFIED | 对应单次 Tool 调用或临时上下文，生命周期不超出当前 Turn，待 E 确认业务必要性 |

### 2.4 preference_scope（偏好作用域）

关联 REQ-02 偏好动态捕捉。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `global` | 全局偏好 | UNVERIFIED | 跨会话、跨主题的通用偏好 |
| `topic` | 主题级偏好 | UNVERIFIED | 限定于特定知识或交互主题 |
| `tool` | 工具级偏好 | UNVERIFIED | 限定于特定 Tool 的调用行为偏好 |
| `session` | 会话级偏好 | UNVERIFIED | 限定于当前会话的临时偏好调整 |
| `time_window` | 时间窗口偏好 | UNVERIFIED | 特定时间段内的偏好（如工作日/非工作日） |

### 2.5 sensitivity（敏感度等级）

关联 REQ-05 敏感过滤与精准遗忘。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `none` | 无敏感信息 | PARTIAL | 业务含义层已确认 |
| `low` | 低敏感（如通用主题偏好） | UNVERIFIED | 待 E 定义敏感度分级标准 |
| `medium` | 中敏感（如工具使用偏好） | UNVERIFIED | 待 E 定义敏感度分级标准 |
| `high` | 高敏感（如个人身份、隐私内容） | UNVERIFIED | 待 E 定义敏感度分级标准 |
| `critical` | 严重敏感（如密钥、密码、证件号） | UNVERIFIED | 待 E 定义识别规则与强制过滤策略 |

### 2.6 conflict_type（冲突类型）

关联 REQ-03 知识整合与冲突。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `contradiction` | 逻辑矛盾 | UNVERIFIED | 两条知识在同一话题上给出互斥结论 |
| `temporal_inconsistency` | 时间不一致 | UNVERIFIED | 同主题的旧知识与新知识存在矛盾 |
| `source_conflict` | 来源冲突 | UNVERIFIED | 不同来源对同一事实给出不同版本 |
| `preference_conflict` | 偏好冲突 | UNVERIFIED | 多条偏好对同一偏好 key 给出冲突取值 |
| `scope_ambiguity` | 作用域歧义 | UNVERIFIED | 同一条知识在不同上下文中有不同解释 |

### 2.7 resolution_status（冲突消解状态）

关联 REQ-03 知识整合与冲突。

| 候选值 | 中文含义 | 验证状态 | 备注 |
|--------|---------|---------|------|
| `detected` | 已检测到冲突 | PARTIAL | 业务含义层已确认 |
| `analyzing` | 冲突分析中 | PARTIAL | 业务含义层已确认 |
| `resolved_auto` | 已自动消解 | UNVERIFIED | 待 B 确认自动消解规则与阈值 |
| `resolved_manual` | 已人工消解 | UNVERIFIED | 待确认人工交互通道是否在范围内 |
| `deferred` | 暂缓处理 | UNVERIFIED | 待 B/E 确认暂缓策略 |
| `unresolvable` | 无法消解 | UNVERIFIED | 待 B/E 确认无法消解的判定标准 |

### 2.8 forget_mode（遗忘模式/粒度）

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
| 来源 | `业务事件`、`系统生成`、`外部输入` 或 `派生计算` |
| 验证状态 | 当前该字段定义的确认程度 |
| 虚构示例 | 脱敏合成数据，不含任何真实用户信息 |

### 3.1 MemorySourceEvent（来源事件对象）

**对应 REQ**：REQ-01 多源数据。

**业务含义**：表示来自官方 AI 助手或系统环境的单次信息输入事件，是多源记忆采集的最初入口。`MemorySourceEvent` 在业务上是 `Preference` 和 `Knowledge` 的上游来源，二者通过 `source_event_id` 关联回本对象。

| 字段名 | 中文含义 | 候选类型 | 必填性 | 来源 | 验证状态 | 虚构示例 |
|--------|---------|---------|--------|------|---------|----------|
| `event_id` | 事件全局唯一标识 | `string` | required | 系统生成 | PARTIAL | `"evt_20260730_a1b2c3"` |
| `source_type` | 来源类型（见枚举 2.1） | `string` | required | 系统生成 | UNVERIFIED | `"tool_result"` |
| `event_status` | 事件处理状态（见枚举 2.2） | `string` | required | 系统生成 | PARTIAL | `"raw"` |
| `memory_type` | 记忆类型（见枚举 2.3） | `string` | conditional | 派生计算 | UNVERIFIED | `"short_term"` |
| `captured_at` | 事件捕获时间 | `timestamp` | required | 系统生成 | PARTIAL | `"2026-07-30T14:30:00+08:00"` |
| `session_id` | 所属会话标识 | `string` | required | 业务事件 | UNVERIFIED | `"sess_d4e5f6"` |
| `actor_id` | 行为主体标识（如用户、系统、Tool） | `string` | required | 业务事件 | UNVERIFIED | `"user_default"` |
| `raw_payload_ref` | 原始载荷引用（摘要或索引引用，不存真实内容） | `string` | optional | 系统生成 | UNVERIFIED | `"ref://events/evt_20260730_a1b2c3/raw"` |
| `content_summary` | 事件内容简要摘要 | `string` | optional | 派生计算 | UNVERIFIED | `"用户通过文件管理器搜索了近期文档"` |
| `turn_id` | 所属对话 Turn 标识 | `string` | conditional | 业务事件 | UNVERIFIED | `"turn_07"` |
| `tool_call_id` | 关联的 Tool 调用标识 | `string` | conditional | 业务事件 | UNVERIFIED | `"tool_file_search_v2_001"` |
| `sensitivity` | 敏感度等级（见枚举 2.5） | `string` | required | 派生计算 | UNVERIFIED | `"low"` |
| `is_sensitive_matched` | 是否命中敏感过滤规则 | `boolean` | required | 派生计算 | UNVERIFIED | `false` |
| `requires_embedding` | 是否需要生成 Embedding 向量 | `boolean` | required | 派生计算 | UNVERIFIED | `true` |
| `has_structured_payload` | 是否包含可抽取的结构化载荷 | `boolean` | optional | 派生计算 | UNVERIFIED | `true` |
| `language_tag` | 内容语言标记（BCP 47） | `string` | optional | 派生计算 | PARTIAL | `"zh-CN"` |

**标注说明**：
- `turn_id` 与 `tool_call_id` 的存在性依赖官方 AI 助手真实事件结构，当前 C 轨道尚未取得麒麟 VM 证据 → `UNVERIFIED`，D3 Gate 前待 C 轨道取证回填。
- `raw_payload_ref` 的具体存储形态（内联摘要 vs. 外部引用 vs. 分片存储）待 D 确认，本稿不冻结 → `待 D 轨道确认`。
- `memory_type` 与 `event_status` 的具体状态机条件与流转规则待 A/E/D 后续 Detail Design 确认，本稿仅定义候选值范围。

### 3.2 Preference（偏好对象）

**对应 REQ**：REQ-02 偏好动态捕捉。

**业务含义**：表示从用户行为中提取的显式或隐式偏好，以 key-value 结构承载，支持置信度评分、衰减策略和激活状态管理，是 Memory Service 向官方 AI 助手提供个性化上下文的核心载体。

| 字段名 | 中文含义 | 候选类型 | 必填性 | 来源 | 验证状态 | 虚构示例 |
|--------|---------|---------|--------|------|---------|----------|
| `preference_id` | 偏好全局唯一标识 | `string` | required | 系统生成 | PARTIAL | `"pref_20260730_x9y0z1"` |
| `preference_scope` | 偏好作用域（见枚举 2.4） | `string` | required | 派生计算 | UNVERIFIED | `"topic"` |
| `preference_key` | 偏好键名（业务语义标识） | `string` | required | 业务事件 | UNVERIFIED | `"file_search_sort_order"` |
| `preference_value` | 偏好值 | `string` | required | 业务事件 | UNVERIFIED | `"by_modified_desc"` |
| `confidence_score` | 置信度评分（0.0–1.0） | `float` | required | 派生计算 | UNVERIFIED | `0.85` |
| `is_active` | 当前是否激活 | `boolean` | required | 系统生成 | PARTIAL | `true` |
| `should_decay` | 是否应随时间衰减 | `boolean` | required | 派生计算 | UNVERIFIED | `false` |
| `decay_after_at` | 衰减生效时间（过期后置信度下降或失效） | `timestamp` | conditional | 派生计算 | UNVERIFIED | `"2026-08-30T00:00:00+08:00"` |
| `evidence_event_ids` | 依据来源事件 ID 列表 | `list[string]` | required | 系统生成 | UNVERIFIED | `["evt_20260730_a1b2c3", "evt_20260729_d4e5f6"]` |
| `created_at` | 创建时间 | `timestamp` | required | 系统生成 | PARTIAL | `"2026-07-30T14:30:00+08:00"` |
| `updated_at` | 最后更新时间 | `timestamp` | required | 系统生成 | PARTIAL | `"2026-07-30T15:00:00+08:00"` |
| `requires_confirmation` | 是否需要用户显式确认 | `boolean` | required | 派生计算 | UNVERIFIED | `false` |
| `extracted_entities` | 关联的实体列表（用于语义关联） | `list[string]` | optional | 派生计算 | UNVERIFIED | `["文件管理器", "排序方式", "修改日期"]` |

**标注说明**：
- `confidence_score` 的量化方法（基于频率/时序/行为模式加权）和具体阈值由 A/E 在 Embedding 提取 Provider 设计阶段确认，本稿仅定义字段语义 → `待 A/E 确认`。
- `decay_after_at` 与 `should_decay` 的具体衰减函数（线性/指数/阶梯）待 A/E 在偏好模型选型 ADR 中确认，本稿不冻结算法 → `待 A/E 确认`。
- `preference_key` 和 `preference_value` 的具体 schema 取决于官方 AI 助手偏好模型，当前官方模型未提供 → `UNVERIFIED`。

### 3.3 Knowledge（结构化知识对象）

**对应 REQ**：REQ-03 知识整合与冲突、REQ-04 端侧 Embedding 与轻量检索。

**业务含义**：表示经过抽取和归一化后的结构化知识条目，是语义检索和 RRF 排序的最小知识单元。本对象仅定义业务字段，不冻结 SQLite 存储布局、Vector 索引结构和 FTS5 分词策略。

| 字段名 | 中文含义 | 候选类型 | 必填性 | 来源 | 验证状态 | 虚构示例 |
|--------|---------|---------|--------|------|---------|----------|
| `knowledge_id` | 知识条目全局唯一标识 | `string` | required | 系统生成 | PARTIAL | `"kn_20260730_m3n4o5"` |
| `memory_type` | 记忆类型（见枚举 2.3） | `string` | required | 派生计算 | UNVERIFIED | `"medium_term"` |
| `source_event_id` | 来源事件标识，关联 `MemorySourceEvent.event_id` | `string` | required | 系统生成 | UNVERIFIED | `"evt_20260730_a1b2c3"` |
| `content_summary` | 知识内容摘要（可检索字段） | `string` | required | 派生计算 | UNVERIFIED | `"用户频繁通过文件管理器按修改日期降序排列文件"` |
| `content_ref` | 完整内容引用（不冻结具体存储形态） | `string` | optional | 系统生成 | UNVERIFIED | `"ref://knowledge/kn_20260730_m3n4o5/full"` |
| `primary_category` | 主分类标签 | `string` | optional | 派生计算 | UNVERIFIED | `"文件操作"` |
| `language_tag` | 内容语言标记（BCP 47） | `string` | optional | 派生计算 | PARTIAL | `"zh-CN"` |
| `confidence_score` | 置信度评分（0.0–1.0） | `float` | required | 派生计算 | UNVERIFIED | `0.72` |
| `requires_embedding` | 是否需要生成 Embedding 向量 | `boolean` | required | 派生计算 | UNVERIFIED | `true` |
| `created_at` | 创建时间 | `timestamp` | required | 系统生成 | PARTIAL | `"2026-07-30T14:30:00+08:00"` |
| `updated_at` | 最后更新时间 | `timestamp` | required | 系统生成 | PARTIAL | `"2026-07-30T14:30:00+08:00"` |
| `is_outdated` | 是否已过时 | `boolean` | required | 派生计算 | UNVERIFIED | `false` |
| `superseded_by_id` | 替代此条目的知识 ID | `string` | optional | 系统生成 | UNVERIFIED | `null` |
| `access_count` | 累计被检索/使用的次数 | `integer` | optional | 派生计算 | PARTIAL | `3` |
| `last_accessed_at` | 最后被访问时间 | `timestamp` | optional | 系统生成 | PARTIAL | `"2026-07-30T16:00:00+08:00"` |
| `extracted_entities` | 抽取的实体列表 | `list[string]` | optional | 派生计算 | UNVERIFIED | `["文件管理器", "文件排序", "修改日期"]` |

**标注说明**：
- `content_ref` 不冻结具体存储形态（内联/外部分片/SQLite BLOB/文件系统引用），具体实现由 D 轨道在存储布局 ADR 中确认 → `待 D 确认`。
- `requires_embedding` 产生的 Embedding 向量是否在同一语义对象中承载还是分离为独立 Vector 索引条目，由 B 轨道在 Vector 索引设计阶段确认 → `待 B 确认`。（`README.md` 明确 Vector 非真源、可从 SQLite 重建。）
- `access_count` 与 `last_accessed_at` 的具体统计窗口和精度待 D 确认，本稿仅定义业务语义，不冻结实现细节 → `待 D 确认`。

### 3.4 Conflict（冲突对象）

**对应 REQ**：REQ-03 知识整合与冲突。

**业务含义**：表示两条或多条知识条目之间检测到的语义或事实不一致，用于驱动冲突消解流程。本对象是业务层面的冲突记录，不冻结具体的消解算法、RRF 融合权重和存储布局。

| 字段名 | 中文含义 | 候选类型 | 必填性 | 来源 | 验证状态 | 虚构示例 |
|--------|---------|---------|--------|------|---------|----------|
| `conflict_id` | 冲突全局唯一标识 | `string` | required | 系统生成 | PARTIAL | `"cfl_20260730_p7q8r9"` |
| `conflict_type` | 冲突类型（见枚举 2.6） | `string` | required | 派生计算 | UNVERIFIED | `"temporal_inconsistency"` |
| `left_knowledge_id` | 冲突左方的知识条目 ID | `string` | required | 系统生成 | PARTIAL | `"kn_20260730_m3n4o5"` |
| `right_knowledge_id` | 冲突右方的知识条目 ID | `string` | required | 系统生成 | PARTIAL | `"kn_20260728_a1b2c3"` |
| `involved_knowledge_ids` | 涉及的全部知识条目 ID（用于多知识冲突） | `list[string]` | optional | 系统生成 | UNVERIFIED | `["kn_20260730_m3n4o5", "kn_20260728_a1b2c3"]` |
| `conflict_summary` | 冲突内容简要描述 | `string` | required | 派生计算 | UNVERIFIED | `"知识条目 kn_*_m3n4o5 表明用户偏好按修改日期排序，而 kn_*_a1b2c3 表明用户偏好按文件名排序"` |
| `resolution_status` | 消解状态（见枚举 2.7） | `string` | required | 系统生成 | PARTIAL | `"detected"` |
| `resolution_strategy` | 消解策略（保留较新值/保留较高置信度/标记为冲突待确认/合并） | `string` | conditional | 派生计算 | UNVERIFIED | `"keep_higher_confidence"` |
| `is_auto_resolvable` | 是否可自动消解 | `boolean` | required | 派生计算 | UNVERIFIED | `true` |
| `resolution_confidence` | 消解结果的置信度（0.0–1.0） | `float` | optional | 派生计算 | UNVERIFIED | `0.68` |
| `detected_at` | 冲突检测时间 | `timestamp` | required | 系统生成 | PARTIAL | `"2026-07-30T15:00:00+08:00"` |
| `resolved_at` | 冲突消解时间 | `timestamp` | conditional | 系统生成 | PARTIAL | `null` |
| `resolved_by` | 消解执行方标识（规则/模块/轨道标识，非自然人） | `string` | conditional | 系统生成 | UNVERIFIED | `"conflict_resolver_v1"` |

**标注说明**：
- `conflict_type` 中 `contradiction`（逻辑矛盾）与 `temporal_inconsistency`（时间不一致）的判定阈值和判别逻辑由 B 轨道在冲突检测模块设计阶段确认 → `待 B 确认`。
- `resolution_strategy` 的具体策略集合和优先级排序待 B/E 在 ADR 中确认 → `待 B/E 确认`。
- `is_auto_resolvable` 的判定标准（置信度阈值/差异幅度/类型判定）待 B/E 确认 → `待 B/E 确认`。

### 3.5 ForgetPlan（遗忘计划对象）

**对应 REQ**：REQ-05 敏感过滤与精准遗忘。

**业务含义**：表示一次有计划、可追踪的遗忘操作，覆盖单条记录、会话级、主题级、时间窗口级和全量重置等遗忘粒度。遗忘计划对象记录遗忘的目标范围、执行状态和级联清理要求，是本系统精准遗忘能力的核心业务记录。

| 字段名 | 中文含义 | 候选类型 | 必填性 | 来源 | 验证状态 | 虚构示例 |
|--------|---------|---------|--------|------|---------|----------|
| `forget_plan_id` | 遗忘计划全局唯一标识 | `string` | required | 系统生成 | PARTIAL | `"fgp_20260730_s1t2u3"` |
| `forget_mode` | 遗忘模式/粒度（见枚举 2.8） | `string` | required | 外部输入 | PARTIAL | `"single_item"` |
| `target_type` | 遗忘目标的业务类型（`knowledge`、`preference`、`event`、`all`） | `string` | required | 外部输入 | UNVERIFIED | `"knowledge"` |
| `target_id` | 精确遗忘的目标 ID（`forget_mode` 为 `single_item` 时必填） | `string` | conditional | 外部输入 | PARTIAL | `"kn_20260730_m3n4o5"` |
| `target_session_id` | 目标会话 ID（`forget_mode` 为 `session` 时必填） | `string` | conditional | 外部输入 | UNVERIFIED | `"sess_d4e5f6"` |
| `target_topic` | 目标主题/分类（`forget_mode` 为 `topic` 时必填） | `string` | conditional | 外部输入 | UNVERIFIED | `"文件操作"` |
| `target_time_range` | 目标时间范围（`forget_mode` 为 `time_window` 时必填） | `string` | conditional | 外部输入 | UNVERIFIED | `"2026-07-01T00:00:00/2026-07-31T23:59:59"` |
| `created_at` | 遗忘计划创建时间 | `timestamp` | required | 系统生成 | PARTIAL | `"2026-07-30T16:00:00+08:00"` |
| `executed_at` | 实际执行时间 | `timestamp` | optional | 系统生成 | PARTIAL | `"2026-07-30T16:00:05+08:00"` |
| `status` | 执行状态（`pending`、`in_progress`、`completed`、`failed`、`rolled_back`） | `string` | required | 系统生成 | PARTIAL | `"completed"` |
| `is_cascade` | 是否级联清理关联记忆（如遗忘事件时同时清理其派生的 Knowledge/Preference） | `boolean` | required | 外部输入 | UNVERIFIED | `true` |
| `has_vector_cleanup` | 是否需要同步清理 Vector 索引 | `boolean` | required | 派生计算 | UNVERIFIED | `true` |
| `requires_confirmation` | 是否需要用户确认后执行 | `boolean` | required | 外部输入 | UNVERIFIED | `false` |
| `affected_count` | 实际影响的记录数量 | `integer` | optional | 系统生成 | PARTIAL | `5` |
| `rollback_plan_id` | 回滚计划 ID（记录执行前快照的引用，用于失败回滚） | `string` | optional | 系统生成 | UNVERIFIED | `"rb_fgp_20260730_s1t2u3"` |

**标注说明**：
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

### 4.2 本稿不冻结的技术实现

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

### 4.3 标注约定

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
- `Knowledge` 的检索相关字段（`content_summary`、`extracted_entities`、`primary_category`、`language_tag`）是否覆盖 FTS5 全文搜索和元数据过滤的业务需求
- `Conflict` 的冲突检测字段（`conflict_type`、`is_auto_resolvable`、`resolution_confidence`）是否支持应用层 RRF 排序与融合的业务边界
- `ForgetPlan.has_vector_cleanup`、`is_cascade` 是否对齐 Vector 索引清理和一致性保证策略
- `memory_type`（短/中/长期）在检索层的区分语义是否匹配 B 的召回边界设计

**产出形式**：D3 审查前提交 B 轨道字段差异清单，逐字段给出「符合/需修订/需新增」标记及修订建议。

**当前状态**：`UNVERIFIED/PENDING`（B 轨道 Vector 索引与 RRF 均未开始实现，检索过滤字段未设计）

### 5.3 C 轨道（OS Agent Hook、MemoryClient、Tool/Turn Adapter）

**核对内容**：
- `MemorySourceEvent.source_type`、`turn_id`、`tool_call_id`、`session_id`、`actor_id` 是否在真实官方 AI 助手 Tool/Turn/Context 事件中存在对应字段，字段语义是否一致
- `source_type` 六项候选值是否覆盖真实宿主可提供的全部事件类型
- `MemorySourceEvent.raw_payload_ref` 的事件封装方式是否与 C 的 Hook 数据流兼容

**产出形式**：D3 审查前提交 C 轨道字段核对与取证计划，逐字段标注「已在 VM 取证确认 / 待 VM 取证 / 不存在对应宿主字段」，对不存在字段给出替代方案建议。

**当前状态**：`UNVERIFIED/PENDING`（官方 AI 助手真实事件结构尚未取得麒麟 VM 证据，全部 C 核对字段均处于 UNVERIFIED 状态）

### 5.4 D 轨道（IPC、SQLite、Outbox、成品化）

**核对内容**：
- 五个核心业务对象的持久化相关字段（`*_id`、`*_at`、状态字段）与 SQLite 存储布局的映射可行性
- `MemorySourceEvent.raw_payload_ref`、`Knowledge.content_ref` 等引用字段的持久化策略（内联/外部分片/文件系统引用）
- `ForgetPlan` 的遗忘执行状态和回滚方案在 SQLite 事务模型中的可行性
- 全部 `system_generated` 字段的 ID 生成策略和时间戳精度与 IPC 协议的兼容性

**产出形式**：D3 审查前提交 D 轨道字段映射清单，逐字段给出「已纳入 IPC 协议 / 已纳入 SQLite schema 草案 / 需修订业务字段定义 / 需新增 IPC 字段」标记。

**当前状态**：`UNVERIFIED/PENDING`（D 轨道尚未开始 IPC JSON Schema 和 SQLite 表设计）

---

## 六、未确认能力与人工决策待办

以下事项需团队成员在后续阶段人工决策，本 v0.1 DRAFT 仅如实记录当前已知的未确认项。

| 编号 | 事项 | 关联 REQ | 责任轨道 | 计划窗口 |
|------|------|---------|---------|---------|
| HD-SCHEMA-01 | 导入赛题原文、总体架构 SOP、官方 SDK 与 OS Agent 能力边界基线至 `docs/baseline/`，用于复核全稿字段 | REQ-01–07 | 团队/E | D3 Gate 前 |
| HD-SCHEMA-02 | C 轨道在麒麟 VM 取证官方 AI 助手 Tool/Turn/Context 真实事件结构，回填 `MemorySourceEvent` 中 `turn_id`、`tool_call_id`、`actor_id` 等字段的 UNVERIFIED 状态 | REQ-01 | C | L2 取证窗口 |
| HD-SCHEMA-03 | A/E 确认 `Preference.confidence_score` 计算模型与 `should_decay`/`decay_after_at` 衰减策略的语义定义 | REQ-02 | A·E | D3 Gate 前 |
| HD-SCHEMA-04 | B 确认 `Conflict` 类型判定阈值（`contradiction` v.s. `temporal_inconsistency` 的判别逻辑）与 `is_auto_resolvable` 判定标准 | REQ-03 | B | D3 Gate 前 |
| HD-SCHEMA-05 | B 确认 Vector 索引与 SQLite 真源的一致性策略（增量更新/全量重建），回填 `ForgetPlan.has_vector_cleanup` 的实现可行性 | REQ-04 | B | D3 Gate 前 |
| HD-SCHEMA-06 | E 确认 `ForgetPlan.is_cascade` 的遗忘级联范围与 `forget_mode.full_reset` 的安全边界 | REQ-05 | E | D3 Gate 前 |
| HD-SCHEMA-07 | D 确认 `memory_type` 短/中/长期的分层边界（时间阈值/访问频率/重要性混合）和存储分层布局 | REQ-06 | D | D3 Gate 前 |
| HD-SCHEMA-08 | B 确认检索评测指标基线（Recall@K、MRR、NDCG），与 `Knowledge` 被检索字段的业务覆盖度对齐 | REQ-07 | B | D3 Gate 前 |
| HD-SCHEMA-09 | D 确认 `*_id` 全局唯一标识的生成策略（UUID v4/UUID v7/纳秒时间戳+随机数）与 IPC 协议的兼容性 | REQ-01–06 | D | D3 Gate 前 |
| HD-SCHEMA-10 | 是否将本文档链接入 `docs/architecture/README.md` 和 `docs/README.md` 的索引（独立维护任务，不在本任务范围） | — | 团队 | 后续维护 |

---

## 七、版本与冻结门槛

### 变更记录

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|---------|------|
| v0.1 | 2026-07-30 | DRAFT 初稿，建立五核心业务对象字段初稿、命名规则、八组候选枚举、反馈责任矩阵和未确认能力清单。基于 README、各模块 README 和赛题追踪矩阵 v0.1 事实编写。所有涉及官方宿主能力的字段均如实标记 UNVERIFIED/PARTIAL。 | E 轨道 |

### 冻结为 v1.0 的条件

以下条件**全部满足**后，本文档方可冻结为 v1.0 版本，成为记忆业务层的正式基线：

1. 赛题原文、总体架构 SOP、官方 SDK 与 OS Agent 能力边界基线文档已导入 `docs/baseline/`，且 `docs/baseline/README.md` 中六项文档状态更新为「已导入」
2. D3 Gate 经 D/E Reviewer 审查通过，且审查结论文档化
3. A/B/C/D 各轨道字段差异清单已提交且全部闭合（差异项须有明确决议）
4. 官方 AI 助手真实 Tool/Turn/Context 事件结构经麒麟 VM 取证，C 轨道已回填 `MemorySourceEvent` 中相关字段的验证状态
5. 六章「未确认能力与人工决策待办」中 HD-SCHEMA-01 至 HD-SCHEMA-09 均有明确决议
6. Evidence Reviewer 确认文档中所有字段的验证状态标注与当时实际证据等级一致
7. 本文档中各枚举章节中所有的「UNVERIFIED」标记在实际确认后更新为「VERIFIED」，或确认为不可能确认后标记为「NOT_APPLICABLE」

在满足以上条件之前，本文档不视为冻结基线，不得作为最终技术实现的唯一依据。

---

> **本文档到此结束。后续版本将在 D3 Gate 审查后根据 A–E 轨道反馈修订。**
