# [D9-A] Embedding 吞吐/查询缓存/积压指标——查询缓存（LRU+维度指纹键）+ 并发合并 + backlog 告警 + 吞吐基线

> 分支：`feat/day9-embedding-throughput`（基于 main @ `5bd2c3e`；本 PR 4 commits：`1704e43` + `469be56` + `687c5b8` + `5214cfa`）

## 背景与目标

Day8（PR #38 已合并）交付知识结构化抽取。Day9 按 75 项台账 **R47**（A 轨 D9：混合检索与索引积压治理——Embedding 吞吐基线）实施 Embedding 查询层面优化，目标为"**取得 Embedding 吞吐基线和可执行积压治理策略**"：

1. **查询缓存**（LRU，键=模型维度+原文确定性哈希，深拷贝防污染，空向量/degraded 不缓存），架构 TABLE 29 "Embedding 查询≤180ms：缓存"
2. **积压指标**（backlog / oldest_pending_age / 告警阈值），架构 TABLE 36 可观测性，health 分项返回
3. **请求合并**（相同文本并发请求共享一次 Provider 调用），后台批量合并候选（SDK 无批量 embed 接口，待 SDK 支持后实现）
4. **吞吐基线**（串行 10.52 req/s，P99=154.73ms 在 180ms 预算内）
5. **TABLE 29 短文本降级策略**（积压告警时超 256 字符文本跳过 embed 返回结构化降级）

## 修改范围

- **`memory-service/embedding/embedding_cache.py`（新增）**：LRU 查询缓存 + 请求合并
  - `EmbeddingQueryCache`：LRU 缓存，键=模型维度+原文确定性哈希（sha256 不经归一化），深拷贝返回，TTL/容量可配，空结果不缓存
  - `EmbeddingCoalescer`：同文本并发请求合并（共享一次 Provider 调用），合并统计+失败传播+悬挂释放
  - `raw_text_hash()`：原文确定性哈希（区分大小写/空白，不串键，与 content_fingerprint 归一化不同）
- **`memory-service/embedding/embedding_metrics.py`（新增）**：积压指标与告警阈值
  - `EmbeddingBacklogTracker`：backlog 队列深度 / oldest_pending_age 最老等待时长 / 告警阈值（backlog_warn=32，oldest_warn=0.2s），线程安全，snapshot 快照
- **`memory-service/embedding/embedding_service.py`（增强）**：
  - `__init__`：新增 `_cache` / `_backlog` / `_coalescer` / `_max_short_text_length`（256）
  - `embed()`：缓存命中→直接返回；请求合并→共享 Provider 调用；短文本降级→积压告警时跳过超长文本
  - `_embed_uncached()`：Provider 调用 + 写缓存 + 合并注册/释放
  - `health()`：新增 backlog 快照+阈值+缓存统计
  - 对外暴露 `cache` / `backlog` / `coalescer` 属性（供评测/诊断页）
- **`memory-service/tests/test_embedding_d9.py`（新增，18 项）**：
  - 缓存：命中/深拷贝/空向量不缓存/维度失效/TTL/容量淘汰/统计（7）
  - 积压：enter/leave/backlog 告警/oldest 告警/阈值暴露（5）
  - 合并：并发合并/失败传播（2）
  - health 扩展：backlog+cache 分项/积压非零观测（2）
  - 吞吐 smoke：benchmark 脚本可运行（1）
  - Review 回归：原文哈希不串键/合并等待计入 backlog/合并失败保留原始错误码（3）
- **`scripts/benchmark_embedding.py`（新增）**：串行/低并发吞吐测量脚本
  - 可复现（固定样本/并发/输出原始数据+JSON 汇总），支持 `--fake` 冒烟模式
  - 每轮生成唯一文本（防缓存命中虚高），并发时吞吐=请求数/墙钟时长
