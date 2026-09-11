# D14B Post-Refreeze Capture Checklist

Date: 2026-09-11
Status: `DRAFT / NOT_EXECUTED`
Trigger: Release Owner / Reviewer D approval of
`docs/day15/14_d14b_vector_cli_refreeze_request_20260911.md`.

This checklist is preparation documentation only. It does not execute formal
capture, create an evidence root, or change any runner, query, threshold, IPC,
schema, DB, or error-code contract.

## Preconditions

1. A Release Owner / Reviewer D decision has been recorded with approver
   identity, UTC time, and the exact approved `vector_bridge_cli` SHA-256.
2. A new D14B capture handoff has been derived from the reviewed handoff. It
   may change only the approved vector CLI identity and required approval
   provenance fields.
3. A new unused evidence root has been selected. The existing
   `d14b_20260911T091924Z_ba3b50e` preflight root remains immutable and is not
   reused.
4. `run_d14b_preflight.py` has returned exit code 0 against the new handoff
   and evidence root.
5. The VM and snapshot identity still match the D14D handoff.

## Capture Sequence

Use the four runners already pinned in
`release/handoff/d14b-capture-handoff.json`:

- `scripts/capture_d14b_sqlite_truth.py`
- `scripts/capture_d14b_fts5_results.py`
- `scripts/capture_d14b_vector_results.py`
- `scripts/capture_d14b_rrf_results.py`

For each lifecycle checkpoint, capture the SQLite truth first, then FTS5,
vector, and RRF. Assemble the checkpoint with
`scripts/capture_d14b_retrieval_snapshot.py` using the artifacts and receipts
produced by those runners.

The evidence manifest verifier requires these checkpoints:

| Checkpoint | Required path |
|---|---|
| baseline | `baseline/baseline.json` |
| service_restart_after | `service_restart/service_restart_after.json` |
| rebuild_after | `rebuild/rebuild_after.json` |
| delete_before | `delete/delete_before.json` |
| delete_after | `delete/delete_after.json` |
| reboot_before | `os_reboot/reboot_before.json` |
| reboot_after | `os_reboot/reboot_after.json` |

After the lifecycle sequence, close the evidence root with its SHA256SUMS and
run:

```bash
python3 scripts/verify_d14b_evidence_manifest.py \
  --evidence-root <new-exclusive-evidence-root>
```

## Fail-Closed Rules

1. Never overwrite or reuse an evidence file, receipt, checkpoint, or root.
2. Stop on the first runner, preflight, snapshot-identity, vector-CLI, or
   manifest-verification failure and preserve the partial evidence.
3. Do not replace a failed checkpoint with a second "clean" root.
4. Do not declare `D14B_FORMAL_L3=PASS` until the evidence package passes the
   existing manifest verifier and has completed D review, with E supplemental
   review where performance or security semantics are involved.
5. Keep `release_ready=false` and `production_ready=false` until all required
   release gates have independently closed.
