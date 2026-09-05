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
- VM 上执行 `PYTHONPATH=memory-service python -m unittest
  memory-service.tests.test_d13e_formal_eval -v`：48/48 通过，耗时约 47 秒。该测试使用
  TEST-ONLY trust hook 覆盖签名、固定 Trust Root、路径和 fail-closed 合同；不产生、导入或认可正式私钥/Seal。
- 受控正式 CLI 负向测试退出码为 2，且未写出 summary：仓库候选 Bundle 在
  `formal_result_status=NOT_RUN` 处被拒绝。这是预期的前置 fail-closed 行为，不是正式结果；
  VM 的 `/etc/kylin-memory/trust` 仍不存在，故后续 Gate 0 也尚无法由真实材料通过。
- VM 全套 `PYTHONPATH=memory-service python -m pytest -q memory-service/tests` 完成：
  `1723 passed, 49 skipped, 4 failed`，耗时 200.80 秒；未发现 requirements 声明的依赖缺失，
  未安装额外包。候选 worktree 在测试后仍为 clean。
- 4 个失败均位于 `test_day13a_benchmarks.py::test_full_run_rejects_incomplete_real_index_evidence`。
  原因是测试未传入已被当前 `validate_run_completeness()` 要求的
  `expected_commit` / `expected_branch`，并对旧的短错误文本作列表精确匹配；实际验证已正确
  返回更严格、带完整路径的 fail-closed 错误。此 D13A 测试维护问题不在 D13D 批准范围内，
  不通过修改或跳过测试掩盖。
- VM 上 `bash scripts/verify_repository_baseline.sh` 通过；该结论不覆盖上述 D13A pytest
  失败，也不构成 D13E 正式指标。

## 当前阻塞项

| ID | 事项 | 解除证据 | 状态 |
| --- | --- | --- | --- |
| D13D-PM01 | 新基线 VM 回滚点与隔离部署 | 已有新快照、VM 内 detached `HEAD=4a32e5c...`、clean worktree、独立运行路径与 UDS 预检 | PREPARED |
| D13D-PM02 | Frozen Trust Root | 已安装 `/etc/kylin-memory/trust`；root:root、755/644、non-symlink，Runner 正式加载函数已验证两个 Reviewer D key ID | PREPARED |
| D13D-PM03 | D13E Review Seal | 真实 D Reviewer 对已合并工件签发的 JSON + detached Ed25519 signature，可由 PM02 Trust Root 验证 | BLOCKED |
| D13D-PM04 | D13D Execution Seal | D13D 受控私钥签发的 execution attestation JSON + signature；私钥不进入仓库、证据、CI 或 E 轨 | BLOCKED |
| D13D-PM05 | 四类真实 raw JSONL | 冻结 VM 中产生 Preference、Conflict、Safety、Forget 逐样本结果，并通过 runner Gate 0--10 | BLOCKED |
| D13D-PM06 | D13A 全套 pytest 维护失败 | 4 个 Day13A 断言与当前 `bench_utils` 合同一致，并在 VM 全套 pytest 中复跑通过 | 技术债 / 不阻塞 D13D 冻结 |

## VM 测试结论

- 新基线的迁移、独立 UDS 启动和 D13E 离线评测合同已在指定麒麟 VM 上完成相应 L2 验证。
- 这不是 D13E 正式四项指标：候选 Bundle、Trust Root、双 Seal、D13D execution attestation 和四类 raw JSONL 均未就绪。
- 任何后续正式执行须在同一冻结证据根中使用真实的受控签名材料，并让 CLI 依次通过 Gate 0--10。
- 本轮未安装依赖或仓库：现有隔离 VM 的 `d4d-venv` 已满足 `memory-service/requirements.txt`，
  因此没有为“测试通过”而引入额外包、系统软件或外部仓库。
- 2026-09-06：Reviewer D 已建立两套独立 Ed25519 密钥，私钥只在 Windows 受限目录中保管；
  VM 固定 Trust Root 只接收两份 public PEM 与 Trust Root JSON。正式 Runner 已在 VM 成功加载
  `d13e-review-rd-20260906-v1` 和 `d13d-execution-rd-20260906-v1`。D13A 的 4 个断言维护失败
  调整为并行技术债，不阻塞 D13D 正式冻结。

## 受控下一步

1. 在授权材料到位后安装并核验 Trust Root，接收外部 Seal，再完成 raw 与正式 runner。

## 禁止项

- 不伪造 Review Seal、Execution Seal、签名或公钥；不生成或提交私钥。
- 不从 evidence root、Bundle、Seal 或环境变量替代固定 Trust Root。
- 不将隔离 `--no-outbox` 预检、旧 commit、WSL/L0/L1 或历史 VM 日志写为正式 `FROZEN` / PASS。
