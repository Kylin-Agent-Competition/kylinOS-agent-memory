# 08 轨道 B — Vector 检索与索引契约 v1

> **文档状态：D3-B 冻结候选** — PR #20 Review 返工中。取得一名独立、
> 非作者 Reviewer 的 `APPROVED` 且全部适用 Gate 关闭前，不得标记为最终
> `ACCEPTED`。该 approval 只满足 GitHub PR 的人工审批数量门槛；项目任务卡
> 指定的 D/E 专业关注项仍须在 Review 记录中明确覆盖，本契约不修改该治理分工。
>
> 本文冻结 Memory Service 内部的 B 轨技术语义，不冻结 D 轨 IPC 数字错误码、
> SQLite 表结构、Vector Collection 物理布局或 D4 生产实现。

- 契约标识：`vector-retrieval/v1`
- 日期：2026-08-03
- 责任轨道：B（Vector、FTS5、RRF 与检索评测）
- 人工审批门槛：一名独立、非作者 Reviewer 的 `APPROVED`
- 专业关注点：D 关注可实现性；E 关注用户隔离、遗忘、安全与评测
- 治理边界：单一 `APPROVED` 不自动等价为 Day3-B Gate PASS；P0、适用验证、
  证据和任务卡指定的专业关注项均须关闭或有明确阻断结论
- 关联决策：`docs/adr/001-application-layer-rrf.md`

## 1. 目标与边界

本契约为 D4 的 Provider、候选模型、索引状态机和 CRUD/Filter 契约测试
提供无歧义输入，冻结：

1. `VectorProvider` 的操作集合与语言无关签名；
2. `RetrievalHit` 与 `RetrievalCandidate` 的职责分层；
3. `IndexState` 的状态、代次、水位和可检索性语义；
4. 用户、场景与作用域的受控过滤边界；
5. Upsert、Delete、遗忘同步与 Rebuild 的幂等和失败语义；
6. Provider 错误、deadline、取消、部分结果和可观测性约束；
7. 应用层 `rrf-v1` 的接口衔接。

本文不实现以上接口，也不把文档样例、静态检查或 D2 探针表述为生产能力。

## 2. 证据状态词

本文使用以下状态，避免把设计决定与运行事实混淆：

| 状态 | 含义 |
|---|---|
| `FROZEN_CANDIDATE` | D3-B 已给出唯一语义，待 Reviewer 决定是否接受 |
| `HOST_VERIFIED / E4` | 已在目标麒麟宿主取得对应运行证据 |
| `ABI_VERIFIED / E3` | 只证明 ABI/符号存在，不证明目标调用成功 |
| `SOURCE_VERIFIED` | 仅由源码或静态结构确认 |
| `UNTESTED` | 契约已定义，但尚无对应运行测试 |
| `DEFERRED` | 明确留给其他轨道或后续阶段，当前不得自行补值 |

冻结是接口稳定性决定，不等于功能已实现或已通过 Runtime Test。

## 3. 已确认事实

| 事实 | 状态 | 约束影响 |
|---|---|---|
| SQLite 是正文、归属、当前版本、状态和遗忘结果的真源 | 架构基线 | Vector 命中必须回源；Vector 不保存最终授权真相 |
| Vector Collection、Insert、Query、Search、Upsert、Delete 可运行 | `HOST_VERIFIED / E4` | D4 可建立真实 Provider，但只能沿用已验证版本边界 |
| `user_id` 过滤可排除同向量跨用户诱饵 | `HOST_VERIFIED / E4` | `user_id` 必填、精确匹配、融合前硬过滤 |
| 重启后 Collection、CRUD 终态与过滤保持 | `HOST_VERIFIED / E4` | `IndexState` 必须含代次/水位，不能把进程存活当成索引就绪 |
| Vector 原始 score 可返回 | `HOST_VERIFIED / E4` | 只作通道内诊断；语义仍为 `sdk_score_unverified` |
| 原生 Hybrid/RRF ABI 存在 | `ABI_VERIFIED / E3` | 不得作为默认产品融合路径 |
| 原子 Collection 代次切换 | `UNTESTED` | Rebuild 契约不得假设原子 rename/swap 可用 |
| FTS5 + Vector + RRF 端到端与性能指标 | `UNTESTED` | D3 不声明 Recall/P95 达标 |

## 4. 分层与所有权

```text
MemoryQuery / policy
  -> typed RetrievalFilter（D/E 业务策略已解析）
  -> FTS5 Provider --------+
  -> Embedding -> VectorProvider.search
                            |
  -> RetrievalHit 校验、按精确 (memory_id, version_id) 通道内去重
  -> SQLite 回源：归属、当前版本、状态、正文/安全摘要
  -> 硬过滤：用户、场景/作用域、生命周期、敏感、冲突、遗忘
  -> 按 memory_id 聚合为 RetrievalCandidate
  -> rrf-v1
  -> 后续可解释重排 / Top-K / Token 预算
  -> MemoryContext
```

所有权规则：

- A 轨拥有 Embedding/Extraction Provider 和 Bridge 错误事实；
- B 轨拥有检索 Provider、候选、索引状态和 RRF 技术语义；
- C 轨拥有 Hook、`MemoryQuery`/`MemoryContext` 的宿主映射；
- D 轨拥有 IPC、SQLite、Outbox、部署与协议错误码映射；
- E 轨拥有业务枚举、安全、遗忘授权和正式评测口径。

B 轨不得用本契约覆盖 D/E 的待决业务语义。

## 5. 共同基础类型

### 5.1 标识与时间

| 字段 | 类型 | 约束 | 状态 |
|---|---|---|---|
| `contract_version` | string | 固定 `vector-retrieval/v1` | `FROZEN_CANDIDATE` |
| `request_id` | string | 非空；一次逻辑请求内稳定 | `FROZEN_CANDIDATE` |
| `trace_id` | string | 非空；跨 Provider/SQLite/IPC 关联 | `FROZEN_CANDIDATE` |
| `user_id` | string | 非空；来自宿主/业务输入；禁止模型生成 | 业务规则待 E 专业关注，技术必填已冻结 |
| `occurred_at` / `*_at` | UTC datetime | RFC 3339，序列化为 `Z` 或明确 offset | `FROZEN_CANDIDATE` |
| `deadline_at` | UTC datetime | 绝对 deadline，不允许每层重置相对预算 | `FROZEN_CANDIDATE` |
| `idempotency_key` | string | 写操作必填；由接入层/系统生成，禁止模型生成 | `FROZEN_CANDIDATE` |

ID 的 UUID 版本、数据库列型和 IPC 线格式由 D 冻结；B 只要求稳定、非空和
在相应作用域内唯一。

### 5.2 `IndexScope`

索引代次、水位和计数必须绑定显式作用域，不得依赖调用上下文猜测：

```text
IndexScope {
  scope_id: string
  kind: "global" | "user" | "shard"
  user_id: string | null
  shard_id: string | null
  scope_fingerprint: Digest
}
```

- `scope_id` 是由 Service 持久化的稳定内部身份；用于 generation、状态、
  watermark domain 和 Rebuild 幂等域。它不从 HMAC 派生，密钥轮换不得改变它；
