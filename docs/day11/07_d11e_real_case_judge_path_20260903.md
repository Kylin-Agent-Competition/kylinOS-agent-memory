# D11E 真实案例脚本与评委操作路径（同一虚拟机全功能联调验收）

## 文档定位

- 本文件是 D11E 开工工作清单（`docs/day11/04_d11e_business_acceptance_worklist_20260903.md`）工作项 3 的交付物：把 D11E 业务验收落到「评委可复跑的真实案例卡」。每张卡给出目标、入口/操作步骤、合成脱敏输入、预期业务行为、判定证据与通过标准。
- 案例卡与 C-D11 5 步主演示编排（`memory-client/qml/pages/D11DemoOrchestratorPage.qml`，Step1 preChat → Step2 跨会话 → Step3 Tool → Step4 conflict/lifecycle → Step5 forget）对齐，并引用对应 E 轨既有 L0/L1 测试作为可复跑锚点。
- 证据级别：本文件卡片在麒麟 VM、同一 Commit（`origin/main` 最新）上执行前一律 `UNVERIFIED`；本地可先行复跑的是每卡「可复跑锚点」列的 pytest。
- 数据纪律：仅用合成/脱敏样例（user_id 形如 `user_d11e_*`）；不得引入真实用户正文或敏感载荷。

## 验收前置条件（同 Commit 同 VM）

1. 基线与快照：D11D 统一麒麟 VM/快照、同一 Commit（`git rev-parse HEAD` 记录）、`VERSION_MAP`、数据库迁移头与 Vector Engine 版本记录。
2. 服务链路：`kylin-memory.service` active、UDS socket 存在、health 分项正常（或明确 degraded 且有日志）；C 轨 memory-client/D11 编排页可启动；B 轨检索/删除真实输出可调用；A 轨 SDK 状态可查。
3. 证据采集约定：每卡记录 `request_id/trace_id`、JSON 日志、DB 状态（`source_events`/`memory_*`/`forget_*` 表行）、检索输出与 UI 状态；日志与诊断不得含记忆正文、候选标识、用户标识或敏感配置。

## 案例卡总览

| 卡号 | 业务主题 | 入口路径 | 对应 L0/L1 锚点 |
|---|---|---|---|
| D11E-RC-01 | 跨会话偏好沉淀与召回（含临时 vs 长期） | Step1 preChat + Step2 跨会话 | `test_preference_business_flow_d7e.py` |
| D11E-RC-02 | Tool 事实型知识与失败不沉淀 | Step3 Tool | `test_knowledge_domain_mapping_d8e.py`、`test_candidate_admission_gate_d5e.py` |
| D11E-RC-03 | 冲突对比与可解释裁决 | Step4 conflict.compare | `test_conflict_resolution_policy_d8e.py` |
| D11E-RC-04 | 生命周期状态（提升/过期/归档） | Step4 lifecycle.status | `test_lifecycle_policy_d8e.py` |
| D11E-RC-05 | 精准遗忘预览→确认→执行→复检 | Step5 forget Preview→Execute | `test_forgetting_policy_d10e.py`、`test_forget_persistence_d10d.py` |
| D11E-RC-06 | 负向：跨用户隔离零影响 | 任意步骤注入他人 user_id | `test_multisource_security_adversarial_d6e.py`、`test_cross_session_business_case_d5e.py` |
| D11E-RC-07 | 负向：敏感内容不进正文/日志/审计；遗忘后检索排除 | Step5 + 日志断言 | `test_multisource_security_adversarial_d6e.py`、`test_forgetting_policy_d10e.py`、`test_retrieval_business_policy_d9e.py` |

## 案例卡明细

