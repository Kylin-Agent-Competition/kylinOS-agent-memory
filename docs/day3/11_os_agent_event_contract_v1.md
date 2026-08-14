# 11 轨道 C — OS Agent 事件契约 v1 候选

> **状态：`FROZEN_CANDIDATE / BLOCKED_FOR_FINAL_FREEZE`**
> 本文冻结 D3-C 可审查的 Qt/C++ 值对象、JSON 字段、公开校验和兼容规则候选。
> 它不证明官方 AI 助手已经发布这些对象，也不把 D2-C 的 `BLOCKED/E2` 宿主证据升级为 PASS。

- 日期：2026-08-14
- 任务：D3-C「路径选择与共享契约冻结」
- 基线：`origin/main@d37fb95eca9083eb480491cda2464ebe8515477d`
- 代码：`os-agent-integration/contracts/memory_event_contract_v1.h/.cpp`
- 测试：`os-agent-integration/tests/test_memory_event_contract_v1.cpp`
- 启动门禁：`docs/day3/10_os_agent_contract_start_gate.md`

## 1. 冻结边界

本候选只冻结 C 侧公开对象 seam：

1. 调用者构造值对象并调用公开 `validate`；
2. 调用者只通过公开 `toJson`/`*FromJson` 转换；
3. 状态值只通过公开解析器转换为枚举；
4. 失败返回固定错误码、字段名和安全消息，不回显输入值。

以下内容不在本候选内：

- D 轨 UDS 长度前缀、`protocol_version`、`request_id`、`deadline_ms`、取消、重连和错误码映射；
- B 轨检索、索引、Vector、FTS5、RRF 和评测语义；
- E 轨业务枚举终审、敏感分级和同意模型；
- 官方 AI 助手生产 Hook、QML/UI、部署、KYSEC 和回退实现；
- 真实宿主 Tool/Context/Turn 能力通过声明。

`schema_version` 是本文件四个 C 侧 JSON 对象的结构版本，不等于 D 轨 IPC 的
`protocol_version`。SOP 示例中的 `deadline_ms` 属调用预算或 IPC envelope；在 D
完成协议冻结前，不序列化进 `MemoryQuery` Payload。

## 2. C++ 公共接口

命名空间：`kylin::memory::contract::v1`。

公开类型：

- `ContractError { code, field, safeMessage }`
- `ValidationResult { errors, ok() }`
- `ParseResult<T> { optional<T> value, errors, ok() }`
- `MemoryQuery`
- `MemoryContext`
- `ToolExecutionEvent`
- `TurnFinalizedEvent`
- `InjectionStatus`
- `ToolExecutionStatus`

公开函数：

- `validateSchemaVersion(QString)`
- 四对象的 `validate(...)`
- `memoryQueryFromJson(...)`
- `memoryContextFromJson(...)`
- `toolExecutionEventFromJson(...)`
- `turnFinalizedEventFromJson(...)`
- 四对象的 `toJson(...)`
- `injectionStatusFromString(...)` / `toString(InjectionStatus)`
- `toolExecutionStatusFromString(...)` / `toString(ToolExecutionStatus)`

`ParseResult<T>::ok()` 仅在 `value` 存在且 `errors` 为空时返回真；解析失败不返回部分值，
避免调用者误用被默认值填充的对象。

## 3. JSON 通用规则

| 规则 | v1 候选语义 |
|---|---|
| 命名 | JSON 使用 `snake_case`，C++ 使用 lower camel case |
| 版本格式 | `major.minor` 十进制整数，例如 `1.0` |
| 同主版本 | 接受 `1.x`；只允许新增可选字段或不改变既有字段语义 |
| 未知主版本 | `2.x` 等拒绝为 `unsupported_schema_version` |
| 未知字段 | 读取时忽略，重新序列化时不回写 |
| 必填字段缺失 | 不使用 Qt 默认值掩盖，返回 `required` |
| JSON 类型错误 | 返回 `invalid_type`；数组元素也逐项检查 |
| 整数字段 | 必须为有限、无小数且在 C++ `int` 范围内的 JSON number |
| 时间 | ISO 8601 字符串；规范输出为 UTC 且保留毫秒 |
| 文本安全 | 普通错误不回显原值；Tool 参数/结果只承载脱敏引用 |

兼容性是“宽读未知可选字段、严查已知字段”。旧读端不得把新主版本当作 v1 处理；新写端
只输出本文列出的规范字段。

## 4. `MemoryQuery`

用途：宿主在 Pre-Chat 检索前构造的 C 侧查询值对象。它不是完整 IPC envelope。

| JSON | C++ | 类型 | 输入 | 约束 |
|---|---|---|---|---|
| `schema_version` | `schemaVersion` | string | required | `1.x` |
| `user_id` | `userId` | string | required | 非空；来自宿主，不得模型生成 |
| `session_id` | `sessionId` | string | required | 非空；来自宿主 |
| `query_text` | `queryText` | string | required | 非空；只用于检索请求，不得覆盖 UI/聊天库原文 |
| `scene` | `scene` | string | required | 非空；业务枚举由 E 后续终审 |
| `max_context_tokens` | `maxContextTokens` | integer | required | 大于 0 |

