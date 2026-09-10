# D15B：B 轨检索发布收口任务卡（2026-09-09）

## 目标与边界

本任务只盘点和收口 B 轨的 SQLite/FTS5/Vector/RRF、检索评测、索引生命周期、B 轨 manifest 与交接材料；不修改 A、C、D、E 轨实现、冻结契约或审查结论。

## 固定身份

| 字段 | 值 | 说明 |
| --- | --- | --- |
| `assessment_base_commit` | `a7abb1e71c03c4f1558e5c6a9eff2b9f36437993` | D14B 合并后的 `origin/main` 基线，也是本 D15B 分支基线。 |
| `d15b_source_head` | `f1950fee10fac0e1eb87efe240620ed8fd5e4d81` | 本次状态评估开始时 PR #173 的 head；最终 identity closure 另行记录。 |
| `d14b_merge_sha` | `a7abb1e71c03c4f1558e5c6a9eff2b9f36437993` | PR #124 merge commit。 |
| `d14b_head_sha` | `fb4531e673bb5f02d6a109ec0f467cb6d384e927` | PR #124 审核通过的分支 head；不是 merge 后身份。 |
| `formal_runtime_tested_commit` | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` | D14B 文档记录的正式运行目标；尚未执行 Formal L3。 |
| `release_package_identity` | `kylin-memory-a-d14a 0.1.0-d14a` | 历史 tar SHA-256：`2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401`。 |
| `formal_input_control_head` | `c5573c1ce75ad08427b86e3551074e18ed806279` | PR #174 合并后的 D 轨 control-plane；三份 handoff 和四个 capture runner 从此提交消费。 |

四类身份不可混用。特别是本 PR 的开发 head、历史 formal runtime commit 和发布包身份不因同处一个 manifest 而自动相等。

## 当前状态

```text
D15B_PR_MERGE_ELIGIBILITY = PASS_WITH_DEBT
D15B_TASK = PARTIAL / WAIVED_FORMAL_INPUTS
B_TRACK_RELEASE_READINESS = BLOCKED_NOT_COMPLETE
D14B_PREPARATION_HARNESS = PASS
D14B_FORMAL_L3 = NOT_RUN / UNVERIFIED
BTRACK_SUBSTITUTE_VALIDATION = PASS_WITH_LIMITATIONS
D14B_FORMAL_INPUTS = PARTIALLY_REMEDIATED
RETRIEVAL_EVAL_INPUTS = NOT_FROZEN
B_TRACK_MANIFEST = NOT_FROZEN
B_TRACK_COMPLETE = NO
```

上述状态是截至本任务卡的仓库事实，不是对 D/E 的裁定。`PASS_WITH_DEBT` 只描述 #173 对与 #124 相同 formal-input debt 的 merge-time 文档资格；它不替代 Formal L3、B-track release readiness 或最终 Release Owner 对 debt 的接受。

## D14B waiver 的 D15B 适用范围

```text
WAIVER_SOURCE = PR #124 / docs/day14/21_d14b_formal_l3_intake_blockers_20260909.md
WAIVER_AUTHORITY = WAIVED_BY_OWNER
WAIVER_SCOPE = d13d/d14d handoff, frozen tar, four production capture runners, D14D clean VM/snapshot
WAIVER_APPLICABILITY = PR #173 merge-status documentation for the same missing formal inputs only
WAIVER_DOES_NOT_APPLY_TO = retrieval eval-input freeze, final metrics, B-track manifest freeze, B_TRACK_COMPLETE, release_ready, production_ready
```

PR #174 已将 `d13d-handoff.json`、`d14d-handoff.json`、`d14b-capture-handoff.json`、四个 runner 及正式 clean-VM 入口合入 `main`；它们已缩小本 waiver 的实际阻断范围。原始冻结 tar 字节仍未找到，新增 `rebuilt-ba3b50e` tar 仅为 provenance-labeled rebuild，不能替代原冻结包的字节级身份或解除 package-bytes preflight gate。

因此 D15B 可以以 `PASS_WITH_DEBT` 进入独立 D Review；不得以此产生或暗示 formal runtime 结果。

## 已完成的 B 侧工作

1. 固定 D14B merge identity，并将 `fb4531e…` 与 merge commit 分离记录。
2. 完成 B 轨对象、历史 evidence 与未关闭债务盘点，见 `d15b_btrack_inventory.json`。
3. 复跑 D14B harness、D13B formal-eval 与 D9 数据/Gold 契约：`226 passed, 2 skipped`。跳过仅为 Windows 本机无 symlink 能力，未产生 Formal L3 evidence root。
4. 对 D9 corpus、query candidate、Gold Policy 和 evaluator 计算 SHA-256；候选状态和缺失 provenance 记录在 `D15B_RETRIEVAL_EVAL_INPUTS.json`。

## 停止线与交接条件

下列任一缺失时不得创建 Formal L3 evidence root、不得生成 D13B final metrics、不得将 B 轨写为 COMPLETE；它们不是 #173 对相同 formal-input debt 的 merge-time waiver 反向条件：

1. 原始冻结 tar 实际字节，或有权主体的新版 package identity/refreeze 裁定；`rebuilt-ba3b50e` 不满足此条件；
2. D/B 在正式 clean-VM 以已固定 handoff/runner 完成四类 capture、lifecycle 和 receipt；
3. E/D 已审核封存的检索 corpus、query、qrel/Gold、环境 provenance 与阈值；
4. D 的正式 debt 接受记录，或 Formal L3 的闭合证据；
5. 独立 D 审查（以及适用的 E 评测补审）。

本任务不以替代 VM、历史日志、候选 D9 数据或本地测试替代以上任一输入。
