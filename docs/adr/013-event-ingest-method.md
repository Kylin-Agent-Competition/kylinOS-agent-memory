# ADR-013：新增 `event.ingest` IPC 写方法（FRZ-IPC-007 / D6-D 扩展）

- **状态**：📝 草案（待 D 决策 + Reviewer E 签署）
- **日期**：2026-08-31
- **决策人**：周子腾（D）｜**Reviewer**：E（谢嘉然，待签）
- **责任轨道**：D（IPC）为主，A/E 协作（编排现有 pipeline / admission，不复制真源）
- **决策版本**：`event-ingest-method-v1`
- **适用范围**：FRZ-IPC-007 顶层方法路由表；关联 `docs/adr/012-source-events-table.md`（落库表）、`memory-service/pipeline/schemas.py`（MemorySourceEvent 输入真源）、`memory-service/security/source_admission.py`（准入）、FRZ-IPC-002/005/006、ADR-010（turn.finalized 先例）、ADR-012

---

## 背景

1. **FRZ-IPC-007 冻结顶层方法路由**（`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:25`）：活跃 `echo / health / memory.retrieve`；写方法仅 `turn.finalized`（ADR-010，标 `CANDIDATE / BLOCKED_BY_HOST_MAPPING`）。
2. **D6-D（台账 R35）需要统一事件入口**：多源事件（ToolExecutionEvent、行为事件、ManualConfigEvent、完整聊天回合）需经 Gateway 进入 `source_events` 持久化（ADR-012）。`turn.finalized` 是**回合收尾专用**写方法，不能承载任意来源事件（语义混淆）。
3. **输入真源已存在**：A 轨 `MemorySourceEvent`（`pipeline/schemas.py`，E 轨 Schema v0.1 §3.1 落地）为外部输入模型（校验拒绝缺字段/类型错/未知高风险字段）；`EventPipeline.process(raw)` 输出 `NormalizedEvent + QualityScore`；E 轨 `SourceAdmissionPolicy.evaluate(result, ctx)` 输出 `SourceAdmissionResult`（ALLOW_EXTRACTION / AUDIT_ONLY / REJECT）。
4. **D-7 已确认（2026-08-31）**：D6-D 本版包含 handler（不等 D6-C 合并）。
5. **activation 先例**：ADR-010 采用「production 默认不注册 → UNSUPPORTED_METHOD；test/validation profile 显式注册」；event.ingest 沿用同模式（事件来源 C 轨 Hook/Adapter 未就绪 → `BLOCKED_BY_HOST_MAPPING`）。

---

## 候选方案

### 方案 A：新增 `event.ingest` 方法（本 ADR 决策）

FRZ-IPC-007 路由表新增写方法 `event.ingest`，payload 对齐 A 轨 `MemorySourceEvent` 字段集；Gateway handler 编排：`EventPipeline.process`（清洗+评分+指纹，复用不改）→ `SourceAdmissionPolicy.evaluate`（准入，复用不改）→ `source_events` 落库（ADR-012，同事务）；`turn.finalized` 保持专用语义不动。

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

选择方案 A：`event-ingest-method-v1`。**FRZ-IPC-007 路由表新增写方法 `event.ingest`（payload = A 轨 `MemorySourceEvent` 字段形成的 IPC 映射契约），Gateway handler 编排 `EventPipeline.process` → `SourceAdmissionPolicy.evaluate` → `source_events` 落库（ADR-012 表）；`turn.finalized` 保持专用语义不动；production 默认不注册（标 `CANDIDATE / BLOCKED_BY_HOST_MAPPING`），test/validation profile 显式注册。**

本 ADR 冻结范围 = **D 轨 IPC 映射契约 + 编排语义**；A 轨 `MemorySourceEvent` / E 轨 `SourceAdmissionResult` 对象状态**不随本 ADR 改变**（保持既有 FROZEN/已实现状态）。

### IPC 契约定义（映射契约）

- **路由**：`event.ingest`（写方法，加入冻结路由表）
- **payload**（JSON `snake_case`，逐字段复用 A 轨 `MemorySourceEvent` required/optional 语义；`schema_version` 接受 `0.1`，主版本 != 0 拒为 INVALID_REQUEST——**注意与 turn.finalized 的 schema_version 语义差异**，后者对齐 C 轨事件契约 v1 接受 `1.x`）：

