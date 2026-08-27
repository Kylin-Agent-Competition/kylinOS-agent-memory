# ADR-010：新增 `turn.finalized` IPC 方法（FRZ-IPC-007 / B-1 方案 A1）

- **状态**：✅ 已采纳（D 决策 + Reviewer E 签署，2026-08-27）
- **日期**：2026-08-26（PR #60 Review 后语义细化修订）
- **决策人**：周子腾（D）｜**Reviewer**：E（谢嘉然，已签 2026-08-27）
- **责任轨道**：D（IPC）为主，C（Memory Client）协作，E 审查
- **决策版本**：`turn-finalized-method-v1`
- **适用范围**：FRZ-IPC-007 顶层方法路由表；关联 `docs/day3/11_os_agent_event_contract_v1.md` §7（TurnFinalizedEvent，**FROZEN_CANDIDATE**）、FRZ-IPC-005、ADR-006、ADR-011、checklist Phase 4.1

---

## 背景

1. **FRZ-IPC-007 冻结顶层方法路由**（`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:25`）：
   活跃 3 项 `echo / health / memory.retrieve`；`memory.store` 未实现返回 `UNSUPPORTED_METHOD`（符合预期，Gate 0 结论）；`evidence.record` 已按 P0-4 移除。
2. **写链路缺口**（`docs/day10/04_d5d_prerequisite_design_survey_20260826.md` §2.1）：FRZ-IPC-007 冻结路由**无任何写方法**，而 checklist Phase 4.1 要求「TurnFinalizedEvent → SQLite INSERT + Outbox INSERT 同事务」。故打通 Gateway→SQLite→Outbox 写链路必须先定「事件怎么进来」。
3. **事件契约状态**：`docs/day3/11_os_agent_event_contract_v1.md` §7 冻结的是 **C 轨 `FROZEN_CANDIDATE / BLOCKED_FOR_FINAL_FREEZE` 的 `TurnFinalizedEvent` 候选契约**（字段、required/optional、校验与错误模型），不代表事件已在宿主发布（真实宿主映射 `BLOCKED/PARTIAL`，TD-007/008/009、R-ARCH-05）。**本 ADR 冻结的是 D 轨据此形成的 IPC 映射契约**，不冻结、不上调 C 轨对象状态。
4. **关键边界**：写链路的「事件来源」与「服务端落库」是两件事。D5-D 打通的是服务端链路（模拟/测试客户端发事件 → Gateway → UoW → SQLite+Outbox），不依赖 C 轨真实 Hook 端到端；真实 Hook 接入（R-ARCH-05）属 C 轨范围，不阻塞本 ADR 的服务端方法契约。
5. **幂等**：FRZ-IPC-005（`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:23`）冻结 `idempotency_key` + 三元组作用域 `(user_id, session_id, idempotency_key)` + 24h TTL；实现在 D4-D 幂等 PK（ADR-006）基础上收口。
6. **落库联动**：ADRs 视角下 `turn.finalized` 是 trace_id / host_turn_id 落库的驱动方；host_turn_id 作为 upsert 匹配键，DDL 变更走 ADR-011。

---

## 候选方案

### 方案 A1：新增 `turn.finalized` 方法（本 ADR 决策）

FRZ-IPC-007 路由表新增写方法 `turn.finalized`，payload 对齐事件契约 v1 `TurnFinalizedEvent` 候选字段；Gateway 新增 handler：payload 解析 → 必填/类型校验 → 注入 `RequestContext`（user_id/session_id/trace_id/idempotency_key，envelope 为权威源）→ `UnitOfWork.save_turn_with_outbox` 同事务落库+入队。

优点：

- 与事件契约 v1 命名/字段天然对齐，减少语义漂移；
- 不动 `memory.store` 既有冻结语义，不反转 Gate 0「store 未实现符合预期」的结论；
- 为后续 `tool.execution`（ToolExecutionEvent）、`memory.ingest` 等写方法预留一致模式。

缺点：

- 冻结路由表新增方法须走 ADR + D/E 签署流程；
- C 轨 Memory Client（PR#49）`protocol_adapter` 需同步新增方法（不阻塞服务端，可用测试/模拟客户端验证）。

### 方案 A2：启用 `memory.store`（将 UNSUPPORTED 转为真实写路径）

