# Memory Client

## 模块定位

Qt/QML 侧记忆客户端，基于 QLocalSocket 连接 Memory Service，提供 QML 可调用的记忆存取、偏好查询、上下文管理接口。

## 输入与输出

* **输入**：QML 侧调用（用户偏好设置、Tool 上下文、查询请求、D5 Pre/Post Pipeline）

* **输出**：QML 可消费的结构化记忆数据、三路原文隔离文本、TurnFinalizedEvent 预览

## 责任轨道

* **主要**：C、D

* **协作**：B（检索结果消费）、E（事件枚举终审）

* **D5-C 演示参考**：`docs/adr/010-turn-finalized-method.md`（ADR-010）、`contracts/examples/memory_context.v1.json`

## 当前状态

**Memory Client L0（D5 / D6 / D7 / D8 / D9 / D10 / D11 原型链；L0 ctest 预期 10/10
（protocol\_adapter / memory\_client\_mock / d5\_vertical\_link\_demo /
d6c\_multi\_source\_adapters / d7c\_preference\_editor / d8c\_knowledge\_conflict\_lifecycle /
d9c\_context\_assemble / d10c\_forgetting / d11c\_e2e\_orchestrator / d11c\_qml\_load；
d11c\_qml\_load 在缺 Qt5::Gui/Qml/Quick/QuickControls2 IMPORTED target 的环境会
跳过，其余 9 个不受影响）+ QML build-smoke green；C 角色各天 Demo 保持 OPEN；
SEC-CTX-01 Runtime Evidence 未生成；
未接入真实 AI Assistant Hook / Chat DB / ChatRecord / model\_request /
TurnExtractionAdapter / 知识治理 / 冲突仲裁持久化后端）。**

* 协议编解码 `protocol_adapter.{h,cpp}`：4 字节大端长度前缀 + UTF-8 JSON envelope
  （对齐 D 轨 FRZ-IPC-001\~007 + ADR-010 turn.finalized，`deliverables/D4_IPC_PROTOCOL_*FREEZE_20260817.md`）

  * **活跃方法**：`echo / health / memory.retrieve`

  * **写链路候选方法**：`turn.finalized`（ADR-010；CANDIDATE / BLOCKED\_BY\_HOST\_MAPPING；生产默认不注册；Demo 客户端可发送）

  * **未实现**：`memory.store`（保持 UNSUPPORTED\_METHOD，ADR-010 §决策不动）

* MemoryClient `memory_client.{h,cpp}`：QLocalSocket 异步收发，信号驱动，不回显原文

  * `sendTurnFinalizedEvent()`：按 ADR-010 直接路由 `turn.finalized`；payload = TurnFinalizedEvent JSON，**不再**包装 `{event_type,event_body}` wrapper

* 公共 ViewModel `view_models/memory_view_model.{h,cpp}`：

  * D5-C Pre-Chat Pipeline：`runPreChatPipeline()`；status=error 明确失败；MemoryContext 严格按 `memory_context.v1.json` 契约解析；空/error/malformed/injection=failed 不产生伪 `[MEMORY-CONTEXT]`

  * D5-C Post-Turn Pipeline：`runPostTurnPipeline()` → `turn.finalized`；status=error 明确 `failed/timeout`，memory.store 不再承担 TurnFinalizedEvent 写链路

  * 原文隔离：三路 QString（`originalUserText / modelRequestText / injectedContextText`）+ `textIsolationVerified` 指示灯

  * 运行健壮性：`preChatBusy_ + postTurnBusy_` 双 busy；独立 `pendingPreChatRequestId_ / pendingPostTurnRequestId_`；per-request deadline QTimer（默认 5000ms）；timeout 失败

* QML：`qml/main.qml` + StackView 路由（Status / MemoryQuery / Preferences / VerticalLink Demo）

  * **High 修复**：VerticalLinkPage postTurnPreview 采用纯 declarative binding（`lastTurnFinalizedEvent || previewHelper.previewDoc`），不再做 imperative `.text =` 赋值；Preview 只写 `previewHelper.previewDoc` 状态

  * **High 修复**：`viewModel.busy` 兼容属性 = `preChatBusy || postTurnBusy`；旧页（main/Status/MemoryQuery）不再引用已移除的全局 `busy_`

* L0 Mock 契约测试 `tests/`：

  * `test_protocol_adapter.cpp` 协议编解码

  * `test_memory_client_mock.cpp` Client ↔ Mock Gateway

  * `test_d5_vertical_link_demo.cpp` D5-C Demo 覆盖（10 用例：A1/A2/B1-B5/C1-C3）

**关键声明（Route B）**：

* 本实现仅为 memory-client 侧的 Pipeline Harness / Demo

