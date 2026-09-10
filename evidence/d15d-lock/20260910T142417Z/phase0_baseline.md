# D15D Phase 0 baseline evidence

- Recorded at: `2026-09-10T14:24:17Z`
- Repo/worktree: `E:/Kylin-memory-dev/main`
- Checkout branch: `docs/d14d-formal-inputs-handoff`
- Checkout HEAD: `306c15ed8e1bb88378c849e83119828afd35083d`

## 0.1 Release commit decision

Command:

```bash
git diff --name-only ba3b50e..HEAD -- packaging/ memory-service/ cpp-bridge/ migrations/ config/
git merge-base --is-ancestor ba3b50e1bdeea185bca9daee9d1d45958f62a636 306c15ed8e1bb88378c849e83119828afd35083d
```

Observed result:

- `git diff --name-only` returned no paths.
- `git merge-base --is-ancestor` exited `0`.
- Classification: `DOCS_EVIDENCE_ONLY`.
- Decision: `release_commit = ba3b50e1bdeea185bca9daee9d1d45958f62a636`.

## 0.2 Guard regression

Command:

```bash
python3 -m pytest \
  docs/day15/test_d15a_rc_lock_matrix.py \
  packaging/release/test_d14a_package_integrity.py \
  packaging/release/test_d14a_relocatable_runtime.py \
  packaging/release/test_d14a_transactional_rollback.py \
  packaging/release/test_d14a_verify_smoke.py \
  docs/day14/test_d14a_release_provenance.py -q
```

Observed result:

```text
93 passed in 34.80s
```

## Phase 1 blocker

- Available local rebuilt tar: `main/release/packages/kylin-memory-a-d14a-0.1.0-d14a-rebuilt-ba3b50e.tar.gz`.
- Rebuilt tar SHA-256: `de4050ee22d3c70f67c3cbf314ada1a76ac7d8d0527d7ba397477122553a30d8`.
- D14D frozen tar SHA-256: `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401`.
- The rebuilt tar does not match the frozen identity; it must not be used for D15D lock.
- Port `2222` refused connections and `KYLIN_VM_PASSWORD` was absent, so read-only VM recovery of the original tar was not possible.
