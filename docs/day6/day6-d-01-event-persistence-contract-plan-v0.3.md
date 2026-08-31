# D6-D 多源事件持久化契约规划（草案 v0.3）

- **编制日期**：2026-08-31（v0.3 按 Review #83 修订）
- **编制人**：opencode（D 轨开发 Agent）
- **状态**：DRAFT v0.3 — D 已确认 v2 决策点并重冻结，按 Review #83 Reviewer E REWORK 修订；待 Reviewer E 再签（ADR-013/014 流程）
- **对照基线**：main @ `fca8a87`（PR #67/#68 合并后，rebase 完成）；`docs/day10/05_d5d_task_list_20260826.md`；`deliverables/D4_DB_INITIAL_DESIGN_FREEZE_20260817.md`（FRZ-DB-001 v1.3 + ADR-011 扩展）；`docs/day3/11_os_agent_event_contract_v1.md`（D3-C FROZEN_CANDIDATE）；E 轨 D6 `docs/day6/day6-e-01-source-quality-admission-policy-v1.md`

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
- 契约文档（本文档 v0.3 + ADR-013 + ADR-014 + 冻结文档回写）

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
| `content_fingerprint` | NormalizedEvent.content_fingerprint（fingerprint.py） | **重复检测** |
| `admission_decision` | SourceAdmissionResult.decision | ALLOW/AUDIT_ONLY/REJECT |
| `admission_reason_code` | SourceAdmissionResult.reason_code | 稳定 reason code |
| `processing_status` | 本层维护 | pending/extracting/extracted（embedded/stored 待 consumer 接线） |
| `created_at` / `updated_at` | 本层维护 | aware UTC ISO8601 |

### 3.2 Handler 输入契约（D-7 已确认：本版包含 handler + consent 前置 + Context Adapter）

新增 IPC 写方法 `event.ingest`（**ADR-014**：FRZ-IPC-007 路由表扩展，与 ADR-010 同模式）：

- **输入**：原始事件 dict（**flat**，对齐 A 轨 `MemorySourceEvent.model_validate` 输入，`extra="forbid"`），envelope 含 `trace_id/request_id/deadline_ms`（FRZ-IPC-006）；`schema_version` 仅精确 `"0.1"`
- **编排**：`EventPipeline.process(raw)`（清洗+评分+指纹，复用不改）→ **D 轨 consent 前置判定**（`consent_scope=none` → REJECT，handler 层实现，不改 `security/`）→ `SourceAdmissionPolicy.evaluate(result, ctx_svc)`（复用不改，`ctx_svc` 由 `RequestContext → ServiceRequestContext` 显式转换构造，身份取宿主注入值）→ `source_events` 落库（独立事务，**不接 outbox**）
- **注册策略**：production 默认**不注册**（BLOCKED_BY_HOST_MAPPING，与 ADR-010 一致）；validation/test profile 显式注册
- **错误语义**：FRZ-IPC-002 五错误码（非法载荷 INVALID_REQUEST / 内部异常 INTERNAL_ERROR / 未注册 UNSUPPORTED_METHOD）
- 不修改 `pipeline/`、`security/`、`gateway/registry.py` 冻结路由表以内内容（路由新增走 ADR-014 签署；handler/registry seam 为新增）

### 3.3 明确不落库
- **用户/助手正文原文**（原文隔离红线 [02 §4.1]）：只落 `content_summary`（脱敏）+ `raw_payload_ref`/`source_reference`（受控引用）
- **敏感载荷原文、API 密钥/令牌/口令**（写入边界拒绝，A 轨 sensitive 已标记；**命中敏感的事件 content_summary/raw_payload_ref 强制 NULL**，见 ADR-013）
- `allowed_extraction_kinds`（准入的抽取范围集合）——如需审计可落 JSON 到扩展列，本版不落（控制范围，决策点 D-3）

---

## 四、DB 表设计（新增 `source_events`，FRZ-DB-001 扩展）

