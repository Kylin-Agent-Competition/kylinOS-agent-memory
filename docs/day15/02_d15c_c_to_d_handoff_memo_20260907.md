# C→D Handoff Memo: D15C Host Mapping Closure

| 字段 | 内容 |
|------|------|
| 编号 | D15C-HANDOFF |
| 日期 | 2026-09-08 (D15 执行日) |
| 来源 | C 轨 (刘承恩)；任务卡 `01_d15c_host_mapping_closure_task_card_20260907.md` |
| 目标 | D 轨 (D 主审)；用于 R-ARCH-05 收敛、TD-007/008/009 关闭提请、D14C formal L3 G4/G5 输入 |
| 证据目录 | `evidence/l2-kylin-vm/d15c_20260908/` |
| tested_commit | kylin-aiassistant `5a89601` (V11 3.0.67 tag) |
| 状态 | HANDOFF_SUBMITTED (C 侧材料交付，D 轨评审待定) |

---

## 一、执行环境

| 项 | 值 |
|----|-----|
| VM | bacon VM (银河麒麟 V11 x86_64, Qt 5.15.19) |
| SSH | `ssh -p 2222 bacon@127.0.0.1` |
| 宿主源码 | gitee kylin-aiassistant @ `5a89601` (tag 3.0.67) |
| 构建工具链 | qmake + make, DEVROOT 闭包 (Qt5/KF5 headers + libs) |
| 模型运行时 | `/usr/bin/kytensor` (--model-repository, --model-control-mode=explicit) |
| ChatSDK | kylin-aiassistant 内置 ChatSDK, `m_osassistant->chatAsync()` |
| 模型仓库 | `/opt/appdata/kylin-ai/model-repository/` (空) + `/usr/share/kylin-ai/model-repository/` (ASR/embedding/OCR/SAM/TTS, **无 LLM**) |
| 已安装模型包 | kylin-cn-clip-model, kylin-gte-base-model, kylin-paddle-ocr-model, kylin-portrait-matting-model, kylin-sam-model, kylin-speech-asr-model, kylin-speech-tts-model, kylin-ai-abstract-models |
| 缺失 | **无聊天 LLM 模型** (kylin-qwen2.5-3b-gguf-model 2.67GB 下载速度 ~1MB/min, 不实际) |
| offscreen 模式 | QT_QPA_PLATFORM=offscreen (绕过 Wayland 协议错误) |

---

## 二、TD-007 出站 Hook 证据（VERIFIED）

### 2.1 Hook 部署

| 项 | 值 |
|----|-----|
| Patch 文件 | `tool_hook_patch.diff` (systemchat.cpp + msgpane.cpp) |
| Observer | `tool_execution_observer.h` (header-only, KyInfo JSON 输出) |
| 原二进制 SHA-256 | `86453fc660a47940c26031d87807cc735ea1cfd628a657f34a5c896cb0c7ccf6` |
| 补丁二进制 SHA-256 | `a712d541496934520092d0688cd2be0e26d7c7cbd2fe254551f0af8dc06a82f0` |
| 部署路径 | `/var/opt/kaiming/layers/stable/x86_64/app/cn.kylin.kylin-aiassistant/binary/3.0.67/files/bin/kylin-aiassistant` |
| 回退验证 | 原二进制还原, SHA-256 一致, 助手可启动 (PID 187375/187390) |

### 2.2 出站 tool_invocation 事件（成功态）

触发方式: 直接调用 `onPictureOperateClick(3, "/home/bacon/d15c_test_img.png")` (图片分析 toolId=3), 绕过 GUI 流程。

日志时间戳: `2026-09-08 16:01:15.029`

出站 JSON (systemchat.cpp:756, `toolStartJson()` 输出):

```json
{"arguments":"/home/bacon/d15c_test_img.png","event":"tool_invocation","file_type":"image","started_at":"2026-09-08T16:01:15","tool_id":3}
```

字段覆盖:
| 字段 | 值 | 来源 |
|------|-----|------|
| event | `tool_invocation` | tool_execution_observer.h |
| tool_id | `3` (integer) | systemchat.cpp sendToolMessage 参数 |
| arguments | `/home/bacon/d15c_test_img.png` | 图片路径 |
| file_type | `image` | systemchat.cpp 推断 |
| started_at | `2026-09-08T16:01:15` | tool_execution_observer.h 时间戳 |

### 2.3 环境前置阻塞（失败态未采集）

ChatSDK 回调 `chatCallback` (systemchat.cpp:79) 立即返回 `"model is empty"` — 运行时无聊天 LLM 模型可用, 请求未到达推理服务器。这是环境 / 前置条件失败，**不计为一次真实 Tool 执行后的 failure result**。

日志: `2026-09-08 16:01:15.031 | chatCallback | model is empty`

### 2.4 取消态

**NOT_OBSERVED** — 宿主未显式建模取消事件。`tool_execution_observer.h` 中 `cancelled` 字段留空标注, 不编造。

---

## 三、TD-008 Hook 点 A 结论（AMBIGUOUS）

