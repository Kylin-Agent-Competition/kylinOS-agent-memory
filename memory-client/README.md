# Memory Client

## 模块定位

Qt/QML 侧记忆客户端，基于 QLocalSocket 连接 Memory Service，提供 QML 可调用的记忆存取、偏好查询和上下文管理接口。

## 输入与输出

- **输入**：QML 侧调用（用户偏好设置、Tool 上下文、查询请求）
- **输出**：QML 可消费的结构化记忆数据

## 责任轨道

- **主要**：C、D
- **协作**：B（检索结果消费）

## 当前状态

**D4 骨架 L0 完成 + D4 冻结协议对齐完成（L0_COMPLETE / FROZEN_ALIGNED；ctest 2/2
52/52 子用例 PASS，含 QML_APP=ON 构建闭环 + QML startup smoke，总耗时 0.60s，
WSL Ubuntu 22.04 GCC 11.4.0 Qt 5.15.3；协议编解码
已对齐 D4 冻结 FRZ-IPC-001~007（ALIGN-001~006 全部完成）；L1/L2 待联调）。**

- 协议编解码 `protocol_adapter.{h,cpp}`：4 字节大端长度前缀 + UTF-8 JSON envelope
  （对齐 D4 冻结 FRZ-IPC-001~007，`deliverables/D4_IPC_PROTOCOL_FREEZE_20260807.md`）
- MemoryClient `memory_client.{h,cpp}`：QLocalSocket 异步收发，信号驱动，不暴露原文
- 公共 ViewModel `view_models/memory_view_model.{h,cpp}`：Q_PROPERTY 绑定 + Q_INVOKABLE 触发
- QML 主窗口 `qml/main.qml` + StackView 路由 + 三页面（Status / MemoryQuery / Preferences 占位）
- L0 Mock 契约测试 `tests/test_protocol_adapter.cpp` 与 `tests/test_memory_client_mock.cpp`
  （QLocalServer Mock Gateway）

状态语义：D 轨 IPC envelope 已于 2026-08-17 正式冻结签署
（`deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`，FRZ-IPC-001~007）。
C 轨客户端协议编解码已对齐冻结协议帧结构与字段（FROZEN_ALIGNED），但
FRZ-IPC-004 客户端超时行为（deadline_ms + 100ms 未响应视为超时）尚未实现（已正式
登记为 TD-022，计划 D5 阶段关闭），
FROZEN_ALIGNED 仅覆盖帧/字段层对齐，不等于全部冻结行为已实现。真实 MemoryContext
注入受 `BLOCKED / TD-008` 阻断；偏好/知识业务 Schema 受 E 轨终审阻断。

## 明确不负责的内容

- 不实现 Python 侧服务逻辑
- 本 QML 应用为独立 Qt 演示壳（旁路演示），非官方 AI 助手集成；不包含官方 AI 助手 UI 源码
- 不直接操作 SQLite/Vector
- 不固化偏好/知识业务字段（待 E 轨 Schema 终审）
- 不冒充 L2 麒麟 VM Runtime 证据

## 目录

```
memory-client/
├── CMakeLists.txt
├── README.md
├── src/
│   ├── main.cpp                       # QML 入口
│   ├── memory_client.{h,cpp}          # QLocalSocket 客户端
│   ├── protocol_adapter.{h,cpp}       # 长度前缀 JSON envelope 编解码
│   └── view_models/
│       └── memory_view_model.{h,cpp}  # QML 公共 ViewModel
├── qml/
│   ├── main.qml                       # ApplicationWindow + StackView
│   ├── resources.qrc
│   └── pages/
│       ├── StatusPage.qml
│       ├── MemoryQueryPage.qml
│       └── PreferenceEditorPage.qml   # 占位（待 E 轨 Schema）
└── tests/
    ├── CMakeLists.txt
    ├── mock_gateway_server.{h,cpp}    # QLocalServer Mock
    ├── test_protocol_adapter.cpp      # L0 协议单元测试
    └── test_memory_client_mock.cpp    # L0 Client ↔ Mock Gateway
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

## 验收要求

| 层级 | 要求 | 状态 |
|------|------|------|
| **L0** | 编译通过、Mock 协议测试 | **L0_COMPLETE** — ctest 2/2 52/52 PASS（0.60s，WSL Ubuntu 22.04 GCC 11.4.0 Qt 5.15.3，含 QML_APP=ON 构建闭环 + QML startup smoke） |
| **L1** | QLocalSocket 连接 Memory Service 正常 | 待联调 |
| **L2** | 麒麟 VM 中 QML 界面调用链路完整 | 未实现 |
