# D14A Release Package Contract（溯源收口 v5 · Reviewer E Identity Adjudication Approved · G-D7 SIGNED）

> 依据：D14A 交接文档（2026-09-05）§Phase 2 + §A14-B01 解除要求。
> 状态：**SIGNED / REVIEWER_E_IDENTITY_ADJUDICATION_APPROVED / G_D7_SIGNED**（v4 曾按 2026-09-06 D14D 人工裁决清单
> D-03/D-04 会签为 FROZEN；GitHub 第四轮 review 执行仍属 Ducknesses 的实际动作，
> 本会签不替代）。
> 2026-09-10 v5 第二轮返工：当前 package/provenance identity 改为消费 D14D 正式
> evidence root（`d14d_20260907T141000Z_ba3b50e`）的 `ba3b50e` 冻结身份；
> 旧 v4 身份仅保留为 §1.3 historical/superseded 记录。§6bis 的 ReviewerD 授权
> repository reference 为
> <https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/175#issuecomment-5615523980>。
> 该 reference 由 PR author `Ducknesses` 发布，因此仅保留为 invalid historical authority record，不再作为当前 active blocker。
> 2026-09-10 ReviewerE identity adjudication：非作者 Reviewer E 在
> <https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/175#issuecomment-5616426125>
> 独立裁定接受 D14D `ba3b50e` identity/provenance closure，并确认可回填 contract、
> D15D manifest 与 Round 2 evidence。该裁定仅覆盖 identity/provenance/contract
> consistency closure，不替代 D15D 最终签署。
> 该升版只冻结外部依赖身份；不改变 D14D `L3_READY=true` / `release_ready=false` /
> `production_ready=false` 边界，也不宣称 Release Gate 或 production 就绪。
> 冻结方式：本文件为 package contract 唯一真源；本 v5 identity closure 由上述
> ReviewerE identity adjudication 专项裁定，D15D/G-D7 最终签署由 PR #175 Round 7 review `5168962906` 完成。
> 2026-09-06 会签变更：§3/§6bis 统一为“SDK 全量 fail-closed；runtime/model
> HANDOFF_REQUIRED，由正式 D14D G0 采集冻结后回填并升版”；正式 package version 固定
> `0.1.0-d14a`（D-05）。除此之外 v4 溯源收口内容不变。
> v4 溯源收口：§1.1 中 `current_pr_head` 不再落库固定 SHA，改为以
> `git rev-parse HEAD` 执行时事实为唯一真源；复核改为执行时三分类
> （EVIDENCE_CURRENT / DOCS_EVIDENCE_ONLY / RUNTIME_EVIDENCE_STALE）；如实声明
> 当前 runtime evidence 相对本 PR HEAD 为 **RUNTIME_EVIDENCE_STALE**（需重新打包 →
> 重算 hash → 重跑真实 VM 后回填；正式刷新超出本 Task 尚未执行）。其余四身份语义、
> §6bis BLOCKER C 与安装/verify 架构（整包复制 install_prefix + `~/.local/bin`
> symlink + 安装前缀 launcher + 独立 embedding server PID 实际加载校验）不变。

---

## 0. 目的

定义 A 轨「正式发布包」的内容、身份、安装、验证与回退契约，使：
- 干净 VM 仅凭发布包 + 声明的前置依赖即可完成 install → start → real SDK smoke → restart → status
  （real SDK smoke 前置：先启动真实独立 embedding server 并取得其真实 PID，见 §9；
  非 gateway 单 PID 自加载）；
- **不依赖**源码 checkout、个人 venv、开发者 HOME 下的残留；
- Bridge/SDK/model/runtime 的身份可追溯（声明的即实际加载的）。

---

## 1. Package Identity（冻结字段）

