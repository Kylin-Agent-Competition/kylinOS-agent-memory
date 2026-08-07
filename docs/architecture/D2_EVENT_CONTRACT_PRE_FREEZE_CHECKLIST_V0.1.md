# Day2 E 轨道 Gate 0 事件契约冻结前检查表（v0.1 DRAFT）

- **版本**：v0.1
- **状态**：DRAFT
- **阶段定位**：Day2 / E 轨道 / Gate 0 输入
- **用途**：为 C/D 真实 Spike 审查与 D3 共享契约冻结提供业务、安全、证据、冲突、遗忘与幂等检查依据，覆盖 `MemoryContext`、`ToolExecutionEvent`、`TurnFinalizedEvent` 及 D 轨道 UDS/IPC 承载与失败语义
- **冻结门槛**：本文件是 D3 冻结输入，**不是**已冻结的 C++ 结构体、JSON 协议、数据库表或 SDK 事实。D3 Gate 前不得视为冻结；未经 C 轨道麒麟取证、基线 DOCX（赛题原文/总体架构 SOP/官方 SDK 能力边界）导入仓库、D/E Reviewer 审查，不得冻结为 v1.0
- **依据来源**：
  - `README.md`（项目定位、技术路线、责任轨道 A–E、当前阶段与明确未完成项）
  - `docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md`（Day1 记忆业务 Schema v0.1 DRAFT，定义 `MemorySourceEvent` 与五个原始业务对象及 14 个公共字段雏形）
  - `datasets/ANNOTATION_GUIDELINE_V0.1.md`（Day1 标注规范 v0.1 DRAFT，`execution_status` 业务语义与 S-01..S-09 敏感边界）
  - `docs/project-management/REQUIREMENT_TRACEABILITY_MATRIX.md`（Day1 追踪矩阵 v0.1 DRAFT，业务/SDK 双轴证据状态口径）
  - `memory-service/`、`cpp-bridge/`、`memory-client/`、`os-agent-integration/` 模块 README（C/D 轨道职责边界，当前均「仅建立目录和职责边界，尚无生产实现」）
- **局限声明**：
  - 基线 DOCX（赛题原文、总体架构 SOP v1.1、官方 SDK 与 OS Agent 能力边界）尚未导入仓库（`docs/baseline/README.md` 均标注「待人工导入」），本文件涉及的字段语义待权威基线终审
  - C 轨道麒麟 VM 取证未执行，`MemoryContext`/`ToolExecutionEvent`/`TurnFinalizedEvent` 均为**业务候选对象**，不是官方 SDK 原生字段，也不是已批准的最终协议
  - 本文件仅形成冻结前候选，所有字段、枚举、必填性均为候选建议，D3 才正式冻结

---

## 一、范围与对象

- **检查对象**：
  - `MemoryContext`：Memory Service 组装后注入 `model_request` 的上下文承载对象
  - `ToolExecutionEvent`：单次 Tool 调用执行结果事件（来源 `tool_result` 的派生承载）
  - `TurnFinalizedEvent`：单个 Turn 收尾事件（Turn 边界与重试语义承载）
  - D 轨道 UDS/IPC 承载与失败语义（`protocol_version`、`request_id`、幂等、取消、结构化错误、断线重连、用户身份边界等）
- **非目标**：不冻结 D3 才允许冻结的正式公共协议、数据库 Schema、错误码或 IPC 版本；不修改 Day1 业务 Schema、追踪矩阵、标注规范；不修改 C/D 轨道 C++/Python/UDS/Hook/部署/KYSEC/Runtime 代码
- **字段命名基线**：沿用 `MEMORY_BUSINESS_SCHEMA_V0.1.md` 的 snake_case 命名与 `*_id`/`*_at` 规则；`execution_status` 业务语义参照 `ANNOTATION_GUIDELINE_V0.1.md` §2.3；证据状态使用追踪矩阵双轴口径（业务状态 `PENDING/UNVERIFIED/PARTIAL`；SDK 能力状态 `UNTESTED/SOURCE_VERIFIED/ABI_VERIFIED/PARTIAL/NOT_FOUND/BLOCKED/HOST_VERIFIED`）

---

## 二、C/D/E 责任边界

