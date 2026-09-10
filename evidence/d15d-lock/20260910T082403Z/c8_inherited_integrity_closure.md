# D15D C8 rework - inherited frozen-tar integrity

Run ID: `20260910T082403Z`

## Closure rule

Runbook C8 now explicitly allows `PASS_INHERITED_FROZEN_TAR_IDENTITY` when:

1. the local checksum run reaches the exact tar;
2. its SHA-256 equals the D14D G2-verified frozen tar;
3. all regular files return OK;
4. every failed item is one of the three package symlinks that cannot be
   opened in WSL because `/usr/bin/python3.12` is absent; and
5. the package was not rebuilt or modified.

Any regular-file mismatch, missing file, extra file, or provenance-labeled
rebuild remains a hard C8 failure.

## Binding

| Object | SHA-256 | Binding |
|---|---|---|
| Original tar | `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401` | D14D frozen tar identity |
| D14D G2 verification | `SHA_VERIFY_RC=0` / integrity Gate PASS | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e` |
| Local checksum run | exit 1; 3357 OK; 3 symlink open/read failures | WSL environment limitation only |

## Result

`PASS_INHERITED_FROZEN_TAR_IDENTITY`

This does not convert WSL into Kylin VM evidence and does not upgrade
`release_ready` or `production_ready`. It closes the local byte/manifest
consistency semantics by inheriting the already completed D14D G2 verification
for the same immutable tar bytes.
