# D14A 实施报告 v2（REWORK 修复后，2026-09-05 · 溯源收口 v4）

> 对应 D14A 交接文档 + 台账 D14-A「L3 干净虚拟机发布回归」。
> 本报告为 D14A 第一阶段（发布包构建 + 发布链验证）完成记录；正式 L3 clean-VM
> 回归待 D14D 干净快照 + D13D 冻结环境就绪后执行。
> **状态：PACKAGE_IMPLEMENTATION_CANDIDATE**（按 D 主审 BLOCKER 5 口径；正式 L3 前不升
> READY；BLOCKER C（见 §6）解除前不宣称 runtime/model identity 闭环）。
> **2026-09-06 仲裁收口**：契约 §3/§6bis 按 D14D 人工裁决 D-03 统一为
> `HANDOFF_REQUIRED`（SDK 全量 fail-closed；runtime/model 由正式 D14D G0 采集冻结后
> 回填升版）；契约依 D-03/D-04 以 v4 升 **FROZEN**；正式 package version 依 D-05 固定
> `0.1.0-d14a`。BLOCKER C 不再以 DEPENDENCY_BLOCKED 阻塞 packaging 代码线收敛，但仍
> 未解除，不得宣称 runtime/model identity 闭环。
> **证据新鲜性（执行时事实）**：当前 runtime evidence 相对本 PR HEAD
> （`git rev-parse HEAD` 执行时事实）为 **RUNTIME_EVIDENCE_STALE / RUNTIME_UNVERIFIED**——
> 需重新打包 → 重算 hash → 真实 VM 重测并回填 `tested_runtime_commit` /
> `evidence_commit` 后方可更新；正式刷新明确超出本 Task 且尚未执行。
> **Historical result only**：本报告 §1/§2/§4（以及 §3 身份表、§5 evidence）中的
> 历史 runtime / package smoke 结论均为**历史证据**——实际发生在
> `tested_runtime_commit=e3d4b9d565e2c3c153973125b3c071225e1b9e4d`
> （历史真实 VM 实际执行提交），**does not prove current HEAD**；历史 PASS 仅表示
> 历史 commit 上实际发生的结果，不表示当前 PR head PASS；当前 HEAD 状态继续为
> **RUNTIME_EVIDENCE_STALE / RUNTIME_UNVERIFIED**（归因见 §5.1 A/B）。
> v4 溯源收口：§3 四身份模型中 `current_pr_head` 不再落库固定 SHA，改以
> `git rev-parse HEAD` 执行时事实为唯一真源；§5.1 复核改为执行时三分类
> （EVIDENCE_CURRENT / DOCS_EVIDENCE_ONLY / RUNTIME_EVIDENCE_STALE）并如实记录
> 当前真实分类；§4 修正 verify 为独立 embedding server PID 实际加载校验表述，
> §6 新增/维持 BLOCKER C；不改变既有 REWORK 事实与候选状态。

---

## 1. REWORK 处置摘要

D 主审 5 个 BLOCKER 全部处置并重新验证：

| BLOCKER | 处置 | 验证 |
|---|---|---|
| B1 launcher/install_prefix 失效 | 整包复制到 `<install_prefix>`；`~/.local/bin` 做 launcher symlink 指向 `<install_prefix>/bin/kylin-memory-server`；unit 渲染 `ExecStart=<install_prefix>/bin/kylin-memory-server`（安装前缀 launcher） | smoke：unit 正确渲染 + 服务从 prefix 启动 + socket 就绪 |
| B2 缺 Alembic 迁移 + env.py 重写错误 | install 前 `alembic upgrade head`；env.py 改为确定性重写（cwd 即 runtime/app）；构建时包内 migration smoke | migration head `20260902_add_memory_relation_conflict`；smoke PASS |
| B3 install/verify fail-closed 缺失 | install 校验 SDK 版本+SHA/manifest；wait socket/journal/restart；verify 校验 PID==MainPID/cmdline/SDK SHA/memory.embed | smoke 全链 PASS |
| B4 evidence 身份不一致 | 从 `e3d4b9d`（当时最终 head）重建 evidence；`manifest.source_commit` 记录该历史 head 的完整 40 位 SHA | 按 §3 四身份语义，该值归位为 tested_runtime_commit（真实 VM 实际执行提交），不得写成当前 PR head；证据文件已重建；该 evidence 相对后续 PR head 为 STALE（见 §5.1），刷新属后续独立事项 |
| B5 evidence 格式/语义 | 修复 JSON；补全 install/smoke/service identity/dependency audit；状态降级 | 16 个 evidence 文件全部合法 |