| 字段 | 值 | 说明 |
|---|---|---|
| `package_name` | `kylin-memory-a-d14a` | A 轨发布包名 |
| `package_version` | `0.1.0-d14a` | 首个 D14A 版本 |
| `source_commit` | **`ba3b50e1bdeea185bca9daee9d1d45958f62a636`** | **当前 D14D 冻结包构建声明基线**（D14D `package_build_identity.json` 的 `source_commit`）；若 main 前移触及发布路径，必须重新冻结；身份语义见 §1.1，禁止与 evidence/head 混写 |
| `source_tree_dirty` | `false`（打包时 git status --porcelain 为空） | 打包入口强制检查 |
| `target_os` | 银河麒麟桌面 V11 2603 x86_64（kernel 6.6.x） | 与 D14B/D14D 干净快照一致 |
| `target_arch` | amd64 (x86_64) | |
| `install_prefix` | `${XDG_DATA_HOME:-$HOME/.local/share}/kylin-memory-d14a` | 发布包安装根 |
| `runtime_user` | 当前登录用户（systemd --user） | 不要求 root |
| `service_name` | `kylin-memory` | systemd --user unit |
| `socket_path` | `$XDG_RUNTIME_DIR/kylin-memory/memory.sock` | systemd RuntimeDirectory 提供 |
| `config_path` | `${XDG_CONFIG_HOME:-$HOME/.config}/kylin-memory/config.toml` | 未提供则默认值 |
| `data_path` | `${XDG_DATA_HOME:-$HOME/.local/share}/kylin-memory/kylin_memory.db` | SQLite |
| `state_path` | `${XDG_STATE_HOME:-$HOME/.local/state}/kylin-memory` | Outbox/journal 状态 |

---

## 1.1 Provenance 身份语义（当前 D14D 冻结身份）

| 身份字段 | 值 | 语义 |
|---|---|---|
| `source_commit` | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` | 当前 D14D 冻结包构建声明基线 |
| `tested_runtime_commit` | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` | 当前 D14D 正式 L3 evidence root 实际测试的提交；D14D 的构建/测试提交有意相等，不构成伪造 |
| `evidence_commit` | `ec7a66b3e52f8d76b156300d375467290fdc42b6` | D14D evidence root 正式入库 commit（PR #165） |
| `current_pr_head` | `<git rev-parse HEAD 输出>`（执行时事实） | **动态值**：本表不落库固定 SHA，以 `git rev-parse HEAD` 输出为唯一真源；随新提交前移，禁止把 `tested_runtime_commit` 写成 current_pr_head |

- 四者语义独立，**不得互相伪造相等**；当前 `source_commit == tested_runtime_commit`
  是 D14D formal evidence 的真实事实（同一冻结包先构建、后在同一 commit 的
  evidence root 中测试），不表示 evidence/head 可混写。尤其**不得把
  `tested_runtime_commit` 写成当前 PR head**。
- 证据新鲜性以 `git diff --name-only tested_runtime_commit..HEAD`（HEAD 为执行时
  `git rev-parse HEAD` 事实，不落库固定 SHA）做三分类：
  - `EVIDENCE_CURRENT`：diff 为空；
  - `DOCS_EVIDENCE_ONLY`：diff 非空且不含 `packaging/`、`memory-service/`、
    `cpp-bridge/`、`migrations/`、`config/` 任一前缀（仅 docs/evidence 等转换）；
  - `RUNTIME_EVIDENCE_STALE`：diff 含上述任一 packaging/runtime 前缀——必须
    **重新打包 → 重算 hash → 重跑真实 VM** → 回填新的 `tested_runtime_commit` /
    `evidence_commit` 后才可更新 runtime evidence。
- 2026-09-10 第 4 轮返工事实：`ba3b50e..current-main@4a6323f` 命中
  `memory-service/` 锁定前缀，既有 frozen package lock 对 current main 为
  `FAIL_INVALIDATED`；D15D 已登记 `TRIGGER_NEW_RELEASE_PACKAGE_IDENTITY`。
  守卫在每次执行时按 `git diff --name-only tested_runtime_commit..HEAD` 复核分类，
  不得以本段静态文字替代 live 判定。
- 仅文档/测试变更（`DOCS_EVIDENCE_ONLY`）不触发重包，但 `current_pr_head` 前移时
  仍须按上述三分类复核。

### 1.2 当前 D14D 冻结包身份（v5，SSOT 口径）