- **`scripts/verify_day9_vm.sh`（新增）**：麒麟 VM 一键验证脚本（Step1 仓库状态 → Step2 venv → Step3 L2 全量 pytest → Step4 吞吐测量 → Step5 证据落盘）
- **`evidence/l2-kylin-vm/day9_verify_latest.log`（新增）**：L2 麒麟 VM 证据（**337 passed**，串行吞吐 10.52 req/s，P99=154.73ms）

### 技术债修复合并（来自 fix/td-a-pure）

本 PR 同时合并了 `fix/td-a-pure` 的 18 commits 技术债修复（commit `687c5b8`），确保 Day9 代码不丢失已有修复：

- **TD-A-005-09**：SDK 缺失降级（`_SdkMissingProvider` + `__init__`/`start()` 构造/启动兜底）
- **TD-A-005-03/05**：`get_dimension()` 无副作用 + `model_info().loaded` 精确化
- **TD-A-005-04**：模型名集中缓存（SDK get_model_list UAF Wontfix）
- **TD-A-005-06**：`_singleton_lock` 并发锁
- **TD-A-D6-LLM-TOOL-INPUT**：Knowledge LLM 输入绑定 ToolResult
- **TD-A-D7-LLM-HANG-DEGRADE**：LLM 挂死恢复（executor 重建）
- **TD-A-D8-CONTRACT-CATEGORY-SYNC**：六类契约同步

## 明确不修改范围

- 不修改 D5 已合并的 `_submit_bridge` 线程池模式（Bridge 调用仍在线程池执行）
- 不修改 D4/5/6/7/8 已合并的 Provider/Pipeline 核心（`embedding_provider.py` 仅修复技术债，不改接口）
- 不修改架构 4.4 冻结 IPC 方法语义
- 不实现"后台批量合并"（SDK 无批量 embed API，当前合并限于同文本并发，待 SDK 支持后实现）

## 关联任务与技术债

- 任务卡：台账 R47（A 轨 D9：混合检索与索引积压治理——Embedding 吞吐基线）
- 关联：B 轨 D9（混合检索/重排）、D 轨 D9（Outbox 重试/Dead Letter/index_sync_lag 指标）
- **TD-A-D9-SDK-MODEL-LIST-UAF**（Medium，新增 Risk）：SDK get_model_list 外部调用 UAF，跟踪 SDK 边界缺陷
- 沿用 Open：TD-A-D6-EXEC-RACE、TD-A-D6-TOOL-PARTIAL、TD-A-D7-CACHE-USER-DIMENSION

## 架构与能力边界依据

- 架构 v1 TABLE 29 延迟预算：Embedding（查询）≤180ms，降级策略=缓存、短文本、服务不可用时仅结构化召回
- 架构 v1 TABLE 36 可观测性：backlog / index_sync_lag 等指标
- 台账 R47：查询缓存 + 后台批量合并候选 + backlog 与 oldest_pending_age 告警阈值 → 吞吐基线 + 积压治理策略

## 修改文件清单

| 文件 | 变更类型 | 摘要 |
|------|----------|------|
| `memory-service/embedding/embedding_cache.py` | 新增 | LRU 查询缓存 + 请求合并 |
| `memory-service/embedding/embedding_metrics.py` | 新增 | 积压指标与告警阈值 |
| `memory-service/embedding/embedding_service.py` | 修改 | 集成缓存/积压/合并/短文本降级 |
| `memory-service/providers/embedding_provider.py` | 修改 | 技术债修复合并 |
| `memory-service/providers/extraction_provider.py` | 修改 | 技术债修复合并 |
| `memory-service/tests/test_embedding_d9.py` | 新增 | 18 项 D9 测试 |
| `memory-service/tests/test_td_a_005_03_05.py` | 新增 | 技术债回归测试 |
| `memory-service/tests/test_td_a_005_09.py` | 新增 | 技术债回归测试 |
| `memory-service/tests/test_td_a_local_batch.py` | 新增 | 技术债回归测试 |
| `scripts/benchmark_embedding.py` | 新增 | 吞吐测量脚本 |
| `scripts/verify_day9_vm.sh` | 新增 | VM 一键验证脚本 |
| `evidence/l2-kylin-vm/day9_verify_latest.log` | 新增 | L2 证据 |
| `evidence/l2-kylin-vm/td_a_005_*.log` | 新增 | 技术债证据（4 项） |
| `docs/day9/02_pr_description.md` | 新增 | 本 PR 描述 |
| `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` | 修改 | 技术债状态同步 |
| `docs/day3/06_provider_contract_v1.md` | 修改 | 契约同步 |
| `docs/day4/08_bridge_provider_skeleton.md` | 修改 | 轮次标注同步 |
| `docs/day8/01_task_card.md` | 修改 | 引用更新 |
| `docs/day8/02_pr_description.md` | 修改 | 引用更新 |
| `.gitignore` | 修改 | 恢复 opencode 配置条目 |

