# D13B 开工工作清单：封存测试与正式量化评测

## 任务信息

- 施工项：D13 B 轨「封存测试与正式量化评测」（台账 D13-B，负责人：B＝高翌哲）。
- 工作类型：`test`（正式量化评测：Recall@K / MRR / nDCG@K / 检索延迟与错误分类）。
- 工作分支：`test/D13B-retrieval-formal-eval`（按提交分支要求命名：`<类型>/<用途>`，不含 `codex`）。
- 本次范围：仅 B 轨检索评测链。冻结评测配置下，对同一 Commit、同一麒麟 VM 正式执行检索评测，输出正式指标、原始结果、失败查询/过滤/重排错误分类与统一评测结果；不代行 A、C、D、E 轨实现或审查。
- 基线：`origin/main@6e9394b`（含已合并的 D12B PR #121）。
- 开始时间：2026-09-02（准备阶段）。最晚停止时间：尚未由负责人指定；进入实现前须确认。
- 当前进度：D13B 正式施工 1/7（约 14%）：工作项 2 已落地并通过 L0/L1（520 passed）；工作项 1 准备中；工作项 3–7 待 VM/冻结输入。本日完成准备项（读输入、确认任务、写本清单、建分支与 Draft PR）。

## 完成定义

在 D13D 冻结环境、D13E 封存测试集与 Gold 哈希就绪的前提下，正式评测输出：检索正式指标（Recall@K、MRR、nDCG@K）、原始结果、检索延迟（P50/P95），以及失败查询/过滤/重排错误分类；并汇总为统一评测结果与可复现证据包。未取得麒麟 VM 实测、封存测试集或环境冻结证据的结论必须标为 `UNVERIFIED`，不得把本地/L1 结果写成正式量化评测结论。

## 工作清单

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| 1 | 记录正式评测基线与环境口径：`main@6e9394b`、D13D 环境冻结（VM 资源/Commit/依赖/数据版本/统一日志与报告目录）、D13E 封存测试集版本与 SHA-256、评测配置 `d9-retrieval-eval-config/v1`、评测输入输出 JSON schema（`retrieval_ref=(memory_id, version_id)`，完整校验键 `(user_id, memory_id, version_id)`）。 | D13D/D13E 冻结交付；可用 `origin/main` | commit/环境清单、哈希核对、schema 校验 | 准备中（已记录既有 D9 契约；D13D/D13E 冻结输入待提供） |
| 2 | 收敛正式评测运行器：在 `scripts/v007_eval.py` + `memory-service/retrieval/evaluation.py` 基础上固定 EvalConfig（k=10、top_k=10、rrf_k=60、top_k==k、algorithm_version、warmup/repeat/concurrency/statistics_method），补齐输入校验、错误分类输出与 `report_to_dict` 元数据（gold_label_version/dataset_version/implementation_commit/environment/evidence_reference）。 | D9 Gold 契约；D11B 诊断输出契约 | 运行器 L0/L1 测试、负向输入、`git diff --check` | 已完成（L0/L1：520 passed；账本模块 + CLI + 测试落地；正式执行仍待 VM/封存集） |
| 3 | 麒麟 VM 正式检索执行：对 rrf-v1（含 FTS5/Vector 通道对照）采集每条查询 Top-K、延迟与过滤/降级信息；同一 Commit 记录命令、版本、日志与结果。 | 麒麟 VM；D/C 可调用的检索链路或等价真源回放；D13D 统一目录 | 真实 VM 日志、查询数与封存集一致、P50/P95、失败样本可复现 | 待开始（无 VM 证据前为 `UNVERIFIED`） |
| 4 | 指标计算与汇总：Recall@K、MRR、nDCG@K、命中数；对照 E 冻结的 OFFICIAL 阈值（如 M2 知识检索召回率）；空 Gold/护栏统计按 Gold Policy v2 口径。 | D9 Gold Policy v2；D13E 正式口径 | `test_evaluation.py` 等定向测试、单查询明细与聚合核对 | 部分完成（账本模块已实现剔除与护栏统计并通过 L0/L1；正式汇总待封存集/VM） |
| 5 | 失败查询、过滤与重排错误分类：对每条未命中/排序异常按阶段归因（查询/Embedding 失败、过滤规则、版本真源、重排、降级通道、护栏拦截），复用 D6 错误分类与 D11B 诊断输出，输出分类计数与脱敏样例。 | D6 错误分类；D11B 诊断数据 | 分类覆盖 100%、无正文/敏感/凭据泄漏、guardrail/cross_user/sensitive critical=0 | 待开始（依赖 D11B 诊断输出契约与真实失败样本） |
| 6 | 统一评测结果与证据：写 `docs/day13` 正式报告，保存原始 JSON/日志并登记 SHA-256 至 evidence 索引；与 E 的四项核心指标（偏好准确率、冲突正确率、安全/遗忘指标）交叉核对样本规模与口径；列出未达标项真实差距与优化方向。 | 3–5；E 的正式指标 | 报告与原始证据一致、可复现命令、D 主审/E 补审材料 | 待开始 |
| 7 | 回归与审查收口：运行 B 轨回归与评测契约测试、`git diff --check`、处理 Review 意见并回填本清单与 PR。 | 1–6；Review 可用性 | pytest 全绿、`git diff --check`、Review 结论 | 进行中（本批 L0/L1 已跑；待 commit/push 授权与 D/E 审查） |

