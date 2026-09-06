# D14D 当前状态与 Phase 0 返工（2026-09-06 · REWORK / REVIEW_IN_PROGRESS）

> 状态：`REWORK / REVIEW_IN_PROGRESS`。GitHub PR #159 已转 non-draft 并进入正式 Review，
> Reviewer（lovezy0730-create）提交 `REQUEST_CHANGES`（Review ID 5124446136，2026-09-06）。
> 本文件是 D14D 独立载体的入口说明，记录 2026-09-06 仲裁、收敛与首轮 Review 返工后的任务现状。
> D14D 交付物此前随 PR #150 进入过审，评审返工时已从 #150 迁出并按“独立 PR 发布”处理。

## 0. 任务

| 字段 | 值 |
| --- | --- |
| 任务 | D14D：L3 干净快照发布 Gate、安装生命周期、回退与证据闭环 |
| 责任轨道（original_owner → current_executor） | D → B（2026-09-06 接管） |
| authorization_status | FULLY_AUTHORIZED_FOR_EXECUTION（执行/集成授权；不替代独立 Review/Seal——D/E Reviewer 独立批准权保留） |
| 工作类型 | `release/test-infrastructure`；不修改业务、IPC、Schema、数据库或 SDK ABI |
| 关联任务 | D13D 环境冻结、D13E 正式封存、D14A 发布包（PR #152）、D14B/C L3 发布回归 |
| 输出边界 | D14B 只消费 `L3_READY` 的干净快照与发布包输入；本 PR 不代表 D14D PASS |

## 1. 当前结论（两阶段状态模型 + Review 返工）

按 2026-09-06 协调裁决（D-15），D14D 状态拆为两阶段，避免“环境准备”与
“正式 L3 / Release Gate”互相锁死：

```text
D14D_ENV_PREPARED = READY（r3 ACTIVE；fail-closed Gate 脚本 + 正/负向证据；待 CI/复审确认）
D14D_PHASE0       = r3 ACTIVE（r1/r2 SUPERSEDED 历史；H1 由 r3 可审计 fail-closed 证据关闭）
D14D_FORMAL_L3    = BLOCKED / NOT_STARTED（不是 L3_READY）
L3                = NOT_STARTED
D14A_FORMAL_L3_GO = NO
```

- `D14D_ENV_PREPARED` 按两阶段模型与 D13D_FROZEN / A final package / 第四轮 review 解耦；
  r2 已通过 fail-closed clean Gate（2026-09-06）；该状态与 D13D_FROZEN / A final package / L3 仍解耦，不构成 READY 之外任何结论。
- `D14D_FORMAL_L3` 依赖 `D13D_FROZEN + A_FINAL_PACKAGE_READY + final tested commit/package hash`；
  正式 G0–G9 与 Release Gate 只在此阶段执行。

本 PR 禁止提前写入：`L3_READY`、`HOST_VERIFIED`、`production ready`、
`release ready`、`D14D complete`。

- 2026-09-06 首轮独立 Review 结论 `REQUEST_CHANGES`：HIGH-1（r1 clean-state residue 与 summary 矛盾）、
  MEDIUM-1（`checksums.txt` 缺 `.gitattributes`，14 条 ≠ 15 条闭环）、MEDIUM-2（PR Body/GitHub 元数据漂移）、
  LOW-1（两个 #152 相对链接在 #159 404）、LOW-2（`dist_id` 归因）。处理状态见 §2.4。

## 2. 当前已完成内容（2026-09-06）

### 2.1 仲裁、代码线与 CI 收敛

- D-01：以 PR #152 head 为唯一权威 packaging 代码线；本地 `5700d52`/
  `fix/d14a-release-lifecycle` 并行线按被替代归档为历史。
- D-03/D-04/D-05：contract §3/§6bis 统一为 `HANDOFF_REQUIRED`（SDK 全量 fail-closed；
  runtime/model 由正式 D14D G0 采集冻结）；契约升 `FROZEN v4`；正式 package version
  固定 `0.1.0-d14a`。
- D-14：packaging 4 个 Python 测试与 provenance 测试已加入 CI
  （`.github/workflows/baseline-check.yml` 新增 `d14a-packaging-provenance` job）。
- 第四轮 Review（Reviewer D / Ducknesses）执行对象 head：`f24c29b685e4263f439e440d776455daaf56ba65`
  （与 `02ca7a0a6370034f0918ea45809c7fcd2c1cd0f2` runtime/packaging 文件一致，后随提交仅 docs/CI）。
