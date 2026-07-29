# D1 · 轨道 C · OS Agent 调用链图、Hook 候选位置与最小修改任务卡

> 赛题：XA-202612 OS Agent 记忆优化及高效应用研究
> 责任轨道：C · OS Agent 与 Qt/QML
> 开发者：刘承恩
> 日期：2026-07-29（D1，Gate 0：基线与高风险 Spike 启动）
> Reviewer：D 主审（周子腾）；用户交互与安全由 E 补审（谢嘉然）
> 依据文档：01 能力边界 v1.0、02 总体架构/SOP v1.0、03 环境配置手册 v1.0、04 Agent/LLM 指南 v1.0

---

## 0. 任务来源与完成定义

**台账任务（D1-C）：**

1. 定位官方 AI 助手发送请求、最终 is_end、Tool 结果和 QML 数据流位置。
2. 核对宿主应用版本与可获得源码版本。
3. 输出 Hook、Context、Tool 三项 Spike 的修改点和最小 Diff 计划。

**交付物 / 完成定义：** 形成 OS Agent 调用链图、Hook 候选位置和最小修改任务卡。

**Gate 0 约束（02 文档 D1）：** 调查结果必须有命令和证据，不允许静态推测替代宿主验证。本卡中每条结论均标注证据等级（E0–E5）与状态标签（HOST_VERIFIED / SOURCE_VERIFIED / ABI_VERIFIED / PARTIAL / UNTESTED / NOT_FOUND / BLOCKED），来源为 01 文档统一能力矩阵。

---

## 1. 宿主应用版本与源码版本核对

| 项 | 当前基线 | 证据 | 来源 |
| --- | --- | --- | --- |
| 宿主应用（Kaiming） | cn.kylin.kylin-aiassistant **3.0.67**，x86_64 | ABI_VERIFIED / E3 | 01 表21、表10 |
| 真实 ELF 路径 | /opt/kaiming/layers/stable/x86_64/app/cn.kylin.kylin-aiassistant/binary/3.0.67/files/bin/kylin-aiassistant | E3 | 01 表37 |
| ELF Build ID | 409634237f8c49aa7d235932804a4febf80cb8b3（已记录 SHA-256） | E3 | 01 表21 |
| Kaiming Runtime 层 | stable:top.openkylin.ukui/1.1.40/x86_64 | E3 | 03 表5 |
| 上游 AI 助手源码 | 调查源码显示 **3.2.2** | SOURCE_VERIFIED / E2 | 01 表10 |
| 核心依赖 | libkyai-assistant.so.1、libkyai-config.so.1、QtSql、QtDBus、Speech SDK 等 | E3 | 01 表21 |
| 关键导入符号 | chatAsync、setChatAsyncCallback、initWithChatHistory、stopChat、clearContext、Prompt 管理、模型选择 | ABI_VERIFIED / E3 | 01 表21 |
| 未直接导入 | Recollect Client、Embedding SDK、Vector Engine Client | E3 | 01 表21 |
| 聊天数据库 | ~/.config/kylin-aiassistant/kylin_aiassistant_database.db | E4 | 01 表37 |
| Assistant Runtime Socket | /tmp/.kylin-ai-runtime-unix/\<uid\>/assistant.sock | E3 | 01 表37、03 表9 |
| 项目 Memory UDS（拟建） | $XDG_RUNTIME_DIR/kylin-memory/memory.sock | UNTESTED / E0 | 03 表9 |

**版本核对结论：**

- 宿主二进制 3.0.67 与上游源码 3.2.2 存在版本差，但 01 文档明确"核心类与 ABI 高度一致"（01 表10）。
- 风险 AGT-001（01 表31）：源码 Commit 未精确匹配，精确代码行与字段可能变化。**处置：** 按类/函数语义定位 Hook 点，最终分支落地前在实际采用源码分支重新静态核对；不硬编码行号。
- 01 文档表35 风险 R2 已将该版本差定为"中高"，控制方式为"按类/函数语义定位；最终分支重新静态核对"。
- **当前不应依赖（01 表37）：** RECORD.ID、未导出的模型列表接口、虚构 memory_context JSON 字段。

