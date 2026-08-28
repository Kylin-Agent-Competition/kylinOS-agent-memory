## 摘要

**PR 标题**：feat(day10): 精准遗忘与删除一致性——缓存失效 + Bridge 安全审计 + 异常恢复测试

**对应任务**：台账 R52（A 轨 D10）

**完成定义**：删除后 Provider 缓存和临时数据不恢复目标正文 ✅

## 背景与目标

用户执行删除操作（遗忘/硬删除）后，Embedding 查询缓存和抽取缓存可能残留已删除数据的向量/候选结果，导致删除后再次查询时仍返回已删除内容。本 PR 确保：
1. 删除事件触发缓存失效，已删除内容无法通过缓存恢复
2. Bridge/SDK/日志均不保留已删除正文
3. 删除过程中异常不丢失删除状态

## 修改范围

1. EmbeddingQueryCache / PreferenceExtractionCache 粒度缓存失效接口
2. CacheInvalidator 缓存失效协调器（幂等/按用户/按事件/全量）
3. EmbeddingService 对接删除事件入口
4. Bridge 安全审计（零正文残留确认）
5. 15 项 D10 测试 + VM 验证

## 明确不修改范围

- 不接通 Outbox 事件总线（自动消费删除事件）——归入 TD-A-D10-CACHE-INVALIDATION
- 不修改 ForgetPlan 领域模型或遗忘执行逻辑（E 轨范畴）
- 不修改 C++ Bridge 代码（仅审计，无代码变更）

## 关联任务与技术债

- 任务卡：`docs/day10/01_task_card.md`
- 技术债：TD-A-D10-CACHE-INVALIDATION（缓存失效粒度与删除事件对齐，当前通过显式调用触发，未全量接通 Outbox）

## 架构与能力边界依据

- D3 §5.5 ForgetPlan 模型（domain/forgetting.py）
- 架构 TABLE 29 延迟预算：Embedding 查询 ≤180ms
- D9 交付物：EmbeddingQueryCache / EmbeddingCoalescer / EmbeddingBacklogTracker

## 修改文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `memory-service/embedding/embedding_cache.py` | 修改 | 增加 `invalidate_by_content(content_hash)` 按内容指纹失效 |
| `memory-service/providers/extraction_provider.py` | 修改 | 增加 `invalidate_by_event(event_id)` / `invalidate_by_content(fingerprint)` |
| `memory-service/embedding/cache_invalidator.py` | **新增** | CacheInvalidator + DeletionEvent 模型 |
| `memory-service/embedding/embedding_service.py` | 修改 | 增加 `handle_deletion_event` / `set_cache_invalidator` |
| `memory-service/tests/test_embedding_d10.py` | **新增** | 15 项 D10 测试 |
| `scripts/verify_day10_vm.sh` | **新增** | VM 验证脚本 |
| `docs/day10/01_task_card.md` | **新增** | D10 任务卡 |
| `docs/day10/02_pr_description.md` | **新增** | 本文件 |
| `docs/technical-debt/TECHNICAL_DEBT_REGISTER.md` | 修改 | 新增 TD-A-D10-CACHE-INVALIDATION |
| `evidence/l2-kylin-vm/day10_verify_latest.log` | **新增** | L2 证据 |

## 数据库与配置变化

无。纯内存缓存失效，不涉及 DB schema 或配置变更。

## 测试结果

### L0 (单元测试 + 静态检查)

```
# D10 专项测试：15/15 passed
# D9 回归测试：18/18 passed
# 协议 + 生命周期：49/49 passed
# 合计：82 passed in 5.22s
```

### L1 (组件集成)

不适用（纯内存模块，无外部依赖集成）。

### 安全与假实现审查

- ✅ C++ Bridge 审计确认：无临时文件、无正文缓存、日志仅固定串+指针地址
- ✅ EmbeddingService 零 logging 调用，`_degrade` 不包含原文
- ✅ SDK 仅缓存模型名（`ensemble-embd_gte-base_uint8-text`，非用户正文）
- ✅ 删除后 Bridge 进入 `session_destroyed_` 终态不可重建
- ✅ 无 Mock 冒充 Runtime、无密钥泄露、无硬编码配置

### L2 麒麟虚拟机证据

```
evidence/l2-kylin-vm/day10_verify_latest.log
82 passed in 5.22s（麒麟 VM 实测，Python 3.12.3，pytest 9.1.1）
```

### L3 (全链路验收)

不适用。

## 性能影响

- 缓存失效操作 O(n) 扫描（n = 缓存条目数），默认容量 512/256，开销可忽略
- 删除事件处理在独立调用路径，不影响正常 embed 路径延迟

## 已知限制

1. CacheInvalidator 当前通过显式 `handle_deletion()` 调用触发，未接通 Outbox 事件总线（TD-A-D10-CACHE-INVALIDATION）
2. 重启后缓存清空，删除状态不持久化（内存缓存，需上层 Outbox/DB 保证持久化）

## 回滚方式

回滚此 PR：`git revert HEAD` 即可。缓存失效功能退化，但 D9 的 embed 缓存仍正常工作（仅删除事件无法触发失效，需重启服务清空缓存）。

---

**Reviewer 结论**（由 Reviewer 填写）：

- [ ] PASS
- [ ] PASS_WITH_DEBT（需记录技术债 TD 编号）
- [ ] REWORK
- [ ] BLOCKED