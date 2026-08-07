# IPC 协议冻结声明

- **冻结日期**：2026-08-07
- **依据**：[02 §16.8-16.9] 冻结契约流程、`D4_GATE0_FORMAL_DECISION_20260807.md` Gate 0 审查结论
- **证据等级**：E4（麒麟 VM 宿主验证通过）
- **冻结范围**：长度前缀 JSON 协议、错误码枚举、幂等方案（设计冻结，实现待 D4-D）、deadline 定义、protocol_version

---

## 一、冻结：长度前缀 JSON 协议

### 1.1 线协议定义

| 字段 | 定义 | 冻结状态 |
|------|------|---------|
| 帧头 | 4 字节 Big-Endian 无符号整数 (uint32) | **FROZEN** |
| 帧体 | UTF-8 编码 JSON 字节序列，长度 = 帧头值 | **FROZEN** |
| 最大消息 | 65536 字节 (64KB) | **FROZEN** |

**线格式**：
```
[4 bytes: payload_length_network_order][payload_length bytes: UTF-8 JSON]
```

**证据**：ECHO-003 6/6 UDS 全链路 PASS（麒麟 V11 VM 上 kaiming_memory_client 与 echo_server 通过 UDS 交换长度前缀 JSON）

### 1.2 禁止变更

- ❌ 不得改回换行 JSON（`\n` 分隔）
- ❌ 不得改为 protobuf / msgpack / flatbuffers 等二进制格式
- ❌ 不得改变字节序（须保持 Big-Endian）
- ❌ 不得增加非 JSON 控制帧（如心跳、ACK）

### 1.3 允许扩展（不破坏冻结）

- ✅ 新增 JSON 顶级字段（须 optional，源实现能忽略未知字段）
- ✅ 增加 `payload` 内的业务字段
- ✅ 压缩层（压缩为可选协商特性，默认关闭）

---

## 二、冻结：错误码枚举

### 2.1 稳定错误码（FROZEN）

从 `memory_echo_server.py` 的 `safe_error_code()` 提取，已在麒麟 VM 上验证：

| 错误码 | 含义 | 触发条件 | 证据 |
|--------|------|---------|------|
| `UNSUPPORTED_METHOD` | 请求的 method 不在 METHOD_ROUTER 中 | 发送 `kaiming.custom.analyze` 等未知方法 | ECHO-003 KAIMING-UNKNOWN PASS |
| `INVALID_REQUEST` | 消息格式无效 | JSON 解析失败或必填字段缺失 | 待 D4 L1 单元测试 |
| `PROTOCOL_ERROR` | 协议层错误 | 长度超出范围、非法UTF-8 | R1.2 服务端 PROTOCOL_ERROR 检查通过 |
| `INTERNAL_ERROR` | 服务端内部错误 | Handler 抛出未捕获异常 | ECHO-003 KAIMING-STORE PASS (echo 返回 UNSUPPORTED_METHOD) |

### 2.2 错误码安全映射规则（FROZEN）

```python
ERROR_CODE_MAP = {
    "UNKNOWN_METHOD": "UNSUPPORTED_METHOD",
    "INVALID_MESSAGE": "INVALID_REQUEST",
    "PROTOCOL_ERROR": "PROTOCOL_ERROR",
    "INTERNAL_ERROR": "INTERNAL_ERROR",
}
```

**规则**：所有内部错误字符串必须通过 `safe_error_code()` 映射到稳定枚举值，不得将 Python traceback 原始字符串泄漏到客户端。

### 2.3 禁止变更

- ❌ 不得重命名现有错误码
- ❌ 不得改变错误码的语义（如将 `UNSUPPORTED_METHOD` 变为 `NOT_FOUND`）
- ❌ 不得在响应中直接暴露内部异常堆栈

### 2.4 允许扩展

- ✅ 新增错误码（需 ADR）
- ✅ 已有错误码增加 `details` 字段（optional，不可含 PII）

---

## 三、冻结：protocol_version

| 字段 | 值 | 冻结状态 |
|------|-----|---------|
| 当前版本 | `"1.0"` | **FROZEN** |
| 版本位置 | 请求和响应 JSON 的 `protocol_version` 顶级字段 | **FROZEN** |
| 版本格式 | 字符串 `MAJOR.MINOR` | **FROZEN** |

**证据**：ECHO-003 所有请求/响应中 `protocol_version` 为 `"1.0"`，客户端和服务端校验一致。

**规则**：
- 服务端必须校验请求 `protocol_version` 为 `"1.0"`，不匹配返回 `PROTOCOL_ERROR`
- 响应中必须携带 `protocol_version: "1.0"`
- 主版本号变更（`2.0`）表示不兼容变更，需同时支持旧版本或通过 ADR
- 次版本号变更（`1.1`）表示兼容新增

---

## 四、冻结：deadline_ms 定义

### 4.1 字段定义（FROZEN）

| 字段 | 定义 |
|------|------|
| 字段名 | `deadline_ms` |
| 类型 | 整数（毫秒） |
| 含义 | 客户端允许的最大端到端处理时间（含网络传输） |
| 位置 | 请求 JSON 顶级字段 |
| 默认值 | 无默认值，客户端必须显式设置 |

### 4.2 行为约定（FROZEN）

- 服务端收到请求后检查 `deadline_ms`，若 `server_processing_time > deadline_ms` 则立即返回 `status: "error"` 并设置 `error_code: "TIMEOUT"`
- 客户端在 `deadline_ms` + 100ms 后仍未收到响应视为超时
- 服务端不应在超时后继续处理请求（允许关闭连接释放资源）

### 4.3 延迟预算分配（参考，非冻结）