---

## 2. OS Agent 调用链图

### 2.1 官方组件总体调用关系

```
┌─────────────────────────────────────────────────────────────────────┐
│                        麒灵 AI 助手 (Qt5/QML)                        │
│  cn.kylin.kylin-aiassistant 3.0.67                                  │
│                                                                     │
│  QML UI层 ──> C++ ViewModel ──> SystemChat                          │
│                                   │                                  │
│                                   ├─ sendMessageImpl()  [Hook点A]   │
│                                   │    │                             │
│                                   │    ├─ buildDisplayMessage()      │
│                                   │    ├─ buildModelRequest()        │
│                                   │    ├─ [MemoryClient.retrieve] ← 拟新增(Pre-Chat)
│                                   │    ├─ chatDatabase.save(原文)    │
│                                   │    └─ OsAssistant::chatAsync()   │
│                                   │         │                         │
│  CMsgPane <── setChatAsyncCallback <─── 流式回调 ──────────────────┘
│      │                                                              │
│      ├─ is_end=false ×N  (流式中间分片, H2B实测61次)                 │
│      ├─ is_end=true  ×1  (唯一完成事件, [Hook点B: Post-Turn])        │
│      │      ├─ 合并完整回答 recvMessage                              │
│      │      ├─ TurnFinalizedEvent (拟新增)                           │
│      │      └─ recvMessage.clear()                                  │
│      └─ updateBubble (UI聚合, H2B实测17次)                           │
│                                                                     │
│  聊天SQLite ──> RECORD 表 (rowid 递增, H2B 实测 20→22)               │
└─────────────────────────────────────────────────────────────────────┘
        │ libkyai-assistant.so.1
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  kylin-ai-runtime 1.2.0.4-0k0.1                                     │
│  /tmp/.kylin-ai-runtime-unix/<uid>/assistant.sock                   │
│  本地/云端模型调用与运行时调度                                        │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 普通文本聊天调用链（已验证，AGT-002 HOST_VERIFIED / E4）

| 阶段 | 调用点 | 证据 | H2B 实测数据 |
| --- | --- | --- | --- |
| 发送 | SystemChat::sendMessageImpl → OsAssistant::chatAsync | E4 | — |
| 流式回调 | setChatAsyncCallback | E4 | chatCallback 关键词 124 行 |
| 中间分片 | is_end=false | E4 | 61 次 |
| 唯一完成 | is_end=true | E4 | 1 次 |
| UI 更新 | updateBubble | E4 | 17 次 |
| 落库 | RECORD 表新增 | E4 | rowid 20→22，无延迟落库 |

**关键结论（01 表23）：** Pre-Chat 位于 SystemChat 最终 chatAsync 之前；Post-Turn 语义位于唯一 is_end=true 的最终回调阶段。最终注入字段和精确源码行需在实际采用源码分支重新确认。

### 2.3 多路径状态总览（01 表25）

| 路径 | 状态 | 证据 | 当前结论 |
| --- | --- | --- | --- |
| 普通文本发送与流式回答 | HOST_VERIFIED | E4 | 主调用链、唯一结束帧、落库已验证 |
| Prompt/文本 Skill 回答 | PARTIAL | E2/E4 | 可见回答成功，但未证明进入独立 tool_call |
| 真实 Tool Call/Result | PARTIAL | E2/E4 | 源码存在 sendToolMessage 等路径；宿主独立事件未捕获 |
| 停止生成 Stop | SOURCE_VERIFIED | E2 | ABI/源码存在 stopChat；事件去重与记忆状态未测 |
| 重试 Retry | UNTESTED | E0 | 需验证 parent turn、重复事件与 PromptId |
| 语音聊天 | SOURCE_VERIFIED | E2 | 源码存在独立 OsAssistant 调用；宿主未测 |
| 文件问答/DocParse | SOURCE_VERIFIED | E2 | 源码可见；宿主未测 |
| 会议/FollowUp | SOURCE_VERIFIED | E2 | 源码可见；宿主未测 |
| Memory Context 注入格式 | UNTESTED | E0/E2 | 不能虚构 memory_context 字段；需契约实验 |
| Kaiming → Memory Service IPC | UNTESTED | E0 | 技术栈已选 UDS，宿主权限仍需实测 |

### 2.4 聊天数据库边界（01 表24，AGT-003 HOST_VERIFIED / E4）

| 表 | 已确认字段 | 边界 |
| --- | --- | --- |
| RECORD | sessionID、msgIndex、message、operateTime；隐式 rowid 稳定递增 | ID 字段未形成有效递增值；**不得依赖 MAX(ID)** |
| MEETINGRECORD | meetingID、msgIndex、message、summary、fileName、filePath | 会议路径尚未动态验证 |
| HISTORY_ID | history_id | 不包含完整记忆治理字段 |

**原文污染红线（01 §7.3 / 02 §4.1）：** 聊天 Schema 没有"原始用户文本"和"模型增强文本"的独立字段，也没有 Memory Context、记忆来源、证据或版本字段。任何记忆注入不得原地修改随后写入 RECORD.message 的用户文本，否则会污染聊天历史并造成记忆自循环。

### 2.5 官方组件未导入清单（01 表21）

宿主 3.0.67 ELF **未直接导入**：Recollect Client、Embedding SDK、Vector Engine Client。

**含义：** AI 助手自身不持有向量化与向量检索能力；MemoryClient 必须由我方在 AI 助手进程内新增，并通过 UDS 连接我方独立 Memory Service（02 §3.1、§4.3）。

---

## 3. Hook 候选位置（Pre-Chat / Post-Turn / Tool 三项 Spike）

### 3.1 Hook 点 A：Pre-Chat 检索注入

**目标：** 在用户发送消息时，基于原始用户文本检索记忆，组装 Memory Context 合入 model_request，且不污染 UI 与聊天数据库。

**候选位置（02 §4.1）：** SystemChat::sendMessageImpl() 中，原始请求构造完成、调用 OsAssistant::chatAsync() 之前。

**最小修改语义（02 表8）：**

```cpp
OriginalMessage display_user_text = buildDisplayMessage(userInput);
ModelRequest model_request = buildModelRequest(display_user_text);

