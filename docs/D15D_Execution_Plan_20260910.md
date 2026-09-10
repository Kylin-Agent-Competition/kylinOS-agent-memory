# D15D 执行计划与任务流程

> 日期：2026-09-10
> 状态：`NEW_RELEASE_IDENTITY_BUILT_AND_VM_VERIFIED / PENDING_E_SIGN`
> 前置文档：`docs/D15D_TaskCard_20260906.md`、`docs/D15D_Asset_Inventory_Gap_20260906.md`、`docs/D15D_PostLock_Consistency_Runbook_20260906.md`
> 本文件基于 2026-09-10 实际前置闭合状态制定，取代任务卡 §5 中尚未回填的占位值。

## 当前态势

| 维度 | 状态 |
|---|---|
| release_commit | `4a6323f`（old `ba3b50e` lock 仅保留为 historical invalidated record） |
| 新发布包 | `kylin-memory-a-d14a 0.1.0-d14a`，tar SHA `974c2584…`，manifest SHA `4b42d928…`，SHA256SUMS SHA `9d1ac01f…` |
| D14D 证据 | `L3_READY`，G0-G6 PASS，G8 waiver，evidence root 已入 PR #165 |
| main 当前位置 | `4a6323f`（2026-09-10 PR #156 合入）；`cdcce34` 与 `306c15e` 是历史快照 |
| D15D 自身进展 | PR #175 Round 6 返工：新 `4a6323f` release/package/runtime evidence 链已建立；G-D7 仍等待 Reviewer E 签署 |

### Active release identity flow

旧的 `ba3b50e` / `306c15e` 选择问题已关闭，只作为历史记录保留，不再是可执行路径。
当前 active release commit 已选定为 `R = 4a6323f`，并按下表重建与验证：

1. 在干净的 detached worktree checkout `R`，验证 C1：`HEAD == R` 且完整 worktree 为空。
2. 按当前 Runbook C2 执行 `git diff --name-only R..main -- packaging/ memory-service/
   cpp-bridge/ migrations/ config/ docs/day14/00_d14a_release_package_contract.md`；
   非空且未获批准登记即停。
3. 在 `R` 干净树上重建包，生成新的 tar / manifest / SHA256SUMS identity，禁止复用 `2222c904`。
4. 重跑 C3-C12 完整一致性链，并完成所需的麒麟 VM 证据后再请求 G-D7。
5. 本轮执行结果与 run-id 登记在 `evidence/d15d-lock/20260910T205300Z/`。

---

## Phase 0：基线刷新与任务卡升级（半天）

**目标**：把本地草稿从"前置未解"状态升级为"可执行锁定"状态。

| 步骤 | 内容 | 产出 |
|---|---|---|
| 0.1 | 从干净 `main@4a6323f` 或其后续状态选定新的 release commit `R`，记录 40 位 SHA | selected release commit |
| 0.2 | 在 detached worktree 验证 C1，并按含 `config/` 的当前 C2 scope 复核 `R..main` | C1/C2 结论 |
| 0.3 | 重跑当前 D15A/D14A 守卫全套确认回归基线 | CI-equivalent PASS log |
| 0.4 | 更新 `docs/D15D_TaskCard_20260906.md`：release_commit 回填为新的 `R`；更新 §5 输入状态表 | 任务卡 v3 |
| 0.5 | 用 `kylin-memory-dev` skill 走代码/文档变更流程 | — |

**Gate**：Phase 0 完成的标志 = 选定 40 位新 release commit `R`，C1/C2 结论明确，
且任务卡状态不宣称 READY/LOCKED。

---

## Phase 1：包一致性与基线核验（G-D1 / G-D2 / G-D3，半天）

**目标**：证明已冻结包与 main@release_commit 逐字节一致。

| 步骤 | 对应 Runbook | 内容 |
|---|---|---|
| 1.1 | C1 | 确认 release_commit 是 main 祖先，工作树干净 |
| 1.2 | C2 | 锁定后 main 无发布路径漂移 |
| 1.3 | C8 | 在解包目录 `sha256sum -c SHA256SUMS`；manifest.source_commit == release_commit；package_version == `0.1.0-d14a` |
| 1.4 | C3-C6 | `assert_same` 四项：install/uninstall/verify 脚本 + unit，包内 vs `git show release_commit:path` |
| 1.5 | C3(CI) | 在 main checkout 重跑 `d14a-packaging-provenance` 等价测试（pytest packaging/release/test_d14a_*.py） |

**Gate**：全部 PASS → 进入 Phase 2。任一 MISMATCH → 从 release_commit 重建包，重跑全部，不沿用旧包。

**产出**：`consistency_*.log`（每项命令 + stdout + exit code）。

---

## Phase 2：D14D 证据消费（G-D4，半天）

**目标**：确认 D14D 正式证据可被 D15D 消费且与 release_commit 绑定。

