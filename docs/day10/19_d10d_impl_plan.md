# D10D 实现 Plan 摘要（Phase 1 / Plan 交付物）

- **编制**：opencode（D 轨开发 Agent）
- **日期**：2026-09-01
- **状态**：Plan（**D 已决策（D1~D6 全部采用推荐方案），待 Reviewer E 签署**后进入 Phase 2 / Build）
- **基线**：初始 Plan 基线 main @ `ffd20b9`；当前已同步 main @ `577c14c`（behind=0）
- **对照**：契约 `docs/day10/16_d10d_forget_contract_plan_v0.3.md`（§〇~§十二）；ADR-015/019 草案 `docs/day10/17_d10d_adr015_019_draft.md`；任务卡 `docs/day10/18_d10d_impl_task_card.md`
- **产出**：本文档 + 17_（ADR 草案）+ 18_（任务卡）

---

## 一、迁移链真实确认（契约 §四.3 MEDIUM-02 处置，实跑记录）

```
$ alembic -c migrations/alembic.ini heads
20260901_d10b_vector_ledger (head)

$ alembic -c migrations/alembic.ini history
20260831_add_source_events -> 20260901_d10b_vector_ledger (head)
20260831_preference_versions -> 20260831_add_source_events
20260826_add_trace_id -> 20260831_preference_versions
001_initial_schema -> 20260826_add_trace_id
<base> -> 001_initial_schema
```

- 真实链：`001_initial_schema → 20260826_add_trace_id → 20260831_preference_versions → 20260831_add_source_events → 20260901_d10b_vector_ledger (head)`。
- **结论**：PR #98（D6-D `20260831_add_source_events`）已并入 main 链（合并提交 `79411f1`）；契约 v0.3 写入时「未合并」的判断**已过时**，按 MEDIUM-02 规则以真实 head 为 down_revision。
- **新迁移**：`migrations/versions/20260901_add_forget_plan.py`；`revision = "20260901_add_forget_plan"`、`down_revision = "20260901_d10b_vector_ledger"`；追加后链保持**单 head**（`... → 20260901_d10b_vector_ledger → 20260901_add_forget_plan (head)`），禁止多 head。
- 契约 §四.3 中 `20260831_add_source_events` 的 down_revision 标注（`20260831_preference_versions`）与 ADR-013/014 实施对齐记录一致，本 D10D 迁移不受影响。

---

## 二、契约 §三~§九 落地映射（逐项）

