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

- **D 轨版本持久化已合入默认分支（本次校对解除）**：`origin/main@c1ee840` 已含 D7D #90 的 `memory_items / memory_versions / memory_version_receipts` 表与 `save_preference_version / get_preference_version / get_current_preference_version / list_preference_versions / rollback_preference_version` Repository 接口；D7-C 的 ROLLBACK / UPDATE 用户可观察结果所需的持久化语义已具备（实现阶段仍需与 D7D 对列名/语义确认，因其以 `memory_items`（user_id+key+scope）为聚合键，而非 `Preference` domain 的 `preference_id`）。
- **IPC 偏好方法（原硬依赖，本 PR 已解决；契约冻结前条件注册）**：FRZ-IPC-007 原先仅 `echo / health / memory.retrieve` 活跃、无 `preference.*` 方法；D 轨契约变更已获用户授权，本 PR 新增 `preference.list / create / update / rollback / history` 五个方法（`memory-service/gateway/preference_handlers.py`）。因契约仍为 `CANDIDATE_SYNC`（ADR-016 待立项），**production 默认不注册（→ UNSUPPORTED_METHOD），仅 `--register-preference-handlers` 显式激活**（HIGH-1 返工；与 #93 候选路线一致）。
- **客户端能力（原不足，本 PR 已补齐）**：`MemoryClient` 新增 5 个偏好便捷方法；`MemoryViewModel` 新增偏好读/写/历史/回滚 `Q_INVOKABLE` 与 `preferenceItems / preferenceHistory / preferenceBusy / preferenceError / preferenceStage / lastPreferenceAction / lastPreferenceItem` 属性（保留 D5-C 既有管线方法）。
- **HIGH-2 双轨收敛（用户已决策，路线 A）**：保留本 PR（#87）`preference.*` 为 D7-C 实现路线；#93（`preference.version.*`）视为客户端候选 Demo；命名/页面归属由 D/E 在 ADR-016 统一；本 PR 不修改、不关闭 #93。
- **TD-008**：真实 MemoryContext 注入被阻断；TD-022 / TD-023：客户端超时 / 响应字段归一化待关闭。

### Review 结论与对齐（Ducknesses，PR #87，APPROVE）

独立 Reviewer `Ducknesses` 已对当前准备产物给出 **APPROVE**，明确结论为：作为 D7-C 施工准备产物合格、可合入；**实际 QML/C++/协议实现需在后续提交中按任务卡逐项落地并另行审查**。同时给出以下非阻断建议，本任务卡在本次校对中已吸纳或如实登记：

1. **基线重对齐**：任务卡原写 `origin/main@8ab369b`，但 main 已推进；建议实现开始时以最新 main 重新对齐基线，避免续后 diff 混入无关变更。→ 本任务卡「基线」行已更新为 `origin/main@c1ee840`。
2. **编号风格**：`08_d7c_task_card.md` 与 D7D 的 `08_d7d_task_card.md`（PR #90）共用 `08_` 前缀，可考虑按台账序号重排避免引用歧义。→ 因牵连跨文档引用，本批次不直接重命名，登记为后续命名整理项。
3. **契约节奏**：工作项 2「确定偏好 CRUD/历史/回滚 IPC 方法」建议与 D6-D 契约（ADR-012/013，PR #83）及 D7D 持久化（PR #90）保持同一 ADR 评审节奏，避免 C 轨实现等待期间契约再次变动。→ 见 `10_d7c_preference_ipc_contract_draft.md`，其已与 `origin/main` 上 D7D 落库 API 对齐（`CANDIDATE_SYNC`，不冻结）。

**E 轨补审关切（非阻断但实现阶段必须双层落实）**：验收 5.7 跨用户历史不可见、不可回滚、不可修改，不能在 UI 层仅做隐藏；必须在 Repository（`user_id` 强制过滤）与 UI 双层落实。实际实现时将在保留 D7D Repository 的 `user_id` 过滤语义前提下，再由 UI 层做显示隔离。

**身份隔离声明（MEDIUM-01，lovezy0730-create 第二轮）**：当前已验证 Repository 按 `user_id` 过滤 + handler payload 一致性校验（双层数据隔离），但**尚未验证「可信调用者身份 → `RequestContext.user_id`」绑定**（QML 中 user_id 仍可由用户输入、生产 Gateway 未注入可信身份）。因此**不宣称验收 5.7 已完整闭环**；「可信调用者身份绑定」登记为 **ADR-016 / production activation gate**（候选契约未激活前不扩大为 UDS 认证工程）。

## 五、工作清单（初始进度）