### 4.1 表定义（草案，35 列：33 列 NormalizedEvent 投影 + 去重标记 2 列）

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
    raw_payload_ref          TEXT,                            -- 受控引用，非正文（敏感强制 NULL）
    content_summary          TEXT,                            -- 脱敏摘要，非原文（敏感强制 NULL）
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
    occurred_at              TEXT    NOT NULL,                -- aware UTC ISO8601
    captured_at              TEXT    NOT NULL,                -- aware UTC ISO8601
    content_fingerprint      TEXT,                            -- 重复检测
    dedup_group              TEXT,                            -- 指纹去重组
    duplicate_of             INTEGER,                         -- 首次同指纹事件 id（自关联）
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
| `idx_source_events_dedup_group` | (dedup_group) | 去重组查询 |
| `idx_source_events_status` | (user_id, processing_status) | 处理状态扫描 |

### 4.3 迁移
- 文件：`migrations/versions/20260831_add_source_events.py`（ADR-007 命名 `YYYYMMDD_<desc>.py`）
- upgrade：CREATE TABLE + 5 索引；downgrade：DROP TABLE（新表无既有数据依赖，可整表回滚）
- 独立 revision，不触碰 `001_initial_schema` / `20260826_add_trace_id` 既有迁移

---

## 五、关键决策点（D 已确认 v2 / Reviewer E 再签）

| # | 决策点 | 推荐/决议（v2） | 备选 | 理由 |
|---|---|---|---|---|
| D-1 | event_id 唯一键粒度 | **全局 `UNIQUE(event_id)`** ✅ v2 重冻结（对齐 D3 冻结语义「事件全局唯一标识」） | 用户内唯一 UNIQUE(user_id,event_id) | 消除「全局唯一 vs 用户内唯一」矛盾（Review #83 意见四）；跨用户复用由 DB 约束拒绝 → EventOwnershipError |
| D-2 | 幂等键与 idempotency_cache 关系 | source_events 自带 `idempotency_key` 列 + 应用层查重；**不新建**第二套幂等缓存表 | 复用 idempotency_cache | 事件级幂等与 IPC 请求级幂等分层；避免耦合 D5-D 已冻结语义 |
| D-3 | 准入抽取范围（allowed_extraction_kinds）是否落库 | **本版不落**（仅落 decision + reason_code） | JSON 扩展列 | 控制范围；审计可用 decision/reason_code 复原，抽取范围由 E 轨策略重放 |
| D-4 | 指纹去重语义 | **保留事件 + 标记去重** ✅ v2 重冻结：同 user+fingerprint+source_type 窗口内 → 仍落库新行，标记 `duplicate_of`/`dedup_group`，抑制重复抽取但不丢事件时间线/审计/频次（Review #83 意见五） | 24h 窗口跳过插入（v1 原方案） | SourceEvent 是可溯源审计真源，10:00/12:00 两次打开文件 A 是两次真实行为；性能仍为 `idx_source_events_fingerprint` 索引点查 O(logN+k) |
| D-5 | processing_status 终态 | **本版落库停在 `extracting`**；`extracted/embedded/stored` 留待真实抽取链路（消费 dedup_group）后推进（TD-D4D-001） | 直接写 extracted（v1 原方案） | 不假装成功；REJECT/AUDIT_ONLY 不得标 extracted（Review #83 意见二）；processing_status 属 D3 技术候选，本版不重新定义状态机 |
| D-6 | 事务边界 | **事件落库独立事务，本版不接 outbox** ✅（与 ADR-013 一致；outbox CHECK 冻结不扩展） | 落库 + outbox 入队同事务（v1 原方案） | 消除与 ADR-013「独立事务不接 outbox」的冲突（Review #83 意见七）；outbox 接线走后续 ADR/schema 扩展 |
| D-7 | 事件入口 handler | **本版包含 handler** ✅：`event.ingest` IPC 写方法（ADR-014 路由扩展，production 默认不注册）+ gateway handler 编排 pipeline→consent 前置→admission→落库 | 仅 repository 层 | 用户指示本版自建 handler，不等 D6-C；路由新增走 ADR-014 冻结流程 |
| D-8 | consent_scope=none 准入归属 | **D 轨 handler 前置 REJECT** ✅（`consent_not_granted`，不改 `security/source_admission.py`） | 依赖 E 轨补 consent 分支 | SourceAdmissionPolicy 当前无 consent_scope 判定，"E 轨已处理" 为假断言（Review #83 意见八）；本版 D 轨闭环，后续 E 轨补齐保持一致 |
| D-9 | Gateway Context 身份真源 | **宿主可信注入** ✅：handler 内 `RequestContext → ServiceRequestContext` 显式转换；user_id/actor_id/session_id 取宿主注入值，trace_id 唯一真源 = envelope；生产注册前须经 host_mapping（BLOCKED_BY_HOST_MAPPING）（Review #83 意见三） | 登记待定不冻结 | 消除 Gateway RequestContext（无 user_id/actor_id）与 ServiceRequestContext 类型不兼容，杜绝拿不可信异源值做隔离 |

