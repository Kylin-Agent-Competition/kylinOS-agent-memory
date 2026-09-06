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
| P0-I3b | All four real dispatchers and only canonical 4/4/4/5 raw output | `BLOCKED_PARTIAL`: Preference/Conflict/Safety are review-pending code candidates; Forget needs an externally supplied state binding plus real retrieval observations. |
| P0-I3c | Non-author independent review and merge of the complete adapter | `PENDING` |
| P0-I3d | Reselect the post-adapter formal tested commit and revalidate an isolated VM | `PENDING` |

No stage here produces formal raw, a Seal, a Runner decision, or `D13D_FROZEN`. The tested commit remains `PENDING_P0_I3_RESELECTION`.

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
- RuntimeBinding 冻结 production vent.ingest handler identity：dispatch 前要求
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