### 3.1 chatAsync 入参捕获

`sendToolMessage` (systemchat.cpp:692-755) 构造 JSON 并调用 `m_osassistant->chatAsync(jsonDoc.toJson().toStdString())`。

出站 JSON 内容已完整捕获 (见第二节)。关键字段检查:

| 检查项 | 结果 |
|--------|------|
| memory_context | **不存在** |
| context | **不存在** |
| history | **不存在** |
| session_id | **不存在** |
| trace_id | **不存在** |

### 3.2 结论: AMBIGUOUS

- **源码层面**: `sendToolMessage` 构造的 chatAsync 入参 **不含** `memory_context` / `context` / `history` 类注入字段。
- **运行时层面**: ChatSDK 返回 `"model is empty"` 立即退出, 请求未到达 kytensor 推理服务器, 无法确认 ChatSDK 内部是否在转发前注入上下文。
- **完整确认条件**: 需安装聊天 LLM 模型 (kylin-qwen2.5-3b-gguf-model 2.67GB) 后复测, 观察 chatCallback 回程是否携带 memory_context。

### 3.3 D 轨建议

1. 在具备 LLM 模型的环境中复测 TD-008, 确认 ChatSDK 内部行为;
2. 若 ChatSDK 确实不注入 memory_context, 则结论升级为 `NOT_IMPLEMENTED_IN_HOST`;
3. 若 ChatSDK 注入, 则结论升级为 `INJECTED`, 需定位注入点代码。

---

## 四、TD-009 实际 Tool 执行路径（整体 BLOCKED；出站 VERIFIED / 回程 BLOCKED）

### 4.1 执行路径结构化事件

| 阶段 | 事件 | 源码位置 | 状态 |
|------|------|----------|------|
| 出站 | `tool_invocation` (toolStartJson) | systemchat.cpp:756 | **VERIFIED** |
| 回程 | `ToolExecutionEvent` (toolResultJson) | msgpane.cpp:1118 (onRecvMsg) | **BLOCKED** |

出站路径: `onPictureOperateClick(3, imgPath)` → `sendToolMessage(toolId, type, para)` → `toolStartJson()` KyInfo 输出 → `m_osassistant->chatAsync(json)`

回程路径: ChatSDK `chatCallback` → `onRecvMsg` → (预期) `toolResultJson()` KyInfo 输出

### 4.2 回程阻塞原因

ChatSDK `chatCallback` 返回 `"model is empty"` (code=26), 未产生有效 ToolExecutionEvent 回程消息。`onRecvMsg` 收到空响应, 无 toolReply 信号。

### 4.3 Route B 评估

主 Hook (源码 instrument) 在出站方向可行且已验证。Route B (D-Bus 解码) 当前未激活；在真实 Hook 完成端到端成功 / 失败 / 取消三态验证前，继续按 ADR-004 保留为备份。回程 Hook 在 patch 中已就位 (msgpane.cpp `onRecvMsg` 打点), 仅待 LLM 模型到位后自然触发。

---

## 五、Production Identity 决策输入

### 5.1 Hook 事件标识

出站 `tool_invocation` JSON 使用 `tool_id` (integer `3`) 作为 **outbound tool selector / tool kind id**。该值对应 `systemchat.cpp` 中 `sendToolMessage` 的第一个参数, 源自 `onPictureOperateClick(3, ...)` 调用；它不是 Chat DB 行身份。

### 5.2 标识来源追踪

| 标识 | 值 | 来源 | 可用性 |
|------|-----|------|--------|
| tool_id | `3` (integer) | onPictureOperateClick 硬编码 | **可用** — 仅作为 outbound tool selector / tool kind id |
| rowid | 未观察 | Chat DB RECORD 表 | Production Identity 候选；需 P3 DB 只读查询 (未执行) |
| sessionID | 未观察 | ChatSDK 内部 | Hook 未捕获 |
| msgIndex | 未观察 | Chat DB RECORD 表 | 需 DB 只读查询 (回程阻塞, 未执行) |

### 5.3 决策结论

**Production Identity: `UNRESOLVED / BLOCKED`。**

依据:
1. `tool_id=3` 是宿主硬编码传入 `sendToolMessage` 的工具选择 / 类型标识, 会跨 session 和多次调用复用;
2. 当前没有证据证明 outbound `tool_id` 能映射到 Chat DB `RECORD` 行身份或 `rowid`;
3. P3 的只读 DB 时序对比未执行, `rowid / sessionID / msgIndex` 均未观察;
4. 在 P3 或其他可复核证据完成前, 禁止将 `tool_id` 或 `tool_id + started_at` 写入 `ref:chat-record:{messageId}` 所需的 Chat RECORD identity 字段。

**默认配置**: 保持 `fail-closed` (PRODUCTION_RESOLVER_STATUS 不变), 待 D 轨评审确认后调整。

### 5.4 需 D 轨补充

