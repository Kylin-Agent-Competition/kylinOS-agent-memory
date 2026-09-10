# D15E 最终提交材料准备与提交锁定矩阵（as-of 2026-09-09）

> **性质声明**：本文件为 D15E Phase 0 最终提交**材料准备与提交锁定矩阵**的文档基线，
> 以 as-of 快照方式如实记录 2026-09-09 的仓库事实，aggregate E15-1 ~ E15-6 六个
> 提交锁点、submission inventory、claim-to-evidence mapping（C1~C8）、upstream
> blocker matrix、final lock trigger 与 BOUND-1~BOUND-8 禁止 overclaim 边界。
> 本文件**不执行、不宣称任何正式锁**；`D15E_FINAL_SUBMISSION_LOCK=WAITING_PREREQ`、
> `D15E_FINAL_SUBMISSION_LOCK_DECLARED=false`，**不宣布 D15E FINAL LOCK**，
> **不签署 D14E final acceptance**。本矩阵线自身状态独立标记为
> `DOCUMENTATION_PREPARATION / READY_FOR_REVIEW`，不得与其他锁点行混标。
> 本文件为纯 docs 任务（`runtime_required=false`），不执行 L2/L3，不访问麒麟 VM，
> 不生成新的 Runtime 结论。

---

## 1. 性质声明与范围边界

### 1.1 性质声明

- 本文件是 D15E Phase 0 最终提交材料准备与提交锁定矩阵的**单一可审计文档基线**，
  用于在 2026-09-09 快照下聚合：
  - E15-1 ~ E15-6 六个 submission lock 点的锁定对象、当前状态、证据/身份绑定与阻塞来源；
  - submission inventory（提交物清单）与各提交物当前状态、是否可冻结；
  - claim-to-evidence mapping（C1~C8）及「当前是否允许作为最终比赛事实」判定；
  - upstream blocker matrix（D14B / D14C / D15A / D15C / D14E）；
  - final lock trigger 八条触发条件；
  - BOUND-1~BOUND-8 禁止 overclaim 边界与机器守卫覆盖边界。
- 本文件只做**事实登记与状态聚合**，不代替任何上游（D14B/D14C/D15A/D15C/D14E）
  完成 formal runtime、证据或签署动作。
- 本文件**不创建测试**；配套机器守卫 `docs/day15/test_d15e_final_submission_lock_matrix.py`
  由同批 guard 任务创建，不在本任务范围内。

### 1.2 范围边界

本任务仅新增**一个文件**：`docs/day15/10_d15e_final_submission_lock_matrix_20260909.md`（module=docs）。
以下内容一律**不修改、不新增、不调用**：

- **不修改 production code**：`packaging/**`、`memory-service/**`、`cpp-bridge/**`、
  `memory-client/**`、`os-agent-integration/**`、`migrations/**`、`config/**`、
  `scripts/**`、`tests/**`、`interfaces/**`、`perf/**`、`third_party/**`；
- **不修改** `evaluation/**` 与 `datasets/**`（含任何 Gold / Threshold / dataset /
  metrics 定义）；
- **不修改** `evidence/**` 任何内容（含冻结 root/raw/Seal/attestation/SHA256SUMS）
  与 `evidence/index.yaml`；
- **不修改** `docs/day13/**`、`docs/day14/**`、`docs/day11/**` 任何既有文档及其配套测试；
- **不修改** `docs/day15/00_d15a_rc_lock_matrix_20260906.md`、
  `docs/day15/01_d15a_a15_evidence_review_readiness_20260908.md`、
  `docs/day15/test_d15a_rc_lock_matrix.py`；
- 本任务**不创建** `docs/day15/test_d15e_final_submission_lock_matrix.py`
  （由同批 guard 任务创建）；
- **不修改** `.github/**`、`.local-agent-workflow/**` 的 workflow-engine 文件
  （orchestrator.py、run_batch.sh、`.opencode/agents/**`）；
- **不执行 L2/L3**、不访问银河麒麟 VM、不生成新的 Runtime 结论、不新增 evidence 条目；
- **不宣布 D15E FINAL LOCK**、不签署 D14E final acceptance、不把 D14B/D14C 未闭合
  写成通过、不把 D14D L3_READY 解释为 release readiness 或 production readiness；
- **不 push**、不创建/更新 PR、不 merge、不 release、不弱化守卫、不改变验收标准。

---

## 2. 快照身份与状态行

### 2.1 快照身份（as-of 2026-09-09）

