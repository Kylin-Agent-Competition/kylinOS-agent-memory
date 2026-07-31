# D1-B-03 应用层 RetrievalCandidate 与 RRF 默认方案草案

- **状态**：D1 调查草案，待 D 主审；不是冻结契约
- **日期**：2026-07-31
- **责任轨道**：B（Vector、FTS5、RRF 与检索评测）
- **适用阶段**：D1 方案起草；D3 冻结；D4 以后实现

## 1. 目的与边界

本草案定义 FTS5 与 Vector 两路召回进入 Memory Service 后的统一候选
表示，以及默认的应用层 Reciprocal Rank Fusion（RRF）流程。它用于：

1. 隔离 SQLite FTS5、Vector SDK 和未来可选 Provider 的返回结构；
2. 让融合只依赖稳定排名，不直接比较 BM25 距离与向量相似度；
3. 保留每一路命中、排名、降级和过滤原因，支持检索解释与评测；
4. 在 Vector 不可用时保留 FTS5/结构化检索降级路径。

本节点只形成结构草案和决策输入，不新增生产 Schema、Provider 或检索
实现。字段是否必填、枚举值、默认参数和 IPC 暴露范围必须在 D3 经过
契约审查后冻结。

## 2. 已知事实与约束

1. SQLite 是结构化记忆真源，Vector 只是可重建语义索引。
2. 召回前必须按 `user_id`、场景、作用域、状态、当前版本、有效期和
   敏感等级执行结构化过滤。
3. FTS5/BM25 负责工具名、命令、路径、错误码和专有名词等精确召回；
   Vector Search 负责自然语言语义召回。
4. 官方原生 `HybridSearch/RRFRanker` 当前最高只有
   `ABI_VERIFIED / E3`，没有宿主成功运行的 E4 证据。
5. 当前 Vector Engine 数据面在 `ShowCollections` 返回 RPC `1002`，
   因此默认产品路径不得依赖原生 Hybrid/RRF。
6. 总检索目标延迟不超过 500 ms；融合与上下文组装候选预算不超过
   80 ms，超时时应返回可解释的部分结果或空上下文，不阻塞聊天。

## 3. 两层候选模型

为避免把 Provider 私有分数泄漏到业务层，草案区分单路命中
`RetrievalHit` 与融合结果 `RetrievalCandidate`。

### 3.1 RetrievalHit

`RetrievalHit` 是某一路召回列表中的一次命中。建议字段如下：

| 字段 | 建议类型 | 含义与约束 |
|---|---|---|
| `memory_id` | string | 记忆稳定身份；非空 |
| `version_id` | string | 本次命中的版本；必须是当前允许注入的版本 |
| `channel` | enum | `fts5` 或 `vector`；未来新增值需经过契约审查 |
| `rank` | integer | 单路列表中的 1 起始排名；必须大于 0 |
| `raw_score` | number/null | Provider 原始分数，仅诊断；不跨通道直接比较 |
| `provider` | string | 产生命中的具体实现，例如 `sqlite_fts5` |
| `retrieved_at` | datetime | 本次命中时间，统一为 UTC |

同一通道若重复返回相同 `memory_id`，只保留最佳 `rank`；重复项必须
计入诊断，不得重复增加 RRF 分数。

### 3.2 RetrievalCandidate

`RetrievalCandidate` 是按 `memory_id` 聚合、经安全与版本检查后可进入
重排和 Context 预算阶段的统一候选。

