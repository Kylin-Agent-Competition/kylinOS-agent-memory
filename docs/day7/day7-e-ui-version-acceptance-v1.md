# Day7 E 轨偏好 UI 与版本行为验收规范 v1 候选

- **版本**：v1
- **状态**：`PENDING_INTEGRATION`
- **阶段定位**：Day7 / E 轨验收规范候选（对 C 轨偏好 UI 与 D 轨版本持久化的**业务验收标准**）
- **作者轨道**：E（记忆业务、安全、数据集与业务指标）
- **Reviewer 轨道**：D（周子腾）主审；C 轨 UI 影响时 C 补审
- **冻结为团队基线条件**：仅 E 轨道单方面提出的**业务验收标准候选**。本文件不冻结任何 QML 组件名、SQLite DDL、IPC 线格式或实现细节，不替 C/D 虚构实现或「已实现」契约。实际 UI 与持久化验收须由 C 轨与 D 轨分别实现并提供真实证据后，方可判定通过。
- **本文件是（地位）**：E 轨提出的、应呈现给用户的、关于偏好创建/共存/更新/回滚与版本历史的**用户可观察行为验收标准**；用于指导并核验 C 轨 QML 偏好 UI 与 D 轨版本持久化层各自应达到的业务结果。
- **本文件不是（地位）**：QML 组件设计、C++ MemoryClient 接口定义、SQLite Schema、Migration、IPC 协议、`current_version` 指针实现细节，或任何轨道的生产代码。

**重要声明**：本文件为 E 轨道单方面提出的验收规范候选，**不代表 C 轨 UI 或 D 轨版本持久化已实现或已通过验收**。本任务 `runtime_required=false`，不包含任何银河麒麟 Runtime Test；文件内全部 C/D 验收案例证据状态统一为 `RUNTIME_UNVERIFIED`。

---

## 一、依据来源与局限声明

### 1.1 依据来源（仓库内已核验文件）

| 编号 | 来源 | 路径/描述 | 仓库状态 |
|------|------|-----------|----------|
| S-01 | D3 记忆业务契约 v1 | `docs/architecture/D3_MEMORY_BUSINESS_CONTRACT_V1.md`（§3.2/§5.2/§7.1/§7.2/§7.4/§7.5/§7.9，状态 `CANDIDATE_FOR_FREEZE`；版本/回溯/临时偏好/用户隔离业务语义冻结，`preference_scope` 五值 §5.2/§5.6 枚举 2.9 `FROZEN_BUSINESS_SEMANTIC`） | SOURCE_VERIFIED（在库） |
| S-02 | Day7E 版本变更规划策略 | `memory-service/service/preference_version_policy.py`（CREATE/COEXIST/UPDATE/NO_OP/ROLLBACK 五种业务动作 + REJECTED 防御态；reason_code 集合见第 65–98 行） | SOURCE_VERIFIED（已实施，E 轨 service 内部） |
| S-03 | Day7E 长期化业务决策策略 | `memory-service/service/preference_business_policy.py`（should_store / requires_confirmation / reason_code；临时边界 reason_code `temporary_not_persistent` / `should_persist_false`） | SOURCE_VERIFIED（已实施，E 轨 service 内部） |
| S-04 | Preference Domain 模型 | `memory-service/domain/preference.py`（`_version_chain` / `_temporary_boundary` / `_time_order` 校验器；`version`/`previous_version_id`/`memory_status` 字段） | SOURCE_VERIFIED（已实施，E 轨 domain） |
| S-05 | D4 数据库初始需求 | `deliverables/D4_DB_INITIAL_REQUIREMENTS_20260817.md`（D4-D 版本持久化实施署名「待填写」；`memory_entries` 含 `version` 乐观锁字段但无 `current_version` 指针） | SOURCE_VERIFIED（仅引用需求边界，不引用未实现实现） |
| S-06 | C 轨 memory-client 现状 | `memory-client/README.md`（「仅建立目录和职责边界，尚无生产实现」；无 .qml 生产文件） | SOURCE_VERIFIED（C 轨未实现） |
| S-07 | D7E 回归与单元测试 | `memory-service/tests/test_preference_business_policy_d7e.py` / `test_preference_version_policy_d7e.py` / `test_preference_business_flow_d7e.py` | SOURCE_VERIFIED（E 轨策略/领域测试，非 UI/DB 验收） |

### 1.2 局限声明

