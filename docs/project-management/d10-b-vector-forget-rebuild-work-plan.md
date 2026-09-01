# D10-B Vector 精确删除与重建一致性工作计划

## 目标与完成定义

基于 `origin/main@8ab369b`，交付 D10 B 轨的 Vector 精确删除、由 SQLite 真源构建的全量重建，以及删除残留率验证。完成时，已经遗忘的记忆必须同时满足：

1. 实时 Vector 查询不再召回；
2. SQLite 真源重建后的新 Collection 也不再召回；
3. 用户、版本、确认范围和删除态均保持 fail-closed；
4. 宿主实测日志能绑定 `tested_commit`，不以本地替身测试替代麒麟 VM 证据。

台账依据：`75项个人施工台账` 的 D10-B（R53）。该行要求“实现 Vector 精确删除和过滤、实现 SQLite→Vector 全量重建、验证实时删除和重建后的残留率”。

## 基线与范围

| 项目 | 结论 |
| --- | --- |
| 工作分支 | `feature/d10-b-vector-forget-rebuild` |
| 基线 | `origin/main@8ab369b`（已含 D8-B、D9-B 与 A 轨 D10 缓存失效） |
| B 轨范围 | Vector bridge、Python Vector 适配、重建编排/验证、检索与删除一致性测试、B 轨证据和 PR 材料 |
| 审查 | D 主审；遗忘、用户隔离和指标口径请 E 补审 |

不在本批范围：A 轨缓存失效和 Embedding Provider 改造、C 轨遗忘 QML、D 轨 Forget 事务/确认令牌/Outbox 优先级、E 轨 ForgetPlan 解析和业务安全规则。

## 已确认的现状

- `VectorProvider` 已冻结 `delete` 与 `rebuild` 契约；`FakeVectorProvider` 已覆盖单条删除、跨用户拒绝、重放、full-reset 门禁与代次重建。
- 生产 `VectorCliClient` 和 `vector_bridge_cli.cpp` 目前仅支持 `create_collection`、`insert`、`search`、`drop_collection`，没有精确删除或重建命令。
- `memory_entries` 的软删除会同步移除 FTS5 记录；Vector 侧虽有不可绕过的 `is_deleted` 查询过滤，仍缺少物理精确删除与从真源恢复的闭环。
- SQLite 表不保存向量。重建必须经由已合并的 Embedding 能力重新生成向量，且只读取已提交、非删除、属于目标用户/作用域的真源记录。

## 原子工作清单

总进度：3/5（60%）；第 4 项 L1 口径已完成，L2 重建残留率待真实宿主；第 5 项待提交授权。

1. **精确删除 bridge**：为 C++ CLI 增加受控 `delete` 请求；仅接受解析后的用户、记忆 ID、版本/代次条件，构造不可放宽用户边界的 SDK 表达式；未知 JSON 键、空/通配选择器、跨用户和服务端失败均失败关闭。
2. **SQLite 重建快照边界**：定义 B 轨只读快照读取器，固定 `snapshot_id`、水位、用户/作用域、排序和记录摘要；软删除、非当前版本或无法生成合法向量的记录不得进入目标 Collection，并被计入明确的拒绝原因。
3. **代次重建与激活**：在新代次 Collection 完整写入并校验计数/水位/摘要后才切换 serving generation；构建、写入或校验失败时保留旧代次，清理失败目标并报告可重试结果。
4. **残留率与回归验证**：构造“写入→Forget 已提交→实时删除→搜索→全量重建→搜索”的最小数据集，分别计算实时和重建后的残留率；覆盖重复删除、重放、跨用户、版本不匹配、重启后和部分失败恢复。
5. **证据与 Draft PR**：补齐 L1/L2 运行器、脱敏日志索引、已知限制和回滚说明；Draft PR 只陈述已执行测试，未取得前台麒麟 VM 证据的项目明确标为待验证。

## 2026-08-31 执行状态

本次先收口当前分支可独立完成的 B 轨 bridge 工作，状态如下：

| 项目 | 状态 | 已有证据 / 限制 |
| --- | --- | --- |
| 受控 Vector CLI `delete` 协议 | 已实现并完成 L1 | C++ bridge 只接受用户、数值主键和同位置版本 ID，单次至多 500 对；未知键、空选择器、超长选择器、未配对版本与 SDK 错误均失败关闭。Python 桥接测试和完整 retrieval 测试通过。 |
| 宿主删除运行器 | 已提供，待麒麟验证 | 运行器覆盖目标删除、跨用户 ID、版本不匹配、重复删除、超长选择器与其他非法输入，并仅清理本次成功创建的 `d10b_` 临时集合。当前工作区没有受信任 `vector_bridge_cli` 二进制，不能将静态检查或模拟运行表述为 L2。 |
| 冻结 `VectorDeleteRequest` 正式适配 | 阻塞 | 缺少 D 轨提供的逻辑记忆 ID 到 Vector 数值主键映射、serving generation、水位与幂等结果接线；不得用 CLI 的 `requested_count` 伪造 `VectorDeleteResult`。 |
| SQLite 重建快照读取器 | 已实现并完成 L1 | `SqliteVectorSnapshotReader` 仅在调用方已开启的 SQLite 读事务中，按用户和主键顺序读取未软删除的 `memory_entries`；保留调用方提供的快照标识与水位，无法解析索引文本或版本非法的记录以明确原因拒绝。它不消费 D 轨版本真源、不激活代次，也不调用 Embedding。 |
| 代次重建与残留率 | 阻塞 | 仍依赖 D 轨提供逻辑记忆 ID 到 Vector 数值主键映射、版本真源、serving generation、水位与幂等结果接线，以及 A 轨可调用的真实 Embedding 输入；当前不得用固定向量或模拟成功代替。 |