## 本批已落地（2026-09-02，L0/L1）

本批新增以下文件（未改动既有生产链路、数据集或冻结文档）：

- `memory-service/retrieval/formal_eval.py`：D13B 正式检索评测账本模块。config fail-closed（必须绑定 dataset/gold/commit/environment，`config_version=d9-retrieval-eval-config/v1`，k=10/top_k=10/rrf_k=60）；按 D9 empty_gold_rule 剔除空 Gold、按 negative_guardrail_scope 剔除护栏类别查询；按 guardrail_violation_accounting 统计返回 Top-K 的护栏违规；每通道 Recall@K/MRR/nDCG@K/P50/P95 复用 `retrieval/evaluation.py`。
- `scripts/run_d13b_formal_eval.py`：CLI，读取 bundle JSON（config+corpus+queries）输出报告 JSON。
- `memory-service/tests/retrieval/test_formal_eval.py`：L0/L1 共 15 项（矩阵、fail-closed、剔除、护栏、手算指标）。

验证：`pytest memory-service/tests/retrieval + evaluation/test_d9_retrieval_gold_spec.py + test_d9_retrieval_dataset.py + test_d6_multisource_devset.py`＝520 passed；`scripts/run_d13b_formal_eval.py` CLI 冒烟通过；`py_compile` 通过。

正式量化结论仍 `UNVERIFIED`：未取得 D13D 冻结环境、D13E 封存测试集与麒麟 VM 实测前，不得把本模块输出描述为正式达标。

## 固定验收口径

- 正式评测参数沿用 `d9-retrieval-eval-config/v1`：Recall@K、输出 Top-K=10、RRF `k=60`，并要求 `top_k == k`。
- Gold 引用使用版本级 `retrieval_ref=(memory_id, version_id)`；完整校验键为 `(user_id, memory_id, version_id)`。positive-answerable 定义：`active` + `is_current=true` + `conflict_state != unresolved` + `sensitivity ∈ {none,low,medium}`。
- 标准 Memory Context 必须排除 `removed`、`expired`、跨用户、敏感与 `unresolved` 冲突对象；`deprecated` 仅可在显式授权的 history/audit 模式检索，且不进入标准 M2 指标。
- 任一 guardrail violation、跨用户或敏感对象进入最终 Top-K 均为 Critical；目标为 0。
- 检索延迟报告 P50/P95/mean/max，统计方法（warmup/repeat/concurrency）随 EvalConfig 绑定登记。
- 任何正式达标结论只基于麒麟 VM 实测 + 封存测试集 + 冻结环境；否则标 `UNVERIFIED`。

## 跨轨依赖与不在范围

| 依赖 | 责任轨道 | D13B 处理方式 |
|---|---|---|
| 环境冻结（VM 资源/Commit/依赖/数据版本/统一日志与报告目录/可复现证据包） | D13D | 消费冻结环境与统一目录；问题反馈，不代为实现。 |
| 封存测试集与 SHA-256、Gold 判定键、偏好准确率/冲突正确率/安全与遗忘指标及真实差距 | D13E | 消费封存集与指标口径；不一致时反馈，不代为实现。 |
| 端到端检索调用、服务/OS 重启后索引状态、真实用户输入 | D/C | 作为正式评测前置条件；未取得 VM 证据不宣称完成。 |
| Embedding/Provider、SDK 状态与性能 | A | 以其健康状态作为前置条件，不改 Provider。 |

本批不修改 Vector/FTS5/RRF 生产实现、SQLite 真源、QML、部署与 systemd；不以 L0/L1 或历史 L2 冒充当前 Commit 的正式评测。

## Draft PR 准备

- 拟题：`docs(D13B)：封存测试与正式量化评测开工工作清单`；Draft PR 已创建（PR #123）。
- PR 正文、评论、提交信息均使用中文；分支名不含 `codex`。
- 本批新增代码与工作清单状态更新，在取得单独 `commit`/`push` 授权后提交到 `test/D13B-retrieval-formal-eval` 并更新 PR；Draft→Ready 与合并由用户手动决定。