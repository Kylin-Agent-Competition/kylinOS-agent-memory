# D7C 任务卡：偏好编辑 UI、版本历史与回滚（C 轨）

| 字段 | 内容 |
|------|------|
| 任务编号 | D7-C |
| 任务标题 | 完成偏好手动配置与版本 QML 组件；联调跨会话行为输入；展示当前版本、历史版本和回滚入口 |
| 责任轨道 | C（刘承恩）；当前暂由 B（高翌哲）代替实施，C 轨 Review 由 D/E 完成 |
| Reviewer | D 主审；用户交互与安全由 E 补审 |
| 基线 | 初始 `origin/main@8ab369b`；截至本次校对（2026-08-31）`origin/main` 已含 D7D 偏好版本持久化（`c1ee840`，`feat: D7D 偏好版本持久化 (#90)`），实现阶段建议以该最新基线重新对齐 |
| 分支 | `feat/C-d7-preference-version-ui`（新增，未包含 `codex`，按命名规则以 `feat/` 前缀） |
| 工作类型 | 新增功能（feature） |
| 完成定义（台账 D7-C） | 用户可添加、修改、查看历史并发起回滚 |

## 一、权威目标与验收口径

15 天 75 项施工台账为 D7-C 指定三项交付：

1. 完成手动配置和偏好版本 QML 组件；
2. 联调跨会话行为输入；
3. 展示当前版本、历史版本和回滚入口。

验收要求为：**用户可添加、修改、查看历史并发起回滚**。

本任务同时以前置 E 轨验收规范作为用户可观察行为的业务判据来源：

- `docs/day7/day7-e-ui-version-acceptance-v1.md`（状态 `PENDING_INTEGRATION`）
  - 5.1 CREATE（首版 v1、`current_version` 指向 v1、无历史入口）
  - 5.2 COEXIST（不同 scope 共存，局部 scope 当前值优先但 global 历史不得删除/隐藏）
  - 5.3 UPDATE（版本递增、旧版 `superseded` 保留可回溯）
  - 5.4 NO_OP（重复提交不产生版本膨胀）
  - 5.5 ROLLBACK（`current_version` 切换、中间版本保留）
  - 5.6 临时偏好不得误展示为稳定 global 长期偏好
  - 5.7 跨用户历史不可见、不可回滚、不可修改

## 二、修改范围（计划，当前未实现）

本任务卡为**准备产物**，不包含任何实现代码。计划修改范围如下：

- `memory-client/qml/pages/PreferenceEditorPage.qml`：由 D4 占位骨架升级为可操作偏好编辑器
  - 手动添加/编辑偏好（类别 / scope 五值 / value / 临时-长期标识）
  - 当前版本展示 + 历史版本列表（按版本链渲染，保留 `superseded`）
  - 回滚交互入口，触发 ROLLBACK
  - 临时/长期偏好展示区分；跨用户数据只渲染当前用户
- `memory-client/src/view_models/` 与 `memory-client/src/memory_client.*`：新增偏好读/写/历史/回滚能力（`Q_INVOKABLE`），供 QML 调用
- `memory-client/src/protocol_adapter.*`：如协议方法需要扩展，需与 D 轨冻结路由表对齐并走契约变更
- `memory-client/tests/`：协议/ViewModel 层面 L0 用例（Mock Gateway 契约）
- 跨会话行为输入联调（路径待与 C/D 轨既有链路确认）

## 三、明确不修改的范围

- 不实现 A、B、D、E 轨代码、契约、业务策略或持久化。
- 不新增 SQLite `current_version` 指针、`previous_version_id` 版本链、Repository、Migration 或 Outbox。
- 不修改冻结的 Provider / IPC Schema（FRZ-IPC-001~007）既有字段；新增方法如涉及须先走 D 轨契约变更。
- 不实现 D8 知识关系过滤、D9 业务重排 / Top-K / token 预算 / 检索指标。
- 不把本地纯函数测试或静态代码存在冒充麒麟宿主真实交互验收。

