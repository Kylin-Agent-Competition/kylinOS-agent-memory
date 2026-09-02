# D13B 开工工作清单：封存测试与正式量化评测

## 任务信息

- 施工项：D13 B 轨「封存测试与正式量化评测」（台账 D13-B，负责人：B＝高翌哲）。
- 工作类型：`test`（正式量化评测：Recall@K / MRR / nDCG@K / 检索延迟与错误分类）。
- 工作分支：`test/D13B-retrieval-formal-eval`（按提交分支要求命名：`<类型>/<用途>`，不含 `codex`）。
- 本次范围：仅 B 轨检索评测链。冻结评测配置下，对同一 Commit、同一麒麟 VM 正式执行检索评测，输出正式指标、原始结果、失败查询/过滤/重排错误分类与统一评测结果；不代行 A、C、D、E 轨实现或审查。
- 基线：`origin/main@6e9394b`（含已合并的 D12B PR #121）。
- 开始时间：2026-09-02（准备阶段）。最晚停止时间：尚未由负责人指定；进入实现前须确认。
- 当前进度：D13B 正式施工 1/7（约 14%）：工作项 2 落地并通过 Review 返工 v2（L0/L1 528 passed）；工作项 1 准备中；工作项 3–7 待 VM/冻结输入。PR #123 已由用户转为 Ready for review。

## 完成定义

在 D13D 冻结环境、D13E 封存测试集与 Gold 哈希就绪的前提下，正式评测输出：检索正式指标（Recall@K、MRR、nDCG@K）、原始结果、检索延迟（P50/P95），以及失败查询/过滤/重排错误分类；并汇总为统一评测结果与可复现证据包。未取得麒麟 VM 实测、封存测试集或环境冻结证据的结论必须标为 `UNVERIFIED`，不得把本地/L1 结果写成正式量化评测结论。

## 工作清单

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| 1 | 记录正式评测基线与环境口径：`main@6e9394b`、D13D 环境冻结（VM 资源/Commit/依赖/数据版本/统一日志与报告目录）、D13E 封存测试集版本与 SHA-256、评测配置 `d9-retrieval-eval-config/v1`、评测输入输出 JSON schema（`retrieval_ref=(memory_id, version_id)`，完整校验键 `(user_id, memory_id, version_id)`）。 | D13D/D13E 冻结交付；可用 `origin/main` | commit/环境清单、哈希核对、schema 校验 | 准备中（已记录既有 D9 契约；D13D/D13E 冻结输入待提供） |
| 2 | 收敛正式评测运行器：在 `scripts/v007_eval.py` + `memory-service/retrieval/evaluation.py` 基础上固定 EvalConfig（k=10、top_k=10、rrf_k=60、top_k==k、algorithm_version、warmup/repeat/concurrency/statistics_method），补齐输入校验、错误分类输出与 `report_to_dict` 元数据（gold_label_version/dataset_version/implementation_commit/environment/evidence_reference）。 | D9 Gold 契约；D11B 诊断输出契约 | 运行器 L0/L1 测试、负向输入、`git diff --check` | 已完成（Review 返工 v2；L0/L1 528 passed；正式执行仍待 VM/封存集） |
| 3 | 麒麟 VM 正式检索执行：对 rrf-v1（含 FTS5/Vector 通道对照）采集每条查询 Top-K、延迟与过滤/降级信息；同一 Commit 记录命令、版本、日志与结果。 | 麒麟 VM；D/C 可调用的检索链路或等价真源回放；D13D 统一目录 | 真实 VM 日志、查询数与封存集一致、P50/P95、失败样本可复现 | 待开始（无 VM 证据前为 `UNVERIFIED`） |
| 4 | 指标计算与汇总：Recall@K、MRR、nDCG@K、命中数；对照 E 冻结的 OFFICIAL 阈值（如 M2 知识检索召回率）；空 Gold/护栏统计按 Gold Policy v2 口径。 | D9 Gold Policy v2；D13E 正式口径 | `test_evaluation.py` 等定向测试、单查询明细与聚合核对 | 部分完成（账本模块已实现剔除与护栏统计并通过 L0/L1；正式汇总待封存集/VM） |
| 5 | 失败查询、过滤与重排错误分类：对每条未命中/排序异常按阶段归因（查询/Embedding 失败、过滤规则、版本真源、重排、降级通道、护栏拦截），复用 D6 错误分类与 D11B 诊断输出，输出分类计数与脱敏样例。 | D6 错误分类；D11B 诊断数据 | 分类覆盖 100%、无正文/敏感/凭据泄漏、guardrail/cross_user/sensitive critical=0 | 待开始（依赖 D11B 诊断输出契约与真实失败样本） |
| 6 | 统一评测结果与证据：写 `docs/day13` 正式报告，保存原始 JSON/日志并登记 SHA-256 至 evidence 索引；与 E 的四项核心指标（偏好准确率、冲突正确率、安全/遗忘指标）交叉核对样本规模与口径；列出未达标项真实差距与优化方向。 | 3–5；E 的正式指标 | 报告与原始证据一致、可复现命令、D 主审/E 补审材料 | 待开始 |
| 7 | 回归与审查收口：运行 B 轨回归与评测契约测试、`git diff --check`、处理 Review 意见并回填本清单与 PR。 | 1–6；Review 可用性 | pytest 全绿、`git diff --check`、Review 结论 | 进行中（首轮 REQUEST_CHANGES 已返工 v2，待 D Reviewer 复审） |

