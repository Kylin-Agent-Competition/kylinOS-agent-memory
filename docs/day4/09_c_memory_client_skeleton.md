# 09 轨道 C — Day4 Memory Client 工程骨架

> **状态：`L0_COMPLETE / PENDING_REVIEW`** — 工程骨架 + Mock 契约测试 L0 全部
> 通过（2/2 ctest，30/30 子用例 PASS，总时长 0.08s）；协议编解码与 A 轨
> `memory-service/embedding/protocol.py` 已逐项对齐；待 D 主审与 E 补审（用户交互与
> 安全）；L1/L2 未实现。

## 目标（xlsx D4-C）

1. 创建 C++ MemoryClient、QLocalSocket 和协议编解码。
2. 创建 QML 主窗口、路由和公共 ViewModel。
3. 建立 Client/Gateway Mock 契约测试。

预期产出：C++ Client 与 QML 主框架可编译，协议样例可收发。

## 基线

- 主分支：`origin/main` 最新
- 依赖契约：`os-agent-integration/contracts/memory_event_contract_v1.h`（C 轨 D3 候选）
- 依赖协议：`memory-service/embedding/protocol.py`（A 轨 Day5 已落地长度前缀 JSON envelope）

## 新增文件

| 文件 | 说明 |
|------|------|
| `memory-client/src/protocol_adapter.h` | 长度前缀 JSON envelope 编解码候选接口 |
| `memory-client/src/protocol_adapter.cpp` | encode/decode/build/parse envelope 实现 |
| `memory-client/src/memory_client.h` | QLocalSocket 异步客户端接口 |
| `memory-client/src/memory_client.cpp` | 连接/收发/错误处理实现 |
| `memory-client/src/view_models/memory_view_model.h` | QML 公共 ViewModel 接口 |
| `memory-client/src/view_models/memory_view_model.cpp` | 信号聚合 + Q_PROPERTY 实现 |
| `memory-client/src/main.cpp` | QML 入口（注册 kylin.memory 模块） |
| `memory-client/qml/main.qml` | ApplicationWindow + StackView 路由 |
| `memory-client/qml/pages/StatusPage.qml` | 连接状态与最近响应展示 |
| `memory-client/qml/pages/MemoryQueryPage.qml` | memory.query 请求构造 |
| `memory-client/qml/pages/PreferenceEditorPage.qml` | 偏好编辑占位（待 E 轨 Schema） |
| `memory-client/qml/resources.qrc` | QML 资源 |
| `memory-client/CMakeLists.txt` | 模块构建（lib + 可选 QML app + tests） |
| `memory-client/tests/CMakeLists.txt` | L0 测试构建 |
| `memory-client/tests/mock_gateway_server.h` | QLocalServer Mock 接口 |
| `memory-client/tests/mock_gateway_server.cpp` | Mock 收发 + handler 注入实现 |
| `memory-client/tests/test_protocol_adapter.cpp` | 协议编解码 L0 单元测试 |
| `memory-client/tests/test_memory_client_mock.cpp` | Client ↔ Mock Gateway L0 契约测试 |

## L0 验证证据（2026-08-17 WSL Ubuntu 22.04）

**构建环境**：GCC 11.4.0 / Qt 5.15.3 (`qtbase5-dev`，Core+Network+Test)
（目标声明 Qt ≥ 5.12；Ubuntu 22.04 自带 5.15 为后向兼容的更高小版本）

**cmake 配置命令**：
```bash
cmake -S memory-client -B memory-client/build \
    -DKYLIN_MEMORY_CLIENT_BUILD_QML_APP=OFF \
    -DKYLIN_MEMORY_CLIENT_BUILD_TESTS=ON
cmake --build memory-client/build --parallel
```
产物：`libkylin_memory_client.a`（静态库）、`test_protocol_adapter`、`test_memory_client_mock`。

**ctest 结果（-V 全量子用例）**：

| ctest 名 | 子用例数 | 结果 | 耗时 |
|----------|----------|------|------|
| protocol_adapter | 22 | PASS | 0.02 s |
| memory_client_mock | 8 | PASS | 0.01 s |
| **合计** | **30/30** | **100%** | **0.08 s** |

