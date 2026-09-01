# ADR-013：新增 `source_events` 表持久化多源事件（FRZ-DB-001 / D6-D 扩展）

- **状态**：✅ D 已决策（2026-08-31，方案 A）；REWORK 修订 v5（按 Review #83 Reviewer E 第五轮意见重冻结）；待 Reviewer E 签署
- **日期**：2026-08-31（v5 修订同日）
- **决策人**：周子腾（D）｜**Reviewer**：E（谢嘉然，待签）
- **责任轨道**：D（DB）为主，A/E 协作（消费现有 pipeline / admission 模型，不复制真源）
- **决策版本**：`source-events-table-v5`
- **适用范围**：FRZ-DB-001 表定义扩展；关联 `docs/day6/day6-d-01-event-persistence-contract-plan-v0.5.md`、`memory-service/pipeline/schemas.py`（MemorySourceEvent / NormalizedEvent）、`memory-service/security/source_admission.py`（SourceAdmissionResult）、`memory-service/pipeline/fingerprint.py`、ADR-007（迁移命名）、ADR-011（扩展先例）、ADR-014（event.ingest 路由）、FRZ-IPC-005、FRZ-DB-004（Dead Letter 策略）

> **v2 修订摘要（Review #83 REWORK 第一轮处置）**：① 敏感命中事件 content_summary/raw_payload_ref 强制 NULL；② event_id 唯一键改全局 `UNIQUE(event_id)` 对齐 D3 冻结语义；③ 指纹去重改为"保留事件 + 标记去重"（新增 dedup_group/duplicate_of 列）；④ 补齐 NormalizedEvent 投影列（含 requires_embedding/has_structured_payload/language_tag）+ 2 去重标记列 = **35 列**（组成口径以 DDL 实际列清单为准）；⑤ consent_scope=none 由 D 轨 handler 前置 REJECT（不依赖 E 轨）；⑥ processing_status 不写 `extracted`（如实停在 `extracting`）；⑦ ADR 编号从 012 重排为 013。

> **v3 修订摘要（Review #83 Reviewer E 第三轮意见处置）**：① event_id 冲突处置改为「immutable identity 一致 = 幂等重放（返回首次持久化 admission 结果）/ 不一致 = `EventIdentityConflict` → INVALID_REQUEST」，删除「跨 session 复用一律 EventOwnershipError」与「同 event_id 一律返回既有记录」的冲突口径（HIGH-01）；② processing_status 首次落库一律 `pending`，REJECT/AUDIT_ONLY/指纹重复事件不落 `extracting`（admission_decision 为正交字段），杜绝永久「抽取处理中」假状态（MEDIUM-01）；③ `dedup_group` 增加 user scope（组键含 `user_id`，索引改 `(user_id, dedup_group)` 复合）（MEDIUM-05）；④ 敏感摘要清空规则收紧为「仅敏感/安全类强制 NULL」，普通质量型 AUDIT_ONLY 保留已脱敏摘要（MEDIUM-07）。

> **v4 修订摘要（Review #83 Reviewer E 第四轮意见处置）**：① immutable event identity **重定义**为独立稳定字段集 + 派生 `event_identity_fingerprint`——**禁止复用现有 `content_fingerprint`**（其无正文时 fallback 到 `event_id+idempotency_key+session_id`，会把请求级幂等键/会话间接塞回事件身份）；冻结 `user_id + actor_id + source_type + event_type + occurred_at(UTC 规范化) + event_content_identity(正文存在性稳定内容身份)`，**不包含 `idempotency_key` / `session_id`**，正文有无不影响组成（HIGH-01）；② **敏感/security reject/consent reject 事件持久化 `content_fingerprint = NULL`**——普通确定性 SHA-256 对低熵敏感值可离线枚举，不等价于不可恢复脱敏；未授权/敏感事件不参与内容级指纹去重（HIGH-03）；③ 事件碰撞处置固定顺序统一为「schema precheck → Pipeline 纯计算（normalization/fingerprint，无副作用）→ event identity compare → replay 跳过 consent/admission/persistence」（MEDIUM-01）；④ `processing_status='pending'` 消费资格谓词冻结：仅 `pending + admission_decision='allow_extraction' + duplicate_of IS NULL` 可进抽取调度（MEDIUM-02）；⑤ 跨用户 event_id `IntegrityError` fail-close 回查路径明确：不回读/不返回其他用户旧事件（MEDIUM-03）；⑥ dedup head 查找与插入同 **UoW / 单写锁 / 事务** 原子绑定（MEDIUM-04）。

