# D2 · 轨道 C · OS Agent 宿主实验执行手册（H2C-PreChat / PostTurn / Tool）

> **当前审计结论（2026-08-08）：D2-C 为 BLOCKED，不得以本手册中的历史候选状态
> 宣称 Gate 通过。** PostTurn 尚缺数据库快照、15 秒稳定性和 UI/RECORD 一致性；
> PreChat 尚缺 UI 截图及已解码模型请求证明；Tool 尚缺成功、失败、取消的真实
> 结构化事件。必须由人在麒麟 VM 补采证据，并由 D/E 按职责复核。

> 赛题：XA-202612 OS Agent 记忆优化及高效应用研究
> 责任轨道：C · OS Agent 与 Qt/QML
> 开发者：刘承恩
> 日期：2026-07-30（D2，Gate 0：核心集成可行性验证）
> Reviewer：D 主审（周子腾）；用户交互与安全由 E 补审（谢嘉然）
> 依据：01 能力边界 v1.0 §7/§11（AGT-001~005）、02 总体架构 v1.0 §4/§16.15、03 环境配置手册 v1.0
> 状态：BLOCKED（2026-08-08 审计）。下文的候选状态和执行记录仅描述旧提交的部分观察，
> 不构成 D2-C 完成、Gate 通过或合并准入证据。
> 历史执行 Commit: 20adffc7449ad97f837108b02ce0dcc0d1d79f24
> 执行环境: Kylin-Desktop V11 / Linux 6.6.0-63-generic / VirtualBox

---

## 0. 任务来源与边界声明

**台账任务（D2-C）：**

1. 执行 Memory Context 注入实验，比较 UI、聊天库和模型请求。
2. 执行真实 Tool 成功/失败/取消事件实验。
3. 验证最终回合只产生一次 TurnFinalizedEvent。

**交付物：** 取得 Context 注入、Tool 事件和最终回合的真实宿主证据。

**关键边界（02 §16.15 步骤 14）：**

- L2 证据必须来自当前 Commit 的银河麒麟虚拟机，截图/日志/数据库变化齐备。
- 不允许用 WSL、Reasonix 沙箱或静态推测替代宿主验证。
- 本手册由 Agent 生成，提供只读/低风险观察脚本与执行步骤；**真实运行与证据采集必须由人在麒麟虚拟机完成**。
- Agent 职责：生成只读或低风险测试脚本，分析上传证据。
- 人职责：启动 VirtualBox 快照、同步当前 Commit、手动操作 UI、保存日志/数据库/截图。
- Reviewer 职责：核对日志是否来自当前 Commit、环境是否真实、是否有失败被忽略。

**当前 Commit 基线：** 执行前需在麒麟虚拟机同步到 `docs/C-d1-osagent-spike` 分支 HEAD（`8d52155`）或 D2 专用分支 HEAD，并记录实际 Commit SHA。

---

## 1. 实验前置准备

### 1.1 环境核对清单（人在麒麟虚拟机执行）

| 项 | 期望值 | 核对命令 |
| --- | --- | --- |
| 操作系统 | 银河麒麟桌面操作系统 V11 2603 x86_64 | `cat /etc/kylin-build` 或 `cat /etc/os-release` |
| 宿主应用 | cn.kylin.kylin-aiassistant 3.0.67 | `kaiming info cn.kylin.kylin-aiassistant` |
| ELF 路径 | /opt/kaiming/layers/stable/x86_64/app/cn.kylin.kylin-aiassistant/binary/3.0.67/files/bin/kylin-aiassistant | `ls -l <path>` |
| Runtime Socket | /tmp/.kylin-ai-runtime-unix/\<uid\>/assistant.sock | `ls -l /tmp/.kylin-ai-runtime-unix/*/assistant.sock` |
| 聊天数据库 | ~/.config/kylin-aiassistant/kylin_aiassistant_database.db | `ls -l ~/.config/kylin-aiassistant/kylin_aiassistant_database.db` |
| 当前 Commit | 同步到 D2 分支 HEAD | `cd ~/kylinOS-agent-memory && git rev-parse HEAD` |
| 虚拟机快照 | 已回滚到 D2 基线快照 | VirtualBox 管理器 |