* **不关闭 C-D5**

* **不声称 SEC-CTX-01 Runtime Verified**

* **尚未接入**：真实 AI Assistant Hook、真实 model request、真实 Chat DB / ChatRecord / source resolver、真实 assistant final message

* memory\_items 在 Context 渲染中的使用为 Demo 扩展，**不是**正式 C-D5 Context renderer 最终契约

* ADR-010 turn.finalized 标注为 CANDIDATE / BLOCKED\_BY\_HOST\_MAPPING：本 Demo 客户端可发送，但生产服务端默认不注册 handler，因此 Demo 调用真实生产 Gateway 仍返回 UNSUPPORTED\_METHOD（符合预期）

**非阻断 Technical Debt（可后续跟踪）**：

* FRZ-IPC-004 deadline 计时精度：目前使用 `deadlineMs` 常量；冻结口径为 `deadline_ms + 100ms`

* timeout 后 `MemoryClient::pendingRequests_` 不自动删除；late response 可能刷新 `lastResponse`

* `memory_items` 展示作为 Demo 扩展暂存，待正式契约决策

### D8-C 知识详情 / 冲突对比 / 生命周期状态（Demo / Prototype）

**D8-C Demo / Prototype（CANDIDATE / pending ADR；未接入真实知识 / 冲突 / 生命周期后端；
C-D8 保持 OPEN）。**

* 候选 IPC 方法（`protocol_adapter.{h,cpp}`）：`knowledge.detail` / `conflict.compare` /
  `lifecycle.status`，标记 `CANDIDATE / pending ADR`；生产默认返回 `UNSUPPORTED_METHOD`，
  Demo / 测试态 Mock Gateway 可注册 handler。

* MemoryClient 便捷方法：`sendKnowledgeDetailRequest()` / `sendConflictCompareRequest()` /
  `sendLifecycleStatusRequest()`，复用 `sendRequest()` 共享 envelope 编码与 pending 跟踪。

* ViewModel Pipeline：`runKnowledgeDetailPipeline()` / `runConflictComparePipeline()` /
  `runLifecycleStatusPipeline()`；三组独立 busy / stage / error / pending，沿用 D5 REWORK §C1
  模式避免多请求竞态；响应投影到 `knowledgeDetail` / `conflictCandidates` / `lifecycleItems`。

* QML 页面：`KnowledgeDetailPage.qml` / `ConflictComparisonPage.qml` /
  `LifecycleStatusPage.qml`（目标 Qt 5.12，ScrollView 防 960×640 溢出）。

* L0 测试：`test_d8c_knowledge_conflict_lifecycle.cpp`（14 用例：K1-K3 / C1-C3 / L1-L3 /
  E1-E3 / R1-R2）。

**关键声明（D8-C）**：本实现仅为 memory-client 侧 Demo / Prototype；不关闭 C-D8；
不接入真实 AI Assistant Hook / Chat DB / 知识 / 冲突 / 生命周期持久化后端；
三个候选方法 pending ADR 立项；L2 宿主验证需在麒麟 VM 上另行执行。

### D9-C Memory Context 组装（Demo / Prototype）

**D9-C Demo / Prototype（CANDIDATE / pending ADR；未接入真实 Context 组装后端；
C-D9 保持 OPEN）。**

* 候选 IPC 方法（`protocol_adapter.{h,cpp}`）：`context.assemble`，标记
  `CANDIDATE / pending ADR`；生产默认返回 `UNSUPPORTED_METHOD`，Demo / 测试态
  Mock Gateway 可注册 handler。方法语义：把召回候选（B 轨混合检索输出）组装为
  受 Token 预算控制的 MemoryContext，返回可解释字段（召回来源、记忆类型、
  冲突 / 不确定性提示、`injection_status`）。

* MemoryClient 便捷方法：`sendContextAssembleRequest()`，复用 `sendRequest()`
  共享 envelope 编码与 pending 跟踪。

* ViewModel Pipeline：`runContextAssemblePipeline()`；独立 `contextAssembleBusy_` /
  `pendingContextAssembleRequestId_`，沿用 D5 REWORK §C1 模式避免与 D5/D6/D7/D8
  Pipeline 竞态；响应投影到 `assembledContext` / `contextRecallSources` /
  `contextMemoryTypes` / `contextConflictHints` / `contextUncertaintyHints` /
  `contextTokenBudget` / `contextActualTokenCount` / `contextBudgetExceeded` /
  `contextInjectionStatus`。

* 防伪 Context：`injection_status` 为 `failed` / `skipped` 或 `status=error` /
  空响应时，一律不产生伪 `assembledContext`（沿用 D5 Pre-Chat 防伪 Context 模式），
  所有投影字段清零。

