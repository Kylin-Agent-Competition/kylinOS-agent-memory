# Memory Client

## 模块定位

Qt/QML 侧记忆客户端，基于 QLocalSocket 连接 Memory Service，提供 QML 可调用的记忆存取、偏好查询、上下文管理接口。

## 输入与输出

- **输入**：QML 侧调用（用户偏好设置、Tool 上下文、查询请求、D5 Pre/Post Pipeline）
- **输出**：QML 可消费的结构化记忆数据、三路原文隔离文本、TurnFinalizedEvent 预览

## 责任轨道

- **主要**：C、D
- **协作**：B（检索结果消费）、E（事件枚举终审）
- **D5-C 演示参考**：`docs/adr/010-turn-finalized-method.md`（ADR-010）、`contracts/examples/memory_context.v1.json`

## 当前状态

**D6-C Demo / Prototype 扩展（在 D5-C Route B 基础上）；L0_COMPLETE；
ctest 4/4 全部子用例 PASS；C-D5 保持 OPEN；C-D6 不关闭；
SEC-CTX-01 Runtime Evidence 未生成；未接入真实 AI Assistant Hook /
Chat DB / ChatRecord / model_request / TurnExtractionAdapter）。**

- 协议编解码 `protocol_adapter.{h,cpp}`：4 字节大端长度前缀 + UTF-8 JSON envelope
  （对齐 D 轨 FRZ-IPC-001~007 + ADR-010 turn.finalized，`deliverables/D4_IPC_PROTOCOL_*FREEZE_20260817.md`）
  - **活跃方法**：`echo / health / memory.retrieve`
  - **写链路候选方法**：`turn.finalized`（ADR-010；CANDIDATE / BLOCKED_BY_HOST_MAPPING；生产默认不注册；Demo 客户端可发送）
  - **D6-C 候选写方法**（不冻结；ADR-013/014/015 待立项）：
    `tool.execution` / `manual.config.ingest` / `behavior.observe`
  - **未实现**：`memory.store`（保持 UNSUPPORTED_METHOD，ADR-010 §决策不动）
- MemoryClient `memory_client.{h,cpp}`：QLocalSocket 异步收发，信号驱动，不回显原文
  - `sendTurnFinalizedEvent()`：按 ADR-010 直接路由 `turn.finalized`
  - D6-C 新增 `sendToolExecutionEvent()` / `sendManualConfigEvent()` / `sendBehaviorEvent()`
    （复用 `sendEventEnvelope()` 共享写链路：trace_id 取 metadata.trace_id）
- 公共 ViewModel `view_models/memory_view_model.{h,cpp}`：
  - D5-C Pre-Chat Pipeline：`runPreChatPipeline()`；status=error 明确失败；MemoryContext 严格按 `memory_context.v1.json` 契约解析；空/error/malformed/injection=failed 不产生伪 `[MEMORY-CONTEXT]`
  - D5-C Post-Turn Pipeline：`runPostTurnPipeline()` → `turn.finalized`；status=error 明确 `failed/timeout`，memory.store 不再承担 TurnFinalizedEvent 写链路
  - 原文隔离：三路 QString（`originalUserText / modelRequestText / injectedContextText`）+ `textIsolationVerified` 指示灯
  - 运行健壮性：`preChatBusy_ + postTurnBusy_` 双 busy；独立 `pendingPreChatRequestId_ / pendingPostTurnRequestId_`；per-request deadline QTimer（默认 5000ms）；timeout 失败
  - **D6-C 多源 Adapter Pipeline（Demo / Prototype）**：
    - `runToolPipeline()` → `tool.execution`；5 状态（success/partial/failure/cancelled/timeout）；独立 `pendingToolRequestId_` + `toolBusy_`
    - `runManualConfigPipeline()` → `manual.config.ingest`；客户端侧敏感预检（high/critical 拒绝发送）；独立 `pendingManualConfigRequestId_` + `manualConfigBusy_`
    - `runBehaviorPipeline()` → `behavior.observe`；显式注入 `mapping_status=PENDING_C_CONFIRMATION`；独立 `pendingBehaviorRequestId_` + `behaviorBusy_`
    - `busy` 兼容属性扩展为五 busy 合并：`preChatBusy || postTurnBusy || toolBusy || manualConfigBusy || behaviorBusy`
    - 四 busy 独立 pending（沿用 D5-C REWORK §C1 模式扩展），PreChat in-flight 时 Tool 响应不串台