MemoryQuery query = MemoryQuery::from(display_user_text, sessionContext);
MemoryContext memory = memoryClient.retrieve(query, 150ms);

if (memory.ok()) {
    model_request = memoryAssembler.augment(model_request, memory);
}

chatDatabase.save(display_user_text);     // 不保存内部记忆上下文
osAssistant.chatAsync(model_request.json());
```

**禁止事项（02 表9）：** 禁止原地修改 userText 后同时用于 UI、聊天数据库和模型请求，否则内部记忆会污染用户可见历史，并可能在下一轮被重新抽取成"新记忆"。

**Spike 验证项（D2 执行）：**

| 编号 | 验证目标 | 方法 | 通过标准 |
| --- | --- | --- | --- |
| H2C-PreChat-1 | UI 显示原始用户文本 | 注入后截图对比 | 用户可见文本不含 Memory Context |
| H2C-PreChat-2 | 数据库 message 不含 Memory Context | 查询 RECORD.message | 与用户输入一致 |
| H2C-PreChat-3 | 模型请求使用了记忆 | 抓取 chatAsync 入参 | model_request 含 Memory Context |
| H2C-PreChat-4 | MemoryClient 超时降级 | 断开 UDS | 聊天继续，返回空上下文 |

### 3.2 Hook 点 B：Post-Turn 回合观察

**目标：** 在模型流式回答完成、完整回答仍可取得、内部缓冲区清空之前，发布 TurnFinalizedEvent，触发异步记忆提取。

**候选位置（02 §4.2）：** CMsgPane 最终 is_end=true 回调，完整分片合并完成、recvMessage 清空之前。

**最小修改语义（02 表10）：**

```cpp
if (isEnd) {
    const QString finalAnswer = recvMessage;
    TurnFinalizedEvent event{
        .sessionId = sessionId,
        .userText = originalUserText,
        .assistantText = finalAnswer,
        .status = TurnStatus::Completed,
        .source = TurnSource::TextChat
    };
    memoryClient.observeTurnAsync(event);
    recvMessage.clear();
}
```

**约束（02 §4.2）：** 发布事件必须快速返回，不得在 QML/UI 线程中执行向量化或冲突计算（异步写入原则，02 表6）。

**Spike 验证项（D2 执行）：**

| 编号 | 验证目标 | 方法 | 通过标准 |
| --- | --- | --- | --- |
| H2C-PostTurn-1 | 唯一 is_end=true 触发一次 TurnFinalizedEvent | 日志计数 | 1 次，不重复 |
| H2C-PostTurn-2 | 完整回答可取得 | 比对 event.assistantText 与 UI | 一致 |
| H2C-PostTurn-3 | Stop 生成不形成稳定知识 | 停止后观察事件 | status=Cancelled，不沉淀 |
| H2C-PostTurn-4 | 事件发布不阻塞 UI | 测量回调耗时 | <50ms 返回 |

### 3.3 Hook 点 C：Tool Result 观察

**目标：** 捕获真实 Tool 成功/失败/取消结果，形成结构化 ToolExecutionEvent。

**当前状态（01 表25 / 表31，AGT-004 PARTIAL / E2·E4）：**

- 源码存在 sendToolMessage 等路径（E2）。
- 文本 Skill 回答可见（E4），但未证明进入独立 tool_call。
- **宿主独立 Tool 事件未捕获。**

**候选位置（02 §10.3）：** sendToolMessage 调用路径与 Tool 结果回调。精确 Hook 点需在源码分支确认。

**ToolExecutionEvent 业务 Schema（02 表31）：**

```
ToolExecutionEvent
- tool_call_id
- tool_name
- arguments
- started_at
- finished_at
- status          (success / failure / cancelled)
- result
- error
- side_effect
- user_confirmed
- rollback_status
- source_trace_id
```

**边界红线（02 表32）：** Tool Result Adapter 的业务 Schema 可以开发，但真实宿主 Hook 仍需定向验证。翻译、润色、总结等 Prompt Skill **不得**作为真实 tool_call 证据。

**Spike 验证项（D2 执行，对应 TD-007）：**

| 编号 | 验证目标 | 方法 | 通过标准 |
| --- | --- | --- | --- |
| H2C-Tool-1 | 真实 Tool 成功事件 | 触发一次成功 Tool | 结构化 ToolExecutionEvent(status=success) |
| H2C-Tool-2 | 真实 Tool 失败事件 | 触发一次失败 Tool | status=failure，error 字段完整 |
| H2C-Tool-3 | Tool 取消事件 | 中断 Tool | status=cancelled |
| H2C-Tool-4 | Prompt Skill 不被误判为 Tool | 触发翻译/润色 | 不生成 tool_call 证据 |
| H2C-Tool-5 | 失败 Tool 不形成成功知识 | 检查知识候选 | 仅 FailureMemory |

---

## 4. 三项 Spike 最小 Diff 计划

### 4.1 总体策略

- **不重写**聊天 UI、模型配置和流式模型运行时（02 §1.2）。
- 在 OS Agent 应用编排层加入**轻量 MemoryClient**（C++/Qt），通过 UDS 连接 Python Memory Service（02 执行摘要）。
- 三项 Hook 在 D1 只产出**修改点与最小 Diff 计划**；实际编码在 D4（工程骨架）与 D5（首个真实垂直链路）执行。
- D2 先执行 Memory Context 注入实验与真实 Tool 事件实验（台账 D2-C）。

### 4.2 MemoryClient 最小接口（C++ 侧，02 §4.3 / 表11）

**MemoryClient 负责：**

- 连接与断线恢复
- 长度前缀编码与 JSON 序列化
- 请求 ID、Trace ID、协议版本
- 超时、取消、错误映射和降级
- 健康检查与状态通知

**MemoryClient 不负责：**

- 偏好提取算法、数据库事务、Embedding/Vector 业务策略、冲突解决、生命周期、精准遗忘范围判断

**IPC 契约示例（02 表12，长度前缀 JSON）：**

```json
{
  "protocol_version": "1.0",
  "request_id": "req_01J...",
  "trace_id": "trc_01J...",
  "method": "memory.retrieve",
  "deadline_ms": 150,
  "payload": {
    "user_id": "local-user",
    "session_id": "session-uuid",
    "query_text": "用户当前问题",
    "scene": "software_development",
    "max_context_tokens": 800
  }
}
```

### 4.3 最小 Diff 文件清单（计划，D4/D5 落地）

| 文件 | 改动类型 | 说明 | 关联 Hook |
| --- | --- | --- | --- |
| aiassistant-integration/memory_client.h/.cpp | 新增 | C++ MemoryClient：QLocalSocket + 长度前缀 JSON 编解码 + 超时降级 | A/B/C |
| aiassistant-integration/memory_query.h | 新增 | MemoryQuery / MemoryContext / TurnFinalizedEvent / ToolExecutionEvent C++ 结构（D3 冻结） | A/B/C |
| SystemChat::sendMessageImpl | 修改 | 在 chatAsync 前插入 retrieve + augment；保留 display_user_text 原文落库 | A |
| CMsgPane 最终 is_end=true 回调 | 修改 | 在清空前发布 TurnFinalizedEvent，observeTurnAsync | B |
| sendToolMessage 路径 | 修改 | 注入 ToolExecutionEvent 观察点（精确行待源码分支确认） | C |
| aiassistant-integration/memory_view_model.h/.cpp | 新增 | QML 公共 ViewModel，供记忆中心/偏好/冲突/遗忘页面调用 | — |

**约束（02 §16.10 步骤9）：** C 在 worktree-memory-client 开发 C++ UDS Client；D 在 worktree-memory-gateway 开发 Python Gateway。双方只依赖冻结的协议样例，不同时修改同一文件。

---

## 5. 最小修改任务卡（按 02 文档附录 A 模板）

```
任务编号：D1-C-OSAGENT-SPIKE
任务标题：OS Agent 调用链定位与 Hook/Context/Tool Spike 修改点计划
责任轨道：C · OS Agent 与 Qt/QML
负责人：刘承恩
Reviewer：D 主审（周子腾）；用户交互与安全由 E 补审（谢嘉然）
基线分支与 Commit：待 D4 建立 worktree-memory-client（02 §16.10）