* Token 预算校验：客户端独立计算 `budget_exceeded = (actual_token_count >
  token_budget)`，覆盖服务端可能漏返回该字段的场景。

* QML 页面：`ContextAssemblePage.qml`（目标 Qt 5.12，ScrollView 防 960×640
  溢出；输入区 user\_id / query\_text / token\_budget / scene / candidates；
  输出区展示组装结果与可解释字段）。

* L0 测试：`test_d9c_context_assemble.cpp`（17 用例 A/E/S/R 命名：
  A1-A11 组装成功 / recall\_sources 字符串投影 / memory\_types 对象投影 /
  conflict\_hints 对象投影 / uncertainty\_hints 字符串投影 / 预算内 / 超预算 /
  空 user\_id / 空 query\_text / 非正 budget / candidates 转发；
  E1-E2 status=error / UNSUPPORTED\_METHOD；S1-S2 injection=skipped/failed 防伪；
  R1-R2 与 D8C 独立 pending / 未连接拒绝）。

**关键声明（D9-C）**：本实现仅为 memory-client 侧 Demo / Prototype；不关闭 C-D9；
不接入真实 AI Assistant Hook / Chat DB / SourceResolver / Token Budget 服务端
实现；`context.assemble` 候选方法 pending ADR 立项；L2 宿主验证需在麒麟 VM 上
另行执行。

### D10-C 精准遗忘 Pipeline（Demo / Prototype）

**D10-C Demo / Prototype（CANDIDATE / pending ADR；未接入真实 D-B-E 跨轨 Forget
事务；C-D10 保持 OPEN；Runtime Hard Delete / Cascade / Full Reset 保持
fail-closed）。**

业务契约基于 `docs/day10/16_d10d_forget_contract_plan_v0.3.md`（§一\~§九 冻结）。
本 QML Pipeline Harness 仅演示客户端侧状态机与安全投影闭环：

* 候选 IPC 方法（`protocol_adapter.{h,cpp}`）：`forget.preview` /
  `forget.execute`，标记 `CANDIDATE / pending ADR`；生产默认返回
  `UNSUPPORTED_METHOD`。Demo / 测试态 Mock Gateway 可注册 handler 验证契约。

  * `forget.preview`：接收 ForgetPlan（user\_id / forget\_plan\_id / forget\_mode
    / target\_type / requires\_confirmation + 模式条件字段），返回
    `selection_hash` + `affected_count` + `credential_ttl_s` +
    `resolved_target_ids_preview_snippet` + `selector_cleared:true`（§四.8
    HIGH-01：Preview 完成即清除明文 target\_selector / target\_topic）。

  * `forget.execute`：携带 `forget_plan_id` + `confirmation_token` +
    可选 `idempotency_key` + `delete_mode`（soft 硬删优先 / hard Runtime
    fail-closed）。服务端校验 selection\_hash 一致、凭据有效未过期、
    expected\_affected\_count 匹配后执行软删事务，v0.3/MEDIUM-03 要求
    executed\_count == affected\_count，不一致不得进入 completed。

* MemoryClient 便捷方法：`sendForgetPreviewRequest()` /
  `sendForgetExecuteRequest()`，复用 `sendRequest()` 共享编解码与超时门禁。

* ViewModel Pipeline（D9C 相同分层风格，独立 pending / busy）：

  * `runForgetPreviewPipeline()`：SEC-FORGET-03 五模式互斥校验（single\_item
    → target\_id / session → target\_session\_id / topic → target\_topic /
    time\_window → target\_time\_range / full\_reset → 无任何 target\_\*）；
    登记 pending + 暂存明文（Preview 完成后清除）。

  * `handleForgetPreviewResponse()`：跨用户 user\_id 预检（C-D10 #3，不匹配
    → forgetCrossUserBlocked=true + stage=failed）→ 投影 → 清除本地明文
    pendingForgetPreviewSelector\_/Topic\_ → forgetSelectorCleared 置位 →
    保存 selection\_hash / affected\_count 快照 → stage=awaiting\_confirmation。

  * `runForgetExecutePipeline()`：awaiting\_confirmation 门禁 + 校验三必填
    → 附带 selection\_hash 二次校验 + expected\_affected\_count 漏删保护。

  * `handleForgetExecuteResponse()`：projectForgetExecute 投影 executed\_count
    → v0.3/MEDIUM-03 漏删保护（executed != affected → stage=failed +
    forgetHasMissingDeletes=true）→ 否则 stage=completed。

