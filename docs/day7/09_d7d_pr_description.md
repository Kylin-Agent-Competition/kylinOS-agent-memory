# D7D Draft PR：偏好版本持久化、事务与迁移

## 当前 PR 状态

本 PR 为 Draft，当前提交仅包含 D7D 施工任务卡与 PR 正文准备材料。尚未实现 `MemoryItem` / `MemoryVersion`、Migration、Repository、并发控制、幂等、回滚或任何运行时能力；不得据此宣称 D7D 已完成。

## 目标

按 D7D 台账建立偏好版本持久化真源：历史不可原地覆盖，同一用户同一记忆最多一个 current 版本，创建/更新/去重/回滚在事务中完成，Migration 可升级并可回退。

## 本次提交内容

| 文件 | 变更 | 说明 |
|---|---|---|
| `docs/day7/08_d7d_task_card.md` | 新增 | 施工范围、基线、约束、依赖、顺序与验收标准 |
| `docs/day7/09_d7d_pr_description.md` | 新增 | Draft PR 状态、后续实施范围与验证门槛 |

## 后续计划

1. 根据 D4D Alembic 基线实现可逆的 D7D Migration。
2. 实现 Repository 的创建、更新、幂等、历史读取和回滚事务。
3. 以数据库约束保证 `(user_id, memory_id)` 的 current 版本唯一性。
4. 完成升级/回退、并发、重复证据、事务失败和跨用户隔离测试。
5. 在银河麒麟前台虚拟机执行 L2 迁移与回归，补充可复现证据。

## 不在范围内

- 不修改 A、B、C、E 轨交付物，不替代其实现或审查。
- 不增加 Provider、QML、IPC、FTS/Vector/RRF、Outbox 重试、D8 冲突或 D10 遗忘实现。
- 不将文档、L0/L1 结果或本地 SQLite 验证表述为宿主 L2/L3 能力。

## 已知依赖与风险

- 当前基线已有 `Preference.version` / `previous_version_id` 领域校验与 D7B current-version 消费逻辑，但缺少 D7D 数据库真源。
- 具体表结构、部分唯一索引、回滚的数据语义和跨轨调用接缝必须先通过测试锁定；任何不明确的业务选择移交 E 轨确认。
- 创建实际实现前必须重新同步 `main`；本 Draft 基于 `origin/main@8ab369b` 的本地缓存。

## 验证状态

| 层级 | 状态 | 说明 |
|---|---|---|
| 文档核验 | 通过 | 已核对任务卡的文件、范围、施工顺序与 PR 正文一致 |
| L0/L1 | 未执行 | 尚无 D7D 代码或 Migration |
| L2 麒麟虚拟机 | 未执行 | 仅在实现和本地验证后执行 |
| L3 全链路 | 未执行 | 本 PR 当前阶段不具备条件 |

## Reviewer 检查重点

- 本 Draft 是否准确限制为准备文档，未虚报运行时实现或测试完成。
- 后续代码是否用数据库约束和事务保证 current 唯一性、用户隔离、幂等与历史不可变。
- 每个 Migration 是否具备可验证的 `upgrade()` 与 `downgrade()`；回退不得静默丢失版本历史。