| 字段 | 值 |
|------|-----|
| as-of | as-of=2026-09-09 |
| scan_branch | scan_branch=docs/D15E-final-submission-preparation |
| scan_time_main_head | scan_time_main_head=a7abb1e71c03c4f1558e5c6a9eff2b9f36437993 |
| frozen_tested_commit | frozen_tested_commit=ba3b50e1bdeea185bca9daee9d1d45958f62a636 |
| package | package kylin-memory-a-d14a 0.1.0-d14a |
| package_tar_sha256 | package_tar_sha256=2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401 |
| package_manifest_sha256 | package_manifest_sha256=76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0 |
| package_sha256sums_sha256 | package_sha256sums_sha256=8540cd1dc2b8c743bc466cd89f435e09940ddc5e5df842cacb9367021eddcf67 |
| manifest_files | manifest_files=3360 |
| d13e_report_sha256 | d13e_report_sha256=dee80d5044c2194b79f13e7185b39f0162c63468f7a47b86799a1abb23c489ee |
| runtime_status | runtime_status=RUNTIME_NOT_REQUIRED |

关键区分声明（独立一行，逐字）：

**scan-time main HEAD 不等于 frozen tested_commit，四类身份对象（main HEAD / frozen tested_commit / package SHA / evidence-report SHA-256）不得互相冒充。**

- scan-time main HEAD（`a7abb1e71c03c4f1558e5c6a9eff2b9f36437993`）是 PR #124
  merge（`D14B：L3 干净虚拟机发布回归（全部交付收敛） (#124)`）后的 main 顶点；
- historical main merge chain：`#171 → 3ef0ce518844749f14aa384790efbcde5af39ec9`、
  `#167 → a4034c9cdab1de31f70bced73dcab8ff2b18407c`、
  `#124 → a7abb1e71c03c4f1558e5c6a9eff2b9f36437993`；仅最后一条是 current scan-time main；
- frozen tested_commit（`ba3b50e1bdeea185bca9daee9d1d45958f62a636`）是
  D13D/D14A/D14D 冻结的 tested commit，与 scan-time main HEAD 是不同的 Git 对象；
- D14A package SHA（tar `2222c904…` / manifest `76a839…` / SHA256SUMS `8540cd…`）
  与 d13e evidence-report SHA-256（`dee80d50…`）均为独立哈希对象；
- 四类身份对象各自独立标注、互不冒充，任何「相等/可互换」表述一律禁止（BOUND-7）。

### 2.2 状态行（各独立成行，逐字）

D15E_PHASE0_PREPARATION=READY
D15E_FINAL_SUBMISSION_LOCK=WAITING_PREREQ
D15E_FINAL_SUBMISSION_LOCK_DECLARED=false
D15E_SIGNOFF_STATUS=BLOCKED

说明：上述四条为独立机器状态行。`D15E_PHASE0_PREPARATION=READY` 仅表示
「Phase 0 提交材料准备文档基线」已建立；`D15E_FINAL_SUBMISSION_LOCK` 仍为
`WAITING_PREREQ`、`D15E_FINAL_SUBMISSION_LOCK_DECLARED=false`（未宣布任何锁）；
`D15E_SIGNOFF_STATUS=BLOCKED`（未签署）。

### 2.3 历史快照失效说明

`docs/day14/23_d14e_phase1_acceptance_baseline_20260908.md` 自述的
as-of=2026-09-08 与「基线提交尚未合入 origin/main」在 PR #171 squash merge 合入
main（HEAD=`3ef0ce5…`）后已**过期**；该历史文档快照可失效。本文件以 2026-09-09
重新扫描的仓库事实为准（scan_time_main_head、D14B/D14C 稳定身份（PR / branch /
head）等全部按 2026-09-09 值登记）。

---

## 3. E15-1 ~ E15-6 Submission Lock Matrix

### 3.1 锁点状态表（as-of 2026-09-09）

| Lock | 锁定对象 | 当前状态 | 证据/身份绑定 | 阻塞来源 |
|------|----------|----------|----------------|----------|
| E15-1 | 技术文档与用户手册口径 | WAITING_PREREQ | 文档骨架/口径草案基于 as-of 2026-09-09 仓库事实 | 无已闭合的技术/手册口径前置基线，等待前置评审 |
| E15-2 | 功能测试与效果验证报告 | BLOCKED_BY_D14B | 无 formal evidence root（D14B Formal L3 debt 未闭合） | D14B（D14B_FORMAL_L3=NOT_RUN/UNVERIFIED；D14B_TASK=PARTIAL/WAIVED_FORMAL_INPUTS；Preparation Harness PASS 不替代 Formal L3） |
| E15-3 | 真实案例与四项核心指标结论 | BLOCKED_BY_D14C | 无 formal evidence root（D14C 未闭合） | D14C（Real AI Assistant E2E 未合入 main；G4=BLOCKED_PENDING_D15C_HANDOFF；D15C handoff input ready，等待 D14C/D 主审消费） |
| E15-4 | 提交物清单与交付物身份 | WAITING_PREREQ | 提交物清单可开始统稿（§4 inventory） | 等待 E15-1~E15-3 上游事实与身份核验前置 |
| E15-5 | claim-to-evidence 映射与 overclaim 终检 | WAITING_PREREQ | C1~C8 映射表可开始统稿（§5） | 等待 D14B/D14C 结论与 D15A 状态闭合 |
| E15-6 | 最终提交口径与签署触发 | BLOCKED | D14E final signoff 未签署（状态行=BLOCKED） | D14E final acceptance 未接受（人工签署未发生） |

