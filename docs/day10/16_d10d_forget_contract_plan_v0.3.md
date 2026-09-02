# D10-D 精准遗忘持久化契约规划（草案 v0.3）

- **编制日期**：2026-09-01（v0.3 按 Review #99 Reviewer E 第一、二轮 REWORK 意见修订）
- **编制人**：opencode（D 轨开发 Agent）
- **状态**：DRAFT v0.3 — 按 Review #99 Reviewer E 第一、二轮 REWORK 意见修订（第一轮 HIGH-01 / MEDIUM-01~04 / 非阻断 2 项；第二轮 MEDIUM-01 / MEDIUM-02 / LOW-1 / LOW-2 全部闭合），并吸收 PR #98 冻结回复（`APPROVED_WITH_STAGED_RUNTIME`，2026-09-01）；**ADR-015/019 已由 D 决策，待 Reviewer E 签署**后转正式契约
- **对照基线**：main @ `0cdada7`（PR #88 E 轨检索治理合并后，含 PR #94 D10E B 轨；PR #99 已 rebase 同步）；`docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md`（§5.5 ForgetPlan，`CANDIDATE_FOR_FREEZE`）；`deliverables/D4_DB_INITIAL_DESIGN_FREEZE_20260817.md`（FRZ-DB-001）；`deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-007）；`docs/adr/013-source-events-table.md`、`014-event-ingest-method.md`（D6-D 契约 v5，编号占用先例）；PR #94（D10-E B 轨代行，selector 边界/状态机前置）；PR #82（D10-B Vector 删除工作计划）

---

## 〇、冻结申请回复要点（Reviewer E，2026-09-01，权威依据）

E 轨对 D10-D 精准遗忘冻结申请的正式回复（PR #98 评论区，lovezy0730-create）：**APPROVED_WITH_STAGED_RUNTIME** —— 同意路径 A（D10-D 与 D10-E 并行），分层冻结：

- **立即冻结（业务基线明确）**：`forget_mode` 五值 + selector 互斥；`resolved_target_ids` 由系统规则引擎生成（禁止 LLM 决定删除范围）；Preview→Confirmation→Execute 状态机；普通遗忘默认软删；`is_cascade=false` 默认；`full_reset` 限当前用户 Agent Memory 自有数据域；最小审计「零正文」；误删/跨用户=0、漏删不报完成。
- **冻结契约、执行 fail-closed（跨轨 Runtime 依赖）**：Hard Delete 物理清除、Cascade Runtime、Full Reset Runtime、Vector 全量清理、Cache/重建残留全验证——在对应跨轨实现 + 麒麟 L2 证据闭环前，Runtime Execute 一律 fail-closed。
- **继续 DEFERRED（缺依据，实现侧不得自行解释）**：`time_window` canonical 时间字段（业务时间字段 / 时区 / 区间开闭）需 D/E 另行书面冻结。
- **对外状态口径**：完整跨轨实现与真实麒麟验证完成前，一律写 `PARTIAL / staged implementation`；不得写 `D10 DONE / 精准遗忘完整完成 / hard delete supported / full_reset supported`。

本规划 v0.3 全量吸收该回复并闭合 Review #99 REWORK 意见；**本文件本身不替物理 Schema / ADR / Runtime 实现作完成性背书**。

### REWORK 处置摘要（Review #99 Reviewer E，2026-09-01）

| REWORK 项 | 处置（对应章节） |
|---|---|
| **HIGH-01** `target_selector` 明文生命周期 | §四.8：原始 `target_selector` 仅短期存在，Preview 后或 Hard Delete 完成前清除/替换安全占位；持久层不长期保存原始 selector，仅存结构化 selector / `selection_hash`；`target_topic` 等可能承载自然语言正文的字段同纳入；Sentinel 验收覆盖 `forget_plan` / `forget_audit` / Outbox payload / 服务日志 / 导出与临时输出 |
| **MEDIUM-01** `forget_audit` 补 `executed_at` | §四.2：补 `executed_at` 字段并明确 execute / terminal audit 填写语义（与 `created_at` 不等价） |
| **MEDIUM-02** 迁移链修正 | §四.3：迁移规则改为「以实现时 `alembic heads` 真实链路为准」；当前以已合并 PR #98 后的真实 head 为准；禁止产生多 head |
| **MEDIUM-03** `affected_count` 语义 | §三.1 / §四.1：统一为 Preview 时确定并经确认的目标数量 = `len(resolved_target_ids)`；另设 `executed_count`，实际处理数量与 `affected_count` 不一致时不得进入 `completed` |
| **MEDIUM-04** `delete_mode` 门禁 | §四.9：`delete_mode` 可信来源由 ADR-019 冻结；Repository 不得按 `target_selector` 自行推导；LLM 不得终判 soft/hard；接线前 Hard Delete Runtime fail-closed |
| 非阻断 1 | PR body 表述修正为「基于前置 v0.1 修订后首次入库 v0.2」 |
| 非阻断 2 | §四.2：`forget_audit` 的 `forget_mode` / `target_type` / `status` SQL CHECK 注明留待 ADR-015 Schema 定稿时补充 |

### REWORK 第二轮处置摘要（Review #99 Reviewer E，2026-09-01，基于 HEAD `b8740ac`）

上一轮 5 项已全部闭合，本轮为第二轮最小修订（MEDIUM 2 + LOW 2）：

