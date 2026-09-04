# D12D TD-049 Closure Candidate

- Task card: `D12D-PostMerge-01`
- Tested commit: `cc4acf6ec67de50ca6fbb60bb7044cff46f7d4a5`
- VM: `Kylin-desktop-neo D12-TDR`, Kylin V11, kernel `6.6.0-76-generic`
- Snapshot before deployment work: `d12d-pre-main-cc4acf6-20260904`
- Evidence: `evidence/l2-kylin-vm/d12d_td049_cross_uid_20260904.log`

## TD-049 Closure Conditions

| Sub-item | Evidence | Result |
| --- | --- | --- |
| UID-scoped production socket | `$XDG_RUNTIME_DIR/kylin-memory/memory.sock`; config/share `0700`, socket/DB `0600`, no legacy `/tmp/kylin-memory/embedding.sock` candidate | PASS |
| Cross-UID failure closed | Disposable user `d12d_uid_probe` attempted `connect_ex()` to uid 1000's socket and received `errno=13` (`EACCES`); the account was removed in cleanup | PASS |
| Safe verification facility and metadata | Verification ran after a named VirtualBox snapshot; command, tested commit, VM, socket and result are stored in the raw L2 record and indexed by SHA-256 | PASS |

## Scope Boundary

This is a TD-049 closure candidate only. It does not close `TD-DEPLOY-001`, `TD-KYSEC-001`, or `TD-055`.

- `TD-DEPLOY-001`: rollback/reinstall was exercised on `cc4acf6`, but the 5.0.3 AGT-006 layout verification remains outstanding.
- `TD-KYSEC-001`: `kysec_policy exec on` can be enabled, but the disposable unknown binary was not blocked; a later `-A` policy probe affected SSH command execution and the VM was restored to the pre-deploy snapshot. The current policy is confirmed `exec=off`.
- `TD-055`: OS reboot recovery passed on `cc4acf6`, but no real C-to-D-to-B request exists; `memory.retrieve` still returns only the documented empty-context degradation.

## Review Request

The register remains `In Progress (Closure Candidate pending D Reviewer)`. A non-author D reviewer must verify the raw evidence checksum and the three TD-049 closure conditions before marking it `Resolved`.
