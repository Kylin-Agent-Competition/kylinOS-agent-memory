# D13D trust-root installation audit record

Date: 2026-09-08

## Result

`INSTALLATION_AND_VERIFICATION = PASS`

The frozen VM trust root was installed at the exact fixed path
`/etc/kylin-memory/trust` before the formal Runner Gate 0-10 run.

## System facts

| Item | Value |
| --- | --- |
| VM environment | `Kylin-D14D-clean-vdi-20260906:d14d-clean-base-20260907-r4` |
| System path | `/etc/kylin-memory/trust` |
| Directory owner / mode | `root:root`, `0755` |
| Trust-file owner / mode | `root:root`, `0644` |
| Non-symlink Gate | `PASS` |
| Store JSON SHA-256 | `cdd22c5c62e3de592bddca62f018a8c7e293b0144c9bda44c7c10573bad99d6e` |

The installed trust-file set is:

1. `D13E_TRUST_ROOTS_V1.json`
2. `d13e-review-public.pem`
3. `d13d-execution-public.pem`

## Key anchors

| Role | Key ID | Public-key SHA-256 |
| --- | --- | --- |
| D13E Review | `d13e-review-rd-20260908-v1` | `a107ee92d7acb4f8fac7fe0b4cf393a68631d5a85d6aa45d99f24eb86eeb6286` |
| D13D Execution | `d13d-execution-lovezy0730-20260908-v1` | `bbba93c041746231e203237995ae7e763ef584e912d4ad2467e8500edbf2b406` |

## Boundary

- The repository copy in this directory contains only the trust-store JSON
  and this audit record.
- PEM files are intentionally not committed; the authoritative public PEMs
  live in the VM trust root.
- Private keys are outside the repository, evidence root, CI, VM, and chat.
- The formal Runner is bound to the exact system path above and to
  `scripts/run_d13e_formal_eval.py`, SHA-256
  `297d534a4c1a4a3009942cc90a7614dc17eaec5843656d9b50ba601028a3036f`.
