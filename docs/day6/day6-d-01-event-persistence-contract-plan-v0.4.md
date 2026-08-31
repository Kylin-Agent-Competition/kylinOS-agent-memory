# D6-D 多源事件持久化契约规划（草案 v0.4）

- **编制日期**：2026-08-31（v0.4 按 Review #83 第四轮修订）
- **编制人**：opencode（D 轨开发 Agent）
- **状态**：DRAFT v0.4 — D 已确认决策点并重冻结，按 Review #83 Reviewer E 第四轮 REWORK 修订；待 Reviewer E 再签（ADR-013/014 流程）
- **对照基线**：main @ `c1ee840`（PR #90 D7D 合并后，rebase 完成）；`docs/day10/05_d5d_task_list_20260826.md`；`deliverables/D4_DB_INITIAL_DESIGN_FREEZE_20260817.md`（FRZ-DB-001 v1.3 + ADR-011 扩展）；`docs/day3/11_os_agent_event_contract_v1.md`（D3-C FROZEN_CANDIDATE）；E 轨 D6 `docs/day6/day6-e-01-source-quality-admission-policy-v1.md`

> **v0.3 第三轮修订（Review #83 Reviewer E 第三轮）**：① event_id 冲突区分「幂等重放 vs identity collision」（HIGH-01，D-1 决策细化）；② processing_status 首次落库一律 `pending`、REJECT/AUDIT_ONLY 不落 extracting（MEDIUM-01，D-5 修订）；③ payload 身份仅属事件声明、非可信身份源（MEDIUM-02，D-9 修订）；④ 响应新增 `duplicate_reason=idempotent_replay/content_duplicate`、`duplicate_of`（MEDIUM-06）；⑤ schema_version 为 event.ingest IPC required override、handler 显式预检（MEDIUM-04）；⑥ dedup_group 含 user scope、索引 `(user_id, dedup_group)`（MEDIUM-05）；⑦ 敏感摘要清空规则收紧为仅敏感/安全类（MEDIUM-07）。

> **v0.4 第四轮修订（Review #83 Reviewer E 第四轮）**：① immutable identity 重定义（HIGH-01）：独立稳定字段集 + `event_identity_fingerprint`，**排除 `idempotency_key`/`session_id`/脆弱 `content_fingerprint`，纳入 `actor_id`，`occurred_at` 统一 canonicalization，正文有无不影响组成**；② 请求级幂等补全 `request_fingerprint` 冲突语义 + `UoW.execute_idempotent` 单事务边界（HIGH-02，D-2 修订，新增 D-11）；③ 敏感/security/consent reject 事件 `content_fingerprint` 持久化 NULL、不参与内容级指纹去重（HIGH-03，新增 D-12）；④ 事件碰撞固定顺序统一「schema precheck → pipeline 纯计算 → identity compare → replay 跳过准入/落库」（MEDIUM-01，D-1 修订）；⑤ `pending` 消费资格谓词 `pending + allow_extraction + duplicate_of IS NULL`（MEDIUM-02，D-5 修订）；⑥ 跨用户 IntegrityError fail-close 回查、不回读他人事件（MEDIUM-03，D-1 修订）；⑦ dedup head 与插入同 UoW/单写锁原子绑定（MEDIUM-04，D-4 修订）；⑧ content_summary provenance 门禁（MEDIUM-05，D-9 修订）；⑨ 指纹窗口参数化正式登记 **TD-D6D-001**（不再保持候选）。

---

## 一、背景与目标（台账 R35 / D6-D）

D5-D（R30）已打通 Gateway→SQLite→Outbox 写链路（PR #65）。D6-D 承接「多源接入、质量与安全」的 **D 轨持久化职责**：

1. **持久化 SourceEvent、授权、指纹和幂等键** —— 把统一事件入口（A 轨 EventPipeline 输出 + E 轨准入结果）落为结构化真源；
2. **实现日志脱敏、目录权限和跨用户 Repository 约束** —— 安全红线落库与可审计；
3. **完成重复事件和事务失败测试** —— 幂等/一致性证据。

交付边界：**事件持久化层**（表 + 迁移 + Repository + 事务语义 + 测试），不接 Vector consumer（TD-D4D-001 保持 Open）；**不接 outbox**（source_events 独立事务）；不改 IPC 协议既有字段。

---

## 二、范围与禁止修改范围

### 允许修改
- `memory-service/db/schema.py`（新增 source_events 表，既有表定义不动）
- `memory-service/db/repositories.py`（新增事件 Repository 函数）
- `memory-service/db/uow.py`（如需要新增事件事务封装，复用现有模式）
- `migrations/versions/20260831_add_source_events.py`（新增迁移，ADR-007 命名）
- `memory-service/domain/enums.py`（如需要补充事件持久化枚举，优先复用 pipeline.schemas）
- `memory-service/gateway/handlers.py`（**新增** `event_ingest_handler`，只增不覆盖既有 handler）
- `memory-service/gateway/registry.py`（提供 `event.ingest` 显式注册 seam；**不修改**既有冻结路由条目）
- 新增测试 `memory-service/tests/test_source_events_d6d.py`
- 契约文档（本文档 v0.4 + ADR-013 + ADR-014 + 冻结文档回写）

