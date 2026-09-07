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
| G2 | validation runtime router 未接入 deletion consumer（P1-1 仅限 production default） | `outbox/router.build_outbox_router` 需 vector_provider/embedding_service；`app.py` production default 仍未接线；adapter validation runtime 已在 2026-09-07 接入正式 worker/router/consumer |
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

- 代码侧已完成：V2 binding、sealed→per-sample clones、dispatch 重接线、approved FTS profile、receipt provenance、负向矩阵（F6–F14/F18/F19）；validation runtime 内 `forget.executed` 已接正式 `OutboxWorker/OutboxRouter/build_forget_consumer`，成功后由 Worker ACK；
- 未闭合前不宣称：Forget 5/5 real preview/execute/realtime/rebuild PASS、residual=0 正式证明；
- 上表 G1–G6 由责任轨提交代码与证据后，由非作者 Reviewer 独立复审。

## 4. 交接物

- 本文件（#160 分支）
- `docs/day13/29_d13d_forget_retrieval_profile_contract_20260906.md`（E 确认规则 + 阻塞登记）
- `docs/day13/28_d13d_forget_state_binding_v2_contract_20260906.md`

## 5. 闭合状态更新（2026-09-06）

| 缺口 | 状态 | 提交/说明 |
|---|---|---|
| G1 | ✅ 已核对（生产者已存在） | `uow.execute_forget_plan` 已 enqueue `EVENT_FORGET_EXECUTED`；无需新增 |
| G3 | ✅ 已闭合 + L1 | `repositories.soft_delete_resolved_targets` knowledge 返回稳定 `v<version>`、`all` 汇聚 versions；`deletion_consumer._build_delete_request` 规范化 tagged ids 并强制 version_ids 对齐；提交 `2e3fa45` |
| G2 | ✅ validation runtime 已闭合 + L1 | execute 后运行正式 `OutboxWorker → OutboxRouter → build_forget_consumer`；approved FTS deletion port 消费签名 `VectorDeleteRequest`，失败/未 ACK 时 dispatch fail-closed；production `app.py` 默认接线仍保持 P1-1 |
| G4 | ⏳ 待 D/E 决策 | preference 是否进入 Vector 重建真源（feature：memory_items/memory_versions 索引文本=key+value）；或保持 key-value 非 Vector 语义并**显式 fail-closed 排除**（防止静默漏清理） |
| G5 | ⏳ 环境/实现 | seeded state 的 embedding + `memory.upserted` index producer（pre-delete probe 需先命中） |
| G6 | ⏳ 环境 | 0k1.1 `Database.h` headers 获取 + `vector_bridge_cli` 编译/smoke |

G4/G5/G6 仍按本文件阻塞；未完成前不宣称 Forget 5/5 或 production realtime cleanup 完成。

## 6. 闭合状态更新（2026-09-07）

| 缺口 | 状态 | 说明 |
|---|---|---|
| G4 | ✅ 保守排除已闭合 + L1 | D/E 未裁定进入 Vector 真源前采用保守方案：`SqliteVectorSnapshotReader` 只读 knowledge；若该用户仍有 active preference（`memory_versions.memory_status != "removed"`），整个 Vector rebuild snapshot fail-closed，防止 full_reset 后残留 preference 被 rebuild 静默排除。已补 active/removed 两条 L1。 |
| G5 | 🟡 preparation READY / formal BLOCKED | L1 seam + VM preparation 均可用：`evaluation/d13d_forget_index_producer.index_knowledge_docs` 已接真实 outbox/index-consumer 语义；2026-09-07 在麒麟 VM 从当前源码编译 `kylin_embedding` 并完成真实 SDK embed smoke（默认模型 `ensemble-embd_gte-base_uint8-text`，768 维，norm≈1.0）。准备证据见 `evidence/phase3-prep/d13d_g5_embedding_smoke_20260907/`。正式仍 BLOCKED：必须把真实 Embedding 与 Vector provider 注入 isolated runtime binding，且 pre-delete probe 在 FTS/Vector 双通道命中并留 provenance。 |
| G6 | 🟡 preparation READY / formal BLOCKED | SDK client 包为 `1.2.0.0-0k1.1`；本地 dev 包 `libkysdk-vector-engine-client-dev_1.2.0.0-0k1.1_amd64.deb` 已解包出 `0k1.1` headers，`vector_bridge_cli` 已用这些 headers 在 VM 上编译/链接并完成真实 engine smoke（create → insert → search hit → delete → search empty → drop）。准备证据见 `evidence/phase3-prep/d13d_g6_bridge_smoke_20260907/`。准备阶段不做 formal raw/Seal/Runner。正式执行仍需在 final tested_commit 的冻结 evidence root 上重放并独立复核。禁止复用旧 `0k0.7` binary/header。 |

G5 正式关闭标准：在麒麟 VM 的 isolated runtime binding 中注入真实 Embedding/Vector provider，pre-delete probe 在 FTS 与 Vector 双通道都命中，且 vector delete/rebuild 证据可复核。在此之前，FTS-only L1 不得写成 Forget 5/5 或 Vector 双通道完成。

## 7. Phase 3 preparation scope（2026-09-07）

Reviewer E 已在 PR #160 comment `5564455955` 将阶段授权更正为
`APPROVE_PHASE3_START`，但只覆盖 `PREPARATION / NON-FORMAL` scope。

因此本文件允许 G5/G6 的真实 provider、SDK headers、bridge compile/link/smoke
前置准备；但不允许把准备结果写成 Forget 5/5、Vector 双通道完成或正式 evidence。
Phase 3 准备阶段的统一口径与证据结构见
[31_d13d_phase3_preparation_handoff_20260907.md](31_d13d_phase3_preparation_handoff_20260907.md)。