锁点与状态逐字绑定：E15-1=WAITING_PREREQ（技术文档与用户手册口径锁定）；E15-2=BLOCKED_BY_D14B（功能测试与效果验证报告锁定）；E15-3=BLOCKED_BY_D14C（真实案例与四项核心指标结论锁定）；E15-4=WAITING_PREREQ（提交物清单与交付物身份锁定）；E15-5=WAITING_PREREQ（claim-to-evidence 映射与 overclaim 终检锁定）；E15-6=BLOCKED（最终提交口径与签署触发锁定）。

- 本矩阵线自身状态单独记为 `DOCUMENTATION_PREPARATION / READY_FOR_REVIEW`，
  表示本文档作为准备基线处于文档评审状态，**不得与 E15 行混标**，不得被解读为
  任何正式锁；
- 每个 E15-x 锁点在表格中**恰好一行**、严格 5 列（Lock | 锁定对象 | 当前状态 |
  证据/身份绑定 | 阻塞来源），任何重复/歧义/混合/额外状态一律 fail-closed
  （实际强制由同批 guard 任务创建的 `test_d15e_final_submission_lock_matrix.py`
  承担，本任务不创建该测试）。

### 可冻结事实（as-of 2026-09-09）

以下为**可冻结事实**清单，逐条登记（每条只冻结其声明范围，禁止越界扩展）：

- **D13D_FROZEN**：tested_commit=ba3b50e1bdeea185bca9daee9d1d45958f62a636，
  evidence/index.yaml 条目 `D13D-FORMAL-CLOSURE-BA3B50E-20260908`，
  status=FROZEN；
- **D14A final package identity FROZEN**：A_FINAL_PACKAGE_READY=YES，
  evidence/index.yaml 条目 `D14A-FINAL-PACKAGE-FREEZE`，
  status=PACKAGE_HASH_FROZEN，**仅指 package identity**（不代表 production release）；
- **D14D L3_READY=true**：必须同时保留 release_ready=false 与 production_ready=false
  边界，G7 NOT_RUN/N-A、G8 NOT_RUN waiver；
- **D14E Phase 1 验收基线已随 PR #171 合入 main**：D14E_PHASE1_ACCEPTANCE_BASELINE=READY、
  D14E_FINAL_ACCEPTANCE=BLOCKED、D14E_SIGNOFF_STATUS=BLOCKED。
  （注意：该基线文档自身 as-of=2026-09-08 快照已随 PR #171 过期，见 §2.3。）

---

## 4. Submission Inventory（提交物清单）

### 4.1 提交物清单（as-of 2026-09-09）

| 提交物 | 当前状态 | 是否可冻结 | 说明/依据 |
|--------|----------|------------|-----------|
| 技术文档 | 统稿中（骨架/口径草案可开始） | NOT_FROZEN | 口径锁定等待 E15-1 前置闭合 |
| 用户手册 | 统稿中（骨架可开始） | NOT_FROZEN | 口径锁定等待 E15-1 前置闭合 |
| 功能测试报告 | PENDING_UPSTREAM | NOT_FROZEN | 依赖 D14B 闭合（E15-2） |
| 效果验证报告 | PENDING_UPSTREAM | NOT_FROZEN | 依赖 D14B 闭合（E15-2） |
| 真实案例材料 | PENDING_UPSTREAM | NOT_FROZEN | 依赖 D14C 闭合（E15-3） |
| 四项核心指标结论 | BLOCKED | NOT_FROZEN | 正式结论须以 §5 C1~C8 允许性判定为准；D14B/D14C 未闭合前不可冻结 |
| 演示视频素材 | PENDING_UPSTREAM | NOT_FROZEN | 待 D14B/D14C 闭合后核对叙事一致（C8） |
| 发布包与安装/升级/回退说明 | 发布包 identity=FROZEN；安装/升级/回退说明=PENDING_UPSTREAM | 部分可冻结（仅 identity） | D14A final package identity 已冻结（C3，仅 identity）；安装/升级/回退说明依赖 D14B 发布回归闭合 |
| 提交清单/README | 统稿中（submission inventory 可开始） | NOT_FROZEN | E15-4 等待前置（提交物身份锁定） |

