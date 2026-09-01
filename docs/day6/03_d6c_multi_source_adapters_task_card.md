# D6-C 任务卡：多源接入、质量与安全（C 轨）

| 字段 | 内容 |
|------|------|
| 任务编号 | D6-C |
| 任务标题 | Tool Adapter 主干 + 行为事件接入 + 手动配置入口 + 重复回合/Stop/Retry 事件标识验证 |
| 责任轨道 | C（刘承恩） |
| Reviewer | D 主审（周子腾）；用户交互与安全由 E 补审（谢嘉然） |
| 基线分支 | `feat/C-d6-multi-source-adapters`（基于 `origin/main` @ `31b5279`，含已合并 D5-C Demo / Prototype） |
| 目标 | 在 memory-client 侧打通 Tool / 行为 / 手动配置三类硬数据源进入统一事件入口；为 A 轨 EventPipeline 与 E 轨 source admission 提供 C 侧 Adapter 主干；验证重复回合、Stop、Retry 的事件标识契约 |
| 完成定义（台账） | Tool、行为、手动配置三类硬数据源均可进入统一事件入口 |

## 0. 任务来源与前置状态

### 0.1 台账任务（D6-C）

1. 接入行为事件和 Tool Adapter 主干。
2. 实现手动配置接口与 QML 入口。
3. 验证重复回合、Stop、Retry 的事件标识。

### 0.2 D5-C 已合并基线（`31b5279`，PR #62）

- `memory-client/`：MemoryClient + ProtocolAdapter + MemoryViewModel + QML StackView（4 页）
- `os-agent-integration/contracts/memory_event_contract_v1.{h,cpp}`：MemoryQuery / MemoryContext / ToolExecutionEvent / TurnFinalizedEvent C++ 结构 + JSON 编解码 + validate
- `contracts/examples/*.v1.json`：四类事件样例
- ADR-010 已采纳：`turn.finalized` IPC 方法冻结；明确"为后续 `tool.execution`、`memory.ingest` 等写方法预留一致模式"
- D5-C 状态：**Demo / Prototype**，不关闭 C-D5，未接入真实 AI Assistant Hook

### 0.3 D5-C 明确遗留（D6-C 起点）

- MemoryClient 缺 `sendToolExecutionEvent` / `sendManualConfigEvent` / `sendBehaviorEvent`
- ProtocolAdapter 路由表无 `tool.execution` / `manual.config` / `behavior.observe`
- QML 仅有 `VerticalLinkPage`（Pre/Post Demo），缺 Tool / 手动配置 / 行为事件入口
- `memory_event_contract_v1` 已有 ToolExecutionEvent 结构，但 ViewModel 与 MemoryClient 未消费
- 行为事件到 `MemorySourceEvent.source_type` 的映射未冻结（E 轨 D6 标 `PENDING_C_CONFIRMATION`）

## 1. 修改范围

### 1.1 memory-client（C 轨主代码）

- `src/protocol_adapter.{h,cpp}`：路由表新增 `tool.execution` / `manual.config.ingest` / `behavior.observe` 三个**写方法常量**（与 `turn.finalized` 同样走 ADR 模式；本任务先在 client 侧加常量与 envelope 构造，服务端 handler 注册由 D 轨 D6-D 负责）
- `src/memory_client.{h,cpp}`：
  - `sendToolExecutionEvent(eventJson)`：构造 `tool.execution` envelope 发送
  - `sendManualConfigEvent(eventJson)`：构造 `manual.config.ingest` envelope 发送
  - `sendBehaviorEvent(eventJson)`：构造 `behavior.observe` envelope 发送
  - 三者复用 `sendRequest` 异步路径与 pendingRequests_ 关联机制
- `src/view_models/memory_view_model.{h,cpp}`：
  - 新增 `runToolPipeline(toolCallId, toolName, status, resultRef, sideEffect, ...)` 与 `lastToolEvent` / `toolStage` 状态
  - 新增 `runManualConfigPipeline(scope, key, value, isTemporary, shouldPersist)` 与 `lastManualConfigEvent` / `manualConfigStage` 状态
  - 新增 `runBehaviorPipeline(behaviorKind, observedAction, contextRef)` 与 `lastBehaviorEvent` / `behaviorStage` 状态
  - 拆分三路独立 `pendingXxxRequestId_` 与 `xxxBusy_`（沿用 D5 PreChat/PostTurn 双 busy 模式扩展为四 busy）
  - `toolStage` / `manualConfigStage` / `behaviorStage` 枚举：idle / sending / timeout / sent / failed