| 步骤 | 对应 Runbook | 内容 |
|---|---|---|
| 2.1 | C11 | D14D evidence root（`evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e`）checksums 23/23 OK 只记录为 `HISTORICAL_PASS_AT_ba3b50e`；它不是新 release commit `R` 的最终 C11 证明 |
| 2.2 | C10 | 从 D14D G0 提取 SDK/runtime/model 身份（SDK `1.2.0.0-0k0.4` SHA `028e7099…`；runtime `1.2.0.4-0k0.1`；model `1.0.0.1-0k0.9`），确认无 `HANDOFF_REQUIRED` 遗留 |
| 2.3 | — | 确认 G7 = NOT_RUN / N-A（D-09），G8 = NOT_RUN + 正式 waiver（D-10），与版本清单口径一致 |
| 2.4 | — | 确认 `L3_READY=true`、`release_ready=false`、`production_ready=false` 边界 |

**Gate**：C10 身份闭合且新 release identity 的 C11 由 `evidence/d15d-lock/20260910T205300Z/`
闭合后进入 Phase 3。旧 D14D root 仅作参考输入；若 runtime/model 身份仍有
`HANDOFF_REQUIRED` 遗留，D15D 结论最高 PARTIAL。

---

## Phase 3：版本清单建立（G-D5，1-2 小时）

**目标**：产出 `D15D_VERSION_MANIFEST.json`，三方一致。

| 步骤 | 对应 Runbook | 内容 |
|---|---|---|
| 3.1 | C9 | 新建 `docs/day15/D15D_VERSION_MANIFEST.json`，包含：release_commit、package tar/manifest/SHA256SUMS SHA、脚本/unit SHA、VERSION_MAP 版本、D14D evidence 引用 |
| 3.2 | C9 | 逐项断言 manifest ↔ 包 ↔ D14D evidence 三方相等 |
| 3.3 | — | 用 `kylin-commit-standard` 扫描后 commit |

**Gate**：C9 PASS → 进入 Phase 4。任何不一致字段 → 修正清单后重新断言。

---

## Phase 4：提交包清单（G-D6，1 小时）

**目标**：提交包文件集与 main 锁定清单一一对应。

| 步骤 | 对应 Runbook | 内容 |
|---|---|---|
| 4.1 | C12 | 定义固定内容清单：发布包 tar + 解包目录 + 版本清单 + 契约 + 证据索引 |
| 4.2 | C12 | 与 main 锁定清单 `comm -3` 比对：无多余、无缺失 |
| 4.3 | — | 全量 checksums 校验 |

**Gate**：C12 PASS → 进入 Phase 5。缺件 → 补全后重跑。

---

## Phase 5：迁入仓库 + PR + E 签署（G-D7，1-2 天含等待）

**目标**：D15D 材料入库、PR 发出、E 签署。

| 步骤 | 内容 |
|---|---|
| 5.1 | 从当前 main 新建 `docs/day15-d15d-lock` 分支 |
| 5.2 | 迁入任务卡、版本清单、consistency logs、evidence root 到 `docs/day15/` + `evidence/d15d-lock/<run-id>/` |
| 5.3 | 修 GAP-03：`packaging/systemd/README.md` 改为"历史/只读，正式入口 = `packaging/release/`"（只改 README，不改脚本） |
| 5.4 | 开 PR，body 同步 exact HEAD + Gate 矩阵；request Reviewer E |
| 5.5 | E APPROVE → 任务卡升 `SIGNED_PREPARED`；台账 H→I→J 推进 |
| 5.6 | merge → `LOCKED` |

**Gate**：E APPROVE = G-D7 通过 = D15D 完成。D 轨不自签、不代签。

---

## 任务流程图

```
Phase 0 (基线刷新)
  ├─ 0.1 release_commit 判定
  ├─ 0.2 守卫回归
  └─ 0.3 任务卡升级
        ↓
Phase 1 (包一致性)
  ├─ C1: 祖先关系 + 干净树
  ├─ C2: 发布路径无漂移
  ├─ C3-C6: 四项 assert_same
  ├─ C8: 包完整性
  └─ CI 等价测试
        ↓
Phase 2 (D14D 消费)
  ├─ C10: runtime/model 身份闭合
  ├─ C11: evidence root 绑定
  └─ G7/G8 waiver 口径一致
        ↓
Phase 3 (版本清单)
  └─ C9: 三方一致断言
        ↓
Phase 4 (提交包)
  └─ C12: 一一对应
        ↓
Phase 5 (PR + E 签署)
  ├─ 迁入 docs/day15/
  ├─ 修 GAP-03
  ├─ 开 PR → E review
  └─ E APPROVE → LOCKED
```

---

## 失败处置

任一 Gate 失败 → **停**，保留原始输出，不开新结论。按 Runbook §4 对应处置：

- C1/C2 失败：main 触及锁定路径 → 重建 release_commit/包
- C3-C8 失败：包与 main 不一致 → 重建包
- C9/C10 失败：清单或身份矛盾 → 修正清单
- C11/C12 失败：证据/提交包不完整 → 补全
- C13 未通过：最高 `PENDING_E_SIGN / PARTIAL`

## Skill 使用矩阵

| Phase | Skill | 用途 |
|---|---|---|
| Phase 0 / 3 | `kylin-memory-dev` | 文档/代码变更流程 |
| Phase 5 | `kylin-memory-review` | PR review |
| 全阶段 commit 前 | `kylin-commit-standard` | 敏感信息扫描 |
| C7（如需 VM 复核） | `kylin-vm-test` | 麒麟 VM 验证 |