> **Historical evidence（就地标记）**：上表 B1–B5 的全部处置验证均为**历史
> smoke/package 结论**，实际发生在
> `tested_runtime_commit=e3d4b9d565e2c3c153973125b3c071225e1b9e4d`
> （历史真实 VM 实际执行提交）；仅表示历史 commit 上实际发生的结果，
> **does not prove current HEAD**——当前 HEAD 为 RUNTIME_EVIDENCE_STALE /
> RUNTIME_UNVERIFIED（归因见 §5.1 A/B）。

---

## 2. 完成情况总览

| 交接要求 | 状态 | 证据 |
|---|---|---|
| 冻结 release package contract | ✅ | `docs/day14/00_d14a_release_package_contract.md` |
| 构建正式发布包（无源码/无个人 venv 依赖） | ✅ | `dist/kylin-memory-a-d14a-0.1.0-d14a/`（87MB，3360 文件） |
| 消除个人开发目录依赖 | ✅ | launcher 可重定位；`ldd` 0 not-found；无 RPATH |
| 发布链（install→migrate→start→verify→restart→rollback） | ✅ | `package_smoke.sh` 全链 EXIT=0 |
| 真实 SDK 调用 | ✅ | `memory.embed` dim=768，非 fake；SDK SHA 校验 |
| 异常恢复（restart） | ✅ | restart 后 verify 全 PASS |
| 性能基线 | ⏳ | 单次 embed 205.5ms/restart 后 2.1ms；D13A 可比基准待 L3 |
| A READY 声明 | ⏳ | 待 D 主审 + L3 clean-VM + D13A 性能回归 |

> **Historical evidence（就地标记）**：上表 ✅ 完成项（冻结 contract / 构建正式包 /
> 消除开发目录依赖 / 发布链 install→migrate→start→verify→restart→rollback /
> 真实 SDK 调用 / 异常恢复 restart）均为**历史 runtime/package smoke 结论**，
> 实际发生在 `tested_runtime_commit=e3d4b9d565e2c3c153973125b3c071225e1b9e4d`
> （历史真实 VM 实际执行提交）；历史 PASS 仅表示历史 commit 上实际发生的结果，
> **does not prove current HEAD**——当前 HEAD 为 RUNTIME_EVIDENCE_STALE /
> RUNTIME_UNVERIFIED，正式重打包 → 重算 hash → 真实 VM 重测并回填新
> tested_runtime_commit 属后续独立事项（尚未执行）。

---

## 3. 发布包身份（四身份模型，禁止互相伪造相等）

| 项 | 值 |
|---|---|
| package_name / version | `kylin-memory-a-d14a` / `0.1.0-d14a` |
| **source_commit**（构建声明基线） | **`5424d28e1178d3d16764ad7c050b878bc8981583`**（与契约 §1.1 口径一致；非执行/证据/当前 head） |
| **tested_runtime_commit**（真实 VM 实际执行） | **`e3d4b9d565e2c3c153973125b3c071225e1b9e4d`**（原报告 §3 误标为 source_commit 的值，语义修正） |
| **evidence_commit**（evidence-only 快照） | **`68bb8f764e204818759fceae0616cac0048753a2`** |
| **current_pr_head**（动态） | **`<git rev-parse HEAD 输出>`**（执行时事实：本表不落库固定 SHA，以 `git rev-parse HEAD` 输出为唯一真源；随新提交前移，禁止把 `tested_runtime_commit` 写成 current_pr_head） |
| package_tar_sha256 | `15d79383f5aed05407d849cf5dfafe6ab2195a80ee42d987294747c6f74081ce` |
| manifest_sha256 | `18475655969b8fb6c88820d9e3ee94dc9c5e17a4e2c533b4cf65be46cb46ef22` |
| bridge_so_sha256 | `a271891238102d0299395284d486c2e5afdaa4494e6ab0d1ff51a2d2ab9d4db6` |
| SDK `.so` | `/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0` sha `028e7099…` |
| SDK 版本 | `libkylin-coreai-embedding 1.2.0.0-0k0.4` |
| runtime | `kylin-ai-runtime 1.2.0.4-0k0.1`（内部 1.3.0，PARTIAL 已知） |
| model | `ensemble-embd_gte-base_uint8-text`（dim=768） |