- `qml/pages/ToolAdapterPage.qml`（新增）：Tool 事件构造表单 + 发送 + 结果展示
- `qml/pages/ManualConfigPage.qml`（新增）：手动配置编辑表单 + 提交 + 状态展示
- `qml/pages/BehaviorObservePage.qml`（新增）：行为事件观察表单 + 提交 + 状态展示
- `qml/main.qml`：StackView 路由新增三个入口
- `qml/resources.qrc`：注册新 QML 文件

### 1.2 memory-client 测试

- `tests/test_d6c_multi_source_adapters.cpp`（新增）：
  - §A Tool Adapter：A1 success / A2 failure / A3 cancelled / A4 timeout / A5 partial 五状态
  - §B Manual Config：B1 长期偏好 / B2 临时设置 / B3 安全相关配置 / B4 敏感内容拦截 / B5 冲突非法值
  - §C Behavior Observe：C1 chat 行为 / C2 user_message / C3 agent_response / C4 mapping_status=PENDING_C_CONFIRMATION 标注
  - §D 事件标识契约：D1 Retry 时 `retry_of_turn_id != turn_id` / D2 Stop 显式 stop_reason / D3 重复 turn_id 走幂等冲突 / D4 重复 event_id 不替代 idempotency_key
  - §E 运行正确性：E1 四 busy 独立 pending 不串台 / E2 Reset 各路独立 / E3 Preview ⇄ Send 复用同一 event_id
- `tests/mock_gateway_server.{h,cpp}`：Mock 新增三个写方法的响应构造（UNSUPPORTED_METHOD 是默认；测试态可显式注册成功响应）
- `tests/CMakeLists.txt`：注册 `test_d6c_multi_source_adapters` ctest 目标

### 1.3 os-agent-integration（契约扩展，仅 demo 客户端侧）

- `contracts/examples/tool_execution_event.v1.json`：已有，无需修改
- `contracts/examples/manual_config_event.v1.json`（新增，候选 schema）：手动配置事件样例
- `contracts/examples/behavior_event.v1.json`（新增，候选 schema）：行为事件样例
- `contracts/memory_event_contract_v1.{h,cpp}`：**不修改**（ToolExecutionEvent 已存在；ManualConfig / Behavior 不纳入 v1 冻结契约，仅在客户端 Demo 范围）

### 1.4 文档

- `docs/day6/03_d6c_multi_source_adapters_task_card.md`（本任务卡）
- `memory-client/README.md`：状态更新（D6-C 扩展；继续声明 Demo / Prototype；C-D5 保持 OPEN）
- `docs/adr/README.md`：登记待立项 ADR-013/014/015（`tool.execution` / `manual.config.ingest` / `behavior.observe` IPC 方法候选；本 PR 不冻结，仅登记）

## 2. 禁止修改范围

- 不修改 `os-agent-integration/contracts/memory_event_contract_v1.{h,cpp}`（D3 已冻结）
- 不修改 `memory-service/**`（A/B/D/E 轨代码；本任务仅在 C 轨客户端侧构造事件并发送）
- 不擅自新增 `SourceType` 枚举值（`pipeline/schemas.py` 已有 7 值；若 behavior 需独立枚举须走 E 轨审查 + ADR）
- 不修改已冻结 FRZ-IPC-001~007 字段/envelope/错误码
- 不实现真实 AI Assistant Hook 接入（C-D5 仍未关闭；D6-C 仍为 Demo / Prototype）
- 不冒充 L1/L2 银河麒麟 VM Runtime 证据
- 不修改 ADR-010 已采纳的 `turn.finalized` 契约
- 不修改 D6-A / D6B / D6D / D6E 的代码或证据

## 3. 输入契约

### 3.1 已冻结输入

- `ToolExecutionEvent` C++ 结构（`contracts/memory_event_contract_v1.h:89-103`）
- `TurnFinalizedEvent` C++ 结构（同上 `:105-114`，含 `retry_of_turn_id` / `stop_reason` / `tool_call_ids`）
- ADR-010 `turn.finalized` IPC 映射契约（写方法模板）
- `SourceType` 七值（`pipeline/schemas.py:31-41`）：`chat / tool_result / manual_config / recollect / file / meeting / voice`
- FRZ-IPC-006 envelope 五必填：`protocol_version / request_id / trace_id / method / payload`

### 3.2 候选输入（本任务定义，不冻结）

- `ManualConfigEvent` 候选字段：`scope` / `key` / `value` / `is_temporary` / `should_persist` / `confidence` / `source_reference`
- `BehaviorEvent` 候选字段：`behavior_kind` / `observed_action` / `context_ref` / `actor` / `occurred_at`
- 三个新 IPC 方法名：`tool.execution` / `manual.config.ingest` / `behavior.observe`

## 4. 输出契约

### 4.1 MemoryClient 新增方法