- GitHub CI：`Repository Baseline Check` PASS、`D14A packaging + provenance L1` PASS。
- L0/L1：PR head packaging + provenance 独立实测 `77 passed`（WSL；不替代麒麟 L3）。
- 第四轮 Review 结论（Reviewer D / Ducknesses，2026-09-06 04:21 UTC）：第三轮核心 BLOCKER/HIGH/MEDIUM
  全部 CLOSED，返工增量（26e8c00→f24c29b）无新增 BLOCKER/HIGH/MEDIUM，残留 4 LOW；
  结论 `WAIT_FOR_MAIN_SYNC`（COMMENT，未 APPROVE）。
- PR #152 已获 Reviewer D APPROVE（2026-09-06 06:41 UTC，head `6ae281a0b6d8680ddc56f467c43d3df9c9ecf2de`）：仅批准 `PACKAGE_IMPLEMENTATION_CANDIDATE`；第四轮 4 LOW 已关闭。
  未批准：READY / L3_READY / FINAL_P freeze / formal package rebuild / formal hash freeze / D14D Formal L3。
  final tested_commit：`NOT_SELECTED`；D14A final package：`NOT_FROZEN`；D14A formal package hash：`NOT_FROZEN`。

仲裁明细与契约收敛记录已在 D14A 载体可见（固定到 #152 当前候选 head `6ae281a0`，避免在 #159 页面 404）：
- [00_d14a_release_package_contract.md](https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/blob/6ae281a0b6d8680ddc56f467c43d3df9c9ecf2de/docs/day14/00_d14a_release_package_contract.md)（FROZEN v4）
- [14_d14a_arbitration_record_20260906.md](https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/blob/6ae281a0b6d8680ddc56f467c43d3df9c9ecf2de/docs/day14/14_d14a_arbitration_record_20260906.md)

### 2.2 Phase A/B 收口（历史，不升级为正式 Gate）

- 5700d52 clean-VM run 已补齐 G9 归档（gate_matrix/checksums/summary/README），
  结论维持历史 `PARTIAL`。
- G1/G5 首跑失败与同 root 重试偏离已按原始日志分类：
  G1＝调用方漏传 `install` 子命令；G5＝reboot 后独立 embedding server 30s 未就绪、
  90s 重试通过（启动时序风险）；重试偏离“失败即停、另开 root”纪律已记录。
- packaging 双代码源对照完成；结论按 D-01 以 PR #152 head 收敛。
- 上述内容保留在本地工作分支（`chore/d14d-*`）与本地工作区 `docs/`，未随本 PR 推送；
  正式 run 与独立审查完成前不宣称 L3。

### 2.3 ENV_PREPARED 冻结值（r1 记录；Review 后 SUPERSEDED，r2 待建）

> 2026-09-06 Review 后状态：r1 snapshot 的 clean-state probe 发现
> `/home/kylin-agent/featday9-embedding-throughput/cpp-bridge/build` 残留，且 probe 非 fail-closed，
> 因此 r1 不作为已闭合 READY 起点消费。下表为 r1 实测记录（历史保留），
> 正式起点待 r2 snapshot 清理重建后替换。

| 项 | 值 | 状态 |
| --- | --- | --- |
| VM | `Kylin-D14D-clean-vdi-20260906`（UUID `70ca1ea3-c27e-483d-aaba-0cac7dc5c77c`） | r1 记录（snapshot_identity.json）；r2 重建时复核 |
| r1 snapshot（历史 / SUPERSEDED） | `d14d-clean-base-20260906-r1`（UUID `4eeade26-5cd3-4467-a31b-c7440c5b04e0`），poweroff | D-11 产出；Review 后不作为正式起点，待 `d14d-clean-base-20260906-r2` |
| OS | 银河麒麟桌面 V11：`KYLIN_RELEASE_ID=2603`（r1 实测）；`dist_id=Kylin-Desktop-V11-2603-Release-20260228-X86_64` 为 REFERENCE_ONLY / HISTORICAL（r1 未采集，正式 G0 重采后再冻结） | r1 实测（os-release）仅覆盖 `KYLIN_RELEASE_ID` 等字段 |
| kernel / arch | Linux `6.6.0-76-generic` / x86_64 | r1 实测（probe/raw 日志） |
| SDK | `libkylin-coreai-embedding 1.2.0.0-0k0.4`；`.so` SHA `028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48` | FROZEN（dependency_identity.json，r1 实测；r2 重采确认） |
| runtime / model | runtime `kylin-ai-runtime 1.2.0.4-0k0.1`（/usr/bin SHA `b3f83fc9…`）；model `kylin-gte-base-model 1.0.0.1-0k0.9`（ONNX SHA `cef0fc76…`，默认 `ensemble-embd_gte-base_uint8-text`） | r1 host baseline（SUPERSEDED，待 r2 重采）；契约 vendor-lock = `HANDOFF_REQUIRED`，正式 G0 / D Reviewer 升版 |
| Trust Root | candidate `D13E_TRUST_ROOTS_V1.json` + public PEM；`--trust-roots` 重验入口已定义 | 重验/Seal 属阶段二（D13D I3d / W6） |
| evidence root | `d14d_<UTC-RUN-ID>_<前7位SHA>`；预创建、空、不可复用、单次执行 | D-11 / Phase0 TaskCard |

