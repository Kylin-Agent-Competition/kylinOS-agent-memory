# openkylin 阻塞项修复 — 阶段 4-5 完成报告

> **计划**: `deliverables/OPENKYLIN_BLOCKER_REMEDIATION_PLAN.md`
> **执行日期**: 2026-08-15
> **执行环境**: 麒麟 VM (KylinOS V11 x86_64)，SSH 会话
> **执行人**: Agent 辅助（人工复核待 D/E 主审）

---

## 一、执行摘要

阶段 4（Tool Result Hook 验证）与阶段 5（证据收集与技术债关闭）已按计划推进。核心结论：

| 阶段 | 计划产出 | 实际结果 | 状态 |
|------|---------|---------|------|
| 4.1 定位 sendToolMessage | tool_hook_audit.md | 调用链完整审计（出站 sendToolMessage → 回程 toolReply → onRecvTool） | ✅ 完成 |
| 4.2 实现 ToolExecutionEvent 捕获 | tool_hook_patch.diff + 编译 | 最小观察点 patch 已实现 + 头文件语法通过；完整重编译阻塞 | ⚠️ 部分完成 |
| 4.3 5 场景测试 | tool_result_test_matrix.log | T4 源码级通过；T1/T2/T3/T5 阻塞 | ⚠️ 部分完成 |
| 5.1 证据收集 | MANIFEST.sha256 | 35 文件 SHA-256 已生成 | ✅ 完成 |
| 5.2 技术债更新 | R-ARCH-05 / TD-007 | R-ARCH-05 进展更新；TD-007 新增登记 | ✅ 完成 |
| 5.3 完成报告 | 本报告 | 已生成 | ✅ 完成 |

**关键结论**: 真实 Tool Result Hook 的端到端宿主验证**未能在纯 SSH 环境完成**——真实 Tool 触发是纯 GUI 驱动的（QML 按钮），Wayland 桌面无 xdotool 自动化、dbus 接口无消息注入能力。TD-007 与 R-ARCH-05 **未关闭**，仍为 Open / In Progress。

---

## 二、阶段 4 详细结果

### 4.1 Tool 调用链审计（完成）

完整调用链已定位（详见 `tool_hook_audit.md`）：

```
[出站] QML → CMsgPane::xxx → SystemChat::sendToolMessage(toolId, fileType, para)
        (systemchat.cpp:692) → m_osassistant->chatAsync(json)   // message_type=tool_call

[回程] kylin-ai-runtime → m_osassistant 流式回调 → 解析器 tool_call 分支
        (systemchat.cpp:88) → Q_EMIT toolReply(msg, toolMap, imageUrl, errorCode, model, feedbackURL)
        (systemchat.cpp:117-120)

[UI]   connect(toolReply → CMsgPane::onRecvTool) (msgpane.cpp:146)
        onRecvTool (msgpane.cpp:1243) → 成功/失败分支渲染
```

**Hook 点选择**: `CMsgPane::onRecvTool()`（成功/失败判定 + tool 名 + 结果文本的唯一汇聚点）。

### 4.2 最小观察点 patch（部分完成）

- 新增 `tool_execution_observer.h`（header-only，无外部依赖），提供 `toolStartJson()`（出站 started_at/arguments）与 `toolResultJson()`（回程 ToolExecutionEvent，符合 02 表31）。
- `systemchat.cpp::sendToolMessage` 注入 `[ToolInvocation]` 观察点。
- `msgpane.cpp::onRecvTool` 注入 `[ToolExecutionEvent]` 观察点。
- **头文件语法检查**: `g++ -fsyntax-only` → `EXIT=0` ✅
- **完整重编译**: ❌ 阻塞（S4-BLOCK-003），详见 §四。

### 4.3 5 场景测试（部分完成）

| 场景 | 结果 | 说明 |
|------|------|------|
| T1 成功 Tool | BLOCKED | GUI-only 触发 |
| T2 失败 Tool | BLOCKED | GUI-only 触发 |
| T3 取消 Tool | BLOCKED | GUI-only + cancelled 未建模 |
| T4 Prompt Skill 不误判 | ✅ 源码级 PASS | 文本 Skill 不进入 tool_call 分支 |
| T5 失败不形成成功知识 | BLOCKED | 依赖 T2 |

---

## 三、ToolExecutionEvent Schema 字段映射结论（02 表31）

| 字段 | 宿主源码可用性 |
|------|---------------|
| tool_name / result / error / status(success/failure) | ✅ 可从 toolReply 信号获得 |
| arguments / started_at | ⚠️ 仅出站 sendToolMessage 可见 |
| tool_call_id / source_trace_id / side_effect / user_confirmed | ❌ 宿主未暴露 |
| cancelled 状态 | ❌ 未显式建模（stopChat 不经过 toolReply） |
| rollback_status | ✅ 默认 "none" |

