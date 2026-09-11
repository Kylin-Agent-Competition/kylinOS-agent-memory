# D14B Vector CLI Binary Identity Refreeze Request

Date: 2026-09-11
Status: `PENDING_RELEASE_OWNER_OR_REVIEWER_D`
Classification: `P0_ADJUDICATION_REQUEST`
Affected workflow: D14B Formal L3 Vector capture

## Request

D14B formal capture is fail-closed because the pinned `vector_bridge_cli`
identity cannot be satisfied on the approved clean VM. The request is limited to
authorizing a provenance-labeled rebuild of that CLI binary as the D14B vector
capture input. No IPC, schema, DB, error-code, runner, query, threshold, or
result semantics are proposed for change.

If approved:

1. Create a new D14B capture handoff derived from the reviewed
   `d14b-capture-handoff.json`, changing only
   `source_bindings.vector.vector_cli_sha256` to the approved rebuild SHA.
2. Record the approval decision, approver identity, UTC time, and provenance
   details in that handoff.
3. Run `run_d14b_preflight.py` again using a new exclusive evidence root.
4. Continue only if the new preflight PASSes. The existing
   `d14b_20260911T091924Z_ba3b50e` preflight remains an isolated preflight
   artifact and must not be reused, overwritten, or upgraded into formal
   evidence.

If rejected, D14B remains `BLOCKED / NOT_RUN / UNVERIFIED`; no rebuild may be
substituted for the missing original identity.

## Identity Evidence

| Item | Value |
|---|---|
| Tested commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` |
| Control head | `306c15ed8e1bb88378c849e83119828afd35083d` |
| Existing preflight | `evidence/l3-kylin-vm/d14b_20260911T091924Z_ba3b50e/provenance/preflight.json` |
| Existing preflight status | `PASS` for identity/package/worktree gates; it does not constitute formal runtime |
| Original pinned CLI SHA-256 | `004876742624e4c7d32d65aa7b0f14280e9faafa077eca9a7035a7caa375e489` |
| Current rebuild CLI SHA-256 | `92ddec480b6b21b9aaffe35ded3207b0b0a02e251a77cef9d8b96a6c5d91a235` |
| Rebuild Build ID | `d22504858d9799c1bf9f3cc98a16c9d4c1a17749` |
| CLI source SHA-256 | `5f0e1310023b1fabc50df5d7a591e4c6f427892a87977706daea565a148d54d9` |
| Header SHA-256 | `12c6f819adcb5ad76f28da2d355b2fe1eac86abf8a66975cef160de1878f8447` |
| Compiler | `g++ (openKylin 12.3.0-1ok3k0.1) 12.3.0` |
| VM | `Kylin-D14D-clean-vdi-20260906` / `70ca1ea3-c27e-483d-aaba-0cac7dc5c77c` |
| Snapshot | `d14d-clean-base-20260907-r4` / `6dc9468e-36a8-41b3-b7c9-6115c7b8fc56` |
| Vector client package | `libkysdk-vector-engine-client:amd64 1.2.0.0-0k1.1` |
| Vector engine package | `kylin-ai-vector-engine 1.2.0.1-0k1.0` |

The VM path of the rebuild is
`/home/kylin-agent/d13d-g6-prep/vector_bridge_cli`. Its header dependency is
`/home/kylin-agent/.local/d8b-sdk/sdk-compat-0k1.1/usr/include/kysdk-vector-engine-client/Database.h`.
The source bytes are byte-identical to
`tests/vector-engine/vector_bridge_cli.cpp` in the reviewed control checkout.

## Why Original Identity Cannot Be Recovered

- The approved clean snapshot r4 did not contain the G6 preparation directory;
  the current CLI was created during today's preparation rebuild.
- The original pinned binary was not found in VM snapshots, local archives,
  evidence packages, or the released D14A package.
- No original build command, build log, script, or DWARF build provenance was
  found in the VM filesystem, shell history, local workspace, PR #160 evidence,
  or archived artifacts.
- Header and source identities match the D13D G6 provenance, but compile/link
  invocation details were not preserved. Therefore byte-level reconstruction is
  not available and cannot be honestly claimed.

## Boundary

This request does not authorize:

- mutation of the existing preflight evidence root;
- reuse of the failed or superseded capture inputs;
- relabeling the rebuild as the original frozen binary;
- upgrade of this preparation evidence into `D14B_FORMAL_L3=PASS`;
- change to `release_ready=true` or `production_ready=true`.

Approver must be Release Owner or Reviewer D. The executor is not authorized to
self-approve.
