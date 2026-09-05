# D13D P0：D 轨执行适配器前置实现清单

## 决定

- 决定日期：2026-09-06。
- P0-0 四类 raw 的集成责任：D 轨（D13D）。
- 独立复核和签名保管：Reviewer D。
- B owner 的回执已由项目负责人确认；B 轨不承担 Preference、Conflict、Safety、Forget 的业务
  `actual` 或 raw 批准。
- D13A 仅负责其既有、有限的性能和运行时辅助范围；不承担业务 raw、Gold、Seal 或本清单所列
  生产语义实现。

## 当前代码事实

唯一被测基线仍为 `4a32e5c948a968f3bd4409d91deac320002baea1`。在该基线中：

| 类别 | 已存在的真实入口 | 不能由 adapter 补造的缺口 |
| --- | --- | --- |
| Preference | `providers.extraction_provider.ExtractionProvider.extract_preferences` | 无已确认缺口；adapter 可用真实 `TurnFinalizedEvent` 调用并记录脱敏 trace。 |
| Conflict | `service.conflict_resolution_policy.ConflictResolutionPolicy.resolve` | 无已确认缺口；adapter 可将封存集结构化侧输入转换为 `ConflictSide`。 |
| Safety | `pipeline.sensitive.detect_sensitivity` 只提供敏感分类 | 没有可供隔离执行读取的 admission、正常写入、审计明文泄漏、跨用户拒绝四项真实计数及同一 trace 链。仅调用分类器或手工置零不符合 B07 D 项。 |
| Forget | `service.forgetting.resolve_forget_targets`、`gateway.forget_handlers` | 解析器只支持 `single_item`/`session`；封存集还要求 `topic`、`time_window`、`full_reset`。同时缺少同次事务执行后实时检索与全量重建检查点的五项计数出口。 |

## 为什么不能在 PR #150 内直接“补齐”

PR #150 的任务卡范围是冻结基础设施和证据包，禁止修改检索、Embedding、Vector、IPC、Schema、
数据库或生产业务语义。Safety 的可审计 Gate/audit 计数及 Forget 的三个模式、事务后检查点都属于
生产语义与持久化流程，而不是适配器参数或文档问题。

实现这些缺口会修改被测代码，因此 `4a32e5c...` 不再是实施后的被测 commit。把改动放进 PR #150
再以旧 SHA 生成 raw，将违反 D13D B-01 和“唯一被测基线”规则。故本 PR 可继续交付责任映射、
收件标准、adapter 合同和失败闭合检查，但不得宣称可产生合格的 17 条正式 raw。

## 必须先完成的独立实现任务

### P0-I1：Safety 可审计执行路径

新增一个不改变冻结 IPC/Schema 的内部评测观测接口，必须在同一隔离执行中从真实 admission、
正常写入、audit 与用户隔离检查派生以下非负整数：

- `critical_gate_bypass_count`
- `normal_memory_write_count`
- `audit_plaintext_leak_count`
- `cross_user_violation_count`

接口不得接收 Gold、阈值、expected 或“期望计数”。每个样本须能生成脱敏 trace 并在调用失败时
保留失败事实、非零退出。

### P0-I2：Forget 五模式与事务后检查点

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

I1/I2 经独立审查合并后，D 轨重新选择完整 commit、重新建 VM 快照和隔离工作树。只有在新基线
上，才可实现/启用版本化 adapter，并验证：Dataset SHA 与 17 条 4/4/4/5 分布、Gold 隔离、四类
真实 dispatch、缺 trace/重复 ID/未知 metric/已存在输出目录/调用失败的 fail-closed 行为。

## D13D 推进门禁

在 I1、I2 合并并重新选择基线之前，D13D 状态保持 `BLOCKED`，不得进行 VM formal raw、最终
Manifest、Review Seal、Execution Seal 或正式 Runner Gate 0--10。该结论是范围与证据约束，不是
对 B owner 回执有效性的否定。