---

## 六、错误语义（复用冻结域，不新增错误码）

| 场景 | 行为 | 映射 |
|---|---|---|
| 事件已存在（同 event_id，全局唯一） | 返回既有记录，不重复插入（幂等命中） | 正常路径，非错误 |
| 指纹重复（同 user+fingerprint+source_type 窗口内） | **仍插入新行** + 标记 duplicate_of/dedup_group（D-4） | 正常路径，非错误（duplicate=true） |
| SQLITE_BUSY（busy_timeout 到期） | 抛 `DatabaseLockedError`，由调用方降级 | FR-DB-003 既有语义 |
| 跨用户复用 event_id | 抛 `EventOwnershipError`（新增，仿 `ConversationOwnershipError`） | handler 转 INVALID_REQUEST（不回显标识） |
| 校验失败（字段/枚举非法 / schema_version != "0.1"） | Pydantic ValidationError → 结构化错误 | 既有模式 |
| consent_scope = none | 前置 REJECT（D-8），随事件落库 | 正常业务决策，非错误 |

---

## 七、安全边界（写入与检索两道）

1. **用户隔离**：所有查询强制 `user_id` 过滤（Repository 层，[02 §16.6]）+ `UNIQUE(event_id)` 全局唯一（阻断跨用户同名复用）+ 注入式身份一致性（D-9）；
2. **原文隔离**：正文/敏感载荷不落库、不入日志；只落脱敏摘要 + 受控引用；**命中敏感的事件 content_summary/raw_payload_ref 强制 NULL**（BLOCKER 回归项）；
3. **授权落库**：`consent_scope` 随事件持久化；`consent_scope=none` **由 D 轨 handler 前置 REJECT**（D-8），不声称 E 轨已处理；
4. **日志脱敏**：复用 D5-D observability JSON 日志 PII filter；事件正文/summary 不出现在任何日志，只记录结构化 ID（event_id/trace_id）；
5. **目录权限**：数据目录 `~/.local/share/kylin-memory/` 0700、DB 文件 0600（systemd `RuntimeDirectory` 已有，TD-IPC-002 已 Resolved）；L2 实测 stat 权限位。

---

## 八、测试规划

### L0
- `python3 -m compileall memory-service/db memory-service/tests/test_source_events_d6d.py`
- Ruff `--select F,E9`；`git diff --check`

