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
| 5 | E10 | 建立正式 Runner；provenance 与唯一 evidence 根、D13D execution attestation（含依赖/数据、SHA256SUMS、evidence index）、阈值版本/哈希、外部 Review Seal 与 D13D execution seal、版本、哈希、四类 metric 样本集不完整即 fail-closed；Runner 完全离线，不访问 GitHub API | E2--E4 | CLI 行为测试与手工复现 | CANDIDATE_READY（40 项离线契约测试通过并接入 CI；真实 raw、签名 Seal 与 VM provenance 待 D13D/D Reviewer） |
| 6 | E5/E7/E8/E9 | 以真实链路或正式等价回放生成 per-sample raw JSONL | E1--E4、E10、D13D VM | 原始结果完整可追溯 | BLOCKED |
| 7 | E6/E12--E14 | 输出错误分类、四项汇总、真实 Gap、优化映射 | 第 6 项 | summary 与报告 | BLOCKED |
| 8 | E11/E15 | 麒麟 VM 执行、D 非作者审查、审查返工 | D13D、D Reviewer | 证据包和 Reviewer 结论 | BLOCKED |

## 4. 预先限定的 Runner 公共边界

为避免测试耦合内部实现，本批仅通过下列 CLI 边界验证：

```text
PYTHONPATH=memory-service python scripts/run_d13e_formal_eval.py \
  evaluation/d13e/D13E_FORMAL_BUNDLE_V1.json \
  --review-seal <证据目录>/D13E_REVIEW_SEAL_V1.json \
  --d13d-seal <证据目录>/D13D_EXECUTION_SEAL_V1.json \
  --trust-roots /etc/kylin-memory/trust \
  --output evidence/day13/d13e/summary.json
```

预期的可观察行为：

1. 合法且哈希匹配的 bundle 才能输出四类指标结构；
2. provenance 缺失、文件哈希不符、Dataset/Gold 不一一对应或有效样本为零时，命令必须以非零退出并且不得写出正式报告；
3. 未经麒麟 VM 实测的候选输入，输出仅可标记 `UNVERIFIED`，不得产生 `PASS`。

以上边界不替代 D Reviewer 的独立审查，也不把单元测试当作 VM 执行证据。

Runner 已完全离线：GitHub 联网核验迁移到麒麟 VM 外的可信封存阶段，VM 内
只验证本地 `D13E_REVIEW_SEAL_V1.json`（d13e-review-seal/v1，含 approved
hashes 与 reviewed_commit）与 `D13D_EXECUTION_SEAL_V1.json`
（d13d-execution-seal/v1，冻结 execution attestation digest）。
`.github/workflows/baseline-check.yml` 已新增
`python3 -m unittest memory-service.tests.test_d13e_formal_eval -v` 步骤。

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

除上述原始字段外，正式执行还需要 D13D 轨在证据目录冻结
`D13D_EXECUTION_SEAL_V1.json`（attestation digest 外部可信根），并在 D
Reviewer 对 Commit C 完成非作者批准后，由 VM 外可信 sealing 流程生成
`D13E_REVIEW_SEAL_V1.json`；两者都是 Review / 冻结完成后的后置工件，不写回
被审批的 Commit C。


## 6. 第三轮 Review 返工（2026-09-05）：签名 Seal + Frozen Trust Root

第三轮 Review 对 head `bc3deed` 已关闭：P1-A（Review-ID 自引用）、P1-C（联网
GitHub）、D13E 定向 CI、Safety/raw 完整性等。本轮只处理剩余信任根问题。

### 状态

```text
Review-ID self-reference       CLOSED
Offline Runner                 CLOSED
D13E CI                        CLOSED

Review Seal authentication     IN_PROGRESS（代码+测试已实现，待第 4 轮 Reviewer）
D13D Seal authentication       IN_PROGRESS（代码+测试已实现，待第 4 轮 Reviewer）
Seal evidence-root binding     IN_PROGRESS（代码+测试已实现，待第 4 轮 Reviewer）

Real D13D raw                  BLOCKED / external
Formal metrics                 BLOCKED / external
```