不新增方法，把现有 `memory.store` 从「返回 UNSUPPORTED_METHOD」改为真实写实现。

- **语义不清**：`memory.store` 冻结语义是「存记忆条目」，与 `TurnFinalizedEvent`（回合事件驱动）不是同一抽象；硬塞回合事件会扭曲契约，后续 E 轨业务（memory entry 管理）与事件写入混用易产生歧义。
- Gate 0 结论「store 未实现符合预期」的反转需更强论证。
- **结论**：仅作为 A1 的备选，不推荐。

### 方案 A3：写路径不经 IPC（Hook 直接写 DAO）

事件由 C 轨 Hook 进程内直接调 DAO，不走 Gateway。

- 破坏「IPC Gateway → Application Service」分层（checklist Phase 2.2 统一 METHOD_ROUTER 意图）；
- Hook 与 Memory Service 不同进程，无法跨进程直接调用 Python DAO；
- 违背冻结「UDS 统一入口」口径（ADR-009）。
- **结论**：否决。

---

## 决策

选择方案 A1：`turn-finalized-method-v1`。**FRZ-IPC-007 路由表新增写方法 `turn.finalized`（payload = 事件契约 v1 `TurnFinalizedEvent` 候选字段形成的 IPC 映射契约），由 Gateway handler 解析、校验、注入 RequestContext、经 UnitOfWork 同事务落库 SQLite + 入队 Outbox；`memory.store` 保持 UNSUPPORTED_METHOD 不动。**

本 ADR 冻结范围 = **D 轨 IPC 映射契约**；C 轨 `TurnFinalizedEvent` 对象仍保持 `FROZEN_CANDIDATE` 状态，未随本 ADR 升级为正式冻结。

### IPC 契约定义（映射契约，细化版）

- **路由**：`turn.finalized`（写方法，加入冻结路由表；`memory.store` 保持 UNSUPPORTED 不动）
- **payload**（JSON `snake_case`，逐字段复用事件契约 v1 §3.2 + §7 的 required/optional 语义）：

| 分组 | JSON 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| metadata | `schema_version` | string | ✅ | C 侧事件结构版本，接受 `1.x`；与 `protocol_version` 不同属 |
| metadata | `event_id` | string | ✅ | 事件唯一身份；**不替代幂等键** |
| metadata | `user_id` | string | ✅ | 来自可信宿主 |
| metadata | `session_id` | string | ✅ | 来自可信宿主 |
| metadata | `turn_id` | string | ✅ | **host_turn_id**（宿主字符串 ID）；与 DB `turns.id`（db_turn_id）显式区分 |
| metadata | `idempotency_key` | string | ✅ | 写方法必填；权威值见「幂等」节 |
| metadata | `trace_id` | string | 可选 | 若提供必须等于 IPC envelope.trace_id，不一致 → `INVALID_REQUEST` |
| metadata | `occurred_at` | ISO 8601 | ✅ | 事件发生时间，来自宿主；规范输出 UTC 毫秒 |
| metadata | `collected_at` | ISO 8601 | ✅ | 采集时间，来自宿主；规范输出 UTC 毫秒 |
| metadata | `source_reference` | string | ✅ | 只存受控引用，不存正文；是正文的唯一解析入口 |
| 事件 | `is_final` | boolean | ✅ | 必须显式为 `true`，不得用缺省 false 掩盖缺字段；否则 `INVALID_REQUEST` |
| 事件 | `finalized_at` | ISO 8601 | ✅ | 宿主回合收尾时间 |
| 事件 | `final_message_id` | string | 可选 | 宿主消息引用 |
| 事件 | `finalization_reason` | string | 可选 | 枚举待 E 终审 |
| 事件 | `stop_reason` | string | 可选 | 枚举待 C/E 终审 |
| 事件 | `retry_of_turn_id` | string | 可选 | 不得等于自身 `turn_id` |
| 事件 | `tool_call_ids` | string array | 可选 | 元素必须为本 Turn 内唯一字符串 |

  **schema_version ≠ protocol_version**：`schema_version` 是 C 侧事件结构版本，用于 payload 校验（接受 `1.x`，主版本 != 1 拒为 INVALID_REQUEST）；`protocol_version` 是 D 侧 IPC envelope 版本（固定 `"1.0"`，FRZ-IPC-003），用于 envelope 校验。二者在不同层各自校验，不得混用。

