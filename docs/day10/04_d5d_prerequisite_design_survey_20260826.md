# D5-D 前置设计调查报告：写链路入口（B-1）与 trace_id 落库（B-2）

- **编制日期**：2026-08-26
- **编制人**：opencode（D 轨开发 Agent）｜适用轨道：D 为主，E 审查，C/B 协作
- **调查基线**：`main` @ `d12df5a`（PR#52/#57/#51/#56 已合并）
- **目标任务**：D5-D —— ① 打通 Gateway→SQLite→Outbox；② 统一 trace_id/request_id/event_id；③ health + 结构化日志
- **依据文档**：`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-001~007 + ALIGN-001~005）、`D4_IPC_PROTOCOL_FREEZE_20260807.md`、`D4_DB_INITIAL_DESIGN_FREEZE_20260817.md`（FRZ-DB-001~005/FRZ-CFG-001）、`D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md`、`D4_IMPLEMENTATION_PUSH_CHECKLIST_20260824.md`、`docs/day3/11_os_agent_event_contract_v1.md`、`docs/adr/005~009`、`docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`、`docs/day10/01_task_card.md`/`02_development_report.md`/`03_pr52_review_unresolved_checklist.md`

---

## 一、结论速览

| 决策点 | 推荐方案 | 是否需 ADR | 预计工作量 | 主要风险 |
|--------|---------|:---:|:---:|---------|
| B-1 写链路 IPC 入口 | **A1：新增 `turn.finalized` 方法**（对齐事件契约 v1） | 是（FRZ-IPC-007 变更） | 中（约 0.5~1 人日） | 冻结流程 + C 轨 client 同步 |
| B-2 trace_id 落库 | **B1：turns/memory_entries 新增 nullable `trace_id` 列** + outbox payload 携带 | 是（FRZ-DB-001 变更） | 中（约 0.5~1 人日） | 冻结 DDL 变更 + 迁移 |
| 任务 3 health/日志 | 无契约冲突，纯新增 | 否 | 小~中（约 0.5 人日） | 低 |

**总体判断**：D5-D 无「代码级硬阻塞」，但 B-1/B-2 均触及**冻结契约变更**，必须先走 ADR + D/E 签署再动代码；其余（health 增补、JSON 结构化日志）可并行先行。与 C 轨（PR#49 client）、B 轨（TD-018/019/020）存在跨轨依赖，需协调。

---

## 二、现状梳理（调查结果）

### 2.1 写链路（Gateway→SQLite→Outbox）现状

| 层 | 已实现（main @ d12df5a） | 缺口 |
|----|--------------------------|------|
| IPC 路由 | FRZ-IPC-007 冻结 3 活跃方法：`echo`/`health`/`memory.retrieve`；`memory.store` → UNSUPPORTED_METHOD；`evidence.record` 已按 P0-4 移除；`memory.forget`/`extract_preference`/`resolve_conflict` DEFERRED | **无任何写方法**（checklist Phase 4.1 要求的 TurnFinalizedEvent 写入口不存在） |
| Gateway | `gateway/server.py`（UDS + 长度前缀 JSON + 64KB + 5 错误码 + deadline 事后判定）、`gateway/registry.py`（HandlerRegistry，未注册 → UNSUPPORTED_METHOD）、`gateway/handlers.py`（echo/health/retrieve/store 四 handler） | 无写 handler；`RequestContext` 已有 `request_id/trace_id/user_id/session_id` 字段，但无 handler 消费 |
| SQLite | 5 表 + 4 冻结索引 + FTS5 + 触发器（`db/schema.py` + `001_initial_schema.py`）；DAO（`db/repositories.py`）；UoW（`db/uow.py` `save_turn_with_outbox` 已实现：conversation upsert + turn 插入 + outbox 入队**同事务**） | `insert_turn`/`save_turn_with_outbox` **均无 trace_id 参数**；无调用方（没有任何 handler 调 UoW） |
| Outbox | `outbox/worker.py`：轮询/退避/DL/幂等缓存清理；consumer=None（无 consumer 真实失败退避，不假装成功） | consumer 未接线（TD-D4D-001，关联 R-9）；单事务批量处理持锁（TD-D4D-003） |

**关键事实**：
- 事件契约 v1（`docs/day3/11_os_agent_event_contract_v1.md`）已冻结 `TurnFinalizedEvent`（C++ 结构 + JSON 字段：`metadata.eventId/traceId/userId/sessionId/turnId/idempotencyKey/occurredAt/collectedAt/sourceReference` + `final_message_id/is_final/finalization_reason/stop_reason/retry_of_turn_id/tool_call_ids/finalized_at`），但标注「本文只冻结候选接口，不宣称事件已在宿主发布」，真实宿主映射 `BLOCKED/PARTIAL`（TD-007/008/009、R-ARCH-05 In Progress）。
- **写链路的「事件来源」与「服务端落库」是两件事**：D5-D 打通的是服务端链路（模拟/测试客户端发事件 → Gateway → UoW → SQLite+Outbox），不依赖 C 轨真实 Hook 端到端；真实 Hook 接入（R-ARCH-05）是 C 轨范围，不阻塞 D5-D 服务端实现。

### 2.2 ID 三字段现状（任务 2）

| 字段 | 冻结协议 | 代码现状 | 缺口 |
|------|---------|---------|------|
| `request_id` | FRZ-IPC-006 请求 7 字段之一，FROZEN | Gateway `_dispatch` 已提取并回显 | 未落库（turns 表无列） |
| `trace_id` | FRZ-IPC-006 请求 7 字段之一，FROZEN；事件契约 `metadata.traceId`（可选，source_trace_id→trace_id 已统一） | Gateway 已提取并回显；embedding 已回显 | **turns/memory_entries/outbox 三表均无 trace_id 列**（冻结 DDL 如此）；UoW/DAO 无 trace_id 参数 |
| `event_id` | 事件契约 `metadata.eventId` 必填，不替代幂等键；`fingerprint.py:65` `idempotency_key or event_id` 语义保持 | 事件层语义已确认 | 仅需文档核对（checklist 5.3），不阻塞 |

### 2.3 health + 日志现状（任务 3）

| 项 | 现状 | 缺口 |
|----|------|------|
| health | `health_handler` 返回 `status/db/methods`（db 走真实 SELECT 1） | 缺 outbox backlog（checklist 6.2；`worker.metrics()` 已实现 backlog/oldest_pending/dead_letter，**现成可接**） |
| 路由名 | Gateway `health`；embedding 子服务 `memory.health`（ADR-008 已裁决子服务方法域） | 无冲突，6.1 已由 ADR-008/009 收敛 |
| 结构化日志 | `logging_setup.py`：文本格式（asctime levelname name threadName message） | **无 JSON 日志**（checklist 6.3 要求每行 `trace_id/request_id/event_id/level/ts`）；无日志 filter 注入 ID；PII 脱敏仅靠业务层自觉（6.5） |

---

## 三、B-1 方案对比：写链路 IPC 入口方法

### 背景
checklist Phase 4.1：「Outbox 同事务写入 = TurnFinalizedEvent → SQLite INSERT + Outbox INSERT 同事务」。但 FRZ-IPC-007 冻结路由**无写方法**，`memory.store` 明确「未实现返回 UNSUPPORTED_METHOD 符合预期」（Gate 0 结论）。故打通写链路必须先定「事件怎么进来」。

### 方案 A1：新增 `turn.finalized` 方法（推荐）
- **内容**：FRZ-IPC-007 路由表新增 `turn.finalized`（写方法，payload = 事件契约 v1 `TurnFinalizedEvent` 字段），走 ADR 变更流程；Gateway 新增 handler：解析 payload → `RequestContext` 注入 `user_id/session_id/trace_id/idempotency_key` → `UnitOfWork.save_turn_with_outbox` 同事务落库+入队。
- **工作量**：
  1. ADR-010 文档（方案描述、payload 字段、错误语义、与事件契约 v1 对齐、回滚）——约 2~3h
  2. `gateway/handlers.py` 新增 `turn_finalized_handler`（含字段校验、UNSUPPORTED/INVALID_REQUEST 映射）——约 2h
  3. `db/repositories.py` `insert_turn`/`save_turn_with_outbox` 补 trace_id 透传（与 B-2 联动）——约 1h
  4. 契约测试（L0/L1）：正反用例、幂等、用户隔离、事务回滚——约 3~4h
  5. L2 清单更新（麒麟 VM 模拟客户端端到端）——约 1h
- **预计**：0.5~1 人日（不含 ADR 签署等待）。
- **风险**：
  - 冻结变更流程风险：FRZ-IPC-007 变更须 ADR + D 决策 + Reviewer E 签署；周期取决于 E 响应。
  - 跨轨依赖：C 轨 client（PR#49）的 `protocol_adapter` 需同步新增方法（当前 CHANGES_REQUESTED 未合并）；若 C 轨不合并，可用测试客户端验证，不阻塞服务端。
  - payload 字段校验需与事件契约 v1 严格对齐（必填/可选），避免语义漂移。

### 方案 A2：启用 `memory.store`（从 UNSUPPORTED 转为真实写路径）
- **内容**：不新增方法，把现有 `memory.store` 从「返回 UNSUPPORTED_METHOD」改为真实写实现。
- **工作量**：与 A1 相近（handler 实现 + 测试 + ADR），但省去路由表新增（仍属 FRZ-IPC-007 语义变更，需 ADR）。
- **风险（高于 A1）**：
  - **语义不清**：`memory.store` 冻结语义是「存记忆条目」，与 `TurnFinalizedEvent`（回合事件驱动）不是同一抽象；硬塞回合事件会扭曲契约，后续 E 轨业务（memory entry 管理）与事件写入混用易产生歧义。
  - Gate 0 结论「store 未实现符合预期」的反转需要更强论证。
- **结论**：不推荐作为主方案，可作为 A1 的备选。

### 方案 A3：写路径不经 IPC（内部直连 / Hook 直写 DAO）
- **内容**：事件由 C 轨 Hook 进程内直接调 DAO，不走 Gateway。
- **风险（高）**：破坏「IPC Gateway → Application Service」分层（checklist Phase 2.2 统一 METHOD_ROUTER 意图）；跨进程边界（Hook 与 Memory Service 不同进程）无法直连 Python DAO；违背冻结「UDS 统一入口」口径（ADR-009）。
- **结论**：否决。

### B-1 推荐
**方案 A1（新增 `turn.finalized`）**。理由：与事件契约 v1 命名/字段天然对齐；不动 `memory.store` 既有语义；为后续 `tool.execution`（ToolExecutionEvent）、`memory.ingest` 等写方法预留一致模式。

---

## 四、B-2 方案对比：trace_id 落库

### 背景
checklist 5.2「turns/memory_entries 落库写入 trace_id」、5.4「Outbox 记录携带 trace_id（payload/字段）」。冻结 FRZ-DB-001 三表均无 trace_id 列；outbox 有 `payload` JSON 列（可承载 trace_id 而不改 DDL）。

### 方案 B1：turns/memory_entries 新增 nullable `trace_id` 列（推荐，完整满足 5.2）
- **内容**：走 ADR 变更 FRZ-DB-001；新增 Alembic 迁移 `20260826_add_trace_id.py`（`turns.trace_id`/`host_turn_id`、`memory_entries.trace_id`，均 nullable，不破坏既有行；downgrade 走表重建满足 ADR-007 红线）；同步 `db/schema.py`；DAO/UoW 透传；outbox 的 trace_id 走 payload（5.4，无需列）。
- **工作量**：
  1. ADR-011 文档（列定义、nullable、迁移策略、回滚=downgrade）——约 2h
  2. 迁移 `20260826_add_trace_id.py` + `schema.py` 同步——约 1~2h
  3. `repositories.py`（insert_turn/insert_memory_entry）+ `uow.py` 透传——约 1h
  4. 测试（迁移往返、落库值、FTS 触发器不受影响、软删除仍同步）——约 2~3h
  5. L2 更新（VM alembic upgrade 后 schema 对照）——约 1h
- **预计**：0.5~1 人日。
- **风险**：
  - 冻结 DDL 变更：FRZ-DB-001 变更控制「任何变更须走 ADR + Gate」；nullable 新增列向后兼容，不破坏既有数据，审查阻力小。
  - 与 B-1 联动：`turn.finalized` handler 是 trace_id 落库的驱动方，两者需同一 PR 或顺序落地。
  - FTS5 触发器不涉及 trace_id（不入 FTS），无额外影响。

### 方案 B2：仅 outbox payload 携带 trace_id（不新增列）
- **内容**：trace_id 只写入 `outbox.payload`（JSON 内嵌），turns/memory_entries 不落库 trace_id；溯源通过 outbox.payload 关联。
- **工作量**：小（约 0.5 天，仅改 payload 组装 + 测试）。
- **风险（不满足验收）**：checklist 5.2 明确要求「turns/memory_entries 落库写入 trace_id」；不落库则回合/记忆条目无法按 trace 直接溯源，任务 2 验收不完整。仅作为「冻结 DDL 阻力过大」时的降级折中。

### 方案 B3：trace_id 写入 `memory_entries.content`（JSON 正文内）
- **风险（高，否决）**：污染业务 content JSON，破坏「content 为业务记忆正文」的语义；检索/抽取会误读 trace_id；违反「日志/正文隔离」直觉。**否决**。

### B-2 推荐
**方案 B1（新增 nullable 列 + 迁移）+ outbox payload 携带**。理由：完整满足 checklist 5.2/5.4；nullable 新增列向后兼容、风险可控；与 B-1 的 `turn.finalized` handler 形成完整溯源闭环。

---

## 五、任务 3（health + 结构化日志）方案要点

| 子项 | 方案 | 工作量 | 风险 |
|------|------|:---:|------|
| health 增补 | `health_handler` 调 `OutboxWorker.metrics()` 返回 `outbox_backlog/oldest_pending_age/dead_letter`（对齐 `embedding_metrics.py` 语义）；busy 时降级 | 小（2~3h） | 低；注意 health 不得因 DB/Outbox 故障抛错（降级返回 degraded） |
| JSON 结构化日志 | 新增 `memory-service/observability/`（或 `logging_setup.py` 扩展）：自定义 `logging.Filter` 注入 `trace_id/request_id/event_id`（从 `threading.local`/context 取），JSON Formatter 输出；业务日志点改为结构化调用 | 中（0.5 天） | 中；需保证 PII 脱敏（filter 层禁止 content 字段）；与现有文本日志兼容（可双输出） |
| 日志贯穿 | Gateway `_dispatch` 设置当前请求 ID → 各层 logger 自动携带（同一 trace 可关联） | 中 | 需线程局部变量设计，避免泄漏到其他连接线程 |

---

## 六、总体推进建议（组合拳）

```
PR-1（契约先行，纯文档）: ADR-010（turn.finalized 方法）+ ADR-011（trace_id 列）
   ├─ 签署：D 决策 → Reviewer E 签署 → 回写 FRZ-IPC-007 / FRZ-DB-001