| 分组 | JSON 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| metadata | `schema_version` | string | ✅ | A 轨事件结构版本，接受 `0.1` |
| metadata | `event_id` | string | ✅ | 事件唯一身份；**不替代幂等键** |
| metadata | `user_id` | string | ✅ | 来自可信宿主；**禁止从正文推断** |
| metadata | `actor_id` | string | ✅ | 实际发起者（SEC-UI-07） |
| metadata | `session_id` | string | ✅ | 来自可信宿主 |
| metadata | `trace_id` | string | 可选 | 若提供必须等于 IPC envelope.trace_id，不一致 → `INVALID_REQUEST` |
| metadata | `source_reference` | string | 可选 | 受控引用，不存正文 |
| metadata | `raw_payload_ref` | string | 可选 | 受控引用，不存正文 |
| metadata | `consent_scope` | string | 默认 | `memory_only` / `memory_and_analytics` / `none` |
| metadata | `idempotency_key` | string | ✅ | 写方法必填（MemorySourceEvent 冻结必填）；权威值见「幂等」节 |
| metadata | `occurred_at` | ISO 8601 | ✅ | 事件发生时间，规范输出 UTC 毫秒 |
| metadata | `captured_at` | ISO 8601 | ✅ | 采集时间，规范输出 UTC 毫秒 |
| 事件 | `source_type` | string | ✅ | 七值：chat/tool_result/manual_config/recollect/file/meeting/voice |
| 事件 | `event_type` | string | ✅ | 三值：user_message/agent_response/system_message |
| 事件 | `source_business_status` | string | 默认 | 八值，默认 `raw` |
| 事件 | `memory_type` | string | 可选 | short_term/medium_term/long_term/ephemeral |
| 事件 | `turn_id` | string | 可选 | 宿主回合引用 |
| 事件 | `tool_call_id` | string | 条件 | `source_type=tool_result` 时必填 |
| 事件 | `content_summary` | string | 可选 | **脱敏摘要**（非原文） |
| 事件 | `sensitivity` | string | 默认 | 五级，默认 `none` |
| 事件 | `is_sensitive_matched` | boolean | 默认 | 默认 false |
| 事件 | `should_ignore` | boolean | 默认 | 默认 false（D3 安全契约） |
| 事件 | `payload_security_checked` | boolean | 默认 | 默认 false（H1-mini） |
| 事件 | `requires_embedding` | boolean | 默认 | 默认 true |
| 事件 | `has_structured_payload` | boolean | 默认 | 默认 false |
| 事件 | `language_tag` | string | 可选 | — |

- **handler 编排（固定顺序，复用不改）**：
  1. `EventPipeline.process(raw)`：清洗（校验+时间/状态标准化）→ 敏感标记 → 内容指纹 → 六维质量评分 → 安全/质量 Gate；输出 `PipelineResult`；校验失败 → `EventValidationError` → `INVALID_REQUEST`（safe_message 固定英文，不回显原值）；
  2. `SourceAdmissionPolicy.evaluate(result, ctx)`：fail-closed 三值决策（用户隔离 → 安全红线 → 生命周期保守 → 质量 Gate → 业务状态范围）；**REJECT / AUDIT_ONLY 不是 IPC 错误**，是正常业务决策，随事件落库；
  3. `source_events` 落库（ADR-012 表）：`processing_status='extracted'`，`admission_decision/reason_code` 取自准入结果；重复事件（UNIQUE(user_id, event_id) 冲突或指纹窗口命中）→ 返回既有记录，不重复插入。

- **校验与错误映射**：
  - payload 校验失败（Pydantic ValidationError / EventValidationError）→ `INVALID_REQUEST`（safe_message 固定英文，不回显原值）；
  - envelope 校验失败沿用 Gateway `validate_request`（PROTOCOL_ERROR / INVALID_REQUEST，FRZ-IPC-002/006）；
  - 内部异常 → `INTERNAL_ERROR`（safe_error_code，不泄漏 traceback/正文）；
  - 未注册方法 → `UNSUPPORTED_METHOD`（production 默认注册表不含 `event.ingest`）。

- **幂等**：
  - **权威 idempotency_key 合并规则**：取 IPC envelope 顶级字段（FRZ-IPC-006）→ 未提供则取 `payload.metadata.idempotency_key` → 两者同提供且不一致 → `INVALID_REQUEST`（对齐 ADR-010 合并规则）；
  - **请求级幂等**：三元组 `(user_id, session_id, 权威 idempotency_key)` 走既有 `idempotency_cache`（FRZ-IPC-005 / ADR-006，TTL 24h）；命中 → 返回首次成功响应，不重复执行 pipeline/落库；失败请求不缓存；
  - **事件级幂等**：`UNIQUE(user_id, event_id)`（ADR-012 索引）为 DB 约束兜底，重复写入返回既有记录（`duplicate: true`）；
  - `event_id` **不替代** `idempotency_key`（保持 FRZ-IPC-005 / ADR-010 语义）。

