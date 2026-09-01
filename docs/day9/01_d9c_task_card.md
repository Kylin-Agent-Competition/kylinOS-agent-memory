# D9C 任务卡：Memory Context 组装 Pipeline（C 轨）

| 字段 | 内容 |
|------|------|
| 任务编号 | D9-C |
| 任务标题 | Memory Context 组装：召回来源 / 记忆类型 / 冲突 / 不确定性提示 + Token 预算校验（Demo / Prototype） |
| 责任轨道 | C（刘承恩） |
| Reviewer | D 主审；Context 组装 / Token Budget / injection_status 语义由 E 补审 |
| 基线 | `origin/main`（同步，含 D5/D6/D7/D8 原型链） |
| 分支 | `feat/C-d9-context-assemble` |
| 工作类型 | 新增功能（feature） |
| 完成定义（台账 D9-C） | 接入 Memory Context 组装：组装 Memory Context、显示召回来源 / 记忆类型 / 冲突 / 不确定性提示、校验 Context 不超过 Token 预算 |

## 一、权威目标与验收口径

15 天 75 项施工台账为 D9-C 指定三项交付：

1. 组装 Memory Context（把召回候选组装为受 Token 预算控制的 Context）；
2. 显示召回来源、记忆类型、冲突 / 不确定性提示等可解释字段；
3. 校验 Context 不超过 Token 预算（客户端独立计算 `budget_exceeded`）。

验收要求为：**用户可触发 Memory Context 组装，并查看组装结果与可解释字段，
超预算时给出明确指示，注入失败 / 跳过时不产生伪 Context**。

本任务为 memory-client 侧 Demo / Prototype，沿用 D5/D6/D7/D8 的 Pipeline Harness 模式：
- 仅在 L0 Mock Gateway 或已部署的 Echo/D 轨 Gateway 上演示 envelope / payload 形状；
- **尚未**接入真实 AI Assistant Hook、Chat DB、SourceResolver、Token Budget 服务端实现；
- 候选 IPC 方法 `context.assemble` 标记为 `CANDIDATE / pending ADR`，生产默认返回
  `UNSUPPORTED_METHOD`，Demo / 测试态 Mock Gateway 可注册 handler。

## 二、候选 IPC 方法契约（CANDIDATE / pending ADR）

### 2.1 `context.assemble` — Memory Context 组装

- payload 必填：
  - `schema_version`（string，固定 `"1.0"`）
  - `user_id`（string，非空）
  - `query_text`（string，非空）
  - `token_budget`（integer，正数）
- payload 可选：
  - `scene`（string）
  - `candidates`（array，B 轨混合检索输出的候选列表）
- 响应 `data` 投影：
  - `context`（object）→ `assembledContext`
  - `recall_sources[]` → `contextRecallSources`
  - `memory_types[]` → `contextMemoryTypes`
  - `conflict_hints[]` → `contextConflictHints`
  - `uncertainty_hints[]` → `contextUncertaintyHints`
  - `token_budget` → `contextTokenBudget`
  - `actual_token_count` → `contextActualTokenCount`
  - `budget_exceeded`（bool）→ `contextBudgetExceeded`（客户端独立复核）
  - `injection_status`（string：`injected` / `failed` / `skipped`）→ `contextInjectionStatus`

方法直接复用 `MemoryClient::sendRequest()` 共享 envelope 编码与 pending 跟踪链路，
envelope 遵循 FRZ-IPC-006 长度前缀 JSON 规范，客户端死线 `5000ms`。

## 三、落地映射

| 台账交付 | 客户端实现 |
|---|---|
| 组装 Memory Context | `runContextAssemblePipeline()` + `assembledContext` 投影 |
| 显示召回来源 / 记忆类型 / 冲突 / 不确定性提示 | `contextRecallSources` / `contextMemoryTypes` / `contextConflictHints` / `contextUncertaintyHints` 投影 |
| 校验 Token 预算 | 客户端独立计算 `budget_exceeded = (actual_token_count > token_budget)` → `contextBudgetExceeded` |

### 3.1 ViewModel 扩展（已完成）

