# D13C 开工工作清单：端到端会话评测与主演示稳定性复测

## 任务信息

- 施工项：D13 C 轨「端到端会话评测与主演示稳定性复测」（台账 D13-C，负责人：C＝李田皓）。
- 工作类型：`test`（端到端会话评测：跨会话/Tool/Stop-Retry/UX 会话 + 主演示稳定性复测）。
- 工作分支：`test/D13C-session-eval`（按提交分支要求命名：`<类型>/<用途>`，不含 `codex`）。
- 本次范围：仅 C 轨会话评测与稳定性复测链。基于冻结评测配置，对 D11-C 主演示编排执行端到端会话评测（跨会话隔离、Tool 调用、Stop/Retry 语义、deadline timeout），复测主演示稳定性（复跑 N 轮、stop/retry 语义、deadline 行为），输出会话指标、稳定性证据与完整演示证据；不代行 A、B、D、E 轨实现或审查。
- 基线：`origin/main`（含已合并的 D11C/D12C PR）。
- 开始时间：2026-09-03。最晚停止时间：尚未由负责人指定。
- 当前进度：D13C 正式施工 6/8（约 75%）：工作项 1-6 已落地（Python 评测模块 + CLI + L1 测试 32 passed + C++ L0 稳定性测试 S1-S6 + CMake 注册 + CLI 冒烟通过）；工作项 7-8 待 CI 验证与文档收口。

## 完成定义

在冻结评测配置（`d13c-session-eval-config/v1`）下，对 D11-C 主演示编排（5 步 7 IPC 方法）执行端到端会话评测与稳定性复测，输出：

1. 会话指标：step_completion_rate、isolation_pass_rate、guardrail_critical_count、ipc_method_coverage、stop_retry_violation_count、cross_session_isolation_pass_rate、latency_p50/p95。
2. 稳定性证据：复跑 N 轮无 hang、无 stage 错乱、安全护栏通过（textIsolationVerified、forgetSelectorCleared、forgetHasMissingDeletes=false）。
3. 完整演示证据：L0 Mock 契约测试 + L1 评测账本测试全绿；可复现回归日志。

未取得麒麟 VM 实测前 Runtime 结论标为 `UNVERIFIED`，不得把本地/L0/L1 结果写成正式会话评测结论。

## 工作清单

| # | 工作项 | 依赖 | 验证方式 | 状态 |
|---|---|---|---|---|
| 1 | 创建 feature 分支 `test/D13C-session-eval` 并记录基线 commit | `origin/main` 可用 | 分支存在、基线 commit 记录 | 已完成 |
| 2 | 构建 Python 会话评测账本模块 `memory-service/evaluation/d13c_session_eval.py`：config 解析（fail-closed）、SessionRecord/StepRecord 数据类、会话指标计算（step_completion_rate / isolation_pass_rate / guardrail_critical_count / ipc_method_coverage / stop_retry_violation / cross_session_isolation / latency_p50_p95）、provenance 绑定、critical_zero_ok 护栏 | D11-C 主演示编排契约；ADR-010 turn.finalized；memory_context.v1.json | L1 测试全绿、负向输入 fail-closed | 已完成 |
| 3 | 构建 CLI `scripts/run_d13c_session_eval.py`：读取 bundle JSON → 计算报告 → 输出 JSON（含 fail-closed 路径） | 工作项 2 | CLI 冒烟通过、报告字段完整 | 已完成 |
| 4 | 构建 L1 测试 `memory-service/tests/test_d13c_session_eval.py`：A1-A8 成功 bundle / E1-E4 fail-closed / S1-S3 guardrail / R1-R4 边界 / N1-N5 稳定性语义 | 工作项 2 | pytest 32 passed | 已完成（32 passed） |
| 5 | 构建 C++ L0 稳定性测试 `memory-client/tests/test_d13c_stability.cpp`（S1-S6）：复跑 5 轮稳定性 / stop_reason 透传 / retry 语义 / deadline timeout / 跨会话隔离复跑 / reset 防 stale 回写 | D11-C E2E Orchestrator L0；MemoryViewModel API | ctest 全绿（CI 验证） | 已完成（待 CI 验证） |
| 6 | 注册 `test_d13c_stability` 到 `memory-client/tests/CMakeLists.txt` | 工作项 5 | CMake configure + ctest 通过（CI 验证） | 已完成（待 CI 验证） |
| 7 | 文档与证据收口：worklist / PR 描述 / L0L1 回归日志 / evidence 索引 / README 更新 | 工作项 1-6 | 文档完整、evidence 登记、git diff --check | 进行中 |
| 8 | 回归与审查收口：运行 C 轨 L0+L1 回归、`git diff --check`、处理 Review 意见并回填本清单与 PR | 1-7；Review 可用性 | ctest + pytest 全绿、`git diff --check`、Review 结论 | 待开始 |

