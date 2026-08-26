# ADR-010：新增 `turn.finalized` IPC 方法（FRZ-IPC-007 / B-1 方案 A1）

- **状态**：📝 提议（待 D 决策 + Reviewer E 签署）
- **日期**：2026-08-26
- **决策人**：周子腾（D）｜**Reviewer**：E（谢嘉然，待签）
- **责任轨道**：D（IPC）为主，C（Memory Client）协作，E 审查
- **决策版本**：`turn-finalized-method-v1`
- **适用范围**：FRZ-IPC-007 顶层方法路由表；关联 `docs/day3/11_os_agent_event_contract_v1.md` §7（TurnFinalizedEvent）、FRZ-IPC-005、checklist Phase 4.1

## 背景

1. **FRZ-IPC-007 冻结顶层方法路由**（`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:25`）：
   活跃 3 项 `echo / health / memory.retrieve`；`memory.store` 未实现返回 `UNSUPPORTED_METHOD`（符合预期，Gate 0 结论）；`evidence.record` 已按 P0-4 移除。
2. **写链路缺口**（`docs/day10/04_d5d_prerequisite_design_survey_20260826.md` §2.1）：FRZ-IPC-007 冻结路由**无任何写方法**，而 checklist Phase 4.1 要求「TurnFinalizedEvent → SQLite INSERT + Outbox INSERT 同事务」。故打通 Gateway→SQLite→Outbox 写链路必须先定「事件怎么进来」。
3. **事件契约 v1 已冻结 TurnFinalizedEvent 字段**（`docs/day3/11_os_agent_event_contract_v1.md` §7）：`metadata`（event_id/trace_id/user_id/session_id/turn_id/occurred_at/collected_at/source_reference/idempotency_key）+ 事件字段（final_message_id/is_final/finalization_reason/stop_reason/retry_of_turn_id/tool_call_ids/finalized_at）。但本文只冻结**候选接口**，不宣称事件已在宿主发布（`BLOCKED/PARTIAL`，TD-007/008/009、R-ARCH-05）。
4. **关键边界**：写链路的「事件来源」与「服务端落库」是两件事。D5-D 打通的是服务端链路（模拟/测试客户端发事件 → Gateway → UoW → SQLite+Outbox），不依赖 C 轨真实 Hook 端到端；真实 Hook 接入（R-ARCH-05）属 C 轨范围，不阻塞本 ADR 的服务端方法契约。
5. **幂等**：FRZ-IPC-005（`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:23`）冻结 `idempotency_key` + 三元组作用域 `(user_id, session_id, idempotency_key)` + 24h TTL；实现待 D4-D 落库收口。

## 候选方案

### 方案 A1：新增 `turn.finalized` 方法（本 ADR 决策）

FRZ-IPC-007 路由表新增写方法 `turn.finalized`，payload 对齐事件契约 v1 `TurnFinalizedEvent` 字段；Gateway 新增 handler：payload 解析 → 必填校验 → 注入 `RequestContext`（user_id/session_id/trace_id/idempotency_key）→ `UnitOfWork.save_turn_with_outbox` 同事务落库+入队。

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

## 决策

选择方案 A1：`turn-finalized-method-v1`。**FRZ-IPC-007 路由表新增写方法 `turn.finalized`（payload = 事件契约 v1 `TurnFinalizedEvent` 字段），由 Gateway handler 解析、注入 RequestContext、经 UnitOfWork 同事务落库 SQLite + 入队 Outbox；`memory.store` 保持 UNSUPPORTED_METHOD 不动。**

### IPCe 契约定义（草案）

