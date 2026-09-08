# D13D Dual-Channel Observation Contract Draft（2026-09-07）

| 字段 | 内容 |
| --- | --- |
| 文档状态 | `DRAFT_EXECUTED / NON-FORMAL / E_REBUILD_RULING_RECORDED` |
| 任务 | `P2-T0.3` 契约草案 + `P2-T0.4` 负路径测试清单 |
| 目标 profile | `d13d-validation-profile-v2-dual-channel` |
| 关联契约 | `29_d13d_forget_retrieval_profile_contract_20260906.md`、`30_d13d_forget_runtime_seam_handoff_20260906.md`、`33_d13d_phase2_remaining_task_plan_20260907.md` |
| 硬边界 | 不修改冻结 IPC / Schema / DB / 错误码 / Dataset / Gold / Threshold / Runner；不改现有 FTS-only profile 语义 |
| 当前阻塞 | 无；E rebuild ruling 已记录，Stage 2/3 已按裁定完成 |

## 1. 范围与状态

本文件最初是 Stage 2 实现前的 **draft**，用于固定 P2-T0.3 / P2-T0.4 的准备产出。
后续实现使用独立 profile `d13d-validation-profile-v2-dual-channel`，并按下方
已记录的 E ruling 完成 5/5 dual-channel E2E；本文件不改写历史，也不作为正式
Runner/raw schema 冻结依据。

现有 `d13d-validation-profile-v2` 继续保持 FTS-only 语义不变。dual-channel
实现必须使用独立 profile，避免把 FTS-only 历史证据重新解释成 Vector 已闭合。

## 2. Profile 名与 allowlist 语义

```text
d13d-validation-profile-v2-dual-channel
```

实现后只能通过 `OBSERVATION_PROFILES` closed allowlist 显式注册。缺失、未知、
大小写不一致或空 profile 名都必须 fail-closed。production `app.py` 默认路径
不隐式开启 Embedding、Forget consumer 或 Vector provider。

## 3. 双通道观测契约草案

### 3.1 通道

| Channel | Pre-delete | Realtime | Rebuild |
| --- | --- | --- | --- |
| `fts` | 真实 FTS5 检索必须命中 confirmed target | 真实 consumer ACK 后查询现有 FTS 索引 | 从当前真源重建新 FTS 代次后查询 |
| `vector` | 真实 Embedding + Vector provider 检索必须命中 confirmed target | 真实 consumer ACK 后查询当前 Vector generation | 真实 `SqliteVectorProvider.rebuild(VectorRebuildRequest)` 激活新 generation 后查询 |

任一通道 pre-delete 未命中、realtime 未发生在 worker ACK 后、rebuild 未产生
新 generation，都视为失败并 fail-closed。

### 3.2 观测字段草案

顶层记录建议为：

```json
{
  "profile_id": "d13d-validation-profile-v2-dual-channel",
  "sample_id": "d13e-forget-001",
  "forget_mode": "single_item",
  "user_id": "user_d13e_alpha",
  "foreign_user_id": "user_d13e_beta",
  "confirmed_target_ids": ["knowledge:1"],
  "channels": {
    "fts": {
      "pre_delete_hit": true,
      "realtime_residual": 0,
      "rebuild_residual": 0,
      "realtime_snapshot_id": "fts:user:realtime:g1",
      "realtime_watermark": "<Watermark>",
      "rebuild_snapshot_id": "fts:user:rebuild:g1",
      "rebuild_watermark": "<Watermark>"
    },
    "vector": {
      "pre_delete_hit": true,
      "realtime_residual": 0,
      "rebuild_residual": 0,
      "realtime_snapshot_id": "vector:user:realtime:g1",
      "realtime_watermark": "<Watermark>",
      "rebuild_snapshot_id": "vector:user:rebuild:g2",
      "rebuild_watermark": "<Watermark>",
      "collection_namespace": "<scope_id + generation>",
      "index_generation": 2
    }
  },
  "consumer_ack": {
    "event": "forget.executed",
    "forget_plan_id": "<runtime_plan_id>",
    "ack_mode": "outbox_row_deleted_by_worker",
    "router": "OutboxRouter",
    "consumer": "build_forget_consumer"
  },
  "residual": {
    "realtime_union": 0,
    "rebuild_union": 0
  }
}
```

说明：

- `confirmed_target_ids`、`ranked_ids` 继续沿用 `knowledge:<id>` /
  `preference:<id>` tagged 语义。
- `realtime_residual` / `rebuild_residual` 按通道独立计算；联合 residual 取
  双通道 residual 的并集，不允许用一个通道的 miss 掩盖另一通道残留。
- `<Watermark>` 复用 `retrieval.contracts.Watermark` 的现有结构，不新增
  冻结契约字段。
- `collection_namespace` 只记录 provider 派生结果，不允许 artifact 注入
  collection 名。
