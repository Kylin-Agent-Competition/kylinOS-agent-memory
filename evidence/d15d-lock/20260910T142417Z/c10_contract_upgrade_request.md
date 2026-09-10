# D15D C10 contract upgrade request

Run ID: `20260910T142417Z`

Status: `DRAFT_REQUEST_PENDING_D_REVIEWER`

## Request

D15D requests D Reviewer authorization to close D14A contract section 6bis
using the D14D formal G0 identities below. This document is not a contract
upgrade, D Reviewer sign-off, or closure claim.

## Proposed identity record

| Component | Version | Path | SHA-256 |
|---|---|---|---|
| SDK canonical `.so` | `1.2.0.0-0k0.4` | `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0` | `028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48` |
| Runtime binary | `kylin-ai-runtime 1.2.0.4-0k0.1` | `/usr/bin/kylin-ai-runtime` | `b3f83fc90966394e7397979945f324a4691a208a1b944ed1c2488b20b296e225` |
| GTE ONNX model | `kylin-gte-base-model 1.0.0.1-0k0.9` | `/usr/share/kylin-ai/model-repository/embd_gte-base_uint8-text/1/gte-base-multilingual-model_QUInt8.onnx` | `cef0fc76165ee5bb4f3da5ab6b9b6e6fdfdd278d3077f2db2d4a6cde4d4c32b1` |

Source evidence:

- `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/dependency_identity.json`
- `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/raw/g0_baseline.log`
- `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/raw/g0_packages.log`

## Proposed contract transition

D Reviewer may authorize changing contract section 6bis from
`HANDOFF_REQUIRED` to a frozen identity record containing exactly the values
above and the D14D evidence root reference:

`evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e`

The authorization should explicitly state:

1. The D14D G0 evidence is accepted as the runtime/model frozen identity source.
2. The contract version increases from v4 to the next D Reviewer approved version.
3. D15D may consume the upgraded contract in `D15D_VERSION_MANIFEST.json`.

## Non-authority boundary

D15D does not sign this request, does not alter the frozen contract, and does
not declare runtime/model identity closure.
