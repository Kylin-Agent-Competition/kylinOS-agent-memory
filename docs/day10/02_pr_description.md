## 摘要

**PR 标题**：feat(day10): 精准遗忘与删除一致性——缓存失效 + Bridge 安全审计 + 异常恢复测试

**对应任务**：台账 R52（A 轨 D10）

**完成定义**：删除后 Provider 缓存和临时数据不恢复目标正文 ✅

## 变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `memory-service/embedding/embedding_cache.py` | 修改 | 增加 `invalidate_by_content(content_hash)` 按内容指纹失效缓存条目 |
| `memory-service/providers/extraction_provider.py` | 修改 | 增加 `invalidate_by_event(event_id)` / `invalidate_by_content(content_fingerprint)` 粒度失效 |
| `memory-service/embedding/cache_invalidator.py` | **新增** | CacheInvalidator 缓存失效协调器 + DeletionEvent 模型 |
| `memory-service/embedding/embedding_service.py` | 修改 | 对接删除事件，增加 `handle_deletion_event` / `set_cache_invalidator` |
| `memory-service/tests/test_embedding_d10.py` | **新增** | 19 项 D10 测试（缓存失效/删除事件/并发/异常恢复/重启） |
| `scripts/verify_day10_vm.sh` | **新增** | VM 验证脚本 |
| `docs/day10/01_task_card.md` | **新增** | D10 任务卡 |
| `docs/day10/02_pr_description.md` | **新增** | 本文件 |
| `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` | 修改 | 新增 TD-A-D10-CACHE-INVALIDATION |

## 子任务完成情况

### 子任务 1：Embedding/抽取缓存失效接口 ✅

- `EmbeddingQueryCache.invalidate_by_content(content_hash)` — 按原文确定性哈希失效
- `PreferenceExtractionCache.invalidate_by_event(event_id)` — 按事件 ID 失效
- `PreferenceExtractionCache.invalidate_by_content(content_fingerprint)` — 按内容指纹失效
- `CacheInvalidator` — 协调器，接收 `DeletionEvent`，维护用户→事件→指纹映射

### 子任务 2：检查 Bridge 临时文件和日志不保留已删除正文 ✅

**结论**：删除后内容不可恢复。
- C++ Bridge 无文件写入用户内容，零临时文件，日志仅记录固定串+指针地址
- EmbeddingService 零 logging 调用，`_degrade` 不包含原文
- SDK 仅缓存模型名（非用户正文）
- 删除后 Bridge 进入 `session_destroyed_` 终态不可重建

### 子任务 3：删除期间异常恢复测试 ✅

19 项测试全部通过，覆盖：
- 缓存粒度失效（正/反向）
- 删除事件幂等去重 / 按用户失效 / 全量失效
- Provider 异常时删除不丢失
- 删除后新 Provider 不恢复旧数据
- 并发删除与读取无竞态

## 验证

- D10 专项测试：19/19 passed
- D9 回归测试：18/18 passed
- 协议 + 生命周期测试：49/49 passed