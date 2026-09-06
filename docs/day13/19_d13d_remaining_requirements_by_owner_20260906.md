# D13D：剩余缺失项需求清单与责任拆分

## 当前判定

来源：B 轨状态回执 `D13D_B07_B轨详细状态回执_20260905.md`，文件 SHA-256：
`26bb97a5927922083986d398ddaf46544a510354a8baa1c9ef3d493ba5aa2ece`。

结论：B 轨确认 D13E 候选输入的静态完整性，但没有、也不承担 Preference、Conflict、Safety、
Forget 四类业务 raw 的 adapter 或真实执行。因此 D13D-B07 仍为 `BLOCKED`。此前基线
`4a32e5c948a968f3bd4409d91deac320002baea1` 已被 PR #157 的 P0-I1/I2 实现变更失效；当前仅有
`main@17dce3696066213b54e9dcbe6b87c4944cb41c8c` 前置候选，正式 `tested_commit` 待 P0-I3 重新选择。
PR #157 最终审查已批准其 P0 实现、迁移、L1/CI；其 VM/formal 测试豁免仅限该 PR 的 merge blocker，
不能解除本任务的真实 raw、双 Seal、attestation、Runner 或 `FROZEN` 门禁。

## P0-0：已冻结的四类 raw 责任映射

责任人：D 轨（D13D）。D13E Review Seal 由 Reviewer D 独立复核；D13D Execution Seal 必须由
非作者的独立执行审查人签发（`PENDING_NAMED_ASSIGNMENT`）。B owner 的书面确认已被项目负责人接受，
B 轨不承担四类业务 `actual` 的生成或批准。

本项由项目负责人于 2026-09-06 明确指定，替代此前“D13E 负责人或项目负责人待指定”的
占位要求。D 轨负责集成、隔离环境、证据收件和失败闭合；Reviewer D 只签发 D13E Review Seal，
独立 Execution Reviewer 只签发 D13D Execution Seal，二者均不参与 author 自批。D13A 的责任仅限已批准的性能/运行时辅助工作，不承担四类
业务语义、Gold 判定、raw 批准或 Seal 签发。

必须书面指定以下每个 metric 的执行责任轨、具名 Owner、实现/复核边界和审批引用：

| Metric | 需指定的责任 | 不可接受的替代 |
| --- | --- | --- |
| Preference（4） | 真实偏好提取/读取链路与状态查询 Owner | B 轨、Gold、单测断言或手工结果。 |
| Conflict（4） | 真实冲突判断/消解链路与状态查询 Owner | 预置 winner、Gold 或单元测试输出。 |
| Safety（4） | 真实 Gate/admission/audit 与四硬零计数 Owner | 默认全零、脱离运行时的 fixture。 |
| Forget（5） | 真实 forget 事务、实时/重建检查点与五硬零计数 Owner | 仅检索侧结果、仅 DB 手工查询或默认全零。 |

验收交付：具名责任矩阵、每类真实调用入口、输入映射、受控查询/trace 方案、审批引用。D 轨
不得通过 Mock、固定零值或读取 Gold 替代业务事实；任何会改变生产语义的缺口，必须先在独立的
实现任务中完成并重新选择被测基线，不能混入本次冻结 PR 后继续沿用旧基线。

## P0-1：四类责任轨交付真实调用适配器

每个已指定 Owner 必须共同交付一个版本化 adapter，或由一个明确主 Owner 集成四类经批准的
dispatch。最小要求：

- 固定路径、完整 commit 或 artifact SHA-256、具名确认人和独立审批引用。
- 只读 `D13E_FORMAL_TESTSET_V1.jsonl`，运行时复算其 SHA-256、17 条总数和 4/4/4/5 分布。
- 禁止读取 Gold、Threshold、tests 的 expected 或固定答案表；禁止 Mock、fixture、手工 `actual`。
- 在隔离 VM worktree、DB、socket、state、唯一 evidence root 中调用真实链路。
- 每条 raw 包含 `sample_id`、`metric`、`actual`、顶层脱敏 `trace_reference`；失败样本保留，任一必要调用失败时非零退出。
- 提供 Gold 隔离、缺输入、调用失败、缺 trace、缺硬零字段、重复 ID、未知 metric、输出目录复用的 L0/L1 负向验证。