| 序号 | 工作项 | 类型 | 依赖 | 验证方式 | 状态 |
|------|--------|------|------|----------|------|
| 1 | 核对 D 轨版本持久化与 IPC 方法现状，确定 D7-C 可消费的契约 | 调研/对齐 | 无 | 读仓储、冻结契约文档 | 已完成 |
| 2 | 确定偏好 CRUD / 历史 / 回滚的 IPC 方法与 payload 契约 | 契约对齐 | 1 | 与 D 轨契约冻结对齐 | 已完成（本 PR 落地） |
| 3 | 客户端 `MemoryClient` / `MemoryViewModel` 增加偏好读/写/历史/回滚接口 | 实现 | 2 | L0 编译 + Mock 契约测试 | 已实现（L0 编译待 CI ctest） |
| 4 | `PreferenceEditorPage.qml` 手动添加/编辑 + 当前/历史版本 + 回滚入口 | 实现 | 3 | QML 启动 + 交互链路证据 | 已实现（麒麟宿主交互待 L2） |
| 5 | 临时/长期偏好展示区分 + 跨用户隔离渲染 | 实现 | 4 | 验收 5.6 / 5.7 | 已实现（UI + Repository 双层） |
| 6 | 跨会话行为输入联调 | 联调 | 5 | 宿主链路日志 | 部分完成（网关级真实 IPC 已验证；宿主 AI 助手跨会话待联调） |
| 7 | 本地回归（L0/L1 可用部分）+ 麒麟宿主 L2 验证 | 验证 | 3–6 | pytest / ctest / VM 后真实交互 | 已完成（VM L2 @ a4abe0e：pytest 1285 passed/49 skipped；ctest 4/4；真实 IPC 9/9，见 11 号文档） |

总进度：6/7（86%）。工作项 7（麒麟 L2 验证）已完成，见 `docs/day7/11_d7c_l2_verification_20260831.md`；工作项 6 宿主 AI 助手跨会话联调仍未执行。工作项 1–5 已在 D7C PR #87 中落地：D 轨偏好 IPC 方法（`preference.*`，用户授权）实现并注册；服务端 L0 handler 测试 10/10 通过、相关回归 201/201 通过；客户端 `MemoryClient / MemoryViewModel / PreferenceEditorPage.qml` 与 L0 Mock 测试已写入（C++ 编译由 CI `memory-client L0 ctest` 验证，本机无 Qt 无法编译）。工作项 7 的麒麟 L2（pytest/ctest/真实 IPC）已执行并归档证据；工作项 6 的宿主 AI 助手跨会话联调仍需另行联调。

> 前置核对结论（v3 更新）：D7D #90 已合入，默认分支已具 `memory_items / memory_versions / memory_version_receipts` 版本链与 `save/get_current/list/rollback_preference_version` Repository；偏好 IPC 方法已由 D7C PR #87 实现（**条件注册**：production 默认不注册 → UNSUPPORTED_METHOD，`--register-preference-handlers` 显式激活）。**剩余待确认（不再表述为单一硬依赖）**：UI 所需字段（category / confidence / evidence_event_ids 等）与 D7D 真源的映射、用户偏好集合枚举（已补 `list_preference_items`，字段映射待 D/E 确认）、ROLLBACK 语义（`PENDING_D_E_ALIGNMENT`）。详见 `docs/day7/09_d7c_prerequisite_audit.md` 与 `10_d7c_preference_ipc_contract_draft.md`。

### 工作项状态补充（同步实现进度）

| 工作项 | 状态 | 依赖 |
|--------|------|------|
| 1 现状核对 | 已完成 | 无 |
| 2 确定 IPC 方法/payload 契约 | 已完成（`10_d7c_preference_ipc_contract_draft.md` 落地为 `preference.*` 方法） | D7D 持久化已就绪 |
| 3 客户端接口 | 已实现（C++ 编译待 CI ctest） | preference.* 已由本 PR 实现 |
| 4 QML 页面 | 已实现（麒麟宿主交互待 L2） | 工作项 3 |
| 5 临时/长期 + 跨用户隔离 | 已实现（UI + Repository 双层） | 工作项 4 |
| 6 跨会话联调 | 待 L2 | 麒麟宿主链路 |
| 7 本地回归 + L2 | 服务端 L0 已过；客户端 ctest 待 CI；L2 待执行 | 工作项 3–6 |

## 六、风险与说明

- 本任务卡与工作清单为 D7-C **准备产物**，不意味着 D/C 轨道已完成或已通过验收；全部实现与验收证据状态为 `RUNTIME_UNVERIFIED`。
- 若实现中发现判据与真实宿主/存储能力不可调和，应由 C（或代做 D7-C 的 B）提出修订任务，不在本任务内降级判据。
- 本 PR 当前包含准备产物 + D7C 实现（D 轨偏好 IPC 方法、客户端 `MemoryClient / MemoryViewModel / PreferenceEditorPage.qml`、L0 测试与文档更新）；QML/C++ 编译由 CI `memory-client L0 ctest` 验证，麒麟宿主真实交互（工作项 6/7）需在 L2 VM 执行后补充证据，逐提交保持原子化。

