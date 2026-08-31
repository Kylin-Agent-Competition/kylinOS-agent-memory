# ADR-014：新增 `event.ingest` IPC 写方法（FRZ-IPC-007 / D6-D 扩展）

- **状态**：✅ D 已决策（2026-08-31，方案 A）；REWORK 修订 v3（按 Review #83 Reviewer E 第三轮意见重冻结）；待 Reviewer E 签署
- **日期**：2026-08-31（v3 修订同日）
- **决策人**：周子腾（D）｜**Reviewer**：E（谢嘉然，待签）
- **责任轨道**：D（IPC）为主，A/E 协作（编排现有 pipeline / admission，不复制真源）
- **决策版本**：`event-ingest-method-v3`
- **适用范围**：FRZ-IPC-007 顶层方法路由表；关联 `docs/adr/013-source-events-table.md`（落库表）、`memory-service/pipeline/schemas.py`（MemorySourceEvent 输入真源）、`memory-service/security/source_admission.py`（准入）、FRZ-IPC-002/005/006、ADR-010（turn.finalized 先例）、ADR-013

> **v2 修订摘要（Review #83 REWORK 第一轮处置）**：① payload 统一为 **flat**（对齐 MemorySourceEvent，删除 `payload.metadata.*` 嵌套口径）；② 新增 Gateway `RequestContext` → `ServiceRequestContext` 转换步骤与身份可信源冻结；③ `consent_scope=none` 由 D 轨 handler 前置 REJECT；④ 指纹去重改"保留事件+标记"；⑤ event_id 对齐全局唯一（ADR-013）；⑥ 编排删除 outbox 同事务表述；⑦ schema_version 仅接受精确 `0.1`；⑧ ADR 编号从 013 重排为 014。

> **v3 修订摘要（Review #83 Reviewer E 第三轮意见处置）**：① event_id 冲突区分「幂等重放 vs identity collision」——immutable identity 一致返回首次持久化结果（含既有 admission），不一致抛 `EventIdentityConflict` → `INVALID_REQUEST`（HIGH-01）；② 可信身份文案修正——payload 身份仅属事件声明，非独立可信身份源，「与 envelope 请求级身份一致」为不可实现表述删除；production ACTIVE 前必须以独立 trusted host identity + fail-close 比对为硬门禁（MEDIUM-02）；③ `schema_version` 界定为 event.ingest 的 **IPC required override**，handler 在校验前显式检查 payload 包含该字段（MEDIUM-04）；④ 响应区分 `duplicate_reason=idempotent_replay / content_duplicate`（MEDIUM-06）；⑤ 落库 `processing_status` 首次一律 `pending`，REJECT/AUDIT_ONLY 不落 extracting（MEDIUM-01）。

---

## 背景

1. **FRZ-IPC-007 冻结顶层方法路由**（`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:25`）：活跃 `echo / health / memory.retrieve`；写方法仅 `turn.finalized`（ADR-010，标 `CANDIDATE / BLOCKED_BY_HOST_MAPPING`）。
2. **D6-D（台账 R35）需要统一事件入口**：多源事件（ToolExecutionEvent、行为事件、ManualConfigEvent、完整聊天回合）需经 Gateway 进入 `source_events` 持久化（ADR-013）。`turn.finalized` 是**回合收尾专用**写方法，不能承载任意来源事件（语义混淆）。
3. **输入真源已存在**：A 轨 `MemorySourceEvent`（`pipeline/schemas.py`，E 轨 Schema v0.1 §3.1 落地）为外部输入模型（校验拒绝缺字段/类型错/未知高风险字段）；`EventPipeline.process(raw)` 输出 `NormalizedEvent + QualityScore`；E 轨 `SourceAdmissionPolicy.evaluate(result, ctx)` 输出 `SourceAdmissionResult`（ALLOW_EXTRACTION / AUDIT_ONLY / REJECT）。注意：D3 契约总体为 `CANDIDATE_FOR_FREEZE`，部分 host mapping 仍 pending——本文按既有实现消费，**不声称输入模型已冻结/宿主可用**。
4. **D-7 已确认（2026-08-31）**：D6-D 本版包含 handler（不等 D6-C 合并）。
5. **activation 先例**：ADR-010 采用「production 默认不注册 → UNSUPPORTED_METHOD；test/validation profile 显式注册」；event.ingest 沿用同模式（事件来源 C 轨 Hook/Adapter 未就绪 → `BLOCKED_BY_HOST_MAPPING`）。