- **校验与错误映射**：
  - 事件契约 v1 错误模型（`required` / `invalid_type` / `invalid_value` / `invalid_version` / `unsupported_schema_version` / `invalid_timestamp` / `inconsistent_value` / `duplicate_value`）逐项映射到 IPC `INVALID_REQUEST`（`safe_message` 固定英文，不回显原值）；
  - envelope 校验失败沿用 Gateway `validate_request`（PROTOCOL_ERROR / INVALID_REQUEST，FRZ-IPC-002/006）；
  - 内部异常 ➜ `INTERNAL_ERROR`（`safe_error_code`，不泄漏 traceback/正文）；
  - 未注册方法 ➜ `UNSUPPORTED_METHOD`。

- **幂等（唯一真源 + 冲突语义）**：
  - **字段来源三元组**（唯一真源，消除双真源歧义）：
    - `trace_id` → **IPC envelope 顶级字段**（FRZ-IPC-006）；
    - `idempotency_key` → **唯一权威合并规则**：取 IPC envelope 顶级字段 → 未提供则取 `payload.metadata.idempotency_key` → 两者同提供且不一致 → `INVALID_REQUEST`；
    - `user_id` / `session_id` → **validated `payload.metadata`**（二者**不是** IPC envelope 顶级字段）。
  - 幂等三元组 = `(user_id, session_id, 权威 idempotency_key)`（FRZ-IPC-005 / ADR-006 复合 PK）。
  - 命中缓存 → 返回首次成功响应（不重复执行副作用）；TTL = 24h；**失败请求不缓存**；`event_id` 不替代 `idempotency_key`（保持 FRZ-IPC-005 不变）。
  - **幂等冲突**：相同三元组 + **不同请求语义/payload** → `INVALID_REQUEST`（防不同事件误复用同一 key 被静默吞掉）。判定用请求指纹 `_request_fingerprint = sha256(规范化 method + 业务语义字段)`（字段清单见下「指纹 canonicalization」）。
  - **指纹不包含传输/追踪字段**：`trace_id` / `request_id` / `deadline_ms` 纯传输字段不进入指纹（重投天然变化，若进入会误判正常重试）。

- **trace_id 唯一真源**：RequestContext.trace_id / DB `turns.trace_id` / outbox.payload.trace_id 一律取 **IPC envelope 顶级 `trace_id`**（FRZ-IPC-006）；`payload.metadata.trace_id` 若存在必须相等，否则 `INVALID_REQUEST`。

- **指纹 canonicalization（业务语义字段规范化）**：
  - `tool_call_ids`：排序去重后参与 hash（事件契约已约束元素 Turn 内唯一）；
  - 时间戳：规范化 UTC 毫秒 ISO 8601 后参与 hash；
  - absent 与 null 等价（统一规范化为「缺失」，用同一占位）；
  - **进入**指纹：`event_id`、`host_turn_id`、`source_reference`、`is_final`、`finalized_at`、`occurred_at`、`final_message_id`、`finalization_reason`、`stop_reason`、`retry_of_turn_id`、`tool_call_ids`（排序）；
  - **不进入**（理由）：`trace_id` / `request_id` / `deadline_ms`（传输字段）、`collected_at`（采集时间，重投天然不同，若进入会误判正常重试）。

- **幂等 cache wrapper / unwrap（冻结内部缓存结构，不改 DDL）**：
  - `idempotency_cache.response` 仍为 JSON Text，缓存内容冻结为：
    ```json
    { "_request_fingerprint": "<sha256>", "response": { "db_turn_id": 123, "host_turn_id": "T-1", "conversation_id": 10 } }
    ```
  - 流程：**write** → 计算指纹 → 包 wrapper → 写缓存；**hit** → 比对当前请求指纹与缓存 `_request_fingerprint`：一致 → **unwrap 返回 `response`**；不一致 → `INVALID_REQUEST`（幂等冲突）；
  - 返回 IPC 的 `data` 永远不含 `_request_fingerprint`；
  - 旧/legacy 缓存行（response 无 `_request_fingerprint` 键）→ 按幂等命中直接返回 `response`，不触发指纹校验（向后兼容）。

