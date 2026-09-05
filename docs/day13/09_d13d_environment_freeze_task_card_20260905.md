# D13D 任务卡：正式评测环境冻结与证据包

## 任务信息

- 施工项：D13D「正式评测环境冻结、统一产物目录与可复现证据包」。
- 任务类型：`docs/test-infrastructure`；本任务冻结评测输入和运行环境，不实现或调整检索、Embedding、Vector、IPC、Schema、数据库或 UI 功能。
- 创建日期：2026-09-05。
- 责任边界：D 轨负责环境、部署和证据可复现性；D13B 消费冻结环境执行检索评测；D13E 提供封存集、Gold 判定键、指标阈值及其 SHA-256。
- 状态：`PREPARED`。PR #148 已合并，候选 D13E 工件和离线 Runner 已在被测基线中；但外部签名 Seal、冻结 Trust Root 与实际 VM raw 结果尚未登记，禁止标记为 `FROZEN` 或“正式评测已开始”。
- 关联：`docs/day13/01_d13b_formal_eval_worklist_20260902.md`、`evidence/index.yaml`、`Kylin-runtime-knowledge/VERSION_MAP.md`（2026-09-01）。

## 目标

为 D13B/D13E 的正式量化评测提供一份不可歧义、可复跑的环境清单。冻结记录必须将同一次运行绑定到：

1. 一个完整且已审核的被测 Git commit；
2. 一台指定的银河麒麟 V11 x86_64 VirtualBox VM 及其快照/资源状态；
3. 部署后的工作树、`systemd --user` 单元、运行时依赖及数据路径；
4. D13E 封存数据集、Gold 判定键、评测配置和各自 SHA-256；
5. 统一的原始日志、结果、报告、校验清单和 `evidence/index.yaml` 登记项。

## 当前已知状态与开工门禁

| 项目 | 当前值 | 状态 | 冻结要求 |
| --- | --- | --- | --- |
| 被测提交 | `4a32e5c948a968f3bd4409d91deac320002baea1` | SELECTED | PR #148 merge commit；`kylin-mem/main` 于 2026-09-05 复核的完整 SHA，部署前和 VM 内 `HEAD` 必须精确一致。 |
| 基线来源 | `kylin-mem/main` | CONFIRMED | 该提交包含 D13B 正式评测组件及 PR #148 的 D13E 候选工件、离线正式 Runner。 |
| 当前工作树 | `feat/d10d-build@1e89d5a`，含 D13C 采集器与用户未跟踪文件 | EXCLUDED | 不作为 D13D 候选，除非经审核后显式选定。 |
| D13E 候选输入 | 已合入，未 Seal | BLOCKED | 独立复核 Dataset、Gold、Threshold、Manifest hash；必须由 D Reviewer Review Seal 证明批准，候选文件本身不能自证封存。 |
| Frozen Trust Root | VM 中不存在 | BLOCKED | 由授权流程在 `/etc/kylin-memory/trust` 安装 root-owned 非 symlink Trust Root JSON 与两份 Ed25519 公钥；不得由 evidence 目录或调用参数提供。 |
| 外部签名与 raw 结果 | 未提供 | BLOCKED | 取得 D13E Review Seal/.sig、D13D Execution Seal/.sig 和四类真实逐样本 raw JSONL。 |
| VM 运行环境 | `Kylin-desktop-neo` 为 VERSION_MAP 目标环境 | READY_FOR_CAPTURE | 每次冻结须实际采集，历史基线不可替代当前 commit 的 L2 证据。 |
| 统一证据目录 | 未创建 | READY | 以本任务定义的目录和 manifest 创建，所有文件校验后才登记索引。 |

只有所有 `BLOCKED` 项解除，且 L2 采集完成、校验和复核无误，D13D 才可由 `PREPARED` 转为 `FROZEN`。

## 被测基线决定

本轮 D13D 的唯一被测代码基线为：

```text
remote: kylin-mem
ref:    main
commit: 4a32e5c948a968f3bd4409d91deac320002baea1
subject: test(D13E)：建立封存候选集与正式评测门禁 (#148)
```

选择依据：

- 它是本地已解析的 `kylin-mem/main`/远端默认分支指向，且是可部署、可追溯的完整提交；
- D13B 正式评测组件及 PR #148 的 D13E 候选集、Gold、阈值、manifest、bundle 和离线 Runner 均存在于该树；
- 当前工作树 `feat/d10d-build@1e89d5a` 不是该主线的后代，且包含未合并的 D13C 证据采集器和用户未跟踪文件，不能作为正式被测代码；
- 旧 `7242935bee5f230cee0535d5e28dbe1e60a302f6` 不含合并后的 D13E 正式门禁，故此前针对该提交的隔离预检不再是本轮正式冻结证据；该证据包仅保留为历史准备记录。

