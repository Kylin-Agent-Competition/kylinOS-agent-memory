# PR #68 审查问题清单

> 来源：[PR #68](https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/68) 的 GitHub Pull Request Review（review id `5059828984`，作者 `baconzha`，`CHANGES_REQUESTED`）。
> 导出时间：2026-08-31；head commit：`24ae374`。
> 处置状态：**2026-08-31 已全部修复并核验**（V1/V2/V3 三项有效问题已处理，6 条误报批注不成立），供回填 Closing Comment / 重新请求 Review 使用。

---

## 一、结论

Reviewer 原结论：**REWORK**（总体评审 + 9 条行级批注，其中 4 条标为 BLOCKER / 1 条 HIGH / 2 条 HIGH / 2 条风格类）。

**核验后结论**：9 条批注中 4 条 BLOCKER（Symbol 缺失类）与 2 条 HIGH（TD-028 "未登记"、fixture 类）为**误报/不成立**——相关 API 符号全部存在，3 个新测试在本地真实通过。真正成立的问题为 **3 条**（V1 行级 VT 控制字符 / V2 TD-028 登记状态 / V3 场景 2 缺缓存断言），**全部已修复**（见下）。

---

## 二、有效问题（必须处理）

| # | 位置 | 严重度 | 类型 | 问题描述 | 修复建议 |
|---|------|--------|------|----------|----------|
| V1 | `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md:65`（TD-IPC-003 行） | **High** | 文档/可追溯性 | 证据列中的 `vfy_uds.py` 与 `vfy.slow` 首字符被存为 ASCII VT 控制字符 `\x0B`（各 1 个，位于 col 160 / col 181），Markdown 渲染不可见，grep 无法检索命中，破坏追溯性（已实证确认存在 2 处 `\x0B`） | 删除 `\x0B`，改为可见文本 `vfy_uds.py` / `vfy.slow`，并重跑敏感信息/格式校验 |
| V2 | `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md:96`（TD-028 条目） | **Medium** | TD 登记一致性 | 本 PR 标题与描述声明"TD-028 关闭"，但登记表 TD-028 条目状态仍为 `Open`（本次 diff 仅更新了 TD-IPC-002/003，未将 TD-028 翻转为 `Resolved`）。注意：该条目**已存在**（PR #65 登记，非 Reviewer 所称"未登记"） | 将 TD-028 状态改为 `Resolved`，验收列可引用本 PR 新增的 `tests/test_td028_integrity_race.py` |
| V3 | `memory-service/tests/test_td028_integrity_race.py:133-138`（场景 2 结尾） | **Low** | 断言缺口 | 注释声明"缓存 1 行（首次响应保留）"但未对 `cache_n` 断言；安全拒绝语义要求冲突时不得半写缓存，建议补充缓存行数 + fingerprint 保持断言 | ~~补 `assert cache_n == 1`（及如需，校验缓存 fingerprint 仍为 fp-A）~~ → **已修复（2026-08-31，实测语义校正）**：场景 2 的 fp-A 缓存由 `business_fn` 在同一事务内写入，`IdempotencyConflictError` 上抛后 UoW 整体 rollback（`uow.py:51-52`），缓存随事务回滚 → **`cache_n == 0`（冲突请求不残留任何半写缓存）**。按实际事务语义补 `assert cache_n == 0` 并注释说明，较缓存保留为更强的无副作用保证；场景 1（fingerprint 一致）仍是 `cache_n == 1`。3 passed 复核通过 |

---

## 三、无效/误报批注（Reviewer 批注与代码不符，无需修复）

| 原批注 | Reviewer 声称 | 实证核验结果 |
|--------|----------------|--------------|
| C1（BLOCKER） | `uow.execute_idempotent` 无 `request_fingerprint` 形参，运行时 TypeError | **不成立**：`db/uow.py:71-78` 与 `db/repositories.py:539-546` 均含 `request_fingerprint` 形参 |
| C2（BLOCKER） | `db/repositories.py` 不存在 `_wrap_response` | **不成立**：`db/repositories.py:509` 已定义 |
| C3（BLOCKER） | `insert_turn` 无 `host_turn_id` 形参；schema 无该列与 `idx_turns_host_turn_id` 索引 | **不成立**：`repositories.py:134-145` 含 `host_turn_id`；`schema.py:57` 有列、`schema.py:113-119` 有部分唯一索引（基础 commit `4926345` 亦已含） |
| C4（BLOCKER） | `IdempotencyConflictError` 类不存在，fingerprint 冲突路径未实现 | **不成立**：`repositories.py:42` 已定义并通过冲突场景测试 |
| C5（🟡/严重度标注 HIGH） | fixture `insert_turn` 同样 TypeError | **不成立**：同上，测试真实通过 |
| C9（HIGH） | "TD-028 未在登记表登记即关闭，全文最高编号 TD-023" | **不成立**：TD-028 条目存在于 `TECHNICAL_DEBT_REGISTER.md:96`（PR #65 登记）；但状态未同步为 Resolved（见 V2） |

## 四、已在本地实证通过的测试

- `memory-service/tests/test_td028_integrity_race.py` → **3 passed**（Python 3.13.3 + SQLAlchemy 2.0.52 + pytest 9.0.3，真实 SQLite 约束路径）：
  - `test_td028_race_fingerprint_match_returns_first`
  - `test_td028_race_fingerprint_conflict_rejected`
  - `test_td028_race_no_cache_reraises`

## 五、建议处理顺序

1. ~~修 V1（VT 字符，改 1 行）~~ ✅ 已修复：`\x0bfy`→`vfy`（col 222/247），全文件无 `\x0b` 残留。
2. ~~修 V2（TD-028 登记状态翻转 Resolved，改 1 行）~~ ✅ 已修复：TD-028 状态 `Open→Resolved`，验收注明 `tests/test_td028_integrity_race.py` 3 passed，关联 PR #68。
3. ~~修 V3（补场景 2 的 cache_n 断言，测试文件小幅增强）~~ ✅ 已修复：`assert cache_n == 0`（实测事务 rollback 语义），`pytest test_td028_integrity_race.py` → 3 passed。
4. ~~回填 Review 处置表：逐条列出 C1-C9 的"已修复/异议"结论~~ ✅ 已回填至本文件 §三/§四 与按有效/无效分类：
   - 有效 V1/V2/V3 全部修复（见 §二）；
   - 无效/误报 C1~C5、C9 部分（Symbol 均存在、测试真实通过）已逐一列出证据位置（见 §三）。
   - 另按 Reviewer 顺带建议，TD-IPC-003 登记证据已明确到具体文件 `evidence/l2-kylin-vm/d4d_vm_verify_20260821/verify_run.log`（登记表原含目录级路径，现已含文件名）。
   修复后命令复核：`py_compile` 通过 / `ruff check --select F,E9` All checks passed / `test_td028_integrity_race.py` 3 passed / 敏感信息扫描无命中。供提交复审 Reply 与重新请求 Approval。