- **落库语义（turn 新建/更新）**：
  - 写操作 = **Upsert**：匹配键 `(session_id 对应 conversation, host_turn_id)`（ADR-011 部分唯一索引）；不存在 → INSERT；存在 → UPDATE 同一条（重投 / refinalize 更新，不重复计数）。
  - `turn_index` 唯一来源 = **服务端计算**：同一事务内 `1 + COALESCE(MAX(turn_index), 0) WHERE session_id = ?`；事件不携带。
  - `original_user_text` 唯一来源 = **受控 resolver** 解析 `source_reference` 所得正文；事件**不内嵌正文**（保持原文隔离，`[02 §4.1]`）。
  - resolver 归属 = `memory-service/service/source_resolver.py`（新增 seam），接口 `resolve(source_reference) -> Optional[ResolvedContent{original_user_text, model_request?, model_response?}]`；
  - resolver 生产实现状态 = **`BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED`**（与 C 轨 `TurnExtractionAdapter` 一致）；PR-2 只交付测试/纯内存 resolver，接真实 UoW 写入路径，**不声称真实正文通道已支持**；
  - **失败语义（INSERT 调 resolver，UPDATE/refinalize 不调 resolver）**：
    - **INSERT（无既有 turn）**：**调用 resolver**。resolver 成功 → 写入 `original_user_text`；resolver 失败 → `INTERNAL_ERROR`（safe）；**禁止编造正文、禁止以空串替代**（`turns.original_user_text` NOT NULL 冻结语义）；
    - **UPDATE/refinalize（已有 turn）**：**不调用 resolver**，直接复用数据库已有 `original_user_text`；**不存在「UPDATE resolver 失败」分支**（正文已在首次 INSERT 落库，重投/refinalize 不改变首次正文，保证原文隔离 + 幂等重投不丢既有数据）。
  - 正文隔离 = resolver 结果只用于落库 `original_user_text`，不进入日志/异常消息/响应；
  - `model_request` / `model_response` 本轮不落（NULL），由后续提取/正文链路填充，不属于本方法契约；
  - `occurred_at` / `collected_at` / `finalized_at` 随 outbox.payload 元数据入队，不落 turns 列（turns 无对应列，FRZ-DB-001 冻结）。

- **Upsert 字段矩阵（INSERT vs UPDATE/refinalize，字段级冻结）**：

  | 字段 | INSERT | UPDATE / refinalize |
  |---|---|---|
  | `db_turn_id`(id) | DB 自增生成 | 保持原值（更新同一条） |
  | `host_turn_id` | 请求值 | 保持（匹配键，不改变） |
  | `turn_index` | 服务端 `1+MAX(turn_index)` | **保持首次值**（重投不重算，防序号漂移） |
  | `original_user_text` | resolver 解析 | **保持首次值**（refinalize 不重 resolve，保证原文隔离与稳定） |
  | `trace_id` | 请求 envelope.trace_id | **更新为最新请求 trace_id**（指向最终写入链路） |
  | `created_at` | 服务端时间 | 保持首次 |
  | `is_end` | `=1`（`is_final` 必为 true） | 保持 `=1` |
  | `model_request` / `model_response` | NULL | 保持 NULL |
  | Outbox | enqueue `turn.finalized` | **再次 enqueue**（payload 携带 `host_turn_id` + `refinalize:true`） |

- **activation 策略（production resolver 未就绪时）**：
  - 采用 **方案 A + B**：默认生产路由**不注册** `turn.finalized`（`register_default_handlers` 不含它）→ 未注册即 `UNSUPPORTED_METHOD`，杜绝「协议 SUPPORTED 但生产必然 INTERNAL_ERROR」的矛盾；
  - FRZ-IPC-007 路由表将 `turn.finalized` 标为 **`CANDIDATE / BLOCKED_BY_HOST_MAPPING`**，待 C 轨 `TurnExtractionAdapter`（production resolver）就绪后升级 ACTIVE；
  - PR-2 用测试客户端 + **显式注入内存 resolver** 验证服务端写链路（测试态可注册）。

- **响应**（冻结 envelope：`status/data/server_ts`，ADR-005 不变）：
  - data = `{db_turn_id, host_turn_id, conversation_id}`
    - `db_turn_id` = `turns.id`（SQLite Integer PK）；
    - `host_turn_id` = 请求 payload.metadata.turn_id（宿主字符串，回显）；
    - `conversation_id` = `conversations.id`（SQLite Integer）。
  - 原「`turn_id`」命名废弃，显式区分 host / db 两种身份。

