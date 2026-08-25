# D4 推进顺序 Checklist（Gateway→SQLite→Outbox + ID 统一 + health/结构化日志）

- **生成日期**：2026-08-24
- **适用轨道**：D（IPC / SQLite / Outbox / 发布）为主，E 审查
- **依据文档**：
  - `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md`（FRZ-IPC-001~007 + ALIGN-001~005）
  - `D4_IPC_PROTOCOL_CONSISTENCY_AUDIT_20260817.md`（代码偏离 file:line 证据）
  - `docs/adr/005-db-error-code-envelope.md`（ADR-005 方案 A 已生效）
  - `D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md`（5 表 + 索引 + FTS5 + Outbox 设计冻结）
- **状态**：Checklist 草稿，待推进执行

---

## 当前进度核查结论（2026-08-24）

| 任务 | 设计/契约冻结 | 代码实现 | 结论 |
|------|:---:|:---:|------|
| 1. Gateway→SQLite→Outbox | ✅ 已冻结 | ❌ 零实现 | 可启动，有 2 个前置待办（依赖声明 + 迁移约定） |
| 2. 统一 trace_id/request_id/event_id | ✅ 协议已冻结 | 🟡 部分（仅 embedding 回显） | 可推进，需先收口 3 处偏离（ALIGN-002/003/004） |
| 3. health + 结构化日志 | 🟡 health 冻结/日志未冻结 | 🟡 health 部分 / 结构化日志零 | health 可收口；结构化日志纯新增可推进 |

---

## 依赖关系总览

```
Phase 0 协议对齐 ──┐
                  ├─→ Phase 2 Gateway ─→ Phase 3 SQLite ─→ Phase 4 Outbox
Phase 1 依赖/约定 ─┘                          │                    │
                                              └────── Phase 5 ID 贯通 ──────┘
Phase 3/4 落库完成后 ─→ Phase 6 health + 结构化日志
```

> 红线：**必须先做 Phase 0**。ADR-005 已决策方案 A（错误码映射 + envelope 对齐）且 Reviewer E 已签（2026-08-20），代码偏离是"冻结后对齐"义务，未对齐前不能写依赖它的新 Gateway。

---

## Phase 0 — 协议对齐（任务 2/3 的地基，冻结义务）

依据：`D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md:60-66` 登记的 ALIGN-001~005；`docs/adr/005-db-error-code-envelope.md`（方案 A 已生效）。

| # | 动作 | 目标文件/位置 | 现状依据 | 验收标准 |
|---|------|--------------|---------|---------|
| 0.1 | 最大消息上限对齐 64KB | `memory-service/embedding/protocol.py:32` `MAX_MSG_LEN=4MiB` | ALIGN-001 | 改回 `65536`，或补 ADR 变更 4MiB（需走 IPC 冻结流程） |
| 0.2 | 错误码映射到冻结 5 枚举 | `embedding_service.py:181,213,274,365,371`；`server.py:117` | ALIGN-002 / ADR-005 映射表 | `ERR_*` 全部按 ADR-005 §错误码映射表转为 `PROTOCOL_ERROR/INVALID_REQUEST/TIMEOUT/INTERNAL_ERROR` |
| 0.3 | 响应 envelope 对齐 `status/data/server_ts` | `embedding_service.py:409-433` `_envelope`/`_envelope_error` | ALIGN-003 | 成功 `{status:"ok",data,server_ts}`，失败 `{status:"error",error_code,message}`；移除 `ok/result/error` 与 `error.code` |
| 0.4 | 方法路由纳入统一路由表 | `embedding_service.py:68-73` `_METHODS` | ALIGN-004 | `memory.embed` 等子服务方法并入 FRZ-IPC-007 路由，或 ADR 承认子服务方法域 |
| 0.5 | UDS 路径 ownership 澄清 | `echo/memory_echo_server.py:40-51`；`embedding/server.py`（`_default_socket_path`）；`config/environment.example:8` | ALIGN-005 | Memory Service/Gateway owns `$XDG_RUNTIME_DIR/kylin-memory/memory.sock`；Embedding 子服务 owns 私有 `embedding.sock`；Echo 属 Gate 0 验证细节；**不要求所有进程绑同一 UDS**（见 ADR-009） |
| 0.6 | 更新对齐后的测试断言 | `memory-service/tests/test_embedding_service.py`、`test_protocol.py` | ADR-005 §开发影响 | 断言改为冻结枚举/envelope，全量 pytest 通过 |

**参考实现**：`memory_echo_server.py:107-115` `build_response` 已是正确冻结 envelope（`status/data/server_ts`），`ERROR_CODE_MAP:58-65` 已是正确映射——embedding 侧对齐时照此实现。

---

## Phase 1 — DB 依赖与迁移约定（任务 1 前置，纯配置/文档）

| # | 动作 | 目标文件 | 现状依据 | 验收标准 |
|---|------|---------|---------|---------|
| 1.1 | 补 `sqlalchemy`/`alembic` 依赖 | `memory-service/requirements.txt`（现仅 pydantic/pytest/pybind11） | R-1（进度风险） | 声明 `sqlalchemy>=2,<3` + `alembic>=1.12` |
| 1.2 | 校正迁移文件约定 `.sql`→`.py` | `migrations/README.md:24-27` | R-2（命名冲突） | 目录示意改为 Alembic `YYYYMMDD_<desc>.py`，与冻结约定一致 |
| 1.3 | 建立 Alembic 环境 | `migrations/alembic.ini` + `env.py` + `script.py.mako` | 冻结文档 GAP-DB-001 | `alembic upgrade head` 可空跑 |

---

## Phase 2 — Gateway 骨架（任务 1）

依据：`session-handoff-20260809.md:39` 分层 `IPC Gateway → Application Service → ...`。

