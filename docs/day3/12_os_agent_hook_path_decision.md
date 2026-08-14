# 12 轨道 C — OS Agent Hook 路径决策

> **决策：`PRIMARY_PATH_SELECTED / NO_APPROVED_BACKUP / BLOCKED_FOR_PRODUCTION`**
> D3-C 已选择唯一主路径语义，但当前没有书面批准的备用路径。主路径或其宿主证据不满足时，
> 必须停止并保留阻断，不能自行切换为日志抓取、二进制注入或 Prompt 伪事件。

- 日期：2026-08-14
- 任务：D3-C「路径选择与共享契约冻结」
- 基线：`origin/main@d37fb95eca9083eb480491cda2464ebe8515477d`
- 公共契约：`docs/day3/11_os_agent_event_contract_v1.md`
- 启动门禁：`docs/day3/10_os_agent_contract_start_gate.md`
- 范围：只作路径决策和证据门禁，不实现生产 Hook

## 1. 决策摘要

| 层级 | 决策 | 当前状态 |
|---|---|---|
| 主路径 | 在当前受支持的官方 AI 助手源码中，以最小 source-level patch 接入 Pre-Chat、Post-Turn 和真实 Tool Result 三个语义 seam | `PRIMARY / FROZEN_CANDIDATE` |
| 通用备用候选 | 独立 Qt 演示壳，复用同一 C++/JSON 契约，并明确标注“非官方应用集成” | `ELIGIBLE_CANDIDATE / PENDING_D_E_APPROVAL` |
| Tool 专用备用候选 | 受控的结构化执行日志/数据库 Adapter，保留来源、状态、副作用、回滚和追踪；明确标注“非原生独立事件” | `ELIGIBLE_CANDIDATE / PENDING_D_E_APPROVAL` |
| 当前已批准备用 | 无 | `NOT_FOUND` |
| 无批准时的处置 | 停止生产接入；仅保留候选契约、测试和待验证清单 | `MANDATORY_STOP` |

“SOP 允许使用**批准的**独立 Qt 演示壳或执行 Adapter”是资格条件，不等于本批次已经取得批准。
在仓库已合并材料中未找到 D/E 对具体备用实现、证据要求和安全边界的书面接受，因此本文不得把
任何备用标成 `APPROVED`。

## 2. 唯一主路径

主路径是官方 AI 助手当前受支持源码的最小修改，不是固定旧提交、固定行号或 ABI 猜测。定位必须
以当前宿主版本的类/函数语义和实际调用链为准，并在修改前重新静态核对。

### 2.1 Pre-Chat — `MemoryQuery` / `MemoryContext`

语义位置：原始用户消息已确定，最终 `model_request` 尚未交给真实模型请求入口之前。

必须满足：

1. `display_user_text` 与 `model_request` 分离；
2. `MemoryQuery` 从受信宿主字段构造；
3. 只有 `model_request` 可被 Memory Context 增强；
4. UI 与聊天数据库继续保存原始用户文本；
5. 超时、不可用或校验失败时返回空/跳过 Context，聊天继续；
6. 不在 QML/UI 线程执行检索、向量化或冲突计算。

D1 曾把 `SystemChat::sendMessageImpl` 内最终 `chatAsync` 前作为候选位置；PR #19 的合并证据又观察到
真实智能体请求经过 `~/.kylinbot/gateway.sock`。该差异意味着**语义 seam 已选，精确源代码点未证实**。
D2-C 未观察到真实请求前注入，当前保持 `BLOCKED / NOT_OBSERVED / TD-008`，不能写成
`NOT_IMPLEMENTED`，也不能写成 PASS。

### 2.2 Post-Turn — `TurnFinalizedEvent`

语义位置：唯一最终响应已经完整组装，`is_end=true` 已确认，内部缓冲区清空之前。

必须满足：

