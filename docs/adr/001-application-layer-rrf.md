# ADR-001：默认使用 Memory Service 应用层 RRF

- **状态**：提议（D3-B 冻结候选；PR #20 Review 返工中）
- **日期**：2026-08-03
- **责任轨道**：B（Vector、FTS5、RRF 与检索评测）
- **决策版本**：`rrf-v1`
- **适用范围**：FTS5 与 Vector 两路召回完成硬过滤后的候选融合

## 背景

Memory Service 需要融合 SQLite FTS5 与 Vector Engine 的召回结果。两路
原始分数的方向、范围和标定语义不同：FTS5 使用 BM25 排序，当前固定
Vector SDK/服务端组合返回的浮点 score 只取得“可用于通道内诊断”的宿主
证据，尚未独立确认它是 cosine 相似度、距离还是其他变换结果。

现有事实边界如下：

1. SQLite 是结构化记忆、用户归属、当前版本、状态和正文的真源；Vector
   是可重建语义索引。
2. D2-B 在指定麒麟 V11 环境取得 Vector Collection、Insert、Query、
   Search、Upsert、Delete、用户过滤和重启持久化的 E4 宿主证据。
3. 原生 `HybridSearch`、`RRFRanker` 与 `WeightedRanker` 只取得
   `ABI_VERIFIED / E3`，没有目标宿主成功运行的 E4 证据。
4. 用户、版本、状态、有效期、敏感度、冲突和遗忘属于硬过滤边界，不能
   通过降低融合分数替代。
5. Vector、Embedding 或 FTS5 单路故障时，检索链路必须能返回已经完成
   安全检查的部分结果或结构化空结果，不能阻塞聊天链路。

本 ADR 决定默认融合位置与确定性算法，不宣称 Recall@K、MRR、nDCG 或
P95 已达比赛目标，也不冻结后续业务重排权重。

## 候选方案

### 方案 A：Vector Engine 原生 Hybrid/RRF

由 Vector SDK 的 `HybridSearch` 和 `RRFRanker` 完成融合。

优点：

- 如果目标版本完整支持，可减少应用层融合代码；
- 排序过程可能靠近数据面，减少中间对象传递。

缺点：

- 当前只有 E3 ABI 证据，没有目标宿主 E4 成功调用证据；
- 无法证明其过滤顺序、错误语义、deadline 和确定性 tie-break 满足
  Memory Service 契约；
- FTS5 真源回查、安全过滤和单路降级仍需应用层编排。

### 方案 B：Memory Service 应用层 RRF

两路 Provider 分别返回 1 起始排名。Memory Service 先按精确版本去重，再
完成 SQLite 回源、硬过滤和逻辑记忆聚合，最后执行 RRF。

优点：

- 只依赖通道内 rank，不依赖不可比的原始 score；
- 可以在融合前统一执行 SQLite 回源和硬过滤；
- FTS5-only、Vector-only、双路和部分超时使用同一结果模型；
- 可记录每个分项、降级通道和确定性 tie-break，便于审查与评测；
- 不依赖尚无 E4 证据的原生 Hybrid/RRF。

缺点：

- Memory Service 需要维护去重、融合和诊断逻辑；
- 两路候选需要进入应用进程，增加有限的 CPU 与内存开销；
- Top-N、Top-K 和 `k` 的选择仍需开发集与性能证据校准。

### 方案 C：归一化后线性混合原始 score

对 BM25 与 Vector 原始 score 归一化后加权求和。

优点：

- 理论上可表达不同通道的相关性强弱；
- 权重可通过训练或开发集调优。

缺点：

- 当前 Vector score 语义未验证；
- 归一化范围会随查询、语料和版本变化；
- 在没有稳定数据集与校准证据时容易产生不可解释的排序漂移。

### 方案 D：D3 不选择，推迟到实现阶段

优点是避免提前承诺；缺点是 D4 无法据此建立稳定 Provider 与候选契约，
也无法对单路降级、错误和评测做一致测试。

## 决策

选择方案 B：`rrf-v1` 默认由 Memory Service 在应用层执行。

### 输入边界

RRF 只消费已通过以下处理的 `RetrievalHit`：

1. Provider 响应结构校验；
2. `rank > 0` 校验；
3. 同一通道仅按精确 `(memory_id, version_id)` 去重，每个精确版本只保留
   最佳 rank；
