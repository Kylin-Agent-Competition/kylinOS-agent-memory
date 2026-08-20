# 09 轨道 B — 检索契约审查与 D4 测试矩阵

- 日期：2026-08-03
- 状态：`REWORK`
- 契约：`vector-retrieval/v1`
- 关联 ADR：`ADR-001 / rrf-v1`
- 人工审批门槛：一名独立、非作者 Reviewer 的 `APPROVED`
- 专业关注点：D 关注 Provider/SQLite/Outbox/IPC 可实现性；E 关注用户隔离、
  遗忘、安全与评测；项目任务卡指定的关注项须在 Review 记录中明确覆盖
- Runtime：本轮未启动虚拟机；所有 L2 条目为 `DEFERRED_VM`

## 1. 使用规则

本矩阵同时服务于 D3 Gate 0 人工审查和 D4 契约测试设计。

状态定义：

| 状态 | 含义 |
|---|---|
| `FROZEN_CANDIDATE` | D3-B 已给出唯一候选语义，等待 Reviewer 接受/返工 |
| `DEFERRED_CROSS_TRACK` | 由 C/D/E 冻结，B 已明确自身边界 |
| `PLANNED_D4` | D4 必须实现的非 VM 契约测试 |
| `DEFERRED_VM` | 需要目标麒麟宿主，按本轮用户指令暂不执行 |
| `PASS_LOCAL` | 本轮可在本地完成的静态/纯函数检查已通过 |
| `PENDING_REVIEW` | 等待独立 Reviewer 给出结论 |

Reviewer 结论只能填写：`ACCEPTED`、`REWORK`、`BLOCKED` 或
`ACCEPTED_WITH_TD(<TD编号>)`。作者不得替 Reviewer 填写通过。

一份 GitHub `APPROVED` 只满足人工 Review 的数量组件，不自动等价为 Day3-B
Gate PASS；Gate 0 仍要求 P0 全部关闭、适用的静态/契约验证通过、证据与状态
表述一致、项目任务卡指定的 D/E 专业关注项已记录覆盖，且阻断项均有明确处置。

## 2. Gate 0 P0 审查矩阵

所有 P0 条目必须得到明确结论后，契约和 ADR 才能从“提议/冻结候选”改为
“已接受/已采纳”。