| # | 动作 | 目标 | 验收标准 |
|---|------|------|---------|
| 2.1 | 建 `memory-service/app/api/` Gateway 入口 | 新目录 | 复用已对齐的 UDS 长度前缀 JSON（Phase 0 后），路由到子服务 |
| 2.2 | 统一 `METHOD_ROUTER` | `app/api/gateway.py` | 包含 echo/health/memory.retrieve + 子服务方法（承接 ALIGN-004） |
| 2.3 | 网关层错误码映射函数 | `app/api/errors.py` | 内部异常 → 冻结 5 枚举（实现 ADR-005 §开发影响） |

---

## Phase 3 — SQLite Schema + Alembic 迁移（任务 1）

依据：`D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md:106-207`（5 表 + 索引 + FTS5 已设计冻结）。

| # | 动作 | 表/对象 | 验收标准 |
|---|------|---------|---------|
| 3.1 | 首版迁移：5 张核心表 | `conversations` / `turns` / `memory_entries` / `outbox` / `idempotency_cache` | 字段/约束严格对齐冻结 §2.2（含 idempotency_cache 复合主键 `(user_id,session_id,idempotency_key)`） |
| 3.2 | 4 个索引 | `idx_turns_session`/`idx_memory_user_type`/`idx_memory_deleted`/`idx_outbox_pending` | 对齐 §2.3 |
| 3.3 | FTS5 + 同步触发器 | `memory_fts`（`tokenize='unicode61'`） | 对齐 §2.4，trigger 保持与 memory_entries 同步 |
| 3.4 | DAO/Repository 层 | `memory-service/app/repositories/` | 读写封装，错误经 Phase 2.3 映射 |

---

## Phase 4 — Outbox + Worker + Dead Letter（任务 1）

依据：`D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md:152-170,236-250`。

| # | 动作 | 目标 | 验收标准 |
|---|------|------|---------|
| 4.1 | Outbox 同事务写入 | TurnFinalizedEvent → SQLite INSERT + Outbox INSERT 同事务 | 原子性：两写同提交/同回滚 |
| 4.2 | Worker 轮询（1s） | `app/workers/outbox_worker.py` | `idx_outbox_pending` 扫描 `attempts<=3` |
| 4.3 | 重试退避 | `next_retry_at = now + 2^attempts * 30s` | 对齐 §3.3 |
| 4.4 | Dead Letter | `attempts > 3 → next_retry_at=NULL + 告警` | 事件不丢失（保留 outbox） |
| 4.5 | 告警接口 | FR-DB-004（Outbox Worker 告警接口定义） | 死信/积压告警可观测 |

---

## Phase 5 — trace_id/request_id/event_id 贯通（任务 2）

现状：字段级已冻结 + embedding 回显已就绪；缺的是**贯穿链路**。

| # | 动作 | 目标 | 验收标准 |
|---|------|------|---------|
| 5.1 | Gateway 解析后注入上下文 | `app/api/gateway.py` | request_id/trace_id 从 envelope 提取，贯穿到 SQLite 落库 |
| 5.2 | `turns`/`memory_entries` 落库写入 `trace_id` | Phase 3 schema | 事件 `trace_id` 与请求 `trace_id` 一致（承接 `source_trace_id→trace_id` 已统一的约定 `11_os_agent_event_contract_v1.md:99`） |
| 5.3 | `event_id` 独立语义确认 | 业务事件层 | 明确 `event_id`(业务标识) ≠ `trace_id`(链路) ≠ `request_id`(请求)，不互相替代（`fingerprint.py:65` `idempotency_key or event_id` 语义保持） |
| 5.4 | Outbox 记录携带 `trace_id` | `outbox` 表 payload/字段 | 死信可溯源到原始 trace |

---

## Phase 6 — health 统一 + 结构化日志（任务 3）

| # | 动作 | 目标 | 验收标准 |
|---|------|------|---------|
| 6.1 | 统一 health 路由名 | 合并 Phase 0.4 的路由表 | 同一 `health` 概念收敛为冻结路由，`embedding/health` 与 `echo/health` 不再两套 |
| 6.2 | health 返回 DB/Outbox 状态 | `health()` 增补 | 含 SQLite 连通、outbox backlog（对齐 `embedding_metrics.py:7` 的 index_sync_lag/outbox_backlog 语义） |
| 6.3 | 结构化日志框架 | 新增 `app/observability/` | 运行时 JSON 日志（非 evidence.jsonl），每行含 `trace_id/request_id/event_id/level/ts` |
| 6.4 | 日志贯穿全链路 | Gateway→SQLite→Outbox 各层 | 同一 trace_id 在网关/DAO/Worker 日志中可关联 |
| 6.5 | PII 脱敏 | 日志输出 | `message` 不含 PII/堆栈（ADR-005 §安全影响） |

---

## 落地节奏建议（可分批 PR）

1. **PR-A（纯对齐，低风险）**：Phase 0 + Phase 1 — 只改协议层与依赖，不引入新功能，全量 pytest 回归。
2. **PR-B（DB 骨架）**：Phase 2 + Phase 3 — Gateway + 迁移 + DAO，L0 单测。
3. **PR-C（异步链路）**：Phase 4 — Outbox Worker，L1 集成。
4. **PR-D（可观测收口）**：Phase 5 + Phase 6 — ID 贯通 + health 统一 + 结构化日志，L2 麒麟 VM 验证。

**最关键的阻塞判断**：Phase 0 是硬前置——ADR-005 已决策"冻结优先、冻结后对齐"，5 项 ALIGN 偏离（尤其 0.2/0.3 错误码与 envelope）必须先收口，否则 Gateway/SQLite/Outbox 会建立在偏离契约之上，后续再返工成本更高。