端到端 500ms 分阶段分配 [02 §9.4]：
- IPC ≤ 20ms
- SQLite ≤ 80ms
- Embedding ≤ 180ms
- Vector ≤ 120ms
- 融合 ≤ 80ms

### 4.4 已知缺口

- deadline_ms 超时后服务端行为复测不完整 → TD-IPC-003

---

## 五、冻结：幂等方案（设计冻结）

### 5.1 幂等键（设计冻结）

| 字段 | 定义 | 状态 |
|------|------|------|
| 字段名 | `idempotency_key` | **设计冻结** |
| 类型 | 字符串（UUID v4 格式） | **设计冻结** |
| 位置 | 请求 JSON 顶级字段 | **设计冻结** |
| 作用域 | 单用户单会话内的所有写操作 | **设计冻结** |

### 5.2 幂等语义（设计冻结）

- 相同 `idempotency_key` 的重复请求返回第一次成功响应（不重复执行副作用）
- 幂等键 TTL = 24 小时
- 幂等键范围 = `(user_id, session_id, idempotency_key)` 三元组

### 5.3 实现约定（设计冻结，待 D4-D 实现）

- 幂等存储：SQLite `idempotency_cache` 表
- 幂等检查顺序：先查缓存 → 命中返回缓存结果 → 未命中执行 → 写入缓存
- 失败幂等：执行失败的请求不缓存（允许重试）

---

## 六、冻结：JSON 请求/响应顶级字段

### 6.1 请求结构（FROZEN）

| 字段 | 类型 | 必填 | 冻结 | 说明 |
|------|------|------|------|------|
| `protocol_version` | string | ✅ | **FROZEN** | 固定 `"1.0"` |
| `request_id` | string | ✅ | **FROZEN** | 客户端生成唯一 ID |
| `trace_id` | string | ✅ | **FROZEN** | 链路追踪 ID |
| `method` | string | ✅ | **FROZEN** | 路由方法名 (echo/health/memory.retrieve/memory.store/evidence.record) |
| `deadline_ms` | int | ✅ | **FROZEN** | 超时时间（毫秒） |
| `idempotency_key` | string | 否 | **设计冻结** | 幂等键（写操作建议提供） |
| `payload` | object | ✅ | **FROZEN** | 方法参数 |

### 6.2 响应结构（FROZEN）

| 字段 | 类型 | 始终存在 | 冻结 | 说明 |
|------|------|---------|------|------|
| `protocol_version` | string | ✅ | **FROZEN** | 固定 `"1.0"` |
| `request_id` | string | ✅ | **FROZEN** | 回显请求 ID |
| `trace_id` | string | ✅ | **FROZEN** | 回显追踪 ID |
| `status` | string | ✅ | **FROZEN** | `"ok"` / `"error"` |
| `data` | object | ✅ | **FROZEN** | 成功时的方法返回值 |
| `server_ts` | string | ✅ | **FROZEN** | ISO 8601 UTC 时间戳 |

**错误响应额外字段**（仅 `status == "error"`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `error_code` | string | 稳定错误码（§2.1） |
| `message` | string | 人类可读错误描述（不可含 PII/堆栈） |

### 6.3 方法路由（FROZEN）

| 方法 | 类别 | 状态 |
|------|------|------|
| `echo` | 调试 | Gate 0 已验证 [ECHO-003] |
| `health` | 运维 | Gate 0 已验证 [ECHO-003] |
| `memory.retrieve` | 检索 | Gate 0 已验证（返回空上下文）[ECHO-003] |
| `memory.store` | 写入 | Gate 0 未实现（返回 UNSUPPORTED_METHOD 符合预期） |
| `evidence.record` | 证据 | Gate 0 已验证 [ECHO-007/008] |
| `memory.forget` | 遗忘 | DEFERRED（D4+ 设计） |
| `memory.extract_preference` | 提取 | DEFERRED（D4+ 设计） |
| `memory.resolve_conflict` | 冲突 | DEFERRED（D4+ 设计） |

---

## 七、DEFERRED（明确标注未冻结项）

以下项已识别但当前阶段不冻结，待后续 D4+ 阶段通过 ADR 确定：

| 项 | 当前状态 | 预期冻结阶段 |
|----|---------|-------------|
| 压缩层协商 | 未设计 | D4-D |
| 多路复用（单连接多请求） | 未设计 | D4-D |
| 心跳/keepalive 帧 | 未设计 | D4-D |
| 连接池/连接复用 | 未设计 | D4-D |
| 流式响应（chunked transfer） | 未设计 | D6+ |
| 双向流（服务端主动推送） | 未设计 | D8+ |

---

## 八、冻结对象清单

| 编号 | 对象 | 文件 | 冻结日期 | 可变更条件 |
|------|------|------|---------|-----------|
| FRZ-IPC-001 | 长度前缀 JSON 线协议 | 本文档 §1 | 2026-08-07 | ADR + Gate |
| FRZ-IPC-002 | 错误码枚举 (4项) | 本文档 §2 | 2026-08-07 | ADR（仅新增） |
| FRZ-IPC-003 | protocol_version `"1.0"` | `memory_echo_server.py` L55 | 2026-08-07 | 主版本变更需 ADR |
| FRZ-IPC-004 | deadline_ms 字段与语义 | 本文档 §4 | 2026-08-07 | ADR |
| FRZ-IPC-005 | 幂等方案（设计层） | 本文档 §5 | 2026-08-07 | ADR |
| FRZ-IPC-006 | JSON 请求/响应顶级字段 | 本文档 §6 | 2026-08-07 | 仅允许新增 optional 字段 |
| FRZ-IPC-007 | 方法路由表 (5项活跃) | `memory_echo_server.py` METHOD_ROUTER | 2026-08-07 | ADR |