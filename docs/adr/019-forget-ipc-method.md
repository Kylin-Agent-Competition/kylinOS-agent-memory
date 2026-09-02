# ADR-019：新增 `forget.preview` / `forget.execute` IPC 写方法

- **状态**：✅ 已采纳（D 已决策；Reviewer E 已签署）
- **日期**：2026-09-02
- **决策人**：D（周子腾）
- **Reviewer**：E（谢嘉然），PR #112 `APPROVED`（2026-09-02）
- **决策版本**：`d10d-adr019-v1`
- **适用范围**：FRZ-IPC-007 扩展
- **激活状态**：`CANDIDATE / BLOCKED_BY_HOST_MAPPING`
- **对外能力状态**：`PARTIAL / staged implementation`；生产默认不注册，未注册返回 `UNSUPPORTED_METHOD`
- **权威依据**：`docs/day10/16_d10d_forget_contract_plan_v0.3.md`、`docs/day10/17_d10d_adr015_019_draft.md`、ADR-015、PR #99、PR #112

## 背景

精准遗忘必须把 Preview 与 Execute 分成两个明确方法。Execute 必须验证一次性确认凭据和幂等键；硬删除后审计不得保留正文。现有 FRZ-IPC-007 没有遗忘方法。

## 候选方案

1. **方案 A（采纳）**：新增 `forget.preview` 与 `forget.execute` 两个写方法。
2. 单一 `forget` 方法内部分阶段：不能在路由契约上强制确认边界。
3. Preview 响应中内嵌执行：确认前产生副作用，违反安全红线。

## 决策

采纳方案 A。两方法为 FRZ-IPC-007 的兼容新增，不修改 FRZ-IPC-001～006 的帧结构、envelope、错误码、deadline 或幂等语义：

| method | 类型 | 激活状态 | 默认生产行为 |
|---|---|---|---|
| `forget.preview` | 写方法：解析目标、落计划、生成凭据 | `CANDIDATE / BLOCKED_BY_HOST_MAPPING` | 不注册 → `UNSUPPORTED_METHOD` |
| `forget.execute` | 写方法：校验凭据、执行 staged soft delete、写审计 | `CANDIDATE / BLOCKED_BY_HOST_MAPPING` | 不注册 → `UNSUPPORTED_METHOD` |

只有独立可信宿主身份映射、安全 Gate 和相应 Runtime 闭环具备后，才可经变更控制升级 ACTIVE。

## `forget.preview` 契约

请求 payload 为 flat `snake_case`：

| 字段 | 类型 | 必填 | 语义 |
|---|---|:---:|---|
| `forget_plan_id` | string | ✅ | 宿主生成的计划 ID |
| `user_id` | string | ✅ | 声明身份；禁止模型生成，ACTIVE 时须与可信宿主身份先行比对 |
| `forget_mode` | string | ✅ | `single_item/session/topic/time_window/full_reset` |
| `target_selector` | string | ✅ | 仅用于本次解析；Preview 后清除，不长期保存明文 |
| `target_type` | string | ✅ | `knowledge/preference/event/all` |
| `target_id` / `target_session_id` / `target_topic` / `target_time_range` | string | 条件 | 按模式互斥校验 |
| `requires_confirmation` | bool | ✅ | 宿主给定，禁止模型生成 |
| `is_cascade` | bool | 否 | 默认 false |
| `delete_mode` | string | 否 | 默认 `soft`；仅可信宿主/显式用户操作可指定；LLM 不得终判 |

成功响应沿用冻结 envelope，`data` 至少包含：`forget_plan_id`、`status='awaiting_confirmation'`、`affected_count`、`selection_hash`、`confirmation_token`、`token_expires_at`、`requires_confirmation`、`is_cascade`、`delete_mode`。确认令牌明文只在此次响应返回一次。

## `forget.execute` 契约

请求 payload：

| 字段 | 类型 | 必填 | 语义 |
|---|---|:---:|---|
| `forget_plan_id` | string | ✅ | 已完成 Preview 的计划 |
| `user_id` | string | ✅ | 声明身份；ACTIVE 时须先与可信宿主身份比对 |
| `confirmation_token` | string | ✅ | 一次性明文凭据，仅用于本次校验 |

`idempotency_key` 只取 FRZ-IPC-006 envelope 顶层字段，payload 不携带第二份真源。成功响应 `data` 至少包含：`forget_plan_id`、`status`、`affected_count`、`executed_count`、`delete_mode`、`has_vector_cleanup`、`executed_at`、`audit_id`。