有意不纳入：`deadline_ms`。调用端可把超时作为方法参数或 D 轨 envelope 字段传递，不能由
C 轨在本对象中单方面冻结。

## 5. `MemoryContext`

用途：Memory Service 组装后、仅进入 `model_request` 的上下文元数据。当前对象不承载记忆正文，
避免正式示例、普通日志或错误消息泄漏内容。

| JSON | C++ | 类型 | 输入 | 约束 |
|---|---|---|---|---|
| `schema_version` | `schemaVersion` | string | required | `1.x` |
| `query_id` | `queryId` | string | required | 非空；与 D `request_id` 的映射待 D 确认 |
| `selected_memory_ids` | `selectedMemoryIds` | string array | required | 可为空；元素必须为字符串 |
| `context_version` | `contextVersion` | string | required | 非空；跨 Turn 复用仍待 C/D 决策 |
| `token_budget` | `tokenBudget` | integer | required | 大于 0 |
| `actual_token_count` | `actualTokenCount` | integer | required | 非负且不大于预算 |
| `sensitive_excluded_count` | `sensitiveExcludedCount` | integer | optional | 缺省 0，非负 |
| `forgotten_excluded_count` | `forgottenExcludedCount` | integer | optional | 缺省 0，非负 |
| `conflict_excluded_count` | `conflictExcludedCount` | integer | optional | 缺省 0，非负 |
| `injection_status` | `injectionStatus` | string enum | required | 见下表 |

`InjectionStatus` 候选四态：

| JSON | C++ | 状态 |
|---|---|---|
| `prepared` | `Prepared` | `FROZEN_CANDIDATE` |
| `injected` | `Injected` | `FROZEN_CANDIDATE` |
| `failed` | `Failed` | `FROZEN_CANDIDATE` |
| `skipped` | `Skipped` | `FROZEN_CANDIDATE` |

该枚举的代码面已测试，但真实请求前注入仍为 `NOT_OBSERVED / TD-008`；不得据此标记
`HOST_VERIFIED`。

## 6. `ToolExecutionEvent`

用途：单次真实 Tool 执行结果候选。`arguments_ref`、`result_ref` 是脱敏引用，不是内嵌正文；
模型自述、Prompt Skill 或 UI 文本不得伪装为该事件。

| JSON | C++ | 类型 | 输入 | 约束 |
|---|---|---|---|---|
| `schema_version` | `schemaVersion` | string | required | `1.x` |
| `tool_call_id` | `toolCallId` | string | required | 非空 |
| `tool_name` | `toolName` | string | required | 非空 |
| `arguments_ref` | `argumentsRef` | string | optional | 脱敏引用 |
| `started_at` | `startedAt` | ISO 8601 | required | 有效时间 |
| `finished_at` | `finishedAt` | ISO 8601 | required | 不早于 `started_at` |
| `execution_status` | `executionStatus` | string enum | required | 见下表 |
| `result_ref` | `resultRef` | string | conditional | `success` 时必须非空 |
| `error_type` | `errorType` | string | optional | 结构化、非敏感类型 |
| `error_message_safe` | `errorMessageSafe` | string | optional | 不得包含敏感原文 |
| `side_effect` | `sideEffect` | boolean | required | 不得用缺省 false 掩盖缺字段 |
| `user_confirmed` | `userConfirmed` | boolean | optional | 缺省 false |
| `rollback_required` | `rollbackRequired` | boolean | optional | 缺省 false；事务语义待 D/E |
| `rollback_status` | `rollbackStatus` | string | optional | 暂不冻结枚举，待 D/E |
| `source_trace_id` | `sourceTraceId` | string | optional | 宿主来源追踪 |

`ToolExecutionStatus` 候选五态：

| JSON | C++ | 冻结状态 |
|---|---|---|
| `success` | `Success` | `FROZEN_CANDIDATE` |
| `failure` | `Failure` | `FROZEN_CANDIDATE` |
| `timeout` | `Timeout` | `FROZEN_CANDIDATE` |
| `partial` | `Partial` | `PENDING_CROSS_TRACK_CONFIRMATION` |
| `cancelled` | `Cancelled` | `PENDING_CROSS_TRACK_CONFIRMATION` |

五态均可安全解析，以避免未知状态降级成 success；其中 `partial/cancelled` 是否成为最终业务枚举
仍由 `HD-D2E-05` 管理。任何非 `success` 状态不得形成成功知识。真实结构化 Tool 事件仍为
`NOT_VERIFIED / TD-007 / TD-009`。

## 7. `TurnFinalizedEvent`