* 状态机（§三.3 v0.2 冻结）：`idle → previewing → awaiting_confirmation →
  executing → completed`；任一错误路径回到 `failed`。Preview/Execute 独立
  pending\_RequestId\_ + busy 标志，互斥启动防竞态。

* 安全控制（客户端侧 Demo 闭环）：

  * **明文生命周期**（§四.8 HIGH-01）：Preview 响应后立即清除本地
    target\_selector / target\_topic 明文；forgetSelectorCleared=true。

  * **跨用户操作拒绝**（C-D10 #3）：响应 data.user\_id ≠ 请求 user\_id
    → forgetCrossUserBlocked=true + stage=failed + 清空投影。

  * **漏删一致性**（v0.3/MEDIUM-03）：forgetHasMissingDeletes getter 基于
    affectedCount 与 executedCount 计算；不一致 → stage=failed。

  * **Hard Delete fail-closed**（v0.3/MEDIUM-04）：delete\_mode=hard 时
    服务端返回 fail-closed 错误，Execute 进入 failed，executedCount=-1
    （不得自动降级 soft 后伪成功）。

  * **full\_reset 门禁**：携带任意 target\_\* 立即拒绝（SEC-FORGET-03）。

* QML 页面：`ForgetPage.qml`（目标 Qt 5.12，ScrollView 防 960×640 溢出），
  分区：基础输入 / 自然语言 selector / 模式条件字段（按 forget\_mode 互斥显示）
  / Preview-Execute 按钮 / Execute 参数 / 敏感提示 / 影响范围面板 /
  Execute 一致性校验 / 安全验收（selector 清除 + 跨用户拒绝）/ 原始响应 JSON。

* L0 测试：`test_d10c_forgetting.cpp`（18 用例 A\~J）：

  * **A. 模式互斥**（5 合法模式 + crossMode 携带非模式字段拒绝）

  * **B. Preview 投影**（selection\_hash / affected\_count / TTL /
    resolved\_targets + forgetSelectorCleared=true HIGH-01）

  * **C. 状态机** idle→previewing→awaiting→executing→completed

  * **D. 漏删保护**（MEDIUM-03：executed < affected → failed）

  * **E. 跨用户拒绝**（C-D10 #3：user\_id mismatch → forgetCrossUserBlocked）

  * **F. Execute 门禁**（非 awaiting\_confirmation → 拒绝）

  * **G. 独立 busy + 未连接拒绝**

  * **H. UNSUPPORTED\_METHOD / error → failed 且无伪结果**

  * **I. full\_reset 携带 target\_\* → 拒绝**

  * **J. Hard Delete fail-closed（错误不自动降级）**

**关键声明（D10-C）**：本实现仅为 memory-client 侧 QML Pipeline Harness；
不关闭 C-D10；**不宣称 D 轨 SQLite Forget 事务 / B 轨 Vector+FTS5 物理删除 /
E 轨 ForgetPlan 业务 Gate 已 Runtime 接线**；Hard Delete / Cascade / Full Reset
在跨轨闭环与麒麟 L2 证据前保持 fail-closed；L2 宿主验证需在麒麟 VM 另行执行。

### D11-C 同一虚拟机全功能联调 · E2E Orchestrator（Demo / Prototype）

**D11-C Demo / Prototype（CANDIDATE / Demo 编排骨架；不关闭 C-D5 \~ C-D10；
不声称已接入真实 AI Assistant Hook / Chat DB / 跨轨持久化后端；
L2 宿主 Runtime 证据由 B/D 轨在 D11B 最终 VM（与最终验收 HEAD commit
同一 SHA**，不得提前硬编码）复测并归档
`evidence/l2-kylin-vm/d11b_c_e2e_YYYYMMDD.md`）。

业务编排依据：

* 台账 15 天 D11 C 轨任务卡 #1\~#3：主导 AI 助手 + MemoryClient + 全部 QML
  页面联调；完成「普通聊天 / 跨会话 / Tool / 冲突 / 遗忘」5 条主演示路径；
  修复用户交互和原文隔离问题。主演示路径必须在**同一 Commit、同一虚拟机**中完整通过。

* D11B 回填文档：C1-1 \~ C1-5 样例输入 / 期望输出来源于 D11B 任务在 VM
  内联调后产出的归档文件；本 PR 合入前**不得引用 base/HEAD 均不存在的路径**；
  如 D11B 回填文件最终落位，请在合入前补充相对仓库的可追溯路径。

