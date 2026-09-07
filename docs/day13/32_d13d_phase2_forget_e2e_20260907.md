# D13D Phase 2 Forget FTS-Channel E2E Record (2026-09-07)

## Status

`FTS_CHANNEL_5_5 / PARTIAL_NON_FORMAL`. This record covers only the FTS
realtime and rebuild channel. It does not close the Phase 2 Forget real-dispatch
capability Gate because `29_` and `30_` still require real Vector dual-channel
coverage before a complete Forget 5/5 claim. It is not formal Kylin runtime
evidence, not a canonical 17-sample raw package, and not a Runner Gate, Seal, or
`D13D_FROZEN` result.

## Identity

| Item | Value |
| --- | --- |
| PR | #160 |
| Execution commit | `d60dbe6e5d4e4c9583fb1eca250f811a8d10f75c` |
| State preparation commit | `4ed82e5211a70d930c92431f8a94417bc2d932eb` |
| Binding version | `d13d-forget-state-binding/v2` |
| Canonical binding SHA-256 | `2a337d575acf3d7737e0de7b773d81a79ee3a27e1c8b807af86d5c1e4a919fab` |
| Sealed source DB SHA-256 | `a1c7531522ee949bb3a618a09e974f20a00d75b47726e2f340d1a9220dd91d33` |
| Dataset SHA-256 | `9740c00f4a9d91471bec8e6fa8aeeeb52f890f8680d83f740a84db2b1701a44b` |
| VM | `Kylin-D14D-clean-vdi-20260906` / snapshot `d14d-clean-base-20260906-r1` |
| Evidence root | `/home/kylin-agent/d13d-p2b-exec-20260907-r5/evidence` |

## Real Chain

Each Forget sample used a fresh runtime clone from the sealed source DB and went
through the real production preview, execute, `forget.executed` Outbox event,
`OutboxWorker` / `OutboxRouter` / deletion-consumer ACK, FTS realtime query, and
full FTS rebuild observation. The adapter did not synthesize counters.

No Vector provider was injected for this run. Vector pre-delete positive probe,
Vector deletion, Vector realtime residual, Vector full rebuild/requery, and
per-channel Vector provenance were not exercised. Accordingly, the counters
below are FTS-channel observation counters only.

Five fresh execution receipts were written to the evidence root:

| Sample | Mode | Receipt SHA-256 |
| --- | --- | --- |
| `d13e-forget-001` | single_item | `2915bc42edf80fbce23705f60279d2c994001726e0c4b0712d59b885a9b1378d` |
| `d13e-forget-002` | session | `dd8e11586db3df15c2bd91919fc14b14569959547dd8747a8e672500dbbaf596` |
| `d13e-forget-003` | topic | `a962830f04510b1e9b3c590ec416b8feb18228c5f129b4931b6a43e908250120` |
| `d13e-forget-004` | time_window | `aa9fef6894a8654e23597f73065f45626043d91c6a6159529416b092baed757b` |
| `d13e-forget-005` | full_reset | `c1bb380b375e3914a8c948fec86293a3ab1f2bbea086ff4b35e8e710e52e85a8` |

Summary: `phase2_forget_summary.json`
SHA-256 `9d62c9b9e4f705f54229d9f1f5da7f2d878c824dc10fcf67bb22382b05437bdf`.

All five FTS-channel records observed:

```text
missed_target_items = 0
wrongly_deleted_items = 0
cross_user_violation_count = 0
residual_after_realtime_query = 0
residual_after_full_rebuild = 0
```

## Fixes Exercised

- `fdf9be1`: preserve explicit `knowledge:` / `preference:` kind tags in the
  FTS deletion provider.
- `6ca816d`: derive target kind from `target_type` for real bare-ID
  `forget.executed` payloads used by non-`full_reset` modes.
- `5efbf7f` / `d60dbe6`: align preference deletion provenance with the pre-delete
  stable version identity, avoiding both version-row-id and
  post-delete-version mismatches.

## Verification

| Layer | Command scope | Result |
| --- | --- | --- |
| Local L1 | execution adapter, D9D outbox router, provider delete, observability, relation lifecycle, vector snapshot | `144 passed` |
| Kylin VM L1 | CI's seven D13D prerequisite files | `189 passed` |
| Kylin VM contract | `test_d13e_formal_eval` Runner/Gold/trust contract suite | `48 tests OK` |
| Repository | `verify_repository_baseline.sh` + `git diff --check` | PASS |
| CI @ `d60dbe6` | Repository Baseline Check, D14A packaging + provenance, Carlton independent host evidence closure | all SUCCESS |

CI independently green at the same commit:

```text
Repository Baseline Check                   SUCCESS
D14A packaging + provenance L1              SUCCESS
Carlton independent host evidence closure   SUCCESS
```

## Boundary

`dispatch_and_write_canonical()` remains fail-closed for Forget. P2-B remains
`BLOCKED_PENDING_VECTOR_DUAL_CHANNEL`. Closing it still requires isolated Kylin
VM injection of the real Embedding/Vector provider, per-sample pre-delete hits
on both FTS and Vector, real dual-channel consumer cleanup, Vector rebuild
evidence, and per-channel provenance.

Phase 3 must still replay the final frozen `tested_commit` evidence root,
execute all 17 real samples, produce formal provenance, obtain both seals, and
run Runner Gate 0-10 before any formal result is claimed.
