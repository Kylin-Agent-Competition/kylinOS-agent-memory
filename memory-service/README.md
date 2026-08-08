# Memory Service

## 模块定位

Python 记忆服务核心，以 Unix Domain Socket + 长度前缀 JSON 协议对外提供本地记忆存取、语义检索和偏好推理能力。

## 输入与输出

- **输入**：JSON 格式的 Memory/Preference/ToolResult 操作请求（通过 UDS）
- **输出**：JSON 格式的查询结果、状态确认、错误信息

## 协议（UDS + 长度前缀 JSON，总体架构文档 4.4 IPC 契约）

每个消息 = 4 字节大端长度前缀 + UTF-8 JSON body（envelope 格式）：

```json
{
  "protocol_version": "1.0",
  "request_id": "req_01J...",
  "trace_id": "trc_01J...",
  "method": "memory.embed",
  "deadline_ms": 5000,
  "payload": {"text": "..."}
}
```

- 响应 envelope 同结构（protocol_version/method + request_id/trace_id 回显 + `ok`/`result`|`error`，降级路径含 `degraded`/`degraded_reason`）。
- 方法（D5 最小垂直链路）：`memory.embed` / `memory.embed_batch` / `memory.ping` / `memory.health`；完整方法集见总体架构文档 4.4（TABLE 15）。
- 实现见 `embedding/protocol.py`（build_envelope/parse_envelope）。

## 责任轨道

- **主要**：D、E
- **协作**：A（Embedding）、B（检索评估）

## 当前状态

**仅建立目录和职责边界，尚无生产实现。**

## 明确不负责的内容

- 不直接处理 QML 渲染
- 不处理官方 AI 助手 Hook（由 `os-agent-integration/` 负责）
- 不提供 HTTP/WebSocket 接口
- 不执行用户界面逻辑

## 未来主要目录

```
memory-service/
├── src/
│   ├── server.py
│   ├── protocol.py
│   ├── memory/
│   ├── retrieval/
│   └── embedding/
├── tests/
└── pyproject.toml
```

## 验收要求

| 层级 | 要求 |
|------|------|
| **L0** | 单元测试全覆盖、类型检查通过、Pydantic 模型验证 |
| **L1** | UDS 协议对接 C++ Bridge 通过 |
| **L2** | 麒麟 VM 中完整记忆读写和检索链路通过 |