### 禁止修改（红线）
- 不修改冻结 FRZ-IPC-001~007（IPC/envelope/错误码域；**方法新增走 FRZ-IPC-007 允许的扩展范围**，见 ADR-014 变更控制）
- 不修改 FRZ-DB-001 既有 5 张表定义（conversations/turns/memory_entries/outbox/idempotency_cache）及既有索引/触发器/FTS5；**不扩展 outbox CHECK**
- 不修改 `pipeline/`、`providers/`、`security/source_admission.py`、`service/candidate_governance.py`、`embedding/`、`retrieval/`、`observability/` 既有实现（日志脱敏复用 observability PII filter，不重写）；consent 前置判定在 handler 层实现
- 不接 Outbox consumer / 不接线 outbox（TD-D4D-001 保持 Open；不假装成功）
- 不写 /usr、不覆盖官方 SDK；代码/日志/测试无 API Key/密码/私钥
- 不把 WSL/Mock 结果当宿主证据；L2 未执行不写「已支持」

---

## 三、输入契约（落库字段来源）

事件持久化输入 = **A 轨清洗后事件**（`NormalizedEvent`，pipeline/schemas.py）+ **E 轨准入结果**（`SourceAdmissionResult`，security/source_admission.py）。复用模型，不复制真源。

### 3.1 字段来源映射

| 落库字段 | 来源 | 说明 |
|---|---|---|
| `event_id` | NormalizedEvent.event_id | 事件级唯一键 |
| `user_id` | NormalizedEvent.user_id | **用户隔离键，禁止从正文推断** |
| `actor_id` | NormalizedEvent.actor_id | 实际发起者（SEC-UI-07） |
| `session_id` | NormalizedEvent.session_id | 会话归属 |
| `turn_id` | NormalizedEvent.turn_id | 可空 |
| `tool_call_id` | NormalizedEvent.tool_call_id | tool_result 必填 |
| `source_type` | NormalizedEvent.source_type | 七值枚举 |
| `event_type` | NormalizedEvent.event_type | 三值枚举 |
| `schema_version` | NormalizedEvent.schema_version | 事件结构版本 |
| `trace_id` | NormalizedEvent.trace_id | 追踪链 |
| `source_reference` | NormalizedEvent.source_reference | **受控引用，不存正文** |
| `raw_payload_ref` | NormalizedEvent.raw_payload_ref | **受控引用，不存正文** |
| `content_summary` | NormalizedEvent.content_summary | **脱敏摘要**（可空；正文原文不落库） |
| `idempotency_key` | NormalizedEvent.idempotency_key | 事件幂等键 |
| `consent_scope` | NormalizedEvent.consent_scope | **授权字段** |
| `source_business_status` | NormalizedEvent.source_business_status | 八值 |
| `sensitivity` | NormalizedEvent.sensitivity | 五级 |
| `is_sensitive_matched` | NormalizedEvent.is_sensitive_matched | 敏感标记 |
| `should_ignore` | NormalizedEvent.should_ignore | D3 安全契约 |
| `payload_security_checked` | NormalizedEvent.payload_security_checked | H1-mini |
| `memory_type` | NormalizedEvent.memory_type | 可空 |
| `occurred_at` / `captured_at` | NormalizedEvent | aware UTC ISO8601 |
| `content_fingerprint` | NormalizedEvent.content_fingerprint（fingerprint.py） | **重复检测（脆弱不确定：无正文时 fallback 含 idempotency_key/session_id，不得作事件身份）；敏感/未授权事件持久化 NULL（HIGH-03/D-12）** |
| `admission_decision` | SourceAdmissionResult.decision | ALLOW/AUDIT_ONLY/REJECT |
| `admission_reason_code` | SourceAdmissionResult.reason_code | 稳定 reason code |
| `processing_status` | 本层维护 | **首次落库一律 `pending`**（MEDIUM-01：REJECT/AUDIT_ONLY/指纹重复事件不落 extracting；仅真实进入抽取调度后由 D9-D 推进 pending→extracting→extracted；embedded/stored 待 consumer 接线）；admission_decision 为正交字段 |
| `created_at` / `updated_at` | 本层维护 | aware UTC ISO8601 |

### 3.2 Handler 输入契约（D-7 已确认：本版包含 handler + consent 前置 + Context Adapter）

新增 IPC 写方法 `event.ingest`（**ADR-014**：FRZ-IPC-007 路由表扩展，与 ADR-010 同模式）：