> 四身份相互独立，**不得互相伪造相等**；尤其**不得把 `tested_runtime_commit` 写成当前 PR head**。
> 历史 evidence（`evidence/l3-kylin-vm/d14a_20260905/`）中 `git_identity.json` / `summary.json`
> 记录的 `source_commit=tested_commit=e3d4b9d…`，在四身份语义下归位为 **tested_runtime_commit**
> （真实 VM 实际执行提交），不修改历史 evidence 文件本身。

---

## 4. 发布链验证（`package_smoke.sh` 全链 EXIT=0）

```
package: /tmp/kylin-d14a-dist/kylin-memory-a-d14a-0.1.0-d14a
[install] manifest core files verified
[install] Alembic migration upgrade head -> alembic_version=20260902_add_memory_relation_conflict
[install] journal: Memory Service 就绪
[install] restart 验证 -> 服务 active, socket 就绪
[verify]  PASS: service active
[verify]  PASS: socket holder = MainPID
[verify]  PASS: cmdline 指向发布包 venv（无开发目录依赖）
[verify]  PASS: 真实 SDK memory.embed dim=768 (latency 205.5ms)
[verify]  PASS: 独立 embedding server PID 实际加载 SDK 校验（/proc/<embedding_pid>/maps 路径+SHA = 契约 §6，非 gateway 单 PID 自加载）
[verify]  ALL PASS
[restart] verify 再次 ALL PASS (embed dim=768, latency 2.1ms)
[rollback] symlink/unit/install_prefix 清理完成
ALL PASS: install → migration → start → verify(real SDK) → restart → rollback
```

> **Historical evidence（就地标记）**：以上 ALL PASS 发布链输出为**历史 smoke 日志**，
> 实际发生在 `tested_runtime_commit=e3d4b9d565e2c3c153973125b3c071225e1b9e4d`
> （历史真实 VM 实际执行提交），仅表示历史 commit 上实际发生的结果，
> **does not prove current HEAD**；当前 HEAD 为 **RUNTIME_EVIDENCE_STALE /
> RUNTIME_UNVERIFIED**（归因见 §5.1 A/B），不描述为"与当前 head 一致"。

---

## 5. Evidence（`evidence/l3-kylin-vm/d14a_20260905/`）

```
environment.json  git_identity.json  package_manifest.json  SHA256SUMS
package_identity.json  real_sdk_smoke.json  sdk_model_identity.json
service_identity.txt  smoke.log  summary.json
dependency_audit/{ldd,readelf,path_scan}.txt
recovery/{service_restart,process_crash,stale_socket}.log
```

全部 JSON 合法；`git_identity.json` 与 `summary.json` 记录的
`source_commit=tested_commit=e3d4b9d…` 即 **tested_runtime_commit**（§3 归位），
`evidence_commit`（68bb8f7…）为证据落库快照，`current_pr_head` 为执行时
`git rev-parse HEAD` 动态事实（**不落库固定 SHA，也不把 tested_runtime_commit
写成 current_pr_head**）；四者不得互相伪造相等。

**证据新鲜性声明**：上述历史 evidence 均在 `tested_runtime_commit`（e3d4b9d…）
上执行；当前 PR HEAD 相对该提交已引入 packaging/runtime 行为变更（§5.1），
因此这些历史 evidence 相对当前 head 为 **RUNTIME_EVIDENCE_STALE / 未刷新**——
不描述为"与当前 head 一致"，正式刷新属后续独立事项（超出本 Task 尚未执行）。

---

## 5.1 git diff 三分类复核结论（tested_runtime_commit → 当前 PR head，执行时判定）

复核命令：`git diff --name-only tested_runtime_commit..HEAD`（`tested_runtime_commit`
为 §3 表中 `e3d4b9d565e2c3c153973125b3c071225e1b9e4d`；`HEAD` 为执行时
`git rev-parse HEAD` 事实，不落库固定 SHA）。按 §1.1/§3 三分类规则判定：

- `EVIDENCE_CURRENT`：diff 为空（即当前 head 与真实 VM 执行提交一致）；
- `DOCS_EVIDENCE_ONLY`：diff 非空且不含 `packaging/`、`memory-service/`、
  `cpp-bridge/`、`migrations/`、`config/` 任一前缀（仅 docs/evidence 等转换，不触发重包）；