1. 一个逻辑 Turn 最多发布一个最终事件；
2. 完整回答仍可通过受控来源引用取得；
3. Stop、Retry、续轮和取消不被误记为普通成功完成；
4. 发布快速返回，后续提取和持久化异步执行；
5. `event_id` 与 `idempotency_key` 保持不同语义；
6. 不把聊天正文复制到普通日志。

D1 的普通聊天链和历史唯一结束帧证据支持该语义位置；PR #19 合并了诊断性 `is_end=true` 观察，
但正式 D2-C 索引仍为 `BLOCKED/E2`，Stop/Retry 与完整 Gate 未闭合。因此该 seam 为
`PRIMARY / PARTIAL / FROZEN_CANDIDATE`，不是 `HOST_VERIFIED`。

### 2.3 Tool Result — `ToolExecutionEvent`

语义位置：真实 Tool 执行器已经产生结构化结果，且结果尚未被丢失、文本化或与模型自述混合的位置。

必须满足：

1. 捕获 success、failure、cancelled，候选解析同时安全处理 timeout/partial；
2. 保存 `tool_call_id`、状态、时间、脱敏参数/结果引用、副作用、回滚和来源追踪；
3. `success` 必须有真实 `result_ref`；
4. 非 success 不得形成成功知识；
5. Prompt Skill、模型自述或 UI 文本不得作为 Tool 事实；
6. 实际接入点必须由当前源码 instrument 和宿主事件证据共同确认。

D1 的旧候选 `sendToolMessage` 不能直接冻结。PR #19 发现非 OpenAI `tool_call` 的
`intentionrecognition` 线索，但未捕获结构化 Tool 事件。因此主路径只冻结“真实结果回调的语义
seam”，精确函数仍为 `BLOCKED / TD-007 / TD-009`。

## 3. 主路径为什么优先

| 维度 | 主路径结论 |
|---|---|
| 数据真实性 | 最接近宿主原始请求、结束帧和真实 Tool 结果，可建立来源证据 |
| 原文隔离 | 可在请求构造层分离显示文本和模型请求，不需要回写聊天记录 |
| 延迟 | 可采用异步发布和超时降级，不把重工作放进 UI 线程 |
| 契约一致性 | 可直接构造 D3-C 四对象，不需要从文本反推字段 |
| 可审查性 | Source diff、构建、安装、日志和回退可以逐项取证 |
| 风险 | 受上游版本、构建、Kaiming、KYSEC 和真实 Hook 可见性约束，必须经 D/L2 验证 |

选择主路径不等于授权修改官方应用，也不等于其工程链已经可用；D3-C 只冻结下一步应验证的唯一
方向，生产落地属于后续 C/D 任务与人工门禁。

## 4. 备用候选及批准条件

### 4.1 独立 Qt 演示壳

只在官方 Hook 构建、安装、KYSEC 或版本兼容被证明不可行，且 D/E 书面批准后，才可启用。

批准前至少明确：

- 具体代码仓和责任人；
- 与官方 AI 助手的功能差异和 UI 标识；
- 复用 `memory_event_contract_v1`，不得另造不兼容 Schema；
- 不把演示壳结果写成“官方应用已集成”；
- 安装、卸载、回退、权限和 L2 证据要求；
- 用户交互与安全审查结论。

当前状态：`PENDING_D_E_APPROVAL`。本文没有批准或实现该壳。

### 4.2 结构化执行日志/数据库 Adapter

只用于“宿主不存在可订阅的原生独立 Tool 事件”这一已证实情形，并须 D/E 书面批准。

允许的最低形态：

- 来源是受控执行器产生的结构化记录，不是关键词匹配；
- 可稳定关联 `tool_call_id` 和 `source_trace_id`；
- 状态、副作用、回滚、时间和脱敏引用可复核；
- 事件显式标注为 Adapter 来源，不冒充原生宿主事件；
- 成功、失败、取消均有 L2 案例和负向校验；
- Prompt Skill 和模型自述始终排除。

当前状态：`PENDING_D_E_APPROVAL / TD-007 / TD-009`。本文没有批准或实现该 Adapter。

## 5. 明确禁止的路径