目标：
  1. 定位官方 AI 助手发送请求、最终 is_end、Tool 结果和 QML 数据流位置。
  2. 核对宿主应用版本与可获得源码版本。
  3. 输出 Hook、Context、Tool 三项 Spike 的修改点和最小 Diff 计划。

修改范围：
  - 本任务为 Spike 调查与计划，D1 不修改生产代码。
  - 产出本文档（调用链图 + Hook 候选位置 + 最小修改任务卡）。
  - D2 执行 H2C-PreChat / H2C-PostTurn / H2C-Tool 宿主实验。
  - D4 建立 C++ MemoryClient 与 QML 工程骨架。
  - D5 打通首个真实垂直链路。

禁止修改范围：
  - 官方 SDK 头文件（01 §5.3、03 §8.1）。
  - 已冻结 IPC/Schema（D3 冻结前为候选，02 §16.8）。
  - 聊天 SQLite RECORD.message 原文（01 §7.3 红线）。
  - 任务范围外模块（Embedding Bridge=A、Vector Store=B、Service 基础设施=D、业务/安全/评测=E）。

输入契约：
  - 宿主二进制 3.0.67 ELF 符号（01 表21）。
  - H2B 流式回调证据（01 表22）。
  - 聊天数据库 Schema（01 表24）。
  - 02 文档 §4 Pre-Chat/Post-Turn 语义与代码示例。

