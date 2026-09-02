# PR #116 — D11-C E2E Orchestrator: 5-Step 编排器 + 安全契约 L0

> **最终合入 HEAD 模板**（以 `git rev-parse HEAD` 的最终值为准，合并前重新生成）
>
> - **HEAD**：`5d4d863bd9627bf01a4d8565f049637c877e5671`
> - **Base**：`a929436f696e11316d221ed5f23cf947ee61b4f7`
> - **规模**：`22` commits / `14` changed files

## 变更摘要

在 `memory-client/` 内新增一个**显式 5-Step Demo 编排器**（QML + ViewModel），
将 D5-C / D6-C / D10-C 原型与新增遗忘 Preview→Execute 一次性凭据链串成单页
客户端验收 Harness，配套 **14 个 QtTest E2E slot + 5 个 QML 业务 slot**，
覆盖 Reviewer E 第四轮复审关闭的 1 HIGH + 4 MEDIUM。

## 主要新增文件 (memory-client)

| 文件 | 作用 |
|---|---|
| `qml/pages/D11DemoOrchestratorPage.qml` | 5 张声明式 Step Card（objectName `d11-step-1-card` ~ `d11-step-5-card`），状态直接绑定 `viewModel.*`；4 项安全汇总灯 gate 到对应 pipeline 完成（MEDIUM-03）。 |
| `tests/test_d11c_e2e_orchestrator.cpp` | 14 个 QtTest L0：A1/A2/B1/C1/C2/D1/D2/E1/E2/E3/**E4**/F1/F2/**F3** |
| `tests/test_d11c_qml_load.cpp` | QQuickView 真实加载；5 张 Card 精确 objectName 定位 + 断言 `implicitHeight>0 && height>0`（MEDIUM-01）；slot F `summaryLightsInitiallyNoGreen`（MEDIUM-03）。 |
| `tests/mock_gateway_server.{h,cpp}` | MockGatewayServer 新增 `__hold__:true` 后门（handler 返回时不回包），用于构造"请求 in-flight → reset → stale response"竞态（MEDIUM-02 F3）。 |

## 主要修改文件

| 文件 | 变化 |
|---|---|
| `src/view_models/memory_view_model.{h,cpp}` | 新增 `forgetCredentialDeadlineMs_`（HIGH-01 客户端 TTL 门禁）；Preview 成功记录 deadline=now+TTL*1000，Execute 前校验 `credential==saved && now<deadline`（过期 fail-closed + 不发请求 + 清空 credential）；resetTool/Conflict/Lifecycle 清 pending + cancel deadline timer。 |
| `qml/main.qml` | Drawer 导航新增「D11 E2E Orchestrator」按钮；窗口标题更新。 |
| `qml/resources.qrc` | 注册 `pages/D11DemoOrchestratorPage.qml`。 |
| `tests/CMakeLists.txt` | 新增 ctest target：`d11c_e2e_orchestrator` / `d11c_qml_load`，后者设置 `QT_QPA_PLATFORM=offscreen` + `QT_QUICK_BACKEND=software`。 |
| `tests/test_d10c_forgetting.cpp` | D10 既有契约保持不回归（与 D11 ViewModel 修改编译一致）。 |
| `.github/workflows/memory-client-ctest.yml` | CI 纳入 10 个 ctest 目标（见下）。 |
| `README.md` | D11-C 章节更新到第四轮最终口径：14+5 slot 清单、HIGH-01 TTL、MEDIUM-01/02/03 精确场景、L2 声明。 |

## L0 用例清单（19 业务 QtTest slot）

**D11-C E2E Orchestrator（14 slots，`d11c_e2e_orchestrator`）：**
- A1 Step1 preChat：三路原文隔离 verified + modelRequestText 拼接
- A2 Step1 postTurn：envelope.method==`turn.finalized`，不回退 `memory.store`
- B1 Step2 cross-session：session-demo-0001 → session-demo-0002 + 差异化 Context 正对照
- C1 Step3 tool：toolStage=sent，metadata.tool_name=memory_search
- C2 Step3 tool UNSUPPORTED_METHOD：toolStage=failed + safeMessage 不泄漏正文
- D1 Step4 conflict.compare：ready + candidates.size==2
- D2 Step4 lifecycle.status：ready + items.size==2
- E1 Step5 forget Preview：awaiting_confirmation + selector cleared（D10 HIGH-01）
- E2 Step5 forget Execute：同 credential → completed + executed==1 + no missing deletes
- E3 Step5 forget Execute 错误凭据 → fail-closed + error 含 "credential"
- **E4（HIGH-01 新增）TTL 过期凭据 fail-closed**：TTL=1s → 等 2s → 同匹配凭据 Execute，stage=failed + error 含 "expired/TTL/fail-closed"，Mock **未收到** forget.execute 请求
- F1 未连接时 5 步全部本地 fail-closed（不挂死 busy）
- F2 5 步跑完 → busy 清空 + 6 条 stage 终值一致 + 三绿安全板
- **F3（MEDIUM-02 重写）真实 in-flight → reset → stale response ignored**：
  Mock `__hold__` hold 住 Tool/Conflict/Lifecycle 请求（busy=true / pending 非空）
  → reset → sendRawEnvelope 注入旧 requestId 响应 → stage 保持 idle；
  最后 resetAllPipelines() 再验证一次。

**D11-C QML Load（5 slots，`d11c_qml_load`）：**
- A `resourceUrlResolves`：QRC 资源路径解析
- B+C `componentCreatesWithoutErrors`：QQuickView Ready + rootItem 存在
- **B+C MEDIUM-01 精确化**：通过 objectName 精确定位 5 张 Step Card（`d11-step-1-card` ~ `d11-step-5-card`），断言 5/5 全部存在且 implicitHeight>0 且 height>0；不再使用"任意子项 implicitHeight>0"松弛判定
- D `viewModelAliasExistsAndInitiallyNull`
- E `multipleInstantiationsDoNotLeak`：连续 3 次实例化均通过 MEDIUM-01 精确高度验证
- **F `summaryLightsInitiallyNoGreen`（MEDIUM-03 新增）**：4 项汇总灯 Label 的 objectName 存在，且初始文本都不含 PASS/OK/READY

## ctest 目标（CI：10 个 L0 ctest，已通过 ✅）

> CI `Memory Client L0 ctest`：
> `protocol_adapter` / `memory_client_mock` / `d5_vertical_link_demo` /
> `d6c_multi_source_adapters` / `d7c_preference_editor` /
> `d8c_knowledge_conflict_lifecycle` / `d9c_context_assemble` /
> `d10c_forgetting` / **`d11c_e2e_orchestrator`** / **`d11c_qml_load`**
>
> 另一个 CI `Repository Baseline Check` 同步 ✅。

## 安全契约落地（Reviewer E 第四轮 HIGH + MEDIUM，均已关闭）

| ID | 项目 | 证据 |
|---|---|---|
| **HIGH-01** | confirmation credential TTL 过期 fail-closed（客户端门禁） | ViewModel `forgetCredentialDeadlineMs_` 记录 wall-clock deadline；Execute 前校验 `now<deadline`；过期清空 credential + stage=failed + 不发 forget.execute；E4 L0 用 TTL=1s 真实等待 2s 证明。 |
| **MEDIUM-01** | Step Card 高度不得被任意 QQuickItem 误判 | 5 张 Card 有稳定 objectName；d11c_qml_load 精确找到 5 张并逐一断言 implicitHeight>0 && height>0。 |
| **MEDIUM-02** | F3 reset 真清除 in-flight pending + stale response 不回写 | Mock `__hold__` 后门构造 hold 状态，保证 busy=true / pending 非空时 reset；reset 后 sendRawEnvelope 注入响应，三路（Tool/Conflict/Lifecycle）+ resetAllPipelines 均 stage 保持 idle。 |
| **MEDIUM-03** | 验收汇总初始态不得假阳性 PASS/OK/READY | 4 个汇总灯都 gate 到对应 pipeline stage（preChatStage==ready / forgetStage==completed or failed）；否则显示"未执行 · —"；d11c_qml_load slot F 断言 4 个 Label 初始文本不含 PASS/OK/READY。 |

## 显式不负责 / 回滚方式

- **不声称** SEC-CTX-01 / SEC-CTX-02 / SEC-FORGET-01~05 已 Runtime 验证；
  本 PR 仅为客户端 Harness / Demo，L2 真实 VM 证据必须由 B/D 轨在**同一最终合入 HEAD** 与 VM
  `Kylin-V11-2603-D11B-ffd20b9-Test` 上复测归档为 `d11b_c_e2e_YYYYMMDD.md`
  作为闭环依据（**L2 tested_commit 不硬编码 e9dba4f 或任何特定 SHA**，
  L2 启动时用 `git rev-parse HEAD` 注入）。
- **回滚方式（非单原子 commit）**：
  本 PR 为多 commit 变更（Demo Harness / L0 / Mock / Workflow），合入后推荐
  `git revert -m 1 <merge_commit_sha>` 整体回滚；若粒度回滚则依次 revert 本 PR
  内的"CI 配置→测试→Mock→ViewModel→QML→导航入口"顺序。
- Hard Delete / Cascade / Full Reset Runtime Execute 继续保持 fail-closed（D10-C 口径不变）。
