# D Track Status (SSOT)

> 依据《D轨当前状态与简化流程交接_20260907》§6.1 建立的统一状态 SSOT。
> 历史任务卡（`24_`/`26_`/`29_`/`30_`/`31_`/`32_`/`33_`/`34_`）保留为
> HISTORICAL / REFERENCE，从本文件生效起不再要求同步维护其"当前状态"。
> As-of: 2026-09-08（D13D Phase 3 formal closure / D13D_FROZEN 登记）。

## D13D

| 字段 | 值 |
| --- | --- |
| 任务 | Versioned Execution Adapter / P0-I3b-completion |
| 状态 | Phase 2 DONE；Phase 3 formal closure DONE；`D13D_FROZEN` |
| PR #160 | MERGED @ 2026-09-07T13:41:54Z |
| `I3B_COMPLETION_MERGE_SHA` | `ba3b50e1bdeea185bca9daee9d1d45958f62a636`（= 当前 main HEAD） |
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
| 状态 | REWORK（`RUNTIME_EXECUTED / FORMAL_PREREQUISITES_NOT_CLOSED`）；HIGH-02 CLOSED |
| PR #165 | OPEN @ `feat/d14d-formal-l3`（head 以 GitHub 平台为准，不在此硬编码） |
| Review | ① 2026-09-07T14:37Z `REQUEST_CHANGES`（BLOCKER-01、HIGH-02）；② 2026-09-07T15:15Z 继续复审 COMMENT：HIGH-02 **ACCEPT / CLOSED**（r4 正式接纳为 Formal start replacement，仲裁记录转 CONFIRMED），BLOCKER-01 **OPEN**（按既定冻结链推进） |
| 已执行 | G0-G6 全 PASS（真实麒麟 VM，pre-formal observation 定位，Reviewer 认可 raw 真实性）；G7 = NOT_RUN / N-A（D-09 裁定）；G8 = NOT_RUN（D-10 裁定） |
| G8 裁定 | **正式 waiver**（D 主审，2026-09-07）：G8 维持 NOT_RUN，按 D-10 边界豁免，作为进入 `L3_READY` 的正式前置闭合 |
| 已闭合前置 | `D13D_FROZEN`；final tested_commit = `ba3b50e1bdeea185bca9daee9d1d45958f62a636` |
| 未完成 | `D14A final package/hash freeze`；PR #165 final review。若最终 package identity 与本次 run 的 `2222c904…` 不一致，现有 G0-G6 仅保留为 pre-formal observation，须基于新冻结身份重跑 Formal L3 |
| Evidence root | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e`（tested_commit `ba3b50e`，package tar SHA `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401`） |
| 边界 | `L3_READY=false`；`release_ready=false`；`production_ready=false` |

## D14A

| 字段 | 值 |
| --- | --- |
| 状态 | `PACKAGE_IMPLEMENTATION_CANDIDATE`（PR #152 APPROVE 范围）；final package / formal hash `NOT_FROZEN` |
| 依赖 | final tested_commit 冻结后重新打包 → 重算 hash → 真实 VM 重测回填（D15A 矩阵 §5.2） |

## 下一步（优先级）

1. D14A final package freeze + hash 回填 + `evidence/index.yaml` 登记（tested_commit 已与本次 run 一致，package identity 预期不变）。
2. 条件分支：若最终 package identity 与 `2222c904…` 变化，须先基于新冻结身份重跑 Formal L3，再进入复审。
3. PR #165 final review → APPROVE → merge → `L3_READY`。
