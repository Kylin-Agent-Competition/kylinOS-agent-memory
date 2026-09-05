# D13E 封存测试候选集 v1

本目录的 Dataset 与 Gold 均为合成、脱敏的 **候选封存输入**，而非已经完成
D Reviewer 审核的正式封存集。本目录工件不再保存 `seal_status` /
`gold_status` / `approval_status` 等“审批结果自报”字段：是否被 D Reviewer
批准封存，只由 Review 完成后的外部 **签名 Seal** 工件证明。在 D Reviewer
复核并确认 D13D 环境 provenance 前，不得把本目录或其任何运行结果称为正式 PASS。

## 文件与对应关系

| 文件 | 作用 |
|---|---|
| `D13E_FORMAL_TESTSET_V1.jsonl` | 17 条 held-out 输入：Preference 4、Conflict 4、Safety 4、Forget 5。 |
| `D13E_GOLD_V1.jsonl` | 与 Dataset 按 `sample_id` 一对一的期望结果和判定依据；每条只含稳定字段。 |
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

## 签名与信任模型（冻结）

- 签名算法：**Ed25519（RFC 8032）**，detached signature，算法与合同已冻结，
  不再逐轮更换。
- Canonical payload 合同（签名对象）：

```python
json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
```

  禁止签 pretty-print JSON、不稳定 key 顺序或包含 signature 自身的对象。
- 正式证据结构（Seal 与 .sig 都位于 D13D 唯一证据目录）：

```text
D13E_REVIEW_SEAL_V1.json       +  D13E_REVIEW_SEAL_V1.sig
D13D_EXECUTION_SEAL_V1.json    +  D13D_EXECUTION_SEAL_V1.sig
```

- Frozen Trust Root 位于 **evidence root 之外**，由 D13D 环境冻结时预置：

```text
/etc/kylin-memory/trust/D13E_TRUST_ROOTS_V1.json   # trust_store_version=d13e-trust-roots/v1, signature_scheme=ed25519
/etc/kylin-memory/trust/d13e-review-public.pem
/etc/kylin-memory/trust/d13d-execution-public.pem
```

  Trust Root JSON 至少记录 `key_id` / `public_key_file` / `public_key_sha256`。
- Private key 归属：Review Seal 由 D Reviewer / D 轨受控私钥签名；D13D Seal 由
  D13D-owned process 签名。正式私钥**禁止 commit、禁止进入 evidence、禁止进入
  CI、禁止交给 E actor**。CI 与测试只使用 TEST-ONLY 私钥。

## Seal Payload（被签名内容）

Review Seal（`d13e-review-seal/v1`）至少包含：`seal_version`、
`signature_scheme`、`source_repo`、`source_pr`、**`actual_pr_author`**、
`reviewer_identity`、`reviewer_track`、`review_state`、`review_reference`、
`reviewed_commit`、`approved_artifacts`（dataset / gold / threshold / runner /
manifest 五组 SHA-256）、`key_id`。

非作者判定使用签名内事实：

```text
signed actual_pr_author != signed reviewer_identity
```

D13D Execution Seal（`d13d-execution-seal/v1`）至少包含：`seal_version`、
`signature_scheme`、`attestation_sha256`、`implementation_commit`、
`environment_id`、`dependency_version_reference`、`data_version_reference`、
`evidence_root`、`evidence_reference`、`frozen_by_track`、`approval_reference`、
`key_id`。

## Seal 路径规则（fail-closed）

- 两个 Seal 与两个 `.sig` 必须位于 bundle/evidence root 内；拒绝绝对外部路径、
  `../` 逃逸与 symlink 逃逸。
- Frozen Trust Root 必须位于 evidence root 之外；把自建公钥写进 evidence 目录
  不能获得信任。

## Runner 输入与输出

D13D provenance、四类 raw result、两个签名 Seal 与 frozen trust root 就绪后，
在冻结麒麟 VM 内使用：

```powershell
& <python> scripts/run_d13e_formal_eval.py <D13D 统一证据目录>/bundle.json `
  --review-seal <证据目录>/D13E_REVIEW_SEAL_V1.json `
  --d13d-seal <证据目录>/D13D_EXECUTION_SEAL_V1.json `
  --trust-roots /etc/kylin-memory/trust `
  --output <证据目录>/summary.json
```

`--trust-roots` 默认 `/etc/kylin-memory/trust`；开发/CI 可指向 TEST-ONLY trust store。

Runner 固定 Gate 顺序（任何失败均非零退出且不写正式报告）：

```text
Gate 0  Trust Root 存在（且不在 evidence root 内）
Gate 1  Seal/.sig 位于 evidence root
Gate 2  Review Seal 签名有效
Gate 3  Review policy：actual_pr_author / reviewer / state / commit
Gate 4  approved artifact hashes（dataset/gold/threshold/runner/manifest）
Gate 5  D13D Seal 签名有效
Gate 6  D13D execution identity / attestation digest
Gate 7  Manifest / provenance / Bundle
Gate 8  raw / logs / SHA256SUMS / evidence index
Gate 9  Preference / Conflict / Safety / Forget
Gate 10 写 formal summary
```

正式 `summary.json` 的 provenance 会记录：

```text
review_seal_sha256 / review_signature_sha256 / review_key_id / review_key_fingerprint
d13d_execution_seal_sha256 / d13d_signature_sha256 / d13d_key_id / d13d_key_fingerprint
```

每个 raw JSONL 的每一行均为一个执行后的逐样本对象。Safety raw 必须显式给出
`critical_gate_bypass_count`、`normal_memory_write_count`、
`audit_plaintext_leak_count` 与 `cross_user_violation_count` 四个硬零计数；Forget raw
必须显式给出全部五个硬零计数。未知字段会被拒绝：

```json
{"sample_id":"d13e-pref-001","metric":"preference","actual":{"record_count":1}}
```

## CI

`.github/workflows/baseline-check.yml` 会执行
`python3 -m unittest memory-service.tests.test_d13e_formal_eval -v`，让下一轮
Reviewer 直接在 CI 上看到 D13E 正式评测契约测试结果。CI 只使用 TEST-ONLY
Ed25519 私钥，不接触正式 D/D13D 私钥。