此决定不表示 `4a32e5c...` 在麒麟 VM 已通过正式评测；任何提交、依赖、数据、Trust Root 或 Seal 变化均按本任务卡的失效规则处理。

## 批准范围

允许：

- 新增 D13D 冻结清单、只读采集命令、证据目录、校验清单、评测环境报告和 `evidence/index.yaml` 条目；
- 部署一个明确的候选 commit 到隔离的 VM 工作树，记录部署前状态与回滚点；
- 对项目服务和数据库执行只读状态检查、运行 D13B 的正式评测命令。

禁止：

- 修改 FRZ-IPC-001 至 FRZ-IPC-007、Pydantic/JSON Schema、SQLite/Alembic、错误码、D13E Gold 或评测阈值；
- 为取得指标而修改数据集、删除失败查询、重写检索/Embedding/Vector 生产逻辑，或把开发集替代封存集；
- 覆盖系统 SDK、`/usr` 下库文件、官方模型目录或既有 VM 快照；
- 将 WSL/L0/L1、旧 commit 或历史 VM 日志表述为本冻结 commit 的正式结果。
- 伪造、提交、记录或通过 CI 分发 D Reviewer/D13D 私钥；从 evidence root、Bundle、Seal 或环境变量加载 Trust Root。

## 冻结输入与输出契约

### 输入登记

每项均为必填，不接受“最新”“当前”或短 SHA：

| 字段 | 要求 |
| --- | --- |
| `tested_commit` | 已审核候选的完整 40 位 Git SHA，部署前和 VM 内 `HEAD` 必须一致。 |
| `source_commit` | 本冻结记录/采集脚本所在提交的完整 SHA。 |
| `vm_identity` | VM 名称、UUID、OS release、kernel、架构、快照名/时间和 CPU/RAM/磁盘资源。 |
| `deployment` | VM 工作树绝对路径、`git status --porcelain`、`systemctl --user cat/is-active kylin-memory.service`、socket/数据库/日志路径。 |
| `runtime_dependencies` | Python、SQLite、pytest、SQLAlchemy、Alembic、Embedding/Vector 相关包与动态库版本；动态库 ABI 未实测不得作已验证结论。 |
| `eval_config` | 固定 `d9-retrieval-eval-config/v1` 的完整 JSON 与 SHA-256，包含 k/top_k/rrf_k、warmup/repeat/concurrency/statistics_method。 |
| `dataset` | D13E 封存集版本、完整 SHA-256、条目数、访问限制；不记录用户原文或敏感样本正文。 |
| `gold` | Gold 判定键版本、完整 SHA-256、空 Gold/负例/边界样本策略及 OFFICIAL 阈值来源。 |
| `trust_root` | 固定 `/etc/kylin-memory/trust` 的目录/文件权限、owner、两个 public PEM hash 和 Trust Root JSON hash；不得记录私钥。 |
| `review_seal` | D13E Review Seal 与 detached signature 的路径、SHA-256、key ID、审查引用和验签结果。 |
| `execution_seal` | D13D Execution Seal 与 detached signature 的路径、SHA-256、key ID、attestation hash 和验签结果。 |

### 输出目录

本轮目录固定为 `evidence/l2-kylin-vm/d13d_<UTC_RUN_ID>/`，其中 `<UTC_RUN_ID>` 为 `YYYYMMDDTHHMMSSZ`。不得混入其他 commit 或重复使用目录。

```text
evidence/l2-kylin-vm/d13d_<UTC_RUN_ID>/
  environment_freeze.json
  deployment_preflight.json
  runtime_versions.txt
  service_unit.txt
  commands.log
  d13b_raw_results.json
  d13b_report.json
  SHA256SUMS
  README.md
```

`environment_freeze.json` 最少包含以上输入登记字段、生成时间（UTC）、采集者、命令退出码和 `freeze_status`。`freeze_status` 只能为 `PREPARED`、`BLOCKED`、`FROZEN` 或 `INVALIDATED`；任一必填输入缺失、哈希不匹配、工作树不干净或部署 SHA 不一致时必须为 `BLOCKED` 或 `INVALIDATED`。

## 执行清单

