# D13E 封存测试与正式量化评测工作清单（2026-09-05）

## 1. 目的与证据边界

本工作单落实 D13E「封存测试与正式量化评测」任务：封存独立 held-out 测试集和
Gold Label，建立 fail-closed 正式 Runner，计算 Preference、Conflict、Safety、Forget
四项结果，并保留可复现证据。

本工作单不把以下材料误称为 D13E 正式结论：

- D6 多源开发集（明确为 `DEVSET_V1`，非 Gold、非封存集）；
- 本机或 L0/L1 pytest 结果；
- D11D 的历史 VM 证据；
- 缺少 D13D 冻结 Commit、环境、数据版本或统一证据目录的输出。

正式结果只能绑定 D13D 交付的冻结环境和被测 Commit；在此之前所有尚未执行的
指标均为 `UNVERIFIED`。

## 2. 本批基线与已知阻塞

| 项目 | 当前值 | 状态 | 证据/处理 |
|---|---|---|---|
| 本批开发基线 | `origin/main@053754d611801548fdac59b2894c6862bf85cf56` | 本地可见 | 分支 `test/d13e-formal-eval` 从该已合并缓存基线创建；GitHub fetch 因本机凭据失败，提交前须重新同步。 |
| D13D 冻结 Commit | 未交付 | BLOCKED | 不能用 `latest main`、D11D 或其他历史 Commit 替代。 |
| D13D 麒麟 VM / 依赖 / 数据版本 | 未交付 | BLOCKED | D11D 历史 VM 仅可作能力背景，不能作为 D13E 正式环境。 |
| D13D 统一证据目录 | 未交付 | BLOCKED | 正式 raw result、stdout、stderr、exit code 需写入该目录。 |
| D13E Dataset / Gold | 未建立 | IN_PROGRESS | 本批建立独立候选；封存前须 D Reviewer 审核。 |
| D Reviewer 审查 | 未开始 | PENDING | 不由作者自行替代。 |

## 3. 工作项、依赖与验收方式

| 顺序 | 条目 | 本批动作 | 依赖 | 验收证据 | 状态 |
|---:|---|---|---|---|---|
| 1 | E1 | 将 D13D 交付字段定义为 Runner 必填 provenance | D13D 交付 | 缺字段拒绝正式输出 | IN_PROGRESS |
| 2 | E2 | 建立独立 D13E held-out Dataset，不复用 D6 Devset 为正式集 | D3/D6 规范 | JSONL 格式、稳定 ID、固定样本规模 | CANDIDATE_READY（待 D Reviewer 封存） |
| 3 | E3 | 建立一对一 Gold，含判定依据与有效/边界状态 | E2；D Reviewer 复核 | Dataset/Gold ID 全等 | CANDIDATE_READY（17/17 ID 对应；待 D Reviewer） |
| 4 | E4 | 计算 Dataset/Gold SHA-256，写入 Manifest 和 bundle | E2、E3 | 哈希可独立复算 | CANDIDATE_HASH_VERIFIED（候选哈希已复算） |
| 5 | E10 | 建立正式 Runner；provenance 与唯一 evidence 根、外部核验的 D 非作者封存、PR 当前 head 且无未解决变更请求、阈值版本/哈希、D13D execution attestation（含依赖/数据、SHA256SUMS、evidence index）、版本、哈希、四类 metric 样本集不完整即 fail-closed | E2--E4 | CLI 行为测试与手工复现 | CANDIDATE_READY（20 项契约测试通过；真实 raw、D 批准与 VM provenance 待 D13D/D Reviewer） |
| 6 | E5/E7/E8/E9 | 以真实链路或正式等价回放生成 per-sample raw JSONL | E1--E4、E10、D13D VM | 原始结果完整可追溯 | BLOCKED |
| 7 | E6/E12--E14 | 输出错误分类、四项汇总、真实 Gap、优化映射 | 第 6 项 | summary 与报告 | BLOCKED |
| 8 | E11/E15 | 麒麟 VM 执行、D 非作者审查、审查返工 | D13D、D Reviewer | 证据包和 Reviewer 结论 | BLOCKED |

## 4. 预先限定的 Runner 公共边界

为避免测试耦合内部实现，本批仅通过下列 CLI 边界验证：

```text
PYTHONPATH=memory-service python scripts/run_d13e_formal_eval.py \
  evaluation/d13e/D13E_FORMAL_BUNDLE_V1.json \
  --output evidence/day13/d13e/summary.json
```

预期的可观察行为：

1. 合法且哈希匹配的 bundle 才能输出四类指标结构；
2. provenance 缺失、文件哈希不符、Dataset/Gold 不一一对应或有效样本为零时，命令必须以非零退出并且不得写出正式报告；
3. 未经麒麟 VM 实测的候选输入，输出仅可标记 `UNVERIFIED`，不得产生 `PASS`。

以上边界不替代 D Reviewer 的独立审查，也不把单元测试当作 VM 执行证据。

## 5. 待接收的 D13D 交付

在正式执行前，D13E 必须收到并写入 `D13E_FORMAL_MANIFEST_V1.json` 的原始字段：

```json
{
  "implementation_commit": "40 位小写 Git SHA",
  "environment_id": "D13D 冻结 VM 标识",
  "dependency_version_reference": "依赖清单或其哈希",
  "data_version_reference": "数据版本或其哈希",
  "evidence_root": "统一证据目录"
}
```

没有这些字段时，Runner 和报告必须 fail-closed；不得以 `UNKNOWN`、`latest main`
或历史 D11D 环境填充。
