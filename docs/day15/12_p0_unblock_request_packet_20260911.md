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
| scan-time main head | `afc701ec2ce269268508a278f5aa50fd3ddfc93c` |
| frozen tested commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` |
| D14B control handoff | `release/handoff/d13d-handoff.json` |
| D14D clean-VM handoff | `release/handoff/d14d-handoff.json` |
| D14B capture handoff | `release/handoff/d14b-capture-handoff.json` |
| current rebuilt tar | `release/packages/kylin-memory-a-d14a-0.1.0-d14a-rebuilt-ba3b50e.tar.gz` |
| rebuilt tar SHA-256 | `de4050ee22d3c70f67c3cbf314ada1a76ac7d8d0527d7ba397477122553a30d8` |

The rebuilt tar is a provenance-labeled rebuild. It is not a byte-level
recovery of the original frozen tar and must not be substituted for it
without an explicit authoritative refreeze decision.

## P0-1: D14B Package Input

Provide exactly one of the following:

1. The original frozen package bytes:
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

## P0-2: D15A A15-2 Scope Input

The D owner must choose one:

1. Approve a package-only performance runner and explicit thresholds.
2. Issue a formal scope ruling for A15-2.

If the selected path produces or relies on performance conclusions, E must
perform supplemental review. This packet does not propose thresholds and
does not treat historical substitute measurements as a valid baseline.

## P0-3: D14C Host Chat LLM Input

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

## Required Response Discipline

1. Record each decision with authority, time, and exact input identity.
2. Do not upgrade preparation, substitute, or rebuilt results into formal
   D14B/D14C results.
3. Keep `release_ready=false` and `production_ready=false` boundaries intact.
4. Refresh `docs/D_TRACK_STATUS.md` only after an actual upstream closure.