- 独立 `contextAssembleBusy_` / `pendingContextAssembleRequestId_`，沿用 D5 REWORK §C1
  模式避免与 D5/D6/D7/D8 Pipeline 多请求竞态；
- `onResponseReceived` 顶部统一解析业务 status，`status=error` 一律路由 `onRequestFailed`；
- 成功响应按 `pendingRequestId` 命中投影到 `assembledContext` 等字段，stage 置 `ready`；
- 失败路由到 `failed` 阶段（status=error / 未连接 / 空参数 / 超时）；
- `contextAssembleBusy_` 参与兼容 `busy` 属性（任一在途即为 busy）。

### 3.2 防伪 Context（关键约束）

沿用 D5 Pre-Chat 防伪 Context 模式，以下情况一律不产生伪 `assembledContext`，
所有投影字段清零：

- `injection_status` 为 `failed` 或 `skipped`；
- `status=error`；
- 空响应 / malformed envelope；
- 超时 / 未连接 / 空参数。

### 3.3 客户端 Token 预算校验

- 即使服务端未返回 `budget_exceeded`，客户端也独立计算
  `budget_exceeded = (actual_token_count > token_budget)`；
- 覆盖服务端可能漏返回该字段的场景；
- `actual_token_count` 缺失时视为 0，不触发超预算。

### 3.4 QML 页面

- `ContextAssemblePage.qml`：输入区（user\_id / query\_text / token\_budget /
  scene / candidates JSON）+ 输出区（组装结果 JSON + 可解释字段列表 +
  budget\_exceeded 指示灯 + injection\_status 状态）；
- 目标 Qt 5.12（不使用 5.15+ 语法），使用 ScrollView 防止 960×640 默认分辨率溢出；
- `main.qml` 新增导航按钮 + Component 声明；
- `resources.qrc` 注册新页面。

## 四、测试矩阵（L0 Mock Gateway）

`test_d9c_context_assemble.cpp` 覆盖 16 个用例：

| 用例 | 验证点 |
|---|---|
| S1 组装成功 | payload 含 schema\_version/user\_id/query\_text/token\_budget；assembledContext 填充 |
| S2 召回来源投影 | recall\_sources\[\] 正确投影 |
| S3 记忆类型投影 | memory\_types\[\] 正确投影 |
| S4 injection\_status=injected | injection\_status 字段投影 |
| B1 超预算指示 | actual\_token\_count > token\_budget → budget\_exceeded=true |
| B2 预算内 | actual\_token\_count <= token\_budget → budget\_exceeded=false |
| B3 服务端漏返回 budget\_exceeded | 客户端独立计算 |
| B4 actual\_token\_count 缺失 | 视为 0，不触发超预算 |
| F1 status=error 路由 failed | stage=failed + error + requestFailed |
| F2 injection\_status=failed 防伪 | assembledContext 为空，所有投影清零 |
| F3 injection\_status=skipped 防伪 | assembledContext 为空，所有投影清零 |
| F4 空响应 / malformed | stage=failed，不产生伪 Context |
| I1 独立 pending | 与 D5 Pre-Chat 并发不串台 |
| I2 独立 pending | 与 D6-C Tool Adapter 并发不串台 |
| I3 独立 pending | 与 D8-C KnowledgeDetail 并发不串台 |
| I4 未连接拒绝 | stage=failed |

## 五、非修改范围（Demo / Prototype 声明）

- 不接入真实 AI Assistant Hook / Chat DB / ChatRecord / model_request；
- 不实现真实 SourceResolver / Token Budget 服务端实现；
- `context.assemble` 为候选方法，pending ADR 立项；
- 不关闭 C-D9，不声称 SEC-CTX-01 / Context 注入已完成 Runtime 验证；
- L2 宿主验证需在麒麟 VM 上另行执行。

## 六、验收清单

- [x] C++ 层（protocol_adapter / memory_client / memory_view_model）扩展完成
- [x] ContextAssemblePage.qml 新增 + main.qml 导航 + resources.qrc 注册
- [x] L0 测试新增并注册到 tests/CMakeLists.txt
- [x] README.md 增加 D9-C 段落
- [x] PR 描述落盘 docs/day9/03_d9c_pr_description.md
- [ ] CI ctest 全绿（待 CI 执行）
