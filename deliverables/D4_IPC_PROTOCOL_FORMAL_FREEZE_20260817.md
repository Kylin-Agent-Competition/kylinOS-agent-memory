# IPC 协议冻结声明（已签署生效）（长度前缀 JSON / 错误码 / 幂等 / deadline / protocol_version）

- **声明日期**：2026-08-17
- **声明人**：周子腾（D）
- **声明性质**：正式冻结**（已签署生效）**——在 `D4_IPC_PROTOCOL_FREEZE_20260807.md` 设计冻结基础上，经 8/16 补充审查确认；冻结内容已定稿，D/E 已签署（Reviewer E 谢嘉然 2026-08-20），正式生效。
- **关联文档**：
  - `D4_IPC_PROTOCOL_FREEZE_20260807.md`（冻结对象与定义明细，本声明不重复，仅引用）
  - `D4_GATE0_SUPPLEMENTARY_REVIEW_20260816.md` §六.2（环境基线升级至 5.0.3 后确认「不受影响，冻结结论继续有效」）
  - `D4_GATE0_FORMAL_DECISION_20260807.md`（Gate 0 正式结论）
- **基线 Commit**：`a6c20b4`（feature/d4-gate0-review-freeze）
- **证据等级**：E4（麒麟 VM 宿主验证：ECHO-003 6/6、UT-2 10/12 核心链路）

---

## 一、冻结对象与状态（本声明正式确认）

| 编号 | 冻结对象 | 冻结日期 | 本声明确认状态 |
|------|---------|---------|--------------|
| FRZ-IPC-001 | 长度前缀 JSON 线协议（4 字节 BE uint32 + UTF-8 JSON，最大 64KB） | 2026-08-07 | ✅ 协议冻结（已签署生效） |
| FRZ-IPC-002 | 错误码枚举（UNSUPPORTED_METHOD / INVALID_REQUEST / PROTOCOL_ERROR / INTERNAL_ERROR / **TIMEOUT**） | 2026-08-07（TIMEOUT 于 2026-08-17 补充，见 §3.2） | ✅ 协议冻结（已签署生效） |
| FRZ-IPC-003 | protocol_version `"1.0"`（MAJOR.MINOR，主版本变更需 ADR） | 2026-08-07 | ✅ 协议冻结（已签署生效） |
| FRZ-IPC-004 | deadline_ms 字段定义与行为约定（类型/位置/超时语义/延迟预算参考） | 2026-08-07 | ✅ 协议冻结（已签署生效；字段与语义）；超时行为复测缺口 TD-IPC-003 保持登记 |
| FRZ-IPC-005 | 幂等方案（idempotency_key + 三元组作用域 + 24h TTL） | 2026-08-07 | ✅ 设计层协议冻结（已签署生效；实现待 D4-D） |
| FRZ-IPC-006 | JSON 请求/响应顶级字段结构（请求 7 字段 / 响应 6 字段 + 错误附加字段） | 2026-08-07 | ✅ 协议冻结（已签署生效；仅允许新增 optional 字段） |
| FRZ-IPC-007 | 方法路由表（活跃 3 项：echo / health / memory.retrieve；ADR-010 `turn.finalized`、ADR-014 `event.ingest`、ADR-019 `forget.preview` / `forget.execute` 均标 CANDIDATE / BLOCKED_BY_HOST_MAPPING；memory.store 未实现返回 UNSUPPORTED_METHOD；evidence.record 已按 P0-4 移除） | 2026-08-07（2026-08-17 更正；2026-08-27 ADR-010 扩展；2026-08-31 ADR-014 扩展；2026-09-02 ADR-019 扩展） | ✅ 协议冻结（已签署生效；ADR-010/014/019 均完成 D 决策 + Reviewer E 签署） |

