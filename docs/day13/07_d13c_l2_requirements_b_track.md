# D13C L2 麒麟 VM 实测需求 — B 轨（检索轨）

## 背景

C 轨 D13C 已完成 L0 Mock 契约测试（S1-S6）与 L1 Python 评测账本（32 passed）。
L0/L1 均基于 Mock Gateway，**Runtime 结论标为 `UNVERIFIED`**。
L2 麒麟 VM 实测需 B 轨在真实部署环境中提供以下结论，以便 C 轨将会话评测
结论从 `UNVERIFIED` 升级为 `VERIFIED`。

---

## B 轨需提供的 L2 结论清单

### 1. 检索通道可用性结论

| # | 结论项 | 验证方法 | 预期结果 |
|---|---|---|---|
| B-L2-01 | FTS5 全文检索通道在麒麟 VM 可用 | 部署 memory-service 后执行 `memory.retrieve`，观察 `recall_sources` 含 `fts5` | 通道可用，返回非空结果 |
| B-L2-02 | Vector 向量检索通道在麒麟 VM 可用 | 同上，观察 `recall_sources` 含 `vector` | 通道可用，返回非空结果 |
| B-L2-03 | RRF 混合排序在麒麟 VM 可用 | 同上，观察 `recall_sources` 含 `rrf` | 通道可用，返回非空结果 |
| B-L2-04 | 检索延迟在麒麟 VM 可接受 | 记录 `memory.retrieve` 请求-响应延迟 | p50 < 500ms，p95 < 2000ms |

### 2. MemoryContext 组装结论（context.assemble）

| # | 结论项 | 验证方法 | 预期结果 |
|---|---|---|---|
| B-L2-05 | context.assemble 在麒麟 VM 返回合法 MemoryContext | 部署后调用 `context.assemble`，校验响应契约 | `injection_status=success`，`actual_token_count <= token_budget` |
| B-L2-06 | Token 预算校验在麒麟 VM 生效 | 构造超预算请求，观察 `budget_exceeded` | `budget_exceeded=true`，`injection_status=degraded` |
| B-L2-07 | 空结果集不产生伪 Context | 查询无命中条件，观察 `injection_status` | `injection_status=skipped`，`assembledContext` 为空 |

### 3. 跨会话隔离结论

| # | 结论项 | 验证方法 | 预期结果 |
|---|---|---|---|
| B-L2-08 | 跨会话检索结果可区分 | Session A / Session B 分别执行 `memory.retrieve`，对比 `injected_context_text` | A ≠ B，含可区分的 memory_id |
| B-L2-09 | 跨会话无串台 | 连续 5 轮 A→B 切换，每轮验证 `injected_context_text` 不含对方标记 | 5 轮全部通过 |

### 4. 精准遗忘结论（forget.preview / forget.execute）

| # | 结论项 | 验证方法 | 预期结果 |
|---|---|---|---|
| B-L2-10 | Vector 精确删除在麒麟 VM 可用 | 执行 `forget.execute` 后重新检索，验证命中条目已删除 | 残留率 = 0% |
| B-L2-11 | FTS5 精确删除在麒麟 VM 可用 | 同上，FTS5 查询不再返回已遗忘条目 | 残留率 = 0% |
| B-L2-12 | 遗漏删除检测 | `forget.execute` 返回 `executed_count` vs `affected_count` | `executed_count == affected_count`，`forgetHasMissingDeletes=false` |

---

## 输出要求

B 轨需将以上结论归档为 evidence 条目（`evidence/index.yaml`），包含：

- **环境信息**：麒麟 OS 版本、memory-service commit SHA、部署配置
- **测试命令**：可复现的完整命令序列
- **原始日志**：请求/响应 envelope 全文（脱敏后）
- **结论标注**：每项标注 `VERIFIED` / `FAILED` / `BLOCKED`
- **SHA-256 校验**：所有日志/数据文件含递归校验和

C 轨在收到 B 轨 L2 结论后，将更新 D13C 会话评测报告的 `provenance.runtime_status`
从 `UNVERIFIED` 升级为对应结论。
