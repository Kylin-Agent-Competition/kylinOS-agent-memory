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