### 实现内容（对应 Commit A/B/C）

- R1/R2：Review Seal 与 D13D Execution Seal 改为 Ed25519 detached signature，
  Runner 离线验签；签名合同为 canonical JSON（sort_keys + 紧凑分隔符 + UTF-8）。
- R3：Review Seal 签名载荷包含 actual_pr_author、reviewer_identity/track、
  review_state、review_reference、reviewed_commit 与 approved_artifacts
  （dataset/gold/threshold/runner/manifest）；非作者判定使用签名内
  actual_pr_author != reviewer_identity。
- R4：Seal 与 .sig 必须位于 evidence root 内；frozen trust root 必须在
  evidence root 之外（`/etc/kylin-memory/trust`，含
  `D13E_TRUST_ROOTS_V1.json` + 两个 public PEM）。
- 正式 summary provenance 记录 seal/signature/key_id/key_fingerprint。
- 测试扩至 40 项，覆盖：假 APPROVED（真实 5120706798 为 CHANGES_REQUESTED）、
  签名后篡改 state/author/identity、reviewer==actual_pr_author、攻击者自建
  key、整链重写无 D13D 私钥、Seal 在 evidence root 外、signature 文件异常等；
  CI 只使用 TEST-ONLY 私钥。

### 仍待外部交付

- D Reviewer：冻结 Commit C 上完成真正 APPROVED Review，由 VM 外可信流程生成
  并签名 `D13E_REVIEW_SEAL_V1.json`。
- D13D：预置 frozen trust store，冻结并签名 `D13D_EXECUTION_SEAL_V1.json`，
  交付真实四类 raw + execution attestation。

## 7. 第四轮 Review 返工（2026-09-05）：固定系统 Trust Root

第四轮 Review 对 head \`58fc398\` 确认 Ed25519 双 Seal / actual_pr_author / Seal
路径均已关闭，剩余核心 P1：正式 Runner 允许调用者通过 \`--trust-roots\` 自选信任根。

### 状态

\`\`\`text
Review-ID self-reference             CLOSED
Offline Runner                       CLOSED
Ed25519 Review Seal                  CLOSED
Ed25519 D13D Seal                    CLOSED
actual_pr_author signed              CLOSED
Seal evidence-root path              CLOSED
D13E CI                              CLOSED

Frozen Trust Root caller override    IN_PROGRESS（代码+测试已实现，待第 5 轮 Reviewer）
System trust permissions             IN_PROGRESS（代码+测试已实现，待第 5 轮 Reviewer）
Attacker external trust test         IN_PROGRESS（代码+测试已实现，待第 5 轮 Reviewer）

Real D Reviewer APPROVED Seal        EXTERNAL BLOCKED
Real D13D raw/evidence               EXTERNAL BLOCKED
Formal four metrics                  EXTERNAL BLOCKED
\`\`\`

### 实现内容（Commit 1 + Commit 2）

- 正式 CLI 删除 \`--trust-roots\`；正式 API \`compute_formal_report()\` 不再接收
  trust-root 参数；测试通过 TEST-ONLY hook
  \`_compute_formal_report_with_verified_trust_root\` 注入临时 trust root。
- 正式 Runner 只读取固定系统路径 \`/etc/kylin-memory/trust\`；不读取 CLI / 环境变量 /
  Bundle / Seal 提供的 trust 路径。
- Trust Root 目录、\`D13E_TRUST_ROOTS_V1.json\` 与两个 public PEM 增加系统权限 Gate：
  \`lstat\` 非 symlink、目录/普通文件类型、owner=root（uid=0）、group/other 不可写
  （\`mode & 0o022 == 0\`）；\`public_key_file\` 只允许 basename；保留 PEM SHA 与 key_id 校验。
- 新增 T35～T41：CLI 拒绝 \`--trust-roots\`、help 无该选项、正式 API 无 override、
  attacker 签名双 Seal 用合法 trust root 验签 FAIL、symlink/owner/group-other 写拒绝。
- 契约测试扩至 48 项（CI POSIX 额外含 real-fs metadata gate 1 项，Windows 跳过）。
