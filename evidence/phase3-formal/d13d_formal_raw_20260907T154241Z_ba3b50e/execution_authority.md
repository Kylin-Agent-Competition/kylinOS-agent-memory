# D13D Formal Raw Execution Authority

These artifacts make the allowed remote orchestration independently reviewable.
The runtime implementation remains frozen at tested commit
`ba3b50e1bdeea185bca9daee9d1d45958f62a636`.

## Artifacts

| Artifact | SHA-256 | Role |
|---|---|---|
| `scripts/tmp_d13d_formal_raw_runner.py` | `cc77e9d12f9b27f6dc916955cffa6eeecdcd0473b1fda0477ad00dfc0b35d27` | Host-side orchestration source |
| `formal_raw_remote_runner.py` | `80f1f9f3b8d69b2bcf358734ce4b45bb217cafd82158e2666f22b367e4f937a8` | Exact remote runner uploaded to the VM |
| `prepare_forget_state_v2.py` | `a123b4e27ce553cc6473029dbe2f19f5f8257132efb9d5277af2d1cc8dfd6132` | Forget state preparation helper |
| `formal-raw-head.bundle` | `bd375d8d106c1835e0be958b184eb3bc236fa7c5f007dddeac32864236666aa0` | Complete Git history bundle |

The `REMOTE_RUNNER` literal in the host-side source is byte-identical to
`formal_raw_remote_runner.py` (10728 bytes, same SHA-256).

## Fixed invocation

```powershell
python scripts/tmp_d13d_formal_raw_runner.py `
  --output evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e `
  --remote-root /home/kylin-agent/d13d-phase3-formal-raw-20260907-r6
```

`KYLIN_VM_PASSWORD` is injected from the environment; the runner exits
non-zero when it is absent. VM, snapshot, SSH, Python, and environment
identities use the defaults in the host-side source and match
`evidence/environment_identity.json`.

## Binding and isolation chain

1. The host runner creates and uploads the bundle, helper, and remote runner.
2. The remote runner rejects pre-existing isolation roots.
3. It clones the bundle, detaches to `ba3b50e...`, verifies `HEAD` and a clean worktree.
4. It imports the adapter from the cloned `ba3b50e` worktree without patching it.
5. It constructs `ExecutionRequest` with the adapter-owned
   `OFFICIAL_D13E_TESTSET_SHA256 = 9740c00f4a9d91471bec8e6fa8aeeeb52f890f8680d83f740a84db2b1701a44b`
   and calls `validate_execution_request()` separately for Safety and Forget.
6. It calls the real dispatchers, then the private canonical writer
   `_write_raw_records()` after all 17 receipts exist.
7. It never reads Gold, thresholds, or Runner results, and never writes seals.

The public `dispatch_and_write_canonical()` remains fail-closed. This run used
the controlled remote orchestration path around that gate while retaining the
frozen adapter validation, real dispatchers, and private canonical writer.

## Dataset identity correction

The executed Dataset is the LF-byte blob at tested commit `ba3b50e...` and
hashes to `9740c00f...`. The VM preflight independently recorded
`sha256sum` output `9740c00f...` for the cloned Dataset. The initial evidence
commit `44f98bd...` copied Windows-checkout CRLF mirrors (Dataset `036954...`,
Gold `2e8ed9...`, Thresholds `9d70a7...`) because `core.autocrlf=true`. On
2026-09-08 the committed manifest/attestation registrations and evidence-root
mirror bytes were corrected to the exact `ba3b50e` blobs. Canonical raw files,
dispatch receipts, execution logs, and execution summary hashes were not
modified.