## 已落地文件清单（2026-09-03）

本批文件（未改动既有生产链路、数据集或冻结文档）：

### Python 评测模块（L1）

- `memory-service/evaluation/d13c_session_eval.py`：D13C 端到端会话评测账本模块 v1。config fail-closed（`d13c-session-eval-config/v1`，provenance 完整绑定与格式校验）；会话指标计算（step_completion_rate / isolation_pass_rate / guardrail_critical_count / ipc_method_coverage / stop_retry_violation_count / cross_session_isolation_pass_rate / latency_p50_p95）；critical_zero_ok 护栏（cross_user / sensitive = 0）；fail-closed 模式（解析/校验失败不输出指标）。
- `scripts/run_d13c_session_eval.py`：CLI，读取 bundle JSON（config+sessions）输出报告 JSON（report v1）。
- `memory-service/tests/test_d13c_session_eval.py`：L1 共 32 项（A1-A8 成功 / E1-E4 fail-closed / S1-S3 guardrail / R1-R4 边界 / N1-N5 稳定性语义 / isolation/latency 类型校验）。
- `memory-service/tests/fixtures/d13c_smoke_bundle.json`：CLI 冒烟用 bundle（2 session × 7 step = 14 step，全成功路径）。

### C++ L0 稳定性测试

- `memory-client/tests/test_d13c_stability.cpp`：D13C 端到端会话稳定性复测 L0 Mock 契约测试（S1-S6 共 6 个 test slot）：
  - S1 `stability_replay_5rounds`：主演示编排复跑 5 轮稳定性（无 hang、无 stage 错乱、安全护栏通过、resetAllPipelines 后 stage 回 idle）。
  - S2 `stop_reason_semantics`：PostTurn stop_reason 透传语义（stop/length/content_filter/tool_use 原样到 metadata.stop_reason）。
  - S3 `retry_semantics`：retry_of_turn_id 透传 + 非 retry 路径必须为空（buildTurnFinalizedEventJson 字段断言）。
  - S4 `deadline_timeout_client_block`：客户端 5000ms deadline timeout fail-closed（Mock `__hold__` 不回包 → timeout → stage=failed/timeout → busy=false → 可恢复）。
  - S5 `cross_session_isolation_replay`：跨会话隔离复跑（5 轮 A/B 切换，injectedContextText 严格区分，session_id 顺序严格 A→B→A→B...）。
  - S6 `reset_clears_pending_no_writeback`：Reset 清 pending 防 stale response 回写（Mock `__hold__` + sendRawEnvelope 注入 stale response → stage 保持 idle）。
- `memory-client/tests/CMakeLists.txt`：注册 `test_d13c_stability` target（链接 Qt5::Core/Network/Test；include src/；ctest 注册名 `d13c_stability`）。

## 验证结果

### Python L1（本地验证，2026-09-03）

```
pytest memory-service/tests/test_d13c_session_eval.py -v
============================= 32 passed in 0.10s ==============================
```

覆盖：
- A1-A8：成功 bundle 各指标正确（step_completion / isolation / method_coverage / stop_retry / cross_session / latency / critical_zero）。
- E1-E4：provenance / config_version / latency / statistics_method fail-closed。
- S1-S3：guardrail critical（cross_user / sensitive）与非 critical（unresolved_conflict）。
- R1-R4：NO_VALID_SESSIONS / 重复 step_id / 重复 session_id / invalid stability_repeat。
- N1-N5：stability_repeat 默认 / retry_of_turn_id=turn_id 违反 / stop 缺 stop_reason / deadline timeout 正确 failed / deadline timeout 错误 stage 违反。
- 类型校验：latency NaN/bool 拒绝、isolation 字段 bool/string 拒绝、response_status 枚举校验、guardrail category 枚举校验。

### CLI 冒烟（本地验证，2026-09-03）

```
python scripts/run_d13c_session_eval.py memory-service/tests/fixtures/d13c_smoke_bundle.json
```

