# D15E Submission Materials Draft (as-of 2026-09-11)

> This file is a documentation-only E15-1/E15-4/E15-5 drafting baseline.
> It records current repository facts and keeps every submission-facing item
> `NOT_FROZEN` until its upstream prerequisite closes and a designated reviewer
> accepts the result. It does not execute L2/L3, create runtime evidence,
> replace `docs/day15/10_d15e_final_submission_lock_matrix_20260909.md`,
> or trigger a final submission decision.

D15E_PHASE0_PREPARATION=READY
D15E_FINAL_SUBMISSION_LOCK=WAITING_PREREQ
D15E_FINAL_SUBMISSION_LOCK_DECLARED=false
D15E_SIGNOFF_STATUS=BLOCKED

## 1. Scope and snapshot

| Field | Value |
|---|---|
| as-of | 2026-09-11 |
| working branch | `docs/d14b-vector-cli-p0-packet-r3` |
| working branch base | `657dbb9d18c7cb863924380c7dfac674c8ca36d1` |
| current main HEAD | `657dbb9d18c7cb863924380c7dfac674c8ca36d1` |
| runtime scope | `RUNTIME_NOT_REQUIRED` for this draft |
| source matrix | `docs/day15/10_d15e_final_submission_lock_matrix_20260909.md` |
| D-track SSOT | `docs/D_TRACK_STATUS.md` |

The working HEAD is a docs-only continuation after the D15D closeout. It is not
the D15D release commit and must not be presented as one. The active release
identity remains independently recorded below.

## 2. Current identity and boundaries

