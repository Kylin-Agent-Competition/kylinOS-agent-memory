# D15E E15-1 Technical and User-Manual Positioning Draft (as-of 2026-09-11)

> Nature: drafting preparation only. This file does not freeze the technical
> document or user manual, does not declare D15E final submission lock, and
> does not sign D14E final acceptance.

## Status Lines

E15_1_TECHNICAL_AND_USER_MANUAL_POSITIONING=REWORK_READY_FOR_REVIEW
E15_1_FINAL_POSITION_LOCK=WAITING_PREREQ
D15E_FINAL_SUBMISSION_LOCK=WAITING_PREREQ
D15E_FINAL_SUBMISSION_LOCK_DECLARED=false
D15E_SIGNOFF_STATUS=BLOCKED

## Purpose

This draft fixes the scope, audience, section skeleton, and evidence
boundaries for the two D15E E15-1 deliverables:

1. the technical document; and
2. the user manual.

It is intentionally not the final document. It provides a reviewable
positioning layer so later drafting can use one consistent claim boundary.

## Audience and Positioning

| Deliverable | Primary audience | Position |
| --- | --- | --- |
| Technical document | reviewers, integrators, maintainers | explain architecture, runtime boundaries, evidence chain, and limitations |
| User manual | evaluator, operator, user | explain installation, operation, verification, evidence-backed maintenance, and troubleshooting |

Both documents must remain traceable to repository evidence. Neither may
restate preparation, substitute, or candidate results as formal runtime proof.

## Shared Claim Boundary

The drafts may say, with the listed restrictions:

| Claim | Allowed wording | Boundary |
| --- | --- | --- |
| D13D formal execution closure | formal execution is complete within its recorded scope | do not generalize beyond sample sizes or environment |
| Preference, Conflict, Safety, Forget metrics | metrics meet their recorded thresholds | include sample sizes, thresholds, and environment identity |
| D14A package identity | package identity is frozen | identity only; not release readiness |
| D14D clean Kylin L3 evidence | L3 evidence is ready | keep `release_ready=false` and `production_ready=false` |
| D14B retrieval lifecycle | blocked | preparation or substitute results are not formal L3 |
| D14C real Host E2E | blocked | no real Host Chat LLM or formal evidence root exists |
| D15E final lock | waiting for prerequisites | no final lock or signoff has occurred |

The following must not appear as achieved facts: release readiness,
production readiness, official AI Assistant production E2E success, D14E
final signoff, or unrestricted full-system performance claims.

## Requirement Traceability

The final technical document must include a requirement-analysis section that
uses `docs/project-management/REQUIREMENT_TRACEABILITY_MATRIX.md` only as the
REQ-01 through REQ-07 taxonomy and historical traceability source. That matrix
is a draft for the early D1-D2-to-D3 gate, not the current evidence-status
SSOT. Current status and evidence must bind to the Day13/14/15 SSOT, formal
evidence roots, and the final E15 refresh. The following section mapping is
mandatory; evidence status must not be promoted by section presence.

| Requirement | Final-document traceability |
| --- | --- |
| REQ-01 multi-source data | multi-source ingestion, normalization, event provenance, and write-boundary sections |
| REQ-02 dynamic preference capture | preference extraction, confidence/versioning, update semantics, and decay/lifecycle sections |
| REQ-03 knowledge integration and conflict | knowledge normalization, conflict detection, resolution priority, and audit sections |
| REQ-04 on-device embedding and lightweight retrieval | embedding/bridge boundary, SQLite/FTS5/Vector roles, and fusion-retrieval sections |
| REQ-05 sensitive filtering and precise forgetting | write gate, sensitivity classification, forget preview/execute, and residue checks |
| REQ-06 short/mid/long-term flow | lifecycle states, promotion/decay rules, SQLite truth source, and index rebuild sections |
| REQ-07 standardized evaluation | dataset/gold/threshold identity, metric definitions, execution environment, and report generation |

## Technical Document Skeleton

1. **Scope and system summary**
   - target environment: Kylin Desktop V11 x86_64
   - objective: local multi-source preference and knowledge memory service
   - supported integration boundary and non-goals
2. **Requirement analysis and traceability**
   - REQ-01 through REQ-07 mapping from the section above
   - explicit separation of implemented behavior, candidate behavior, and
     evidence-blocked behavior
3. **Architecture**
   - Memory Service, SQLite truth source
   - FTS5, Vector, and application-layer RRF retrieval paths
   - embedding and bridge boundary
   - IPC and event flow
   - Main-to-Data handoff boundary introduced by PR #180, with M2/M3 kept
     separate from final Runtime Gate claims
4. **Core algorithm and implementation semantics**
   - preference dynamic capture, confidence, versioning, and update precedence
   - knowledge conflict detection, resolution priority, and unresolved-conflict
     exclusion
   - SQLite/FTS5/Vector fusion and candidate explainability
   - sensitive-write filtering and retrieval-output filtering
   - forget preview/execute separation, scope resolution, idempotency, and
     SQLite/index residue checks