| ID | 领域 | 冻结要求 | 正向样例 | 必须拒绝/降级的反例 | 证据/依据 | 作者状态 | Reviewer |
|---|---|---|---|---|---|---|---|
| B-D3-001 | 版本 | 请求明确 `vector-retrieval/v1`，未知主版本 fail closed | v1 请求进入 Provider | 未知 v2 被当作 v1 执行 | 08 §13 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-002 | 边界 | Provider 不泄漏 SDK RPC/C++ 私有类型 | 返回结构化 `RetrievalError` | SDK 异常对象直接进入 IPC | 08 §5.3–5.4 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-003 | 用户隔离 | `user_id` 非空、精确匹配、双重校验 | alpha 只返回 alpha | 同向量 beta 进入候选 | D2 E4；08 §7 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-004 | 真源 | SQLite 决定正文、归属、版本、状态和遗忘 | Vector 命中回源当前版本 | 使用 Vector 元数据正文直接注入 | 架构基线；08 §4 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-005 | 命名 | `object_type` 区分偏好/知识，`memory_type` 只表示记忆层级 | `object_type=knowledge,memory_type=long_term` | `memory_type=knowledge` | 业务 Schema；08 §9.1 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-006 | Provider | v1 固定 capabilities/upsert/search/delete/rebuild/get_index_state | 五项操作均有输入输出 | 以隐式副作用代替操作 | 08 §6 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-007 | Deadline | 跨层使用同一绝对 `deadline_at` | 剩余预算逐层减少 | 每层重置 500 ms | 08 §5.5 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-008 | 取消 | SDK 不可中断时返回 `outcome_unknown` 并协调 | 幂等键确认最终状态 | 超时后直接宣称未写入并盲重试 | 08 §5.5 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-009 | 错误 | B 层字符串码语义稳定，D 只做协议映射 | `provider_unavailable` 映射 IPC | D 映射后改变可重试性/安全含义 | 08 §5.4 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-010 | Search | 非法 rank/ID/用户/版本/非有限 score 丢弃并计数 | 合法 hits 稳定排序 | 非法 hit 进入 RRF | 08 §6.4/§8 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-011 | 过滤 | Provider 先过滤，SQLite 回源终审 | 两层均确认用户/版本 | 只依赖 Vector 过滤 | D2 E4；08 §7.3 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-012 | Score | raw score 只作通道诊断 | 标记 `sdk_score_unverified` | 与 BM25 直接归一化/相加 | D2 限制；ADR-001 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-013 | Upsert | 复合幂等域+规范 payload hash 一致时重放同结果 | 同用户/操作/Provider/代次安全重放 | 跨用户复用裸 key 误冲突，或同域异载荷被接受 | 08 §5.6/§6.3 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-014 | 水位 | 仅同 scope/stream/partition/source-generation/kind 比较 | 同域 1843 后拒绝 1842 | 跨域比较或旧事件回滚索引版本 | 08 §5.6/§6.3 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-015 | Delete | 只接受已解析、非空 typed selector | 单条 resolved ID 删除 | 自然语言/通配/空列表直传 SDK | 08 §6.5 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-016 | Delete 隔离 | Service 先以 SQLite 校验归属；请求用户与 selector 用户不一致时明确拒绝 | alpha resolved IDs 进入 Provider | 越权 resolved ID 或用户不一致被“0 匹配”掩盖 | D2 E4；08 §6.5 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-017 | Full reset | 必须有独立授权、预览和显式确认引用 | 已授权且确认的 resolved selector | 模型/自然语言直接全量删除或豁免 | 业务 Schema；08 §6.5 | `DEFERRED_CROSS_TRACK` | `PENDING_REVIEW` |
| B-D3-018 | Rebuild | 只从 SQLite 确定性快照/水位构建新代次 | 新代次校验后激活 | 从旧 Vector 正文反向恢复 | 08 §6.6 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-019 | 激活 | 未验证原子切换前 capability=false | maintenance/routing 模式显式 | 假定 Collection rename 原子 | `TD-004`；08 §6.6 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-020 | IndexState | `ready` 必须有 serving generation、Schema 和水位 | 三项完整且已验证 | Socket/进程存在即 ready | 08 §10 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-021 | 状态只读 | `get_index_state` 不创建/启动/修复/重建 | 查询前后状态不变 | 健康检查隐式创建 Collection | 08 §6.7 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-022 | Hit/Candidate | Hit 无正文，Candidate 正文来自 SQLite | `content_source=sqlite_safe_summary` | Vector content 直接进入 Context | 08 §8–9 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-023 | 硬过滤 | 用户/生命周期/敏感/冲突/遗忘在融合前处理 | 被遗忘项不贡献分数 | 仅降低敏感/冲突项分数 | 08 §7/§9 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-024 | RRF | `rrf-v1` 默认 k=60、等权、1 起始 rank | golden cases 精确复算 | raw score 参与或零起始 rank | ADR-001 | `PASS_LOCAL` | `PENDING_REVIEW` |
| B-D3-025 | 排序 | score、通道数、最佳 rank、memory_id 固定 tie-break | 打乱输入仍同序 | 依赖容器迭代顺序 | ADR-001 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-026 | 降级 | 单路成功可返回已安全过滤候选；双路失败结构化空结果 | FTS5-only/Vector-only | 伪造缓存固定候选 | ADR-001 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-027 | 日志 | 记录 ID/hash/rank/计数/耗时，不记录敏感正文 | `user_id_hash` 和计数 | raw content/token/凭据进日志 | ADR-001；08 §5.3 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-028 | 兼容 | 字段语义变化必须升级契约/算法版本 | 增加可选响应字段 | 同 v1 静默改变权重 | 08 §13；ADR-001 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-029 | IPC | 服务内部诊断与 `MemoryContext` 字段分层 | 只暴露安全摘要/必要解释 | raw score/用户/内部错误无审查暴露 | 08 §9.2 | `DEFERRED_CROSS_TRACK` | `PENDING_REVIEW` |
| B-D3-030 | 证据 | 设计、E3、E4 与未测试状态分开 | 引用历史 E4 输入 | 文档静态检查冒充 D3 Runtime | 08 §2/§17 | `FROZEN_CANDIDATE` | `PENDING_REVIEW` |
| B-D3-031 | 命中去重顺序 | 精确版本去重后回源过滤，再按逻辑记忆聚合 | 旧 v1 rank 1 被移除、当前 v2 rank 2 保留 | 先按 memory_id 选 v1 导致 v2 被隐藏 | ADR-001；08 §8 | `FROZEN_CANDIDATE` | `REWORK (2026-08-04)` |
| B-D3-032 | IndexState 作用域 | 请求/状态携带稳定 `scope_id`；代次、水位、计数均绑定该 scope | 用户级与分片级状态独立 | 用户/分片状态被当作全局或跨 scope 合并 | 08 §5.2/§6.7/§10 | `FROZEN_CANDIDATE` | `REWORK (2026-08-04)` |
| B-D3-033 | 幂等域 | 复合域含 principal、操作、Provider、目标代次和稳定 scope 身份 | 跨用户/操作/代次复用裸 key 独立 | 裸 key 全局唯一或 HMAC 轮换导致误冲突 | 08 §5.6.2 | `FROZEN_CANDIDATE` | `REWORK (2026-08-04)` |
| B-D3-034 | 水位域 | 水位仅在完全相同 `scope_id` domain/kind 内按规定类型比较 | 同域整数单调推进 | 跨流、分区、scope、源代次或类型比较 | 08 §5.6.3 | `FROZEN_CANDIDATE` | `REWORK (2026-08-04)` |
| B-D3-035 | 运行状态双轴 | 历史 `evidence_level` 与当前 `availability` 独立 | host-verified 但当前 unavailable | 探活成功自动升级证据或故障抹除证据 | 08 §6.2/§10 | `FROZEN_CANDIDATE` | `REWORK (2026-08-04)` |
| B-D3-036 | 删除确认 | preview/selection/confirmation 绑定；仅单项已提交遗忘清理可版本化豁免 | 单项显式确认或合规清理豁免 | batch/full reset 豁免，或确认未绑定预览 | 08 §6.5 | `FROZEN_CANDIDATE` | `REWORK (2026-08-04)` |
| B-D3-037 | Scope 授权 | Service 在调用前认证并授权 scope，Provider 只消费绑定的内部上下文 | 授权 user/global/shard 请求进入 Provider | 缺 actor/authorization、越权或 scope_id 不匹配 | 08 §5.2/§6.6/§6.7 | `FROZEN_CANDIDATE` | `REWORK (2026-08-04)` |
| B-D3-038 | Scope 密钥轮换 | 稳定 `scope_id` 用于状态、水位和幂等；HMAC 仅用于披露 | k1→k2 后同一 scope 的水位和幂等记录连续 | HMAC 改变导致同一 scope 被当成新身份 | 08 §5.2/§5.6 | `FROZEN_CANDIDATE` | `REWORK (2026-08-04)` |
| B-D3-039 | Scope 授权操作/有效期 | 授权同时绑定 actor、scope、允许操作和过期时间 | `get_index_state` 与 `rebuild` 分别使用匹配且未过期授权 | 跨操作复用、过期或绑定不符仍调用 Provider | 08 §5.2/§5.4/§6.6/§6.7 | `FROZEN_CANDIDATE` | `REWORK (2026-08-05)` |
| B-D3-040 | 摘要密钥轮换闭环 | 历史验证密钥覆盖幂等/确认保留期；索引文本受控重建 | k1→k2 后同一幂等重放和确认安全验证，新 generation 统一使用 k2 | 因 key-id 变更重复副作用、静默确认或混用索引摘要密钥 | 08 §5.4/§5.6.1 | `FROZEN_CANDIDATE` | `REWORK (2026-08-05)` |