> **v5 修订摘要（Review #83 Reviewer E 第五轮意见处置，HIGH-01 协调）**：① **固定顺序重排（与 ADR-014 v5 严格一致）**——`payload 结构预检 → trusted identity precheck（先于任何 user-scoped idempotency_cache lookup，cache-bypass 防护）→ EventPipeline.process(raw) 纯计算（仅一次，无 DB 副作用，是 request_fingerprint 的唯一敏感判定真源）→ privacy-safe request_fingerprint（sensitive/security reject/consent reject 事件内容身份取固定安全占位 `<SENSITIVE-OMITTED>`）→ UoW.execute_idempotent 单事务（business_fn：event identity compare → consent → admission → dedup → source_event 落库 → response cache）`；② **敏感 hash 旁路防护**——除 `source_events.content_fingerprint` 置 NULL（HIGH-03）外，敏感低熵内容**不得经 `idempotency_cache._request_fingerprint` 派生落盘**（ADR-014 v5 privacy-safe 占位规则），正文/摘要/内容指纹/请求指纹四路均不持久化敏感派生值；③ cache replay 允许纯计算 pipeline、禁止重复业务副作用（与 ADR-014 v5 对齐）；④ 补充 L1 用例：高敏 request_fingerprint 安全占位 + trusted identity cache-bypass（见 ADR-014 评测影响）。

---

## 背景

1. **D6-D（台账 R35）任务**：「持久化 SourceEvent、授权、指纹和幂等键」——多源事件（ToolExecutionEvent、行为事件、ManualConfigEvent、完整聊天回合）需形成**可溯源、可审计、可去重**的结构化真源。
2. **FRZ-DB-001 冻结 5 张核心表**（`D4_DB_INITIAL_DESIGN_FREEZE_20260817.md:26`）：`conversations / turns / memory_entries / outbox / idempotency_cache`；**无事件持久化表**。事件目前仅存在于 A 轨 `EventPipeline` 内存管道，未落库 → 无法按用户/时间线审计、无法持久化去重、无法承载准入决策留痕。
3. **A 轨/E 轨已有可信模型**（复用约束）：`NormalizedEvent`（清洗后事件，含 `content_fingerprint`）、`QualityScore`、`SourceAdmissionResult`（`decision / reason_code`）——本 ADR 只落库消费，**不复制/不重建**这些真源模型。
4. **原文隔离红线**（`[02 §4.1]`）：事件正文/敏感载荷**不落库**；只落脱敏 `content_summary` + 受控引用（`source_reference` / `raw_payload_ref`）。
5. **outbox 边界**：`outbox.aggregate_type CHECK IN ('turn','memory')` 为冻结约束（FRZ-DB-001）；本版**不扩展、不接线**（事件索引任务/consumer 属 D9-D 与 TD-D4D-001 接线范围；`source_events` 独立事务，见「事务边界」）。
6. **指纹窗口性能红线**（D 确认 2026-08-31）：指纹检索仅在**索引点查**（O(logN+k)）实现；若实测写路径开销超标，配置开关 `dedup.fingerprint_window_hours=0` 关闭，退化为仅 event_id 幂等。**指纹去重语义为"保留事件 + 标记去重"，不跳过插入**（见「幂等与重复检测」）。

---

## 候选方案

### 方案 A：新增 `source_events` 表（本 ADR 决策）

新增第 6 张表，落库事件元数据 + 授权 + 指纹 + 幂等键 + 准入决策；迁移 `20260831_add_source_events.py`；`db/schema.py` 同步单一真相。

优点：

- 事件形成**独立结构化真源**，可审计/可溯源/可持久化去重；
- 与 ADR-011 先例一致（FRZ-DB-001 扩展走 ADR + Gate，既有表/索引/触发器/FTS5 不动）；
- 为 D6-C 统一事件入口、D9-D Outbox 索引任务、D10-D 遗忘审计提供落库基座。

缺点：

- 冻结契约新增表，须走 ADR + D/E 签署流程。

### 方案 B：仅 outbox 承载事件（不新增表）

事件只写入 `outbox.payload` JSON，消费后即完成使命。

- **不满足验收**：台账要求「持久化 SourceEvent、授权、指纹、幂等键」为**结构化真源**；outbox 是待消费队列，消费/清理后事件不可回溯，审计与去重失效；
- 与 FRZ-DB-004「Outbox 为索引任务队列」语义冲突。
- **结论**：否决。

### 方案 C：泛化 `memory_entries` 承载事件

把事件作为 `entry_type='source_event'` 写入 memory_entries。

