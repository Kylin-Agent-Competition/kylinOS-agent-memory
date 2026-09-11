# D Track Status (SSOT)

> 依据《D轨当前状态与简化流程交接_20260907》§6.1 建立的统一状态 SSOT。
> 历史任务卡（`24_`/`26_`/`29_`/`30_`/`31_`/`32_`/`33_`/`34_`）保留为
> HISTORICAL / REFERENCE，从本文件生效起不再要求同步维护其"当前状态"。
> As-of: 2026-09-11（D13D_FROZEN + D14A historical package/hash freeze + D14D
> `L3_READY` + historical D15D release identity retained at its release commit
> and superseded for current main + D15A prerequisite refresh）。

## D13D

| 字段 | 值 |
| --- | --- |
| 任务 | Versioned Execution Adapter / P0-I3b-completion |
| 状态 | Phase 2 DONE；Phase 3 formal closure DONE；`D13D_FROZEN` |
| PR #160 | MERGED @ 2026-09-07T13:41:54Z |
| `I3B_COMPLETION_MERGE_SHA` | `ba3b50e1bdeea185bca9daee9d1d45958f62a636`（PR #160 merge SHA / frozen tested baseline） |
| 已完成 | P2-A `CONTRACT_MERGED / ADAPTER_CONSUMER_CLOSED`；P2-B dual-channel 5/5 candidate closure（Reviewer E final APPROVE，2026-09-07T13:09Z）；P2-C COMPLETE；Phase 3 formal VM 17 raw；E-track authority `APPROVED_FOR_PHASE3_FORMAL_RAW_EXECUTION`；D13E Review Seal + D13D Execution Seal；frozen trust root 安装；Runner Gate 0-10 PASS；TD-061 关闭；`D13D_FROZEN` |
| 未完成（Phase 3） | 无（D13D 范围）。D14A final package / formal hash freeze 属后续独立任务 |
| Phase 3 Evidence root | `evidence/phase3-formal/d13d_formal_raw_20260907T154241Z_ba3b50e/evidence`（17/17 canonical raw + 17 dispatch receipts；双 Seal；Runner Gate 0-10 PASS；`D13E_FORMAL_REPORT_V1.json` SHA-256 `dee80d5044c2194b79f13e7185b39f0162c63468f7a47b86799a1abb23c489ee`） |
| tested_commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636`（final tested commit 已随 `D13D_FROZEN` 生效） |
| Trust Root / Seal 材料边界 | `/etc/kylin-memory/trust` 已安装；两个 Ed25519 私钥仍分别由 Reviewer D / E 本机持有；仓库、evidence root、CI、VM 与聊天均不持有私钥 |
| Reviewer | lovezy0730-create（E） |
| Dataset identity correction | 实际执行的 Dataset 为 `ba3b50e...` 的 LF 字节，SHA-256 `9740c00f...`；`036954...` 是 Windows CRLF checkout 副本，不是正式 Dataset 身份。evidence 根内的 metadata/输入副本已在 `85d86a1...` 对齐；该修正不改变 raw/receipt/log 哈希。 |

## D14D

| 字段 | 值 |
| --- | --- |
| 任务 | L3 干净快照发布 Gate、安装生命周期、回退与证据闭环 |
| 状态 | DONE（`L3_READY`）；HIGH-02 CLOSED；BLOCKER-01 CLOSED |
| PR #165 | MERGED @ 2026-09-08T11:37:40Z；final reviewed HEAD `cb6c528e6f5a88d7a9c847f8a597597f1e70638a`；squash merge SHA `ec7a66b3e52f8d76b156300d375467290fdc42b6` |
| Review | ① 2026-09-07T14:37Z `REQUEST_CHANGES`（BLOCKER-01、HIGH-02）；② 2026-09-07T15:15Z HIGH-02 **ACCEPT / CLOSED**；③ 2026-09-08 复审 BLOCKER-01 CLOSED 并给出 final APPROVE（2026-09-08T11:33:40Z，绑定 `cb6c528...`） |
| 已执行 | G0-G6 全 PASS（真实麒麟 VM，pre-formal observation 定位，Reviewer 认可 raw 真实性）；G7 = NOT_RUN / N-A（D-09 裁定）；G8 = NOT_RUN（D-10 裁定） |
| G8 裁定 | **正式 waiver**（D 主审，2026-09-07）：G8 维持 NOT_RUN，按 D-10 边界豁免，作为进入 `L3_READY` 的正式前置闭合 |
| 已闭合前置 | `D13D_FROZEN`；final tested_commit = `ba3b50e1bdeea185bca9daee9d1d45958f62a636`；G8 正式 waiver；`A_FINAL_PACKAGE_READY = YES` |
| 未完成 | 无（D14D 范围）。后续 D15A 正式锁点须独立刷新/复核，不以 D14D 状态替代 |
| Evidence root | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e`（tested_commit `ba3b50e`，package tar SHA `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401`） |
| 边界 | `L3_READY=true`；`release_ready=false`；`production_ready=false` |