| 检查对象 | 提供轨道 | 审查轨道 | 责任人占位 | 说明 |
|----------|----------|----------|------------|------|
| `MemoryContext` 字段 | C（宿主事件结构取证）、E（业务语义） | C、D、E | 待任务分配 | 注入 `model_request` 的上下文承载；跨 Turn 复用策略待 C/D 决策 |
| `ToolExecutionEvent` 字段 | C（真实 Tool 结果取证）、E（业务/安全规则） | C、D、E | 待任务分配 | `execution_status` 真实语义与成功知识判定 |
| `TurnFinalizedEvent` 字段 | C（Turn 边界取证）、E（收尾语义） | C、D、E | 待任务分配 | Turn 收尾、停止原因与重试关联 |
| UDS/IPC 承载项 | D（协议草案） | D、C、E | 待任务分配 | 当前 D Day1 PR 未合并 → 相关项 `BLOCKED` |
| 安全/敏感/遗忘/幂等规则 | E | E、D | 待任务分配 | S-01..S-09、已遗忘排除、幂等去重 |

---

## 三、公共事件字段检查表

以下 14 个字段为三类事件候选公共字段，均属候选建议，非已冻结协议。每行十列：字段/要求、中文语义、适用事件、提供轨道、必填性候选、业务用途、所需证据、当前证据状态、D3 建议、未解决责任人。

| 字段/要求 | 中文语义 | 适用事件 | 提供轨道 | 必填性候选 | 业务用途 | 所需证据 | 当前证据状态 | D3 建议 | 未解决责任人 |
|-----------|----------|----------|----------|-------------|----------|----------|---------------|----------|----------|--------------|
| `schema_version` | 事件契约版本号，用于版本识别与兼容 | 三类事件公共字段 | E（定义）、D（UDS 承载） | required | 证据追踪 | C 麒麟取证宿主版本字段 + D UDS 草案 | UNTESTED | 候选；D3 前与 D 协议草案核对 | 待 E/D |
| `event_id` | 事件全局唯一标识 | 三类事件公共字段 | C（宿主）、E | required | 证据追踪、幂等去重 | C 取证宿主事件结构 | UNTESTED | 候选；ID 生成策略待 D（HD-SCHEMA-09） | 待 D |
| `trace_id` | 跨服务追踪标识，关联宿主、Memory Service 与各轨道链路 | 三类事件公共字段 | C、D | optional | 证据追踪 | C 取证 + D UDS 请求链路 | UNTESTED | 候选；与 UDS 请求头关联待 D | 待 D |
| `user_id` | 数据归属用户标识（用户隔离键） | 三类事件公共字段 | C（宿主业务事件） | required | 跨用户隔离、安全授权 | C 取证宿主 user 语义 | UNTESTED | 候选；`*禁止模型生成` | 待 C |
| `session_id` | 所属会话标识 | 三类事件公共字段 | C | required | 证据追踪、精准遗忘 | C 取证 | UNTESTED | 候选 | 待 C |
| `turn_id` | 所属对话 Turn 标识 | 三类事件公共字段 | C | conditional | 证据追踪 | C 取证宿主 Turn 边界 | UNTESTED | 候选；触发条件同 Schema §3.1 | 待 C |
| `source_type` | 来源类型（Schema 枚举 2.1 七值） | 三类事件公共字段 | C、E | required | 证据追踪、冲突处理 | C 取证七值覆盖情况 | UNTESTED | 候选；SOP v1.1 导入后复核 | 待 C/E |
| `event_type` | 事件消息粒度类型（Schema 枚举 2.2 三值） | 三类事件公共字段 | C、E | required | 证据追踪 | C 取证消息角色 | UNTESTED | 候选；与 `source_type` 分层待 C 确认 | 待 C/E |
| `occurred_at` | 事件在宿主侧实际发生时间 | 三类事件公共字段 | C（业务事件） | required | 证据追踪、冲突处理 | C 取证宿主时间字段 | UNTESTED | 候选；`*禁止模型生成` | 待 C |
| `collected_at` | 事件捕获入库时间 | 三类事件公共字段 | D（系统生成） | required | 证据追踪 | D 确认采集链路 | UNTESTED | 候选；与 Day1 `captured_at` 语义差异见「字段差异记录区」 | 待 D |
| `source_reference` | 来源记录定位引用（非原始载荷） | 三类事件公共字段 | C、E | conditional | 证据追踪、精准遗忘 | C 取证 + D 引用存储策略 | UNTESTED | 候选；与 `raw_payload_ref` 语义区分 | 待 C/D |
| `consent_scope` | 数据使用与遗忘同意范围标注 | 三类事件公共字段 | C、E | required | 安全授权、精准遗忘 | C 取证 + E 确认同意模型 | UNTESTED | 候选 | 待 E |
| `idempotency_key` | 接入幂等与去重键 | 三类事件公共字段 | C、D | required | 幂等去重 | C 取证 + D UDS 幂等机制 | UNTESTED | 候选；**不可由 `event_id` 替代** | 待 D |
| `sensitivity` | 敏感度等级（Schema 枚举 2.10 五值） | 三类事件公共字段 | E（终判） | required | 安全授权 | E 确认分级标准 | PARTIAL | 候选；终判不得模型覆写 | 待 E |