- **输入**：原始事件 dict（**flat**，对齐 A 轨 `MemorySourceEvent.model_validate` 输入，`extra="forbid"`），envelope 含 `trace_id/request_id/deadline_ms`（FRZ-IPC-006）；`schema_version` 须**显式提供**且仅精确 `"0.1"`（**event.ingest IPC required override**，handler 在模型校验前先检查 `"schema_version" in raw`，MEDIUM-04）
- **编排**（v0.4 / MEDIUM-01 统一固定顺序）：payload 显式字段预检 → **请求级幂等进入（`UoW.execute_idempotent` 单事务，HIGH-02）** → `EventPipeline.process(raw)` **纯计算**（清洗+评分+指纹，复用不改，无 DB 副作用）→ **event_id 冲突处置**（按 `user_id+event_id` 点查既有行：immutable identity 一致=幂等重放返回首次完整结果+`duplicate_reason='idempotent_replay'`；不一致=`EventIdentityConflict`→INVALID_REQUEST，HIGH-01；跨用户 IntegrityError fail-close，MEDIUM-03）→ **D 轨 consent 前置判定**（`consent_scope=none` → REJECT，handler 层实现，不改 `security/`）→ `SourceAdmissionPolicy.evaluate(result, ctx_svc)`（复用不改，`ctx_svc` 由 `RequestContext → ServiceRequestContext` 显式转换构造）→ `source_events` 落库（`processing_status='pending'`；**敏感/security/consent reject 事件 `content_fingerprint` NULL**，HIGH-03；`find_dedup_group_head`+insert 同事务，MEDIUM-04；独立事务=**不与 outbox 同事务**、但与幂等缓存同 UoW，HIGH-02）→ response cache 同事务写入
- **注册策略**：production 默认**不注册**（BLOCKED_BY_HOST_MAPPING，与 ADR-010 一致）；validation/test profile 显式注册
- **错误语义**：FRZ-IPC-002 五错误码（非法载荷 INVALID_REQUEST / 内部异常 INTERNAL_ERROR / 未注册 UNSUPPORTED_METHOD）；同 event_id + identity 不一致 → INVALID_REQUEST（EventIdentityConflict，不回显标识）；**同幂等三元组 + 不同 request_fingerprint → IdempotencyConflictError → INVALID_REQUEST（HIGH-02）**
- 不修改 `pipeline/`、`security/`、`gateway/registry.py` 冻结路由表以内内容（路由新增走 ADR-014 签署；handler/registry seam 为新增）

### 3.3 明确不落库
- **用户/助手正文原文**（原文隔离红线 [02 §4.1]）：只落 `content_summary`（脱敏）+ `raw_payload_ref`/`source_reference`（受控引用）
- **敏感载荷原文、API 密钥/令牌/口令**（写入边界拒绝，A 轨 sensitive 已标记；**敏感/安全类事件 content_summary/raw_payload_ref 强制 NULL**：`is_sensitive_matched=true`、`sensitivity=high/critical`、security/consent 类 reject、`consent_scope=none`；普通质量型 AUDIT_ONLY 允许保留已脱敏摘要，见 ADR-013，MEDIUM-07）
- `allowed_extraction_kinds`（准入的抽取范围集合）——如需审计可落 JSON 到扩展列，本版不落（控制范围，决策点 D-3）

---

## 四、DB 表设计（新增 `source_events`，FRZ-DB-001 扩展）

### 4.1 表定义（草案，35 列：<NormalizedEvent 业务投影列> + 2 去重标记列（dedup_group/duplicate_of），精确组成以 ADR-013 DDL 为准）

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
    requires_embedding       INTEGER NOT NULL DEFAULT 1,
    has_structured_payload   INTEGER NOT NULL DEFAULT 0,
    language_tag             TEXT,
    occurred_at              TEXT    NOT NULL,                -- aware UTC ISO8601（identity 组成，统一 canonicalization）
    captured_at              TEXT    NOT NULL,                -- aware UTC ISO8601
    content_fingerprint      TEXT,                            -- 重复检测（脆弱不确定；敏感/未授权事件持久化 NULL，HIGH-03）
    dedup_group              TEXT,                            -- 指纹去重组（含 user scope：dedup:<user_id>:<fp>:<source_type>；敏感事件随指纹 NULL 不分组）
    duplicate_of             INTEGER,                         -- 首次同指纹事件 id（自关联 NULL 表示首次；软引用，无 FK 约束）
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

### 4.2 索引（草案）

| 索引 | 定义 | 用途 |
|---|---|---|
| `uq_source_events_event` | **UNIQUE(event_id)** | 事件级幂等 + 全局唯一（D3 冻结语义） |
| `idx_source_events_user_created` | (user_id, created_at) | 按用户时间线查询/审计 |
| `idx_source_events_fingerprint` | (user_id, content_fingerprint) | 指纹重复检索（索引点查） |
| `idx_source_events_dedup_group` | (user_id, dedup_group) | 去重组查询（**含 user scope**，防跨用户误判；MEDIUM-05） |
| `idx_source_events_status` | (user_id, processing_status) | 处理状态扫描 |