### 1.2 脚本部署

将以下脚本复制到麒麟虚拟机 `~/d2c-probe/` 目录：

- `d2c_postturn_isend_counter.sh` — H2C-PostTurn 实验
- `d2c_prechat_context_probe.sh` — H2C-PreChat 实验
- `d2c_tool_event_observer.sh` — H2C-Tool 实验
- `d2c_evidence_collector.sh` — 证据打包脚本

赋权：

```bash
chmod +x ~/d2c-probe/*.sh
```

### 1.3 KYSEC 注意事项（01 §8.2、02 §16.15）

- 仅对测试/观察脚本配置 KYSEC 单文件 `verified`，**禁止全局关闭 KYSEC**。
- 命令示例（按实际路径替换）：

```bash
# 查看当前 KYSEC 状态
sudo getstatus

# 对单文件设置执行许可（如需）
sudo setstatus -p /home/<user>/d2c-probe/d2c_postturn_isend_counter.sh verified
```

---

## 2. 实验 A：H2C-PostTurn — 最终回合 is_end 唯一性验证

### 2.1 目标

验证普通聊天流式回答中，**唯一 is_end=true** 触发一次 TurnFinalizedEvent，且不重复、不遗漏。

### 2.2 关联能力矩阵

- AGT-002 普通聊天流式完成（HOST_VERIFIED / E4，H2B 已验证 is_end=true×1）
- 本实验将 AGT-002 的结论从"已观察"升级为"Hook 点可注入"。

### 2.3 执行步骤

**步骤 A1：** 启动日志捕获（后台运行）

```bash
~/d2c-probe/d2c_postturn_isend_counter.sh start
```

脚本将：
- 启动 `strace` 跟踪 kylin-aiassistant + kylin-ai-runtime 进程的 `write`/`writev`/`sendmsg`/`sendto`/`recvmsg`/`read`/`poll` 系统调用 (LD_PRELOAD 因 KYSEC/签名限制未采用)
- 离线过滤包含 `is_end`、`ChatResult`、`assistant.sock` 关键词的日志行
- 输出到 `~/d2c-probe/out/postturn_<timestamp>.log`

**步骤 A2：** 打开 AI 助手，发起一次普通文本问答

- 用户输入：`你好，请用一句话介绍麒麟操作系统。`
- 等待流式回答完成（UI 显示完整回答）。

**步骤 A3：** 停止捕获并生成计数报告

```bash
~/d2c-probe/d2c_postturn_isend_counter.sh stop
```

脚本输出 `~/d2c-probe/out/postturn_<timestamp>.summary.json`，包含：
- `chatCallback_count` — chatCallback 关键词出现次数
- `is_end_false_count` — is_end=false 次数
- `is_end_true_count` — is_end=true 次数（**期望：1**）
- `updateBubble_count` — updateBubble 次数
- `duration_ms` — 从首个 chatCallback 到 is_end=true 的耗时

**步骤 A4：** 数据库落库验证

```bash
~/d2c-probe/d2c_postturn_isend_counter.sh dbcheck
```

脚本将：
- 查询 `~/.config/kylin-aiassistant/kylin_aiassistant_database.db` 的 RECORD 表
- 记录实验前后的 `rowid` 范围
- 输出 `~/d2c-probe/out/postturn_<timestamp>.db_snapshots.json`

### 2.4 通过标准

| 编号 | 验证项 | 通过标准 |
| --- | --- | --- |
| H2C-PostTurn-1 | is_end=true 唯一 | `is_end_true_count == 1` |
| H2C-PostTurn-2 | is_end=false 多次 | `is_end_false_count >= 1` |
| H2C-PostTurn-3 | RECORD 行新增 | `rowid_end - rowid_start == 2`（用户+助手各一条） |
| H2C-PostTurn-4 | 无延迟落库 | is_end=true 后 15 秒内 rowid 不再变化 |
| H2C-PostTurn-5 | 完整回答可取得 | UI 显示文本与 RECORD.message 一致 |