PR-2（代码主体）: turn.finalized handler + trace_id 列迁移 + UoW/DAO 透传
   + health 增补 + JSON 结构化日志（三个任务一次收口）
   ├─ L0/L1：契约测试全绿；无假实现（模拟事件走真实 UoW 落库）
PR-3（L2 麒麟 VM）: alembic upgrade + schema 对照 + 模拟客户端端到端
   （事件 → Gateway → SQLite + Outbox → Worker 真实失败/退避，consumer 仍注入点）
```

**并行可先行（不依赖 ADR）**：
- health 增补 backlog（`worker.metrics()` 现成）
- JSON 结构化日志框架（纯新增，无契约冲突）
- checklist 5.3 event_id 语义文档核对

**跨轨依赖与前置协调**：
- C 轨：PR#49（Memory Client）CHANGES_REQUESTED 未合并；`protocol_adapter` 需同步 `turn.finalized` 方法（可在 ADR 签署后单独 PR）。
- B 轨：TD-018/019/020（filter_fingerprint 假值/version_id 硬编码/timeout 硬编码）标注「D5 接线时」——**接线 Outbox consumer 前必须关闭**；本次若仍不接 consumer（保持注入点），不阻塞。
- 内部 TD：TD-D4D-001（consumer 未接线）、TD-D4D-003（claim→commit→process→mark 重构）——若本次不接 consumer，两者继续延期，不阻塞 PR-2；TD-D4D-002（deadline 抢占式）在慢 handler（检索）接线前不触发。
- R-9（Vector 接入方式）：PR#51 已用 vector_cli 子进程桥证明可行，但正式确认待 D；本次 Outbox consumer 仍为注入点，不依赖。

---

## 七、风险汇总与缓解

| # | 风险 | 等级 | 缓解 |
|---|------|:---:|------|
| 1 | FRZ-IPC-007/FRZ-DB-001 冻结变更被 E 驳回 | 中 | ADR 提前与 E 对齐；nullable 列 + 新方法均为向后兼容扩展（符合「允许新增 optional」精神） |
| 2 | C 轨 client 不同步导致端到端缺客户端 | 低 | 服务端用测试/模拟客户端验证；C 轨单独 PR 跟进 |
| 3 | 写链路 payload 校验与事件契约 v1 漂移 | 中 | handler 复用事件契约字段定义；契约测试锁定 |
| 4 | 结构化日志 trace_id 泄漏到其他连接 | 中 | 线程局部存储 + 每连接清理；L1 并发测试覆盖 |
| 5 | 迁移 002 与既有 001 冲突 | 低 | 独立 revision id + downgrade 测试；VM L2 验证 |

---

## 八、参考文档索引

- `deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-001~007、ALIGN-001~005、变更控制）
- `deliverables/D4_IPC_PROTOCOL_FREEZE_20260807.md`（§1.3/§2.4/§6.3 方法路由、变更控制）
- `deliverables/D4_DB_INITIAL_DESIGN_FREEZE_20260817.md`（FRZ-DB-001~005、变更控制、附录 A/B/C）
- `deliverables/D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md`（5 表 + Outbox 失败路由）
- `deliverables/D4_IMPLEMENTATION_PUSH_CHECKLIST_20260824.md`（Phase 0~6、验收标准）
- `docs/day3/11_os_agent_event_contract_v1.md`（TurnFinalizedEvent 契约 v1、§7 Adapter 边界）
- `docs/day10/01_task_card.md` / `02_development_report.md` / `03_pr52_review_unresolved_checklist.md`
- `docs/adr/005~009`（错误码/envelope、幂等 PK、迁移命名、子服务方法域、socket ownership）
- `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md`（TD-D4D-001/002/003、TD-018/019/020、TD-IPC-001~004）

---

*本报告为调查与方案评估，不构成已批准方案；B-1/B-2 的 ADR 起草、代码实现与证据分层须按 `kylin-memory-dev` SOP 与冻结变更流程执行。*