- 缺失项一律写为 `PENDING_UPSTREAM` 或 `BLOCKED`，**不得写成已交付**；
- `NOT_FROZEN` 表示该项当前不可冻结为最终提交口径。

### 可开始统稿（as-of 2026-09-09）

以下材料**不受上游闭合阻塞**，可以开始统稿：

- submission inventory（§4.1 清单及其状态登记）；
- claim-to-evidence mapping（§5 C1~C8 骨架）；
- 用户手册/技术文档骨架与口径草案；
- overclaim 终检清单（以 §8 BOUND-1~BOUND-8 为检查项）。

### 仍受阻塞（as-of 2026-09-09）

以下结论**仍受阻塞**，不得写成已闭合：

- D14B_FORMAL_L3=NOT_RUN/UNVERIFIED；
- D14B_FORMAL_RESULT=UNVERIFIED；
- D14B_TASK=PARTIAL/WAIVED_FORMAL_INPUTS；
- D14C_FORMAL_L3=BLOCKED；
- D14C_FORMAL_RESULT=UNVERIFIED；
- D14C G4=BLOCKED_PENDING_D15C_HANDOFF（D15C handoff input ready；等待 D14C/D 主审消费，不得自动解除）；
- D15A A15-2=BLOCKED；
- A15-1/A15-3=READY_FOR_REVIEW 但 D15A 冻结矩阵仍为 WAITING_PREREQ
  （`docs/day15/00_d15a_rc_lock_matrix_20260906.md` as-of 2026-09-06 快照状态行；
  该快照可失效，以最新 A15 review 结论为准）；
- D14E final signoff 未签署。

---

## 5. Claim-to-Evidence Mapping（声明—证据映射）

规则：每条可对外（比赛/演示）声明的 claim 必须可回溯到正式 evidence 路径 +
identity 绑定 + 环境/run ID，并给出「当前是否允许作为最终比赛事实」的判定。
不允许的 claim 只能作为「前置未闭合/待刷新」出现，不得写成已达成事实。

| claim | 正式 evidence 路径 | identity 绑定 | 当前是否允许作为最终比赛事实 | 允许性条件/约束 |
|-------|---------------------|---------------|------------------------------|------------------|
| C1 D13D 正式执行闭环完成（17 raw、双 Seal、Runner Gate 0-10 PASS） | evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/D13D_FREEZE_RECORD_20260908.md | tested_commit ba3b50e1bdeea185bca9daee9d1d45958f62a636；index id D13D-FORMAL-CLOSURE-BA3B50E-20260908 | 允许（范围限定：D13D formal 执行闭环） | 不得扩展为 Day14 全链路或 production 结论 |
| C2 业务域 formal 指标达阈值（Preference/Conflict n=4 accuracy=1.0；Safety n=4 violations=0；Forget n=5 violations=0） | evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/evidence/D13E_FORMAL_REPORT_V1.json | report SHA-256 dee80d5044c2194b79f13e7185b39f0162c63468f7a47b86799a1abb23c489ee；Dataset/Gold/Threshold SHA 见冻结记录 | 允许（必须带 n=4/4/4/5、阈值与 formal 环境限定） | 禁止无限定外推为全场景/整体性能（BOUND-4） |
| C3 D14A final release package identity 已冻结 | evidence/l3-kylin-vm/d14a_final_package_20260908/D14A_FINAL_PACKAGE_FREEZE_RECORD_20260908.md | package kylin-memory-a-d14a 0.1.0-d14a；tar/manifest/SHA256SUMS SHA（见 §2.1）；index id D14A-FINAL-PACKAGE-FREEZE | 允许（仅 package identity 冻结） | 不代表 production release |
| C4 D14D clean Kylin L3 evidence READY | evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/ | tested_commit ba3b50e1bd…；PR #165 ec7a66b、#168 2bd5948 | 允许（必须带 L3_READY=true / release_ready=false / production_ready=false 边界） | G7 NOT_RUN/N-A、G8 NOT_RUN waiver；不得解释为 release readiness 或 production readiness（BOUND-3） |
| C5 Day14 检索/索引生命周期发布回归最终通过 | 无正式 evidence（D14B Formal L3 debt 未闭合） | PR #124 / test/D14B-l3-vm-release-regression（final head=fb4531e673bb5f02d6a109ec0f467cb6d384e927；merge commit=a7abb1e71c03c4f1558e5c6a9eff2b9f36437993；MERGED into main） | **不允许**（当前不可声明） | D14B_FORMAL_L3=NOT_RUN/UNVERIFIED、D14B_FORMAL_RESULT=UNVERIFIED；D14B_TASK=PARTIAL/WAIVED_FORMAL_INPUTS；Preparation Harness PASS 与 substitute validation PASS_WITH_LIMITATIONS 不替代 formal evidence（BOUND-1/BOUND-5） |
| C6 官方 AI Assistant production E2E 已正式通过 | 无正式 evidence（D14C 未闭合） | 分支 test/D14C-l3-clean-vm-release-regression（2026-09-09 tip=refs/pull/156/head=77319aa4ce75d7f7fe4d7ed64f7332cffdb88441；PR #156 PR_OPEN） | **不允许**（当前不可声明） | D14C_FORMAL_L3=BLOCKED、D14C_FORMAL_RESULT=UNVERIFIED；G4=BLOCKED_PENDING_D15C_HANDOFF（D15C handoff input ready；等待 D14C/D 主审消费）；未合入 main（NON_MAIN_BRANCH）（BOUND-2/BOUND-5） |
| C7 D14E 业务/安全最终签署 | N/A（后续 final 流程产生） | N/A | **不允许**（当前不可声明） | D14E_FINAL_ACCEPTANCE=BLOCKED、D14E_SIGNOFF_STATUS=BLOCKED；final signoff 未签署 |
| C8 Demo/视频素材与比赛叙事一致 | N/A（对照 artifact 待建） | N/A | **不允许**（当前不可声明） | 须在 D14B/D14C 事实与最终素材就绪后逐条核对 |