* **编排器页面**：`qml/pages/D11DemoOrchestratorPage.qml`

  * 目标 Qt 5.12，ScrollView 防 960×640 溢出；5-Step Card + 公共参数区 +
    安全汇总面板，方便 B/D 轨在 D11B VM 内一键复跑。

  * Step 1 · 普通聊天（D5 Vertical Link）：user=local-user / session=session-demo-0001 /
    scene=software\_development / max\_context\_tokens=800 +
    original\_user\_text=「帮我回忆昨天讨论的麒麟 OS Agent 记忆系统架构要点」→
    Pre-Chat `memory.retrieve` → 三路原文隔离 PASS → Post-Turn `turn.finalized`
    （ADR-010，`is_end=true`，`turn_id=turn-0001` / `traceId=tr-demo-0001`）。

  * Step 2 · 跨会话召回持久化偏好+知识：session 切到 `session-demo-0002`，
    user 保持 `local-user`，查询「Vector 删除一致性规则」→ context\[] 应含
    preference/knowledge 持久化条目（B 轨决定具体数量）；编排器侧保证
    originalUserText / session 不会回退到 Step 1（独立 pending 防竞态）。

  * Step 3 · Tool 调用事件入记忆（D6 Tool Adapter）：`tool.execution`
    tool\_name=memory\_search / execution\_status=success /
    tool\_input=`{"query":"qlatent 向量召回阈值"}` /
    tool\_output=`{"hits":5,"threshold":0.52}`；错误路径 safeMessage 只显
    error\_code + 通用文案，不得携带 tool\_output 正文/JSON。

  * Step 4 · 冲突对比 + 生命周期状态（D8-C）：memory\_id=km-1，
    include\_resolved=false：`conflict.compare` 返回候选列表；
    再跑 `lifecycle.status` 展示 km-1 的 active/archived 版本流转。

  * Step 5 · 精准遗忘（D10-C Preview→Confirm→Execute，**HIGH-02 凭据链修复**）：
    forget\_mode=single\_item / target\_type=knowledge /
    forget\_plan\_id=plan-demo-001 + 自然语言 selector（成功后 HIGH-01 明文立即清除、
    `forgetSelectorCleared=true`）→
    Preview 响应生成并下发 **confirmation\_credential**（绑定
    user\_id + forget\_plan\_id + selection\_hash，TTL 300s，ViewModel 通过
    `forgetConfirmationCredential` Q\_PROPERTY 暴露给 QML）→
    Execute 按钮仅在 `forgetStage=awaiting_confirmation` 且 credential 非空时启用，
    直接绑定同一 Preview 返回的 credential（ViewModel 端 fail-closed 二次校验：
    空 / 不匹配 / 过期 token 直接 rejected）→ delete\_mode=soft →
    completed 且 `forgetHasMissingDeletes=false`（MEDIUM-03 一致性）。
    **严禁硬编码 credential-demo-32b 作为传参；Preview→Execute 必须闭环。**

  * 安全汇总板：D5 原文隔离 PASS / D10 HIGH-01 Selector 清除 PASS /
    跨用户拦截默认未触发(OK) / 遗忘漏删一致性 OK /
    Demo/Prototype 非真实 Runtime 的显式声明。

* **导航入口**：`qml/main.qml` Drawer 新增「D11 E2E Orchestrator」按钮；
  窗口标题更新为「Kylin Memory Client — D11 E2E Orchestrator (Demo/Prototype)」。

* **QRC**：`qml/resources.qrc` 注册 `pages/D11DemoOrchestratorPage.qml`。

