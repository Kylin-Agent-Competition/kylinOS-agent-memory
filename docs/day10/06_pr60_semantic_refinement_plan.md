# PR60 语义细化方案（ADR-010/011 收紧至可冻结）

- **编制日期**：2026-08-26
- **编制人**：opencode（D 轨开发 Agent）｜适用轨道：D 为主，E 审查
- **基线**：PR #60 HEAD `b9f0bf3`（分支 `feat/d5d-pr0-contract-adr`，基 main @ `d12df5a`）
- **输入**：PR #60 Review（`lovezy0730-create`，2026-08-26，结论 **REWORK**：BLOCKER 0 / HIGH 5 / MEDIUM 若干 / LOW 若干）
- **目的**：使 ADR-010/011 达到"实现者读完后无需自行做架构决策即可直接实现"，逐项收口审查意见，提交复审

---

## 一、目标与原则

**目标**：消除审查指出的全部语义缺口，使 ADR-010/011 可冻结。

**三条总原则**（贯穿所有细化）：

1. **映射契约表述**：turn.finalized 冻结的是"D 轨 IPC 映射契约"，不是 C 轨事件对象；C 轨仍为 `FROZEN_CANDIDATE / BLOCKED_FOR_FINAL_FREEZE`，不得写"已冻结 TurnFinalizedEvent 字段"。
2. **唯一真源**：IPC envelope（FRZ-IPC-006）为权威值；payload.metadata 与其冲突 → `INVALID_REQUEST`。
3. **不修改冻结项既有定义**：FRZ-IPC-001~006 / FRZ-DB-001 既有字段/列一律不动，只做"新增 optional 字段 + 新增方法"。

---

## 二、逐项细化决策

### HIGH-1 — ADR-010 payload 与事件契约逐字段对齐

payload 字段表按 `docs/day3/11_os_agent_event_contract_v1.md` §3.2/§7 **逐字段复用 required/optional 语义**，修正 ADR-010 当前 3 处偏差：

| 字段 | 契约语义 | ADR-010 现状 | 细化为 |
|---|---|---|---|
| `schema_version` | required | **缺失** | 补入，required，接受 `1.x` |
| `occurred_at` | required | 误写 optional | 改 required |
| `collected_at` | required | 误写 optional | 改 required |

并显式写明：

- **`schema_version` 是 C 侧事件结构版本，`protocol_version` 是 D 侧 IPC envelope 版本（`"1.0"`），二者不同属**；
- turn.finalized 的 payload 校验用 `schema_version`，envelope 校验用 `protocol_version`；
- C 轨错误模型（`required`/`invalid_type`/`invalid_value`/`unsupported_schema_version` 等）统一映射到 IPC `INVALID_REQUEST`（safe_message 固定英文，不回显原值）。

### HIGH-2 — turn.finalized → turns/UoW 落库语义（本轮核心）

逐项给出可冻结语义，消除"实现者自行决断"空间：

| 问题 | 决定 |
|---|---|
| 新建 or 更新 | **Upsert**：按 `(conversation via session_id, host_turn_id)` 匹配——不存在 INSERT、存在 UPDATE（重投/refinalize 更新同一条，不重复计数） |
| `turn_index` 唯一来源 | **服务端计算**：同一事务内 `1 + COALESCE(MAX(turn_index),0) WHERE session_id=?`；事件不携带 |
| `original_user_text` 唯一来源 | **受控 resolver**，经 `source_reference` 解析正文（事件不内嵌正文，保持原文隔离） |
| resolver 层级/失败语义 | 归属 `memory-service/service/source_resolver.py`；返回 `Optional[ResolvedContent]`；解析失败且 turn 不存在 → `INTERNAL_ERROR`（safe），**禁止编造正文/空串替代**（`turns.original_user_text` NOT NULL 冻结） |
| resolver 生产状态 | 与 C 轨 `TurnExtractionAdapter` 一致标 `BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED`；PR-2 只交付测试/内存 resolver，**不声称真实正文通道已支持** |
| host↔db turn_id | 事件 `turn_id` = **host_turn_id**（宿主字符串）；DB `turns.id` = **db_turn_id**（Integer PK）；命名显式区分 |
| 响应 turn_id | data 返回 `{db_turn_id, host_turn_id, conversation_id}`（conversation_id = db conversations.id） |
| 其余列 | `model_request/model_response` 本轮不落（NULL）；`created_at` = 服务端时间；`occurred_at/collected_at/finalized_at` 仅入 outbox.payload，不落 turns（无冻结列） |