| REWORK 项 | 处置（对应章节） |
|---|---|
| **MEDIUM-01** Preview 后清除 selector 与 `ForgetPlan` 必填契约冲突 | §三：明确 `forget_plan` persistence row 属 **D 轨持久化实体**，`ForgetPlan` 仅用于创建 / Preview 前业务输入校验；Preview 完成并清理原始 selector 后**不要求持久化记录再次完整反序列化为 E 轨 `ForgetPlan`**；Execute 阶段只消费已确认执行快照（`user_id + forget_plan_id + resolved_target_ids + selection_hash + confirmation state`），**不得重新依赖 selector 做范围解析**；§四.8 同步呼应 |
| **MEDIUM-02** `executed_count` 归属错误 | §三.1：`executed_count` 移出「ForgetPlan 复用字段」，明确为 **D 轨持久化 / Execute 结果字段**（数据库 `forget_plan.executed_count` 可保留）；删除「审计用」表述，是否进最终 `forget_audit` 由 ADR-015 定稿时决定 |
| **LOW-1** 文档基线 SHA 未同步 | 文档头：同步为当前真实基线 `main @ 0cdada7` |
| **LOW-2** PR body rename 描述 | PR body：调整为与 aggregate Diff 一致（git mv 升版 + 修订，GitHub aggregate 显示为新增文件） |

---

## 一、背景与目标（台账 R55 / D10-D）

D6-D（R35）已规划多源事件持久化（`source_events`，ADR-013/014 已签署合并；其 Migration `20260831_add_source_events` 已随 PR #98 并入 main，见 §四.3）。D10-D 承接「精准遗忘与删除一致性」的 **D 轨持久化职责**：

1. **完成 SQLite Forget 事务和确认令牌** —— 遗忘计划落库 + preview/execute 分离 + 确认令牌（`[02 §10.1]`）；
2. **将删除 Outbox 设为高优先级** —— 遗忘/撤回任务优先于普通索引任务（`[02 §11.3]`），需 Outbox 优先级机制；
3. **实现幂等、失败重试和最小审计** —— 幂等键复用（FRZ-IPC-005 / ADR-006）、重试走既有 worker 退避/DL、审计不保留正文。

交付边界：**遗忘持久化层**（表 + 迁移 + Repository + 事务/令牌语义 + 测试），不接 Vector 清理（TD-033/B 轨未完成，`has_vector_cleanup` 保持 DEFERRED），不改 IPC envelope。

**时序（F-7 已确认）**：D 轨可先行开发「结构化 Selector → resolved_target_ids / Preview → Confirmation 边界 → Soft Delete → Audit → Outbox」；Hard Delete / Cascade / Full Reset 物理链路不阻塞开发，但不得提前宣称完成。

---

## 二、范围与禁止修改范围

### 允许修改
- `memory-service/db/schema.py`（新增 `forget_plan` / `forget_audit` 表，既有表定义不动）
- `memory-service/db/repositories.py`（新增遗忘 Repository 函数）
- `memory-service/db/uow.py`（如需遗忘事务封装，复用现有模式）
- `migrations/versions/YYYYMMDD_add_forget_plan.py`（新增迁移，ADR-007 命名）
- `memory-service/domain/forgetting.py`（如需要补充 D 轨持久化枚举，优先复用现有 ForgetMode/ForgetPlanStatus/TargetType；**状态机值域按本文件 §三冻结**）
- `memory-service/outbox/`（优先级机制，见 §六）
- 新增测试 `memory-service/tests/test_forget_persistence_d10d.py`
- 契约文档（本文档 + ADR-015/019 + 冻结文档回写）
- ADR-019 经 D 决策且 Reviewer E 签署后，允许**新增** `memory-service/gateway/forget_handlers.py`
- ADR-019 经 D 决策且 Reviewer E 签署后，允许对 `memory-service/app.py` 进行**仅限 conditional activation seam** 的增量修改；production 默认不注册，不得借此修改其他既有 Gateway 行为

### 禁止修改（红线）
- 不修改冻结 FRZ-IPC-001~007 既有字段/错误码/envelope（forget 方法走 ADR-019 新增）
- 不修改 FRZ-DB-001 既有 5 张表定义（forget 表为新增，走 ADR-015）
- 不修改 `pipeline/`、`providers/`、`security/`、`service/candidate_governance.py`、`gateway/`、`embedding/`、`retrieval/`、`observability/` 既有实现；上方明确授权的新增 `gateway/forget_handlers.py` 与 `app.py` conditional activation seam 除外
- **不接 Vector 清理**（TD-033 未完成；`has_vector_cleanup` 字段仅承载标记，不实现清理）
- **不实现硬删除物理清除**（业务语义已冻结，但 Runtime Execute 保持 fail-closed，见 §四.4；物理清除实现登记 TD 待跨轨闭环）
- **不实现 Cascade / Full Reset Runtime**（语义冻结，Execute fail-closed，见 §四.5/§四.6）
- 不把 WSL/Mock 结果当宿主证据；L2 未执行不写「已支持」

---

## 三、输入契约（复用 E 轨 Domain，不复制真源）

遗忘执行输入 = **`ForgetPlan`**（`memory-service/domain/forgetting.py`，D3 §5.5 字段落地）+ **确认凭据**（本层新增，见 §五）。复用约束：不复制 ForgetMode/ForgetPlanStatus/TargetType 枚举，不重建业务校验器。

> **persistence 边界（v0.3/第二轮 MEDIUM-01）**：`forget_plan` persistence row 属于 **D 轨持久化实体**。`ForgetPlan` 用于**创建 / Preview 前**业务输入校验；Preview 完成并清理原始 selector 后，**不要求持久化记录再次完整反序列化为 E 轨 `ForgetPlan`**（现有 Domain 的 `target_selector: NonEmptyStr` 必填、模式条件字段必填与 `ConfigDict(extra="forbid")` 仅约束创建 / Preview 前输入，不再约束已清理的持久化记录）。Execute 阶段只消费已确认的执行快照（`user_id + forget_plan_id + resolved_target_ids + selection_hash + confirmation state`），**不得重新依赖 selector 做范围解析**。

### 3.1 复用字段（ForgetPlan，D3 §5.5）+ v0.3 冻结修订

