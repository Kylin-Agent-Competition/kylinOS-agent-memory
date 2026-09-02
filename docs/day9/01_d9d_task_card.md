# D9D 任务卡：Outbox Router + 真实 Index Consumer（路径 1：consumer 侧骨架）

| 字段 | 内容 |
|------|------|
| 任务编号 | D9D（Day11-D） |
| 任务标题 | OutboxRouter 统一消费路由 + memory.upserted index consumer + forget.executed deletion consumer 接线 + unknown→fail/retry + L1 测试 |
| 责任轨道 | D（周子腾）；Reviewer：E（谢嘉然） |
| 基线分支 | 基于 main @ `5a1f112`（PR #97 D8-C 合并后） |
| 基线 Commit | `5a1f112`（本地已验证） |
| 需求来源 | Day11 跨轨依赖清单 D-REQ-05（P0/P1）「补齐 D9D 真实 Index Consumer」；D-REQ-06（P2，本版仅指标口径落地） |
| 对照文档 | 02_architecture_sop v1.1（Outbox 并发与积压 §11.3、SQLite 真源 §11.2、证据分层 §16）；VERSION_MAP 真源；既有冻结 FR-DB-004 附录 B（Outbox Worker 行为） |
| 前置依赖 | 无硬前置（不依赖 PR #101 D8D 契约合并）；producer 侧 memory.upserted/forget.executed 真实入队由 D8D（PR #101 合并后）接入，本版以注入点 + L1 测试验证 consumer 行为 |

---

## 一、目标

建立 Outbox 事件的**统一消费路由**（替代当前单一 consumer 回调或 None），使生产 `OutboxWorker` 能按 `event_type` 分流消费：

```text
memory.upserted → index consumer（Vector/Index upsert）
forget.executed  → deletion consumer（cache invalidation → FTS5/Vector delete/rebuild）
unknown          → fail/retry（真实失败，不进 DL 也要可观测）
```

同时落地真实 `index_sync_lag` 指标口径（D-REQ-06，P2），使 `worker.metrics()` 可观测、可测试、backlog=0 时收敛。

**本版边界（路径 1）**：只做 consumer 侧骨架与路由 + 指标，**不实现 producer**（memory.upserted / forget.executed 的真实入队点由 D8D 契约合并后接线）；不做 FTS5/Vector 的真实写入实现细节（复用既有 `retrieval/provider.py` upsert/delete 接口与 D11A deletion consumer）。

## 二、范围

### 2.1 范围内（本任务必须）

| # | 模块 | 内容 | 依据 |
|---|------|------|------|
| 1 | `memory-service/outbox/router.py`（新增） | `OutboxRouter`：按 event_type 注册/分发；`register(event_type, consumer)`；`route(payload)` 对未知 event_type 抛 `UnknownEventTypeError`（由 Worker 按失败处理）；路由表常量使用 `repositories.EVENT_MEMORY_UPSERTED` / `EVENT_FORGET_EXECUTED` / D11A `EVENT_DELETION` | D-REQ-05 路由图 |
| 2 | `memory-service/outbox/index_consumer.py`（新增） | `build_index_consumer(...)`：消费 `memory.upserted` → 构造 `VectorUpsertRequest` → 调 `retrieval provider.upsert()`；payload 字段缺失/非法 → 抛异常（重试/DL）；成功/失败日志带 event_id/trace_id（复用 request_context） | D-REQ-05；02 §11.3 |
| 3 | `memory-service/outbox/deletion_consumer.py`（新增或复用） | `build_forget_consumer(...)`：消费 `forget.executed` → 复用 D11A `build_deletion_consumer` 的 payload 处理（cache invalidation → delete/rebuild 语义）；若 `embedding_service.invalidator is None` → 真实失败（不假装成功） | D-REQ-05；TD-A-D10-CACHE-INVALIDATION |
| 4 | `memory-service/app.py`（修改） | OutboxWorker 构造时注入 `OutboxRouter`（含 index consumer + deletion consumer 注册）；`--no-outbox` 行为不变 | D-REQ-05 |
| 5 | `memory-service/outbox/worker.py`（修改，最小） | `metrics()` 增加真实 `index_sync_lag`：`latest committed memory change timestamp - latest successfully indexed timestamp`（口径冻结见 §4.2）；缺数据时返回 `None` 并保持 backlog=0 收敛 | D-REQ-06 |
| 6 | `memory-service/tests/test_outbox_router_d9d.py`（新增） | L1：路由分发/未知类型失败/注册覆盖/worker 集成（成功删除、未知重试、DL） | NFR-6、D-REQ-05 |
| 7 | `memory-service/tests/test_index_sync_lag_d9d.py`（新增） | L1：指标口径（有/无数据、backlog=0 收敛、可观测） | D-REQ-06 |
| 8 | `docs/day9/03_d9d_pr_description.md`（新增） | PR 描述：背景/范围/测试/技术债/依赖 PR #101 | 输出规范 |

### 2.2 范围外（本任务不做，DEFERRED）

| # | 项 | 理由 |
|---|-----|------|
| 1 | memory.upserted / forget.executed 真实 producer 入队点 | 归 D8D 契约 v0.3（PR #101）合并后接线；本版 UoW 不改 |
| 2 | 真实 FTS5/Vector 写入实现细节 | 复用既有 `retrieval/provider.py`（upsert/delete/rebuild 接口已存在）；无真实宿主 Vector 时按真实 ProviderError 失败重试 |
| 3 | Outbox Worker 批量处理与写锁释放改造 | TD-D4D-003 单独排期；本版保持现有单事务循环 |
| 4 | 修改 E 轨 Domain/Policy/Service 代码 | 红线：E 轨 D7/D8E 冻结，本任务不触碰 |
| 5 | 修改冻结契约（IPC/Schema/DB/错误码） | 无契约变更；outbox event_type 使用既有常量，不新增枚举值 |

