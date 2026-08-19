# 人工验证文档：麒灵 AI 助手 5.0.3 智能体模式与工具调用能力

- **验证日期**：2026-08-16
- **验证人**：周子腾（D）
- **关联文档**：`docs/baseline/v2-20260816/02_kylin_vm_environment_baseline_20260816.md`（环境基线 v2）、`docs/baseline/v2-20260816/05_capability_boundary_reevaluation_20260816.md`（能力边界重评 v1.2）、`D4_GATE0_FORMAL_DECISION_20260807.md`（原 Gate 0 结论）
- **证据等级**：L2/L3（麒麟 VM 宿主验证）

---

## 一、背景与动机

原测试环境基线中麒灵 AI 助手版本为 **3.0.67**，经能力边界调查确认**不具备调用工具（Tool）、技能（Skill）、Harness 的能力**，导致：

- Gate 0 项 3「真实 Tool Result」（AGT-004）长期处于 BLOCKED，只能依赖替代架构路线 B（独立 Qt 演示壳 + 执行日志 Adapter，ADR-004）；
- 「官方是否具备可复用的智能体/工具调用能力」边界不清，影响自研 Memory Service 范围判断。

根据实际情况，**更新环境基线至麒灵 AI 助手 5.0.3**（详见 `docs/baseline/v2-20260816/02_*`，应用路径迁移至 `/opt/kaiming/layers/`）。5.0.3 具备**智能体模式（Agent Mode）**，能够调用工具、Skill、Harness。本次验证在麒麟 VM 上完成，确认该能力可用。

---

## 二、验证环境

| 项目 | 值 |
|------|-----|
| 麒麟 VM | `Kylin-desktop-neo`（VirtualBox，8GB RAM / 8 CPU） |
| 操作系统 | 银河麒麟桌面 V11 2603 x86_64 |
| 麒灵 AI 助手 | `cn.kylin.kylin-aiassistant` **5.0.3** |
| 助手主二进制 | `/opt/kaiming/layers/stable/x86_64/app/<id>/binary/5.0.3/files/bin/kylin-aiassistant` |
| Build ID | `9acaa2de9d94a3d99a2fb510068a31910d47d492` |
| SHA-256 | `6a13dd3aee2f30a963a49f701031df88c03a930d0a9db416b59ee11199874ebd` |
| 模型接入 | 自选模型，接入 **deepseek 官方云端模型**（deepseek-chat / deepseek-reasoner） |

> 模型接入方式：多厂商引擎插件 `deepseek`（ai-engine-plugin 1.1.0.1-0k0.5，nlp 1.2.0.2-0k1.0），配置目录 `/etc/kylin-ai/engines/ai-engines/deepseek/`。

---

## 三、验证清单与结果

> 标记说明：✅ 通过 ｜ ⬜ 未执行/待补充证据 ｜ ❌ 失败
> ⚠️ 下列「✅」结论来自人工在麒麟 VM 上的实际验证；**证据文件（日志/截图/命令输出）待补充到 `evidence/l2-kylin-vm/` 并登记 `evidence/index.yaml`**。

### V1 智能体模式可用性

| 检查项 | 操作 | 预期 | 结果 |
|--------|------|------|:----:|
| V1-1 智能体模式入口 | 在 5.0.3 助手界面确认智能体/Agent 模式入口 | 存在智能体模式选项 | ✅ |
| V1-2 模式切换 | 切换至智能体模式 | 切换成功，无崩溃 | ✅ |

### V2 模型自选与 deepseek 云端接入

| 检查项 | 操作 | 预期 | 结果 |
|--------|------|------|:----:|
| V2-1 自选模型 | 在模型设置中选择模型 | 可选 deepseek 官方云端模型 | ✅ |
| V2-2 云端模型连通 | 发起一轮普通对话 | 模型正常回复（云端调用成功） | ✅ |
| V2-3 模型配置持久化 | 重启助手后复查模型配置 | 配置保持 | ✅ |

### V3 工具调用（成功场景）

| 检查项 | 操作 | 预期 | 结果 |
|--------|------|------|:----:|
| V3-1 工具触发 | 在智能体模式下发起需要工具/外部能力的请求 | 助手发起 tool_call | ✅ |
| V3-2 工具结果回填 | 工具执行成功后，结果进入模型上下文并生成回复 | 回复引用工具结果 | ✅ |
| V3-3 工具调用日志 | 检查助手日志 | 存在工具调用/执行记录 | ✅ |

### V4 Skill / Harness 调用