**联动 DDL**：turns 需新增唯一匹配键 → ADR-011 从"仅 trace_id 两列"扩展为 **turns 加 `trace_id` + `host_turn_id`（部分唯一索引 `UNIQUE(session_id, host_turn_id) WHERE host_turn_id IS NOT NULL`），memory_entries 加 `trace_id`**（推荐一次性收口；是否可接受见"待人工裁决项"）。

### HIGH-3 — trace_id / idempotency_key 唯一真源

采用 Reviewer 推荐，消除双真源：

- **envelope 为权威源**。`trace_id`：RequestContext/DB/outbox 取值 = envelope 值；metadata 中存在必须等于 envelope，否则 `INVALID_REQUEST`。
- `idempotency_key`：turn.finalized（写方法）收紧为**必填**（方法级约束，非改 FRZ-IPC-006 可选性）；取值顺序 envelope → 无则 metadata → 同提供不一致 `INVALID_REQUEST`；幂等三元组用合并后唯一值。
- **幂等冲突语义**（MEDIUM 一并收口）：相同三元组 + 不同请求指纹 → `INVALID_REQUEST`（防静默吞事件）；指纹 = 缓存 response JSON 内嵌 `_request_fingerprint`（sha256 规范化 method+语义字段），**不改 DDL**；TTL=24h / 失败不缓存 / `event_id` 不替代幂等键 保持不变。
- ID 三字段边界：`event_id` 事件身份（outbox.payload + 日志）、`request_id` envelope 请求身份（回显不落库）、`trace_id` 链路追踪（落库列）。

### HIGH-4 — 迁移命名（ADR-007 合规）

`002_add_trace_id.py` → **`20260826_add_trace_id.py`**。revision id 可与文件名独立（内部 `20260826_add_trace_id`），`down_revision = "001_initial_schema"`（已核实 001 的 revision 字面值）。

### HIGH-5 — downgrade 合规（不引入新冻结违约）

遵守"禁止删除列"红线，**不写 `ALTER DROP`**：

- upgrade：`ALTER TABLE ... ADD COLUMN`（nullable，标准 SQLite 支持）；
- downgrade：**表重建方式**——新建同构旧 schema 表 → `INSERT SELECT` 拷数据（丢弃 trace_id/host_turn_id）→ DROP 旧表 → RENAME；索引/触发器/FTS 同步重建。
- 替代方案（不推荐占本轮工期）：若坚持 `DROP COLUMN`，须另走 **新 ADR 修改既有迁移规则**（SQLite 3.49 支持，但违反红线且需 D/E 重签）。

### MEDIUM-1 — C 轨状态表述

唯一表述："基于 C 轨 `FROZEN_CANDIDATE` 的 `TurnFinalizedEvent` **候选契约**形成 D 轨 **IPC 映射**契约，经 D/E 交叉审查后冻结**跨轨映射**"。删除"事件契约 v1 已冻结 TurnFinalizedEvent 字段"。

### MEDIUM-2 — 依据可追溯（已核实 Reviewer 属实）

`docs/day10/04_*` 与 `docs/day10/05_*` 两份文档**在工作树未跟踪**（`git ls-files` 确认，PR HEAD 仅 2 个 ADR 文件）→ **纳入 PR-1 一并提交**，并在 ADR 内补关键论证摘要（B-1/B-2 方案对比结论），保证 ADR 自身可独立可读。

### MEDIUM-4 — protocol_version