`protocol_adapter` 覆盖：encode/decode round-trip、IncompletePacket、DeclaredLengthTooLarge、
InvalidJson、EnvelopeNotObject、多包连续解码、buildEnvelope 可选字段省略与写入、
parseEnvelope（合法含可选字段、缺 protocol_version、不兼容版本 4 行、类型错误版本、
缺 method、method 非字符串、method 空串、payload 非对象、可选字段读取）。

`memory_client_mock` 覆盖：health echo、自定义 handler、未连接即发送 → ERR_NOT_CONNECTED、
不存在服务端 → connectionError、畸形包（超大长度头）→ connectionError + Disconnected、
request_id 关联（并发两个 health）。

**构建阶段修复的三批问题（已进入代码、不作为 L2/L1 证据，仅记录 L0 闭环完整性）**：
1. `parseEnvelope` 返回 `std::optional<EnvelopeParts>` 的解引用错误（6 处 `.method` → `->method`），同时补上 `has_value()` 前置校验（生产代码 memory_client.cpp、测试基础设施 mock_gateway_server.cpp 也各有 1 处同类问题）。
2. `MockGatewayServer::Handler` 引用不存在的嵌套类型 `MockGatewayServer::EnvelopeParts` → 改为 `client::v1::EnvelopeParts`（3 处 lambda 参数）。
3. Qt 5.15 `QLocalSocket::errorOccurred` 与 `QIODevice::errorOccurred` 重载歧义：函数指针 connect 解析到 QIODevice 的版本导致 socket 错误不投递 → 改用字符串 `SIGNAL(errorOccurred(QLocalSocket::LocalSocketError))` 无歧义连接。
4. `QSignalSpy::wait(timeout)` 只计入 wait 调用后新发出的信号：先于 wait() 发出的同步 `Connecting` 信号被忽略，导致等待下一个状态变化时永远超 → 改用 `QTRY_COMPARE_WITH_TIMEOUT` / `QTRY_VERIFY_WITH_TIMEOUT` 轮询（同时涵盖已有与新信号）。
5. WSL 抽象命名空间 socket 可靠性低 → 改用 `/tmp/kylin-mock-<prefix>-<pid>.sock` 文件系统绝对路径 UDS。
6. `malformedServerPacketTriggersConnectionError` 子测试名不副实（实际走 happy-path）：为 MockGatewayServer 增加 `__malformed__: true` 后门，handler 返回该标记时写回超大长度头，真实验证客户端的协议错误熔断路径。

## 设计决议

### 1. 协议候选而非冻结

D 轨 IPC envelope 在 `docs/day3/11_os_agent_event_contract_v1.md` §10 标注
`PENDING_D_CONFIRMATION`。本骨架对齐 `memory-service/embedding/protocol.py`（A 轨
Day5 已落地路径），但不声明 FROZEN。所有协议常量集中在 `protocol_adapter.h`，
便于 D 主审关闭阻断后整体替换。

### 2. 错误模型不回显原文

`ProtocolError` 仅返回固定英文安全消息与错误类别枚举，不包含用户正文、查询
文本、Tool 参数、凭据。MemoryClient 的 `requestFailed` 信号同样只携带固定
`ERR_*` 码与安全消息。

### 3. ViewModel 不固化业务字段

偏好/知识 Schema（`category / scope / confidence / explicitness /
is_temporary / should_persist` 等）受 E 轨终审阻断未冻结。`MemoryViewModel`
只暴露 `lastResponse`（原始 envelope JSON），不解析业务字段。
`PreferenceEditorPage.qml` 为占位，明确标注待 E 轨。

### 4. 不引入真实 MemoryContext 注入

`MemoryContext` 真实注入受 `BLOCKED / TD-008` 阻断。本骨架的
`MemoryQueryPage.qml` 仅构造 `MemoryQuery`（Pre-Chat 检索前的查询值对象），
不构造 `MemoryContext`，不声明已实现请求前注入。

### 5. 测试基础设施为 Mock，非 Runtime

`MockGatewayServer` 基于 `QLocalServer`，仅用于 L0 Mock 契约测试。不冒充真实
Memory Service 联调（L1）或麒麟 VM 链路（L2）。`test_memory_client_mock.cpp`
使用 `QTEST_MAIN`（事件循环），`test_protocol_adapter.cpp` 使用
`QTEST_APPLESS_MAIN`（无事件循环）。

## 测试层级