## D14A

| 字段 | 值 |
| --- | --- |
| 状态 | `A_FINAL_PACKAGE_READY = YES`；final package / formal hash `FROZEN` |
| Package identity | package `kylin-memory-a-d14a 0.1.0-d14a`；source/tested commit `ba3b50e1bdeea185bca9daee9d1d45958f62a636`；package tar SHA-256 `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401`；manifest SHA-256 `76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0`；SHA256SUMS SHA-256 `8540cd1dc2b8c743bc466cd89f435e09940ddc5e5df842cacb9367021eddcf67`；manifest files `3360` |
| Freeze record / index | `evidence/l3-kylin-vm/d14a_final_package_20260908/D14A_FINAL_PACKAGE_FREEZE_RECORD_20260908.md`；`evidence/index.yaml` `D14A-FINAL-PACKAGE-FREEZE` |
| 复用依据 | `ba3b50e…..HEAD` 的变更不含 `packaging/`、`memory-service/`、`cpp-bridge/`、`migrations/`、`config/`，按 D14A contract v4 §1.1 分类为 `DOCS_EVIDENCE_ONLY`；现有包身份免重打包 |
| 边界 | 本登记只冻结 package identity；BLOCKER C 保持 `HANDOFF_REQUIRED`；PR #165 已按冻结 package identity 通过 final review 并合并 |

## D15D

| 字段 | 值 |
| --- | --- |
| 任务 | 发布候选与提交材料锁定 |
| 状态 | `HISTORICAL_VALID_AT_RELEASE_COMMIT / SUPERSEDED_FOR_CURRENT_MAIN / RUNTIME_EVIDENCE_STALE_PENDING_REBUILD` |
| Historical release identity | release_commit `4a6323fb3a8c73e0b15f1f3629d28dfc12071541`；package `kylin-memory-a-d14a 0.1.0-d14a`；tar SHA-256 `974c2584a08bc2ae5277a8526ce3c5dbd711bc0d54c9844e99d658892cca9f28`；manifest SHA-256 `4b42d9281e1fac269bc0e0ba43d831317424fc6200a751380ebf985241124ec4`；SHA256SUMS SHA-256 `9d1ac01fab8a2a876b97ffc5ffd375085661c78029b03a35c6984b7c91f4d9f4` |
| Current-main freshness | `release_commit_is_current_main=false`；`runtime_sensitive_drift_since_release_commit=true`；`frozen_package_lock_valid=false`；`rebuild_required=true`；`rebuild_completed=false`；`host_vm_required=true`；`host_vm_completed=false` |
| Historical release evidence | `evidence/d15d-lock/20260910T205300Z`；C1/C3-C6/C8 PASS；C7 为干净 tar 的 install → migration → start → real SDK dim=768 → restart → rollback smoke；C11 采用替代正式化 release binding；C12 PASS；C13 SIGNED。这些结果只适用于 `4a6323f` release-commit scope，不作为 current-main release lock |
| PR #175 | MERGED @ 2026-09-10T15:19:37Z；Reviewer E final APPROVE / G-D7 SIGNED；reviewer account `lovezy0730-create`；reviewed head `702973e3fc05f9c8435dd82f662788e448eda487`；squash merge SHA `ad782f5be747d9d59f273c1c0813535d62b50dcb` |
| PR #177 closeout | MERGED @ 2026-09-10T17:52:08Z；Reviewer E APPROVE；reviewed head `8dc21f7df7ea359b880efc93902569a5ca4187d8`；squash merge SHA `6e9f56d2983b36c3b174e7acf6687c4af79439d4` |
| PR #178 | MERGED；main HEAD `e62d525e3b7baf2bd4cd18ad8c2128a10aba8a96`；仅记录 closeout merge commit |
| Manifest / contract | `docs/day15/D15D_VERSION_MANIFEST.json` v2；contract v5 `SIGNED_V5 / REVIEWER_E_IDENTITY_ADJUDICATION_APPROVED / G_D7_SIGNED` |
| Historical boundary | D14A package identity `ba3b50e...` / tar `2222c904...` 只保留为 historical scope；不冒充 historical D15D release identity |
| 边界 | `L3_READY=true` 仅继承 D14D 范围；`release_ready=false`；`production_ready=false`；historical D15D 不宣称 current-main runtime/model identity closure |