- `global`：`user_id=null`、`shard_id=null`；只允许经授权的内部调用使用；
- `user`：`user_id` 必填、`shard_id=null`；代次、水位和全部计数只描述该用户；
- `shard`：`shard_id` 必填、`user_id=null`；代次、水位和全部计数只描述该
  确定性分片；
- `scope_fingerprint` 是由规范化后的 `kind`、`user_id`、`shard_id` 计算的可
  轮换 HMAC 披露值，只用于日志、诊断和最小披露；不得作为持久化主键、比较键
  或授权依据。密钥轮换时 Service 重算该值，但保持 `scope_id` 不变；
- 作用域之间的代次、水位和计数以 `scope_id` 隔离，禁止比较、继承或合并；
- 从较窄作用域扩大为较宽作用域必须创建新请求并重新授权，不得在 Provider
  内静默提升。

```text
ScopeAuthorization {
  actor_ref: string
  authorization_ref: string
  scope_id: string
  allowed_operations: non-empty subset(get_index_state, rebuild)
  expires_at: UTC datetime
}
```

Service 在调用 Provider 前负责身份认证、用户关系/委托与 global/shard scope
授权；D/E 冻结具体认证与 RBAC Schema。`actor_ref` 和 `authorization_ref` 必须
进入审计链，且 `scope_id` 必须等于请求 `IndexScope.scope_id`。

授权判定可由不可变授权记录或可解析的 `authorization_ref` 承载，但解析结果必须
同时绑定 `actor_ref`、`scope_id`、`allowed_operations` 与 `expires_at`。Service 在
每次调用 Provider 前按以下顺序校验：请求操作在 `allowed_operations` 中、请求
scope 与绑定 scope 精确相等、当前时间严格早于 `expires_at`，以及 actor 对该
scope 的关系/委托仍满足授权记录。`get_index_state` 只读授权不得用于 `rebuild`，
反之亦然。任何字段缺失、绑定不一致、越权或已过期均不得调用 Provider；分别
返回 `authorization_denied`、`authorization_expired` 或适用的
`user_scope_violation`/`invalid_argument`。

Provider 只接受来自 Service 的内部调用，并校验已经解析的授权上下文仍与 actor、
scope、操作和有效期绑定；不得根据 scope 自行推断或提升权限，也不得把一次
`get_index_state` 授权复用于 Rebuild。

### 5.3 `ProviderResult<T>`

所有预期内 Provider 失败使用结构化返回，不向业务层泄漏 SDK RPC、C++
异常或实现私有类型：

```text
ProviderResult<T> {
  ok: boolean
  value: T | null
  error: RetrievalError | null
  partial: boolean
  provider: string
  request_id: string
  elapsed_ms: integer
  completed_at: UTC datetime
}
```

约束：

- `ok=true` 时 `value` 必填、`error=null`；
- `ok=false` 时 `value=null`，除非具体操作明确允许 `partial=true` 且定义
  部分值类型；
- `partial=true` 不能隐藏错误，必须同时记录未完成阶段/通道；
- `elapsed_ms >= 0`；
- Provider 不在内部静默无限重试；重试由 Service 按错误可重试性和同一
  deadline 决定。

### 5.4 `RetrievalError`

字符串错误码是 B 层稳定语义；D 可映射为 IPC 数字码，但不得改变含义。

| `code` | 含义 | 默认可重试性 | 是否允许降级 |
|---|---|---|---|
| `invalid_argument` | 字段缺失、类型错误、rank/top_n 非法 | 否 | 否 |
| `dimension_mismatch` | 向量维度与 Provider 能力不一致 | 状态变化后 | Search 可降级为 FTS5 |
| `user_scope_violation` | 缺失用户、跨用户或越权作用域 | 否 | 否，必须拒绝 |
| `authorization_denied` | actor、scope 或允许操作缺失、不匹配或不被授权 | 否 | 否，调用 Provider 前拒绝 |
| `authorization_expired` | 授权在本次调用前已过期 | 获取新授权后 | 否，调用 Provider 前拒绝 |
| `digest_key_unavailable` | 需要验证的历史摘要密钥已不可用 | 受控人工/服务端恢复后 | 否，禁止重放或确认副作用 |
| `deadline_exceeded` | 绝对 deadline 已耗尽 | 新请求可重试 | 可返回已安全完成的部分结果 |
| `cancelled` | 调用方取消 | 新请求可重试 | 可返回取消前已安全完成的只读结果 |
| `provider_unavailable` | SDK/服务/连接不可用 | 是，退避且不越过 deadline | Search 可单路降级 |
| `provider_not_ready` | 模型或索引尚未就绪 | 状态变化后 | Search 可单路降级 |
| `provider_protocol_error` | 返回结构、rank、非有限数等违反契约 | 视情况 | 丢弃非法项或通道降级 |
| `stale_index` | 索引代次/版本/水位陈旧 | 状态变化后 | 丢弃陈旧项并安排修复 |
| `conflict` | 幂等键、预期代次或资源所有权冲突 | 状态变化后 | 否 |
| `internal` | 未分类实现错误 | 受控退避 | Search 可单路降级，不得伪造结果 |

`RetrievalError` 至少包含 `code`、安全可展示的 `message`、`retryable`、
`stage`、`provider`、`details`。`details` 不得含未脱敏正文、SDK 堆栈、数据库
凭据或跨用户数据。

### 5.5 Deadline 与取消

1. 请求进入 Memory Service 时生成绝对 `deadline_at`；各层只消费剩余预算；
2. Provider 开始新副作用前必须再次检查 deadline 和取消状态；
3. Search 在 deadline/取消前完成并通过硬过滤的候选可以标为部分结果；
4. Upsert/Delete/Rebuild 不能把“客户端已超时”自动表述为“底层未执行”；
5. 若 SDK 调用无法主动中断，结果必须标为 `outcome_unknown`，随后通过
   `idempotency_key`、源水位和索引代次协调，禁止盲目重复副作用；
6. 取消信号是协作式，不承诺强杀 SDK 线程或进程。

### 5.6 规范摘要、幂等域与水位

#### 5.6.1 `canonical-json/v1` 与 `Digest`

`filter_fingerprint`、`index_text_hash`、`selection_hash` 和 `payload_hash` 使用
同一规范输入规则：

1. 字符串先规范为 Unicode NFC；时间统一为 RFC 3339 UTC `Z`；缺失字段与
   显式 `null` 不等价；
2. 对象按 RFC 8785 JSON Canonicalization Scheme 序列化；map 键按规范排序；
3. Schema 标注为集合语义的数组先去重，再按元素规范 JSON 的 UTF-8 字节序
   排序；顺序有业务含义的数组保持原顺序；
4. 禁止浮点 `NaN`、正负无穷和负零；摘要输入必须先通过对应 Schema 校验；
5. 摘要格式固定为 `hmac-sha256:<key_id>:<64 lowercase hex>`。使用部署密钥的
   HMAC-SHA-256，避免低熵过滤器、ID 集或正文哈希被离线枚举；日志不得记录
   规范输入、密钥或未经脱敏值。

`Digest` 比较要求算法和 `key_id` 相同；Provider 不得把不同 `key_id` 的值推断为
相等。

##### 摘要密钥轮换

Service 维护活动摘要密钥与仅验证历史密钥。旧密钥从切换为仅验证起至少保留至
`max(idempotency_record_retention, confirmation_ttl)` 结束；相应幂等记录和
删除确认记录必须保存产生其摘要的 `key_id`，且确认 TTL 不得晚于该密钥的仅验证
保留期。密钥轮换不改变摘要的规范输入规则，也不允许 Provider 自行选择密钥。