## 四、跨轨依赖与阻塞（如实标注）

以下均为实现前需要先对齐的依赖，本任务卡先记录不掩盖：

- **D 轨版本持久化已合入默认分支（本次校对解除）**：`origin/main@c1ee840` 已含 D7D #90 的 `memory_items / memory_versions / preference_version_operations` 表与 `save_preference_version / get_preference_version / get_current_preference_version / list_preference_versions / rollback_preference_version` Repository 接口；D7-C 的 ROLLBACK / UPDATE 用户可观察结果所需的持久化语义已具备（实现阶段仍需与 D7D 对列名/语义确认，因其以 `memory_items`（user_id+key+scope）为聚合键，而非 `Preference` domain 的 `preference_id`）。
- **IPC 路由表仍无偏好方法（当前硬依赖 / 阻塞）**：FRZ-IPC-007 仅 `echo / health / memory.retrieve` 三项活跃，另含 `memory.store`（未实现）/ `turn.finalized`（候选，BLOCKED_BY_HOST_MAPPING）；无 `preference.list / create / update / rollback / history` 方法。需先确认是扩展方法（走 D 轨契约变更）还是复用既有路径。
- **现有客户端能力不足**：`MemoryViewModel` 目前只有 `connect / disconnect / sendHealth / sendMemoryQuery`，无偏好读写能力。
- **TD-008**：真实 MemoryContext 注入被阻断；TD-022 / TD-023：客户端超时 / 响应字段归一化待关闭。

### Review 结论与对齐（Ducknesses，PR #87，APPROVE）

独立 Reviewer `Ducknesses` 已对当前准备产物给出 **APPROVE**，明确结论为：作为 D7-C 施工准备产物合格、可合入；**实际 QML/C++/协议实现需在后续提交中按任务卡逐项落地并另行审查**。同时给出以下非阻断建议，本任务卡在本次校对中已吸纳或如实登记：

1. **基线重对齐**：任务卡原写 `origin/main@8ab369b`，但 main 已推进；建议实现开始时以最新 main 重新对齐基线，避免续后 diff 混入无关变更。→ 本任务卡「基线」行已更新为 `origin/main@c1ee840`。
2. **编号风格**：`08_d7c_task_card.md` 与 D7D 的 `08_d7d_task_card.md`（PR #90）共用 `08_` 前缀，可考虑按台账序号重排避免引用歧义。→ 因牵连跨文档引用，本批次不直接重命名，登记为后续命名整理项。
3. **契约节奏**：工作项 2「确定偏好 CRUD/历史/回滚 IPC 方法」建议与 D6-D 契约（ADR-012/013，PR #83）及 D7D 持久化（PR #90）保持同一 ADR 评审节奏，避免 C 轨实现等待期间契约再次变动。→ 见 `10_d7c_preference_ipc_contract_draft.md`，其已与 `origin/main` 上 D7D 落库 API 对齐（`CANDIDATE_SYNC`，不冻结）。

**E 轨补审关切（非阻断但实现阶段必须双层落实）**：验收 5.7 跨用户历史不可见、不可回滚、不可修改，不能在 UI 层仅做隐藏；必须在 Repository（`user_id` 强制过滤）与 UI 双层落实。实际实现时将在保留 D7D Repository 的 `user_id` 过滤语义前提下，再由 UI 层做显示隔离。

## 五、工作清单（初始进度）