**公共字段候选红线**：
- `user_id`、`occurred_at` 等时间与归属字段**禁止由模型/LLM 生成**，必须来自宿主侧业务事件或外部输入（对齐 Schema §4.2 禁止模型生成字段清单）。
- `idempotency_key` 用于接入侧幂等与去重，**不可由 `event_id` 替代其业务语义**。
- `sensitivity` 最终定级由敏感过滤规则引擎产出，模型不得覆写或降级（对齐 Schema §4.2 安全终判）。

---

## 四、MemoryContext 字段检查表

`MemoryContext` 为注入 `model_request` 的上下文承载对象。**原文隔离红线**：UI 与聊天数据库保留原始用户文本，Memory Context 只能进入 `model_request`；普通日志不得保存完整敏感 Context。

| 字段/要求 | 中文语义 | 适用事件 | 提供轨道 | 必填性候选 | 业务用途 | 所需证据 | 当前证据状态 | D3 建议 | 未解决责任人 |
|-----------|----------|----------|----------|-------------|----------|----------|---------------|----------|----------|--------------|
| `query_id` | 本次上下文组装请求标识 | MemoryContext | D（IPC 请求） | required | 证据追踪、幂等去重 | D UDS 请求草案 | UNTESTED | 候选；与 `request_id` 关联待 D | 待 D |
| `selected_memory_ids` | 注入记忆条目 ID 列表 | MemoryContext | C/D/E | required | 证据追踪 | C/D 集成链路 + SQLite 回源 | UNTESTED | 候选；回源 SQLite 当前版本，不得用陈旧 Vector 元数据 | 待 D |
| `context_version` | 上下文版本号 | MemoryContext | E（策略）、D（承载） | required | 冲突处理 | E 确认版本升级策略 | UNTESTED | 候选；跨 Turn 复用策略待 C/D 决策 | 待 C/D |
| `token_budget` | 允许注入的 Token 预算上限 | MemoryContext | E/D | required | 安全授权 | D 确认 IPC 消息大小约束 | UNTESTED | 候选；与 D IPC 大小约束对齐 | 待 D |
| `actual_token_count` | 实际注入 Token 数 | MemoryContext | D/E | required | 证据追踪 | D 确认计数链路 | UNTESTED | 候选 | 待 D |
| `sensitive_excluded_count` | 因敏感过滤排除的条目数 | MemoryContext | E | conditional | 安全授权、精准遗忘 | E 确认敏感过滤规则 | UNTESTED | 候选；对应 S-01..S-09 | 待 E |
| `forgotten_excluded_count` | 因已遗忘排除的条目数 | MemoryContext | E/D | conditional | 精准遗忘 | D 确认遗忘后检索排除 | UNTESTED | 候选；已遗忘记忆不得注入 context | 待 E/D |
| `conflict_excluded_count` | 因冲突待消解排除的条目数 | MemoryContext | B/E | conditional | 冲突处理 | B/E 确认冲突排除策略 | UNTESTED | 候选；冲突未消解不注入 | 待 B/E |
| `injection_status` | 注入状态候选（`prepared`/`injected`/`failed`/`skipped`） | MemoryContext | D/E | required | 证据追踪 | D 确认注入链路状态 | UNTESTED | 候选非冻结枚举；待 D/E 审 | 待 D/E |