| 字段 | 类型 | 说明（v0.3 冻结） |
|---|---|---|
| `forget_plan_id` | NonEmptyStr | 遗忘计划唯一 ID |
| `user_id` | NonEmptyStr | **隔离键，禁止模型生成**（D3 §7.10） |
| `forget_mode` | ForgetMode | **五值冻结**：single_item / session / topic / time_window / full_reset。**selector 互斥冻结**：单模式单边界——`single_item` 仅 target_id；`session` 仅 target_session_id；`topic` 仅 target_topic；`time_window` 仅 target_time_range；`full_reset` 不得携带任何 target_* 字段（跨模式 selector 一律拒绝，SEC-FORGET-03） |
| `target_selector` | NonEmptyStr | 用户输入选择器；**明文生命周期（v0.3/HIGH-01，详见 §四.8）**：仅短期存在，持久层不长期保存原始 selector，Preview 完成后清除/置安全占位 |
| `target_type` | TargetType | knowledge / preference / event / all |
| `status` | ForgetPlanStatus | **状态机冻结（v0.2 替换旧七值）**：`pending → previewing → awaiting_confirmation → executing → completed / failed / rolled_back`；见 §三.3 |
| `requires_confirmation` | bool | **禁止模型生成**（D3 §7.10） |
| `resolved_target_ids` | Optional[List[str]] | **禁止模型生成**（D3 §7.6）；**必须由系统规则引擎生成**；Preview 时刻生成的、限定当前 `user_id`、已去重、确定且可重放的业务对象 ID 快照；`[]` 且 `affected_count=0` 为合法 Preview（精准解析零命中），不得强行转错误、不得解释为扩大删除范围 |
| `affected_count` | Optional[int] | **禁止模型生成**；**统一语义（v0.3/MEDIUM-03）**：= Preview 时确定并经确认的目标数量 = `len(resolved_target_ids)`，**不是** execute 才产生的字段；进入 `awaiting_confirmation` 前必须满足 `resolved_target_ids is not None` 且 `affected_count == len(resolved_target_ids)`；`[]` / `0` 为合法零命中 |
| `is_cascade` | bool | **冻结：默认 `false` 为安全语义**；`true` 仅允许沿明确、可验证的业务 provenance/evidence 派生关系扩展目标，且扩展后全部对象**必须进入 `resolved_target_ids` 与 Preview**，不得在执行阶段隐式增加目标；**禁止跨 Consent Scope 自动传播**（不得自动删除宿主聊天历史/Recollect 原始数据/截图 OCR/外部来源实体） |
| `target_id` / `target_session_id` / `target_topic` / `target_time_range` | Optional | 模式条件字段（互斥见上） |
| `executed_at` / `created_at` | AwareDatetime | 时间一致性已由 Domain 校验 |

> **`executed_count` 归属（v0.3/第二轮 MEDIUM-02）**：`executed_count` 为 **D 轨持久化 / Execute 结果字段**，**不属于当前 E 轨 `ForgetPlan` Domain**（现有 `ForgetPlan` 无该字段，且 `extra="forbid"` 无法传入）；数据库 `forget_plan.executed_count` 可保留。其语义不变：Execute 必须完整消费确认快照，`executed_count != affected_count` 时不得进入 `completed`（闭合「漏删不得报完成」）。该字段**不用于审计**；若确需进入最终审计，由 **ADR-015 定稿时**再决定是否加入 `forget_audit`。

### 3.2 本层新增概念（不属 E 轨 Domain）

| 概念 | 说明（v0.3 冻结） |
|---|---|
| **确认凭据（confirmation credential）** | preview → execute 之间的一次性凭据；execute 必须携带；**至少绑定**：`user_id` + `forget_plan_id` + 目标快照（或其稳定 Hash）+ 有效期 + 防重放信息；**必须拒绝**：用户不匹配 / 计划 ID 不匹配 / Preview 已变化 / 目标快照不匹配 / 过期 / 重放（`[02 §10.1]`） |
| **幂等键复用** | 复用 FRZ-IPC-005 三元组 `(user_id, session_id, idempotency_key)` 语义（idempotency_cache，TTL 24h），**不新建**遗忘专用幂等表 |
| **delete_mode 决策来源（v0.3/MEDIUM-04）** | ForgetPlan **本版不新增** `delete_mode` 字段（最终 IPC 字段形态由 ADR-019 冻结）；可信来源门禁：`delete_mode` 的可信输入由 **ADR-019 冻结**；**Repository 不得根据 `target_selector` 自行推导 soft/hard**；**LLM 不得决定最终 soft/hard 执行模式**；可信来源冻结与接线前，Hard Delete Runtime 继续 **fail-closed**（详见 §四.9） |

### 3.3 状态机（v0.2 冻结，替换 v0.1 七值）

```
pending → previewing → awaiting_confirmation → executing → completed / failed / rolled_back
```

- **`previewing → awaiting_confirmation`**：必须已形成完整 Preview（确定的 `resolved_target_ids` + `affected_count` + 当前 `user_id` + 当前 `forget_plan_id` + 可用于确认绑定的目标快照）；不得出现「未形成精准解析结果但已等待确认」的状态。
- **`awaiting_confirmation → executing`**：由 D 轨负责 Runtime 接线；在确认凭据与事务接线完成前，该迁移必须继续 **fail-closed**。
- **消费/执行语义**：最终 Execute 只允许消费已经 Preview 并确认的 `resolved_target_ids`；禁止模糊关键词直接删除、禁止时间条件直接转大范围 SQL 删除绕过 ID 解析、禁止 Preview 后重新扩大目标集合、禁止模型生成/补全/替换最终 ID、禁止跨用户目标进入当前用户 `resolved_target_ids`。

---

## 四、DB 表设计（新增 2 表，FRZ-DB-001 扩展）

### 4.1 `forget_plan`（遗忘计划持久化）