| 序号 | 工作项 | 类型 | 依赖 | 验证方式 | 状态 |
|------|--------|------|------|----------|------|
| 1 | 核对 D 轨版本持久化与 IPC 方法现状，确定 D7-C 可消费的契约 | 调研/对齐 | 无 | 读仓储、冻结契约文档 | 待开始 |
| 2 | 确定偏好 CRUD / 历史 / 回滚的 IPC 方法与 payload 契约 | 契约对齐 | 1 | 与 D 轨契约冻结对齐 | 待开始 |
| 3 | 客户端 `MemoryClient` / `MemoryViewModel` 增加偏好读/写/历史/回滚接口 | 实现 | 2 | L0 编译 + Mock 契约测试 | 待开始 |
| 4 | `PreferenceEditorPage.qml` 手动添加/编辑 + 当前/历史版本 + 回滚入口 | 实现 | 3 | QML 启动 + 交互链路证据 | 待开始 |
| 5 | 临时/长期偏好展示区分 + 跨用户隔离渲染 | 实现 | 4 | 验收 5.6 / 5.7 | 待开始 |
| 6 | 跨会话行为输入联调 | 联调 | 5 | 宿主链路日志 | 待开始 |
| 7 | 本地回归（L0/L1 可用部分）+ 麒麟宿主 L2 验证 | 验证 | 3–6 | pytest / ctest / VM 后真实交互 | 待开始 |

总进度：1/7（14%）。工作项 1 已完成现状核对（见 `09_d7c_prerequisite_audit.md`）。本次校对确认 **D 轨版本持久化已合入 `origin/main@c1ee840`**（D7D #90），因此原先「持久化未达标」的阻塞已解除；工作项 2–7 当前唯一的硬依赖为 **偏好 IPC 方法（`preference.*`）尚未合入默认分支**，需先走 D 轨契约变更或明确复用路径后，方可进入 item 3–7 的实现/联调/验证。

> 前置核对结论（本次已更新）：D7D #90 已合入，默认分支已具 `memory_items / memory_versions` 版本链与 `save/get_current/list/rollback_preference_version` Repository；但 IPC 路由表仍仅 `echo / health / memory.retrieve` 活跃，无偏好增改/历史/回滚方法。详见 `docs/day7/09_d7c_prerequisite_audit.md`。

### 工作项状态补充（同步自前置核对）

| 工作项 | 状态 | 依赖 |
|--------|------|------|
| 1 现状核对 | 已完成（本提交） | 无 |
| 2 确定 IPC 方法/payload 契约 | **待 D 轨**（契约未冻结） | D 轨偏好 IPC 方法扩展或复用路径确认 |
| 3–7 实现/联调/验证 | **待 D 轨**（唯一硬前置：偏好 IPC 方法） | D 轨偏好 IPC 方法合入；D7D 持久化已就绪 |

## 六、风险与说明

- 本任务卡与工作清单为 D7-C **准备产物**，不意味着 D/C 轨道已完成或已通过验收；全部实现与验收证据状态为 `RUNTIME_UNVERIFIED`。
- 若实现中发现判据与真实宿主/存储能力不可调和，应由 C（或代做 D7-C 的 B）提出修订任务，不在本任务内降级判据。
- 本分支只包含准备产物（本任务卡）；实际 QML/C++/协议实现代码将在后续提交中追加，并逐提交保持原子化。

## 七、变更记录

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| v1 | 2026-08-31 | 高翌哲（代 C 轨 D7-C） | 初稿：基于 15 天 75 项台账 D7-C 口径与 E 轨 `day7-e-ui-version-acceptance-v1.md` 建立任务卡与工作清单；标记跨轨依赖（D 轨版本持久化、IPC 方法、TD-008/022/023）；不包含实现代码 |
| v2 | 2026-08-31 | 高翌哲（代 C 轨 D7-C） | 按 PR #87 Reviewer（Ducknesses）非阻断建议与当前事实校对：基线重对齐至 `origin/main@c1ee840`（D7D #90 已合并、持久化阻塞解除）；将剩余唯一硬依赖修正为「偏好 IPC 方法未合入」；纳入编号风格、契约节奏与 5.7 双层落实意见；新增 `09_d7c_prerequisite_audit.md` 与 `10_d7c_preference_ipc_contract_draft.md` 两份配套产物 |