## 三、禁止修改范围（红线）

- 不修改冻结契约：FRZ-IPC-001~007、FRZ-DB-001~005、FRZ-CFG-001、ADR-005~011/013/014 裁定。
- 不修改 `memory-service/domain/`、`service/`（E 轨 policy 与业务语义）、`retrieval/contracts.py` 既有模型字段。
- 不修改 D11A `embedding/outbox_consumer.py` 既有行为（只引用/复用，不重构）。
- 不接 Outbox consumer 之外的生产路径；`turn.finalized` / `event.ingest` 落库行为不变。
- 代码/配置/日志/测试中不得出现 API Key/密码/Token/私钥；last_error 统一经 `sanitize_message` 脱敏。
- 不把 Mock/固定返回当生产功能：index consumer 无 Vector provider 时按真实失败重试；指标缺数据返回 `None` 而不是伪造 0。
- 不把 WSL 结果当宿主证据；L2 项如实标注"待 VM 验证"。

## 四、契约分析

### 4.1 Outbox 事件路由

| event_type | 消费者 | payload 关键字段 | 失败语义 |
|---|---|---|---|
| `memory.upserted`（repositories.EVENT_MEMORY_UPSERTED） | index consumer | `memory_id` / `version_id` / `user_id` / `vector` / `object_type` / `index_text_hash` / `trace_id`（可选） | payload 缺字段 → ValueError；provider 失败 → ProviderError；均按 Worker 退避/进 DL |
| `forget.executed`（repositories.EVENT_FORGET_EXECUTED） | deletion consumer（复用 D11A 处理） | `event_id` / `user_id` / `target_type` / `content_hashes` / `content_fingerprints` / `forget_mode` | 缺 event_id/非法枚举 → ValueError；invalidator 未接线 → RuntimeError 真实失败 |
| 其他 / 未知 | 无（路由未注册） | — | `UnknownEventTypeError` → Worker 失败路径（退避→DL），日志 ERROR 可观测 |

### 4.2 index_sync_lag 口径（冻结）

```text
index_sync_lag = latest committed memory change timestamp（memory_entries 最新 updated_at/created_at 最大值）
               − latest successfully indexed timestamp（Worker 最近成功消费的 outbox.created_at）
```

- 实现：`repositories` 新增两个查询（`latest_memory_change_ts` / `latest_indexed_ts`）；指标返回 ISO 字符串与秒数差。
- 无数据（空库/未消费）→ 返回 `None`，不得伪造 0。
- backlog=0 且全部消费成功 → lag 收敛为 0（或 ≤ 1 轮询周期容差，实现用同库时间戳自洽）。
- 保持既有 metrics 字段（backlog/dead_letter/oldest_pending_created_at/processed/dead_letters）不变，新增 `index_sync_lag` / `index_sync_lag_seconds`。

### 4.3 依赖接口（实现前确认签名）

- `repositories.EVENT_MEMORY_UPSERTED` / `EVENT_FORGET_EXECUTED`（已定义）
- `retrieval/provider.py`：`VectorProvider.upsert(VectorUpsertRequest) → ProviderResult[VectorUpsertResult]`（抽象接口，注入实现）
- `retrieval/contracts.py`：`VectorUpsertRequest` / `VectorRecord` / `ObjectType` / `Digest` 等
- `embedding/outbox_consumer.py`：`build_deletion_consumer(embedding_service)`（复用其 payload 解析逻辑）
- `outbox/worker.py`：`OutboxWorker(engine, consumer=...)`（现有注入点；Router 可作为 consumer 包装）

## 五、安全与测试环境

- 跨用户隔离：index consumer 构造 `VectorUpsertRequest` 必须透传 payload 的 `user_id`；Vector 层硬过滤由 provider 负责（本版不绕过）。
- 日志：不记录 payload 原文/正文，只记录 event_id/trace_id/类型/错误摘要（sanitize_message）。
- WSL 可测（L1）：路由分发、未知类型、consumer 注册、worker 集成（成功/重试/DL）、指标口径、幂等。
- 麒麟 VM（L2，待验证不声称）：真实 Vector provider upsert 链路、UDS 端到端（生产 producer 接线后）。

## 六、交付物与验收标准

- [ ] `outbox/router.py` + `outbox/index_consumer.py` + `outbox/deletion_consumer.py`（或复用命名）实现
- [ ] `app.py` 注入 Router；`--no-outbox` 不变
- [ ] `worker.metrics()` 含真实 index_sync_lag（可观测、可测试、backlog=0 收敛）
- [ ] L1 测试全绿：`pytest memory-service/tests/ -k "outbox_router or index_sync_lag"`（含失败路径/未知类型/DL）
- [ ] WSL2 全量 pytest 不回归（基线 1395 passed, 49 skipped）
- [ ] `docs/day9/03_d9d_pr_description.md` 开发报告（对照文档版本、修改清单、测试数字、TD 变化、待 VM 验证项）

## 七、关联技术债

- TD-D4D-001（Outbox consumer 未接线）：本任务部分关闭（router + consumer 接线）；producer 入队仍待 D8D
- TD-D4D-003（写锁释放）：保持 Open，另排期
- D-REQ-06（index_sync_lag）：本任务落地口径