## D15A

| 字段 | 值 |
| --- | --- |
| 任务 | A 轨发布候选正式锁点（A15-1 / A15-2 / A15-3） |
| 状态 | `IN_PROGRESS`；A15-1 / A15-3 既有 evidence refresh 只能做 historical cross-check；current-main release identity 等待 runtime package rebuild 与 Kylin VM revalidation 后再进入 D 主审判定；A15-2 仍 `BLOCKED` |
| 当前事实 | current main HEAD `657dbb9d18c7cb863924380c7dfac674c8ca36d1`；historical D15D release_commit `4a6323fb3a8c73e0b15f1f3629d28dfc12071541`；tested_commit `ba3b50e1bdeea185bca9daee9d1d45958f62a636`；D15A current-main 判定不得把 historical release identity 当作已通过的新 release 前置 |
| A15-1 | READY_FOR_REVIEW：package manifest 记录 `runtime/bridge/kylin_embedding.cpython-312-x86_64-linux-gnu.so` SHA-256 `a271891238102d0299395284d486c2e5afdaa4494e6ab0d1ff51a2d2ab9d4db6`；G2 dependency / RPATH / path audit PASS；build identity 与 builder command 已登记。待 D 主审判定，不预先宣称正式锁 |
| A15-2 | `BLOCKED`：D14D G8 维持 `NOT_RUN` waiver；D13A perf 三轮基线为 `INVALIDATED`。需 D13A owner / D 主审给出 package-only runner + thresholds，或作出适用于 A15-2 的明确正式范围裁定；涉及性能结论须 E 补审 |
| A15-3 | READY_FOR_REVIEW：`VERSION` / `manifest.package_version` 均为 `0.1.0-d14a`；`manifest.source_commit` = tested_commit = `ba3b50e...`；package tar / manifest / SHA256SUMS 已冻结且 G2 integrity PASS。待 D 主审判定，不预先宣称正式锁 |
| 未完成 | A15-1/2/3 的 D 主审逐项会签；A15-2 性能证据缺口；涉及安全/性能结论时的 E 补审 |
| 边界 | 不改变 D15A 矩阵的 `WAITING_PREREQ` 基线；不宣称 runtime/model identity closure；`release_ready=false`；`production_ready=false` |

## D14B