---

## 6. Upstream Blocker Matrix（上游阻塞矩阵）

列定义：上游 | ref/PR | 是否合入 main | 当前受控状态 | 阻塞的 E15 项 | 来源。

| 上游 | ref/PR | 是否合入 main | 当前受控状态 | 阻塞的 E15 项 | 来源 |
|------|--------|---------------|--------------|----------------|------|
| D14B | PR #124 / test/D14B-l3-vm-release-regression（final head=fb4531e673bb5f02d6a109ec0f467cb6d384e927；merge commit=a7abb1e71c03c4f1558e5c6a9eff2b9f36437993） | 是（PR #124 已合入 main；Formal L3 debt 未闭合） | D14B_FORMAL_L3=NOT_RUN/UNVERIFIED；D14B_FORMAL_RESULT=UNVERIFIED；D14B_TASK=PARTIAL/WAIVED_FORMAL_INPUTS；Formal Input Waiver=WAIVED_BY_OWNER（仅 merge eligibility） | E15-2 | gh PR #124 实测（final head、merge commit；as-of 2026-09-09） |
| D14C | PR #156 / branch=test/D14C-l3-clean-vm-release-regression / head=77319aa4ce75d7f7fe4d7ed64f7332cffdb88441（PR_OPEN；NON_MAIN_BRANCH；NOT_MERGED） | 否（NON_MAIN_BRANCH；NOT_MERGED） | D14C_FORMAL_L3=BLOCKED；D14C_FORMAL_RESULT=UNVERIFIED；D14C G4=BLOCKED_PENDING_D15C_HANDOFF（D15C handoff input ready；等待 D14C/D 主审消费） | E15-3 | GitHub PR #156 / branch head 实测（stable identity；as-of 2026-09-09） |
| D15A | docs/day15/00_d15a_rc_lock_matrix_20260906.md（as-of 2026-09-06 快照）；D15A 文档已随 #169/#170 合入 main（2026-09-08） | 是（#169/#170，2026-09-08 合入 origin/main） | A15-1/A15-3=READY_FOR_REVIEW、A15-2=BLOCKED（上游 review 结论）；D15A 冻结矩阵仍为 WAITING_PREREQ（00 文档 as-of 2026-09-06 状态行，快照可失效） | E15-5（overclaim 终检对 A15 相关声明的核验受限） | docs/day14/23 §A.2 + docs/day15/00 文档快照 |
| D15C | D15C upstream artifact EXISTS and is merged into main via PR #167（branch=feat/C-hook-evidence；final head=b5f8154b9e510c10124e84ecf70d608e4fee7896；merge commit=a4034c9cdab1de31f70bced73dcab8ff2b18407c；review=APPROVED；handoff status=HANDOFF_SUBMITTED） | 是（PR #167 已合入 main；artifact/main entry ready；D15C handoff input ready；not closed） | D14C G4=BLOCKED_PENDING_D15C_HANDOFF（D15C handoff input ready；等待 D14C/D 主审消费；不得自动解除）；TD-007/008/009、R-ARCH-05、Production Identity 未关闭 | E15-3（经 D14C） | git ls-remote / gh PR #167 实测（2026-09-09）；注：.local-agent-workflow/tasks 与 .local-agent-workflow/batches 下无 D15C Task/Batch 仅表示本地 workflow 输入未登记，不能据此推导 upstream artifact 不存在 |
| D14E | docs/day14/23_d14e_phase1_acceptance_baseline_20260908.md（Phase 1 验收基线；随 PR #171 squash merge 合入） | 是（PR #171 merge commit=3ef0ce518844749f14aa384790efbcde5af39ec9；historical merge identity / historical main point，非 current scan-time main；current scan-time main=a7abb1e71c03c4f1558e5c6a9eff2b9f36437993） | D14E_PHASE1_ACCEPTANCE_BASELINE=READY；D14E_FINAL_ACCEPTANCE=BLOCKED；D14E_SIGNOFF_STATUS=BLOCKED；final signoff 未签署 | E15-6 | git log 实测（PR #171 squash merge）+ docs/day14/23 状态行 |

