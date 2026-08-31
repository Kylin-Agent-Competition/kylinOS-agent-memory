# D7-C 前置条件核对结论（工作清单第 1、2 项）

> 本文件为 D7-C 前置条件核对结论（对应任务卡 `08_d7c_task_card.md` 第五节工作清单第 1、2 项）。
> 结论原基于 `origin/main` `8ab369b`（2026-08-31 同步）；本次校对（2026-08-31）已重新基于 `origin/main@c1ee840`（含 D7D #90）核对，并如实标注结论更新。所有结论均取自实际代码与冻结契约，非推测。

## 一、核对结论：D 轨版本持久化已实现（本次校对更新，原为「未实现 → 关键阻塞」）

默认分支 `origin/main@c1ee840` 上，**D 轨版本持久化已由 D7D #90 实现**，具体证据如下。

| 核对项 | 结论 | 证据 |
|--------|------|------|
| `memory_items` 聚合表（user_id+key+scope 唯一、含 current 指针） | 已实现 | `migrations/versions/20260831_preference_versions.py`：`memory_items`（`id / user_id / preference_key / preference_scope / current_version_id`，`uq_memory_items_user_key_scope` 唯一索引 + `ck_memory_items_preference_scope` 五值 CHECK） |
| `previous_version_id` / `rollback_of_version_id` 版本链 | 已实现 | `20260831_preference_versions.py`：`memory_versions`（`version / previous_version_id(FK) / rollback_of_version_id(FK)`，`uq_memory_versions_item_version` 唯一 + `uq_memory_versions_current` 部分唯一 `is_current=1`） |
| 独立偏好版本历史表与回滚审计表 | 已实现 | `memory_items` + `memory_versions` + `memory_version_receipts`（operation_kind / memory_version_id FK）；`db/repositories.py::save_preference_version / list_preference_versions / rollback_preference_version` |
| `current_version_id` 指针语义 | 已实现 | `memory_items.current_version_id`；Repository `get_current_preference_version` 读取、`rollback_preference_version` 切换（追加新 current 版本，不覆盖旧历史） |
| 偏好版本增改/回滚事务持久化 | 已实现 | `db/repositories.py` 的 `save/get_current/list/rollback_preference_version`（均强制 `user_id` 过滤）；迁移 `20260831_preference_versions.py` 可升级/回退；`migrations/alembic.ini` 同步 |

## 二、IPC 方法现状（D 轨契约边界，随 D7C PR #87 更新）

| 核对项 | 结论 | 证据 |
|--------|------|------|
| 基线（本文件初版）活跃方法仅 `echo / health / memory.retrieve` | 是（初版结论，`c1ee840` 复核） | `memory-service/gateway/handlers.py::register_default_handlers` 仅注册 `echo / health / memory.retrieve`；`memory.store` 返回 `UNSUPPORTED_METHOD` |
| 是否有偏好增改/历史/回滚方法 | **已由 D7C PR #87 实现**（原唯一硬依赖已解除；契约冻结前条件注册） | 新增 `memory-service/gateway/preference_handlers.py`：`preference.list / create / update / rollback / history` 五个方法（`CANDIDATE_SYNC`/ADR-016 待立项，**production 默认不注册→UNSUPPORTED_METHOD，仅 `--register-preference-handlers` 显式激活**，HIGH-1 返工）；`protocol_adapter.h/.cpp` 同步新增方法常量；`db/repositories.py` 新增 `list_preference_items` |
| `memory.retrieve` 是否已接主链 | 否 | handlers.py `memory_retrieve_handler` 返回“真实空上下文（检索主链后续接入，禁止假数据）” |

## 三、客户端（C 轨）现状（随 D7C PR #87 更新）

