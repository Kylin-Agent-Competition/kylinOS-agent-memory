# D13D 任务卡：P0-I3b-completion 完整闭环（Phase 2 PR 载体）

| 字段 | 内容 |
|------|------|
| phase | `P0-I3b-completion` |
| 施工项 | D13D「I3b-completion」：把主仓已合并的 P0-I3a + P0-I3b-infra 推进到 P0-I3b-completion = COMPLETE（Safety Gate-9 projection / Forget real dispatch / pref-003 正式处理 / 独立 Review + merge） |
| 责任轨道 | original_owner = D13D；current_executor = B＝高翌哲（2026-09-06 按分工清单代执行）；独立 Review 由非作者 Reviewer（D/E 分工）执行 |
| 工作类型 | `feat`（D13D integration / docs / tests） |
| 工作分支 | `feat/d13d-i3b-completion`（按提交分支要求命名，不含 `codex`） |
| base_commit（POST_PR159_MAIN_SHA） | `dc58e83479d718c8e3fbbbbb5d3b3f046f651973`（= PR #159 merge commit，main HEAD） |
| PR159_MERGE_SHA | `dc58e83479d718c8e3fbbbbb5d3b3f046f651973` |
| main_worktree_clean | YES（开工核对；本地工作树 clean） |
| opened_at_utc | `2026-09-06T11:55:55Z` |
| opened_by | B（高翌哲，Codex 代执行） |
| formal_tested_commit | `PENDING_P0_I3_RESELECTION`（本阶段不选择） |
| 状态 | `BLOCKED_PENDING_CROSS_TRACK_COMPLETION`（Draft 载体；P2-A/B/C 外部依赖闭合后逐项推进） |
| 初始 PR 状态 | Draft（转 Ready for review 由用户手动执行） |
| 编制日期 | 2026-09-06 |
| 完整详细工作清单 | 本地权威清单 `可直接查看/PR_Phase2_D13D_I3b_Completion_详细工作清单.md`；本卡为其仓库内执行摘要与状态载体 |

---

## 0. 开工硬 Gate（2026-09-06 已满足）

PR #159 已独立 Review 并 merge 到 main，Phase 2 开工基线重新冻结：

```text
PR159_MERGE_SHA     = dc58e83479d718c8e3fbbbbb5d3b3f046f651973
POST_PR159_MAIN_SHA = dc58e83479d718c8e3fbbbbb5d3b3f046f651973
main 已包含          PR #157 / PR #150 / PR #152 / PR #159
```

禁止把以下历史/前置 SHA 直接作为新的正式 `tested_commit`：

```text
4a32e5c948a968f3bd4409d91deac320002baea1
17dce3696066213b54e9dcbe6b87c4944cb41c8c
3e233af970d4769d869d55dfa8ca8f62facbd035
```

本阶段保持：

```text
formal_tested_commit = PENDING_P0_I3_RESELECTION
D13D                = BLOCKED（本 PR 不产生 D13D_FROZEN）
```

---

## 1. 唯一目标与边界

唯一目标：把主仓已合并的 `P0-I3a + P0-I3b-infra` 推进到 `P0-I3b-completion = COMPLETE`。

本 PR **不做**（属 Phase 3+）：

```text
formal tested_commit reselection
正式 VM 17 条 raw
Review Seal / Execution Seal / attestation
Runner Gate 0–10
D13D_FROZEN
D14D G0–G9
```

---

## 2. 权威 staging（当前）

| Stage | 范围 | 状态 |
| --- | --- | --- |
| P0-I3a | Versioned preflight / Dataset SHA anchor / isolation-shape checks / L1 | `MERGED`（经 PR #150 入 main） |
| P0-I3b-infra | Preference/Conflict real dispatch、Safety binding + provenance、execution receipts、Forget schema、canonical package | `MERGED`（经 PR #150 入 main） |
| P0-I3b-completion | Safety Gate-9 projection（D13E Gold-independent 裁定）+ Forget real dispatch（外部 binding + realtime/rebuild 观测）+ pref-003 正式处理 | `IN_PROGRESS`（本 PR 载体；P2-A/B/C 闭合前保持 `BLOCKED_PENDING_CROSS_TRACK_COMPLETION`） |
| P0-I3c | 非作者独立 review + merge（partial infra 已由 PR #150 完成；completion review 待 I3b-completion） | `PARTIAL-INFRA COMPLETE / COMPLETION REVIEW PENDING` |
| P0-I3d | I3b-completion 闭合后重新选择正式 tested_commit 并复验隔离 VM | `BLOCKED`（依赖 I3b-completion） |

Phase 2 完成并获批后才允许写：