| 契约节 | 契约要点（冻结） | Plan 落地（任务卡 Step） | 状态 |
|---|---|---|---|
| §三.1 | 复用 E 轨 `ForgetPlan`；五值 forget_mode + selector 互斥；`resolved_target_ids`/`affected_count`/`requires_confirmation` 禁止模型生成；`affected_count = len(resolved_target_ids)`（MEDIUM-03） | S1/S3/S4：Repository/UoW 落库 + Domain 校验复用；Preview 完整性断言 | 落地 |
| §三.2 | 确认凭据（一次性，绑定 user+plan+hash+TTL+防重放）；幂等复用 FRZ-IPC-005（不新建表）；`delete_mode` 可信来源由 ADR-019 冻结（MEDIUM-04） | S3/S4 + ADR-019 §4.2/§4.7；request_fingerprint 敏感占位（对齐 ADR-014 v5） | 落地（D3/D4 已决策） |
| §三.3 | 状态机冻结七值；`awaiting_confirmation → executing` 接线前 fail-closed | S3/S4 终态迁移 + fail-closed | 落地 |
| §四.1 | `forget_plan` 表（DDL + UNIQUE(user_id, forget_plan_id) + (user_id, created_at)） | S1 Schema + 迁移 | 落地 |
| §四.2 | `forget_audit` 零正文 + `executed_at` 填写语义（MEDIUM-01） | S1 + S3 审计写入（terminal 必填 executed_at） | 落地 |
| §四.3 | 迁移规则（真实 heads；禁多 head；downgrade DROP） | §一 + S1 | 落地（已确认） |
| §四.4 | 软删优先（is_deleted=1，FTS 不再命中）；硬删物理清除 Runtime fail-closed；软删可见性以 SQLite 为准 | S5 dispatcher（knowledge/preference 权威状态；event fail-closed D2） | 落地（D2 已决策） |
| §四.5 | is_cascade 默认 false；跨 Consent Scope 禁止传播；Cascade Runtime fail-closed | S5 fail-closed | 落地 |
| §四.6 | full_reset 语义冻结；Runtime fail-closed 至闭环 | S5 fail-closed | 落地 |
| §四.7 | 高敏感批量删除确认门槛语义；绝对拒绝清单 | S4 凭据校验 + fail-closed | 落地 |
| §四.8 | selector 明文生命周期（HIGH-01）：短期存在、Preview 后清除/占位、`target_topic` 同纳入、Sentinel 验收 | S3 清理 + S6/L1 用例 11/16 | 落地 |
| §四.9 | delete_mode 门禁：ADR-019 冻结可信来源；Repository 不推导；LLM 不终判；hard 接线前 fail-closed | ADR-019 §4.2 + S5 fail-closed | 落地（D3 已决策） |
| §五.1 | preview：规则引擎生成 resolved/affected/selection_hash → 凭据（32B，只存 SHA-256）→ 返回 {preview_result, selection_hash, credential_ttl}；Preview 后清 selector | S3/S4 + S9（resolver seam，D6） | 落地（D6 已决策） |
| §五.2 | execute：校验绑定+未过期+未使用 → 只消费已确认 ID 软删 → 标记凭据已消费 → executed_count → 审计；`executed_count != affected_count` 不进 completed | S4/S5 | 落地 |
| §五.3 | execute 幂等重放返回首次结果；**forget.preview 为一次性凭据受控例外（R2 收口）**：同键+同指纹重放 fail-closed → `INVALID_REQUEST`，不重发/不生成第二枚凭据 | S4（execute_idempotent 复用 + preview cache 脱敏） | 落地（R2 收口） |
| §五.4 | 凭据失败 → INVALID_REQUEST；事务失败整体回滚凭据保留 | S3/S4 错误映射 | 落地 |
| §六 | Outbox 高优先级：方案 A（nullable priority + 部分索引 + worker ORDER BY priority DESC, next_retry_at ASC + CHECK 扩展 'forget'） | S1/S6 | 落地（D1 已决策） |
| §七 | 关键决策 F-1~F-14 全部采纳 | 任务卡 §一.1~§一.7 + ADR-015/019 | 落地（F-11 DEFERRED 不实现） |
| §八 | 错误语义复用冻结域，不新增错误码 | S4 映射表（任务卡 §一.3） | 落地 |
| §九 | L0/L1/L2 测试规划（逐项） | 任务卡 §六（21 项 L1 + L0 + L2 清单） | 落地 |

---

## 三、风险清单

| # | 风险 | 等级 | 缓解 |
|---|------|------|------|
| R1 | outbox `aggregate_type` CHECK 值域扩展需 SQLite 表重建，downgrade 数据保留复杂度 | 中 | D1 决策；手写重建迁移 + 往返测试；备选弱化（不改 CHECK 仅 priority 驱动） |
| R2 | event 目标（source_events）无 `is_deleted` 列，消费者在 `pipeline/`（红线不可改）→ event-target 软删不可落 | 中 | D2 决策：Runtime fail-closed + 登记 TD-E（staged，`executed_count` 反映真实，不假完成）；或经独立变更新增 source_events 列（超出本任务红线范围，须 D 另行授权） |
| R3 | preview resolver 覆盖范围（仅 single_item/session 确定性；topic/time_window/full_reset 本期不支持） | 中 | single_item/session 走真实 scoped 解析；topic/time_window/full_reset Preview 明确 fail-closed；不做 Mock/固定返回（红线） |
| R4 | 凭据明文回传信道（响应回传一次 vs 独立确认信道） | 低 | D4 决策；服务端只存 SHA-256，明文生命周期收敛 |
| R5 | request_fingerprint 敏感占位与 selection_hash 派生域边界 | 低 | D5 决策 + L1 用例 19；selection_hash 仅由结构化 ID 派生，不作用于正文 |
| R6 | 对外状态：完整跨轨 + 麒麟 L2 证据闭环前一律 `PARTIAL / staged implementation`，不得写 D10 DONE | 硬性 | 报告与 PR 表述遵守；L2 只列清单不声称已执行 |
| R7 | 状态机「漏删不报完成」依赖 executed_count 精确统计 + 软删 dispatcher 原子性 | 中 | 同事务软删 + executed_count 校验 + L1 用例 2/10/13 |