### 2.5 失败路由

- `is_end_true_count > 1`：可能存在重复回调，记录为 Bug，返回 D1 重新核对 Hook 点 B。
- `is_end_true_count == 0`：可能未完成流式回答或日志捕获失败，检查 strace 权限与 KYSEC。
- `rowid` 未变化：可能存在延迟落库或会话切换，延长观察窗口至 30 秒。

---

## 3. 实验 B：H2C-PreChat — Memory Context 注入三路隔离

### 3.1 目标

验证 Memory Context 注入后，**UI 显示文本、聊天数据库 message、模型请求**三路隔离，内部记忆上下文不污染用户可见历史。

### 3.2 关联能力矩阵

- AGT-005 Memory Context 注入（UNTESTED / E0·E2）
- 本实验将 AGT-005 从 UNTESTED 升级为 HOST_VERIFIED 或明确失败原因。

### 3.3 执行步骤

**步骤 B1：** 记录实验前基线

```bash
~/d2c-probe/d2c_prechat_context_probe.sh baseline
```

脚本将：
- 记录当前 RECORD 表 `rowid` 最大值
- 记录当前 AI 助手进程 PID
- 输出 `~/d2c-probe/out/prechat_<timestamp>.baseline.json`

**步骤 B2：** 启动模型请求捕获

```bash
~/d2c-probe/d2c_prechat_context_probe.sh capture-start
```

脚本将使用 `strace` + 关键词过滤捕获系统调用文本 (非协议解码后的真实 chatAsync 入参 JSON), 按 marker/memory_context/prompt/context 等关键词过滤后保存到 `~/d2c-probe/out/prechat_<timestamp>.model_request.jsonl`。

> **注意：** 实际使用 `strace -e write` + 关键词过滤捕获 socket 写入内容（LD_PRELOAD 因 KYSEC/签名限制未采用）。该文件是关键词过滤后的系统调用文本, 不是经过协议解码后确认的模型请求 JSON; 关键词未命中只能说明当前 strace 观察方式未发现这些明文字段, 不能直接证明 Hook 点 A 未实现。需源码 instrument、D-Bus 解码或真实 chatAsync 入参捕获确认。

**步骤 B3：** 发起带标记的用户输入

- 用户输入：`[D2C-MARKER-PRECHAT-001] 帮我回忆上次讨论的麒麟记忆系统架构。`
- 标记字符串 `[D2C-MARKER-PRECHAT-001]` 用于后续在三路证据中检索。

**步骤 B4：** 等待回答完成，停止捕获

```bash
~/d2c-probe/d2c_prechat_context_probe.sh capture-stop
```

**步骤 B5：** 三路证据采集

```bash
~/d2c-probe/d2c_prechat_context_probe.sh collect
```

脚本将采集：

1. **UI 路径：** 截图 `~/d2c-probe/out/prechat_<timestamp>.ui_screenshot.png`（人工截图或 `kylin-screenshot`）
2. **聊天库路径：** 查询 RECORD 表中包含 `[D2C-MARKER-PRECHAT-001]` 的行，导出 `message` 字段到 `~/d2c-probe/out/prechat_<timestamp>.db_message.txt`
3. **模型请求路径：** 从 `model_request.jsonl` 中提取包含 `[D2C-MARKER-PRECHAT-001]` 的请求体

### 3.4 通过标准

| 编号 | 验证项 | 通过标准 |
| --- | --- | --- |
| H2C-PreChat-1 | UI 显示原始用户文本 | UI 截图中用户气泡仅含 `[D2C-MARKER-PRECHAT-001] 帮我回忆...`，无 Memory Context |
| H2C-PreChat-2 | 数据库 message 不含 Memory Context | RECORD.message 与用户输入一致，无额外记忆前缀 |
| H2C-PreChat-3 | 模型请求含 Memory Context（注入后） | model_request.jsonl 中请求体含记忆上下文字段 |
| H2C-PreChat-4 | MemoryClient 超时降级 | 断开 UDS 后聊天继续，model_request 不含记忆上下文但请求成功 |

