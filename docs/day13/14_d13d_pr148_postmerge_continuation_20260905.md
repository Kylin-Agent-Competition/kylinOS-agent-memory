# D13D：PR #148 合并后续办记录

## 结论

- PR #148 已合并且审核结论为 `APPROVED`；被测基线重新选定为
  `4a32e5c948a968f3bd4409d91deac320002baea1`。
- 旧 `7242935...` 的 D13D 隔离预检不能迁移为新基线的正式冻结证据，
  `d13d_20260905T090507Z` 保留为历史准备记录，正式状态为 `INVALIDATED`。
- D13D 已完成新基线的 VM 快照、隔离部署和 UDS 预检；当前仍不可运行正式评测或标记 `FROZEN`。

## 已完成的安全续办动作

- D13D 分支已并入 `kylin-mem/main@4a32e5c...`，因此本分支包含被测提交及其 D13E Runner 合同。
- 已在 VM 中核验旧隔离实例 PID `75980`：工作目录、命令行、socket 和 DB 均为
  `/home/kylin-agent/kylinOS-agent-memory-d13d-7242935` 命名空间，未涉及现有
  `kylin-memory.service`。
- 已发送 `TERM` 并确认该 PID 终止。遗留 socket 未删除，旧工作树、数据库、状态日志和历史证据均保留。
- 原始核验和退出记录位于 `evidence/l2-kylin-vm/runs/`，其中 stop 命令的最终 socket-absence
  断言失败仅表示 socket 文件仍在；不表示进程仍运行，也未执行删除操作。
- 创建新回滚快照：`d13d-pre-4a32e5c-20260905-2320`，UUID
  `458b6763-5015-404f-a961-cd4a1899232d`；其位于旧 D13D 快照之后，未覆盖任何历史快照。
- 已以本地验证的 bundle SHA-256
  `21a0598cd77fdc17f80f76c399a91b985f4a7ef937028d31886115c6b40948ea`
  上传并在 VM 克隆 `/home/kylin-agent/kylinOS-agent-memory-d13d-4a32e5c`；来宾
  detached `HEAD=4a32e5c948a968f3bd4409d91deac320002baea1` 且 `git status --porcelain` 为空。
- 新候选使用独立 DB、socket 与 state 路径启动，Alembic migration 和长度前缀 JSON
  `health` / `echo` 均成功。它使用 `--no-outbox`，故 `health.data.status=degraded` 是预期的
  隔离预检状态，不能代表正式 service readiness。现有 user-service wrapper 仍指向
  `/home/kylin-agent/kylinOS-agent-memory`，未作修改。
- 已完成新候选的只读运行时采集：OS/KERNEL、Python、SQLite、Alembic、Pydantic、
  SQLAlchemy、三项 Runtime 动态库和 active user-service wrapper 均在 L2 原始日志中记录。
  该采集仅证明当前 VM 观察值，不证明 SDK ABI、Outbox 或正式评测通过。

## 当前阻塞项

| ID | 事项 | 解除证据 | 状态 |
| --- | --- | --- | --- |
| D13D-PM01 | 新基线 VM 回滚点与隔离部署 | 已有新快照、VM 内 detached `HEAD=4a32e5c...`、clean worktree、独立运行路径与 UDS 预检 | PREPARED |
| D13D-PM02 | Frozen Trust Root | `/etc/kylin-memory/trust` 中的 Trust Root JSON、两个 public PEM 均为 root owner、非 symlink、group/other 不可写；公钥来源经授权 | BLOCKED |
| D13D-PM03 | D13E Review Seal | 真实 D Reviewer 对已合并工件签发的 JSON + detached Ed25519 signature，可由 PM02 Trust Root 验证 | BLOCKED |
| D13D-PM04 | D13D Execution Seal | D13D 受控私钥签发的 execution attestation JSON + signature；私钥不进入仓库、证据、CI 或 E 轨 | BLOCKED |
| D13D-PM05 | 四类真实 raw JSONL | 冻结 VM 中产生 Preference、Conflict、Safety、Forget 逐样本结果，并通过 runner Gate 0--10 | BLOCKED |

## 受控下一步

1. 在授权材料到位后安装并核验 Trust Root，接收外部 Seal，再完成 raw 与正式 runner。

## 禁止项

- 不伪造 Review Seal、Execution Seal、签名或公钥；不生成或提交私钥。
- 不从 evidence root、Bundle、Seal 或环境变量替代固定 Trust Root。
- 不将隔离 `--no-outbox` 预检、旧 commit、WSL/L0/L1 或历史 VM 日志写为正式 `FROZEN` / PASS。
