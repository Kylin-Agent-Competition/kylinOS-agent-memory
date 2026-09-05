# D13E 封存测试候选集 v1

本目录的 Dataset 与 Gold 均为合成、脱敏的 **候选封存输入**，而非已经完成
D Reviewer 审核的正式封存集。每条 Gold 的 `gold_status` 为
`CANDIDATE_FOR_D_REVIEW`；在 D Reviewer 复核并确认 D13D 环境 provenance 前，
不得把本目录或其任何运行结果称为正式 PASS。

## 文件与对应关系

| 文件 | 作用 |
|---|---|
| `D13E_FORMAL_TESTSET_V1.jsonl` | 17 条 held-out 输入：Preference 4、Conflict 4、Safety 4、Forget 5。 |
| `D13E_GOLD_V1.jsonl` | 与 Dataset 按 `sample_id` 一对一的期望结果和判定依据。 |
| `D13E_FORMAL_THRESHOLDS_V1.json` | 四项正式 Gate 的候选阈值、来源和待批准字段。 |
| `D13E_FORMAL_MANIFEST_V1.json` | Dataset/Gold 哈希、样本计数与 D13D provenance 状态。 |
| `D13E_FORMAL_BUNDLE_V1.json` | 供正式 Runner 消费的相对路径和 manifest 引用。 |

所有 `input` 均为虚构用户 ID 与测试占位内容；不得替换为真实用户正文、真实凭据
或真实敏感载荷。任何内容改动都必须重新计算哈希、更新 manifest，并重新进入
D Reviewer 审查。

## 当前边界

本集覆盖五种 Forget Mode，并保留安全/遗忘零违规 Gate；但 D13D 的冻结 Commit、
VM、依赖、数据版本和统一证据目录尚未收到。因此当前状态只能是
`CANDIDATE_FOR_SEALING` / `UNVERIFIED`，不能产出正式达标结论。

## Runner 输入与输出

待 D13D provenance 和四类 raw result 均就绪后，使用：

```powershell
& <python> scripts/run_d13e_formal_eval.py evaluation/d13e/D13E_FORMAL_BUNDLE_V1.json \
  --output <D13D 统一证据目录>/summary.json
```

每个 raw JSONL 的每一行均为一个执行后的逐样本对象。Safety raw 必须显式给出
`critical_gate_bypass_count`、`normal_memory_write_count`、
`audit_plaintext_leak_count` 与 `cross_user_violation_count` 四个硬零计数；Forget raw
必须显式给出全部五个硬零计数。未知字段会被拒绝：

```json
{"sample_id":"d13e-pref-001","metric":"preference","actual":{"record_count":1}}
```

Runner 要求每个有效 Dataset 样本在同指标 raw JSONL 中恰好出现一次，且所有 `actual`
字段与 Gold 的 `expected` 对照。D13D 必须同时提供 `d13d-execution-attestation/v1`：它
包含冻结 commit、环境、依赖/数据版本、证据根/引用、四类 raw 文件及 SHA-256、执行日志、
`SHA256SUMS` 和 evidence index 的 SHA-256。正式 Bundle 与其原始输入、raw、日志及该证明
必须位于同一 D13D 唯一证据目录；Runner 在写出报告前验证该证明、清单、Dataset/Gold/阈值
SHA-256、样本规模和四类 raw 结果。D13D 填写 `provenance.evidence_root` 的规范目录引用，
并将上述 Bundle 部署到该目录的物理根部，填写 `provenance.evidence_directory: "."`；
`--output` 也只能写入该目录。

封存后 Runner 还会在线核验 PR #148 的 GitHub Review：批准记录必须是受信任的 D 轨
非作者、状态为 `APPROVED`，且 review commit 与 Manifest 一致。任何输入不完整、错配、
未知安全字段、未批准阈值、PR 当前 head 漂移、未解决的 `CHANGES_REQUESTED` 或核验失败都会
非零退出，不写出正式报告。

D Reviewer 的批准正文必须包含以下摘要（值为当次 Manifest 的实际 SHA-256）；Runner 同时
拒绝任何 Reviewer 当前仍维持的 `CHANGES_REQUESTED`：

```text
D13E_FORMAL_SEAL_APPROVAL
dataset_sha256: <64 位 SHA-256>
gold_sha256: <64 位 SHA-256>
threshold_config_sha256: <64 位 SHA-256>
```
