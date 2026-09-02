# ADR-018：知识详情、冲突对比与生命周期状态只读 IPC

- **状态**：✅ 已采纳（PR #122 契约草案已签署；本 canonical write-back 待 Reviewer E 最终一致性确认）
- **日期**：2026-09-02
- **责任轨道**：D（IPC / 持久化）；E（业务语义、安全与冻结审查）
- **Reviewer**：E（`lovezy0730-create`），PR #122 HEAD `c6ecbae` `APPROVED`（2026-09-02）
- **决策版本**：`d8d-adr018-v1`
- **适用范围**：FRZ-IPC-007 additive 扩展
- **激活状态**：`CANDIDATE / BLOCKED_BY_TRUSTED_IDENTITY_AND_D8D_PERSISTENCE`
- **默认生产行为**：不注册，返回 `UNSUPPORTED_METHOD`
- **批准依据 / 不可变契约附件**：`docs/day8/07_d8d_adr017_018_draft.md` 第二部分（PR #122 批准 HEAD `c6ecbae`）。该文件头部的 `DRAFT / 正式生效=NO` 是提交时历史状态；PR #122 APPROVE 已批准其契约内容，当前 canonical 生效状态以本 ADR、FRZ write-back 及 Reviewer E 最终一致性确认为准。

## 背景

D8-C 需要查询知识详情、冲突候选与生命周期状态，但现有 FRZ-IPC-007 没有对应方法。三条查询都依赖 ADR-017 的 SQLite 真源与可信宿主身份；在两项依赖闭合前不得生产激活。

## 决策

FRZ-IPC-007 兼容新增三个只读候选方法：

| method | 类型 | 激活状态 | 默认生产行为 |
|---|---|---|---|
| `knowledge.detail` | 单知识详情及 relation/evidence 分页 | `CANDIDATE / BLOCKED_BY_TRUSTED_IDENTITY_AND_D8D_PERSISTENCE` | 不注册 → `UNSUPPORTED_METHOD` |
| `conflict.compare` | 冲突候选分页 | 同上 | 不注册 → `UNSUPPORTED_METHOD` |
| `lifecycle.status` | 生命周期状态查询/分页 | 同上 | 不注册 → `UNSUPPORTED_METHOD` |

三方法复用 FRZ-IPC-001～006 的长度前缀 JSON、envelope、五错误码、deadline 与顶层字段，不修改既有方法语义。

## 身份与 scoped read

- 权威用户身份只取 `RequestContext.user_id`；validation/test profile 必须显式注入 synthetic trusted identity。
- `knowledge.detail` 与 `conflict.compare` 不接受 payload `user_id`。
- `lifecycle.status` 为 D8-C 兼容保留 required 声明型 `payload.user_id`，但必须在任何 DB/cache 查询前与 `RequestContext.user_id` 严格相等比较并 fail-closed；不一致返回 `INVALID_REQUEST`。
- unknown、cross-user、legacy-unmapped 与 stale version 统一返回 scoped empty object，不泄露对象是否属于其他用户。

## `knowledge.detail`

- `memory_id` required；`version_id` optional 且提供时精确匹配；`include_evidence/include_conditions` 默认 true。
- `relation_limit` 是 strict integer，默认 25、范围 1..25；cursor 为 `(created_at, relation_id)` 成对提供、stable、exclusive。
- `legacy_unmapped` 返回 `{"found": false}`。
- `evidence_unmapped` 允许受控只读：`found=true` 且 `evidence_tier=null` 字段显式存在；它不进入 Lifecycle Worker、`lifecycle.status`、ConflictResolutionPolicy 或 conflict truth。
- `knowledge_type/conditions` 只读 ADR-017 结构化列；conditions 经 `IpcTextProjectionGate`（NFKC、控制字符拒绝、UTF-8 最大 256 bytes、敏感检测 fail-closed）。
- evidence 只返回 `{relation_id, source_event_id, is_primary}`，不返回自由文本 evidence。
- relation/evidence 同页稳定推进，continuation 必须无遗漏、无重复，不得静默截断。

## `conflict.compare`

- `memory_id` required；`version_id` optional；`include_resolved` 默认 false。
- `limit` 是 strict integer，默认 25、范围 1..25；cursor `(detected_at, conflict_id)` 成对提供、stable、exclusive。
- scoped not-found/无冲突返回 `{"candidates": [], "next_cursor": null}`。
- 只投影固定结构字段；`conflict_summary` 只能是 ADR-017 的系统码，不返回内部 evidence、`resolved_by` 或其他用户标识。

## `lifecycle.status`

- `memory_id` 精确查询与列表 cursor 互斥；列表 `limit` 为 strict integer，默认 50、范围 1..100。
- 只返回 `eligible` knowledge；legacy/evidence-unmapped 均不出现在本方法。
- status/type/evidence tier/access counters 只读 ADR-017 SQLite 真源；不回显正文、conditions 或 evidence。

## 64KB 与分页门禁

- `knowledge.detail` 与 `conflict.compare` 每加入一项，都必须调用真实 `gateway.protocol.encode()` 对完整响应 envelope 试编码。
- `MAX_MSG_LEN=65536` 约束 UTF-8 JSON body；外层 4-byte length prefix 不计入 body 上限。
- 若下一项导致超限，当前页在上一完整项结束并返回 continuation cursor；禁止截字段、吞项、重复或假成功。
- 单项在已冻结 ID/成员上限内仍无法装入空页时返回 `INTERNAL_ERROR`，审计只记录结构化 ID。

## 安全、激活与回滚

- production registry 默认不注册三方法；只有可信宿主身份与 ADR-017 Runtime/持久化闭环完成，并经新 Gate 审查后才可升级 ACTIVE。
- payload extra fields、bool-as-int、宽松 ID/cursor 归一化均拒绝。
- 经后续 ADR 撤销时，删除三条候选路由与 explicit validation registry seam；ADR-017 数据回滚按其自身流程处理。

## 签署与证据

- D 决策：采用方案 A。
- Reviewer E：PR #122 HEAD `c6ecbae`，`ADR-018: APPROVED`。
- 审查结论：trusted identity、scoped empty、结构化投影、分页与 64KB 边界均可冻结。
- 证据边界：签署使方法契约生效，但三方法仍为候选且 production 默认不注册；不构成 Runtime、L1/L2 或麒麟宿主验证证据。
