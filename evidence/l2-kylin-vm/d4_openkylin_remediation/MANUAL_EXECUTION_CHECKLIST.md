# 人工执行项操作清单（阶段 4-5 遗留）

> **关联**: `deliverables/OPENKYLIN_BLOCKER_REMEDIATION_PLAN.md` 阶段 4-5
> **生成日期**: 2026-08-15
> **背景**: 真实 Tool Result Hook 端到端验证在纯 SSH 环境下无法完成，以下操作需人工在麒麟 VM 内执行。

所有阻塞项均需在麒麟 VM 内人工完成，SSH 自动化无法覆盖。

---

## A. 解除 S4-BLOCK-003：构建环境（需 sudo 权限）

**前置**：需要 `kylin-agent` 获得 sudo 权限，或由管理员执行

```bash
# 1. 安装 kylin-aiassistant 完整构建依赖（来自 debian/control Build-Depends）
sudo apt-get build-dep -y kylin-aiassistant
# 或手动补关键包（若 build-dep 源不可用）：
sudo apt-get install -y libgsettings-qt-dev libpeony-dev libkysdk-qtwidgets-dev \
  libkysdk-kabase-dev libkysdk-log-dev libkysdk-config-dev libkysdk-ukenv-dev \
  libkysdk-waylandhelper-dev libkysdk-alm-dev libukui-log4qt-dev \
  libkysdk-datacollect-dev libkysdk-sysinfo-dev libukui-file-metadata-dev \
  libkyai-config-dev libkysdk-coreai-speech-dev libkyai-assistant-dev \
  libkysdk-ai-common-dev libkysdk-genai-nlp-dev librsvg2-dev libkf5wayland-dev

# 2. 验证依赖齐全
pkg-config --exists gsettings-qt && echo OK

# 3. 重新编译（patch 已就位）
cd ~/openkylin-build/kylin-aiassistant/kylin-aiassistant
qmake kylin-aiassistant.pro && make -j$(nproc)

# 4. 验证产物
file kylin-aiassistant && readelf -n kylin-aiassistant | grep -i 'Build ID'
```

**验证点**：qmake 不再报 `gsettings-qt development package not found`，生成新的 73MB+ ELF 二进制。

---

## B. 解除 S4-BLOCK-001：部署 patched 二进制 + 触发真实 Tool（需桌面操作）

**前置**：A 完成（拿到打了 patch 的二进制）

### B1. 备份官方二进制（安全回退）

```bash
sudo cp /usr/bin/kylin-aiassistant /usr/bin/kylin-aiassistant.bak
sudo cp ~/openkylin-build/kylin-aiassistant/kylin-aiassistant/kylin-aiassistant /usr/bin/kylin-aiassistant
# 重启助手进程
pkill kylin-aiassistant; sleep 2
/opt/apps/kaiming/bin/cn.kylin.kylin-aiassistant cn.kylin.kylin-aiassistant 0 /usr/bin/kylin-aiassistant --silence &
```

### B2. 触发 Tool（需物理/虚拟显示器上操作麒灵 AI 助手 GUI）

| 步骤 | 操作 | 触发位置 |
|------|------|---------|
| 1 | 打开"麒灵 AI 助手"窗口 | 桌面托盘/应用菜单 |
| 2 | 输入"帮我画一只猫"并发送 | 图片生成 Tool（msgpane.cpp:3275） |
| 3 | 断网后再次触发图片生成 | 失败 Tool 场景 |
| 4 | 生成中点击"停止" | 取消场景 |
| 5 | 输入"把这段话翻译成英文" | Prompt Skill（不误判验证） |

### B3. 观察日志验证

```bash
tail -f /home/kylin-agent/.log/kylin-aiassistant.log | grep -E 'ToolInvocation|ToolExecutionEvent'
```

**预期日志**：
- `[ToolInvocation]` 含 `tool_id`/`file_type`/`started_at`（出站）
- `[ToolExecutionEvent]` 含 `status=success/failure`、`result/error`（回程）

---

## C. 5 场景测试矩阵执行（对应 T1-T5）

| 场景 | 手动操作 | 通过标准 |
|------|---------|---------|
| **T1 成功 Tool** | B2 步骤 2（图片生成） | 日志 `[ToolExecutionEvent] status=success, result 非空` |
| **T2 失败 Tool** | B2 步骤 3（断网触发） | 日志 `status=failure, error 非空` |
| **T3 取消 Tool** | B2 步骤 4（停止生成） | 观察是否产生 `cancelled`（预期当前宿主无此建模，需记录为缺口） |
| **T4 Prompt Skill 不误判** | B2 步骤 5（翻译） | **无** `tool_call`/`ToolExecutionEvent` 日志 |
| **T5 失败不形成成功知识** | 检查 T2 后知识候选 | 候选列表不含成功记忆 |

**记录要求**：每个场景截图/保存日志片段，记录时间戳，作为 L2 证据。

---

## D. 解除 S4-BLOCK-002：源码补字段（需后续工程链路）

**前置**：T1-T3 通过后，确认哪些字段仍需补齐

1. 在 `systemchat.h` 的 `toolReply` 信号签名中补充 `tool_call_id`、`arguments`、`started_at` 字段
2. 在 `SystemChat::sendToolMessage` 出站时记录 `started_at`/`arguments`，透传到回程信号
3. `stopChat()` 路径补 `cancelled` 状态建模
4. 重新编译 + 部署（走 KYSEC 授权 + 部署前快照 + 异常回退复验，参考 02 §4.5）

---

## E. 关闭技术债（需 D/E 主审确认）

| 项 | 触发条件 | 操作 |
|----|---------|------|
| **TD-007** | C 的 T1/T2/T3/T4/T5 全通过 | 状态 Open → Resolved |
| **R-ARCH-05** | TD-007 关闭 + 端到端跑通 | 状态 In Progress → Resolved |
| **S4-BLOCK-001/003** | A、B、C 完成 | 状态 BLOCKED → RESOLVED |

---

## 优先级建议

1. **A**（构建环境）是根本阻塞，先解决，否则 B/C 无法进行
2. **A → B → C** 是主链（真实 Tool Hook 验证）
3. **D** 依赖 C 的 T3 结果决定是否需要补 cancelled
4. **E** 全部通过后由 D/E 主审关闭