- **15 天 75 项施工台账未导入 Git 仓库**（`docs/baseline/README.md` 编号 06「待人工导入」），Day7 E/C/D 任务卡实体不在仓库内。本文件基于仓库内已实施 D7E-01/02/03 代码、D3 契约与 D4 需求文档推断 Day7 E 轨业务语义边界，**不依赖施工台账实体**。若团队后续导入台账后发现与本规范存在差异，以施工台账为准并走文档修订任务。
- **C 轨 QML 偏好 UI 尚未实现**（S-06）：本规范**不替 C 轨冻结** QML 组件、交互控件或实现细节；QML 历史列表、修改、回滚交互由 C 轨实现和证明。
- **D 轨版本持久化尚未实现**（S-05）：本规范**不替 D 轨冻结** SQLite DDL、Repository、Migration 或 `current_version` 指针；实际 `current_version` 切换、事务与并发正确性由 D 轨实现和证明。
- 本文件只定义**用户可观察的验收标准**，不得作为任何轨道「已通过验收」或「功能已完成」的证据。文件内所有 C/D 验收案例证据状态为 `RUNTIME_UNVERIFIED`。
- 本任务不采集任何 UI 截图或数据库 schema 截图；**不得使用截图或静态代码存在冒充真实交互验收**。

---

## 二、验收范围与边界

### 2.1 验收范围

本规范验收的是两类**用户可观察业务结果**：

1. **C 轨偏好 UI 的用户可观察行为**：偏好创建后如何呈现、多 scope 如何共存展示、值更新后当前值与历史的呈现、回滚交互、临时偏好与长期偏好的展示区分、跨用户数据不可见不可操作。
2. **D 轨版本持久化的用户可观察业务结果**：CREATE/UPDATE/NO_OP/ROLLBACK 在持久化链上应呈现的版本结果（首版 version=1、版本递增、历史保留、回滚不删除中间版本、`current_version` 切换的最终用户可见值）。

### 2.2 明确不验收范围（不由本规范核验）

- **E 轨策略逻辑本身**（D7E-01/02/03）的单元正确性：已有独立单元测试与跨链路回归测试覆盖（S-07），本文件不复测、不以此为文档内容验收依据。
- **IPC 协议**（线格式、长度前缀、错误码）：属 D 轨协议范畴，非本任务范围。
- **Embedding / 检索（B/A 轨）**：`preference_scope` 的语义检索与 RRF 排序不在本规范验收范围。
- **SQLite DDL / Migration / `current_version` 指针实现**：属 D 轨实现层，本文件只定义其应呈现的用户可观察结果，不定义实现方式。
- **QML 组件 / C++ MemoryClient 代码**：属 C 轨实现层，本文件只定义应呈现的用户可观察行为。

### 2.3 边界声明

- 本文件**只定义验收标准**，不得宣称 D/C 已完成。
- 所有验收案例的**证据状态**为 `RUNTIME_UNVERIFIED`；真实执行须由 C/D 轨在银河麒麟 VM 中完成并保留真实命令、退出码与日志证据，方可判定 `PASS`。
- 本规范中「应呈现」「不得」「必须」等描述均为**验收判据**，非当前实现事实。

---

## 三、文档状态与作者约定

- **文档状态**：`PENDING_INTEGRATION`（等价未验收状态）。**不得**标记 `PASS` / `FROZEN` / `HOST_VERIFIED`/「已完成」。
- 本文件是 E 轨单方面提出的验收规范候选。冻结为团队基线须经非作者 D Reviewer 批准且 PR 合并后方可生效；此前的状态不代表 C 轨 UI 或 D 轨版本持久化已实现或已通过验收。
- 如后续 C/D 轨实现后发现本规范某项判据与真实宿主/存储能力不可调和，应由对应轨道提出修订，走独立文档任务，而不是在本任务内降级判据。

---

## 四、业务语义来源映射

下表将每个验收案例映射到 E 轨已冻结的业务语义来源，作为本规范判据的语义根基。

| 验收案例 | E 轨已冻结语义来源（D3） | 版本业务动作定义来源（S-02） |
|----------|---------------------------|------------------------------|
| 4.1 CREATE | D3 §7.2（首版 version=1、previous_version_id=None） | `REASON_CREATE_FIRST_VERSION` / `create_first_version` |
| 4.2 COEXIST | D3 §3.5 作用域共存规则 + §5.2 `preference_scope` 五值（§5.6 枚举 2.9） | `REASON_COEXIST_DIFFERENT_SCOPE` / `coexist_different_scope` |
| 4.3 UPDATE | D3 §7.2（version 递增、previous_version_id 指向上一版、不原地覆盖） | `REASON_UPDATE_VALUE_CHANGED` / `update_value_changed` |
| 4.4 NO_OP | 防版本膨胀业务规则（S-02 模块头注释 + D3 §7.2） | `REASON_NO_OP_SAME_VALUE` / `no_op_same_value` |
| 4.5 ROLLBACK | D3 §7.2（回溯版本链、不删除中间版本） | `REASON_ROLLBACK_TO_HISTORY_VERSION` / `rollback_to_history_version` |
| 4.6 临时偏好边界 | D3 §7.9（is_temporary=true / should_persist=false 不得晋升正式长期） | S-03 `temporary_not_persistent` / `should_persist_false` + S-04 `_temporary_boundary` |
| 4.7 跨用户隔离 | D3 §7.1（user_id 隔离硬约束、跨用户拒绝、隔离破坏标记 critical） | S-02 `REASON_REJECTED_CROSS_USER` / `rejected_cross_user` |