| 层级 | 覆盖 | 运行环境 | 结果 |
|------|------|---------|------|
| L0-1 | `test_protocol_adapter.cpp` encode/decode round-trip + 错误拒绝 | 任意（Qt5 Core+Test） | PASS |
| L0-2 | `test_protocol_adapter.cpp` envelope 构造/解析（含可选字段） | 任意 | PASS |
| L0-3 | `test_protocol_adapter.cpp` 多包连续解码（流式） | 任意 | PASS |
| L0-4 | `test_memory_client_mock.cpp` 连接 + health echo 收发 | 任意（Qt5 Network+Test） | PASS |
| L0-5 | `test_memory_client_mock.cpp` 自定义 handler 响应 | 任意 | PASS |
| L0-6 | `test_memory_client_mock.cpp` 未连接发送 → ERR_NOT_CONNECTED | 任意 | PASS |
| L0-7 | `test_memory_client_mock.cpp` 不存在服务端 → connectionError | 任意 | PASS |
| L0-7b | `test_memory_client_mock.cpp` 畸形服务端包 → connectionError + Disconnected | 任意 | PASS |
| L0-8 | `test_memory_client_mock.cpp` request_id 关联匹配（并发两请求） | 任意 | PASS |
| L1 | QLocalSocket 连接真实 Memory Service | 待联调 | 未实现 |
| L2 | 麒麟 VM 真实 QML 调用链路 | 未实现 | 未实现 |

验证环境（2026-08-17）：WSL Ubuntu 22.04、GCC 11.4.0、Qt 5.15.3（qtbase5-dev，
满足 Qt≥5.12 目标声明）、ctest 2/2 30/30 子用例 PASS（0.08s）。

## 构建步骤

```bash
# L0 测试（不需要 Qt Quick）
cmake -S memory-client -B memory-client/build \
    -DKYLIN_MEMORY_CLIENT_BUILD_QML_APP=OFF \
    -DKYLIN_MEMORY_CLIENT_BUILD_TESTS=ON
cmake --build memory-client/build
ctest --test-dir memory-client/build --output-on-failure

# 含 QML GUI（需要 Qt5 Quick + QuickControls2）
cmake -S memory-client -B memory-client/build -DKYLIN_MEMORY_CLIENT_BUILD_QML_APP=ON
cmake --build memory-client/build
```

## 已知限制（关联阻断）

- D 轨 IPC envelope 未最终冻结 → `PENDING_D_CONFIRMATION`
- `MemoryContext` 真实注入未实现 → `BLOCKED / TD-008`
- `ToolExecutionEvent` 真实宿主映射未实现 → `BLOCKED / TD-007/009`
- 偏好/知识业务 Schema 未冻结 → `PENDING_E_REVIEW`
- 重连退避、重试、超时取消未实现（待 D 轨 IPC 终审后引入）
- L1/L2 未实现（待 D 轨 Gateway 落地后联调）

## 冻结结论与阻断

| 项目 | 当前状态 | 说明 |
|------|----------|------|
| C++ MemoryClient/QLocalSocket 骨架 | `L0_COMPLETE` | 静态库 `libkylin_memory_client.a` 编译通过；ctest 2/2 30/30 子用例 PASS（0.08s） |
| 协议编解码 envelope 候选 | `PENDING_D_CONFIRMATION` | 对齐 A 轨 Day5 `protocol.py`，L0 encode/decode 22 子用例覆盖；待 D 终审冻结 |
| QML 主框架 + 路由 | `L0_COMPLETE` | StackView + Drawer，三页面（Status/MemoryQuery/Preferences 占位）；Qt 5.12 语法兼容 |
| 公共 ViewModel | `L0_COMPLETE` | Q_PROPERTY 绑定 + Q_INVOKABLE，不固化业务字段（待 E 轨 Schema） |
| Mock Gateway 契约测试 | `L0_COMPLETE` | QLocalServer + handler 注入 infrastructure，8 子用例覆盖 echo/custom/ERR_NOT_CONNECTED/missing-server/malformed-packet/request-id 关联 |
| 真实 Memory Service 联调 | `NOT_IMPLEMENTED / L1_PENDING` | 待 D 轨 Gateway 落地 |
| 麒麟 VM QML 链路 | `NOT_IMPLEMENTED / L2_PENDING` | 待 D2-C 阻断关闭 |