| 字段 | 值 |
| --- | --- |
| 任务 | 检索/索引生命周期 Formal L3 |
| 状态 | `F0_FORMAL_INTAKE=BLOCKED`；`D14B_FORMAL_L3=NOT_RUN/UNVERIFIED` |
| 标准输入 | `release/handoff/d13d-handoff.json`、`release/handoff/d14d-handoff.json`、`release/handoff/d14b-capture-handoff.json` 已入库 |
| 当前阻塞 | 原始冻结包字节 `kylin-memory-a-d14a-0.1.0-d14a.tar.gz` 已找到并复核 SHA-256；formal preflight 到 capture stage 后，pinned `vector_bridge_cli` identity 在 approved clean VM 中不可恢复 |
| 禁止替代 | rebuilt/provenance-labeled tar、替代 VM、substitute harness PASS、历史 PASS 均不得升格为 Formal L3 |
| 下一步 | 人工确认 package identity 后，处理 `docs/day15/14_d14b_vector_cli_refreeze_request_20260911.md` 的二选一：找回原始 CLI bytes；或 D 主审 / Release Owner 出具 provenance-labeled rebuild refreeze 决定。随后使用新的 evidence root 重跑 `scripts/run_d14b_preflight.py`，再按 runbook 执行 clean VM capture 与 lifecycle |

## D15B

| 字段 | 值 |
| --- | --- |
| 任务 | B 轨检索发布收口 |
| 状态 | `BLOCKED_NOT_COMPLETE`；`input_freeze_status=NOT_FROZEN`；`execution_binding_status=NOT_BOUND`；`B_TRACK_MANIFEST=NOT_FROZEN`；`B_TRACK_COMPLETE=NO` |
| 上游依赖 | D14B formal evidence 与 D9 retrieval eval inputs freeze |
| 技术债 | `RELEASE_BLOCKING` 债务保持 Open；每项须关闭、waiver 或明确 `ACCEPTED_RELEASE_DEBT` |
| 下一步 | E/D 冻结 queryset/gold/thresholds；D14B formal evidence 通过后执行 evaluator；生成正式 metrics、SHA256SUMS 与 manifest |

## D14C

| 字段 | 值 |
| --- | --- |
| 任务 | 真实 Host / AI Assistant E2E |
| 状态 | `D14C_FORMAL_L3=BLOCKED`；`D14C_FORMAL_RESULT=UNVERIFIED`；formal runtime `NOT_STARTED` |
| 当前阻塞 | RC3 证明 Host Chat 可用，但完整 Host Chat LLM package/binary/model/runtime identity 缺失；TD-008/TD-009/production identity 未在同一真实回合采集；G4-G7 未闭合 |
| 禁止替代 | test profile、mock、旧 Hook、纯 IPC、历史 preparation 结果均不得替代 production E2E |
| 下一步 | 先提供并登记 Host Chat LLM package/binary/version/SHA-256，再采集同一真实回合的 chatAsync 注入、Tool 回程、Chat DB identity 与 production SourceReference |

## D15E / D14E

| 字段 | 值 |
| --- | --- |
| 任务 | 最终提交材料与签署 |
| 状态 | `D15E_PHASE0_PREPARATION=READY`；`D15E_FINAL_SUBMISSION_LOCK=WAITING_PREREQ`；`D15E_FINAL_SUBMISSION_LOCK_DECLARED=false`；`D15E_SIGNOFF_STATUS=BLOCKED` |
| 上游依赖 | E15-2 依赖 D14B；E15-3 依赖 D14C；E15-5 受 D14B/D14C/D15A 限制；E15-6 依赖 D14E final signoff |
| 下一步 | 可继续统稿技术文档、用户手册、submission inventory 与 claim-to-evidence mapping；不得执行 final lock、final signoff 或新增 Runtime 结论 |

## 下一步（优先级）

1. 先取得四个最小 P0 输入：D14B package identity、D14B vector CLI identity、D14C Host Chat LLM identity 与 D15A A15-2 performance scope。
2. 将 D15A A15-1 / A15-3 evidence refresh 限定为 historical cross-check；current-main 判定先完成 runtime package rebuild 与 Kylin VM release identity revalidation，再提交 D 主审逐项判定。
3. D14B preflight/clean VM、D14C 同一真实回合采集与 D15B sealed inputs 在对应前置闭合后才可执行。