输出契约：
  - OS Agent 调用链图（本文 §2）。
  - Hook 候选位置与最小 Diff 计划（本文 §3、§4）。
  - D2 宿主实验任务项（H2C-PreChat/PostTurn/Tool）。

错误语义：
  - MemoryClient 超时/不可用：返回空 MemoryContext，聊天继续（02 表6 聊天优先）。
  - Tool 事件未捕获：不生成 tool_call 证据，登记 TD-007（High）。
  - 版本不匹配：按类/函数语义定位，最终分支重新静态核对（01 表35 R2）。

安全边界：
  - 原文隔离：UI/聊天库保存 original_user_text；Memory Context 只进入 model_request（02 表6）。
  - 失败 Tool 不得形成成功知识（02 表22 示例）。
  - 跨用户操作在 Repository 层与 Vector 过滤层同时限制（02 §10.1）。

WSL 可测项：
  - MemoryClient 协议编解码单元测试（长度前缀 JSON）。
  - MemoryQuery/MemoryContext/ToolExecutionEvent C++ 结构编译。
  - QML ViewModel Mock 契约测试。

麒麟 L2 必测项（D2/D5）：
  - H2C-PreChat：Context 注入实验，验证 UI/数据库/模型请求三路隔离。
  - H2C-PostTurn：唯一 is_end=true 触发一次 TurnFinalizedEvent。
  - H2C-Tool：真实 Tool 成功/失败/取消事件。
  - UDS 跨 Kaiming 可访问性（AGT-005 / IPC-001，01 表31）。

