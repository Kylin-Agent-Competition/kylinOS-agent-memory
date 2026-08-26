# [D10-A] 精准遗忘与删除一致性——缓存失效协调器 + 删除事件集成

> 分支：`feat/day10-forgetting-deletion`（基于 main @ `03857eb`，PR #48 已合并）

## 背景与目标

Day9（PR #48 已合并）交付 Embedding 查询缓存/积压指标/请求合并。D10 按 75 项台账 **R52**（A 轨 D10：精准遗忘与删除一致性）实施删除事件→缓存失效的完整闭环，目标为"**删除后 Provider 缓存和临时数据不恢复目标正文**"：

1. **缓存失效接口**：EmbeddingQueryCache 按内容指纹失效 + PreferenceExtractionCache 按事件 ID / 按内容指纹失效
2. **CacheInvalidator 协调器**：接收删除事件（DeletionEvent），按事件/按用户/全量粒度失效 Embedding 与抽取缓存
3. **Bridge 正文残留检查**：确认 cpp-bridge 无临时文件缓存、无日志正文泄露
4. **删除期间异常恢复**：Provider 异常、并发删除、重启后删除状态均不恢复已删除数据

## 修改范围

- **`memory-service/embedding/cache_invalidator.py`（新增）**：缓存失效协调器
  - `DeletionEvent` 数据类：event_id / user_id / target_type / content_hashes / content_fingerprints / forget_mode / timestamp
  - `CacheInvalidator`：handle_deletion（幂等去重）/ invalidate_by_user（用户级）/ invalidate_all（全量）/ stats 统计
  - 线程安全（锁保护）、事件→指纹映射、用户→事件映射
- **`memory-service/embedding/embedding_cache.py`（增强）**：
  - `EmbeddingQueryCache.invalidate_by_content(content_hash)`：按内容哈希失效缓存条目
- **`memory-service/providers/extraction_provider.py`（增强）**：
  - `PreferenceExtractionCache.invalidate_by_event(event_id)`：按事件 ID 失效缓存条目
  - `PreferenceExtractionCache.invalidate_by_content(content_fingerprint)`：按内容指纹失效缓存条目
- **`memory-service/embedding/embedding_service.py`（增强）**：
  - `set_cache_invalidator(extraction_cache)`：设置缓存失效协调器
  - `handle_deletion_event(event)`：删除事件处理入口
  - `health()`：新增 cache_invalidator 统计分项
  - 导入 `CacheInvalidator` / `DeletionEvent`
- **`memory-service/tests/test_embedding_d10.py`（新增，15 项）**：
  - Embedding 缓存按内容指纹失效（2 项）
  - Extraction 缓存按事件 ID / 内容指纹失效（2 项）
  - CacheInvalidator 删除事件处理（幂等/按用户/全量/统计）（4 项）
  - 删除期间异常恢复（Provider 异常不丢失/新实例不恢复）（2 项）
  - 并发删除与读取无竞态数据恢复（1 项）
  - EmbeddingService 对接删除事件入口（3 项）
  - health 含 invalidator 统计（1 项）
- **`scripts/verify_day10_vm.sh`（新增）**：麒麟 VM 一键验证脚本
  - D10 专项测试 → D9 回归 → L2 全量 pytest → Bridge 日志正文残留检查 → 汇总

## 明确不修改范围

- 不修改 cpp-bridge 代码（检查确认无正文缓存/日志残留）
- 不修改 D5/6/7/8/9 已合并的 Provider/Pipeline 核心接口
- 不修改架构 4.4 冻结 IPC 方法语义
- 不实现删除事件持久化（由上层 Outbox/DB 保证；本模块仅负责内存缓存失效）

## 关联任务与技术债

- 任务卡：台账 R52（A 轨 D10：精准遗忘与删除一致性）
- 新建 **TD-A-D10-CACHE-INVALIDATION**（Medium）：缓存失效粒度与删除事件对齐——当前支持按内容指纹/按事件 ID/按用户失效，但无按时间范围批量失效

## 架构与能力边界依据

- 台账 R52：删除后 Provider 缓存和临时数据不恢复目标正文
- 安全：删除后缓存不应恢复已删除内容（缓存失效为最后防线）

## 修改文件清单

| 文件 | 变更类型 | 摘要 |
|------|----------|------|
| `memory-service/embedding/cache_invalidator.py` | 新增 | 缓存失效协调器（DeletionEvent + CacheInvalidator） |
| `memory-service/embedding/embedding_cache.py` | 修改 | 新增 invalidate_by_content |
| `memory-service/providers/extraction_provider.py` | 修改 | 新增 invalidate_by_event / invalidate_by_content |
| `memory-service/embedding/embedding_service.py` | 修改 | 新增 set_cache_invalidator / handle_deletion_event |
| `memory-service/tests/test_embedding_d10.py` | 新增 | 15 项 D10 测试 |
| `scripts/verify_day10_vm.sh` | 新增 | VM 一键验证脚本 |
| `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` | 修改 | 新增 TD-A-D10-CACHE-INVALIDATION |
| `docs/day10/02_pr_description_a.md` | 新增 | 本 PR 描述 |

## 测试结果

### L0（单元测试 + 静态检查）

```
python -m py_compile memory-service/embedding/cache_invalidator.py \
  memory-service/embedding/embedding_cache.py \
  memory-service/providers/extraction_provider.py \
  memory-service/embedding/embedding_service.py
→ COMPILE OK
```

### L1（组件集成）

```
.venv/bin/python -m pytest memory-service/tests/test_embedding_d10.py -v
→ 15 passed
.venv/bin/python -m pytest memory-service/tests/test_embedding_d9.py -v
→ 18 passed（D9 回归不变）
```

### Bridge 正文残留检查（静态分析）

- cpp-bridge 无临时文件创建（`/tmp` 路径仅用于测试假 .so 路径）
- 无文件缓存（仅 `cached_model_name_` 内存缓存模型名，不存正文）
- 无日志文件写入（仅 `std::fprintf(stderr, ...)` 输出指针地址，不含正文）
- SDK session 重建不恢复已删除数据（缓存失效后无缓存命中）

## 已知限制

- 缓存失效为内存级，重启后缓存自动清空（删除状态由上层 Outbox/DB 持久化）
- 不支持按时间范围批量失效（TD-A-D10-CACHE-INVALIDATION 登记）

## 回滚方式

- 回滚本分支即恢复 main 基线；新增文件（cache_invalidator.py / test_embedding_d10.py / verify_day10_vm.sh / 02_pr_description_a.md）随之移除；修改的现有文件回退后恢复原逻辑

---

**Reviewer 结论**（由 Reviewer 填写）：

- [ ] PASS
- [ ] PASS_WITH_DEBT（需记录技术债 TD 编号）
- [ ] REWORK
- [ ] BLOCKED