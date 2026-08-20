# ADR-005：DB 层对外错误码与 envelope 采用 IPC 冻结契约（R-5）

- **状态**：✅ 已采纳（D 决策 2026-08-17，选方案 A；Reviewer：E（谢嘉然））
- **日期**：2026-08-17
- **决策人**：周子腾（D）｜**Reviewer**：E（谢嘉然，已签）
- **责任轨道**：D（IPC/DB）为主，C 会签；E 审查
- **决策版本**：`err-envelope-v1`
- **适用范围**：Memory Service 对外（UDS）错误码与响应 envelope；关联 FRZ-IPC-002、FRZ-IPC-006、ALIGN-002/003

## 背景

IPC 协议内容已定稿，Reviewer E 已签（2026-08-20），正式生效（`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`）：

1. **FRZ-IPC-002 冻结错误码 5 项**：`UNSUPPORTED_METHOD / INVALID_REQUEST / PROTOCOL_ERROR / INTERNAL_ERROR / TIMEOUT`（TIMEOUT 于 2026-08-17 补充入枚举）；
2. **FRZ-IPC-006 冻结响应 envelope**：`protocol_version / request_id / trace_id / status / data / server_ts`，错误附加 `error_code / message`；
3. **一致性核对报告**（`D4_IPC_PROTOCOL_CONSISTENCY_AUDIT_20260817.md`）发现代码实际偏离（ALIGN-002/003）：
   - `memory-service/embedding/embedding_service.py` 使用 `ERR_PROTOCOL / ERR_INVALID_REQUEST / ERR_TIMEOUT / ERR_UNKNOWN / ERR_EMBED_FAILED / ERR_SERVICE_STOPPED`，不在冻结枚举内；
   - 响应结构为 `{protocol_version, method, ok, result|error:{code,message}, ...}`，缺少 `status/data/server_ts`，错误字段为 `error.code` 而非 `error_code`。

冻结声明已登记「冻结优先、冻结后对齐」（ALIGN-001~005），本 ADR 决定 DB 层（含 Memory Service 各子服务）对外契约的错误码与 envelope 域。

## 候选方案

### 方案 A：DB 层按 IPC 冻结契约实现（本 ADR 决策）

Memory Service 所有对外 UDS 响应统一使用冻结 5 枚举 + `status/data/server_ts` envelope；内部错误（Python 异常 / 子服务内部码）由 DAO/路由层映射为冻结枚举（映射表见决策）。

优点：

- 与 IPC 定稿契约一致，单一错误码域，无映射维护负担之外的额外转换；
- 客户端只需实现一套错误处理；
- 满足冻结声明「不得以任何形式偏离」的效力条款。

缺点：

- 现有 `memory-service/embedding` 的 `ERR_*` 与 `ok/result/error` 结构需要对齐改造（ALIGN-002/003）；
- 改造属于冻结后代码对齐，需安排实施。

### 方案 B：承认子服务独立错误码域（ADR 批准独立域）

允许 `memory-service/embedding` 等子服务保留 `ERR_*` 与 `ok/result/error`，在 IPC 层做转换。

优点：

- 子服务改造量小。

缺点：

- 两套错误码域并存，客户端与诊断需双份映射；
- 与冻结声明「统一错误码枚举」原则冲突；
- 新增错误码时需同时维护两处枚举，维护成本高（审查 2.8 已指出映射维护负担）。

### 方案 C：维持现状

不改代码、不裁决。

缺点：冻结契约与实现持续偏离，违反冻结纪律；验收时无统一标准。

## 决策

选择方案 A：`err-envelope-v1`。**DB 层（含 Memory Service 各子服务）对外 UDS 响应统一使用 FRZ-IPC-002 冻结 5 枚举 + FRZ-IPC-006 `status/data/server_ts` envelope。**

### 错误码映射表（来源：需求 v1.3 附录 D）

| 内部码/异常（`memory-service/embedding`） | 冻结枚举（对外） | 说明 |
|---|---|---|
| `ERR_PROTOCOL` | `PROTOCOL_ERROR` | 协议层错误 |
| `ERR_INVALID_REQUEST` | `INVALID_REQUEST` | 请求格式无效 |
| `ERR_TIMEOUT` | `TIMEOUT` | 超时（冻结已含） |
| `ERR_UNKNOWN` | `INTERNAL_ERROR` | 未分类内部错误 |
| `ERR_EMBED_FAILED` | `INTERNAL_ERROR` | Provider 失败归内部错误（如需专用码走 IPC ADR） |
| `ERR_SERVICE_STOPPED` | `INTERNAL_ERROR` | 服务停止归内部错误 |
| `UNSUPPORTED_METHOD` | `UNSUPPORTED_METHOD` | 同名（echo 层已正确） |

### envelope 约定（对外）

- 成功：`protocol_version / request_id / trace_id / status:"ok" / data / server_ts`
- 失败：`status:"error" / error_code:<冻结枚举> / message:<无 PII>`

### 变更控制

- 错误码变更（新增/改义）一律走 **IPC 冻结 ADR 流程**（FRZ-IPC-002），本 ADR 引用其结论，不另设 DB 错误码 ADR 路径；
- 映射表为 D4-D 起点；IPC 冻结新增错误码时同步更新映射表。

## 影响

### 架构影响

- Memory Service 对外统一错误码域与 envelope；子服务内部可保留自有异常类型，但对外必须映射；
- `memory-service/embedding` 的 `ok/result/error` 结构改造为冻结 envelope（ALIGN-003 对齐动作）。

### 开发影响

- D4-D 需在 DAO/路由层实现错误码映射函数（内部异常 → 冻结枚举）；
- 改造 `embedding_service.py` / `server.py` 的响应封装与错误码；
- 更新对应测试（`tests/test_embedding_service.py` 等断言改为冻结枚举/envelope）。

### 评测影响

- 失败路由验收按冻结枚举断言（L0/L2 用例覆盖 5 枚举）。

### 安全影响

- `message` 字段不得含 PII/堆栈（沿用冻结 §2.2/2.3 约束）。

## 回滚与替代条件

本 ADR 可被新 ADR 替代（如未来承认独立错误码域），但须：

1. 显式撤销/修订本 ADR；
2. 评估两套错误码域并存对客户端与诊断的影响；
3. 经 IPC 冻结变更流程（FRZ-IPC-002 变更须 ADR + Gate）。

## 证据与限制

- `deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-002/006）
- `deliverables/D4_IPC_PROTOCOL_CONSISTENCY_AUDIT_20260817.md`（ALIGN-002/003，file:line 证据）
- `memory-service/embedding/embedding_service.py:181,222-254`（现有错误码/envelope）
- `memory-service/embedding/server.py:117`（`ERR_SERVICE_STOPPED`）
- `deliverables/D4_DB_INITIAL_REQUIREMENTS_20260817.md` 附录 D（映射表）

本 ADR 为文档/契约决策，不新增 Runtime 事实。批准记录：D 决策选方案 A（2026-08-17）；Reviewer E（谢嘉然）已于 2026-08-20 签署确认，正式生效并回写冻结（FRZ-IPC-002/006 不变）。
