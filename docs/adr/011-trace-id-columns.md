# ADR-011：turns/memory_entries 新增 nullable `trace_id` / `host_turn_id` 列（FRZ-DB-001 / B-2 方案 B1 扩展）

- **状态**：✅ 已采纳（D 决策 + Reviewer E 签署，2026-08-27）
- **日期**：2026-08-26（PR #60 Review 后语义细化修订）
- **决策人**：周子腾（D）｜**Reviewer**：E（谢嘉然，已签 2026-08-27）
- **责任轨道**：D（IPC/DB）为主，E 审查
- **决策版本**：`trace-id-columns-v1`
- **适用范围**：FRZ-DB-001 `turns` / `memory_entries` 表定义；关联 `docs/day3/11_os_agent_event_contract_v1.md` §3.2（metadata.traceId，**FROZEN_CANDIDATE**）、FRZ-IPC-006、ADR-007、ADR-010、checklist 5.2/5.4

---

## 背景

1. **FRZ-DB-001 冻结核心表 5 张**（`D4_DB_INITIAL_DESIGN_FREEZE_20260817.md:26`）：`turns` 无 `trace_id` / `host_turn_id` 列（`memory-service/db/schema.py:43-54`），`memory_entries` 无 `trace_id` 列（`:56-75`）；`outbox` 有 `payload` Text JSON 列（`:77-90`）。
2. **checklist 溯源要求**：
   - 5.2「turns/memory_entries 落库写入 trace_id」——需在表上加列才能按 trace 直接溯源；
   - 5.4「Outbox 记录携带 trace_id（payload/字段）」——`outbox.payload` JSON 可承载，无需改 DDL。
3. **ADR-010 落库语义联动**：turn.finalized = **Upsert**，匹配键 `(conversation, host_turn_id)`；事件 `turn_id`（host_turn_id）与 DB `turns.id`（db_turn_id）显式区分 → `turns` 需新增 nullable `host_turn_id` 列承载宿主 ID 并作为匹配键。
4. **迁移命名红线（ADR-007）**：基线 `001_initial_schema.py`（例外）；后续增量迁移一律 `YYYYMMDD_<description>.py`，二者不混用；并明确「禁止删除列」——列结构回滚采用 **表重建/重命名** 方式。

---

## 候选方案

### 方案 B1：turns/memory_entries 新增 nullable `trace_id` 列 + turns 新增 nullable `host_turn_id` 列（本 ADR 决策，推荐）

走 ADR 变更 FRZ-DB-001；新增 Alembic 迁移 `migrations/versions/20260826_add_trace_id.py`：
`turns` 增 `trace_id VARCHAR NULL` + `host_turn_id VARCHAR NULL`（含部分唯一索引）；`memory_entries` 增 `trace_id VARCHAR NULL`；同步 `db/schema.py`；DAO/UoW 透传；outbox 的 trace_id 走 `payload`（checklist 5.4，无需新增列）。

优点：

- 完整满足 checklist 5.2/5.4，回合/记忆条目可按 trace 直接溯源；
- `host_turn_id` 使 ADR-010 的 Upsert 匹配 (`session_id, host_turn_id`) 可落库成立，消除 host/db 双 ID 歧义；
- nullable 新增列向后兼容，不破坏既有数据与 FTS5 触发器（trace_id/host_turn_id 不入 FTS）；
- 与 ADR-010 的 `turn.finalized` handler 形成完整溯源 + 幂等闭环。

缺点：

- 冻结 DDL 变更，须走 ADR + Gate（nullable 新增列 + 部分唯一索引均向后兼容，审查阻力小）。

### 方案 B2：仅 outbox payload 携带 trace_id（不新增列）

trace_id 只写入 `outbox.payload`（JSON 内嵌），turns/memory_entries 不落库。

- 工作量小，但**不满足验收**：checklist 5.2 明确要求「turns/memory_entries 落库写入 trace_id」；且无 `host_turn_id` 列则 ADR-010 的 Upsert 匹配键无处承载，写语义无法闭合。
- **仅作为**「冻结 DDL 阻力过大」时的降级折中。

### 方案 B3：trace_id 写入 memory_entries.content（JSON 正文内）

- **污染业务 content JSON**，破坏「content 为业务记忆正文」语义；检索/抽取会误读 trace_id；违反「日志/正文隔离」直觉。
- **结论**：否决。

---

## 决策

选择方案 B1：`trace-id-columns-v1`。**`turns` 新增 nullable `trace_id` + `host_turn_id` 列，`memory_entries` 新增 nullable `trace_id` 列，经新迁移 `20260826_add_trace_id.py` 落地；`db/schema.py` 同步为单一真相；`trace_id` 透传至 DAO/UoW 落库，outbox 的 trace_id 写入 `payload` JSON（5.4）。**

### DDL 定义（草案）

```sql
ALTER TABLE turns ADD COLUMN trace_id VARCHAR NULL;
ALTER TABLE turns ADD COLUMN host_turn_id VARCHAR NULL;
ALTER TABLE memory_entries ADD COLUMN trace_id VARCHAR NULL;

-- 部分唯一索引：ADR-010 Upsert 匹配键（SQLite 允许多 NULL，部分索引保证非空才唯一）
CREATE UNIQUE INDEX idx_turns_host_turn_id
    ON turns (session_id, host_turn_id)
    WHERE host_turn_id IS NOT NULL;
```