---

## 候选方案

### 方案 A：新增 `event.ingest` 方法（本 ADR 决策）

FRZ-IPC-007 路由表新增写方法 `event.ingest`，payload 对齐 A 轨 `MemorySourceEvent` 字段集；Gateway handler 编排：`EventPipeline.process`（清洗+评分+指纹，复用不改）→ D 轨 consent 前置判定 → `SourceAdmissionPolicy.evaluate`（准入，复用不改）→ `source_events` 落库（ADR-013，独立事务）；`turn.finalized` 保持专用语义不动。

优点：

- 与 A 轨输入模型 / E 轨准入策略字段天然对齐，零复制真源；
- 单方法覆盖全部硬数据源事件（Tool / 行为 / 手动配置 / 聊天回合），D6-C 接入时只改 C 侧调用方，不改服务端契约；
- 不触碰 `turn.finalized` 既有冻结语义与 ADR-010 指纹/upsert 规则。

缺点：

- 冻结路由表新增方法须走 ADR + D/E 签署流程（同 ADR-010 成本）。

### 方案 B：扩展 `turn.finalized` 承载所有事件

把任意来源事件都塞进 `turn.finalized` payload。

- **语义污染**：`turn.finalized` 是「回合收尾」事件（is_final=true 强制、host_turn_id upsert 匹配、resolver 正文解析），Tool 事件/手动配置无回合语义，硬塞会扭曲 ADR-010 已冻结的 upsert 矩阵与指纹字段；
- **结论**：否决。

### 方案 C：事件不经 IPC，由 C 轨 Hook 进程内直写 DAO

- 破坏「IPC Gateway → Application Service」分层（ADR-009 socket ownership / 统一 UDS 入口口径）；
- Hook 与 Memory Service 不同进程，无法跨进程直调 Python DAO；
- **结论**：否决。

---

## 决策

选择方案 A：`event-ingest-method-v3`。**FRZ-IPC-007 路由表新增写方法 `event.ingest`（payload = A 轨 `MemorySourceEvent` 字段形成的 IPC 映射契约），Gateway handler 编排 `EventPipeline.process` → D 轨 consent 前置判定 → `SourceAdmissionPolicy.evaluate` → `source_events` 落库（ADR-013 表）；`turn.finalized` 保持专用语义不动；production 默认不注册（标 `CANDIDATE / BLOCKED_BY_HOST_MAPPING`），test/validation profile 显式注册。**

本 ADR 冻结范围 = **D 轨 IPC 映射契约 + 编排语义**；A 轨 `MemorySourceEvent` / E 轨 `SourceAdmissionResult` 对象状态**不随本 ADR 改变**（如实标注：代码模型已实现，契约总体 CANDIDATE_FOR_FREEZE，不写成已冻结/宿主可用）。

> **v2 修订摘要（Review #83 REWORK 第一轮处置）**：① payload 统一为 **flat**（对齐 MemorySourceEvent，删除 `payload.metadata.*` 嵌套口径）；② 新增 Gateway `RequestContext` → `ServiceRequestContext` 转换步骤与身份可信源冻结；③ `consent_scope=none` 由 D 轨 handler 前置 REJECT；④ 指纹去重改"保留事件+标记"；⑤ event_id 对齐全局唯一（ADR-013）；⑥ 编排删除 outbox 同事务表述；⑦ schema_version 仅接受精确 `0.1`；⑧ ADR 编号从 013 重排为 014。