| 字段 | 建议类型 | 含义与约束 |
|---|---|---|
| `memory_id` | string | 去重主键；稳定身份 |
| `version_id` | string | 当前有效版本；过期或被替代版本不得注入 |
| `memory_type` | enum | 至少区分 `preference`、`knowledge`；D3 冻结 |
| `user_id` | string | 必须与请求用户完全一致，不允许跨用户融合 |
| `scene` | string/null | 场景标识；用于过滤和解释 |
| `scope` | object | 应用、会话、项目等作用域；结构由 E/D 轨道共同冻结 |
| `content` | string | 来自 SQLite 当前版本的可注入正文或安全摘要 |
| `channels` | list | 实际命中的通道集合；按固定顺序输出 |
| `ranks` | map | 通道到 1 起始排名，例如 `{"fts5": 2, "vector": 5}` |
| `raw_scores` | map | 通道原始分数；只供诊断，不参与默认 RRF |
| `rrf_score` | number | 应用层 RRF 基础融合分 |
| `final_score` | number | 后续可解释重排结果；D1 可与 `rrf_score` 相同 |
| `confidence` | number/null | 记忆本身的业务置信度，不等于检索相关度 |
| `evidence_count` | integer/null | 支持证据数量；非负 |
| `status` | string | 必须是允许检索输出的有效状态 |
| `conflict_state` | string | 未解决冲突默认排除或明确标记不确定 |
| `valid_from` | datetime/null | 生效时间 |
| `valid_to` | datetime/null | 失效时间 |
| `sensitivity` | string | 检索输出安全边界使用 |
| `estimated_tokens` | integer | Context 预算估算；非负 |
| `explanation` | object | 命中通道、RRF 分项、过滤/加权原因和降级信息 |

`content`、业务字段与版本状态必须回源 SQLite，不能把 Vector 元数据当成
最终真源。Vector 命中但 SQLite 中不存在、用户不一致、版本过期或已
遗忘的记录应丢弃并记录 `stale_index` 诊断。

### 3.3 非冻结 JSON 示例

```json
{
  "memory_id": "mem_01J...",
  "version_id": "ver_01J...",
  "memory_type": "knowledge",
  "user_id": "local-user",
  "scene": "software_development",
  "scope": {
    "project": "kylin-os-agent-memory"
  },
  "content": "Vector Runtime 结果必须来自麒麟宿主证据。",
  "channels": ["fts5", "vector"],
  "ranks": {
    "fts5": 2,
    "vector": 5
  },
  "raw_scores": {
    "fts5": -8.42,
    "vector": 0.81
  },
  "rrf_score": 0.0315136,
  "final_score": 0.0315136,
  "confidence": 0.94,
  "evidence_count": 3,
  "status": "active",
  "conflict_state": "none",
  "valid_from": "2026-07-30T16:00:00Z",
  "valid_to": null,
  "sensitivity": "normal",
  "estimated_tokens": 18,
  "explanation": {
    "rrf_k": 60,
    "rrf_terms": {
      "fts5": 0.0161290,
      "vector": 0.0153846
    },
    "degraded_channels": []
  }
}
```

示例仅展示候选形状，不代表 D3 已批准字段、枚举或精度。

## 4. 默认应用层 RRF

### 4.1 基础公式

对候选 `d` 和可用召回通道集合 `C`：

```text
RRF(d) = Σ 1 / (k + rank_c(d)),  c ∈ C 且 d 在 c 中出现
```

D1 候选参数：

- `rank` 从 1 开始；
- `k = 60`，仅作为 D1/D2 实验默认值，D3 冻结前可调整；
- FTS5 与 Vector 默认等权；
- 未命中的通道不加分，不补零排名；
- 每通道每个 `memory_id` 最多贡献一次。

采用 RRF 的原因是 BM25 与向量相似度的方向、范围和标定方式不同。
默认融合只使用名次，避免未经数据集验证的分数归一化。

### 4.2 确定性排序

候选按以下顺序稳定排序：

1. `final_score` 降序；
2. 命中通道数降序；
3. 最佳单路 `rank` 升序；
4. `memory_id` 字典序升序。

最后一项只用于保证相同输入得到稳定结果，不表达业务优先级。

### 4.3 可解释业务重排边界

应用层 RRF 先解决多路相关性融合。以下业务因素可以在 RRF 后参与
可解释重排，但 D1 不硬编码权重：

- 作用域匹配；
- 当前版本与有效期；
- 显式程度、证据和可信度；
- 时间新鲜度；
- 重复惩罚；
- 冲突状态；
- 记忆类型配额与 Token 预算。

用户隔离、敏感等级、已遗忘状态、无效版本和未解决冲突属于硬过滤，
不能仅靠降低分数处理。任何后续加权都必须在 `explanation` 中记录
因子、方向和结果，并由 D3 契约与评测数据批准。

## 5. 默认处理流程

```text
MemoryQuery
  -> 结构化/安全过滤条件
  -> FTS5 Top-N ------------------+
  -> Query Embedding -> Vector Top-N
                                  |
  -> 单路 RetrievalHit 校验与去重
  -> 按 memory_id 聚合
  -> SQLite 回源当前版本与正文
  -> 硬过滤：用户/状态/有效期/敏感/冲突
  -> 应用层 RRF
  -> 可解释业务重排
  -> 类型配额、Top-K 与 Token 预算
  -> Memory Context
```

