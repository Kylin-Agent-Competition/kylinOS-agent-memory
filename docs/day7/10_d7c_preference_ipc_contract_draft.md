# D7-C 偏好 IPC 契约建议草案（供 D 轨对齐）

> 状态：`CANDIDATE_SYNC`（建议草案，仅供 D 轨对齐的起点，**不冻结任何契约 / IPC / 数据库结构**）。
> 作者：高翌哲（B 轨代 D7-C）。本文件不替 D 轨冻结 FRZ-IPC-007 路由表、payload schema 或 DB DDL。
> 目标：缩小 D 轨与 C 轨对“偏好增改 / 历史 / 回滚”接口的交界缝隙，便于 D 轨落地持久化与 IPC 方法后 D7-C 实现 UI。
>
> **状态更新（2026-08-31，D7C PR #87）**：本草案已获用户授权落地为 D 轨契约变更，随 D7C PR #87 实现——
> `memory-service/gateway/preference_handlers.py` 新增 `preference.list / create / update / rollback / history` 五个活跃方法（production 默认注册），方法名与 payload 语义与本草案一致。与草案的差异如实记录：
> ① D7D 持久化模型无 `category / explicitness / confidence` 列，故 payload 未包含这些字段（E 轨 Schema 未终审，不制造不可持久化字段）；
> ② `memory_status` 未显式传入时按 D3 §7.9 安全默认推导（临时/不持久化 → candidate，否则 active），显式传入则校验六值枚举；E 轨 `preference_version_policy` 的业务决策未在 handler 内实现（本模块不实现 E 轨策略）；
> ③ 错误码沿用 FRZ-IPC-002 五枚举：偏好领域异常（版本不存在 / 幂等冲突 / 证据冲突）统一映射为 `INVALID_REQUEST`。

## 一、依据来源

| 来源 | 关键语义 |
|------|----------|
| `memory-service/domain/preference.py` | `Preference` 字段：`preference_id / user_id / expression_type / preference_scope / preference_key / preference_value / confidence_score / memory_status / is_active / is_temporary / should_persist / should_decay / evidence_event_ids / version / created_at / updated_at / requires_confirmation`；可选 `previous_version_id / decay_after_at / extracted_entities`；校验器 `_version_chain / _temporary_boundary / _time_order` |
| `memory-service/domain/enums.py` | `PreferenceScope` 五值 `global/topic/tool/session/time_window`；`MemoryStatus` 六值 `active/superseded/deprecated/expired/removed/candidate` |
| `memory-service/service/preference_version_policy.py` | 五种业务动作 `CREATE/COEXIST/UPDATE/NO_OP/ROLLBACK` + `REJECTED` 防御态；fixed reason_code 集合；版本号 `max(现存)/+1`、`previous_version_id`、历史保留、rollback 不删中间版本 |
| `memory-service/db/repositories.py`（D7D #90，`origin/main@c1ee840`） | 持久化真源：`save_preference_version(conn,*, user_id, preference_key, preference_scope, preference_value, memory_status, evidence_fingerprint, idempotency_key?, request_fingerprint)`；`get_preference_version(conn,*, user_id, preference_version_id:int)`；`get_current_preference_version(conn,*, user_id, preference_key, preference_scope)`；`list_preference_versions(conn,*, user_id, preference_key, preference_scope)`；`rollback_preference_version(conn,*, user_id, preference_version_id:int, idempotency_key?, request_fingerprint)`。聚合键为 `memory_items`（user_id+key+scope），版本号与链由 `memory_versions`（`version / previous_version_id / rollback_of_version_id / is_current`）承载；回滚=追加新 current 版本，不覆盖历史 |
| `migrations/versions/20260831_preference_versions.py`（D7D #90） | 表：`memory_items`（`current_version_id` 指针、`uq_memory_items_user_key_scope` 唯一、`ck_memory_items_preference_scope` 五值 CHECK）；`memory_versions`（`uq_memory_versions_item_version` 唯一、`uq_memory_versions_current` 部分唯一 `is_current=1`、`idx_memory_versions_idempotency/evidence/status`）；`memory_version_receipts`（回滚/审计 operation_kind） |
| `memory-service/retrieval/contracts.py` | 既有检索 filter 字段：`scene_id / allowed_scene_ids / include_unscoped / as_of / valid_from / valid_to` |
| E 轨验收 `day7-e-ui-version-acceptance-v1.md` | C 轨 UI 需呈现 CREATE/COEXIST/UPDATE/NO_OP/ROLLBACK + 临时偏好 + 跨用户隔离 |

## 二、建议的 IPC 方法（`CANDIDATE_SYNC`，非冻结）

沿用 FRZ-IPC-006 envelope（`protocol_version / request_id / trace_id / method / deadline_ms / idempotency_key? / payload`）。建议新增以下方法（供 D 轨决策，命名可按 D 轨惯例调整）：