> **v3 修订摘要（Review #83 Reviewer E 第三轮意见处置）**：① event_id 冲突区分「幂等重放 vs identity collision」（HIGH-01）；② 可信身份文案修正、payload 身份仅属声明（MEDIUM-02）；③ schema_version 界定为 event.ingest 的 IPC required override（MEDIUM-04）；④ 响应区分 `duplicate_reason`（MEDIUM-06）；⑤ 落库 `processing_status` 首次一律 `pending`（MEDIUM-01）。

### IPC 契约定义（映射契约）

- **路由**：`event.ingest`（写方法，加入冻结路由表）
- **payload**（JSON `snake_case`，**flat 结构**逐字段复用 A 轨 `MemorySourceEvent` required/optional 语义；`MemorySourceEvent.model_validate` 为 flat + `extra="forbid"`，**禁止嵌套 `payload.metadata.*` 口径**）：

| JSON 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | string | ✅ | **仅接受精确 `"0.1"`**（对齐 A 轨 MemorySourceEvent 默认值 / E 轨 Schema v0.1），`0.2`/`1.x`/`not-a-version` → INVALID_REQUEST——注意与 turn.finalized 的 schema_version 语义差异（后者对齐 C 轨事件契约 v1 接受 `1.x`）；**相对 MemorySourceEvent 属 IPC required override**（模型 `schema_version: str = "0.1"` 允许缺省，本方法要求显式必填，见「校验」节）；校验落在 handler 层 |
| `event_id` | string | ✅ | 事件全局唯一身份；**不替代幂等键** |
| `user_id` | string | ✅ | 来自可信宿主注入（见「Context 适配与身份真源」）；**禁止从正文推断** |
| `actor_id` | string | ✅ | 实际发起者（SEC-UI-07），来自可信宿主 |
| `session_id` | string | ✅ | 来自可信宿主 |
| `trace_id` | string | 可选 | 若提供必须等于 IPC envelope.trace_id，不一致 → `INVALID_REQUEST` |
| `source_reference` | string | 可选 | 受控引用，不存正文 |
| `raw_payload_ref` | string | 可选 | 受控引用，不存正文 |
| `consent_scope` | string | 默认 | `memory_only` / `memory_and_analytics` / `none`（默认 `memory_only`） |
| `idempotency_key` | string | ✅ | 写方法必填（MemorySourceEvent 冻结必填）；权威值见「幂等」节 |
| `occurred_at` | ISO 8601 | ✅ | 事件发生时间，规范输出 UTC 毫秒 |
| `captured_at` | ISO 8601 | ✅ | 采集时间，规范输出 UTC 毫秒 |
| `source_type` | string | ✅ | 七值：chat/tool_result/manual_config/recollect/file/meeting/voice |
| `event_type` | string | ✅ | 三值：user_message/agent_response/system_message |
| `source_business_status` | string | 默认 | 八值，默认 `raw` |
| `memory_type` | string | 可选 | short_term/medium_term/long_term/ephemeral |
| `turn_id` | string | 可选 | 宿主回合引用 |
| `tool_call_id` | string | 条件 | `source_type=tool_result` 时必填 |
| `content_summary` | string | 可选 | **脱敏摘要**（非原文；敏感/安全类强制 NULL，见 ADR-013；普通质量型 AUDIT_ONLY 保留已脱敏摘要） |
| `sensitivity` | string | 默认 | 五级，默认 `none` |
| `is_sensitive_matched` | boolean | 默认 | 默认 false |
| `should_ignore` | boolean | 默认 | 默认 false（D3 安全契约） |
| `payload_security_checked` | boolean | 默认 | 默认 false（H1-mini） |
| `requires_embedding` | boolean | 默认 | 默认 true |
| `has_structured_payload` | boolean | 默认 | 默认 false |
| `language_tag` | string | 可选 | — |

