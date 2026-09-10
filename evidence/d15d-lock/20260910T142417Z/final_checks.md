# D15D final local checks

Run ID: `20260910T142417Z`

## Guard regression

Command:

```bash
python3 -m pytest \
  docs/day15/test_d15a_rc_lock_matrix.py \
  packaging/release/test_d14a_package_integrity.py \
  packaging/release/test_d14a_relocatable_runtime.py \
  packaging/release/test_d14a_transactional_rollback.py \
  packaging/release/test_d14a_verify_smoke.py \
  docs/day14/test_d14a_release_provenance.py -q
```

Result:

```text
93 passed in 35.89s
```

The run used explicit `GIT_DIR` / `GIT_WORK_TREE` only because the Windows
worktree file points to a Windows-style parent Git path that WSL cannot parse
by default. This is an execution environment note, not a masking step.

## JSON validation

Commands:

```bash
python3 -m json.tool docs/day15/D15D_VERSION_MANIFEST.json >/dev/null
python3 -m json.tool evidence/d15d-lock/20260910T142417Z/summary.json >/dev/null
```

Result: both exited 0.

## Whitespace check

Command:

```bash
git diff --check
```

Result: exit 0, no output.

## Evidence checksum verification

The run-local `checksums.txt` verified 11/11 listed files as OK, 0 failed. The
checksum file does not include its own hash.

## Script and unit blob assertions

The four package blobs and the four `ba3b50e1bdeea185bca9daee9d1d45958f62a636`
source blobs produced identical SHA-256 values:

| Package path | Source path | SHA-256 |
|---|---|---|
| `systemd/install.sh` | `packaging/release/systemd_install.sh` | `bce16242411929dbe2e3297a06de31e65d91c94a9ffc0638f5658eb73fa31cc7` |
| `systemd/uninstall.sh` | `packaging/release/systemd_uninstall.sh` | `e29d63ee11c44529fabeeeb87d164454ff2ea08e21ab33fce3b19ae061c00a33` |
| `systemd/verify.sh` | `packaging/release/systemd_verify.sh` | `b9a367900e748184cfed8e51ad3f7f4f0144bfa1ff095b97a538105c4ee48f20` |
| `systemd/kylin-memory.service` | `packaging/systemd/kylin-memory.service` | `cf8f76aab5da36dd5eaff6276a71f8307bf4511b1da135d2226af0402e120c28` |

## Boundary

These are local L0/L1 and byte-identity checks. They do not replace Kylin VM
runtime evidence, do not upgrade `release_ready` or `production_ready`, and do
not substitute for Reviewer E sign-off.
