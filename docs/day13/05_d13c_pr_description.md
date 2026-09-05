## 背景与目标

D13 C 轨「端到端会话评测与主演示稳定性复测」需要一套会话评测账本与稳定性 L0 测试，用于：

1. 对 D11-C 主演示编排（5 步 7 IPC 方法）执行端到端会话评测，输出会话指标（step_completion_rate / isolation_pass_rate / guardrail_critical_count / ipc_method_coverage / stop_retry_violation / cross_session_isolation / latency_p50_p95）。
2. 复测主演示稳定性（复跑 N 轮、stop/retry 语义、deadline timeout、跨会话隔离、reset 防 stale 回写）。
3. 在未取得麒麟 VM 实测前，以 fail-closed 模式输出结构化报告（provenance 字段缺失/配置错误不输出可被误读为正式的指标）。

本 PR 落地 Python 评测账本模块 + CLI + L1 测试（32 passed）+ C++ L0 稳定性测试（S1-S6，待 CI 验证）+ 文档与证据收口。

## 修改范围

### Python 评测模块（L1）

- `memory-service/evaluation/d13c_session_eval.py`（新增）：D13C 端到端会话评测账本模块 v1。config fail-closed（`d13c-session-eval-config/v1`，provenance 完整绑定与格式校验）；会话指标计算（step_completion_rate / isolation_pass_rate / guardrail_critical_count / ipc_method_coverage / stop_retry_violation_count / cross_session_isolation_pass_rate / latency_p50_p95）；critical_zero_ok 护栏（cross_user / sensitive = 0）；fail-closed 模式（解析/校验失败不输出指标）。
- `scripts/run_d13c_session_eval.py`（新增）：CLI，读取 bundle JSON（config+sessions）输出报告 JSON（report v1）；fail-closed 路径返回 exit 2 + 结构化错误报告。
- `memory-service/tests/test_d13c_session_eval.py`（新增）：L1 共 32 项（A1-A8 成功 / E1-E4 fail-closed / S1-S3 guardrail / R1-R4 边界 / N1-N5 稳定性语义 / isolation/latency 类型校验）。
- `memory-service/tests/fixtures/d13c_smoke_bundle.json`（新增）：CLI 冒烟用 bundle（2 session × 7 step = 14 step，全成功路径）。

### C++ L0 稳定性测试

- `memory-client/tests/test_d13c_stability.cpp`（新增）：D13C 端到端会话稳定性复测 L0 Mock 契约测试（S1-S6 共 6 个 test slot）。
- `memory-client/tests/CMakeLists.txt`（修改）：注册 `test_d13c_stability` target（链接 Qt5::Core/Network/Test；include src/；ctest 注册名 `d13c_stability`）。

### 文档

- `docs/day13/02_d13c_session_eval_worklist_20260903.md`（新增）：D13C 开工工作清单。
- `docs/day13/05_d13c_pr_description.md`（新增）：本 PR 描述。
- `docs/day13/06_d13c_l0l1_regression_20260903.log`（新增）：L0/L1 回归日志。

### L2 需求与跨轨交付归档（2026-09-05 追加）

- `docs/day13/07_d13c_l2_requirements_b_track.md`（新增）：B 轨 L2 需求清单（12 项）。
- `docs/day13/08_d13c_l2_requirements_d_track.md`（新增+更新）：D 轨 L2 需求清单（20 项，附 PR #149 交付状态列）。
- `docs/day13/09_d13c_l2_b_track_delivery_20260903.md`（新增）：B 轨 L2 交付归档（6 VERIFIED + 6 PARTIAL/BLOCKED）。
- `docs/day13/10_d13c_l2_d_track_delivery_20260905.md`（新增）：D 轨 L2 交付归档（PR #149：4 VERIFIED + 2 FAILED→BLOCKED + 14 BLOCKED）。
- `docs/day13/11_d13c_l2_status_summary_20260905.md`（新增）：B+D 轨合并视图、runtime_status 升级矩阵、C 轨专属 L2 待办（C-1~C-5）。

## 明确不修改范围

- 不修改既有生产链路（memory-service/retrieval/、memory-client/src/）。
- 不修改数据集或冻结文档。
- 不代行 A/B/D/E 轨实现或审查。
- 不包含麒麟 VM 实测（Runtime 结论标 UNVERIFIED）。
- 不关闭 C-D13（仅落地评测账本与 L0 稳定性测试）。

