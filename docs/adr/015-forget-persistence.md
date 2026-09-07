# ADR-015：精准遗忘持久化与 Outbox 优先级

- **状态**：✅ 已采纳（D 已决策；Reviewer E 已签署）
- **日期**：2026-09-02
- **决策人**：D（周子腾）
- **Reviewer**：E（谢嘉然），PR #112 `APPROVED`（2026-09-02）
- **决策版本**：`d10d-adr015-v1`
- **适用范围**：FRZ-DB-001 扩展
- **对外能力状态**：`PARTIAL / staged implementation`；本 ADR 是设计与契约决策，不构成 Runtime 完成或麒麟宿主验证证据
- **权威依据**：`docs/day10/16_d10d_forget_contract_plan_v0.3.md`、`docs/day10/17_d10d_adr015_019_draft.md`、PR #99、PR #112

## 背景

现有 FRZ-DB-001 没有遗忘计划与最小审计的持久化结构，`outbox` 也没有删除任务优先级。精准遗忘必须持久化 Preview/Execute 状态、一次性确认凭据的哈希及零正文审计，同时保证遗忘/撤回任务优先于普通索引任务。

## 候选方案

1. **方案 A（采纳）**：新增 `forget_plan`、`forget_audit`；为 `outbox` 增加 `priority`、部分索引，并将 `aggregate_type` CHECK 扩展为包含 `forget`。
2. 仅增加 `forget_plan`，审计并入业务记忆表：会污染业务正文与检索语义。
3. 仅以 `outbox` 承载计划和审计：队列消费后不能作为持久化审计真源。

## 决策

采纳方案 A：

- 新增 `forget_plan` 和 `forget_audit`，既有 FRZ-DB-001 表、列、索引、触发器及 FTS5 定义不变。
- `outbox` 仅新增 nullable `priority INTEGER DEFAULT 0` 与部分索引 `idx_outbox_priority`；`aggregate_type` CHECK 从 `turn,memory` 扩展为 `turn,memory,forget`。
- 优先级值域：`0` 普通任务、`1` 删除类 `forget.*`、`2` 预留 urgent；Worker 按 `priority DESC, next_retry_at ASC` 取任务。
- SQLite CHECK 通过保留数据的表重建完成，downgrade 必须对称回滚。
- 迁移为 `20260901_add_forget_plan.py`，`down_revision = "20260901_d10b_vector_ledger"`；实施时仍须用 `alembic heads` 确认单 head。

## 冻结 DDL

```sql
CREATE TABLE forget_plan (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id               TEXT    NOT NULL,
    forget_plan_id        TEXT    NOT NULL,
    forget_mode           TEXT    NOT NULL,
    target_selector       TEXT,
    target_type           TEXT    NOT NULL,
    target_id             TEXT,
    target_session_id     TEXT,
    target_topic          TEXT,
    target_time_range     TEXT,
    resolved_target_ids   TEXT,
    selection_hash        TEXT,
    status                TEXT    NOT NULL,
    requires_confirmation INTEGER NOT NULL DEFAULT 1,
    is_cascade            INTEGER NOT NULL DEFAULT 0,
    delete_mode           TEXT    NOT NULL DEFAULT 'soft',
    has_vector_cleanup    INTEGER NOT NULL DEFAULT 0,
    confirmation_token    TEXT,
    token_expires_at      TEXT,
    affected_count        INTEGER,
    executed_count        INTEGER,
    executed_at           TEXT,
    rollback_plan_id      TEXT,
    created_at            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL,
    CHECK (forget_mode IN ('single_item','session','topic','time_window','full_reset')),
    CHECK (target_type IN ('knowledge','preference','event','all')),
    CHECK (status IN ('pending','previewing','awaiting_confirmation','executing','completed','failed','rolled_back')),
    CHECK (delete_mode IN ('soft','hard'))
);
CREATE UNIQUE INDEX uq_forget_plan_user_plan
    ON forget_plan(user_id, forget_plan_id);
CREATE INDEX idx_forget_plan_user_created
    ON forget_plan(user_id, created_at);

CREATE TABLE forget_audit (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id          TEXT    NOT NULL,
    forget_plan_id    TEXT    NOT NULL,
    user_id           TEXT    NOT NULL,
    forget_mode       TEXT    NOT NULL,
    target_type       TEXT,
    delete_mode       TEXT    NOT NULL,
    is_cascade        INTEGER NOT NULL DEFAULT 0,
    affected_count    INTEGER,
    selection_hash    TEXT,
    confirmation_ref  TEXT,
    status            TEXT    NOT NULL,
    result_code       TEXT,
    trace_id          TEXT,
    sensitivity_max   TEXT,
    created_at        TEXT    NOT NULL,
    executed_at       TEXT,
    CHECK (forget_mode IN ('single_item','session','topic','time_window','full_reset')),
    CHECK (target_type IN ('knowledge','preference','event','all')),
    CHECK (status IN ('pending','previewing','awaiting_confirmation','executing','completed','failed','rolled_back')),
    CHECK (delete_mode IN ('soft','hard'))
);
CREATE INDEX idx_forget_audit_user_created
    ON forget_audit(user_id, created_at);
```

Outbox 扩展语义：

```sql
ALTER TABLE outbox ADD COLUMN priority INTEGER DEFAULT 0;
CREATE INDEX idx_outbox_priority
    ON outbox(priority, next_retry_at) WHERE priority = 1;
-- aggregate_type CHECK: ('turn','memory','forget')
```

## 安全与事务约束

- `user_id` 是 Repository 层强制隔离键；所有计划读取和变更必须包含用户过滤。
- Preview 完成、进入 `awaiting_confirmation` 后，清除 `target_selector` 与可能承载正文的 `target_topic`，或置安全占位；不得将原 selector 写入审计、Outbox、日志、导出或临时输出。
- `confirmation_token` 只存 SHA-256 哈希，明文不落库；消费必须与 Execute 副作用处于同一事务，成功后置 NULL。
- `affected_count = len(resolved_target_ids)`；`executed_count != affected_count` 时不得进入 `completed`。
- `forget_audit` 为最小审计零正文表，不得扩展 `reason`、`details`、`source_reference`、`error_message` 等自由文本正文旁路；终态审计必须填写 `executed_at`。
- `has_vector_cleanup` 仅为状态标记；Vector 清理由 TD-033 跟踪，本 ADR 不授权实现。

## 影响与限制

- SQLite 继续作为结构化真源，Vector 仅为可重建索引。
- 本期仅 staged soft-delete 主路径；Hard Delete、Cascade、Full Reset、time_window canonical、topic Runtime 与完整回滚事务不因本 ADR 获得完成性背书，未闭环路径必须 fail-closed。
- 实施需覆盖迁移 upgrade/downgrade 数据保留、跨用户隔离、确认凭据绑定/过期/防重放、数量一致性、零正文 Sentinel 与 Outbox priority。

## 回滚

经后续 ADR 撤销时，移除 Repository/UoW/Gateway 使用点后执行对称迁移：删除两张新增表，并以保留既有数据的表重建撤销 `outbox.priority` 和 `aggregate_type='forget'`。不得以修改历史迁移代替新 ADR/迁移。

## 签署与证据

- D（周子腾）：2026-09-02，D1～D6 全部采用推荐方案。
- Reviewer E（谢嘉然）：2026-09-02，PR #112 终局 `APPROVED`。
- 证据边界：该签署使 FRZ-DB-001 扩展正式生效，但 Runtime 仍为 `PARTIAL / staged implementation`；L0/L1/L2 实现与宿主验证须另行登记。
