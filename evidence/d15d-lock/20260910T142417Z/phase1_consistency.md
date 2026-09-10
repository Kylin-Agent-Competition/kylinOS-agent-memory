# D15D Phase 1 consistency evidence

Run ID: `20260910T142417Z`

## Result

`BLOCKED` for final D15D lock. This run does not authorize a version manifest,
submission bundle, or reviewer sign-off.

## C1 - release commit and worktree

- Repository: `E:\Kylin-memory-dev\main`
- HEAD: `306c15ed8e1bb88378c849e83119828afd35083d`
- Release commit: `ba3b50e1bdeea185bca9daee9d1d45958f62a636`
- `git merge-base --is-ancestor ba3b50e... 306c15e...`: exit 0.
- Tracked status count: 0.
- `git status --porcelain --untracked-files=normal` count: 15.
- Strict C1 clean-tree condition is therefore not met because 15 unrelated
  untracked files already existed in this worktree. They were not modified or
  deleted by this task.

## C2 - locked-path drift

Command:

```bash
git diff --name-only ba3b50e1bdeea185bca9daee9d1d45958f62a636 HEAD -- \
  packaging/ memory-service/ cpp-bridge/ migrations/ config/ \
  docs/day14/00_d14a_release_package_contract.md
```

Output: empty. Difference count: 0. Classification: `DOCS_EVIDENCE_ONLY`.

## C3-C6 - package script/unit blobs

Compared source blobs at `ba3b50e1bdeea185bca9daee9d1d45958f62a636` against the
D14D formal evidence `package_SHA256SUMS.txt`.

| Source | Package path | SHA-256 | Result |
|---|---|---|---|
| `packaging/release/systemd_install.sh` | `systemd/install.sh` | `bce16242411929dbe2e3297a06de31e65d91c94a9ffc0638f5658eb73fa31cc7` | PASS |
| `packaging/release/systemd_uninstall.sh` | `systemd/uninstall.sh` | `e29d63ee11c44529fabeeeb87d164454ff2ea08e21ab33fce3b19ae061c00a33` | PASS |
| `packaging/release/systemd_verify.sh` | `systemd/verify.sh` | `b9a367900e748184cfed8e51ad3f7f4f0144bfa1ff095b97a538105c4ee48f20` | PASS |
| `packaging/systemd/kylin-memory.service` | `systemd/kylin-memory.service` | `cf8f76aab5da36dd5eaff6276a71f8307bf4511b1da135d2226af0402e120c28` | PASS |

## C8 - original package integrity

`BLOCKED / NOT_RUN`.

The original frozen tar identity remains:

- Tar SHA-256: `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401`
- Manifest SHA-256: `76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0`
- `SHA256SUMS` SHA-256: `8540cd1dc2b8c743bc466cd89f435e09940ddc5e5df842cacb9367021eddcf67`

The original tar bytes were not found locally. The D14D handoff also records
that they were searched on the current VM and the r1 parent snapshot and were
not found. Therefore `sha256sum -c SHA256SUMS` was not executed for the original
package in this run.

The available provenance-labeled rebuild is not eligible:

- Tar SHA-256: `de4050ee22d3c70f67c3cbf314ada1a76ac7d8d0527d7ba397477122553a30d8`
- Manifest SHA-256: `d16f117d6b874ed18f395d7767ebbed92ae6950734106957fcee3e9a11482646`
- Manifest `source_commit`: `bdd7a5dd460faa6fbfe006375e58b5d72a66ba8c`

This rebuild does not match the frozen tar, manifest, or declared source commit
and must not be used to lock D15D.

## Guard tests

The Phase 0 guard baseline remained the 93-test WSL result recorded in
`phase0_baseline.md`. It is not claimed as Kylin VM L2/L3 evidence.
