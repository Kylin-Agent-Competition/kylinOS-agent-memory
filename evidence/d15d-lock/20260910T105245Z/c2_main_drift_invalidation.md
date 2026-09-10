# C2 main-drift invalidation evidence

Run ID: `20260910T105245Z`

## Source

- PR: [#175](https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/175)
- Reviewer E Round 4 formal review: `PRR_kwDOTmtus88AAAABM-v4BA`, submitted at `2026-09-10T10:43:30Z`
- Baseline branch: `docs/day15-d15d-lock`
- Baseline HEAD: `80f5f75c7879796cdf82f70ba9c405374030eaf1`

## Commands and facts

Command:

```powershell
git fetch kylin-mem main
git rev-parse kylin-mem/main
git diff --name-only ba3b50e1bdeea185bca9daee9d1d45958f62a636..kylin-mem/main -- packaging/ memory-service/ cpp-bridge/ migrations/ config/ docs/day14/00_d14a_release_package_contract.md
```

Observed current main:

```text
4a6323fb3a8c73e0b15f1f3629d28dfc12071541
```

Observed locked/runtime prefix changes:

```text
memory-service/evaluation/d14c_evidence_package.py
memory-service/evaluation/d14c_l3_harness.py
memory-service/evaluation/d14c_runtime_precheck.py
memory-service/tests/test_d14c_evidence_package.py
memory-service/tests/test_d14c_l3_harness.py
memory-service/tests/test_d14c_runtime_precheck.py
memory-service/tests/test_d14c_runtime_precheck_cli.py
```

Ancestor checks:

```text
git merge-base --is-ancestor ba3b50e1bdeea185bca9daee9d1d45958f62a636 4a6323fb3a8c73e0b15f1f3629d28dfc12071541: PASS
git merge-base --is-ancestor cdcce34f870472e63a9359e5a03254eaf9ca6db2 4a6323fb3a8c73e0b15f1f3629d28dfc12071541: PASS
git merge-base --is-ancestor 80f5f75c7879796cdf82f70ba9c405374030eaf1 4a6323fb3a8c73e0b15f1f3629d28dfc12071541: FAIL (rc=1)
```

The third check is expected because the old PR branch was based on `cdcce34` and
is not an ancestor of the new main snapshot.

## Builder fact

`packaging/release/build_release_package.sh` uses `shutil.copytree` from
`memory-service/` to `runtime/app/` with exclusions only for `tests`,
`__pycache__`, `*.pyc`, and `.pytest_cache`. It does not exclude `evaluation/`.
Therefore the seven paths above are all C2 policy hits, but they have two
different package-content outcomes:

- 3 files enter `runtime/app/`: `memory-service/evaluation/d14c_evidence_package.py`,
  `memory-service/evaluation/d14c_l3_harness.py`, and
  `memory-service/evaluation/d14c_runtime_precheck.py`.
- 4 files do not enter the package because the builder excludes the whole
  `memory-service/tests/` directory:
  `memory-service/tests/test_d14c_evidence_package.py`,
  `memory-service/tests/test_d14c_l3_harness.py`,
  `memory-service/tests/test_d14c_runtime_precheck.py`, and
  `memory-service/tests/test_d14c_runtime_precheck_cli.py`.

The test files still trigger C2 because the existing Runbook classifies the
entire `memory-service/` prefix as runtime-sensitive. This distinction does not
change the fail-closed conclusion.

## Gate conclusion

- C2: `FAIL_INVALIDATED`
- Release classification against current main:
  `RUNTIME_EVIDENCE_STALE_AGAINST_CURRENT_MAIN`
- Existing frozen package lock: `INVALID` for representing current main
- Explicit conclusion: `TRIGGER_NEW_RELEASE_PACKAGE_IDENTITY`
- Required next actions: rebuild from a clean checkout of the selected new
  release commit, recompute package/manifest/SHA256SUMS identities, rerun the
  full consistency chain, and rerun required Kylin VM evidence.
- This run does not claim a new L2/L3 PASS and does not modify the builder to
  exclude `evaluation/`.

## Boundary

This is a fail-closed invalidation record. The D14D frozen tar remains valid as
a historical D14D artifact, but it is not a valid D15D lock of current main.

## Round 7 current-main recheck

After the `4a6323f-r2` rebuild, current main advanced to:

```text
2782a9048c235006c17024c9798cf988a07627a1
```

The added files are docs-only:

```text
docs/day15/03_c_track_production_integration_closure_status_20260910.md
docs/day15/04_c1_rebuilt_vm_test_status_20260910.md
```

`4a6323f..2782a904` has no hit under `packaging/`, `memory-service/`,
`cpp-bridge/`, `migrations/`, `config/`, or the D14A contract path. Therefore
the Round 4 fail-closed decision above remains the historical cause of the
rebuild, while C2 for the completed `4a6323f-r2` release is
`PASS_CURRENT_MAIN_NO_RUNTIME_SENSITIVE_DRIFT` at current main `2782a904`.
