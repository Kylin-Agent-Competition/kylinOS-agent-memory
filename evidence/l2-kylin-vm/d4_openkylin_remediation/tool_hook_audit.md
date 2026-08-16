# Tool Result Hook (Hook C) 调用链审计报告

> **任务**: `OPENKYLIN_BLOCKER_REMEDIATION_PLAN.md` 阶段 4
> **关联**: D1 任务卡 §3.3 Hook C、TD-007、R-ARCH-05
> **执行环境**: 麒麟 VM (KylinOS V11 x86_64)
> **源码**: openkylin/kylin-aiassistant @ commit `5a89601`
> **审计日期**: 2026-08-15

---

## 一、结论摘要

kylin-aiassistant 的 Tool 调用链已完整定位。核心结论：

1. **Tool 触发**（出站）由 `SystemChat::sendToolMessage()` 承载，构建 `message_type=tool_call` 的 JSON 后通过 `m_osassistant->chatAsync()` 发送。
2. **Tool 结果**（回程）在流式消息解析器中处理 `messageType == "tool_call"` 分支，并通过 `toolReply` 信号回传 UI。
3. **Tool Result Hook 点**（真实宿主观察点）为 `CMsgPane::onRecvTool()`（`toolReply` 信号的唯一槽函数），该处同时具备成功/失败判定（`errorCode`）、tool 名（`imageToolMap`）、结果文本（`msg`）。
4. 当前 `toolReply` 信号**未携带** `arguments`、`tool_call_id`、`started_at`、`cancelled` 状态等字段——这是真实宿主集成时需补齐的源码缺口（详见 §四）。

---

## 二、完整调用链

### 2.1 出站：Tool 触发

```
QML (Chat.qml)  →  CMsgPane::xxx  →  SystemChat::sendToolMessage(toolId, fileType, para)
                                      → m_osassistant->chatAsync(json)
```

**触发点**（UI 层）:

| 位置 | 文件:行 | 说明 |
|------|--------|------|
| 图片生成 | `kylin-aiassistant/msgpane.cpp:3275` | `sendToolMessage(toolId, IMAGE, imagePathTem)` |
| 源文档 | `kylin-aiassistant/msgpane.cpp:3626` | `sendToolMessage(toolId, SOURCE, "")` |
| 日程 | （由 schedule 分支处理，见 2.2） | `fileType == SCHEDULE` |

**实现** `systemchat.cpp:692-755`:

```cpp
void SystemChat::sendToolMessage(int toolId, FileType fileType, QString para)
{
    if (m_osassistant == nullptr) { ... return; }
    QJsonObject jsonObject;
    jsonObject["message_type"] = "tool_call";
    QString type;          // IMAGE→"image", DOCUMENT→"document",
                           // SOURCE→"source_url", SCHEDULE→"schedule"
    jsonObject["file_type"] = type;
    QJsonArray contentArray;
    // tool_id / image_url / schedule_date ...
    jsonObject["content"] = contentArray;
    m_osassistant->chatAsync(jsonDoc.toJson().toStdString());  // :754
}
```

### 2.2 回程：Tool 结果解析

```
kylin-ai-runtime (assistant.sock)
  → m_osassistant 流式回调
  → SystemChat 流式消息解析器 (systemchat.cpp:88)
      if messageType == "tool_call":
        解析 content[] → toolMap (tool_id → tool_name), text
        读取 error_code / error_message / file_type / model / feedback_url
        if fileType == "image":
            Q_EMIT toolReply(msg, toolMap, imageUrl, errorCode, model, feedbackURL)  // :117-120
        if fileType == "schedule" (toolId 21/22):
            Q_EMIT reply(InnerMessage("tool_call", ..., errorCode, ...))            // :134 / :143
```

关键片段 `systemchat.cpp:88-120`:

```cpp
if(messageType == "tool_call"){
    for(const QJsonValue &value: contentArray) {
        if(itemObject["type"] == "text")
            systemChat->text = itemObject["text"].toString();
        if(itemObject.contains("tool_id") && itemObject.contains("tool_name"))
            toolMap.insert(itemObject["tool_id"].toInt(),
                           itemObject["tool_name"].toString());
    }
    for(auto i = toolMap.begin(); i != toolMap.end(); ++i)
        KyInfo() << "toolid:" << i.key() << "toolName:" << i.value();  // :111
    ...
    if(errorCode != 0)
        Q_EMIT systemChat->toolReply(errorMsg, toolMap, imageUrl, errorCode, model, feedbackURL);  // :117
    else {
        Q_EMIT systemChat->toolReply(systemChat->text, toolMap, imageUrl, errorCode, model, feedbackURL);  // :120
        KyInfo() << "________________emit toolReply success";
    }
}
```