建议 FTS5 与 Vector 并发执行，但共享请求 deadline。实现不得为了等待
故障通道而越过总体 deadline。

## 6. 降级与异常语义

| 场景 | 默认行为 | 必须记录 |
|---|---|---|
| 两路成功 | 执行双路 RRF | 通道耗时、候选数、RRF 参数 |
| Vector 不可用/超时 | 返回 FTS5 单路候选 | `degraded_channels=["vector"]` 和错误类别 |
| Embedding 不可用 | 跳过 Vector，保留结构化/FTS5 | Provider 状态与 deadline |
| FTS5 不可用 | 可返回 Vector 单路候选，但仍需 SQLite 回源 | `degraded_channels=["fts5"]` |
| 某通道返回非法 rank | 丢弃非法命中，不让整个请求崩溃 | Provider、memory_id、校验错误 |
| Vector 命中陈旧索引 | 丢弃并安排索引修复/重建 | `stale_index` 计数 |
| 两路均失败 | 返回空候选和结构化降级原因 | 不能伪造固定候选 |
| deadline 耗尽 | 返回已完成且通过安全检查的部分结果，或空结果 | `partial=true`、阶段耗时 |

原始 Provider 异常不得直接穿透为 SDK 内部类型；D3 应统一为结构化
`ProviderError`/检索错误码。

## 7. 可观测性与评测要求

每次检索至少应具备以下不含敏感正文的诊断字段：

- `request_id`、`trace_id`、`user_id_hash`；
- 各通道状态、耗时、原始候选数和有效候选数；
- 去重数、陈旧索引数、硬过滤计数；
- `rrf_k`、通道权重（默认均为 1）和最终 Top-K；
- 是否降级、部分返回或触发 deadline；
- Context 使用 token 数和截断数。

D2/D3 至少验证：

1. RRF 公式、1 起始排名和确定性 tie-break；
2. 单路重复命中只计最佳排名；
3. FTS5-only、Vector-only、双路和双路失败；
4. 跨用户、过期、已遗忘、旧版本和冲突候选被硬过滤；
5. Vector 陈旧索引不成为正文真源；
6. 相同输入重复执行结果稳定；
7. 开发集上比较 FTS5-only、Vector-only 与 RRF 的 Recall@K、MRR、
   nDCG 和 P95，不以单个示例决定参数。

## 8. D3 待冻结问题

以下内容保持开放，不能在 D1 写成最终契约：

1. `memory_type`、`status`、`conflict_state` 和 `sensitivity` 的枚举；
2. `scope` 的公共字段及跨轨道所有权；
3. FTS5/Vector 各自 Top-N、最终 Top-K 和类型配额；
4. `k=60` 是否保留，以及是否允许带权 RRF；
5. 时间、可信度、显式程度等后重排因素的形式和参数；
6. `RetrievalCandidate` 哪些字段进入 IPC，哪些只留服务端诊断；
7. Token 估算器、正文/摘要选择和截断策略；
8. 部分结果与错误码的协议表示。

## 9. 与后续任务的衔接

- **D2-B**：在 Vector 数据面解除阻塞后补真实 Insert/Search/Filter/Delete
  与持久化证据，并建立 FTS5/Vector 统一候选样例。
- **D3-B**：冻结 `VectorProvider`、`RetrievalCandidate`、`IndexState`
  契约，确认应用层 RRF 默认实现并形成 ADR。
- **D4-B**：按冻结契约建立 Provider、Collection Schema、候选模型和
  CRUD/Filter 契约测试。
- **D9-B**：实现真实 FTS5 + Vector + RRF，运行 Recall/MRR/nDCG/P95。

## 10. 参考基线

- `02_麒麟OS_Agent记忆系统_总体架构_团队分工与标准开发SOP_v1.1_20260729.docx`
  第 9 章“检索、重排与上下文组装”
- `evidence/l2-kylin-vm/d1-b-vector-engine-boundary-20260730.md`
- `evidence/l2-kylin-vm/d1-b-native-hybrid-rrf-evidence-20260731.md`