输出：
- `report_version`: `d13c-session-eval-report/v1`
- `aggregate_metrics.session_count`: 2
- `aggregate_metrics.total_step_count`: 14
- `aggregate_metrics.step_completion_rate`: 1.0
- `aggregate_metrics.isolation_pass_rate`: 1.0
- `aggregate_metrics.guardrail_critical_count`: 0
- `aggregate_metrics.critical_zero_ok`: true
- `aggregate_metrics.ipc_method_coverage.coverage_complete`: true
- `fail_closed_reasons`: []

### C++ L0（待 CI 验证）

CMake 不在本地 Windows 环境可用；L0 稳定性测试由 CI（ubuntu-22.04 + qtbase5-dev/qt5-qmake/build-essential）验证。CI 工作流触发条件：PR to main/integration、push to main/integration/feat/**、manual workflow_dispatch。

构建命令：
```
cmake -S memory-client -B memory-client/build -DKYLIN_MEMORY_CLIENT_BUILD_QML_APP=OFF -DKYLIN_MEMORY_CLIENT_BUILD_TESTS=ON
cmake --build memory-client/build
cd memory-client/build && ctest --output-on-failure --verbose
```

### py_compile（本地验证）

```
python -m py_compile memory-service/evaluation/d13c_session_eval.py scripts/run_d13c_session_eval.py memory-service/tests/test_d13c_session_eval.py
```

exit 0（全部通过）。

## 固定验收口径

- 评测配置版本：`d13c-session-eval-config/v1`（冻结）。
- 报告版本：`d13c-session-eval-report/v1`。
- 必填 IPC 方法（7 项）：`memory.retrieve` / `turn.finalized` / `tool.execution` / `conflict.compare` / `lifecycle.status` / `forget.preview` / `forget.execute`。
- step 完成态：`ready` / `completed` / `awaiting_confirmation`（forget.preview 成功终态为 `awaiting_confirmation`，不是失败）。
- step 失败态：`failed` / `timeout`。
- finalization_reason 枚举：`""` / `normal` / `stop` / `retry` / `cancelled` / `length`。
- stop_retry 违规规则：
  - `finalization_reason=retry` 必须携带 `retry_of_turn_id` 且 ≠ `turn_id`。
  - `finalization_reason=stop` 必须携带非空 `stop_reason`。
- guardrail critical 类别：`cross_user` / `sensitive`（目标 = 0）。
- guardrail 非 critical 类别：`unresolved_conflict`。
- 跨会话隔离：同 `scenario` 组的不同 session 的 `injected_context_text` 必须可区分。
- 客户端 deadline timeout：5000ms（DEFAULT_DEADLINE_MS），timeout 后 stage 进入 `failed`/`timeout`，busy=false。
- 稳定性复跑：`stability_repeat` 默认 5 轮，每轮 5 步全流程成功 + 安全护栏通过。
- 任何正式达标结论只基于麒麟 VM 实测 + 冻结环境；否则标 `UNVERIFIED`。

## 跨轨依赖与不在范围

| 依赖 | 责任轨道 | D13C 处理方式 |
|---|---|---|
| D11-C 主演示编排 | C | 复用 MemoryViewModel 5 步 Pipeline（PreChat/PostTurn/Tool/Conflict/Lifecycle/Forget） |
| ADR-010 turn.finalized | D | 按 ADR-010 契约校验 metadata.turn_id / retry_of_turn_id / stop_reason / finalization_reason |
| memory_context.v1.json | D | Pre-Chat 注入契约校验（injection_status / original_user_text_isolated） |
| D10 forget.preview/execute | C | 复用 D10C Pipeline；awaiting_confirmation 为成功终态 |
| 麒麟 VM 实测 | B/D | 本批不包含 VM 实测；Runtime 结论标 UNVERIFIED |
| D13D 环境冻结 | D | 本批不依赖 D13D；本地 L0/L1 验证 |
| D13E 封存测试集 | E | 本批使用自构造 smoke bundle；正式封存集待 D13E |

## 不在范围

- A 轨：标注与分类（不代行）。
- B 轨：检索正式评测（D13B 负责）。
- D 轨：Gateway 服务端实现与 IPC 协议冻结（不代行）。
- E 轨：封存测试集与 Gold 标签（不代行）。
- 麒麟 VM 实测：本批仅本地 L0/L1；VM 实测另行归档。
