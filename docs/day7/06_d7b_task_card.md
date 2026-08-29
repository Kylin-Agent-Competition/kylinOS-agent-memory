# D7B 任务卡：偏好结构化过滤、场景匹配与检索解释

| 字段 | 内容 |
|---|---|
| 任务编号 | D7B |
| 责任轨道 | B（Vector、FTS5、RRF、检索、索引与检索评测） |
| 基线 | `origin/main` `4926345b`（2026-08-29 同步） |
| 目标 | 偏好检索只返回当前有效且场景、作用域匹配的版本，并提供确定性检索解释。 |
| Reviewer | 一名独立、非作者 Reviewer |

## 权威目标与验收口径

15 天 75 项施工台账为 D7B 指定三项交付：

1. 实现偏好结构化过滤和场景匹配；
2. 验证当前版本、作用域和失效时间过滤；
3. 提供偏好检索解释字段。

验收要求为：偏好检索仅返回当前有效、场景匹配的版本。本任务同时按冻结
`vector-retrieval/v1` 契约执行用户、状态、敏感度、对象类型与冲突硬过滤。

## 修改范围

- `memory-service/retrieval/fusion.py`：扩展 SQLite 回源真值承载，执行偏好版本、有效期、场景和作用域硬过滤，生成解释字段，并记录实际降级通道。
- `memory-service/retrieval/preference_scope.py`：直接复用 E 轨 `PreferenceScope` 五值，冻结 `preference-scope-terms/v1` 映射并执行 fail-closed scope 匹配。
- `memory-service/retrieval/rrf.py`：提供共享 RRF 分项纯函数，确保最终分数和解释字段使用同一 `rrf-v1` 公式与校验。
- `memory-service/tests/retrieval/`：覆盖当前版本、半开有效期、UTC、场景、作用域、解释与降级回归。

## 明确不修改的范围

- 不实现 A、C、D、E 轨代码、契约或业务策略。
- 不新增 SQLite `current_version` 指针、`previous_version_id` 版本链、Repository、Migration 或 Outbox 接线。
- 不修改冻结 Provider / IPC Schema；D7B 继续通过既有 `fuse_retrieval(...)` 和 `retrieve_graceful(...)` 接缝消费结构化输入。
- 不实现 D8 知识关系过滤、D9 业务重排、Top-K/token 预算或检索指标。
- 不把本地纯函数测试冒充麒麟宿主或完整持久化链路证据。

## 输入与输出语义

### 当前版本

- 候选版本必须在 SQLite 回源真值中标记 `is_current=true`。
- 同一偏好存在多个 current 版本时失败关闭，任何版本均不返回。
- Knowledge 保持既有选择行为，D7B 不扩张知识检索语义。

### 有效期

- `valid_from`、`valid_to` 必须带时区，并在回源边界归一化到 UTC。
- 有效区间采用半开语义：`valid_from <= as_of < valid_to`；空边界表示该侧不受限。

### 场景与作用域

- 有 `scene_id` 的偏好只匹配 `allowed_scene_ids` 中显式允许的场景。
- 无 `scene_id` 的偏好仅在 `include_unscoped=true` 时可见；空场景集合不是通配。
- 空场景集合下，`include_unscoped=false` 为零命中；`include_unscoped=true` 只允许 unscoped。
- SQLite 真值必须携带显式 `preference_scope`，直接复用 E 轨冻结的 `global/topic/tool/session/time_window` 五值；缺失或非法 identity 失败关闭。
- `preference-scope-terms/v1` 一一映射 `topic/tool/session/time_window` 到同名必要 term；只有显式 `global` 可以没有 term。
- query 或 truth 出现未知 scope key 均拒绝；非 global 缺少必要 key、空值或无交集均失败关闭。
- 多 key 为 AND、同 key 多值为 OR；显式 global 若携带 scope terms 视为不一致并失败关闭。

### 解释字段

返回的偏好候选包含：

- `algorithm_version="rrf-v1"`、`rrf_k` 与逐通道 `rrf_terms`；
- 实际 `degraded_channels` 与 `rerank_version=null`；
- `preference-filter/v2` 与 `preference-scope-terms/v1`；
- 已验证的 `preference_scope` identity，以及 current version、validity、scene、scope 通过结果。

解释不包含用户正文、原始可执行过滤表达式或 Provider 异常文本。

## 验收与验证

| 层级 | 检查 | 结果 |
|---|---|---|
| L0 | D7B 相关 RRF/fusion/degradation 测试 | `52 passed in 0.68s` |
| L1 | `memory-service/tests/retrieval` 完整回归 | `233 passed in 1.30s`；基线为 209，新增 24 项 |
| 静态 | `git diff --check` | PASS |
| Review 返工 | PR #66 High/Medium | scope identity、unknown key、Scene 空组合与 main 同步均已修复；Standards / Spec 双轴复审均 `0 findings / PASS`，待 GitHub 复审 |
| L2/L3 | 麒麟宿主 / 完整持久化链 | 不适用于本次纯融合实现；D 轨版本持久化仍为跨轨依赖 |

## 安全与失败语义

- 用户、对象类型、状态、敏感度、版本、有效期、场景、作用域和未解决冲突均在 RRF 聚合前过滤。
- 偏好 current version 不唯一、scope identity/必要 term 缺失、unknown key、scope 上下文不匹配或场景未授权时均失败关闭。
- 单通道故障保持既有 graceful degradation；解释只记录通道名，不暴露异常正文。
- RRF 分项和总分共享同一纯函数，避免解释与排序发生公式漂移。

## 已知限制与跨轨依赖

- 默认分支尚无 D 轨 `current_version` 指针和 `previous_version_id` 版本链持久化实现；D7B 只消费调用方提供的 SQLite 真值信号，不能声明完整端到端版本链已验证。
- 全服务测试在 Windows 上仍受 AF_UNIX、`os.getuid`、受限默认目录和迁移环境影响；既有 D7-A `TTL=0` 缓存用例也可独立复现失败。这些问题不在 B 轨授权范围内，本任务不修改。

## 回滚

回滚本批次提交即可恢复默认分支上的 D6 融合行为；本任务不包含数据库迁移、配置或外部资源变更。
