# ADR-013：新增 `source_events` 表持久化多源事件（FRZ-DB-001 / D6-D 扩展）

- **状态**：✅ D 已决策（2026-08-31，方案 A）；REWORK 修订 v2（按 Review #83 Reviewer E 意见重冻结）；待 Reviewer E 签署
- **日期**：2026-08-31（v2 修订同日）
- **决策人**：周子腾（D）｜**Reviewer**：E（谢嘉然，待签）
- **责任轨道**：D（DB）为主，A/E 协作（消费现有 pipeline / admission 模型，不复制真源）
- **决策版本**：`source-events-table-v2`
- **适用范围**：FRZ-DB-001 表定义扩展；关联 `docs/day6/day6-d-01-event-persistence-contract-plan-v0.3.md`、`memory-service/pipeline/schemas.py`（MemorySourceEvent / NormalizedEvent）、`memory-service/security/source_admission.py`（SourceAdmissionResult）、`memory-service/pipeline/fingerprint.py`、ADR-007（迁移命名）、ADR-011（扩展先例）、ADR-014（event.ingest 路由）、FRZ-IPC-005、FRZ-DB-004（Dead Letter 策略）

> **v2 修订摘要（Review #83 REWORK 处置）**：① 敏感命中事件 content_summary/raw_payload_ref 强制 NULL；② event_id 唯一键改全局 `UNIQUE(event_id)` 对齐 D3 冻结语义；③ 指纹去重改为"保留事件 + 标记去重"（新增 dedup_group/duplicate_of 列）；④ 补齐 33 列 NormalizedEvent 投影（含 requires_embedding/has_structured_payload/language_tag）+ 2 去重标记列 = **35 字段**；⑤ consent_scope=none 由 D 轨 handler 前置 REJECT（不依赖 E 轨）；⑥ processing_status 不写 `extracted`（如实停在 `extracting`）；⑦ ADR 编号从 012 重排为 013。

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

选择方案 A：`source-events-table-v2`。**新增 `source_events` 表（35 字段 + 5 索引，含去重自关联列），经迁移 `20260831_add_source_events.py` 落地；`db/schema.py` 同步为单一真相；不修改既有 5 张表/索引/触发器/FTS5；不扩展 `outbox` CHECK 约束；事件落库与既有业务写链路互不耦合。**

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
    raw_payload_ref          TEXT,                            -- 受控引用，非正文（敏感命中强制 NULL）
    content_summary          TEXT,                            -- 脱敏摘要，非原文（敏感命中强制 NULL）
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
    occurred_at              TEXT    NOT NULL,                -- aware UTC ISO8601
    captured_at              TEXT    NOT NULL,                -- aware UTC ISO8601
    content_fingerprint      TEXT,                            -- 重复检测
    dedup_group              TEXT,                            -- 指纹去重组标识（同组仅首个可抽取）
    duplicate_of             INTEGER,                         -- 指向首次同指纹事件 id（自关联 NULL 表示首次）
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
| `idx_source_events_dedup_group` | (dedup_group) | 去重组查询（D9-D 抽取跳过） |
| `idx_source_events_status` | (user_id, processing_status) | 处理状态扫描（D9-D 预留） |

### 迁移

- 文件：`migrations/versions/20260831_add_source_events.py`
- **命名**：`YYYYMMDD_<description>.py`（ADR-007 红线）
- **revision**：`revision = "20260831_add_source_events"`，`down_revision = "20260826_add_trace_id"`（版本链 `001_initial_schema → 20260826_add_trace_id → 20260831_add_source_events`）
- **upgrade**：CREATE TABLE + 5 索引（`IF NOT EXISTS` 幂等，与 init_schema 契约一致）
- **downgrade**：DROP TABLE（新表无既有数据依赖，可整表回滚；无列删除红线问题）

### 幂等与重复检测

- **事件级硬幂等**：`UNIQUE(event_id)`（全局唯一，D3 冻结语义）—— 重复写入返回既有记录（DB 约束兜底，不靠应用层先查后插）
- **跨用户 ownership guard**：`event_id` 全局唯一后，跨用户/跨 session 复用同一 event_id 由 DB 约束直接拒绝（IntegrityError → `EventOwnershipError`，handler 转 INVALID_REQUEST，不回显标识）；不再存在"用户内唯一 + 跨用户复用"的矛盾
- **请求级幂等**：FRZ-IPC-005 三元组 `(user_id, session_id, idempotency_key)` 走既有 `idempotency_cache`（ADR-006），由 `event.ingest` handler 层执行（见 ADR-014）；`event_id` **不替代** `idempotency_key`（保持 ADR-010 语义）
- **指纹去重（保留事件 + 标记）**：同 `user_id` + 同 `content_fingerprint` + 同 `source_type` 且 `captured_at >= now - 24h` → **仍插入新事件行**（event_id 必不相同），但标记：
  - `duplicate_of` = 首次同指纹事件 id（无则 NULL）
  - `dedup_group` = 首次同指纹事件聚合键（`dedup:<fingerprint>:<source_type>`），同组仅首个事件可进抽取（`skip_extraction` 语义由 D9-D 消费 `dedup_group` 实现，本版只落库标记不消费）
  - 事件时间线、审计、行为频次、隐式偏好信号**不被丢弃**
  - 实现：`idx_source_events_fingerprint` 索引点查 + 时间过滤（O(logN+k)，非全表扫描、无内存集合、无外部服务）确定同组首行
  - **性能红线（D 确认）**：若 L1/L2 实测写路径开销超标 → 配置 `dedup.fingerprint_window_hours=0` 关闭窗口，退化为仅 event_id 幂等（不做指纹分组标记）；开关在 `config.py` 冻结 8 键之外**新增可选键**（走 FRZ-CFG-001 扩展或登记 TD，见「变更控制」）

