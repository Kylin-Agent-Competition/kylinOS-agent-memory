# D13D Forget Retrieval Profile Contract（draft，待 D/E 确认）

| 字段 | 内容 |
|------|------|
| profile id | `d13d-validation-profile-v2` |
| 用途 | #160 R8/R10：Forget realtime / full-rebuild 检索观测的**真实执行入口**契约 |
| 状态 | `CONFIRMED_WITH_BLOCKERS`（E 2026-09-06 回执 CONDITIONAL_ACCEPT / EXECUTION_BLOCKED；规则 1/2/4/5 已确认，阻塞项关闭前不得宣称 5/5 PASS） |
| 约束 | adapter 不得伪造 ranked_ids、不得复制 realtime→rebuild、不得仅手工 DB 查询宣称 residual=0；未批准 profile 一律 fail-closed |
| 关联 | `docs/day13/28_…v2_contract`（source_state/sealed DB）、`memory-service/evaluation/d13d_execution_adapter.py`（OBSERVATION_PROFILES allowlist） |

> 目标：让 Reviewer 能证明 `dispatch_forget_sample` 的
> realtime_observation / rebuild_observation 来自**真实检索执行**，且与 approved
> source state 的 isolated runtime clone 绑定。

## 1. 观测构造

每条 `ForgetRetrievalObservation` 必须由真实检索产生：

```text
confirmed_target_ids   ← 本 sample preview 解析的 tagged 目标（knowledge:/preference:）
ranked_ids             ← 真实检索对查询的返回（按该通道排序/命中）
dataset_version        ← 固定受控值（如 d13d-forget-v2）
source_snapshot_id     ← 运行时证据实际产生（禁止复制 prepared 锚点冒充）
source_watermark       ← 运行时证据实际产生
```

准备阶段只允许显式命名锚点 `prepared_state_snapshot` / `prepared_state_watermark`（不当作运行后证据）。

## 2. realtime 语义（forget.execute 之后）

- 执行链：`forget.execute` → 真实 realtime 检索 → `ForgetRetrievalObservation`
- 结果必须反映 execute 后的真实状态（已删除目标不得再作为命中返回；若检索通道含删除清理语义，以该通道为准）
- 禁止把 rebuild 的结果复制成 realtime。

## 3. full-rebuild 语义

- 执行链：真实 index/full rebuild → 真实检索 → `ForgetRetrievalObservation`
- rebuild 后已删除目标不得复活；FTS/Vector 无残留；foreign-user controls 保留。

## 4. 需 D/E 确认的映射（阻塞项）

1. **collection / scope 身份**：prepared knowledge/preference ↔ 检索 collection/scope 的对应规则（是否按 user/sample 隔离、命名）；
2. **query 语义**：Forget residual 检索使用的 query 内容/构造与 ranked_ids 的语义（命中=与已删内容相似/命中即 residual？）；
3. **deletion-consumer 触发**：`forget.executed` → embedding/vector 删除清理的接线点与“realtime 是否已含该清理”的判定；
4. **rebuild 入口**：正式 full rebuild 的命令/API（engine `rebuild`、outbox consumer 或 B 轨运行器）；
5. **执行载体**：本 VM（有 `kylin-ai-vector-engine 1.2.0.1-0k1.0` + SDK，无 D10B VM）上可用的真实执行入口（编译 `vector_bridge_cli` 或 SDK 直连）。

## 5. 交付形态

- D/E 对上述 1–5 给出具名确认后，我在 `OBSERVATION_PROFILES["d13d-validation-profile-v2"]` 实现该真实 observer，并在 VM 上跑 5/5 正向 E2E；
- 在 D/E 确认前，`OBSERVATION_PROFILES` 保持空 allowlist，任何 profile 均 fail-closed（F18 已覆盖）。

## 6. E 确认冻结的规则（2026-09-06 回执）

1. **collection/scope**（ACCEPTED_WITH_CONSTRAINTS）：业务隔离真值 = user scope（`IndexScope(kind=USER)`，`scope_id="user:<user_id>"`）；sample 隔离 = fresh runtime clone + **唯一 generation/collection namespace**（禁止 sample 复用 serving collection）；collection 命名沿用 `SqliteVectorProvider` 派生（`scope_id + generation`），artifact 不注入 collection 名；logical ID 必须 `knowledge:<id>` / `preference:<id>` tagged；F5 preference 的**真实检索/重建映射**必须代码事实闭合后才能宣称支持。
2. **query→ranked_ids**（ACCEPTED）：pre-delete probe + exact logical-ID residual；同一 probe 用于 pre/realtime/rebuild；**pre-delete 必须先命中目标**，否则删除后 miss 无证明力 → fail-closed；residual 判定 = confirmed target logical ID **真实出现在返回中**（相似但不同 ID 不算）；FTS5/Vector 分通道留 provenance，残留判定取**并集**防掩盖。
3. **deletion-consumer / realtime 起点**（SEMANTIC_ACCEPTED / CURRENT_HEAD_BLOCKED）：realtime = 业务事务完成 + 对应 `forget.executed` 经真实组合 consumer 成功 ACK 之后的真实检索；当前 HEAD 存在 router wiring 与 `version_ids/kind` mapping 缺口（P0-1/P1-1），修复前不得宣称 realtime cleanup 完成。
4. **full-rebuild**（ACCEPTED_WITH_BLOCKER）：Vector 正式 rebuild = `SqliteVectorProvider.rebuild(VectorRebuildRequest)`，新 generation 激活后再查询；FTS 只做真实重查；当前 `SqliteVectorSnapshotReader` 未覆盖 memory_items/memory_versions（F5 preference）→ 先闭合（P0-2）。
5. **执行载体**（CONDITIONALLY_ACCEPTED）：允许在本 VM 编译当前 HEAD `vector_bridge_cli` 并连真实 engine；前提 = 匹配当前 `0k1.1` SDK 的 headers，完成 compile/link/smoke 并记录完整 provenance；**禁止**复用旧 `0k0.7` binary/header 冒充当前 HOST_VERIFIED（P1-2）。

## 7. E 授权立即实施（B）

- 将 1/2/4/5 已确认规则写入本 profile；
- 保持 `OBSERVATION_PROFILES` closed allowlist；
- 实现 pre-delete positive observability、真实 query、canonical tagged ranked IDs、per-channel provenance；
- 本 VM SDK header 探针 + CLI build/link/smoke；
- 每 sample 独立 generation/collection namespace；
- 对 #3 的 outbox delete payload / version / kind mapping 缺口做最小修复或正式跨轨 handoff + L1；
- F5 preference rebuild/retrieval mapping 跨轨闭合；
- 完成后才执行 5/5 真正 E2E。

## 8. 登记阻塞（未关闭前不宣称 5/5 PASS）

```text
P0-1  forget.executed payload ↔ VectorDeleteRequest 的 version/kind mapping 不闭合（router wiring）
P0-2  full_reset preference 不在 SqliteVectorSnapshotReader 重建真源范围内
P1-1  app.py production default 未把 embedding_service 接入统一 router（forget.executed 默认 route 未注册）
P1-2  当前 VM client SDK=0k1.1；旧 0k0.7 L2 仅作构建方法参考，不替代 ABI/Host 证据
```