```text
P0-I3b-completion = COMPLETE
P0-I3c-completion-review = APPROVED
P0-I3d = READY_TO_START
```

不得把历史 partial-infra APPROVE 直接当作 completion APPROVE。

---

## 3. 三个必须闭合问题（Phase 2 核心）

### P2-A｜Safety Gate-9 projection（Gold-independent）

- 现状：主仓 Safety infra（ValidatedRuntimeBinding / 四 hard-zero counters）已具备，但 `safety-001/002/003` 需真实 sensitivity/admission/operation + 真实 admission，正式状态仍 `CANDIDATE_PENDING_D13E_REVIEW / BLOCKED_PARTIAL`。
- 前置：D13E 先建独立 Safety raw projection contract（独立 PR，责任 D13E），D13D 只作 consumer。
- 约束：projection 只依据真实生产观测；禁止读 `D13E_GOLD_V1.jsonl` / expected / 按 sample_id 写死 / Mock / 固定零值。
- 关闭条件（摘要）：D13E projection PR review + merge；adapter 接入后 safety 001-004 均有真实来源并过 adapter→Runner contract；`CANDIDATE_PENDING_D13E_REVIEW` / `BLOCKED_PARTIAL`（Safety）退出。

### P2-B｜Forget external state-binding + real dispatch

- 现状：主仓只完成 Forget schema / forget_mode / receipt-provenance infra；五条正式 Forget 真实 dispatch 未完成（`BLOCKED_PENDING_EXTERNAL_BINDING`）。
- 前置：由获授权的业务/VM 执行责任方交付版本化 `external state-binding artifact`（binding_version / SHA-256 / owner / approval_reference / source commit / environment / VM-snapshot / state-root / DB identity）。
- 约束：5 个 sample（single_item / session / topic / time_window / full_reset）均需真实前置状态、foreign-user control、realtime retrieval observation、full rebuild observation；任一缺失 fail-closed 且不写 canonical raw。
- 关闭条件（摘要）：binding 交付并核验；5/5 real dispatch + 5/5 realtime + 5/5 rebuild + 5/5 receipt；无手工 target / 无 synthetic zero。

### P2-C｜Preference pref-003 正式缺口

- 现状：已登记 `pref-003` 真实 provider observation 与当前 Gold 不一致；4 条 Preference 预计 3/4=0.75 < 正式 threshold 0.85，不处理则 Phase 3 Runner Gate 9 必败。
- 前置：由业务 Owner + D13E Reviewer 具名裁决 root cause（A. production behavior incorrect；或 B. Gold/formal artifact definition incorrect）。
- 约束：adapter 不得 special-case pref-003；生产修复或 D13E artifact 修复必须走独立 PR（独立 Review + merge）。
- 关闭条件（摘要）：具名裁决 + 独立 PR 闭合 + 4 条 Preference 均可正常形成 formal actual。

---

## 4. 当前 GO / NO-GO（冻结）

```text
PR #159 merge 后建 Phase 2 分支        GO（已完成）
Safety projection 独立工作（D13E 侧）  GO
Forget binding 准备                   GO
Forget real-dispatch integration      CONDITIONAL GO（approved external binding 交付后）
pref-003 处理                         GO
选择 formal tested_commit             NO-GO
跑正式 VM 17 raw                      NO-GO
签 Seal / 标 D13D_FROZEN              NO-GO
```

---

## 5. 机械执行顺序（01–28）

```text
01. fetch/pull main                        （完成：dc58e834）
02. 记录 PR159_MERGE_SHA / POST_PR159_MAIN_SHA（完成：dc58e834）
03. 建 feat/d13d-i3b-completion             （完成）
04. 新增 Phase2 task card（本卡）            （本批）
05. 刷新 D13D authoritative status          （本批：本卡 + 24_ 任务卡状态同步）
06. 建/完成独立 D13E Safety projection PR   （跨轨，D13E）
07. merge Safety projection                 （跨轨）
08. D13D adapter 接入 Safety projection
09. 准备 Forget external binding artifact   （跨轨，业务/VM 责任方）
10. 独立复核 binding
11. 接入 Forget binding validator
12. 完成 5 mode real-dispatch capability
13. 完成 realtime/rebuild observation
14. 处理 pref-003 root cause（独立 PR）
15. merge pref-003 对应独立 PR
16. rebase Phase2 PR 到最新 main
17. 跑 adapter L1
18. 跑 Runner contract regression
19. 跑 Safety/Forget 定向 regression
20. Gold isolation 审计
21. CI green
22. 更新 P0-I3b-completion = READY_FOR_REVIEW
23. independent Review
24. 关闭 review findings
25. final APPROVE
26. merge Phase2 PR
27. 记录 I3B_COMPLETION_MERGE_SHA
28. handoff Phase3 / P0-I3d
```