---

## 7. Final Lock Trigger（最终锁定触发条件）

本文件准备完成与后续机器守卫通过**不构成**任何最终锁定。仅当以下条件**全部**
满足后，才允许由提交口径负责人/签署人（人工）推进 D15E 最终提交口径锁定与
D14E final signoff（该动作超出本任务范围；触发条件与 docs/day14/23
`_d14e_phase1_acceptance_baseline_20260908.md` E 节一致）：

1. **快照身份重新核验**：在触发日执行 `git rev-parse HEAD`、`git status`、
   `git branch --show-current`，确认分支与 HEAD；若与本文档 as-of=2026-09-09 快照
   不一致，须先刷新本文件或新文档中的身份声明。
2. **refs 刷新**：重新扫描 `origin/test/D14B-l3-vm-release-regression` 与
   `origin/test/D14C-l3-clean-vm-release-regression`（含 upstream）的 tip 与
   merge 状态；任何 tip 前移或已合入 main 都须在最终材料中反映。
3. **D14B 闭合前置**：按 D14B Formal Harness/Runbook 形成完整 formal evidence root，
   并通过 final verifier + independent review；`D14B_FORMAL_L3` 与
   `D14B_FORMAL_RESULT` 具备真实结果且绑定实际 used commit。PR #124 已合入 main
   （final head=`fb4531e673bb5f02d6a109ec0f467cb6d384e927`；merge commit=`a7abb1e71c03c4f1558e5c6a9eff2b9f36437993`），
   仅满足 merge-history precondition；`FORMAL_D14D_INPUTS=WAIVED_BY_OWNER` 只针对
   #124 merge eligibility，不满足 D15E final submission lock 对 D14B Formal L3
   真实结果的要求。
4. **D14C 闭合前置（绑定 D14C upstream=PR #156 / test/D14C-l3-clean-vm-release-regression / 77319aa4ce75d7f7fe4d7ed64f7332cffdb88441；NON_MAIN_BRANCH 且未合入 main）**：G4-G7 闭合（含 Host Mapping handoff 经 D review、route ACTIVE、MemoryContext freeze；其中 G4=BLOCKED_PENDING_D15C_HANDOFF 的解除依赖本条下列独立子项 handoff 前置闭合）后，基于 ≥ 当前 main 顶点刷新静态审计并执行 formal L3 E2E，有 formal evidence root，分支合入 main。
   - **D15C handoff 前置（独立子项行）**：D15C upstream artifact（D15C；PR #167；branch=feat/C-hook-evidence；final head=b5f8154b9e510c10124e84ecf70d608e4fee7896；merge commit=a4034c9cdab1de31f70bced73dcab8ff2b18407c；handoff status=HANDOFF_SUBMITTED）已合入 main；不因合入 main 自动视为 D15C handoff 已消费或 D14C G4 解除，D14C G4 保持 BLOCKED_PENDING_D15C_HANDOFF（等待 D14C/D 主审消费），D14C 闭合前置不得推进。
5. **evidence 完整性复核**：逐一复核本文件引用的 evidence 路径真实存在、
   d13e report SHA-256（dee80d50…）、D14A 各 package SHA 与仓库一致；确认冻结
   root/index.yaml 未被改写、未新增伪条目。
6. **身份防混淆复核**：确认最终材料中 main HEAD、frozen tested_commit
   （ba3b50e1bd…）、package SHA、evidence/report SHA 四类对象互相区分且各自准确。
7. **overclaim 终检**：对全部比赛/演示材料逐条执行 §5 C1~C8 允许性判定，确认
   不存在 BOUND-1~BOUND-8 任一越级表述；D14D 仍保留 release_ready=false /
   production_ready=false 边界直至正式 release 判定。