#### 2.3.1 r1 证据包（`evidence/phase0/d14d-env-prepared-20260906/`；历史 / SUPERSEDED）

- 路径：`evidence/phase0/d14d-env-prepared-20260906/`（r1 记录；按 evidence_root_policy §2.5 不改写，保留原始 raw）。
- `snapshot_identity.json`（W5a）：VM / r1 / 父快照 UUID、NIC 2223→22、采集后 `poweroff @ r1`。
- `environment.json`（W5b）：`KYLIN_RELEASE_ID=2603`、kernel `6.6.0-76-generic` x86_64、
  Python 3.12.3、2036 installed pkgs；其 clean-state summary“无残留”与 raw 矛盾（见 HIGH-1 事实）。
- `dependency_identity.json`：SDK FROZEN；runtime/model 按 r1 实测记录为 host baseline；完整 2036 包清单在 raw 日志。
- `evidence_root_policy.md`（W5c）：命名 / 权限 / 不可复用 / 只追加 index 规则。
- `trust_root_candidate.md`：Trust Root candidate + 重验证入口（PEM/Seal 属 W6）。
- `raw/`：kylin_vm_test.py 原始日志（probe1 因 sshd 未就绪 BLOCKED，probe2 PASS）。
- HIGH-1 事实：`raw/envprep_env_20260906_1.log` 的 clean-state probe 命中
  `/home/kylin-agent/featday9-embedding-throughput/cpp-bridge/build`（`find … | head -20 || true`
  使 exit=0），故 r1 clean-state Gate 未 fail-closed；r1 root 保留为真实历史，不改写 raw。
- MEDIUM-1：r1 root `checksums.txt` 为 14 条，未纳入 `.gitattributes`（root 16 regular files −
  checksums.txt 自身 = 15，缺口 1），“15/15 全文件”表述不成立；按 policy 不改写 r1 root，
  全文件闭环（含 `.gitattributes`）在 r2 新 root 完成。
- 边界：ENV_PREPARED ≠ D14D PASS；未执行 FORMAL_L3 install/restart/reboot/rollback/Release Gate。

### 2.4 首轮 Review 返工状态（2026-09-06）

| ID | 级别 | 问题 | 处理 |
|---|---|---|---|
| H1 | HIGH | r1 clean-state residue 与 summary 矛盾，ENV_PREPARED=READY 证据不足 | CLOSED（r3 最终）：r2 Route A 基础 + r3 提交固定 `clean_state_gate.sh`（SHA `f90939d1…`）并保存真实调用：正向 `/home/yanmouren778` PASS/exit 0；受控注入 build → FAIL/exit 1（负向验证） |
| M1 | MEDIUM | `checksums.txt` 14 条，缺 `.gitattributes` | CLOSED（r3）：checksums 16/16 含 `.gitattributes`；r3 `evidence_root_policy.md` §5 交接指向 r3 ACTIVE（不再指向 r1） |
| M2 | MEDIUM | PR Body / GitHub 元数据 / head 漂移 | CLOSED：标题去 Draft；PR Body/文档同步 REWORK→r2；待本批 commit 后最终同步 |
| L1 | LOW | 两个 #152 相对链接在 #159 404 | 已修：固定到 #152 head `6ae281a0` 的完整 URL |
| L2 | LOW | `dist_id` 被写成 r1 实测（os-release） | 已修：`dist_id` 标 REFERENCE_ONLY / HISTORICAL，正式 G0 重采 |

### 2.5 r2 evidence（Route A · 2026-09-06；中间证据，已被 r3 取代为 ACTIVE）