**说明**：`selected_memory_ids` 注入前必须回源 SQLite 当前版本并复核 `user_id`、状态、有效期、敏感等级与冲突状态（对齐 D2 统一候选 `d2-retrieval-candidate-unified.md` §2.2 强制不变量）；`forgotten_excluded_count` 与 `conflict_excluded_count` 为业务用途映射的检查计数，D3 前不冻结其精确统计口径。

---

## 五、ToolExecutionEvent 字段检查表

`ToolExecutionEvent` 为单次 Tool 调用执行结果事件。**`execution_status` 至少区分 `success`/`failure`/`cancelled`/`timeout`**；只有真实 Tool 成功证据才允许形成成功知识；不得把模型自述当真实 Tool 结果。

| 字段/要求 | 中文语义 | 适用事件 | 提供轨道 | 必填性候选 | 业务用途 | 所需证据 | 当前证据状态 | D3 建议 | 未解决责任人 |
|-----------|----------|----------|----------|-------------|----------|----------|---------------|----------|----------|--------------|
| `tool_call_id` | Tool 调用标识 | ToolExecutionEvent | C | required | 证据追踪 | C 麒麟取证真实 Tool 调用 | UNTESTED | 候选 | 待 C |
| `tool_name` | Tool 名称 | ToolExecutionEvent | C | required | 证据追踪、冲突处理 | C 取证 | UNTESTED | 候选 | 待 C |
| `arguments_ref` | 调用参数引用（须脱敏） | ToolExecutionEvent | C | conditional | 安全授权 | C 取证 + E 敏感红线 | UNTESTED | 候选；高敏参数不得明文进入引用 | 待 C/E |
| `execution_status` | 执行状态：`success`/`failure`/`cancelled`/`timeout` | ToolExecutionEvent | C | required | 证据追踪、冲突处理 | C 取证宿主状态语义 | UNTESTED | 候选；`partial` 是否正式入候选待 D3 复核（标注规范已有 success/partial/failure/timeout） | 待 C/E |
| `result_ref` | 结果引用（脱敏/引用，非内嵌真实正文） | ToolExecutionEvent | C | conditional | 证据追踪 | C 取证真实 Tool 结果 | UNTESTED | 候选；不得以模型自述替代 | 待 C |
| `error_type` | 结构化错误类型 | ToolExecutionEvent | C/D | conditional | 证据追踪 | C 取证 + D 错误结构草案 | UNTESTED | 候选；不冻结 D3 错误码 | 待 C/D |
| `error_message_safe` | 脱敏错误消息 | ToolExecutionEvent | C/E | conditional | 安全授权 | E 确认脱敏规则 | UNTESTED | 候选；不得泄漏敏感原文 | 待 E |
| `side_effect` | 是否产生副作用 | ToolExecutionEvent | C/E | required | 冲突处理、精准遗忘 | C 取证 + E 规则 | UNTESTED | 候选 | 待 E |
| `rollback_required` | 是否需要回滚 | ToolExecutionEvent | D/E | conditional | 冲突处理 | D 确认 SQLite 事务回滚可行性 | UNTESTED | 候选；待 D 确认 | 待 D |
| `rollback_status` | 回滚状态候选（`pending`/`done`/`failed`/`N/A`） | ToolExecutionEvent | D/E | conditional | 冲突处理 | D 确认回滚链路 | UNTESTED | 候选；待 D 确认 | 待 D |
| `started_at` | 执行开始时间 | ToolExecutionEvent | C | required | 证据追踪 | C 取证 | UNTESTED | 候选；`*禁止模型生成` | 待 C |
| `finished_at` | 执行结束时间 | ToolExecutionEvent | C | required | 证据追踪 | C 取证 | UNTESTED | 候选；`*禁止模型生成` | 待 C |

**说明**：`execution_status` 取值参照标注规范 §2.3（`success`/`partial`/`failure`/`timeout`）扩展候选 `cancelled`；`partial` 与 `failure` 的业务边界见第八节规则表。`side_effect`/`rollback_required`/`rollback_status` 与 D 在 SQLite 事务模型中的回滚可行性均标记待 D 确认。

---

## 六、TurnFinalizedEvent 字段检查表