> **2026-08-27 扩展（ADR-010 批准）**：FRZ-IPC-007 路由表新增写方法 `turn.finalized`（payload 对齐 C 轨 `TurnFinalizedEvent` **候选契约**形成的 D 轨 IPC 映射契约）。激活状态标 **CANDIDATE / BLOCKED_BY_HOST_MAPPING**：默认生产路由**不注册** → `UNSUPPORTED_METHOD`；待 C 轨生产 resolver（`TurnExtractionAdapter`）就绪后升级 ACTIVE。`memory.store` 保持 UNSUPPORTED_METHOD 不变。详见 `docs/adr/010-turn-finalized-method.md`。

> **2026-08-31 扩展（ADR-014 批准，D 决策 + Reviewer E 终局签署 PASS_WITH_DEBT，TD-D6D-002）**：FRZ-IPC-007 路由表新增写方法 `event.ingest`（payload 对齐 A 轨 `MemorySourceEvent` **flat 映射契约**，`schema_version` 仅接受精确 `"0.1"`）。激活状态标 **CANDIDATE / BLOCKED_BY_HOST_MAPPING**：默认生产路由**不注册** → `UNSUPPORTED_METHOD`；待 C 轨事件源（Hook/Adapter）就绪后升级 ACTIVE。`memory.store` 保持 UNSUPPORTED_METHOD 不变。详见 `docs/adr/014-event-ingest-method.md`。

> **2026-09-02 扩展（ADR-019 批准，D 已决策 + Reviewer E 已签署，PR #112 APPROVED）**：FRZ-IPC-007 路由表新增写方法 `forget.preview` / `forget.execute`，强制 Preview 与 Execute 分离；execute 的幂等键只取 FRZ-IPC-006 envelope 顶层字段，一次性确认凭据绑定 `user_id + forget_plan_id + selection_hash` 且服务端只存 SHA-256。两方法激活状态均为 **CANDIDATE / BLOCKED_BY_HOST_MAPPING**，production 默认路由**不注册** → `UNSUPPORTED_METHOD`；独立可信宿主身份映射和安全 Gate 完成前不得升级 ACTIVE。Hard Delete、Cascade、Full Reset、time_window、topic 及未闭环 event 目标 Runtime 必须 fail-closed，不得降级后报告成功。详见 `docs/adr/019-forget-ipc-method.md`。本扩展仅正式冻结方法契约，对外能力仍为 **`PARTIAL / staged implementation`**，不构成 Runtime 或麒麟宿主验证证据。

**变更控制**：任何变更须走 ADR + Gate 流程；允许扩展范围（新增 optional 字段、新增错误码、次版本号兼容新增）见 `D4_IPC_PROTOCOL_FREEZE_20260807.md` §1.3 / §2.4 / §3。

---

## 二、不受环境基线升级影响的确认

8/16 环境基线由麒灵 AI 助手 3.0.67 升级至 5.0.3（智能体模式），经 `D4_GATE0_SUPPLEMENTARY_REVIEW_20260816.md` §六.2 逐项确认：

- 本协议为**自研协议**，承载于自建 Memory Service UDS（`$XDG_RUNTIME_DIR/kylin-memory/memory.sock`），与宿主助手版本、聊天 DB Schema 无关；
- **路径口径（2026-08-17 澄清）**：Memory Service 标准 socket 路径为 `$XDG_RUNTIME_DIR/kylin-memory/memory.sock`；Gate 0/验证期的 echo（`/run/kylin-memory-echo/echo.sock`、`/tmp/kylin-memory-echo/echo.sock`）与 embedding（`/tmp/kylin-memory-embed.sock`）等独立 socket 属实现细节，统一规划见 §3.2 ALIGN-005；
- 长度前缀 JSON、错误码、protocol_version、deadline、幂等方案**均不受 5.0.3 影响**，冻结结论继续有效；
- 5.0.3 新增的聊天 DB 字段（如 `request_data`）不影响本协议帧结构；若未来 Memory Context 注入契约定案使用 `request_data` 通道，属业务 payload 层扩展，不触碰本冻结协议。

---

## 三、冻结效力与适用边界