## 3. 跨轨待决矩阵

这些条目不是授权 B 轨代替其他轨道决策。Reviewer 应确认责任归属和失败时
是否阻断 Gate 0。

| ID | 待决事项 | B 已冻结边界 | 责任轨道 | 建议 Gate 结论 | 当前状态 |
|---|---|---|---|---|---|
| B-D3-X01 | `memory_status` 允许检索集合 | 发生在 RRF 前的硬过滤 | D/E | 未给集合时不得 `ACCEPTED` 全契约 | `DEFERRED_CROSS_TRACK` |
| B-D3-X02 | `sensitivity` 分级与可见范围 | 发生在 RRF 前；模型不得降级终判 | E | 安全部分需 E 专业关注 | `DEFERRED_CROSS_TRACK` |
| B-D3-X03 | 场景/作用域枚举与继承 | Provider 只消费 typed filter | D/E | 可接受 B 边界，枚举另案闭合 | `DEFERRED_CROSS_TRACK` |
| B-D3-X04 | full reset 授权、确认、级联 | Provider 只消费 resolved+authorized selector | D/E | 未闭合前 full reset 保持禁用 | `DEFERRED_CROSS_TRACK` |
| B-D3-X05 | IPC 数字错误码和 JSON 字段 | B 字符串错误语义不可改变 | C/D | 映射表必须单独评审 | `DEFERRED_CROSS_TRACK` |
| B-D3-X06 | SQLite/Outbox 水位类型与事务顺序 | SQLite 为真源；Vector 副作用可重放 | D | D4 实现前必须冻结 | `DEFERRED_CROSS_TRACK` |
| B-D3-X07 | `MemoryContext` 暴露字段 | 默认最小披露，raw diagnostics 留服务端 | C/D/E | IPC 契约前闭合 | `DEFERRED_CROSS_TRACK` |
| B-D3-X08 | Top-N/Top-K/类型配额 | 必须有界、版本化、进入评测记录 | B/E | 评测集前不得宣称最优 | `DEFERRED_CROSS_TRACK` |
| B-D3-X09 | Token 估算与截断 | Candidate 只携带非负估算和版本 | B/C | Context 实现前冻结 | `DEFERRED_CROSS_TRACK` |
| B-D3-X10 | Provider 同步/异步实现 | 绝对 deadline、取消、幂等语义不变 | A/B/D | D4 可选实现，不能改契约 | `DEFERRED_CROSS_TRACK` |
| B-D3-X11 | UDS 身份与 deadline 线格式 | 每次逻辑请求使用稳定且不复用的 ID，进入 Provider 前已有非空 `user_id` 与同一绝对 `deadline_at` | C/D | PR #18 `1b8111c1` 的 30 秒 Socket timeout 仅防阻塞；正式 IPC 不得沿用固定 ID、缺失用户或未消费的相对 deadline | `DEFERRED_CROSS_TRACK` |
| B-D3-X12 | Embedding→检索错误、预算与生命周期适配 | `cancelled`、`deadline_exceeded` 保持可区分；A 轨异常/相对 timeout 归一且不重置预算；进程级单例约束不得泄漏为业务语义 | A/B/D | PR #17 `5510f94d` 可作为 A 轨骨架；适配测试通过前不得声明完整检索链契约符合 | `DEFERRED_CROSS_TRACK` |

