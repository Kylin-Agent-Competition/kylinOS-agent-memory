# D6-D 多源事件持久化契约规划（草案 v0.2）

- **编制日期**：2026-08-31
- **编制人**：opencode（D 轨开发 Agent）
- **状态**：DRAFT v0.2 — D 已确认三点（① 开启新分支；② 指纹窗口不得强性能开销；③ D-7 本版含 handler），待 Reviewer E 确认后转正式契约（ADR-012/013 流程）
- **对照基线**：main @ `4926345`（PR #65 合并后）；`docs/day10/05_d5d_task_list_20260826.md`；`deliverables/D4_DB_INITIAL_DESIGN_FREEZE_20260817.md`（FRZ-DB-001 v1.3 + ADR-011 扩展）；`docs/day3/11_os_agent_event_contract_v1.md`（D3-C FROZEN_CANDIDATE）；E 轨 D6 `docs/day6/day6-e-01-source-quality-admission-policy-v1.md`

---

## 一、背景与目标（台账 R35 / D6-D）

D5-D（R30）已打通 Gateway→SQLite→Outbox 写链路（PR #65）。D6-D 承接「多源接入、质量与安全」的 **D 轨持久化职责**：

1. **持久化 SourceEvent、授权、指纹和幂等键** —— 把统一事件入口（A 轨 EventPipeline 输出 + E 轨准入结果）落为结构化真源；
2. **实现日志脱敏、目录权限和跨用户 Repository 约束** —— 安全红线落库与可审计；
3. **完成重复事件和事务失败测试** —— 幂等/一致性证据。

交付边界：**事件持久化层**（表 + 迁移 + Repository + 事务语义 + 测试），不接 Vector consumer（TD-D4D-001 保持 Open），不改 IPC 协议。

---

## 二、范围与禁止修改范围

### 允许修改
- `memory-service/db/schema.py`（新增 source_events 表，既有表定义不动）
- `memory-service/db/repositories.py`（新增事件 Repository 函数）
- `memory-service/db/uow.py`（如需要新增事件事务封装，复用现有模式）
- `migrations/versions/20260831_add_source_events.py`（新增迁移，ADR-007 命名）
- `memory-service/domain/enums.py`（如需要补充事件持久化枚举，优先复用 pipeline.schemas）
- 新增测试 `memory-service/tests/test_source_events_d6d.py`
- 契约文档（本文档 + ADR-012 + 冻结文档回写）

### 禁止修改（红线）
- 不修改冻结 FRZ-IPC-001~007（IPC/envelope/错误码域）
- 不修改 FRZ-DB-001 既有 5 张表定义（conversations/turns/memory_entries/outbox/idempotency_cache）及既有索引/触发器/FTS5
- 不修改 `pipeline/`、`providers/`、`security/source_admission.py`、`service/candidate_governance.py`、`gateway/`、`embedding/`、`retrieval/`、`observability/` 既有实现（日志脱敏复用 observability PII filter，不重写）
- 不接 Outbox consumer（TD-D4D-001 保持 Open；不假装成功）
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

### 3.2 Handler 输入契约（D-7 已确认：本版包含 handler）

新增 IPC 写方法 `event.ingest`（**ADR-013**：FRZ-IPC-007 路由表扩展，与 ADR-010 同模式）：

- **输入**：原始事件 dict（对齐 A 轨 `EventPipeline.process(raw)` 输入，即 `MemorySourceEvent` 字段集），envelope 含 `trace_id/request_id/deadline_ms`（FRZ-IPC-006）
- **编排**：`EventPipeline.process(raw)`（清洗+评分+指纹，复用不改）→ `SourceAdmissionPolicy.evaluate(result, ctx)`（准入，复用不改）→ `source_events` 落库 + 可选 outbox 入队（同事务）
- **注册策略**：production 默认**不注册**（BLOCKED_BY_HOST_MAPPING，与 ADR-010 一致）；validation/test profile 显式注册
- **错误语义**：FRZ-IPC-002 五错误码（非法载荷 INVALID_REQUEST / 内部异常 INTERNAL_ERROR / 未注册 UNSUPPORTED_METHOD）
- 不修改 `pipeline/`、`security/`、`gateway/registry.py` 冻结路由表以外内容（路由新增走 ADR-013 签署）

### 3.3 明确不落库
- **用户/助手正文原文**（原文隔离红线 [02 §4.1]）：只落 `content_summary`（脱敏）+ `raw_payload_ref`/`source_reference`（受控引用）
- 敏感载荷原文、API 密钥/令牌/口令（写入边界拒绝，A 轨 sensitive 已标记）
- `allowed_extraction_kinds`（准入的抽取范围集合）——如需审计可落 JSON 到扩展列，本版不落（控制范围，决策点 D-3）