- [ ] 选择并人工确认 `tested_commit`，记录批准来源。
- [ ] 从干净/可回退 VM 快照创建本轮工作副本；记录 VM UUID、资源、OS 与快照信息。
- [ ] 部署精确 `tested_commit`，核对 VM 内 `git rev-parse HEAD` 和 `git status --porcelain`。
- [ ] 采集 service unit、active 状态、Memory Service socket 权限、数据库路径及 Python/SQLite/依赖版本。
- [ ] 取得 D13E 封存集、Gold、阈值和评测配置；逐一执行 SHA-256 校验并记录条目数。
- [ ] 核验 `/etc/kylin-memory/trust` 的固定路径、root owner、非 symlink 与 group/other 非写权限；未授权不得自行安装或生成公钥。
- [ ] 接收并离线验签 D13E Review Seal、D13D Execution Seal；两份 Seal/.sig 必须位于本轮 evidence root 内。
- [ ] 创建唯一证据目录，记录所有实际执行命令、退出码与原始输出。
- [ ] 由 D13B 在同一冻结目录运行正式评测；结果和报告与环境清单中的 `tested_commit`、数据集和配置哈希一致。
- [ ] 对目录内所有交付物生成 `SHA256SUMS` 并独立复核。
- [ ] 将状态、限制和校验和登记到 `evidence/index.yaml`；`tested_commit` 与 `evidence_commit` 分开记录。
- [ ] 复核无敏感正文、凭据、Token、私钥或可识别用户原文进入日志/报告；失败样例只保留脱敏标识和错误分类。

## L2 采集命令基线

以下命令是操作清单，不代表已经执行。路径应由本轮冻结记录替换，且所有输出必须进入本轮证据目录：

```bash
git rev-parse HEAD
git status --porcelain
cat /etc/kylin-release
uname -a
systemctl --user is-active kylin-memory.service
systemctl --user cat kylin-memory.service
stat -c '%a %n' "$XDG_RUNTIME_DIR/kylin-memory/memory.sock"
sqlite3 --version
python3 --version
sha256sum <d13e_dataset> <d13e_gold> <eval_config>
```

VM 运行时路径、SDK/Vector ABI 和安装包版本以实际 VM 采集为准；`VERSION_MAP.md` 仅提供 2026-09-01 的对照参考。任何 ⚠️ 或 ❌ 源码匹配项不得仅凭源码版本声明为宿主兼容。

## 验收标准

1. `tested_commit`、VM 内 `HEAD`、评测报告 metadata 与 `evidence/index.yaml` 的 `tested_commit` 完全一致。
2. VM、部署、依赖、数据集、Gold 和配置的版本/哈希/来源完整可追溯，且 `SHA256SUMS` 全部验证通过。
3. 原始结果、聚合报告、实际命令和退出码可由独立人员在指定 VM 快照复跑。
4. 证据索引按现有 1.1 契约登记 `id`、`task_id`、`description`、`status`、`evidence_level`、`source`、`date`、`reviewer`、`limitations`、`checksum_sha256`；同时记录 `tested_commit`、`evidence_commit`、`manifest_sha256`。
5. 对未满足的前提明确写 `BLOCKED` / `UNVERIFIED`，不得以环境冻结替代 D13B 指标通过、D13E 数据集批准或 C/D 端到端链路验收。

## 风险、失效与回滚

- 候选提交、VM 快照、服务 unit、依赖、配置、D13E 输入、Trust Root 或任一 Seal 任一变化，当前冻结立即标记 `INVALIDATED`，创建新的 `<UTC_RUN_ID>`，禁止增量覆盖旧目录。
- 部署失败、服务不活跃、哈希不匹配或工作树不干净时停止正式评测，保留诊断日志并标记 `BLOCKED`。
- VM 仅在项目级工作树与用户级服务范围内操作；不覆盖系统包/库、不更新系统依赖。部署前保存工作树和 service 状态，失败时回退至采集到的部署前 commit/状态并复验。
- 日志必须避免封存样本正文、认证信息和用户原文。需要调查失败样本时，使用 dataset 行号或脱敏 query ID。

## 未决事项

1. D Reviewer / 受控 signing 流程需交付已验签的 Review Seal；D13D signing 流程需交付 Execution Seal。
2. 需获得安装 frozen Trust Root 所需的已批准公钥材料及系统级变更授权。
3. 需在新的 `4a32e5c...` VM 快照上完成隔离部署与真实四类 raw JSONL。

在上述事项关闭前，本任务卡仅授权准备与只读采集，不授权发布任何正式量化结论。
