# D11E UI 文案、证据与安全确认静态审查（2026-09-03）

## 文档定位

- 本文件是 D11E 开工工作清单（`docs/day11/04_d11e_business_acceptance_worklist_20260903.md`）工作项 4 的交付物：对 D11 主演示编排的 UI 文案、展示证据与安全确认做静态审查（先行层）。
- 审查方法：静态通读 C 轨 QML 文案/状态绑定与 ViewModel 语义，与 E 冻结业务契约和安全规则比对；**不执行运行态**。
- 结论口径：运行态（真实麒麟 VM、同一 Commit）证据未取得前，凡涉及「实际显示正确/安全确认生效」的结论一律 `UNVERIFIED`；本文件只给出静态层判定，不修改任何 C 轨代码。

## 审查对象与依据（静态）

- 对象：
  - `memory-client/qml/main.qml`（导航入口与窗口标题）。
  - `memory-client/qml/pages/D11DemoOrchestratorPage.qml`（5 张 Step Card + 安全与隔离汇总面板）。
  - `memory-client/src/view_models/memory_view_model.{h,cpp}`（stage / credential / TTL / selector 清除语义）。
  - `memory-client/README.md` D11-C 章节与 `docs/project-management/PR116_body.md`（口径声明）。
- 依据：D11E 验收矩阵（`docs/day11/06_d11e_acceptance_matrix_20260903.md`）；E 冻结契约（D3 §3/§5/§7）与安全验收（SEC-CTX-01、SEC-FORGET-01..05、SEC-UI-*、SEC-SENS-*）；C 轨 L0 测试 `tests/test_d11c_e2e_orchestrator.cpp`（14 slots）与 `tests/test_d11c_qml_load.cpp`（MEDIUM-01/03）。

## 一、UI 文案与业务事实一致性（静态）

| 页面元素 | QML 文案要点 | 对应业务事实 / 契约 | 静态判定 |
|---|---|---|---|
| 编排页标题 | D11 End-to-End Demo Orchestrator (同一 Commit / 同一 VM) | D11 同 VM 全功能联调目标 | 一致（演示定位标注明确） |
| Step 1 | 普通聊天 (Pre-Chat → Post-Turn)；说明引用 D5 Vertical Link、三路原文隔离、turn.finalized/is_end | D5-C 主路径与原文隔离（SEC-CTX-01） | 一致（L0 A1/A2 锚点） |
| Step 2 | 跨会话召回 (同一 user / 不同 session)；期望 context 含持久化 preference/knowledge，session 不回退 | D5/D7/D9 跨会话偏好与知识召回 | 一致（L0 B1 锚点） |
| Step 3 | Tool 调用 (Tool Result 入记忆)；错误路径 safeMessage 只显 error_code，不泄露 tool_output 正文 | SEC-SENS-*/SEC-TOOL-* 脱敏 | 一致（L0 C1/C2 锚点） |
| Step 4 | Conflict Compare + Lifecycle Status（km-1，include_resolved=false；active/archived 版本流转） | D8-C 冲突对比与生命周期状态 | 一致（L0 D1/D2 锚点） |
| Step 5 | Preview → Confirm → Execute；凭据绑定 userId+forgetPlanId+selection_hash、TTL=300s、HIGH-01 立即清除 selector 明文、错配/过期 fail-closed | D3 §7.6 / SEC-FORGET-01/02 / D10-C HIGH-01/02 | 一致（L0 E1–E4 锚点） |
| 安全汇总初始态 | 未运行 Step 时显示「未执行 · —」，不得出现 PASS/OK/READY 假阳性 | C-D11 MEDIUM-03 | 一致（L0 slot F 断言初始无 PASS/OK/READY） |
| 页面底部声明 | 本页为客户端编排 Demo，未接入真实 AI 助手 Hook / Chat DB / 持久化后端；真实 Runtime 证据需 B/D 轨在麒麟 VM（同一 Commit）复测归档 | 不冒充真实宿主证据 | 一致（诚实声明，E 接受） |

## 二、安全确认核对（静态）

| 核对项 | 代码语义 | 对应安全规则 | 静态判定 |
|---|---|---|---|
| 先预览再确认 | Step5 Preview 生成凭据并进入 awaiting_confirmation，Execute 仅在携带同一 Preview 凭据时放行 | SEC-FORGET-01/02 | 一致（L0 E1/E2/E3） |
| 凭据过期/错配 fail-closed | ViewModel 记录 TTL deadline；过期或错配 → failed 且不发 forget.execute | SEC-FORGET-02、D10-C HIGH-01 | 一致（L0 E3/E4） |
| selector 明文生命周期 | Preview 完成后立即清除本地明文 selector | SEC-FORGET-03（明文不长期留存） | 一致（L0 E1：forgetSelectorCleared） |
| 漏删保护 | executed 与 affected 不一致 → failed + 漏删告警 | v0.3/MEDIUM-03 | 一致（L0 E2：无漏删） |
| 原文隔离门禁 | 汇总灯 gate 到 preChatStage==ready 才允许 PASS/FAIL | SEC-CTX-01 | 一致（QML 绑定 + L0 F2） |
| 错误/日志脱敏 | Step3 错误路径只显示 error_code；D 轨日志脱敏由 D11D 证据（JSON 日志/trace_id） | SEC-SENS-* | 静态一致；运行日志脱敏以 D11D L2 为准 |
| 跨用户隔离 | 编排页跨用户项默认「未触发 (默认)」占位，不替代真实拦截 | SEC-UI-* | 占位不冒充；真实拦截以服务/检索/遗忘链实测为准（RC-06） |

## 三、发现与待办

- 静态层未发现 D11 主演示编排页 UI 文案与冻结业务事实相矛盾，或初始态假阳性 PASS/OK/READY 的问题（与 C 轨 D11 L0 断言一致）。
- 待 VM 运行确认（`UNVERIFIED`）：
  1. 汇总灯在同 Commit 同 VM 运行后的终态与原始证据（日志/DB/检索）一致；
  2. Step5 文案所述 TTL=300s 与 ViewModel deadline 实际运行日志一致（静态层以 C 轨实现为准，不代验证）；
  3. 跨用户拦截的实跑负向证据（对应案例卡 D11E-RC-06）；
  4. PreferenceEditor/ConflictComparison/LifecycleStatus/Forget 等业务页面的运行态文案与数据一致性（本批静态审查以 D11 编排页为主）。
- 跨轨口径备注（不代实现）：C-D11 文档声明的 L2 归档引用 D11B VM（`Kylin-V11-2603-D11B-ffd20b9-Test`），而 D11E 验收采用 D11D 统一 VM/最新 `main` 口径；两者差异需在 L2 执行时由 D/B 轨确认为同一 Commit，避免证据口径混淆。

## 四、结论口径

- 静态层结论：D11 主演示编排页的 UI 文案、状态门禁与安全汇总语义与 E 冻结契约一致，未发现假阳性「通过」展示；C 轨页面自身亦声明「未接入真实后端、需 B/D 轨同 VM 复测归档」，E 接受该口径。
- 运行态结论保持 `UNVERIFIED`，待同 Commit 同 VM 验收（工作清单项 5）后由 E 据此签署安全确认。
- 本文件不修改任何 C 轨代码或冻结契约。
