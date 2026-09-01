# D10D 实现任务卡：精准遗忘持久化（forget_plan / forget_audit + 确认凭据 + Outbox 高优先级 + 软删主路径 + 最小审计）

| 字段 | 内容 |
|------|------|
| 任务编号 | D10D（台账 R55，精准遗忘持久化） |
| 任务标题 | ① `forget_plan`/`forget_audit` 两表 + 迁移（ADR-007 命名）+ Repository；② 确认凭据（preview/execute 分离，SHA-256 哈希存储，TTL 5 分钟）；③ Outbox 删除高优先级（方案 A：nullable `priority` 列 + 部分索引，worker `ORDER BY priority DESC, next_retry_at ASC`）；④ 幂等（复用 idempotency_cache）+ 最小审计（零正文）；⑤ Soft Delete 主路径（is_deleted=1），Hard Delete / Cascade / Full Reset Runtime fail-closed；⑥ 状态机 `pending → previewing → awaiting_confirmation → executing → completed / failed / rolled_back` |
| 责任轨道 | D（周子腾）；Reviewer：E（谢嘉然） |
| 基线分支 | `feat/d10d-impl`（基于 main @ `ffd20b9`，已切换） |
| 基线 Commit | `ffd20b9` |
| 对照文档版本 | 权威契约 `docs/day10/16_d10d_forget_contract_plan_v0.3.md`（Reviewer E 冻结回复 **APPROVED_WITH_STAGED_RUNTIME** + Review #99 REWORK 全闭合）；ADR-015/016 草案 `docs/day10/17_d10d_adr015_016_draft.md`（本任务前置，签署后实施）；ADR-005/006/007/010/011/013/014；FRZ-IPC-001~007 / FRZ-DB-001~005；技术栈基线 `[02 §2.1]`；VERSION_MAP 真源 |
| 前置 | ADR-015/016 经 D 决策 + Reviewer E 签署（Phase 2 开工条件）；契约 v0.3 已冻结业务语义（§〇~§五），**本任务卡定稿不改变契约** |
| 交付边界 | **遗忘持久化层**（表 + 迁移 + Repository + 事务/令牌语义 + 测试 + outbox 优先级 + gateway 接线 seam）；**不接 Vector 清理**（TD-033，`has_vector_cleanup` 仅标记）；不改 IPC envelope |

---

## 一、契约分析（第 3 步，实现依据，对齐契约 §三~§八）

### 1.1 输入契约（契约 §三）

- 遗忘执行输入 = **E 轨 `ForgetPlan`**（`memory-service/domain/forgetting.py`）+ **确认凭据**（D 轨新增）。
- **persistence 边界（v0.3/第二轮 MEDIUM-01）**：`forget_plan` 持久化行属 **D 轨持久化实体**；`ForgetPlan` 仅用于创建/Preview 前业务输入校验；Preview 清理 selector 后**不要求再次完整反序列化为 E 轨 `ForgetPlan`**；Execute 只消费已确认执行快照 `user_id + forget_plan_id + resolved_target_ids + selection_hash + confirmation state`，**不得重新依赖 selector 做范围解析**。
- 复用约束：不复制 ForgetMode / ForgetPlanStatus / TargetType 枚举（`domain/enums.py` 已存在，七值状态机 v0.2 已冻结），不重建业务校验器（`ForgetPlan._mode_conditional` / `_resolved_target_consistency` 等复用）。

### 1.2 输出契约（execute 成功返回）

`{forget_plan_id, status, affected_count, executed_count, executed_at, audit_id}`；`executed_count != affected_count` 时**不得进入 completed**（v0.3/MEDIUM-03）。

### 1.3 错误语义（契约 §八，复用冻结域，不新增错误码）

全部映射到既有 5 错误码；凭据失败/跨用户/模式互斥/快照不匹配/不支持 Runtime → `INVALID_REQUEST`（safe_message 固定英文，不回显原文）；幂等冲突 → `IdempotencyConflictError` → `INVALID_REQUEST`；SQLITE_BUSY → `DatabaseLockedError`；零命中 → `affected_count=0` 正常路径。

