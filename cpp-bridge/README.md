# C++ Bridge

## 模块定位

基于 pybind11 + CMake 构建的 C++/Python SDK Bridge，负责将 C++ 侧（Qt/QLocalSocket）的请求转发至 Python Memory Service，并将响应回传。

## 输入与输出

- **输入**：Qt 侧 QLocalSocket 消息、C++ 侧的 SDK 调用
- **输出**：Python 侧方法调用结果、错误码

## 责任轨道

- **主要**：A、D
- **协作**：C（MemoryClient 对接）

## 当前状态

**仅建立目录和职责边界，尚无生产实现。**

## 明确不负责的内容

- 不实现业务记忆逻辑（由 `memory-service/` 负责）
- 不实现 QML UI
- 不包含官方 SDK 二进制

## 未来主要目录

```
cpp-bridge/
├── src/
│   ├── bridge.cpp
│   ├── py_module.cpp
│   └── protocol.cpp
├── include/
├── cmake/
├── tests/
└── CMakeLists.txt
```

## 验收要求

| 层级 | 要求 |
|------|------|
| **L0** | 编译通过、CMake 配置正确、单元测试 |
| **L1** | Bridge C++ ↔ Python 双向调用通过 |
| **L2** | 麒麟 VM 中与 Memory Service 联调通过 |