* **L0 测试**：

  1. `tests/test_d11c_e2e_orchestrator.cpp`（A\~F 共 **15 个 QtTest slot**：
     A1/A2/B1/C1/C2/D1/D2/E1/E2/E3/E4/F1/F2/F3），
     使用 test\_support::MockGatewayServer + setHandler(lambda) 注册 9 路活跃 handler
     （memory.retrieve / turn.finalized / tool.execution / conflict.compare /
     lifecycle.status / forget.preview / forget.execute / health / echo）。

     * **A. Step1 普通聊天**：A1 PreChat → ready，三路原文隔离 textIsolationVerified=true
       且 `modelRequestText = originalUserText + separator + injectedContextText`（**HEAD
       b634894 起废除"originalUserText 不得出现在 modelRequestText"的错误断言，Model
       Request 本身必须带原始查询以便 AI 处理**；originalUserText **不得**出现在
       injectedContextText）；A2 PostTurn 发送的 envelope.method 必须是 ADR-010 的
       `turn.finalized` 且不得回退为 `memory.store`（非 retry 路径下
       retry\_of\_turn\_id 必须为空）。

     * **B. Step2 跨会话（MEDIUM-02 修复：session 正对照）**：
       Gateway **分别捕获** Step 1 / Step 2 请求的 `payload.session_id`，
       断言第一次为 `session-demo-0001`、第二次为 `session-demo-0002`；
       Mock 对两个 session 返回**可区分**的 Context（Session B 含独有偏好条目，
       injectedContextText 不同），证明第二次确为新 session 而非 Step 1 拋留。

     * **C. Step3 Tool**：C1 toolStage=sent；Gateway 收到的
       `metadata.tool_name=memory_search` / `metadata.execution_status=success`；
       C2 UNSUPPORTED\_METHOD 错误注入 → toolStage=failed + requestFailed 信号
       safeMessage **不含** `PK0f3e2d_c2` 等 tool\_output 正文。

     * **D. Step4 知识+生命周期**：D1 conflictCompareStage=ready，
       conflictCandidates.size()==2；D2 lifecycleStatusStage=ready，
       lifecycleItems.size()==2，两条错误为空。

     * **E. Step5 精准遗忘（HIGH-02 凭据链正反向 + HIGH-01 TTL 过期门禁）**：
       E1 Preview → awaiting\_confirmation + forgetSelectorCleared=true（HIGH-01），
       forgetConfirmationCredential 非空且投影的 forgetMode/targetType 正确；
       E2 Execute 若用 Preview 返回的 **同一条** credential → completed +
       forgetExecutedCount==1 + forgetHasMissingDeletes==false（MEDIUM-03）；
       E3 Execute 若用错误 credential / 空 token → fail-closed：
       forgetStage=failed，forgetExecuteError 含 "credential"；
       **E4（HIGH-01 TTL 过期 fail-closed，第三轮新增）**：
       ViewModel 设置 forgetCredentialTtlSeconds=1 → 发起 Preview 拿到 credential →
       QTest::qWait(2000) 等待 TTL 过期 → 用**完全相同**的 credential 发起 Execute →
       客户端门禁 reject（forgetStage=failed、forgetExecuteError 含
       "expired" / "TTL" / "fail-closed"），Mock 侧**未收到**任何 forget.execute 请求。

     * **F. 编排器总体一致性（含 MEDIUM-02 Reset 防 stale response 回写）**：
       F1 未连接时 5 步全部本地 fail-closed（stage=failed，busy 不会挂死，
       至少 1 次 requestFailed 信号）；F2 依次跑完 5 步后
       `QTRY_VERIFY_WITH_TIMEOUT(!vm.busy(), 3000)`，六个阶段最终值一致
       （ready/sent/ready/ready/ready/completed）+ 三绿安全板
       （textIsolationVerified / forgetSelectorCleared / !forgetHasMissingDeletes）；
       **F3（MEDIUM-02 真实竞态修复：in-flight → reset → stale）**：
       Mock 新增 `__hold__` 后门——对指定 method 仅捕获 requestId 但不回包，
       等 ViewModel busy=true 后再调 reset\*Pipeline()（此时 pendingXxxRequestId\_
       确实非空，clear 真正生效）；随后通过 Mock sendRawEnvelope() 注入
       "旧 requestId"的响应，断言 Tool / Conflict / Lifecycle 三路均不再回写 stage
       （保持 idle）。最后再验证 resetAllPipelines() 的全量竞态。
  2. `tests/test_d11c_qml_load.cpp`（**MEDIUM-01 / MEDIUM-03 真实 QML 验证**）：
     用 **QQuickView**（QT\_QPA\_PLATFORM=offscreen + QT\_QUICK\_BACKEND=software，
     headless）直接加载 `qrc:/qt/qml/memory_client/pages/D11DemoOrchestratorPage.qml`，
     断言：资源可解析、`view.status() == QQuickView::Ready`、`rootObject()` 非空、
     根对象为有效 `QQuickItem`；
     **MEDIUM-01（第三轮精确化）**：给 5 张 Step Card 加 objectName
     （`d11-step-1-card` \~ `d11-step-5-card`），通过 findChild 递归定位全部 5 张，
     逐一断言 **全部 5 张都存在 且 implicitHeight>0 且 height>0**（view show()

     * resize(960x640) + layout 等待后 height 必有有效值）；不再使用"任意子项
       implicitHeight>0"的松弛判定；
       `viewModel` alias 属性存在且初始为 null；连续 3 次实例化无泄漏；
       **MEDIUM-03（第三轮新增 slot F summaryLightsInitiallyNoGreen）**：
       页面初始态（未运行任何 Step、未设置 viewModel 上下文）下，4 个汇总灯 Label
       （objectName: `d11-summary-text-isolation` / `d11-summary-selector-cleared` /
       `d11-summary-credential-chain` / `d11-summary-forget-missing`）的 text 都不得
       含 PASS / OK / READY——必须显示"未执行 · —"，避免初始态假阳性绿灯。
       **注意**：原使用裸 `QQmlComponent::create()` 在 headless CI 触发
       SIGSEGV (signal 11)，已改用 `QQuickView`（内部管理 QQuickWindow + scene graph
       生命周期）稳定完成实例化；弥补原 CI QML smoke build 仅验证打包不验证 parser
       的缺口。