- **Handler 编排（固定顺序，复用不改 + D 轨前置判定）**：
  1. **payload 显式字段预检**（MEDIUM-04）：确认 raw payload **显式包含** `schema_version`（`["schema_version"] not in raw` → `INVALID_REQUEST`）且值为精确 `"0.1"`，再调用 `MemorySourceEvent.model_validate`——避免模型默认值 `"0.1"` 吞掉"缺失"导致无法区分显式提供与缺省；
  2. `EventPipeline.process(raw)`：清洗（校验+时间/状态标准化）→ 敏感标记 → 内容指纹 → 六维质量评分 → 安全/质量 Gate；输出 `PipelineResult`；校验失败 → `EventValidationError` → `INVALID_REQUEST`（safe_message 固定英文，不回显原值）；
  3. **事件级冲突处置**（HIGH-01，先于准入）：按 `user_id + event_id` 点查既有行（`get_source_event_by_event_id`）：
     - 无既有行 → 继续 4；
     - 有既有行 + **immutable identity 一致**（`user_id`/`source_type`/`event_type`/`occurred_at`/`content_fingerprint` 全等）→ **幂等重放**：不再执行 consent/admission/落库，**返回首次持久化记录完整结果**（`source_event_id` + 既有 `admission_decision`/`admission_reason_code` + `duplicate=true` + `duplicate_reason='idempotent_replay'`）；不重新形成事件事实、不返回新请求重算结果；
     - 有既有行 + **immutable identity 不一致** → 抛 `EventIdentityConflict` → `INVALID_REQUEST`（不回显标识）；不得按普通 duplicate 返回旧行；
  4. **D 轨 consent 前置判定**（不依赖 E 轨）：`event.consent_scope == "none"` → 直接 REJECT（`consent_not_granted`）随事件落库（ADR-013），不继续抽取放行；这一判定在 handler 层实现，不改 `security/source_admission.py`；
  5. `SourceAdmissionPolicy.evaluate(result, ctx_svc)`：fail-closed 三值决策（类型准入 → 用户隔离 → 安全红线 → 生命周期保守 → 质量 Gate → 业务状态范围）；**REJECT / AUDIT_ONLY 不是 IPC 错误**，是正常业务决策，随事件落库；
  6. `source_events` 落库（ADR-013 表）：`processing_status='pending'`（MEDIUM-01，REJECT/AUDIT_ONLY 亦为 pending，不落 extracting），`admission_decision/reason_code` 取自准入结果；指纹重复 → **仍插入新行**（event_id 必不相同）并标记 `duplicate_of`/`dedup_group`（不丢弃真实事件），响应 `duplicate=true` + `duplicate_reason='content_duplicate'` + `duplicate_of`；同 event_id 冲突已在步骤 3 处置。

