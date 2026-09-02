# D12-A 任务卡：SDK 超时/异常恢复/性能抖动修复 + Bridge 假实现/吞异常检查 + 异常输入回归

| 字段 | 内容 |
|------|------|
| 任务编号 | D12-A（台账 row 61） |
| 任务标题 | ① 修复 SDK 超时、异常恢复和性能抖动；② 完成 Bridge 假实现/吞异常检查；③ 回归全部异常输入 |
| 责任轨道 | A（刘依枫）；Reviewer：D 主审；安全/评测影响时 E 补审 |
| 基线分支 | `fix/day12a-sdk-stability`（基于 main，已 merge main @ 6058391（#110/#123 等合入后）） |
| 阶段 | 功能冻结、联调缓冲与缺陷清理 |
| 完成定义 | SDK 相关 Critical/High 清零，或有明确负责人和日期；提交修复代码 + L0/L1 测试 + （必要时）L2 麒麟 VM 证据；更新证据索引与相关任务卡/PR 描述 |

---

## 一、范围

### 1.1 当日详细施工任务（台账 D12-A）

1. **修复 SDK 超时、异常恢复和性能抖动**：真实 SDK 调用在超时/异常/性能抖动场景下的稳定化处理。
2. **完成 Bridge 假实现/吞异常检查**：逐一核对 `cpp-bridge` 无假实现、无吞异常（对照 D11 期间 Bridge 安全审计口径）。
3. **回归全部异常输入**：空文本、超长文本、错误模型、非法枚举、异常返回等全量回归。

### 1.2 核心缺陷分析（任务 1）

**Bridge 线程池挂死恢复缺失（本 PR 核心修复）**：

- `EmbeddingService` 的 Bridge 调用统一在模块级线程池执行（`_executor`，max_workers=2）。
- 真实 SDK 调用超时后，`fut.cancel()` **无法中断已运行的 worker 线程**（SDK 无 cancel API，TD-A-005-01 Wontfix 已登记）。
- 若 2 个 worker 全部被永久挂死的 SDK 调用占满，后续所有 embed 请求排队 → 全部超时 → **Embedding 路径性能抖动归零**，直到进程重启。
- 对照：`extraction_provider.py` 的 LLM 路径已有 TD-A-D7-LLM-HANG-DEGRADE 挂死恢复机制（`_rebuild_executor()`），Embedding 路径缺失同类保护。

**修复方案**：镜像 TD-A-D7-LLM-HANG-DEGRADE——

- 跟踪 in-flight future 的提交时间（`_in_flight: Dict[Future, start_monotonic]`）。
- 每次请求入口（含合并等待路径）调用 `recover_hung_bridge_executor()`：若任一 in-flight 超过 `_embed_hang_threshold_ms`（默认 60s，远大于单次超时 5s）仍未完成 → 判定永久挂死 → 重建 executor（仅恢复后续请求能力；旧挂死 worker 无法终止，SDK 无 cancel API，残余风险见 TD-058），并有界上限 `_embed_max_hang_rebuilds`=3，超限进入 restart-required 快速失败（HIGH-01）；`_submit_bridge` 在锁内原子执行 recover/检测 + restart 判定 + submit（R2 HIGH-01 收口），同进程 stop/start 不绕过上限。；stop 时存在未完成 active Bridge Future → 保守置 restart-required（R3，threshold-before-stop 不绕过），空闲 stop 才允许同进程 start。
- 重建后 in-flight 清空、`_embed_hang_recovered` 计数递增；health 新增 `executor` 分项暴露可观测性；`_submit_bridge` 注册 `add_done_callback` 主动清理 in_flight（MEDIUM-01）。

### 1.3 范围外（本任务不做）

- 不涉及 B 轨 Vector/FTS5 检索链路（R-9 pending，勿扩大范围）。
- 不涉及 C 轨 MemoryClient/OS Agent Hook。
- 不涉及 E 轨记忆业务语义。
- 不涉及数据库 schema 变更。
- 不修改 `text_embedding_init_model` HOST_UNTESTED 状态（SDK 自动加载默认模型，bridge 未显式调用 init_model，保持现状）。
- 不处理既有测试顺序依赖问题（`test_td_a_local_batch.py` 的 `importlib.reload()` 产生新类，基线已存在，登记技术债不扩大范围）。

