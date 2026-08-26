# ADR-011：turns / memory_entries 新增 nullable `trace_id` 列（FRZ-DB-001 / B-2 方案 B1）

- **状态**：📝 提议（待 D 决策 + Reviewer E 签署）
- **日期**：2026-08-26
- **决策人**：周子腾（D）｜**Reviewer**：E（谢嘉然，待签）
- **责任轨道**：D（IPC/DB）为主，E 审查
- **决策版本**：`trace-id-columns-v1`
- **适用范围**：FRZ-DB-001 `turns` / `memory_entries` 表定义；关联 `docs/day3/11_os_agent_event_contract_v1.md` §3.2（metadata.traceId）、FRZ-IPC-006、checklist 5.2/5.4、ADR-010

## 背景

1. **FRZ-DB-001 冻结核心表 5 张**（`D4_DB_INITIAL_DESIGN_FREEZE_20260817.md:26`）：`turns` 无 `trace_id` 列（`memory-service/db/schema.py:43-54`），`memory_entries` 无 `trace_id` 列（`:56-75`）；`outbox` 有 `payload` Text JSON 列（`:77-90`）。
2. **checklist 溯源要求**：
   - 5.2「turns/memory_entries 落库写入 trace_id」——需在表上加列才能按 trace 直接溯源；
   - 5.4「Outbox 记录携带 trace_id（payload/字段）」——`outbox.payload` JSON 可承载，无需改 DDL。
3. **ID 三字段现状**（`docs/day10/04_d5d_prerequisite_design_survey_20260826.md` §2.2）：`trace_id` 已冻结（FRZ-IPC-006 请求字段之一；事件契约 `metadata.traceId` 可选，`source_trace_id→trace_id` 已统一），Gateway/embedding 层已提取回显，但 **turns/memory_entries/outbox 三表均无 trace_id 落点**；UoW/DAO 无 trace_id 参数。
4. **驱动方**：ADR-010 的 `turn.finalized` handler 是 trace_id 落库的驱动方，两者需同一 PR 或顺序落地形成完整溯源闭环。

## 候选方案

### 方案 B1：turns/memory_entries 新增 nullable `trace_id` 列（本 ADR 决策，推荐）

走 ADR 变更 FRZ-DB-001；新增 Alembic 迁移 `migrations/versions/002_add_trace_id.py`，`turns.trace_id`、`memory_entries.trace_id` 均为 `VARCHAR NULL`；同步 `db/schema.py`；DAO/UoW 透传；outbox 的 trace_id 走 `payload`（checklist 5.4，无需新增列）。

优点：

- 完整满足 checklist 5.2/5.4，回合/记忆条目可按 trace 直接溯源；
- nullable 新增列向后兼容，不破坏既有数据与 FTS5 触发器（trace_id 不入 FTS）；
- 与 ADR-010 的 `turn.finalized` handler 形成完整溯源闭环。

缺点：

- 冻结 DDL 变更，须走 ADR + Gate（nullable 新增列向后兼容，审查阻力小）。

### 方案 B2：仅 outbox payload 携带 trace_id（不新增列）

trace_id 只写入 `outbox.payload`（JSON 内嵌），turns/memory_entries 不落库。

- 工作量小，但**不满足验收**：checklist 5.2 明确要求「turns/memory_entries 落库写入 trace_id」；不落库则回合/记忆条目无法按 trace 直接溯源，任务 2 验收不完整。
- **仅作为**「冻结 DDL 阻力过大」时的降级折中。

### 方案 B3：trace_id 写入 memory_entries.content（JSON 正文内）

- **污染业务 content JSON**，破坏「content 为业务记忆正文」语义；检索/抽取会误读 trace_id；违反「日志/正文隔离」直觉。
- **结论**：否决。

## 决策

选择方案 B1：`trace-id-columns-v1`。**`turns` 与 `memory_entries` 各新增 nullable `trace_id` 列（`VARCHAR NULL`），经新迁移 `002_add_trace_id.py`（upgrade ADD / downgrade DROP，独立 revision，不与 001 冲突）落地；`db/schema.py` 同步为单一真相；`trace_id` 透传至 DAO/UoW 落库，outbox 的 trace_id 写入 `payload` JSON（5.4）。**

### DDL 定义（草案）

```sql
ALTER TABLE turns ADD COLUMN trace_id VARCHAR NULL;
ALTER TABLE memory_entries ADD COLUMN trace_id VARCHAR NULL;
```

- **迁移**：`migrations/versions/002_add_trace_id.py`（upgrade ADD / downgrade DROP，独立 revision id）
- **outbox**：不改表；`trace_id` 写入 `payload` JSON（checklist 5.4）
- **向后兼容**：nullable 新增列，既有行不受影响；FTS5 触发器不涉及 trace_id

### 变更控制

- `trace_id` 为 nullable 新增列，属 FRZ-DB-001 允许的「新增 optional 字段」扩展（`D4_DB_INITIAL_DESIGN_FREEZE_20260817.md:34` 变更控制「任何变更须走 ADR + Gate」）；
- 已冻结 FRZ-DB-001 既有列定义 **不得修改**。

## 影响

### 架构影响

- turns/memory_entries 支持按 trace 直接溯源，SQLite 仍为结构化真源；
- outbox.payload 携带 trace_id 使 Worker/消费侧可关联，不改 outbox 表结构。

### 开发影响

- `db/schema.py` 同步 `turns.trace_id` / `memory_entries.trace_id`（单一真相）；
- `db/repositories.py` `insert_turn`/`insert_memory_entry` 增加 `trace_id` 参数透传；
- `db/uow.py` `save_turn_with_outbox` 增加 `trace_id` 参数；outbox payload 携带 trace_id；
- 新增迁移 `002_add_trace_id.py` 与测试（迁移往返、落库值、FTS 触发器不受影响、软删除仍同步）。

### 评测影响

- 迁移往返由 L1 测试 + 麒麟 VM L2（`alembic upgrade head` + `.schema` 对照）验证。

### 安全影响

- `trace_id` 为内部追踪标识，非用户内容；无 PII；日志/正文隔离不受影响。

## 回滚与替代条件

若未来决定撤销 trace_id 列或改方案，可经新 ADR 撤销本 ADR：执行迁移 downgrade（DROP trace_id 列）恢复 FRZ-DB-001 原 DDL，DA0/UoW 参数回退；outbox.payload 中已写 trace_id 为历史数据，不影响既有消费语义。

## 证据与限制

- `deliverables/D4_DB_INITIAL_DESIGN_FREEZE_20260817.md:26/34`（FRZ-DB-001、变更控制）
- `memory-service/db/schema.py:43-90`（turns/memory_entries/outbox 表定义现状）
- `docs/day10/04_d5d_prerequisite_design_survey_20260826.md` §四（B-2 方案对比：B1 推荐）
- `docs/day10/05_d5d_task_list_20260826.md` §1.2（PR-1 ADR-011 内容）
- `docs/day3/11_os_agent_event_contract_v1.md` §3.2（metadata.traceId 可选）

本 ADR 为文档/契约决策，不新增 Runtime 事实。批准记录：D 决策选方案 B1（待定）；Reviewer E（谢嘉然）签署（待定），签署后状态更新为「已采纳」，并回写 FRZ-DB-001 表定义。