## 关联任务与技术债

- 任务卡：C-D13（端到端会话评测与主演示稳定性复测）
- TD 编号：无新增技术债

## 架构与能力边界依据

- ADR-010 `turn.finalized`：Post-Turn 写链路；`finalization_reason=retry` 必须携带 `metadata.retry_of_turn_id` 且 ≠ `turn_id`。
- `memory_context.v1.json`：Pre-Chat 注入契约；`injection_status ∈ {injected, skipped, failed, degraded}`。
- D11-C E2E Orchestrator：5 步 7 IPC 方法主演示编排（PreChat / PostTurn / Tool / Conflict+Lifecycle / ForgetPreview+Execute）。
- D10C forget.preview/execute：`awaiting_confirmation` 为 forget.preview 的成功终态（等待用户确认后进入 execute），不是失败。
- FRZ-IPC-006：客户端 deadline timeout（5000ms）防止长期挂死在 querying/sending 状态。
- fail-closed 模式：provenance 字段缺失、配置错误等情况不输出可被误读为正式的指标。

## 修改文件清单

| 文件 | 变更类型 | 摘要 |
|---|---|---|
| `memory-service/evaluation/d13c_session_eval.py` | 新增 | D13C 端到端会话评测账本模块 v1 |
| `scripts/run_d13c_session_eval.py` | 新增 | CLI 读取 bundle JSON 输出报告 JSON |
| `memory-service/tests/test_d13c_session_eval.py` | 新增 | L1 测试 32 项 |
| `memory-service/tests/fixtures/d13c_smoke_bundle.json` | 新增 | CLI 冒烟用 bundle |
| `memory-client/tests/test_d13c_stability.cpp` | 新增 | C++ L0 稳定性测试 S1-S6 |
| `memory-client/tests/CMakeLists.txt` | 修改 | 注册 test_d13c_stability target |
| `docs/day13/02_d13c_session_eval_worklist_20260903.md` | 新增 | D13C 工作清单 |
| `docs/day13/05_d13c_pr_description.md` | 新增 | 本 PR 描述 |
| `docs/day13/06_d13c_l0l1_regression_20260903.log` | 新增 | L0/L1 回归日志 |
| `docs/day13/07_d13c_l2_requirements_b_track.md` | 新增 | B 轨 L2 需求清单（12 项） |
| `docs/day13/08_d13c_l2_requirements_d_track.md` | 新增 | D 轨 L2 需求清单（20 项，附交付状态） |
| `docs/day13/09_d13c_l2_b_track_delivery_20260903.md` | 新增 | B 轨 L2 交付归档 |
| `docs/day13/10_d13c_l2_d_track_delivery_20260905.md` | 新增 | D 轨 L2 交付归档（PR #149） |
| `docs/day13/11_d13c_l2_status_summary_20260905.md` | 新增 | L2 状态汇总 + C 轨待办 C-1~C-5 |
| `evidence/index.yaml` | 修改 | 新增 D13C-L1-REGRESSION 条目 |
| `memory-client/README.md` | 修改 | 新增 D13-C 章节说明 |

## 数据库与配置变化

无数据库变更。新增评测配置版本 `d13c-session-eval-config/v1`（冻结）。

## 测试结果

### L0 (单元测试 + 静态检查)

**C++ L0 稳定性测试（待 CI 验证）**

CMake 不在本地 Windows 环境可用；L0 稳定性测试由 CI（ubuntu-22.04 + qtbase5-dev/qt5-qmake/build-essential）验证。

测试用例（S1-S6 共 6 个）：
- S1 `stability_replay_5rounds`：主演示编排复跑 5 轮稳定性
- S2 `stop_reason_semantics`：PostTurn stop_reason 透传语义
- S3 `retry_semantics`：retry_of_turn_id 透传 + 非 retry 必须为空
- S4 `deadline_timeout_client_block`：客户端 5000ms deadline timeout fail-closed
- S5 `cross_session_isolation_replay`：跨会话隔离复跑
- S6 `reset_clears_pending_no_writeback`：Reset 清 pending 防 stale response 回写

**py_compile 静态检查（本地通过）**

```
python -m py_compile memory-service/evaluation/d13c_session_eval.py scripts/run_d13c_session_eval.py memory-service/tests/test_d13c_session_eval.py
exit 0
```

### L1 (组件集成)