- **activation 策略（事件来源未就绪时）**：
  - 采用 **方案 A + B**（同 ADR-010）：默认生产路由**不注册** `event.ingest`（`register_default_handlers` 不含它）→ 未注册即 `UNSUPPORTED_METHOD`；
  - FRZ-IPC-007 路由表将 `event.ingest` 标为 **`CANDIDATE / BLOCKED_BY_HOST_MAPPING`**，待 C 轨事件源（Hook/Adapter）就绪后升级 ACTIVE；
  - PR 用测试客户端 + 显式注册验证服务端写链路（测试态可注册）。

- **响应**（冻结 envelope：`status/data/server_ts`，ADR-005 不变）：
  - data = `{source_event_id, event_id, admission_decision, admission_reason_code, duplicate}`
    - `source_event_id` = `source_events.id`（SQLite Integer PK）；重复命中时为既有记录 id；
    - `event_id` = 请求 payload.event_id（回显）；
    - `admission_decision` / `admission_reason_code` = 准入结果（回显，审计用）；
    - `duplicate` = boolean（重复事件标记，默认 false）。

### 变更控制

- `event.ingest` 为新增可选方法，属 FRZ-IPC-007 允许的「扩展范围」（回溯 `D4_IPC_PROTOCOL_FREEZE_20260807.md` §1.3 / §2.4 / §3 兼容新增，同 ADR-010）；
- 新增字段/方法/方法级必填约束走本次 ADR；已冻结 FRZ-IPC-001~006 字段/错误码/envelope **不得修改**。

---

## 影响

### 架构影响

- 打通「多源事件 → Gateway → pipeline → 准入 → source_events」统一入口，与 ADR-005 envelope、ADR-006 幂等 PK、ADR-010 写方法模式、ADR-012 落库表一致；
- 不新增运行时组件，沿用 UDS + 长度前缀 JSON + 既有 pipeline/admission（零复制真源）。

### 开发影响

- `gateway/handlers.py` 新增 `event_ingest_handler`（编排 pipeline → admission → repository）；
- `gateway/registry.py` 提供 `event.ingest` **显式注册 seam**（production default registry 不注册；test profile 显式注册）；
- `db/repositories.py` / `db/uow.py` 新增事件写入（ADR-012）；
- 不修改 `pipeline/`、`security/source_admission.py`、`service/candidate_governance.py`、`embedding/`、`retrieval/`；
- C 轨调用方（D6-C 统一事件入口）后续接入，不阻塞本 PR 服务端。

### 评测影响

- L1 契约测试覆盖：pipeline 校验失败 → INVALID_REQUEST；准入 REJECT/AUDIT_ONLY 正常落库（非错误）；幂等命中/冲突；事件级重复（UNIQUE 冲突返回既有 + duplicate=true）；跨用户复用 event_id → INVALID_REQUEST；正文不出现于日志/响应。

### 安全影响

- `content_summary` / `source_reference` / `raw_payload_ref` 只承载脱敏摘要或受控引用，不承载正文（原文隔离 `[02 §4.1]`）；
- `user_id` / `event_id` / `trace_id` 按非正文受控标识处理；错误消息 safe_message 不回显原文/用户 ID/凭据；
- 跨用户隔离：Repository 层 `user_id` 作用域 + ADR-012 复合唯一索引双重限制。

---

## 回滚与替代条件

若未来决定废弃 `event.ingest` 或改用其他事件入口，可经新 ADR 撤销本 ADR：删除路由表条目与 handler，`source_events` 表经 ADR-012 自身回滚流程处理；`turn.finalized` 语义不受影响；冻结回写 `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-007 路由表）恢复原状。

---

## 证据与限制

- `deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:25/27`（FRZ-IPC-007 路由表 + ADR-010 扩展先例）
- `docs/adr/010-turn-finalized-method.md`（写方法先例：payload 映射、幂等合并规则、activation A+B、CANDIDATE/BLOCKED_BY_HOST_MAPPING）
- `docs/adr/012-source-events-table.md`（落库表 + 事件级幂等索引）
- `memory-service/pipeline/schemas.py`（MemorySourceEvent 字段/枚举/校验，输入真源）
- `memory-service/pipeline/pipeline.py`（EventPipeline.process 编排）
- `memory-service/security/source_admission.py`（SourceAdmissionPolicy，三值决策）
- `docs/day6/day6-d-01-event-persistence-contract-plan-v0.2.md`（D6-D 契约规划，D-7 决策：本版含 handler）

本 ADR 为文档/契约决策，不新增 Runtime 事实。批准记录：**D（周子腾）待决策**；**Reviewer E（谢嘉然）待签署**；签署后回写 `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-007 路由表）。