- **污染业务记忆表**：memory_entries 是偏好/知识/行为记忆正文表（含 FTS5 索引），事件日志混入会污染检索与抽取语义；
- 违背「事件源 → 清洗 → 记忆」分层。
- **结论**：否决。

---

## 决策

选择方案 A：`source-events-table-v5`。**新增 `source_events` 表（35 字段 + 5 索引，含去重自关联列），经迁移 `20260831_add_source_events.py` 落地；`db/schema.py` 同步为单一真相；不修改既有 5 张表/索引/触发器/FTS5；不扩展 `outbox` CHECK 约束；事件落库与既有业务写链路互不耦合。**（v5 协调：与 ADR-014 v5 同固定顺序；敏感保留字 hash 旁路防护见「授权与安全」。）

### DDL 定义（草案）

```sql
CREATE TABLE source_events (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                  TEXT    NOT NULL,                -- 隔离键，禁止正文推断
    event_id                 TEXT    NOT NULL,                -- 事件级全局唯一键（宿主生成）
    actor_id                 TEXT    NOT NULL,
    session_id               TEXT    NOT NULL,
    turn_id                  TEXT,
    tool_call_id             TEXT,
    source_type              TEXT    NOT NULL,                -- 七值枚举（pipeline.schemas）
    event_type               TEXT    NOT NULL,                -- 三值枚举
    schema_version           TEXT    NOT NULL,
    trace_id                 TEXT,
    source_reference         TEXT,                            -- 受控引用，非正文
    raw_payload_ref          TEXT,                            -- 受控引用，非正文（敏感/安全类强制 NULL）
    content_summary          TEXT,                            -- 脱敏摘要，非原文（敏感/安全类强制 NULL）
    idempotency_key          TEXT    NOT NULL,
    consent_scope            TEXT    NOT NULL,                -- 授权字段
    source_business_status   TEXT    NOT NULL,                -- 八值
    sensitivity              TEXT    NOT NULL,                -- 五级
    is_sensitive_matched     INTEGER NOT NULL DEFAULT 0,
    should_ignore            INTEGER NOT NULL DEFAULT 0,
    payload_security_checked INTEGER NOT NULL DEFAULT 0,
    memory_type              TEXT,
    requires_embedding       INTEGER NOT NULL DEFAULT 1,      -- NormalizedEvent 原样投影
    has_structured_payload   INTEGER NOT NULL DEFAULT 0,      -- NormalizedEvent 原样投影
    language_tag             TEXT,                            -- NormalizedEvent 原样投影
    occurred_at              TEXT    NOT NULL,                -- aware UTC ISO8601（identity 组成，须规范化）
    captured_at              TEXT    NOT NULL,                -- aware UTC ISO8601
    content_fingerprint      TEXT,                            -- 重复检测（脆弱不确定：无正文时 fallback 含 idempotency_key/session_id；敏感/未授权事件持久化 NULL，HIGH-03）
    dedup_group              TEXT,                            -- 指纹去重组（含 user scope：dedup:<user_id>:<fp>:<source_type>；敏感事件随 content_fingerprint=NULL 不分组）
    duplicate_of             INTEGER,                         -- 指向首次同指纹事件 id（自关联 NULL 表示首次；软引用，无 FK 约束）
    admission_decision       TEXT    NOT NULL,                -- allow_extraction/audit_only/reject
    admission_reason_code    TEXT    NOT NULL,                -- 稳定 reason code
    processing_status        TEXT    NOT NULL DEFAULT 'pending',
    created_at               TEXT    NOT NULL,
    updated_at               TEXT    NOT NULL,
    CHECK (consent_scope IN ('memory_only','memory_and_analytics','none')),
    CHECK (source_business_status IN ('raw','completed','success','partial','failed','cancelled','timeout','ignored')),
    CHECK (sensitivity IN ('none','low','medium','high','critical')),
    CHECK (admission_decision IN ('allow_extraction','audit_only','reject')),
    CHECK (processing_status IN ('pending','extracting','extracted','embedded','stored'))
);
```

### 索引（草案）

| 索引 | 定义 | 用途 |
|---|---|---|
| `uq_source_events_event` | **UNIQUE(event_id)** | 事件级幂等 + 全局唯一（D3 冻结语义，[02 附录]） |
| `idx_source_events_user_created` | (user_id, created_at) | 按用户时间线查询/审计 |
| `idx_source_events_fingerprint` | (user_id, content_fingerprint) | 指纹重复检索（索引点查） |
| `idx_source_events_dedup_group` | (user_id, dedup_group) | 去重组查询（**含 user scope**，D9-D 抽取跳过；Review #83 第三轮 MEDIUM-05） |
| `idx_source_events_status` | (user_id, processing_status) | 处理状态扫描（D9-D 预留） |