### 3.1 Git 集成预检

以下内容是 `2026-08-04` 的只读审计快照，只描述当时远端 SHA 的机械冲突结果，
不是当前实现依赖、合并基线或持续有效结论。后续判断必须重新同步默认分支并
生成新快照：

| 来源 | 结果 | 确定性处置 |
|---|---|---|
| PR #18 `feature/kaiming-uds-echo@1b8111c1` | 可机械合并 | 保持 D3-B 契约索引与 PR #18 UDS Spike 索引，两者语义仍按 `B-D3-X11` 分层 |
| PR #17 `feat/day4-bridge-provider-new@5510f94d` | `TECHNICAL_DEBT_REGISTER.md` 内容冲突 | 保留 `TD-003/TD-004` 与 `TD-A-005-01~05` 全部记录；不得选择单侧覆盖 |
| PR #19 `docs/C-d2-osagent-runtime@2797ae08` | `TECHNICAL_DEBT_REGISTER.md` 内容冲突 | 保留 `TD-003/TD-004` 与 `TD-007~009` 全部记录；不得选择单侧覆盖 |

本快照只记录冲突处置提示；不得以这些未合并 PR/SHA 作为实现基线，也不预先
merge、rebase、Review 或改写其他作者分支。

## 4. D4 非 VM 契约测试计划