| 路径 | 结论 | 原因 |
|---|---|---|
| 未批准的 LD_PRELOAD、二进制 patch、ABI 拦截或进程注入 | `PROHIBITED` | 版本、完整性、KYSEC 和回退风险不可控 |
| 全局关闭 KYSEC 或扩大系统权限 | `PROHIBITED` | 违反最小授权和正式验收红线 |
| 原地改写 UI/聊天库使用的用户原文 | `PROHIBITED` | 污染历史并可能被重新抽取成伪记忆 |
| 在 QML/UI 线程运行检索、向量化、冲突计算或持久化 | `PROHIBITED` | 阻塞交互并扩大崩溃面 |
| 从模型回答、Prompt Skill、界面文本或关键词推断 Tool success | `PROHIBITED` | 无真实执行证据，可能生成伪成功知识 |
| 未经批准轮询/抓取普通日志或数据库文本作为事件 | `PROHIBITED` | 来源、幂等、脱敏和状态语义不可靠 |
| 把旧 `sendToolMessage` 名称直接当成冻结 Hook | `PROHIBITED_UNTIL_VERIFIED` | PR #19 已显示真实路径可能不同 |
| 用 `RECORD.ID` 作为可靠递增事件或幂等标识 | `PROHIBITED` | 已有证据显示不能依赖该假设 |
| 由 C 轨单方面冻结 D IPC/KYSEC/部署或 E 业务枚举 | `OUT_OF_SCOPE` | 违反跨轨责任边界 |

## 6. 从候选升级所需证据

### 6.1 主路径

每个 seam 至少需要：

1. 当前目标 Commit 和宿主版本；
2. 精确 source diff 或受支持审计接口说明；
3. 构建、安装、启动和原版回退证据；
4. Kaiming/KYSEC 最小权限证据；
5. L2 正向、负向和重复触发案例；
6. UI/聊天库/模型请求三路原文隔离对照；
7. 结构化事件 Payload 与 v1 候选契约的逐字段对照；
8. D 主审与涉及用户交互/安全的 E 补审。

### 6.2 备用路径

除上述适用证据外，还必须有：

- 明确的失败触发条件；
- 书面批准人、日期和批准范围；
- 对外标识与能力差异；
- 不得宣称原生宿主事件或官方应用集成；
- 从备用恢复主路径或完整卸载的步骤。

## 7. 决策状态矩阵

| 路径 | 语义选择 | 实现 | 宿主证据 | 批准 | 当前可执行结论 |
|---|---|---|---|---|---|
| 官方源码 Pre-Chat | 已选 | 本任务不实现 | `NOT_OBSERVED / TD-008` | 后续变更需门禁 | 只保留候选 |
| 官方源码 Post-Turn | 已选 | 本任务不实现 | `PARTIAL / D2-C BLOCKED/E2` | 后续变更需门禁 | 只保留候选 |
| 官方真实 Tool 回调 | 已选语义 | 精确点未确认 | `NOT_VERIFIED / TD-007/009` | 后续变更需门禁 | 阻断 |
| 独立 Qt 演示壳 | 备用候选 | 未实现 | 无本批次证据 | `PENDING_D_E_APPROVAL` | 不得启用 |
| 结构化日志/数据库 Adapter | Tool 备用候选 | 未实现 | 无本批次证据 | `PENDING_D_E_APPROVAL` | 不得启用 |
| 禁止路径 | 不选 | 不实现 | 不适用 | 不可批准为本候选 | 禁止 |

## 8. 最终结论

D3-C 的唯一主方向已经明确：**当前官方 AI 助手源码上的最小 source-level Hook，按 Pre-Chat、
Post-Turn、真实 Tool Result 三个语义 seam 落地，并复用 v1 候选契约。**

当前没有已批准备用路径。若主路径在后续宿主验证中失败，应提交失败证据和具体备用提案等待
D/E 决策；在批准之前，正确动作是保持 `BLOCKED`，不是自行切换技术路线。
