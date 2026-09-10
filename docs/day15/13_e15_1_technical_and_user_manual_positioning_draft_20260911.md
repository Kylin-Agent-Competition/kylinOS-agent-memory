# D15E E15-1 Technical and User-Manual Positioning Draft (as-of 2026-09-11)

> Nature: drafting preparation only. This file does not freeze the technical
> document or user manual, does not declare D15E final submission lock, and
> does not sign D14E final acceptance.

## Status Lines

E15_1_TECHNICAL_AND_USER_MANUAL_POSITIONING=READY_FOR_REVIEW
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
| User manual | evaluator, operator, user | explain installation, operation, verification, upgrade/rollback, and troubleshooting |

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

## Technical Document Skeleton

1. **Scope and system summary**
   - target environment: Kylin Desktop V11 x86_64
   - objective: local multi-source preference and knowledge memory service
   - supported integration boundary and non-goals
2. **Architecture**
   - Memory Service, SQLite truth source
   - FTS5, Vector, and RRF retrieval paths
   - embedding and bridge boundary
   - IPC and event flow
3. **Runtime and deployment**
   - package identity and installation path
   - systemd service lifecycle
   - migration and startup order
   - configuration inputs and local data ownership
4. **Retrieval and memory semantics**
   - user isolation and versioning
   - conflict and lifecycle handling
   - delete, forget, and rebuild semantics
5. **Testing and evidence**
   - D13D formal evidence
   - D14A package identity evidence
   - D14D L3 evidence and its boundaries
   - D14B/D14C open items and why they remain blocked
6. **Operational limits**
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
5. **Upgrade and rollback**
   - supported flow
   - package/service identity checks
6. **Troubleshooting and safety**
   - common service and IPC failures
   - what information to collect for support
   - local-data and privacy boundary

## Required Identity Fields

The final documents must carry these identities separately:

| Identity | Source |
| --- | --- |
| main head | `git rev-parse HEAD` at final refresh |
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