### scope 共存约束（本规范遵循）

- `preference_scope` 五值：`global`/`topic`/`tool`/`session`/`time_window`（D3 §5.2/§5.6 枚举 2.9，`FROZEN_BUSINESS_SEMANTIC`）。
- 不同 scope 可共存：同 `preference_key` + 不同 scope → 各自创建独立首版（COEXIST），旧 scope active 偏好**不被 supersede**。
- **局部 scope 覆盖不得删除 global 历史**：UI 展示当前生效值时，global 历史版本必须保留可回溯。
- scope 优先级在 UI 展示层面的业务语义：局部 scope 当前值优先展示，但**不得删除或隐藏 global 历史**。

---

## 五、业务验收案例（用户可观察行为）

> 每个案例统一给出：场景 / 用户可观察结果 / 通过判据 / 失败判据 / 责任轨道 / 证据状态。证据状态全部为 `RUNTIME_UNVERIFIED`。

### 5.1 CREATE（创建首版）

- **场景**：用户首次表达某 `global` 偏好（同 user_id + 同 preference_key + 同 scope 无 active 当前记录）。
- **用户可观察结果**：UI 出现该偏好，标注作用域 `global`，版本号 v1；无历史版本可追溯；`current_version` 指向 v1。
- **通过判据**：
  - UI 呈现该偏好，版本 v1，且不显示「历史版本」入口（无历史可回溯）；
  - C 轨：UI 正确展示首版偏好；
  - D 轨：持久化 v1（version=1、previous_version_id=None）；`current_version` 指向 v1。
- **失败判据**：UI 不显示该偏好；或首版不是 v1；或 v1 携带 previous_version_id；或 `current_version` 未指向 v1。
- **责任轨道**：C（UI 展示首版）；D（持久化首版 + `current_version` 指向 v1）。
- **证据状态**：`RUNTIME_UNVERIFIED`。

### 5.2 COEXIST（scope 共存与优先级展示）

- **场景**：同 `preference_key` 存在不同 scope，如 `global` 与 `session` 各存一条；或新增一个不同 scope 的偏好。
- **用户可观察结果**：UI 同时展示两条（或多条）不同 scope 的偏好；当前会话/展示层面局部 scope（如 `session`）当前值优先展示，但 `global` 偏好及其历史**不可被删除或隐藏**。
- **通过判据**：
  - UI 同时呈现不同 scope 的偏好，且各自版本独立（各为独立链路 v1）；
  - 局部 scope 当前值优先展示，但 global 历史仍可查看/回溯，不被 supersede 删除；
  - D 轨：新 scope 创建独立首版，旧 scope active 偏好**不被 supersede**。
- **失败判据**：新增 scope 后旧 scope active 被删除/隐藏；或不同 scope 被合并为单条覆盖；或 `global` 历史不可回溯。
- **责任轨道**：C（UI 同时展示多 scope、且保留 global 历史）；D（COEXIST 独立首版持久化，不 supersede 旧 scope）。
- **证据状态**：`RUNTIME_UNVERIFIED`。

### 5.3 UPDATE（更新及旧版本保留）

- **场景**：同 user_id + 同 preference_key + 同 scope 的偏好值变化（如 `global` 值从 A 变为 B）。
- **用户可观察结果**：UI 当前值更新为 v2；历史 v1 保留可查看；v1 `memory_status=superseded` 不被删除，可回溯。
- **通过判据**：
  - 当前生效值为 v2（version 递增）；
  - 不原地覆盖：v1 历史版本保留，标记 superseded 不删除，版本链可回溯；
  - D 轨：version = current.version + 1、previous_version_id 指向 v1；
  - C 轨：历史列表展示 v1，当前值对话上下文展示 v2。
- **失败判据**：值原地覆盖导致 v1 丢失；或 version 不递增；或 previous_version_id 不指向上一版；或历史列表不可见 v1。
- **责任轨道**：D（版本链持久化：递增 + 历史保留）；C（历史列表展示 + 当前值对话展示）。
- **证据状态**：`RUNTIME_UNVERIFIED`。

