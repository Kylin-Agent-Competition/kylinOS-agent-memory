# D15D evidence root semantics

This root is the authoritative D15D clean-tar VM release-binding evidence for
release commit `4a6323fb3a8c73e0b15f1f3629d28dfc12071541` and package identity
`974c2584a08bc2ae5277a8526ce3c5dbd711bc0d54c9844e99d658892cca9f28`.

It deliberately does **not** claim to be a new D14D formal G0-G9 L3 evidence
root.  The historical D14D root remains:

`evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e`

and is `HISTORICAL_PASS_AT_ba3b50e / NOT_SUFFICIENT_FOR_NEW_RELEASE`.  Its G0
host identity is retained as a reference input only; it is not represented as a
current-release G0-G9 rerun.

Under the TaskCard G-D4 alternative path, this root closes the current release
binding because it records the clean detached rebuild, package identity, C3-C6
blob consistency, C8 full package integrity, and clean-tar VM smoke PASS in a
machine-readable root with `summary.json`, `gate_matrix.json`,
`evidence_index.json`, and `checksums.txt`.

`checksums.txt` covers every indexed file except itself, so it also verifies
`evidence_index.json`.

## Mixed-run selection

The initial smoke attempts exposed pyc contamination and a long-running service.
Their logs are preserved unchanged.  The authoritative smoke result is:

`d15d_smoke_clean_tar_nbc2_4a6323f_20260910T205300Z`

That run used a fresh extraction of the unchanged `4a6323f-r2` tar with
`PYTHONDONTWRITEBYTECODE=1`, reported `VM_TEST_EXIT=0`, and recorded zero
`runtime/app` `.pyc` files and `__pycache__` directories.  No failed test was
deleted, weakened, or rewritten.  `summary.json` records this selection
relation machine-readably.
