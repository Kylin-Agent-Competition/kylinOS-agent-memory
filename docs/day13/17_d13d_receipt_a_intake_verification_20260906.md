# D13D 收件核验：回执 A（B 轨执行适配器与逐样本口径）

## 收件对象

- 附件名称：`D13D_回执A_B轨执行适配器与逐样本口径确认.md`。
- 收件日期：2026-09-06。
- 文件 SHA-256：`119a8e46c431025531def3f2e52085615b0e63a967bb340c4724ea55bba68591`。
- 关联：D13D-B07、[回执模板](16_d13d_written_confirmation_and_delivery_template_20260906.md)、PR #150。
- 被测基线：`4a32e5c948a968f3bd4409d91deac320002baea1`。

## 核验结论

`CONTENT_CONSISTENT / CONTRACT_PENDING_IDENTITY / DELIVERY_BLOCKED`

附件内容与 D13D 回执 A 的安全和证据口径一致，但不能作为可关闭 D13D-B07 的正式交付。
它不构成 D13D `FROZEN`、正式 raw 执行完成、Review Seal 或 Execution Seal。

## 已核对一致项

- 基线为完整 SHA `4a32e5c948a968f3bd4409d91deac320002baea1`，Dataset 文件和 SHA-256 与
  D13D 模板一致。
- 明确规定 adapter 不得读取 Gold，`actual` 不得来自 Mock、单测断言、固定表或手工结果。
- 明确四类结果须来自冻结 VM 的真实调用链/受控查询，并绑定 trace reference。
- 明确 Safety 必须包含四个硬零计数、Forget 必须包含五个硬零计数。
- 明确保留失败样本、必要执行失败非零退出，且 adapter 不得声明 formal PASS。

## 未满足项

| 模板字段或交付物 | 附件状态 | D13D 判定 |
| --- | --- | --- |
| `confirmed_by` | `请填写 B 轨确认人姓名或 GitHub ID` 占位 | 缺少可追溯具名确认，不能登记为已签署回执。 |
| `adapter_path_or_artifact_id` | `BLOCKED_NOT_YET_DELIVERED` | 未交付。 |
| `adapter_commit_or_artifact_sha256` | `BLOCKED_NOT_AVAILABLE` | 未交付。 |
| `adapter_invocation` | `BLOCKED_NOT_AVAILABLE` | 未交付。 |
| `approval_reference` | `PENDING` | 未交付。 |
| 四类 17 条 raw JSONL | `NOT YET PRODUCED` | 未交付。 |

## B/D13E 最小补件

无需重发整份回执；只需以可追溯书面回复补齐以下字段，并附版本化 adapter 或批准的命令序列：

```text
confirmed_by:
adapter_path_or_artifact_id:
adapter_commit_or_artifact_sha256:
adapter_invocation:
approval_reference:
```

adapter 必须能够在 D13D 冻结 VM 的隔离 worktree、数据库、socket、state 和唯一 evidence root
中执行；D13D 随后将独立核对其不读取 Gold、实际 exit code、逐样本 raw、执行日志与 hash。

## D13D 后续动作

1. 收到具名补件后，核对 adapter 版本、输入隔离与调用口径。
2. 在冻结 VM 执行 adapter；失败即保留诊断并保持 `BLOCKED`。
3. 仅在 17 条真实 raw 完整产生后，创建 attestation 并进入 Review/Execution Seal 顺序。
