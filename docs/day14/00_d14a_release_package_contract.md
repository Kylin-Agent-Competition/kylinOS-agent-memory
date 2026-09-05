# D14A Release Package Contract（FROZEN_DRAFT · 溯源收口 v3）

> 依据：D14A 交接文档（2026-09-05）§Phase 2 + §A14-B01 解除要求。
> 状态：**FROZEN_DRAFT**（待 D 主审会签后升 FROZEN；**D Reviewer 会签前不得升 FROZEN**）。
> 冻结方式：本文件为 package contract 唯一真源；任何字段改动需 D 主审会签并升版。
> v3 溯源收口：新增 §1.1 Provenance 四身份语义、§6bis BLOCKER C，并修正安装/verify
> 架构描述（整包复制 install_prefix + `~/.local/bin` symlink + 安装前缀 launcher +
> 独立 embedding server PID 实际加载校验）。

---

## 0. 目的

定义 A 轨「正式发布包」的内容、身份、安装、验证与回退契约，使：
- 干净 VM 仅凭发布包 + 声明的前置依赖即可完成 install → start → real SDK smoke → restart → status；
- **不依赖**源码 checkout、个人 venv、开发者 HOME 下的残留；
- Bridge/SDK/model/runtime 的身份可追溯（声明的即实际加载的）。

---

## 1. Package Identity（冻结字段）

| 字段 | 值 | 说明 |
|---|---|---|
| `package_name` | `kylin-memory-a-d14a` | A 轨发布包名 |
| `package_version` | `0.1.0-d14a` | 首个 D14A 版本 |
| `source_commit` | **`5424d28e1178d3d16764ad7c050b878bc8981583`** | **构建声明基线**（仅声明打包基线，非执行/证据/当前 head）；若 main 前移，开工前重新冻结；四身份语义见 §1.1，禁止互相伪造相等 |
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

## 1.1 Provenance 身份语义（四类字段，禁止互相伪造相等）

| 身份字段 | 值（40 位 SHA） | 语义 |
|---|---|---|
| `source_commit` | `5424d28e1178d3d16764ad7c050b878bc8981583` | **构建时声明基线**（非执行/证据/当前 head） |
| `tested_runtime_commit` | `e3d4b9d565e2c3c153973125b3c071225e1b9e4d` | 历史 runtime 包在真实 VM **实际执行**的提交 |
| `evidence_commit` | `68bb8f764e204818759fceae0616cac0048753a2` | evidence-only 快照提交 |
| `current_pr_head` | `15de7c67426909c7c872f9cb3f9a04a2575753fd` | **动态值**：R2 开工基线；随新提交前移时必须回填本表并同步测试断言 |

- 四者独立，**不得互相伪造相等**；尤其**不得把 `tested_runtime_commit` 写成当前 PR head**。
- 经 `git diff --name-only` 复核：`e3d4b9d565e2c3c153973125b3c071225e1b9e4d..15de7c67426909c7c872f9cb3f9a04a2575753fd`
  范围内**无 D14A packaging/runtime 行为文件变化**（仅 docs/evidence 与 main 合入的
  memory-client/D13E/CI 等非 D14A runtime 内容）。
- 任何后续 **packaging/runtime 行为变更**必须 **重新打包 → 重算 hash → 重跑真实 VM** →
  回填新的 `tested_runtime_commit` / `evidence_commit`；仅文档/测试变更不触发重包，
  但 `current_pr_head` 前移时必须复核本表。

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
libkylin-coreai-embedding = 1.2.0.0-0k0.4   (amd64)
kylin-ai-runtime         = 1.2.0.4-0k0.1
kylin-gte-base-model     = 1.0.0.1-0k0.9
python3.12               (系统 python，用于创建包内 venv)
```

> 安装入口脚本对每个前置依赖执行存在性 + 版本 + SHA-256 校验，缺一即 fail-closed。

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

## 5. Dependency Audit（打包时强制）

| 检查 | 命令 | 必须结果 |
|---|---|---|
| Bridge 动态依赖 | `ldd runtime/bridge/kylin_embedding*.so` | 无 `not found`；全部 NEEDED 可解析 |
| RPATH/RUNPATH | `readelf -d ... \| grep -E 'RPATH\|RUNPATH'` | 无开发机绝对路径 |
| 硬编码路径 | `grep -RInE '(/home/\|/Users/\|[A-Za-z]:\\\|.venv\|d4d-venv\|PYTHONPATH\|--repo\|build/)' runtime/ packaging/` | 无个人开发目录命中（或逐条登记结论） |
| SDK 身份 | `sha256sum` + `readelf -d` SONAME | = 合同 §6 |

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

## 6bis. BLOCKER C — runtime/model 冻结身份缺失（DEPENDENCY_BLOCKED / HANDOFF_REQUIRED）

- runtime/model **identity / version / hash / vendor-frozen lock** 尚无 D Reviewer 接受的
  可信外部冻结输入，状态 **DEPENDENCY_BLOCKED / HANDOFF_REQUIRED**（fail-closed）。
- 不得伪造 runtime/model version、hash、vendor lock、D Reviewer 会签或麒麟 evidence；
  不由本文档或本 Task 补写虚构的 runtime/model version/hash/vendor lock/D Reviewer 会签。
- 解除条件：外部可信冻结输入 + D Reviewer 会签后，回填本表并升版。
- 解除前，安装 Gate（§7）与任何验收声明**不得宣称 runtime/model identity 闭环**。

---

## 7. Install 契约（`systemd/install.sh`）

```bash
bash systemd/install.sh install
# 动作:
#   1. 校验前置系统依赖（§3）存在 + 版本 + SHA-256（fail-closed）
#   2. 校验 package manifest/SHA256SUMS（与已冻结 hash 一致）
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
bash systemd/verify.sh
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

---

## 11. 验收 Gate（D14A READY 前置）

- [ ] contract FROZEN（D 主审会签）
- [ ] 本地/L1 package smoke PASS（build → install → start → real SDK smoke → restart → rollback）
- [ ] dependency audit PASS（无开发路径/RPATH/not-found）
- [ ] clean-VM L3：package-only install + real SDK + recovery + D13A 可比性能
- [ ] L3 evidence 完整（§12）

> Gate 边界：contract FROZEN 仅可由 D 主审会签后达成（当前维持 **FROZEN_DRAFT**，
> D Reviewer 会签前不得升 FROZEN）；本 Gate 清单与全文不产生任何状态越级声明
> （既不宣称宿主环境已验证，也不宣称三级验收通过），且 BLOCKER C 解除前不得
> 宣称 runtime/model identity 闭环。

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

*本契约 v3 溯源收口（FROZEN_DRAFT）由 A 轨编制，D Reviewer 会签前不得升 FROZEN。*