* **ctest 目标**：`d11c_e2e_orchestrator` 与 `d11c_qml_load`。
  CI `memory-client-ctest.yml` 随 `protocol_adapter / memory_client_mock /
  d5_vertical_link_demo / d6c_multi_source_adapters / d7c_preference_editor /
  d8c_knowledge_conflict_lifecycle / d9c_context_assemble /
  d10c_forgetting / d11c_e2e_orchestrator / d11c_qml_load` 一起执行（**共 10 个**，此前口径请以此行覆盖）。

**关键声明（D11-C）**：

* 本实现仅为 memory-client 侧的**编排 Harness / Demo**，不关闭 C-D5 \~ C-D10。

* **不声称 SEC-CTX-01 / SEC-CTX-02 / SEC-FORGET-01\~05 已 Runtime 验证**。

* **尚未接入**：真实 AI Assistant Hook / Chat DB / ChatRecord /
  source resolver / model request 真实注入 / 跨轨 B 轨混合检索 /
  D 轨 SQLite 事务 / E 轨业务规则。

* D11B 最终 VM 的真实复测与 L2 证据归档（含 Wireshark/socat UDS 抓包、
  journalctl 原文泄露扫描、5 路径截图与 SHA-256）必须由 B 轨在
  **最终合入的 HEAD commit（本 README 不提前硬编码 SHA，以合入时 git rev-parse HEAD 为准）**
  与同一 VM（`Kylin-V11-2603-D11B-ffd20b9-Test`）上执行并完成，
  以 D11B 回填文档 `d11b_c_e2e_YYYYMMDD.md` 归档为唯一闭环依据。

* Hard Delete / Cascade / Full Reset Runtime Execute 在跨轨闭环 + L2 证据前
  继续保持 fail-closed（D10-C 既有口径不变）。

## 明确不负责的内容

* 不实现 Python 侧服务逻辑

* 本 QML 应用为独立 Qt 演示壳（旁路演示），非官方 AI 助手集成；不包含官方 AI 助手 UI 源码

* 不直接操作 SQLite/Vector

* 不固化偏好/知识业务字段（待 E 轨 Schema 终审）

* 不冒充 L1/L2 银河麒麟 VM Runtime 证据

## 目录

```
memory-client/
├── CMakeLists.txt
├── README.md
├── src/
│   ├── main.cpp                       # QML 入口
│   ├── memory_client.{h,cpp}          # QLocalSocket 客户端
│   ├── protocol_adapter.{h,cpp}       # 长度前缀 JSON envelope 编解码（含 ADR-010 turn.finalized）
│   └── view_models/
│       └── memory_view_model.{h,cpp}  # QML 公共 ViewModel（D5~D11 Demo Pipeline）
├── qml/
│   ├── main.qml                       # ApplicationWindow + StackView
│   ├── resources.qrc
│   └── pages/
│       ├── StatusPage.qml
│       ├── MemoryQueryPage.qml
│       ├── PreferenceEditorPage.qml   # 占位（待 E 轨 Schema）
│       ├── VerticalLinkPage.qml       # D5-C Demo（Pre/Post + 原文隔离）
│       ├── KnowledgeDetailPage.qml    # D8-C 知识详情 Demo
│       ├── ConflictComparisonPage.qml # D8-C 冲突对比 Demo
│       ├── LifecycleStatusPage.qml   # D8-C 生命周期状态 Demo
│       ├── ContextAssemblePage.qml   # D9-C Memory Context 组装 Demo
│       ├── ForgetPage.qml            # D10-C 精准遗忘 Pipeline Demo
│       └── D11DemoOrchestratorPage.qml # D11-C E2E Orchestrator（5-Step Demo）
└── tests/
    ├── CMakeLists.txt
    ├── mock_gateway_server.{h,cpp}    # QLocalServer Mock（含 sendRawEnvelope 注入 stale response）
    ├── test_protocol_adapter.cpp      # L0 协议单元测试
    ├── test_memory_client_mock.cpp    # L0 Client ↔ Mock Gateway
    ├── test_d5_vertical_link_demo.cpp # L0 D5-C Demo（§A/B/C 10 用例）
    ├── test_d6c_multi_source_adapters.cpp # L0 D6-C 多源 Adapter（Tool/Manual/Behavior）
    ├── test_d7c_preference_editor.cpp # L0 D7-C 偏好编辑
    ├── test_d8c_knowledge_conflict_lifecycle.cpp # L0 D8-C Demo（14 用例）
    ├── test_d9c_context_assemble.cpp # L0 D9-C Demo（17 用例 A/E/S/R）
    ├── test_d10c_forgetting.cpp      # L0 D10-C Demo（18 用例 A~J 遗忘契约）
    ├── test_d11c_e2e_orchestrator.cpp # L0 D11-C E2E（15 用例 A1~F3，含 E4 TTL过期 + F3 in-flight→reset→stale）
    └── test_d11c_qml_load.cpp        # L0 D11-C QML（5 业务 slot，含 Card objectName 精确高度 + F 汇总灯初始态禁绿灯）
```