1. 在具备 LLM 模型的环境中执行 P3 (identity 时序对比): GUI 触发对话 → onRecvTool 打点时刻只读查询 Chat DB → 对比 Hook 事件时序与 RECORD 行 rowid/msgIndex 分配;
2. 在取得可复核的映射证据前, 不把 `tool_id` 解释为 `RECORD.ID`、`tools.rowid` 或任何 Chat DB 行身份;
3. D14C G4/G5 输入必须记录: 当前只证明 Hook 能拿到 tool selector, 尚未证明能拿到 Chat RECORD identity。

---

## 六、回退演练证据

| 步骤 | 结果 |
|------|------|
| 补丁二进制 SHA-256 | `a712d541496934520092d0688cd2be0e26d7c7cbd2fe254551f0af8dc06a82f0` |
| 原始备份 SHA-256 | `86453fc660a47940c26031d87807cc735ea1cfd628a657f34a5c896cb0c7ccf6` |
| 还原操作 | `sudo cp backup/layer-kylin-aiassistant.orig` → 部署路径 |
| 还原后 SHA-256 | `86453fc660a47940c26031d87807cc735ea1cfd628a657f34a5c896cb0c7ccf6` (一致) |
| 助手启动验证 | PID 187375/187390 运行 (offscreen 模式) |
| 回退命令 | 见 `deploy_manifest.txt` rollback_cmd 字段 |

---

## 七、Resolver 生产 Config 建议

| 配置项 | 当前值 | 建议 | 依据 |
|--------|--------|------|------|
| PRODUCTION_RESOLVER_STATUS | `fail-closed` | **保持不变** | TD-008 AMBIGUOUS, 未确认 memory_context 注入 |
| production identity | `UNRESOLVED / BLOCKED` | **不可选择 `tool_id`** | 当前仅有 outbound tool selector, 缺少 Chat RECORD 行身份证据 |
| Route B (D-Bus) | 未激活 | **保留为备份** | 真实 Hook 三态验证完成前不得解除备份地位 |

---

## 八、Trusted Host Identity 评估材料（C 侧输入）

### 8.1 宿主环境

- 银河麒麟 V11 x86_64, Kaiming 容器化部署 (overlay filesystem)
- KySec 路径执行控制 (read-only 层限制)
- ChatSDK 运行时: kytensor (model-control-mode=explicit)
- 真实 Chat DB: SQLite (RECORD 表 + JSON blob, 见 PR #151 S5r2 验证)

### 8.2 Hook 可信度评估

| 维度 | 评估 |
|------|------|
| 源码 instrument 可靠性 | **高** — header-only observer, 无外部依赖, KyInfo 原生输出 |
| 出站事件完整性 | **高** — tool_id + arguments + started_at + file_type 完整 |
| 回程事件完整性 | **低** — 阻塞于 ChatSDK "model is empty", 未验证 |
| identity 可获得性 | **BLOCKED** — tool selector 可用, rowid/msgIndex 未观察 |
| 部署安全性 | **高** — SHA-256 前后记录, 一键回退验证通过 |

### 8.3 D 轨评估所需补充

1. LLM 模型安装后的完整 round-trip 验证 (TD-008 升级, TD-009 回程确认);
2. P3 identity 时序对比 (Hook 时刻 vs DB 行写入时序);
3. D14C formal L3 在干净 VM 复测; G4/G5 输入须保持 Production Identity 为 UNRESOLVED/BLOCKED, 仅承认当前 Hook 捕获 outbound tool selector;
4. S5r3 服务端全链路 (memory-service 运行时栈, 条件项)。

---

## 九、证据清单

| 编号 | 文件 | SHA-256 | 状态 |
|------|------|---------|------|
| EV-001 | `d15c_20260908/td007_outbound_tool_invocation.json` | 见文件 | VERIFIED |
| EV-002 | `d15c_20260908/td008_chatasync_input_analysis.md` | 见文件 | BLOCKED（业务结论 AMBIGUOUS） |
| EV-003 | `d15c_20260908/td009_execution_path.md` | 见文件 | BLOCKED（出站 VERIFIED / 回程 BLOCKED） |
| EV-004 | `d15c_20260908/rollback_verification.md` | 见文件 | VERIFIED |
| EV-005 | `d15c_20260908/environment.json` | 见文件 | VERIFIED |
| EV-006 | `d15c_20260908/deploy_manifest.txt` | 见文件 | VERIFIED |

---

## 十、R-ARCH-05 收敛状态

| 条件 | 状态 |
|------|------|
| S3 Hook 观察点部署 | **完成** (出站 VERIFIED, 回程 BLOCKED on LLM) |
| S4 TD-007/009 三态采集 | **BLOCKED** (成功态出站 VERIFIED, 失败态 NOT_OBSERVED, 取消态 NOT_OBSERVED) |
| S5/L3 证据 | S5r2 已完成 (#151), S5r3 BLOCKED_ON_SERVICE_RUNTIME |
| C→D handoff | **本备忘录** |
| 收敛目标 | **仅剩 D14C formal L3 输入 + LLM 模型环境复测** |

R-ARCH-05 保持 `In Progress`, 收敛至「仅剩 D14C formal L3 输入 + LLM 模型环境复测」状态。
