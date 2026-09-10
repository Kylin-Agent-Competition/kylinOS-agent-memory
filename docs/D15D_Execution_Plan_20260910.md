# D15D 执行计划与任务流程

> 日期：2026-09-10
> 状态：`C2_INVALIDATED_PENDING_NEW_RELEASE_IDENTITY / PENDING_E_SIGN`（2026-09-10 Reviewer E 第 4 轮检出 main 前移）
> 前置文档：`docs/D15D_TaskCard_20260906.md`、`docs/D15D_Asset_Inventory_Gap_20260906.md`、`docs/D15D_PostLock_Consistency_Runbook_20260906.md`
> 本文件基于 2026-09-10 实际前置闭合状态制定，取代任务卡 §5 中尚未回填的占位值。

## 当前态势

| 维度 | 状态 |
|---|---|
| release_commit | `ba3b50e` 的既有锁定已因 current main 运行时漂移失效；新 release commit 待重建 |
| 已冻结包 | `kylin-memory-a-d14a 0.1.0-d14a`，tar SHA `2222c904…` |
| D14D 证据 | `L3_READY`，G0-G6 PASS，G8 waiver，evidence root 已入 PR #165 |
| main 当前位置 | `4a6323f`（2026-09-10 PR #156 合入）；`cdcce34` 与 `306c15e` 是历史快照 |
| D15D 自身进展 | PR #175 第 4 轮返工：C2 `FAIL_INVALIDATED`，选择触发新 release/package identity；G-D7 不可签署 |

### 核心决策点：release_commit 选 `ba3b50e` 还是 `306c15e`

Runbook C2 的判定逻辑：

- 若 `ba3b50e..306c15e` 仍为 `DOCS_EVIDENCE_ONLY`（不触碰 `packaging/` `memory-service/` `cpp-bridge/` `migrations/` `config/`），则 **release_commit = `ba3b50e`**，复用已冻结包 `2222c904`，免重打包。
- 若触发了运行时/打包路径，则必须选择新的 release commit 并重建包、重跑全部一致性检查。当前
  `ba3b50e..4a6323f` 已命中 `memory-service/`，结论为 `TRIGGER_NEW_RELEASE_PACKAGE_IDENTITY`。

#170 时（`35cc43d`）确认过为 DOCS_EVIDENCE_ONLY。之后 #171/#172/#174 合入，需重新验证。

---

## Phase 0：基线刷新与任务卡升级（半天）

**目标**：把本地草稿从"前置未解"状态升级为"可执行锁定"状态。

| 步骤 | 内容 | 产出 |
|---|---|---|
| 0.1 | 在 `main` checkout（`306c15e`）跑 `git diff --name-only ba3b50e..HEAD -- packaging/ memory-service/ cpp-bridge/ migrations/ config/`，判定 DOCS_EVIDENCE_ONLY 与否 | 分类结论 |
| 0.2 | 重跑 D15A/D14A 守卫（37 tests）确认回归基线 | CI-equivalent PASS log |
| 0.3 | 更新 `docs/D15D_TaskCard_20260906.md`：release_commit 从 PENDING 回填为 `ba3b50e` 或 `306c15e`；更新 §5 输入状态表 | 任务卡 v2 |
| 0.4 | 用 `kylin-memory-dev` skill 走代码/文档变更流程 | — |

**Gate**：Phase 0 完成的标志 = 任务卡状态仍为 `DRAFT / PREPARED`（不是 READY/LOCKED），且 release_commit 为 40 位实值。

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
| 2.1 | C11 | 确认 D14D evidence root（`evidence/l3-kylin-vm/d14d_20260907T141000Z_ba3b50e`）存在且 checksums 23/23 OK |
| 2.2 | C10 | 从 D14D G0 提取 SDK/runtime/model 身份（SDK `1.2.0.0-0k0.4` SHA `028e7099…`；runtime `1.2.0.4-0k0.1`；model `1.0.0.1-0k0.9`），确认无 `HANDOFF_REQUIRED` 遗留 |
| 2.3 | — | 确认 G7 = NOT_RUN / N-A（D-09），G8 = NOT_RUN + 正式 waiver（D-10），与版本清单口径一致 |
| 2.4 | — | 确认 `L3_READY=true`、`release_ready=false`、`production_ready=false` 边界 |

**Gate**：C10 + C11 PASS → 进入 Phase 3。若 runtime/model 身份仍有 HANDOFF_REQUIRED 遗留，D15D 结论最高 PARTIAL。

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