```cpp
// tool.execution 写链路（对齐 ToolExecutionEvent v1 字段）
Q_INVOKABLE QString sendToolExecutionEvent(const QJsonObject& eventJson);

// manual.config.ingest 写链路（候选 schema）
Q_INVOKABLE QString sendManualConfigEvent(const QJsonObject& eventJson);

// behavior.observe 写链路（候选 schema）
Q_INVOKABLE QString sendBehaviorEvent(const QJsonObject& eventJson);
```

### 4.2 MemoryViewModel 新增 Q_PROPERTY / Q_INVOKABLE

- `lastToolEvent` / `toolStage` / `toolBusy` / `runToolPipeline(...)`
- `lastManualConfigEvent` / `manualConfigStage` / `manualConfigBusy` / `runManualConfigPipeline(...)`
- `lastBehaviorEvent` / `behaviorStage` / `behaviorBusy` / `runBehaviorPipeline(...)`
- `busy` 兼容属性扩展为 `preChatBusy || postTurnBusy || toolBusy || manualConfigBusy || behaviorBusy`

### 4.3 QML 新页面

- `ToolAdapterPage.qml`：5 状态构造表单（success/failure/cancelled/timeout/partial）+ 发送 + stage 展示
- `ManualConfigPage.qml`：长期/临时/安全/敏感边界表单 + 提交
- `BehaviorObservePage.qml`：行为类型选择 + 观察动作输入 + mapping_status 显式标注

## 5. 错误语义

### 5.1 协议级（沿用 D5-C）

- Mock 默认返回 `UNSUPPORTED_METHOD`（生产 D 轨 Gateway 未注册 handler）
- 测试态可显式注册成功响应（MockGatewayServer 已支持）
- envelope 校验失败 → `INVALID_REQUEST`
- 编解码失败 → `PROTOCOL_ERROR`

### 5.2 业务级（ViewModel）

- `status=error` → `xxxStage = "failed"`（沿用 D5-C REWORK §A 路径）
- per-request deadline（5000ms）超时 → `xxxStage = "timeout"` → `requestFailed`
- 三路独立 pending 不串台（沿用 D5-C REWORK §C1 模式扩展为四路）

## 6. 事件标识验证矩阵（台账第 3 项）

| 场景 | 验证目标 | 期望 | 测试用例 |
|------|---------|------|---------|
| Retry | `retry_of_turn_id` 必须不等于自身 `turn_id` | 不等则合法；等则 `INVALID_REQUEST` | D1 |
| Stop | `stop_reason` 显式标注（不依赖缺省） | 缺省/空 → 不构造 TurnFinalizedEvent | D2 |
| 重复 turn_id | 同 turn_id 不同 event_id 走幂等冲突 | `(user, session, idempotency_key)` 三元组 + 指纹校验 | D3 |
| 重复 event_id | `event_id` 不替代 `idempotency_key` | 同 event_id 不同 idempotency_key → 不被静默吞 | D4 |
| Cancelled Tool | status=cancelled 不形成稳定知识 | ViewModel 标 `toolStage=sent` 但 Mock 返回 `AUDIT_ONLY` 语义 | A3 |

## 7. 安全边界

### 7.1 敏感内容拦截（Manual Config）

- ManualConfigPage 提交前调用 `sensitive_regex`（与 A 轨 `pipeline/sensitive.py` 对齐的客户端侧预检）
- high/critical 敏感等级 → ViewModel 拒绝构造事件，`manualConfigStage = "failed"`，`lastError = "sensitive_content_blocked"`
- 不发送原始敏感正文到 Mock Gateway

### 7.2 行为事件 PENDING 标注

- `BehaviorObservePage` 显式 UI 标注："behavior → MemorySourceEvent.source_type 映射 PENDING_C_CONFIRMATION"
- 候选映射：`behavior_kind=user_action → source_type=chat`（暂用现有 `chat` 枚举，不新增 `behavior`）
- ViewModel 在事件 JSON 中显式注入 `mapping_status: "PENDING_C_CONFIRMATION"` 字段
- 不擅自新增 `SourceType.BEHAVIOR` 枚举（需 E 轨审查 + ADR）

### 7.3 原文隔离

- 沿用 D5-C 三路 QString 隔离模式扩展到 Tool / Manual / Behavior 三路
- `originalToolArguments` / `originalManualValue` / `originalBehaviorAction` 不与注入字段混用
- `textIsolationVerified` 扩展覆盖三路

## 8. WSL 可测项

- 全部 L0 Mock 契约测试本地通过、顺序无关
- ctest 4/4 全绿（`protocol_adapter` / `memory_client_mock` / `d5_vertical_link_demo` / `d6c_multi_source_adapters`）
- QML_APP=ON 构建通过（Qt5 Quick + QuickControls2 可用环境）

## 9. 麒麟 L2 必测项（本任务不完成，登记待 C-D5 关闭后补）

