# D11B `filter_diagnostics` 候选字段契约 v1

> 状态：`CANDIDATE_INTERNAL_ONLY`（2026-09-02）
>
> 适用实现：`memory-service/retrieval/fusion.py` 的 `RetrievalOutcome.filter_diagnostics`
> Policy version：`retrieval-filter-diagnostics/v1`

## 1. 定位与冻结边界

本文登记 D11B 检索融合层的**公共 Python 输出字段**，以便审计、测试和后续
Integration Gate 使用。它不是 IPC、C 轨 Client、OS Agent 对外服务或用户可观察
接口的冻结协议；这些边界当前均为 `NOT_FROZEN`。

`GATE-D11B-DIAGNOSTICS`：首次把本结构跨越任一上述边界前，必须由 D/E 完成
正式 Schema、reason-code 值域、隐私/存在性泄露语义、版本升级与兼容策略的冻结。
C/D/客户端在 Gate 完成前不得硬编码本结构或任一 reason code。

## 2. 公共字段 Schema

`RetrievalOutcome.filter_diagnostics` 必须是下表所列的对象；v1 不增删或改名字段。
每个计数均为非负整数，表示本次调用中的命中数；不支持 `null`、浮点数或字符串
计数。

| 字段 | 类型 | 必填 | 语义 |
|---|---|---:|---|
| `policy_version` | string | 是 | 固定为 `retrieval-filter-diagnostics/v1`。 |
| `input_hit_count` | integer ≥ 0 | 是 | FTS5 与 Vector 原始命中数之和，去重前。 |
| `deduplicated_hit_count` | integer ≥ 0 | 是 | 按 `(user_id, memory_id, version_id)` 精确去重后的命中数。 |
| `hard_filter_passed_hit_count` | integer ≥ 0 | 是 | 通过硬过滤、进入 current-version 检查的命中数。 |
| `current_version_passed_hit_count` | integer ≥ 0 | 是 | 通过 current-version 检查、进入融合候选集的命中数。 |
| `dropped_by_reason` | object<string, integer ≥ 0> | 是 | 过滤掉的去重命中按公共 reason code 聚合的计数；空对象合法，键按字典序输出。 |

同一次调用必须满足：

```text
0 ≤ current_version_passed_hit_count ≤ hard_filter_passed_hit_count
  ≤ deduplicated_hit_count ≤ input_hit_count
sum(dropped_by_reason.values())
  = deduplicated_hit_count - current_version_passed_hit_count
```

`dropped_by_reason` 不记录同一命中的多个原因：硬过滤遵循 fail-closed 检查顺序，
仅计入第一个拒绝原因；`not_current_version` 在硬过滤通过后计入。

## 3. 公共 reason-code 值域

v1 的公共值域是以下封闭集合。实现不得向公共输出写入其他值；新增、删除或改变
任一语义均须发布新的 policy version，并完成本节所述 Gate。

| 分组 | 允许值 |
|---|---|
| 真值与基础过滤 | `missing_truth`、`object_type`、`memory_status`、`sensitivity`、`memory_type` |
| Preference 过滤 | `scene`、`scope`、`validity` |
| Knowledge 过滤 | `knowledge_metadata`、`knowledge_status_mismatch`、`knowledge_type`、`knowledge_category`、`knowledge_source_event`、`knowledge_version`、`knowledge_relation` |
| 其它硬过滤 | `unresolved_conflict` |
| 当前版本检查 | `not_current_version` |
| 安全泛化 | `security_filtered` |

`security_filtered` 是公共安全泛化码：当前实现仅将内部 `cross_user` 聚合到此码。
它**不得**被解释为稳定的跨轨枚举，也不得反推出具体安全策略、用户存在性、命中
数量以外的身份信息或内部拒绝原因。

## 4. 隐私与可见性约束

公共对象只可包含本契约的版本、计数和公共 reason code，禁止出现正文、查询内容、
候选/记忆/版本/用户标识、原始过滤输入、内部异常或精确内部拒绝码（特别是
`cross_user`）。

`_retrieve_graceful_with_internal_diagnostics()` 返回的精确诊断仅供可信内部
telemetry/debug 使用，不是 `RetrievalOutcome` 字段，也不在本文公共字段契约内。
它不得被序列化到 IPC、C 轨、OS Agent 对外服务、客户端或用户可观察输出。

## 5. 兼容与升级

- v1 只保证本仓库内的 Python 调用和测试可审计；不承诺任何跨进程或跨轨兼容性。
- v1 内字段、类型、公共值域和计数语义均为固定候选；破坏性修改必须新建
  `retrieval-filter-diagnostics/vN`，保留或显式迁移旧版本，并更新测试与本契约。
- 在 `GATE-D11B-DIAGNOSTICS` 未关闭前，任何跨边界需求必须先提交 D/E 冻结记录；
  仅提升本文件状态不构成 Gate 关闭。

## 6. 验证锚点

- Schema 和公共脱敏：`memory-service/tests/retrieval/test_v006_fusion.py` 的
  `test_retrieve_graceful_exposes_redacted_filter_diagnostics`。
- 内部 `cross_user` 与公共 `security_filtered` 的隔离：同文件
  `test_internal_filter_diagnostics_keeps_precise_cross_user_internal_only`。
- 实现入口：`memory-service/retrieval/fusion.py` 的
  `_fuse_retrieval_with_diagnostics`、`_to_public_filter_diagnostics` 与
  `retrieve_graceful`。
