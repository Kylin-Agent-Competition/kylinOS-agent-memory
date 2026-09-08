# D14E 第一阶段验收基线：业务、安全与比赛事实一致性（2026-09-08）

本文档是 D14E（业务/安全最终验收）第一阶段正式验收基线，用于在单一可审计位置聚合
「已闭合冻结事实 + 未闭合 upstream dependency + 状态边界 + 禁止 overclaim 规则」，
并作为确定性 pytest 守卫（见同目录 `test_d14e_phase1_acceptance_baseline.py`）的守护对象。

本任务为纯 docs / evidence-consumption / acceptance-governance 基线：
- `runtime_required=false`，不执行 L2/L3，不操作麒麟 VM；
- 不代替 D14B/D14C 完成 formal runtime；
- 不产生、不伪造任何 evidence/ 新条目、Seal、attestation、Release Candidate 或正式签署结论；
- 不签署最终业务/安全验收 PASS。

## 快照身份与状态行（Snapshot Identity）

| 字段 | 值 |
|------|-----|
| as-of | as-of=2026-09-08 |
| 扫描/当前分支 | `test/D14E-business-security-final-acceptance` |
| 当前分支 HEAD | `2bd5948`（commit message：`docs(D14D): mark PR165 merged and L3_READY (#168)`） |
| main HEAD | `2bd5948`（main 最近历史：`2bd5948` ← `ec7a66b`（D14D formal L3 evidence #165）← `632b24b` ← `ba3b50e`（feat(D13D) 正式执行闭环 #160）） |
| D13D/D14A/D14D 冻结 tested_commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` |
| evidence/index.yaml 引用 | 仅按 id 与路径引用既有条目 `D14A-FINAL-PACKAGE-FREEZE` 与 `D13D-FORMAL-CLOSURE-BA3B50E-20260908`；不改写其内容与哈希；本基线不新增条目 |
| 运行时验证状态 | RUNTIME_NOT_REQUIRED |

关键区分声明（独立一行，逐字）：

**主分支 main HEAD（`2bd5948`）≠ D13D/D14A/D14D 冻结 tested_commit（`ba3b50e1bdeea185bca9daee9d1d45958f62a636`）。**

main HEAD `2bd5948` 是 D14D 文档合并（#168）后的仓库顶点；frozen tested_commit
`ba3b50e1bdeea185bca9daee9d1d45958f62a636` 是 D13D/D14A/D14D 正式执行（#160 闭环、
#165 正式 L3）的冻结基线。两者是不同的 Git 对象，也都不等于各 package/report/evidence
的 SHA-256（D14A tar/manifest/SHA256SUMS SHA、D13E report SHA 等均为独立哈希对象）。

本快照按 2026-09-08 仓库状态记录，**可失效**；最终签署前必须以 `git rev-parse HEAD`
与 `git status` 重新核验分支、HEAD 与工作区状态，任何前移或分支切换都会使本快照过期。

### 状态行

D14E_PHASE1_ACCEPTANCE_BASELINE=READY
D14E_FINAL_ACCEPTANCE=BLOCKED
D14E_SIGNOFF_STATUS=BLOCKED

说明：上述三条为独立状态行。只有「第一阶段事实聚合与文档守卫」置为 READY；
D14E 最终业务/安全验收仍为 BLOCKED，SIGNOFF 状态仍为 BLOCKED。文档准备完成
（本文档 + pytest 通过）**不等同于**最终签署，后续任何签署动作都必须走 E 节触发条件。

---

## A. 当前开工与验收状态

### A.1 与 2026-09-05 历史骨架（docs/d14e-preacceptance 20/21/22）的差异与失效原因

- 2026-09-05 曾在未合并分支 `docs/d14e-preacceptance`（tip `5cad210`）建立
  `docs/day14/` 下 `20/21/22_*` 历史骨架（含配套 pytest）。
- 该分支未合入 main，其内容早于 D13D_FROZEN（2026-09-08 冻结记录）与
  D14D L3_READY（2026-09-07 正式 L3 + #165/#168 合并）两批冻结事实，
  所依赖的验收前置条件与证据基线已被主线事实取代，**整体失效**。
- 本文件不迁移、不修改、不将 `20/21/22_*` 标记为生效，仅作历史引用；
  2026-09-08 的正式验收基线以本文件（`23_*`）为准。

### A.2 当前开工/验收状态

| 维度 | 状态 |
|------|------|
| D14E 开工状态 | 已开工：建立第一阶段验收基线（A–E 五节聚合 + 确定性 pytest 守卫） |
| 已闭合事实（冻结 evidence） | D13D formal 执行闭环、D13E formal metrics、D14A final package identity、D14D clean Kylin L3 evidence（带边界） |
| 未闭合 upstream | D14B（检索/索引生命周期发布回归）、D14C（Real AI Assistant E2E）：均未合入 main，formal L3 均 BLOCKED / UNVERIFIED |
| 最终业务/安全验收 | BLOCKED（未签署，本任务不签署） |

### A.3 本基线的职责边界

- 仅消费已冻结 evidence 事实并做一致性聚合与守卫；
- 不执行 L2/L3、不产生新验证事件、不新增 evidence/index.yaml 条目；
- 不替 D14B/D14C 补写生产实现或正式 Runtime 证据；
- 不降低既有 Gate、不删除测试、不通过修改验收标准获得 PASS。

---

## B. D14E Acceptance Matrix

| 行 | 事项 | owner | required artifact | evidence path | tested commit | artifact/package SHA | environment/run ID | status | blocker | reviewer |
|----|------|-------|-------------------|---------------|---------------|----------------------|--------------------|--------|---------|----------|
| B1 | Preference 业务事实线（D13E formal） | E 轨道（业务域） | D13E formal 结果（D13E_FORMAL_REPORT_V1.json 内 Preference 段） | evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/evidence/D13E_FORMAL_REPORT_V1.json | ba3b50e1bdeea185bca9daee9d1d45958f62a636 | report SHA-256 dee80d5044c2194b79f13e7185b39f0162c63468f7a47b86799a1abb23c489ee | d13d-phase3-formal@Kylin-D14D-clean-vdi-20260906:d14d-clean-base-20260907-r4 | VERIFIED（n=4, accuracy=1.0，达 D13E formal 阈值） | 无（formal 小样本，禁止外推全场景，见 C 节边界2） | 非作者指定 Reviewer（按 CONTRIBUTING D/E 互审） |
| B2 | Conflict 业务事实线（D13E formal） | E 轨道（冲突域） | D13E formal 结果（D13E_FORMAL_REPORT_V1.json 内 Conflict 段） | evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/evidence/D13E_FORMAL_REPORT_V1.json | ba3b50e1bdeea185bca9daee9d1d45958f62a636 | report SHA-256 dee80d5044c2194b79f13e7185b39f0162c63468f7a47b86799a1abb23c489ee | d13d-phase3-formal@Kylin-D14D-clean-vdi-20260906:d14d-clean-base-20260907-r4 | VERIFIED（n=4, accuracy=1.0，达 D13E formal 阈值） | 无（formal 小样本，禁止外推全场景，见 C 节边界2） | 非作者指定 Reviewer（按 CONTRIBUTING D/E 互审） |
| B3 | Safety 业务事实线（D13E formal） | E 轨道（安全域） | D13E formal 结果（D13E_FORMAL_REPORT_V1.json 内 Safety 段） | evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/evidence/D13E_FORMAL_REPORT_V1.json | ba3b50e1bdeea185bca9daee9d1d45958f62a636 | report SHA-256 dee80d5044c2194b79f13e7185b39f0162c63468f7a47b86799a1abb23c489ee | d13d-phase3-formal@Kylin-D14D-clean-vdi-20260906:d14d-clean-base-20260907-r4 | VERIFIED（n=4, violations=0，达 D13E formal 阈值） | 无（violations=0 不构成绝对安全声明，见 C 节边界3） | 非作者指定 Reviewer（按 CONTRIBUTING D/E 互审） |
| B4 | Forget 业务事实线（D13E formal） | E 轨道（遗忘域） | D13E formal 结果（D13E_FORMAL_REPORT_V1.json 内 Forget 段） | evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/evidence/D13E_FORMAL_REPORT_V1.json | ba3b50e1bdeea185bca9daee9d1d45958f62a636 | report SHA-256 dee80d5044c2194b79f13e7185b39f0162c63468f7a47b86799a1abb23c489ee | d13d-phase3-formal@Kylin-D14D-clean-vdi-20260906:d14d-clean-base-20260907-r4 | VERIFIED（n=5, violations=0，达 D13E formal 阈值） | 无（violations=0 不构成未来场景绝不残留声明，见 C 节边界4） | 非作者指定 Reviewer（按 CONTRIBUTING D/E 互审） |
| B5 | D13D formal provenance / dual Seal / Runner | D 轨道（Runner/Seal/发布流程） | D13D 冻结记录（D13D_FREEZE_RECORD_20260908.md） | evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/D13D_FREEZE_RECORD_20260908.md | ba3b50e1bdeea185bca9daee9d1d45958f62a636 | N/A（非发布包；冻结记录含 17 raw、双 Seal 引用） | phase3-formal（Runner Gate 0-10 PASS） | FROZEN | 无（已冻结；evidence/index.yaml 既有条目 D13D-FORMAL-CLOSURE-BA3B50E-20260908） | 非作者指定 Reviewer（按 CONTRIBUTING D/E 互审） |
| B6 | D13E formal metrics 整体 | E 轨道（业务指标）+ D 轨道（Runner 执行） | D13E formal 报告 + Dataset/Gold/Threshold 身份 | evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/evidence/D13E_FORMAL_REPORT_V1.json | ba3b50e1bdeea185bca9daee9d1d45958f62a636 | report SHA-256 dee80d5044c2194b79f13e7185b39f0162c63468f7a47b86799a1abb23c489ee；Dataset SHA 9740c00f…/Gold SHA aeea9bea…/Threshold SHA 561034df…（全量以冻结记录为准） | d13d-phase3-formal@Kylin-D14D-clean-vdi-20260906:d14d-clean-base-20260907-r4 | VERIFIED（阈值：Preference/Conflict accuracy>=0.85/0.88、Safety/Forget violations=0；实测见 B1–B4） | 无（formal 小样本：4/4/4/5，禁止无限定外推） | 非作者指定 Reviewer（按 CONTRIBUTING D/E 互审） |
| B7 | D14A final release package identity | A 轨道（包内容）+ D 轨道（release 流程） | D14A final package freeze record | evidence/l3-kylin-vm/d14a_final_package_20260908/D14A_FINAL_PACKAGE_FREEZE_RECORD_20260908.md | ba3b50e1bdeea185bca9daee9d1d45958f62a636 | kylin-memory-a-d14a 0.1.0-d14a；tar SHA 2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401；manifest SHA 76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0；SHA256SUMS SHA 8540cd1dc2b8c743bc466cd89f435e09940ddc5e5df842cacb9367021eddcf67；manifest files=3360 | d14a_final_package_20260908 | FROZEN | 无（已冻结；evidence/index.yaml 既有条目 D14A-FINAL-PACKAGE-FREEZE；仅指 package identity 冻结，不代表 production release） | 非作者指定 Reviewer（按 CONTRIBUTING D/E 互审） |
| B8 | D14D clean Kylin L3 evidence | D 轨道（L3 执行与证据） | D14D L3 evidence root（gate_matrix 等） | evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/ | ba3b50e1bdeea185bca9daee9d1d45958f62a636 | N/A（evidence root；PR #165 squash merge ec7a66b、#168 docs merge 2bd5948） | Kylin clean VM（D14D 2026-09-07 L3 run） | L3_READY=true；release_ready=false；production_ready=false | 无（G0–G6 PASS；G7 NOT_RUN/N-A；G8 NOT_RUN waiver；不构成 production ready） | 非作者指定 Reviewer（按 CONTRIBUTING D/E 互审） |
| B9 | Retrieval lifecycle 发布回归 / D14B | B 轨道（检索/索引回归） | D14B formal L3 evidence root（缺失） | 无 formal evidence root（仅 harness/runbook/preparation：15_d14b_l3_formal_harness_contract_20260907.md、16_d14b_formal_execution_runbook.md，位于分支 test/D14B-l3-vm-release-regression） | N/A（未执行 formal L3；分支 tip 85a35cd / upstream tip 6fb057a，2026-09-08 扫描快照） | N/A | N/A（未执行；需 Kylin VM） | BLOCKED_BY_D14B | D14B_FORMAL_L3=BLOCKED；D14B_FORMAL_RESULT=UNVERIFIED；未合入 main | 非作者指定 Reviewer（按 CONTRIBUTING D/E 互审） |
| B10 | Real AI Assistant E2E / D14C | C 轨道（OS Agent Hook/MemoryClient/E2E） | D14C formal L3 evidence root（缺失） | 无 formal evidence root（仅 worklist/静态审计/preflight 02-09 文件，位于分支 test/D14C-l3-clean-vm-release-regression；最后一次静态审计基于 origin/main@632b24b） | N/A（未执行 formal L3；分支 tip ac0c58b / upstream tip b2f533e，2026-09-08 扫描快照） | N/A | N/A（未执行；需 Kylin VM） | BLOCKED_BY_D14C | D14C_FORMAL_L3=BLOCKED；D14C_FORMAL_RESULT=UNVERIFIED；未合入 main | 非作者指定 Reviewer（按 CONTRIBUTING D/E 互审） |
| B11 | Demo/video fact alignment | D14E 验收组（业务/安全） | Demo/视频素材与其声称事实的对照表 | N/A（尚无对照 artifact；须复用 C 节 claim 映射） | N/A | N/A | N/A | PENDING_UPSTREAM（等价受控：待 D14B/D14C 事实与最终材料就绪） | 依赖 D14B/D14C 闭合后的真实演示内容与最终事实基线核对 | 非作者指定 Reviewer（按 CONTRIBUTING D/E 互审） |
| B12 | Final D14E signoff | D14E 业务/安全签署人（人工） | 最终业务/安全签署结论（本任务不产生） | N/A（后续 D14E final 流程新建） | N/A | N/A | N/A | BLOCKED | D14B/D14C 未闭合 + E 节触发条件未满足前不得签署 | 非作者指定 Reviewer（按 CONTRIBUTING D/E 互审） |

矩阵状态词规则：已闭合行（B1–B8）只使用与真实 evidence 一致的 VERIFIED / FROZEN /
L3_READY 状态并附边界说明；依赖 D14B/D14C 的行（B9/B10）严格使用 BLOCKED_BY_D14B /
BLOCKED_BY_D14C；B11/B12 使用受控 PENDING_UPSTREAM / BLOCKED，均不构成完成态。

---

## C. Claim-to-Evidence 与比赛叙事事实映射

规则：每条可对外（比赛/演示）声明的 claim 必须可回溯到正式 evidence 路径 +
identity 绑定（tested_commit / package SHA / report hash）+ 环境/run ID，
并给出「当前是否允许作为最终比赛事实」的判定。不允许的 claim 只能作为
「前置未闭合/待刷新」出现，不得写成已达成事实。

| claim | 正式 evidence 路径 | identity 绑定 | 当前是否允许作为最终比赛事实 | 允许性条件/约束 |
|-------|---------------------|---------------|------------------------------|------------------|
| C1 D13D 正式执行闭环完成（17 raw、双 Seal、Runner Gate 0-10 PASS） | evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/D13D_FREEZE_RECORD_20260908.md | tested_commit ba3b50e1bdeea185bca9daee9d1d45958f62a636；index id D13D-FORMAL-CLOSURE-BA3B50E-20260908 | 允许（范围限定：D13D formal 执行闭环） | 不得扩展为 Day14 全链路或 production 结论 |
| C2 业务域 formal 指标达阈值（Preference/Conflict n=4 accuracy=1.0；Safety n=4 violations=0；Forget n=5 violations=0） | evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/evidence/D13E_FORMAL_REPORT_V1.json | report SHA-256 dee80d5044c2194b79f13e7185b39f0162c63468f7a47b86799a1abb23c489ee；Dataset/Gold/Threshold SHA 见冻结记录 | 允许（必须带 n、阈值与 formal 环境限定） | 禁止无限定外推为全场景/整体性能（边界2） |
| C3 D14A final release package identity 已冻结 | evidence/l3-kylin-vm/d14a_final_package_20260908/D14A_FINAL_PACKAGE_FREEZE_RECORD_20260908.md | package kylin-memory-a-d14a 0.1.0-d14a；tar/manifest/SHA256SUMS SHA 见 B7；index id D14A-FINAL-PACKAGE-FREEZE | 允许（仅指 package identity 冻结） | 不代表 production release |
| C4 D14D clean Kylin L3 evidence READY | evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e/ | tested_commit ba3b50e…；PR #165 ec7a66b、#168 2bd5948 | 允许（必须带 L3_READY 边界） | 必须保留 release_ready=false / production_ready=false、G7 N/A、G8 waiver（边界1） |
| C5 Day14 检索/索引生命周期发布回归最终通过 | 无正式 evidence（D14B 未闭合） | 分支 test/D14B-l3-vm-release-regression（tip 85a35cd / upstream 6fb057a） | **不允许**（当前不可声明） | 待 D14B 闭合并 merge main（边界6） |
| C6 官方 AI Assistant production E2E 已正式通过 | 无正式 evidence（D14C 未闭合） | 分支 test/D14C-l3-clean-vm-release-regression（tip ac0c58b / upstream b2f533e） | **不允许**（当前不可声明） | 待 D14C 闭合并 merge main（边界5） |
| C7 D14E 业务/安全最终签署 PASS | N/A（后续 final 流程产生） | N/A | **不允许**（当前不可声明） | 三条状态行保持 BLOCKED（边界见下） |
| C8 Demo/视频素材与比赛叙事一致 | N/A（对照 artifact 待建） | N/A | **不允许**（当前不可声明） | 须在 D14B/D14C 事实与最终素材就绪后逐条核对（边界5/6 同源） |

### C.0 禁止 overclaim 边界（8 类，逐字守卫）

- 【BOUND-1】不得把 D14D 的 L3_READY 状态写成 production ready；必须保留
  `L3_READY=true` 与 `release_ready=false`、`production_ready=false` 边界，
  不得声明 release_ready 或 production_ready 为真。
- 【BOUND-2】不得把 D13E formal 小样本（Preference/Conflict n=4、Safety n=4、
  Forget n=5）的通过结果写成未经限定的全场景/整体性能结论。
- 【BOUND-3】Safety violations=0 仅表示本次 formal 样本内未观察到违规，
  不得写成绝对安全。
- 【BOUND-4】Forget violations=0 仅表示本次 formal 样本内未观察到残留，
  不得写成所有未来场景绝不残留。
- 【BOUND-5】在 D14C 未闭合前，不得宣称官方 AI Assistant 的 production E2E
  已正式通过。
- 【BOUND-6】在 D14B 未闭合前，不得宣称 Day14 检索/索引生命周期发布回归
  已最终通过。
- 【BOUND-7】不得混淆以下不同对象：frozen tested_commit（ba3b50e1bd…）、
  D14A package SHA（tar/manifest/SHA256SUMS）、evidence/report SHA-256 与
  main HEAD（2bd5948）；它们互相不得冒充相等。
- 【BOUND-8】D14E 职责止于验收基线与守卫；不得越界修改生产代码或既有
  evidence（冻结 root/raw/Seal/attestation/SHA256SUMS/evidence_index.yaml）。

---

## D. 未闭合 Upstream Dependency 清单

以下两分支均为未合入 main 的 upstream，依赖其闭合方可推进 D14E final signoff。
所有分支 tip 均为 2026-09-08 扫描快照值，最终签署前必须重新扫描刷新。

### D1. D14B（Retrieval lifecycle / 发布回归）

- 分支 ref：`origin/test/D14B-l3-vm-release-regression` → tip `85a35cd`
  （2026-09-08 扫描）；upstream tip `6fb057a`。
- 现有内容：仅 harness/runbook/preparation，即
  `15_d14b_l3_formal_harness_contract_20260907.md`、
  `16_d14b_formal_execution_runbook.md`。
- 状态：`D14B_FORMAL_L3=BLOCKED`；`D14B_FORMAL_RESULT=UNVERIFIED`。
- 缺失 handoff 输入：正式 L3 执行结果、formal evidence root（含 raw/Seal/
  attestation）、与冻结基线的 tested_commit 对齐、merge 到 main 的合入记录、
  release_ready/production_ready 的明确判定。
- 刷新要求：正式执行前用 `git rev-parse`/`git ls-remote origin` 重新扫描
  两 tip；执行结果必须绑定实际 used commit，不得引用本快照 tip 作为执行身份。

### D2. D14C（Real AI Assistant E2E / 官方助手集成）

- 分支 ref：`origin/test/D14C-l3-clean-vm-release-regression` → tip `ac0c58b`
  （2026-09-08 扫描）；upstream tip `b2f533e`。
- 现有内容：仅 worklist/静态审计/preflight 准备（02-09 文件）；其最后一次
  静态审计基于 `origin/main@632b24b`，在 D13D_FROZEN（#160 后）/D14D_L3_READY
  （#165/#168 后）handoff 之后必须刷新。
- 状态：`D14C_FORMAL_L3=BLOCKED`；`D14C_FORMAL_RESULT=UNVERIFIED`。
- 缺失 handoff 输入：基于最新 main 的静态审计刷新、正式 L3 E2E 执行、
  formal evidence root、tested_commit 对齐、merge 到 main 的合入记录。
- 刷新要求：同上（执行前重新扫描 tip，审计基线升级到 ≥ 当前 main 顶点后再执行）。

### D3. 通用约定

- 两分支均无 formal evidence root、均未 merge 到 main；
- 本清单所有 tip/状态在最终签署前必须重新扫描刷新，任何前移不自动改变本基线
  内容的正确性（本基线为 2026-09-08 快照）。

---

## E. Final Delta Review 与 Signoff 触发条件

本文档准备完成与 pytest 通过**不构成**最终签署。仅当以下条件**全部**满足后，
才允许由业务/安全签署人（人工）发起 D14E final signoff（另建后续 D14E final
文档记录结论并迁移状态行；该动作超出本任务范围）：

1. **快照身份重新核验**：在最终签署日执行 `git rev-parse HEAD`、
   `git status`、`git branch --show-current`，确认分支与 HEAD；若与本文档
   as-of=2026-09-08 快照不一致，须先刷新本基线或新文档中的身份声明。
2. **refs 刷新**：重新扫描 `origin/test/D14B-l3-vm-release-regression` 与
   `origin/test/D14C-l3-clean-vm-release-regression`（含 upstream）的 tip 与
   merge 状态；任何 tip 前移或已合入 main 都须在最终材料中反映。
3. **D14B 闭合前置**：D14B formal L3 已在麒麟 VM 实际执行并有 formal
   evidence root（raw/Seal/attestation），`D14B_FORMAL_L3` 与
   `D14B_FORMAL_RESULT` 具备真实结果且绑定实际 used commit，分支合入 main。
4. **D14C 闭合前置**：D14C 基于 ≥ 当前 main 顶点刷新静态审计后，formal L3
   E2E 已在麒麟 VM 实际执行并有 formal evidence root，分支合入 main。
5. **evidence 完整性复核**：逐一复核本文档引用的 evidence 路径真实存在、
   D13E report SHA-256（dee80d50…）、D14A 各 package SHA、Dataset/Gold/
   Threshold SHA 与仓库一致；确认冻结 root/index.yaml 未被改写、未新增伪条目。
6. **身份防混淆复核**：确认 final 材料中 main HEAD、frozen tested_commit
   （ba3b50e1bd…）、package SHA、evidence/report SHA 四类对象互相区分且各自
   准确（BOUND-7）。
7. **overclaim 终检**：对全部比赛/演示材料逐条执行 C 节允许性判定，
   确认不存在 BOUND-1…BOUND-8 任一越级表述；D14D 仍保留
   release_ready=false / production_ready=false 边界直至正式 release 判定。
8. **人工签署**：由 D14E 业务与安全签署人（非文档作者、非本任务执行者）基于
   上述全部前置独立核验后签署；签署结论以新建 D14E final 文档为准，并显式
   迁移三条状态行（D14E_FINAL_ACCEPTANCE、D14E_SIGNOFF_STATUS）为最终值。

任一条件未满足时，D14E_FINAL_ACCEPTANCE 与 D14E_SIGNOFF_STATUS 必须保持
BLOCKED，不得提前签署。