交付物：
  - 本任务卡文档（D1-C-OSAGENT-SPIKE）。
  - 调用链图、Hook 候选位置、最小 Diff 计划。

验收标准：
  - 调用链每条路径标注状态与证据等级，无静态推测冒充宿主验证。
  - Hook 点 A/B/C 均有修改位置、最小 Diff 语义与 D2 验证项。
  - 版本差风险已识别并有处置方案。
  - Reviewer（D）复核关键修改点与证据映射。

关联能力矩阵（01 表31）：
  - AGT-001 chatAsync ABI（ABI_VERIFIED / E3）
  - AGT-002 普通聊天流式完成（HOST_VERIFIED / E4）
  - AGT-003 聊天数据库落库（HOST_VERIFIED / E4）
  - AGT-004 真实 Tool Result（PARTIAL / E2·E4）→ D2 H2C-Tool
  - AGT-005 Memory Context 注入（UNTESTED / E0·E2）→ D2 H2C-PreChat
  - IPC-001 UDS 可访问性（UNTESTED / E0）→ D2 Echo
  - MEM-001 官方 MemoryClient（NOT_FOUND / E3）→ 按自研计划

关联 Bug / Blocker / Risk / TD：
  - Risk R2（01 表35）：AI 助手源码版本与 3.0.67 未精确对应（中高）。
  - Risk R3：真实 Tool Result 路径未证实（高）→ D2 优先 H2C-Tool。
  - Risk R4：Memory Context 注入契约未确认（高）→ D2 契约实验。
  - Risk R5：Kaiming 到自定义 UDS 未实测（高）→ D2 Echo。
  - TD-007（02 §17.6）：真实 Tool Result Hook 尚未完成宿主验证（High，PLANNED）。
