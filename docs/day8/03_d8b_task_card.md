# D8-B 任务卡：知识索引字段与关系、状态、版本检索

| 字段 | 内容 |
|---|---|
| 任务编号 | D8-B |
| 责任轨道 | B（Vector、FTS5、RRF、检索、索引与检索评测） |
| 基线 | `origin/main` `8011e26`（2026-08-29 同步） |
| 目标 | 设计并接通 Knowledge 的 FTS5/Vector 检索元数据，在 SQLite 回源边界按类型、来源、当前版本、状态和关系执行确定性硬过滤。 |
| 完成定义 | 知识可按类型、来源、版本、状态和关系检索；非法或不一致的当前版本、状态和关系输入失败关闭。 |
| Reviewer | 一名独立、非作者 Reviewer；D 关注可实现性，遗忘、用户隔离或指标影响由 E 关注。 |

## 权威目标与约束

15 天 75 项施工台账为 D8-B 指定三项交付：

1. 设计知识 FTS/Vector 索引字段；
2. 实现证据关系和状态过滤；
3. 准备冲突、版本和生命周期检索条件。

本任务继续遵守 ADR-001：FTS5 与 Vector 只负责召回和可验证的标量预过滤，
SQLite 是正文、用户归属、版本、状态、关系和冲突的真源；全部合法性检查必须在
RRF 聚合前完成。

## 预先确认的测试接缝

- `RetrievalFilter` / `RetrievalCandidate`：Knowledge 查询条件和结果元数据的 typed contract。
- `Fts5Index.upsert()` / `Fts5Index.search()`：FTS5 知识元数据写入和参数化预过滤。
- `VectorCliClient.insert()` / `VectorCliClient.search()`：Vector 标量字段的 JSON 桥接边界。
- `fuse_retrieval()` / `retrieve_graceful()`：SQLite 回源硬过滤、当前版本选择、RRF 与解释字段。

测试仅通过以上公共接口观察行为，不测试私有函数或内部 SQL 实现细节。

## 索引与真源字段

| 语义 | 字段 | FTS5 / Vector 预过滤 | SQLite 回源复核 |
|---|---|---|---|
| 用户隔离 | `user_id` | 必须 | 必须 |
| 对象类型 | `object_type=knowledge` | 必须 | 必须 |
| 知识类型 | `knowledge_type` | 支持 | 必须 |
| 开放分类 | `primary_category` | 逻辑索引元数据 | 必须 |
| 来源 | `source_event_id` | 支持 | 必须 |
| 版本 | `version_id` | 支持 | 必须；且必须是唯一 current |
| 生命周期 | `memory_status` | 支持 | 必须 |
| 关系 | `relation_ids` | 不依赖标量索引判定 | 必须；查询要求为 AND 子集匹配 |
| 冲突 | `conflict_state` | 不参与相关性打分 | 必须；未解决项默认排除 |
| 敏感度 | `sensitivity` | 不依赖索引判定 | 必须 |
| 全文/向量输入 | 经敏感过滤的 `content_summary` | 召回输入 | 返回时仍回源 SQLite |

索引字段只能缩小召回范围，不能替代 SQLite 的相同条件复核。关系 ID 不拼接为
Vector 表达式，也不写入解释正文；D 轨 `memory_relation` 表合并前由调用方通过
既有 `TruthRecord` 接缝提供结构化关系真值。

## 原子实施顺序

1. 扩展 typed filter、Vector record 和候选元数据契约，锁定空值拒绝、去重排序和兼容默认值。
2. 扩展 Knowledge 回源真值与硬过滤，覆盖类型、来源、版本、状态和关系；解决 TD-031 的多 current 顺序依赖。
3. 扩展 FTS5 知识元数据写入与参数化预过滤，并证明回源复核仍能拦截陈旧或伪造索引命中。
4. 扩展 Vector CLI 标量字段桥接与过滤表达式，保持未知字段拒绝、字符串转义和用户隔离。
5. 运行 D8-B 定向测试、完整 retrieval 回归和静态检查，补齐 PR 草案与限制说明。

每个行为切片均按 red → green 执行，前一切片通过后才进入下一项。

## 明确不修改的范围

- 不实现或修改 D 轨 `memory_relation`、`memory_conflict` 表、Migration、Repository、Outbox 或事务策略。
- 不实现 A 轨知识抽取、C 轨 QML，或 E 轨知识分类、冲突优先级和生命周期流转规则。
- 不实现冲突检测阈值、业务重排、Top-K/token 预算或比赛指标调参。
- 不把本地 Python/C++ 静态检查冒充麒麟宿主或完整持久化链证据。
- 不读取或使用其他人的未合并分支作为实现基线。

## 验收与验证

- typed contract：Knowledge filter 列表去重排序，空字符串、未知字段和跨对象误用被拒绝。
- 检索：按知识类型、来源、指定当前版本、状态及必要关系组合查询均可验证。
- 失败关闭：跨用户、非 current、多 current、未解决冲突、非法状态、缺少必要关系均不进入 RRF。
- 一致性：FTS5/Vector 预过滤不能绕过 SQLite 回源复核；输入顺序置换不改变结果。
- 降级：FTS5-only、Vector-only 和单通道故障继续返回经过完整硬过滤的结果。
- 回归：`memory-service/tests/retrieval` 全绿，`git diff --check` 通过。
- L2（待目标麒麟环境执行）：`tests/vector-engine/run_d8b_knowledge_filter_l2.sh` 对真实
  Vector CLI 验证类型、分类、来源、版本和状态标量预过滤，并输出被测提交与 bridge 哈希。

## 已知跨轨依赖

- 默认分支尚无 D 轨 `memory_relation` / `memory_conflict` 持久化；本任务只能验证结构化真值接缝，不能声明完整数据库链路通过。
- `memory_status`、知识六类及冲突业务优先级来自已合并 E 轨业务语义；B 不扩写或替代这些规则。
- Vector C++ 桥的新增物理字段仍需在目标麒麟 Vector Engine 版本完成 L2 构建与运行验证后，才能升级宿主证据等级。

## 回滚

回滚本批次提交即可恢复 D7-B 的偏好过滤和既有 Knowledge 选择行为；本任务不包含
数据库迁移、外部资源创建或不可逆数据变更。
