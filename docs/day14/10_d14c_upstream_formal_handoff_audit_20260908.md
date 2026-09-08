# D14C：上游正式 handoff 消费审计（2026-09-08）

> 性质：读取合入 `origin/main@7782612` 的 D-track SSOT、freeze record、package
> freeze record 和 D14D evidence identity。不是 D14C Runtime evidence，不创建
> evidence root，也不把未关闭的 Host Mapping / route / MemoryContext Gate 升级为通过。

## 审计身份

| 项 | 值 |
|---|---|
| D14C development HEAD | `b53bdd2f718d3dfa164275836bf7f72b8bc17911` |
| 合入的 main | `origin/main@77826122a8aa1eaeed60ec9295a4bb8f979b3fe7` |
| frozen runtime tested commit | `ba3b50e1bdeea185bca9daee9d1d45958f62a636` |
| package | `kylin-memory-a-d14a 0.1.0-d14a` |
| package tar SHA-256 | `2222c904cd2f1ca4e7fec65a1fe76f611760d2c49a63d5839cfb5011dd32b401` |
| package manifest SHA-256 | `76a839335541814bbc7ff53b510ded9877a216b85da87bec6840c7916cd46fc0` |
| D14D evidence root | `evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e` |

`b53bdd2` 是运行 preflight、保存 D14C preparation 工具的 development HEAD；它
不是运行时包的 source commit。D14C formal handoff 必须将 package、D13D 与 D14D
绑定到 `ba3b50e`，同时以干净的 `preflight_runner_commit=b53bdd2` 绑定预检工具。

## 已可消费的正式输入

| 输入 | 状态 | 可消费事实 |
|---|---|---|
| D13D | `D13D_FROZEN` | Phase 3 evidence root、双 Seal、Runner Gate 0-10 PASS，tested commit 为 `ba3b50e`。 |
| D14A | `A_FINAL_PACKAGE_READY=YES` | final package/version、tar/manifest/SHA256SUMS 均已冻结，source commit 为 `ba3b50e`。 |
| D14D | `L3_READY` / DONE | G0-G6 PASS，G8 waiver 已由 D 主审关闭，evidence package 与 package tar SHA 绑定 `ba3b50e`。 |

## D14C Gate 重新判定

| Gate | 当前状态 | 说明 |
|---|---|---|
| G1 final tested commit | `READY_TO_CONSUME_FROZEN_BASELINE` | 可使用 `ba3b50e`；实际 formal handoff 仍须逐项校验 D13D/D14D/package identity。 |
| G2 clean VM + final package | `READY_TO_CONSUME_FROZEN_PACKAGE_VM` | 可消费 D14D clean VM lineage 与 D14A frozen package；D14C 自身 runtime identity 尚未采集。 |
| G3 #151 assets | `DEVELOPMENT_READY_FORMAL_PENDING` | 仍须在 D14C formal handoff 中保持 compatibility/identity 可复核。 |
| G4 resolver / Host DB binding | `BLOCKED_PENDING_D15C_HANDOFF` | PR #167 仍 `CONFLICTING`，且 handoff 未经 D review。 |
| G5 trusted host identity | `BLOCKED_PENDING_D_APPROVAL` | #167 仅有评估材料；无 D 主审批准的 final identity manifest。 |
| G6 production routes | `BLOCKED_PENDING_D_ACTIVATION` | 四条 route 尚无 `ACTIVE` formal handoff。 |
| G7 MemoryContext | `BLOCKED_PENDING_CDE_FREEZE` | 仍无 hit/no-match/failure 的 frozen mapping。 |
| G8 evidence root | `NOT_CREATED_BY_DESIGN` | G4-G7 未关闭，禁止创建。 |

## Preflight 绑定规则

`d14c-formal-handoff/v1` 现在明确区分两种身份：

```text
formal_tested_commit = D13D/D14D/D14A frozen runtime source commit
preflight_runner_commit = 执行预检的干净仓库 HEAD
release_package.source_commit = formal_tested_commit
d13d.tested_commit = formal_tested_commit
d14d.tested_commit = formal_tested_commit
d14d.package_tar_sha256 = release_package.sha256
```

任何一项不一致均拒绝 preflight。该规则允许 docs/evidence/preflight-tool 变更不
重写已经冻结的 runtime package 身份，但不允许它们冒充 Runtime PASS。

## 结论

```text
D14C_PREPARATION = ADVANCED / IN_PROGRESS
D14C_G1_G2 = READY_TO_CONSUME
D14C_G4_G7 = BLOCKED
D14C_FORMAL_L3 = BLOCKED
D14C_FORMAL_RESULT = UNVERIFIED
```

下一步唯一的 D14C Gate 动作是消费经 D 主审完成的 #167 trusted identity / Host
Mapping handoff、四条 production route `ACTIVE` handoff 与 MemoryContext freeze；
三者未到位前不得运行 formal preflight 或创建 formal evidence root。
