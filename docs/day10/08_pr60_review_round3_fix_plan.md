# PR60 第三轮 Review 修复方案（收口 1 HIGH 契约阻断 + 4 LOW）

- **编制日期**：2026-08-27
- **编制人**：opencode（D 轨开发 Agent）｜Reviewer：E（谢嘉然）
- **基线**：PR #60 HEAD `9bd5192`（分支 `feat/d5d-pr0-contract-adr`，基 main @ `d12df5a`）
- **输入**：PR #60 第三轮 Review（`lovezy0730-create`，2026-08-27 03:21，结论 **REWORK**：BLOCKER 0 / HIGH 1 / MEDIUM 0 / LOW 若干）
- **目的**：仅关闭 1 个真正会让 Implementer 做出不同实现的契约歧义（resolver UPDATE/refinalize 语义），并按 LOW 顺手项同步 Task List / ADR 措辞 / PR Body。
- **结论判定（Reviewer）**：本轮未标记实现/验证级问题；重构语义问题留在 PR #60，实现正确性问题进入 PR-2，Runtime/L2 验证进入 PR-3。

---

## 一、HIGH-1 — UPDATE/refinalize 的 resolver 行为矛盾

**文件**：`docs/adr/010-turn-finalized-method.md` §落库语义 / §Upsert 字段矩阵

**矛盾**：ADR-010 同时存在两种口径 ——
- 一处写「UPDATE/refinalize 场景 + resolver 失败 → 继续使用既有 `original_user_text`，不报错」；
- 字段矩阵又写「original_user_text 保持首次值 / refinalize 不重 resolve」。

两口径无法同时成立：若 refinalize **不重新调用 resolver**，则不存在「UPDATE + resolver 失败」分支；若仍调用 resolver，则字段矩阵「保持首次值」与之矛盾。Implementer 因此仍需自行决定「UPDATE 到底调不调用 resolver」。

**修复（冻结为）**：

```text
INSERT（无既有 turn）：
  调用 resolver。
  resolver 成功 → 写入 original_user_text。
  resolver 失败 → INTERNAL_ERROR（safe）。
  禁止空串/伪造正文替代。

UPDATE/refinalize（已有 turn）：
  不调用 resolver。
  直接复用数据库中已有 original_user_text。
  不存在「UPDATE resolver 失败」分支。
```

此口径与字段矩阵「保持首次值 / refinalize 不重 resolve」完全一致，也最符合「重投/refinalize 不改变首次正文」的既定语义。

参照 Reviewer 建议原句：

> INSERT：调用 resolver；resolver 成功 → 写入 original_user_text；resolver 失败 → INTERNAL_ERROR；禁止空串/伪造正文替代。
> UPDATE/refinalize：不调用 resolver；直接复用数据库中已有 original_user_text；不存在 UPDATE resolver failure 分支。

---

## 二、LOW 顺手项

| # | 项 | 处理 |
|---|---|---|
| 1 | ADR-010「开发影响」泛写 `gateway/registry.py 注册方法` | 改为「**提供 `turn.finalized` 显式注册 seam**；production default registry 不注册；test profile 显式注册 + 注入 in-memory resolver」 |
| 2 | Task List PR-3 L2-2 未注明 test/profile | L2-2 注明 **test/validation profile + explicit registration + in-memory resolver**；**production profile** 验证 `turn.finalized → UNSUPPORTED_METHOD` |
| 3 | 并发 `IntegrityError` 幂等回查未列入 L1 | Task List 测试要求补「**并发 IntegrityError 幂等回查路径（同样执行 fingerprint compare + unwrap）**」（属 PR-2 实现审查 / L1 验收） |
| 4 | PR Body 首句「仅交付两份 ADR 文档」不准确 | 更新为「纯文档契约 PR（ADR + 设计/Task/Review 辅助文档，无代码改动）」 |

---

## 三、文件修改清单

- `docs/adr/010-turn-finalized-method.md`（HIGH-1 + LOW-1）
- `docs/day10/05_d5d_task_list_20260826.md`（LOW-2 + LOW-3）
- 本方案文档（LOW-4 不在仓库内，随 PR Body 更新）

---

## 四、后续

收口后（resolver 语义收口且无新架构回归），下一轮应进入 **PASS / PASS_WITH_DEBT**，不再扩大 ADR 冻结范围；按 Reviewer 分层：架构语义留 PR #60、实现正确性进 PR-2、Runtime/L2 验证进 PR-3。