| 检查项 | 操作 | 预期 | 结果 |
|--------|------|------|:----:|
| V4-1 Skill 调用 | 触发预置 Skill（如文档问答/润色/摘要类） | Skill 被正确路由执行 | ⬜ 无法验证 |
| V4-2 Harness 能力 | 验证智能体 Harness（工具编排/多步执行） | 多步任务可编排执行 | ⬜ 无法验证 |

> ⚠️ **V4 状态说明**：人工收集日志中**未发现 Skill 调用相关日志**，无法从日志观测 Skill/Harness 执行路径，因此 V4 暂时无法运行验证。已登记为待补项（见 §五 EV-4）。不将「未验证」表述为「已验证」。

### V5 失败与取消场景（取消已补测）

| 检查项 | 操作 | 预期 | 结果 |
|--------|------|------|:----:|
| V5-1 工具失败 | 断网/无效参数触发工具失败 | 失败状态建模，不产生成功结果 | ⚠️ 部分证据（失败已观测：`ls -la /root` → `权限不够`，无成功结果；失败状态建模端到端待 Hook 集成） |
| V5-2 工具取消 | 执行中点击停止 | cancelled 状态可观测 | ✅ 已验证（`v5_task_cancel_log.txt`：`User stop task mode!`） |
| V5-3 失败不沉淀知识 | 检查失败后是否形成知识候选 | 不形成成功记忆 | ⚠️ 部分证据（失败场景+无沉淀观测，端到端待 Hook 集成） |

---

## 四、验证结论

1. **麒灵 AI 助手 5.0.3 具备可用的智能体模式**，能够调用工具（V1、V3 已验证，工具调用成功闭环：shell tool_call → tool_result 音量查询 → 助手回复）。
2. **deepseek 官方云端模型接入成功**（V2 自选模型验证通过，日志显示正常对话回复）。
3. **取消场景已验证**（V5-2：`User stop task mode!`）；**失败场景已观测**（V5-1/V5-3 补测：`ls -la /root` → `权限不够`，助手如实报告失败、无成功结果；宿主日志无沉淀记录），但端到端「失败状态建模 / 失败不沉淀」仍需 Hook/Memory Service 集成后验证（详见 `evidence/l2-kylin-vm/d4_agent_mode_5_0_3_20260816/v5_3_fail_no_precipitate_evidence.md`）。
4. **V4 Skill/Harness 调用暂无法验证**：日志中无 Skill 调用记录，不将未验证项表述为已支持。
5. **对 Gate 0 的影响**：AGT-004「真实 Tool Result」此前因 3.0.67 无工具能力而 BLOCKED；5.0.3 智能体模式 + 工具调用能力已在宿主验证，**真实 Tool Result 路径的宿主基础已具备**，可进入重新评估（详见《Gate 0 补充审查文档》）。
6. **证据状态**：V1/V2/V3/V5-2/V5-3 证据已落库 `evidence/l2-kylin-vm/d4_agent_mode_5_0_3_20260816/`（含 MANIFEST.sha256），并已登记 `evidence/index.yaml`（AGT-004-5.0.3-001）。

---

## 五、待补充证据清单

| 编号 | 证据内容 | 状态 |
|------|---------|------|
| EV-1 | 智能体模式入口截图（`v1_agentmode_entry.png`） | ✅ 已落库 |
| EV-2 | deepseek 云端模型对话回复日志（`v2_deepseek_chat_log.txt`） | ✅ 已落库 |
| EV-3 | 工具调用（tool_call 出站 + 结果回填）日志片段（`v3_tool_call_result_log.txt`） | ✅ 已落库 |
| EV-4 | Skill/Harness 调用日志片段 | ⬜ 无法收集（日志无 Skill 调用记录） |
| EV-5 | V5-2 取消场景日志（`v5_task_cancel_log.txt`） | ✅ 已落库 |
| EV-6 | V5-3 失败场景日志 + 无沉淀证据（`v5_fail_tool_log.txt` + `v5_3_fail_no_precipitate_evidence.md`） | ⚠️ 已落库（部分证据，端到端待 Hook 集成） |
| EV-7 | V5-1 工具失败场景日志（`v5-1_tool_call_failed_log.txt`：补查工作区未找到 root 文件夹，失败已观测） | ⚠️ 已落库（部分证据，状态建模端到端待 Hook 集成） |

---

## 六、签署

| 角色 | 姓名 | 日期 | 结论 |
|------|------|------|------|
| 验证人 | 周子腾（D） | 2026-08-16 | 待证据落库后确认 |
| Reviewer 1 | 待填写 | | |
| Reviewer 2 | 待填写 | | |