### 5.4 NO_OP（防重复版本）

- **场景**：同 user_id + 同 preference_key + 同 scope + 相同 value 重复提交。
- **用户可观察结果**：UI 不新增版本、不产生版本膨胀；`current_version` 保持不变，当前值仍为该 value。
- **通过判据**：
  - 不产生新版本、`current_version` 不变、值不变；
  - D 轨：不执行版本写入、不产生无意义版本记录；
  - C 轨：UI 不显示新版本条目、不触发无变化的更新动画/提示。
- **失败判据**：重复提交产生新版本、版本膨胀；或 `current_version` 被无意义推进；或 UI 出现重复版本条目。
- **责任轨道**：D（不写版本、不推进 current_version）；C（UI 不展示重复版本）。
- **证据状态**：`RUNTIME_UNVERIFIED`。

### 5.5 ROLLBACK（回滚及历史保留）

- **场景**：用户回滚到某历史版本（如当前 v3，用户回滚到 v1）。
- **用户可观察结果**：当前生效值切换为目标历史版本（v1）内容；中间版本（v2、v3）历史**不被删除**，版本链完整；回滚后当前值呈现该目标版本内容。
- **通过判据**：
  - `current_version` 切换到目标历史版本（唯一 active 为 v1），当前值呈现 v1 内容；
  - 中间版本 v2、v3 历史保留、不回退/不删除未来版本记录；
  - D 轨：`current_version` 切换 + 事务提交原子性 + 回滚不删除中间版本；
  - C 轨：回滚交互触发 + 历史列表完整呈现 v1/v2/v3。
- **失败判据**：回滚删除中间版本；或不保留版本链；或`current_version` 切换后未来版本被物理删除；或回滚后 UI 仍显示旧当前值。
- **责任轨道**：D（`current_version` 切换 + 事务 + 历史保留）；C（回滚交互 + 历史展示）。
- **证据状态**：`RUNTIME_UNVERIFIED`。

### 5.6 临时偏好不得稳定长期化的 UI 验收

- **场景**：`is_temporary=true` 或 `should_persist=false` 的偏好（如会话级临时偏好）。
- **用户可观察结果**：UI **不得**将其展示为稳定 `global` 长期偏好；须明确标注临时/会话级/到期；到期后呈现 `expired`，不进入长期偏好列表，不参与全局长期偏好检索链路展示。
- **通过判据**：
  - UI 将临时偏好明确标注为临时/会话级/到期，不误展示为稳定 global 长期偏好；
  - `memory_status` 为 `candidate` 或 `expired`，不晋升 `active`（D3 §7.9）；
  - 到期后 UI 呈现 `expired`，不进入长期偏好列表。
- **失败判据**：临时偏好被误展示为 global active 长期偏好；或到期后仍被当作长期偏好展示/注入检索链路。
- **责任轨道**：C（UI 展示区分临时/长期，不误展示）；E（业务策略已冻结 `temporary_not_persistent` / `should_persist_false`）。
- **证据状态**：`RUNTIME_UNVERIFIED`。

### 5.7 跨用户历史不可见不可操作

- **场景**：用户 A 查看/回滚/修改偏好历史；存在用户 B 的偏好历史。
- **用户可观察结果**：用户 A 的 UI 只列出 A 自己的偏好与历史；B 的偏好**不可见、不可回滚、不可修改**。
- **通过判据**：
  - A 的查询/展示/回滚/修改范围严格限定在 A 的 `user_id`；
  - 跨 user_id 的读取、更新、回滚一律拒绝，隔离破坏不被静默允许（D3 §7.1）；
  - C 轨：UI 仅渲染当前用户数据，不暴露其他用户条目。
- **失败判据**：A 能看到或操作 B 的偏好历史；跨用户读写/回滚成功返回。
- **责任轨道**：D（`user_id` 隔离查询与持久化硬约束）；C（UI 仅渲染当前用户数据）。
- **证据状态**：`RUNTIME_UNVERIFIED`。

---

## 六、D 轨需提供的实际证据清单（均为 `RUNTIME_UNVERIFIED`）

以下证据须由 D 轨实现后在银河麒麟 VM 中实际执行并保留真实命令、退出码、stdout/stderr 与日志，方可作为验收通过依据。当前全部未执行。