这些测试可以在普通开发环境使用明确标记的 fake/in-memory Provider 验证
契约逻辑。它们只能证明 L0/L1 逻辑，禁止表述为真实 Vector Runtime 通过。

> D4-B PR #40 第三轮返工（2026-08-21）已合入最新 `origin/main@2b8bed7`，
> L0/L1_FAKE 共 131 个 pytest 用例并全部通过。T038 已覆盖 Rebuild `applied` / `outcome_unknown`
> 首次结果精确重放、同域冲突及跨 generation/scope 独立，Delete / Rebuild 写请求默认
> 从语义载荷复算摘要并 fail-closed；T039 已按 RFC 8785/JCS 数字边界输出；
> T044 已补 scope key 轮换后的 Rebuild 幂等连续性。T017 的 Provider 自身边界
> 已通过，但 SQLite resolved-ID ownership gate 属 Service，因此降为
> `PARTIAL_LOCAL`；T047 继续仅因删除确认历史 key/TTL Service 边界保持
> `PARTIAL_LOCAL`。这些结果只证明本地契约逻辑，不构成 L2 麒麟宿主证据；
> §5 B-D3-V001–V007 继续为 `DEFERRED_VM`。第三轮 `CHANGES_REQUESTED` 基于
> HEAD `f9297f9`；本轮返工尚待本地双轴审查、人工提交授权、推送与复审。


