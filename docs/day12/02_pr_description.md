# A-feat(day12): SDK 超时/异常恢复/性能抖动修复 + Bridge 假实现/吞异常检查 + 异常输入回归

## 背景与目标

D11（同一虚拟机全功能联调，PR #84）已合并。D12 进入功能冻结、联调缓冲与缺陷清理阶段，A 轨任务（台账 D12-A row 61）：
1. 修复 SDK 超时、异常恢复和性能抖动
2. 完成 Bridge 假实现/吞异常检查
3. 回归全部异常输入

**核心缺陷**：EmbeddingService 的 Bridge 线程池（max_workers=2）缺少挂死恢复机制。真实 SDK 调用超时后 `fut.cancel()` 无法中断已运行的 worker（SDK 无 cancel API，TD-A-005-01 Wontfix），若 2 个 worker 全被永久挂死的调用占满，后续所有 embed 请求排队超时——Embedding 路径性能抖动归零，直到进程重启。

## 修改范围

1. **Bridge 线程池挂死恢复**（镜像 TD-A-D7-LLM-HANG-DEGRADE）：
   - `embedding_service.py` 新增 `_in_flight` future 跟踪 + `_maybe_recover_hung_executor()`（超阈值重建 executor）+ `recover_hung_bridge_executor()`（每次请求入口调用，含合并等待路径）+ `_mark_future_complete()`（完成/失败自动清理）
   - `health()` 新增 `executor` 分项（max_workers/in_flight/hang_recovered/hang_threshold_ms）暴露可观测性
2. **Bridge 假实现/吞异常检查**：`docs/day12/03_bridge_audit_checklist.md` 逐项核对（6 套 C++ 测试 + 逐 catch 核对 + 2 处 Wontfix 固定值判定）
3. **异常输入回归**：`test_embedding_d12a.py` 19 项（挂死恢复 7 + 错误传播 3 + 异常输入回归 9：空文本/超长/错误模型/非法枚举/异常返回/非 str/batch 非法）

## 明确不修改范围

- 不涉及 B 轨 Vector/FTS5 检索链路（R-9 pending）
- 不涉及 C 轨 MemoryClient/OS Agent Hook
- 不涉及 E 轨记忆业务语义
- 不涉及数据库 schema 变更
- 不修改 `text_embedding_init_model` HOST_UNTESTED 状态
- 不处理既有测试顺序依赖（`test_td_a_local_batch.py` importlib.reload 污染，基线已存在，登记技术债）

## 关联任务与技术债

- 任务卡：`docs/day12/01_task_card.md`
- 关联：TD-A-005-01（Wontfix，本 PR 补强）、TD-A-D7-LLM-HANG-DEGRADE（模式复用）
- 新增候选：测试顺序依赖问题登记技术债

## 架构与能力边界依据

- 架构 TABLE 29（延迟预算）：Embedding 查询 ≤180ms
- 架构 TABLE 36（可观测性）：health 分项指标
- TD-A-D7-LLM-HANG-DEGRADE：挂死恢复模式（extraction_provider 已实现）

## 修改文件清单

| 文件 | 变更类型 | 摘要 |
|------|---------|------|
| `memory-service/embedding/embedding_service.py` | 修改 | +挂死恢复机制 + health executor 分项 |
| `memory-service/tests/test_embedding_d12a.py` | 新增 | 19 项 D12A 专项测试 |
| `docs/day12/01_task_card.md` | 新增 | D12-A 任务卡 |
| `docs/day12/02_pr_description.md` | 新增 | 本文件 |
| `docs/day12/03_bridge_audit_checklist.md` | 新增 | Bridge 假实现/吞异常检查清单 |
| `evidence/index.yaml` | 修改 | 新增 D12A 条目 |

## 测试结果

### L0

```
python -m py_compile memory-service/embedding/embedding_service.py  # OK
```

### L1（WSL）

```
test_embedding_d12a.py: 19 passed
test_embedding_service.py + d9 + d10 + d12a: 79 passed
```

覆盖：挂死恢复（超时→重建→恢复 / 未超阈值不误重建 / 并发无死锁 / in-flight 清理 / health 分项）、错误传播（错误码保留 / 未知异常不崩溃 / 失败不伪装成功）、异常输入（空文本/超长/错误模型/非法枚举/异常返回/非 str/batch 非法/降级结构化）。

### 安全与假实现审查

- Bridge 检查清单：无空 catch、无吞异常、无固定返回、无 stub（见 `docs/day12/03_bridge_audit_checklist.md`）
- 挂死恢复仅重建线程池，不触碰 Provider/SDK 会话（线程池重建与 SDK 会话解耦，安全）
- 所有测试使用 FakeProvider（不依赖 SDK），无 Mock 冒充 Runtime 行为
- 无密钥泄露、无硬编码配置

### L2 麒麟虚拟机证据

**待 VM 运行**（本次会话 VM 不可达，SSH 127.0.0.1:2222 connection refused）。验证脚本 `scripts/verify_day12a_vm.sh` 待执行，结果回填本 PR 与 evidence/index.yaml。

## 性能影响

- 正常路径零开销：`recover_hung_bridge_executor()` 仅在每次 embed 入口检查 in-flight 计数（O(in-flight) 极小，默认 2 worker）
- 仅挂死超过阈值（60s）时才重建 executor，正常慢任务不触发
- health 分项仅读内存计数，无 SDK 调用

## 已知限制

- 挂死恢复是调用方超时保护的第二层保障（SDK 无主动中断能力，TD-A-005-01 Wontfix 保持）
- `_embed_hang_threshold_ms` 默认 60s，为进程级全局配置（未参数化到 config.toml，如需可后续登记）
- L2 证据待 VM 运行后回填

## 回滚方式

回滚分支 `fix/day12a-sdk-stability` 即可；无数据库变更，无配置迁移，纯代码回滚安全。

---

**Reviewer 结论**（由 Reviewer 填写）：

- [ ] PASS
- [ ] PASS_WITH_DEBT（需记录技术债 TD 编号）
- [ ] REWORK
- [ ] BLOCKED
