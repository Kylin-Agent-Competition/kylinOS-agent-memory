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
     - `contextInjectionStatus`（prepared / degraded / failed / skipped）

4. **防伪 Context**（关键约束）
   - `injection_status` 为 `failed` / `skipped` 或 `status=error` / 空响应时，
     一律不产生伪 `assembledContext`，所有投影字段通过 `resetContextProjection()`
     统一清零（沿用 D5 Pre-Chat 防伪 Context 模式）
   - **REWORK I-2 修复**：本地校验失败路径（busy / 空参数 / 未连接 / send 失败）
     统一调用 `resetContextProjection()` 清空上一轮投影，避免 stale Context 残留

5. **客户端 Token 预算校验**
   - 客户端独立计算 `budget_exceeded = (actual_token_count > token_budget)`
   - 覆盖服务端可能漏返回该字段的场景
   - `actual_token_count` 缺失时视为 0，不触发超预算
   - **REWORK M-2 修复**：响应缺失 `token_budget` 时回退到本次请求的
     `requestedTokenBudget_`，避免 UI 显示 "250 / 0" 且无法触发超预算

6. **QML 页面**（目标 Qt 5.12，ScrollView 防 960×640 溢出）
   - `ContextAssemblePage.qml`：输入区 user\_id / query\_text / token\_budget / scene /
     candidates JSON + 输出区组装结果与可解释字段
   - `main.qml`：新增导航按钮 + Component 声明
   - `resources.qrc`：注册新页面

7. **L0 测试**：`test_d9c_context_assemble.cpp`（17 用例，A/E/S/R 命名）
   - A1-A11：组装成功 / recall\_sources 字符串投影 / memory\_types 对象投影 /
     conflict\_hints 对象投影 / uncertainty\_hints 字符串投影 / 预算内 / 超预算 /
     空 user\_id / 空 query\_text / 非正 budget / candidates 转发
   - E1-E2：status=error 路由 failed / UNSUPPORTED\_METHOD 路由 failed
   - S1-S2：injection=skipped 防伪 / injection=failed 防伪
   - R1-R2：与 D8C 独立 pending / 未连接拒绝

8. **tests/CMakeLists.txt**：注册 `d9c_context_assemble` ctest 目标

9. **README.md**：新增 D9-C 段落 + 更新目录树 / CI ctest 目标列表

10. **docs/day9/01_d9c_task_card.md**：D9-C 任务卡（17 用例矩阵 + injection_status
    值域统一为 prepared/degraded/failed/skipped）

## REWORK 修复（针对 review 5078244445 / 5078405804）

- **C-1（BLOCKER）**：新增 `projectJsonArrayMixed()` 投影函数，同时保留字符串与
  对象元素；D9C 全部四个数组投影（recall\_sources / memory\_types / conflict\_hints /
  uncertainty\_hints）改用此函数。修复前 `projectJsonArray` 仅保留 isObject()，
  导致字符串数组（fts5/vector/rrf、vector\_score\_unverified）被丢弃，
  A2/A5 测试确定性失败（CI 2/17 failed）。
- **I-2（Important）**：新增 `resetContextProjection()` 辅助函数，所有失败路径
  （busy / 空参数 / 未连接 / send 失败 / status=error / injection=failed/skipped /
  超时）统一调用清空投影，避免 stale Context 残留。
- **I-1（Important）**：任务卡 / PR 描述测试矩阵更新为实际 17 用例
  （A1-A11 / E1-E2 / S1-S2 / R1-R2），删除声明的 B4/F4/I1/I2。
- **M-1**：injection\_status 值域统一为 `prepared / degraded / failed / skipped`
  （任务卡 §2.1 + .h 注释对齐）。
- **M-2**：响应缺失 token\_budget 时回退到 `requestedTokenBudget_`。
- **M-3**：用例数口径统一为 17。
- **LOW-2**：rebase 同步 main（behind=0）。

## 测试结果

- 本地环境（Windows）未安装 cmake，无法本地构建；CI 将在 ubuntu-22.04 上执行构建 + ctest
- 预期 ctest 目标：`protocol_adapter` / `memory_client_mock` / `d5_vertical_link_demo` /
  `d6c_multi_source_adapters` / `d7c_preference_editor` / `d8c_knowledge_conflict_lifecycle` /
  `d9c_context_assemble`（7/7）
- 新增测试用例：17 个（A1-A11 / E1-E2 / S1-S2 / R1-R2）
- 上一轮 CI（HEAD 4b88896）：d9c\_context\_assemble 15/17 passed（A2/A5 失败，
  根因 C-1 字符串投影）；本轮 REWORK 后预期 17/17 passed

## 完成标准

- [x] C++ 层（protocol_adapter / memory_client / memory_view_model）扩展完成
- [x] ContextAssemblePage.qml 新增 + main.qml 导航 + resources.qrc 注册
- [x] L0 测试新增并注册到 tests/CMakeLists.txt（17 用例 A/E/S/R 命名）
- [x] README.md 增加 D9-C 段落
- [x] PR 描述落盘
- [x] REWORK 修复：C-1 字符串投影 / I-2 失败路径清空 / M-2 budget 回退 /
  I-1 文档矩阵对齐 / M-1 injection\_status 词汇统一 / M-3 用例数统一
- [ ] CI ctest 全绿（待 CI 执行，预期 7/7 含 d9c 17/17）

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