## 七、变更记录

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| v1 | 2026-08-31 | 高翌哲（代 C 轨 D7-C） | 初稿：基于 15 天 75 项台账 D7-C 口径与 E 轨 `day7-e-ui-version-acceptance-v1.md` 建立任务卡与工作清单；标记跨轨依赖（D 轨版本持久化、IPC 方法、TD-008/022/023）；不包含实现代码 |
| v2 | 2026-08-31 | 高翌哲（代 C 轨 D7-C） | 按 PR #87 Reviewer（Ducknesses）非阻断建议与当前事实校对：基线重对齐至 `origin/main@c1ee840`（D7D #90 已合并、持久化阻塞解除）；将剩余唯一硬依赖修正为「偏好 IPC 方法未合入」；纳入编号风格、契约节奏与 5.7 双层落实意见；新增 `09_d7c_prerequisite_audit.md` 与 `10_d7c_preference_ipc_contract_draft.md` 两份配套产物 |
| v3 | 2026-08-31 | 高翌哲（代 C 轨 D7-C） | 实现批次：修正 MEDIUM-1 表名（`preference_version_operations` → `memory_version_receipts`，3 文件 5 处）与 LOW-1 描述（09 MemoryViewModel）；用户授权跨轨依赖，新增 D 轨偏好 IPC 方法 `preference.list/create/update/rollback/history`（`gateway/preference_handlers.py` + `repositories.list_preference_items` + app 注册 + L0 测试 10 项）；客户端 `MemoryClient`/`MemoryViewModel`/`PreferenceEditorPage.qml` 与 L0 Mock 测试；工作清单更新为 5/7（6–7 待麒麟 L2） |
| v4 | 2026-08-31 | 高翌哲（代 C 轨 D7-C） | 麒麟 L2 验证批次：D7C 克隆（`Kylin-V11-2603-D7C-aaed155-Test`）上执行 memory-service 全量 pytest（1281 passed/49 skipped）、memory-client L0 ctest（4/4，含 d7c_preference_editor）、网关级真实 IPC 冒烟（9/9 PASS）；新增 `11_d7c_l2_verification_20260831.md`；工作项 7 完成，工作项 6 宿主 AI 助手跨会话联调待做 |
| v5 | 2026-08-31 | 高翌哲（代 C 轨 D7-C） | REWORK 返工批次（Ducknesses）：HIGH-1 契约治理——`preference.*` 改为条件注册（默认不注册→UNSUPPORTED_METHOD，`--register-preference-handlers` 显式激活）；HIGH-2——显式声明与 #93（`preference.version.*` 候选）的关系与取舍；HIGH-01——10 号草案统一 ROLLBACK=追加新 current 版本并标 `PENDING_D_E_ALIGNMENT`；MEDIUM-1——`preference.list` 文档对齐 `list_preference_items`；MEDIUM-2——`is_temporary/should_persist` 显式 bool 校验 + 负测试；MEDIUM-03——PR body 同步实现批次状态 |
| v6 | 2026-08-31 | 高翌哲（代 C 轨 D7-C） | HIGH-2 收敛决策：用户确认路线 A——保留本 PR `preference.*` 为 D7-C 实现路线，#93 视为客户端候选 Demo，命名/页面归属由 D/E 在 ADR-016 统一；同步 08/09 表述（条件注册、字段映射/集合枚举/ROLLBACK 语义待 D/E 确认） |
| v7 | 2026-08-31 | 高翌哲（代 C 轨 D7-C） | 第二轮 REWORK（lovezy0730-create，0f05462）：HIGH-01——`_resolve_memory_status` 增加 D3 §7.9 冲突校验（is_temporary/should_persist 与显式 memory_status 冲突拒绝）；客户端 `updatePreference`/QML 显式携带生命周期标志；补 3 个测试；MEDIUM-01——身份隔离声明（可信调用者身份 → RequestContext.user_id 登记为 ADR-016/production gate，不宣称 5.7 完整闭环）；MEDIUM-02——L2 证据在最终 HEAD 重跑并绑定真实命令/SHA |
| v8 | 2026-08-31 | 高翌哲（代 C 轨 D7-C） | MEDIUM-02 落地：L2 证据在最终 HEAD `a4abe0e` 重跑（VM 经字节传输同步；全量 1285/49、定向 14、真实 IPC 9/9 含 `--register-preference-handlers`）；11 号文档/证据摘要绑定 tested_commit= a4abe0e 与真实命令/日志 SHA |
