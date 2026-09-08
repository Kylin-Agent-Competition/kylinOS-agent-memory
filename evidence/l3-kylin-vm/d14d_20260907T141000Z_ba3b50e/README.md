# D14D Formal L3 Evidence Root

- Evidence root: `d14d_20260907T141000Z_ba3b50e`
- Final tested commit: `ba3b50e1bdeea185bca9daee9d1d45958f62a636`
- Final package tar SHA-256: `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401`
- Formal run started at: `2026-09-07T14:10:51Z`

This root records the formal D14D L3 run after PR #160 merged. The clean
starting point was rebuilt as snapshot `d14d-clean-base-20260907-r4` because the
previously recorded r2 snapshot was not present in the current VirtualBox
registry. The r4 snapshot was created only after the fail-closed clean-state
gate reached `CLEAN_STATE_PASS` with all eight counts at zero. This deviation is
recorded explicitly rather than reusing a snapshot that no longer exists.

The run is not `L3_READY` until a non-author reviewer accepts this evidence. It
must not be described as production ready or release ready.
