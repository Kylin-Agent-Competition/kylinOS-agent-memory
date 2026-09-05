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
