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

**仅建立目录和职责边界，尚无生产实现。**

## 明确不负责的内容

- 不实现 Python 侧服务逻辑
- 不包含官方 AI 助手 UI 源码
- 不直接操作 SQLite/Vector

## 未来主要目录

```
memory-client/
├── src/
│   ├── memory_client.cpp
│   ├── memory_client.h
│   └── protocol_adapter.cpp
├── qml/
│   ├── MemoryQueryPanel.qml
│   └── PreferenceEditor.qml
├── tests/
└── CMakeLists.txt
```

## 验收要求

| 层级 | 要求 |
|------|------|
| **L0** | 编译通过、Mock 协议测试 |
| **L1** | QLocalSocket 连接 Memory Service 正常 |
| **L2** | 麒麟 VM 中 QML 界面调用链路完整 |