- 幂等重放先按 §5.6.2 复合域定位已有记录；若记录使用历史 `key_id`，Service
  用该记录的仅验证密钥重算请求语义字段并比较。相同则返回已记录结果，不同则
  返回 `conflict`；不得因活动密钥已变更把同一请求当作新副作用。
- 删除的 `selection_hash`、`preview_hash` 与确认引用按其记录的 `key_id` 验证。
  密钥不可用或确认超过 TTL 时返回 `digest_key_unavailable` 或适用的过期错误，
  不执行 Delete；不得静默接受、降级比较或改用活动密钥确认。
- `index_text_hash` 轮换由受控重建完成：从 SQLite 真源重新计算新 key 的摘要，
  将目标 generation 标为 `building`，完整校验后再激活。一个 serving generation
  不得混用不同 `key_id` 的 `index_text_hash`；密钥轮换本身不得改变 `scope_id`、
  水位域或既有幂等域。
- 需要验证的历史密钥已按保留策略销毁时，Service 必须安全失败并记录可审计原因；
  只有在原操作结果已确定后，才可由受控恢复流程建立新的幂等或确认事实。

#### 5.6.2 写操作幂等域

幂等记录的唯一键不是裸 `idempotency_key`，而是以下复合域：

```text
(principal_scope, operation, provider, target_generation, idempotency_key)
```

- `principal_scope` 对 Upsert/Delete 为请求 `user_id`，对 Rebuild 为稳定的
  `scope.scope_id`；
- `operation` 为 `upsert`、`delete` 或 `rebuild`，`target_generation` 对前两者
  为 `index_generation`、对 Rebuild 为 `target_generation`；
- 所有写请求必须携带按 `canonical-json/v1` 计算的 `payload_hash`，且 Provider
  必须从语义字段复算；`request_id`、`trace_id`、`deadline_at`、重试次数等易变
  传输字段以及 `payload_hash` 自身不进入载荷，业务字段、作用域、选择器、
  目标代次和源水位必须进入；
- 同一复合域且 `payload_hash` 相同返回首次逻辑结果；同域不同 hash 返回
  `conflict`；相同裸 key 在不同用户、操作、Provider 或代次中互不冲突。

#### 5.6.3 `Watermark`

```text
Watermark {
  domain: {
    scope_id: string
    stream: string
    partition: string
    source_generation: string
  }
  kind: "monotonic_int" | "fixed_width_lex"
  value: integer | string
}
```

- 仅当 `domain` 四个字段与 `kind` 完全相同才允许比较；跨用户/作用域、流、
  分区或源代次比较必须返回 `invalid_argument`，不得据此判新旧；
- `monotonic_int` 使用非负整数数值比较；`fixed_width_lex` 要求同一 domain 下
  长度固定的 ASCII 字符串，按无符号字节序比较；不得把数字字符串按整数猜测；
- 相等表示安全重放；较大值可推进；较小值确定性返回 `stale_index`，且不得
  改写数据或已应用水位；
- `applied_watermark`、`required_watermark` 和 `source_watermark` 均使用该
  结构，禁止裸字符串/整数跨域比较。

## 6. `VectorProvider` 接口

### 6.1 语言无关签名

```text
interface VectorProvider {
  capabilities() -> VectorCapabilities
  upsert(VectorUpsertRequest) -> ProviderResult<VectorUpsertResult>
  search(VectorSearchRequest) -> ProviderResult<VectorSearchResult>
  delete(VectorDeleteRequest) -> ProviderResult<VectorDeleteResult>
  rebuild(VectorRebuildRequest) -> ProviderResult<VectorRebuildResult>
  get_index_state(IndexStateRequest) -> ProviderResult<IndexState>
}
```

接口是否以 Python 同步、异步或进程池形式实现属于 D4；D3 冻结操作语义、
输入输出和 deadline，不冻结语言运行时调度方式。

### 6.2 `VectorCapabilities`

| 字段 | 类型 | 约束 |
|---|---|---|
| `provider` | string | 实现稳定名，例如 `kylin_vector_0k0.7` |
| `provider_version` | string | 实际客户端/适配器版本 |
| `dimension` | integer | 正整数；当前目标模型宿主证据为 768，但不得硬编码成所有实现通用值 |
| `score_semantics` | enum | 当前目标组合固定报告 `sdk_score_unverified` |
| `supports_scalar_filter` | boolean | 当前目标组合有 E4 用户过滤证据 |
| `supports_delete` | boolean | 当前目标组合有 E4 证据 |
| `supports_rebuild` | boolean | 表示适配器具备受控重建流程，不等于原子 swap |
| `supports_atomic_generation_switch` | boolean | 当前默认 `false/UNTESTED`，不得猜测为真 |
| `max_top_n` | integer/null | 只有来源明确时填写；未知为 null |
| `evidence_level` | enum | 历史证据：`host_verified`、`abi_verified`、`untested`；不得用瞬时故障降级历史证据 |
| `availability` | enum | 当前观测：`available`、`degraded`、`unavailable`、`unknown` |
| `availability_checked_at` | UTC datetime | 当前可用性观测时间；不得当作历史验证时间 |

`capabilities()` 是只读操作，不得隐式加载模型、创建 Collection、重建索引或
修改服务状态。

`evidence_level` 只说明该能力曾达到的证据等级；`availability` 只说明
`availability_checked_at` 时的当前观测。曾有 `host_verified` 的 Provider 当前
仍可为 `unavailable`，当前 `available` 也不得把 `untested` 自动提升为
`host_verified`。

### 6.3 Upsert

`VectorUpsertRequest`：

| 字段 | 类型 | 必填 | 约束 |
|---|---|:---:|---|
| 公共标识/deadline | 见 5.1 | 是 | 同一逻辑写入保持稳定 |
| `idempotency_key` | string | 是 | 按 5.6.2 复合域判定重放或冲突 |
| `payload_hash` | `Digest` | 是 | Provider 按 `canonical-json/v1` 复算 |
| `index_generation` | string | 是 | 只能写入明确的目标代次 |
| `source_watermark` | `Watermark` | 是 | 对应 SQLite/Outbox 已提交事实，由 D 生成 |
| `records` | `VectorRecord[]` | 是 | 非空、大小受 Provider 能力与 Service 限制 |

`VectorRecord`：

| 字段 | 类型 | 约束 |
|---|---|---|
| `memory_id` | string | 稳定逻辑 ID；非空 |
| `version_id` | string | SQLite 当前已提交版本；非空 |
| `user_id` | string | 必须与请求 `user_id` 完全相同 |
| `vector` | float[] | 长度等于 capabilities.dimension；全部为有限数 |
| `object_type` | enum | `preference` 或 `knowledge`；区分业务对象，不复用 `memory_type` |
| `memory_type` | string/null | 承载 E/D 的短/中/长期业务枚举；B 不自行新增枚举值 |
| `scene_id` | string/null | 已规范化的场景标识，不是自由表达式 |
| `scope_terms` | map<string,string[]> | 只含契约允许键和值；数组去重并稳定排序 |
| `index_text_hash` | `Digest` | 敏感过滤后索引文本的 HMAC 摘要；不要求 Vector 保存正文 |