`TurnFinalizedEvent` 为单个 Turn 收尾事件，承载 Turn 边界、停止原因、重试与 Tool 调用关联。

| 字段/要求 | 中文语义 | 适用事件 | 提供轨道 | 必填性候选 | 业务用途 | 所需证据 | 当前证据状态 | D3 建议 | 未解决责任人 |
|-----------|----------|----------|----------|-------------|----------|----------|---------------|----------|----------|--------------|
| `final_message_id` | 收尾消息标识 | TurnFinalizedEvent | C | conditional | 证据追踪 | C 取证 | UNTESTED | 候选 | 待 C |
| `is_final` | 是否为最终收尾（含重试/续轮语境） | TurnFinalizedEvent | C/E | required | 证据追踪 | C 取证 + E 语义 | UNTESTED | 候选；重试语境下语义待 E 复核 | 待 C/E |
| `finalization_reason` | 收尾原因候选集合 | TurnFinalizedEvent | C/E | conditional | 证据追踪 | C 取证 + E 候选值 | UNTESTED | 候选非冻结枚举 | 待 E |
| `stop_reason` | 停止原因候选（`stop`/`tool`/`timeout`/`cancelled` 等） | TurnFinalizedEvent | C/E | conditional | 证据追踪 | C 取证宿主停止语义 | UNTESTED | 候选非冻结枚举；待 D/E 审 | 待 C/E |
| `retry_of_turn_id` | 重试所指向的 Turn ID | TurnFinalizedEvent | C/E | conditional | 幂等去重 | C 取证重试机制 | UNTESTED | 候选；与幂等去重相关 | 待 C |
| `tool_call_ids` | 本 Turn 内 Tool 调用 ID 列表 | TurnFinalizedEvent | C | conditional | 证据追踪、冲突处理 | C 取证 + 关联上游 `ToolExecutionEvent` | UNTESTED | 候选；与 `ToolExecutionEvent.tool_call_id` 关联 | 待 C |
| `finalized_at` | Turn 收尾时间 | TurnFinalizedEvent | C | required | 证据追踪 | C 取证 | UNTESTED | 候选；`*禁止模型生成` | 待 C |

**说明**：`is_final` 与重试/续轮语境需联动判断（重试中 `retry_of_turn_id` 指向被重试的 Turn，`is_final` 语义待 E 复核）；`tool_call_ids` 须与上游 `ToolExecutionEvent` 关联以支撑证据链与冲突处理。

---

## 七、UDS/IPC 承载检查表

本表全部条目当前标记**待 D 确认或待真实证据**；D Day1 PR 未合并时，D 相关 UDS、Hook、KYSEC、安装与回退项一律为 `BLOCKED`。

| 检查项 | 中文语义 | 适用事件 | 提供轨道 | 必填性候选 | 业务用途 | 所需证据 | 当前证据状态 | D3 建议 | 未解决责任人 |
|--------|----------|----------|----------|-------------|----------|----------|---------------|----------|----------|--------------|
| `protocol_version` | UDS 协议版本号 | 全部 IPC 消息 | D | required | 证据追踪 | D 协议草案 | BLOCKED | 候选；D3 才正式冻结 | 待 D |
| `request_id` | 请求唯一标识 | 全部请求/响应 | D | required | 幂等去重 | D 协议草案 | BLOCKED | 候选 | 待 D |
| `trace_id` | IPC 链路追踪标识 | 全部消息 | D | optional | 证据追踪 | D 协议草案 | BLOCKED | 候选 | 待 D |
| deadline/超时 | 请求截止时间与超时语义 | 请求消息 | D | required | 证据追踪 | D 协议草案 | BLOCKED | 候选 | 待 D |
| 幂等 | 重复请求去重与重放保护 | 写入类请求 | D | required | 幂等去重 | D 协议草案 | BLOCKED | 候选 | 待 D |
| 取消 | 取消语义与取消后的状态处理 | 长任务请求 | D | conditional | 证据追踪 | D 协议草案 | BLOCKED | 候选 | 待 D |
| 结构化错误 | 错误码与错误消息结构 | 响应消息 | D | required | 证据追踪 | D 协议草案 | BLOCKED | 候选；不冻结 D3 错误码 | 待 D |
| 断线重连 | 连接中断与重连策略 | IPC 传输层 | D | conditional | 幂等去重 | D 协议草案 | BLOCKED | 候选 | 待 D |
| 用户身份边界 | `user_id` 身份绑定与跨用户隔离 | 全部请求 | D/C | required | 跨用户隔离、安全授权 | D 协议草案 + C 取证 | BLOCKED | 候选；身份绑定待 D，禁止模型生成 | 待 D |

