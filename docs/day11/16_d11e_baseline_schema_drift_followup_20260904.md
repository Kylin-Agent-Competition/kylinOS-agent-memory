# D11E 基线与 schema-drift 随动记录（2026-09-04）

## 背景

- `origin/main` 已由 `b70827c` 前进至 **`f263d5b` = E 轨 schema-drift 修复 PR #137（已合入）**：
  - TD-013：`NonEmptyStr` 拒绝空串与纯空白（不 strip 原值，含有效字符原样保留）；
  - TD-014/015/017：`Conflict.involved_knowledge_ids/resolved_by`、`Knowledge.content_ref/superseded_by_id`、`Preference.previous_version_id`、`ForgetPlan.rollback_plan_id` 由 `Optional[str]` 收严为 `Optional[NonEmptyStr]`；
  - 新增 `docs/architecture/KMA_UNIFIED_DATA_FORMAT_FREEZE_V1.md` 与 TD/lifecycle drift handoff 文档。

## 本批动作

- D11E PR #132 分支 **merge `origin/main@f263d5b`**（合并提交 `e9db0b8`，无冲突）。
- 主机复跑 E 轨 L0/L1：**571 passed**（`docs/day11/17_d11e_e_l0l1_regression_f263d5b_20260904.log`；#137 为 `test_domain_models_d4e.py` 新增用例，故 535→571）。
- 文档/矩阵/案例路径（04/06/07）基线引用更新为 `f263d5b`，L0/L1 口径改为 571（历史 535 见 05 log）。
- 历史 VM 证据（09–15，采集于 `b70827c`/`f4d9a00`）保持原基线引用不变，作为 #137 合入前快照。

## 影响与结论

- E 业务语义无回归（571 passed）；D11E 验收基线现与 `main@f263d5b` 对齐，不再落后 canonical/冻结口径。
- VM 侧同 Commit 复跑（571/广回归）待下次开机或 A/C/D 回填时执行；此前 VM 侧结论按原证据基线标注。

## 仍未合入 main 的跨轨 drift（合入后需复核）

| 来源 | 分支/PR | 内容 |
|---|---|---|
| A | `fix/a-track-schema-drift-captured-at`（`62376bc`） | DRIFT-001 `captured_at` Canonical 真源 + 反向门禁 |
| C | `fix/c-d12-schema-drift-canonical-adapter`（`30a2c31`） | C 侧字段对齐 KMA canonical v1 |
| D | `feat/d10d-build` PR #139（`2983d14`） | embedding server 线程竞态修复（D3，无字段/契约变更） |
| D | `fix/d12d-post-merge-techdebt` | D12D 合并后技术债 L2 证据 |

## 边界

- 本批为文档/基线随动 + 主机复跑；未修改生产代码、冻结契约或其他轨道交付物。


## 2026-09-04 随动更新（A/C/D/B drift 合入后）

- `origin/main` 前进至 `cc4acf6`，已合入：A DRIFT-001 captured_at（#135）、B D12B 评测枚举与 Canonical 同源 + 反向守卫（#138）、C 对齐 KMA canonical v1（#140）、D embedding accept-stop/thread-start 生命周期竞态修复（#141）、D12D 合并后技术债 L2（#136）。
- D11E 分支已 merge `cc4acf6`（合并提交 `ef49c85`，无冲突）。
- 主机复跑 E 轨 L0/L1：仍 **571 passed**（`docs/day11/21_d11e_e_l0l1_regression_cc4acf6_20260904.log`），A/C/D/B 漂移修复未引入 E 业务回归。
- VM 侧 `cc4acf6` 同 Commit 复跑与 C 主演示/A 真实 SDK 完整 E2E 待后续执行（当前仍 `UNVERIFIED`）。
