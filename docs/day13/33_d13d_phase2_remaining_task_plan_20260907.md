# D13D Phase 2 剩余任务计划（2026-09-07）

## 状态与边界

| 项 | 值 |
| --- | --- |
| 文档状态 | `PLANNING / NON-FORMAL` |
| 计划基线 | PR #160 @ `f674c199c7ffc4f07d6f7f8114063fc28b48cb75` |
| 当前主要阻塞 | 无工程阻塞；等待非作者独立终审 |
| 已有 Forget 证据 | FTS + Vector dual-channel `5/5 / NON-FORMAL CANDIDATE` |
| 目标 | final review；APPROVE 后 merge 并记录 `I3B_COMPLETION_MERGE_SHA` |
| 禁止升级 | 不宣称 formal raw / Seal / Runner Gate / `D13D_FROZEN` |

本计划只覆盖 PR #160 的 Phase 2 剩余收口。Phase 3 preparation 可以并行推进，
但 Phase 3 formal execution 必须等待 Phase 2 final APPROVE、merge 和
`I3B_COMPLETION_MERGE_SHA` 之后才开始。

## 当前事实

2026-09-07 执行更新：Stage 1 preparation、Stage 2 dual-channel implementation、
Stage 3 的 5/5 FTS + Vector E2E 以及 Stage 4 的最终回归、状态同步与 CI 已完成。
当前执行记录与最小证据索引见 `26_` §9.10 和 PR #160 comment `5570965897`。
本文件剩余表格保留为历史执行计划，不再新增状态层。

1. Reviewer E 已在 `57466cc` 确认上一轮 HIGH/MEDIUM 闭合，且无新增阻塞 finding。
2. `29_` / `30_` 冻结口径要求完整 Forget 5/5 必须有真实 Vector 双通道证据；
   FTS-only 证据只能标记为 partial non-formal。
3. G5 已有 VM 真实 Embedding smoke，G6 已有 `0k1.1` headers / `vector_bridge_cli`
   compile/link/smoke preparation evidence，但都还没有进入 Forget 双通道 E2E。
4. 当前 `OBSERVATION_PROFILES` 只注册 FTS observer；真实 Vector provider /
   Embedding provider 尚未注入 Forget E2E observer。
5. `SqliteVectorSnapshotReader` 对 active preference 保持 fail-closed；
   若某个 Forget mode 后仍存在 active preference，必须先与 E 确认 Vector
   rebuild 语义，不能静默绕过。
6. `app.py` production default 仍未接线 Embedding/Forget consumer；这属于已登记的
   production seam 边界，不影响 validation profile 的显式注入路径。

## 执行阶段

### Stage 0：契约核对与执行前风险清点

| ID | 任务 | 输出 | 完成标准 |
| --- | --- | --- | --- |
| P2-T0.1 | 复核 `29_` §6/§8、`30_` §6/§7、`31_` 的冻结 Gate 和禁止项 | 无代码变更 | 确认新增实现不得改 Dataset、Gold、Threshold、Runner、冻结 IPC/Schema/错误码 |
| P2-T0.2 | 在 VM 只读清点五个 Forget sample 的 target kind、knowledge/preference 分布和删除后 active preference 状态 | 风险清单 | 明确每个 mode 是否具备 Vector rebuild 前提；若存在矛盾，先请求 E 裁定 |
| P2-T0.3 | 确定 dual-channel observer 的 profile 名、字段和 provenance schema | [34_d13d_dual_channel_observation_contract_draft_20260907.md](34_d13d_dual_channel_observation_contract_draft_20260907.md) | per-channel 记录 FTS/Vector 的 pre-delete hit、realtime residual、rebuild residual、snapshot/watermark/receipt provenance |
| P2-T0.4 | 设计 fail-closed 负路径 | [34_d13d_dual_channel_observation_contract_draft_20260907.md](34_d13d_dual_channel_observation_contract_draft_20260907.md) §5 | 覆盖 embedding unavailable、vector unavailable、pre-delete miss、delete/rebuild 失败、outbox 未 ACK、scope violation |

出口条件：E 或仓库冻结文档无需进一步澄清；若必须裁定，先形成 comment/evidence 再进入 Stage 1。

### Stage 1：G5/G6 真实前置收口

