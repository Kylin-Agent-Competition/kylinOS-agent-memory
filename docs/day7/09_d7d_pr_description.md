# D7D PR：偏好版本持久化、事务与迁移

## 当前 PR 状态

本 PR 已收到非作者 Reviewer 的 `REWORK`。现已修复 NO_OP 操作回执、历史不可变约束、状态枚举约束和文档偏差，并提交、推送至 `48a2bea`；本地定向回归和麒麟 L2 均已完成。当前仅等待非作者 Reviewer 对最新提交给出复审结论，不据此提前宣称 D7D 已完成。

## 目标

按 D7D 台账建立偏好版本持久化真源：历史不可原地覆盖，同一用户同一记忆最多一个 current 版本，创建/更新/去重/回滚在事务中完成，Migration 可升级并可回退。

## 本次提交内容

| 文件 | 变更 | 说明 |
|---|---|---|
| `memory-service/db/schema.py` | 修改 | 增加版本项、版本历史、操作回执、current 指针、枚举约束、索引和不可变触发器 |
| `memory-service/db/engine.py` | 修改 | 在快速建库路径创建 D7D 版本与回执触发器 |
| `memory-service/db/repositories.py` | 修改 | 实现创建、更新、当前/历史读取、幂等、证据去重、NO_OP 回执与回滚 Repository |
| `migrations/versions/20260831_preference_versions.py` | 新增 | 新增 D7D 版本表、操作回执与可逆 Migration；存在历史或回执时拒绝破坏性 downgrade |
| `migrations/alembic.ini` | 修改 | 删除非 ASCII 注释，避免 Windows 默认编码下 Alembic 读取配置失败 |
| `memory-service/tests/test_preference_version_repository_d7d.py` | 新增 | 覆盖事务、NO_OP 回执、幂等/证据冲突、回滚、隔离、并发、历史不可变与枚举约束 |
| `memory-service/tests/test_migrations_d7d.py` | 新增 | 覆盖升级、触发器/索引、既有 D4D 数据保留、空库回退、历史存在时回退拒绝 |
| `docs/day7/08_d7d_task_card.md` | 修改 | 回填真实实现与验证状态 |
| `docs/day7/09_d7d_pr_description.md` | 修改 | 回填 Draft PR 的实际范围与验证状态 |

## 后续计划

1. 等待 Reviewer 基于 `48a2bea` 完成逐项复审。
2. 取得非作者 Reviewer 批准后，按门禁合并。

## 不在范围内

- 不修改 A、B、C、E 轨交付物，不替代其实现或审查。
- 不增加 Provider、QML、IPC、FTS/Vector/RRF、Outbox 重试、D8 冲突或 D10 遗忘实现。
- 不将 L0/L1 结果或本地 SQLite 验证表述为宿主 L2/L3 能力。

## 已知依赖与风险

- 当前基线已有 `Preference.version` / `previous_version_id` 领域校验与 D7B current-version 消费逻辑；本 PR 新增 D7D 数据库真源，但尚未接入 C 轨 IPC/QML 调用链。
- 版本表与 `memory_entries` 保持独立，避免改写 D4D 通用记忆表；跨轨需要时由调用方以 Repository 接缝集成。
- 破坏性 Migration downgrade 会在版本历史存在时拒绝执行，避免静默删除数据；真实生产恢复策略仍需 L2 演练。
- 本实现起始于 `origin/main@8ab369b`，现已通过 merge 同步至 `origin/main@31b5279`。

## 验证状态

| 层级 | 状态 | 说明 |
|---|---|---|
| 静态检查 | 通过 | `compileall -q db tests/test_preference_version_repository_d7d.py tests/test_migrations_d7d.py` 与 `git diff --check` 通过 |
| L0/L1 | 通过 | D4D、PR2、D7D Migration 与 Repository 组合测试：`30 passed in 26.64s` |
| L2 麒麟虚拟机 | 通过 | 前台可见麒麟 V11 链接克隆；SSH 传输并校验 `48a2bea`；四个定向测试文件 `30 passed in 20.56s`、退出码 `0` |
| L3 全链路 | 未执行 | 本 PR 当前阶段不具备条件 |

## 安全与假实现审查

- current 版本由 `memory_items.current_version_id` 与 `memory_versions.is_current` 双重一致性检查读取；部分唯一索引拒绝两个 current 版本，历史版本不得被直接重新激活。
- 所有读取以 `user_id` 过滤；跨用户读取与回滚均失败关闭。
- 每次写入或 NO_OP 都创建不可变操作回执；相同幂等键仅在请求指纹相同才重放，同一证据指纹试图写入不同值或状态时拒绝。
- 更新和回滚均插入新版本；历史正文、证据、请求审计字段和版本链不可原地修改，仅允许 current 切换时将旧版本标记为 `superseded`。
- 不使用 Mock 冒充宿主能力；L2 已在真实麒麟虚拟机执行，L3 未执行状态如实保留。

## 性能影响

- current 读取走 `(user_id, preference_key, preference_scope)` 唯一项及 current 指针；版本历史按 `(memory_item_id, version)` 有序索引读取。
- 写入仍复用 D4D 的 WAL、`busy_timeout` 与进程内单写锁；并发更新被串行化，避免双 current。

## 回滚方式

- 业务回滚：`rollback_preference_version()` 追加新的 current 版本，不覆盖历史。
- 部署回滚：版本表和操作回执均为空时可执行 `alembic downgrade 20260826_add_trace_id`；存在历史或回执时 Migration 将拒绝破坏性回退，需先按数据保留方案处理，禁止直接删除版本记录。

## Reviewer 检查重点

- 本 PR 是否准确说明已实现的运行时范围、已完成的 L2 证据与尚未完成的 L3 证据。
- 代码是否用数据库约束和事务保证 current 唯一性、用户隔离、幂等与历史不可变。
- 每个 Migration 是否具备可验证的 `upgrade()` 与 `downgrade()`；回退不得静默丢失版本历史。