真实宿主集成阶段需补齐字段（S4-BLOCK-002）。

---

## 四、新增阻塞项（S4 系列）

| 编号 | 描述 | 状态 | 解除方案 |
|------|------|------|---------|
| S4-BLOCK-001 | 真实 Tool 触发为 GUI-only（Wayland 无 xdotool，dbus 无消息注入） | BLOCKED | 手动操作麒麟桌面触发 Tool；或补 X11+xdotool |
| S4-BLOCK-002 | toolReply 信号缺 arguments/tool_call_id/started_at/cancelled | OPEN | 集成阶段源码补字段 |
| S4-BLOCK-003 | VM 缺 ~40 个 -dev 包（qmake 报 gsettings-qt development package not found），无 sudo | BLOCKED | `sudo apt-get build-dep kylin-aiassistant` 或带 dev 依赖的构建机 |
| S4-BLOCK-004 | VM 无 git，无法 git diff | RESOLVED | 宿主机 difflib 生成 patch |

---

## 五、新增发现（N 系列）

| 编号 | 发现 | 说明 |
|------|------|------|
| N6 | 阶段 1 "主程序 73MB 编译成功" 与 build_make.log 不一致 | build_make.log 末尾显示主程序 qmake 失败（`gsettings-qt development package not found`，错误 3），无任何 g++/编译记录。73MB 二进制（BuildID=e62502，含 debug_info）存在但非本次 make 产物，来源待核实 |
| N7 | 当前 VM 为"运行时完备、构建环境缺失" | AI 子系统运行时（kylin-aiassistant/kylin-ai-runtime/kytensor）完整运行，但 pkg-config 检查显示 16 个依赖中仅 glib-2.0 可用，其余 -dev 包缺失 |
| N8 | Tool 触发无命令行/dbus 入口 | dbus `org.ukui.kylin_aiassistant` 仅 showOrHideView/showGlobalScribeFloatingBar 两视图方法 |

---

## 六、技术债状态更新

| 编号 | 原状态 | 现状态 | 说明 |
|------|--------|--------|------|
| R-ARCH-05 | In Progress | **In Progress（未关闭）** | Socket 重定向已通（3/3），但 ToolResultEvent 端到端未跑通 |
| TD-007 | （原未登记） | **Open** | 新增登记：真实 Tool Result Hook 宿主验证未完成 |

---

## 七、Gate 0 第 3 项重新评估

| 子项 | 原状态 | 修复后状态 |
|------|--------|-----------|
| 模拟客户端 | PASS | PASS（不变） |
| 真实 Hook | BLOCKED（源码已开源） | **PARTIAL（未 PASS）** — Socket 重定向已验证，但 Tool Result Hook 端到端因 GUI-only + 构建环境缺失未跑通 |

---

## 八、证据文件清单

| 文件 | 内容 | SHA-256 |
|------|------|---------|
| tool_hook_audit.md | 调用链审计报告 | 380b1c0c… |
| tool_hook_patch.diff | 最小观察点 patch（3 文件） | 947cfc0d… |
| tool_execution_observer.h | 观察点头文件 | 8b217bb8… |
| tool_hook_build.log | 重编译尝试日志（qmake 失败） | 6ad4088b… |
| tool_result_test_matrix.log | 5 场景测试矩阵 | 15163903… |
| MANIFEST.sha256 | 全部 35 文件校验 | （见文件） |

---

## 九、残余阻塞项汇总（全阶段）

| 编号 | 描述 | 状态 |
|------|------|------|
| S1-BLOCK-001 | peony-menu-plugin 编译失败（缺 libpeony-dev + libgsettings-qt-dev） | BLOCKED（关联 S4-BLOCK-003） |
| S4-BLOCK-001 | Tool 触发 GUI-only，无法自动化 | BLOCKED |
| S4-BLOCK-002 | toolReply 信号字段缺口 | OPEN |
| S4-BLOCK-003 | VM 构建环境缺 -dev 包 + 无 sudo | BLOCKED |
| S4-BLOCK-004 | VM 无 git | RESOLVED |

**建议下一步**（人工决策）:
1. 为 VM 申请 sudo/构建环境，执行 `apt-get build-dep kylin-aiassistant`，解除 S4-BLOCK-003 + S1-BLOCK-001。
2. 采用手动桌面操作（或物理显示器 + xdotool）验证 T1/T2/T3，解除 S4-BLOCK-001。
3. 集成阶段补齐 toolReply 信号字段（tool_call_id/arguments/started_at/cancelled），解除 S4-BLOCK-002。
4. 上述三项全部通过后，关闭 TD-007 与 R-ARCH-05。