- **路由**：`turn.finalized`（写方法，加入冻结路由表；`memory.store` 保持 UNSUPPORTED 不动）
- **payload**（对齐事件契约 v1 §3.2 + §7）：
  - `metadata`：
    - `event_id`（string，必填，不替代幂等键）
    - `user_id`（string，必填，来自可信宿主）
    - `session_id`（string，必填，来自可信宿主）
    - `turn_id`（string，必填，TurnFinalizedEvent 中必填）
    - `idempotency_key`（string，必填）
    - `trace_id`（string，可选，统一承接追踪语义）
    - `occurred_at`（ISO 8601，可选）
    - `collected_at`（ISO 8601，可选）
    - `source_reference`（string，必填，TurnFinalizedEvent 中必填；只存受控引用，不存正文）
  - 事件字段：
    - `is_final`（boolean，必填，必须显式为 `true`，不得用缺省 false 掩盖缺字段）
    - `finalized_at`（ISO 8601，必填）
    - `final_message_id`（string，可选，宿主消息引用）
    - `finalization_reason`（string，可选，枚举待 E 终审）
    - `stop_reason`（string，可选，枚举待 C/E 终审）
    - `retry_of_turn_id`（string，可选，不得等于自身 `turn_id`）
    - `tool_call_ids`（string array，可选，元素为本 Turn 内唯一字符串）
- **错误语义**（对齐 FRZ-IPC-002 / ADR-005 冻结 5 枚举）：
  - 非法 payload / 缺必填 ➜ `INVALID_REQUEST`
  - 内部异常 ➜ `INTERNAL_ERROR`（`safe_error_code`，不泄漏 traceback/正文）
  - 未注册方法 ➜ `UNSUPPORTED_METHOD`
- **幂等**：FRZ-IPC-005 三元组 `(user_id, session_id, idempotency_key)`，命中返回缓存结果不重复落库。
- **响应**：`{turn_id, conversation_id}`（冻结 envelope：`status/data/server_ts`，ADR-005）

### 变更控制

- `turn.finalized` 为新增可选方法，属 FRZ-IPC-007 允许的「扩展范围」（回溯 `D4_IPC_PROTOCOL_FREEZE_20260807.md` §1.3 / §2.4 / §3 兼容新增）；
- 新增字段/方法走本次 ADR；已冻结 FRZ-IPC-001~006 字段/错误码/envelope **不得修改**。

## 影响

### 架构影响

- 打通 Gateway→SQLite→Outbox 写链路，与 ADR-005 envelope、ADR-006 幂等 PK、ADR-009 socket ownership 一致；
- 不新增运行时组件，写链路沿用现有 UDS + 长度前缀 JSON + `UnitOfWork` 单连接事务。

### 开发影响

- `gateway/handlers.py` 新增 `turn_finalized_handler`；`gateway/registry.py` 注册方法；`app.py` 注入 UnitOfWork；
- `db/repositories.py`/`db/uow.py` 补 `trace_id` 透传（与 ADR-011 联动）；
- C 轨 `protocol_adapter` 需同步 `turn.finalized` 方法（ADR 签署后单独 PR，不阻塞本 PR 服务端）。

### 评测影响

- 失败路由验收按冻结 5 枚举断言（ADR-005）；新增方法路由按 FRZ-IPC-007 + 本 ADR 白名单断言。

### 安全影响

- `source_reference` 只承载受控引用，不承载正文（对齐事件契约 v1 §7）；
- 错误消息 `safe_error_code`，不回显原文/用户 ID/凭据；
- 跨用户隔离沿用 Repository 层 `user_id` 作用域。

## 回滚与替代条件

若未来决定废弃 `turn.finalized` 或改用其他写路径，可经新 ADR 撤销本 ADR：删除路由表条目与 handler，`memory.store` 维持 UNSUPPORTED 语义不变；冻结回写 `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-007 路由表）恢复原状。

## 证据与限制

- `deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:23/25`（FRZ-IPC-005、FRZ-IPC-007）
- `docs/day3/11_os_agent_event_contract_v1.md` §3.2 / §7（TurnFinalizedEvent 字段、Adapter 边界）
- `docs/day10/04_d5d_prerequisite_design_survey_20260826.md` §三（B-1 方案对比：A1 推荐）
- `docs/day10/05_d5d_task_list_20260826.md` §1.1（PR-1 ADR-010 内容）
- `memory-service/gateway/handlers.py` / `registry.py`、`memory-service/db/uow.py`（实现现状）

本 ADR 为文档/契约决策，不新增 Runtime 事实。批准记录：D 决策选方案 A1（待定）；Reviewer E（谢嘉然）签署（待定），签署后状态更新为「已采纳」，并回写 FRZ-IPC-007 路由表。