---

## 八、失败/取消/超时/部分执行/副作用/回滚业务规则表

| 场景 | 业务处理规则 | 适用对象 | 是否形成记忆 | 依据 | 当前证据状态 | D3 建议 |
|------|--------------|----------|--------------|------|---------------|----------|
| success | 仅真实 Tool 成功证据允许形成成功知识；成功但属瞬态上下文（如一次性查询）不得形成长期记忆 | ToolExecutionEvent | 视复用价值 | 标注规范 §2.3 正例7 | UNTESTED | 待 C 取证后确认 |
| failure | 不得从失败信息推断任何知识；`should_form_memory=false` | ToolExecutionEvent | 否 | 标注规范 §2.3 正例3/反例2 | UNTESTED | 待 C 取证 |
| cancelled | 用户或系统取消；按取消处理，不形成成功知识 | ToolExecutionEvent | 否 | 标注规范 §2.3 扩展候选 | UNTESTED | 待 C 取证 |
| timeout | 超时等同失败处理；不得以超时结果冒充成功 | ToolExecutionEvent | 否 | 标注规范 §2.3 | UNTESTED | 待 C 取证 |
| partial | 部分成功；仅成功部分可形成知识，失败项不得记录敏感文件名/内容（如 `[REDACTED_FILENAME]`） | ToolExecutionEvent | 视成功部分 | 标注规范边界案例2 | UNTESTED | `partial` 是否入 D3 正式候选待 E/B/D 复核 |
| side_effect | 有副作用的执行须记录副作用；副作用信息不得由模型自述 | ToolExecutionEvent | 视情况 | Schema §3.4 六档冲突优先级第3档 | UNTESTED | 待 D 确认 SQLite 事务可行性 |
| rollback | 需要回滚时记录 `rollback_required`/`rollback_status`；回滚不视为成功 | ToolExecutionEvent | 否 | Schema §3.4 六档冲突优先级 | UNTESTED | 待 D 确认 |
| 模型自述 | 不得把模型自述当真实 Tool 结果；模型推测为第6档，不得覆盖第1–5档高可信来源 | 全部事件 | 仅候选 | Schema §3.4 六档冲突优先级 | UNTESTED | 待 E/B 复核 |

**红线重申**：
- 只有真实 Tool 成功证据才允许形成成功知识；`execution_status != success`（含 failure/cancelled/timeout）不得形成成功知识。
- 不得把模型自述当真实 Tool 结果（六档冲突优先级中真实 Tool 执行结果为第 3 档，模型自身推测为第 6 档）。
- 失败、取消、超时、部分执行、副作用、回滚在业务上必须分别处理，不得混为一类。

---

## 九、安全/隔离/遗忘/幂等业务用途映射表

| 业务用途 | 关键字段/机制 | 适用对象 | 关联 REQ | 当前证据状态 | D3 建议 |
|----------|----------------|----------|----------|---------------|----------|
| 原文隔离 | UI 与聊天数据库保留原始用户文本；Memory Context 只能进入 `model_request`；普通日志不得保存完整敏感 Context | MemoryContext | REQ-05 | UNTESTED | 待 D 确认日志与 IPC 边界 |
| 跨用户隔离 | `user_id` 硬过滤；跨用户命中在融合前丢弃 | 公共字段/全部对象 | REQ-05、REQ-07 | UNTESTED | 待 C 取证 + D UDS 身份绑定 |
| 安全授权 | `consent_scope`、`sensitivity` 终判、S-01..S-09 敏感类型 | 公共字段/Tool 事件 | REQ-05 | UNTESTED | 待 E 终审分级标准 |
| 敏感过滤 | `sensitive_excluded_count`、`error_message_safe`、`arguments_ref` 脱敏 | MemoryContext/Tool 事件 | REQ-05 | UNTESTED | 待 E 确认脱敏规则 |
| 已遗忘记忆排除 | `forgotten_excluded_count`；已遗忘记忆不得注入 context 或检索返回 | MemoryContext | REQ-05 | UNTESTED | 待 D 确认检索排除链路 |
| 冲突排除 | `conflict_excluded_count`；冲突未消解不注入 context | MemoryContext | REQ-03 | UNTESTED | 待 B/E 确认冲突排除策略 |
| 幂等去重 | `idempotency_key`、`request_id`、`retry_of_turn_id` | 公共字段/UDS/Turn 事件 | REQ-01 | UNTESTED | 待 D 确认 UDS 幂等机制 |