Upsert 不变量：

- SQLite/Outbox 事实必须先提交，Vector Upsert 不能成为业务真源；
- Provider 只能索引请求用户记录，批内任一跨用户项必须拒绝；
- 同一幂等复合域 + 同一 `payload_hash` 重放不得重复产生逻辑记录；
- 同一复合域但 `payload_hash` 不同必须返回 `conflict`；跨复合域复用裸 key
  不得误报冲突；
- 旧 `source_watermark` 不得覆盖同一水位 domain 的更高值，跨 domain 比较
  必须拒绝；
- 部分批次失败必须逐项返回状态，不能只返回模糊“成功”；
- 正文是否进入 Vector 物理元数据由 D4 Schema 决定，但不得作为检索输出真源。

`VectorUpsertResult` 至少包含 `accepted_count`、`upserted_count`、
`unchanged_count`、`rejected[]`、`index_generation`、`applied_watermark` 和
`outcome`（`applied`、`no_op`、`partial`、`outcome_unknown`）。

### 6.4 Search

`VectorSearchRequest`：

| 字段 | 类型 | 必填 | 约束 |
|---|---|:---:|---|
| 公共标识/deadline | 见 5.1 | 是 | deadline 到期前才可开始调用 |
| `query_vector` | float[] | 是 | 维度匹配、全部有限数 |
| `filter` | `RetrievalFilter` | 是 | `user_id` 精确过滤不可省略 |
| `top_n` | integer | 是 | `> 0` 且不超过 Service/Provider 上限 |
| `required_generation` | string/null | 否 | 指定时不允许静默查询其他代次 |

`VectorSearchResult` 至少包含：

- `hits: RetrievalHit[]`；
- `index_state: IndexStateSummary`；
- `raw_hit_count`、`valid_hit_count`、`dropped_hit_count`；
- `partial`、`degraded_reason`；
- 实际 `filter_fingerprint`，不含原始敏感值。

Search 不变量：

- Provider 层先执行 `user_id` 硬过滤；Service 回源时再次校验用户归属；
- SDK 返回顺序转为 1 起始 rank；
- 同一通道只对精确 `(memory_id, version_id)` 重复项保留最佳 rank；必须先按
  §8 完成 SQLite 当前版本与合法性过滤，才可按 `memory_id` 聚合最佳合法 rank；
- 非正 rank、非有限 raw score、缺失 ID/用户/版本的命中被丢弃并计数；
- Search 不返回正文，正文由 Service 回源 SQLite；
- `top_n` 是上限，不保证一定返回足量结果；
- 无命中是成功空列表，不是 `provider_unavailable`。

### 6.5 Delete

Provider 只接受已经由确定性规则解析完成的选择器，不接受自然语言或任意
SDK/SQL 表达式。

`VectorDeleteRequest`：

| 字段 | 类型 | 必填 | 约束 |
|---|---|:---:|---|
| 公共标识/deadline | 见 5.1 | 是 | 写操作要求完整审计 |
| `idempotency_key` | string | 是 | 按 5.6.2 复合域判定重放或冲突 |
| `payload_hash` | `Digest` | 是 | Provider 按 `canonical-json/v1` 复算 |
| `index_generation` | string | 是 | 禁止跨代次模糊删除 |
| `source_watermark` | `Watermark` | 是 | 对应已提交 ForgetPlan/Outbox 事实 |
| `selector` | `ResolvedDeleteSelector` | 是 | 已解析、非空、受控 |
| `authorization_ref` | string/null | 条件 | 批量/full reset 按 E/D 规则要求 |

`ResolvedDeleteSelector` 允许：

```text
{
  user_id: string,
  memory_ids: non-empty string[],
  version_ids: string[] | null,
  selection_mode: single_item | resolved_batch | full_reset,
  selection_hash: Digest,
  resolved_by: deterministic_rule_engine | system,
  preview_ref: string,
  preview_hash: Digest,
  confirmation_mode: explicit | policy_exempt,
  confirmation_ref: string | null,
  exemption: {
    code: committed_forget_cleanup,
    policy_id: string,
    policy_version: string,
    decision_ref: string
  } | null
}
```

冻结约束：

- `user_id` 必填并与请求用户相同；
- `memory_ids` 必须来自 SQLite/遗忘规则引擎的确定性解析，禁止模型生成；
- `selection_hash` 绑定规范化后的用户、ID、版本、模式和解析来源；
  `preview_hash` 还必须绑定预计匹配数、不可逆影响摘要和源水位；两者均按
  `canonical-json/v1` 计算，`preview_ref` 指向同一份未过期预览；
- `single_item` 必须恰好包含一个 `memory_id` 和一个明确 `version_id`。默认使用
  `confirmation_mode=explicit` 并携带绑定 `preview_hash` 的 `confirmation_ref`；
- 只有“已提交遗忘事实的单项向量清理”可使用 `policy_exempt`：模式必须为
  `single_item`，`exemption.code=committed_forget_cleanup`，`authorization_ref`
  必须指向同用户、同 memory/version 的已提交 ForgetPlan/Outbox 事实，且
  `policy_id`、`policy_version`、`decision_ref` 全部非空。该决定只能由版本化的
  确定性规则引擎产生，模型、自然语言、调用方布尔值或 Provider 推断均无效；
- `resolved_batch` 必须使用 `confirmation_mode=explicit`，携带非空
  `confirmation_ref`，并绑定完整 `selection_hash` 与 `preview_hash`；不得豁免；
- `full_reset` 必须使用 `confirmation_mode=explicit`，同时携带独立非空的
  `authorization_ref` 与 `confirmation_ref`，二者均绑定用户、作用域、预览、
  目标代次和过期时间；不得豁免；
- `explicit` 时 `confirmation_ref` 非空且 `exemption=null`；`policy_exempt` 时
  `confirmation_ref=null` 且 `exemption` 完整。其他组合一律 `invalid_argument`；
- 空 ID 列表、通配符、原始自然语言、任意过滤表达式全部 `invalid_argument`；
- Service 必须先用 SQLite 真源确认 resolved IDs 均属于请求用户；若已知包含
  跨用户目标，必须在调用 Provider 前返回 `user_scope_violation`；
- `request.user_id != selector.user_id` 时 Provider 必须返回
  `user_scope_violation`，不得执行删除；
- Provider 在用户硬过滤下未匹配的 ID 返回 `not_matched_ids`；Service 只有在
  SQLite/Outbox 已确认目标不存在或遗忘已生效时，才能把它归一为
  `already_absent`，不能用“0 条匹配”掩盖越权请求；
- 删除后出现陈旧命中时，Service 丢弃并记录 `stale_index`，不得恢复正文。

`VectorDeleteResult` 至少包含 `matched_count`、`deleted_count`、
`not_matched_ids`、`rejected[]`、`index_generation`、`applied_watermark` 和
`outcome`。

遗忘事务顺序及授权/确认策略由 D/E 跨轨冻结；B Provider 只消费 Service 已按
上述结构解析、授权并校验的确定性选择器，不自行解释业务意图或签发豁免。
SQLite/ForgetPlan 是真源，Vector 删除是可重放索引副作用；Vector 失败不能
撤销已授权的业务遗忘事实，但必须进入修复队列并使索引状态变为
`stale`/`degraded`。

