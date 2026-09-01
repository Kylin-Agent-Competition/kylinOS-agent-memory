# 开发报告：D9D OutboxRouter + 真实 Index Consumer（路径 1）

- 任务卡：`docs/day9/01_d9d_task_card.md`（D9D，路径 1）
- 分支 / 基线：`feat/d9d-index-consumer`（基于 main @ `5a1f112`，PR #97 合并后）
- 对照文档：02_architecture_sop v1.1（Outbox 并发与积压 §11.3 / SQLite 真源 §11.2 / 证据分层 §16）；Day11 跨轨依赖清单 D-REQ-05（P0/P1）、D-REQ-06（P2）；VERSION_MAP 真源
- 执行方式：委托 opencode（`D9D_IMPL_DELEGATION_20260901.md`），opencode 在报告/提交前被环境 SIGKILL 中断，由 orchestrator 接手验证与收尾（代码为 opencode 施工产物，验证/提交/报告为 orchestrator 完成）

## 修改文件清单（新增 / 修改）

| 文件 | 变更类型 | 摘要 |
|------|----------|------|
| `memory-service/outbox/router.py` | 新增 | `OutboxRouter`：按 event_type 注册/分发；未知类型抛 `UnknownEventTypeError`；重复注册失败；`build_outbox_router()` 工厂（依赖未接线不注册对应消费者） |
| `memory-service/outbox/index_consumer.py` | 新增 | `build_index_consumer(provider)`：`memory.upserted` → 校验 payload → 构造 `VectorUpsertRequest`（透传 user_id，payload_hash 经 `digest_from_canonical` 签名）→ `provider.upsert()`；缺字段 ValueError / provider 失败 RuntimeError（Worker 退避/DL） |
| `memory-service/outbox/deletion_consumer.py` | 新增 | `build_forget_consumer(embedding_service)`：`forget.executed` → 复用 D11A `_handle_deletion_payload`（不改既有行为）；invalidator 未接线 → 真实失败 |
| `memory-service/outbox/worker.py` | 修改 | `metrics()` 新增 `index_sync_lag` / `index_sync_lag_seconds`（D-REQ-06 口径）；成功消费记录最近 `outbox.created_at`（内存追踪，无 Schema 变更） |
| `memory-service/db/repositories.py` | 修改 | 新增 `latest_memory_change_ts(conn)`（memory_entries 最新 created_at/updated_at 最大值，空表 None） |
| `memory-service/app.py` | 修改 | OutboxWorker 注入 `build_outbox_router(vector_provider=None, embedding_service=None)` 的 `route`；生产依赖未接线 → 事件按未知类型失败/重试/DL（真实结果）；`--no-outbox` 不变 |
| `memory-service/tests/test_outbox_router_d9d.py` | 新增 | L1 16 项：路由注册/分发/未知类型/重复注册；index consumer 成功/缺字段/provider 失败；forget consumer 成功/invalidator 未接线失败；worker 集成（成功删除/未知重试/DL） |
| `memory-service/tests/test_index_sync_lag_d9d.py` | 新增 | L1 5 项：指标口径（空库 None/未消费 None/backlog=0 收敛/60s 差值/仓库查询） |
| `docs/day9/01_d9d_task_card.md` | 新增 | D9D 任务卡（本 PR 关联文档） |
| `docs/day9/03_d9d_pr_description.md` | 新增 | 本开发报告 |

## 契约变化（Schema / IPC / DB / 错误码）

**无**。不新增 outbox event_type 枚举值（复用 `repositories.EVENT_MEMORY_UPSERTED` / `EVENT_FORGET_EXECUTED` / D11A `EVENT_DELETION`）；不修改冻结 IPC/DB/错误码；`worker.metrics()` 仅新增字段（向后兼容）。

## 设计说明（关键决策）

1. **Router 可调用注入**：`OutboxRouter.route(payload)` 直接作为 `OutboxWorker.consumer` 注入，Worker 骨架零改动即获得按类型分流（D-REQ-05 路由图）。
2. **未知类型不静默**：`UnknownEventTypeError` → Worker 失败路径（退避→DL）+ ERROR 日志，可观测；重复注册直接失败暴露接线错误。
3. **依赖未接线 = 真实失败**：生产 `vector_provider=None / embedding_service=None` 时对应消费者不注册，事件按未知类型失败——不假装成功（红线：Mock/固定返回零容忍；producer 由 D8D PR #101 合并后接线）。
4. **index_sync_lag 口径**（任务卡 §4.2 冻结）：`latest_memory_change_ts − last_indexed_ts`；`_last_indexed_ts` 内存追踪（成功消费后 outbox 行被删，无持久化）；任一侧缺数据返回 None 不伪造 0；backlog=0 全消费 → 收敛为 0（同库时间戳自洽）。
5. **复用 D11A**：deletion consumer 直接引用 `_handle_deletion_payload`，不重构既有行为（范围克制）。

## 测试结果（L0/L1）

- L0：`python -m py_compile` 6 文件 → **通过（rc=0）**
- L1（WSL2，Python 3.10.12）：
  - `pytest memory-service/tests/test_outbox_router_d9d.py memory-service/tests/test_index_sync_lag_d9d.py -v` → **21 passed**（4.93s）
  - 全量回归 `pytest memory-service/tests/ -q` → **1416 passed, 49 skipped**（86.95s；基线 1395 passed, 49 skipped，新增 21 全绿，零回归）

## 待麒麟宿主 L2 验证项（未执行，不声称通过）

- 真实 VectorProvider upsert 链路（memory.upserted → Vector 索引生效）——需生产 producer（D8D 合并后）接线 + 真实 provider 注入
- forget.executed → CacheInvalidator → FTS5/Vector delete/rebuild 真实链路（D11A 已有宿主证据，本任务仅接线）
- UDS 端到端：event.ingest / turn.finalized → outbox → router 分发（生产 producer 就绪后）

## 技术债变化

- **TD-D4D-001（Outbox consumer 未接线）**：部分关闭——router + consumer 接线完成；producer 真实入队仍待 D8D（PR #101）→ 保持 Open 待 producer 合并后全链路验证再关
- TD-D4D-003（写锁释放）：保持 Open，另排期
- D-REQ-06（index_sync_lag）：本任务落地口径，P2 完成

## 风险与回滚方式

- 风险：`_last_indexed_ts` 内存态重启丢失（metrics 缺数据回 None，不伪造）——可接受，符合口径；真实持久化版本可后续用 outbox 审计表/索引水位表实现
- 风险：生产 producer 未接线期间，outbox 中的 memory.upserted/forget.executed 事件将反复重试直至 DL——当前生产无此类事件入队（无 producer），不触发；D8D 合并后接线即可
- 回滚：删除本分支提交即可完整回退（纯新增 + 3 文件小改，无迁移）