### 3.5 失败路由

- UI 含记忆上下文：违反原文隔离红线（02 §4.1），记录为 Blocker，返回 D1 重新设计 Hook 点 A。
- 数据库 message 含记忆上下文：同上 Blocker。
- 模型请求不含记忆上下文：Hook 点 A 未生效或 MemoryClient 未连接，检查 IPC-001（UDS Echo）。
- 无法拦截 chatAsync 入参：改用源码分支 instrument 或 DBus 监听，记录为 TD。

---

## 4. 实验 C：H2C-Tool — 真实 Tool 成功/失败/取消事件

### 4.1 目标

捕获真实 Tool 的成功、失败、取消三类事件，形成结构化 ToolExecutionEvent，并验证 Prompt Skill（翻译/润色/总结）不被误判为 Tool。

### 4.2 关联能力矩阵

- AGT-004 真实 Tool Result（PARTIAL / E2·E4）
- 本实验将 AGT-004 从 PARTIAL 升级为 HOST_VERIFIED，关闭 TD-007。

### 4.3 执行步骤

**步骤 C1：** 启动 Tool 事件观察

```bash
~/d2c-probe/d2c_tool_event_observer.sh start
```

脚本将：
- 跟踪 kylin-aiassistant 进程的 `sendToolMessage`、`tool_call`、`tool_result` 相关日志
- 输出到 `~/d2c-probe/out/tool_<timestamp>.log`

**步骤 C2：** 执行成功 Tool 场景

在 AI 助手中触发一个真实 Tool（如打开应用、查询天气、系统设置），等待 Tool 执行完成。

**步骤 C3：** 执行失败 Tool 场景

触发一个会失败的 Tool（如打开不存在的应用、查询无网络天气）。

**步骤 C4：** 执行取消 Tool 场景

触发一个 Tool，在执行过程中点击"停止"按钮。

**步骤 C5：** 执行 Prompt Skill 对照组

触发翻译/润色/总结功能，观察是否被误判为 tool_call。

**步骤 C6：** 停止观察并生成报告

```bash
~/d2c-probe/d2c_tool_event_observer.sh stop
```

脚本输出 `~/d2c-probe/out/tool_<timestamp>.summary.json`，包含：
- `success_events` — 成功 Tool 事件列表（tool_name、started_at、finished_at、result）
- `failure_events` — 失败 Tool 事件列表（tool_name、error）
- `cancelled_events` — 取消 Tool 事件列表（tool_name、cancelled_at）
- `prompt_skill_events` — Prompt Skill 事件列表（用于验证不被误判）

### 4.4 通过标准

| 编号 | 验证项 | 通过标准 |
| --- | --- | --- |
| H2C-Tool-1 | 真实 Tool 成功事件 | `success_events` 非空，含 tool_name、result |
| H2C-Tool-2 | 真实 Tool 失败事件 | `failure_events` 非空，含 error 字段 |
| H2C-Tool-3 | Tool 取消事件 | `cancelled_events` 非空 |
| H2C-Tool-4 | Prompt Skill 不被误判 | `prompt_skill_events` 中不生成 tool_call 证据 |
| H2C-Tool-5 | 失败 Tool 不形成成功知识 | 检查知识候选，仅 FailureMemory |

### 4.5 失败路由

- 无法捕获任何 Tool 事件：sendToolMessage 路径未确认，记录为 TD-007（High，OPEN），需源码分支 instrument。
- Prompt Skill 被误判为 tool_call：违反 02 §10.3 边界红线，记录为 Bug。
- 失败 Tool 形成成功知识：违反 02 表22 示例，记录为 Blocker。

---