### 6.6 Rebuild

`VectorRebuildRequest`：

| 字段 | 类型 | 必填 | 约束 |
|---|---|:---:|---|
| 公共标识/deadline | 见 5.1 | 是 | 重建预算不得无限延伸 |
| `idempotency_key` | string | 是 | 按 5.6.2 复合域判定重放或冲突 |
| `payload_hash` | `Digest` | 是 | Provider 按 `canonical-json/v1` 复算 |
| `source_snapshot_id` | string | 是 | D 提供的确定性 SQLite 快照/读取会话标识 |
| `source_watermark` | `Watermark` | 是 | 快照对应水位 |
| `target_generation` | string | 是 | 不得覆盖当前 serving generation |
| `schema_version` | string | 是 | 绑定 D4 Collection/字段 Schema |
| `reason` | enum | 是 | `bootstrap`、`schema_change`、`repair`、`full_reset` |
| `scope` | `IndexScope` | 是 | 全局或明确用户/分片；禁止隐式扩大范围 |
| `scope_authorization` | `ScopeAuthorization` | 是 | Service 已完成授权；必须绑定 `scope.scope_id` |

重建阶段：

```text
allocate_generation
  -> stream_from_sqlite_snapshot
  -> validate_record_counts_and_rejections
  -> verify_generation
  -> activate_if_supported_and_approved
  -> retire_previous_generation_later
```

冻结约束：

- 从 SQLite 确定性快照重建，不从旧 Vector 正文反向恢复；
- 新代次构建/验证失败时，不替换当前可用代次；
- 只有记录数、源水位、用户隔离抽查和拒绝原因通过后才能请求激活；
- 当前没有原子 Collection swap 的宿主证据，Provider 必须显式返回
  `activation_mode`：`atomic_switch`、`maintenance_window` 或 `routing_switch`；
- `atomic_switch` 只有 capabilities 明确支持且取得目标宿主证据时允许；
- 旧代次清理由单独、可审计、幂等的生命周期步骤执行；
- 超时/取消后状态必须可从 `IndexState` 恢复，不得留下“未知但标 ready”的代次。

`VectorRebuildResult` 至少包含 `scope`、`target_generation`、`source_snapshot_id`、
`source_watermark`、`read_count`、`indexed_count`、`rejected_count`、
`rejection_reasons`、`verified`、`activated`、`activation_mode`、
`previous_generation` 和 `outcome`。

### 6.7 `get_index_state`

这是严格只读操作：

```text
IndexStateRequest {
  request_id: string
  trace_id: string
  scope: IndexScope
  scope_authorization: ScopeAuthorization
  required_watermark: Watermark | null
  deadline_at: UTC datetime
}
```

- 不隐式创建 Collection；
- 不加载模型；
- 不启动/重启服务；
- 不修复、删除或重建；
- 不因状态查询更新业务水位。

## 7. `RetrievalFilter`

### 7.1 结构

```text
RetrievalFilter {
  user_id: string
  scene: SceneFilter
  scope_terms: map<string, string[]>
  object_types: subset(preference, knowledge)
  memory_types: string[]
  allowed_memory_statuses: string[]
  allowed_sensitivity: string[]
  conflict_policy: string
  as_of: UTC datetime
}

SceneFilter {
  allowed_scene_ids: string[]
  include_unscoped: boolean
}
```

### 7.2 构造边界

- `RetrievalFilter` 由 Service 的确定性策略层构造，不直接接收模型输出；
- `user_id` 不允许为空、通配或 `all`；
- 场景“全局/无场景是否可见”的业务规则由 E/D 计算成
  `allowed_scene_ids + include_unscoped`，Provider 不自行猜测；
- `scope_terms` 的允许键由版本化 Schema 定义；未知键默认拒绝；
- 数组去重、稳定排序并限制长度；
- `allowed_memory_statuses`、`allowed_sensitivity` 和 `conflict_policy` 的正式
  枚举由 E/D 冻结，B 只要求它们在 Provider 调用前已解析；
- 用户隔离、生命周期、敏感度、冲突和遗忘是硬过滤，不得改成降权；
- Provider 只能从类型化结构生成参数绑定 SQL/受控 Vector 表达式，禁止
  拼接未经验证的用户字符串。

### 7.3 双重校验

Provider 过滤降低数据暴露与无效候选数量；SQLite 回源校验是最终授权判断。
二者缺一不可：

1. Provider 返回跨用户项：丢弃整项、记录协议违约，并视严重程度降级通道；
2. Provider 命中版本与 SQLite 当前版本不同：丢弃并记录 `stale_index`；
3. Provider 命中在 SQLite 不存在/已遗忘：丢弃并安排索引修复；
4. Provider 返回的元数据不得覆盖 SQLite 业务字段。

## 8. `RetrievalHit`

`RetrievalHit` 是单一召回通道的内部结果，不是可直接注入 Context 的对象。

| 字段 | 类型 | 必填 | 约束 |
|---|---|:---:|---|
| `memory_id` | string | 是 | 非空、稳定逻辑 ID |
| `version_id` | string | 是 | 命中索引版本；回源确认前不视为当前版本 |
| `user_id` | string | 是 | 必须等于请求用户 |
| `channel` | enum | 是 | `fts5` 或 `vector` |
| `rank` | integer | 是 | 1 起始、`> 0` |
| `raw_score` | finite number/null | 是 | 只诊断，不跨通道比较 |
| `score_semantics` | string | 是 | `bm25` 或 `sdk_score_unverified` 等明确标签 |
| `provider` | string | 是 | 实现稳定名 |
| `index_generation` | string/null | 条件 | Vector 命中必填；FTS5 按实现填写 |
| `retrieved_at` | UTC datetime | 是 | 本次命中时间 |
| `filter_fingerprint` | `Digest` | 是 | 过滤结构的 HMAC 安全指纹，不含正文 |
| `diagnostics` | object | 是 | 非敏感、大小受限、结构化 |

禁止字段：`content`、未经脱敏正文、SDK 私有对象、可执行过滤表达式。

同一通道的处理顺序固定为：

1. 仅对精确 `(memory_id, version_id)` 重复项去重，每个精确版本保留最小
   rank；rank 相同则按稳定字段顺序选择，并记录重复计数；
2. 回源 SQLite 校验用户归属、当前版本、状态、有效期、敏感度、冲突和遗忘
   策略，移除过期版本和其他非法命中；
3. 对剩余合法命中按 `memory_id` 聚合，每个通道保留最佳合法 rank；
4. 聚合后的每个逻辑记忆在同一通道只贡献一次 RRF 分数。

禁止在版本校验前按 `memory_id` 去重。例如同一记忆的旧 `v1` 为 rank 1、当前
`v2` 为 rank 2 时，必须移除 `v1` 并保留 `v2`，不能因旧版本先胜出而隐藏当前
合法版本。

## 9. `RetrievalCandidate`

候选在完成 SQLite 回源和全部硬过滤后形成，可进入 RRF、业务重排与 Context
预算。