### 授权与安全

- `consent_scope` 随事件落库（授权字段）；`consent_scope=none` 由 D 轨 `event.ingest` handler **前置 REJECT**（`consent_not_granted`，见 ADR-014 §编排），本层持久化决策结果；**不依赖 E 轨 SourceAdmissionPolicy 判断**（其当前无 consent 分支）
- **敏感命中强制 NULL**（`[02 §4.1]` 原文隔离）：`is_sensitive_matched=true` 或 `admission_decision=reject`（security/consent 类）或 `audit_only` 的事件，落库时 `content_summary` / `raw_payload_ref` **必须为 NULL**（或安全占位 `<redacted>` 走 content_summary，禁止原始字符串）；本 ADR 禁止任何"敏感事件仍写原始摘要"的降级路径
- **跨用户隔离**：Repository 层所有查询强制 `user_id` 过滤 + `UNIQUE(event_id)` 阻止跨用户同名复用（`[02 §16.6]`）
- 日志脱敏复用 D5-D observability PII filter；事件正文/summary 不入日志

### processing_status

- 本版落库推进到 **`extracting`**（清洗+准入完成，尚未执行真实抽取，与 D3 技术候选状态机一致）；`extracted / embedded / stored` 留待真实抽取链路消耗 `dedup_group` 后推进（D9-D 与 TD-D4D-001），**不假装成功**；REJECT / AUDIT_ONLY 事件同样停在 `extracting`（不得标 `extracted`）

### 事务边界

- 事件落库独立事务（UoW 模式）；本版**不接线 outbox**（CHECK 约束冻结不动，索引任务属 D9-D）
- 失败语义：SQLITE_BUSY → `DatabaseLockedError`（FR-DB-003）；跨用户复用 event_id → `EventOwnershipError`（仿 `ConversationOwnershipError`，handler 转 INVALID_REQUEST）；请求级幂等冲突 → `IdempotencyConflictError`（既有语义）

---

## 变更控制

- `source_events` 为**新增表**，属 FRZ-DB-001 允许的「新增 optional 扩展」（既有 5 表/索引/触发器/FTS5 定义**不得修改**）；
- 迁移命名走 ADR-007；新增配置键（如 `dedup.fingerprint_window_hours`）走 FRZ-CFG-001 扩展或登记 TD（本版默认值 24h 硬编码，配置化登记 TD 不阻塞）；
- 已冻结 FRZ-DB-001~005、FRZ-IPC-001~007 既有条目**不得修改**（本 ADR 只增不改）。
- **v2 契约变更已按 Review #83 处置**：UNIQUE 唯一键改全局、指纹去重改保留+标记（新增 2 列 = 35 字段）、33 列 NormalizedEvent 投影补齐、敏感命中强制 NULL、processing_status 停在 extracting——均属本 ADR 冻结范围，回写 FRZ-DB-001 扩展节时一并记录。

---

## 影响

### 架构影响

- 多源事件形成独立结构化真源（第 6 张表），支撑溯源/审计/去重/准入留痕；SQLite 仍为结构化真源，Vector 仅为可重建索引（`[02 §11.2]`）；
- 与 ADR-011 先例一致：冻结表集扩展走 ADR + Gate，不动既有 DDL。

### 开发影响

- `db/schema.py` 新增 `source_events` 表 + 5 索引 + 35 列投影（单一真相）；
- `db/repositories.py` 新增：`insert_source_event`（幂等，UNIQUE 冲突回查返回既有；`is_sensitive_matched` 时强制 NULL content_summary/raw_payload_ref）、`get_source_event_by_event_id`（user 限定）、`find_dedup_group_head`（指纹点查，返回首次同指纹 id）、`list_source_events`（user + 时间线分页，审计用）；
- `db/uow.py` 新增事件写入事务封装（复用现有模式）；
- 新增迁移 `20260831_add_source_events.py` 与测试；
- 新增测试 `memory-service/tests/test_source_events_d6d.py`。

### 评测影响

- 迁移往返由 L1 测试 + 麒麟 VM L2（`alembic upgrade head` + `.schema` 对照）验证；
- 事件审计查询（按 user/时间线）纳入 L1 契约测试；
- **新增 L1 安全断言**：构造 `content_summary="my api_key is sk_..."` 等高敏事件经 handler 落库后，SQLite 中 `content_summary`/`raw_payload_ref` 为 NULL 或 `<redacted>`，原文不被查询到（Review #83 BLOCKER 回归项）。

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
- `docs/day6/day6-d-01-event-persistence-contract-plan-v0.3.md`（D6-D 契约规划，D-1/D-4/D-5/D-6/D-8/D-9 决策）

本 ADR 为文档/契约决策，不新增 Runtime 事实。批准记录：**D（周子腾）2026-08-31 决策选方案 A，v2 按 Review #83 重冻结**；**Reviewer E（谢嘉然）待签署**；签署后回写 `D4_DB_INITIAL_DESIGN_FREEZE_20260817.md`（FRZ-DB-001 扩展节）。