4. 按 `(memory_id, version_id)` 回源 SQLite；
5. 校验用户归属、当前版本、状态、有效期、敏感度、冲突和遗忘策略，并移除
   过期版本与其他非法命中；
6. 对仍合法的命中按 `memory_id` 聚合，每个通道保留最佳合法 rank；
7. 仅以聚合后的合法候选执行 RRF。

禁止先按 `memory_id` 选择最佳 rank 再校验版本。例如旧版本 `v1` 为 rank 1、
当前版本 `v2` 为 rank 2 时，必须移除 `v1` 并保留 `v2`；不得因 `v1` 先胜出而
把整个 `memory_id` 丢弃。

任何未通过硬过滤的命中不得进入融合分母、通道计数或 tie-break。

### `rrf-v1` 公式

对候选 `d` 与实际成功并命中该候选的通道集合 `C(d)`：

```text
rrf_score(d) = Σ 1 / (k + rank_c(d)),  c ∈ C(d)
```

冻结规则：

- `rank` 从 1 开始；
- 默认 `k = 60`；`k` 必须是正整数，并随请求诊断和评测结果记录；
- FTS5 与 Vector 在 `rrf-v1` 中固定等权；
- 未命中的通道不贡献分数，不补零 rank 或虚拟 rank；
- 每通道每个 `memory_id` 最多贡献一次；
- `raw_score` 与 `score_semantics` 仅用于诊断，不参与公式；
- 非单位通道权重属于新的算法行为，必须变更决策版本并补评测证据，
  不能在 `rrf-v1` 下静默启用。

`k` 的非默认配置必须进入版本化配置、日志和评测记录；未经 Recall@K、
MRR、nDCG 与 P95 对照，不得替换产品默认值 60。

### 确定性排序

候选按以下键稳定排序：

1. `final_score` 降序；
2. 命中通道数降序；
3. 最佳单路 rank 升序；
4. `memory_id` 按 UTF-8/ASCII 稳定字典序升序。

D3 v1 中若没有经过批准的业务重排，`final_score = rrf_score`。未来增加
时间、显式程度、可信度或类型配额时，必须使用新的重排版本，并在
`explanation` 中记录因子、方向和前后分数。

### 单路与故障行为

| 场景 | `rrf-v1` 行为 | 必须记录 |
|---|---|---|
| FTS5、Vector 均成功 | 双路融合 | 两路耗时、有效候选数、`k`、分项 |
| Vector/Embedding 失败或超时 | 使用已完成硬过滤的 FTS5 命中 | `degraded_channels=["vector"]`、结构化错误 |
| FTS5 失败或超时 | Vector 命中回源 SQLite 后执行单路 RRF | `degraded_channels=["fts5"]`、结构化错误 |
| 某通道返回非法 rank | 丢弃非法命中，不中断其他合法候选 | Provider、`memory_id`、校验错误 |
| deadline 耗尽 | 只返回 deadline 前完成并通过硬过滤的候选，或结构化空结果 | `partial=true`、完成阶段与耗时 |
| 两路均失败 | 返回空候选和结构化降级原因 | 不得生成固定或缓存伪候选 |

单路 RRF 分数不能与不同 `k`、不同算法版本或不同通道集合的历史请求
直接当作绝对相关度比较。

## Golden cases

以下样例固定 `k = 60`，供 D4 契约测试复算：

| 候选 | FTS5 rank | Vector rank | 预期 `rrf_score` | 说明 |
|---|---:|---:|---:|---|
| `mem-a` | 1 | 3 | `0.0322664585` | `1/61 + 1/63` |
| `mem-b` | 2 | 2 | `0.0322580645` | `1/62 + 1/62` |
| `mem-c` | 1 | — | `0.0163934426` | FTS5 单路 |
| `mem-d` | — | 1 | `0.0163934426` | Vector 单路 |

因此 `mem-a` 排在 `mem-b` 之前；`mem-c` 与 `mem-d` 分数及通道数、最佳
rank 相同，若无其他候选字段参与，应按 `memory_id` 稳定排序。

必须另测：

- 同通道精确 `(memory_id, version_id)` 重复项只使用最佳 rank，版本过滤后再按
  `memory_id` 聚合；