### D11E-RC-01 跨会话偏好沉淀与召回
- 目标：验证「显式长期偏好沉淀 → 下一次会话召回」，同时「临时指令不进入稳定长期偏好」。
- 操作：Step1 preChat 注入（三路原文隔离验证）；Step2 跨会话（session-demo-0001 → session-demo-0002）构造包含显式长期偏好表述的对话；随后在偏好编辑器确认；再发起一次依赖该偏好的查询。
- 输入（合成）：`user_d11e_rc01`；显式长期偏好示例「以后开会请把会议纪要按议题归档」；临时指令示例「这次先别归档」。
- 预期：显式长期偏好以 `memory_status=candidate→（确认后）active`、`version=1` 沉淀并在后续会话的差异化 Context 中可解释召回；临时指令不产生稳定长期条目；跨会话 Context 差异为正对照。
- 判定证据：trace 关联、DB 中 preference 行（key/scope/version/status）、Step2 Context 差异、偏好编辑器状态。
- 通过标准：长期偏好可召回且可解释；临时指令无稳定长期写入；无跨用户/敏感泄露。
- 当前状态：L0/L1 锚点已覆盖（535 passed）；本卡 L2 待执行（UNVERIFIED）。

### D11E-RC-02 Tool 事实型知识与失败不沉淀
- 目标：验证真实 Tool 结果沉淀为知识且高于模型自述；Tool 失败/取消/超时不沉淀为稳定记忆。
- 操作：Step3 Tool（memory_search 等）真实成功一次、构造失败/取消一次。
- 输入（合成）：`user_d11e_rc02`；Tool 结果片段（脱敏）。
- 预期：成功 Tool 产生六类知识中相应类型（如 fact/workflow）且带 `source_event_id` 证据引用；失败/取消/超时事件被来源安全门禁/候选治理拒绝，不进入稳定记忆；safeMessage 不泄漏正文。
- 判定证据：Tool 事件日志、候选治理拒绝原因、DB 知识行与证据引用、UI 错误提示（脱敏）。
- 通过标准：知识可解释、证据可溯源；失败事件零稳定写入；无正文/敏感泄漏。
- 当前状态：L0/L1 锚点已覆盖；本卡 L2 待执行（UNVERIFIED）。

### D11E-RC-03 冲突对比与可解释裁决
- 目标：验证同一用户两段矛盾/不一致记忆被检测并进入对比，裁决可解释且裁决值非模型生成。
- 操作：Step4 conflict.compare（构造冲突双方）。
- 输入（合成）：`user_d11e_rc03`；两条矛盾事实。
- 预期：candidates 展示（size>=2）；按六档证据优先级给出 KEEP_LEFT/KEEP_RIGHT/COEXIST/DEFER/REJECT 之一；`resolution_status` 由规则引擎产出（resolved_auto/resolved_manual/unresolvable），无模型生成终判。
- 判定证据：冲突对比页状态、`service/conflict_resolution_policy.py` 裁决、DB conflict 行。
- 通过标准：裁决可解释、可复算；跨用户不产生冲突。
- 当前状态：L0/L1 锚点已覆盖；本卡 L2 待执行（UNVERIFIED）。

### D11E-RC-04 生命周期状态
- 目标：验证提升/过期/归档请求产生正确 lifecycle 决策，且过期/归档后不再进入标准上下文/检索。
- 操作：Step4 lifecycle.status（构造短中长期条目与过期条件）。
- 输入（合成）：`user_d11e_rc04`。
- 预期：PROMOTE/DEMOTE/EXPIRE/ARCHIVE_REQUEST 决策与 `memory_status` 计划一致；expired/removed 在标准检索/上下文被排除；deprecated 仅显式 history/audit 模式可检索且不进入标准 M2 指标。
- 判定证据：lifecycle 决策输出、DB 状态行、Step2/检索复检输出。
- 通过标准：状态迁移正确；排除生效；无正文/敏感泄漏。
- 当前状态：L0/L1 锚点已覆盖；本卡 L2 待执行（UNVERIFIED）。