| ID | 目标 | 正向断言 | 负向/边界断言 | 层级 | 状态 |
|---|---|---|---|---|---|
| B-D3-T001 | 契约版本 | v1 被接受 | 未知主版本 fail closed | L0 | `PASS_LOCAL` |
| B-D3-T002 | 公共字段 | 完整 request/trace/user/deadline 通过 | 任一必填缺失拒绝 | L0 | `PASS_LOCAL` |
| B-D3-T003 | 向量校验 | 768 个有限数通过当前 capability | 维度错、NaN、Inf 拒绝 | L0 | `PASS_LOCAL` |
| B-D3-T004 | typed filter | 允许键生成稳定指纹 | 未知键、超长数组、通配用户拒绝 | L0 | `PASS_LOCAL` |
| B-D3-T005 | Upsert 幂等 | 同键同 payload 返回同逻辑结果 | 同键不同 payload 为 conflict | L1_FAKE | `PASS_LOCAL` |
| B-D3-T006 | Upsert 水位 | 新水位应用 | 旧水位拒绝覆盖 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T007 | Upsert 隔离 | 批内用户全匹配 | 任一跨用户项逐项拒绝 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T008 | Upsert 部分失败 | rejected 列表准确 | 模糊整批成功禁止 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T009 | Search 无命中 | 成功空 hits | 空结果误报 unavailable 禁止 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T010 | Search 排名 | SDK 顺序转 1 起始 rank | rank<=0 丢弃并计数 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T011 | Search 去重 | 同通道精确版本重复项保留最佳 rank | 不同版本被提前按 memory_id 合并或重复项多次贡献 RRF 禁止 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T012 | Search 隔离 | 目标用户命中进入回源 | 跨用户同向量诱饵丢弃 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T013 | SQLite 回源 | 当前版本生成 Candidate | 不存在/旧版本/已遗忘丢弃 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T014 | raw score | 有限数按标签保留 | NaN/Inf 丢弃；不参与融合 | L0 | `PASS_LOCAL` |
| B-D3-T015 | object/memory 类型 | 两字段独立序列化 | `memory_type=knowledge` 拒绝/迁移提示 | L0 | `PASS_LOCAL` |
| B-D3-T016 | Delete 单条 | resolved single item 幂等删除 | 空、通配、自然语言拒绝 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T017 | Delete 隔离 | Provider 拒绝 request/selector 用户不一致；SQLite 归属校验后只调用同用户删除 | Provider 越界模拟 SQLite ownership 或 Service 放行已知跨用户 resolved ID 失败 | L1_FAKE | `PARTIAL_LOCAL`：Provider 边界通过；SQLite ownership gate 待 Service |
| B-D3-T018 | Delete 重放 | Provider `not_matched` 经真源确认后归一为 already_absent | 伪造 deleted_count 或用 0 匹配掩盖越权禁止 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T019 | Full reset 门禁 | 授权+确认引用齐全才进入 | 任一缺失拒绝 | L0/L1_FAKE | `PASS_LOCAL` |
| B-D3-T020 | Rebuild 代次 | 新代次构建验证后请求激活 | 覆盖 serving generation 拒绝 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T021 | Rebuild 失败 | 保留旧 serving generation | 失败代次标 ready 禁止 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T022 | Rebuild 水位 | 快照/水位/计数一致 | 计数或水位不符不激活 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T023 | 激活能力 | capability false 选 maintenance/routing | 未验证却选 atomic 禁止 | L0 | `PASS_LOCAL` |
| B-D3-T024 | IndexState ready | 代次/Schema/水位完整 | 缺任一字段不允许 ready | L0 | `PASS_LOCAL` |
| B-D3-T025 | IndexState empty | 已验证空索引可查询空结果 | unknown record_count 伪装 0 禁止 | L0 | `PASS_LOCAL` |
| B-D3-T026 | 状态只读 | 前后对象和副作用计数不变 | 隐式初始化/修复失败测试 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T027 | RRF golden | 四个 ADR 样例误差在容限内 | 0 起始/重复贡献失败 | L0 | `PASS_LOCAL` |
| B-D3-T028 | RRF 稳定性 | 输入打乱输出不变 | 容器顺序影响结果失败 | L0 | `PASS_LOCAL` |
| B-D3-T029 | RRF 降级 | FTS5-only/Vector-only 有确定输出 | 双路失败伪造候选失败 | L0 | `PASS_LOCAL` |
| B-D3-T030 | Deadline | 同一绝对 deadline 派生逐层递减的剩余 timeout；已完成安全结果可 partial | 每层重置预算、忽略过期 deadline 或到期后启动新副作用失败 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T031 | 取消 | 协作取消返回明确 `cancelled`；不可中断副作用使用 `outcome_unknown` 协调 | 把取消折叠为超时，或把 outcome_unknown 当未执行失败 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T032 | 错误映射 | A/Bridge 异常归一后每个 B 字符串码语义稳定，取消与超时可区分 | SDK 私有异常穿透或 `BridgeCancelledError→deadline_exceeded` 失败 | L0/L1_FAKE | `PASS_LOCAL` |
| B-D3-T033 | 日志安全 | 仅 ID/hash/rank/计数/耗时 | 正文、凭据、跨用户数据出现失败 | L0 | `PASS_LOCAL` |
| B-D3-T034 | 兼容性 | 可选响应字段兼容 | 同 v1 改字段语义失败 | L0 | `PASS_LOCAL` |
| B-D3-T035 | 旧/当前版本组合 | 旧 v1 rank 1 被过滤后当前 v2 rank 2 保留 | v1 先胜出导致整个 memory_id 丢失失败 | L1_FAKE | `PASS_LOCAL` |
| B-D3-T036 | 用户级 IndexState | user-alpha 的代次、水位、计数只覆盖 alpha | 混入 beta 或返回 global scope 失败 | L0/L1_FAKE | `PASS_LOCAL` |
| B-D3-T037 | 分片级 IndexState | shard-a 与 shard-b 状态独立 | 同名 generation 跨 scope 合并失败 | L0/L1_FAKE | `PASS_LOCAL` |
| B-D3-T038 | 幂等复合域 | 同域同 hash 重放首次 `applied` / `outcome_unknown`；跨用户/操作/代次复用裸 key 独立；写请求语义摘要默认 fail-closed | 同域异 hash 未 conflict、跨域误 conflict、重放产生第二次副作用或摘要校验被旁路失败 | L0/L1_FAKE | `PASS_LOCAL` |
| B-D3-T039 | 规范摘要 | map/集合重排与 NFC 等价输入得到同 Digest | 有序数组重排、null/缺失或不同 key-id 被判相等失败 | L0 | `PASS_LOCAL` |
| B-D3-T040 | 水位比较域 | 同域整数/定宽串确定性推进 | 跨 scope/stream/partition/source-generation/kind 比较或数字串猜测失败 | L0/L1_FAKE | `PASS_LOCAL` |
| B-D3-T041 | 证据/可用性双轴 | host_verified+unavailable 与 untested+available 均可表达 | 任一轴自动改写另一轴失败 | L0 | `PASS_LOCAL` |
| B-D3-T042 | 删除确认/豁免 | 单项显式确认与合规 committed-forget 豁免通过 | batch/full reset 豁免、过期/错 preview 确认拒绝 | L0/L1_FAKE | `PASS_LOCAL` |
| B-D3-T043 | Scope 授权边界 | Service 传入绑定 actor_ref/authorization_ref/scope_id 的内部上下文 | 缺失、越权或 scope_id 不匹配时 Provider 不执行 | L0/L1_FAKE | `PASS_LOCAL` |
| B-D3-T044 | Scope 密钥轮换 | k1→k2 后稳定 scope_id 的状态、水位与幂等记录仍连续 | HMAC 改变导致重试、比较或 generation 隔离断裂 | L0/L1_FAKE | `PASS_LOCAL` |
| B-D3-T045 | Scope 操作隔离 | 匹配操作的未过期授权可执行对应请求 | `get_index_state` 授权调用 Rebuild，或 Rebuild 授权调用状态查询时 Provider 不执行 | L0/L1_FAKE | `PASS_LOCAL` |
| B-D3-T046 | Scope 授权过期 | 当前时间严格早于 `expires_at` 的授权可执行 | `expires_at` 相等或已过期时返回 `authorization_expired` 且 Provider 不执行 | L0/L1_FAKE | `PASS_LOCAL` |
| B-D3-T047 | 幂等/确认摘要轮换 | 历史仅验证密钥下的同域同语义重放返回记录结果，未过期确认可验证 | key-id 改变导致重复副作用，密钥不可用或确认过期仍执行 Delete 失败 | L0/L1_FAKE | `PARTIAL_LOCAL`：幂等轮换通过；删除确认 key/TTL 待 Service 边界 |
| B-D3-T048 | 索引文本摘要轮换 | SQLite 真源重算后仅完整校验的新 key generation 激活 | serving generation 混用 key-id 或未重建即激活失败 | L1_FAKE | `PASS_LOCAL` |