### 1.4 状态机（契约 §三.3，冻结）

`pending → previewing → awaiting_confirmation → executing → completed / failed / rolled_back`；`awaiting_confirmation → executing` 接线前 **fail-closed**。

### 1.5 确认凭据（契约 §五 / F-2 / F-3 / F-14）

- 随机 32B 一次性凭据；服务端只存 SHA-256 哈希（`forget_plan.confirmation_token`）；审计仅存 `confirmation_ref`。
- 绑定 `user_id + forget_plan_id + selection_hash`；TTL 默认 300s（可调，登记 TD-D）；防重放 = 成功事务内置 NULL。
- 幂等 = 复用 FRZ-IPC-005 三元组 + `idempotency_cache`（TTL 24h，ADR-006）；request_fingerprint 对敏感 selector 用固定安全占位 `<SENSITIVE-OMITTED>`（对齐 ADR-014 v5 HIGH-01）。

### 1.6 delete_mode 门禁（契约 §四.9 / F-12 / MEDIUM-04）

`delete_mode` 可信输入由 ADR-016 冻结（可信宿主显式提供，默认 soft）；Repository **不得**按 `target_selector` 推导；LLM 不得终判；hard Runtime 跨轨闭环前 fail-closed。

### 1.7 target_selector 明文生命周期（契约 §四.8 / F-13 / HIGH-01）

原始 `target_selector` / `target_topic` 等仅在计划创建 → Preview 完成间短期存在；进入 `awaiting_confirmation` 后清除或置安全占位（置 NULL 或固定 `<CLEARED>`）；持久层仅存结构化 selector + `selection_hash`；Sentinel 验收覆盖 `forget_plan` / `forget_audit` / Outbox payload / 服务日志 / 导出与临时输出。

---

## 二、允许修改清单（契约 §二「允许修改」）

| # | 文件 | 变更内容 | 状态 |
|---|------|---------|------|
| 1 | `memory-service/db/schema.py` | 新增 `forget_plan` / `forget_audit` 表（ADR-015 DDL 定稿）；`outbox` 只增 nullable `priority` 列 + `idx_outbox_priority` 部分索引 + `aggregate_type` CHECK 值域扩展 `'forget'`（D1 决策后）；既有表定义不动 | 修改 |
| 2 | `memory-service/db/repositories.py` | 新增遗忘 Repository 函数（见 §四 Step 3）；修改 `enqueue_outbox`（可选 `priority` 参数）/ `claim_pending_outbox`（`ORDER BY priority DESC, next_retry_at ASC`） | 修改 |
| 3 | `memory-service/db/uow.py` | 新增 preview/execute 事务封装（复用 `execute_idempotent` 模式；业务写 + 审计 + 凭据消费 + Outbox 入队同事务） | 修改 |
| 4 | `migrations/versions/20260901_add_forget_plan.py` | 新增迁移（ADR-007 命名；down_revision=`20260901_d10b_vector_ledger`，见 §三） | 新增 |
| 5 | `memory-service/domain/forgetting.py` | **如需要**：D 轨持久化辅助（默认不改；若需 `delete_mode` 常量/占位符等，优先放 D 轨实体或复用 `enums.py`；**不新增 `ForgetPlan.delete_mode` 字段**） | 修改（如需） |
| 6 | `memory-service/outbox/worker.py` | Worker 取数顺序改为优先级驱动（消费 `claim_pending_outbox` 新排序，无需其他逻辑改动；短事务单写协调不变） | 修改 |
| 7 | `memory-service/app.py` | **如需要（依赖 ADR-016 签署）**：新增 `--register-forget-handlers` seam（默认不注册 → `UNSUPPORTED_METHOD`，对齐 ADR-010/014 activation 方案 A+B） | 修改（如需） |
| 8 | `memory-service/gateway/forget_handlers.py` | **新增（依赖 ADR-016 签署）**：`forget.preview` / `forget.execute` handler（固定编排顺序见 ADR-016 草案 §4.9）；**不修改**既有 handler 模块 | 新增（如需） |
| 9 | `memory-service/service/forgetting.py` | **新增（Preview 规则引擎 seam）**：scoped 真实解析（single_item / session 确定性解析；topic 复用既有只读检索或 fail-closed；time_window/full_reset fail-closed）；非 Mock、非固定返回 | 新增（如需，D6 决策后） |
| 10 | `memory-service/tests/test_forget_persistence_d10d.py` | 新增 L0/L1 测试（契约 §九 逐项，见 §五） | 新增 |