- `RUNTIME_EVIDENCE_STALE`：diff 含上述任一前缀——必须 **重新打包 → 重算 hash →
  重跑真实 VM** → 回填新的 `tested_runtime_commit` / `evidence_commit`。

**当前真实结论（执行时事实）**：`git diff --name-only tested_runtime_commit..HEAD`
前缀扫描命中 `packaging/`、`memory-service/`、`migrations/` 等 runtime 前缀，
当前 HEAD 相对 `tested_runtime_commit` 分类为 **RUNTIME_EVIDENCE_STALE /
RUNTIME_UNVERIFIED**。该分类是 provenance 三分类前缀扫描的**客观分类结果**，
不是对 PR152 的归因断言。命中路径按 git history/diff 事实拆分为两类：

- **A. PR152 自有 remediation 引入**：`packaging/release/*`（build_release_package.sh、
  package_smoke.sh、systemd_install.sh、systemd_uninstall.sh、systemd_verify.sh、
  test_d14a_package_integrity.py、test_d14a_transactional_rollback.py 等）——
  由 PR152 自有 D14A commit（4fb71cc/bf0fe65/c06c718/93b9325/26e8c00/ebcdbbd
  第一父链）引入；
- **B. Upstream/main synchronization 引入**：`memory-service/`（db/、gateway/、
  pipeline/、service/、tests/ 等）、`migrations/versions/20260906_*`
  （20260906_add_forget_topic_key.py、20260906_add_preference_receipt_trace.py）、
  `evaluation/`、`scripts/`、`memory-client/`、`os-agent-integration/`、
  `docs/day13/*` 等——由 main 同步 merge（15de7c6/c3a5489/8a04441，另含 02ca7a0
  handoff 同步）带入的 upstream PR #150/#157/#134/#148 变更，**非 PR152 引入**。

要求：正式「重新打包 → 重算 hash → 重跑真实 VM」并回填新
`tested_runtime_commit` / `evidence_commit` 属后续独立事项，**超出本 Task 且尚未
执行**——完成前 runtime evidence 保持 **STALE / RUNTIME_UNVERIFIED**，不得宣称与
当前 head 一致；仅文档/测试变更（`DOCS_EVIDENCE_ONLY`）不触发重包，本报告
不再沿用旧式『范围内无 packaging/runtime 行为变化』结论。

---

## 6. 遗留事项（不阻塞发布包交付）

1. **D13A 可比性能回归**：正式 L3 上按 `scripts/run_day13a_benchmarks.sh` 复跑，budget 需 D 主审冻结。
2. **c8/c16 高并发**：归入正式 L3。
3. **正式 L3 clean-VM**：依赖 D14D 干净快照 + D13D 冻结环境；用本包 `systemd/install.sh` + `verify.sh`。
4. **状态维持（不越级）**：保持 PACKAGE_IMPLEMENTATION_CANDIDATE；升 READY 须 D 主审
   对发布链 smoke + evidence 与 BLOCKER C 解除共同确认；不产生任何宿主环境已验证、
   三级验收通过或状态越级声明。
5. **BLOCKER C — runtime/model 冻结身份（2026-09-06 裁决 HANDOFF_REQUIRED）**：runtime/model
   identity/version/hash/vendor-frozen lock 尚无 D Reviewer 接受的可信外部冻结输入，
   状态 **HANDOFF_REQUIRED**（不再以 DEPENDENCY_BLOCKED 阻塞本 PR 收敛）；不得伪造 runtime/model version、hash、vendor lock、D Reviewer 会签或麒麟 evidence；
   解除须正式 D14D G0 采集冻结（或外部可信冻结输入 + D Reviewer 会签），属独立后续
   事项，不在本任务解决。

---

*D14A REWORK 修复完成；发布链 smoke 全 PASS，历史 evidence 从 `tested_runtime_commit`
（e3d4b9d…）重建并归位；四身份语义与 BLOCKER C fail-closed 边界按 v4 收口表述；
2026-09-06 仲裁后 BLOCKER C 状态为 HANDOFF_REQUIRED、契约升 FROZEN v4、正式 package
version 固定 `0.1.0-d14a`；
当前 runtime evidence 相对本 PR HEAD 为 RUNTIME_EVIDENCE_STALE / RUNTIME_UNVERIFIED，
正式重打包 → 重算 hash → 真实 VM 重测属后续独立事项，完成前保持候选态。*