## Review 返工记录（PR #123 首轮 REQUEST_CHANGES，2026-09-02）

第二轮复审（2026-09-02 10:02）确认 R1–R6 已关闭，新增 N1–N3 与流程观察：

| 项 | 级别 | 处置 |
|---|---|---|
| N1 采样参数（statistics_method/warmup/repeat/concurrency）隐式硬编码且未写入报告 provenance | P1 | 改为显式必填配置并严格校验（拒绝 UNKNOWN/PENDING/bool/越界），写入最终 report config（report v3） |
| N2 有 results 但缺该通道 latency 仍标记 COMPUTED | P1 | formal 模式 fail-closed：results.<channel> 存在必须提供 latency_ms.<channel>，否则报错 |
| N3 latency 允许 NaN/Infinity 穿透 | P2 | 仅接受有限非负数（math.isfinite，拒绝 bool/NaN/±Inf） |
| O1 PR 正文仍写 Draft | 观察 | 按 B 轨惯例保留原正文作历史记录，状态以最新 comment/工作清单为准 |
| O2 CI 未跑 pytest | 观察 | 以可复现日志 `03_d13b_l0l1_regression_20260902.log` 作为本轮证据 |
| O3 hash 只校验格式 | 观察 | 正式 VM 执行前必须核对真实封存输入哈希（待 D13D/D13E） |


Reviewer（Ducknesses）给出 REQUEST_CHANGES。逐项处置：

| Review 项 | 级别 | 处置 | 证据 |
|---|---|---|---|
| positive-answerable 未真正用于分母；corpus 枚举/布尔校验不严 | P1 | `metric_valid` 显式要求 relevant 全部 `positive_answerable()` 且无护栏类别；`from_records` 严格校验字段必填、`is_current` 真布尔、枚举值，不允许默认放宽；stale 归 `boundary:not_current_version` | 负向测试：缺字段/非法枚举/字符串布尔/stale |
| 全局 guardrail violation query count 跨类别重复计数 | P1 | 维护违规 query 唯一集合计全局数；per-category 独立统计 | q7 同时命中 cross_user+sensitive：全局=1、两类各=1 测试 |
| 0 个有效 positive query 输出 `COMPUTED+0.0` | P1 | 返回 `NO_VALID_QUERIES`/`NO_CHANNEL_RESULTS`，指标为 `null` | 全 empty-gold / 全 guardrail 测试 |
| 单 latency 复用于三通道 | P1 | 改为按通道 `latency_ms: {channel: ms}` 独立汇总 | fts5 p50=5 vs rrf p50=25 测试 |
| provenance 哈希/证据引用可缺 | P2 | commit 校验 40 位 Git SHA；dataset/gold 校验 64 位 SHA-256；evidence_reference 必填 | 负向测试 |
| Top-K 输入契约未校验 | P2 | 每通道返回 ref 唯一、长度 ≤ `top_k=10`，超限/重复 fail-closed | duplicate / >10 负向测试 |
| PR 元数据 Ready 但正文写 Draft；CI 未跑 pytest | 观察 | 正文与清单统一为 Ready/待审查；补可复现回归日志 `docs/day13/03_d13b_l0l1_regression_20260902.log` | 日志产物 + 526 passed |