| ID | 任务 | 输出 | 完成标准 |
| --- | --- | --- | --- |
| P2-T1.1 | 固化 VM 上的真实 `kylin_embedding` build/run 参数 | build provenance | 记录源码 commit、compiler、model、dimension=768、norm、socket/library 路径 |
| P2-T1.2 | 固化 `0k1.1` headers 和 `vector_bridge_cli` build/link 参数 | build provenance | 禁止复用 `0k0.7`；记录 headers SHA、binary SHA、engine version、smoke exit code |
| P2-T1.3 | 在隔离目录完成真实 Vector create/upsert/search/delete/rebuild smoke | smoke evidence | 每一步都有 stdout/stderr、exit code、binary/header/engine SHA |
| P2-T1.4 | 验证真实 Embedding + `SqliteVectorProvider`/`VectorCliClient` 的最小 upsert/search/delete 链路 | integration smoke | 输出维度和 scope 与契约一致；失败必须 fail-closed |

出口条件：G5/G6 只能标为 `PREPARATION CLOSED`，不能直接标为 formal closure 或 5/5 完成。

2026-09-07 Stage 1 preparation 已按 r4 记录闭合，证据根目录
`evidence/phase3-prep/d13d_stage1_integration_smoke_20260907_r4/`，提交
`8801763`。该结果仍是 `PREPARATION_NON_FORMAL`，不等于 Vector dual-channel
formal closure。

### Stage 2：实现 Vector 双通道 observer 与 consumer

| ID | 任务 | 输出 | 完成标准 |
| --- | --- | --- | --- |
| P2-T2.1 | 实现独立 dual-channel observer，不覆盖现有 FTS profile | 新 observer 模块 | pre-delete probe 先分别命中 FTS 与 Vector；任一通道未命中则 fail-closed |
| P2-T2.2 | 将真实 Embedding/Vector provider 显式注入 validation profile | `OBSERVATION_PROFILES` 更新 | 未知 profile 仍 fail-closed；只允许显式 approved profile 进入 dispatch |
| P2-T2.3 | 将 `forget.executed` 消费链扩展到真实 Vector provider | consumer wiring | 仍走 `OutboxWorker → OutboxRouter → build_forget_consumer`；worker ACK 后才进入 realtime |
| P2-T2.4 | 实现真实 Vector full rebuild/requery | rebuild observation | 新 generation 激活后查询；保留 generation、snapshot、watermark、binary/provider provenance |
| P2-T2.5 | 保留 FTS + Vector 联合 residual 判定 | raw/receipt schema | residual 取双通道真实结果；禁止用一通道 miss 掩盖另一通道 residual |
| P2-T2.6 | 补齐 L1 契约和负路径测试 | tests | 覆盖正向双通道、单通道失败、未命中、ACK 失败、preference fail-closed、scope mismatch |

实现约束：

- 不在 production `app.py` 默认路径隐式开启 Forget/Embedding；
- 不用 Fake provider 或 deterministic embedding 生成 VM 证据；
- 不让 observer 自己删除 FTS/Vector 后自证成功；
- 不把 consumer 返回值当成 worker ACK，必须以 outbox 行删除为 ACK 语义。

### Stage 3：在 V2 binding 上重跑完整 5/5 dual-channel E2E

| ID | 任务 | 输出 | 完成标准 |
| --- | --- | --- | --- |
| P2-T3.1 | 建立新的 isolated evidence root，不复用 r5 | evidence root | README 写明 `PHASE2_NON_FORMAL / DUAL_CHANNEL_CANDIDATE`，含 SHA256SUMS |
| P2-T3.2 | 每 sample 使用 fresh runtime clone 和唯一 generation/collection namespace | execution logs | 禁止 sample 复用 serving collection；记录 runtime DB、collection、generation SHA |
| P2-T3.3 | 重跑 `single_item/session/topic/time_window/full_reset` 五个真实 dispatch | receipts + raw candidate | preview → execute → real outbox ACK → FTS/Vector realtime → FTS/Vector rebuild → receipt |
| P2-T3.4 | 验证 controls 和 residual | per-sample summary | `missed_target_items=0`、`wrongly_deleted_items=0`、`cross_user_violation_count=0`、dual-channel realtime/rebuild residual=0 |
| P2-T3.5 | 记录 all-channel provenance | `SHA256SUMS` + summary | receipts、logs、FTS/Vector snapshot/watermark、embedding/vector build SHA、binding DB SHA 全部可复核 |
| P2-T3.6 | 失败样本保留原始输出 | failure archive | 不删除、不改写、不重试到 pass；失败进入 Bug/Blocker 路由 |