详细验收以 [B07 标准](18_d13d_b07_detailed_acceptance_criteria_20260906.md) A--E 为准。

## P0-2：冻结 VM 真实执行与 Raw 收件

责任人：D13D（环境和证据）+ P0-0 指定的业务 Owner（实际调用）。

必须交付：

- VM 内完整 HEAD、clean status、OS/kernel、adapter SHA、完整 invocation、stdout/stderr、exit code。
- 四份 raw：Preference 4、Conflict 4、Safety 4、Forget 5；每份 SHA-256 和逐样本 trace-to-sample 映射。
- 安全四硬零字段与 Forget 五硬零字段均来自真实 Gate/audit/事务/检查点查询。
- 唯一 evidence root，不复用历史 `d13d_20260905T090507Z` 或开发机状态。

验收结果：17 条实际 raw 完整且可追溯后，B07 才可更新为 `RAW_READY_PENDING_SEALS`；任一失败停止后续签署。

## P0-3：最终 Manifest 与 D13E Review Seal

责任人：D13D 准备最终 Manifest；Reviewer D 独立签发。

- D13D 在 evidence root 写入 `FROZEN_BY_D13D` provenance，绑定 implementation commit、environment、依赖/数据版本和 evidence reference。
- Reviewer D 复算最终 Manifest 的 SHA-256，交付 `D13E_REVIEW_SEAL_V1.json`、`.sig` 和公开公钥验证信息。
- Seal 必须绑定 Dataset、Gold、Threshold、Runner 与最终 Manifest hash；不得重用仓库候选 `PENDING_D13D` Manifest hash。
- 私钥不得进入 Git、VM、CI、evidence root 或工作树。

## P0-4：Attestation、D13D Execution Seal 与正式 Runner

责任人：D13D 准备证据；非作者的独立 Execution Reviewer 独立签发。

- 生成 execution log、`SHA256SUMS`、`evidence/index.yaml`、execution attestation；attestation 绑定四类 raw hash、日志、索引、commit、环境、依赖/数据和 evidence root。
- 独立 Execution Reviewer 对 attestation hash 签发 `D13D_EXECUTION_SEAL_V1.json` 和 `.sig`，并使用不同于 D13E Review Seal 的 key ID 和公钥。
- 在目标 VM 固定 `/etc/kylin-memory/trust` 下离线验签双 Seal，并运行 `scripts/run_d13e_formal_eval.py`。
- Runner Gate 0--10 必须全部通过，summary 落盘；否则 D13D 仍为 `BLOCKED`。

## P0-5：PR #150 独立审查

责任人：PR #150 作者之外的 Reviewer。

- 审查当前 PR HEAD，核对唯一基线、Trust Root 状态、raw/Seal 阻塞未被错误关闭、文档无 `FROZEN` overclaim。
- 交付 GitHub review URL 与 `APPROVE` / `REQUEST_CHANGES` 结论。
- 此审查仅覆盖任务卡和流程材料，不替代 P0-1 至 P0-4 的正式证据。

## B 轨支持边界

B 轨不承担四类业务 raw 的生成或批准。其可在 P0-2 的真实 raw 产生后提供：Vector/FTS5/RRF
引用核验、D13B 检索报告、删除后的检索残留复查、Dataset/Manifest hash 复核。上述支持不能替代
Forget 事务、跨用户隔离、Safety audit 或重建后残留的业务证据。

## 完成顺序

```text
P0-0 责任映射
  -> P0-1 adapter
  -> P0-2 VM raw
  -> P0-3 最终 Manifest + Review Seal
  -> P0-4 attestation + Execution Seal + Gate 0--10
  -> D13D FROZEN
```

P0-5 可并行进行，但不削减主证据链的任何条件。