## 三、禁止修改清单（红线，两个阶段都适用）

- 不修改冻结 FRZ-IPC-001~007 既有字段/错误码/envelope（forget 方法走 ADR-016 新增，未签署前不接线）。
- 不修改 FRZ-DB-001 既有表定义既有列（forget 表为新增；outbox 仅允许本任务卡的只增变更，且须 D1 决策通过）。
- 不修改 `pipeline/`、`providers/`、`security/`、`service/candidate_governance.py`、`gateway/`（既有实现）、`embedding/`、`retrieval/`、`observability/` 既有实现。
- **不接 Vector 清理**（TD-033 未完成；`has_vector_cleanup` 仅承载标记，不实现清理）。
- **不实现硬删除物理清除**（语义冻结；Runtime Execute fail-closed，物理清除登记 TD 待跨轨闭环）。
- **不实现 Cascade / Full Reset Runtime**（语义冻结；Execute fail-closed）。
- **不实现 time_window canonical**（F-11 DEFERRED，待 D/E 书面冻结；实现侧不得自行决定）。
- **不实现回滚事务完整逻辑**（`rollback_plan_id` 仅承载语义）。
- 日志 sanitize_message；不记录 selector 明文/正文/PII；不出现任何密钥。
- 不把 Mock/固定返回当生产功能；降级只返回真实结果或空上下文。
- 不把 WSL 结果当宿主证据；L2 项只列待验证清单。
- **不 push、不创建 PR**（orchestrator 审查后处理）。

---

## 四、分步实施计划（Step 1..N，每步可独立验证）

### Step 1：Schema + 迁移（D1 决策后）

- `db/schema.py`：新增 `forget_plan` / `forget_audit`（ADR-015 DDL 定稿版，含全部 CHECK）；`outbox` 加 nullable `priority`（默认 0）+ `idx_outbox_priority` 部分索引 + `aggregate_type` CHECK 值域扩展（D1）。
- `migrations/versions/20260901_add_forget_plan.py`：upgrade = CREATE 2 表 + 索引 + outbox 加列/部分索引（`IF NOT EXISTS` 幂等）；downgrade = DROP 2 表 + outbox 变更对称回滚（D1：重建需保留数据）。
- **验证**：`alembic -c migrations/alembic.ini heads` 输出**单一 head = `20260901_add_forget_plan`**；`alembic upgrade head` → `.schema` 断言（两表 + 索引 + CHECK 存在）→ `downgrade base` 往返；`python3 -m compileall migrations/versions`。

### Step 2：D 轨辅助与持久化实体（如需）

- 如需 `delete_mode` 常量 / 安全占位 `<CLEARED>` / `<SENSITIVE-OMITTED>` / 凭据 TTL 参数，落在 D 轨实体或 `enums.py`；**不改 E 轨 `ForgetPlan`**（不新增 `delete_mode` 字段，不放松 `extra="forbid"`）。
- 确认持久化行反序列化边界：清理后行不回读成 `ForgetPlan`（D 轨专用读取函数）。
- **验证**：既有 Domain 测试全绿（`test_domain_models_d4e.py` / `test_forgetting_policy_d10e.py`）。

### Step 3：Repository 层