## 5. 目标麒麟 VM 验证队列（本轮跳过）

以下条目需要启动目标麒麟虚拟机或改变隔离测试环境。本轮不执行、不创建新
Runtime 日志，也不更改 KySec、systemd、数据库、Socket、SSH、NAT 或 VM 状态。

| ID | 目标 Runtime 事实 | 解除条件 | 状态 |
|---|---|---|---|
| B-D3-V001 | 当前固定 SDK raw score 的方向、范围和稳定语义 | 受控 identical/orthogonal/opposite 向量实验；证据绑定 commit/版本 | `DEFERRED_VM / TD-003` |
| B-D3-V002 | Provider v1 真实 upsert/search/delete 错误映射 | D4 Provider 实现与隔离环境就绪 | `DEFERRED_VM` |
| B-D3-V003 | deadline/取消在不可中断 SDK 调用下的真实行为 | D4 调度实现和故障注入方案就绪 | `DEFERRED_VM` |
| B-D3-V004 | 索引新代次构建、失败保旧与恢复 | D4 Collection Schema/重建器就绪 | `DEFERRED_VM` |
| B-D3-V005 | 原子 generation/Collection 切换能力 | 官方接口或宿主故障注入证据 | `DEFERRED_VM / TD-004` |
| B-D3-V006 | FTS5 + Vector + rrf-v1 端到端 | FTS5、Provider、SQLite 回源、RRF 均实现 | `DEFERRED_VM` |
| B-D3-V007 | Recall@K/MRR/nDCG/P95 | Gold Label、封存集、配置版本和评测脚本就绪 | `DEFERRED_VM` |

## 6. 本轮本地检查