## 本批已落地（2026-09-02，L0/L1，含返工 v2）

本批文件（未改动既有生产链路、数据集或冻结文档）：

- `memory-service/retrieval/formal_eval.py`：D13B 正式检索评测账本模块 v2。config fail-closed（provenance 完整绑定与格式校验，`d9-retrieval-eval-config/v1`，k=10/top_k=10/rrf_k=60）；正式分母基于 `positive_answerable()`；empty Gold / negative guardrail / boundary（stale）剔除；返回 Top-K 护栏违规统计（全局唯一 query 计数）；每通道独立 Recall@K/MRR/nDCG@K/P50/P95 与延迟。
- `scripts/run_d13b_formal_eval.py`：CLI，读取 bundle JSON（config+corpus+queries）输出报告 JSON（report v2）。
- `memory-service/tests/retrieval/test_formal_eval.py`：L0/L1 共 21 项。
- `docs/day13/03_d13b_l0l1_regression_20260902.log`：可复现回归日志。

验证：`pytest memory-service/tests/retrieval + evaluation/test_d9_retrieval_gold_spec.py + test_d9_retrieval_dataset.py + test_d6_multisource_devset.py`＝526 passed（含新增 21 项）；CLI 冒烟通过（per-channel latency 独立）；`py_compile` 通过；LF 行尾、无尾随空白。

正式量化结论仍 `UNVERIFIED`：未取得 D13D 冻结环境、D13E 封存测试集与麒麟 VM 实测前，不得把本模块输出描述为正式达标。

## 固定验收口径

- 正式评测参数沿用 `d9-retrieval-eval-config/v1`：Recall@K、输出 Top-K=10、RRF `k=60`，并要求 `top_k == k`。
- Gold 引用使用版本级 `retrieval_ref=(memory_id, version_id)`；完整校验键为 `(user_id, memory_id, version_id)`。positive-answerable 定义：`active` + `is_current=true` + `conflict_state != unresolved` + `sensitivity ∈ {none,low,medium}`。
- 标准 Memory Context 必须排除 `removed`、`expired`、跨用户、敏感与 `unresolved` 冲突对象；`deprecated` 仅可在显式授权的 history/audit 模式检索，且不进入标准 M2 指标。
- 任一 guardrail violation、跨用户或敏感对象进入最终 Top-K 均为 Critical；目标为 0。
- 检索延迟报告 P50/P95/mean/max，按通道记录并随 EvalConfig 绑定登记。
- 任何正式达标结论只基于麒麟 VM 实测 + 封存测试集 + 冻结环境；否则标 `UNVERIFIED`。

## 跨轨依赖与不在范围

| 依赖 | 责任轨道 | D13B 处理方式 |
|---|---|---|
| 环境冻结（VM 资源/Commit/依赖/数据版本/统一日志与报告目录/可复现证据包） | D13D | 消费冻结环境与统一目录；问题反馈，不代为实现。 |
| 封存测试集与 SHA-256、Gold 判定键、偏好准确率/冲突正确率/安全与遗忘指标及真实差距 | D13E | 消费封存集与指标口径；不一致时反馈，不代为实现。 |
| 端到端检索调用、服务/OS 重启后索引状态、真实用户输入 | D/C | 作为正式评测前置条件；未取得 VM 证据不宣称完成。 |
| Embedding/Provider、SDK 状态与性能 | A | 以其健康状态作为前置条件，不改 Provider。 |

本批不修改 Vector/FTS5/RRF 生产实现、SQLite 真源、QML、部署与 systemd；不以 L0/L1 或历史 L2 冒充当前 Commit 的正式评测。

## PR 状态与提交

- PR #123（`test/D13B-retrieval-formal-eval`）已由用户转为 Ready for review；标题：`test(D13B)：封存测试与正式量化评测账本（工作清单 + 评测模块 + L0/L1 测试）`。
- 返工 v2 代码与文档在取得单独 `commit`/`push` 授权后提交；Draft→Ready 与合并由用户手动决定。
- PR 正文、评论、提交信息均使用中文；分支名不含 `codex`。