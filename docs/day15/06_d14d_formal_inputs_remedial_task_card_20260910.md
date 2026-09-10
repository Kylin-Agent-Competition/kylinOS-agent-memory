# D14D Formal Inputs Remedial Task Card (2026-09-10)

## Purpose

This PR supplements the D14D formal inputs that were waived in PR #124
(`docs/day14/21_d14b_formal_l3_intake_blockers_20260909.md`) and
referenced by PR #173 (`release/btrack/D15B_BTRACK_MANIFEST.json`).

## Missing File Inventory

The following D14D-related formal inputs were identified as missing
from the repository baseline (`a7abb1e`) and from PR #173's diff.

| # | Item | Status in this PR | Notes |
|---|------|-------------------|-------|
| 1 | `d13d-handoff.json` | **Added** | Generated from `D13D_CLOSURE_HANDOFF_20260908.md` |
| 2 | `d14d-handoff.json` | **Added** | Generated from `docs/D_TRACK_STATUS.md` + D14D evidence root |
| 3 | `d14b-capture-handoff.json` | **Added** | Binds 4 production capture runner scripts with SHA-256 |
| 4 | `scripts/d14b_capture_runner_common.py` | **Added** | Shared fail-closed helper for all 4 runners |
| 5 | `scripts/capture_d14b_fts5_results.py` | **Added** | FTS5 channel capture runner |
| 6 | `scripts/capture_d14b_rrf_results.py` | **Added** | RRF channel capture runner |
| 7 | `scripts/capture_d14b_vector_results.py` | **Added** | Vector channel capture runner |
| 8 | `scripts/capture_d14b_sqlite_truth.py` | **Added** | SQLite truth channel capture runner |
| 9 | `tests/retrieval/test_d14b_capture_runners.py` | **Added** | Unit tests for capture runner common helper |
| 10 | `kylin-memory-a-d14a-0.1.0-d14a.tar.gz` | **Still missing** | Binary frozen tar bytes; only SHA-256 / manifest records exist |
| 11 | Production capture runner credentials | **CLOSED (2026-09-10)** | VM SSH confirmed; kylin_memory.db accessible on VM |
| 12 | D14D clean VM/snapshot formal access | **CLOSED (2026-09-10)** | Snapshot `d14d-clean-base-20260907-r4` confirmed active on `Kylin-D14D-clean-vdi-20260906` |

## Items 10-12 Explanation

- **Item 10 (frozen tar)**: The tar SHA-256 (`2222c904...`) and manifest
  SHA-256 (`76a83933...`) are recorded in `package_manifest.json` and
  `D14A_FINAL_PACKAGE_FREEZE_RECORD_20260908.md`, but the actual binary
  tar bytes were never uploaded to the repository or any accessible
  release. This PR cannot fabricate the binary.
- **Item 11 (runner credentials) CLOSED**: VM SSH access confirmed
  2026-09-10 at `127.0.0.1:2223`; `kylin_memory.db` present at
  `/home/kylin-agent/.local/share/kylin-memory/kylin_memory.db` with
  full schema (`memory_entries` empty on clean snapshot, expected).
  Password passed via `KYLIN_VM_PASSWORD` env var, never stored in
  files. Long-term solution remains SSH public key.
- **Item 12 (clean VM/snapshot) CLOSED**: VirtualBox snapshot
  `d14d-clean-base-20260907-r4` (UUID `6dc9468e-36a8-41b3-b7c9-
  6115c7b8fc56`) confirmed active on VM `Kylin-D14D-clean-vdi-
  20260906` (UUID `70ca1ea3-c27e-483d-aaba-0cac7dc5c77c`), VM running,
  OS Kylin V11 / kernel 6.6.0-76-generic / x86_64.

## Waiver Relationship

PR #173's manifest (`release/btrack/D15B_BTRACK_MANIFEST.json`) records
`actual_tar_bytes_available: false` and the waiver scope. This PR
addresses items 1-9 of the missing inventory. Items 10-12 remain as
`deferred_formal_debt_actions` requiring external provision.

## Verification

After this PR merges, the capture runners can be invoked with:

```bash
python3 scripts/capture_d14b_sqlite_truth.py \
  --db-path <production_db> \
  --user-id <test_user> \
  --tested-commit ba3b50e1bdeea185bca9daee9d1d45958f62a636 \
  --capture-handoff release/handoff/d14b-capture-handoff.json \
  --output evidence/d14b/sqlite_truth.json \
  --receipt-output evidence/d14b/sqlite_truth_receipt.json
```

The runner will fail-closed if the handoff JSON, tested commit, or
runner SHA-256 does not match.