- **Context 适配与身份真源**（Review #83 意见三 + 第三轮 MEDIUM-02）：
  - Gateway 收到 `gateway.registry.RequestContext`（无 user_id/actor_id 注入，见 `server.py`）；`SourceAdmissionPolicy.evaluate` 要求 `service.contracts.ServiceRequestContext`（fail-closed `invalid_context`）。**必须在 handler 内新增显式转换步骤**：`RequestContext → ServiceRequestContext`（取值见下）。
  - **可信身份边界（v3 修正）**：**当前 test/validation 状态下，payload 中的 `user_id/actor_id/session_id` 仅属"事件声明（declaration）"，不是独立可信身份源**；`payload.user_id → Event.user_id` 与 `payload.user_id → ServiceRequestContext.user_id` 再由 `ctx_svc.user_id == event.user_id` 比对，**等价于 `payload.user_id == payload.user_id`，属自证，不是真实可信身份校验**——本 ADR 不把该比对描述为可信身份认证。
  - **envelope 无用户身份字段**：当前 IPC envelope 顶级没有 `user_id/actor_id/session_id`，故**删除**「与 envelope 请求级身份一致」的不可实现表述；若未来 envelope 增加请求级身份，须另行 ADR 冻结。
  - **production ACTIVE 硬门禁**：生产激活前必须满足——`独立 trusted host identity`（宿主注入的身份对象，非 payload）→ 注入 `RequestContext / extras / host identity object` → handler 用它构造 `ServiceRequestContext`，随后执行**真实的 fail-close 比对**：`trusted_identity.user_id vs payload.user_id`，不一致 → 拒绝。**即：`payload.user_id` 只能是待验证声明，不得同时作为可信上下文来源。**本项为 ACTIVE 前置，本版维持 `BLOCKED_BY_HOST_MAPPING` 未激活（见 activation 节），**不声称宿主身份已真实认证**。
  - **trace_id 唯一真源 = IPC envelope 顶级**；payload 若带 trace_id 必须相等，否则 `INVALID_REQUEST`（同 ADR-010）。
  - 用户隔离检查使用**注入的身份值**（`ctx_svc.user_id == event.user_id`，SourceAdmissionPolicy 既有逻辑），不得拿不可信异源值做隔离；test/profile 下该比对以「声明内部自洽」为最低要求并在文档标注为自证（见上），不得上浮为宿主认证证据。

- **校验与错误映射**：
  - payload 校验失败（Pydantic ValidationError / EventValidationError）→ `INVALID_REQUEST`（safe_message 固定英文，不回显原值）；
  - envelope 校验失败沿用 Gateway `validate_request`（PROTOCOL_ERROR / INVALID_REQUEST，FRZ-IPC-002/006）；
  - 内部异常 → `INTERNAL_ERROR`（safe_error_code，不泄漏 traceback/正文）；
  - 未注册方法 → `UNSUPPORTED_METHOD`（production 默认注册表不含 `event.ingest`）。

- **幂等**：
  - **权威 idempotency_key 合并规则**：取 IPC envelope 顶级字段（FRZ-IPC-006）→ 未提供则取 **payload 顶级 `idempotency_key`**（flat，无 `payload.metadata.*`）→ 两者同提供且不一致 → `INVALID_REQUEST`（对齐 ADR-010 合并规则）；
  - **请求级幂等**：三元组 `(user_id, session_id, 权威 idempotency_key)` 走既有 `idempotency_cache`（FRZ-IPC-005 / ADR-006，TTL 24h）；命中 → 返回首次成功响应，不重复执行 pipeline/落库；失败请求不缓存；
  - **事件级冲突处置**（HIGH-01，见 Handler 编排步骤 3）：`UNIQUE(event_id)`（ADR-013 全局唯一索引）为 DB 约束兜底；应用层先按 `user_id + event_id` 点查 → **immutable identity 一致 = 幂等重放**（返回首次持久化 `source_event_id` + 既有 `admission_decision/reason_code` + `duplicate=true` + `duplicate_reason='idempotent_replay'`）；**不一致 = `EventIdentityConflict` → `INVALID_REQUEST`**（跨用户/跨 session 复用统一归入此）；不再采用「同 event_id → 一律返回既有记录（EventOwnershipError）」旧口径；
  - `event_id` **不替代** `idempotency_key`（保持 FRZ-IPC-005 / ADR-010 语义）。

- **activation 策略（事件来源未就绪时）**：
  - 采用 **方案 A + B**（同 ADR-010）：默认生产路由**不注册** `event.ingest`（`register_default_handlers` 不含它）→ 未注册即 `UNSUPPORTED_METHOD`；
  - FRZ-IPC-007 路由表将 `event.ingest` 标为 **`CANDIDATE / BLOCKED_BY_HOST_MAPPING`**，待 C 轨事件源（Hook/Adapter）就绪后升级 ACTIVE；
  - PR 用测试客户端 + 显式注册验证服务端写链路（测试态可注册）。