| 字段 | 类型 | 必填 | 约束/所有者 |
|---|---|:---:|---|
| `memory_id` | string | 是 | 聚合主键 |
| `version_id` | string | 是 | SQLite 当前有效版本 |
| `object_type` | enum | 是 | `preference` 或 `knowledge`；B 技术判别字段 |
| `user_id` | string | 是 | 与请求完全相同；服务内部安全字段 |
| `memory_type` | string/null | 否 | E/D 的短/中/长期业务语义，不表示对象类别 |
| `memory_status` | string | 是 | E/D 生命周期枚举；只允许检索策略批准值 |
| `scene_id` | string/null | 否 | 已通过场景策略 |
| `scope_terms` | map | 是 | 已通过作用域策略 |
| `content` | string | 是 | SQLite 当前版本的安全正文/摘要 |
| `content_source` | enum | 是 | `sqlite_current` 或 `sqlite_safe_summary` |
| `channels` | enum[] | 是 | 固定顺序：`fts5`、`vector` |
| `ranks` | map<channel,integer> | 是 | 1 起始 |
| `raw_scores` | map<channel,number/null> | 是 | 只诊断 |
| `score_semantics` | map<channel,string> | 是 | 防止误用 raw score |
| `rrf_score` | finite number | 是 | `rrf-v1` 结果 |
| `final_score` | finite number | 是 | 无批准重排时等于 `rrf_score` |
| `sensitivity` | string | 是 | E 安全规则批准值 |
| `conflict_state` | string | 是 | E 业务语义；未解决项按策略硬过滤 |
| `valid_from` / `valid_to` | UTC datetime/null | 否 | 以查询 `as_of` 校验 |
| `estimated_tokens` | integer | 是 | 非负；估算器版本另行记录 |
| `explanation` | object | 是 | 通道、RRF 分项、降级、过滤和重排版本 |

### 9.1 字段冲突消解

D1 草案曾用 `memory_type` 表示 `preference/knowledge`；当前业务 Schema
已将 `memory_type` 用于 `short_term/medium_term/long_term/ephemeral`。
D3-B 冻结以下修正：

- 使用 `object_type` 区分 `preference` 与 `knowledge`；
- 保留 `memory_type` 承载业务记忆层级，不再承担对象判别；
- D4 代码、测试和 JSON 示例不得延续 D1 的双重语义。

### 9.2 IPC 可见性

B 层冻结服务内部对象，IPC 最终映射由 C/D 决定：

| 字段组 | B 层建议 | 状态 |
|---|---|---|
| ID、对象类型、安全正文/摘要、最终分、必要解释 | 可进入 `MemoryContext` | 待 C/D 冻结 |
| `user_id`、原始 score、Provider、过滤指纹、内部错误详情 | 默认仅服务端 | `FROZEN_CANDIDATE` 建议，IPC 映射 `DEFERRED` |
| 敏感度、冲突/过滤原因 | 仅暴露安全归一化结果 | 待 E/C/D 联审 |

## 10. `IndexState`

### 10.1 状态枚举

| `status` | 含义 | 是否可查询 |
|---|---|---|
| `unavailable` | Provider/服务不可达，无法确认索引 | 否 |
| `empty` | 索引可用但当前受控范围无记录 | 是，返回空结果 |
| `building` | 新代次正在构建/验证 | 由 `is_queryable` 与 serving generation 决定 |
| `ready` | serving generation 已验证且水位满足策略 | 是 |
| `degraded` | 仍可查询，但有通道/代次/同步问题 | 是，必须返回降级原因 |
| `stale` | serving generation 落后真源或含已知陈旧项 | 由策略决定；命中仍须回源 |
| `failed` | 最近构建/校验失败且没有可安全服务的代次 | 否 |

### 10.2 字段

| 字段 | 类型 | 约束 |
|---|---|---|
| `provider` | string | 实现稳定名 |
| `scope` | `IndexScope` | 与请求作用域完全一致；不得返回更宽范围 |
| `status` | `IndexStatus` | 上表枚举 |
| `is_queryable` | boolean | 与状态和 serving generation 一致 |
| `schema_version` | string | 当前 serving Schema |
| `serving_generation` | string/null | 当前查询代次 |
| `building_generation` | string/null | 当前构建代次 |
| `source_snapshot_id` | string/null | serving generation 的真源快照 |
| `applied_watermark` | `Watermark`/null | 已应用 SQLite/Outbox 水位 |
| `required_watermark` | `Watermark`/null | 调用方要求水位；必须与 applied 同域同 kind |
| `record_count` | integer/null | 非负；未知为 null，不伪造 0 |
| `pending_count` | integer/null | 非负；未知为 null |
| `stale_count` | integer/null | 非负；未知为 null |
| `last_success_at` | UTC datetime/null | 最近成功同步/激活时间 |
| `last_checked_at` | UTC datetime | 本次只读状态采集时间 |
| `last_error` | safe `RetrievalError`/null | 不含敏感详情 |
| `evidence_level` | enum | `host_verified`、`abi_verified`、`untested`；历史证据轴 |
| `availability` | enum | `available`、`degraded`、`unavailable`、`unknown`；当前观测轴 |

`serving_generation`、`building_generation`、`source_snapshot_id`、两类水位、
`record_count`、`pending_count`、`stale_count`、状态和时间戳均以 `scope` 为
统计边界。用户级状态不得汇入其他用户记录，分片级状态不得汇入其他分片；
同名 generation 在不同 `scope_id` 下仍是不同代次。

`evidence_level` 与 `availability` 必须独立更新：历史宿主验证不会因当前服务
中断而消失，当前探活成功也不能提升历史证据等级。`availability` 的采集时点为
`last_checked_at`；超过调用方的新鲜度预算后必须视为 `unknown`，不得沿用旧值。

### 10.3 状态约束与转换

- `ready` 必须有非空 `serving_generation`、`schema_version` 和水位；
- `empty` 表示已验证的空索引，不等同于状态未知；
- `building` 可以在旧 serving generation 仍可用时 `is_queryable=true`；
- `stale`/`degraded` 命中仍需 SQLite 回源，且必须记录修复计划；
- 新代次只有完成校验后才能成为 serving generation；
- 构建失败保留旧可用代次，整体状态为 `degraded`，除非没有安全代次才为
  `failed`；
- 进程存活、Socket 存在或 Collection 名存在都不能单独推导 `ready`；
- 状态查询不得产生状态转换，转换由明确的写/重建/协调操作记录。

## 11. JSON 样例

样例用于固定字段形状；D4 实现可以增加向后兼容的可选字段，但不能改变已
冻结字段语义。

### 11.1 Search 请求

```json
{
  "contract_version": "vector-retrieval/v1",
  "request_id": "req-20260803-001",
  "trace_id": "trace-20260803-001",
  "user_id": "user-alpha",
  "deadline_at": "2026-08-03T02:00:00Z",
  "query_vector_ref": "embedding-result:req-20260803-001",
  "query_dimension": 768,
  "filter": {
    "user_id": "user-alpha",
    "scene": {
      "allowed_scene_ids": ["software-development"],
      "include_unscoped": true
    },
    "scope_terms": {
      "project_id": ["kylin-os-agent-memory"]
    },
    "object_types": ["knowledge", "preference"],
    "memory_types": ["medium_term", "long_term"],
    "allowed_memory_statuses": ["active"],
    "allowed_sensitivity": ["none", "low"],
    "conflict_policy": "exclude_unresolved",
    "as_of": "2026-08-03T01:59:59Z"
  },
  "top_n": 20,
  "required_generation": "vector-gen-0007"
}
```

