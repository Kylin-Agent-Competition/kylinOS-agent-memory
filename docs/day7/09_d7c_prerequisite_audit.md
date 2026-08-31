# D7-C 前置条件核对结论（工作清单第 1、2 项）

> 本文件为 D7-C 前置条件核对结论（对应任务卡 `08_d7c_task_card.md` 第五节工作清单第 1、2 项）。
> 结论原基于 `origin/main` `8ab369b`（2026-08-31 同步）；本次校对（2026-08-31）已重新基于 `origin/main@c1ee840`（含 D7D #90）核对，并如实标注结论更新。所有结论均取自实际代码与冻结契约，非推测。

## 一、核对结论：D 轨版本持久化已实现（本次校对更新，原为「未实现 → 关键阻塞」）

默认分支 `origin/main@c1ee840` 上，**D 轨版本持久化已由 D7D #90 实现**，具体证据如下。

| 核对项 | 结论 | 证据 |
|--------|------|------|
| `memory_items` 聚合表（user_id+key+scope 唯一、含 current 指针） | 已实现 | `migrations/versions/20260831_preference_versions.py`：`memory_items`（`id / user_id / preference_key / preference_scope / current_version_id`，`uq_memory_items_user_key_scope` 唯一索引 + `ck_memory_items_preference_scope` 五值 CHECK） |
| `previous_version_id` / `rollback_of_version_id` 版本链 | 已实现 | `20260831_preference_versions.py`：`memory_versions`（`version / previous_version_id(FK) / rollback_of_version_id(FK)`，`uq_memory_versions_item_version` 唯一 + `uq_memory_versions_current` 部分唯一 `is_current=1`） |
| 独立偏好版本历史表与回滚审计表 | 已实现 | `memory_items` + `memory_versions` + `preference_version_operations`（operation_kind / memory_version_id FK）；`db/repositories.py::save_preference_version / list_preference_versions / rollback_preference_version` |
| `current_version_id` 指针语义 | 已实现 | `memory_items.current_version_id`；Repository `get_current_preference_version` 读取、`rollback_preference_version` 切换（追加新 current 版本，不覆盖旧历史） |
| 偏好版本增改/回滚事务持久化 | 已实现 | `db/repositories.py` 的 `save/get_current/list/rollback_preference_version`（均强制 `user_id` 过滤）；迁移 `20260831_preference_versions.py` 可升级/回退；`migrations/alembic.ini` 同步 |

## 二、IPC 方法现状（D 轨契约边界）

| 核对项 | 结论 | 证据 |
|--------|------|------|
| 活跃方法仅 `echo / health / memory.retrieve` | 是 | `memory-service/gateway/handlers.py::register_default_handlers` 仅注册 `echo / health / memory.retrieve`；`memory.store` 注册 handler 但返回 `UNSUPPORTED_METHOD` |
| 是否有偏好增改/历史/回滚方法（现唯一硬依赖） | **否（当前唯一硬依赖）** | `memory-service/gateway/handlers.py::register_default_handlers` 无 `preference.*`/`rollback`/`history` handler；`protocol_adapter.h` FRZ-IPC-007 路由表仅 `echo / health / memory.retrieve / memory.store(未实现) / turn.finalized`，无 `preference.*` |
| `memory.retrieve` 是否已接主链 | 否 | handlers.py `memory_retrieve_handler` 返回“真实空上下文（检索主链后续接入，禁止假数据）” |

## 三、客户端（C 轨）现状

| 核对项 | 结论 | 证据 |
|--------|------|------|
| `MemoryViewModel` 能力 | 仅 `connect / disconnect / sendHealth / sendMemoryQuery` | `memory-client/src/view_models/memory_view_model.h` |
| 偏好 CRUD / 历史 / 回滚接口 | 无 | `memory_view_model.h` 无相关 `Q_INVOKABLE` |

## 四、D7-C 工作项前置达标性划分

| 工作项 | 前置条件 | 前置是否达标 | 状态 |
|--------|----------|--------------|------|
| 1 核对 D 轨版本持久化与 IPC 方法现状 | 无 | 达标 | 本文件已完成 |
| 2 确定偏好 CRUD / 历史 / 回滚的 IPC 与 payload 契约 | D 轨版本持久化（已达标）＋ IPC 方法 | **未达标（IPC 仍缺）** | 待 D 轨 |
| 3 客户端新增偏好读/写/历史/回滚接口 | 第 2 项契约 | **未达标（IPC 仍缺）** | 待 D 轨 |
| 4 `PreferenceEditorPage.qml` 增改/当前/历史/回滚 | 第 3 项接口 | **未达标（IPC 仍缺）** | 待 D 轨 |
| 5 临时/长期展示区分 + 跨用户隔离渲染 | 第 4 项 | **未达标（IPC 仍缺）** | 待 D 轨 |
| 6 跨会话行为输入联调 | 第 5 项 + 宿主链路 | **未达标（IPC 仍缺）** | 待 D 轨 |
| 7 本地回归 + 麒麟宿主 L2 验证 | 第 3–6 项 | **未达标（IPC 仍缺 + 宿主链路）** | 待 D 轨 |

## 五、结论

- **持久化前置已解除**：D7D #90 已把偏好版本持久化（`memory_items / memory_versions / preference_version_operations` + Repository）合入默认分支，D7-C 的 UPDATE / ROLLBACK 用户可观察结果所需的底层语义已具备。
- **唯一剩余硬依赖为偏好 IPC 方法**：默认分支网关（`handlers.py`）与客户端路由表（`protocol_adapter.h`）均无 `preference.*` 方法；D7-C 第 2–7 项因此仍处于“待 D 轨”状态，需 D 轨扩展 IPC 路由表或明确复用路径。
- 在 IPC 方法合入前，本批次不编写 QML/C++/IPC 实现代码——否则会违反 E 轨验收规范“不得以静态代码存在冒充真实交互验收”。
- 已完成的实质产物：本核对结论（第 1、2 项的“现状调研”部分，已按 `c1ee840` 复核）。第 2 项的“契约确定”需 D 轨达成后再定。

## 六、等待项与交接

待 **D 轨**在默认分支合入以下前置后，D7-C 可立即恢复推进第 2 项（持久化已就绪，仅需 IPC 方法）：

1. ✅ 已就绪：`memory_items.current_version_id` 指针 + `memory_versions.previous_version_id` 版本链 / `rollback_of_version_id` / `preference_version_operations`；`save / get_current / list / rollback_preference_version` Repository（含 `user_id` 过滤与 `is_current` 部分唯一约束）。
2. ⏳ 待 D 轨：IPC 路由表新增偏好增改 / 历史 / 回滚方法（或复用既有方法并明确 payload 契约）。
3. ⏳ 待 D 轨：若选定「扩展方法」则需相应 FRZ-IPC-007 契约变更（对齐 ADR-012/013 先例）、并发与事务语义的 handler 接线；迁移已就绪，无 Outbox 硬依赖（偏好版本通过 `idempotency_key + request_fingerprint` 幂等）。

**等待前置对应的跨轨依赖**：D 轨（周子腾）为 D7-C 的偏好 IPC 契约与 `preference.*` 路由注册负责人；D7D（持久化）已合并，C 轨需在 D 轨确认 IPC 方法后据此实现 UI。
