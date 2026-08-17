# IPC 协议冻结声明 vs 项目实际实现 — 一致性核对报告

- **核对日期**：2026-08-17
- **核对对象**：`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（正式冻结）及引用的 `D4_IPC_PROTOCOL_FREEZE_20260807.md`（设计冻结）
- **核对范围**：FRZ-IPC-001~007 + UDS 路径
- **核对方法**：逐项比对冻结声明与仓库内实际代码实现

---

## 一、核心结论

冻结声明描述的协议与 Gate 0 echo server（`os-agent-integration/echo/memory_echo_server.py`）基本一致，
但与 `memory-service/embedding/*` 这套 Day5 协议实现存在多处**实质性偏离**。

---

## 二、逐项对照表

| 冻结项 | 结论 | 依据（file:line） |
|---|---|---|
| FRZ-IPC-001 线协议（4B BE + UTF-8 JSON） | ✅ 一致 | echo `memory_echo_server.py:92` `struct.unpack(">I")`；`embedding/protocol.py:47` `struct.pack(">I")` 均大端 |
| FRZ-IPC-001 最大 64KB | ❌ 不一致 | `embedding/protocol.py:32` `MAX_MSG_LEN = 4 * 1024 * 1024`（4 MiB）；echo `memory_echo_server.py:54` `MAX_MESSAGE_BYTES = 65536` 正确 |
| FRZ-IPC-002 错误码枚举（4 项） | ❌ 不一致 | `embedding_service.py` 使用 `ERR_PROTOCOL / ERR_INVALID_REQUEST / ERR_TIMEOUT / ERR_UNKNOWN / ERR_EMBED_FAILED / ERR_SERVICE_STOPPED`，不在冻结 4 项内；echo `memory_echo_server.py:58` `ERROR_CODE_MAP` 正确 |
| FRZ-IPC-003 protocol_version "1.0" | ✅ 一致 | echo `memory_echo_server.py:55`；`embedding/protocol.py:35` 均为 `"1.0"` |
| FRZ-IPC-004 deadline_ms | ⚠️ 部分 | 两处均解析后丢弃/未实现超时检查（`embedding_service.py:108` `_deadline` 未使用）；文档已登记 TD-IPC-003 属已知缺口。另文档 §4.2 要求超时返回 `error_code:"TIMEOUT"`，但 "TIMEOUT" 不在 FRZ-IPC-002 冻结错误码枚举中（文档自身矛盾） |
| FRZ-IPC-005 幂等 | ✅ 设计冻结未实现（符合声明） | 无 `idempotency_cache` 表（`migrations/` 仅 README）；echo 不处理 idempotency_key；与"实现待 D4-D"一致 |
| FRZ-IPC-006 请求 7 字段 / 响应 6 字段 | ❌ 响应结构不一致 | echo `build_response`（`memory_echo_server.py:107`）含 status/data/server_ts + error_code/message 符合；但 `embedding_service.py:222` `_envelope` 为 `{protocol_version, method, ok, result\|error, ...}`，无 `status/data/server_ts`，错误用 `error.code` 而非 `error_code` |
| FRZ-IPC-007 方法路由表（5 项） | ❌ 不一致 | 冻结声明列 `echo/health/memory.retrieve/memory.store/evidence.record` 5 项；echo 实际 `METHOD_ROUTER`（`memory_echo_server.py:148`）仅 3 项，`evidence.record` 注释明确"已移除(P0-4)"；`embedding_service.py:58` 另用 `memory.embed/embed_batch/ping/health` 4 项 |

---

## 三、详细发现

### 3.1 最大消息上限：4 MiB vs 64KB

- 冻结声明（设计文档 §1.1）：最大消息 `65536 字节 (64KB)`。
- 实际：`memory-service/embedding/protocol.py:32` 为 `MAX_MSG_LEN = 4 * 1024 * 1024`（4 MiB）。
- 影响：如按声明执行，恶意 64KB~4MiB 超包将绕过冻结上限；需改回 65536 或走 ADR 变更。

### 3.2 错误码枚举偏离

冻结 4 项稳定错误码（设计文档 §2.1）：

```
UNSUPPORTED_METHOD / INVALID_REQUEST / PROTOCOL_ERROR / INTERNAL_ERROR
```

`memory-service/embedding` 实际使用的错误码：

- `embedding_service.py:112` → `ERR_PROTOCOL`
- `embedding_service.py:125` → `ERR_INVALID_REQUEST`
- `embedding_service.py:181` → `ERR_TIMEOUT`（`ProviderErrorCode.ERR_TIMEOUT.name`）
- `embedding_service.py:187` → `ERR_UNKNOWN`
- `embedding_service.py:213` → `ERR_EMBED_FAILED`
- `embedding/server.py:117` → `ERR_SERVICE_STOPPED`

这些均不在 FRZ-IPC-002 冻结枚举内，违反"所有内部错误字符串必须映射到稳定枚举值"的规则。

### 3.3 deadline_ms 语义缺口

- `memory-service/embedding/embedding_service.py:108`：`parse_envelope` 返回的 deadline_ms 被赋给 `_deadline` 后**未使用**。
- echo server 同样只读取 request_id/trace_id，不做 deadline 检查。
- 冻结文档 §4.2 要求：服务端超时返回 `status:"error"` + `error_code:"TIMEOUT"`，但 "TIMEOUT" 不在冻结错误码枚举中 → **文档自身矛盾**。
- 已登记缺口：TD-IPC-003（超时行为复测不完整），本次核对确认该缺口仍存在。

### 3.4 响应 envelope 结构偏离（FRZ-IPC-006）

冻结响应结构（设计文档 §6.2，6 字段）：

```
protocol_version / request_id / trace_id / status / data / server_ts
```

错误额外字段：`error_code` + `message`。

`memory-service/embedding/embedding_service.py` 实际响应结构：

```
{ protocol_version, method, ok: true|false, result|error: { code, message }, request_id?, trace_id? }
```

差异：
- 缺少 `status` / `data` / `server_ts` 字段；
- 用 `ok` 布尔 + `result`/`error` 对象替代 `status` + `data`；
- 错误字段为 `error.code` / `error.message`，而非冻结的 `error_code` / `message`。

### 3.5 方法路由表偏离（FRZ-IPC-007）

- 冻结声明 §一 FRZ-IPC-007：`echo / health / memory.retrieve / memory.store / evidence.record`。
- echo server `METHOD_ROUTER`（`memory_echo_server.py:148-152`）：仅 `echo / health / memory.retrieve`。
- `evidence.record` 已在 P0-4（PR21 R3）移除，代码注释（`memory_echo_server.py:144-146`）明确说明。
- `memory.store` 从未实现（返回 UNSUPPORTED_METHOD，符合设计文档 §6.3 的"Gate 0 未实现"描述）。
- `memory-service/embedding` 使用另一套方法集：`memory.embed / memory.embed_batch / memory.ping / memory.health`（`embedding_service.py:58-63`）。

---

## 四、UDS 路径不一致（声明正文 §二）

冻结声明 §二 写 `$XDG_RUNTIME_DIR/kylin-memory/memory.sock`，但项目内实际存在 3 套不同路径：

| 组件 | 路径 | 依据 |
|---|---|---|
| echo server（systemd） | `/run/kylin-memory-echo/echo.sock` | `memory_echo_server.py:46` |
| echo server（dev） | `/tmp/kylin-memory-echo/echo.sock` | `memory_echo_server.py:43` |
| embedding server | `/tmp/kylin-memory-embed.sock` | `embedding/server.py:146` |
| 环境变量示例 | `KMA_SOCKET_PATH=/tmp/kylin-memory-service.sock` | `config/environment.example:8` |

> socket 路径本身不在 FRZ-IPC-001~007 冻结对象清单内，但声明正文 §二 明确写了路径，需澄清以哪套为准。

---

## 五、主要风险点

1. **最大消息 4 MiB vs 64KB**（`protocol.py:32`）：超包绕过冻结上限，需改回 65536 或走 ADR。
2. **`memory-service/embedding` 整套 envelope 与错误码偏离冻结契约**：`ok/result/error` 结构与 `error.code` 命名与 FRZ-IPC-002/006 冲突，属声明 §三.1"不得以任何形式偏离"的范围。
3. **`evidence.record` 状态矛盾**：冻结声明列为活跃路由，代码已移除，需在声明中更正或确认。

---

## 六、建议后续动作

1. `embedding/protocol.py` 消息上限对齐 64KB（或发起 ADR 变更为 4 MiB）。
2. `embedding_service.py` / `server.py` 错误码与 envelope 对齐 FRZ-IPC-002/006，或补充 ADR 说明该子服务采用独立错误码域。
3. 冻结声明更正 FRZ-IPC-007（移除 evidence.record 或标注 P0-4 移除）。
4. 澄清 UDS 统一路径与 §二 的 `$XDG_RUNTIME_DIR` 表述。
5. deadline_ms 超时行为补齐（TD-IPC-003）后，确认错误码 "TIMEOUT" 与 FRZ-IPC-002 的枚举关系。