### 迁移

- 文件：`migrations/versions/20260831_add_source_events.py`
- **命名**：`YYYYMMDD_<description>.py`（ADR-007 红线）
- **revision**：`revision = "20260831_add_source_events"`，`down_revision = "20260826_add_trace_id"`（版本链 `001_initial_schema → 20260826_add_trace_id → 20260831_add_source_events`）
- **upgrade**：CREATE TABLE + 5 索引（`IF NOT EXISTS` 幂等，与 init_schema 契约一致）
- **downgrade**：DROP TABLE（新表无既有数据依赖，可整表回滚；无列删除红线问题）

### 幂等与重复检测

- **事件级硬幂等（全局唯一）**：`UNIQUE(event_id)`（D3 冻结语义，全局唯一）为 DB 约束兜底；本版按「**immutable identity** 一致性」区分两种语义（Review #83 第三轮 HIGH-01 基线 + **第四轮 HIGH-01 重定义**）：
  - **幂等重放（idempotent replay）**：同 `event_id` 且 **immutable identity 完全一致** → 视为同一事件重放，不形成新的事件事实，**返回首次持久化记录的完整结果**（含既有 `source_event_id` / `admission_decision` / `admission_reason_code` / `duplicate=true`），不重复执行 consent/admission/落库，也**不返回新请求重新计算的结果**——避免「Response 指向旧 SQLite 行但准入结果属于新请求」的持久化真源不一致；
  - **identity collision**：同 `event_id` 但 **immutable identity 不一致** → 抛 `EventIdentityConflict`（handler 转 `INVALID_REQUEST`，不回显标识）；**不得**把第二次请求当普通 duplicate 返回旧行。
  - **immutable identity 定义（v4 重定义，独立稳定字段集 + 派生指纹；Review #83 第四轮 HIGH-01）**：
    - **字段集（不可变、跨生命周期稳定）**：
      1. `user_id`（隔离键，禁止正文推断）；
      2. `actor_id`（同 user 下可多 actor，**属于 identity**——同 event_id 换 actor 不得判为 replay，弥补 v3 缺 actor 的间隙）；
      3. `source_type`；
      4. `event_type`；
      5. `occurred_at`（**统一 canonicalization**：aware UTC ISO8601 毫秒，比对时规范化后比较）；
      6. **`event_content_identity`**：稳定内容身份 —— 取**归一化 `content_summary`**（不存在则取**归一化 `raw_payload_ref`**；两者皆无 → 固定空占位 `<no-content>`，**使定义不受"正文有无"影响**）。**敏感/security reject/consent reject 事件因正文强制 NULL（见「授权与安全」HIGH-03），其 content 不参与 identity 比对**（此类事件 identity = 前 5 项非内容字段；文档显式标注该简并）。
    - **明确排除**：`idempotency_key`、`session_id`、`trace_id`、`content_fingerprint`（现有 `fingerprint.py` 无正文时 fallback 到 `event_id+idempotency_key+session_id`，**属请求级/会话级污染，禁止复用为事件身份**）。
    - **派生 `event_identity_fingerprint`**（比较用，**本版不新增存储列**，DDL 保持 35 列）：= `SHA256(规范化拼接 上述适用 identity 字段)`，handler 在比较时计算两侧以做确定性比对（避免逐列字符串比较的规范化差异）。
  - **实现顺序（固定，统一 ADR-013/ADR-014 v5，MEDIUM-01 + HIGH-01 v5 协调）**：`payload 结构预检` → **`trusted identity precheck`（先于任何 user-scoped idempotency_cache lookup，cache-bypass 防护，见 ADR-014 v5 Handler 步骤 2）** → `EventPipeline.process(raw)` **纯计算**（normalization + fingerprint，**无 DB 副作用**；是 request_fingerprint 的唯一敏感判定真源）→ `privacy-safe request_fingerprint`（sensitive/security reject/consent reject 事件内容身份取固定安全占位 `<SENSITIVE-OMITTED>`，见 ADR-014 v5）→ `UoW.execute_idempotent(...)` 单事务（`business_fn` 内：event identity compare → consent 前置 → admission → dedup → source_event 落库 → response cache）。replay 允许重跑一次性无副作用 pipeline 用于 identity 比对，但不得重跑准入与写入副作用（同一 UoW 内）。**不再采用「先点查既有行再决定是否跑 pipeline」的旧表述**——immutable identity 的 `event_content_identity/occurred_at` 须 pipeline 规范化后方可比较。
  - **跨用户 event_id IntegrityError fail-close 回查（MEDIUM-03）**：`get_source_event_by_event_id` 按 `user_id` 限定回查——1) 当前 user 下查得 → 同用户并发，走正常 identity compare；2) 当前 user 下查不到，但 `INSERT` 触发 `UNIQUE(event_id)` IntegrityError → 判定「event_id 已被其他 ownership 占用」→ **直接 `EventIdentityConflict` → INVALID_REQUEST**；**不回查、不读取、不返回其他用户旧事件内容**（保持跨用户读取边界，`[02 §16.6]`）。