`query_vector_ref` 只为文档避免粘贴 768 个浮点数；实际 Provider 调用必须
传入通过维度/有限数校验的向量对象，D 轨决定 IPC 是否允许引用形式。

### 11.2 `RetrievalHit`

```json
{
  "memory_id": "kn-000101",
  "version_id": "ver-0003",
  "user_id": "user-alpha",
  "channel": "vector",
  "rank": 1,
  "raw_score": 0.9998,
  "score_semantics": "sdk_score_unverified",
  "provider": "kylin_vector_0k0.7",
  "index_generation": "vector-gen-0007",
  "retrieved_at": "2026-08-03T01:59:59.120Z",
  "filter_fingerprint": "hmac-sha256:k1:8af799eed65e29c7473a302c979252bb3b53e6f29f47b038510039e2c4c39a90",
  "diagnostics": {
    "provider_elapsed_ms": 18,
    "duplicate_count": 0
  }
}
```

### 11.3 `RetrievalCandidate`

```json
{
  "memory_id": "kn-000101",
  "version_id": "ver-0003",
  "object_type": "knowledge",
  "user_id": "user-alpha",
  "memory_type": "long_term",
  "memory_status": "active",
  "scene_id": "software-development",
  "scope_terms": {
    "project_id": ["kylin-os-agent-memory"]
  },
  "content": "Vector Runtime 结果必须来自麒麟宿主证据。",
  "content_source": "sqlite_safe_summary",
  "channels": ["fts5", "vector"],
  "ranks": {
    "fts5": 2,
    "vector": 1
  },
  "raw_scores": {
    "fts5": -7.42,
    "vector": 0.9998
  },
  "score_semantics": {
    "fts5": "bm25",
    "vector": "sdk_score_unverified"
  },
  "rrf_score": 0.0325224749,
  "final_score": 0.0325224749,
  "sensitivity": "low",
  "conflict_state": "none",
  "valid_from": "2026-07-31T00:00:00Z",
  "valid_to": null,
  "estimated_tokens": 18,
  "explanation": {
    "algorithm_version": "rrf-v1",
    "rrf_k": 60,
    "rrf_terms": {
      "fts5": 0.0161290323,
      "vector": 0.0163934426
    },
    "degraded_channels": [],
    "rerank_version": null
  }
}
```

### 11.4 `IndexState`

```json
{
  "provider": "kylin_vector_0k0.7",
  "scope": {
    "scope_id": "scope-user-001",
    "kind": "user",
    "user_id": "user-001",
    "shard_id": null,
    "scope_fingerprint": "hmac-sha256:k1:9bf799eed65e29c7473a302c979252bb3b53e6f29f47b038510039e2c4c39a93"
  },
  "status": "building",
  "is_queryable": true,
  "schema_version": "vector-schema/v1",
  "serving_generation": "vector-gen-0007",
  "building_generation": "vector-gen-0008",
  "source_snapshot_id": "sqlite-snapshot-20260803-001",
  "applied_watermark": {
    "domain": {
      "scope_id": "scope-user-001",
      "stream": "sqlite-outbox",
      "partition": "user-001",
      "source_generation": "sqlite-epoch-202608"
    },
    "kind": "monotonic_int",
    "value": 1842
  },
  "required_watermark": {
    "domain": {
      "scope_id": "scope-user-001",
      "stream": "sqlite-outbox",
      "partition": "user-001",
      "source_generation": "sqlite-epoch-202608"
    },
    "kind": "monotonic_int",
    "value": 1842
  },
  "record_count": 1200,
  "pending_count": 0,
  "stale_count": 0,
  "last_success_at": "2026-08-03T01:40:00Z",
  "last_checked_at": "2026-08-03T01:59:59Z",
  "last_error": null,
  "evidence_level": "host_verified",
  "availability": "available"
}
```

### 11.5 Delete 请求

```json
{
  "contract_version": "vector-retrieval/v1",
  "request_id": "req-delete-001",
  "trace_id": "trace-forget-001",
  "user_id": "user-alpha",
  "deadline_at": "2026-08-03T02:01:00Z",
  "idempotency_key": "forget-plan-fgp-001-watermark-1843",
  "payload_hash": "hmac-sha256:k1:7ab799eed65e29c7473a302c979252bb3b53e6f29f47b038510039e2c4c39a91",
  "index_generation": "vector-gen-0007",
  "source_watermark": {
    "domain": {
      "scope_id": "scope-user-alpha",
      "stream": "sqlite-outbox",
      "partition": "user-alpha",
      "source_generation": "sqlite-epoch-202608"
    },
    "kind": "monotonic_int",
    "value": 1843
  },
  "selector": {
    "user_id": "user-alpha",
    "memory_ids": ["kn-000101"],
    "version_ids": ["ver-0003"],
    "selection_mode": "single_item",
    "selection_hash": "hmac-sha256:k1:c10bd1d548b7d1665534b0ef3c81a9e0f7b7fe003444e19238d604a791a2ee33",
    "resolved_by": "deterministic_rule_engine",
    "preview_ref": "delete-preview-001",
    "preview_hash": "hmac-sha256:k1:d20bd1d548b7d1665534b0ef3c81a9e0f7b7fe003444e19238d604a791a2ee34",
    "confirmation_mode": "explicit",
    "confirmation_ref": "delete-confirmation-001",
    "exemption": null
  },
  "authorization_ref": null
}
```

## 12. 与业务 Schema 的 B 轨差异核对

| 业务字段/问题 | B 轨结论 | 状态/待办 |
|---|---|---|
| `Knowledge.content_summary` | 可作为 FTS5/Embedding 输入，但须先敏感过滤；检索输出仍回源 SQLite | 符合，E 关注安全边界 |
| `extracted_entities` | 可作为受控元数据过滤，不允许直接拼表达式 | 符合，D4 Schema 决定物理布局 |
| `primary_category` | 开放业务分类，可过滤/解释，不得替代 `knowledge_type` | 符合 |
| `knowledge_type` | 可作为类型化过滤字段；正式枚举由 E | 符合，枚举 `DEFERRED` |
| `language_tag` | 可用于过滤与分词选择，采用规范化 BCP 47 | 符合，D4 验证 |
| `memory_type` | 保留短/中/长期语义；不得再表示 preference/knowledge | 需以 `object_type` 消除 D1 双重语义 |
| `memory_status` | 作为硬过滤输入；只允许策略批准状态 | 枚举与迁移由 D/E `DEFERRED` |
| `Conflict` 字段 | 未解决冲突默认硬过滤；不直接混入 RRF 分数 | 业务策略由 E，B 冻结过滤位置 |
| `ForgetPlan.has_vector_cleanup` | 应由系统根据已索引记录和策略派生，不由模型决定 | 需 D/E 确认派生与事务顺序 |
| `ForgetPlan.is_cascade` | B 接受解析后的确定性 ID 集，不决定级联业务范围 | E/D `DEFERRED` |
| `full_reset` | Provider 只消费已授权、已确认、已解析选择器 | 授权/确认由 E/D `DEFERRED` |

## 13. 版本与兼容规则

