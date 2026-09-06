# D13D Forget Retrieval Profile Contract（draft，待 D/E 确认）

| 字段 | 内容 |
|------|------|
| profile id | `d13d-validation-profile-v2` |
| 用途 | #160 R8/R10：Forget realtime / full-rebuild 检索观测的**真实执行入口**契约 |
| 状态 | `DRAFT_PENDING_D/E_CONFIRM`（D/E 确认 collection/query/deletion-consumer 映射后冻结） |
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