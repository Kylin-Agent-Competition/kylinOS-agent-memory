# D13A 历史结果失效声明

`run_01/`、`run_02/`、`run_03/` 与根目录 `summary.json` 是 2026-09-04 前的
VM 采集遗留文件，仅为问题复盘保留，**不得**作为 D13A 正式基线、性能对比、
Gate 结论或 PR 合并依据。

失效原因：

- Git commit、branch 与 clean 状态无法在采集时验证；
- 旧吞吐口径未区分尝试速率与成功吞吐；
- 缺少冻结的 expected Git identity；
- 产物写入 worktree，可能影响后续轮次的 clean 校验；
- 未测量 `memory.upserted → index consumer → real Vector backend` 的真实索引积压；
- 新的核心 benchmark 完整性与 SDK/模型 provenance fail-closed 规则尚未满足。

新的 VM 运行必须由 `scripts/run_day13a_benchmarks.sh` 写入 Git worktree 外的
目录，并在人工复核后通过独立 evidence import 步骤加入仓库。
