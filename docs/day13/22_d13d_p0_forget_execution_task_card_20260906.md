# D13D P0-I2 任务卡：Forget 五模式执行与残留观测

## 授权与目标

- 授权：项目负责人于 2026-09-06 授权 D 轨跨原任务边界完成 D13D 前置实现。
- 目标：为 `single_item`、`session`、`topic`、`time_window`、`full_reset` 提供真实的
  preview/confirmation/execute 链路，并为后续 adapter 提供事务后可验证事实。
- 不修改：D13E Dataset、Gold、Threshold、既有 IPC 字段和错误码；不删除 source events。

## 冻结语义

1. `topic`：只匹配 `memory_entries.topic_key` 的精确相等值，且只处理 active knowledge。
   不得从 `content`、`conditions` 或自然语言 selector 推断 topic。
2. `time_window`：只处理具有 primary evidence relation 的 knowledge；依据同一用户
   `source_events.occurred_at`，输入必须是带时区 JSON `{ "from": ..., "to": ... }`，转换为
   UTC 后使用半开区间 `[from, to)`。
3. `full_reset`：仅 `target_type=all`，精确覆盖当前可删除的 knowledge 与 preference；
   source events、审计和其他不可删除实体保留。内部 selection 使用 `knowledge:<id>` 与
   `preference:<id>`，消除跨表数字 ID 歧义。
4. 其余 target type/mode 组合保持 fail-closed；hard delete 与 cascade 仍不实现。

## topic_key 权威写入真源

- `topic_key` 仅可由受控 structured knowledge ingress 在调用
  `db.repositories.insert_knowledge_entry(..., topic_key=...)` 时显式传入；Repository 拒绝空白值。
- 对受控评测状态准备，可使用同一受控入口预置明确的 `topic_key`。这是 state preparation，
  不读取 Gold、不由 adapter 按 sample 修改既有数据库、也不从 target selector 回填字段。
- 旧 knowledge 的 `topic_key=NULL` 保持 NULL；topic resolver 不做 content、conditions 或自然语言 fallback。

## Safety observation 边界

- `normal_memory_write_count` 冻结为同一 trace 下的实际 normal Memory Service entity 写入：
  active `memory_entries` 写入，加上有 `memory_version_receipts.trace_id` 的 preference
  `write`/`rollback` 写入；不以 created_at 时间推测归属，no-op 不计为写入。
- Safety observer 只返回事实计数和 trace reference，不读取 Gold、不接收 expected counter、
  不判断 PASS/FAIL。后续 versioned adapter 才负责把事实层投影为 formal `actual`。

## 允许修改

- `memory_entries` 新增 nullable `topic_key` 与 user-scoped index；`memory_version_receipts`
  新增 nullable `trace_id` 审计归属列；两者均通过 Alembic migration 管理；
- Forget resolver、UoW dispatcher、受影响 L1/迁移测试；
- 只读的事务后残留观测接口及后续 adapter 调用。

## 验收

- 每种 mode 在同用户范围内 preview 后才能 execute；确认凭据、幂等、零正文审计和 Outbox
  优先级保持不变。
- topic 精确匹配、time UTC 边界、full reset tagged selection、跨用户同名对象、重复 execute、
  未支持组合、漏删和输出残留均有 L1 覆盖。
- 迁移 upgrade/downgrade 维持单一 head；WSL L1 不作为麒麟 VM formal raw 证据。