### 4.3 迁移
- 文件：`migrations/versions/20260831_add_source_events.py`（ADR-007 命名 `YYYYMMDD_<desc>.py`）
- upgrade：CREATE TABLE + 5 索引；downgrade：DROP TABLE（新表无既有数据依赖，可整表回滚）
- 独立 revision，不触碰 `001_initial_schema` / `20260826_add_trace_id` 既有迁移

---

## 五、关键决策点（D 已确认 v2 / Reviewer E 再签）

| # | 决策点 | 推荐/决议（v4） | 备选 | 理由 |
|---|---|---|---|---|
| D-1 | event_id 唯一键粒度与冲突语义 | **全局 `UNIQUE(event_id)`** ✅ v2 重冻结（对齐 D3 冻结语义「事件全局唯一标识」）；**v3 细化冲突处置（HIGH-01）**：同 event_id + immutable identity 一致 = 幂等重放 → 返回首次持久化完整结果；不一致 = `EventIdentityConflict` → INVALID_REQUEST；**v4 修订（HIGH-01 / MEDIUM-01 / MEDIUM-03）**：immutable identity 重定义为独立稳定字段集 + `event_identity_fingerprint`（排除 idempotency_key/session_id/脆弱 content_fingerprint，纳入 actor_id，occurred_at 统一 canonicalization，正文有无不影响）；事件碰撞固定顺序统一「schema precheck → pipeline 纯计算 → identity compare → replay 跳过准入/落库」；跨用户 IntegrityError fail-close（不回读他人事件） | 用户内唯一 UNIQUE(user_id,event_id) | 消除「全局唯一 vs 用户内唯一」矛盾（Review #83 意见四）；杜绝「Response 指向旧行但准入结果属于新请求」真源不一致；防止 idempotency_key/session_id 经 fallback 指纹污染事件身份（第四轮 HIGH-01) |
| D-2 | 幂等键与 idempotency_cache 关系 | source_events 自带 `idempotency_key` 列 + **复用既有 `idempotency_cache`（FRZ-IPC-005 / ADR-006）** ✅；**v4 修订（HIGH-02）**：请求级幂等补全 `request_fingerprint` 冲突语义（same triple + same fingerprint → cache replay；same triple + different fingerprint → `IdempotencyConflictError` → INVALID_REQUEST），**不新建**第二套幂等缓存表 | 新建第二套幂等缓存表 | 事件级幂等（event_id identity）与 IPC 请求级幂等（idempotency_key 三元组）分层；复用既有 `UoW.execute_idempotent` + request_fingerprint wrapper（ADR-010 已实现，不改 DDL） |
| D-3 | 准入抽取范围（allowed_extraction_kinds）是否落库 | **本版不落**（仅落 decision + reason_code） | JSON 扩展列 | 控制范围；审计可用 decision/reason_code 复原，抽取范围由 E 轨策略重放 |
| D-4 | 指纹去重语义 | **保留事件 + 标记去重** ✅ v2 重冻结：同 user+fingerprint+source_type 窗口内 → 仍落库新行，标记 `duplicate_of`/`dedup_group`，抑制重复抽取但不丢事件时间线/审计/频次（Review #83 意见五）；**v3：dedup_group 含 user scope**（`dedup:<user_id>:<fp>:<source_type>`，索引 `(user_id, dedup_group)`，MEDIUM-05）；**v4 修订（MEDIUM-04）**：`find_dedup_group_head` + `insert_source_event` 同一 `UoW / 单写锁 / 事务` 原子执行，杜绝两并发同指纹各自 `duplicate_of=NULL` 产生双组首 | 24h 窗口跳过插入（v1 原方案） | SourceEvent 是可溯源审计真源，10:00/12:00 两次打开文件 A 是两次真实行为；性能仍为 `idx_source_events_fingerprint` 索引点查 O(logN+k)；并发隔离依赖 UoW 单写锁（FR-DB-004） |
| D-5 | processing_status 终态 | **首次落库一律 `pending`** ✅ v3 修订（MEDIUM-01）：admission_decision 为正交字段；REJECT/AUDIT_ONLY/指纹重复事件不落 `extracting`，杜绝永久「抽取处理中」假状态；**v4 修订（MEDIUM-02）**：冻结 D9-D 消费资格谓词 = `pending + admission_decision='allow_extraction' + duplicate_of IS NULL` 三条件，仅满足者可推进 `pending→extracting` | 直接写 extracted（v1 原方案）/ 停在 extracting（v2 方案） | 不假装成功；防止只扫 `pending` 把 REJECT/AUDIT_ONLY/content duplicate 全部误捞；processing_status 属 D3 技术候选状态机，本版不重新定义、不提前扩展语义 |
| D-6 | 事务边界 | **事件落库 + 幂等检查 + response cache 同一 `UoW.execute_idempotent` 事务，本版不接 outbox** ✅ v2 重冻结 + **v4 明确（HIGH-02）**：独立事务 = 不与 Outbox 同事务（outbox CHECK 冻结不扩展），**不是**与 idempotency_cache 拆两事务；拆两会破坏 FRZ-IPC-005「相同幂等请求只产生一次副作用」 | 落库 + outbox 入队同事务（v1 原方案） | 消除与 ADR-013「独立事务不接 outbox」的冲突（Review #83 意见七）；outbox 接线走后续 ADR/schema 扩展；请求级幂等并发安全依赖同事务（第四轮 HIGH-02） |
| D-7 | 事件入口 handler | **本版包含 handler** ✅：`event.ingest` IPC 写方法（ADR-014 路由扩展，production 默认不注册）+ gateway handler 编排（v4：request_fingerprint → pipeline 纯计算 → event_id 冲突处置 → consent 前置 → admission → 落库 → response cache，单事务） | 仅 repository 层 | 用户指示本版自建 handler，不等 D6-C；路由新增走 ADR-014 冻结流程 |
| D-8 | consent_scope=none 准入归属 | **D 轨 handler 前置 REJECT** ✅（`consent_not_granted`，不改 `security/source_admission.py`） | 依赖 E 轨补 consent 分支 | SourceAdmissionPolicy 当前无 consent_scope 判定，"E 轨已处理" 为假断言（Review #83 意见八）；本版 D 轨闭环，后续 E 轨补齐保持一致 |
| D-9 | Gateway Context 身份真源 | **宿主可信注入（production ACTIVE 门禁）** ✅ v2 重冻结 + **v3 修正（MEDIUM-02）**：handler 内 `RequestContext → ServiceRequestContext` 显式转换；**payload 中 user_id/actor_id/session_id 仅属事件声明，非独立可信身份源**；删除「与 envelope 请求级身份一致」不可实现表述；production ACTIVE 前须由独立 trusted host identity → RequestContext → ServiceRequestContext，再与 payload.user_id 执行真实 fail-close 比对（BLOCKED_BY_HOST_MAPPING）；**v4 修订（MEDIUM-05）**：`content_summary` provenance 门禁——ACTIVE 前置 Host Adapter 必须产生经受控 sanitization/summarization 的 content_summary，禁止直映宿主原始正文 | 登记待定不冻结 | 消除 Gateway RequestContext（无 user_id/actor_id）与 ServiceRequestContext 类型不兼容；杜绝「payload==payload」自证冒充可信身份校验；content_summary 为调用方声明，非系统生成摘要，不得上浮为系统脱敏证据（第四轮 MEDIUM-05） |
| D-10 | immutable identity 组成（第四轮 HIGH-01） | **独立稳定字段集 + 派生 `event_identity_fingerprint`** ✅ v4 新增：`user_id + actor_id + source_type + event_type + occurred_at(规范化 UTC ms) + event_content_identity`（归一化 content_summary / 否则归一化 raw_payload_ref / 均无则固定 `<no-content>` 占位）；**明确排除** `idempotency_key`、`session_id`、`trace_id`、脆弱 `content_fingerprint`（`fingerprint.py` 无正文时 fallback 到 event_id+idempotency_key+session_id，属请求级/会话级污染）；`actor_id` **属于** identity（换 actor 不得判 replay）；`session_id` **不属于**（会话级属性，不入身份）；敏感/security/consent reject 事件 content 不参与（正文 NULL，identity 简并为非内容字段） | 复用现有 `content_fingerprint` 作身份（否决） | 防 `idempotency_key/session_id` 经 dedup fallback 间接污染事件身份；同事件重放 idempotency_key 变化仍判 replay；换 actor/换 occurred_at 判 conflict（Review #83 第四轮 HIGH-01） |
| D-11 | 请求级幂等冲突语义与事务边界（第四轮 HIGH-02） | **复用既有 `idempotency_cache` + `request_fingerprint`** ✅ v4 新增：`request_fingerprint = sha256(method + 业务语义字段[e.v event_id/occurred_at 规范化/content identity/...])`（不含 trace_id/request_id/deadline_ms/schema_version/idempotency_key）；`same triple + same fingerprint → cache replay`；`same triple + different fingerprint → IdempotencyConflictError → INVALID_REQUEST`；**事务边界**：幂等检查 + event collision + pipeline/admission + source_event 写入 + response cache 全部在 `UoW.execute_idempotent` 单事务`内完成（不拆两事务） | 拆成幂等与业务两个事务（否决） | FRZ-IPC-005「相同幂等请求只产生一次副作用」依赖同事务 + 进程级单写锁（uow.py 已实现）；idem_1 先后用于 evt_A/evt_B → 冲突拒绝（Review #83 第四轮 HIGH-02） |
| D-12 | 敏感/未授权事件内容指纹（第四轮 HIGH-03） | **`content_fingerprint` 持久化 NULL** ✅ v4 新增：`is_sensitive_matched=true` / `sensitivity=high/critical` / security reject / consent reject / `consent_scope=none` 事件落库时 `content_fingerprint` 必须 NULL，**不参与内容级指纹去重/分组**（dedup_group/duplicate_of 为空）；未来敏感判重须走 keyed HMAC / 隐私保护型指纹 + 独立 ADR | 持久化普通确定性 SHA-256（否决） | 低熵敏感值（手机号/身份证/口令）可离线枚举 SHA-256，不等价不可恢复脱敏（Review #83 第四轮 HIGH-03） |

---

## 六、错误语义（复用冻结域，不新增错误码）

| 场景 | 行为 | 映射 |
|---|---|---|
| 事件已存在（同 event_id，immutable identity 一致） | **幂等重放**：返回首次持久化完整结果（source_event_id + 既有 admission_decision/reason_code + duplicate=true + duplicate_reason=idempotent_replay），不重跑 pipeline/admission（HIGH-01） | 正常路径，非错误 |
| 事件已存在（同 event_id，immutable identity 不一致） | 抛 `EventIdentityConflict` → INVALID_REQUEST（HIGH-01） | INVALID_REQUEST（不回显标识） |
| 请求级幂等冲突（同三元组 + 不同 request_fingerprint） | 抛 `IdempotencyConflictError` → INVALID_REQUEST（HIGH-02，如 idem_1 先 evt_A 后 evt_B）；同三元组 + 同指纹 → cache replay 返回首次 response | INVALID_REQUEST（不回显标识） |
| 指纹重复（同 user+fingerprint+source_type 窗口内） | **仍插入新行** + 标记 duplicate_of/dedup_group（D-4，同 UoW 原子，MEDIUM-04）；响应 duplicate=true + duplicate_reason=content_duplicate + duplicate_of（MEDIUM-06） | 正常路径，非错误 |
| SQLITE_BUSY（busy_timeout 到期） | 抛 `DatabaseLockedError`，由调用方降级 | FR-DB-003 既有语义 |
| 跨用户复用 event_id | 当前 user 未查到但 INSERT 触发 UNIQUE(event_id) IntegrityError → fail-close `EventIdentityConflict` → INVALID_REQUEST（MEDIUM-03，不与 user-scoped 回查混淆） | handler 转 INVALID_REQUEST（不回显标识、不回读他人事件） |
| 校验失败（字段/枚举非法 / schema_version 缺失或 != "0.1"） | Pydantic ValidationError → 结构化错误 | 既有模式 |
| consent_scope = none | 前置 REJECT（D-8），随事件落库（processing_status=pending，content_fingerprint=NULL，HIGH-03） | 正常业务决策，非错误 |

---

## 七、安全边界（写入与检索两道）

1. **用户隔离**：所有查询强制 `user_id` 过滤（Repository 层，[02 §16.6]）+ `UNIQUE(event_id)` 全局唯一 + immutable identity 一致性（同 event_id + identity 不一致 → 拒绝，D-10）+ 跨用户 event_id IntegrityError fail-close（不回读他人事件，MEDIUM-03）；**payload 身份仅属事件声明（test/validation 下为自证一致性，非可信身份认证）**，production ACTIVE 前须以独立 trusted host identity + fail-close 比对为硬门禁（D-9 / MEDIUM-02）；
2. **原文隔离**：正文/敏感载荷不落库、不入日志；只落脱敏摘要 + 受控引用；**敏感/安全类事件 content_summary/raw_payload_ref 强制 NULL**（is_sensitive_matched=true / high-critical / security-consent reject / consent_scope=none），普通质量型 AUDIT_ONLY 保留已脱敏摘要（BLOCKER 回归项 + MEDIUM-07）；**敏感/未授权事件 `content_fingerprint` 持久化 NULL**（HIGH-03 / D-12），不参与内容级指纹去重；
3. **授权落库**：`consent_scope` 随事件持久化；`consent_scope=none` **由 D 轨 handler 前置 REJECT**（D-8），不声称 E 轨已处理；
4. **日志脱敏**：复用 D5-D observability JSON 日志 PII filter；事件正文/summary 不出现在任何日志，只记录结构化 ID（event_id/trace_id）；
5. **content_summary provenance（MEDIUM-05 / D-9）**：`content_summary` 为调用方声明值，非系统生成摘要；ACTIVE 前置 Host Adapter 受控 sanitization/summarization，禁止直映宿主原文；test 态标注为声明，不得上浮为系统脱敏证据；
6. **目录权限**：数据目录 `~/.local/share/kylin-memory/` 0700、DB 文件 0600（systemd `RuntimeDirectory` 已有，TD-IPC-002 已 Resolved）；L2 实测 stat 权限位。

---

## 八、测试规划

### L0
- `python3 -m compileall memory-service/db memory-service/tests/test_source_events_d6d.py`
- Ruff `--select F,E9`；`git diff --check`

### L1（pytest，WSL2）
| 用例 | 覆盖 |
|---|---|
| 事件落库成功 + 字段映射完整性（35 列投影正常，processing_status=pending） | 正向 |
| 同 event_id + immutable identity 一致（重放）→ 返回首次 source_event_id + 既有 admission + duplicate=true + duplicate_reason=idempotent_replay | 幂等重放（HIGH-01） |
| **无正文事件（无 content_summary/raw_payload_ref）重放：换 idempotency_key/session_id 重投 → 仍判 replay 而非 conflict（identity 不随请求级字段变化）** | identity 污染回归（HIGH-01 / D-10） |
| **同 event_id 换 actor_id 或换 occurred_at → EventIdentityConflict → INVALID_REQUEST（identity 含 actor/时间）** | identity 组成（HIGH-01 / D-10） |
| 同 event_id + immutable identity 不一致 → EventIdentityConflict → INVALID_REQUEST | identity collision（HIGH-01） |
| **请求级幂等：同三元组 + 同 request_fingerprint → cache replay（返回首次 response，无新增副作用）** | request fingerprint（HIGH-02 / D-11） |
| **请求级幂等冲突：同三元组 + 不同 request_fingerprint（evt_A→evt_B）→ IdempotencyConflictError → INVALID_REQUEST** | 幂等冲突（HIGH-02 / D-11） |
| **同 UoW 原子：幂等缓存写入与 source_event 写入同一事务（回滚后两者均不落地）** | 事务边界（HIGH-02 / D-11） |
| 跨用户复用 event_id → INVALID_REQUEST（EventIdentityConflict，不回读他人事件） | 隔离负向 / 跨用户 fail-close（MEDIUM-03） |
| 同指纹窗口重复 → 仍落库新行 + duplicate_of/dedup_group（含 user scope）+ duplicate_reason=content_duplicate | 指纹保留+标记（D-4 / MEDIUM-06） |
| **dedup head 并发原子：两个不同 event_id + 同 fingerprint 并发提交 → 两行均存在、仅一行 duplicate_of IS NULL、另一行指向首次行 id** | dedup head 原子（MEDIUM-04 / D-4） |
| 跨用户查询隔离（B 查不到 A 的事件） | 隔离 |
| **高敏事件（content_summary 含 sk_xxx）落库后 content_summary/raw_payload_ref 为 NULL 或 <redacted>** | 安全 BLOCKER 回归 |
| **高敏/security reject/consent reject 事件落库后 content_fingerprint/dedup_group/duplicate_of 为 NULL，且不进入任何去重复用** | 敏感指纹 NULL（HIGH-03 / D-12） |
| **消费谓词：扫 pending 资格仅返回 pending + allow_extraction + duplicate_of IS NULL；REJECT/AUDIT_ONLY/content duplicate 不返回** | 消费资格谓词（MEDIUM-02 / D-5） |
| 普通质量型 AUDIT_ONLY 保留脱敏 content_summary（非敏感不强制清空） | MEDIUM-07 回归 |
| consent_scope=none → 落库 REJECT(consent_not_granted)，processing_status=pending | 授权（D-8 / MEDIUM-01） |
| schema_version 缺失 / != "0.1" → INVALID_REQUEST（显式预检） | 契约校验（MEDIUM-04） |
| REJECT/AUDIT_ONLY 事件 processing_status !== 'extracting'（保持 pending） | MEDIUM-01 回归 |
| RequestContext → ServiceRequestContext 转换 + 声明内部一致性（test 态自证标注） | Context Adapter（D-9 / MEDIUM-02） |
| content_summary 声明值不标注为系统脱敏产物（provenance 标记） | content_summary 门禁（MEDIUM-05 / D-9） |
| admission_decision/reason_code 三值映射 | 准入落库 |
| content_summary 为脱敏摘要（无原文） | 安全 |
| 迁移 upgrade/downgrade 往返 + schema 对照（含 5 索引/CHECK，dedup_group 复合索引） | 迁移 |

### L2（麒麟 VM，人工操作清单，不声称已执行）
- `alembic upgrade head` + `.schema` 对照（source_events 表 + 5 索引 + 全局 UNIQUE + CHECK）
- systemd 部署后 `stat` 数据目录 0700 / DB 0600
- 真实 CLI 事件写入 → 落库 + 幂等回放 + 跨用户拒绝 + 指纹标记（uds_client）
- 服务日志扫描：无正文/PII 泄漏（复用 JSON 日志探针）

---

## 九、技术债关联

| TD | 处置 |
|---|---|
| TD-D4D-001（Outbox consumer 未接线） | 保持 Open；processing_status 首次一律 pending，仅真实抽取调度后推进 pending→extracting（消费资格谓词 MEDIUM-02）；指纹去重仅落标记（dedup_group/duplicate_of）不消费 |
| TD-D4D-002/003 | 保持 Open（不涉及本层） |
| TD-028 | 已由 PR #68 关闭（真实 IntegrityError 竞态测试） |
| **TD-D6D-001**（v4 正式登记，取消候选） | **事件指纹窗口阈值参数化**：`dedup.fingerprint_window_hours`（默认 24h，性能超标可 `=0` 关窗降级退化为仅 event_id 幂等）走 FRZ-CFG-001 扩展/新配置键，本版默认值硬编码于实现 PR；配置化实现与验收见技术债总账 TD-D6D-001 |

---

## 十、签署与落地流程

1. 本文档 + ADR-013（source_events 表设计，FRZ-DB-001 扩展）+ ADR-014（event.ingest，FRZ-IPC-007 扩展）提交 D 决策（周子腾）
2. Reviewer E（谢嘉然）**再次签署**（Review #83 已 REWORK，v4 修订后重提）
3. 回写 `D4_DB_INITIAL_DESIGN_FREEZE_20260817.md`（FRZ-DB-001 扩展节）与 `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-007 路由表）
4. 任务卡定稿（含验收标准）→ 开发分支（基于最新 main @ `c1ee840`）
5. 实现 + L0/L1 → PR → 麒麟 L2 证据 → 台账 R35 勾选