## 构建

```bash
# 仅 L0 测试（不需要 Qt Quick）
cmake -S memory-client -B memory-client/build \
    -DKYLIN_MEMORY_CLIENT_BUILD_QML_APP=OFF \
    -DKYLIN_MEMORY_CLIENT_BUILD_TESTS=ON
cmake --build memory-client/build
ctest --test-dir memory-client/build --output-on-failure

# 含 QML GUI（需要 Qt5 Quick + QuickControls2）
cmake -S memory-client -B memory-client/build -DKYLIN_MEMORY_CLIENT_BUILD_QML_APP=ON
cmake --build memory-client/build
```

## CI（新增）

`.github/workflows/memory-client-ctest.yml`：

* **触发**：PR → main/integration；push → main/integration/feat/\*\*；手动 `workflow_dispatch`

* **路径过滤**：`memory-client/**` + 工作流文件本身

* **环境**：ubuntu-22.04（qtbase5-dev / qt5-qmake / qtdeclarative5-dev / Qt Quick 模块）

* **Job 1 / L0 ctest**：cmake configure（QML OFF / tests ON）→ cmake --build → `ctest --output-on-failure --verbose`

  * 覆盖 ctest 目标（**共 10 个**，按注册顺序）：
    `protocol_adapter` / `memory_client_mock` / `d5_vertical_link_demo` /
    `d6c_multi_source_adapters` / `d7c_preference_editor` /
    `d8c_knowledge_conflict_lifecycle` / `d9c_context_assemble` /
    `d10c_forgetting` / `d11c_e2e_orchestrator` / `d11c_qml_load`

* **Job 2 / QML build smoke**：cmake configure（QML ON / tests OFF）→ cmake --build → 产物存在校验

  * 验证 `resources.qrc` 可处理、`main.qml` Component 引用无误、
    `KnowledgeDetailPage.qml` / `ConflictComparisonPage.qml` / `LifecycleStatusPage.qml` /
    `ContextAssemblePage.qml` / `D11DemoOrchestratorPage.qml` 可参与 Qt Quick 构建

  * **运行态 QQuickView 真实加载验证由 Job 1 的 d11c\_qml\_load 承担**（Reviewer E HIGH-01：
    原 QQmlComponent::create() 在 headless CI 触发 SIGSEGV，已改用 QQuickView +
    QT\_QUICK\_BACKEND=software 稳定完成实例化，至少验证一个 Step Card implicitHeight>0）

  * VM L2 不在本 job 范围

## 验收要求

| 层级                 | 要求                                                                                | 状态                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ------------------ | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **L0**             | 编译通过、Mock 协议测试 + QML build smoke                                                  | **L0\_PENDING CI** — ctest 预期 **10/10**（protocol\_adapter / memory\_client\_mock / d5\_vertical\_link\_demo / d6c\_multi\_source\_adapters / d7c\_preference\_editor / d8c\_knowledge\_conflict\_lifecycle / d9c\_context\_assemble / d10c\_forgetting / d11c\_e2e\_orchestrator / d11c\_qml\_load；d11c\_qml\_load 在缺 Qt5 Quick 运行时的环境会跳过）；QML\_APP=ON 构建 smoke job 验证 QRC / main.qml / 五 Page 可编译（含 D11DemoOrchestratorPage） |
| **L1**             | QLocalSocket 连接真实 Gateway / Echo；turn.finalized 测试态 handler；真实 MemoryContext 返回非空 | 待联调                                                                                                                                                                                                                                                                                                                                                                                                                           |
| **L2**             | 银河麒麟 VM 中真实 AI Assistant Hook / ChatRecord / Chat DB / SourceResolver 打通          | **未实现**（属后续真实 C-D5 关闭工作）                                                                                                                                                                                                                                                                                                                                                                                                      |
| **HOST\_VERIFIED** | SEC-CTX-01 原文隔离宿主级证据                                                              | **RUNTIME\_UNVERIFIED**                                                                                                                                                                                                                                                                                                                                                                                                       |