## 数据库与配置变化

无。本 PR 不涉及 SQLite Schema、Migration 或配置变更。

## 测试结果

### L0（单元测试 + 静态检查）

```
python -m py_compile memory-service/embedding/embedding_cache.py \
  memory-service/embedding/embedding_metrics.py \
  memory-service/embedding/embedding_service.py
→ COMPILE OK
```

### L1（组件集成）

```
.venv/bin/python -m pytest memory-service/tests/ -v \
  --ignore=memory-service/tests/test_embedding_service_real.py
→ 290 passed, 39 skipped @ 5214cfa
```

### 安全与假实现审查

- 缓存不存储空向量/degraded 结果（避免缓存放大降级态）
- 深拷贝返回（防止调用方污染缓存数据）
- 合并失败传播保留原始错误码（不吞异常）
- 无 Mock 冒充 Runtime 证据（L2 麒麟 VM 真实 SDK 验证）

### L2 麒麟虚拟机证据

```
cd /mnt/shared && bash scripts/verify_day9_vm.sh
→ 337 passed（evidence/l2-kylin-vm/day9_verify_latest.log）
```

吞吐基线：

| 并发 | 吞吐(req/s) | P50 | P95 | P99 |
|------|------------|-----|-----|-----|
| 1 | 10.52 | 90.31ms | 135.11ms | **154.73ms** |
| 4 | 9.60 | 377ms | 875ms | 1146ms |
| 8 | 9.95 | 734ms | 1397ms | 1857ms |

串行 P99=154.73ms 在架构 TABLE 29 "Embedding 查询≤180ms" 预算内。并发不提升吞吐（SDK 单会话上限 ~14 req/s，TD-A-005-02 已确认串行化等价）。

### L3（全链路验收）

不适用。本 PR 为 A 轨 Embedding 服务层优化，不涉及端到端全链路。

## 性能影响

- 正面：缓存命中减少 Provider 调用（同文本重复请求直接返回），请求合并减少并发 SDK 调用次数，短文本降级保护积压时不被长文本拖慢
- 安全：无新增敏感数据暴露风险

## 已知限制

- "后台批量合并"为候选设计，当前 SDK 无批量 embed 接口，合并限于同文本并发
- 缓存键缺少 user 维度（TD-A-D7-CACHE-USER-DIMENSION 沿用 Open，待事件契约加入可信 user_id 后升级）

## 回滚方式

- 回滚 `5214cfa`（连同其下 3 commits）即恢复 main 基线；新增文件（embedding_cache.py / embedding_metrics.py / test_embedding_d9.py / benchmark_embedding.py / verify_day9_vm.sh）随之移除；`embedding_service.py` 回退后恢复 D5 原逻辑（无缓存/积压/合并）

---

**Reviewer 结论**（由 Reviewer 填写）：

- [ ] PASS
- [ ] PASS_WITH_DEBT（需记录技术债 TD 编号）
- [ ] REWORK
- [ ] BLOCKED