### 2.3 UI 渲染：Tool 结果落 UI

**信号声明** `systemchat.h:84`:

```cpp
void toolReply(const QString &message, QMap<int, QString> imageToolMap,
               QString imageUrl, int errorCode, QString model, QString feedbackURL);
```

**连接** `msgpane.cpp:146`:

```cpp
connect(m_chat, &SystemChat::toolReply, this, &CMsgPane::onRecvTool);
```

**槽函数** `msgpane.cpp:1243-1285`:

```cpp
void CMsgPane::onRecvTool(QString msg, QMap<int, QString> imageToolMap,
                          QString imagePath, int errorCode,
                          QString model, QString feedbackURL)
{
    if(errorCode != 0) {                 // 失败路径
        errorMessageToJs("", "ai", "red", msg);
        clearJsonMessage();
        return;
    }
    // 成功路径：构建 pictureOperates JSON → pushMsg("appendRecvTool", ...)
    ...
}
```

---

## 三、Hook 点选择

| 候选 | 位置 | 优点 | 缺点 | 结论 |
|------|------|------|------|------|
| **P1** | `CMsgPane::onRecvTool()` (msgpane.cpp:1243) | 唯一汇聚点，具备 success/failure 判定、tool 名、结果文本；QML 层最轻量接入 | 无 `arguments`/`started_at`（需上游补充） | ✅ **选用** |
| P2 | `toolReply` emit 处 (systemchat.cpp:117-120) | 更靠近数据源 | 需穿透 QThread 信号语义；字段同 P1 | 备选 |
| P3 | 流式解析器 tool_call 分支 (systemchat.cpp:88) | 原始 JSON 最完整 | 侵入 Runtime 回程解析，风险高 | 不选 |

**最终 Hook 点**: `CMsgPane::onRecvTool()` 入口 + `SystemChat::sendToolMessage()` 入口（配对记录 started_at / arguments）。

---

## 四、ToolExecutionEvent Schema 字段映射（02 表31）

| Schema 字段 | 源码来源 | 可用性 |
|-------------|---------|--------|
| `tool_call_id` | 无（toolReply 未携带独立 call id） | ❌ 需源码补齐或派生 |
| `tool_name` | `imageToolMap.values()` (toolId→toolName) | ✅ |
| `arguments` | `sendToolMessage` 的 `para`（未透传到 onRecvTool） | ⚠️ 仅出站路径可得 |
| `started_at` | 未追踪（需在 sendToolMessage 打时间戳） | ⚠️ 需新增 |
| `finished_at` | 未追踪（需在 onRecvTool 打时间戳） | ⚠️ 需新增 |
| `status` | `errorCode == 0 ? success : failure` | ✅（success/failure）；cancelled 未追踪 ❌ |
| `result` | `msg`（errorCode==0 时） | ✅ |
| `error` | `msg`（errorCode!=0 时） | ✅ |
| `side_effect` | 无 | ❌ 宿主未暴露 |
| `user_confirmed` | 无 | ❌ 宿主未暴露 |
| `rollback_status` | 无（默认 `"none"`） | ✅（默认值） |
| `source_trace_id` | 无 | ❌ 需上游注入 trace |

**关键源码缺口**（真实宿主集成需补齐，本次 spike 已如实标注）:
1. `tool_call_id` / `source_trace_id` 未在 toolReply 链路出现。
2. `cancelled` 状态未显式建模（停止生成走 `stopChat()`，不经过 toolReply 的 cancelled 分支）。
3. `arguments` 仅在出站 `sendToolMessage` 可见，未随回程信号透传。
4. Prompt Skill（翻译/润色/总结）走普通 `reply` 文本流，**不产生** `message_type=tool_call`，天然满足"不得误判为 tool_call"边界（T4 场景的源码级依据）。

---

## 五、最小修改 patch 说明

