# D15B：B 轨检索发布收口报告（2026-09-09）

## 结论

本报告完成 B 轨发布收口的事实盘点、当前输入身份固定和跨轨交接；**不宣布 `B_TRACK_COMPLETE`**。截至 `origin/main@a7abb1e71c03c4f1558e5c6a9eff2b9f36437993`，D14B Preparation Harness 已通过，但 Formal L3 和 D13B final retrieval evaluation 均没有可消费的正式输入或运行证据。因此 D15B 的正确状态是：

```text
B_TRACK_STATUS = BLOCKED_NOT_COMPLETE
D14B_FORMAL_L3 = NOT_RUN / UNVERIFIED
RETRIEVAL_EVAL_INPUTS = NOT_FROZEN
B_TRACK_MANIFEST = NOT_FROZEN
```

把以上任何一项写成 PASS、FROZEN 或 COMPLETE 都会把候选/替代验证错误升级为正式发布结论。

本报告对应 Draft PR [#173](https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/173)，分支为 `docs/D15B-retrieval-finalization`。交接文件记录其产生时的 source head；最终冻结 head 只能在独立审查和发布裁定后填写。

## 范围与当前组件身份

本次范围仅为 SQLite truth、FTS5、Vector、RRF/hybrid、删除/重建生命周期、D13B evaluator、D14B harness、D9 eval inputs 和 B 轨 evidence/manifest。组件清单及其状态见 [`d15b_btrack_inventory.json`](d15b_btrack_inventory.json)。

关键身份如下：

| 对象 | 当前身份 | 可用结论 |
| --- | --- | --- |
| D14B merge | PR #124 → `a7abb1e…` | 已合并；不是 Formal L3 完成。 |
| D14B harness | PR #124 CI + 本地契约回归 | Preparation Harness `PASS`。 |
| lifecycle substitute VM | `ba3b50e…` 上的替代环境 | `PASS_WITH_LIMITATIONS`，仅参考。 |
| D14B Formal L3 | 标准 handoff/tar/runner/clean-VM 缺失 | `NOT_RUN / UNVERIFIED`。 |
| D13B evaluator | CLI/账本契约可用 | 可执行，不代表已产生 final metrics。 |
| D9 corpus/query/Gold policy | 当前候选文件及 SHA | 仅 candidate/reference，未冻结。 |

## 已验证的回归

在本 D15B worktree 上使用 bundled Python 运行：

```text
tests/retrieval/test_d14b_harness.py
memory-service/tests/retrieval/test_formal_eval.py
evaluation/test_d9_retrieval_dataset.py
evaluation/test_d9_retrieval_gold_spec.py
```

结果为 `226 passed, 2 skipped`。两个 skip 对应 Windows 本机无创建 symlink 的能力；没有访问 Vector 服务、没有创建 Formal evidence root，也没有产生可用作正式指标的检索结果。

## 正式 debt 与运行时停止线

`docs/day14/21_d14b_formal_l3_intake_blockers_20260909.md` 已记录 Formal L3 缺失标准 handoff、冻结 tar 实际字节、四个 production runner 和 D14D clean-VM/snapshot。D14D 现有 evidence summary 的范围仅为 G0-G6，且 `G7=NOT_RUN_NA`、`G8=NOT_RUN`、`L3_READY=false`；它不能代替 B 的 lifecycle Formal L3。

技术债总账中仍有 B 轨 Open 项，完整标识见 inventory 和逐项[审计](05_d15b_btrack_open_debt_audit_20260909.md)。它们没有 D/E 所需的关闭或 release-debt acceptance 记录，故本报告不改写其状态。当前未发现未经解释的 B 轨 P0/High 条目；这不等同于所有 Medium/Low 技术债已关闭。

## 评测输入与指标

[`D15B_RETRIEVAL_EVAL_INPUTS.json`](../../release/btrack/D15B_RETRIEVAL_EVAL_INPUTS.json) 固定了当前候选输入和 evaluator 的 SHA-256，并明确 `freeze_status=NOT_FROZEN`：query 文件仍含 `candidate` / `pending_review` 注释状态，且没有 D13D environment provenance、被测提交、逐通道 raw results、独立 latency samples 或批准阈值。

因此本轮没有生成 Recall@10、MRR、nDCG@10、P50/P95，也没有把历史 substitute 指标复制成 final metrics。比赛“检索召回率 ≥85% / 响应时间 ≤500ms”的交叉检查同样为 `UNVERIFIED`，直到正式 evaluator 在受批准的输入和环境中运行。

## Manifest、evidence 与交接

- [`D15B_BTRACK_MANIFEST.json`](../../release/btrack/D15B_BTRACK_MANIFEST.json) 是 `NOT_FROZEN` 的 release-readiness manifest；它不创建虚假的 D15B evidence root 或 SHA256SUMS。
- [`D15B_BTRACK_HANDOFF.json`](../../release/btrack/D15B_BTRACK_HANDOFF.json) 向 D/E 指明所需的 formal inputs、审查责任和禁止外推的结论。
- 现有 D6B、D8B、D10B、D13B、D14B 记录只按 formal/reference 边界消费；本任务未删除、覆盖或重写历史 evidence。

## 达成 `B_TRACK_COMPLETE` 的唯一后续路径

1. D 提供可验证 Formal L3 输入并在 clean-VM 完成 B0/B1/B2/B3、删除残留和 evidence closure，或由最终 Release Owner 书面接受该 debt；
2. D/E 提供 sealed retrieval eval inputs，B 在冻结环境运行既有 D13B evaluator 并固定 raw/results/metrics；
3. 生成并校验正式 D15B evidence `SHA256SUMS`，更新 `evidence/index.yaml`；
4. 将 Open B debt 逐项关闭或取得明确的 `ACCEPTED_RELEASE_DEBT`；
5. D 独立审查、适用时 E 补审，随后才可冻结 manifest、合并 D15B 并标记 `B_TRACK_COMPLETE=YES`。

在上述条件满足前，本 PR 只交付可审计的停止线与交接材料，不会越权替 D/E 作出接受、封存或发布裁定。