```sql
CREATE TABLE forget_plan (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id               TEXT    NOT NULL,          -- 隔离键，禁止模型生成
    forget_plan_id        TEXT    NOT NULL,          -- 计划唯一 ID（宿主生成）
    forget_mode           TEXT    NOT NULL,          -- 五值枚举（v0.2 冻结）
    target_selector       TEXT,                      -- 用户输入选择器（明文生命周期见 §四.8：仅短期存在，Preview 后/Hard Delete 完成前清除或置安全占位，可空）
    target_type           TEXT    NOT NULL,          -- 四值枚举
    target_id             TEXT,                      -- 模式条件字段（互斥）
    target_session_id     TEXT,
    target_topic          TEXT,                      -- 模式条件字段（互斥）；可能承载自然语言正文，按 §四.8 明文生命周期处理
    target_time_range     TEXT,
    resolved_target_ids   TEXT,                      -- JSON 数组（preview 产物，禁止模型生成；含 cascade 扩展目标）
    selection_hash        TEXT,                      -- Preview/Selection 稳定 Hash（确认凭据绑定 + 审计引用，非正文；长期持久化真源之一）
    status                TEXT    NOT NULL,          -- v0.2 冻结状态机（见 §三.3）
    requires_confirmation INTEGER NOT NULL DEFAULT 1, -- 禁止模型生成
    is_cascade            INTEGER NOT NULL DEFAULT 0, -- v0.2 冻结：默认 false；true 仅业务派生且目标进 Preview
    delete_mode           TEXT    NOT NULL DEFAULT 'soft', -- soft / hard（v0.2 冻结语义；v0.3/MEDIUM-04 可信决策来源门禁见 §四.9；hard 物理清除 Runtime fail-closed）
    has_vector_cleanup    INTEGER NOT NULL DEFAULT 0, -- DEFERRED（待 B，本版不实现清理）
    confirmation_token    TEXT,                      -- 确认凭据（哈希存储，见 §五）
    token_expires_at      TEXT,                      -- 凭据 TTL（建议 5 分钟，可调）
    affected_count        INTEGER,                   -- Preview 时确定并经确认的目标数量 = len(resolved_target_ids)，禁止模型生成（v0.3/MEDIUM-03）
    executed_count        INTEGER,                   -- 实际执行成功数量（v0.3/MEDIUM-03，可选）；与 affected_count 不一致时不得进入 completed
    executed_at           TEXT,                      -- 遗忘动作实际执行时间
    rollback_plan_id      TEXT,
    created_at            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL,
    CHECK (forget_mode IN ('single_item','session','topic','time_window','full_reset')),
    CHECK (target_type IN ('knowledge','preference','event','all')),
    CHECK (status IN ('pending','previewing','awaiting_confirmation','executing','completed','failed','rolled_back')),
    CHECK (delete_mode IN ('soft','hard'))
);
```

**索引**：`UNIQUE(user_id, forget_plan_id)`（计划级唯一 + 跨用户隔离双重限制）；`(user_id, created_at)`（时间线审计）。

> 说明：v0.1 旧七值 `draft/pending/previewed/confirmed/completed/failed/rolled_back` 被 v0.2 冻结状态机替换；`previewed`→`awaiting_confirmation`、`confirmed` 语义并入 `awaiting_confirmation`（确认凭据绑定）。

### 4.2 `forget_audit`（最小审计，零正文）

按 Reviewer E 冻结回复 §8 最小字段集：

```sql
CREATE TABLE forget_audit (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id          TEXT    NOT NULL,              -- 审计唯一 ID
    forget_plan_id    TEXT    NOT NULL,
    user_id           TEXT    NOT NULL,
    forget_mode       TEXT    NOT NULL,              -- 五值
    target_type       TEXT,                          -- 四值
    delete_mode       TEXT    NOT NULL,              -- soft / hard
    is_cascade        INTEGER NOT NULL DEFAULT 0,
    affected_count    INTEGER,
    selection_hash    TEXT,                          -- Preview/Selection Hash（非正文）
    confirmation_ref  TEXT,                          -- 确认凭据的非敏感引用/Hash（不得保存原 Token）
    status            TEXT    NOT NULL,              -- 终态或动作后状态
    result_code       TEXT,                          -- 结果码（复用错误语义域）
    trace_id          TEXT,                          -- 追踪链（非正文）
    sensitivity_max   TEXT,                          -- 可选：结构化等级字段
    created_at        TEXT    NOT NULL,              -- 审计记录生成时间
    executed_at       TEXT,                          -- 遗忘动作实际执行时间（v0.3/MEDIUM-01，填写语义见下）
    CHECK (delete_mode IN ('soft','hard'))
    -- forget_mode / target_type / status 的 SQL CHECK 留待 ADR-015 Schema 定稿时一并补充（Review #99 非阻断 2，本轮前置草案不要求完成全部数据库约束）
);
```

**红线（v0.2 冻结，验收见 §九）**：
- `forget_audit` **不保留正文**：禁止保存 Memory 正文 / Summary / 原始 `target_selector` / 原始引用文本 / Preference·Knowledge 原值 / Confirmation Token 原文 / 敏感错误详情 / 可重新恢复被删正文的 Payload。
- 不只检查名为 `content` 的字段：`target_selector` / `reason` / `details` / `source_reference` / `error_message` / 任意自由文本扩展字段均不得进入正文。
- Hard Delete 优先保留 `selection_hash + affected_count`，不长期保存完整明细 ID 集。

**`executed_at` 填写语义（v0.3/MEDIUM-01）**：`created_at` = 审计记录生成时间；`executed_at` = 遗忘动作实际执行时间（execute 实际执行时刻）。Preview 与 Execute 可能间隔明显，二者不等价。填写规则：
- Preview 阶段生成的审计（若有）：`executed_at` 置 NULL（未执行）；
- execute 实际执行完成（含失败 / 回滚终态）时：必须填写 `executed_at`；
- terminal audit（`completed` / `failed` / `rolled_back`）必须携带 `executed_at`；仅 `created_at` 而无 `executed_at` 的记录不得作为「已执行」证据。

