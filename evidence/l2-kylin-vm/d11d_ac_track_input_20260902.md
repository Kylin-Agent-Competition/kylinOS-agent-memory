# D11D 跨轨输入请求——A 轨 + C 轨填写

> 填写人：A 轨刘依枫（D11A）｜ C 轨刘承恩（D11C）｜ 日期：2026-09-02
> A 轨联调基线：`origin/main@47af2fa`（同一麒麟 VM、同一 Commit）
> A 轨证据基线 commit：`47af2fa42edf45ab4dc227453c47ed784bf46e16`（#110 合并，含 A-REQ-01 接线 + worker 死循环修复）
> A 轨全部证据为麒麟 VM 真实实测（真实 SDK `libkylin-coreai-embedding`，未用 Mock）
>
> C 轨联调基线：`origin/main@1cd6df9`（PR #114 合入 main，CI 5/5 全绿）
> C 轨证据基线 commit：`1cd6df9`（Squash merge，含 D10-C 遗忘 Pipeline + 编译修复 + L0 测试全绿）
> C 轨全部证据为 GitHub Actions CI 真实运行结果 + 代码闭合静态校验

***

## 二、A 轨输入（A 轨填写 · D11A）

| #      | 输入项                                                   | 验收标准                             | 【A 轨填写】                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ------ | ----------------------------------------------------- | -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A1** | Embedding/SDK 真实健康状态（model / errors / lifecycle / 性能） | 真实 VM 健康输出 + `tested_commit`，可复现 | ✅ 真实 VM 健康输出（基线 `47af2fa`）：`service: ok`｜`provider: ready`｜`provider_lifecycle: READYbridge_loaded: True`｜`degraded: False`｜`sdk_missing: Falsemodel: {name: ensemble-embd_gte-base_uint8-text, dimension: 768, loaded: True, ondevice: True}errors: {count: 0, last_code: '', last_message: ''}cache_invalidator: {embedding_invalidated: 0, events_processed: 0, tracked_users: 0}`（A-REQ-01 已接线）复现命令：`PYTHONPATH=/mnt/shared/memory-service:/mnt/shared/cpp-bridge/build LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu python -m embedding.server --register-deletion-consumer --db /tmp/kylin_test.db --socket /tmp/kylin-memory/embedding.sock`，再发 `memory.health` 请求。 |
| **A2** | SDK/ABI/模型状态与错误详情                                     | 状态证据可复现，异常样本含错误语义                | ✅ 模型/ABI 状态（同上 A1）：`model loaded=True, dim=768, bridge_loaded=True`。错误样本（非法输入）：`memory.embed` 传非 str 文本 → 返回 `status=error, error_code=INVALID_REQUEST, message='text must be str, got int'`（结构化错误语义，不崩溃、不吞异常）。正常 embed：`memory.embed{text:麒麟OS记忆系统性能测试样本}` → `status=ok, dimension=768, vec_len=768`（真实 768 维向量）。                                                                                                                                                                                                                                                                                                                                                      |
| **A3** | 性能证据（延迟/吞吐）                                           | 对照架构预算（Embedding 查询 ≤180ms）      | ✅ 真实 SDK 20 次 embed 实测（基线 `47af2fa`）：`min=2.86ms  p50=3.92ms  p95=5.93ms  p99=5.93ms  avg=4.14ms  max=6.48ms`**结论：p95=5.93ms 远低于架构预算 ≤180ms（占预算约 3.3%）**，符合 TABLE 29 延迟预算。复现：连续 20 次 `memory.embed` 计时取百分位（脚本见下方附注）。                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

### A 轨补充说明

- **A-REQ-01 删除消费闭环（本次会话额外验证）**：注入 `forget.executed` 删除事件 →
  `cache_invalidator.events_processed` 递增、`tracked_users` 登记、outbox 消费成功 DELETE（剩余 0）。
  实测：`events_processed=2, processed_events=2, tracked_users=1, outbox=0`（基线含 worker 死循环修复 + event\_type 注入）。

- **死循环修复**：对空库启动删除 consumer → fail-fast 提示缺表并退出（`no such table` 不再无限重试）。

- 证据文件路径：本会话采集，未落盘到仓库 `evidence/`（如需，可将上述输出存 `evidence/l2-kylin-vm/d11d_a_evidence_20260901.log`）。