---

## 四、D 决策记录（D1~D6 已决策，2026-09-01 全部采用推荐方案；Build 前闭合）

| # | 决策点 | D 决策结论 | 影响范围 |
|---|--------|------|---------|
| D1 | outbox `aggregate_type` CHECK 值域扩展（SQLite 重建） | **采用方案 A**：扩展（重建迁移，保留数据） | 迁移 + outbox/worker + 入队 |
| D2 | event 目标（source_events）软删机制 | **fail-closed + 登记 TD-E**（staged）；不本任务内改 source_events（红线） | S5 dispatcher + executed_count 语义 |
| D3 | `delete_mode` 可信输入来源冻结 | **ADR-019 冻结**为「可信宿主显式提供，默认 soft」；接线前 hard fail-closed | ADR-019 + S7 |
| D4 | Preview 凭据明文回传信道 | **响应回传一次明文**（服务端只存哈希；已冻结 `confirmation_token` 字段） | ADR-019 + handler |
| D5 | selection_hash 派生域 | **仅由结构化 `resolved_target_ids` 派生** | S3 + 安全用例 |
| D6 | Preview 规则引擎 seam 归属与范围 | **D 轨新增 `service/forgetting.py`**；single_item/session 确定性；topic/time_window/full_reset fail-closed | S9 新增文件 + 测试 |

> **R2 收口说明（PR #120 第二轮 REWORK）**：`forget.preview` 幂等重放受控例外与 Preview 响应字段真源统一由 ADR-019 v2 记录（§五.3 / 任务卡 §一.5 / 用例 21），属契约文档治理收口，未新增 D 决策项，待 Reviewer E 复审确认。

---

## 五、Phase 2（Build）范围预授权边界

- Build 将严格限定在任务卡（18_）批准范围内：schema/迁移/Repository/UoW/outbox 优先级/软删主路径/fail-closed/测试 +（ADR-019 签署后）gateway seam（MEDIUM-02 方案 2：与持久化层同 PR 交付）。
- 红线不随 Phase 2 解除：不修改冻结契约与既有实现、不接 Vector 清理、不实现 hard/cascade/full_reset（**方案 A：full_reset Preview/Execute 本期均 fail-closed，MEDIUM-04**）/time_window/回滚完整逻辑、不 push/不创建 PR、WSL 结果不作宿主证据。
- Build 完成后按 skill 输出格式出开发报告，L2 只列麒麟人工操作清单。

---

## 六、完成判定（Phase 1）对照

| 判定项 | 状态 |
|--------|------|
| 三个文档产出且内容对齐契约 v0.3（§三~§九）无遗漏 | ✅ 17_/18_/19_ 已产出（映射表见 §二） |
| 迁移链已用真实 `alembic heads` 确认并记录实际输出 | ✅ 见 §一（head=`20260901_d10b_vector_ledger`；单 head） |
| 红线无违反 | ✅ Plan 阶段仅写文档，零代码生成；无 push、无 PR |

---
*本文档为 Phase 1 / Plan 交付物之一（`docs/day10/19_d10d_impl_plan.md`）；按委托书红线仅写文档不写代码；无 push、无 PR。编制：opencode（D 轨），2026-09-01。*