### 4.3 迁移（v0.3/MEDIUM-02 修订）
- 文件：`migrations/versions/20260901_add_forget_plan.py`（ADR-007 命名，独立 revision）
- **迁移规则以实现时真实 Alembic HEAD 为准（v0.3/MEDIUM-02）**：
  - PR #98（D6-D，`20260831_add_source_events`）已并入 main（合并提交 `79411f1`）；
  - 当前真实 Alembic HEAD 为 `20260901_d10b_vector_ledger`，本任务迁移以该 revision 为 `down_revision`；
  - 实现 PR 创建时再次执行 `alembic heads` 确认真实链路，**禁止产生多 head**；
  - 本 PR（契约先行）不实现 Migration。
- downgrade：DROP TABLE（新表无既有数据依赖）

### 4.4 软删除 / 硬删除语义（v0.2 冻结）

- **软删除优先（普通精准遗忘默认路径）**：对当前 SQLite 真源采用 `is_deleted=1` 等既有权威删除状态。软删成功提交后**必须立即**产生：标准 SQLite 查询不再视为 active；FTS 不得再次命中；Vector 不得参与有效召回；Cache 不得恢复被删内容；MemoryContext 不得再注入；后续重建不得恢复可见。即「删除可见性以 SQLite 权威真源状态为准，派生索引清理失败不得使已遗忘内容重新可见」。软删允许受控恢复（rollback/restore）。
- **硬删除（`hard_delete=true`）**：不可恢复的物理正文清除；完成后在本产品承诺覆盖的 SQLite / FTS5 / Vector / Cache / 普通日志 / 导出及可重建来源中不得保留可检索明文残留。**不得实现为「只置 is_deleted=1 后声称彻底删除」**；关键数据层无法物理清除时**必须 fail-closed，不得自动降级为软删后返回「硬删除成功」**；**Hard Delete 完成前必须完成 selector 明文清除（原始 `target_selector` / `target_topic` 等，见 §四.8）**。
- **回滚边界**：Soft Delete 允许受控恢复；Hard Delete 不承诺正文恢复；`rollback_plan_id` 服务于软删恢复/事务失败补偿/部分执行回滚，已物理清除的正文不得依赖隐藏副本恢复。
- **Runtime 状态**：软删可先行实现并声称完成；**Hard Delete Runtime Execute 在跨轨实现 + L2 证据闭环前保持 fail-closed**（业务契约已冻结，能力状态未完成）。

### 4.5 `is_cascade` 语义（v0.2 冻结，见 §三.1）

- 同一业务对象在 SQLite / FTS / Vector / Cache / MemoryContext 的表示属于「删除一致性闭包」，**不属于 `is_cascade` 的业务级联**——即使 `is_cascade=false`，被删对象这些派生表示也必须全部退出可见范围。
- `is_cascade=true` 仅沿明确业务 provenance/evidence 派生关系扩展（如事件 E1 → Preference P1 / Knowledge K1），扩展对象全部进 Preview；**禁止跨 Consent Scope 自动传播**。
- Cascade Runtime 在跨轨实现前 fail-closed；本版表结构承载语义与标记，不实现级联执行。

### 4.6 `full_reset` 安全边界（v0.2 冻结）

- 语义：当前 `user_id` 在 Agent Memory 自有数据域中的**全部记忆对象重置**；不自动等于删除聊天历史 / Recollect 原始采集数据 / 其他独立数据域。
- 必须满足：不携带具体对象 selector；先生成全量 Preview 快照；显式确认；**高于普通删除的确认等级**；确认绑定 Preview/Selection Hash；校验过期与重放。
- **Runtime**：业务语义冻结；在 D 轨确认凭据/事务/审计、B 轨 Vector 清理一致性闭环完成前，`full_reset` Runtime Execute 保持 **fail-closed**；不得因枚举存在而视为「全量重置能力已完成」。

### 4.7 高敏感与批量删除（v0.2 冻结）

- 不采用「高敏感数据一律禁止批量/full_reset 删除」；正确语义为：**敏感度越高、范围越大，确认门槛越高，但用户对自己合法数据的删除权不因数据敏感而取消**。
- 确认等级建议：普通小范围 = Preview + Confirmation；批量/高敏感/跨来源 = Fresh/强确认；`full_reset` = 最高级确认 + 独立确认凭据。
- 绝对拒绝：跨用户 / 身份不可信 / 授权不匹配 / Preview 不完整 / 确认凭据与计划不匹配 / 目标快照变化仍尝试执行。

### 4.8 `target_selector` 明文生命周期（v0.3/HIGH-01 处置）

Hard Delete 冻结语义要求「SQLite / FTS5 / Vector / Cache / 日志 / 导出 / 可重建来源中不得保留可检索明文残留」；原始 `target_selector`（用户原始选择描述）可能直接包含待永久删除的敏感正文，若长期保留于 `forget_plan` 即违反该语义。契约规则：

