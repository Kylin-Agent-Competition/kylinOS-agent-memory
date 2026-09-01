# D8C 任务卡：知识详情 / 冲突对比 / 生命周期状态 Pipeline（C 轨）

| 字段 | 内容 |
|------|------|
| 任务编号 | D8-C |
| 任务标题 | 知识详情、冲突对比与生命周期状态 QML 组件与 IPC Pipeline（Demo / Prototype） |
| 责任轨道 | C（刘承恩） |
| Reviewer | D 主审；知识/冲突/生命周期业务语义与遗忘/用户隔离由 E 补审 |
| 基线 | `origin/main@47018a4`（2026-08-31 同步，含 D6D 契约先行 v5 与 D7C/D7D） |
| 分支 | `feat/C-d8-knowledge-conflict-lifecycle` |
| 工作类型 | 新增功能（feature） |
| 完成定义（台账 D8-C） | 用户可查看单条知识详情、发起冲突对比、查看生命周期状态 |

## 一、权威目标与验收口径

15 天 75 项施工台账为 D8-C 指定三项交付：

1. 知识详情组件（单条记忆的证据 / 适用条件投影）；
2. 冲突对比组件（候选记忆列表与未解决冲突展示）；
3. 生命周期状态组件（按 user_id / memory_status 过滤的记忆条目列表）。

验收要求为：**用户可查看单条知识详情、发起冲突对比、查看生命周期状态**。

本任务为 memory-client 侧 Demo / Prototype，沿用 D5/D6/D7 的 Pipeline Harness 模式：
- 仅在 L0 Mock Gateway 或已部署的 Echo/D 轨 Gateway 上演示 envelope / payload 形状；
- **尚未**接入真实 AI Assistant Hook、Chat DB、知识/冲突/生命周期持久化后端；
- 三个候选 IPC 方法（`knowledge.detail` / `conflict.compare` / `lifecycle.status`）标记为
  `CANDIDATE / pending ADR`，生产默认返回 `UNSUPPORTED_METHOD`，Demo / 测试态 Mock Gateway
  可注册 handler。

## 二、候选 IPC 方法契约（CANDIDATE / pending ADR）

### 2.1 `knowledge.detail` — 单条知识详情

- payload 必填：`memory_id`（string）。
- payload 可选：`include_evidence`（bool，默认 true）、`include_conditions`（bool，默认 true）。
- 响应 `data` 投影：整对象直接作为 `knowledgeDetail`（含 `evidence[]` / `conditions[]` 列表）。

### 2.2 `conflict.compare` — 冲突候选对比

- payload 必填：`memory_id`（string）。
- payload 可选：`include_resolved`（bool，默认 false，仅返回未解决冲突）。
- 响应 `data.candidates[]` 投影到 `conflictCandidates`。

### 2.3 `lifecycle.status` — 生命周期状态

- payload 必填：`user_id`（string）。
- payload 可选：`memory_id`（string）、`memory_status`（string，如 `active` / `candidate` /
  `superseded` / `archived`）。
- 响应 `data.items[]` 投影到 `lifecycleItems`。

三个方法均直接复用 `MemoryClient::sendRequest()` 共享 envelope 编码与 pending 跟踪链路，
envelope 遵循 FRZ-IPC-006 长度前缀 JSON 规范，客户端死线 `5000ms`。

## 三、落地映射

| 台账交付 | 客户端实现 |
|---|---|
| 知识详情组件 | `KnowledgeDetailPage.qml` + `runKnowledgeDetailPipeline` + `knowledgeDetail` 投影 |
| 冲突对比组件 | `ConflictComparisonPage.qml` + `runConflictComparePipeline` + `conflictCandidates` 投影 |
| 生命周期状态组件 | `LifecycleStatusPage.qml` + `runLifecycleStatusPipeline` + `lifecycleItems` 投影 |

### 3.1 ViewModel 扩展（已完成）

- 三组独立 busy / stage / error / pending 状态，沿用 D5 REWORK §C1 模式避免多请求竞态；
- `onResponseReceived` 顶部统一解析业务 status，`status=error` 一律路由 `onRequestFailed`；
- 成功响应按 `pendingRequestId` 命中分别投影到 `knowledgeDetail` / `conflictCandidates` /
  `lifecycleItems`，stage 置 `ready`；
- 失败 / 超时路由区分 `failed` / `timeout` 阶段；
- 三组 busy 共同参与兼容 `busy` 属性（任一在途即为 busy）。

### 3.2 QML 页面（本任务）

- `KnowledgeDetailPage.qml`：`memory_id` 输入 + evidence/conditions 开关 + 详情 JSON 展示；
- `ConflictComparisonPage.qml`：`memory_id` 输入 + include_resolved 开关 + 候选列表；
- `LifecycleStatusPage.qml`：`user_id` 输入 + memory_id/memory_status 可选过滤 + 条目列表。

三页均目标 Qt 5.12（不使用 5.15+ 语法），使用 ScrollView 防止 960×640 默认分辨率溢出。

## 四、测试矩阵（L0 Mock Gateway）

`test_d8c_knowledge_conflict_lifecycle.cpp` 覆盖：

| 用例 | 验证点 |
|---|---|
| K1 知识详情成功 | payload 含 memory_id/include_evidence/include_conditions；knowledgeDetail 填充 |
| K2 知识详情 evidence 投影 | evidence[] 列表正确投影 |
| K3 知识详情空 memory_id | stage=failed，不发送 |
| C1 冲突对比成功 | payload 含 memory_id/include_resolved；conflictCandidates 填充 |
| C2 冲突对比默认未解决 | include_resolved=false 默认值 |
| C3 冲突对比空候选 | 空数组投影不报错 |
| L1 生命周期状态成功 | payload 含 user_id；lifecycleItems 填充 |
| L2 生命周期状态可选过滤 | memory_id/memory_status 透传 |
| L3 生命周期状态空 user_id | stage=failed |
| E1 知识详情 status=error | stage=failed + error + requestFailed |
| E2 冲突对比 status=error | stage=failed + error |
| E3 生命周期状态 status=error | stage=failed + error |
| R1 三 pipeline 独立 pending | 并发不串台 |
| R2 未连接拒绝 | stage=failed |
| R3 超时路由 timeout | deadline 触发后 stage=timeout |

## 五、非修改范围（Demo / Prototype 声明）

- 不接入真实 AI Assistant Hook / Chat DB / ChatRecord / model_request；
- 不实现知识 / 冲突 / 生命周期持久化后端；
- `knowledge.detail` / `conflict.compare` / `lifecycle.status` 为候选方法，pending ADR 立项；
- 不关闭 C-D8，不声称 SEC-CTX-01 / 知识治理 / 冲突仲裁已完成 Runtime 验证；
- L2 宿主验证需在麒麟 VM 上另行执行。

## 六、验收清单

- [x] C++ 层（protocol_adapter / memory_client / memory_view_model）扩展完成
- [ ] 3 个 QML 页面新增 + main.qml 导航 + resources.qrc 注册
- [ ] L0 测试新增并注册到 tests/CMakeLists.txt
- [ ] 本地构建 + ctest 全绿
- [ ] README.md 增加 D8-C 段落
- [ ] PR 描述落盘 docs/day8/06_d8c_pr_description.md