### L1（pytest，WSL2）
| 用例 | 覆盖 |
|---|---|
| 事件落库成功 + 字段映射完整性（35 列投影正常） | 正向 |
| 同 event_id 重复 → 幂等返回既有记录（全局唯一） | 幂等 |
| 跨用户复用 event_id → EventOwnershipError | 隔离负向 |
| 同指纹窗口重复 → 仍落库新行 + duplicate_of/dedup_group 标记 | 指纹保留+标记（D-4） |
| 跨用户查询隔离（B 查不到 A 的事件） | 隔离 |
| **高敏事件（content_summary 含 sk_xxx）落库后 content_summary/raw_payload_ref 为 NULL 或 <redacted>** | 安全 BLOCKER 回归 |
| consent_scope=none → 落库 REJECT(consent_not_granted) | 授权（D-8） |
| schema_version != "0.1" → INVALID_REQUEST | 契约校验 |
| RequestContext → ServiceRequestContext 转换 + 身份一致性 | Context Adapter（D-9） |
| admission_decision/reason_code 三值映射 | 准入落库 |
| content_summary 为脱敏摘要（无原文） | 安全 |
| 迁移 upgrade/downgrade 往返 + schema 对照（含 5 索引/CHECK） | 迁移 |

### L2（麒麟 VM，人工操作清单，不声称已执行）
- `alembic upgrade head` + `.schema` 对照（source_events 表 + 5 索引 + 全局 UNIQUE + CHECK）
- systemd 部署后 `stat` 数据目录 0700 / DB 0600
- 真实 CLI 事件写入 → 落库 + 幂等回放 + 跨用户拒绝 + 指纹标记（uds_client）
- 服务日志扫描：无正文/PII 泄漏（复用 JSON 日志探针）

---

## 九、技术债关联

| TD | 处置 |
|---|---|
| TD-D4D-001（Outbox consumer 未接线） | 保持 Open；processing_status 只到 extracting；指纹去重仅落标记（dedup_group/duplicate_of）不消费 |
| TD-D4D-002/003 | 保持 Open（不涉及本层） |
| TD-028 | 已由 PR #68 关闭（真实 IntegrityError 竞态测试） |
| 新增候选 | 事件指纹窗口阈值（24h）如后续需可调，登记参数化 TD（指纹窗口关闭时 `dedup.fingerprint_window_hours=0`） |

---

## 十、签署与落地流程

1. 本文档 + ADR-013（source_events 表设计，FRZ-DB-001 扩展）+ ADR-014（event.ingest，FRZ-IPC-007 扩展）提交 D 决策（周子腾）
2. Reviewer E（谢嘉然）**再次签署**（Review #83 已 REWORK，v2 修订后重提）
3. 回写 `D4_DB_INITIAL_DESIGN_FREEZE_20260817.md`（FRZ-DB-001 扩展节）与 `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-007 路由表）
4. 任务卡定稿（含验收标准）→ 开发分支（基于 PR #67/#68 合并后的 main @ fca8a87）
5. 实现 + L0/L1 → PR → 麒麟 L2 证据 → 台账 R35 勾选

---

## 十一、决策状态与待澄清缺口（v0.3 更新）

**D 已确认（2026-08-31，v2 重冻结，按 Review #83）**：

- [x] 开启新分支 `feat/d6d-event-persistence`
- [x] D-1：全局 `UNIQUE(event_id)`（对齐 D3 全局唯一）
- [x] D-4：指纹去重改「保留事件 + 标记 duplicate_of/dedup_group」，不丢真实事件
- [x] D-5：processing_status 停 `extracting`，不写 extracted
- [x] D-6：source_events 独立事务，不接 outbox
- [x] D-7：本版包含 handler（`event.ingest`，ADR-014）
- [x] D-8：consent_scope=none 由 D 轨 handler 前置 REJECT（不依赖 E 轨）
- [x] D-9：身份可信源 = 宿主注入，Context Adapter 冻结于 ADR-014

**仍待确认**：

1. D-3：准入抽取范围集合是否确有审计落库需求（决定是否加 JSON 扩展列）——建议不落，E 轨策略可重放；
2. 事件保留策略（TTL/清理）是否属本版范围（建议登记 TD 不阻塞）；
3. **Reviewer E 复核 v2 修订**：ADR 编号重排（012→013 / 013→014）、敏感强制 NULL、payload flat、schema_version 精确 0.1、Context Adapter。

**后续流程**：ADR-013（source_events 表设计）+ ADR-014（event.ingest 路由）→ D 决策确认 v2 + Reviewer E 再签 → 任务卡定稿 → 代码实现。