1. **原始 `target_selector` 仅短期存在**：生命周期 = 计划创建 → Preview 完成（进入 `awaiting_confirmation`）后**清除或替换为安全占位**（置 NULL 或固定 `<CLEARED>`）；若进入 Hard Delete，**在物理清除完成前必须已清除**；任何路径（含软删可恢复路径）都不得长期保留明文 selector。
2. **持久层不长期保存原始 selector**：长期仅保存结构化 selector（模式条件字段）与 `selection_hash`（Preview/Selection 稳定 Hash，非正文、不可逆推正文）；原始 selector 不作为审计或可重建来源。
3. **`target_topic` 等可能承载自然语言正文的字段同纳入处理**：`target_topic` / `target_time_range` 等若携带用户正文 / 敏感正文，Preview 完成后同等清除或替换为安全占位；执行阶段只依赖 `resolved_target_ids + selection_hash`，不依赖明文条件字段。
4. **执行与审计不依赖明文**：execute 仅消费已确认的 `resolved_target_ids`；审计只存 `selection_hash + affected_count` 等结构化引用（§四.2 红线）。
5. **Schema**：`forget_plan.target_selector` 改为**可空列**（TEXT，不设 NOT NULL），以承载「已清除」状态；`selection_hash` 为长期持久化真源之一。
6. **Sentinel 验收扩展（§九）**：覆盖 `forget_plan`、`forget_audit`、Outbox payload、服务日志、导出 / 临时输出——带唯一 Sentinel 的合成敏感正文执行遗忘后，上述全部范围 0 命中。
7. **persistence 反序列化边界（v0.3/第二轮 MEDIUM-01）**：清理后的持久化记录属于 **D 轨实体**，**不要求再完整反序列化为 E 轨 `ForgetPlan`**（Domain 的 `target_selector` 必填与模式条件必填仅约束创建 / Preview 前输入，见 §三）；Execute 仅消费已确认执行快照（`user_id + forget_plan_id + resolved_target_ids + selection_hash + confirmation state`），不因清理后字段置空而违反任何输入校验、也不重新依赖 selector 做范围解析。

### 4.9 `delete_mode` 可信决策来源门禁（v0.3/MEDIUM-04 处置）

Schema 已含 `delete_mode = soft / hard`，但 `ForgetPlan` 输入不含该字段，须明确「谁决定最终 soft/hard」。契约规则：

1. **可信来源由 ADR-019 冻结**：`delete_mode`（含 hard 触发的显式信号）最终可信输入来源由 ADR-019 冻结；本 PR 为前置草案，不预先锁定 IPC 字段形态。
2. **Repository 不得根据 `target_selector` 自行推导**：禁止从自然语言 selector 推断 soft/hard。
3. **LLM 不得决定最终 soft/hard 执行模式**：soft/hard 属执行模式决策，禁止交由 LLM 终判。
4. **接线前 fail-closed**：在可信输入来源冻结并接线前，Hard Delete Runtime Execute 继续 **fail-closed**（不得自动降级软删后报「硬删除成功」）；软删主路径不受影响。

---

## 五、确认凭据与 preview/execute 分离（v0.3 修订）

1. **preview**：规则引擎解析 `ForgetPlan` → 生成 `resolved_target_ids` + `affected_count` + `selection_hash`（Preview/Selection 稳定 Hash）→ 生成**确认凭据**（随机 32B，**只存 SHA-256 哈希**，不存明文）→ 返回 `{preview_result, selection_hash, credential_ttl}`；凭据绑定 `user_id + forget_plan_id + selection_hash`。Preview 完成后按 §四.8 清除原始 `target_selector`（及含正文的模式条件字段），仅保留结构化 selector + `selection_hash`。
2. **execute**：携带 `forget_plan_id + 确认凭据` → 校验绑定（用户/计划/目标快照一致）+ 未过期 + 未使用（防重放）→ 仅消费已确认的 `resolved_target_ids` 执行软删事务 → 标记凭据已消费 → 填写 `executed_count`（实际成功数量）→ 审计写入；**不得在 execute 阶段重新扩大目标集合**；**`executed_count != affected_count` 时不得进入 `completed`（v0.3/MEDIUM-03，闭合「漏删不得报完成」）**。
3. **幂等**：execute 用幂等三元组（FRZ-IPC-005），重放返回首次结果。
4. **失败语义**：凭据无效/过期/已消费/快照不匹配 → `INVALID_REQUEST`（固定 safe_message）；事务失败 → 整体回滚，凭据保留可重试（或按 TTL 失效）。

---

## 六、Outbox 删除高优先级（`[02 §11.3]`）

**现状**：`outbox` 无 priority 列；worker 按 `next_retry_at` 排序轮询（`idx_outbox_pending`）；`aggregate_type CHECK IN ('turn','memory')` 冻结。

**候选方案**：

| 方案 | 描述 | 评价 |
|---|---|---|
| **A（推荐）** | 新增 nullable `priority` 列（INTEGER，默认 0；删除类事件 = 1）+ `idx_outbox_priority` 部分索引；worker 取数 `ORDER BY priority DESC, next_retry_at ASC`；`aggregate_type` CHECK 扩展 `'forget'` | 只增不改既有列；优先级语义简单可测试；CHECK 扩展走 ADR-015 变更控制 |
| B | 复用 `event_type='forget.executed'` 判断优先级（不新增列） | 无 DDL 变更，但 event_type 语义混合、排序条件复杂、索引失效 |
| C | 独立 forget 队列（新表） | 违背「SQLite Outbox + asyncio Worker，不引入额外消息队列」技术栈红线（`[02 §2.1]`） |

**推荐方案 A**：`outbox` 增 nullable `priority`（默认 0，`forget.*` = 1）；worker 轮询改为 `ORDER BY priority DESC, next_retry_at ASC LIMIT n`（短事务单写协调不变）；遗忘/撤回任务优先于普通索引任务（`[02 §11.3]`）。优先级取值域文档化（0=普通 / 1=删除类 / 预留 2=urgent）。

---

## 七、关键决策点（v0.3 按 Review #99 REWORK 更新）

