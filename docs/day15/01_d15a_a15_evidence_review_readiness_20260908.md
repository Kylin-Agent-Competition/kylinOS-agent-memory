# D15A A15-1 / A15-3 evidence review readiness (2026-09-08)

> Status: `READY_FOR_REVIEW`.
> This file is review-preparation material only. It is not a D Reviewer
> conclusion and does not grant, execute, or imply any formal lock.
> The frozen D15A matrix remains authoritative: A15-1, A15-2, and A15-3 stay
> `WAITING_PREREQ` until Ducknesses signs each lock item separately.

## 1. Review target and provenance

- Target reviewer: Ducknesses (D primary reviewer).
- Current merged main: `77826122a8aa1eaeed60ec9295a4bb8f979b3fe7`
  (PR #169 squash merge).
- PR #169 was a docs-only refresh of `docs/D_TRACK_STATUS.md`; GitHub compare
  `2bd59488...77826122` reports one modified file, +17/-2.
- Formal tested/source commit:
  `ba3b50e1bdeea185bca9daee9d1d45958f62a636`.
- This PR is intended to contain this readiness document only. It changes no
  runtime path (`packaging/`, `memory-service/`, `cpp-bridge/`,
  `migrations/`, or `config/`).
- The review workspace had unrelated untracked preparation artifacts; they are
  excluded from this PR and are not evidence relied on here.

## 2. Provenance refresh record

The D15A matrix requires a pre-lock read-only refresh. The observations below
are preparation facts, not a formal lock execution.

| Check | Observation |
| --- | --- |
| Current PR preparation base | `7ce83f7e9e382e3976b274c9a5aa8c29493634d9` (content-equivalent source of merged PR #169) |
| Tracked worktree | Clean before this docs-only commit (`git status --porcelain --untracked-files=no` empty) |
| `ba3b50e...HEAD` classification | `DOCS_EVIDENCE_ONLY`; no changes under the five runtime/production prefixes listed in D15A section 4.3 |
| D14D evidence root | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e` |
| D14A package freeze record | `evidence/l3-kylin-vm/d14a_final_package_20260908/D14A_FINAL_PACKAGE_FREEZE_RECORD_20260908.md` |
| Evidence index entry | `D14A-FINAL-PACKAGE-FREEZE`, status `PACKAGE_HASH_FROZEN` |

## 3. A15-1 — Bridge, dependency, and build identity

### 3.1 Proposed lock object

`runtime/bridge/kylin_embedding.cpython-312-x86_64-linux-gnu.so` in the frozen
D14A package.

### 3.2 Evidence chain

| Item | Value / source |
| --- | --- |
| Bridge SHA-256 | `a271891238102d0299395284d486c2e5afdaa4494e6ab0d1ff51a2d2ab9d4db6` |
| Manifest binding | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/package_manifest.json` |
| Checksum binding | Same value appears in `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/package_SHA256SUMS.txt` |
| Build identity | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/package_build_identity.json` |
| Builder | `packaging/release/build_release_package.sh` |
| Builder command | `bash packaging/release/build_release_package.sh --source-commit ba3b50e1bdeea185bca9daee9d1d45958f62a636` |
| Build time UTC | `2026-09-07T13:58:21.266763+00:00` |
| Build host | `Kylin-D14D-clean-vdi-20260906`, pre-formal-run build session |
| Dependency audit | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/raw/g2_dependency_audit.log` |
| Targeted path audit | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/raw/g2_targeted_path_audit.log` |

### 3.3 Audit observations

- `ldd` reports the bridge's dynamic dependencies as resolvable system
  libraries; no `not found` appears.
- The RPATH/RUNPATH section is empty in the G2 dependency audit.
- The targeted build/user path scan completes with `TARGET_SCAN_RC=0`.
- G2 records SDK SHA-256
  `028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48`,
  SONAME `libkylin-coreai-embedding.so.1`, and package version
  `1.2.0.0-0k0.4`.
- The formal package freeze record classifies the current delta from the
  package source commit as `DOCS_EVIDENCE_ONLY`.

### 3.4 Boundary

This evidence supports D adjudication of the frozen bridge artifact, its
dependency surface, and its build identity only. It does not establish:

- runtime/model identity closure;
- A15-2 SDK defense/performance lock;
- release readiness or production readiness;
- any lock in the frozen D15A matrix until D signs it.

## 4. A15-3 — Final package identity consistency

### 4.1 Evidence chain

| Item | Value / source |
| --- | --- |
| Package name | `kylin-memory-a-d14a` |
| Package version | `0.1.0-d14a` |
| Source commit in manifest | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` |
| Package tar SHA-256 | `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401` |
| Package manifest SHA-256 | `76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0` |
| Package SHA256SUMS SHA-256 | `8540cd1dc2b8c743bc466cd89f435e09940ddc5e5df842cacb9367021eddcf67` |
| Manifest file count | `3360` |
| Freeze record | `evidence/l3-kylin-vm/d14a_final_package_20260908/D14A_FINAL_PACKAGE_FREEZE_RECORD_20260908.md` |
| G2 package audit | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/raw/g2_package_audit.log` |
| Formal root summary | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/summary.json` |

### 4.2 Consistency checks recorded

- G2 records the package tar SHA-256 above.
- G2 `SHA256SUMS` verification ends with `SHA_VERIFY_RC=0`.
- G2 integrity gate reports PASS for 3360 files and ends with
  `INTEGRITY_RC=0`.
- The frozen package manifest records `package_version=0.1.0-d14a` and
  `source_commit=ba3b50e...`; the corresponding `VERSION` checksum in
  `package_SHA256SUMS.txt` is
  `442bac3702196e98bfaedd4882ec6a7ee588f25da2c3c78e7201c351d358f30d`.
- The evidence index entry and freeze record bind the same package identity.

## 5. Items requiring separate D adjudication

These items are intentionally not resolved by this PR.

| Item | Current state | Decision requested from D |
| --- | --- | --- |
| A15-1 | Evidence above is ready for review | Decide PASS, REWORK, or REJECT for the bridge/dependency/build lock only. |
| A15-3 | Evidence above is ready for review | Decide PASS, REWORK, or REJECT for package/version/source identity lock only. |
| A15-2 | `BLOCKED` | Choose one: approve a package-only performance runner plus thresholds, or issue a formal scope ruling for A15-2. Performance conclusions also require E follow-up review. |
| D14A BLOCKER C | `HANDOFF_REQUIRED` | Decide whether `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/dependency_identity.json` is accepted as the contract section 6bis unlock input. If accepted, authorize a separate contract-upgrade PR; otherwise keep it open. |

For BLOCKER C, the collected identity file records SDK as `FROZEN`, while
`kylin-ai-runtime` and `kylin-gte-base-model` remain `G0_OBSERVED`. This PR
therefore does not claim contract upgrade or identity closure.

## 6. Requested review method

1. Confirm the frozen D15A matrix still contains exactly one A15-1, A15-2, and
   A15-3 row, each `WAITING_PREREQ`.
2. Inspect the evidence paths and identity values in sections 3 and 4.
3. Recompute or cross-check any hashes independently as desired.
4. Classify this PR by D15A section 4.3; the intended result is
   `DOCS_EVIDENCE_ONLY`.
5. Return an item-by-item decision for A15-1 and A15-3, plus explicit rulings
   for A15-2 and BLOCKER C if they are being addressed now.

## 7. Explicit non-goals

- No package rebuild.
- No new VM run.
- No modification to frozen evidence roots.
- No change to the frozen D15A matrix or D14A contract.
- No declaration of A15 full lock, D14A complete, release readiness, or
  production readiness.