8. **人工签署**：由 D14E 业务与安全签署人（非文档作者、非本任务执行者）基于
   上述全部前置独立核验后签署；签署结论以新建 D14E final 文档为准，并显式迁移
   状态行。

任一条件未满足时，`D15E_FINAL_SUBMISSION_LOCK` 保持 `WAITING_PREREQ`、
`D15E_FINAL_SUBMISSION_LOCK_DECLARED` 保持 `false`、`D15E_SIGNOFF_STATUS` 保持
`BLOCKED`。

**本文件不宣布 D15E FINAL LOCK、不签署 D14E final acceptance、不执行 L2/L3、不生成新的 Runtime 结论。**

---

## 8. 禁止 Overclaim 边界与机器守卫覆盖边界

以下为禁止 overclaim 边界（BOUND-1~BOUND-8，逐字）：

- 【BOUND-1】D14B Formal L3 未闭合期间，检索/索引生命周期发布的正式指标保持
  UNVERIFIED；不得把 D14B 的 PREPARATION / VALIDATION 结果写成正式通过或
  VERIFIED。
- 【BOUND-2】D14C Formal L3 未闭合期间，不得声明官方 AI Assistant 的
  production E2E 已正式通过（含任何等价 PASS 表述）。
- 【BOUND-3】D14D 的 L3_READY=true 不得解释为 release readiness 或 production
  readiness；必须保留 L3_READY=true 与 release_ready=false、production_ready=false
  边界（G7 NOT_RUN/N-A、G8 NOT_RUN waiver），不得声明 release_ready 或
  production_ready 为真。
- 【BOUND-4】不得把 D13E formal 小样本（Preference/Conflict n=4、Safety n=4、
  Forget n=5）的通过结果写成未经限定的全场景/整体性能结论；Safety/Forget
  violations=0 不得写成绝对安全/绝不残留。
- 【BOUND-5】open upstream PR 事实必须标识来源（任务扫描快照或实测）与非主干状态
  （NON_MAIN_BRANCH / PR_OPEN），不得把分支/PR 上的准备材料冒充为已合入 main 的
  正式结果。
- 【BOUND-6】历史文档旧状态不得直接当作当前事实：docs/day14/23 的 as-of=2026-09-08
  与「尚未合入 origin/main」已随 PR #171 失效；引用历史快照必须注明可失效，并以
  2026-09-09 重扫事实为准。
- 【BOUND-7】不得混淆四类身份对象：scan-time main HEAD（current=
  a7abb1e71c03c4f1558e5c6a9eff2b9f36437993）、frozen
  tested_commit（ba3b50e…）、D14A package SHA（tar/manifest/SHA256SUMS）、
  d13e evidence-report SHA-256（dee80d5…）；互相不得冒充相等。
  PR #171 merge commit `3ef0ce518844749f14aa384790efbcde5af39ec9` 仅作为 historical merge identity /
  historical main point 保留，不得标为 current scan-time main HEAD。
- 【BOUND-8】D15E Phase 0 职责止于提交材料准备与锁定矩阵文档；不得越界修改
  production code、evidence（冻结 root/raw/Seal/attestation/SHA256SUMS/
  index.yaml）、evaluation/datasets 与既有 docs/day13/14、docs/day15 00/01 文档；
  不得以文档表格代替真实锁与真实签署。

### 机器守卫覆盖边界

- 本文件是后续同批 guard 任务创建的 `docs/day15/test_d15e_final_submission_lock_matrix.py`
  的守护对象（本任务不创建该测试）；
- 既有 D15A 守卫 `docs/day15/test_d15a_rc_lock_matrix.py` 仅固定读取
  `docs/day15/00_d15a_rc_lock_matrix_20260906.md`，不扫描 `10_*` 新文件，
  本文件不破坏该守卫；
- `docs/day15/test_d15e_final_submission_lock_matrix.py` 当前性质是
  **executable / manual static guard（可执行、当前手工运行的静态守卫）**；
  它**不是** GitHub merge CI enforced gate（截至 as-of 2026-09-09 未接入
  `.github/**` workflow，run #805 未执行本守卫）。因此 Repository Baseline
  Check = green 不得被描述为「D15E guard 已由 GitHub CI 强制执行」；
  本 PR 不新增 workflow、不新增 runner。
- 机器守卫只覆盖受控英文 sentinel 缺席、结构化状态行、E15 锁矩阵行级绑定与已定义
  provenance/state token 在场；中文/自然语言同义越级、语义归因与 evidence 真实性
  由独立 Reviewer 人工审查（本文件不引入 NLP/LLM/机器学习检测）。

---

## 9. 状态词纪律、责任与 Reviewer

### 9.1 允许使用的受控状态词