- **响应**（冻结 envelope：`status/data/server_ts`，ADR-005 不变）：
  - data = `{source_event_id, event_id, admission_decision, admission_reason_code, duplicate, duplicate_reason, duplicate_of}`
    - `source_event_id` = `source_events.id`（SQLite Integer PK）；**幂等重放时为首次既有记录 id**；指纹重复（content_duplicate）时为**新插入行 id**；
    - `event_id` = 请求 payload.event_id（回显）；
    - `admission_decision` / `admission_reason_code` = 本次准入结果；**幂等重放时为首次持久化的既有结果**（新请求不再重算准入，避免「Response 指向旧 SQLite 行但准入结果属于新请求」的真源不一致，HIGH-01）；
    - `duplicate` = boolean（重复事件标记，默认 false）；
    - **`duplicate_reason`**（MEDIUM-06，客户端确定性判别）：
      - `idempotent_replay`：同 event_id + immutable identity 一致 → 幂等重放，**没有新增 DB 行**，`source_event_id`/admission 来自首次记录；
      - `content_duplicate`：新事件已持久化，仅因 fingerprint 内容重复标记 `duplicate_of`（新增行，`processing_status='pending'`）；
      - `null`：首次事件，非重复。
    - `duplicate_of` = 指纹重复时指向首次同指纹 `id`（幂等重放/normal 时 null）。

### 变更控制

- `event.ingest` 为新增可选方法，属 FRZ-IPC-007 允许的「扩展范围」（回溯 `D4_IPC_PROTOCOL_FREEZE_20260807.md` §1.3 / §2.4 / §3 兼容新增，同 ADR-010）；
- 新增字段/方法/方法级必填约束走本次 ADR；已冻结 FRZ-IPC-001~006 字段/错误码/envelope **不得修改**；
- **v2 契约变更已按 Review #83 第一轮处置**：payload 统一 flat、schema_version 精确 0.1、consent 前置、Context Adapter 与身份真源、指纹保留+标记——均属本 ADR 冻结范围，回写路由表时一并记录。
- **v3 契约变更已按 Review #83 第三轮处置**：event_id 幂等重放 / identity collision 契约（HIGH-01）、可信身份文案修正 + ACTIVE 硬门禁（MEDIUM-02）、schema_version IPC required override（MEDIUM-04）、`duplicate_reason=idempotent_replay/content_duplicate`（MEDIUM-06）、processing_status 首次一律 pending（MEDIUM-01）——均属本 ADR 冻结范围，回写路由表时一并记录。

---

## 影响

### 架构影响

- 打通「多源事件 → Gateway → pipeline → 准入 → source_events」统一入口，与 ADR-005 envelope、ADR-006 幂等 PK、ADR-010 写方法模式、ADR-013 落库表一致；
- 不新增运行时组件，沿用 UDS + 长度前缀 JSON + 既有 pipeline/admission（零复制真源）；**本版不接线 outbox**（source_events 独立事务）。

### 开发影响

- `gateway/handlers.py` 新增 `event_ingest_handler`（编排 payload 显式字段预检 → pipeline → event_id 冲突处置 → consent 前置 → admission → repository；新增 `RequestContext → ServiceRequestContext` 显式转换函数）；
- `gateway/registry.py` 提供 `event.ingest` **显式注册 seam**（production default registry 不注册；test profile 显式注册）；
- `db/repositories.py` / `db/uow.py` 新增事件写入（ADR-013；`get_source_event_by_event_id` / `insert_source_event` 支持 immutable identity 比对与 `EventIdentityConflict`）；
- 不修改 `pipeline/`、`security/source_admission.py`、`service/candidate_governance.py`、`embedding/`、`retrieval/`；
- C 轨调用方（D6-C 统一事件入口）后续接入，不阻塞本 PR 服务端。

### 评测影响