保持 `"1.0"`，ADR 写明兼容矩阵：新客户端 + 旧服务端 → `UNSUPPORTED_METHOD`；旧客户端 + 新服务端 → 旧方法行为不变。

### MEDIUM-5 — trace_id 安全表述

改"`trace_id` 按**非正文的受控追踪标识**处理；**不得假设外部输入的 trace_id 永不含敏感信息**，日志与审计仍按受控标识处理"。

### MEDIUM-6 — 回写落点明确

指定载体：**D/E 签署后、合并前，由本 PR 追加 commit 回写** FRZ-IPC-007 路由表与 FRZ-DB-001 表定义，并同步两份 ADR 状态为"已采纳"——杜绝"ADR 已采纳但 freeze 文档旧定义"的双真源。

### LOW-1 — README 索引

`docs/adr/README.md` 追加 ADR-010/011 行，状态"提议（待 D 决策 + Reviewer E 签署）"，与正文一致。

---

## 三、变更文件清单

| 文件 | 动作 |
|---|---|
| `docs/adr/010-turn-finalized-method.md` | 改写（HIGH-1/2/3、MEDIUM-1/4） |
| `docs/adr/011-trace-id-columns.md` | 改写（trace_id + host_turn_id、HIGH-4/5、MEDIUM-5） |
| `docs/day10/04_d5d_prerequisite_design_survey_20260826.md` | 纳入 commit + 迁移/响应命名一致性同步（MEDIUM-2） |
| `docs/day10/05_d5d_task_list_20260826.md` | 纳入 commit + 迁移/响应命名一致性同步（MEDIUM-2） |
| `docs/adr/README.md` | 登记 ADR-010/011（LOW-1） |
| `deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md` | 签署后回写 FRZ-IPC-007 |
| `deliverables/D4_DB_INITIAL_DESIGN_FREEZE_20260817.md` | 签署后回写 FRZ-DB-001 |

---

## 四、实施顺序

1. 改写 ADR-010/011；
2. 纳入 `04/05` 依据文档 + README 索引；
3. 推送 PR HEAD 更新，请求 E 复审；
4. E 签署 → 追加回写 commit（FRZ-IPC-007 / FRZ-DB-001）；
5. PR-2 按新契约实现：`turn_finalized_handler` + `20260826_add_trace_id.py`（重建式 downgrade）+ resolver seam + 幂等指纹 + 对应 L0/L1 测试与 L2 清单。

---

## 五、人工裁决结论（2026-08-26 已裁决，ADR 已按其改写）

| # | 裁决项 | 结论 |
|---|---|---|
| 1 | host_turn_id 列并入 ADR-011 | ✅ **并入**：turns 增 `trace_id` + `host_turn_id`（部分唯一索引），memory_entries 增 `trace_id` |
| 2 | 响应字段命名 | ✅ **替换原 `turn_id` 命名**：data = `{db_turn_id, host_turn_id, conversation_id}` |
| 3 | 生产 resolver 缺失 INSERT 场景 | ✅ **接受返回 `INTERNAL_ERROR`**（safe；禁止编造正文/空串） |
| 4 | 幂等指纹存储位置 | ✅ **内嵌缓存 response JSON**（`_request_fingerprint`，无 DDL 变更） |

四项裁决已全部落定并反映到 ADR-010/011 改写稿（见 `docs/adr/010-turn-finalized-method.md`、`docs/adr/011-trace-id-columns.md`）。

---

## 六、红线自查（回归）

- 未修改冻结 FRZ-IPC-001~006 / FRZ-DB-001 既有定义；只新增 optional 字段/方法；
- 不内嵌正文，原文隔离，source_reference resolver 边界保持；
- 无 resolver 时拒绝（INTERNAL_ERROR）而非编造正文，符合 `[02 §16.14]` 假实现红线；
- 迁移 downgrade 采用表重建，遵守 `[ADR-007]`"禁止删除列"。

*本方案为语义细化计划，落盘备查；ADR 改写与 PR-2 实现严格按 `kylin-memory-dev` SOP 与冻结变更流程执行。*