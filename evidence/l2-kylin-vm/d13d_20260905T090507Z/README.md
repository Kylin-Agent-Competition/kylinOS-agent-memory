# D13D Environment Preparation Evidence

Run ID: `d13d_20260905T090507Z`

This directory records only the initial D13D Kylin VM deployment preparation for `7242935bee5f230cee0535d5e28dbe1e60a302f6`.

The existing production user service was left unchanged. The candidate was cloned to an isolated worktree and started only with an isolated SQLite database, an isolated UDS socket, and `--no-outbox`. Its UDS `health` and `echo` probes passed at the envelope level; `health.data.status=degraded` is expected for the explicit no-Outbox preflight mode.

This is not a formal systemd deployment, D13E data sealing, D13B formal evaluation, or a `FROZEN` environment. The environment remains `BLOCKED` until the D13E Dataset/Gold review and seal, official threshold approval, real provenance bundle, and formal deployment/evidence review are complete.

Raw runner logs and summaries are copied from `evidence/l2-kylin-vm/runs/`. `SHA256SUMS` covers every file in this directory after the preparation record was generated.