见同目录 `tool_hook_patch.diff`。patch 内容：

1. 新增头文件 `kylin-aiassistant/kylin-aiassistant/tool_execution_observer.h`（header-only，无外部依赖），提供：
   - `toolStartJson(toolId, fileType, para)` — 出站观察点
   - `toolResultJson(toolName, errorCode, result, model, startedAt)` — 回程观察点
   - 两者输出符合 02 表31 的 `ToolExecutionEvent` JSON 结构，缺失字段标注为空/默认。
2. `systemchat.cpp::sendToolMessage` 入口注入 `[ToolInvocation]` 日志（started_at + arguments）。
3. `msgpane.cpp::onRecvTool` 入口注入 `[ToolExecutionEvent]` 日志（status/result/error）。

**编译验证**: 新增头文件 `tool_execution_observer.h` 已通过 `g++ -fsyntax-only` 语法检查（`EXIT=0`）。完整 `qmake && make` 重编译**未通过**，原因是当前 VM 缺少完整构建环境（见 §七 S4-BLOCK-003）。

---

## 六、5 场景测试矩阵（T1-T5）结论

详见 `tool_result_test_matrix.log`。

| 场景 | 触发方式 | 结果 | 说明 |
|------|---------|------|------|
| T1 成功 Tool | GUI 图片/源文档触发 | ⬜ 未执行 | 需手动桌面操作 |
| T2 失败 Tool | GUI 触发失败场景 | ⬜ 未执行 | 需手动桌面操作 |
| T3 取消 Tool | GUI 中断 | ⬜ 未执行 | 需手动桌面操作 |
| T4 Prompt Skill 不误判 | 翻译/润色 | ✅（源码级） | 文本 Skill 不经过 tool_call 分支 |
| T5 失败不形成成功知识 | 检查知识候选 | ⬜ 未执行 | 依赖 T2 |

**阻塞原因**（见 §七）: 真实 Tool 触发是纯 GUI 驱动的（QML 按钮），SSH 环境下无 X11（`DISPLAY` 为空，桌面为 `kylin-wlcom` Wayland 合成器），且无 `xdotool` 自动化工具，无法通过命令行/dbus 注入 Tool 触发。dbus 接口 `org.ukui.kylin_aiassistant` 仅暴露 `showOrHideView()` 与 `showGlobalScribeFloatingBar()` 两个视图控制方法，无消息/Tool 注入能力。

---

## 七、残余阻塞项（阶段 4 新增）

| 编号 | 描述 | 状态 | 解除方案 |
|------|------|------|---------|
| S4-BLOCK-001 | 真实 Tool 触发为 GUI-only，SSH 环境无法自动化（Wayland 无 xdotool） | **BLOCKED** | 手动操作麒麟桌面 AI 助手触发 Tool（图片生成/源文档/日程）；或引入 X11 + xdotool 自动化 |
| S4-BLOCK-002 | `toolReply` 信号缺 `arguments`/`tool_call_id`/`started_at`/`cancelled` 字段 | **OPEN（源码缺口）** | 真实宿主集成阶段在源码补字段（需重新走 KYSEC 授权 + 部署回退链路） |
| S4-BLOCK-003 | 当前 VM 缺完整构建环境（~40 个 `-dev` 包缺失，仅运行时库），无 sudo 无法安装，qmake 报 `gsettings-qt development package not found` | **BLOCKED** | 在 VM 内 `sudo apt-get build-dep kylin-aiassistant`（需 sudo 权限）；或使用 kylin-ai-subsystem 的 build-deploy.sh；或在带完整 dev 依赖的构建环境交叉编译 |
| S4-BLOCK-004 | VM 无 `git`，无法用 `git diff` 生成 patch | **RESOLVED（本地 difflib 生成）** | 已用 Python difflib 在宿主机生成 `tool_hook_patch.diff` |

---

## 八、阶段 4 产出清单

| 文件 | 内容 |
|------|------|
| `tool_hook_audit.md` | 本报告 |
| `tool_hook_patch.diff` | ToolExecutionEvent 观察点最小 patch |
| `tool_execution_observer.h` | 观察点头文件（已上传 VM 编译） |
| `tool_hook_build.log` | patch 后编译日志 |
| `tool_result_test_matrix.log` | 5 场景测试结果（T4 源码级通过，其余需 GUI） |
