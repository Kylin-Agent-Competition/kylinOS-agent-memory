# D2 FTS5 / Vector 统一候选字段样例

- 状态：D2 实验样例，已结合真实 Vector 用户过滤验证
- 日期：2026-07-31
- 适用范围：D2 及之前
- 非目标：不冻结 D3 契约、Provider、IPC、错误码或 RRF 参数

## 1. 目的

FTS5 与 Vector 的原始分数方向、范围和语义不同。D2 先统一两路
召回进入应用层时的最小字段形状，使后续代码可以：

1. 在融合前执行相同的用户、版本、状态与作用域检查；
2. 保留通道自己的 rank 和原始分数，不跨通道直接比较；
3. 按 `memory_id` 聚合命中，同时回源 SQLite 当前版本；
4. 记录降级、陈旧索引和过滤原因；
5. 为 D3 契约评审提供已验证输入，而不是提前冻结接口。

## 2. 强制不变量

### 2.1 用户过滤先于融合

每一路召回都必须带入请求的 `user_id` 硬过滤条件。任何
`candidate.user_id != request.user_id` 的命中必须在合并、RRF、
重排和 Context 组装之前丢弃，不能仅降分。

D2 Vector 实测使用一个与查询向量完全相同、但属于另一用户的
诱饵记录 id 201。过滤后它没有进入结果，证明目标版本组合支持
在 Vector 数据面执行该硬边界。

### 2.2 SQLite 仍是真源

Vector 中的 `content` 或元数据只能帮助召回和诊断。候选进入融合前
必须按 `memory_id + version_id` 回源 SQLite，并确认：

- 记录存在且属于请求用户；
- 命中版本仍是当前允许版本；
- 状态、有效期、敏感等级和冲突状态允许输出；
- 正文来自 SQLite 当前版本，而不是陈旧 Vector 元数据。

### 2.3 原始分数不跨通道比较

- FTS5/BM25 的原始值保留为诊断字段；
- Vector COSINE 相似度或距离保留为诊断字段；
- 默认融合只消费各通道 1 起始 `rank`；
- D2 不决定分数归一化、权重或最终 RRF 参数。

## 3. 单路命中 `RetrievalHitSample`

| 字段 | D2 样例类型 | 约束 |
|---|---|---|
| `memory_id` | string | 稳定记忆 ID，非空 |
| `version_id` | string | 命中索引版本；融合前须回源确认 |
| `user_id` | string | 必须与请求用户完全相同 |
| `channel` | string | D2 仅为 `fts5` 或 `vector` |
| `rank` | integer | 通道内 1 起始排名 |
| `raw_score` | number/null | 仅诊断，不跨通道直接比较 |
| `score_semantics` | string | 例如 `bm25`、`sdk_score_unverified`；未验证前不得宣称相似度或距离语义 |
| `provider` | string | 例如 `sqlite_fts5`、`kylin_vector_0k0.7` |
| `retrieved_at` | UTC datetime | 本次命中时间 |
| `filter_context` | object | 本次请求使用的用户/场景/作用域条件 |
| `diagnostics` | object | 超时、陈旧索引、降级等非正文信息 |

`filter_context` 记录条件，不作为新的权限真源；真正的授权与当前版本
仍由 SQLite 回源检查决定。

## 4. 通道映射

| 统一字段 | FTS5 来源 | Vector 来源 |
|---|---|---|
| `memory_id` | FTS5 外部内容表稳定 ID | Vector 主键或主键映射 |
| `version_id` | FTS5 索引行关联版本 | Vector 元数据中的索引版本 |
| `user_id` | SQL `WHERE user_id = ?` | Search `user_id == "..."` 表达式 |
| `rank` | BM25 排序后的 1 起始位置 | Search 返回顺序的 1 起始位置 |
| `raw_score` | SQLite `bm25(...)` | COSINE 相似度或 SDK 返回距离 |
| `score_semantics` | `bm25` | `sdk_score_unverified` |
| `provider` | `sqlite_fts5` | `kylin_vector_0k0.7` |