`WAITING_PREREQ`、`BLOCKED`、`BLOCKED_BY_D14B`、`BLOCKED_BY_D14C`、
`BLOCKED_PENDING_D15C_HANDOFF`、`L3_READY`、`NOT_FROZEN`、`RUNTIME_UNVERIFIED`、
`UNVERIFIED`、`NOT_RUN`、`N-A`、`NON_MAIN_BRANCH`、`PR_OPEN`、
`PACKAGE_HASH_FROZEN`、`FROZEN`、`DOCUMENTATION_PREPARATION`、`READY_FOR_REVIEW`、
`PENDING_UPSTREAM`、`RUNTIME_NOT_REQUIRED`。
边界书写采用 `release_ready=false` / `production_ready=false` / `L3_READY=true`
等带下划线的赋值形式与 `release readiness` / `production readiness` 短语形式。

### 9.2 禁止出现的越级语义（全文不得出现）

以下**语义**在本文件全文中一律不得以任何中英文等价表述出现，属必须遵守的
**文档纪律**（中文/自然语言同义越级同样受约束，不只是受控英文 sentinel）；
本小节仅以中文语义描述这些越级类别，**不书写其英文原词组合**：

- **正式终锁类**：以「最终锁定 / final 锁定」语义表述的状态结论
  （final 前缀加 lock 后缀的英文组合即属此类）；
- **终态锁定类**：以英文「锁定」（lock 词族）独立词义结尾的终态结论
  （受控词 `BLOCKED` 除外——`BLOCKED` 中的局部拼写不构成越级结论）；
- **提交锁定类**：以「提交物已锁定」语义表述的终态结论
  （submission 与 lock 词族的英文组合即属此类）；
- **「生产就绪」类**：production 与「就绪/ready」语义组合的越级状态结论
  （合法形式仅允许 `production_ready=false`，禁止 `=true` 形式与带空格短语）；
- **「发布就绪」类**：release 与「就绪/ready」语义组合的越级状态结论
  （合法形式仅允许 `release_ready=false`，禁止 `=true` 形式与带空格短语）；
- **「宿主已核验」类**：host 与「已核验/verified」语义组合的越级结论；
- **「Runtime 已核验」类**：runtime 与「已核验/verified」语义组合的越级结论
  （受控词 `RUNTIME_UNVERIFIED`/`RUNTIME_NOT_REQUIRED` 不受影响）；
- **「production E2E 通过」类**：官方 AI Assistant 的 production E2E 已正式
  通过、以英文 PASS 收尾的组合结论（production 与 E2E 与 PASS 的英文组合
  即属此类）；
- **签署类**：D14E 业务/安全已最终签署、signoff 已批准、以 SIGNED 收尾的
  英文源词组合结论（受控状态行 `D14E_SIGNOFF_STATUS=BLOCKED` 不受影响，
  禁止任何等于 SIGNED 的赋值形式）；
- **赋值越级类**：D14B/D14C formal L3 与 D14E final acceptance 以 PASS 收尾的
  状态赋值、以及任意以 true 收尾的越级状态赋值
  （凡「等于 PASS」「等于 true」的越级赋值式均属此类）。

受控词 `BLOCKED`/`BLOCKED_BY_D14B`/`BLOCKED_BY_D14C`/
`BLOCKED_PENDING_D15C_HANDOFF`/`L3_READY`/`NOT_FROZEN`/`RUNTIME_UNVERIFIED`/
`WAITING_PREREQ` 必须保留使用。中文/自然语言同义越级（如最终锁定、发布就绪、
生产就绪的断言语义）同样受文档纪律约束，由独立 Reviewer 人工审查。

### 9.3 责任与 Reviewer

- **责任方**：本文件由 D15E 提交材料准备（Phase 0）维护；正式锁点判定与最终
  签署须由 D14E 业务/安全签署人依据真实 evidence 与 §7 触发条件人工完成，
  作者不得自审；
- **Reviewer**：本矩阵线的 Review 由 D14E 指定 Reviewer（按 CONTRIBUTING
  D/E 互审）执行；Evidence Reviewer 负责核验本文件引用的 identity/状态与
  evidence 事实一致；
- 任何越级结论、伪造 evidence、以 Mock 冒充 Runtime Test、把 D14B/D14C 未闭合
  写成通过、把 D14D L3_READY 解释为 release readiness 或 production readiness
  的行为，一律 fail-closed 拒绝并上升为阻断项。

---

*本文档为 D15E 最终提交材料准备与提交锁定矩阵（as-of 2026-09-09）。
最终锁定触发前必须按 §7 逐条重跑复核，任何变更均须 D14E 指定 Reviewer 会签。
本文件不宣布 D15E FINAL LOCK、不签署 D14E final acceptance。*