新增（`db/repositories.py`）：
- `insert_forget_plan`（含 user_id 隔离；`status='pending'`）
- `get_forget_plan_by_id(conn, *, user_id, forget_plan_id)`（**user 强制过滤**，跨用户返回 None）
- `update_forget_plan_preview`（写 resolved_target_ids / affected_count / selection_hash / confirmation_token(SHA-256) / token_expires_at / 清除 target_selector+target_topic 明文 / 置安全占位 / status→awaiting_confirmation）
- `consume_confirmation_token`（校验绑定 + 过期 + 未消费；消费 = confirmation_token 置 NULL；同事务执行）
- `update_forget_plan_terminal`（executing→completed/failed/rolled_back；写 executed_count / executed_at；`executed_count != affected_count` 时禁止 completed）
- `insert_forget_audit`（零正文字段集；terminal 必填 executed_at）
- 软删执行器 `soft_delete_resolved_targets`（见 Step 5 dispatcher）
- `enqueue_outbox` 加 `priority` 可选参数（默认 0）；`claim_pending_outbox` 改 `ORDER BY priority DESC, next_retry_at ASC`
- 规则引擎 seam 调用的 scoped 查询（single_item/session 确定性解析，user 限定）
- **验证**：L1 Repository 契约测试（§五 A/B/C 组）。

### Step 4：UoW 事务封装

`db/uow.py` 新增：
- `preview_forget_plan(...)`：`execute_idempotent` 单事务（落计划 + 凭据哈希 + selector 清理 + response cache）；request_fingerprint 敏感占位。
- `execute_forget_plan(...)`：`execute_idempotent` 单事务（凭据校验绑定/过期/消费 → 软删 dispatcher → executed_count → 凭据置 NULL → 审计写入 → 终态；`executed_count != affected_count` → 不 completed → failed/rolled_back）。
- 事务失败 → 整体回滚，凭据保留可重试（或按 TTL 失效）→ 映射 INVALID_REQUEST（契约 §五.4）。
- **验证**：L1 事务/凭据/幂等用例（§五 B/D 组）。

### Step 5：软删主路径 + fail-closed dispatcher

- 主路径：对已确认 `resolved_target_ids`，按目标类别 dispatch 到**既有权威软删状态**：
  - `knowledge` → `memory_entries.is_deleted=1`（复用 `soft_delete_memory_entry` 乐观锁；FTS 由既有触发器同步移除）；
  - `preference` → D7D `memory_status='removed'` 机制（复用既有 Repository 语义）；
  - `event`（source_events）→ **无 is_deleted 列且消费者在 `pipeline/`（红线不可改）→ Runtime fail-closed**（D2 决策后落地；未闭环前 execute 对 event 目标 fail-closed，`executed_count` 反映真实处理数，不进入 completed 的假完成）。
- fail-closed 清单：`delete_mode=hard` / `is_cascade=true` 级联扩展 / `full_reset` / `time_window` → 一律拒绝执行（INVALID_REQUEST），**不自动降级软删后报成功**。
- `has_vector_cleanup` 仅标记（TD-033），不实现清理。
- **验证**：L1 软删+FTS / fail-closed / Gate 误删用例（§五 E/F 组）。

### Step 6：Outbox 高优先级接线（契约 §六）

- worker 轮询消费 `claim_pending_outbox` 新排序（priority DESC → next_retry_at ASC）；`forget.*` 事件 `priority=1`。
- `aggregate_type` CHECK 扩展后允许 `aggregate_type='forget'` 入队（D1）。
- **验证**：L1 Outbox priority 用例（§五 D 组）：堆积普通任务 + 后入 forget 事件 → 优先消费 forget。

### Step 7（依赖 ADR-016 签署）：Gateway seam + app.py 接线

- `gateway/forget_handlers.py` 新增 `forget.preview` / `forget.execute`（固定编排顺序，ADR-016 草案 §4.9；trusted identity precheck 先于幂等查找）。
- `app.py` 新增 `--register-forget-handlers`（默认不注册 → `UNSUPPORTED_METHOD`）；production 禁止注册。
- **验证**：L1 Gateway 端到端（uds_client preview→execute）+ 未注册时 UNSUPPORTED_METHOD（§五 G 组）。

### Step 8：自检 + 报告

- L0（§五 L0）+ 全量 L1 通过；`git diff --check`。
- 按 skill 输出格式出开发报告；L2 只列人工操作清单，不声称已执行。

---

## 五、迁移链处理（契约 §四.3，MEDIUM-02；本分支实跑记录）

