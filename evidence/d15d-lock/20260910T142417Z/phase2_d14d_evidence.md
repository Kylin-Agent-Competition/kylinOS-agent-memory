# D15D Phase 2 D14D evidence review

Run ID: `20260910T142417Z`

## Result

`BLOCKED` for final D15D lock. C11 evidence-root checks pass locally, but C10
does not satisfy the D15D final-lock condition because the frozen D14A contract
still records runtime/model identity as `HANDOFF_REQUIRED`.

## C11 - D14D evidence root

Evidence root:

`evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e`

Checked copy:

`E:\Kylin-memory-dev\pr160-rework\evidence\l3-kylin-vm\d14d_20260907T141000Z_ba3b50e`

- Evidence checksum verification: 23 total, 23 OK, 0 failed.
- `package_manifest.json` SHA-256:
  `76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0`
- `package_SHA256SUMS.txt` SHA-256:
  `8540cd1dc2b8c743bc466cd89f435e09940ddc5e5df842cacb9367021eddcf67`
- Package name: `kylin-memory-a-d14a`
- Package version: `0.1.0-d14a`
- Manifest `source_commit`:
  `ba3b50e1bdeea185bca9daee9d1d45958f62a636`
- Manifest file count: 3360.

D14D gate states:

| Gate | State |
|---|---|
| G0-G6 | PASS |
| G7 | `NOT_RUN / N-A` (D-09 arbitration) |
| G8 | `NOT_RUN` (D-10 waiver) |
| G9 | `READY_FOR_REVIEW` |

Boundary citation:

- `D_TRACK_STATUS.md` records D14D `L3_READY=true`,
  `release_ready=false`, and `production_ready=false`.
- The D14D evidence `summary.json` records `L3_READY=false` at its
  ready-for-review stage. This is a phase-boundary difference, not a change to
  the tested runtime result; the later SSOT reflects accepted D14D review.

## C10 - runtime/model identity

The D14D G0 evidence records these observed identities:

| Component | Identity | SHA-256 |
|---|---|---|
| SDK canonical `.so` | `1.2.0.0-0k0.4`, soname `libkysdk-coreai-embedding.so.1` | `028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48` |
| Runtime binary | `kylin-ai-runtime 1.2.0.4-0k0.1` | `b3f83fc90966394e7397979945f324a4691a208a1b944ed1c2488b20b296e225` |
| GTE ONNX model | `kylin-gte-base-model 1.0.0.1-0k0.9` | `cef0fc76165ee5bb4f3da5ab6b9b6e6fdfdd278d3077f2db2d4a6cde4d4c32b1` |

These are consumption-ready observations, but D15D cannot claim contract
closure. `docs/day14/00_d14a_release_package_contract.md` section 6bis remains
`HANDOFF_REQUIRED`; replacing or removing that state requires a D Reviewer
authorized contract upgrade and sign-off. D15D does not have that authority and
does not grant it here.

Consequently, the Phase 2 gate for creating a final version manifest is not
passed.
