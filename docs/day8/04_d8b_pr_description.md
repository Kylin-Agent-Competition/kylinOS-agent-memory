# [D8-B] Knowledge 索引元数据与关系、状态、版本检索

## 背景与目标

D8-B 按 75 项施工台账交付 Knowledge 的 FTS5/Vector 索引字段设计、证据关系和
状态过滤，并准备冲突、版本和生命周期检索条件。目标是让知识能按类型、来源、版本、
状态和关系检索，同时保持 SQLite 回源真值和 RRF 前硬过滤。

对应任务卡：[`docs/day8/03_d8b_task_card.md`](03_d8b_task_card.md)。

## 本 PR 变更

- 新增 `KnowledgeFilter` 与 `KnowledgeIndexMetadata`，统一描述知识类型、开放分类、
  来源事件、版本、状态和关系查询/索引元数据；空元数据、跨对象使用均拒绝。
- 扩展 FTS5 最小索引端口：以参数化标量字段预过滤类型、分类、来源、版本和状态；
  索引输入仅接受上游敏感过滤后的 `content_summary`；`relation_ids` 不进入 FTS
  表达式，必须由 SQLite 真值复核。
- 扩展 Vector CLI JSON bridge 与 Collection scalar fields：支持同一组 Knowledge 元数据
  的写入与类型、分类、来源、版本、状态预过滤。
- 扩展 `fuse_retrieval()`：对 Knowledge 在 RRF 前执行类型、分类、来源、版本、状态和
  必要关系的硬过滤；候选解释只报告匹配状态，不暴露关系 ID。
- 关闭 `TD-031`：同一用户、同一 Knowledge 存在多个 `is_current=true` 版本时，无论
  truth 输入顺序均失败关闭，不再 last-wins。
- 新增 D8-B 定向测试与目标麒麟 L2 脚本。

## 安全与失败语义

- 用户隔离、对象类型、状态、敏感度、冲突、当前版本和关系过滤均在 RRF 前执行。
- 索引端的命中永远不能绕过 SQLite 回源复核；未解决冲突、多个 current、状态不一致、
  关系缺失或非法元数据均不进入融合。
- 关系 ID 不写入候选解释；候选 `explanation` 的单通道降级只公开通道名称。
  `RetrievalOutcome.degraded_channels` 的 Provider 异常原文脱敏仍由 `TD-029` 跟踪。

## 验证

| 层级 | 检查 | 结果 |
|---|---|---|
| L0/L1 | D8-B、E2E 输入契约与 Vector 桥定向测试 | 54 passed |
| L1 | `memory-service/tests/retrieval` | 266 passed |
| 更广 Python（信息性） | `cd memory-service && pytest tests -q` | 1022 passed、49 skipped、36 failed、36 errors（Windows 缺少 `socket.AF_UNIX`，并有非 D8-B 配置、迁移、Outbox 失败）；不作为本 PR 的通过证据 |
| 静态 | `git diff --check` | PASS |
| L2 | `tests/vector-engine/run_d8b_knowledge_filter_l2.sh` | 待目标麒麟环境与 KySec-trusted CLI 执行；未声称已验证 |

## 性能影响

- FTS5 与 Vector 仅增加可索引的标量预过滤条件；RRF 算法、候选上限和 SQLite 回源
  复核流程不变。
- 真实 Vector CLI 的索引写入、查询延迟与资源占用尚未在目标麒麟环境量化；L2 执行时
  应记录基线与变更后的指标，未取得该证据前不作性能改善或无回归的结论。

## 范围与跨轨依赖

- 不实现 D 轨 `memory_relation` / `memory_conflict` 持久化、Migration、Outbox 或事务策略。
  D8-B 通过已存在的 `TruthRecord` 接缝消费关系真值。
- 不实现 A 轨知识抽取、C 轨 QML、E 轨业务生命周期/冲突优先级，亦不冻结冲突判定阈值。
- 真实 Vector CLI 的新增字段需要在目标麒麟环境完成 L2 编译和运行，才可升级宿主证据；
  本 PR 的本地测试不替代该证据。

## Reviewer 关注项

1. 索引预过滤是否始终由 SQLite 真源同条件复核；
2. 多 current 版本是否在所有对象类型上顺序无关地失败关闭；
3. Vector scalar 字段、输入长度校验和表达式转义是否与 CLI JSON 契约一致；
4. 关系 ID 与 Provider 异常原文是否未泄露到对外候选解释。

## 回滚

回滚本 PR 即可恢复 D7-B 的 Knowledge 选择行为；无数据库迁移、外部资源创建或不可逆
数据变更。
