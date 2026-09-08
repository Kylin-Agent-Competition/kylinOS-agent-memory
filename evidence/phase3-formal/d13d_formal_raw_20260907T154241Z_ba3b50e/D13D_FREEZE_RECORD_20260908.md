# D13D Phase 3 formal closure freeze record

Date: 2026-09-08

## Frozen decision

`D13D_FROZEN = YES`

This record registers the completed D13D Phase 3 formal closure. It does not
change the frozen evidence root, `SHA256SUMS`, or `evidence_index.yaml`. The
D13E formal evaluation report was produced on the frozen Kylin VM and then
copied back to the evidence root.

## Final identities

| Item | Value |
| --- | --- |
| tested_commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` |
| Environment | `d13d-phase3-formal@Kylin-D14D-clean-vdi-20260906:d14d-clean-base-20260907-r4` |
| Dataset SHA-256 | `9740c00f4a9d91471bec8e6fa8aeeeb52f890f8680d83f740a84db2b1701a44b` |
| Gold SHA-256 | `aeea9beab5d25461083bb693424014a813cd91bae6b0d7b60443f817f33c6be0` |
| Thresholds SHA-256 | `561034df97ee5c73675784a40b18726c51f3ff1120022ad04f2c66b0366c7ff9` |
| Formal manifest SHA-256 | `2dc0b9557fe7927756acd77218c3a1b7cc33c46218a14c9f831d2bb01f2b05b5` |
| Formal Runner SHA-256 | `297d534a4c1a4a3009942cc90a7614dc17eaec5843656d9b50ba601028a3036f` |
| Attestation SHA-256 | `2407d92e7b4ea4b237fdf7ba10960b57c943efe2b5df70e49295b43ade316c8d` |

## Evidence root

`evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/evidence`

The root contains 17/17 dispatch receipts, four canonical raw JSONL files, the
dual seals, and the formal evaluation report. The pre-existing `SHA256SUMS`
and `evidence_index.yaml` were intentionally left unchanged; the freeze state
is recorded here.

## Dual seals and trust root

### D13E Review Seal

- Reviewer: `Ducknesses` (Track D)
- Key ID: `d13e-review-rd-20260908-v1`
- Public key anchor: `a107ee92d7acb4f8fac7fe0b4cf393a68631d5a85d6aa45d99f24eb86eeb6286`
- Canonical JSON SHA-256: `b4822ec7f223b3fbee1365f2d8ff6df81e609a4ef2590c8346e51d04e426ecab`
- Signature SHA-256: `bb93764a498389df2f5c518026f294df1b9548e65d19d87f7ec865f49ecd9100`

### D13D Execution Seal

- Execution Reviewer: `lovezy0730-create`
- Approval reference: `https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/165#pullrequestreview-5137833119`
- Key ID: `d13d-execution-lovezy0730-20260908-v1`
- Public key anchor: `bbba93c041746231e203237995ae7e763ef584e912d4ad2467e8500edbf2b406`
- Canonical JSON SHA-256: `ad84ad3a748d1b883b69cb89bf5dad46d5a508062894b948c85668b2ac9b02e0`
- Signature SHA-256: `7ff05d6fe304a55cf1844ad028b56ad82b5a0c3bcc52b9901c6245790cf8717c`

Both seals were independently verified. The frozen VM trust root is installed
at `/etc/kylin-memory/trust`; its `D13E_TRUST_ROOTS_V1.json` SHA-256 is
`cdd22c5c62e3de592bddca62f018a8c7e293b0144c9bda44c7c10573bad99d6e`. The
installation record is:

`evidence/phase3-prep/d13d_trust_root_install_20260908/`

Private keys remain outside the repository, evidence root, CI, VM, and chat.

## Runner Gate 0-10

The formal Runner was executed offline on the frozen Kylin VM with:

```bash
python3 run_d13e_formal_eval.py \
  --bundle evidence/bundle.json \
  --review-seal evidence/D13E_REVIEW_SEAL_V1.json \
  --d13d-seal evidence/D13D_EXECUTION_SEAL_V1.json \
  --output evidence/D13E_FORMAL_REPORT_V1.json
```

Result: `EXIT=0`.

| Metric | Result |
| --- | --- |
| Preference | PASS, accuracy `1.0` |
| Conflict | PASS, accuracy `1.0` |
| Safety | PASS, violations `0` |
| Forget | PASS, violations `0` |

Formal report SHA-256:

`dee80d5044c2194b79f13e7185b39f0162c63468f7a47b86799a1abb23c489ee`

## Closure effect

The final tested commit for the D13D frozen baseline is therefore:

`ba3b50e1bdeea185bca9daee9d1d45958f62a636`

This closure does not freeze the D14A final package. The D14A package and
formal hash remain `NOT_FROZEN` until their separate final package closure is
completed. It also does not by itself declare `L3_READY`.
