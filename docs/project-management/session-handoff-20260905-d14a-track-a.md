# 项目整体交接文档（A 轨视角 · 2026-09-05）

> 适用：下一会话（审查其他分支 + 处理其他分支任务）
> 编制：A 轨刘依枫（opencode）
> 基线：`main@5424d28`（D13A 合并后）；D14A 分支 `release/D14A-clean-vm-package@68bb8f7`（未合并，PR #152）
> 目标：让下一会话快速掌握项目全貌、各轨道进度、A 轨资产、待审查分支清单与任务队列

---

## 0. 项目一句话

麒麟 OS Agent 记忆系统（kylinOS-agent-memory）：为麒麟 AI 助手提供偏好/知识记忆的持久化、
检索、遗忘与安全治理服务。五轨道（A/B/C/D/E）并行，每轨负责垂直切片，D12 功能冻结后进入
D13 评测、D14 发布回归。

---

## 1. 轨道职责速查

| 轨道 | 职责 | 核心代码域 |
|---|---|---|
| **A**（刘依枫） | Embedding SDK + Bridge + Provider/抽取 + 性能/发布包 | `memory-service/providers` `memory-service/embedding` `cpp-bridge` `packaging/release` |
| **B**（高翌哲） | Retrieval/Vector/FTS5/RRF + 评测 | `memory-service/retrieval` `tests/vector-engine` `evaluation` |
| **C**（刘承恩） | OS Agent/MemoryClient/QML + Host 契约 | `memory-client` `os-agent-integration` |
| **D** | IPC/Gateway/Outbox/SQLite/迁移 | `memory-service/gateway` `db` `outbox` `migrations` |
| **E**（谢嘉然） | 业务语义/安全/评测契约 | `memory-service/domain` `security` `service` |

---

## 2. 当前 Git 状态

### 2.1 main（`5424d28`，D13A 合并后）

关键近期提交（倒序）：
```
5424d28 perf: D13A 性能基线与高压负载测试 (#147)
2cba011 test(D13C): D-track L2 evidence collector (#149)
7242935 fix(D12D): 防护 event.ingest 字段漂移 (#143)
adec5b4 docs: 审计D12E合并后剩余关闭项 (#144)
b2347b4 fix(C): resolve 3 field drifts (#142)
889b755 fix(embedding): accept-stop/thread-start lifecycle races (#141)
1a85704 fix(A): DRIFT-001 captured_at Canonical (#135)
d5e3b0f fix(retrieval): D12B 字段漂移 - 评测枚举 Canonical 同源 (#138)
f263d5b E: d12 business schema drift remediation (#137)
```

### 2.2 本地分支

| 分支 | HEAD | 状态 |
|---|---|---|
| `main` | 5424d28 | 已同步 origin |
| `fix/a-track-schema-drift-captured-at` | 62376bc | 已合入 main（1a85704），可删 |
| `release/D14A-clean-vm-package` | **68bb8f7** | **当前分支，PR #152 待复审** |
| `docs/day1-baseline-deliverables` | — | 历史遗留 |

### 2.3 工作区未跟踪（3 个交接文档，勿误提交）

```
A轨_真实SDK交接清单_20260903.md
D11E_A轨需求分析与测试计划报告_20260903.md
PR_DESCRIPTION_A_TRACK_SCHEMA_DRIFT.md
```

---

## 3. A 轨已完成资产（可复用的关键证据/代码）

### 3.1 已合入 main

