# 09 轨道 C — Day4 Memory Client 工程骨架

> **状态：`L0_CODE_COMPLETE / BUILD_VERIFICATION_PENDING / PENDING_REVIEW`** — 工程
> 骨架 + Mock 契约测试代码已实现并与 A 轨 `protocol.py` 对齐；待 D 主审与 E 补审
> （用户交互与安全）；本机缺少 Qt5 dev 工具链（Windows 无 cmake/Qt5，WSL 有 cmake
> 但无 qtbase5-dev 且 sudo 需密码），编译/Mock 测试运行验证待 D 审查环境补齐；L1/L2 未实现。

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

| 层级 | 覆盖 | 运行环境 |
|------|------|---------|
| L0-1 | `test_protocol_adapter.cpp` encode/decode round-trip + 错误拒绝 | 任意（Qt5 Core+Test） |
| L0-2 | `test_protocol_adapter.cpp` envelope 构造/解析（含可选字段） | 任意 |
| L0-3 | `test_protocol_adapter.cpp` 多包连续解码（流式） | 任意 |
| L0-4 | `test_memory_client_mock.cpp` 连接 + health echo 收发 | 任意（Qt5 Network+Test） |
| L0-5 | `test_memory_client_mock.cpp` 自定义 handler 响应 | 任意 |
| L0-6 | `test_memory_client_mock.cpp` 未连接发送 → ERR_NOT_CONNECTED | 任意 |
| L0-7 | `test_memory_client_mock.cpp` 不存在服务端 → connectionError | 任意 |
| L0-8 | `test_memory_client_mock.cpp` request_id 关联匹配 | 任意 |
| L1 | QLocalSocket 连接真实 Memory Service | 待联调 |
| L2 | 麒麟 VM 真实 QML 调用链路 | 未实现 |

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
| C++ MemoryClient/QLocalSocket 骨架 | `L0_CODE_COMPLETE` | 代码实现完成，协议对齐已核对；编译/Mock 测试运行待 Qt5 dev 工具链就绪后验证 |
| 协议编解码 envelope 候选 | `PENDING_D_CONFIRMATION` | 对齐 A 轨 Day5 落地路径，待 D 终审 |
| QML 主框架 + 路由 | `L0_COMPLETE` | StackView + 三页面，待 E 轨业务字段 |
| 公共 ViewModel | `L0_COMPLETE` | 不固化业务字段 |
| Mock Gateway 契约测试 | `L0_COMPLETE` | 非生产代码，仅测试基础设施 |
| 真实 Memory Service 联调 | `NOT_IMPLEMENTED / L1_PENDING` | 待 D 轨 Gateway 落地 |
| 麒麟 VM QML 链路 | `NOT_IMPLEMENTED / L2_PENDING` | 待 D2-C 阻断关闭 |