- L1 契约测试覆盖：payload 缺 `schema_version` → INVALID_REQUEST（IPC required override）；pipeline 校验失败 → INVALID_REQUEST；schema_version 非 `0.1` → INVALID_REQUEST；consent_scope=none → REJECT 落库（consent_not_granted，`processing_status='pending'`）；准入 REJECT/AUDIT_ONLY 正常落库（非错误，均 `pending` 不落 extracting）；同 event_id + identity 一致 → 幂等重放返回首次记录完整结果（`duplicate=true, duplicate_reason='idempotent_replay'`）；同 event_id + identity 不一致 → EventIdentityConflict → INVALID_REQUEST；指纹重复 → 新行 + duplicate_of/dedup_group + `duplicate_reason='content_duplicate'`；跨用户复用 event_id → INVALID_REQUEST；高敏原文不出现于正文落库/日志/响应（BLOCKER 回归项）。

### 安全影响

- `content_summary` / `source_reference` / `raw_payload_ref` 只承载脱敏摘要或受控引用，不承载正文（原文隔离 `[02 §4.1]`）；**敏感命中强制 NULL**（ADR-013，仅敏感/安全类；普通质量型 AUDIT_ONLY 保留脱敏摘要）；
- `user_id` / `event_id` / `trace_id` 按非正文受控标识处理；错误消息 safe_message 不回显原文/用户 ID/凭据；
- 跨用户隔离：`user_id` 强制过滤 + `SourceAdmissionPolicy` `user_id` 比对 + ADR-013 `UNIQUE(event_id)` 全局唯一索引 + immutable identity 一致性（identity 冲突 → 拒绝）多重限制；
- consent_scope=none 在 D 轨 handler 前置 REJECT（不依赖 E 轨，消除授权语义缺口）；
- **可信身份边界（v3）**：`payload.user_id` 仅属声明，非独立可信身份源；test/validation 下 `ctx_svc.user_id == event.user_id` 为声明内部自洽（已如实标注，非宿主认证证据）；production ACTIVE 前须以独立 trusted host identity + fail-close 比对为硬门禁（MEDIUM-02）。

---

## 回滚与替代条件

若未来决定废弃 `event.ingest` 或改用其他事件入口，可经新 ADR 撤销本 ADR：删除路由表条目与 handler，`source_events` 表经 ADR-013 自身回滚流程处理；`turn.finalized` 语义不受影响；冻结回写 `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-007 路由表）恢复原状。

---

## 证据与限制

- `deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:25/27`（FRZ-IPC-007 路由表 + ADR-010 扩展先例）
- `docs/adr/010-turn-finalized-method.md`（写方法先例：payload 映射、幂等合并规则、activation A+B、CANDIDATE/BLOCKED_BY_HOST_MAPPING）
- `docs/adr/013-source-events-table.md`（落库表 + 事件级幂等全局唯一索引 + 指纹保留/标记）
- `memory-service/pipeline/schemas.py`（MemorySourceEvent 字段/枚举/校验，输入真源；D3 契约总体 CANDIDATE_FOR_FREEZE）
- `memory-service/pipeline/pipeline.py`（EventPipeline.process 编排）
- `memory-service/security/source_admission.py`（SourceAdmissionPolicy，三值决策）
- `memory-service/gateway/registry.py`、`gateway/server.py`（RequestContext 现状：无 user_id/actor_id 注入 → 需显式 Adapter）
- `memory-service/service/contracts.py`（ServiceRequestContext 结构）
- `docs/day6/day6-d-01-event-persistence-contract-plan-v0.3.md`（D6-D 契约规划，D-7/D-8/D-9 决策：本版含 handler + consent 前置 + Context Adapter）

本 ADR 为文档/契约决策，不新增 Runtime 事实。批准记录：**D（周子腾）2026-08-31 决策选方案 A，v2 按 Review #83 第一轮重冻结，v3 按第三轮意见修订**；**Reviewer E（谢嘉然）待签署**；签署后回写 `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-007 路由表）。