---

## 6. Reviewer Gate / 完成定义 / 禁止表述

Reviewer 检查重点：

```text
Safety projection 是否真正 Gold-independent（不读 Gold/expected）
Forget target/retrieval observation 是否由真实 approved binding 提供
pref-003 是否没有 adapter hardcode
canonical raw 是否只来自真实 dispatch（含 provenance）
receipt/runtime provenance 是否继续 fail-closed
formal tested_commit 是否仍 PENDING
有无提前产生 VM/Seal/FROZEN overclaim
```

完成定义（同时满足）：

```text
Safety 4/4  真实观察 + Gold-independent projection
Forget 5/5  approved external binding + real preview/execute/retrieval/rebuild
Preference   pref-003 已正式处理
Conflict     保持真实 dispatch 能力
全部 provenance / fail-closed / Gold isolation PASS
独立 Review APPROVE → merge main
```

禁止提前表述：

```text
D13D_FROZEN / FORMAL PASS / L3_READY / HOST_VERIFIED / production ready
```

---

## 7. 本批变更与验证记录（2026-09-06 kick-off）

- 变更：新增本任务卡（`docs/day13/26_d13d_i3b_completion_worklist_20260906.md`），并把 `docs/day13/24_d13d_versioned_execution_adapter_task_card_20260906.md` 的 P0-I3 staging 中 `P0-I3b-completion` 更新为 `IN_PROGRESS`（追加 2026-09-06 kick-off 记录，不改写历史）。
- 未改动：生产代码、契约、Dataset/Gold/Threshold、既有历史任务卡正文、其他轨交付物。
- 验证：`git diff --check` PASS；UTF-8 无 BOM、LF；分支名不含 `codex`。
- 已知阻塞（跨轨，不在本批闭合）：P2-A 需 D13E 独立 Safety projection PR；P2-B 需外部 Forget state-binding artifact（owner/approval/SHA-256）；P2-C 需业务 Owner + D13E Reviewer 具名裁决。
- 后续：依赖闭合后按 §5 顺序推进代码集成（Commit 2-6），并同步权威任务卡状态。

## 8. D/E 回执裁定与状态推进（2026-09-06）

已收到 D/E 对跨轨协助请求（B-1/B-2/B-3）的书面回执。以下登记只做状态推进，不改写既有历史；作为 Phase 2 后续执行依据。

### 8.1 B-1 / P2-A Safety projection → `DECISION_READY / WAITING_INDEPENDENT_D13E_PR_AND_REVIEW`

D/E 裁定：

1. 保持现有 D13E Dataset / Gold / Threshold / Runner bytes 不变；
2. Safety projection 必须 Gold-independent；
3. safety-001/002：`sensitivity` 来自真实 dispatch trace 对应 persisted `source_events.sensitivity`；`admission` 来自 persisted `admission_decision` 稳定投影；缺真实事件、来源冲突或字段不唯一时 fail-closed；
4. safety-003：`operation` 来自已 SHA 验证的 Dataset input；`admission` 由真实 user-scoped repository read observation 推导，不得固定写 `reject`；
5. safety-004 维持四个 hard-zero counter；四个 Safety sample 均输出四项 hard-zero counter；
6. adapter 禁止读取 Gold / expected / threshold，禁止按 sample_id 写死 expected result。

现有 Runner 已允许 `expected fields + safety hard-zero counters`，因此本裁定不要求修改正式 Runner/Gold。

- D13D 侧待办：等 D13E 独立 projection PR 落地并 merge 后，作为 consumer 接入（§5 步骤 06–08）。

### 8.2 B-2 / P2-B Forget external state binding → `ACCEPTED / BLOCKED_PENDING_VM_BINDING_ARTIFACT`

D/E 裁定（接单，但仍需真实 VM state preparation）：

- 由独立业务/VM Owner 在隔离麒麟 VM snapshot 使用真实生产 Repository/API 预置合成状态，产出 `D13D_FORGET_STATE_BINDING_V1.json`；
- artifact 绑定 tested_commit / environment / VM snapshot / DB / state root；五个 sample 映射真实 DB/state identity；session/topic/time_window/full_reset 均须存在真实生产关系；每类 target kind 准备 same-user control 与 foreign-user same-kind control；
- confirmation token 不进入 artifact，由真实 `forget.preview` 动态产生；
- artifact 提供真实 realtime/full-rebuild retrieval 入口、snapshot/watermark/trace；
- D13D adapter 不得创建测试目标、不得伪造 observation、不得补零；任一输入缺失即 fail-closed 且不写 canonical raw；
- 正式执行可用 validation profile 显式注册真实 `forget.preview/forget.execute` handler；不得因此宣称 production default registration 已解除 `BLOCKED_BY_HOST_MAPPING`。