- 非正 rank 被拒绝；
- 输入顺序打乱不改变输出顺序；
- 跨用户、陈旧版本、已遗忘和未解决冲突命中在融合前消失；
- FTS5-only、Vector-only、部分超时和双路失败；
- 不同 `k` 的结果被记录为不同配置，不能静默混用。

## 影响

### 架构影响

- Provider 只需返回统一 `RetrievalHit`，不承担跨通道分数归一化；
- Memory Service 负责 SQLite 回源、硬过滤、聚合、RRF 和解释信息；
- `RetrievalCandidate` 必须保存通道 rank 与 RRF 分项，不能只保存最终分；
- IPC 是否暴露全部诊断字段由 D/C 契约决定，服务端必须保留可审计信息。

### 开发影响

- D4 需要建立 RRF 纯函数、精确版本去重、过滤后逻辑记忆聚合、确定性排序和
  单路降级测试；其中必须覆盖“旧 `v1` rank 1、当前 `v2` rank 2，最终保留
  `v2`”的组合场景；
- 不得把 Vector SDK `RRFRanker` 作为默认实现的隐藏依赖；
- 原始 score 语义确认后仍只能用于诊断或经新 ADR 批准的重排，不自动改变
  `rrf-v1`。

### 评测影响

- 开发集必须分别报告 FTS5-only、Vector-only 与 `rrf-v1` 的 Recall@K、
  MRR、nDCG 和 P95；
- 调整 `k`、通道权重、Top-N/Top-K 或业务重排必须记录配置和数据集版本；
- 单个手工样例不能作为参数优于其他方案的证据。

### 安全影响

- 硬过滤发生在融合前；用户隔离、敏感度、遗忘和版本检查不能降级为排序因素；
- 日志只记录用户哈希、ID、rank、计数、耗时和结构化原因，不记录未脱敏正文。

## 回滚与替代条件

本 ADR 可被新 ADR 替代，但不得在同一 `rrf-v1` 标识下静默改变算法。

考虑切换到原生 Hybrid/RRF 至少需要：

1. 目标麒麟版本、客户端和服务端组合取得 E4 宿主成功证据；
2. 证明用户/版本/安全过滤顺序与本契约等价；
3. 证明 deadline、取消、部分失败和确定性 tie-break 可表达；
4. 在固定数据集上与应用层 RRF 对比 Recall@K、MRR、nDCG 和 P95；
5. 一名独立、非作者 Reviewer 给出 `APPROVED`，以满足 GitHub PR 的人工
   审批数量门槛；该 approval 本身不等价于 Day3-B Gate 完成；
6. 适用的实现、评测与安全 Gate 均有可核验证据，并在 Review 记录中覆盖项目
   任务卡指定的 D 可实现性与 E 隔离/遗忘/安全/评测关注项；
7. 使用新的算法版本并保留回退到 `rrf-v1` 的配置开关。

若应用层实现出现问题，回滚方式是禁用双路融合并按结构化降级策略返回
经过硬过滤的单路候选，而不是启用未经验证的原生 Hybrid/RRF。

## 证据与限制

- `evidence/index.yaml`：`D1-B-02` 原生 Hybrid/RRF 为
  `ABI_VERIFIED / E3 / runtime_result=UNTESTED`；
- `evidence/index.yaml`：`VECTOR-CALL-003` 记录 D2-B 指定提交的 Vector
  数据面 E4 宿主结果；该条目的 Review 字段是历史状态，不用于推导本 ADR
  已经通过 D3 审查；
- `evidence/l2-kylin-vm/d2-vector-smoke-evidence-20260802c1.md`：用户过滤、
  CRUD、重启持久化和原始 score 语义限制；
- `docs/architecture/d1-b-retrieval-candidate-rrf-draft.md`：D1 方案输入；
- `docs/architecture/d2-retrieval-candidate-unified.md`：D2 统一字段样例。

本 ADR 为文档/契约决策，不新增 Runtime 事实。本轮未启动虚拟机；状态从
“提议”改为“已采纳”要求一名独立、非作者 Reviewer 给出 `APPROVED`，并且
P0 问题、适用验证和证据门槛均已关闭。该 approval 只满足 GitHub PR 的人工
审批数量门槛；项目任务卡指定的 D 可实现性与 E 隔离/遗忘/安全/评测关注项须在
Review 记录中明确覆盖。本 ADR 不修改项目任务卡或共享治理文档，也不将单一
approval 自动表述为 Day3-B Gate PASS。