| 检查 | 预期 | 当前结果 |
|---|---|---|
| ADR golden score 复算 | 4 个值及排序一致 | `PASS_LOCAL` |
| 契约 JSON 样例解析 | 5/5 可解析 | `PASS_LOCAL` |
| 文档引用存在 | 全部目标文件存在，索引相对链接可解析 | `PASS_LOCAL` |
| GitHub Review 获取 | PR #40 当前 Review 与被审提交可追踪 | 第三轮 `CHANGES_REQUESTED`；Reviewer `lovezy0730-create`；被审 head `f9297f9`；T038/T039 为核心返工 Gate |
| GitHub 跨分支兼容核对 | 历史 SHA 仅作为有日期的只读快照，不作为实现基线 | `AUDIT_SNAPSHOT_2026-08-04`；后续判断须重新同步默认分支 |
| `git diff --check` | 无 whitespace error | `PASS_LOCAL` |
| D4-B retrieval pytest | T001–T048 的 L0/L1_FAKE 当前实现 | `131 passed`；T017 Service ownership、T047 删除确认 key/TTL 为 `PARTIAL_LOCAL` |
| 仓库基线脚本 | 7/7，0 错误 | `BLOCKED_ENVIRONMENT`；2026-08-05 尝试未运行，宿主 WSL2 缺少 Hyper-V（`HCS_E_HYPERV_NOT_INSTALLED`），未启动 VM；历史 `PASS_LOCAL` 不作为本轮验证结果 |
| 工作区范围 | 只修改 B 轨契约、Fake、契约测试与状态矩阵 | `PASS_LOCAL`；PR #40 未扩展到 A/C/D/E 轨实现，最终 Review 状态以 PR 最新 HEAD 为准 |

## 7. Reviewer 记录

### 当前 Review

- Reviewer：`lovezy0730-create`
- 审查提交：`8a7914bc`
- 提交时间：`2026-08-04T14:29:27Z`
- GitHub 结论：`CHANGES_REQUESTED`
- 矩阵结论：`REWORK`
- 返工范围：P0-01 至 P0-03、P1-01 至 P1-04 及三项冻结建议

### 第二轮 Review

- Reviewer：`lovezy0730-create`
- 审查提交：`639dbcd`
- 提交时间：`2026-08-04T17:37:24Z`
- GitHub 结论：`CHANGES_REQUESTED`
- 矩阵结论：`REWORK`
- 返工范围：P0-01～02、P1-01～02、P2 清理项；D1/D2 历史审查文案仅核对，
  不在 B 轨 PR 中改写

### 第三轮 Review

- Reviewer：`lovezy0730-create`
- 审查提交：`9c808cd`
- 提交时间：`2026-08-05T09:10:00Z`
- GitHub 结论：`CHANGES_REQUESTED`
- 矩阵结论：`REWORK`
- 返工范围：R3-P0-01（PR 计数、head 与审查表述同步）、R3-P1-01（授权操作与
  有效期绑定）、R3-P1-02（摘要密钥轮换闭环）。PR 正文和修复报告在本轮经用户
  授权提交、推送后更新；不以“一名 approval”替代任务卡要求记录的 D/E 专业
  关注覆盖。

### 复审模板

- 契约版本：`vector-retrieval/v1`
- 审查提交：`<commit after user-approved commit>`
- 结论：`PENDING_REVIEW`
- P0 返工项：无 / `<ID 列表>`
- D 关注项（如适用）：Provider / SQLite / Outbox / IPC / `<B-D3-X ID 列表>`
- E 关注项（如适用）：用户隔离 / 敏感度 / 冲突 / 遗忘 / 评测 /
  `<B-D3-X ID 列表>`
- 允许进入 D4：是 / 否
- 说明：

在一名独立、非作者 Reviewer 实际给出 `APPROVED`，且 P0、验证、证据和项目
任务卡指定的 D/E 专业关注项全部记录覆盖前，作者不得把 ADR 状态改为“已采纳”，
不得把契约状态改为“已接受”，不得声明 Gate 0 PASS。本矩阵不修改项目任务卡
或共享治理文档，也不将单一 approval 自动表述为 Gate 通过。