实现必须使用参数绑定或受控表达式构造，不得把未经校验的用户输入
直接拼接为 SQL 或 Vector 过滤表达式。

`sdk_score_unverified` 仅表示保留当前固定 SDK/服务端组合返回的原始浮点值用于诊断；
D2 未完成该值究竟是 COSINE 相似度还是距离的独立验证，因此不据此跨通道比较、归一化
或冻结正式字段语义。

## 5. 聚合候选 `RetrievalCandidateSample`

单路命中通过硬过滤并按 `memory_id` 去重后，形成 D2 聚合样例：

| 字段 | D2 样例类型 | 约束 |
|---|---|---|
| `memory_id` | string | 聚合与去重主键 |
| `version_id` | string | SQLite 回源确认后的当前版本 |
| `user_id` | string | 与请求用户完全相同 |
| `content` | string | SQLite 当前版本正文或安全摘要 |
| `channels` | string[] | 固定顺序：`fts5`、`vector` |
| `ranks` | object | 通道到 1 起始 rank |
| `raw_scores` | object | 通道原始分数，仅诊断 |
| `rrf_score` | number/null | D2 可计算样例；D3 前不冻结 |
| `status` | string | 必须是允许检索输出的当前状态 |
| `filter_result` | object | 用户、版本、状态等硬检查结果 |
| `explanation` | object | 命中通道、分项及降级信息 |

## 6. JSON 样例

```json
{
  "memory_id": "mem-101",
  "version_id": "ver-3",
  "user_id": "user-alpha",
  "content": "来自 SQLite 当前版本的正文",
  "channels": ["fts5", "vector"],
  "ranks": {
    "fts5": 2,
    "vector": 1
  },
  "raw_scores": {
    "fts5": -7.42,
    "vector": 0.9998
  },
  "rrf_score": null,
  "status": "active",
  "filter_result": {
    "user": "pass",
    "current_version": "pass",
    "status": "pass"
  },
  "explanation": {
    "providers": ["sqlite_fts5", "kylin_vector_0k0.7"],
    "degraded_channels": [],
    "stale_index": false
  }
}
```

`null` 的 `rrf_score` 表示 D2 字段能够承载融合输出，但本文件不批准
具体公式参数或强制所有调用都执行融合。

## 7. 错误与降级样例

| 场景 | D2 行为 |
|---|---|
| Vector 不可用 | 保留通过硬检查的 FTS5 命中并标记降级 |
| FTS5 不可用 | Vector 命中仍须回源 SQLite 后才可输出 |
| 用户不匹配 | 立即丢弃，不进入候选集合 |
| 版本陈旧/已遗忘 | 丢弃并记录 `stale_index` |
| 两路均不可用 | 返回空候选与结构化原因，不伪造结果 |
| rank 非正数或重复 | 丢弃非法项；同通道同 ID 只保留最佳 rank |

## 8. D2 验证对应关系

- 探针：`tests/vector-engine/d2_vector_smoke.cpp`
- runner：`scripts/run_d2_vector_smoke.sh`
- 证据：
  `evidence/l2-kylin-vm/d2-vector-smoke-evidence-20260731.md`

真实数据面已验证 Insert、Query Filter、Vector Search Filter、Upsert、
Delete 和服务重启持久化。FTS5/Vector 的联合执行和 RRF 指标不在
D2 实测范围内。

## 9. 留给 D3 的决策

以下内容保持开放：

1. 字段正式名称、必填性和 IPC 可见性；
2. `memory_type`、`status`、`sensitivity` 等枚举；
3. `scope` 的公共结构和所有权；
4. RRF `k`、通道权重、Top-N/Top-K；
5. Provider 接口、统一错误码与超时契约；
6. 分数精度、序列化格式和向后兼容策略。