## 二、禁止修改范围（红线）

- 不修改已冻结契约：FRZ-IPC-002/006 错误码/envelope、Provider 错误码映射表。
- 不修改官方 SDK 头文件、不写 `/usr`、不覆盖官方 .so。
- 不把 Mock/固定返回/空实现当生产功能；降级只返回真实结果或明确空向量。
- 不把 WSL/沙箱结果当宿主证据；L2 真实 SDK 正常路径 HOST_VERIFIED；真实 SDK 挂死→重建恢复 RUNTIME_UNVERIFIED（无法安全注入永久挂死，算法由 L1 FakeProvider 模拟验证，HIGH-02 收敛声明）。

## 三、交付物清单

| # | 交付物 | 类型 |
|---|--------|------|
| 1 | `memory-service/embedding/embedding_service.py`：挂死恢复（`_maybe_recover_hung_executor`/`_submit_bridge`/`_mark_future_complete`/`recover_hung_bridge_executor`）+ health executor 分项 | 修改 |
| 2 | `memory-service/tests/test_embedding_d12a.py`：25 项（挂死恢复 7 + 错误传播 3 + 异常输入回归 9 + A-REQ-01 事件类型对齐 1 + 有界恢复/回调清理/stop-start/submit-gate 4） | 新增 |
| 3 | `docs/day12/01_task_card.md`：本文件 | 新增 |
| 4 | `docs/day12/03_bridge_audit_checklist.md`：Bridge 假实现/吞异常检查清单 | 新增 |
| 5 | `docs/day12/02_pr_description.md`：PR 描述 | 新增 |
| 6 | `evidence/index.yaml`：新增 D12A-L1/审计条目 | 修改 |

## 四、测试矩阵

| 层级 | 命令 | 预期 |
|------|------|------|
| L0 | `python -m py_compile memory-service/embedding/embedding_service.py` | 通过 |
| L1 | `PYTHONPATH=memory-service python -m pytest memory-service/tests/test_embedding_d12a.py` | 25 passed |
| L1 回归 | `... test_embedding_service.py test_embedding_d9.py test_embedding_d10.py test_embedding_d12a.py` | 85 passed |
| L2 | `scripts/verify_day12a_vm.sh`（麒麟 VM 真实 SDK） | 7/7 ALL PASS（PASS 7 FAIL 0） |

## 五、技术债关联

- TD-A-005-01（Wontfix）：SDK 无 cancel API，`timeout_ms` 透传；本 PR 在 Service 层线程池提供挂死恢复（调用方超时保护之外的第二层保障）。
- TD-A-D7-LLM-HANG-DEGRADE（Resolved）：本 PR 将同款挂死恢复模式扩展至 Embedding Bridge 线程池。
- TD-058（新登记）：SDK 无 cancel API，旧 executor worker 无法回收；本 PR 以有界重建（上限 3）防无界线程，超限 restart-required；同进程 stop/start 不重置计数，仅进程级重启清场。
- 新增候选：测试顺序依赖问题（`test_td_a_local_batch.py` `importlib.reload()` 污染），登记技术债。

## 六、验收标准

- L0/L1 全绿；25 项 D12A 专项测试 + A 轨回归 85 项通过（含 A-REQ-01 事件类型对齐、有界恢复、回调清理）。
- Bridge 检查清单逐项核实：无假实现、无吞异常、无固定返回、无空 catch。
- 异常输入回归覆盖：空文本/超长/错误模型/非法枚举/异常返回/非 str/batch 非法。
- PR 描述如实标注 L2 真实 SDK 正常路径 HOST_VERIFIED、真实 SDK 挂死恢复 RUNTIME_UNVERIFIED 的能力边界。

---
*任务卡编制：opencode（2026-09-01）｜依据：session-handoff-20260901.md §五、台账 D12-A row 61*