- 路径：`evidence/phase0/d14d-env-prepared-20260906-r2/`（中间证据 root，现 SUPERSEDED 历史，未改写）。
- snapshot：`d14d-clean-base-20260906-r2`（UUID `c5e3c3de-1c70-4f58-b22a-ab07b2d2d56d`），父链 20-btrack-test-deps-20260821 → D14D → d14d-r2-prep-before-provision-20260906；VM `Kylin-V11-2603-BTrack-Base`（UUID `103fb8a8-…`）。
- Route A（D 轨授权，2026-09-06）：删除 `/home/yanmouren778` 下 7 个 build 残留；维护模式安装冻结版 `libkylin-coreai-embedding 1.2.0.0-0k0.4` / `kylin-ai-runtime 1.2.0.4-0k0.1` / `kylin-gte-base-model 1.0.0.1-0k0.9` / `kylin-ai-subsystem 1.3.0.1-0k0.1` / `kylin-ai-parser-extension 1.2.0.0-0k0.4` 并提交持久层；冷启动 r2 后 normal 模式复验通过。
- clean-state Gate（fail-closed）：probe 全 0 → `CLEAN_STATE_PASS`（raw `envprep_probe_20260906_r2.log`）。
- 身份（r2 实测，与 r1/D14A 契约一致的项）：SDK `.so` SHA `028e7099…`、runtime `/usr/bin/kylin-ai-runtime` SHA `b3f83fc9…`、model ONNX SHA `cef0fc76…`；installed pkgs = 2030。
- 差异登记：kernel 为 `6.6.0-63-generic`（Route A 新基础；superseded r1 记录为不同 VM 的 `6.6.0-76`）；VM/snapshot 身份按本环境重新冻结。
- checksums：`checksums.txt` = 13 条，覆盖含 `.gitattributes` 在内的全部 13 个 regular files（root 共 14 个，排除自身）；`file-count == entry-count`，逐文件 SHA-256 复验 PASS。
- VM 状态：证据采集后优雅关机，`poweroff @ d14d-clean-base-20260906-r2`。

### 2.6 r3 ACTIVE evidence（第三轮 Review 修正 · 2026-09-06）

- 路径：`evidence/phase0/d14d-env-prepared-20260906-r3/`（**ACTIVE** root；r1/r2 均为 SUPERSEDED 历史，未改写）。
- 第三轮 Review（Review ID 5124446136 后续，2026-09-06）要求：r2 raw 未保存可复核的 fail-closed probe 脚本/命令，且 r2 内 `evidence_root_policy.md` §5 交接仍指向 r1。因 root 不可改写，按 immutable 纪律新增 r3 修正版（绑定同一 r2 snapshot `c5e3c3de…`）。
- 固定 Gate 脚本：`clean_state_gate.sh`（SHA `f90939d1b19c74ea06c182516ab21f7b0efc8791657a1945c7830345e8adc9cf`，提交于 r3 root 内）。
- 正向运行（ROOT=/home/yanmouren778）：8 类 count 全 0 → `CLEAN_STATE_PASS` / exit 0（raw `envprep_probe_20260906_r3.log`）。
- 负向验证（受控注入 build，临时 root，测后删除，不污染 /home）：`build_dir_count=1` → `CLEAN_STATE_FAIL` / exit 1（raw `envprep_neg_20260906_r3.log`）。
- identity 复采：SDK `028e7099…`、runtime `b3f83fc9…`、model ONNX `cef0fc76…`；installed pkgs = 2030（重采无 grep 错误）。
- policy：`evidence_root_policy.md` §5 交接指向本 r3 ACTIVE root（D13D I3d / A package 消费入口）。
- checksums：16/16 全文件闭环（含 `.gitattributes` 与 `clean_state_gate.sh`）；`file-count == entry-count`，逐文件 SHA-256 复验 PASS。
- VM 状态：采集后关机并恢复 r2 snapshot，`poweroff @ d14d-clean-base-20260906-r2`（快照未变）。

## 3. 正式 Gate 状态（阶段二）