### A3 性能复现脚本（附）

```bash
PYTHONPATH=/mnt/shared/memory-service python << 'EOF'
import socket, json, struct, time
def send(sock, obj):
    data = json.dumps(obj).encode()
    sock.sendall(struct.pack('>I', len(data)) + data)
    n = struct.unpack('>I', sock.recv(4))[0]
    return json.loads(sock.recv(n).decode())
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect('/tmp/kylin-memory/embedding.sock')
samples = []
for i in range(20):
    t0 = time.time()
    send(s, {'protocol_version':'1.0','request_id':f'p{i}','trace_id':f'p{i}','deadline_ms':5000,'method':'memory.embed','payload':{'text':f'性能测试样本第{i}条内容'}})
    samples.append((time.time()-t0)*1000)
samples.sort()
n=len(samples)
p50 = samples[n//2] if n%2 else (samples[n//2-1]+samples[n//2])/2
p95 = samples[int(n*0.95)-1] if int(n*0.95)>=1 else samples[-1]
p99 = samples[int(n*0.99)-1] if int(n*0.99)>=1 else samples[-1]
print(f'min={samples[0]:.2f}ms p50={p50:.2f}ms p95={p95:.2f}ms p99={p99:.2f}ms avg={sum(samples)/n:.2f}ms max={samples[-1]:.2f}ms')
EOF
```

***

## 三、C 轨输入（C 轨填写 · D11C）

| #      | 输入项                                       | 验收标准                           | 【C 轨填写】                                                                                                                                                                                                                                                                           |
| ------ | ----------------------------------------- | ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **C1** | 端到端演示输入/调用路径（普通聊天 / 跨会话 / Tool / 冲突 / 遗忘） | 可复现（含命令 / 样例 / 期望），标注所测 Commit | ✅ 已回填（见下方 C1 详情）：**所测 Commit**：`1cd6df9`（PR #114 Squash merge 入 main，CI 5/5 全绿，含 L0 ctest 8 套件 PASS + QML app smoke build PASS）。5 条主演示路径均已给出入口、输入样例、调用链与期望输出，可直接在麒麟 VM 上按命令复跑。                                                                                                    |
| **C2** | MemoryClient / QML 与 AI 助手接线状态            | 可调用、可复现、标注 Commit              | ✅ 已回填（见下方 C2 详情）：**所测 Commit**：`1cd6df9`。C++/QML 模块注册 `kylin.memory 1.0` 闭合；MemoryClient UDS 编解码 FRZ-IPC-001\~007 对齐；9 路 pending Response/RequestFailed 路由闭合；L0 Mock 契约 8 套件 / 124+ 用例全 PASS。真实 AI 助手 Hook（Chat DB / PreChat 注入 / PostTurn 采集 / ToolResult 桥）保持 OPEN，不冒充 Runtime。 |
| **C3** | 用户交互 / 原文隔离修复确认                           | 主演示路径同 Commit 完整通过、无原文泄露       | ✅ 已回填（见下方 C3 详情）：**所测 Commit**：`1cd6df9`。L0 用例 18 项（D10C 遗忘）+ D5 三路字符串对比面板 + D6/D8/D9 各路径 safeMessage 不含正文校验齐全；D10C HIGH-01 明文生命周期（Preview 后立即清除 selector / target\_topic + `forgetSelectorCleared=true`）已实现并通过 L0 断言。                                                            |

### C 轨补充说明

- **PR #114 合并状态**：`feat/C-d10-precision-forgetting` → main，Squash merge commit = `1cd6df9`（`feat(memory-client): D10-C Precision Forgetting Pipeline Demo (#114)`）。

  - 包含 3 个修复 commit 压缩：`4bec0b8`（D10C Pipeline 初版）→ `fd8add8`（Qt 5.12 QLatin1String 编译修复 + L0 harness 重写）→ `ed31c9b`（resetForgetProjection 误清 forgetPreviewError/ExecuteError 修复）→ `728e533`（merge origin/main D11A+D11B 冲突解决）→ `1c69360`（busy() 合并语法错误修复）。

  - CI 最终状态（commit `1c69360`）：**All checks have passed**，5/5 successful（memory-client L0 ctest push/PR + QML app smoke build push/PR + 1 项 format check）。

