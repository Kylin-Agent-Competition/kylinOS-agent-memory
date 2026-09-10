# D15D rework - local verification

Run ID: `20260910T082403Z`

## Repository checks

```text
git diff --check
exit code: 0

D15A lock matrix + D14A provenance guard
python -m pytest docs/day15/test_d15a_rc_lock_matrix.py docs/day14/test_d14a_release_provenance.py -q
37 passed
```

The packaging/runtime tests were not rerun on Windows because they are
WSL-oriented and the local WSL service returned `E_ACCESSDENIED` during this
rework session. No packaging script or production runtime file was changed by
the rework; the existing CI packaging job remains the authoritative check for
those files.

## Evidence checksums

The rework-root `checksums.txt` covers all sibling evidence files except
`checksums.txt` itself.