用途：单个 Turn 收尾、重试和 Tool 关联候选。为避免在共享事件和普通日志中复制原始正文，
本候选使用 `source_reference` 指向受控来源记录，不采用 D1 伪代码中的内嵌
`userText/assistantText` 作为冻结字段。

| JSON | C++ | 类型 | 输入 | 约束 |
|---|---|---|---|---|
| `schema_version` | `schemaVersion` | string | required | `1.x` |
| `event_id` | `eventId` | string | required | 非空；不得替代幂等键 |
| `user_id` | `userId` | string | required | 非空；宿主归属字段 |
| `session_id` | `sessionId` | string | required | 非空 |
| `turn_id` | `turnId` | string | required | 非空 |
| `source_reference` | `sourceReference` | string | optional | 受控来源引用，不是正文 |
| `idempotency_key` | `idempotencyKey` | string | required | 非空，独立于 `event_id` |
| `final_message_id` | `finalMessageId` | string | optional | 宿主消息引用 |
| `is_final` | `isFinal` | boolean | required | 不得用缺省 false 掩盖缺字段 |
| `finalization_reason` | `finalizationReason` | string | optional | 暂不冻结枚举，待 E |
| `stop_reason` | `stopReason` | string | optional | 暂不冻结枚举，待 C/E |
| `retry_of_turn_id` | `retryOfTurnId` | string | optional | 不得等于自身 `turn_id` |
| `tool_call_ids` | `toolCallIds` | string array | optional | 元素为字符串且在本 Turn 内唯一 |
| `finalized_at` | `finalizedAt` | ISO 8601 | required | 有效时间，来自宿主 |

Post-Turn 的候选语义位置已有部分/诊断证据，但 D2-C 正式索引仍为 `BLOCKED/E2`；Stop、Retry、
续轮与真实字段映射未闭合，因此本文只冻结候选接口，不宣称事件已在宿主发布。

## 8. 错误模型

| `code` | 含义 |
|---|---|
| `required` | 必填 key 或必填值缺失 |
| `invalid_type` | 已知字段 JSON 基础类型错误，或 ID 数组元素不是字符串 |
| `invalid_value` | number 不是可表示的整数 |
| `out_of_range` | 正数/非负数约束失败 |
| `invalid_enum` | 注入状态或 Tool 状态未知 |
| `invalid_version` | 版本不是 `major.minor` |
| `unsupported_schema_version` | 主版本不是 1 |
| `invalid_timestamp` | ISO 8601 时间无效 |
| `inconsistent_value` | 跨字段不变量失败，例如计数超预算、时间倒序或自重试 |
| `duplicate_value` | Turn 内 Tool ID 重复 |

`field` 只使用规范 JSON key；`safeMessage` 是固定英文消息。错误不得包含 query、Tool 参数、
Tool 结果、聊天正文、用户 ID 的实际值或凭据。

## 9. 规范示例与测试

规范示例：

- `os-agent-integration/contracts/examples/memory_query.v1.json`
- `os-agent-integration/contracts/examples/memory_context.v1.json`
- `os-agent-integration/contracts/examples/tool_execution_event.v1.json`
- `os-agent-integration/contracts/examples/turn_finalized_event.v1.json`

示例全部为合成数据。Qt 测试内另有人工审定固定字面值，并逐文件比较正式示例，防止示例与实现
静默漂移。

通用构建方式：

```text
cmake -S os-agent-integration -B <build-dir> -DBUILD_TESTING=ON -DQt5_DIR=<Qt5Config-directory>
cmake --build <build-dir> --config Debug --target test_memory_event_contract_v1
ctest --test-dir <build-dir> -C Debug --output-on-failure
```

该测试是本地 L0/L1 契约测试，不替代麒麟 VM 的 L2 Hook、注入、Tool 和 Turn 证据。

## 10. 冻结结论与阻断

| 项目 | 当前状态 | 说明 |
|---|---|---|
| Qt/C++ 值对象与公开 seam | `FROZEN_CANDIDATE` | 已实现并通过本地契约测试 |
| JSON 字段、版本与错误语义 | `FROZEN_CANDIDATE` | 等待 D 主审与 E 补审 |
| `MemoryContext` 真实注入 | `BLOCKED / TD-008` | D2-C 未技术证明请求前注入 |
| `ToolExecutionEvent` 真实宿主映射 | `BLOCKED / TD-007/009` | 未捕获结构化 Tool 事件 |
| `TurnFinalizedEvent` 真实宿主映射 | `BLOCKED / PARTIAL` | 只有部分/诊断证据，完整 Gate 未闭合 |
| D IPC envelope | `PENDING_D_CONFIRMATION` | 不在本文冻结 |
| E 枚举与安全终审 | `PENDING_E_REVIEW` | `partial/cancelled`、原因枚举等待审 |

因此，本文件允许后续代码和 Reviewer 围绕单一候选 seam 工作，但在上述阻断关闭前，状态不得
升级为最终 `FROZEN`、`ACCEPTED`、`HOST_VERIFIED` 或 Gate PASS。