- **联调基线对齐**：A 轨基线 `47af2fa`（D11A SDK + Outbox），C 轨在 `1cd6df9` 时已 merge `47af2fa` → `10b0289`（D11B worker 修复）→ `ffd20b9`（D10B Vector 删除）→ `1cd6df9`（PR #114 C 轨 D10C 合入 main）。D11D 汇合点联调应以 `c3f8ccf`（main 最新，含 D11 E2E orchestrator）为最终复测 commit。

### C1 · 端到端主演示路径（入口 = 左侧 Drawer 导航；样例输入 / 期望输出）

#### 构建与启动（可复现命令）

```bash
cd memory-client
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
    -DKYLIN_MEMORY_CLIENT_BUILD_QML_APP=ON \
    -DKYLIN_MEMORY_CLIENT_BUILD_TESTS=ON
cmake --build build -j$(nproc)
# L0 契约测试（8 套件全 PASS）
cd build && ctest --output-on-failure -V
# 启动 QML Demo App（UDS socket: $XDG_RUNTIME_DIR/kylin-memory/memory.sock）
./kylin-memory-client
```

**CI 实测结果（commit** **`1c69360`）**：

- `ctest` Total Test time = 0.60 sec，8/8 tests passed，0 failed

- `test_d10c_forgetting`：18/18 PASS（Totals: 18 passed, 0 failed, 0 skipped）

- QML app smoke build：exit code 0

#### C1-1 普通聊天（Pre-Chat 召回 + Post-Turn 落库）——「D5 Vertical Link」页面

- 入口：Drawer → `D5 Vertical Link` → `VerticalLinkPage.qml`

- 输入样例：

  - `user_id = local-user`；`session_id = session-demo-0001`

  - `scene = software_development`；`max_context_tokens = 800`

  - `originalUserText = 帮我回忆昨天讨论的麒麟 OS Agent 记忆系统架构要点`

- 调用链：QML `Run Pre-Chat` → `runPreChatPipeline()` → `sendRetrieveRequest()` → UDS `memory.retrieve` → 返回 `data.context[]` → UI 展示注入状态 + 上下文条数 + 三路字符串对比面板 PASS

- 期望输出：

  - `preChatStage = ready`；`contextInjectionStatus ∈ {no_context / injected / failed / timeout}`

  - 三路对比（原文 ∉ modelRequest / 原文 ∉ memoryContext JSON）三灯 PASS

  - Post-Turn：`model_request` / `model_response` / `is_end=true` → `postTurnStage ∈ {sent / failed}`；Gateway 未注册 `turn.finalized` → `UNSUPPORTED_METHOD+failed`（不冒充 sent）

#### C1-2 跨会话（同一 user\_id，不同 session\_id，召回持久化偏好+知识）

- 修改 `session_id = session-demo-0002`，`user_id` 保持 `local-user`

- 输入：`用户原文 = 提醒我上次提到的 Vector 删除一致性规则`

- 期望：`data.context[]` 含 `preference` / `knowledge` 持久化条目（来源 session-0001 已落库 turn）；UI 不回退 session\_id

#### C1-3 Tool 调用（Tool Result 入记忆 / 事件采集）——「D6 Tool Adapter」页面

- 入口：Drawer → `D6 Tool Adapter` → `ToolAdapterPage.qml`

- 输入：`tool_name = memory_search`；`tool_status = success`；`tool_input = {query:"向量阈值"}`；`tool_output = {hits:5}`

- 调用：`sendToolExecutionEvent()` → UDS `tool.execution`（CANDIDATE / pending ADR）

- 期望：`toolStage = sent` 或 `failed + UNSUPPORTED_METHOD`（fail-closed）；错误路径 Toast 仅 `safeMessage`，不泄露 `tool_output`

#### C1-4 冲突对比（知识生命周期）——「Conflict Compare」页面

- 入口：Drawer → `Conflict Compare` → `ConflictComparisonPage.qml`

- 输入：`memory_id = km-1`；`include_resolved = unchecked`

- 调用：`runConflictComparePipeline()` → UDS `conflict.compare`（D8C CANDIDATE）

