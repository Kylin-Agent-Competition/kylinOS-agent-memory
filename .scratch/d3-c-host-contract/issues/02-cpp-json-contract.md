# D3-C C++/JSON 公共契约

Type: task
Status: resolved
Blocked by: 01

## Outcome

通过逐个 vertical slice 的 TDD 循环，交付四个 Qt/C++ 值对象、公开验证及 JSON 转换接口、已知良好示例 Payload 和契约文档。

## Human gate

首个失败测试前，用户须确认 `spec.md` 中列出的公共测试 seams。

## TDD order

1. `MemoryQuery` 已知良好 Payload 往返。
2. `MemoryQuery` 缺失必填字段返回结构化错误。
3. `MemoryContext` 往返及计数/状态约束。
4. `ToolExecutionEvent` success/failure/cancelled/timeout/partial 状态解析；未审定枚举保持候选。
5. `TurnFinalizedEvent` 往返及 retry/tool 关联。
6. `schema_version` 与未知字段兼容规则。

每个步骤必须先红、最小变绿，再进入下一步骤；不测试 private helper 或内部调用次数。

## Acceptance

- 示例 JSON 是测试的独立已知良好字面值。
- 不记录真实敏感参数或结果正文，只使用脱敏引用。
- C++/JSON 字段和文档一致；证据不足字段保留候选状态。

## Comments

- 2026-08-14：用户已确认 C++ 值对象、JSON 往返、枚举/结构化错误三个公共 seam；允许开始首个失败测试。
- 2026-08-14：六个主切片及 required/type/integer/array 边界加固均完成 red→green；四个正式示例由独立字面值锁定。

## Answer

- 已交付四个 Qt/C++ 值对象、公开 `validate`、公开 JSON 转换、状态解析器和结构化安全错误。
- 已交付四个脱敏示例和 `docs/day3/11_os_agent_event_contract_v1.md`。
- `schema_version` 接受 `1.x`、拒绝未知主版本；未知可选字段读取时忽略。
- `partial/cancelled`、原因枚举和真实宿主映射仍明确保持候选/阻断状态。
