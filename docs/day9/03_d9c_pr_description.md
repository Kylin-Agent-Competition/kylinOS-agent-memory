# PR: feat(memory-client): D9-C Memory Context 组装 Pipeline Demo / Prototype

## 背景

15 天 75 项施工台账 D9-C 要求：接入 Memory Context 组装，显示召回来源、记忆类型、
冲突 / 不确定性提示，校验 Context 不超过 Token 预算。

本 PR 在 memory-client 侧新增候选 IPC 方法 `context.assemble` 的 Pipeline Harness、
QML 页面与 L0 Mock 契约测试，沿用 D5/D6/D7/D8 的 Demo / Prototype 模式。

## 修改范围

1. **protocol_adapter.{h,cpp}**：新增 1 个候选 IPC 方法常量
   - `context.assemble`（CANDIDATE / pending ADR）

2. **memory_client.{h,cpp}**：新增 1 个 Q_INVOKABLE 便捷 send 方法
   - `sendContextAssembleRequest()`
   - 复用 `sendRequest()` 共享 envelope 编码与 pending 跟踪链路

3. **memory_view_model.{h,cpp}**：新增 D9-C 组装 Pipeline
   - `runContextAssemblePipeline()` → `assembledContext` 投影（含可解释字段）
   - 独立 `contextAssembleBusy_` / `pendingContextAssembleRequestId_`，沿用 D5 REWORK
     §C1 模式避免与 D5/D6/D7/D8 Pipeline 多请求竞态
   - `onResponseReceived` 顶部统一解析业务 status，`status=error` 一律路由 `onRequestFailed`
   - 失败 / 超时区分 `failed` / `timeout` 阶段
   - 响应投影字段：
     - `assembledContext`（context 对象）
     - `contextRecallSources`（召回来源列表）
     - `contextMemoryTypes`（记忆类型列表）
     - `contextConflictHints`（冲突提示列表）
     - `contextUncertaintyHints`（不确定性提示列表）
     - `contextTokenBudget` / `contextActualTokenCount` / `contextBudgetExceeded`
     - `contextInjectionStatus`（injected / failed / skipped）

4. **防伪 Context**（关键约束）
   - `injection_status` 为 `failed` / `skipped` 或 `status=error` / 空响应时，
     一律不产生伪 `assembledContext`，所有投影字段清零（沿用 D5 Pre-Chat 防伪 Context 模式）

5. **客户端 Token 预算校验**
   - 客户端独立计算 `budget_exceeded = (actual_token_count > token_budget)`
   - 覆盖服务端可能漏返回该字段的场景
   - `actual_token_count` 缺失时视为 0，不触发超预算

6. **QML 页面**（目标 Qt 5.12，ScrollView 防 960×640 溢出）
   - `ContextAssemblePage.qml`：输入区 user\_id / query\_text / token\_budget / scene /
     candidates JSON + 输出区组装结果与可解释字段
   - `main.qml`：新增导航按钮 + Component 声明
   - `resources.qrc`：注册新页面

7. **L0 测试**：`test_d9c_context_assemble.cpp`（16 用例）
   - S1-S4：组装成功 / 召回来源投影 / 记忆类型投影 / injection\_status=injected
   - B1-B4：超预算指示 / 预算内 / 服务端漏返回 budget\_exceeded / actual 缺失
   - F1-F4：status=error / injection=failed 防伪 / injection=skipped 防伪 / 空响应
   - I1-I4：与 D5 Pre-Chat / D6-C Tool / D8-C KnowledgeDetail 独立 pending + 未连接拒绝

8. **tests/CMakeLists.txt**：注册 `d9c_context_assemble` ctest 目标

9. **README.md**：新增 D9-C 段落 + 更新目录树 / CI ctest 目标列表（7/7）

10. **docs/day9/01_d9c_task_card.md**：D9-C 任务卡

## 测试结果

- 本地环境（Windows）未安装 cmake，无法本地构建；CI 将在 ubuntu-22.04 上执行构建 + ctest
- 预期 ctest 目标：`protocol_adapter` / `memory_client_mock` / `d5_vertical_link_demo` /
  `d6c_multi_source_adapters` / `d7c_preference_editor` / `d8c_knowledge_conflict_lifecycle` /
  `d9c_context_assemble`（7/7）
- 新增测试用例：16 个（S1-S4 / B1-B4 / F1-F4 / I1-I4）

## 完成标准

- [x] C++ 层（protocol_adapter / memory_client / memory_view_model）扩展完成
- [x] ContextAssemblePage.qml 新增 + main.qml 导航 + resources.qrc 注册
- [x] L0 测试新增并注册到 tests/CMakeLists.txt
- [x] README.md 增加 D9-C 段落
- [x] PR 描述落盘
- [ ] CI ctest 全绿（待 CI 执行）

## 非修改范围（Demo / Prototype 声明）

- **不关闭 C-D9**
- 不接入真实 AI Assistant Hook / Chat DB / ChatRecord / model_request
- 不实现真实 SourceResolver / Token Budget 服务端实现
- `context.assemble` 为候选方法，pending ADR 立项；
  生产默认返回 `UNSUPPORTED_METHOD`，Demo / 测试态 Mock Gateway 可注册 handler
- 不声称 SEC-CTX-01 / Context 注入已完成 Runtime 验证
- L2 宿主验证需在麒麟 VM 上另行执行

## 风险与后续

- 候选方法 `context.assemble` pending ADR 立项，方法名 / payload 结构可能在 ADR 冻结后调整
- 客户端 Token 预算校验仅做 `actual > budget` 比较，不实现真实 token 计数（依赖服务端返回）
- 后续 D9-D 可补充真实 SourceResolver / Token Budget 服务端联调
- 防伪 Context 仅清零客户端投影，不阻止服务端记录失败原因（审计完整性由服务端负责）