**Python L1 评测账本测试（本地通过）**

```
pytest memory-service/tests/test_d13c_session_eval.py -v
============================= 32 passed in 0.10s ==============================
```

覆盖：
- A1-A8：成功 bundle 各指标正确（step_completion / isolation / method_coverage / stop_retry / cross_session / latency / critical_zero）
- E1-E4：provenance / config_version / latency / statistics_method fail-closed
- S1-S3：guardrail critical（cross_user / sensitive）与非 critical（unresolved_conflict）
- R1-R4：NO_VALID_SESSIONS / 重复 step_id / 重复 session_id / invalid stability_repeat
- N1-N5：stability_repeat 默认 / retry_of_turn_id=turn_id 违反 / stop 缺 stop_reason / deadline timeout 正确 failed / deadline timeout 错误 stage 违反
- 类型校验：latency NaN/bool 拒绝、isolation 字段 bool/string 拒绝、response_status 枚举校验、guardrail category 枚举校验

**CLI 冒烟（本地通过）**

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

### 安全与假实现审查

- [x] 无 Mock 冒充 Runtime：L0 测试使用 MockGatewayServer，明确声明 Demo/Prototype，不声称真实 AI Assistant Hook / Chat DB / ChatRecord 已接入
- [x] 无密钥泄露：测试凭据 `cred-d13c-stab-7f3a-9c2e` 为 Demo 占位值，非真实凭据
- [x] 无硬编码配置：评测配置通过 bundle JSON 注入，非硬编码
- [x] fail-closed 模式：provenance 字段缺失/配置错误不输出指标
- [x] critical_zero_ok 护栏：cross_user / sensitive critical 违规目标 = 0

### L2 麒麟虚拟机证据

本 PR 不包含 L2 麒麟 VM 证据本体，但已归档跨轨 L2 交付状态（2026-09-05）：
- **B 轨交付**（main@`b70827c`）：12 项中 6 VERIFIED（FTS5/Vector 通道、检索延迟、跨会话区分、双通道精确删除）
- **D 轨交付**（PR #149，VM baseline@`053754d`）：20 项中 4 VERIFIED（UDS socket/连接/编解码、retrieve 延迟 p50=1.703ms）
- **BLOCKED 22 项**：根因为 gateway 检索主链未接线、host mapping 未生产化、C 轨编排未部署 VM

Runtime 结论整体保持 `UNVERIFIED`（fail-closed：部分通道 VERIFIED 不构成整体会话链路 VERIFIED）。
C 轨待办 C-1~C-5 与逐指标升级矩阵见 `docs/day13/11_d13c_l2_status_summary_20260905.md`。
正式会话评测结论待 C-1~C-4 完成后以真实 VM 会话 bundle 复算归档。

### L3 (全链路验收)

不适用（本 PR 为评测账本与 L0 稳定性测试，非全链路验收）。

## 性能影响

无性能影响。本 PR 仅新增测试代码与评测账本模块，不修改既有生产链路。

## 已知限制

1. **C++ L0 测试待 CI 验证**：CMake 不在本地 Windows 环境可用，L0 稳定性测试由 CI 验证。
2. **Runtime 结论 UNVERIFIED**：未取得麒麟 VM 实测前，会话评测结论标 `UNVERIFIED`。
3. **smoke bundle 为自构造**：`d13c_smoke_bundle.json` 为 CLI 冒烟用自构造 bundle，非 D13E 封存测试集。
4. **D13C 不关闭 C-D13**：本 PR 仅落地评测账本与 L0 稳定性测试，不声称完整端到端会话评测已 Runtime 验证。

## 回滚方式

纯新增文件（无既有文件破坏性修改），回滚方式：

```bash
git revert <commit-sha>
```

或直接删除新增文件：
- `memory-service/evaluation/d13c_session_eval.py`
- `scripts/run_d13c_session_eval.py`
- `memory-service/tests/test_d13c_session_eval.py`
- `memory-service/tests/fixtures/d13c_smoke_bundle.json`
- `memory-client/tests/test_d13c_stability.cpp`

并还原 `memory-client/tests/CMakeLists.txt` 中 `test_d13c_stability` target 注册段。

---

**Reviewer 结论**（由 Reviewer 填写）：

- [ ] PASS
- [ ] PASS_WITH_DEBT（需记录技术债 TD 编号）
- [ ] REWORK
- [ ] BLOCKED