- **请求级幂等**：FRZ-IPC-005 三元组 `(user_id, session_id, idempotency_key)` 走既有 `idempotency_cache`（ADR-006），由 `event.ingest` handler 层执行（见 ADR-014 §幂等）；**事件级 `event_id` identity 与请求级幂等为两层正交语义**——同一 `idempotency_key` 携带不同业务 payload 属 **请求指纹冲突**（`IdempotencyConflictError`，见 ADR-014），与 `event_id` identity collision 分开处置；`event_id` **不替代** `idempotency_key`。
- **指纹去重（保留事件 + 标记；MEDIUM-04 原子性）**：同 `user_id` + 同 `content_fingerprint` + 同 `source_type` 且 `captured_at >= now - 24h` → **仍插入新事件行**（event_id 必不相同），但标记：
  - `duplicate_of` = 首次同指纹事件 id（无则 NULL）
  - `dedup_group` = 首次同指纹事件聚合键，**含 user scope**：`dedup:<user_id>:<content_fingerprint>:<source_type>`（Review #83 第三轮 MEDIUM-05：防止跨用户 events 落入同一 dedup_group 被 D9-D consumer 误判「同组仅首条提取」）；同组仅首个事件可进抽取（`skip_extraction` 语义由 D9-D 消费 `dedup_group` 实现，本版只落库标记不消费）
  - **`find_dedup_group_head` + `insert_source_event` 必须在同一 `UnitOfWork / 进程级单写锁 / 事务` 内执行**（MEDIUM-04）：两个同指纹不同 event_id 的并发请求若分开两步，可能同时查到 `head=None` 并各自 `duplicate_of=NULL`，产生两个"组首事件"；同一写锁 + 事务内串行化保证仅一行 `duplicate_of IS NULL`
  - 事件时间线、审计、行为频次、隐式偏好信号**不被丢弃**
  - 实现：`idx_source_events_fingerprint` 索引点查 + 时间过滤（O(logN+k)，非全表扫描、无内存集合、无外部服务）确定同组首行
  - **敏感/security reject/consent reject 事件**：`content_fingerprint` 持久化 **NULL**（HIGH-03，见「授权与安全」），**不参与**指纹去重/分组
  - **性能红线（D 确认）**：若 L1/L2 实测写路径开销超标 → 配置 `dedup.fingerprint_window_hours=0` 关闭窗口，退化为仅 event_id 幂等（不做指纹分组标记）；开关在 `config.py` 冻结 8 键之外**新增可选键**（走 FRZ-CFG-001 扩展；参数化登记 **TD-D6D-001**，见「变更控制」与新候选账项）

### 授权与安全

- `consent_scope` 随事件落库（授权字段）；`consent_scope=none` 由 D 轨 `event.ingest` handler **前置 REJECT**（`consent_not_granted`，见 ADR-014 §编排），本层持久化决策结果；**不依赖 E 轨 SourceAdmissionPolicy 判断**（其当前无 consent 分支）
- **敏感命中强制 NULL**（`[02 §4.1]` 原文隔离，Review #83 BLOCKER 回归项）：仅以下**敏感/安全类**事件落库时 `content_summary` / `raw_payload_ref` **必须为 NULL**（或安全占位 `<redacted>` 走 content_summary，禁止原始字符串）：
  - `is_sensitive_matched = true`；
  - `sensitivity = high / critical`；
  - `admission_decision = reject`（security / consent 类 reject）；
  - `consent_scope = none`（D 轨前置 REJECT）。
  - **普通质量型 AUDIT_ONLY**（如 `quality_not_eligible`）**不强制清空**：若 `content_summary` 已通过安全边界确认（脱敏摘要、非原文），允许保留，避免损失 SourceEvent 审计价值（Review #83 第三轮 MEDIUM-07）。**本版禁止任何「敏感事件仍写原始摘要」的降级路径。**
