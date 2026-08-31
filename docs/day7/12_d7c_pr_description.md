## 背景

D7-C 台账要求在 memory-client 侧落地偏好版本管理 UI / Pipeline Demo / Prototype，对应"完成 C 角色 D7"指令的 D7-C 实施部分。本 PR 在 D5-C Route B + D6-C 基础上扩展，沿用 Demo / Prototype 路线，对齐 D7D Repository `save/list/rollback_preference_version` 接口，登记三个候选 IPC 方法 `preference.version.commit / history / rollback`（不冻结；ADR-016 待立项）。

**声明（Demo / Prototype）**：本 PR 仅为 memory-client 侧 L0 契约 Demo / Prototype，不关闭 C-D5 / C-D6 / C-D7，不声称 SEC-CTX-01 已完成 Runtime 验证，未接入真实 AI Assistant Hook / Chat DB / ChatRecord / model_request / TurnExtractionAdapter / 偏好持久化后端。

## 修改范围

### 1. protocol_adapter.{h,cpp}
- 登记三个候选方法常量：`kPreferenceVersionCommit` / `kPreferenceVersionHistory` / `kPreferenceVersionRollback`
- 不冻结 FRZ-IPC-007 路由表；沿用 ADR-010 候选模式；ADR-016 待立项

### 2. memory_client.{h,cpp}
- 新增 `sendPreferenceCommitEvent()` / `sendPreferenceHistoryRequest()` / `sendPreferenceRollbackEvent()`
- 复用 `sendEventEnvelope()` 共享写链路（trace_id 取 metadata.trace_id）

### 3. view_models/memory_view_model.{h,cpp}
新增三组 Pipeline：
- `runPreferenceCommitPipeline()` → `preference.version.commit`（对齐 `save_preference_version`）
  - 客户端侧敏感预检：`sensitivity=high/critical` 拒绝构造事件、拒绝发送
  - 显式注入 `mapping_status=PENDING_C_CONFIRMATION`
- `runPreferenceHistoryPipeline()` → `preference.version.history`（对齐 `list_preference_versions`）
- `runPreferenceRollbackPipeline()` → `preference.version.rollback`（对齐 `rollback_preference_version`）

状态管理：
- 三组 `lastXxx/stage/busy` Q_PROPERTY（commit / history / rollback）
- 三 busy 独立 pending request id（沿用 D6-C §C1 模式）：commit in-flight 时 rollback 响应不串台
- 扩展 `busy` 合并属性为八 busy 合并：`preChatBusy || postTurnBusy || toolBusy || manualConfigBusy || behaviorBusy || preferenceCommitBusy || preferenceHistoryBusy || preferenceRollbackBusy`
- per-request deadline QTimer（默认 5000ms）；timeout 路由 `failed/timeout`
- status=error 响应明确路由 failed 阶段（沿用 D5-C REWORK §A 修复）

### 4. qml/pages/PreferenceVersionPage.qml（新增）
- 当前版本展示区（user_id / scope / key / value / memory_status / version / is_current）
- 版本历史列表区（include_history 切换）
- 回滚入口（target_version_id 输入 + 发起回滚）
- 跨会话行为联调：复用 D6-C Behavior Pipeline 的 sessionId 触发 `behavior.observe`，演示跨会话行为 → 偏好版本管理的链路联调
- 三组 stage / busy 实时反馈

### 5. qml/main.qml + qml/resources.qrc
- 注册 D7 Preference Version 导航入口与页面 Component

### 6. contracts/examples/preference_version_event.v1.json（新增）
- 候选 schema 样例（commit / history / rollback 三类 payload）
- 标注 CANDIDATE，不冻结；对齐 D7D Repository