### 变更控制

- `turn.finalized` 为新增可选方法，属 FRZ-IPC-007 允许的「扩展范围」（回溯 `D4_IPC_PROTOCOL_FREEZE_20260807.md` §1.3 / §2.4 / §3 兼容新增）；
- 新增字段/方法/方法级必填约束走本次 ADR；已冻结 FRZ-IPC-001~006 字段/错误码/envelope **不得修改**（幂等键在 turn.finalized 方法级收紧为必填，不改 FRZ-IPC-006 字段可选性定义）。

---

## 影响

### 架构影响

- 打通 Gateway→SQLite→Outbox 写链路，与 ADR-005 envelope、ADR-006 幂等 PK、ADR-009 socket ownership、ADR-011 列变更一致；
- 不新增运行时组件，写链路沿用现有 UDS + 长度前缀 JSON + `UnitOfWork` 单连接事务。

### 开发影响

- `gateway/handlers.py` 新增 `turn_finalized_handler`；`gateway/registry.py` 提供 `turn.finalized` **显式注册 seam**（production default registry 不注册；test profile 显式注册 + 注入 in-memory resolver）；`app.py` 注入 UnitOfWork；
- `db/repositories.py` / `db/uow.py` 补 `trace_id` / `host_turn_id` 透传 + upsert 逻辑 + 幂等指纹（与 ADR-011 联动）；
- `service/source_resolver.py` 新增 resolver seam（测试/内存实现 + 生产占位标注 BLOCKED_BY_HOST_MAPPING）；
- C 轨 `protocol_adapter` 需同步 `turn.finalized` 方法（ADR 签署后单独 PR，不阻塞本 PR 服务端）。

### 评测影响

- 失败路由验收按冻结 5 枚举断言（ADR-005）；新增方法路由按 FRZ-IPC-007 + 本 ADR 白名单断言；
- L1 契约测试覆盖：幂等命中/冲突（含相同三元组不同 payload → INVALID_REQUEST）、resolver 失败 INSERT → INTERNAL_ERROR、行文隔离（正文不出现于日志/响应）。

### 安全影响

- `source_reference` 只承载受控引用，不承载正文（对齐事件契约 v1 §7）；
- `trace_id` / `host_turn_id` 均按**非正文的受控追踪标识**处理；**不得假设外部输入永不含敏感信息**，日志与审计仍按受控标识处理；
- 错误消息 `safe_error_code` / 固定 safe_message，不回显原文/用户 ID/凭据；
- 跨用户隔离沿用 Repository 层 `user_id` 作用域。

---

## 回滚与替代条件

若未来决定废弃 `turn.finalized` 或改用其他写路径，可经新 ADR 撤销本 ADR：删除路由表条目与 handler，`memory.store` 维持 UNSUPPORTED 语义不变；冻结回写 `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-007 路由表）恢复原状；ADR-011 的 host_turn_id 列经其自身回滚流程处理。

---

## 证据与限制

- `deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:23/25`（FRZ-IPC-005、FRZ-IPC-007）
- `deliverables/D4_IPC_PROTOCOL_FREEZE_20260807.md` §5/§6（幂等、envelope 结构）
- `docs/day3/11_os_agent_event_contract_v1.md` §3.2 / §7（TurnFinalizedEvent **候选契约**、Adapter 边界、错误模型）
- `docs/day10/04_d5d_prerequisite_design_survey_20260826.md` §三（B-1 方案对比：A1 推荐；**本 PR 已纳入仓库**）
- `docs/day10/05_d5d_task_list_20260826.md` §1.1（PR-1 ADR-010 内容；**本 PR 已纳入仓库**）
- `docs/day10/06_pr60_semantic_refinement_plan.md`（本方案；PR #60 Review 逐项收口）
- `memory-service/gateway/handlers.py` / `registry.py`、`memory-service/db/uow.py`（实现现状）

本 ADR 为文档/契约决策，不新增 Runtime 事实。批准记录：**D（周子腾）2026-08-27 决策选方案 A1**；**Reviewer E（谢嘉然）2026-08-27 签署**；状态更新为「已采纳」，并在**本 PR 内追加 commit 回写** FRZ-IPC-007 路由表。