- **敏感/security reject/consent reject 事件 `content_fingerprint` 持久化 NULL（Review #83 第四轮 HIGH-03）**：pipeline 顺序为 `detect sensitivity → fill_event_fingerprint → security gate → persistence projection`，即敏感正文被 NULL 前**已先计算并准备持久化确定性 SHA-256**。对手机号/身份证/常见口令等**低熵敏感值**，普通确定性 SHA-256 可离线枚举比对，**不等价于不可恢复脱敏**。因此**本版规定：** 以下事件落库时 `content_fingerprint` **必须为 NULL**，**不参与内容级指纹去重/分组**（dedup_group/duplicate_of 亦为空）：
  - `is_sensitive_matched = true`；
  - `sensitivity = high / critical`；
  - `admission_decision = reject`（security / consent 类 reject）；
  - `consent_scope = none`（D 轨前置 REJECT）。
  - 若未来确有敏感内容判重需求，**须另设计 keyed HMAC / 隐私保护型指纹**，并经独立 ADR；本版不允许直接持久化普通确定性 SHA-256 于敏感/未授权事件。
  - **敏感 hash 旁路防护（v5，HIGH-01 协调）**：除 `source_events.content_fingerprint` 置 NULL 外，敏感低熵内容**不得经 `idempotency_cache._request_fingerprint` 派生落盘**——handler 的 `request_fingerprint` 对敏感/未授权事件内容身份取固定安全占位 `<SENSITIVE-OMITTED>`（ADR-014 v5）；由此保证正文 / `content_summary` / `content_fingerprint` / `request_fingerprint` **四路均不持久化敏感派生值**，杜绝低熵 SHA-256 可离线枚举的同类风险在幂等缓存旁路复现。
- **跨用户隔离**：Repository 层所有查询强制 `user_id` 过滤 + `UNIQUE(event_id)` 阻止跨用户同名复用，identity 不一致按 `EventIdentityConflict` 拒绝（`[02 §16.6]`）；跨用户 `IntegrityError` 按 fail-close 回查规则处置，**不回读/不返回他人事件内容**（MEDIUM-03）。
- 日志脱敏复用 D5-D observability PII filter；事件正文/summary 不入日志

### processing_status

- **首次落库一律 `pending`**（Review #83 第三轮 MEDIUM-01）：`awaiting processing`，与 DDL `DEFAULT 'pending'` 及既有 `pipeline/schemas.py` 语义一致；`admission_decision`（allow_extraction / audit_only / reject）为**正交字段**，独立表达准入结果，不借用 processing_status；
- **REJECT / AUDIT_ONLY / 指纹去重重复事件**：保持 `pending`（它们可能永不进入真实抽取）；**禁止**落 `extracting`——避免形成永久"抽取处理中"假状态、被 D9-D 反复当作待处理事件消费；
- **D9-D 消费资格谓词（Review #83 第四轮 MEDIUM-02）**：仅**同时满足**以下三项的事件可进入 Extraction 调度（推进 `pending → extracting`）：
  1. `processing_status = 'pending'`；
  2. `admission_decision = 'allow_extraction'`；
  3. `duplicate_of IS NULL`（fingerprint 重复事件由 D9-D 依据 `dedup_group` 抑制重复抽取，不重复进入调度）。
  —— 仅扫 `processing_status='pending'` 会把 REJECT/AUDIT_ONLY/content duplicate 全部误捞，必须在扫描谓词中固定三条件。
- 仅当真实进入 Extraction 调度后由 D9-D consumer 推进 `pending → extracting → extracted`（`embedded/stored` 同理留待接线）；**本版不假装成功、不提前重新定义状态机**（processing_status 属 D3 技术候选状态机，A/B/D 待最终确认，本版不扩展其语义）。

### 事务边界

- 事件落库独立事务（UoW 模式）；本版**不接线 outbox**（CHECK 约束冻结不动，索引任务属 D9-D）
- **请求级幂等 + 业务副作用同事务（Review #83 第四轮 HIGH-02）**：`event.ingest` 走既有 **`UoW.execute_idempotent(...)`**（ADR-006 / FRZ-IPC-005），其在**同一事务 + 进程级单写锁**内完成：`幂等检查 → 业务写入（event collision → pipeline/admission → source_event write）→ response cache 写入`——请求级幂等检查与 `source_events` 写入**不得拆成两个事务**（否则相同 idempotency_key 的两个并发请求可能各自先产生业务副作用、最后才在缓存撞键，破坏 FRZ-IPC-005「相同幂等请求只产生一次副作用」）；「source_events 独立事务」仅指**不与 Outbox 同事务**（TD-D4D-001 接线前），非脱离 idempotency_cache UoW
- 失败语义：SQLITE_BUSY → `DatabaseLockedError`（FR-DB-003）；同 event_id + immutable identity 不一致 → `EventIdentityConflict`（Review #83 第三轮 HIGH-01，替代原 `EventOwnershipError` 口径——跨用户/跨 session 复用统一归入 identity 不一致，handler 转 INVALID_REQUEST）；请求级幂等冲突（同三元组 + 不同 request fingerprint）→ `IdempotencyConflictError`（既有语义，见 ADR-014 §幂等）；跨用户 event_id IntegrityError → `EventIdentityConflict` → INVALID_REQUEST（MEDIUM-03）