---

## 十一、决策状态与待澄清缺口（v0.4 更新）

**D 已确认（2026-08-31，v2 重冻结按 Review #83 第一轮；v3 修订按第三轮；v4 修订按第四轮）**：

- [x] 开启新分支 `feat/d6d-event-persistence`
- [x] D-1：全局 `UNIQUE(event_id)`（对齐 D3 全局唯一）；**v3：同 event_id + immutable identity 一致 = 幂等重放返回首次结果 / 不一致 = EventIdentityConflict → INVALID_REQUEST（HIGH-01）**；**v4：identity 重定义为独立稳定字段集 + event_identity_fingerprint（排除 idempotency_key/session_id/脆弱 content_fingerprint，纳入 actor_id，occurred_at canonicalization）；固定「schema precheck → pipeline 纯计算 → identity compare → replay 跳过准入」（MEDIUM-01）；跨用户 IntegrityError fail-close（MEDIUM-03）**
- [x] D-2：幂等键走既有 idempotency_cache + request_fingerprint（v4，HIGH-02，D-11）
- [x] D-4：指纹去重改「保留事件 + 标记 duplicate_of/dedup_group」，不丢真实事件；**v3：dedup_group 含 user scope（MEDIUM-05）**；**v4：dedup head + insert 同一 UoW 原子（MEDIUM-04）**
- [x] D-5：processing_status 首次落库一律 `pending`（REJECT/AUDIT_ONLY 不落 extracting；admission_decision 为正交字段）（MEDIUM-01）；**v4：消费资格谓词 = pending + allow_extraction + duplicate_of IS NULL（MEDIUM-02）**
- [x] D-6：source_events + 幂等检查 + response cache 同一 `UoW.execute_idempotent` 事务，不接 outbox（D-6 v4 明确，HIGH-02）
- [x] D-7：本版包含 handler（`event.ingest`，ADR-014）
- [x] D-8：consent_scope=none 由 D 轨 handler 前置 REJECT（不依赖 E 轨）
- [x] D-9：身份可信源 = 宿主注入；**v3：payload 身份仅属事件声明，非独立可信身份源；ACTIVE 前须独立 trusted host identity + fail-close 比对（MEDIUM-02）**；**v4：content_summary provenance 门禁（MEDIUM-05）**
- [x] D-10：immutable identity 组成（v4，HIGH-01）
- [x] D-11：请求级幂等 request_fingerprint + 单事务边界（v4，HIGH-02）
- [x] D-12：敏感/未授权事件 content_fingerprint NULL（v4，HIGH-03）
- [x] TD-D6D-001：指纹窗口参数化正式登记（v4）

**仍待确认**：

1. D-3：准入抽取范围集合是否确有审计落库需求（决定是否加 JSON 扩展列）——建议不落，E 轨策略可重放；
2. 事件保留策略（TTL/清理）是否属本版范围（建议登记 TD 不阻塞）；
3. **Reviewer E 复核 v4 修订**：identity 重定义（HIGH-01）、request_fingerprint 与单事务边界（HIGH-02）、敏感指纹 NULL（HIGH-03）、pending 谓词（MEDIUM-02）、跨用户 fail-close（MEDIUM-03）、dedup head 原子（MEDIUM-04）、content_summary 门禁（MEDIUM-05）、TD-D6D-001 登记。

**后续流程**：ADR-013（source_events 表设计）+ ADR-014（event.ingest 路由）→ D 决策确认 v4 + Reviewer E 再签 → 任务卡定稿 → 代码实现。
