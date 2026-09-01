# PR: feat(memory-client): D8-C 知识详情 / 冲突对比 / 生命周期状态 Pipeline Demo / Prototype

## 背景

15 天 75 项施工台账 D8-C 要求：用户可查看单条知识详情、发起冲突对比、查看生命周期状态。
本 PR 在 memory-client 侧新增三个候选 IPC 方法（`knowledge.detail` / `conflict.compare` /
`lifecycle.status`）的 Pipeline Harness、QML 页面与 L0 Mock 契约测试，沿用 D5/D6/D7 的
Demo / Prototype 模式。

## 修改范围

1. **protocol_adapter.{h,cpp}**：新增 3 个候选 IPC 方法常量
   - `knowledge.detail` / `conflict.compare` / `lifecycle.status`（CANDIDATE / pending ADR）

2. **memory_client.{h,cpp}**：新增 3 个 Q_INVOKABLE 便捷 send 方法
   - `sendKnowledgeDetailRequest()` / `sendConflictCompareRequest()` / `sendLifecycleStatusRequest()`
   - 复用 `sendRequest()` 共享 envelope 编码与 pending 跟踪链路

3. **memory_view_model.{h,cpp}**：新增三组 Pipeline
   - `runKnowledgeDetailPipeline()` → `knowledgeDetail` 投影（含 evidence/conditions）
   - `runConflictComparePipeline()` → `conflictCandidates` 投影
   - `runLifecycleStatusPipeline()` → `lifecycleItems` 投影
   - 三组独立 busy / stage / error / pending，沿用 D5 REWORK §C1 模式避免多请求竞态
   - `onResponseReceived` 顶部统一解析业务 status，`status=error` 一律路由 `onRequestFailed`
   - 失败 / 超时区分 `failed` / `timeout` 阶段

4. **QML 页面**（目标 Qt 5.12，ScrollView 防 960×640 溢出）
   - `KnowledgeDetailPage.qml`：memory_id 输入 + evidence/conditions 开关 + 详情 JSON
   - `ConflictComparisonPage.qml`：memory_id 输入 + include_resolved 开关 + 候选列表
   - `LifecycleStatusPage.qml`：user_id 输入 + memory_id/memory_status 可选过滤 + 条目列表
   - `main.qml`：新增 3 个导航按钮 + Component 声明
   - `resources.qrc`：注册 3 个新页面（同时补齐 D6-C 遗漏的 3 个页面）

5. **L0 测试**：`test_d8c_knowledge_conflict_lifecycle.cpp`（14 用例）
   - K1-K3：知识详情成功 / evidence 投影 / 空 memory_id 拒绝
   - C1-C3：冲突对比成功 / 默认未解决 / 空候选
   - L1-L3：生命周期成功 / 可选过滤透传 / 空 user_id 拒绝
   - E1-E3：三 pipeline status=error 路由 failed
   - R1-R2：三 pipeline 独立 pending 不串台 / 未连接拒绝

6. **tests/CMakeLists.txt**：注册 `d8c_knowledge_conflict_lifecycle` ctest 目标

7. **README.md**：新增 D8-C 段落 + 更新目录树 / CI ctest 目标列表

8. **docs/day8/05_d8c_task_card.md**：D8-C 任务卡

## 测试结果

- 本地环境（Windows）未安装 cmake，无法本地构建；CI 将在 ubuntu-22.04 上执行构建 + ctest
- 预期 ctest 目标：`protocol_adapter` / `memory_client_mock` / `d5_vertical_link_demo` /
  `d6c_multi_source_adapters` / `d7c_preference_editor` / `d8c_knowledge_conflict_lifecycle`（6/6）
- 新增测试用例：14 个（K1-K3 / C1-C3 / L1-L3 / E1-E3 / R1-R2）

## 完成标准

- [x] C++ 层（protocol_adapter / memory_client / memory_view_model）扩展完成
- [x] 3 个 QML 页面新增 + main.qml 导航 + resources.qrc 注册
- [x] L0 测试新增并注册到 tests/CMakeLists.txt
- [x] README.md 增加 D8-C 段落
- [x] PR 描述落盘
- [ ] CI ctest 全绿（待 CI 执行）

## 非修改范围（Demo / Prototype 声明）

- **不关闭 C-D8**
- 不接入真实 AI Assistant Hook / Chat DB / ChatRecord / model_request
- 不实现知识 / 冲突 / 生命周期持久化后端
- `knowledge.detail` / `conflict.compare` / `lifecycle.status` 为候选方法，pending ADR 立项；
  生产默认返回 `UNSUPPORTED_METHOD`，Demo / 测试态 Mock Gateway 可注册 handler
- 不声称 SEC-CTX-01 / 知识治理 / 冲突仲裁已完成 Runtime 验证
- L2 宿主验证需在麒麟 VM 上另行执行

## 风险与后续

- 三个候选方法 pending ADR 立项，方法名 / payload 结构可能在 ADR 冻结后调整
- 本 PR 基于 main（47018a4），temp commit 包含 D6-C 合并文件（D6-C PR #88 未合并时的依赖）
- 后续 D8-D 可补充真实知识 / 冲突 / 生命周期后端联调