| 字段 | 值 | 来源 |
|---|---|---|
| package name / version | `kylin-memory-a-d14a` / `0.1.0-d14a` | D14D `package_build_identity.json` |
| frozen tar SHA-256 | `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401` | D14D `package_build_identity.json` |
| package manifest SHA-256 | `76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0` | D14D `package_build_identity.json` |
| package `SHA256SUMS` SHA-256 | `8540cd1dc2b8c743bc466cd89f435e09940ddc5e5df842cacb9367021eddcf67` | D14D `package_build_identity.json` |
| evidence root | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e` | D14D `summary.json` |
| machine-readable mirror | `docs/day15/D15D_VERSION_MANIFEST.json` | D15D lock manifest |

本表与 D15D manifest、D14D evidence 的任何身份字段不一致时守卫必须失败；
失败时不得用历史 v4 身份或重建产物解释为当前身份。

### 1.3 Historical / superseded D14A v4 identity

| 身份字段 | 历史值 | 状态 |
|---|---|---|
| `source_commit` | `5424d28e1178d3d16764ad7c050b878bc8981583` | **historical / superseded**，不得用于当前安装或锁定 |
| `tested_runtime_commit` | `e3d4b9d565e2c3c153973125b3c071225e1b9e4d` | **historical / superseded**，仅解释 D14A v4 历史 evidence |
| `evidence_commit` | `68bb8f764e204818759fceae0616cac0048753a2` | **historical / superseded**，仅指 D14A v4 历史 evidence 快照 |

---

## 2. Package 内容清单（发布包内）

```
dist/kylin-memory-a-d14a-0.1.0-d14a/
├── bin/
│   └── kylin-memory-server          # 自包含 launcher（见 §4）
├── runtime/
│   ├── python/                      # 独立 venv（python3.12 + requirements）
│   ├── app/                         # memory-service 应用包（模块级，非源码 checkout）
│   └── bridge/                      # kylin_embedding*.so（pybind11 模块）
├── config/
│   └── config.toml.example
├── systemd/
│   ├── kylin-memory.service
│   └── install.sh / uninstall.sh / verify.sh
├── VERSION                          # 0.1.0-d14a
├── manifest.json                    # 文件清单 + sha256 + source_commit
└── SHA256SUMS                       # 打包后对所有文件生成
```

### 是否随包

| 组件 | 是否入包 | 说明 |
|---|---|---|
| Memory Service runtime | ✅ `runtime/app/` | 模块级复制（`memory-service/` 内的包），**不含 .git / docs / tests** |
| Bridge | ✅ `runtime/bridge/kylin_embedding*.so` | pybind11 构建产物 |
| Bridge 动态库 | ✅（`ldd` 静态链接或 NEEDED 可解析） | 见 §5 dependency audit |
| SDK `.so` | ❌（**外部系统依赖声明**） | `libkylin-coreai-embedding 1.2.0.0-0k0.4` 由 OS 包提供；包内仅记录身份（§6） |
| Model / runtime | ❌（**外部系统依赖声明**） | `ensemble-embd_gte-base_uint8-text` 由 SDK 默认加载；包内记录身份 |
| Python runtime | ✅ `runtime/python/`（独立 venv） | 不依赖个人 venv |
| systemd unit | ✅ `systemd/kylin-memory.service` | 冻结 unit，install 复制 |
| install / uninstall / verify | ✅ | 见 §7/§8/§9 |
| manifest + SHA256SUMS | ✅ | 见 §10 |

---

## 3. 前置系统依赖（不在包内，clean VM 需预装或由 D14D 提供）

```text
libkylin-coreai-embedding = 1.2.0.0-0k0.4   (amd64)   # SDK：install 全量 fail-closed（版本 + SHA）
kylin-ai-runtime         = 1.2.0.4-0k0.1               # runtime：正式 G0 冻结值（见 §6bis）
kylin-gte-base-model     = 1.0.0.1-0k0.9               # model：正式 G0 冻结值（见 §6bis）
python3.12               (系统 python，用于创建包内 venv)
```

> Gate 口径（2026-09-06 裁决 D-03）：
> - **SDK**（`libkylin-coreai-embedding` `.so`）：install 必须执行存在性 + exact
>   package version + SHA-256，缺一即 fail-closed（当前实现）。
> - **runtime / model**：上表版本仅为参考值（基线 v2 实测来源），未经 D Reviewer
>   冻结验证；v5 依据 D14D 正式 G0 证据冻结 version/hash，仅用于安装前提审计。
>   本版 install 仍按原实现对 SDK 全量 fail-closed；runtime/model 不做 hash Gate。

---

## 4. Launcher（`bin/kylin-memory-server`）

- 自包含 shell launcher：
  - `PYTHONPATH=<prefix>/runtime/app:<prefix>/runtime/bridge`
  - `exec <prefix>/runtime/python/bin/python -m app ... "$@"`
- **禁止**硬编码 `/home/<developer>`；prefix 从自身路径推导：
  `prefix="$(cd "$(dirname "$0")/.." && pwd)"`
- 透传全部 `app.py` CLI 参数（`--socket --config --db --no-migrate --no-outbox
  --vector-cli --vector-dimension --digest-key-id --digest-key --json-logs`）；
  production 默认不带 `--register-*` seam 参数（BLOCKED_BY_HOST_MAPPING 保持）。

---

## 5. Dependency Audit（正式候选发布包 / D14D evidence Gate 前强制完成）

Dependency Audit 按责任阶段分为两层：**A. Build-time Builder Gate**（构建期由
`build_release_package.sh` 当前实际已实现的强制能力）与 **B. Formal Candidate /
D14D Evidence Gate**（正式候选发布包 / L3 前 **REQUIRED** 的依赖与身份审计）。
两层均**非 optional、非「建议执行」**；B 类不得在构建期提前宣称已完成。

### 5.1 A. Build-time Builder Gate（`build_release_package.sh` 当前实际已实现）

| 检查 | 实现位置/方式 | 必须结果 |
|---|---|---|
| 包结构组装 | Phase 2 组装 | dist 目录结构完整（bin/runtime/config/systemd/VERSION/manifest/SHA256SUMS） |
| VERSION / package_version | Phase 2 写入 | `0.1.0-d14a` 一致 |
| source identity Gate | Phase 0（`--source-commit` 必填且须与 HEAD 一致） | 构建声明基线 = manifest.source_commit，fail-closed |
| dirty-tree Gate | Phase 0 | 构建时 `git status --porcelain` 为空（source_tree_dirty=false） |
| Python/SDK 前置 | Phase 0 | Python≥3.10 与 SDK `.so` 存在性检查 |
| 构建路径残留扫描 | Phase 2.4.2 | 无开发机绝对路径/构建残留（fail-closed） |
| 包内 migration smoke | Phase 2.9 | 包内 `alembic upgrade head` smoke 通过 |
| manifest 生成 + files 全集 | Phase 3 | manifest 含 source_commit/sdk identity/files 全集，与磁盘双向一致断言 |
| SHA256SUMS | Phase 3 | 打包后对所有文件生成 |
| install 侧完整性 Gate | `systemd/install.sh` | manifest/SHA256SUMS 校验 + SDK 三向闭合完整性 Gate，fail-closed |

### 5.2 B. Formal Candidate / D14D Evidence Gate（正式候选发布包 / L3 前 REQUIRED）

| 检查 | 命令 | 必须结果 |
|---|---|---|
| Bridge 动态依赖 | `ldd runtime/bridge/kylin_embedding*.so` | 无 `not found`；全部 NEEDED 可解析 |
| RPATH/RUNPATH | `readelf -d ... \| grep -E 'RPATH\|RUNPATH'` | 无开发机绝对路径 |
| 硬编码路径 | `grep -RInE '(/home/\|/Users/\|[A-Za-z]:\\\|.venv\|d4d-venv\|PYTHONPATH\|--repo\|build/)' runtime/ packaging/` | 无个人开发目录命中（或逐条登记结论） |
| SDK 身份审计 | 独立 embedding server `/proc/<embedding_pid>/maps` 实际加载路径+hash + `sha256sum` + `readelf -d` SONAME | = 合同 §6（声明的即实际加载的） |

> 现状：B 类审计当前仅以**历史证据采集形态**存在于
> `evidence/l3-kylin-vm/d14a_20260905/dependency_audit/`（采集于历史
> `tested_runtime_commit`），仅记录证据，**未构成**正式候选包 / L3 的 REQUIRED Gate；
> 正式 D14D 候选包 / L3 前必须按上表以 REQUIRED Gate 重新执行——
> 不得因历史采集形态将其降为 optional 或「建议执行」。

---

## 6. SDK / Model 身份（声明 = 实际加载）

| 项 | 值（基线 v2 实测） |
|---|---|
| SDK `.so` 路径 | `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0` |
| SDK SHA-256 | `028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48` |
| SDK SONAME | `libkysdk-coreai-embedding.so.1` |
| SDK 版本 | `1.2.0.0-0k0.4` |
| runtime 版本 | `kylin-ai-runtime 1.2.0.4-0k0.1` |
| 默认模型 | `ensemble-embd_gte-base_uint8-text`（dim=768, ondevice=True） |

**验证**（clean VM）：SDK 由**独立 embedding server 进程**实际加载；定位**独立
embedding server PID**，`grep -F '.so' /proc/<embedding_pid>/maps` 中实际加载路径/hash
必须与上表一致（**非 gateway 单 PID 自加载**）。

---

## 6bis. BLOCKER C — runtime/model 冻结身份（v5：正式 G0 冻结）

- v4 曾将 runtime/model **identity / version / hash / vendor-frozen lock** 记为
  **HANDOFF_REQUIRED**；该状态由正式 D14D G0 证据与 2026-09-10 Reviewer E identity
  adjudication 解除。
- 本节身份只声明外部依赖的冻结输入，不改变 L3 证据边界，不宣称
  `release_ready=true` 或 `production_ready=true`。
- 不得伪造 runtime/model version、hash、vendor lock、reviewer 会签或麒麟 evidence；
  不由本文档或本 Task 补写虚构的 runtime/model version/hash/vendor lock/D Reviewer 会签。
- 解除依据：
  `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/dependency_identity.json`
  及其原始 `raw/g0_baseline.log`、`raw/g0_packages.log`；contract 证据校验记录见
  `evidence/d15d-lock/20260910T142417Z/c10_contract_closure.md`。
- D14D G0 冻结身份如下：

| Component | Version | Path | SHA-256 |
|---|---|---|---|
| SDK canonical `.so` | `1.2.0.0-0k0.4` | `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0` | `028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48` |
| Runtime binary | `kylin-ai-runtime 1.2.0.4-0k0.1` | `/usr/bin/kylin-ai-runtime` | `b3f83fc90966394e7397979945f324a4691a208a1b944ed1c2488b20b296e225` |
| GTE ONNX model | `kylin-gte-base-model 1.0.0.1-0k0.9` | `/usr/share/kylin-ai/model-repository/embd_gte-base_uint8-text/1/gte-base-multilingual-model_QUInt8.onnx` | `cef0fc76165ee5bb4f3da5ab6b9b6e6fdfdd278d3077f2db2d4a6cde4d4c32b1` |

---

## 7. Install 契约（`systemd/install.sh`）

```bash
EXPECT_SOURCE_COMMIT=<40位完整 source commit> bash systemd/install.sh install
# EXPECT_SOURCE_COMMIT：必填（fail-closed），必须为 40 位完整 SHA，且必须等于被安装
#   正式 package 的 manifest.source_commit——即该正式 package 对应的 source identity
#   （构建声明基线，见 §1.1）；该值由调用方对正式 package 显式可信提供，不得从
#   checkout/被测包推断、不得使用短 SHA、不得使用不解释来源的占位符；无 optional
#   语义，缺失/格式错误/与 manifest 不匹配均为 fail-closed 拒绝。
# 动作:
#   1. 校验 EXPECT_SOURCE_COMMIT 与 manifest.source_commit 绑定（fail-closed）＋
#      manifest/SHA256SUMS 校验（与已冻结 hash 一致）
#   2. SDK（§3/§6）存在 + exact package version + SHA-256（fail-closed）；
#      runtime/model 身份按 §6bis v5 冻结；本版仍不对 runtime/model 做 hash Gate
#   3. 整包复制到 <install_prefix>（${XDG_DATA_HOME:-$HOME/.local/share}/kylin-memory-d14a）；
#      $HOME/.local/bin 创建 launcher symlink 指向 <install_prefix>/bin/kylin-memory-server；
#      unit 渲染 ExecStart=<install_prefix>/bin/kylin-memory-server（安装前缀 launcher）
#   4. systemctl --user daemon-reload && enable --now kylin-memory
#   5. wait socket + journal "Memory Service 就绪"
#   6. restart 后再次 status_check
```

## 8. Uninstall / Rollback 契约（`systemd/uninstall.sh`）

```bash
bash systemd/uninstall.sh rollback [--keep-unit]
# 停止 + 禁用 + 恢复备份 / 删除；确认服务不再 active
```

## 9. Verify / Smoke 契约（`systemd/verify.sh`）

```bash
# 前置步骤（必需）：install 完成（§7）→ 启动真实独立 embedding server（正式发布包
#   runtime venv 的 `python -m embedding.server`）→ 取得其真实 PID → embedding.sock
#   就绪后，执行：
bash systemd/verify.sh --embed-socket <EMBED_SOCK> --embed-pid <REAL_EMBEDDING_SERVER_PID>
# --embed-pid：必填（fail-closed），必须是独立 embedding server 进程的真实 PID
#   （SDK 由它实际加载），不是 gateway PID、不是随便选择的 Python PID——错误 PID
#   会在 /proc/<embedding_pid>/maps 的 SDK 路径/SHA Gate FAIL。
# 1. systemctl --user is-active
# 2. socket 存在且 holder PID 与 unit MainPID 一致
# 3. /proc/<embedding_pid>/maps 中 SDK .so 实际加载路径 + hash = §6
#    （SDK 由独立 embedding server 进程实际加载并经 embedding PID 校验，非 gateway 单 PID 自加载）
# 4. 真实 SDK smoke：memory.embed 返回 dim=768（fake=false）
# 5. cmdline / cwd 不含源码 checkout 与个人 venv
```

---

## 10. Manifest / Hash

- `manifest.json`：`{source_commit, package_version, built_at, files:{path:{size,sha256}}, sdk:{...}, model:{...}}`
- `SHA256SUMS`：打包后生成，作为正式 evidence 的 package 身份。
- 后续任何 VM 测试只允许引用该 hash；若补文件 → 重新打包 → 新 hash → 重置 snapshot → 重测。
- 任何 packaging/runtime 行为变更必须 **重新打包 → 重算 hash → 重跑真实 VM**，并回填 §1.1 身份表。
- **当前声明**：当前冻结包身份为 §1.2 的 D14D formal frozen tar；其 `tested_runtime_commit`
  为 `ba3b50e…`，evidence root 已由 PR #165 入库。相对当前 `git rev-parse HEAD` 的
  新鲜性由守卫 live 三分类判定；本契约不再声明历史 v4 的 `RUNTIME_EVIDENCE_STALE`
  作为当前状态。

---

## 11. 验收 Gate（D14A READY 前置）

- [x] contract SIGNED v5 / REVIEWER_E_IDENTITY_ADJUDICATION_APPROVED / G_D7_SIGNED（2026-09-10 已同步 D14D `ba3b50e` formal identity；
  既有 `Ducknesses` 授权评论仅保留为 invalid historical authority record；Reviewer E 已在
  PR comment 5616426125 独立裁定 identity/provenance closure APPROVED，D15D/G-D7
  最终签署由 review `5168962906` 完成）
- [x] 本地/L1 package smoke PASS（D14D G3/G4：package-only install → real SDK
  smoke → restart；evidence root 见 §1.2）
- [x] dependency audit PASS（D14D G2 无开发路径/RPATH/not-found）
- [x] clean-VM L3：package-only install + real SDK + restart + OS reboot（D14D
  G3/G4/G5/G6 PASS；G7/G8 不在已验证范围）
- [x] L3 evidence 完整（D14D evidence root 23/23 checksums OK；Reviewer E 已专项
  接受 identity/provenance closure，但不因此升级 release/production claim）

> Gate 边界：contract 已按 2026-09-06 D-03/D-04 裁决升 **FROZEN v4**，并于
> 2026-09-10 按 ReviewerE identity adjudication 以 D14D G0 证据形成 **SIGNED v5 / G_D7_SIGNED**。本 Gate 清单与
> 全文不产生任何状态越级声明
> （既不宣称宿主环境已验证，也不宣称三级验收通过），v5 仅冻结 §6bis 外部依赖身份。
> 备注：上述 Gate 引用的是 D14D formal evidence root 对同一 `ba3b50e` frozen tar
> 的既得结果，不是新 PR HEAD 的重跑结果。第 4 轮 main drift 后，当前 frozen
> package lock 对 current main 为 `RUNTIME_EVIDENCE_STALE_AGAINST_CURRENT_MAIN`;
> 任何 runtime/packaging 漂移仍触发 §1.1 的重打包与真实 VM 重测规则。

## 12. Evidence 输出（`evidence/l3-kylin-vm/d14a_<run_id>/`）

```text
environment.json  git_identity.json  package_manifest.json  SHA256SUMS
install.log  install_result.json  service_identity.txt  sdk_model_identity.json
real_sdk_smoke.json  dependency_audit/{ldd,readelf,path_scan}.txt
recovery/{service_restart,process_crash,bridge_recovery,stale_socket}.log
performance/{embedding,bridge,ipc,index_backlog}/
cleanup.log  summary.json
```

并登记 `evidence/index.yaml`（SHA-256）。

---

*本契约 v4 溯源收口（FROZEN）已于 2026-09-06 依 D14D 人工裁决 D-03/D-04 会签。*
