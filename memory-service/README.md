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

- 响应 envelope（FRZ-IPC-006 冻结）：`protocol_version`/`request_id`/`trace_id`/`status`/`data`/`server_ts`，其中 `data` 恒为 object；失败响应附加 `error_code`/`message`（FRZ-IPC-002 冻结枚举）。
- 方法（D5 最小垂直链路）：`memory.embed` / `memory.embed_batch` / `memory.ping` / `memory.health`；完整方法集见总体架构文档 4.4（TABLE 15）。
- 实现见 `embedding/protocol.py`（build_envelope/parse_envelope）。

> **架构文档引用说明**：本文件引用的「总体架构文档 v1」（4.4 IPC 契约、TABLE 12/48/54/55/15/17）
> 为团队共享的外部文档（docx，版本 v1.0，2026-07-26 编制），仓库 `docs/architecture/` 尚未
> 收录全文；仓库内可交叉验证的基线条目见 `docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md`、
> `docs/day3/06_provider_contract_v1.md`。引用编号以该外部文档 v1.0 为准，若与仓库条目冲突以
> 仓库冻结契约优先。待总体架构文档同步入库后移除本说明。

## 责任轨道

- **主要**：D、E
- **协作**：A（Embedding）、B（检索评估）

## 当前状态

**D5（首个真实垂直链路）已实现 Embedding 最小链路**（`embedding/` 子包，见下方"实现"）：

- `embedding/protocol.py`：UDS 长度前缀 JSON + 架构 4.4 envelope（`build_envelope`/`parse_envelope`，protocol_version=1.0 校验、method 白名单）
- `embedding/embedding_service.py`：EmbeddingService（`memory.embed`/`embed_batch`/`ping`/`health`），Bridge 调用在线程池（不阻塞聊天线程），Provider 不可用时返回明确空向量 + `degraded`（真实降级，非固定样例）
- `embedding/server.py`：UDS 服务器（`python -m embedding.server --socket ...`）

麒麟 VM 验证（2026-08-08）：真实 SDK 8/8 无 Skip（768 维/中文/空串/batch/envelope 分发/health/降级）+ 本地 23/23 + 端到端 UDS（health bridge_loaded=true、embed dim=768）。

其余记忆读写、检索、偏好/知识治理等仍在后续迭代（D6+）。

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
