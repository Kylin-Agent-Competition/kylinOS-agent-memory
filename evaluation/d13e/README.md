# D13E 封存测试候选集 v1

本目录的 Dataset 与 Gold 均为合成、脱敏的 **候选封存输入**，而非已经完成
D Reviewer 审核的正式封存集。本目录工件不再保存 `seal_status` /
`gold_status` / `approval_status` 等“审批结果自报”字段：是否被 D Reviewer
批准封存，只由 Review 完成后的外部 Seal 工件证明。在 D Reviewer 复核并确认
D13D 环境 provenance 前，不得把本目录或其任何运行结果称为正式 PASS。

## 文件与对应关系

| 文件 | 作用 |
|---|---|
| `D13E_FORMAL_TESTSET_V1.jsonl` | 17 条 held-out 输入：Preference 4、Conflict 4、Safety 4、Forget 5。 |
| `D13E_GOLD_V1.jsonl` | 与 Dataset 按 `sample_id` 一对一的期望结果和判定依据；每条只含稳定字段（`sample_id`/`metric`/`evaluation_status`/`expected`/`rationale`/`evidence_reference`）。 |
| `D13E_FORMAL_THRESHOLDS_V1.json` | 四项正式 Gate 的候选阈值；纯被审批对象，只含 `threshold_version` 与 `metrics`。 |
| `D13E_FORMAL_MANIFEST_V1.json` | Dataset/Gold/Threshold 文件名与 SHA-256、样本计数、`required_reviewer_track=D` 与 D13D provenance 状态。 |
| `D13E_FORMAL_BUNDLE_V1.json` | 供正式 Runner 消费的相对路径和 manifest 引用（候选模板）。 |

所有 `input` 均为虚构用户 ID 与测试占位内容；不得替换为真实用户正文、真实凭据
或真实敏感载荷。任何内容改动都必须重新计算哈希、更新 manifest，并重新进入
D Reviewer 审查。

## 当前边界

本集覆盖五种 Forget Mode，并保留安全/遗忘零违规 Gate；但 D13D 的冻结 Commit、
VM、依赖、数据版本和统一证据目录尚未收到。因此本目录只能是候选（Manifest
`provenance.status=PENDING_D13D`），Runner 对候选模板 fail-closed，不产出正式
达标结论。

## Runner 完全离线

正式执行路径**不访问 GitHub API**：联网核验（读取 D Reviewer 的 GitHub Review、
PR 作者/head、reviewDecision）已迁移到麒麟 VM 外的可信封存阶段。VM 内 Runner
只消费两个由 D 轨外部流程冻结的本地 Seal：

- `D13E_REVIEW_SEAL_V1.json`（`d13e-review-seal/v1`）：Review 完成后生成，
  含 `reviewed_commit`、`reviewer_identity`、`reviewer_track=D`、
  `review_state=APPROVED`、`review_reference`，以及 `approved_artifacts`
  中的 dataset / gold / threshold / **runner** 四组 SHA-256。
- `D13D_EXECUTION_SEAL_V1.json`（`d13d-execution-seal/v1`）：D13D 轨冻结
  execution attestation digest 后生成，含 `attestation_sha256`、
  `implementation_commit`、`environment_id`、`evidence_root`、
  `frozen_by_track=D` 与 `approval_reference`。

Seal 是 Review / D13D 冻结完成后的后置工件，只出现在 D13D 唯一证据目录中，
不写回被审批的 Commit C，因此不存在“把 Review ID 写回工件→SHA 变化→原
Review 作废”的自引用循环。

## Runner 输入与输出

D13D provenance、四类 raw result 与两个 Seal 就绪后，在冻结麒麟 VM 内使用：

```powershell
& <python> scripts/run_d13e_formal_eval.py evaluation/d13e/D13E_FORMAL_BUNDLE_V1.json `
  --review-seal <证据目录>/D13E_REVIEW_SEAL_V1.json `
  --d13d-seal <证据目录>/D13D_EXECUTION_SEAL_V1.json `
  --output <D13D 统一证据目录>/summary.json
```

Runner 验证顺序（任何失败均非零退出且不写正式报告）：

1. Bundle / Manifest 稳定字段与 D13D provenance（`FROZEN_BY_D13D`）；
2. Review Seal 结构、reviewer 身份/轨道/状态与批准哈希；
3. 本地 Dataset / Gold / Threshold / Runner 实际 SHA-256 == Seal 批准哈希；
4. D13D execution attestation digest == D13D execution seal 冻结值，且
   attestation 与 manifest provenance、seal 三者一致；
5. SHA256SUMS / evidence index / execution log 与四类 raw 文件哈希；
6. 每类指标逐样本对比与 Safety/Forget 硬零 Gate。

每个 raw JSONL 的每一行均为一个执行后的逐样本对象。Safety raw 必须显式给出
`critical_gate_bypass_count`、`normal_memory_write_count`、
`audit_plaintext_leak_count` 与 `cross_user_violation_count` 四个硬零计数；Forget raw
必须显式给出全部五个硬零计数。未知字段会被拒绝：

```json
{"sample_id":"d13e-pref-001","metric":"preference","actual":{"record_count":1}}
```

正式 Bundle 与其原始输入、raw、日志、attestation 与两个 Seal 必须位于同一
D13D 唯一证据目录；`--output` 也只能写入该目录。

## CI

`.github/workflows/baseline-check.yml` 会执行
`python3 -m unittest memory-service.tests.test_d13e_formal_eval -v`，让下一轮
Reviewer 直接在 CI 上看到 D13E 正式评测契约测试结果，而不只依赖评论中的本地
测试数字。