1. **`current_version` 指针切换真实执行日志**：CREATE/UPDATE/ROLLBACK 后 `current_version` 正确指向对应版本，且切换原子提交。
2. **版本链事务完整性证据**：事务提交/回滚后版本链一致（v1→v2→v3 链完整，previous_version_id 正确）。
3. **并发更新冲突证据**：对 `memory_entries.version` 乐观锁字段的并发更新冲突检测与失败处理证据。
4. **回滚不删除中间版本证据**：ROLLBACK 后 v1/v2/v3 历史记录仍完整保留在持久化层。
5. **跨用户查询隔离证据**：不同 `user_id` 读写/回滚相互隔离，跨用户访问被拒绝。

> 上述均为 D 轨版本持久化的**用户可观察业务结果**证据，属 D 轨职责；E 轨不代为实现或证明。

## 七、C 轨需提供的实际证据清单（均为 `RUNTIME_UNVERIFIED`）

以下证据须由 C 轨实现后在银河麒麟 VM 中实际执行并保留真实交互/日志证据，方可作为验收通过依据。当前全部未执行。**不得使用截图或静态代码存在冒充真实交互验收**。

1. **QML 历史列表渲染证据**：偏好历史版本列表按版本链正确渲染（UPDATE 保留 v1、ROLLBACK 保留中间版本）。
2. **修改交互证据**：用户修改偏好触发 UPDATE，UI 当前值更新为 vN 且历史保留。
3. **回滚交互证据**：用户回滚操作触发 ROLLBACK，UI 当前值切换为目标历史版本且中间版本历史保留。
4. **临时/长期偏好 UI 区分展示证据**：临时偏好明确标注为临时/会话级/到期，不误展示为稳定 global 长期偏好。
5. **跨用户不可见证据**：仅渲染当前用户数据，其他用户偏好历史不可见、不可操作。

> 上述均为 C 轨偏好 UI 的**用户可观察行为**证据，属 C 轨职责；E 轨不代为实现或证明。QML 真实交互需在银河麒麟 VM 中表现为可操作的真实行为（真实 UDS 连接链路），不得以 Mock 冒充。

---

## 八、禁止状态声明

本文件**不包含**任何 `PASS` / `HOST_VERIFIED` /「已完成」声明。以下事项在本任务 `runtime_required=false` 下均为 `RUNTIME_UNVERIFIED`，**不得**标记为已验收或已实现：

- C 轨 QML 历史列表、修改、回滚交互；
- D 轨 `current_version` 指针切换、事务、并发正确性；
- 任何 UI 截图或数据库 schema 截图（本任务不采集）；
- 本文件定义的任一验收案例的真实执行。

E 轨策略（D7E-01/02/03）已有单元测试与回归测试（S-07），但那些是**策略逻辑**的 L0/L1 证据，**不是** C 轨 UI 或 D 轨版本持久化的验收证据，也不构成对本文件验收案例的通过判定。

---

## 九、禁止以本地回归冒充文档内容验收

- 本任务可执行的本地白名单 pytest 命令（D7E 单元与回归测试）仅作为**既有 E 轨生产代码不被本任务破坏**的回归证据，**不得**把 pytest 通过冒充本文件验收案例的验收，或冒充 C/D 轨 UI/持久化通过。
- 本文件关键内容（各验收案例判据、状态标记、scope 约束、D/C 责任划分）由 Reviewer **逐条核对 acceptance_criteria** 后判定，而非由自动化 pytest 判定。

---

## 十、会议/交接要点（供 D/C 轨衔接）

- 本规范只冻结**用户可观察的验收标准**；D 轨与 C 轨各自负责实现与证明其职责范围（见第六、七章）。
- D 轨实现 `current_version` 切换、事务与并发时，应保证本规范 UPDATE/NO_OP/ROLLBACK 的用户可观察结果可达成；C 轨实现 UI 时，应保证本规范 CREATE/COEXIST/UPDATE/ROLLBACK/临时/跨用户隔离的展示行为可达成。
- 若实现中发现判据与真实宿主能力冲突，请提出修订任务，不得在本任务内降级判据。

---

## 十一、变更记录

| 版本 | 日期 | 作者 | 变更说明 | 状态 |
|------|------|------|----------|------|
| v1 | 2026-08-24 | E 轨道 | 初稿：形成 Day7E 对 C 轨偏好 UI 与 D 轨版本持久化的业务验收规范（CREATE/COEXIST/UPDATE/NO_OP/ROLLBACK + 临时偏好 + 跨用户隔离）；明确 D/C 各自证据清单；全部 C/D 验收案例证据状态 `RUNTIME_UNVERIFIED`；文档状态 `PENDING_INTEGRATION` | `PENDING_INTEGRATION` |

---

*本文档为 E 轨单方面提出的验收规范候选，不代表 C 轨 UI 或 D 轨版本持久化已实现或已通过验收。*