- 真实 AI Assistant Hook 中 sendToolMessage 路径 → ToolExecutionEvent 真实捕获
- 真实 Stop / Retry UI 操作 → 真实 stop_reason / retry_of_turn_id 字段
- 真实行为事件宿主证据（D2-C BLOCKED 项 H2C-Tool-1~5）
- 本任务不生成 L2 证据，不更新 `evidence/index.yaml`

## 10. 交付物

- `memory-client/` 三个新 IPC 方法 + ViewModel 三路 Pipeline + 三个 QML 页面 + 测试
- `os-agent-integration/contracts/examples/manual_config_event.v1.json` / `behavior_event.v1.json` 候选样例
- 本任务卡 + `memory-client/README.md` 状态更新
- ADR-013/014/015 立项登记（不冻结）

## 11. 验收标准

- 三类硬数据源（Tool / Manual / Behavior）均可通过 QML 入口构造事件并发送到 Mock Gateway
- Mock Gateway 默认返回 `UNSUPPORTED_METHOD` 时三路 stage 显式 `failed`（不伪装 `sent`）
- 重复回合 / Stop / Retry 事件标识验证矩阵（§6）全部通过
- 四 busy 独立 pending 不串台（PreChat in-flight 时 Tool 响应不影响 PreChat stage）
- 敏感内容客户端侧预检拦截（不发送到 Mock）
- 行为事件显式标注 `mapping_status=PENDING_C_CONFIRMATION`
- ctest 4/4 全绿、顺序无关
- 无固定样例假实现（降级 = 真实空响应或失败 stage）
- **C-D5 仍保持 OPEN**，不声称真实 Hook 已接入
- **C-D6 不声称 L2 Runtime Verified**

## 12. 与其他轨道接口边界

| 轨道 | 依赖方向 | 接口 | 状态 |
|------|---------|------|------|
| A（EventPipeline） | A → C | `MemorySourceEvent` schema 已冻结；C 客户端构造的 JSON 须可被 A 轨 `EventCleaner.clean()` 接受 | 对齐 |
| B（VectorProvider） | 无直接依赖 | — | — |
| D（IPC Gateway） | C → D | 三个新写方法 `tool.execution` / `manual.config.ingest` / `behavior.observe` 需 D 轨注册 handler；本任务仅客户端侧 | **PENDING_D_TRACK** |
| D（D6D 事件持久化） | C → D | D6D 分支 `feat/d6d-event-persistence` 在 ADR-012/013 设计 source_events 表；C 客户端事件字段须可被 D 落库 | **PENDING_D_TRACK** |
| E（source admission） | C → E | behavior → source_type 映射 `PENDING_C_CONFIRMATION`；E 轨 D6 多源开发集待 C 冻结后解除 PENDING | **PENDING_C_FREEZE** |
| E（业务 Schema） | E → C | ManualConfig 字段 `is_temporary` / `should_persist` 由 E 轨 D7/D8 终审；C 客户端先用候选字段 | **PENDING_E_FINAL** |

## 13. PENDING 项汇总（本任务不关闭）

| PENDING ID | 描述 | 关闭条件 |
|------------|------|---------|
| PENDING_D_TRACK | D 轨注册 `tool.execution` / `manual.config.ingest` / `behavior.observe` handler | D 轨 D6D 完成 + ADR-013/014/015 采纳 |
| PENDING_C_FREEZE | C 轨冻结 behavior → MemorySourceEvent.source_type 映射 | 本任务产出候选映射；正式冻结需 E 轨会签 |
| PENDING_E_FINAL | E 轨终审 ManualConfig 业务字段 | E 轨 D7/D8 完成 |
| PENDING_HOST_HOOK | 真实 AI Assistant Hook 接入 | C-D5 关闭后定向验证 |
| PENDING_L2_EVIDENCE | 麒麟 VM 真实宿主证据 | 人工 VM 操作 + D/E 复核 |

## 14. 已知技术债（登记，本任务不关闭）

- `TD-C-D6-001`：四个新写方法仅客户端侧，生产 Gateway 未注册，调用真实 Gateway 仍返回 `UNSUPPORTED_METHOD`（符合预期）
- `TD-C-D6-002`：behavior → source_type 映射使用现有 `chat` 枚举暂代，待 E 轨审查是否新增 `behavior` 枚举
- `TD-C-D6-003`：ManualConfig 客户端侧敏感预检为简化版，完整敏感识别在 A 轨 `pipeline/sensitive.py`
- `TD-C-D6-004`：四 busy 状态管理复杂度上升，待真实接入后评估是否合并为统一 request tracker

## 15. 回滚

回滚本批次提交即可恢复为 D5-C 已合并的 memory-client 状态；本任务不修改任何已冻结契约或服务端代码，无生产影响。
