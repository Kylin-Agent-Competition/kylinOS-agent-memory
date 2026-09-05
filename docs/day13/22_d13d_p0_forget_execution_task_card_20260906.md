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

## 允许修改

- `memory_entries` 新增 nullable `topic_key` 与 user-scoped index，以及单一 Alembic migration；
- Forget resolver、UoW dispatcher、受影响 L1/迁移测试；
- 只读的事务后残留观测接口及后续 adapter 调用。

## 验收

- 每种 mode 在同用户范围内 preview 后才能 execute；确认凭据、幂等、零正文审计和 Outbox
  优先级保持不变。
- topic 精确匹配、time UTC 边界、full reset tagged selection、跨用户同名对象、重复 execute、
  未支持组合、漏删和输出残留均有 L1 覆盖。
- 迁移 upgrade/downgrade 维持单一 head；WSL L1 不作为麒麟 VM formal raw 证据。