- 该 JSON 是 evidence/raw 候选草案；正式 Runner/raw schema 变更仍需按既定
  流程另行确认，不在本 draft 中擅自冻结。

### 3.3 Provenance 字段草案

dual-channel evidence 至少保留：

```json
{
  "binding": {
    "binding_artifact_sha256": "<sha256>",
    "source_db_sha256": "<sha256>",
    "runtime_db_initial_sha256": "<sha256>",
    "restore_id": "<id>",
    "state_preparation_commit": "<sha256>"
  },
  "embedding": {
    "provider": "kylin_embedding",
    "model": "<runtime_model>",
    "dimension": 768,
    "build_or_library_sha256": "<sha256>"
  },
  "vector": {
    "provider": "SqliteVectorProvider + VectorCliClient",
    "binary_sha256": "<sha256>",
    "headers_sha256": "<sha256>",
    "engine_version": "<version>",
    "rebuild_request_id": "<id>",
    "snapshot_generation": "<generation>"
  },
  "consumer": {
    "outbox_event_id": "<id>",
    "forget_plan_id": "<id>",
    "ack_mode": "outbox_row_deleted_by_worker"
  },
  "receipt": {
    "sample_id": "<sample>",
    "receipt_sha256": "<sha256>"
  }
}
```

所有哈希必须来自运行现场实际产物；禁止把 preparation SHA、旧 `0k0.7` binary
或前一 sample 的 provenance 复制到当前 execution evidence。

## 4. Fail-closed 语义草案

1. Pre-delete FTS 或 Vector 任一未命中 confirmed target，整个 dispatch 失败。
2. Embedding provider 不可用、维度不符、norm 异常或 Vector provider 不可用时，
   不降级为 FTS-only PASS。
3. `forget.executed` 未被真实 Outbox Worker 消费、router 未调用 deletion
   consumer、或 outbox 行未删除时，不得进入 realtime observation。
4. Vector delete 或 rebuild 失败时，不得把 FTS residual=0 写成成功。
5. Vector rebuild 前若发生 active preference 语义冲突，必须按 E 裁定执行；
   未裁定前保持 `SqliteVectorSnapshotReader` 现有 fail-closed 行为。
6. scope / user / collection / generation 不匹配时，整个 dispatch 失败。
7. 未知 profile 或 observer 类型不在 closed allowlist 中时，pre-delete 前失败。

## 5. P2-T0.4 负路径测试清单草案

Stage 2.6 实现时至少覆盖以下 L1 测试：

| 类别 | 用例 |
| --- | --- |
|正向双通道|FTS 与 Vector pre-delete 均命中，consumer ACK 后双通道 realtime residual=0，rebuild 后双通道 residual=0|
|Embedding unavailable|Embedding provider 抛错 / 返回错误维度时，dispatch fail-closed，不写 canonical raw|
|Vector unavailable|Vector provider delete/search/rebuild 抛错时，dispatch fail-closed，不以 FTS residual=0 代替双通道 PASS|
|Pre-delete miss|FTS 或 Vector 任一 pre-delete 未命中 confirmed target，dispatch fail-closed|
|Delete 失败|Vector delete 返回失败或 matched/deleted 结果异常时，realtime observation 不允许产生|
|Rebuild 失败|Vector rebuild 抛错、generation 未推进或 watermark 缺失时，dispatch fail-closed|
|Outbox 未 ACK|outbox 行仍存在、router/consumer 未执行、worker 未删除事件时，禁止进入 realtime|
|Preference fail-closed|非 full_reset 或 full_reset 后仍存在 active preference 且语义未获 E 授权时，Vector rebuild snapshot 继续拒绝|
|Scope mismatch|user_id / collection / generation / foreign control 不匹配时，dispatch fail-closed|
|Profile allowlist|未知 profile、空 profile、重复注册尝试均 fail-closed；production 默认路径不自动启用 dual-channel|

## 6. E rebuild ruling（recorded）

Reviewer E 已在 PR #160 comment `5568565138` 记录：
`APPROVE_KNOWLEDGE_ONLY_PARTIAL_REBUILD`。

约束执行如下：

1. 001-004 允许 Knowledge-only rebuild；snapshot 必须是该 `request.user_id`
   删除后的全部 active / non-deleted Knowledge 真源。
2. 不全局删除 active-Preference fail-closed 语义；Knowledge-only rebuild 与
   full user reset rebuild 显式区分。
3. 005/full_reset 保持严格 fail-closed；若仍有 active Preference 必须失败。
4. 双通道 E2E 证明 pre-delete FTS/Vector 命中、consumer ACK、realtime miss、
   rebuild 后不复活，并保留同用户 Knowledge control 与 foreign-user 数据。
5. 本裁定不授权 Preference embedding/indexing、Preference index-text 规则或
   Preference Vector retrieval contract。
