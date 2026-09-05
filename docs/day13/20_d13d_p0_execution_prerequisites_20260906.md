# D13D P0：D 轨执行适配器前置实现清单

## 决定

- 决定日期：2026-09-06。
- P0-0 四类 raw 的集成责任：D 轨（D13D）。
- D13E Review Seal：Reviewer D 独立复核；D13D Execution Seal：非作者独立执行审查人签发，当前为 `PENDING_NAMED_ASSIGNMENT`。两份 Seal 不得复用姓名、key ID 或公钥。
- B owner 的回执已由项目负责人确认；B 轨不承担 Preference、Conflict、Safety、Forget 的业务
  `actual` 或 raw 批准。
- D13A 仅负责其既有、有限的性能和运行时辅助范围；不承担业务 raw、Gold、Seal 或本清单所列
  生产语义实现。

## 当前代码事实

历史基线 `4a32e5c948a968f3bd4409d91deac320002baea1` 已因 PR #157 合并失效。PR #157 的合并提交为
`17dce3696066213b54e9dcbe6b87c4944cb41c8c`，实现了 P0-I1/P0-I2 的前置能力；它只是 P0-I3 的候选，
尚不是正式 `tested_commit`。当前代码事实如下：

| 类别 | 已存在的真实入口 | 不能由 adapter 补造的缺口 |
| --- | --- | --- |
| Preference | `providers.extraction_provider.ExtractionProvider.extract_preferences` | 无已确认缺口；adapter 可用真实 `TurnFinalizedEvent` 调用并记录脱敏 trace。 |
| Conflict | `service.conflict_resolution_policy.ConflictResolutionPolicy.resolve` | 无已确认缺口；adapter 可将封存集结构化侧输入转换为 `ConflictSide`。 |
| Safety | `service/d13d_safety_observability.py` 的 `observe_safety_execution`，配合真实 handler 注册 | P0-I1 已由 PR #157 实现；adapter 仍须在隔离环境调用并记录真实 trace，不得补造计数。 |
| Forget | `service/d13d_forget_observability.py` 的真实 preview/execute 及检查点 | P0-I2 已由 PR #157 实现五模式与计数观测；adapter 仍须在隔离环境 dispatch，不得以测试或固定零值代替。 |

PR #157 的最终 reviewed head 为 `946f18bd308ebaadff3de0d08136ab0d7ab03642`，结论为
`APPROVED`；其 merge commit 为上述 `17dce...`。审查已确认两项 P1 闭合：`topic_key` 只能由
`insert_knowledge_entry(..., topic_key=...)` 受控建立，且 canonical replay 对 `topic_key` 执行不可变比较。
该 PR 的 VM/formal 测试只被豁免为合并门槛；它不生成 formal raw、Seal、Runner 或 `FROZEN` 结论。

## 为什么不能在 PR #150 内直接“补齐”

PR #150 的任务卡范围是冻结基础设施和证据包，禁止修改检索、Embedding、Vector、IPC、Schema、
数据库或生产业务语义。Safety 的可审计 Gate/audit 计数及 Forget 的三个模式、事务后检查点都属于
生产语义与持久化流程，而不是适配器参数或文档问题。

PR #157 已在独立实现 PR 中完成上述生产语义前置。PR #150 仍只交付责任映射、收件标准、adapter
合同和失败闭合检查；adapter 合并与 P0-I3 正式基线选择前，不得宣称可产生合格的 17 条正式 raw。

## 已关闭的独立实现任务（历史验收要求）

### P0-I1：Safety 可审计执行路径（IMPLEMENTED_BY_PR_157）

状态：`CLOSED_BY_PR_157_APPROVED`。以下条目记录实现验收边界，不要求在 D13D 冻结前重复修改该实现。

新增一个不改变冻结 IPC/Schema 的内部评测观测接口，必须在同一隔离执行中从真实 admission、
正常写入、audit 与用户隔离检查派生以下非负整数：

- `critical_gate_bypass_count`
- `normal_memory_write_count`
- `audit_plaintext_leak_count`
- `cross_user_violation_count`

接口不得接收 Gold、阈值、expected 或“期望计数”。每个样本须能生成脱敏 trace 并在调用失败时
保留失败事实、非零退出。

### P0-I2：Forget 五模式与事务后检查点（IMPLEMENTED_BY_PR_157）

状态：`CLOSED_BY_PR_157_APPROVED`。以下条目记录实现验收边界；后续 adapter 只可调用真实路径并记录事实，不能回填或固定这些计数。

为 `single_item`、`session`、`topic`、`time_window`、`full_reset` 提供真实、按 `user_id` 隔离的
preview/execute 路径；execute 后必须从真实事务、实时查询和全量重建检查点派生：

- `missed_target_items`
- `wrongly_deleted_items`
- `cross_user_violation_count`
- `residual_after_realtime_query`
- `residual_after_full_rebuild`

不支持的模式必须在实现前保持 fail-closed，不能由 adapter 映射为零值。该任务需明确目标类型、
幂等、确认令牌、审计脱敏、Outbox/索引重建语义，并增加 L1 负向测试。

### P0-I3：基线重新选择和 adapter 集成

I1/I2 已由 PR #157 合并；待版本化 adapter 经独立审查并合并后，D 轨重新选择包含该 adapter 的完整
commit、重新建 VM 快照和隔离工作树。只有在新基线上，才可启用 adapter 并验证：Dataset SHA 与 17 条
4/4/4/5 分布、Gold 隔离、四类真实 dispatch、缺 trace/重复 ID/未知 metric/已存在输出目录/调用失败的 fail-closed 行为。

## D13D 推进门禁

在 P0-I3 完成（adapter 合并、正式基线重选）之前，D13D 状态保持 `BLOCKED`，不得进行 VM formal raw、最终
Manifest、Review Seal、Execution Seal 或正式 Runner Gate 0--10。该结论是范围与证据约束，不是
对 B owner 回执有效性的否定。