---

## 变更控制

- `source_events` 为**新增表**，属 FRZ-DB-001 允许的「新增 optional 扩展」（既有 5 表/索引/触发器/FTS5 定义**不得修改**）；
- 迁移命名走 ADR-007；新增配置键（如 `dedup.fingerprint_window_hours`）走 FRZ-CFG-001 扩展或登记 TD（本版默认值 24h 硬编码，配置化登记 TD 不阻塞）；
- 已冻结 FRZ-DB-001~005、FRZ-IPC-001~007 既有条目**不得修改**（本 ADR 只增不改）。
- **v2 契约变更已按 Review #83 第一轮处置**：UNIQUE 唯一键改全局、指纹去重改保留+标记（新增 2 列 = 35 字段）、33 列 NormalizedEvent 投影补齐、敏感命中强制 NULL、processing_status 不写 extracted——均属本 ADR 冻结范围，回写 FRZ-DB-001 扩展节时一并记录。
- **v3 契约变更已按 Review #83 第三轮处置**：event_id identity collision 契约（幂等重放 vs `EventIdentityConflict`）、processing_status 首次一律 `pending`、dedup_group 含 user scope、敏感摘要清空规则收紧——均属本 ADR 冻结范围，回写 FRZ-DB-001 扩展节时一并记录。
- **v4 契约变更已按 Review #83 第四轮处置**：immutable identity 重定义（独立稳定字段集 + `event_identity_fingerprint`，排除 idempotency_key/session_id/pipeline 脆弱 content_fingerprint，纳入 actor_id，occurred_at 统一 canonicalization）、敏感/未授权事件 `content_fingerprint` 持久化 NULL（HIGH-03）、固定「schema precheck → pipeline 纯计算 → identity compare → replay 跳过准入」统一顺序（MEDIUM-01）、`pending` 消费资格三条件谓词（MEDIUM-02）、跨用户 IntegrityError fail-close 回查（MEDIUM-03）、dedup head 与插入同 UoW/单写锁原子绑定（MEDIUM-04）——均属本 ADR 冻结范围，回写 FRZ-DB-001 扩展节与 `event_identity_fingerprint` 说明时一并记录。
- **v5 契约变更已按 Review #83 第五轮处置（与 ADR-014 v5 协调）**：固定顺序重排（payload 结构预检 → trusted identity precheck → pipeline 纯计算 → privacy-safe request_fingerprint → `UoW.execute_idempotent` 单事务）、敏感 hash 旁路防护（request_fingerprint 对敏感/未授权事件用固定安全占位，四路均不持久化敏感派生值）、cache replay 允许纯计算但禁止重复业务副作用（HIGH-01）——均属本 ADR 冻结范围，回写 FRZ-DB-001 扩展节时一并记录。

---

## 影响

### 架构影响

- 多源事件形成独立结构化真源（第 6 张表），支撑溯源/审计/去重/准入留痕；SQLite 仍为结构化真源，Vector 仅为可重建索引（`[02 §11.2]`）；
- 与 ADR-011 先例一致：冻结表集扩展走 ADR + Gate，不动既有 DDL。

### 开发影响

- `db/schema.py` 新增 `source_events` 表 + 5 索引 + 35 列投影（单一真相）；
- `db/repositories.py` 新增：`insert_source_event`（幂等，UNIQUE 冲突回查按 immutable identity 比对：一致返回既有 / 不一致抛 `EventIdentityConflict`；**敏感类强制 NULL content_summary/raw_payload_ref + content_fingerprint**；`find_dedup_group_head` 与 insert 同事务调用）、`get_source_event_by_event_id`（user 限定）、`find_dedup_group_head`（指纹点查，返回首次同指纹 id，user 限定）、`list_source_events`（user + 时间线分页，审计用）；
- `db/uow.py` 新增事件写入事务封装（复用现有 `execute_idempotent` 模式：请求级幂等 + 业务写入 + response cache 同事务，HIGH-02）；
- 新增迁移 `20260831_add_source_events.py` 与测试；
- 新增测试 `memory-service/tests/test_source_events_d6d.py`。