## 5. 证据收集与打包

### 5.1 证据包结构

执行完三项实验后，运行：

```bash
~/d2c-probe/d2c_evidence_collector.sh pack
```

生成 `~/d2c-probe/out/d2c_evidence_<timestamp>.tar.gz`，包含：

```
d2c_evidence_<timestamp>/
├── README.md                          # 证据包说明
├── environment.json                   # 环境信息（OS、宿主版本、Commit SHA）
├── postturn/
│   ├── postturn_<ts>.log              # 原始日志
│   ├── postturn_<ts>.summary.json     # 计数报告
│   └── postturn_<ts>.db_snapshots.json # 数据库快照
├── prechat/
│   ├── prechat_<ts>.baseline.json     # 基线
│   ├── prechat_<ts>.ui_screenshot.png  # UI 截图
│   ├── prechat_<ts>.db_message.txt     # 数据库 message
│   └── prechat_<ts>.model_request.jsonl # 模型请求
├── tool/
│   ├── tool_<ts>.log                  # 原始日志
│   └── tool_<ts>.summary.json         # 事件报告
└── checksums.sha256                   # 所有文件 SHA-256
```

### 5.2 证据包必填字段（evidence/README.md）

每个证据包至少记录：

- `task_id` — D2-C-OSAGENT-SPIKE
- `commit` — 实际执行的 Commit SHA
- `os` — 银河麒麟 V11 x86_64
- `virtualization` — 由 d2c_evidence_collector.sh 的 detect_virt() 自检测 (systemd-detect-virt / dmidecode / dmesg), 禁止硬编码
- `command` — 执行的验证命令
- `result` — 命令输出摘要或截图链接
- `reviewer` — D（周子腾）；E 补审（谢嘉然）
- `limitations` — 已知限制（如 LD_PRELOAD 失败、KYSEC 限制）
- `checksum` — 文件 SHA-256

### 5.3 脱敏要求

- 仓库只放脱敏、小体积证据（文本日志、JSON 输出）。
- 大日志、视频、虚拟机快照放外部受控存储，在 evidence/index.yaml 中保留链接与 SHA-256。
- 不得包含 API Key、用户聊天敏感原文。

---

## 6. D2-C 完成定义

**当前状态：** BLOCKED。以下是 2026-08-01 旧提交上的历史观察记录，不改变本手册开头
的审计结论，也不能替代当前 Commit 的麒麟 VM 重跑。

**实验执行结果汇总（2026-08-01）：**

| 实验 | 状态 | 关键结论 |
|---|---|---|
| A: H2C-PostTurn | PASS_CANDIDATE | is_end=true 唯一 (precise模式计数=1, sendmsg 到 assistant.sock); 待补数据库前后快照和15秒稳定性验证 |