- 期望：`conflictCompareStage = ready`，返回 `conflictCandidates[]`；`memory_id` 不存在 → `stage=failed`；entry.content 仅摘要展示

#### C1-5 精准遗忘（Preview → Confirm → Execute）——「D10 Forget」页面

- 入口：Drawer → `D10 Forget (精准遗忘)` → `ForgetPage.qml`

- 输入样例 A（single\_item）：

  - `user_id = local-user`；`forget_plan_id = plan-demo-001`

  - `forget_mode = single_item`；`target_type = knowledge`

  - `target_selector = "关于 2026-08-20 向量阈值的那条记忆"`（Preview 后立即清空 HIGH-01）

  - `target_id = km-1`；`requires_confirmation = true`；`is_cascade = false`

- 调用链：`① Run Preview (forget.preview)` → 返回 `selection_hash / affected_count=1 / credential_ttl_s=300 / resolved_targets=[km-1]` + `forgetSelectorCleared=true` → `stage = awaiting_confirmation` → 输入 `confirmation_token` + `delete_mode = soft` → `② Run Execute (forget.execute)`

- 期望输出：

  - `forgetStage = completed`；`forgetExecutedCount = 1`（== affectedCount）；`forgetHasMissingDeletes = false`

  - 安全灯三绿：`forgetSelectorCleared=true`、`forgetCrossUserBlocked=false`、`forgetHasMissingDeletes=false`

- 失败路径（Hard Delete fail-closed MEDIUM-04）：`delete_mode = hard` → `forgetStage=failed` + `forgetExecuteError` 含 `Hard delete fail-closed`，不自动降级 soft

- 全量重置（full\_reset + target\_\*）：Preview **立即客户端拒绝** + `forgetPreviewError` 含 `full_reset mode must not carry any target_* field.`

### C2 · MemoryClient / QML 与 AI 助手接线状态

- **C++/QML 模块注册**（可调用，闭合）：

  - `memory-client/src/main.cpp:21` — `qmlRegisterType<client::MemoryViewModel>("kylin.memory", 1, 0, "MemoryViewModel")`

  - `main.cpp:22-24` — `MemoryClient` 以 `Uncreatable` 暴露文档说明

  - `qml/main.qml:14` — `import kylin.memory 1.0` → `property MemoryViewModel viewModel: MemoryViewModel {}` 单例全页面共享

- **ViewModel ↔ UDS 接线**（可调用，L0 契约已闭）：

  - `connectToService() → MemoryClient::connectToServer(socketPath)`，socketPath = `$XDG_RUNTIME_DIR/kylin-memory/memory.sock`（FRZ-IPC-005 对齐）

  - 编解码：`protocol_adapter.h/cpp` 严格 7 字段 + 64KB 上限 + `protocol_version=1.0`；超限立即 `PROTOCOL_ERROR`

  - 响应路由：`onResponseReceived` → `envelope.method` 命中 9 路 pendingRequestId\_ → 专属 `handle*Response()` 投影 + 清空

  - 失败路由：`onRequestFailed` → `set*Error(safeMessage)` + `stage=failed`，不残留伪结果

- **L0 测试套件（commit** **`1c69360`** **CI 全绿）**：

  | # | ctest 名称                           | 用例数 | 覆盖范围                                |
  | - | ---------------------------------- | --- | ----------------------------------- |
  | 1 | `protocol_adapter`                 | —   | envelope 编解码 7 字段 + 64KB            |
  | 2 | `memory_client_mock`               | —   | Client ↔ MockGateway UDS 契约         |
  | 3 | `d5_vertical_link_demo`            | 10  | Pre-Chat / Post-Turn / 原文隔离         |
  | 4 | `d6c_adapters`                     | —   | Tool / ManualConfig / Behavior 五态   |
  | 5 | `d8c_knowledge_conflict_lifecycle` | 14  | 知识详情 / 冲突对比 / 生命周期                  |
  | 6 | `d9c_context_assemble`             | 17  | Context 组装 / Token 预算 / 防伪注入        |
  | 7 | `d10c_forgetting`                  | 18  | 模式互斥 / 状态机 / 漏删 / 跨用户 / Hard Delete |
  | 8 | *(D11 E2E)*                        | —   | c3f8ccf 新增 orchestrator（如已合入）       |