出口条件：5/5 dual-channel E2E 全部可复核。只有此时才允许更新 `26_` §9.9 和新增
execution record，把 P2-B 从 `BLOCKED_PENDING_VECTOR_DUAL_CHANNEL` 改为闭合。

### Stage 4：最终回归、状态同步与终审交接

| ID | 任务 | 输出 | 完成标准 |
| --- | --- | --- | --- |
| P2-T4.1 | 重跑 Phase 2 targeted regression | pytest 结果 | 覆盖 adapter、outbox router、provider delete/rebuild、state binding、observability、vector snapshot |
| P2-T4.2 | 重跑 Runner/Gold/trust contract regression | pytest 结果 | `test_d13e_formal_eval` 契约套件全绿 |
| P2-T4.3 | 执行 Gold-isolation audit | audit evidence | 生产/adapter 路径不读 Gold、expected、threshold；禁止词扫描和代码路径复核均通过 |
| P2-T4.4 | 同步 `26_` / `29_` / `30_` / `32_` / PR Body | docs | exact HEAD、P2-A/P2-B/P2-C 状态、剩余边界一致 |
| P2-T4.5 | 运行 repository baseline、`git diff --check` 和 CI | CI evidence | final exact HEAD 三项 CI 全绿 |
| P2-T4.6 | 更新 `P0-I3b-completion = READY_FOR_REVIEW` | status record | 仅在 Stage 3/4 全部通过后更新 |
| P2-T4.7 | 请求 Reviewer E final review | PR comment | 附 evidence root、commit、测试、审计和边界声明 |

出口条件：Reviewer E final `APPROVE` 后才 merge PR #160 并记录
`I3B_COMPLETION_MERGE_SHA`。

## 依赖与风险

| 风险 | 处置 |
| --- | --- |
| preference 不属于当前 Vector snapshot 语义，可能阻塞部分 mode 的 full rebuild | Stage 0 必须先按 sample 只读清点；有矛盾时请求 E 裁定，不静默绕过 |
| 真实 Vector engine 与 SDK ABI 环境差异 | 只使用 `0k1.1` headers 和当前 HEAD bridge；禁止复用旧 binary/header |
| Embedding provider 可用但 Vector provider 不可用 | 整个 dispatch fail-closed，不降级为 FTS-only 成功 |
| observer 旁路删除导致假阴性 | realtime/rebuild 只能发生在真实 consumer ACK 之后，并保留 outbox/consumer provenance |
| 旧 FTS r5 证据被误读为完成 | 所有文档和 PR Body 继续标 `PARTIAL NON-FORMAL`，直到 dual-channel 5/5 完成 |
| final regression 通过但状态漂移 | Stage 4.4 在 CI 前同步文档和 PR Body，确保五方口径一致 |

## Definition of Done

1. 五个 Forget sample 均有真实 FTS + Vector pre-delete 正向命中。
2. 五个 sample 的 `forget.executed` 均经真实 Outbox Worker / Router / consumer ACK。
3. 五个 sample 的双通道 realtime residual 和 full rebuild/requery residual 均为 0。
4. 跨用户控制无违规，wrongly deleted 和 missed target 均为 0。
5. 所有 receipts/logs/provenance 有 SHA-256，且 evidence root 可独立复核。
6. 最终 exact HEAD 的 targeted regression、Runner contract regression、
   Gold-isolation audit、`git diff --check` 和 CI 全绿。
7. `26_` / `29_` / `30_` / `32_` / PR Body 状态一致。
8. `P0-I3b-completion = READY_FOR_REVIEW`，等待 Reviewer E final APPROVE。

## 明确不做

- 不选择 formal `tested_commit`；
- 不执行正式 VM 17 raw；
- 不生成 Review Seal / Execution Seal / attestation；
- 不执行 Runner Gate 0-10；
- 不标记 `D13D_FROZEN` / `HOST_VERIFIED` / `FORMAL PASS`；
- 不修改 Dataset、Gold、Threshold、Runner 或冻结契约。
