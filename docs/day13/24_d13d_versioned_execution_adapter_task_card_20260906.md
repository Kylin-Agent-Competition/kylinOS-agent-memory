# D13D Task Card: Versioned Execution Adapter

## Status and baseline

- Status: `CANDIDATE_NOT_FROZEN`.
- Candidate baseline: `main@17dce3696066213b54e9dcbe6b87c4944cb41c8c` (PR #157 merge).
- Candidate Dataset SHA-256 (current repository content):
  `9740c00f4a9d91471bec8e6fa8aeeeb52f890f8680d83f740a84db2b1701a44b`.
- Delivery branch: `feat/d13d-versioned-execution-adapter`.
- This task starts only after PR #157's production prerequisites were merged. It does not
  convert the merged commit into a formal tested or frozen commit.

## P0-I3 staged delivery

| Stage | Scope | Current state |
| --- | --- | --- |
| P0-I3a | Versioned preflight, approved Dataset SHA anchor, isolation/shape checks and L1 regressions | `IMPLEMENTED_PENDING_INDEPENDENT_REVIEW` |
| P0-I3b-infra | Preference/Conflict real dispatch, Safety ValidatedRuntimeBinding + provenance, uniform execution receipts, Forget schema contract (`forget_mode`), canonical package layout under execution evidence root | `CANDIDATE_PENDING_INDEPENDENT_REVIEW`（PR #150 合并范围） |
| P0-I3b-completion | Safety Gate-9 projection（需 D13E 独立裁定 Gold-independent projection 规则）与 Forget 真实 dispatch（需外部 state-binding + realtime/rebuild 观测） | `IN_PROGRESS`（独立 follow-up 已开工：分支 feat/d13d-i3b-completion + 任务卡 26_d13d_i3b_completion_worklist_20260906.md；非 PR #150 merge gate；P2-A/B/C 闭合前保持 `BLOCKED_PENDING_CROSS_TRACK_COMPLETION`） |
| P0-I3c | 非作者独立 review 并 merge **partial candidate infrastructure（PR #150）** | `PENDING` |
| P0-I3d | 在 I3b-completion 闭合后重新选择正式 tested_commit 并复验隔离 VM | `PENDING`（依赖 I3b-completion） |

PR #150 只推进 I3a + I3b-infra 的候选基础设施合并，不产生 formal raw、Seal、attestation、
Runner 结论或 `D13D_FROZEN`；Safety Gate-9 投影与 Forget 真实 dispatch 的闭合在独立
follow-up（I3b-completion）完成后，才进入正式 I3d 与冻结流程。tested commit 保持
`PENDING_P0_I3_RESELECTION`。

### 2026-09-06 Phase 2 kick-off（PR #159 merge 后）

- PR #159（D14D Phase 0）已 merge，main HEAD = `dc58e83479d718c8e3fbbbbb5d3b3f046f651973`；I3b-completion 独立 follow-up 开工：分支 `feat/d13d-i3b-completion`，任务卡 `docs/day13/26_d13d_i3b_completion_worklist_20260906.md`，PR 初始 Draft / `BLOCKED_PENDING_CROSS_TRACK_COMPLETION`。
- 本卡 staging 中 P0-I3b-completion 已更新为 `IN_PROGRESS`；formal tested_commit 仍 `PENDING_P0_I3_RESELECTION`，不产生 formal raw / Seal / attestation / Runner / `D13D_FROZEN`。
- 既有 infra 历史（I3a/I3b-infra 经 PR #150 合并）与 `CANDIDATE_NOT_FROZEN` 边界不因本次 kick-off 改写。

### 2026-09-06 PR #150 review round（codex 批次）

- 候选 Gold-independent raw projection schema `D13E_RAW_RESULT_SCHEMA_V1`
  （状态 `CANDIDATE_PENDING_D13E_REVIEW`，未冻结）；`raw_record` 与 writer 改为按
  metric 精确白名单校验，`actual` 的未知字段 fail-closed。
- Preference actual 改为顶层稳定字段投影，移除 `records[]`（消除正式 Runner Gate 9 对
  Preference 的未知字段崩溃）。
- Safety dispatch 只接受 `ValidatedRuntimeBinding`：engine/registry/DB canonical path
  由受控 builder 在 validated `state_root` 下一次性创建；不再接受调用方裸
  `conn` + `registry`。负测覆盖 state_root 外 DB、跨 validated binding、复用既有 DB。
- canonical raw 生产权收紧：writer 只接受真实 dispatch 产出的 `ObservedRawRecord`
  （拒绝手工 raw Mapping），并保持完整性校验；正式 orchestration 待 Forget 外部
  binding 到位后闭合。
- 未闭合跨轨依赖：Safety `sensitivity`/`admission`/`operation` 投影需要 D13E 对正式
  Runner/Gold 重新基线（见 18_ 文档“候选投影契约”）；Forget 仍 BLOCKED。

### 2026-09-06 re-review round（Review HEAD 04fc080）

- schema 状态改为 `CANDIDATE_PENDING_D13E_REVIEW`，不再自称冻结；Safety 跨轨投影
  合同未由 D13E 裁定前，Safety raw 不视为 Gate-9 完成。
- `ValidatedRuntimeBinding` 三重绑定：engine.url.database 必须等于 db_path，engine
  与 registry 必须携带同一受控 run token；新增 engine 指向外部 DB / registry 绑定
  另一 engine 的 fail-closed 负测。
- `ObservedRawRecord.actual` 改为不可变快照（MappingProxyType + digest）；writer 写
  入前重新执行完整 actual/trace/runtime 校验；手工 plain-dict 构造与篡改均无法进入
  canonical package。
- Preference/Conflict dispatch 生成真实可审计 trace ID（绑定 sample_id、tested
  commit、UTC、actual digest）；wrong-sample trace 负测。
- raw package 改为 sibling temp + atomic rename，I/O 中途失败不留正式 output（故障
  注入测试覆盖）。
- 09 任务卡执行清单修正 Seal 顺序（D13D Execution Seal 在 attestation 之后），并把
  `freeze_status` 拆为 `environment_status` + `evidence_status`（legacy 仅派生）。
- 集成测试改为逐样本显式期望：must-True / 已登记观测缺口（pref-003）/ Safety
  跨轨 blocked 三组分别断言。

### 2026-09-06 re-review round（Review HEAD dd089f9）

- ValidatedExecution.records 递归不可变快照（dict->MappingProxyType、list->tuple），
  Dataset SHA 校验后不可再改写样本 input 后以官方身份 dispatch；负测覆盖顶层、pref
  user_text、conflict side、forget target_selector。
- RuntimeBinding 冻结 production vent.ingest handler identity：dispatch 前要求
  registry.route() 返回 builder 记录的同一 callable；覆盖/unregister 后 fail-closed，
  fake handler 不会被调用。
- receipt provenance 边界：_raw_record/_write_raw_records 降为内部私有 seam；
  正式 canonical 唯一入口为 dispatch_and_write_canonical()（不接受外部 receipts，
  内部完成 dispatch->serialize）；Forget binding 未到位前该入口 fail-closed，不产生
  任何 output。
- Preference/Conflict trace 升级为 evidence-backed：每次 dispatch 在 evidence_root/
  dispatch/<sample_id>.json 落一条 execution receipt（sample/metric/tested_commit/
  actual_digest/UTC/entrypoint），writer 收件时校验 trace 目标存在且 sample/metric/
  commit/digest 一致；负测覆盖 missing trace / cross-sample / cross-commit。
- Safety 跨轨投影合同与 pref-003 观测缺口保持 CANDIDATE_PENDING_D13E_REVIEW /
  登记缺口处理，未读取 Gold、未补零。

### 2026-09-06 re-review round（Review HEAD dc3ca63）

- Evidence root 生命周期统一（方案 A）：adapter 以仓库外、全新且唯一的
  `execution_evidence_root` 为 D13D 唯一证据目录，`dispatch/` receipts 与 `raw/`
  canonical 四文件同根；取消独立 output/evidence 双根互斥。preflight 只要求
  execution evidence root 与 state_root 全新、互不 overlap、不与仓库 overlap。
  Gate 0--10 通过后 immutable import 到仓库
  `evidence/l2-kylin-vm/d13d_<UTC_RUN_ID>` delivery 副本（见 09 任务卡“输出目录”）。
- stateless execution receipt 改为 **exclusive-create**：同一 sample 重复 dispatch
  fail-closed，绝不静默覆盖首条执行证据；负测覆盖。
- 新增 integration test：canonical 四文件位于 execution evidence root/raw，且经
  Runner evidence-root path gate 解析后仍在唯一证据目录内。
- 修复本文档早前 `event.ingest` 前误入的控制字符（ESC），恢复为正常文本。
- Safety 跨轨投影合同与 pref-003 观测缺口继续登记；未读 Gold、未补零。

### 2026-09-06 re-review round（Review HEAD 04c67ca）

- Forget schema 闭合：候选投影契约把 `forget_mode` 纳入 required + allowed，值来自
  validated Dataset / 真实 forget invocation（非 expected），并做五个合法 mode 枚举
  校验；五个 mode 的 counters-0 投影均通过 adapter->Runner contract（不再存在
  “adapter schema 与 Runner/Gold 结构不兼容”的 Forget blocker）。
- stateful（Safety/Forget）provenance 与 stateless 对齐：每次真实 dispatch 写
  `dispatch/<sample_id>.json` execution receipt（绑定 sample/metric/tested_commit/
  actual_digest/runtime_scope/trace_reference，exclusive-create）；writer 对每个
  record（含 Safety/Forget）校验 receipt 存在且内容一致，杜绝 synthetic stateful
  receipt 进入 canonical package。
- Safety Gate-9 显式预期：safety-004（counter 判定）当前 True；safety-001/002/003
  在投影合同经 D13E 裁定前为 False 且不得视为完成（保持 CANDIDATE_PENDING_D13E_REVIEW/
  BLOCKED_PARTIAL，未读 Gold、未补零）。
- 同步 18_ 验收文档、evaluation/d13e/README 的 raw 合同说明。

### 2026-09-06 re-review round（Review HEAD 4a16cf6，第七轮 re-scope）

- Reviewer 已确认关闭：Forget `forget_mode` schema BLOCKER；stateful/stateless 统一
  execution receipt provenance HIGH。
- 剩余唯一核心 BLOCKER 为 Safety Gate-9 projection（需 D13E 独立裁定 Gold-independent
  规则，adapter 不得读 Gold/expected；改 Runner/Gold 需独立 D13E 变更与重新 Seal）。
- 本 PR 按 Reviewer 提议 re-scope 为 **partial candidate infrastructure merge**：
  合并范围 = I3a + I3b-infra；I3c merge gate 只针对该基础设施，不再宣称“complete
  adapter”；Safety Gate-9 projection 与 Forget 真实 dispatch 登记为独立 follow-up
  （I3b-completion），完成后才进入正式 I3d/冻结。
- 集成测试对 Safety 保持显式 Gate-9 预期：safety-004=True；safety-001/002/003 在
  D13E 裁定前为 False 且不得视为完成（未读 Gold、未补零）。

## Goal

Provide a versioned, fail-closed execution adapter for the D13E formal Dataset. The adapter
must validate its invocation and eventually dispatch the existing Preference, Conflict,
Safety, and Forget production paths against isolated state. It projects observed facts to
per-sample raw records; it never evaluates correctness.

## Approved scope

- Add the adapter and focused L1 tests.
- Add strict validation for the Dataset identity, tested commit, clean worktree, empty output
  root, isolated state paths, sample uniqueness, and metric distribution.
- Reuse existing production policy/handler/observation seams. Safety and Forget raw values
  come from their read-only observers.
- Produce only the four raw JSONL record shapes required by the formal runner, and only in a
  later invocation whose frozen-environment preconditions have been independently met.

## Explicit non-goals and prohibitions

- Do not read, import, hash-check, copy, or derive behavior from Gold or Threshold artifacts.
- Do not change Dataset, Gold, Threshold, IPC contracts, error codes, or frozen schema.
- Do not implement hard delete, cascade, or source-event deletion.
- Do not generate formal raw, attestations, seals, or a `FROZEN` conclusion in this task.
- Do not represent WSL/L1 results as Kylin VM L2 evidence.
- Do not make adapter-side database updates from a target selector or otherwise synthesize
  zero-valued observations.

## Invocation contract

The adapter accepts an explicit tested commit, Dataset path, expected Dataset SHA-256, and a
new isolated execution/output root. It rejects all of the following before dispatch:

- tested commit differs from `HEAD`, is not a full Git SHA, or the worktree is dirty;
- Dataset is missing, has a wrong hash, malformed JSONL, duplicate IDs, an unknown metric,
  incorrect total/distribution, or an invalid record shape;
- output root exists or an isolated state/evidence path is absent, relative, or overlaps a
  repository path; and
- a dispatch result lacks its trace/reference or a Safety/Forget observer fails closed.

For every raw record the top level is exactly `sample_id`, `metric`, `actual`, and
`trace_reference`. The adapter may not add expected values, a pass/fail field, or information
from evaluation artifacts other than the Dataset inputs.

## Security and evidence boundary

The adapter runs supplied data through the existing user-scoped production boundaries. It
uses a new per-run SQLite/state/evidence location and never touches normal user data. Free
text is not placed in logs or trace references. Any missing controlled state, observer result,
or retrieval binding is an execution error rather than a zero count.

## Validation and acceptance

- L0: `py_compile`, Ruff `F,E9`, and `git diff --check` pass.
- L1: valid Dataset preflight; all stated malformed/integrity/isolation failures; raw record
  shape validation; and a test proving no Gold/Threshold access are covered.
- Kylin VM L2 (later): freeze a new tested commit and isolated VM evidence root, execute all
  17 samples, collect authentic raw/logs, obtain the two seals, then run the formal runner.

## Blocking conditions for formal execution

1. A post-adapter tested commit must be frozen after all L0/L1 and review are complete.
2. The assigned non-author execution authority must independently revalidate the VM snapshot, environment identity, and external trust root; it must not reuse the D13E Review Seal identity/key.
3. A unique VM evidence directory and its write authority must be assigned.
4. Raw execution, execution attestation, and both signatures must be produced by the
   authorized formal process. Until then this work remains `CANDIDATE_NOT_FROZEN`.
5. Forget formal dispatch additionally requires the reviewed external state-binding and
   retrieval-observation input described in
   `docs/day13/25_d13d_formal_forget_state_binding_request_20260906.md`; the adapter
   must fail closed rather than synthesize targets or observations.

## Rollback

The adapter is a new standalone entry point. Reverting its commit removes no production
schema or runtime behavior. It must refuse to reuse a pre-existing output root.