- **迁移**：`migrations/versions/20260826_add_trace_id.py`
  - **命名**：`YYYYMMDD_<description>.py`（ADR-007 红线；废弃序号 `002_add_trace_id.py`）。
  - **revision**：revision id 与文件名可独立定义；内部 `revision = "20260826_add_trace_id"`，`down_revision = "001_initial_schema"`（已核实 001 字面值），版本链 `001_initial_schema → 20260826_add_trace_id`。
  - **upgrade**：`ALTER TABLE ... ADD COLUMN`（nullable 新增列，标准 SQLite 支持，每条 ALTER 单一列）。
  - **downgrade**：**遵守「禁止删除列」冻结红线，不得 `ALTER DROP COLUMN`**；采用**表重建/重命名**方式回滚，对 turns 与 memory_entries 依次执行：
    1. 新建同构旧 schema 表（按 001 定义，不含 trace_id / host_turn_id）；
    2. `INSERT INTO 新表 (…) SELECT 旧表原列（显式列清单，丢弃新增列）`；
    3. `DROP TABLE` 旧表（其附加触发器随之移除）；
    4. `ALTER TABLE 新表 RENAME TO` 旧表名 + 重建冻结索引（`idx_turns_session` / `idx_memory_user_type` / `idx_memory_deleted`）；
    5. memory_entries 重建后**重建 4 个 FTS5 同步触发器**（`memory_fts_ai/au_content/au_deleted/ad`，`CREATE TRIGGER IF NOT EXISTS`）并**同步回填 memory_fts**（先清空再按 `SELECT id, content, entry_type, user_id FROM memory_entries` 重灌，保证 FTS 与正文一致）。
- **outbox**：不改表；`trace_id` 写入 `payload` JSON（checklist 5.4）
- **向后兼容**：nullable 新增列 + 部分唯一索引，既有行不受影响；FTS5 触发器不涉及 trace_id / host_turn_id

### 变更控制

- `trace_id` / `host_turn_id` 为 nullable 新增列 + 新增辅助索引，属 FRZ-DB-001 允许的「新增 optional 字段」扩展（`D4_DB_INITIAL_DESIGN_FREEZE_20260817.md:34` 变更控制「任何变更须走 ADR + Gate」）；
- 已冻结 FRZ-DB-001 既有列定义 **不得修改**。

---

## 影响

### 架构影响

- turns/memory_entries 支持按 trace 直接溯源；`host_turn_id` 支撑 ADR-010 Upsert 写语义（重投/refinalize 更新同一条）；SQLite 仍为结构化真源；
- outbox.payload 携带 trace_id 使 Worker/消费侧可关联，不改 outbox 表结构。

### 开发影响

- `db/schema.py` 同步 `turns.trace_id` / `turns.host_turn_id` / `memory_entries.trace_id` + 部分唯一索引（单一真相）；
- `db/repositories.py` `insert_turn` 增加 `trace_id` / `host_turn_id` 参数；`insert_memory_entry` 增加 `trace_id` 参数；
- `db/uow.py` `save_turn_with_outbox` 增加 `trace_id` / `host_turn_id` 参数并实现 upsert 匹配逻辑；outbox payload 携带 trace_id；
- 新增迁移 `20260826_add_trace_id.py` 与测试（迁移往返、落库值、索引/触发器/FTS 完整性、软删除仍同步）。

### 评测影响

- 迁移往返由 L1 测试 + 麒麟 VM L2（`alembic upgrade head` + `.schema` 对照，`downgrade base` schema 与 001 一致）验证。

### 安全影响

- `trace_id` / `host_turn_id` 均按**非正文的受控追踪标识**处理；**不得假设外部输入永不含敏感信息**，日志与审计仍按受控标识处理；
- 两列均不入 FTS、不作为业务正文字段，日志/正文隔离不受影响。

---

## 回滚与替代条件

若未来决定撤销 trace_id / host_turn_id 列或改方案，可经新 ADR 撤销本 ADR：执行迁移 **downgrade（表重建回滚）**恢复 FRZ-DB-001 原 DDL，DAO/UoW 参数回退；outbox.payload 中已写 trace_id 为历史数据，不影响既有消费语义。

---

## 证据与限制

- `deliverables/D4_DB_INITIAL_DESIGN_FREEZE_20260817.md:26/34`（FRZ-DB-001、变更控制）
- `docs/adr/007-db-migration-baseline-naming.md`（ADR-007：基线例外 + `YYYYMMDD_<desc>.py` + 禁止删除列 + 重建回滚）
- `memory-service/db/schema.py:43-90`（turns/memory_entries/outbox 表定义现状）
- `docs/day10/04_d5d_prerequisite_design_survey_20260826.md` §四（B-2 方案对比：B1 推荐；**本 PR 已纳入仓库**）
- `docs/day10/05_d5d_task_list_20260826.md` §1.2（PR-1 ADR-011 内容；**本 PR 已纳入仓库**）
- `docs/day10/06_pr60_semantic_refinement_plan.md`（本方案；PR #60 Review 逐项收口）
- `docs/day3/11_os_agent_event_contract_v1.md` §3.2（metadata.traceId 可选）
- `docs/adr/010-turn-finalized-method.md`（联动：host_turn_id 为 Upsert 匹配键、trace_id 唯一真源）

本 ADR 为文档/契约决策，不新增 Runtime 事实。批准记录：**D（周子腾）2026-08-27 决策选方案 B1**；**Reviewer E（谢嘉然）2026-08-27 签署**；状态更新为「已采纳」，并在**本 PR 内追加 commit 回写** FRZ-DB-001 表定义。