- QML：`qml/main.qml` + StackView 路由（Status / MemoryQuery / Preferences / VerticalLink Demo / **D6 Tool Adapter / D6 Manual Config / D6 Behavior Observe**）
  - **High 修复**：VerticalLinkPage postTurnPreview 采用纯 declarative binding（`lastTurnFinalizedEvent || previewHelper.previewDoc`），不再做 imperative `.text =` 赋值；Preview 只写 `previewHelper.previewDoc` 状态
  - **High 修复**：`viewModel.busy` 兼容属性 = `preChatBusy || postTurnBusy || toolBusy || manualConfigBusy || behaviorBusy`；旧页（main/Status/MemoryQuery）不再引用已移除的全局 `busy_`
- L0 Mock 契约测试 `tests/`：
  - `test_protocol_adapter.cpp` 协议编解码
  - `test_memory_client_mock.cpp` Client ↔ Mock Gateway
  - `test_d5_vertical_link_demo.cpp` D5-C Demo 覆盖（10 用例：A1/A2/B1-B5/C1-C3）
  - `test_d6c_multi_source_adapters.cpp` D6-C 多源 Adapter 覆盖（17 用例：A1-A5/B1-B5/C1-C4/D1-D4/E1-E2）

**关键声明（Route B + D6-C）**：
- 本实现仅为 memory-client 侧的 Pipeline Harness / Demo
- **不关闭 C-D5**，也**不关闭 C-D6**
- **不声称 SEC-CTX-01 Runtime Verified**
- **尚未接入**：真实 AI Assistant Hook、真实 model request、真实 Chat DB / ChatRecord / source resolver、真实 assistant final message、真实 sendToolMessage 路径
- memory_items 在 Context 渲染中的使用为 Demo 扩展，**不是**正式 C-D5 Context renderer 最终契约
- ADR-010 turn.finalized 标注为 CANDIDATE / BLOCKED_BY_HOST_MAPPING：本 Demo 客户端可发送，但生产服务端默认不注册 handler，因此 Demo 调用真实生产 Gateway 仍返回 UNSUPPORTED_METHOD（符合预期）
- D6-C 三个新写方法 `tool.execution` / `manual.config.ingest` / `behavior.observe` 为候选方法，生产 Gateway 默认不注册 → UNSUPPORTED_METHOD（符合预期）；handler 注册属 D 轨 D6D 范围（PENDING_D_TRACK）
- behavior → MemorySourceEvent.source_type 映射未冻结，ViewModel 显式注入 `mapping_status=PENDING_C_CONFIRMATION`；不擅自新增 SourceType 枚举（待 E 轨审查 + ADR）
- ManualConfig 客户端侧敏感预检为简化版（high/critical 拦截），完整敏感识别在 A 轨 `pipeline/sensitive.py`

**非阻断 Technical Debt（可后续跟踪）**：
- FRZ-IPC-004 deadline 计时精度：目前使用 `deadlineMs` 常量；冻结口径为 `deadline_ms + 100ms`
- timeout 后 `MemoryClient::pendingRequests_` 不自动删除；late response 可能刷新 `lastResponse`
- `memory_items` 展示作为 Demo 扩展暂存，待正式契约决策

## 明确不负责的内容

- 不实现 Python 侧服务逻辑
- 本 QML 应用为独立 Qt 演示壳（旁路演示），非官方 AI 助手集成；不包含官方 AI 助手 UI 源码
- 不直接操作 SQLite/Vector
- 不固化偏好/知识业务字段（待 E 轨 Schema 终审）
- 不冒充 L1/L2 银河麒麟 VM Runtime 证据

## 目录

