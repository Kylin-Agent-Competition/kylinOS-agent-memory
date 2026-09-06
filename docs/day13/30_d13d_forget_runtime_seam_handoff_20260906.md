# D13D Forget Runtime Seam 跨轨 Handoff（formal，E 授权）

| 字段 | 内容 |
|------|------|
| PR | #160（`feat/d13d-i3b-completion`，HEAD 见 26_/PR Body） |
| 依据 | E 2026-09-06 回执（CONDITIONAL_ACCEPT / EXECUTION_BLOCKED）第 5 节：允许对 #3 outbox delete payload/version/kind mapping 缺口做**最小修复或正式跨轨 handoff + L1** |
| 状态 | `BLOCKED_PENDING_TRACK_CLOSURE`（本 PR 不宣称 Forget 5/5 PASS） |
| 责任 | 涉及 B 轨运行时（Vector/Index/Outbox/Embedding）与 D 轨 forget executor 的代码事实闭合；本文件为交接依据，非实现替代 |

## 1. 已核验缺口（文件:行 事实）

| 编号 | 缺口 | 代码事实 |
|---|---|---|
| G1 | `forget.executed` 生产者**已存在**（核对更正） | `uow.execute_forget_plan` 终态事务已 enqueue `EVENT_FORGET_EXECUTED`（priority=FORGET_PRIORITY），payload 含 user_id/forget_plan_id/target_type/forget_mode/resolved_target_ids/version_ids/selection_hash/confirmation_ref/trace_id；无需再实现生产者 |
| G2 | 统一 router 未接入 deletion consumer（P1-1） | `outbox/router.build_outbox_router` 需 vector_provider/embedding_service；`app.py` production default 未接线；adapter validation runtime 未挂 router |
| G3 | payload version/kind mapping 缺口（P0-1） | `deletion_consumer._build_delete_request` 接受 `resolved_target_ids`/`version_ids`，无 `knowledge:`/`preference:` kind 映射；preference（memory_items）无 version_ids 真源 |
| G4 | SnapshotReader 重建真源缺 preference（P0-2） | `retrieval/sqlite_vector_snapshot.py` 重建真源仅覆盖 memory_entries（knowledge），未覆盖 memory_items/memory_versions |
| G5 | seeded 状态无 vector 索引/embedding 链 | 预置仅写 memory 行；`memory.upserted → index consumer` 生产者/embedding 未对 D13D runtime DB 运行 → pre-delete probe 无法命中（违反 E 规则 2） |
| G6 | SDK 0k1.1 headers 缺失（P1-2） | VM 仅装 `.so`（`dpkg -L libkysdk-vector-engine-client` 无头文件）；`vector_bridge_cli.cpp` 依赖 `Database.h` + nlohmann；禁止复用 0k0.7 |

## 2. 建议闭合顺序与责任

1. **D13D/B（本 PR）**：G3 kind/version 规范化——`outbox.deletion_consumer._build_delete_request` 接受 `knowledge:`/`preference:` tagged memory_ids，strip tag→数字 id，version_ids 与 memory_ids 长度对齐，未知 tag fail-closed；补 L1；
2. **B**：G3 deletion consumer 的 kind/version 映射（strip tag → 对应 collection/logical id），补 L1；
3. **B**：G4 `SqliteVectorSnapshotReader` 重建真源并入 preference（memory_items/memory_versions），补 L1；
4. **B**：G2 validation profile 内接线统一 router（vector_provider + embedding_service.invalidator），execute 后等待 forget.executed 消费 ACK 再进 realtime，补 L1；
5. **B**：G5 建立 seeded state 的 vector 索引（embedding+upsert consumer）使 pre-delete probe 命中，补 L1；
6. **B/D（环境）**：G6 取得 0k1.1 匹配 `Database.h` 头文件，编译 `vector_bridge_cli` + smoke（记录 compile/link/运行 provenance）。
7. 闭合后：实现 `OBSERVATION_PROFILES["d13d-validation-profile-v2"]`（E 规则 1/2/4/5），在 VM 跑 5/5 E2E，补齐 evidence。

## 3. 本 PR 立场

- 代码侧已完成：V2 binding、sealed→per-sample clones、dispatch 重接线、profile allowlist（空）、receipt provenance、负向矩阵（F6–F14/F18/F19）；
- 未闭合前不宣称：Forget 5/5 real preview/execute/realtime/rebuild PASS、residual=0 正式证明；
- 上表 G1–G6 由责任轨提交代码与证据后，由非作者 Reviewer 独立复审。

## 4. 交接物

- 本文件（#160 分支）
- `docs/day13/29_d13d_forget_retrieval_profile_contract_20260906.md`（E 确认规则 + 阻塞登记）
- `docs/day13/28_d13d_forget_state_binding_v2_contract_20260906.md`