```

---

## 6. D1 → D2 衔接

D1 已完成调查与计划，D2（台账 D2-C）将执行三项宿主实验：

1. **Memory Context 注入实验**（H2C-PreChat）：比较 UI、聊天库和模型请求，验证原文隔离。
2. **真实 Tool 成功/失败/取消事件实验**（H2C-Tool）：捕获结构化 ToolExecutionEvent，关闭 TD-007。
3. **最终回合只产生一次 TurnFinalizedEvent**（H2C-PostTurn）：验证 is_end=true 唯一性。

D2 证据要求（02 §16.14 步骤14）：必须来自当前 Commit 的麒麟虚拟机，截图/日志/数据库变化齐备，不允许用 WSL 或 Reasonix 沙箱替代。

---

## 7. 证据来源索引

| 证据 | 路径/文件 | 用途 |
| --- | --- | --- |
| AI 助手 H1 | assistant_contract_h1.txt | 3.0.67 ELF、ABI、数据库 Schema、Recollect 导入边界 |
| AI 助手 H2B | summary(2).txt、log_structure.jsonl、db_snapshots.jsonl | 流式回答、唯一 is_end、rowid 落库、运行库状态 |
| 系统调查 | probe_v2.txt | Kaiming、进程、D-Bus、Recollect、动态库、配置 |
| 能力矩阵 | 01 文档 §11 | AGT-001~005、IPC-001、MEM-001~002 |
| 架构决策 | 02 文档 §4 | Pre-Chat/Post-Turn Hook 语义与代码示例 |
| 环境基线 | 03 文档 §3-§5 | 宿主版本、Runtime 路径、Socket、模型目录 |

---

## 8. 自检清单（01 文档附录 C）

| 检查项 | 完成 |
| --- | --- |
| 调查结论基于真实宿主证据或明确标注 SOURCE/UNTESTED，未用静态推测冒充宿主验证 | √ |
| 记录 OS/包/ABI/源码分支和调查日期 | √ |
| 未包含 API Key 或聊天敏感原文 | √ |
| 检查结果真实性，而非只看返回码 | √ |
| Hook 点标注修改位置、最小 Diff 语义与验证项 | √ |
| 待 D Reviewer 复核，且未审查自己的修改 | □ 待 D 复核 |
| 版本差风险已识别并有处置方案 | √ |
| 同步能力矩阵影响（AGT-001~005 状态不变，D2 升级） | √ |

---

## 9. 边学边开发记录（02 文档附录 E）

- **模块：** 轨道 C · OS Agent 与 Qt/QML
- **本轮任务：** D1 调用链定位与 Hook Spike 计划
- **开发前需理解的概念：** SystemChat/OsAssistant/CMsgPane 调用链、is_end 语义、聊天数据库 Schema、原文隔离原则
- **官方接口与本项目边界：** 官方已有聊天/流式/落库；我方新增 MemoryClient + Pre/Post Hook + Tool Adapter，不重写 Runtime
- **数据流：** QML → SystemChat → (Pre-Chat Hook) → chatAsync → 流式回调 → (Post-Turn Hook) → 落库；Tool → (Tool Hook) → ToolExecutionEvent
- **关键设计决策及原因：** Hook 点选在 chatAsync 前 / is_end=true / sendToolMessage，因为这是不侵入 Runtime 的最轻量接入点
- **常见错误：** 原地修改 userText 污染历史；把 Prompt Skill 当真实 Tool；依赖 RECORD.ID
- **如何测试：** D2 在麒麟虚拟机执行 H2C-PreChat/PostTurn/Tool
- **宿主证据证明了什么：** 普通聊天主链、唯一结束帧、落库已验证；Pre-Chat/Post-Turn 语义位置已确认
- **仍未知内容：** 精确源码行、真实 Tool 独立事件、Memory Context 注入字段格式、UDS 跨 Kaiming 权限
- **开发者能否独立复述和演示：** 是
