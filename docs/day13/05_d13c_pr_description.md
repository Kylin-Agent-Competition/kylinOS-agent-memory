## 背景与目标

D13 C 轨「端到端会话评测与主演示稳定性复测」需要一套会话评测账本与稳定性 L0 测试，用于：

1. 对 D11-C 主演示编排（5 步 7 IPC 方法）执行端到端会话评测，输出会话指标（step_completion_rate / isolation_pass_rate / guardrail_critical_count / ipc_method_coverage / stop_retry_violation / cross_session_isolation / latency_p50_p95）。
2. 复测主演示稳定性（复跑 N 轮、stop/retry 语义、deadline timeout、跨会话隔离、reset 防 stale 回写）。
3. 在未取得麒麟 VM 实测前，以 fail-closed 模式输出结构化报告（provenance 字段缺失/配置错误/证据漂移不输出可被误读为正式的指标）。

本 PR 落地 Python 评测账本模块 + CLI + L1 测试（config `d13c-session-eval-config/v2`，**82 passed**）+ C++ L0 稳定性测试（S1-S6，CI SUCCESS）+ 文档与 evidence 收口。

## 修改范围

### Python 评测模块（L1）

- `memory-service/evaluation/d13c_session_eval.py`：D13C 端到端会话评测账本模块。config fail-closed（`d13c-session-eval-config/v2`）；会话指标计算（step_completion_rate / isolation_pass_rate / guardrail_critical_count / ipc_method_coverage / retry_violation / cross_session_isolation / latency_p50_p95）；fail-closed（解析/校验失败不输出指标）。
  - 数据模型：`execution_group_id + stability_cohort_id + stability_round`（同给同不给）+ `execution_record_id`（bundle 唯一键；真实 `session_id` 允许跨 round 复用）。
  - 稳定性：每 cohort 独立覆盖 1..stability_repeat；缺轮/重复轮/越界/重复执行位置均 fail-closed。
  - deadline：每条 `step.deadline_ms` 必须 == `config.deadline_ms`，漂移 → `DEADLINE_CONFIG_EVIDENCE_MISMATCH` fail-closed。
  - 状态组合：`response_status × timed_out × stage_final` 冻结合法矩阵；非法组合解析期拒绝。
  - `finalization_reason` 不冻结业务枚举，仅保留 retry 跨字段约束。
  - 无 comparable cross-session pair → 顶层 fail-closed（aggregate=null + exit 2）。
- `scripts/run_d13c_session_eval.py`：CLI；文件读取/JSON 解析/root/config/sessions 类型/config/compute 全链受控异常，统一 exit 2 + 结构化 fail-closed 报告（无 traceback）。
- `memory-service/tests/test_d13c_session_eval.py` + `memory-service/tests/test_d13c_session_eval_cli.py`：L1（55 个测试函数，参数化后 **82 passed**）。
- `memory-service/tests/fixtures/d13c_smoke_bundle.json`：CLI 冒烟 bundle（A/B comparable pair，config v2）。

### C++ L0 稳定性测试

- `memory-client/tests/test_d13c_stability.cpp`：S1-S6（5 轮稳定性 / stop_reason / retry / 5000ms deadline / 跨会话 / reset 防 stale）。
  - S3 retry 真实经 `MemoryClient::sendRequest("turn.finalized", …)` → Mock Gateway（builder→transport→Mock；不声称完整 ViewModel/UI retry pipeline）。
  - S4 同时断言 `kDefaultDeadlineMs == 5000` 与实际约 4500~6500ms 超时窗口。
- `memory-client/tests/CMakeLists.txt`：注册 `test_d13c_stability` target。

### 文档 / Evidence

- `docs/day13/13_d13c_latest_review_rework_20260906.md`、`docs/day13/14_d13c_p1_closure_20260906.md`：Review 返工/收口记录。
- `evidence/index.yaml`：`D13C-L1-REGRESSION` 已回填（config v2、82 passed、C++ L0 CI SUCCESS、tested_commit `f3f9f0c`）。

## 明确不修改范围

- 不修改既有生产链路（memory-service/retrieval/、memory-client/src/ 除 deadline 常量暴露外）。
- 不修改数据集或冻结文档；不回写历史 worklist/log 快照。
- 不代行 A/B/D/E 轨实现或审查。
- 不包含麒麟 VM 实测（Runtime 结论标 UNVERIFIED）。
- 不关闭 C-D13（仅落地评测账本与 L0 稳定性测试）。

## 关联任务与技术债

- 任务卡：C-D13（端到端会话评测与主演示稳定性复测）
- TD 编号：无新增技术债
- 非阻断债务：Python L1 测试（test_d13c_session_eval.py + _cli.py）尚未纳入 GitHub Actions workflow（Reviewer 记为技术债，非阻断）。

## 验证与 CI

- Python L1：**82 passed**（VM：Python 3.12.3 / pytest 9.1.1）；py_compile PASS；`git diff --check` PASS。
- CLI：valid bundle exit 0；no-pair/malformed/root/config/sessions fail-closed exit 2。
- GitHub Actions：`Repository Baseline Check` SUCCESS；`Memory Client L0 ctest + Contract L0 ctest` SUCCESS（含 S1-S6）。
- Runtime / 麒麟 VM 会话闭环：`UNVERIFIED`（后续 L2 工作）。

## Review 状态

- Reviewer（Ducknesses）：**APPROVE**（2026-09-06，基于 HEAD `60e2b72`）；非阻断文档债务已在本正文同步处理。
- 合并门槛：满足（Reviewer APPROVE + CI 全绿）；Runtime L2 闭环仍待后续。

## 回滚方式

纯新增文件 + 局部修改，回滚可 revert 本分支提交或删除新增文件并还原 `memory-client/tests/CMakeLists.txt` 注册段。