- D13D 侧待办：binding artifact 到位并核验后接入（§5 步骤 09–13）。

### 8.3 B-3 / P2-C pref-003 → `PRODUCTION_FIX_REQUIRED`

D/E 正式裁定：**A（production behavior incorrect）**。

- 根因：完整 `ExtractionProvider` candidate admission 入口使用 `PREFERENCE_EXPLICIT_PATTERN`，该表达式未覆盖 `优先使用/优先用/首选` 等显式工具选择表达；fallback instruction pattern 又要求临时时态限定词，导致 pref-003 在完整 production extraction path 中 false negative。
- 处置：另开独立 production PR，最小修复显式 tool-selection preference marker，补完整 Provider 回归和负样本测试。
- 禁止：修改 D13D adapter special-case pref-003；为通过 Gate 改写 Gold；降低 threshold。
- 当前 Gold 与既有 Preference helper 业务语义一致，不启动 D13E Dataset/Gold/Threshold/Runner re-baseline。
- 影响：修复走独立 PR（不入 PR #160）；合并后 D13D adapter 只消费修复后的真实结果。

### 8.4 状态汇总（2026-09-06 回执后）

```text
P2-A = DECISION_READY / WAITING_INDEPENDENT_D13E_PR_AND_REVIEW
P2-B = ACCEPTED / BLOCKED_PENDING_VM_BINDING_ARTIFACT
P2-C = PRODUCTION_FIX_REQUIRED（裁定 A：production behavior incorrect → 独立 production PR）

P0-I3b-completion 仍 = IN_PROGRESS / BLOCKED_PENDING_CROSS_TRACK_COMPLETION
formal_tested_commit 仍 = PENDING_P0_I3_RESELECTION
D13D_FROZEN = NO（本阶段不产生）
```

## 9. P2-B 承接与执行记录（2026-09-06）

### 9.1 授权与状态

- B（高翌哲）已获**完整明确授权**（用户 2026-09-06 确认）以业务/VM Owner 身份完成 P2-B Forget external state binding（D/E B-2 回执 ACCEPTED / BLOCKED_PENDING_VM_BINDING_ARTIFACT）。
- binding 目标 tested_commit：候选 `main@dc58e83479d718c8e3fbbbbb5d3b3f046f651973`（用户已确认；正式 tested_commit 仍 `PENDING_P0_I3_RESELECTION`，若 Phase 3 最终基线变化须重生成 binding）。
- 执行方式：VM 直连（用户选项 2），连接信息待用户提供后继续 VM 侧步骤。
- 状态：`P2-B = IN_PROGRESS`（本机可交付部分：#1 schema 契约 + #2 generator/verifier + #3 任务卡登记）。

### 9.2 执行清单

1. binding artifact V1 schema/字段冻结（见 `docs/day13/27_d13d_forget_state_binding_contract_20260906.md`）；
2. binding generator/verifier（模块 `memory-service/evaluation/d13d_forget_state_binding.py` + CLI `scripts/run_d13d_forget_state_binding.py` + 单测）；
3. 独立 Review（generator/verifier 代码与契约）；
4. 隔离麒麟 VM 干净快照 restore（候选 `d14d-clean-base-20260906-r2`）；
5. 真实生产 Repository/API 预置 5 sample（single_item/session/topic/time_window/full_reset）目标与 same-user/foreign-user controls；
6. 采集真实 DB/state identity + realtime/rebuild retrieval 入口/snapshot/watermark/trace → 生成 `D13D_FORGET_STATE_BINDING_V1.json` + SHA-256；
7. 独立复核 binding（confirmation token 不入 artifact；不读 Gold/expected）；
8. 接入本 PR：#160 集成 binding validator + 五模式真实 dispatch + observation。

### 9.3 约束（D/E B-2 裁定，不回写历史）

- artifact 绑定 tested_commit/environment/VM snapshot/DB/state root；
- 5 sample 映射真实 DB/state identity；session/topic/time_window/full_reset 须有真实生产关系；
- 每 target kind 备 same-user control 与 foreign-user same-kind control；
- confirmation token 不入 artifact，由真实 `forget.preview` 动态产生；
- artifact 提供真实 realtime/full-rebuild retrieval 入口、snapshot/watermark/trace；
- adapter 不得创建测试目标/伪造 observation/补零；缺输入 fail-closed 且不写 canonical raw；
- 正式执行可用 validation profile 显式注册真实 `forget.preview/forget.execute` handler；不得宣称解除 `BLOCKED_BY_HOST_MAPPING`。