# D14/D15 P0 Unblock Request Packet (as-of 2026-09-11)

> Nature: review/request preparation only. This packet does not authorize a
> formal run, does not create evidence, and does not declare any upstream
> track complete or unlocked.

## Status Lines

D14B_FORMAL_L3=NOT_RUN/UNVERIFIED
D15A_A15_2=BLOCKED
D14C_FORMAL_L3=BLOCKED
D15E_FINAL_SUBMISSION_LOCK=WAITING_PREREQ
D15E_FINAL_SUBMISSION_LOCK_DECLARED=false
D15E_SIGNOFF_STATUS=BLOCKED

## Snapshot

| Field | Value |
| --- | --- |
| as-of | 2026-09-11 |
| branch base at scan time | `e62d525e3b7baf2bd4cd18ad8c2128a10aba8a96` |
| scan-time main head | `657dbb9d18c7cb863924380c7dfac674c8ca36d1` |
| frozen tested commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` |
| D14B control handoff | `release/handoff/d13d-handoff.json` |
| D14D clean-VM handoff | `release/handoff/d14d-handoff.json` |
| D14B capture handoff | `release/handoff/d14b-capture-handoff.json` |
| current rebuilt tar | `release/packages/kylin-memory-a-d14a-0.1.0-d14a-rebuilt-ba3b50e.tar.gz` |
| rebuilt tar SHA-256 | `de4050ee22d3c70f67c3cbf314ada1a76ac7d8d0527d7ba397477122553a30d8` |

The rebuilt tar is a provenance-labeled rebuild. It is not a byte-level
recovery of the original frozen tar and must not be substituted for it
without an explicit authoritative refreeze decision.

## Minimum P0 Input Set

The most useful four-input set, ordered by dependency and closure value, is:

1. **D14B package identity input** — authority acceptance of the located
   original frozen tar bytes, or an authoritative package refreeze decision.
2. **D14B vector CLI identity input** — either the original
   `vector_bridge_cli` bytes or an authoritative provenance-labeled rebuild
   refreeze decision.
3. **D14C Host Chat LLM input** — a usable real Host Chat LLM with complete
   package, binary, model, and runtime identity for the exact round.
4. **D15A A15-2 performance scope input** — approval of a package-only
   performance runner with explicit thresholds, or a formal scope ruling.

This is an executor recommendation for review sequencing. It is not a formal
authority approval, does not self-approve any refreeze, and does not change
any Gate ownership.

## P0-1: D14B Package Input

The original frozen package bytes have been located and their SHA-256 has been
re-verified. The remaining decision is therefore authority acceptance of that
located original identity, not recovery of missing bytes.

Provide exactly one of the following:

1. Accept the located original frozen package bytes:
   `kylin-memory-a-d14a-0.1.0-d14a.tar.gz`
2. An authoritative refreeze decision that identifies a new formal package
   identity and explicitly authorizes its use for D14B Formal L3.

Required verification for option 1:

| Item | Required value |
| --- | --- |
| Package name | `kylin-memory-a-d14a` |
| Package version | `0.1.0-d14a` |
| Source commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` |
| Original tar SHA-256 | `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401` |
| Original manifest SHA-256 | `76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0` |

After the input is accepted, run the fail-closed preflight on a new local
path without creating an evidence root:

```bash
python3 scripts/run_d14b_preflight.py \
  --expected-tested-commit ba3b50e1bdeea185bca9daee9d1d45958f62a636 \
  --expected-control-head <approved-control-head> \
  --d13d-handoff release/handoff/d13d-handoff.json \
  --d14d-handoff release/handoff/d14d-handoff.json \
  --package-manifest <approved-package-manifest> \
  --tested-repo-root <exact-clean-tested-checkout> \
  --control-root <reviewed-tooling-checkout> \
  --evidence-root <new-unused-root> \
  --capture-handoff release/handoff/d14b-capture-handoff.json \
  --package-tar <approved-frozen-tar> \
  --actual-package-manifest <approved-frozen-manifest>
```

A zero exit authorizes the next formal-run step only. It is not a D14B
result and does not permit reuse of an existing evidence root.

## P0-2: D14B Vector CLI Identity Input

After the package input was located and formal preflight reached the capture
stage, the pinned `vector_bridge_cli` binary identity was not recoverable on
the approved clean VM. The separate
`docs/day15/14_d14b_vector_cli_refreeze_request_20260911.md` remains the
authoritative refreeze request. It requests approval for a provenance-labeled
rebuild only; approval must be recorded there before that rebuild identity is
substituted.

Provide exactly one of the following:

1. The original `vector_bridge_cli` bytes satisfying the pinned SHA-256.
2. An authoritative refreeze decision approving the recorded rebuild SHA-256
   for D14B vector capture.

Either decision must be followed by a new preflight using a new evidence root.
This does not reuse or upgrade the existing preflight evidence root.

## P0-3: D14C Host Chat LLM Input

The current Host Chat LLM identity audit is recorded in
`docs/day15/15_d14c_host_llm_identity_audit_20260911.md`; it keeps D14C
blocked until the missing package, binary, model, and runtime identity is
supplied for the exact RC3 round.

Provide a usable real Host Chat LLM and record, for the exact deployed
artifact:

| Item | Required evidence |
| --- | --- |
| Package identity | package name/version and source provenance |
| Binary identity | deployed binary path and SHA-256 |
| Model/runtime version | recorded runtime and model version |
| Usability evidence | a real Host Chat round reaches the model runtime |

This input is necessary but not sufficient for D14C. Trusted host identity,
production routes, MemoryContext freeze, and formal clean-VM runtime capture
remain separate gates.

## P0-4: D15A A15-2 Scope Input

The D owner must choose one:

1. Approve a package-only performance runner and explicit thresholds.
2. Issue a formal scope ruling for A15-2.

If the selected path produces or relies on performance conclusions, E must
perform supplemental review. This packet does not propose thresholds and
does not treat historical substitute measurements as a valid baseline.

## Required Response Discipline

1. Record each decision with authority, time, and exact input identity.
2. Do not upgrade preparation, substitute, or rebuilt results into formal
   D14B/D14C results.
3. Keep `release_ready=false` and `production_ready=false` boundaries intact.
4. Refresh `docs/D_TRACK_STATUS.md` only after an actual upstream closure.