> **真实 Alembic head 确认（2026-09-01，`feat/d10d-impl` @ `ffd20b9`）**：

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
- **结论**：PR #98（D6-D `20260831_add_source_events`）已并入 main 链（合并提交 `79411f1`）；契约 v0.3 的「未合并」判断已过时。
- 新迁移：`revision = "20260901_add_forget_plan"`，`down_revision = "20260901_d10b_vector_ledger"`；追加后链为 `... → 20260901_d10b_vector_ledger → 20260901_add_forget_plan (head)`。
- **禁止多 head**：实施 PR 创建时再次执行 `alembic heads` 确认真实链与单 head。

---

## 六、L1 测试清单（契约 §九 表逐项）

| # | 用例 | 契约 §九 覆盖 | 对应 Step |
|---|------|--------------|----------|
| 1 | forget_plan 落库 + preview 生成凭据（哈希存储 + selection_hash 绑定） | 正向 | S1/S3/S4 |
| 2 | execute 有效凭据 → 软删 + 审计写入同事务；仅消费已确认 resolved_target_ids | 正向 | S4/S5 |
| 3 | execute 凭据无效/过期/已消费/快照不匹配 → INVALID_REQUEST，零副作用 | 凭据语义 | S3/S4 |
| 4 | execute 幂等重放 → 返回首次结果，不重复软删 | 幂等 | S4 |
| 5 | 幂等键复用 + 不同业务 payload → IdempotencyConflictError | 幂等冲突 | S4 |
| 6 | 跨用户访问他人 forget_plan / 凭据 → INVALID_REQUEST | 隔离 | S3/S4 |
| 7 | forget_mode 与 selector 互斥（single_item 带 target_session_id 等）→ INVALID_REQUEST | 模式互斥 | S1/S4（Domain 复用） |
| 8 | full_reset 携带 target_* → INVALID_REQUEST；full_reset Preview 全量 + 最高级确认 | full_reset 边界 | S4/S5 |
| 9 | `affected_count != len(resolved_target_ids)` 不得进入 awaiting_confirmation | Preview 完整性 | S3/S4 |
| 10 | **executed_count 语义（MEDIUM-03）**：`executed_count != affected_count`（漏删/部分失败）不得进入 completed | Preview/Execute 一致性 | S4/S5 |
| 11 | **selector 明文生命周期（HIGH-01）**：Preview 完成后 `forget_plan` 原始 target_selector/target_topic 已清除/置安全占位；持久层仅存结构化 selector + selection_hash | 安全 | S3 |
| 12 | 软删 + FTS 同步（MATCH 不再命中）；Vector/Cache 清理失败不使已删内容重新可见（软删可见性以 SQLite 为准） | 删除一致性 | S5 |
| 13 | 事务失败（软删 + 审计）→ 整体回滚 | 事务 | S4 |
| 14 | Outbox priority：forget 事件优先于普通索引任务 | 优先级 | S6 |
| 15 | 迁移 upgrade/downgrade 往返 + schema 对照（含单 head 断言） | 迁移 | S1 |
| 16 | **审计/计划零正文验收（HIGH-01 扩展）**：唯一 Sentinel 合成敏感正文执行遗忘 → 扫描 forget_plan（含 target_selector/target_topic）、forget_audit 全部字段（含 reason/details/source_reference/error_message）、Outbox payload、服务日志、导出/临时输出 → Sentinel 0 命中 | 安全 | S3/S4/S6 |
| 17 | **Gate 验收**：误删=0（不在确认快照中的对象不受影响）；跨用户 affected_count=0；已报告成功的遗忘目标不重新进入标准检索/MemoryContext/重启后不恢复 | Gate 硬要求 | S5 |
| 18 | Hard Delete / Cascade / Full Reset 未闭环前执行 → fail-closed（不得自动降级软删后报成功） | 红线 | S5 |
| 19 | **request_fingerprint 敏感占位**：preview 携带敏感 selector 时 idempotency_cache 不落敏感派生 hash（`<SENSITIVE-OMITTED>`） | 安全（ADR-014 v5 对齐） | S4 |
| 20 | **trusted identity cache-bypass**：身份不匹配不得被 cache replay 绕过（ADR-016 seam 场景） | 隔离（ADR-014 v5 对齐） | S7 |

