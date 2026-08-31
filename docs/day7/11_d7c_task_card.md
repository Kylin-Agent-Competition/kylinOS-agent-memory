# D7C 实施任务卡：偏好版本管理 UI / Pipeline Demo / Prototype

> 状态：IMPLEMENTATION（实施版本；前置准备产物见 `08_d7c_task_card.md` / `09_d7c_prerequisite_audit.md` / `10_d7c_preference_ipc_contract_draft.md`）
> 本任务卡对应“完成 C 角色 D7”指令的 D7-C 实施落地，沿用 D5-C / D6-C Demo / Prototype 路线。

| 字段 | 内容 |
|------|------|
| 任务编号 | D7-C（实施） |
| 任务标题 | 偏好版本管理 UI / Pipeline Demo（commit / history / rollback）+ 跨会话行为联调 |
| 责任轨道 | C（刘承恩）；当前暂由 B（高翌哲）代实施 |
| 基线 | `origin/main@c1ee840`（已含 D7D #90 偏好版本持久化）+ feat/C-d6-multi-source-adapters |
| 分支 | `feat/C-d7-preference-version-management` |
| 工作类型 | 新增功能（feature，Demo / Prototype） |
| 完成定义（台账 D7-C） | 用户可发起偏好版本 commit / 查询 history / 发起 rollback；UI 展示当前版本与历史链；跨会话行为输入可触发偏好事件 |

## 一、实施范围（与 Demo / Prototype 声明一致）

本任务在 `memory-client` 侧落地偏好版本管理的 L0 Demo / Prototype，沿用 D5-C / D6-C 路线：

1. `protocol_adapter.{h,cpp}`：登记三个候选方法常量 `preference.version.commit` / `preference.version.history` / `preference.version.rollback`（不冻结 FRZ-IPC-007 路由表，沿用 ADR-010 候选模式）。
2. `memory_client.{h,cpp}`：新增三个候选写方法 `sendPreferenceCommitEvent` / `sendPreferenceHistoryRequest` / `sendPreferenceRollbackEvent`，复用 `sendEventEnvelope` 共享写链路。
3. `view_models/memory_view_model.{h,cpp}`：新增偏好版本 Pipeline（commit / history / rollback）+ 三组 `lastXxx/stage/busy` Q_PROPERTY 与独立 pending request id，沿用 D6-C 双 busy 拆分模式；扩展 `busy` 合并属性以包含三组新 busy。
4. `qml/pages/PreferenceVersionPage.qml`：当前版本展示 + 历史版本列表 + 回滚入口 + 跨会话行为联调触发按钮。
5. `qml/main.qml` + `qml/resources.qrc`：注册新页面与导航入口。
6. `contracts/examples/preference_version_event.v1.json`：候选 schema 样例（commit / history / rollback 三类）。
7. `tests/test_d7c_preference_version_management.cpp`：L0 Mock Gateway 契约测试，注册 ctest 目标 `d7c_preference_version_management`。
8. `README.md`：更新 D7-C 状态；保留 Demo / Prototype 声明。

## 二、不修改的范围

- 不实现 A / B / D / E 轨代码、契约、业务策略或持久化。
- 不修改 FRZ-IPC-007 冻结路由表；候选方法仅登记在客户端 `methods` 命名空间。
- 不修改 D7D 的 `memory_items / memory_versions / preference_version_operations` 表结构或 Repository 接口。
- 不实现真实 IPC 服务端 handler；生产 Gateway 默认返回 `UNSUPPORTED_METHOD`，由 Mock Gateway 在测试态注入 handler 演示。
- 不声称关闭 C-D7；不声称已接入真实 AI Assistant Hook / Chat DB / ChatRecord / 真实偏好持久化后端。

## 三、IPC 候选方法（不冻结）

沿用 FRZ-IPC-006 envelope（`protocol_version / request_id / trace_id / method / deadline_ms / idempotency_key? / payload`）。三个候选方法对齐 D7D Repository 接口：

| 候选 method | 请求 payload 关键字段 | 响应 `data` 关键字段 | 对齐 D7D |
|-------------|----------------------|----------------------|---------|
| `preference.version.commit` | `metadata{...}` + `preference{user_id, key, scope, value, memory_status, is_temporary, should_persist, confidence, sensitivity_level, mapping_status}` | `item{version, memory_status, previous_version_id, is_current, created_at}` | `save_preference_version` |
| `preference.version.history` | `metadata{...}` + `query{user_id, key, scope, include_history}` | `items[]`（按版本链排序，含 superseded） | `list_preference_versions` |
| `preference.version.rollback` | `metadata{...}` + `rollback{user_id, key, scope, target_version_id, idempotency_key?}` | `item{version, memory_status, previous_version_id, rollback_of_version_id, is_current, created_at}` + `history[]` | `rollback_preference_version` |

## 四、L0 测试矩阵（test_d7c_preference_version_management.cpp）

| 用例 | 范围 |
|------|------|
| §A Commit | A1 首版 commit → `preferenceCommitStage=sent`；A2 敏感内容（high）客户端侧拦截 → `failed`；A3 critical 同样拦截；A4 UNSUPPORTED_METHOD 响应 → `failed`；A5 客户端 deadline 超时 → `timeout` |
| §B History | B1 查询成功 → `preferenceHistoryStage=sent` + `lastPreferenceHistoryEvent` 非空；B2 空历史 → 仍 `sent`，事件 JSON 含空 items；B3 错误响应 → `failed` |
| §C Rollback | C1 回滚成功 → `preferenceRollbackStage=sent` + 事件含 `target_version_id`；C2 不存在的目标 → 服务端 INVALID_REQUEST，`failed`；C3 客户端 deadline 超时 → `timeout` |
| §D 事件契约 | D1 commit 事件含 `metadata` + `preference` 嵌套；D2 rollback 事件含 `metadata` + `rollback` 嵌套；D3 history 查询含 `metadata` + `query` 嵌套；D4 `mapping_status=PENDING_C_CONFIRMATION` 显式注入 |
| §E 运行正确性 | E1 三 busy 独立 pending：commit in-flight 时 rollback 响应不串台；E2 commit sent 不影响 rollback failed；E3 `busy` 合并属性正确反映三组 busy |

## 五、变更记录

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| v1 | 2026-08-31 | 高翌哲（代 C 轨 D7-C） | 实施任务卡：定义 D7-C Demo / Prototype 落地范围、IPC 候选方法对齐 D7D、L0 测试矩阵；与准备产物（08/09/10）配套 |
