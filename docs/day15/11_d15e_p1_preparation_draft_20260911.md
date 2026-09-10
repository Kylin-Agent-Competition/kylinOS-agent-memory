# D15E P1 Preparation Draft (as-of 2026-09-11)

> Nature: preparation draft only. This file does not declare D15E final
> submission lock, does not sign D14E final acceptance, and does not upgrade
> any blocked upstream result.

## Status Lines

D15E_P1_PREPARATION=READY_FOR_REVIEW
D15E_FINAL_SUBMISSION_LOCK=WAITING_PREREQ
D15E_FINAL_SUBMISSION_LOCK_DECLARED=false
D15E_SIGNOFF_STATUS=BLOCKED

## Snapshot

| Field | Value |
| --- | --- |
| as-of | 2026-09-11 |
| main head | `e62d525e3b7baf2bd4cd18ad8c2128a10aba8a96` |
| merged closeout | PR #178 |
| frozen tested commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` |
| package | `kylin-memory-a-d14a 0.1.0-d14a` |
| package tar SHA-256 | `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401` |
| package manifest SHA-256 | `76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0` |
| package SHA256SUMS SHA-256 | `8540cd1dc2b8c743bc466cd89f435e09940ddc5e5df842cacb9367021eddcf67` |

The main head is not the frozen tested commit. Package hashes and evidence
hashes are separate identities and must not be substituted for each other.

## P0 Inputs Still Required

1. D14B: original frozen tar bytes or an authoritative refreeze decision.
2. D15A: a package-only performance runner and thresholds, or a formal scope
   ruling for A15-2.
3. D14C: a usable real Host Chat LLM with recorded package, binary, version
   and SHA-256 identity.

No P0 ruling has been recorded in this draft. The corresponding upstream tracks
remain blocked and must not be treated as complete.

## E15 Drafting State

| Lock | Object | Status | Drafting state | Boundary |
| --- | --- | --- | --- | --- |
| E15-1 | Technical document and user-manual positioning | WAITING_PREREQ | Skeleton and positioning can be drafted | Not frozen and not approved |
| E15-2 | Functional test and effect verification report | BLOCKED_BY_D14B | No formal evidence root available | Preparation or substitute results do not replace D14B formal L3 |
| E15-3 | Real cases and four core metric conclusions | BLOCKED_BY_D14C | No formal evidence root available | D14C formal runtime remains blocked |
| E15-4 | Submission inventory and deliverable identity | WAITING_PREREQ | Inventory can be drafted | Not frozen |
| E15-5 | Claim-to-evidence mapping and overclaim final check | WAITING_PREREQ | Mapping can be drafted | Not frozen |
| E15-6 | Final submission position and signoff trigger | BLOCKED | Trigger list can be drafted | No final signoff |

## Submission Inventory Draft

| Deliverable | Status | Freeze state | Evidence boundary |
| --- | --- | --- | --- |
| Technical document | Draftable | NOT_FROZEN | Wait for E15-1 upstream review |
| User manual | Draftable | NOT_FROZEN | Wait for E15-1 upstream review |
| Functional test report | PENDING_UPSTREAM | NOT_FROZEN | Requires D14B formal evidence |
| Effect verification report | PENDING_UPSTREAM | NOT_FROZEN | Requires D14B formal evidence |
| Real case material | PENDING_UPSTREAM | NOT_FROZEN | Requires D14C formal evidence |
| Four core metric conclusions | BLOCKED | NOT_FROZEN | Requires formal upstream results |
| Demo video material | PENDING_UPSTREAM | NOT_FROZEN | Requires final D14B/D14C facts |
| Release package identity | PACKAGE_HASH_FROZEN | FROZEN | Identity only; not release readiness |
| Installation, upgrade and rollback narrative | PENDING_UPSTREAM | NOT_FROZEN | Requires D14B formal regression |
| Submission README | Draftable | NOT_FROZEN | Wait for E15-4 review |

## Claim Mapping Draft

| Claim | Current allowability | Required binding | Boundary |
| --- | --- | --- | --- |
| D13D formal execution closure is complete | Allowed, narrowly scoped | tested commit and evidence root | Do not extend to full-system performance |
| Preference, Conflict, Safety and Forget formal metrics meet their recorded thresholds | Allowed, narrowly scoped | report SHA, dataset and thresholds | Do not generalize beyond sample sizes |
| D14A package identity is frozen | Allowed, narrowly scoped | package hashes | Identity only, not release readiness |
| D14D clean Kylin L3 evidence is ready | Allowed, narrowly scoped | tested commit and evidence root | Keep release and production readiness false |
| D14B retrieval and index lifecycle release regression passes | Not allowed | formal evidence root not present | Preparation and substitute runs are not formal L3 |
| Official AI Assistant production E2E passes | Not allowed | formal evidence root not present | Real Host LLM and D approvals are missing |
| D14E final acceptance is signed | Not allowed | no signoff | Human signoff has not occurred |
| Demo and narrative are consistent | Not allowed | final artifacts not complete | Compare only against formal evidence after closure |

## P1 Work Completed In This Draft

1. Refreshed the D15E preparation snapshot to current main `e62d525...`.
2. Recorded the three P0 inputs that still block formal execution.
3. Kept all formal and signoff locks separate from draft work.
4. Made the draft/inventory distinction explicit for every submission item.

## Verification Done For This Draft

1. `scripts/verify_repository_baseline.sh` returned zero on the LF checkout.
2. The Day14A / Day15 pytest set passed with 132 tests.
3. D15D `checksums.txt` verified all 31 listed files after restoring LF text
   checkout state. No evidence content was changed.

## Remaining Actions

1. Obtain the three P0 rulings or inputs listed above.
2. Keep D14B and D14C formal work on their prescribed clean-VM routes.
3. Do not freeze this draft until E15-1 through E15-6 each have an auditable
   upstream-supported status.
4. Refresh `docs/D_TRACK_STATUS.md` only after an actual upstream closure.