| 核对项 | 结论 | 证据 |
|--------|------|------|
| `MemoryViewModel` 能力（初版） | 含连接/健康/检索 + D5-C 管线方法（`runPreChatPipeline` / `runPostTurnPipeline` / `buildTurnFinalizedEventJson` 等）；**原无偏好读写 `Q_INVOKABLE`** | `memory-client/src/view_models/memory_view_model.h`（按 Reviewer LOW-1 修正描述） |
| 偏好 CRUD / 历史 / 回滚接口 | **已由 D7C PR #87 新增**：`loadPreferences / loadPreferenceHistory / createPreference / updatePreference / rollbackPreference` + `preferenceItems / preferenceHistory / preferenceStage / preferenceError / lastPreferenceAction / lastPreferenceItem` 属性 | `memory_view_model.h/.cpp`、`memory_client.h/.cpp`、`PreferenceEditorPage.qml` |

## 四、D7-C 工作项前置达标性划分（随 D7C PR #87 更新）

| 工作项 | 前置条件 | 前置是否达标 | 状态 |
|--------|----------|--------------|------|
| 1 核对 D 轨版本持久化与 IPC 方法现状 | 无 | 达标 | 本文件已完成 |
| 2 确定偏好 CRUD / 历史 / 回滚的 IPC 与 payload 契约 | D 轨版本持久化（已达标）＋ IPC 方法 | **已达标（本 PR 落地）** | 已完成（见 `10_d7c_preference_ipc_contract_draft.md`） |
| 3 客户端新增偏好读/写/历史/回滚接口 | 第 2 项契约 | 达标（本 PR 实现，编译待 CI ctest） | 已实现 |
| 4 `PreferenceEditorPage.qml` 增改/当前/历史/回滚 | 第 3 项接口 | 达标（交互证据待 L2） | 已实现 |
| 5 临时/长期展示区分 + 跨用户隔离渲染 | 第 4 项 | 达标（UI + Repository 双层） | 已实现 |
| 6 跨会话行为输入联调 | 第 5 项 + 宿主链路 | **未达标（需麒麟宿主）** | 待 L2 |
| 7 本地回归 + 麒麟宿主 L2 验证 | 第 3–6 项 | 部分达标（L2 待执行） | 服务端 L0 已过；客户端 ctest 待 CI；L2 待执行 |

## 五、结论（随 D7C PR #87 更新）

- **持久化前置已解除**：D7D #90 已把偏好版本持久化（`memory_items / memory_versions / memory_version_receipts` + Repository）合入默认分支。
- **偏好 IPC 方法原为唯一硬依赖，已由 D7C PR #87 落地**（用户授权 D 轨契约变更）：`preference.list/create/update/rollback/history` 已实现（**条件注册**：production 默认不注册，`--register-preference-handlers` 显式激活），客户端接口与 QML 页面已编写；**UI 所需字段（category / confidence / evidence_event_ids 等）与 D7D 真源的映射、用户偏好集合枚举（已补 `list_preference_items`）仍待 D/E 确认**（不再表述为单一硬依赖已全部解除）。
- **剩余未完成**：工作项 6（跨会话行为输入联调）与工作项 7 的麒麟 L2 真实交互验证，需在银河麒麟 VM 执行后补充证据；C++/QML 编译由 CI `memory-client L0 ctest` 验证（本机无 Qt）。
- 已完成的实质产物：本核对结论（第 1、2 项，已按 `c1ee840` 复核）+ D7C PR #87 实现批次。

## 六、等待项与交接（随 D7C PR #87 更新）

1. ✅ 已就绪：`memory_items.current_version_id` 指针 + `memory_versions.previous_version_id` 版本链 / `rollback_of_version_id` / `memory_version_receipts`；`save / get_current / list / rollback_preference_version` Repository（含 `user_id` 过滤与 `is_current` 部分唯一约束）。
2. ✅ 已由本 PR 落地：IPC 路由表新增偏好增改 / 历史 / 回滚方法（`preference.*`，D 轨契约变更获用户授权）。
3. ⏳ 待 L2：跨会话行为输入联调 + 麒麟宿主真实交互验证（工作项 6/7）；QML/C++ 编译由 CI `memory-client L0 ctest` 验证。

**等待前置对应的跨轨依赖（更新）**：原等待 D 轨的偏好 IPC 方法已在本 PR 实现；剩余等待项为麒麟 L2 宿主验证（工作项 6/7）。
