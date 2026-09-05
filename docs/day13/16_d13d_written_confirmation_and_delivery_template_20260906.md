# D13D：书面确认与交付回执模板

## 用途与边界

本模板用于关闭 D13D 正式冻结的外部依赖。回复必须逐项填写，不能以“已确认”或
“按既有流程”替代字段。所有哈希使用完整 64 位小写 SHA-256，所有 Git commit 使用完整
40 位小写 SHA。

当前唯一被测基线：

```text
kylin-mem/main@4a32e5c948a968f3bd4409d91deac320002baea1
```

本回执不授权修改 Gold、阈值、IPC、Schema、数据库或生产逻辑。不得提交、粘贴或传递私钥、
sudo 密码、Token、用户原文或未脱敏的封存样本；只允许交付公开密钥、签名、哈希、路径标识、
脱敏日志和审批引用。

## 回执 A：D13E/B 执行适配器与逐样本口径确认

责任方应确认真实调用链，而不是从 Gold、单测断言或固定表生成 `actual`。

```text
confirmation_id:
confirmed_by:
track_and_role:
confirmed_at_utc:

implementation_commit: 4a32e5c948a968f3bd4409d91deac320002baea1
adapter_delivery_type: [versioned_script | approved_command_sequence]
adapter_path_or_artifact_id:
adapter_commit_or_artifact_sha256:
adapter_invocation:

dataset_file: D13E_FORMAL_TESTSET_V1.jsonl
dataset_sha256: 9740c00f4a9d91471bec8e6fa8aeeeb52f890f8680d83f740a84db2b1701a44b
gold_file_read_by_adapter: NO
mock_or_handcrafted_actual: NO

preference_actual_source:
conflict_actual_source:
safety_actual_source:
forget_actual_source:

preference_sample_count: 4
conflict_sample_count: 4
safety_sample_count: 4
forget_sample_count: 5
raw_record_contract: Each JSONL row contains only sample_id, metric, actual, and approved trace reference.
execution_namespace: isolated VM worktree, database, socket, state, and evidence root.
failure_behavior: Preserve failing sample rows; exit non-zero on adapter failure; do not emit a formal PASS claim.
approval_reference:
limitations_or_not_tested:
```

验收要求：适配器读取 Dataset 输入但不读取 Gold；每一条 `actual` 来自对应真实调用结果或
受控数据查询；Safety 的四个硬零计数和 Forget 的五个硬零计数齐全；任何失败样本保留并能由
`sample_id` 追溯。

## 回执 B：D13E Review Seal 交付

此回执只能在 D13D 写入最终 `FROZEN_BY_D13D` Manifest 后填写。禁止重用仓库候选
`PENDING_D13D` Manifest 的 hash。

```text
confirmation_id:
signed_by: Reviewer D
signed_at_utc:
key_id: d13e-review-rd-20260906-v1
public_key_file: d13e-review-public.pem
public_key_sha256: 7cf46363d93a6d0fbe52842d61ca46fa9f10327fcd9cdfb8ab24aef1b019da41

review_reference: https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/148#pullrequestreview-5121766539
reviewed_commit: aa6564a3fa544ab01302adf0b1598436c97f88c0
final_manifest_sha256:
review_seal_file: D13E_REVIEW_SEAL_V1.json
review_seal_sha256:
detached_signature_file: D13E_REVIEW_SEAL_V1.sig
detached_signature_sha256:
evidence_root_identifier:
offline_verification_result: [PASS | FAIL]
```

验收要求：Seal 的 Dataset、Gold、Threshold、Runner 和最终 Manifest hash 与 evidence root
内实物一致；Seal 与 `.sig` 均位于同一 evidence root；私钥不进入 VM、Git、CI 或证据目录。

## 回执 C：D13D Execution Seal 交付

本回执只能在真实 raw、execution log、SHA256SUMS、evidence index 和 execution attestation
均已生成后填写。

```text
confirmation_id:
signed_by: Reviewer D
signed_at_utc:
key_id: d13d-execution-rd-20260906-v1
public_key_file: d13d-execution-public.pem
public_key_sha256: 464aca34fa53a9b8a59e8cd120162f854e54217d4a1769e3e45abac8104debc0

implementation_commit: 4a32e5c948a968f3bd4409d91deac320002baea1
environment_id:
evidence_root_identifier:
execution_attestation_file: D13D_EXECUTION_ATTESTATION_V1.json
execution_attestation_sha256:
execution_seal_file: D13D_EXECUTION_SEAL_V1.json
execution_seal_sha256:
detached_signature_file: D13D_EXECUTION_SEAL_V1.sig
detached_signature_sha256:
offline_verification_result: [PASS | FAIL]
approval_reference:
```

验收要求：attestation 同时绑定 implementation commit、environment、依赖/数据版本、四类
raw hash、execution log、SHA256SUMS 与 evidence index；Seal 和 attestation 的字段逐项一致。

## 回执 D：非作者 Reviewer 对 PR #150 的审查

PR #150 仅审查 D13D 的任务卡、阻塞状态、责任边界和证据纪律，不审为正式 `FROZEN` 结论。

```text
reviewer_identity:
reviewer_track_or_role:
reviewed_pr: https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/150
reviewed_head_commit: 1ad1997ea098038de3523ce55a42790f11188000
reviewed_at_utc:
review_conclusion: [APPROVE | REQUEST_CHANGES | COMMENT]

baseline_binding_checked: [YES | NO]
trust_root_status_consistency_checked: [YES | NO]
raw_and_seal_blockers_retained: [YES | NO]
no_formal_freeze_overclaim_found: [YES | NO]
required_changes_or_limitations:
review_reference:
```

验收要求：Reviewer 必须是 PR #150 作者之外的独立人员；若结论为 `APPROVE`，仅代表文档/
流程材料可合并，不替代 D13E Review Seal、D13D Execution Seal 或正式 Runner Gate 0--10。

## D13D 收件检查

收到任一回执后，D13D 依序执行：

1. 核对提交、文件名、哈希与交付物实物完全一致。
2. 将回执与脱敏执行日志放入新的唯一 evidence root，不复用历史准备目录。
3. 在冻结 VM 离线验签两份 Seal，并记录不含敏感原文的命令输出与退出码。
4. 仅在四类 raw、attestation 与 Seal 全部齐备后运行正式 Runner。
5. Gate 0--10 全部通过且 summary 落盘后，才将 D13D 标记为 `FROZEN`。
