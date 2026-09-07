# D13C PR #134 最新 Review 返工收口（2026-09-06）

> 分支：`test/D13C-session-eval`；任务：D13C（original_owner=C，current_executor=B）。
> 只处理最新复审（Ducknesses）未关闭的 NR-1~NR-5，不重写已确认修复项。

## 0. 基线

| 项目 | 值 |
|---|---|
| 返工基线 HEAD | 514cf0e（含 merge main@8a405ae #151 的 4fcf228） |
| GitHub CI | Repository Baseline Check SUCCESS；Memory Client L0 ctest + Contract L0 ctest SUCCESS |
| Python L1 | 本轮返工后 **72 passed**（module + CLI tests） |
| Runtime | `UNVERIFIED`（保持，未声称 VM 闭环） |

## 1. NR-1：stability cohort 模型（CLOSED）

- Session 证据字段改为三件套：`execution_group_id` + `stability_cohort_id` + `stability_round`，三项同时提供或同时不提供（只出现一部分 fail-closed）。
- `_validate_stability_rounds()` 按 `(execution_group_id, stability_cohort_id)` 分组，每个 cohort 独立校验 rounds == {1..stability_repeat}（缺轮/同 cohort 重复/越界/无证据 fail-closed）。
- A/B 同 round 不再误判 duplicate：`A1 B1 ... A5 B5` 形态通过。
- `_cross_session_isolation()` 改为 round-scoped：只比较同 `(execution_group_id, stability_round, scenario)` 下不同 cohort 的 A/B pair，不再跨 round 两两（A1 vs A2 / B1 vs B5 不比较）；无轮次证据的 bundle 退回按 scenario 通用比较。

## 2. NR-2：删除 repeat_count 假 provenance（CLOSED）

- `EvalSessionConfig` 删除 `repeat_count` 字段与解析；`_config_dict()` 不再输出。
- 配置版本提升为 `d13c-session-eval-config/v2`（避免“版本 v1 但 schema 已变”）。
- fixture / 测试 CONFIG / CLI 文档示例同步删除 `repeat_count`；未引入新的无证据 repeat 维度。
- D13C 保留的唯一重复语义：`stability_repeat` + `stability_round` + `stability_cohort_id`（主演示稳定性复跑）。

## 3. NR-3：finalization_reason 不冻结枚举（CLOSED）

- 删除 `_VALID_FINALIZATION_REASONS` 白名单；`finalization_reason` 只严格要求为字符串，不再限制业务枚举。
- `ended / truncated / filtered / 未来新增值` 均可进入 evaluator；与 C++ S2 语义一致。
- 保留已明确的 retry 跨字段约束：`retry` 必须携带非空 `retry_of_turn_id` 且 ≠ `turn_id`（计入 violation，不 null 整体）。
- 不再假设 `finalization_reason == "stop"` 必须携带 `stop_reason`（与上游契约/当前 C++ 模型一致）。

## 4. NR-4：S3 retry 真实走 IPC（CLOSED，待 CI ctest 验证）

- S3 构造 retry 事件后，经生产 `MemoryClient::sendRequest("turn.finalized", retryEvent)` 真实发送到 MockGatewayServer。
- Mock 捕获并断言：收到 `finalization_reason=retry`、`retry_of_turn_id="turn-s3-001"`、≠ 当前 turn id；前后非 retry 发送 `retry_of_turn_id` 为空。
- 删除“builder-only 足够”的旧注释；未改动 QML PostTurn API。

## 5. NR-5：无 comparable pair 顶层 fail-closed（CLOSED）

- `compute_session_report()` 在 `_cross_session_isolation()` 返回 `fail_closed_reason` 时直接 `_empty_report(config, reason)` → `aggregate_metrics=null` + 顶层 `fail_closed_reasons`。
- CLI `_emit()` 对 `aggregate_metrics=null` 统一 exit 2（已有逻辑），新增 no-pair CLI 负向测试。
- smoke bundle 调整为可比较 A/B 样本（scenario 相同、cohort 不同、round 相同、context 不同）。

## 6. 本轮修改文件

| 文件 | 变更 |
|---|---|
| `memory-service/evaluation/d13c_session_eval.py` | NR-1/2/3/5 主体 |
| `memory-service/tests/test_d13c_session_eval.py` | 重构 + 新增测试 |
| `memory-service/tests/test_d13c_session_eval_cli.py` | 新增 no-pair exit2 等 |
| `memory-service/tests/fixtures/d13c_smoke_bundle.json` | v2、去 repeat_count、A/B 打标 |
| `scripts/run_d13c_session_eval.py` | 文档示例同步（v2、去 repeat_count） |
| `memory-client/tests/test_d13c_stability.cpp` | S3 retry 真实 IPC |

## 7. 验证与剩余

- Python：`72 passed`；`py_compile` PASS；CLI valid exit 0 / no-pair exit 2（测试覆盖）。
- C++：S3 改动与 S4（上一轮）需 GitHub `Memory Client L0 ctest` 验证（本机/VM 无 Qt5 dev）。
- 文档：02/05/06（09-03/09-05 快照）保留历史状态，以本文档 + PR 评论为最新口径。
- 下一步：CI 全绿 → PR 更新 closure 表（评论形式）→ 请求 Ducknesses 复审。Runtime 保持 UNVERIFIED。