5. **Short-term and mid-term memory flow**
   - turn/event ingestion into candidate or short-term state
   - evidence, confidence, explicit confirmation, and time decay as promotion
     or suppression inputs
   - interaction with retrieval and model-request context while original user
     text remains isolated in the chat/UI source
   - handoff toward long-term storage through versioned SQLite records and
     asynchronous index updates
6. **Runtime and deployment**
   - package identity and installation path
   - systemd service lifecycle
   - migration and startup order
   - configuration inputs and local data ownership
7. **Testing, datasets, and quantitative analysis**
   - dataset and gold-label identity: `datasets/ANNOTATION_GUIDELINE_V0.1.md`,
     `datasets/GATE0_BUSINESS_ACCEPTANCE_CASES_V0.1.json`,
     `evaluation/D9_RETRIEVAL_DATASET_README_V2.md`, and
     `evaluation/d13e/README.md`
   - metric definitions and thresholds: `evaluation/D3_GOLD_LABEL_AND_METRICS_SPEC_V1.md`
   - D13E formal test set and threshold identity under `evaluation/d13e/`
   - comparative retrieval design: compare SQLite/FTS5/Vector and fused RRF
     candidates on the same frozen inputs, commands, seed, and environment
   - quantitative metric analysis structure: sample size, numerator/denominator,
     failed-case classes, confidence intervals when specified, and failure
     boundaries; no unbounded extrapolation
8. **Kylin adaptation and compatibility evidence locations**
   - `docs/day3/14_os_agent_kylin_host_test_report_20260816.md`
   - `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e`
   - `evidence/d15d-lock/20260910T205300Z`
   - compatibility claims must remain bounded to the cited commit/package and
     evidence tier
9. **Retrieval and memory semantics**
   - user isolation and versioning
   - conflict and lifecycle handling
   - delete, forget, and rebuild semantics
10. **Testing and evidence hierarchy**
   - D13D formal evidence
   - D14A package identity evidence
   - D14D L3 evidence and its boundaries
   - D14B/D14C open items and why they remain blocked
11. **Operational limits**
   - no unqualified performance claims
   - no release or production readiness claim
   - known debts and follow-up items

## User Manual Skeleton

1. **Before you start**
   - supported environment
   - required artifacts and package identity
2. **Install and start**
   - package install
   - service start and health check
   - first-run data location
3. **Use the memory service**
   - storing preferences and knowledge
   - retrieval behavior
   - update, conflict, and forget paths
4. **Maintenance**
   - service restart
   - index rebuild
   - backup and restore expectations
5. **Evidence-backed capability and limitation matrix**
   - installation and rollback: describe only the scope covered by the cited
     historical D15D clean-tar smoke evidence
   - upgrade: keep `PENDING_UPSTREAM`; D14D G7 is `NOT_RUN/N-A` with waiver and
     D14B formal regression has not closed, so no user-reliable upgrade promise
     is permitted
   - package/service identity checks before any lifecycle operation
6. **Troubleshooting and safety**
   - common service and IPC failures
   - what information to collect for support
   - local-data and privacy boundary

## Four Core Metric Evidence Binding

The final technical document must bind each official metric to its definition,
dataset/gold identity, execution identity, and result status. This positioning
draft records no result values.

| Metric | Required evidence binding | Current final-conclusion status |
| --- | --- | --- |
| Preference accuracy | D3 metric definition, D13E dataset/gold/threshold identity, tested commit, execution environment, and report hash | Restricted D13D evidence only; not an unrestricted final conclusion |
| Retrieval recall | D3 metric definition, frozen D9/D15B inputs, evaluator command, tested commit, and formal report | Blocked by D14B and D15B input freeze |
| Retrieval latency | D3 metric definition, approved A15-2 runner/thresholds or scope ruling, tested package identity, and raw timing evidence | Blocked by A15-2 |
| Conflict-handling correctness | D3 metric definition, conflict gold identity, tested commit, execution environment, and report hash | Restricted D13D evidence only; not an unrestricted final conclusion |

## Required Identity Fields

The final documents must carry these identities separately:

| Identity | Source |
| --- | --- |
| scan-time main head | `git rev-parse origin/main` at final refresh |
| branch base at scan time | the main commit from which the drafting branch starts |
| frozen tested commit | D13D/D14D evidence |
| package tar/manifest/SHA256SUMS hashes | D14A freeze record |
| evidence report hash | D13D formal report |
| evidence roots | exact repository-relative paths |

Main head, frozen tested commit, package hashes, and evidence hashes are
independent objects and must not be equated or substituted.

## Review Inputs

1. Review the section skeletons for missing E15-1 scope.
2. Confirm that the shared claim boundary preserves D14B/D14C blocked state.
3. Confirm that the technical and user-manual audiences are distinct.
4. Return PASS, REWORK, or REJECT for this draft positioning only.

This review does not lock the technical document, user manual, D15E final
submission, or D14E final acceptance.