本节仅更新实际执行状态，不改变既有契约、验收标准或跨轨责任边界。

## 2026-09-01 执行状态（本轮：正式适配、代次重建与残留率口径）

> 在 D 轨、A 轨授权下，于 `feature/d10-b-vector-forget-rebuild` 直接实现并验证；仅更新实际执行状态，不改变既有契约、验收标准或跨轨责任边界。

| 项目 | 状态 | 已有证据 / 限制 |
| --- | --- | --- |
| 冻结 `VectorDeleteRequest` 正式适配 | 已实现并完成 L1，删除 bridge 麒麟 L2 通过 | 新增 `SqliteVectorProvider.delete`：D 轨确认 selector 经 SQLite 真源映射为数值 PK 与 `v{version}`，幂等回执落库，不伪造 `requested_count`。映射约定冻结：`memory_id == str(memory_entries.id)`、`version_id == "v" + memory_entries.version`。 |
| 代次重建与激活 | 已实现并完成 L1 | `SqliteVectorProvider.rebuild`：事务快照 → A 轨 Embedding → 新 Collection → 校验摘要/水位 → 原子切换 serving；构建/写入失败保留旧代次并清理目标代次；重放与幂等、截止超时、重启恢复均有测试。`get_index_state` 从 SQLite 账本返回可查询状态。 |
| 残留率评测口径 | 已实现并完成 L1 | `evaluate_forget_residual` 输出数据集版本、快照标识、水位、样本/观测/残留数与残留率；L2 重建残留率仍待真实宿主。 |
| Vector 账本迁移 | 已实现并完成 L1 | `20260901_d10b_vector_ledger`：generations/entries/receipts 三张表 + 每作用域至多一个 serving 的部分唯一索引；回退拒绝有数据的账本。 |
| 麒麟 L2（删除协议） | 已通过 | 克隆 VM `Kylin-V11-2603-D10B-c15866d-Test`（基快照 `20-btrack-test-deps-20260821`）；`run_d10b_vector_delete_l2.sh` 在最终 HEAD 上重跑 **15/15 通过**，tested_commit=`4675e60`（桥接/运行器哈希与 c15866d 一致，证明 L2 主题零差异）；engine `1.2.0.1-0k0.11`，client `1.2.0.0-0k0.7`；证据见 `evidence/l2-kylin-vm/d10b_vector_delete_l2_20260901.md`（原始日志 SHA-256 见该文档）。 |

L1 验证：D10B 定向 57 passed；`tests/retrieval` + 迁移 311 passed；`git diff --check`、`py_compile` 通过。全量 suite 中 24 failed / 36 errors 均为 Windows 无 `AF_UNIX` 的既有环境问题（主基线同样复现），与本批改动无关。

仍未完成（不改变既有结论）：
- 代次重建与残留率的麒麟 L2：依赖 D 轨确认请求 DTO 接入运行服务、A 轨真实 Embedding 输入，本轮未执行，保持 `UNVERIFIED`；不得以本地测试或模拟成功替代。
- 本批代码尚未提交；提交、推送与 PR #82 更新待用户单独授权。

## 依赖与阻塞边

| Ticket | 前置条件 | 跨轨依赖 | 验证方式 |
| --- | --- | --- | --- |
| 01 精确删除 bridge | 无 | D/E 已解析且已确认的删除选择器与授权信息 | CLI 单测 + Python 适配测试 |
| 02 快照读取器 | 无 | D 的已提交真源/水位；A 的可用 Embedding 调用 | SQLite fixture + 非法/删除行排除测试 |
| 03 代次重建 | 02 | D 的 serving generation 状态接线 | 构建失败保留旧代次测试 |
| 04 残留率验证 | 01、03 | E 确认遗忘/残留统计口径 | L1 端到端 + 前台麒麟 L2 |
| 05 证据与 Draft PR | 04 | D/E 独立审查 | `tested_commit`、日志和 PR 检查表 |

若 D 的水位/服务代次接线或 A 的可调用 Embedding 输入尚未合并，02/03/04 必须标记 BLOCKED；不得用固定向量、模拟成功或未验证的默认分支替代。

## 验收标准

| 类别 | 验收条件 |
| --- | --- |
| 精确性 | 同一 user、同一确认范围内的目标被删除；其他用户、未选版本和未确认记录不受影响 |
| 一致性 | 实时删除与 SQLite→Vector 重建后，目标均为零召回；残留率计算可复现且绑定数据集版本 |
| 可恢复性 | 重放不造成额外副作用；构建失败不替换 serving generation；重启后根据真源恢复 |
| 安全 | 选择器空值/通配、跨用户、未知 filter 键、非法向量和 SDK 错误均失败关闭；日志不含正文 |
| L1 | B 轨相关 pytest、C++ bridge 协议测试和静态检查通过 |
| L2 | 麒麟 VM 前台执行真实 Vector 删除/重建/重启测试，归档脱敏日志、环境、Collection 名称和 `tested_commit` |

## Draft PR 预案

- 标题：`feat(retrieval): 实现 D10 Vector 精确删除与重建一致性`
- 基准分支：`main`
- 头分支：`feature/d10-b-vector-forget-rebuild`
- 状态：Draft
- 正文必须列出上述五个事项的实际状态、测试结果、D/E 依赖、L2 证据位置、风险与回滚；不得把计划或 L1 替身结果表述为宿主完成。

## 回滚

回滚本批 B 轨提交可恢复到 `origin/main@8ab369b` 的检索实现。测试 Collection 必须使用隔离前缀并在运行器结束时清理；不会删除生产 Collection、SQLite 真源或其他轨道证据。