### L0（契约 §九 L0）

- `python3 -m compileall memory-service/db memory-service/domain memory-service/tests/test_forget_persistence_d10d.py`
- `ruff check --select F,E9 memory-service/db memory-service/domain memory-service/outbox memory-service/tests/test_forget_persistence_d10d.py`（如项目 ruff 配置）
- `git diff --check`
- `alembic -c migrations/alembic.ini heads`（单 head 断言）

### L2（麒麟 VM，人工操作清单，不声称已执行）

- `alembic upgrade head` + `.schema` 对照（forget_plan / forget_audit 表 + 索引 + CHECK）
- 真实 CLI（uds_client）：preview → execute 端到端，确认凭据流转 + selection_hash 绑定
- 软删后检索不复现目标正文；forget_plan / forget_audit / Outbox payload / 导出与临时输出零正文（Sentinel 扫描）
- Outbox 高优先级实测（forget 事件先于积压普通事件消费）
- 对外状态如实标注 `PARTIAL / staged implementation`

---

## 七、安全边界（契约 §四/§五/§八 + `[02 §16.6]`）

- 跨用户隔离：Repository 层所有查询强制 `user_id` 过滤 + `UNIQUE(user_id, forget_plan_id)` 双重限制；跨用户访问凭据/计划 → INVALID_REQUEST。
- 原文隔离：selector 明文生命周期（HIGH-01）；审计零正文；日志 sanitize_message；凭据只存 SHA-256 哈希；request_fingerprint 敏感占位（对齐 ADR-014 v5）。
- 写入边界 + 检索输出边界双重实现；误删=0、漏删不报完成。

## 八、交付物

- 修改：`db/schema.py`、`db/repositories.py`、`db/uow.py`、`outbox/worker.py`、`migrations/versions/20260901_add_forget_plan.py`（新增）、`tests/test_forget_persistence_d10d.py`（新增）、（如需）`domain/forgetting.py`、`service/forgetting.py`、`gateway/forget_handlers.py`、`app.py`。
- 文档：本任务卡 + ADR-015/016 草案 + Plan 摘要（17_/19_）。
- 禁止：push、创建 PR（orchestrator 审查后处理）。

## 九、验收标准

- L0 全绿 + L1（§六 20 项）全通过（含失败路径/幂等/并发/边界，禁止删测试换取通过）。
- 迁移单 head；`.schema` 与 ADR-015 DDL 逐列一致；upgrade/downgrade 往返通过。
- 契约零偏离：FRZ-IPC/FRZ-DB 既有条目不动；forget 表走 ADR-015/016。
- 无假实现：preview resolver 真实 scoped 解析；fail-closed 不降级报成功；TODO/FIXME 引用 TD 编号。
- 开发报告按输出格式（修改清单/契约变化/设计说明/测试结果/待 L2 项/技术债/风险与回滚）。

## 十、技术债关联（契约 §十）

| TD | 处置 |
|---|---|
| TD-D4D-001（Outbox consumer 未接线） | 保持 Open；优先级机制先行，consumer 接线待 Vector |
| TD-033（Vector bridge 重编译） | 保持 Open；`has_vector_cleanup` 仅标记 |
| TD-015（ForgetPlan 模式互斥） | 复用 Domain 校验 + 契约 §三.1 口径，不重复实现 |
| TD-A（Hard Delete 物理清除 Runtime） | 登记；跨轨闭环前 fail-closed |
| TD-B（Cascade / Full Reset Runtime 接线） | 登记；语义冻结，Execute fail-closed |
| TD-C（time_window canonical 时间口径） | 登记；待 D/E 书面冻结 |
| TD-D（确认凭据 TTL 参数化，默认 5 分钟） | 登记；默认硬编码，参数化不阻塞 |
| TD-E（event 目标软删，D2 决策前 fail-closed） | 新增候选；source_events 无 is_deleted，staged |

---
*任务卡编制：opencode（D 轨，Phase 1 / Plan，2026-09-01）｜依据契约 v0.3 + ADR-015/016 草案；红线遵守，无 push、无 PR。*