---

## 十、证据输入清单

| 证据项 | 责任轨道 | 当前状态 | 说明 |
|--------|----------|----------|------|
| 官方 Tool/Turn/Context 真实字段取证 | C | UNTESTED | 麒麟 VM 取证后回填三个派生对象字段状态 |
| UDS 协议草案（`protocol_version`/`request_id`/幂等/取消/错误结构/断线重连） | D | BLOCKED | D Day1 PR 未合并 → 阻塞 |
| Hook 集成证据 | C/D | BLOCKED | D Day1 PR 未合并 |
| KYSEC/安装/回退证据 | D | BLOCKED | D Day1 PR 未合并 |
| 安全/敏感/字段复核 | E | UNTESTED | 待 E 终审敏感分级与候选枚举 |
| 基线 DOCX（赛题原文/SOP v1.1/SDK 能力边界） | 团队/E | BLOCKED | 待人工导入 `docs/baseline/` |
| 证据等级守则 | 全部 | — | **无麒麟真实证据时禁止使用 `HOST_VERIFIED`**（追踪矩阵第五节）；本文件所有 SDK 能力相关条目统一 `UNTESTED` 或 `BLOCKED`，不以静态/Mock 证据替代 |

---

## 十一、字段差异记录区

以下模板表记录每个派生字段相对 Day1 `MemorySourceEvent` 的差异（新增/语义不同/待确认），供 D3 前逐项闭合。当前全部标记「待确认」或「候选」，不视为已定差异决议。

| 派生对象/字段 | Day1 对应基准 | 差异类型 | 差异说明 | 待确认方 | 当前状态 |
|---------------|----------------|----------|----------|----------|----------|
| 公共字段 `collected_at` | `MemorySourceEvent.captured_at` | 语义不同/待确认 | 任务要求 `collected_at`，Day1 用 `captured_at`，两词语义是否等价待 D/E 确认 | D/E | 待确认 |
| 公共字段 `user_id`/`session_id`/`turn_id`/`source_type`/`event_type`/`occurred_at`/`source_reference`/`consent_scope`/`idempotency_key`/`sensitivity` | `MemorySourceEvent` 同名或近似字段 | 语义一致（候选） | 派生事件复用 Day1 语义，无新增差异；`idempotency_key` 保持不可由 `event_id` 替代 | C/E | 待确认 |
| `MemoryContext.*` 九字段 | Day1 无对应对象 | 新增 | 注入上下文对象为 D2 派生候选，Day1 未定义 | C/D/E | 待确认 |
| `ToolExecutionEvent.*` 十二字段 | Day1 `tool_call_id` 存在，其余为标注规范 §2.3 字段 | 新增/语义扩展 | `cancelled` 为标注规范未定义的新候选；`side_effect`/`rollback_*` 为新增 | C/D/E | 待确认 |
| `TurnFinalizedEvent.*` 七字段 | Day1 无对应对象 | 新增 | Turn 收尾事件为 D2 派生候选，Day1 未定义 | C/E | 待确认 |

---

## 十二、D3 冻结建议区

| 候选分组 | 冻结建议 | 前置条件 | 当前状态 |
|----------|----------|----------|----------|
| 公共事件字段（与 Day1 Schema 语义一致的字段） | 可在 D3 冻结为候选基线 | 基线 DOCX 导入 + D/E Reviewer 审查 | UNTESTED |
| `MemoryContext` 九字段 | 可在 D3 冻结业务语义；`injection_status` 枚举、`context_version` 跨 Turn 复用策略须先经 C/D 决策 | C 取证 + D 草案 | UNTESTED |
| `ToolExecutionEvent` 十二字段 | 必须等 C 麒麟取证真实 Tool 结构后再冻结；`execution_status` 候选集合（含 `cancelled`/`partial`）须 E/B/D 复核 | C 取证 | UNTESTED |
| `TurnFinalizedEvent` 七字段 | 必须等 C 取证 Turn 边界与重试机制后再冻结；`stop_reason`/`finalization_reason` 枚举待 E 审 | C 取证 | UNTESTED |
| UDS/IPC 全部承载项 | **不得在 D3 前冻结**；须 D 协议草案完成并解除 BLOCKED | D Day1 PR 合并 + D 草案 | BLOCKED |

