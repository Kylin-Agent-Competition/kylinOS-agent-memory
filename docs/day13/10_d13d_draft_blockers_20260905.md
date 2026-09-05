# D13D Draft：阻塞项与开工条件

- Draft 分支：`docs/d13d-environment-freeze`
- 被测代码基线：`kylin-mem/main@4a32e5c948a968f3bd4409d91deac320002baea1`（PR #148 merge commit）
- 状态：`PREPARED`。本记录不是环境冻结成功证据，也不发布正式量化结论。
- 关联任务卡：`docs/day13/09_d13d_environment_freeze_task_card_20260905.md`

## 阻塞项

| ID | 阻塞项 | 责任方 | 解除条件 | 当前状态 |
| --- | --- | --- | --- | --- |
| D13D-B01 | D13E Review Seal 未交付 | D Reviewer / 受控签名流程 | 提供已签名的 `D13E_REVIEW_SEAL_V1.json` / `.sig`，其批准的 Dataset、Gold、Threshold、Runner、Manifest hash 与 `4a32e5c...` 一致。 | BLOCKED |
| D13D-B02 | D13D Execution Seal 未签发 | Reviewer D / D13D | Frozen Trust Root 已安装并核验；待真实 execution attestation 生成后，由 Reviewer D 受控私钥签发 execution seal/.sig。不得提交私钥。 | BLOCKED |
| D13D-B03 | 本轮 VM 快照与资源登记 | D13D | 已创建 `d13d-pre-4a32e5c-20260905-2320`（UUID `458b6763-5015-404f-a961-cd4a1899232d`）；VM 身份和资源见续办记录。 | PREPARED |
| D13D-B04 | 新基线隔离部署与 VM 核验 | D13D | VM 内 `HEAD=4a32e5c948a968f3bd4409d91deac320002baea1`、工作树干净，独立 DB/socket 已启动并完成 UDS 预检；现有 user service 未切换。 | PREPARED |
| D13D-B05 | 本轮正式证据目录与校验清单尚未生成 | D13D | 创建唯一 `evidence/l2-kylin-vm/d13d_<UTC_RUN_ID>/`，写入最终环境清单、命令输出、Manifest、attestation 和 `SHA256SUMS`；不得复用旧基线准备目录。 | BLOCKED |
| D13D-B06 | D13B -> D13D 正式 Evaluation Contract | B 轨 | B 轨已提供正式 CLI、输入/输出合同和 fail-closed 语义；真实输入绑定随 D13E/B01、B02 与 D13D 环境冻结执行。 | B 轨已解除 |
| D13D-B07 | 四类真实 raw JSONL 与受批准执行适配器缺失 | D13D + D13E / B 轨 | 已收到回执 A（内容 hash 见 D13D 收件核验记录）：不读 Gold、真实调用链、逐样本 trace、失败非零退出等口径与模板一致；但 `confirmed_by` 未具名，adapter path/commit-or-hash/invocation/approval reference 均为未交付，17 条 raw 尚未产生。B/D13E 必须补具名确认并交付或书面批准适配器及执行步骤；适配器不得读取 Gold 生成 actual、不得使用 Mock 或手工构造结果。随后在冻结 VM 产生 Preference、Conflict、Safety、Forget 的逐样本 raw，并由正式 Runner Gate 0--10 校验。 | CONTRACT_PENDING_IDENTITY / DELIVERY_BLOCKED |

## 开工条件

允许开始 VM 部署与只读环境采集，必须同时满足：

1. 使用上述完整 `tested_commit` 创建隔离 VM 工作树；旧 `7242935...` 预检已失效，不得使用当前开发树或旧候选替代。
2. 已保存部署前 VM 状态和回滚点，且不覆盖系统 SDK、系统库、模型目录或既有快照。
3. 所有命令、输出和退出码写入唯一的 D13D 证据目录；日志不记录封存样本正文、用户原文或任何凭据。

允许开始正式 D13B 评测，必须额外满足：

1. D13D-B01 至 D13D-B07 全部关闭，并在 `environment_freeze.json` 写入 `freeze_status=FROZEN`。
2. 评测报告中的 `tested_commit`、数据集/Gold/配置哈希与环境清单逐项一致。
3. `SHA256SUMS` 验证通过，且 `evidence/index.yaml` 可按 1.1 契约登记。

## 不可绕过的边界

- 不合并 `kylin-mem/test/d13e-formal-eval@6f55dfefeb248a11a0c9b54ce392762d49c4e065` 作为被测代码；该分支含封存数据之外的未合并跨层变更。
- 不因阻塞项存在而修改 Gold、阈值、评测样本或生产检索实现。
- 不以 WSL/L0/L1、旧 commit 或历史 VM 日志替代本次基线的 L2 证据。

## Draft 退出条件

本 Draft PR 仅在任务卡、阻塞项和开工门禁被确认后可合并。合并本 PR 不等同 D13D `FROZEN`；实际冻结证据必须在后续同分支或关联 PR 中按任务卡生成和审核。