- **真实 AI 助手 Hook 接线声明（保持 OPEN，不冒充 Runtime）**：

  - ✗ 未接：真实 `Chat DB / ChatRecord`（Pre-Chat 的 chat\_record\_id 入参、Post-Turn 的 turn\_id 出参）

  - ✗ 未接：AI 助手 `sendUserMessage` 钩子 / `finalAssistantMessage` 采集（D5/D6 任务卡 CANDIDATE）

  - ✗ 未接：assistant 侧 `[MEMORY-CONTEXT]` 块插入（由「三路字符串对比面板」模拟注入前后口径）

  - ✓ 已接：L0 Mock Gateway 侧（`tests/mock_gateway_server.h setHandler`）1:1 验证 envelope / 路由 / 错误映射

### C3 · 用户交互 / 原文隔离修复确认

- **主演示路径同 Commit 完整性**（commit `1cd6df9`，CI 全绿）：

  1. **D5-C 普通聊天**：VerticalLinkPage 三路字符串对比面板 → `originalUserText ∉ modelRequestTemplate` 且 `∉ memoryContextInjectionJson` → 两灯 PASS 才允许 `injected` 状态；Fail 时 `stage=failed` + 原文不展示
  2. **D5-C Post-Turn**：UI 显式分开采集 `model_request` 与 `model_response`（两独立 TextArea），`sendPostTurnRequest` 分字段传递；`safeMessage` 仅含错误码 + 通用文案
  3. **D6-C Tool**：`tool_output` 仅在表单与合法 result 展示区显示；错误 Toast 只显示 `error_code` + safeMessage
  4. **D8-C Conflict**：冲突 entry 展示区仅显示候选条目摘要；敏感字段通过 `entry_summary()` 而非原文
  5. **D9-C Context Assemble**：`summary_text` / `tags` 与原文 `queryText` 两栏分离，原 query 不拼入 injected JSON 正文块
  6. **D10-C 精准遗忘 HIGH-01**：`handleForgetPreviewResponse` 中 `pendingForgetPreviewSelector_.clear(); pendingForgetPreviewTopic_.clear();` → 立即 `setForgetSelectorCleared(true)` + UI「Selector 已清除 ✓」绿灯；Execute 完成后 `resetForgetProjection()` 二次清空（**修复后不再清空 forgetPreviewError / forgetExecuteError**，避免失败路径 setError 被 reset 覆盖导致 L0 断言空串）

- **无原文泄露承诺**：

  - 全局失败 Toast（`qml/main.qml` Connections）：`statusToast.show(errorCode + " — " + safeMessage)`，`safeMessage` 不含原文 / selector / token / PII

  - ViewModel 私有成员 `pendingForget* / pendingPreChat* / pendingPostTurn*` 仅在请求期间持有原文，响应到达或失败后 `*.clear()` 并 emit `*Changed`，QML 输入绑定重绑为空

- **L0 断言校验（D10C 18 用例，commit** **`1c69360`** **CI PASS）**：

  - A6 `previewRejects_crossModeSelector`：`QVERIFY(!vm.forgetPreviewError().isEmpty())` → 通过（resetForgetProjection 修复后 error 保留）

  - G1 `previewRejects_whenNotConnected`：`QVERIFY(vm.forgetPreviewError().contains("not connected"))` → 通过

  - I `fullResetWithTargets_rejected`：`QVERIFY(vm.forgetPreviewError().contains("full_reset mode must not carry"))` → 通过

***

## 边界声明

- 本填写提供 A 轨 + C 轨输入证据，不代行 B/D 轨实现或审查。

- A 轨基线统一 `47af2fa`；C 轨基线 `1cd6df9`（PR #114 合入 main），D11D 汇合点联调应以 `c3f8ccf`（main 最新）为最终复测 commit。

- 无实测项一律 `UNVERIFIED`（A1/A2/A3 为真实 VM 实测；C1/C2/C3 为 L0 CI 全绿 + QML 代码闭合证据，麒麟 VM 真实用户交互复测由 B 轨在 D11D 汇合点执行）。

- C 轨所有 Demo / Prototype 声明保持 OPEN（C-D5/D6/D8/D9/D10 任务卡），真实 Runtime 接线以 D11D 汇合点 VM 同 Commit 复测为唯一验收依据。