1. **生效范围**：自本声明签署之日起，本项目所有实现（C++ Bridge / Python Memory Service / Qt 客户端 / 测试）必须遵循 FRZ-IPC-001~007，不得以任何形式偏离；
2. **已知缺口（不撤销冻结，登记跟踪）**：
   - TD-IPC-003：deadline_ms 超时后服务端行为复测不完整 → D4 补齐复测；
   - TD-IPC-002 / TD-IPC-004：权限（RuntimeDirectory 不可确认）/ 重连（单连接阻塞式）→ D4 补齐；
   - 幂等实现（FRZ-IPC-005）为设计层冻结，落库实现待 D4-D，实现后需以麒麟 VM 幂等重复请求验证收口。
3. **DEFERRED 项**（压缩协商 / 多路复用 / 心跳 / 连接池 / 流式 / 双向流）：维持不冻结，待 D4+ 阶段 ADR 确定（见 08-07 文档 §七）。

### 3.2 一致性核对结论与代码对齐安排（2026-08-17）

依据 `D4_IPC_PROTOCOL_CONSISTENCY_AUDIT_20260817.md`（周子腾实际核对），确认以下处置原则：

- **仓库口径**：以 `Unified-Json-format`（最新版）为准；`UDS-Kylin-Echo` 为归档旧版仓库，不参与冻结对齐；
- **冻结优先**：本冻结声明为权威契约，**先完成冻结，代码偏离一律在冻结完成后对齐**，不反向修改冻结；
- **TIMEOUT 错误码补充说明**：§4.2 超时行为契约要求返回 `error_code: "TIMEOUT"`，但 08-07 枚举缺此项（文档自身矛盾，见核对报告 §3.3），本次冻结声明将 TIMEOUT 纳入 FRZ-IPC-002 枚举（共 5 项）以修复矛盾；
- **已登记偏离清单（冻结后代码对齐任务，不阻塞冻结）**：

| 编号 | 偏离项 | 冻结目标 | 当前实现（偏离） | 对齐动作 |
|------|--------|---------|----------------|---------|
| ALIGN-001 | 最大消息上限 | 65536 B (64KB) | embedding `protocol.py:32` `MAX_MSG_LEN=4MiB` | 改回 64KB，或走 ADR 变更为 4MiB |
| ALIGN-002 | 错误码枚举 | FRZ-IPC-002 五项 | embedding 使用 `ERR_PROTOCOL/ERR_INVALID_REQUEST/ERR_TIMEOUT/ERR_UNKNOWN/ERR_EMBED_FAILED/ERR_SERVICE_STOPPED` | 统一映射到冻结枚举，或 ADR 承认独立错误码域 |
| ALIGN-003 | 响应 envelope | `status/data/server_ts` + `error_code/message` | embedding `_envelope` 为 `ok/result/error`，错误用 `error.code` | 对齐冻结结构，或 ADR |
| ALIGN-004 | 方法路由 | FRZ-IPC-007 三项活跃 | embedding 另用 `memory.embed/embed_batch/ping/health` | 子服务方法纳入统一路由，或 ADR |
| ALIGN-005 | UDS 路径 | `$XDG_RUNTIME_DIR/kylin-memory/memory.sock` | echo `/run/kylin-memory-echo/echo.sock`、`/tmp/kylin-memory-echo/echo.sock`；embedding `/tmp/kylin-memory-embed.sock`；`KMA_SOCKET_PATH=/tmp/kylin-memory-service.sock` | 冻结后统一 socket 路径规划 |

---

## 四、签署

| 角色 | 姓名 | 日期 | 结论 |
|------|------|------|------|
| 冻结声明人 | 周子腾（D） | 2026-08-17 | 确认冻结 |
| Reviewer 1 | E（谢嘉然） | 2026-08-20 | 已签署 |
| Reviewer 2 | 待填写 | | |

> 注：本声明由 D4 阶段人工审查召集时一并裁决确认；确认后登记 `evidence/index.yaml`（如新增 IPC-FREEZE-001 条目）并关联冻结 Commit。