```
memory-client/
├── CMakeLists.txt
├── README.md
├── src/
│   ├── main.cpp                       # QML 入口
│   ├── memory_client.{h,cpp}          # QLocalSocket 客户端
│   ├── protocol_adapter.{h,cpp}       # 长度前缀 JSON envelope 编解码（含 ADR-010 turn.finalized）
│   └── view_models/
│       └── memory_view_model.{h,cpp}  # QML 公共 ViewModel（D5-C Demo Pipeline）
├── qml/
│   ├── main.qml                       # ApplicationWindow + StackView
│   ├── resources.qrc
│   └── pages/
│       ├── StatusPage.qml
│       ├── MemoryQueryPage.qml
│       ├── PreferenceEditorPage.qml   # 占位（待 E 轨 Schema）
│       ├── VerticalLinkPage.qml       # D5-C Demo（Pre/Post + 原文隔离）
│       ├── ToolAdapterPage.qml        # D6-C Tool 事件构造与发送
│       ├── ManualConfigPage.qml       # D6-C 手动配置事件
│       └── BehaviorObservePage.qml    # D6-C 行为观察事件
└── tests/
    ├── CMakeLists.txt
    ├── mock_gateway_server.{h,cpp}             # QLocalServer Mock
    ├── test_protocol_adapter.cpp               # L0 协议单元测试
    ├── test_memory_client_mock.cpp             # L0 Client ↔ Mock Gateway
    ├── test_d5_vertical_link_demo.cpp          # L0 D5-C Demo（§A/B/C 10 用例）
    └── test_d6c_multi_source_adapters.cpp      # L0 D6-C 多源 Adapter（§A/B/C/D/E 17 用例）
```

## 构建

```bash
# 仅 L0 测试（不需要 Qt Quick）
cmake -S memory-client -B memory-client/build \
    -DKYLIN_MEMORY_CLIENT_BUILD_QML_APP=OFF \
    -DKYLIN_MEMORY_CLIENT_BUILD_TESTS=ON
cmake --build memory-client/build
ctest --test-dir memory-client/build --output-on-failure

# 含 QML GUI（需要 Qt5 Quick + QuickControls2）
cmake -S memory-client -B memory-client/build -DKYLIN_MEMORY_CLIENT_BUILD_QML_APP=ON
cmake --build memory-client/build
```

## CI（新增）

