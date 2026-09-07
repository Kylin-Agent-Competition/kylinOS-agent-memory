# D13D P0-I1 Safety Observation Scope

## Status

`IN_PROGRESS`。本文件冻结 #157 的生产 prerequisite 口径，不代表 D13D formal raw、Seal、
麒麟 VM 运行或 FROZEN 状态。

## Observation facts

- `critical_gate_bypass_count`：同一 trace 的 persisted critical source event 中
  `admission_decision=allow_extraction` 的数量。
- `normal_memory_write_count`：同一 trace 的 active `memory_entries`，加上
  `memory_version_receipts.trace_id` 绑定的 preference `write` 或 `rollback` 回执数。
  该口径不按时间窗口猜测，no-op 不计入写入。
- `audit_plaintext_leak_count`：critical source event 的受抑制内容字段仍有值的数量。
- `cross_user_violation_count`：从 foreign user's active memory control 读取时，实际 user-scoped
  repository boundary 错误返回该实体的数量。

## Boundaries

- observation 只读 persisted facts；缺 trace 或 foreign memory control 时 fail-closed。
- API Key、password 和 prompt-injection 样本通过真实 `event.ingest` security path；cross-user
  样本通过真实 `memory_entries` user-scoped read boundary。
- observer 不读 Gold、不接收 expected 值、不判定 PASS/FAIL。formal projection 属于 #157 合并后
  的 versioned adapter 工作，不在本 PR 实现。
