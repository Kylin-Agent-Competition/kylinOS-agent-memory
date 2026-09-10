# D15D C10 contract closure record

Run ID: `20260910T142417Z`

## Authorization

On 2026-09-10, the human workspace owner acting as ReviewerD authorized
closure of the D14A contract section 6bis identity by recording:

> 我以ReviewerD身份授权contract使用D14D G0身份闭环

Stable repository authority reference:

- URL: <https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/175#issuecomment-5615523980>
- Comment ID: `5615523980`
- Account: `Ducknesses`

D15D did not self-authorize, self-sign as Reviewer E, or alter any production
code. Reviewer E sign-off remains pending.

## Accepted identity source

The accepted source is the D14D formal G0 evidence:

`evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/dependency_identity.json`

with raw evidence:

- `raw/g0_baseline.log`
- `raw/g0_packages.log`

The D14D evidence checksum file remains 23/23 OK.

## Frozen identities

| Component | Version | Path | SHA-256 |
|---|---|---|---|
| SDK canonical `.so` | `1.2.0.0-0k0.4` | `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0` | `028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48` |
| Runtime binary | `kylin-ai-runtime 1.2.0.4-0k0.1` | `/usr/bin/kylin-ai-runtime` | `b3f83fc90966394e7397979945f324a4691a208a1b944ed1c2488b20b296e225` |
| GTE ONNX model | `kylin-gte-base-model 1.0.0.1-0k0.9` | `/usr/share/kylin-ai/model-repository/embd_gte-base_uint8-text/1/gte-base-multilingual-model_QUInt8.onnx` | `cef0fc76165ee5bb4f3da5ab6b9b6e6fdfdd278d3077f2db2d4a6cde4d4c32b1` |

The D14A contract content was upgraded from FROZEN v4 to PROPOSED v5 solely to
record this external dependency identity in section 6bis. The ReviewerD
authorization binds the G0 identity and section 6bis content, but Reviewer E
co-signature is still required before calling v5 a FROZEN final state. This
does not make D14D `release_ready=true` or `production_ready=true`, and does
not replace Reviewer E sign-off.