---

## 四、DB 表设计（新增 `source_events`，FRZ-DB-001 扩展）

### 4.1 表定义（草案）

```sql
CREATE TABLE source_events (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                  TEXT    NOT NULL,                -- 隔离键，禁止正文推断
    event_id                 TEXT    NOT NULL,                -- 事件级唯一键（宿主生成）
    actor_id                 TEXT    NOT NULL,
    session_id               TEXT    NOT NULL,
    turn_id                  TEXT,
    tool_call_id             TEXT,
    source_type              TEXT    NOT NULL,                -- 七值枚举（pipeline.schemas）
    event_type               TEXT    NOT NULL,                -- 三值枚举
    schema_version           TEXT    NOT NULL,
    trace_id                 TEXT,
    source_reference         TEXT,                            -- 受控引用，非正文
    raw_payload_ref          TEXT,                            -- 受控引用，非正文
    content_summary          TEXT,                            -- 脱敏摘要，非原文
    idempotency_key          TEXT    NOT NULL,
    consent_scope            TEXT    NOT NULL,                -- 授权字段
    source_business_status   TEXT    NOT NULL,                -- 八值
    sensitivity              TEXT    NOT NULL,                -- 五级
    is_sensitive_matched     INTEGER NOT NULL DEFAULT 0,
    should_ignore            INTEGER NOT NULL DEFAULT 0,
    payload_security_checked INTEGER NOT NULL DEFAULT 0,
    memory_type              TEXT,
    occurred_at              TEXT    NOT NULL,                -- aware UTC ISO8601
    captured_at              TEXT    NOT NULL,                -- aware UTC ISO8601
    content_fingerprint      TEXT,                            -- 重复检测
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
| `uq_source_events_user_event` | **UNIQUE(user_id, event_id)** | 事件级幂等 + 跨用户隔离双重限制（[02 §16.6]） |
| `idx_source_events_user_created` | (user_id, created_at) | 按用户时间线查询/审计 |
| `idx_source_events_fingerprint` | (user_id, content_fingerprint) | 重复事件检测 |
| `idx_source_events_status` | (user_id, processing_status) | 处理状态扫描 |

### 4.3 迁移
- 文件：`migrations/versions/20260831_add_source_events.py`（ADR-007 命名 `YYYYMMDD_<desc>.py`）
- upgrade：CREATE TABLE + 索引；downgrade：DROP TABLE（新表无既有数据依赖，可整表回滚）
- 独立 revision，不触碰 `001_initial_schema` / `20260826_add_trace_id` 既有迁移

---

## 五、关键决策点（待 D 决策 / Reviewer E 确认）

| # | 决策点 | 推荐方案 | 备选 | 理由 |
|---|---|---|---|---|
| D-1 | event_id 唯一键粒度 | **UNIQUE(user_id, event_id)** ✅ D 已确认 | 全局 UNIQUE(event_id) | 跨用户隔离在索引层双重限制；防 B 复用 A 的 event_id 污染 [02 §16.6] |
| D-2 | 幂等键与 idempotency_cache 关系 | source_events 自带 `idempotency_key` 列 + 应用层查重；**不新建**第二套幂等缓存表 | 复用 idempotency_cache | 事件级幂等与 IPC 请求级幂等分层；避免耦合 D5-D 已冻结语义 |
| D-3 | 准入抽取范围（allowed_extraction_kinds）是否落库 | **本版不落**（仅落 decision + reason_code） | JSON 扩展列 | 控制范围；审计可用 decision/reason_code 复原，抽取范围由 E 轨策略重放 |
| D-4 | 重复事件判定窗口 | **保留 24h 窗口，但性能约束已确认**：同 user_id + 同 content_fingerprint + 同 source_type 且 `captured_at >= now-24h` → 重复（跳过并返回既有记录） | 仅 UNIQUE(event_id)（窗口关闭降级路径） | 实现为 `idx_source_events_fingerprint` 索引点查 + 时间过滤（O(logN+k)，非全表扫描、无内存集合、无外部服务）；**若 L1/L2 实测写路径开销超标，提供配置开关 `dedup.fingerprint_window_hours=0` 关闭，退化为仅 event_id 幂等** |
| D-5 | processing_status 终态 | 本版推进到 `extracted`；`embedded/stored` 留待 consumer 接线（TD-D4D-001） | 直接到 stored | 不假装成功；consumer 未接线不得标 stored |
| D-6 | 事务边界 | 事件落库与（可选）outbox 索引任务入队**同事务**（复用 UoW 模式） | 事件落库独立事务 | 与 D5-D 写链路一致；失败整体回滚 |
| D-7 | 事件入口 handler | **本版包含 handler** ✅ D 已确认：`event.ingest` IPC 写方法（ADR-013 路由扩展，production 默认不注册）+ gateway handler 编排 pipeline→admission→落库 | 仅 repository 层 | 用户指示本版自建 handler，不等 D6-C；路由新增走 ADR-013 冻结流程，不破坏 FRZ-IPC-007 既有条目 |

---

## 六、错误语义（复用冻结域，不新增错误码）

| 场景 | 行为 | 映射 |
|---|---|---|
| 事件已存在（同 user+event_id） | 返回既有记录，不重复插入（幂等命中） | 正常路径，非错误 |
| 同指纹窗口重复 | 返回既有记录（D-4） | 正常路径，非错误 |
| SQLITE_BUSY（busy_timeout 到期） | 抛 `DatabaseLockedError`，由调用方降级 | FR-DB-003 既有语义 |
| 跨用户复用 event_id / session_id | 抛 `EventOwnershipError`（新增，仿 `ConversationOwnershipError`） | handler 转 INVALID_REQUEST（不回显标识） |
| 校验失败（字段/枚举非法） | Pydantic ValidationError → 结构化错误 | 既有模式 |

---

## 七、安全边界（写入与检索两道）

1. **用户隔离**：所有查询强制 `user_id` 过滤（Repository 层，[02 §16.6]）+ `uq_source_events_user_event` 索引层双重限制；
2. **原文隔离**：正文/敏感载荷不落库、不入日志；只落脱敏摘要 + 受控引用；
3. **授权落库**：`consent_scope` 随事件持久化；`none` 授权事件不进入提取（E 轨准入已 REJECT，本层仅持久化决策结果）；
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
| 事件落库成功 + 字段映射完整性 | 正向 |
| 同 (user_id, event_id) 重复 → 幂等返回既有记录 | 幂等 |
| 同指纹 24h 窗口重复 → 跳过（D-4） | 重复检测 |
| 跨用户查询隔离（B 查不到 A 的事件） | 隔离 |
| 跨用户复用 event_id → EventOwnershipError | 隔离负向 |
| 事件落库 + outbox 入队同事务失败 → 整体回滚 | 事务失败 |
| 迁移 upgrade/downgrade 往返 + schema 对照（含索引/CHECK） | 迁移 |
| admission_decision/reason_code 三值映射 | 准入落库 |
| content_summary 为脱敏摘要（无原文） | 安全 |

### L2（麒麟 VM，人工操作清单，不声称已执行）
- `alembic upgrade head` + `.schema` 对照（source_events 表 + 4 索引 + CHECK）
- systemd 部署后 `stat` 数据目录 0700 / DB 0600
- 真实 CLI 事件写入 → 落库 + 幂等回放 + 跨用户拒绝（uds_client）
- 服务日志扫描：无正文/PII 泄漏（复用 JSON 日志探针）

---

## 九、技术债关联

| TD | 处置 |
|---|---|
| TD-D4D-001（Outbox consumer 未接线） | 保持 Open；processing_status 只到 extracted |
| TD-D4D-002/003 | 保持 Open（不涉及本层） |
| TD-028 | 已由 PR #68 关闭（真实 IntegrityError 竞态测试） |
| 新增候选 | 事件指纹窗口阈值（24h）如后续需可调，登记参数化 TD |

---

## 十、签署与落地流程

1. 本文档 + ADR-012（source_events 表设计，FRZ-DB-001 扩展）提交 D 决策（周子腾）
2. Reviewer E（谢嘉然）签署
3. 回写 `D4_DB_INITIAL_DESIGN_FREEZE_20260817.md`（FRZ-DB-001 扩展节）
4. 任务卡定稿（含验收标准）→ 开发分支（基于 PR #67/#68 合并后的 main）
5. 实现 + L0/L1 → PR → 麒麟 L2 证据 → 台账 R35 勾选

---

## 十一、决策状态与待澄清缺口（v0.2 更新）

**D 已确认（2026-08-31）**：

- [x] 开启新分支 `feat/d6d-event-persistence`
- [x] D-1：UNIQUE(user_id, event_id)
- [x] D-4：24h 指纹窗口保留，但性能约束成立（索引点查，非强开销；超标可关窗降级）
- [x] D-7：本版包含 handler（`event.ingest`，ADR-013）

**仍待确认**：

1. D-3：准入抽取范围集合是否确有审计落库需求（决定是否加 JSON 扩展列）——建议不落，E 轨策略可重放；
2. 事件保留策略（TTL/清理）是否属本版范围（建议登记 TD 不阻塞）。

**后续流程**：ADR-012（source_events 表设计）+ ADR-013（event.ingest 路由）→ D 决策 + Reviewer E 签署 → 任务卡定稿 → 代码实现。
