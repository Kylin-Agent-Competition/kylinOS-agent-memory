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

每个 raw JSONL 的每一行均为一个执行后的逐样本对象：

```json
{"sample_id":"d13e-pref-001","metric":"preference","actual":{"record_count":1}}
```

Runner 要求每个有效 Dataset 样本在同指标 raw JSONL 中恰好出现一次，且所有 `actual`
字段与 Gold 的 `expected` 对照。它在写出报告前验证 D13D provenance、Dataset/Gold
SHA-256、样本规模和四类 raw 结果；任一项不完整、错配或无有效样本都会非零退出。