### 评测影响

- 迁移往返由 L1 测试 + 麒麟 VM L2（`alembic upgrade head` + `.schema` 对照）验证；
- 事件审计查询（按 user/时间线）纳入 L1 契约测试；
- **新增 L1 安全断言**：构造 `content_summary="my api_key is sk_..."` 等高敏事件经 handler 落库后，SQLite 中 `content_summary`/`raw_payload_ref` 为 NULL 或 `<redacted>`，原文不被查询到（Review #83 BLOCKER 回归项）；
- **新增 L1 契约用例（v3）**：同 event_id + 同 immutable identity 重放 → 返回首次 `source_event_id` + 既有 `admission_decision/reason_code` + `duplicate=true`（HIGH-01 回归项）；同 event_id + 不同 immutable identity → `EventIdentityConflict` → `INVALID_REQUEST`；REJECT/AUDIT_ONLY 事件落库 `processing_status='pending'`（MEDIUM-01 回归项）；普通质量型 AUDIT_ONLY 保留脱敏 `content_summary`、敏感类强制 NULL（MEDIUM-07 回归项）。
- **新增 L1 契约用例（v4）**：① **identity 污染回归（HIGH-01）**——无正文事件（无 content_summary/raw_payload_ref）重放时 `event_identity_fingerprint` 不随 `idempotency_key/session_id` 变化：同 event_id + 不同 idempotency_key 重投 → 判 replay 而非 conflict；换 `actor_id` 或换 `occurred_at` → `EventIdentityConflict`；② **敏感事件指纹 NULL（HIGH-03）**——高敏/security-reject/consent-reject 事件落库后 `content_fingerprint/dedup_group/duplicate_of` 为 NULL，且不进入任何去重复用；③ **三条件消费谓词（MEDIUM-02）**——扫描 `find_pending_eligible` 仅返回 `pending + allow_extraction + duplicate_of IS NULL`，REJECT/AUDIT_ONLY/content duplicate 不返回；④ **跨用户 IntegrityError fail-close（MEDIUM-03）**——user_B 复用 user_A 已持有的 event_id → `EventIdentityConflict` → INVALID_REQUEST，且 user_B 查询不到 user_A 事件内容；⑤ **dedup head 并发原子（MEDIUM-04）**——两个不同 event_id、同 fingerprint 并发提交：两行均存在、仅一行 `duplicate_of IS NULL`、另一行 `duplicate_of=首次行 id`。

### 安全影响

- `user_id` / `event_id` / `trace_id` 均按**非正文的受控标识**处理；**不得假设外部输入永不含敏感信息**，日志与审计按受控标识处理；
- 正文/敏感载荷两道边界：写入侧（A 轨 sensitive 标记 + 本层不落原文）与检索侧（Repository user 过滤）均已覆盖（`[02 §6.4]`）。

---

## 回滚与替代条件

若未来决定撤销 `source_events` 表或改方案，可经新 ADR 撤销本 ADR：执行迁移 downgrade（DROP TABLE + 索引）恢复 FRZ-DB-001 原表集；Repository/UoW 事件函数一并回退；已落库事件数据为历史数据，不影响既有 5 表消费语义。

---

## 证据与限制

- `deliverables/D4_DB_INITIAL_DESIGN_FREEZE_20260817.md:26/34`（FRZ-DB-001 冻结表集 + 变更控制「任何变更须走 ADR + Gate」）
- `docs/adr/011-trace-id-columns.md`（FRZ-DB-001 扩展先例）
- `docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md`（event_id 全局唯一冻结语义）
- `memory-service/pipeline/schemas.py`（NormalizedEvent / 枚举值域 / 33 列投影来源 + 2 去重标记列，D6-D 输入真源）
- `memory-service/security/source_admission.py`（SourceAdmissionResult，准入落库来源）
- `memory-service/pipeline/fingerprint.py`（content_fingerprint / event_duplicate_key）
- `docs/day6/day6-d-01-event-persistence-contract-plan-v0.5.md`（D6-D 契约规划，D-1/D-4/D-5/D-6/D-8/D-9/D-10/D-11/D-12 决策）

本 ADR 为文档/契约决策，不新增 Runtime 事实。批准记录：**D（周子腾）2026-08-31 决策选方案 A，v2 按 Review #83 第一轮重冻结，v3 按第三轮意见修订，v4 按第四轮意见修订，v5 按第五轮意见修订**；**Reviewer E（谢嘉然）待签署**；签署后回写 `D4_DB_INITIAL_DESIGN_FREEZE_20260817.md`（FRZ-DB-001 扩展节）。