| Gate | 状态 | 说明 |
| --- | --- | --- |
| G0 基线 | BLOCKED | 需正式 tested_commit（D14A 当前候选 head `6ae281a0…`；final 未选定）工作树干净、runtime/model 身份 G0 采集、D13D FROZEN |
| G1 快照 | READY（起点）/ FORMAL NOT_RUN | r2 snapshot `d14d-clean-base-20260906-r2` 已建（UUID `c5e3c3de…`）；cold boot 复验 clean Gate PASS；VM poweroff @ r2 |
| G2 包审计 | NOT_RUN（工具 READY） | 正式包须从 tested_commit 重建并冻结 tar/manifest/SHA256SUMS |
| G3 安装 | NOT_RUN | 正式 run 未执行 |
| G4 真 SDK | NOT_RUN | 正式 run 未执行 |
| G5 服务重启 | NOT_RUN | 正式 run 未执行；等待语义=30s→90s→停止另开 root（D-07） |
| G6 OS 重启 | NOT_RUN | 正式 run 未执行 |
| G7 升级 | NOT_RUN / N/A | D-09 书面不适用；不得标 PASS |
| G8 性能 | NOT_RUN | D-10：package-only runner/阈值未批准 |
| G9 Evidence | NOT_RUN | 历史归档仅为 PARTIAL；正式 run 未产生 |

## 4. 阻塞项与外部动作

| 编号 | 阻塞 | 责任人 / 动作 |
| --- | --- | --- |
| B1 | PR #152：Reviewer D 已于 2026-09-06 06:41 UTC APPROVE（仅 `PACKAGE_IMPLEMENTATION_CANDIDATE`，head `6ae281a0…`）；final package `NOT_FROZEN`；final tested_commit `NOT_SELECTED`；D14A formal hash `NOT_FROZEN` | D14D（正式 run 阶段基于最终 tested_commit 重新打包冻结） |
| B2 | D13D FROZEN 未闭合；TD-061 Open（High）；无 Seal / 17 raw / Runner Gate 0–10 | D13D 实施方 / D Reviewer |
| B3 | runtime/model host baseline 已按 r2 重采（dependency_identity.json，r2 root）；契约 vendor-lock / D Reviewer 会签仍 `HANDOFF_REQUIRED`，待正式 G0 升版 | D14D 执行（正式 run） |
| B4 | 正式 package 未从 tested_commit 重建 / hash 未冻结 | A/D14D（G2/G3 解锁后） |
| B5 | G8 package-only runner/阈值未批准 | D 主审 + D13A owner |
| B6 | 正式 evidence root 上 G0–G9 未执行、非作者独立审查未完成 | D14D 执行 + D/E Reviewer |
| B7 | PR159 Review H1/M1（r1 residue + checksums 未闭环） | CLOSED（r2 evidence root 已生成并本地 13/13 闭环；待 CI/复审） |

## 5. 下一步

1. ✅（本批已完成）r2 Route A：清除 7 个 build 残留；维护模式安装冻结版 SDK/runtime/model/subsystem/parser 并提交持久层；建 `d14d-clean-base-20260906-r2` 快照；冷启动复验 clean Gate（fail-closed）PASS；W5a/W5b/dependency identity 重跑；生成 `evidence/phase0/d14d-env-prepared-20260906-r2/`（13/13 全文件闭环）；VM 恢复 `poweroff @ r2`。
2. 提交本批（状态文档 + r2 evidence root）→ push PR #159 → 等待 Repository Baseline Check PASS。
3. 独立 Reviewer 复审（撤销 REQUEST_CHANGES / APPROVE）→ merge PR #159（需另行授权）。
4. PR #152：已 APPROVE（仅 PACKAGE_IMPLEMENTATION_CANDIDATE）；final package / formal hash 冻结留待 final tested_commit 选定后的正式 D14D run。
5. D13D：Safety Gate-9 projection 与 Forget real dispatch follow-up → I3b-completion → 选定 final tested_commit → VM 环境复验/ENVIRONMENT_FROZEN → 17 raw → Final Manifest + Review Seal → attestation + Execution Seal → Runner Gate 0–10 → `D13D_FROZEN`。
6. D14D Formal：基于 r2 起点与最终 tested_commit 执行 G0–G9 → 非作者独立审查 → `L3_READY` → 交接 D14B/C。

## 6. Reviewer 检查重点

- 是否守住“ENV_PREPARED ≠ PASS；FORMAL_L3 未闭合前不得 L3_READY”边界；
- 本 PR 是否未虚报正式 VM G0–G9、D13D FROZEN、D14A 最终包或 D14D 完成；
- 状态值（第四轮被审 head `f24c29b` / APPROVED candidate head `6ae281a0…` / r1 SUPERSEDED / `0.1.0-d14a` /
  SDK identity）是否与 PR #152、契约 v4 与本地仲裁记录一致；
- HIGH-1/M1 是否按返工清单闭合：r2 clean-state Gate fail-closed、新 root checksums 含
  `.gitattributes` 全文件闭环、README 只在真实闭环后写“全部文件”；
- 历史 PARTIAL run / r1 root 是否仅作历史证据、未升级为正式 PASS。