### 7. tests/test_d7c_preference_version_management.cpp（新增）
L0 Mock Gateway 契约测试 18 用例：
- §A Commit 5 用例：首版 sent / 敏感 high 拦截 / critical 拦截 / UNSUPPORTED_METHOD → failed / 客户端 deadline timeout
- §B History 3 用例：查询 sent / 空历史 sent / 错误响应 failed
- §C Rollback 3 用例：成功 sent / INVALID_REQUEST failed / deadline timeout
- §D 事件契约 4 用例：commit/rollback/history 嵌套 + mapping_status=PENDING_C_CONFIRMATION
- §E 运行正确性 3 用例：三 busy 独立 pending 不串台 / commit sent 不影响 rollback failed / busy 合并属性反映三组

注册 ctest 目标 `d7c_preference_version_management`。

### 8. docs/day7/11_d7c_task_card.md（新增）
- D7-C 实施任务卡（沿用 D5-C/D6-C Demo/Prototype 路线）
- 前置准备产物：`08_d7c_task_card.md` / `09_d7c_prerequisite_audit.md` / `10_d7c_preference_ipc_contract_draft.md`

### 9. README.md
- 更新当前状态：D7-C Demo / Prototype 扩展
- 新增 D7-C 候选偏好版本方法说明
- 新增 D7-C Pipeline 段落
- 保留 Demo / Prototype 声明；C-D5 / C-D6 / C-D7 保持 OPEN

## 测试结果

### CI（GitHub Actions）
- Workflow: `Memory Client L0 ctest`
- 触发：PR to main，paths `memory-client/**`
- 运行环境：ubuntu-22.04 + qtbase5-dev/qt5-qmake/build-essential
- 构建配置：`-DKYLIN_MEMORY_CLIENT_BUILD_QML_APP=OFF -DKYLIN_MEMORY_CLIENT_BUILD_TESTS=ON`
- 执行命令：`cmake --build ... -j$(nproc)` + `ctest --output-on-failure --verbose`
- 预期结果：ctest 5/5 子目标全绿
  - protocol_adapter
  - memory_client_mock
  - d5_vertical_link_demo
  - d6c_multi_source_adapters
  - **d7c_preference_version_management（新增）**

### 本地验证
- 本地为 Windows 环境，无 Qt5 开发环境；CI ubuntu-22.04 完成构建与 ctest 验证
- 代码静态自审：三 busy 独立 pending / status=error 路由 failed / 敏感预检对齐 D6-C ManualConfig

## 完成定义对照（台账 D7-C）

| 台账项 | 本 PR 落地 |
|--------|-----------|
| 完成手动配置和偏好版本 QML 组件 | PreferenceVersionPage.qml（commit/history/rollback 三段式 UI） |
| 联调跨会话行为输入 | 跨会话行为联调区：复用 D6-C Behavior Pipeline sessionId 触发 behavior.observe |
| 展示当前版本、历史版本和回滚入口 | 当前版本展示区 + 历史版本列表 + 回滚入口 |

## 不修改的范围

- 不修改 D7D Repository 侧 `save/list/rollback_preference_version` 实现
- 不冻结 FRZ-IPC-007 路由表（preference.version.* 为候选方法）
- 不新增 ADR-016（待立项）
- 不修改 memory.store（保持 UNSUPPORTED_METHOD，ADR-010 §决策不动）
- 不修改 D5-C/D6-C 既有 Pipeline 逻辑（仅扩展 busy 合并属性）
- 不接入真实 AI Assistant Hook / Chat DB / ChatRecord / 偏好持久化后端

## 风险与后续

- **候选方法不冻结**：`preference.version.commit / history / rollback` 为候选 IPC 方法，ADR-016 待立项；D 轨 Gateway 侧未注册 handler，生产环境调用将返回 UNSUPPORTED_METHOD（符合预期）
- **C-D7 保持 OPEN**：本 PR 仅完成 memory-client 侧 L0 Demo，不关闭 C-D7；待 D 轨 Gateway 注册 handler + 真实偏好持久化后端联调后方可关闭
- **SEC-CTX-01 未完成 Runtime 验证**：本 PR 不声称 SEC-CTX-01 已完成
- **跨会话行为联调为 Demo**：UI 触发的 behavior.observe 仅演示链路，不声称真实跨会话行为→偏好持久化链路已完成
