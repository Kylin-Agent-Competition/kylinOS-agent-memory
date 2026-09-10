# D15D Round 2 rework evidence

Run ID: `20260910T090314Z`

## Scope

- BLOCKER-1: synchronized the current D14A contract package/provenance identity to
  the D14D formal evidence root `d14d_20260907T141000Z_ba3b50e`.
- MEDIUM-1: synchronized D15D TaskCard runtime/model state and G-D1 frozen-tar
  consumption semantics.
- BLOCKER-2: marked the existing PR-author authorization as not valid for
  independent ReviewerD review. A non-author ReviewerD record is still pending.

## Current identity

| Field | Value | Source |
|---|---|---|
| release / source / tested commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` | D14D `summary.json`, `package_build_identity.json`, D15D manifest |
| evidence commit | `ec7a66b3e52f8d76b156300d375467290fdc42b6` | PR #165 merge commit containing D14D evidence root |
| frozen tar SHA-256 | `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401` | D14D formal frozen tar |
| package manifest SHA-256 | `76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0` | D14D formal evidence |
| SHA256SUMS SHA-256 | `8540cd1dc2b8c743bc466cd89f435e09940ddc5e5df842cacb9367021eddcf67` | D14D formal evidence |

## Verification

Command:

```powershell
C:\Users\jackb\AppData\Local\Programs\Python\Python313\python.exe -m pytest -q docs/day14/test_d14a_release_provenance.py docs/day15/test_d15a_rc_lock_matrix.py
```

Result: `38 passed in 0.33s`.

This is a Windows local L0/L1 guard run. Packaging/release tests were not run
locally and are not claimed here. CI remains the canonical packaging test
environment.

## Authority boundary

The existing GitHub comment `5615523980` was posted by `Ducknesses`, who is
also PR #175 author. It therefore does not satisfy author/reviewer separation.
The contract status is `PROPOSED v5 / PENDING_INDEPENDENT_D_REVIEW_AND_E_SIGN`.
Reviewer E sign-off remains pending.