| # | 决策点 | 冻结/推荐结论 | 说明 |
|---|---|---|---|
| F-1 | 软删 vs 硬删 | **软删优先（已冻结）**；硬删物理清除 Runtime fail-closed，登记 TD 待跨轨闭环 | E 冻结回复 §3/§4 |
| F-2 | 确认凭据存储 | **只存 SHA-256 哈希**（`confirmation_token` 列），明文不落库；审计仅存非敏感引用/Hash | 防 DB 泄露凭据复用 |
| F-3 | 凭据 TTL | 5 分钟（可调参数） | 与幂等 TTL（24h）分离：凭据短时确认，幂等重放保护 |
| F-4 | Outbox 优先级实现 | **新增 nullable `priority` 列**（方案 A） | 见 §六 |
| F-5 | forget_audit 正文 | **零正文冻结**：不落任何正文/摘要/selector 原文，只落结构化 ID 引用（selection_hash/confirmation_ref）+ 计数 | 验收含 Sentinel 扫描（§九） |
| F-6 | IPC 方法形态 | `forget.preview` / `forget.execute` 两个写方法（ADR-019） | preview/execute 分离是 `[02 §10.1]` 红线，必须两方法 |
| F-7 | 与 E 轨 D10-E 时序 | **已确认并行（路径 A，冻结回复）**：D 轨可先行开发 Preview/ID 快照/软删/FTS 退出/最小审计/Outbox/幂等/fail-closed；Hard Delete/Cascade/Full Reset/Vector 全量清理不阻塞开发但不得提前宣称完成 | 冻结回复 §11 |
| F-8 | 状态机 | **v0.2 冻结**：`pending → previewing → awaiting_confirmation → executing → completed / failed / rolled_back`；`awaiting_confirmation → executing` 接线前 fail-closed | 冻结回复 §2 |
| F-9 | full_reset | **语义冻结**：当前用户 Agent Memory 自有数据域全量重置 + 最高级确认 + 绑定 selection_hash；Runtime Execute fail-closed 至跨轨闭环 | 冻结回复 §6 |
| F-10 | is_cascade | **冻结**：默认 false；true 仅业务 provenance 派生且目标全进 Preview；禁止跨 Consent Scope 传播 | 冻结回复 §5 |
| F-11 | time_window canonical 时间口径 | **DEFERRED（待 D/E 书面补充冻结）**：业务时间字段 / 时区规则 / 区间开闭（建议半开区间 `[start_at, end_at)`）；**不得由 Repository/SQL 实现侧自行决定** | 冻结回复 §12 |
| F-12 | delete_mode 可信决策来源 | **由 ADR-019 冻结（v0.3/MEDIUM-04）**：Repository 不得按 `target_selector` 推导；LLM 不得终判 soft/hard；可信来源接线前 Hard Delete Runtime fail-closed | Review #99 MEDIUM-04 + 冻结回复 §4 |
| F-13 | target_selector 明文生命周期 | **仅短期存在（v0.3/HIGH-01）**：Preview 后 / Hard Delete 完成前清除或置安全占位；持久层仅存结构化 selector + `selection_hash`；`target_topic` 等同纳入 | Review #99 HIGH-01 |
| F-14 | affected_count 语义 | **统一为 Preview 确定并经确认的目标数量 = `len(resolved_target_ids)`（v0.3/MEDIUM-03）**；另设 `executed_count`，实际数量不一致不得进入 `completed` | Review #99 MEDIUM-03 + 冻结回复 §1.2 |

---

## 八、错误语义（复用冻结域，不新增错误码）

| 场景 | 行为 | 映射 |
|---|---|---|
| 确认凭据无效/过期/已消费/快照不匹配 | 拒绝执行，零副作用 | `INVALID_REQUEST`（safe_message 固定英文） |
| 幂等重放（同三元组 + 同 request fingerprint） | 返回首次结果 | 正常路径（idempotency_cache 命中） |
| 幂等键复用但业务 payload 不同 | 拒绝 | `IdempotencyConflictError` → `INVALID_REQUEST`（复用 D6-D/ADR-014 request_fingerprint 模式） |
| 跨用户访问 forget_plan / 凭据 | 拒绝 | `INVALID_REQUEST`（Repository 层 user 过滤 + UNIQUE(user_id, plan_id)） |
| `forget_mode` 与 selector 不匹配 / 跨模式 selector | 拒绝 | `INVALID_REQUEST`（模式互斥，SEC-FORGET-03） |
| 凭据与 Preview 快照不一致 / Preview 变化 | 拒绝执行 | `INVALID_REQUEST`（目标快照绑定） |
| SQLITE_BUSY | `DatabaseLockedError` 降级 | FR-DB-003 既有语义 |
| 目标条目不存在 / 精准解析零命中 | 返回 `affected_count=0`（真实结果） | 正常路径，不假装删除 |

---

## 九、测试规划（v0.3 按 Review #99 REWORK 扩充）

### L0
- `python3 -m compileall memory-service/db memory-service/domain memory-service/tests/test_forget_persistence_d10d.py`
- Ruff `--select F,E9`；`git diff --check`