## 状态机与确认凭据

- 状态机：`pending → previewing → awaiting_confirmation → executing → completed / failed / rolled_back`。
- 凭据使用随机 32B 生成，默认 TTL 300 秒；服务端仅保存 SHA-256。
- 凭据绑定 `user_id + forget_plan_id + selection_hash`，必须同时验证用户、计划、选择集合、未过期与未消费。
- 成功事务内消费凭据并置 NULL；过期、绑定不符或已消费均 fail-closed。
- `affected_count` 是 Preview 冻结数量，`executed_count` 是真实成功数量；不一致不得返回 `completed`。

## 固定编排顺序

`forget.preview`：

1. envelope/payload 结构校验；
2. trusted identity precheck（ACTIVE profile，先于用户作用域幂等缓存查找）；
3. E 轨 `ForgetPlan` 创建/Preview 前校验；
4. 对 `single_item/session` 执行用户隔离的确定性解析；本期不支持的模式 fail-closed；
5. 计算 `resolved_target_ids`、`affected_count`、`selection_hash`；
6. 在 `UoW.execute_idempotent` 单事务内落计划、保存 token hash、清除 selector 明文并缓存成功响应。

`forget.execute`：

1. envelope/payload 结构校验；
2. trusted identity precheck（ACTIVE profile，先于用户作用域幂等缓存查找）；
3. 读取用户隔离的计划并校验 `awaiting_confirmation`；
4. 校验 delete mode、模式/目标支持边界、凭据绑定/TTL/未消费；
5. 在 `UoW.execute_idempotent` 单事务内切换 `executing`、执行真实 soft delete、核对数量、消费 token、写零正文审计、写 terminal 状态及必要 Outbox；
6. 仅当 `executed_count == affected_count` 时进入 `completed` 并返回成功响应。

## 幂等与错误语义

- 三元组 `(user_id, session_id, idempotency_key)` 复用 FRZ-IPC-005 / ADR-006；成功请求可 cache replay，失败请求不缓存。
- request fingerprint 不得由 selector、正文或 confirmation token 原文派生；敏感输入统一使用 `<SENSITIVE-OMITTED>` 占位。
- 同三元组、不同 privacy-safe request fingerprint → `INVALID_REQUEST`；不得静默复用首次响应。
- payload/模式/selector/凭据/状态/数量不合法以及未支持执行路径 → `INVALID_REQUEST`；deadline → `TIMEOUT`；内部异常 → `INTERNAL_ERROR`；未注册 → `UNSUPPORTED_METHOD`。不新增错误码，不回显正文、凭据或敏感详情。

## 安全与 staged Runtime 边界

- `payload.user_id` 仅是声明，不能作为独立可信身份源；生产 ACTIVE 必须先完成独立可信宿主身份注入与 fail-closed 比对，cache replay 不得绕过。
- `delete_mode=hard`、`is_cascade=true`、`full_reset`、`time_window`、`topic` 和 event 目标在本期 Runtime 未闭环，必须拒绝执行；不得自动降级为 soft delete 后报告成功。
- `target_selector`、`target_topic`、confirmation token 明文不得写入计划长期态、审计、Outbox、日志、响应缓存、导出或临时输出。
- Vector 清理仍由 TD-033 跟踪；`has_vector_cleanup` 只能反映真实状态，不能作为已清理声明。

## 影响与回滚

- Gateway 增加显式注册 seam；production 默认 registry 保持不注册，两方法继续返回 `UNSUPPORTED_METHOD`。
- 测试/validation profile 可显式注册以验证服务端 staged 链路，但不能上浮为宿主 ACTIVE 证据。
- 经后续 ADR 撤销时，删除两个路由条目、handler 与显式注册 seam；ADR-015 数据回滚按其自身流程执行。

## 签署与证据

- D（周子腾）：2026-09-02，D1～D6 全部采用推荐方案。
- Reviewer E（谢嘉然）：2026-09-02，PR #112 终局 `APPROVED`。
- 证据边界：签署使 FRZ-IPC-007 扩展正式生效；两方法仍为 `CANDIDATE / BLOCKED_BY_HOST_MAPPING`，对外保持 `PARTIAL / staged implementation`，不构成 Runtime 或麒麟宿主验证证据。