| Item | Value | Boundary |
|---|---|---|
| D15D active release commit | `4a6323fb3a8c73e0b15f1f3629d28dfc12071541` | Release identity only; not current-main identity |
| D15D package | `kylin-memory-a-d14a 0.1.0-d14a` | Package identity only |
| package tar SHA-256 | `974c2584a08bc2ae5277a8526ce3c5dbd711bc0d54c9844e99d658892cca9f28` | Must not be conflated with manifest, SHA256SUMS, source, or evidence hashes |
| package manifest SHA-256 | `4b42d9281e1fac269bc0e0ba43d831317424fc6200a751380ebf985241124ec4` | Package manifest identity |
| package SHA256SUMS SHA-256 | `9d1ac01fab8a2a876b97ffc5ffd375085661c78029b03a35c6984b7c91f4d9f4` | Checksum-file identity |
| D15D evidence root | `evidence/d15d-lock/20260910T205300Z` | Clean-tar VM release binding; not a D14D G0-G9 replacement |
| historical tested commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` | Historical D13D/D14A/D14D scope only |

D15D status is `SIGNED_PREPARED / MERGED / LOCKED` for its release-identity
scope. It does not establish `release_ready=true` or `production_ready=true`.
The D14D boundary remains `L3_READY=true`, `release_ready=false`, and
`production_ready=false`.

Current upstream blockers are explicit:

- D14B formal capture remains `BLOCKED`. The original frozen package bytes were
  located and the formal preflight passed, but the capture stage is now
  fail-closed on a pending `vector_bridge_cli` refreeze decision.
- D15B remains `BLOCKED_NOT_COMPLETE`; its inputs, metrics, and manifest are not frozen.
- D14C formal runtime is `BLOCKED`. RC3 provides real Host Chat usability
  evidence, but the exact package, binary, model, and runtime identity fields
  required by P0-3 remain incomplete.
- D15A A15-2 remains `BLOCKED`; A15-1/A15-3 still require D adjudication against the active D15D identity.
- D14E final acceptance remains unsigned.

## 3. E15-1 technical and user documentation outline

### 3.1 Technical-document scope

The technical submission narrative should be organized around the implemented
architecture and verified boundaries, not around aspirational features:

1. **System overview**: a local preference and knowledge memory service for the
   Kylin V11 desktop AI Assistant, isolated from chat-origin text storage.
2. **Architecture**: Memory Service in Python with asyncio and Pydantic v2;
   SQLite as the structured source of truth; FTS5 and Vector as retrieval
   indexes; application-layer fusion rather than a delivery claim for native runtime RRF.
3. **IPC and lifecycle**: Unix Domain Socket with length-prefixed JSON;
   systemd user-scoped deployment; migration before production start; restart,
   rollback, and reinstall behavior described only to the extent covered by the
   cited evidence.
4. **Data and retrieval design**: write-path separation of original user text
   and model-request memory context; asynchronous indexing; deletion and
   lifecycle behavior kept as pending formal validation while D14B is blocked.
5. **Release identity**: the active D15D package and evidence root; explicit
   distinction between release identity, current main, historical tested commit,
   and evidence hashes.
6. **Security and privacy**: local service boundary, user isolation, sensitive
   write controls, retrieval output filtering, and no plaintext-secret policy.
   No absolute security claim is permitted.
7. **Testing and evidence hierarchy**: L0/L1 local tests, L2/L3 Kylin VM
   evidence, formal evidence roots, and the rule that preparation or mock results
   cannot be promoted to runtime/formal results.

### 3.2 User-manual scope

The user manual should describe the delivered package and observable service
operations only:

1. Intended environment: Kylin V11 x86_64 with the declared SDK/runtime/model
   prerequisites.
2. Package layout and identity verification using the release manifest and
   checksums.
3. Service installation, status inspection, restart, rollback, and uninstall at
   the level supported by the D15D clean-tar smoke evidence.
4. Local storage and configuration locations.
5. Failure behavior: service absence or timeout must not be described as
   producing synthetic memory content; behavior must remain fail-closed.
6. Known limitations that follow from blocked D14B/D14C work.

Neither document is frozen here. The wording must be reviewed against the final
D14B/D14C/D15A/D15B facts before any submission-facing version is issued.

## 4. E15-4 submission inventory draft

| Item | Current state | Freeze state | Identity/evidence anchor |
|---|---|---|---|
| Active release package | Recorded and checksum-verified in D15D | Package identity may be referenced as D15D-locked, not as final release approval | `evidence/d15d-lock/20260910T205300Z/submission_inventory.json` |
| Release manifest | Machine-readable v2 manifest present | Not a final submission manifest | `docs/day15/D15D_VERSION_MANIFEST.json` |
| Technical document | Draft outline only | `NOT_FROZEN` | This file, E15-1 |
| User manual | Draft outline only | `NOT_FROZEN` | This file, E15-1 |
| Functional test report | `PENDING_UPSTREAM` | `NOT_FROZEN` | Requires D14B formal evidence |
| Effectiveness report | `PENDING_UPSTREAM` | `NOT_FROZEN` | Requires D14B formal evidence |
| Real-case material | `PENDING_UPSTREAM` | `NOT_FROZEN` | Requires D14C formal evidence |
| Four core metric conclusions | `BLOCKED` | `NOT_FROZEN` | Requires D14B/D14C formal evidence and permitted mapping |
| Demo/video material | `PENDING_UPSTREAM` | `NOT_FROZEN` | Must be checked after D14B/D14C facts are available |
| Submission inventory / README | Draft inventory only | `NOT_FROZEN` | This file, E15-4 |
| Claim-to-evidence mapping | Draft mapping only | `NOT_FROZEN` | This file, E15-5 |

The D15D package inventory records 3,351 manifest entries with a full checksum
pass and no unexpected manifest/tar difference. That fact applies to package
integrity only; it does not turn pending reports into delivered material.

## 5. E15-5 claim-to-evidence mapping draft

Every external claim must retain its row identity and restrictions. Rows marked
not allowed may be described only as pending or blocked.

| Claim | Evidence / status | Allowed as final competition fact | Constraint |
|---|---|---|---|
| D15D active release identity is locked and package integrity is verified | `evidence/d15d-lock/20260910T205300Z`; package hashes above; 3351/3351 checksum pass | Allowed only for release-identity/package-integrity scope | Not release readiness, production readiness, or final submission readiness |
| D15D clean-tar VM release binding smoke completed | D15D evidence root, clean detached rebuild, install/migration/start/real SDK verify/restart/rollback scope | Allowed only with the cited run scope | Does not replace D14D G0-G9 and does not close D14B/D14C |
| D13D formal business-domain execution closed | `evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/evidence/D13E_FORMAL_REPORT_V1.json`; report SHA-256 `dee80d5044c2194b79f13e7185b39f0162c63468f7a47b86799a1abb23c489ee` | Allowed only with frozen D13D scope, small sample sizes, dataset/threshold identity, and historical tested commit | No unqualified whole-system or safety claim |
| D14D clean Kylin VM L3 evidence exists | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e`; historical tested commit `ba3b50e...` | Allowed only as historical D14D evidence with `L3_READY=true`, `release_ready=false`, `production_ready=false` | G7 is `NOT_RUN/N-A`; G8 remains waived; not sufficient for new release identity |
| Day14 retrieval/index lifecycle formal regression is complete | D14B formal evidence absent; package preflight passed, but capture is blocked by a pending `vector_bridge_cli` refreeze decision | Not allowed | Preparation, substitute VM, or rebuild results cannot be promoted |
| Official AI Assistant production E2E is complete | D14C formal evidence absent; RC3 proves chat usability, but exact package/binary/model/runtime identity is incomplete | Not allowed | Test profile, mock, IPC-only, or historical preparation evidence cannot substitute |
| D14E business/security acceptance is complete | D14E final acceptance unsigned | Not allowed | Requires independent human signoff |
| Demo narrative exactly matches verified behavior | Final demo artifacts not reconciled | Not allowed | Recheck every C row before use |

## 6. Overclaim checklist

Before any draft becomes a submission-facing version:

1. Separate current main HEAD, D15D release commit, historical tested commit,
   package hashes, and evidence/report hashes.
2. Keep `release_ready=false` and `production_ready=false` unless a later
   authoritative decision explicitly changes them.
3. Do not convert D14B preparation, D14C preparation, mock data, or local
   L0/L1 results into L2/L3 or formal results.
4. Keep blocked reports, metrics, cases, and demo claims as pending; do not
   deliver them as complete.
5. Recheck every cited evidence path and checksum on the final submission day.
6. Obtain independent D/E review and D14E signoff before final acceptance.

## 7. Draft disposition

This draft is usable as an internal consolidation baseline. It does not close
E15-1, E15-4, or E15-5 and does not alter the guarded D15E matrix. Those items
remain `WAITING_PREREQ` until upstream facts and designated review close them.
