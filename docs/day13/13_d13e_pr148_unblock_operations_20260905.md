# PR #148 解锁与 D13D 续办操作清单

## 当前判定

- PR：[#148](https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/148)
- 核对提交：`92bc0d6a5751a3a19231d261f6c85a3afa2d8d71`
- GitHub 状态：`OPEN`，`reviewDecision=CHANGES_REQUESTED`，merge state=`BLOCKED`；仓库基线验证已成功。
- D13E manifest：`seal_status=CANDIDATE_FOR_SEALING`，D 非作者审核为 `PENDING_NON_AUTHOR_REVIEW`，D13D provenance 为 `PENDING_D13D`，bundle 为 `NOT_RUN` / `UNVERIFIED`。
- 结论：PR #148 尚不可合并，D13D 尚不可转为 `FROZEN` 或执行正式评测。

## D 非作者 Reviewer 操作

1. 在提交 `92bc0d6...` 上审核 17 条 Dataset/Gold 对：样本 ID 一一对应、每项 `metric` 一致、Dataset `inclusion_status` 与 Gold `evaluation_status` 一致，且所有输入为合成/脱敏数据。
2. 独立复算并记录当前工件 SHA-256：

   ```text
   Dataset: evaluation/d13e/D13E_FORMAL_TESTSET_V1.jsonl
   Gold:    evaluation/d13e/D13E_GOLD_V1.jsonl
   ```

   当前 manifest 声明的候选值为 Dataset `9740c00f4a9d91471bec8e6fa8aeeeb52f890f8680d83f740a84db2b1701a44b`、Gold `2d19904ede82f6ce7171e416bbb84b65c4534c803476765d13b7a2280619623d`。不得使用先前的 Gold hash。
3. 审核空样本、边界样本、Safety/Forget 零违规 gate 与 Gold 判定依据；不允许删除失败样本或以开发集替换封存集。
4. 提供书面的正式阈值配置、版本、完整 SHA-256、来源、批准人和批准引用。D13B 的 K/Top-K/RRF 配置已固定，但 D13E 四项指标的 PASS/FAIL 阈值仍须独立批准。
5. 在 PR #148 留下非作者 D Reviewer 的批准引用，并将 review decision 从 `CHANGES_REQUESTED` 收敛为可合并结论。没有批准引用不得将 `seal_status` 改为 `SEALED_BY_D_REVIEWER`。

## D13E 作者操作

1. 仅在上述审核和阈值批准完成后，更新 `D13E_FORMAL_MANIFEST_V1.json`：

   ```text
   seal_status=SEALED_BY_D_REVIEWER
   review.status=APPROVED_BY_D_NON_AUTHOR_REVIEWER
   review.gold_review_status=APPROVED_BY_D_NON_AUTHOR_REVIEWER
   review.approval_reference=<PR review URL>
   ```

2. 将经过批准的 Dataset/Gold hash、版本和样本规模保持一一对应；任何内容修改均要求重算 hash 并重新审查。
3. 接收 D13D 的实值 provenance 后，写入完整 `implementation_commit`、`environment_id`、`dependency_version_reference`、`data_version_reference`、`evidence_root` 和 `evidence_reference`，并把 provenance status 更新为 `FROZEN_BY_D13D`。
4. 由真实 VM 执行生成 Preference、Conflict、Safety、Forget 四类逐样本 raw JSONL，填充 bundle 的 `raw_result_files`，再将 `formal_result_status` 更新为 `READY_FOR_FORMAL_EVALUATION`。
5. 在冻结 VM 的统一证据目录运行 D13E runner；记录命令、退出码、raw JSONL、summary、错误分类和真实 gap。任何校验失败都不得写出正式报告。

## D13D 操作

1. 保持现有环境记录 `evidence/l2-kylin-vm/d13d_20260905T090507Z/` 为 `BLOCKED`，不得将隔离 `--no-outbox` 预检视为正式部署。
2. 等 PR #148 被 D 非作者 Reviewer 封存且阈值获批后，核验 D13E 提供的 Dataset/Gold 实体 hash、manifest hash 与批准引用。
3. 使用已建立的快照 `d13d-pre-7242935-20260905-0858` 和候选基线 `7242935bee5f230cee0535d5e28dbe1e60a302f6` 执行正式 user-service 部署；记录 VM 内 HEAD、worktree clean、unit、socket、数据库和依赖。
4. 创建新的或按审批续用的唯一 D13D evidence run，填入真实 `environment_id` 和 `evidence_root`。如 VM、提交、依赖、输入或配置发生变化，旧 run 标记 `INVALIDATED`，不得覆盖。
5. 将完整 D13D provenance 交给 D13E/B13 runner，并在同一冻结目录收集 raw result 与报告；校验所有文件后更新 `SHA256SUMS` 和 `evidence/index.yaml`。

## 合并与开跑门禁

下列条件必须全部满足：

- [ ] PR #148 的非作者 D Reviewer 审核与批准引用存在，review decision 不再为 `CHANGES_REQUESTED`。
- [ ] Dataset、Gold、manifest 与阈值配置的 hash 均已独立复核。
- [ ] D13E manifest 是 `SEALED_BY_D_REVIEWER`，bundle 使用相同版本与实值 hash。
- [ ] D13D 正式环境为 `FROZEN`，包含被测提交、VM、依赖、数据版本和唯一 evidence root。
- [ ] 四类 raw JSONL 在冻结 VM 上产生，且全部 runner fail-closed 校验通过。

任一项未完成时，PR #148 和 D13D 均保持 `BLOCKED` / `UNVERIFIED`；不得把候选 hash、L0/L1、隔离预检或历史 VM 日志升级为正式结论。