| 建议 method | 请求 payload 关键字段 | 响应 `data` 关键字段 | 说明 |
|-------------|----------------------|----------------------|------|
| `preference.list` | `user_id`、`scope?`、`key?`、`include_history` | `items[]`（含 `version` / `memory_status` / `previous_version_id` / `created_at` / `updated_at`） | 列出当前用户偏好及其历史版本链 |
| `preference.create` | `user_id`、`key`、`value`、`scope`、`category`、`explicitness`、`is_temporary`、`should_persist`、`confidence`、`evidence_event_ids` | `item`（首版 `version=1`、`previous_version_id=None`） | 触发 CREATE / COEXIST（由策略而非 UI 决定） |
| `preference.update` | `user_id`、`key`、`scope`、`new_value`、`idempotency_key` | `item`（`version` 递增、`previous_version_id` 指向当前 active） | 触发 UPDATE / NO_OP（值相同则不增版本） |
| `preference.rollback` | `user_id`、`key`、`scope`、`target_version` 或 `target_version_id`、`idempotency_key` | `item`（`current_version` 切换至目标版本）+ `history` | 触发 ROLLBACK；中间历史版本保留 |
| `preference.history` | `user_id`、`key`、`scope` | `items[]`（全版本链，含 superseded） | 供 UI 渲染历史列表 |

> 对齐说明（D7D #90 已合入）：以上 `preference.list` 对应 `list_preference_versions`（UI 历史列表）；`preference.create / update` 对应 `save_preference_version`（`memory_status` 由 E 轨策略决定，`evidence_fingerprint / request_fingerprint / idempotency_key` 由 handler 或调用方产生，见下）；`preference.rollback` 对应对 `rollback_preference_version`（`target` 用 D7D 的 `preference_version_id:int`，非 `Preference.preference_id`）。D7C 只消费结果，`memory_status`、是否 `active/superseded`、版本号递增、`is_current` 唯一性均由 D 轨 Repository/策略保证。

## 三、建议 payload 字段与契约约束（非冻结）

- **用户隔离**：所有 method 均显式携带 `user_id`；服务端强制以 `user_id` 隔离过滤，跨用户一律拒绝（D3 §7.1）。
- **版本链**：`version=1` → `previous_version_id=None`；`version>1` → 必填（`_version_chain`）。`current_version` 指向链内唯一 active。
- **版本号单调**：`next_version = max(同 user_id+key+scope 链内全部现存记录的 version)+1`，含历史 superseded，不回用旧号（对应 TD-023）。
- **临时/长期边界**：`is_temporary=true` 或 `should_persist=false` 时 `memory_status` 只能在 `candidate/expired`，不得晋升 active（D3 §7.9）。
- **NO_OP**：同 key+scope+value 相同 → 不产生新版本、不推进 `current_version`。
- **ROLLBACK**：切换 `current_version` 至目标历史版本，中间版本保留不删除；目标必须是同 user_id+key+scope 链内历史版本。
- **时间**：`created_at/updated_at/valid_from/valid_to/as_of` 均为 aware UTC，半开区间 `valid_from <= as_of < valid_to`（空边界不限）。
- **回滚后再次 UPDATE**：仍按链内 `max(version)+1`，避免版本号复用。

## 四、与 D 轨的待确认点

1. 新增方法是否纳入 FRZ-IPC-007 路由表（D 轨决策），还是复用 `memory.retrieve` / 既有方法？
2. `current_version` 指针与版本链维护：D7D **已实现**（`memory_items.current_version_id` + `memory_versions`，`origin/main@c1ee840`），C 轨只消费结果；需 D 轨确认 handler 复用此接口时 `user_id` 强制过滤与跨用户拒绝语义不变。
3. `idempotency_key` / `request_fingerprint` 是否由偏好 IPC 写 handler 沿用 D7D 幂等语义（本次自 D 轨确认）；D7C 调用方是否须随写请求携带 `idempotency_key`。
4. `memory_status` 取值与“临时→长期”边界：D7D `save_preference_version` 要求 `memory_status`，但其 CHECK 约束仅限 `active/superseded/deprecated/expired/removed/candidate`；由 E 轨策略决定并传值，D7C 不自行判定；需 D 轨确认 handler 如何调用 E 轨 `preference_version_policy` 或在持久化层前置定型。
5. 错误码是否沿用 FRZ-IPC-002 五枚举（`UNSUPPORTED_METHOD / INVALID_REQUEST / PROTOCOL_ERROR / TIMEOUT / INTERNAL_ERROR`），还是需为“版本冲突 / 回滚目标不存在”（D7D `PreferenceVersionNotFoundError / IdempotencyConflictError / EvidenceConflictError`）等新增语义（D 轨决策）。

## 五、结论

- 本文件是 D7-C 工作清单第 2 项「确定偏好 CRUD / 历史 / 回滚的 IPC 方法与 payload 契约」的**建议起点**；已随 D7C PR #87（用户授权 D 轨契约变更）落地为 `preference.*` 方法（见文件头状态更新），方法名与 payload 语义与本草案一致。
- D7D `save/get_current/list/rollback_preference_version` 已就绪（`origin/main@c1ee840`）；D7-C 第 3–5 项实现与 L0 测试已写入，第 6–7 项（跨会话联调 / 麒麟 L2）待 VM 执行后补充证据。
