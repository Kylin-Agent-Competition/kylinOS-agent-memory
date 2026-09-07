# D Track Status (SSOT)

> 依据《D轨当前状态与简化流程交接_20260907》§6.1 建立的统一状态 SSOT。
> 历史任务卡（`24_`/`26_`/`29_`/`30_`/`31_`/`32_`/`33_`/`34_`）保留为
> HISTORICAL / REFERENCE，从本文件生效起不再要求同步维护其"当前状态"。
> As-of: 2026-09-07（PR #165 review REQUEST_CHANGES 之后）。

## D13D

| 字段 | 值 |
| --- | --- |
| 任务 | Versioned Execution Adapter / P0-I3b-completion |
| 状态 | Phase 2 DONE；Phase 3（formal closure）IN_PROGRESS |
| PR #160 | MERGED @ 2026-09-07T13:41:54Z |
| `I3B_COMPLETION_MERGE_SHA` | `ba3b50e1bdeea185bca9daee9d1d45958f62a636`（= 当前 main HEAD） |
| 已完成 | P2-A `CONTRACT_MERGED / ADAPTER_CONSUMER_CLOSED`；P2-B dual-channel 5/5 candidate closure（Reviewer E final APPROVE，2026-09-07T13:09Z）；P2-C COMPLETE |
| 未完成（Phase 3） | 正式 VM 17 raw（17 样本 × Preference/Conflict/Safety/Forget per-sample raw）；Final Manifest（FROZEN_BY_D13D）+ SHA-256；D13E Review Seal；attestation + Execution Seal；Runner Gate 0-10；`D13D_FROZEN`；TD-061 关闭 |
| tested_commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636`（D 主审裁定，2026-09-07：选定为 Phase 3 formal execution tested_commit；与 D14D 现有 G0-G6 run 身份一致。final tested commit 身份随 `D13D_FROZEN` 生效） |
| Trust Root / Seal 材料边界 | `D13E_TRUST_ROOTS_V1.json` + 两个 public PEM、Ed25519 私钥由 D13E/D Reviewer 侧持有；工作区不代持、不伪造 |
| Reviewer | lovezy0730-create（E） |

## D14D

| 字段 | 值 |
| --- | --- |
| 任务 | L3 干净快照发布 Gate、安装生命周期、回退与证据闭环 |
| 状态 | REWORK（`RUNTIME_EXECUTED / FORMAL_PREREQUISITES_NOT_CLOSED`）；HIGH-02 CLOSED |
| PR #165 | OPEN @ `feat/d14d-formal-l3`（head 以 GitHub 平台为准，不在此硬编码） |
| Review | ① 2026-09-07T14:37Z `REQUEST_CHANGES`（BLOCKER-01、HIGH-02）；② 2026-09-07T15:15Z 继续复审 COMMENT：HIGH-02 **ACCEPT / CLOSED**（r4 正式接纳为 Formal start replacement，仲裁记录转 CONFIRMED），BLOCKER-01 **OPEN**（按既定冻结链推进） |
| 已执行 | G0-G6 全 PASS（真实麒麟 VM，pre-formal observation 定位，Reviewer 认可 raw 真实性）；G7 = NOT_RUN / N-A（D-09 裁定）；G8 = NOT_RUN（D-10 裁定） |
| G8 裁定 | **正式 waiver**（D 主审，2026-09-07）：G8 维持 NOT_RUN，按 D-10 边界豁免，作为进入 `L3_READY` 的正式前置闭合 |
| 未完成 | BLOCKER-01 冻结链：`D13D Phase3 → D13D_FROZEN → final tested_commit 生效 → D14A final package/hash freeze`；若最终 tested_commit / package identity 与本次 run 的 `ba3b50e / 2222c904…` 任一不一致，现有 G0-G6 仅保留为 pre-formal observation，须基于新冻结身份重跑 Formal L3 |
| Evidence root | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e`（tested_commit `ba3b50e`，package tar SHA `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401`） |
| 边界 | `L3_READY=false`；`release_ready=false`；`production_ready=false` |

## D14A

| 字段 | 值 |
| --- | --- |
| 状态 | `PACKAGE_IMPLEMENTATION_CANDIDATE`（PR #152 APPROVE 范围）；final package / formal hash `NOT_FROZEN` |
| 依赖 | final tested_commit 冻结后重新打包 → 重算 hash → 真实 VM 重测回填（D15A 矩阵 §5.2） |

## 下一步（优先级）

1. D13D Phase 3 formal closure（tested_commit 已选定 `ba3b50e` → VM 17 raw → Final Manifest → Seal → Runner 0-10 → `D13D_FROZEN`）。
2. D14A final package freeze + hash 回填 + `evidence/index.yaml` 登记（tested_commit 已与本次 run 一致，package identity 预期不变）。
3. 条件分支：若最终 tested_commit / package identity 与 `ba3b50e / 2222c904…` 任一变化，须先基于新冻结身份重跑 Formal L3，再进入复审。
4. PR #165 新 exact HEAD 复审 → APPROVE → merge → `L3_READY`。