> **PostTurn is_end 3x 重复说明 (Reviewer D Issue #2):**
>
> 非 precise 模式 (fallback/宽松匹配) 下, strace `-f` 会同时跟踪多个线程/进程, 导致同一次 is_end 事件被捕获 3 份副本:
> 1. `write(1</dev/null>)` — stdout (丢弃)
> 2. `write(4<.../kylin-ai-runtime.log>)` — 本地日志文件 (副本)
> 3. `sendmsg(N<...assistant.sock>)` — DBus 业务回调 (真正的事件)
>
> **去重策略:**
> - **precise 模式** (首选): 仅统计 `sendmsg + assistant.sock + is_end` 的行, 天然去重, 得到真实事件数 (is_end_true=1)
> - **fallback 模式**: 保留原始计数 (raw_count), **不再自动除以 3** (Reviewer E 阻断项六已修复); summary.json 同时输出 `raw_is_end_*_count` 和 `is_end_*_count` 供 Reviewer 核对
> - 多轮实验中, 前期非 precise 模式观察到 is_end_true=3 属于已知的 3x 重复现象, 非业务错误
| B: H2C-PreChat | PARTIAL_FAIL_CANDIDATE | H2C-PreChat-2 通过 (DB 无污染); H2C-PreChat-3 memory_context 未观察到 (AGT-005=NOT_OBSERVED) |
| C: H2C-Tool | ARCHITECTURE_FINDING_UNVERIFIED | 发现 stop_chat/intentionrecognition 线索; OpenAI风格关键词=0; 成功/失败/取消Tool结构化事件未捕获 |

**三大架构发现：**

1. **AF-1**: Hook 点 A (Pre-Chat Memory Context 注入) strace 未观察到 memory_context 字段 — AGT-005 状态为 NOT_OBSERVED (需源码 instrument 确认, 不得直接判定 NOT_IMPLEMENTED)
2. **AF-2**: 麒麟 AI 助手不使用 OpenAI 风格 tool_call/function_call — Tool 动作由 kylin-ai-runtime 内部 intentionrecognition.cpp 直接执行 (AGT-004=PARTIAL, TD-007=OPEN)
3. **AF-3**: 真实 IPC 通道为 /tmp/.kylin-ai-runtime-unix/1000/assistant.sock (DBus), 方法 chat/stop_chat, 信号 ChatResult

**升级为 COMPLETED 需要：**

1. ⚠️ 人在麒麟虚拟机以当前被测 Commit 重跑三项实验（A/B/C）。— 历史运行仅基于 `20adffc`，不满足当前证据绑定要求
2. ⚠️ 收集完整证据包（日志、截图、数据库快照、JSON 报告）。— 当前缺少 PostTurn 快照/稳定性/UI 一致性、PreChat UI 与已解码请求、Tool 三类结构化事件
3. ⚠️ 所有通过标准满足，或失败项已分类为 Bug/Blocker/Risk/TD。— Gate 0 仍需 D 的正式决策；AGT-005/AGT-004 不得以关键词观察替代验证
4. ⚠️ 将脱敏后的完整证据上传到 `evidence/l2-kylin-vm/d2c/`，将大体积原始材料迁至受控存储并记录链接与 SHA-256
5. ⚠️ 更新 `evidence/index.yaml`。— 当前条目应保持 `BLOCKED`，仅在完整证据和复核后按准入流程升级
6. ✅ 更新 01 文档能力矩阵 AGT-004（Tool）、AGT-005（Context）状态。— AGT-005 NOT_OBSERVED, AGT-004=PARTIAL
7. ✅ 关闭或更新 TD-007（Tool Hook）。— 路径已确认为 intentionrecognition.cpp, TD-007 保持 OPEN, 需源码 instrument
8. ⚠️ D Reviewer 复核证据真实性。— 待 D 复核

---

## 7. 关联文档

- [D1 OS Agent 调用链与 Hook Spike 任务卡](./D1_OS_Agent_调用链与Hook_Spike_任务卡.md)
- 01 能力边界文档 (外部参考, 不在仓库中): `01_麒麟OS_Agent_官方SDK与现有系统能力边界及验证矩阵_v1.0_20260726.docx`
- 02 总体架构/SOP (外部参考, 不在仓库中): `02_麒麟OS_Agent记忆系统_总体架构_团队分工与标准开发SOP_v1.0_20260726.docx`
- 03 环境配置手册 (外部参考, 不在仓库中): `03_麒麟OS_Agent记忆系统_开发与Runtime环境快速配置手册_v1.0_20260726.docx`
- 04 Agent/LLM 指南 (外部参考, 不在仓库中): `04_麒麟OS_Agent记忆系统_Agent_LLM与CodeAgent使用指南_v1.0_20260726.docx`
- 仓库内基线文档: [docs/baseline/01_sdk_model_abi_baseline.md](../baseline/01_sdk_model_abi_baseline.md), [docs/baseline/03_defensive_checklist.md](../baseline/03_defensive_checklist.md)
- 仓库内技术债登记: [docs/technical-debt/TECHNICAL_DEBT_REGISTER.md](../technical-debt/TECHNICAL_DEBT_REGISTER.md)