| 资产 | commit/PR | 说明 |
|---|---|---|
| D12A SDK 超时/异常恢复/性能抖动 | `22cb497` (#100) | Embedding executor 挂死恢复 + Bridge 审计 + 异常输入回归；L2 7/7 |
| DRIFT-001 captured_at Canonical | `1a85704` (#135) | `TurnFinalizedEvent.captured_at` + schema drift 门禁测试 |
| D13A 性能基线 | `5424d28` (#147) | `scripts/run_day13a_benchmarks.sh` + `bench_*` 全套 |
| A-REQ-01 outbox 死循环修复 | `10b0289` (#113) | embedding deletion consumer |

### 3.2 D14A 分支（PR #152，未合并）

| 资产 | 位置 | 说明 |
|---|---|---|
| Release package contract | `docs/day14/00_d14a_release_package_contract.md` | FROZEN_DRAFT v1 |
| 构建器 | `packaging/release/build_release_package.sh` | Git 身份 Gate + migration smoke + manifest/SHA256SUMS |
| systemd install/uninstall/verify | `packaging/release/` | 无开发目录依赖；verify 校验 PID/SDK SHA/embed |
| 自动化 smoke | `packaging/release/package_smoke.sh` | 全链 EXIT=0（install→migrate→start→verify→restart→rollback） |
| L3 evidence | `evidence/l3-kylin-vm/d14a_20260905/` | 16 文件，tested_commit 可追溯 |
| 实施报告 | `docs/day14/01_d14a_implementation_report_20260905.md` | 状态 PACKAGE_IMPLEMENTATION_CANDIDATE |

**D14A 冻结身份**：package `0.1.0-d14a`；`source_commit=e3d4b9d565e2c3c153973125b3c071225e1b9e4d`；
package_tar_sha256 `15d79383…`；manifest_sha256 `18475655…`；bridge_so `a2718912…`。

### 3.3 关键 SDK 事实（麒麟 VM）

- SDK：`libkylin-coreai-embedding 1.2.0.0-0k0.4`，`.so` `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0`，SHA `028e7099…`
- runtime：`kylin-ai-runtime 1.2.0.4-0k0.1`（内部自报 1.3.0，PARTIAL 已知）
- 模型：`ensemble-embd_gte-base_uint8-text`（dim=768, ondevice）
- Bridge：`cpp-bridge/build-d14a*/kylin_embedding.cpython-312-x86_64-linux-gnu.so`

---

## 4. 待审查分支清单（下一会话重点）

按最近活动排序，附审查关注点：

| 分支 | 最近活动 | 审查关注点 |
|---|---|---|
| `release/D14A-clean-vm-package` | 2026-09-05 | **本分支 PR #152**：发布链 smoke/evidence 已按 REWORK 修复，待 D 主审确认 |
| `test/D11E-vm-business-acceptance` | 2026-09-03 | D11E 业务验收：A1/A2/A3 真实 SDK 复跑需求（A 轨回填） |
| `fix/D12D-stability-gate` | 2026-09-03 | D12D Path C：install/restart/rollback/reinstall 证据 |
| `test/D13C-session-eval` | 2026-09-03 | D13C 会话评测（#149 已合 main） |
| `test/D14B-l3-vm-release-regression` | 2026-09-02 | **D14B**：需 A 发布包作为上游输入（见 §6） |
| `fix/day12a-sdk-stability` | 2026-09-02 | 已合入 main（22cb497），历史分支 |
| `feat/C-d11-e2e-orchestrator` | 2026-09-02 | C 轨 D11 E2E |
| `feat/d10d-build` | 2026-09-02 | D10D PR #139 线程竞态 |
| `docs/d8d-adr017-018-freeze` | 2026-09-02 | ADR-017/018 冻结（已合 main） |

---

## 5. 各轨道当前阶段（D13/D14 全景）

| 轨道 | D13 状态 | D14 状态 |
|---|---|---|
| A | ✅ D13A 性能基线已合（#147） | 🚧 D14A 发布包 PR #152 待复审；L3 clean-VM 待 D14D 快照 |
| B | ✅ D13B 封存评测（#123） | 🚧 D14B L3 发布回归（待 A 包 + D14D 快照） |
| C | ✅ D12 字段漂移修复（#140/#142） | —（随 A/D 发布包） |
| D | ✅ D13C 评测证据（#149） | 🚧 D14D 干净快照/L3 发布生命周期（A/B/C 的上游） |
| E | ✅ D12E 业务冻结（#137） | —（随 A 发布包验收） |

---

## 6. 跨轨依赖与阻塞点

| 依赖 | 责任 | 状态 |
|---|---|---|
| A 发布包 → B（D14B 回归） | A | ✅ 包已建（PR #152）；正式 L3 待 B/D 消费 |
| D14D 干净快照 → A/B（正式 L3） | D | ⏳ 未冻结（PR #150 D13D 也是 Draft） |
| D13D 冻结环境 → A/B（正式 L3 门槛） | D | ⏳ Draft/PREPARED |
| Kaiming 打包（A14-B07） | A | ⏳ deferred，待 D 主审确认是否 D14A 必交 |

---

## 7. A 轨下一步任务（按优先级）

1. **D14A 复审收尾**：等待 D 主审对 PR #152 的 REWORK 复审；若通过则 D14A 进入
   READY_CANDIDATE → 交接发布包给 B/D（D14B/D14D）。
2. **正式 L3 clean-VM 回归**（D14D 快照就绪后）：用 `package_smoke.sh`/`verify.sh` 复跑，
   并执行 D13A 可比性能（`scripts/run_day13a_benchmarks.sh`），与 D13A 账本对照。
3. **D11E 任务卡回填**（A1/A2/A3）：D11E 要求同 Commit 真实 SDK 证据；当前已有
   `evidence/l3-kylin-vm/d14a_20260905/` 可作回填素材，需补 tested_commit 对齐。
4. **performance regression budget 冻结**：向 D 主审申请冻结（低/中并发无新错误、P95 无
   不可解释回退、c16 饱和错误保留不崩溃）。

---

## 8. 麒麟 VM 操作备忘（下一会话）

```
SSH:   ssh -p 2222 Lyf@127.0.0.1    密码: 12345678.
共享:  /mnt/shared = vboxsf 挂载（Lyf 已在 vboxsf 组，可读写；但 vboxsf 不支持符号链接，
       故 venv/发布包必须在 /tmp 或 $HOME 本地盘构建）
Python: /usr/bin/python3.12（唯一可用 3.12）；venv 用 python3.12 -m venv
SDK:   /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0
构建发布包: cd /mnt/shared && bash packaging/release/build_release_package.sh --source-commit <HEAD>
smoke:  INSTALL_PREFIX=... bash packaging/release/package_smoke.sh --package <pkg-dir>
Posh-SSH 备忘: Set-SCPItem 只能传单文件到已存在目录；vboxsf 目录 SCP 不可靠，优先用 /tmp
```

---

## 9. 纪律提醒（历史教训）

1. **vboxsf 不支持符号链接**：venv 复制必须用 `tar` 管线（cp -a 会因 symlink 失败）。
2. **install_prefix 方案**：整包安装到 `<prefix>`，`~/.local/bin` 做 symlink，unit 渲染
   `ExecStart=<prefix>/bin/...`——不要靠 launcher `$0` 重定位（被复制后会失效）。
3. **embedding.sock 放 /tmp**：避免被 systemd `RuntimeDirectory` 清理。
4. **Git 身份 Gate**：打包脚本 `source_commit` 需与 HEAD 一致（展开完整 40 位 SHA 比较）。
5. **迁移 env.py**：打包时确定性重写（cwd 即 runtime/app），勿用多次字符串 replace。
6. **evidence 诚实**：状态如实降级（PACKAGE_IMPLEMENTATION_CANDIDATE），无实测不写 VERIFIED。
7. **LF 行尾**：evidence 从 VM 拉取为 LF，git 可能转 CRLF（警告无害，但勿手动改内容）。
8. **SCP 到 vboxsf 不可靠**：小文件直接 SCP 到 `/tmp` 再 cp，或用 base64 经 SSH 写入。

---

## 10. 参考文档索引

| 文档 | 位置 |
|---|---|
| Git 规范 | `docs/project-management/git-conventions.md` |
| 历史交接 | `docs/project-management/session-handoff-*.md` |
| D14A 契约 | `docs/day14/00_d14a_release_package_contract.md` |
| D14A 实施报告 | `docs/day14/01_d14a_implementation_report_20260905.md` |
| D14B 工作清单 | `docs/day14/01_d14b_l3_vm_release_regression_worklist_20260902.md`（D14B 分支） |
| D13A 性能 | `scripts/run_day13a_benchmarks.sh` + `docs/day13/` |
| 技术债 | `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` |

---

*交接完毕。下一会话可据此开展其他分支审查与任务处理。*