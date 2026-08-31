# D7D 任务卡：偏好版本持久化、事务与迁移

| 字段 | 内容 |
|---|---|
| 任务编号 | D7D |
| 责任轨道 | D（SQLite、Repository、Migration、事务与部署） |
| 基线 | 起始基线为 `origin/main@8ab369b`；已通过 merge 同步至 `origin/main@31b5279` |
| Reviewer | E（非作者 Reviewer） |
| 当前状态 | `REVIEW_REWORK_PENDING_APPROVAL`：独立 Reviewer 提出的 D7D 数据一致性问题已修复、提交、推送，并通过 L0/L1 与麒麟 L2；待最新提交的独立复审 |

## 目标与完成定义

完成 15 天 75 项台账的 D7D 交付：建立 `MemoryItem` / `MemoryVersion` 持久化模型和 current version 真源，提供创建、更新、去重、回滚的事务语义，并验证 Migration 可升级、可回退。

完成后，版本历史不得被原地覆盖；同一用户、同一记忆至多存在一个 current 版本；并发写入、重复证据和事务失败均具有确定、可恢复的行为。

## 已确认基线与约束

- D4D 已提供 Alembic、`001_initial_schema`、`20260826_add_trace_id` 与 SQLite WAL / `busy_timeout` 配置；后续脚本必须遵循 `YYYYMMDD_<description>.py` 命名且实现 `downgrade()`。
- 基线的 `memory_entries` 是既有记忆实体表；D7D 在此基础上演进，不手工修改用户数据库，也不重写已存在的迁移。
- `Preference` 领域模型已冻结 `version` / `previous_version_id` 校验：首版无前驱，后续版本必须指向前版；领域校验不等同于数据库持久化已完成。
- D7B 检索融合层要求每个偏好版本链只有一个 `is_current=true` 真值。D7D 必须用数据库约束和事务保证此不变量，不能依赖调用方约定。
- `user_id`、版本编号、时间戳、当前指针和幂等键均由受信任服务端路径写入，模型不得生成或覆盖。

## 计划修改范围

1. 新增 D7D Migration：演进 `memory_entries` 并新增或规范化版本表、版本链、current 标识、版本/用户/状态索引与唯一性约束。
2. 在 `memory-service/db/` 或现有 D 轨 DAO 接缝实现版本 Repository：创建、读取 current、读取历史、更新、回滚与幂等回查。
3. 将版本更新纳入单一事务：旧 current 失效、新版本插入、版本链写入、审计/索引事件（如已存在的接缝允许）必须一起成功或一起回滚。
4. 新增 Repository 与 Migration 测试，覆盖升级、回退、唯一性、跨用户隔离、并发竞争、重复证据、事务异常与回滚。
5. 补充 L0/L1 证据；在银河麒麟前台虚拟机执行 L2 迁移与回归，记录真实结果（已完成）。

## 禁止扩张范围

- 不实现 A 轨偏好抽取、B 轨 FTS/Vector/RRF 检索、C 轨 QML/IPC 页面或 E 轨业务规则。
- 不更改已冻结 Provider 或 IPC 方法语义；若 D7D 实施发现必需的跨轨契约缺口，登记依赖而非自行扩张。
- 不实现 D8 关系/冲突、D9 Outbox 重试或 D10 精准遗忘业务。
- 不把本地 SQLite 单测或 Migration 文档冒充为银河麒麟 L2/L3 证据。

## 施工顺序与验收

| 顺序 | 工作项 | 验收方式 |
|---|---|---|
| 1 | 冻结字段到列的映射与不变量 | 任务卡和实现 Diff 对照：用户隔离、版本链、状态、证据、时间和 current 语义完整 |
| 2 | 编写可逆 Migration | 空库及已有 D4D 数据库分别执行 `upgrade head` 与 `downgrade base`；Schema 和数据策略可核验 |
| 3 | 写入唯一性约束 | 数据库拒绝同一偏好版本链存在多个 current 版本，且 Repository 对异常失败关闭 |
| 4 | 实现版本 Repository 事务 | 创建、更新和回滚后版本历史连续；任一 SQL 失败不遗留半更新 |
| 5 | 实现幂等与去重 | 相同幂等键或相同证据重放不创建新版本；冲突输入有结构化失败结果 |
| 6 | 实现回滚 | 回滚生成可追溯的新 current 版本或等价审计版本，不覆盖既有历史 |
| 7 | 运行 L0/L1 测试 | 迁移、Repository、并发和回归测试全绿；`git diff --check` 通过 |
| 8 | 执行麒麟 L2 | 前台虚拟机真实执行迁移链和相关回归；保存命令、提交、结果和失败信息 |

## 麒麟 L2 证据

- 环境：由基础快照 `20-btrack-test-deps-20260821` 创建的前台可见麒麟 V11 链接克隆 `Kylin-V11-2603-D7D-48a2bea-Test`，Python 3.12.3。
- 传输与提交：通过 SSH 传输仅包含 D7D 分支和 `main` 基线的 Git bundle；来宾中校验的 `HEAD` 为 `48a2beacadd3e39b86e1fe96a21c98b30054751b`。
- 依赖：离线安装项目声明范围内的 pytest 9.1.1、SQLAlchemy 2.0.52、Alembic 1.19.1 与 Pydantic 2.12.5。
- 命令：`cd memory-service && python3 -m pytest tests/test_migrations_d4d.py tests/test_migrations_trace_id_pr2.py tests/test_migrations_d7d.py tests/test_preference_version_repository_d7d.py -q`。
- 结果：`30 passed in 20.56s`，退出码 `0`。

## 风险与跨轨依赖

- SQLite 部分唯一索引与迁移回退的数据保留策略需先由测试锁定；不允许以删除历史换取唯一性通过。
- 并发写入必须在 WAL / `busy_timeout` 语义下验证；锁等待或约束冲突不能导致无限阻塞或产生双 current。
- D7B 已消费 current-version 真值；D7D 的列名、真值读取方式或变更通知如影响检索接缝，须与 B 轨确认后再修改。
- 偏好创建、共存、更新和回滚的业务选择属于 E 轨语义；D7D 只实现经确认的持久化行为。

## 交付门槛

- 首次实现提交前，展示完整 Diff、测试结果、Migration 升级/回退结果和已知风险，取得单独的 `commit` 授权。
- 推送与创建或更新 PR 需分别取得授权。
- 当前 PR 已进入 Ready for review；只有非作者 E Reviewer 对最新提交审查完成且 L2 证据齐全，才可声明 D7D 验收完成。