`.github/workflows/memory-client-ctest.yml`：
- **触发**：PR → main/integration；push → main/integration/feat/**；手动 `workflow_dispatch`
- **路径过滤**：`memory-client/**` + 工作流文件本身
- **环境**：ubuntu-22.04（qtbase5-dev/qt5-qmake/build-essential）
- **步骤**：cmake configure（QML OFF / tests ON）→ cmake --build → `ctest --output-on-failure --verbose`
- **覆盖 4 个 ctest**：`protocol_adapter` / `memory_client_mock` / `d5_vertical_link_demo` / `d6c_multi_source_adapters`

## 验收要求

| 层级 | 要求 | 状态 |
|------|------|------|
| **L0** | 编译通过、Mock 协议测试 | **L0_COMPLETE** — ctest **4/4**（test_protocol_adapter / test_memory_client_mock / test_d5_vertical_link_demo / test_d6c_multi_source_adapters），覆盖 D5-C §A/B/C 共 10 个 + D6-C §A/B/C/D/E 共 17 个用例；QML_APP=ON 构建闭环待 CI 扩展（TB-D6C-07） |
| **L1** | QLocalSocket 连接真实 Gateway / Echo；turn.finalized 测试态 handler；真实 MemoryContext 返回非空 | 待联调 |
| **L2** | 银河麒麟 VM 中真实 AI Assistant Hook / ChatRecord / Chat DB / SourceResolver 打通 | **未实现**（属后续真实 C-D5 关闭工作） |
| **HOST_VERIFIED** | SEC-CTX-01 原文隔离宿主级证据 | **RUNTIME_UNVERIFIED** |

## 技术债（D6-C PR #91）

> 解除条件：BLOCK 类 **必须在 D6D 立项前解除**；DEBT 类优先 D6D 首迭代处理；COSMETIC 类随下次顺手修。

### 🔴 BLOCK — D6D 前置解除条件

| ID | 文件 | 债务描述 | 解除条件 |
|----|------|----------|----------|
| TB-D6C-01 | `protocol_adapter.{h,cpp}` | 三候选方法常量未冻结：`tool.execution` / `manual.config.ingest` / `behavior.observe` 仅登记在 `methods` 命名空间，未加入 FRZ-IPC-007 路由表 | ADR-013/014/015 立项并通过 E 轨冻结审查；三方法加入 `supportedMethod()` 白名单 |
| TB-D6C-02 | `memory_view_model.cpp` / `.h` | Behavior `mapping_status=PENDING_C_CONFIRMATION`：`behavior` → `MemorySourceEvent.source_type` 映射未冻结，硬编码占位字符串 | C 轨审查通过 behavior→source_type 正式映射表；替换硬编码字符串为真实 `MemorySourceType` 枚举 |
| TB-D6C-03 | 三 QML 页 / README | 真实 AI Assistant Hook / Chat DB / ChatRecord / SourceResolver / sendToolMessage 未接入；生产 Gateway 三方法均返回 UNSUPPORTED_METHOD | D 轨 D6D 完成 handler 注册与真实集成；真实 Gateway 联调至少 L1 通过 |
| TB-D6C-04 ✅ 本 PR 已修 | `memory_view_model.{h,cpp}` + D1 测试 | `buildTurnFinalizedEventJson` 原无 `retryOfTurnId` 参数入口，D6D Retry 流程无法自动注入 `metadata.retry_of_turn_id` | ✅ 已扩展第 9 参数（默认空保持兼容），D1 测试补真实断言（存在性 + 非相等） |

### 🟡 DEBT — 优先 D6D 首迭代处理

| ID | 文件 | 债务描述 | 解除条件 |
|----|------|----------|----------|
| TB-D6C-05 ✅ 本 PR 已修 | `memory_view_model.cpp:507` | 双重 `occurred_at` 漂移：`behavior.occurred_at` 与 `metadata.occurred_at` 是两次独立 `nowIso8601UtcMs()` 调用 | ✅ 改为复用 `metadata["occurred_at"]`，保证单源时间戳 |
| TB-D6C-06 | `memory_view_model.cpp:438` + B4 测试 | `connectionError` 语义过载：传输层错误与业务层敏感拦截复用同一信号 | 新增 `manualConfigRejected(QString reason)` 专用信号或标准化 `requestFailed` 无 requestId 语义 |
| TB-D6C-07 | `README.md:140` + CI workflow | QML 页面未纳入 CI 编译验证：`QML_APP=ON` 构建路径无 Job，QML 语法错误 / 缺失 import 合并前无法发现 | 新增 workflow Job 编译 `QML_APP=ON` 目标（无需运行 GUI） |
| TB-D6C-08 ✅ 本 PR 已修 | `manual_config_event.v1.json` | 候选样例不对称：`behavior_event.v1.json` 有 `PENDING_C_CONFIRMATION`，Manual Config 候选样例无对应字段 | ✅ `config.mapping_status = PENDING_C_CONFIRMATION`，与 behavior 对称 |
| TB-D6C-09 ✅ 本 PR 已修 | `memory_view_model.cpp:434` | ManualConfig 敏感预检仅精确匹配 `"high"` / `"critical"`（大小写敏感），不兼容 `"HIGH"` / `"Critical"` / 前后空白 | ✅ 改为 `trimmed().toLower()` 归一化后比较 |

### 🟢 COSMETIC — 代码卫生

| ID | 文件 | 债务描述 | 解除条件 |
|----|------|----------|----------|
| TB-D6C-10 ✅ 本 PR 已修 | `test_d6c_multi_source_adapters.cpp:240` | A4 测试函数名 `toolTimeoutRoutesToTimeoutStage` 名实不符（修复后断言 `sent`） | ✅ 重命名为 `toolTimeoutExecutionStatusSentSuccessfully` |
| TB-D6C-11 ✅ 本 PR 已修 | `test_d6c_multi_source_adapters.cpp` §D | D1/D3 测试名实不符：D1 只断言 turn_id 非空；D3 名字含 "DifferentIdempotencyKey" 实际断言 idempotency_key 相同 | ✅ D1 扩展第 9 参数 + 补真实断言；D3 重命名为 `duplicateTurnIdProducesSameIdempotencyKeyDifferentEventId` |
| TB-D6C-12 ✅ 本 PR 已修 | `memory_view_model.cpp:461` | `config` 对象重复写入 `source_reference`（`metadata.source_reference` 已承载同值） | ✅ 删除重复字段，替换为候选冻结标记 `mapping_status` |

**债务处理进度**：本 PR 修复 BLOCK 1/4、DEBT 3/5、COSMETIC 3/3，合计 7/12；剩余 BLOCK 3 项（需跨轨 ADR 立项 / 真实集成）、DEBT 2 项（跨文件信号重构 / CI workflow 扩展）。