---

## 十三、阻塞项区

| 编号 | 阻塞项 | 影响范围 | 解除条件 | 对应/复用编号 |
|------|--------|----------|----------|---------------|
| HD-D2E-01 | D Day1 PR 仍存在阻断且尚未合并 | D 相关 UDS、Hook、KYSEC、安装与回退项全部 `BLOCKED` | D Day1 PR 合并通过 | 复用 HD-SCHEMA-09（ID 生成策略） |
| HD-D2E-02 | C 轨道麒麟 VM 官方 Tool/Turn/Context 取证缺位 | 三个派生对象字段证据 `UNTESTED` | C 在麒麟 VM 完成取证回填 | 复用 HD-SCHEMA-02/HD-ANNO-02/HD-SCHEMA-16 |
| HD-D2E-03 | 基线 DOCX（赛题原文/SOP v1.1/SDK 能力边界）未导入 | 字段语义待权威基线终审 | 人工导入 `docs/baseline/` | 复用 HD-01a/HD-SCHEMA-01 |
| HD-D2E-04 | SOP v1.1 未终审 | `source_type` 七值、`event_type` 三值、六档冲突优先级引用需后续复核 | SOP v1.1 实体文件导入 | 复用 HD-SCHEMA-15 |
| HD-D2E-05 | `execution_status` 是否正式新增 `cancelled`/`partial` 候选 | 成功知识判定边界 | E/B/D 在 D3 复核 | 标注规范 §2.3 候选 |
| HD-D2E-06 | `MemoryContext` 是否允许跨 Turn 复用 | `context_version` 升级策略 | C/D 决策 | 本文件第四章 |
| HD-D2E-07 | 本文档是否链接入 `docs/architecture/README.md` 与 `docs/README.md` 索引 | 文档可发现性 | 独立维护任务（不在本任务范围） | 复用 HD-SCHEMA-10 |

---

## 十四、版本与冻结门槛

### 变更记录

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v0.1 | 2026-08-07 | DRAFT 初稿：建立 Day2 E 轨道 Gate 0 事件契约冻结前检查表，覆盖 `MemoryContext`/`ToolExecutionEvent`/`TurnFinalizedEvent` 与 D 轨道 UDS/IPC 承载，含 C/D/E 责任边界、证据输入清单、字段差异记录区、D3 冻结建议区、阻塞项区。所有派生字段均为候选，证据状态统一 `UNTESTED`/`BLOCKED`，未使用 `HOST_VERIFIED`。 | E 轨道 |

### 冻结为 v1.0 的条件

以下条件**全部满足**后，本文件方可冻结为 v1.0：

1. 基线 DOCX（赛题原文、总体架构 SOP v1.1、官方 SDK 与 OS Agent 能力边界）已导入 `docs/baseline/` 并完成版本核验
2. C 轨道已在麒麟 VM 取证官方 Tool/Turn/Context 真实事件结构，三个派生对象字段状态已回填
3. D 轨道 UDS/IPC 协议草案完成，D Day1 PR 合并，`BLOCKED` 项解除
4. D3 Gate 经 D/E Reviewer 审查通过，且审查结论文档化
5. 字段差异记录区（第十一章）逐项闭合且有明确决议
6. Evidence Reviewer 确认本文件所有证据状态标注与当时实际证据等级一致，无 `HOST_VERIFIED` 虚标

在满足以上条件之前，本文件不视为冻结基线，**不得作为最终 C++ 结构体、JSON 协议、数据库表或 SDK 事实的唯一依据**。

---

> **本文档到此结束。后续版本将在 D3 Gate 审查、C 麒麟取证、D 协议草案与基线 DOCX 导入后根据 A–E 轨道反馈修订。**