### D11E-RC-05 精准遗忘预览→确认→执行→复检
- 目标：验证遗忘业务闭环：目标解析精准、先预览再确认、确认凭据有效期内执行、执行后检索/上下文排除、硬删除无可检索明文残留。
- 操作：Step5 forget Preview→Execute（single_item 与 session 各一）；构造错误/过期凭据一次验证 fail-closed；执行后按真源/Vector/FTS5 复检。
- 输入（合成）：`user_d11e_rc05`；选择遗忘条目与会话。
- 预期：Preview 生成 `resolved_target_ids/affected_count`（禁模型生成）；状态机 pending→previewing→awaiting_confirmation→executing→completed；错误/过期凭据 fail-closed 且不发出 forget.execute；软删除后标准查询排除目标；硬删除后 SQLite/Vector/FTS5/日志/审计无可检索明文（审计不含正文与原始 selector）。
- 判定证据：Preview/Execute 状态与凭据校验日志、forget_plan/forget_audit 行、删除后检索/上下文复检、B 轨删除残留率口径。
- 通过标准：误删=0、漏删=0、跨用户=0；硬删除无明文残留（Critical 项）。
- 当前状态：L0/L1 锚点已覆盖；本卡 L2 待执行（UNVERIFIED；依赖 D10B/D11D 删除链路真实输出）。

### D11E-RC-06 负向：跨用户隔离零影响
- 目标：验证任何写入/检索/遗忘都不跨用户。
- 操作：以 `user_d11e_rc06a` 沉淀数据，再以 `user_d11e_rc06b` 检索/遗忘目标。
- 输入（合成）：两个独立 user_id。
- 预期：user_b 检索不到 user_a 记忆；user_b 遗忘对 user_a 零影响；审计含 `isolation_violation` 语义（如有违规）或仅记录原因码。
- 判定证据：检索输出、forget 影响计数、审计行。
- 通过标准：跨用户命中 count=0、rate=0（Critical 项）。
- 当前状态：L0/L1 锚点已覆盖；本卡 L2 待执行（UNVERIFIED）。

### D11E-RC-07 负向：敏感过滤与遗忘后排除
- 目标：验证敏感内容不进正文/日志/审计；已遗忘对象不重新注入检索或 MemoryContext。
- 操作：注入含 S-01..S-09 风格占位（如 `sk-demo-*`）的样例并触发日志/审计；遗忘目标后重查。
- 输入（合成）：密钥占位、证件占位（仅演示用）。
- 预期：日志/审计/UI 均以脱敏占位或 ID 引用出现，无完整敏感原文；遗忘后重查不再命中目标。
- 判定证据：日志脱敏断言、审计内容、检索/上下文复检。
- 通过标准：任一敏感/遗忘后命中 = Critical；目标为 0。
- 当前状态：L0/L1 锚点已覆盖；本卡 L2 待执行（UNVERIFIED）。

## 评委判定汇总表（验收时填写）

| 卡号 | 执行结果（通过/失败/阻塞） | 关键证据（trace/日志/DB/检索/UI） | 备注 |
|---|---|---|---|
| D11E-RC-01 | 待执行 | — | L2 待 VM |
| D11E-RC-02 | 待执行 | — | L2 待 VM |
| D11E-RC-03 | 待执行 | — | L2 待 VM |
| D11E-RC-04 | 待执行 | — | L2 待 VM |
| D11E-RC-05 | 待执行 | — | L2 待 VM |
| D11E-RC-06 | 待执行 | — | L2 待 VM |
| D11E-RC-07 | 待执行 | — | L2 待 VM |

## 结论口径

- 在取得同 Commit 同 VM 实测证据前，本文件所有案例卡结论保持 `UNVERIFIED`，不作为 D11E 完成证据。
- 案例卡对应的 L0/L1 业务锚点已在 `origin/main@0820036` 复跑通过（535 passed，见 `docs/day11/05_d11e_l0l1_regression_20260903.log`）。