# D15D C1 rework - clean detached release checkout

Run ID: `20260910T082403Z`
Supersedes the C1 result in run `20260910T142417Z`.

This rework uses Reviewer E option 1. It reruns the original strict C1
definition without reinterpreting HEAD, clean-tree, or ancestry conditions.

## Worktree

- Path: `E:\Kylin-memory-dev\tmp\d15d-c1-20260910T082403Z`
- Creation command: `git worktree add --detach <path> ba3b50e1bdeea185bca9daee9d1d45958f62a636`
- `git rev-parse --show-toplevel`: `E:/Kylin-memory-dev/tmp/d15d-c1-20260910T082403Z`
- `git rev-parse HEAD`: `ba3b50e1bdeea185bca9daee9d1d45958f62a636`

## Strict C1 checks

```text
git rev-parse HEAD
ba3b50e1bdeea185bca9daee9d1d45958f62a636

git rev-parse kylin-mem/main
cdcce34f870472e63a9359e5a03254eaf9ca6db2

git merge-base --is-ancestor ba3b50e1bdeea185bca9daee9d1d45958f62a636 kylin-mem/main
exit code: 0

git status --porcelain=v1 --untracked-files=all --ignored=no
line count: 0

git diff --check
exit code: 0
```

## Result

`PASS_CLEAN_DETACHED_WORKTREE`

- `HEAD == RELEASE_COMMIT`: PASS.
- Full status, including normal untracked files, is empty: PASS.
- `RELEASE_COMMIT` is an ancestor of `kylin-mem/main`: PASS.

This is repository-state evidence, not Kylin VM runtime evidence.