1. 请求必须携带 `contract_version`；未知主版本默认拒绝；
2. v1 新增可选响应字段可以向后兼容，但不得重用现有字段表达不同语义；
3. 删除/重命名必填字段、改变枚举语义或默认 RRF 行为需要 v2/新 ADR；
4. `object_type` 与 `memory_type` 的语义区分是 v1 强约束；
5. 日志、评测和证据必须记录契约版本、算法版本、Provider 版本、索引代次与
   Schema 版本；
6. 未知过滤键/枚举默认 fail closed，不允许静默放宽用户或安全边界。

## 14. D4 契约测试入口

D4 至少覆盖：

- Provider 输入校验、维度/有限数、deadline 和取消；
- Upsert 幂等、payload 冲突、旧水位、批内跨用户与部分失败；
- Search 用户硬过滤、无命中、非法 rank、精确版本去重、过滤后逻辑记忆聚合、
  陈旧版本和代次约束；必须覆盖旧 `v1` rank 1、当前 `v2` rank 2 时仍保留
  `v2`；
- Delete 空/通配/自然语言拒绝、跨用户拒绝、重复删除和 full reset 门禁；
- Rebuild 新代次、失败保留旧代次、校验失败不激活和非原子能力声明；
- `IndexState` 不变量、只读状态查询和状态恢复；
- `RetrievalCandidate` SQLite 回源、`object_type`/`memory_type` 区分；
- ADR-001 golden RRF、确定性 tie-break、单路降级与双路失败。

详细条目见 `docs/day3/09_retrieval_contract_review_matrix.md`。

## 15. 未冻结项

以下项目显式 `DEFERRED`，不得在 D3-B 文档中伪造结论：

| 项目 | 责任方/阶段 | D3-B 已冻结的边界 |
|---|---|---|
| IPC JSON/长度前缀/数字错误码 | D/C | B 错误字符串语义与字段职责不变 |
| SQLite 表、Outbox 水位类型、事务顺序 | D | SQLite/Outbox 为真源，Vector 副作用可重放 |
| Collection/字段/主键物理 Schema | D4 B/D | 稳定逻辑 ID、用户/版本和代次必须可表达 |
| 场景/作用域正式枚举与继承 | E/D | Provider 只接收已解析 typed filter |
| `memory_status`、敏感度、冲突正式枚举 | E/D | 它们是融合前硬过滤 |
| full reset 授权、确认与级联范围 | E/D | Provider 只消费已授权的 resolved selector |
| Top-N/Top-K 默认数与类型配额 | B/E 评测 | 必须有界、版本化并进入评测记录 |
| Token 估算器和 Context 截断 | C/B | 候选携带非负估算与版本化解释 |
| 原子索引代次切换 | D4 Runtime | 未验证前 capabilities=false |
| IPC 用户身份与 deadline 线格式 | C/D | 进入 B Provider 前必须解析出非空 `user_id` 和同一绝对 `deadline_at`；相对 timeout 只能由剩余预算派生，Echo 固定值不得成为正式协议默认值 |
| Embedding 到检索的错误/deadline 适配 | D4 A/B/D | 保留 `cancelled` 与 `deadline_exceeded` 的区别；A 轨异常和相对 timeout 必须在编排层归一，不能泄漏私有错误或重置预算 |
| Provider 同步/异步实现 | D4 A/B/D | 绝对 deadline、取消与结果语义不变 |

### 15.1 2026-08-04 GitHub 跨分支兼容核对

以下是 `2026-08-04` 的只读审计快照：当时以
`main@56de07977cb10c4fb87878e24ed5a7c97bf27ba2` 为基线核对三个未合并分支。
它只描述指定 SHA 当时的机械冲突和兼容判断，不是当前实现依赖、合并基线或
持续有效结论；后续判断必须重新同步默认分支并生成新快照。该记录不替代相应
PR 的独立 Review，也不把原型实现提升为正式契约：

| 来源 | 已观察事实 | D3-B 兼容判断 |
|---|---|---|
| PR #18 `feature/kaiming-uds-echo@1b8111c1` | Echo 请求仍使用固定 `request_id`、相对 `deadline_ms`，`memory.retrieve` 未携带 `user_id`；服务端新增 30 秒 Socket 读写超时，但尚未消费请求 deadline 或取消 | 仅可作为 Gate 0 UDS 连通性原型；传输防永久阻塞不等于跨层绝对 deadline。由 C/D 在 IPC 冻结时补齐身份、绝对 deadline、取消和安全错误结构 |
| PR #17 `feat/day4-bridge-provider-new@5510f94d` | EmbeddingProvider 使用相对 `timeout_ms`，主动中断尚未实现，并把 `BridgeCancelledError` 归入 `ERR_TIMEOUT`；最新实现增加进程级 Bridge/session 单例约束 | A/B Provider 的职责仍可分层；D4 编排适配必须保留取消/超时差异，在同一绝对 deadline 内归一 A 轨异常，并把生命周期约束纳入调度设计；继续受 `TD-A-005-01` 约束 |
| PR #19 `docs/C-d2-osagent-runtime@2797ae08` | `memory_context` 为 `NOT_OBSERVED`，真实 Runtime Socket/Hook 事实仍待进一步验证 | 与本契约的 C 轨宿主映射 `DEFERRED` 状态一致，不构成矛盾，也不得据此声称 Context 注入已实现 |

相对该快照中的 D3-B HEAD，三方预检结果为：PR #18 可机械合并；PR #17 与
PR #19 均在 `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` 产生内容冲突。
冲突来自各轨在同一表尾追加记录，不是编号碰撞。集成时必须保留 B 轨
`TD-003/TD-004`、A 轨 `TD-A-005-01~05` 以及 C 轨 `TD-007~009` 的并集，
不得通过选择一侧删除其他轨技术债。该机械处置规则不表示跨轨语义已经闭合，
也不得据此 merge、rebase、Review 或改写其他作者分支。

## 16. 完成与审查门槛

本契约从“冻结候选”变为“已接受”需要：

1. 一名独立、非作者 Reviewer 给出 `APPROVED`，以满足 GitHub PR 的人工审批
   数量门槛；该 approval 不自动等价为 Day3-B Gate PASS；
2. Review 记录明确覆盖项目任务卡指定的 D 可实现性与 E 用户隔离、遗忘、安全、
   评测关注项；本契约不修改该角色分工；
3. ADR-001 状态同步更新为“已采纳”；
4. 审查矩阵中所有 P0 条目为 `ACCEPTED` 或有明确阻断结论；
5. `git diff --check`、仓库基线、JSON 样例解析和 RRF golden 复算通过；
6. 文档明确记录本轮未启动虚拟机，未新增 Runtime 证据。

## 17. 证据与引用

- `evidence/index.yaml`：`VECTOR-CALL-003`（指定历史提交的 D2-B E4
  Runtime 结果）与 `D1-B-02`（原生 Hybrid/RRF E3）；
- `evidence/l2-kylin-vm/d2-vector-smoke-evidence-20260802c1.md`；
- `docs/architecture/d1-b-retrieval-candidate-rrf-draft.md`；
- `docs/architecture/d2-retrieval-candidate-unified.md`；
- `docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md`；
- `docs/day3/06_provider_contract_v1.md`；
- `docs/adr/001-application-layer-rrf.md`。

本文未启动麒麟虚拟机、未修改默认数据库/服务/KySec/网络或系统状态，也未
产生新的 L2/L3 证据。D2 的 E4 事实只作为契约输入，不代表 D3/D4 功能已完成。