### L1（pytest，WSL2）
| 用例 | 覆盖 |
|---|---|
| forget_plan 落库 + preview 生成凭据（哈希存储 + selection_hash 绑定） | 正向 |
| execute 携带有效凭据 → 软删 + 审计写入同事务；仅消费已确认 resolved_target_ids | 正向 |
| execute 凭据无效/过期/已消费/快照不匹配 → INVALID_REQUEST，零副作用 | 凭据语义 |
| execute 幂等重放 → 返回首次结果，不重复软删 | 幂等 |
| 幂等键复用 + 不同业务 payload → IdempotencyConflictError | 幂等冲突 |
| 跨用户访问他人 forget_plan / 凭据 → INVALID_REQUEST | 隔离 |
| forget_mode 与 selector 互斥（single_item 带 target_session_id 等）→ INVALID_REQUEST | 模式互斥 |
| full_reset 携带 target_* → INVALID_REQUEST；full_reset Preview 全量 + 最高级确认 | full_reset 边界 |
| `affected_count != len(resolved_target_ids)` 不得进入 awaiting_confirmation | Preview 完整性 |
| **executed_count 语义（v0.3/MEDIUM-03）**：`executed_count != affected_count`（漏删 / 部分失败）时不得进入 `completed` | Preview/Execute 一致性 |
| **selector 明文生命周期（v0.3/HIGH-01）**：Preview 完成后 `forget_plan` 中原始 `target_selector` / `target_topic` 已清除或置安全占位；持久层仅存结构化 selector + `selection_hash`；Hard Delete 完成后无明文残留 | 安全 |
| 软删 + FTS 同步（MATCH 不再命中）；Vector/Cache 清理失败不使已删内容重新可见（软删可见性以 SQLite 为准） | 删除一致性 |
| 事务失败（软删 + 审计）→ 整体回滚 | 事务 |
| Outbox priority：forget 事件优先于普通索引任务 | 优先级 |
| 迁移 upgrade/downgrade 往返 + schema 对照 | 迁移 |
| **审计/计划零正文验收（v0.3/HIGH-01 扩展）**：带唯一 Sentinel 的合成敏感正文执行遗忘 → 扫描 **`forget_plan`（含 `target_selector` / `target_topic`）**、`forget_audit` 全部字段（含 reason/details/source_reference/error_message）、**Outbox payload**、服务日志、导出 / 临时输出 → Sentinel 0 命中 | 安全 |
| **Gate 验收**：误删=0（不在确认快照中的对象不受影响）；跨用户 affected_count=0；已报告成功的遗忘目标不重新进入标准检索/MemoryContext/重启后不恢复 | Gate 硬要求 |
| Hard Delete / Cascade / Full Reset 未闭环前执行 → fail-closed（不得自动降级软删后报成功） | 红线 |

### L2（麒麟 VM，人工操作清单，不声称已执行）
- `alembic upgrade head` + `.schema` 对照（forget_plan/forget_audit 表 + 索引 + CHECK）
- 真实 CLI：preview → execute 端到端（uds_client），确认凭据流转 + selection_hash 绑定
- 软删后检索不复现目标正文；`forget_plan` / `forget_audit` / Outbox payload / 导出与临时输出零正文（Sentinel 扫描）
- Outbox 高优先级实测（forget 事件先于积压普通事件消费）
- 对外状态如实标注 `PARTIAL / staged implementation`（完整跨轨 + 真实麒麟验证完成前不写 D10 DONE）

---

## 十、技术债关联

| TD | 处置 |
|---|---|
| TD-D4D-001（Outbox consumer 未接线） | 保持 Open（优先级机制可先行，consumer 接线待 Vector） |
| TD-033（Vector bridge 重编译） | 保持 Open；`has_vector_cleanup` 仅标记，不实现清理 |
| TD-015（ForgetPlan 模式互斥） | 复用 Domain 校验 + 本文件 §三.1 冻结口径，不重复实现 |
| 新增候选 TD-A | **Hard Delete 物理清除 Runtime**：跨轨（B 轨 Vector/FTS5 物理删除、D 事务）闭环前 fail-closed |
| 新增候选 TD-B | **Cascade / Full Reset Runtime 接线**：语义冻结，Execute fail-closed 至确认凭据/审计/Vector 闭环 |
| 新增候选 TD-C | **time_window canonical 时间口径**：待 D/E 书面冻结（业务时间字段/时区/半开区间），实现侧不得自行决定 |
| 新增候选 TD-D | 确认凭据 TTL 参数化（默认 5 分钟） |

---

## 十一、签署与落地流程（v0.3 更新）

1. **本文件（契约规划 v0.3）入库** ← 本 PR：吸收 Reviewer E 冻结回复（APPROVED_WITH_STAGED_RUNTIME）并闭合 Review #99 第一、二轮 REWORK（第一轮 HIGH-01 / MEDIUM-01~04 / 非阻断 2 项；第二轮 MEDIUM-01 / MEDIUM-02 / LOW-1 / LOW-2），作为 ADR-015/019 前置
2. **ADR-015**（forget_plan/forget_audit 表 + outbox priority，FRZ-DB-001 扩展）+ **ADR-019**（forget.preview/forget.execute，FRZ-IPC-007 扩展；编号说明：ADR-016 已由 D7C `preference.*` IPC 契约预留，ADR-017/018 已由 D8-D 关系/冲突持久化契约预留，Forget IPC 顺延至 ADR-019）提交 D 决策
3. Reviewer E（谢嘉然）签署 ADR
4. 回写冻结文档（FRZ-DB-001 / FRZ-IPC-007）
5. 任务卡定稿 → 代码实现（按 F-7 并行：Preview/ID 快照/软删/FTS 退出/最小审计/Outbox/幂等/fail-closed）
6. 实现 + L0/L1 → PR → 麒麟 L2 证据 → 台账 R55 勾选（对外状态 `PARTIAL / staged`，不写 D10 DONE）

---

## 十二、待澄清缺口（v0.3 更新）

1. **time_window canonical 时间口径（F-11）**：Reviewer E 已明确要求 D/E 另行书面冻结——业务时间字段、时区规则、区间开闭（建议 `[start_at, end_at)` 半开区间）；**未冻结前实现侧不得自行决定**。← 下一轮 D/E 补充冻结项
2. **Hard Delete / Cascade / Full Reset 跨轨闭环时序**：依赖 B 轨（Vector 物理删除/重建/残留率，PR #82 工作计划）与 D 轨确认凭据/事务；闭环前 Runtime 保持 fail-closed（不影响软删主路径开发）
3. **Outbox priority 多级取值域**：本版定 0/1/预留 2，建议 ADR-015 一并文档化
4. **回滚（rollback）**：`rollback_plan_id` 语义已冻结（软删恢复/事务补偿/部分执行回滚）；完整回滚事务实现登记 TD-B 不阻塞软删主路径
