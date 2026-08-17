# ADR-006：idempotency_cache 采用复合主键 (user_id, session_id, idempotency_key)（R-6）

- **状态**：✅ 已采纳（E 决策 2026-08-17，选方案 A；Reviewer：D）
- **日期**：2026-08-17
- **决策人**：周子腾（E）｜**Reviewer**：D（待签）
- **责任轨道**：D（IPC/DB）为主，E 审查
- **决策版本**：`idem-pk-v1`
- **适用范围**：`idempotency_cache` 表主键与幂等 DAO 实现；关联 FRZ-DB-005、FRZ-IPC-005、冻结文档 §2.2.5

## 背景

1. **冻结契约自相矛盾**（`D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md`）：
   - §2.2.5 定义 `idempotency_cache` 主键为**单列 `idempotency_key`**；
   - §3.5 幂等查询使用**三元组** `(user_id, session_id, idempotency_key)`；
   - `D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md` FRZ-IPC-005 同样声明「幂等键作用域为三元组」。
2. **代码证据表明 key 非全局唯一**：`memory-service/pipeline/fingerprint.py:66` 去重键格式为 `user_id:{key}`（接入侧按用户限定生成），即不同用户的 `idempotency_key` 可能相同。
3. **后果**：若按单列 PK 建表，不同用户同 key 直接撞键（唯一约束冲突）；若按复合 PK，与冻结 §2.2.5 单列 PK 表述冲突。需求 v1.3 已按复合 PK 写 DDL，本 ADR 将其正式裁定并回写冻结。

## 候选方案

### 方案 A：复合主键 (user_id, session_id, idempotency_key)（本 ADR 决策）

以三元组为复合主键，天然保证「幂等作用域=单用户单会话」语义。

优点：

- 与 FRZ-IPC-005 三元组作用域一致；
- 跨用户/跨会话同 key 不冲突；
- 幂等查询直接按三元组命中，无需额外索引；
- 符合 `fingerprint.py:66` 的 `user_id:{key}` 现实。

缺点：

- 与冻结 §2.2.5 单列 PK 表述冲突，需回写冻结（本 ADR 即回写动作）。

### 方案 B：idempotency_key 强制全局唯一（UUID v4 全局唯一）

要求客户端保证 `idempotency_key` 全局唯一（如 `UUID4`），主键保持单列。

优点：

- 单列 PK 简洁。

缺点：

- 与「三元组作用域」语义冲突：同一业务键（如用户重试同一操作）需要客户端自行加盐；
- 与 `fingerprint.py` 的 `user_id:{key}` 去重键格式不符，需改代码；
- 跨用户键冲突风险转嫁客户端，不可控。

### 方案 C：单列 PK + 唯一索引 (user_id, session_id, idempotency_key)

表结构复杂化，主键语义混乱。

缺点：主键与业务唯一性不一致，DAO 实现歧义，不推荐。

## 决策

选择方案 A：`idem-pk-v1`。**`idempotency_cache` 采用复合主键 `(user_id, session_id, idempotency_key)`。**

### 表结构（DDL 依据）

```sql
CREATE TABLE idempotency_cache (
    user_id         TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    response        TEXT NOT NULL,   -- 缓存响应 JSON
    created_at      TEXT NOT NULL,   -- ISO 8601
    expires_at      TEXT NOT NULL,   -- ISO 8601，TTL=24h
    PRIMARY KEY (user_id, session_id, idempotency_key)
);
CREATE INDEX idx_idempotency_expires ON idempotency_cache(expires_at);  -- 过期清理（辅助索引）
```

### 幂等语义

- 幂等作用域 = `(user_id, session_id, idempotency_key)` 三元组（与 FRZ-IPC-005 一致）；
- 同三元组重复请求返回首次缓存 `response`（不执行副作用）；
- TTL=24h（`expires_at = created_at + 24h`）；
- 过期清理：Worker 轮询顺带 `DELETE ... WHERE expires_at < now LIMIT 100`（借 `idx_idempotency_expires`）。

### 回写冻结

批准后回写 `D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md` §2.2.5：主键由单列改为复合三元组（标注 ADR-006 依据）。

## 影响

### 架构影响

- 幂等 DAO 的 INSERT/UPSERT 以三元组为键；并发未命中时第二次 INSERT 触发唯一键冲突 → 捕获后回查返回首次响应（需求 v1.3 附录 A）；
- 客户端幂等键生成建议 `UUID4`，但服务端不依赖全局唯一。

### 开发影响

- D4-D 按复合 PK 写基线迁移（`001_initial_schema.py`）与 DAO；
- 并发幂等测试：双请求同时未命中 → 断言副作用仅执行一次（L0 用例）。

### 评测影响

- 幂等验收用例按三元组断言（同 user+session+key 重复 → 单次副作用；跨 user 同 key → 各自独立）。

### 安全影响

- 三元组含 user_id，天然用户隔离；日志不得输出幂等缓存正文（response）。

## 回滚与替代条件

若后续出现性能/存储问题，可经新 ADR 改为「代理键 id + 三元组唯一索引」，但不得在同一 `idem-pk-v1` 标识下静默变更。切换至少需：评估查询模式、补迁移、独立 Reviewer 批准。

## 证据与限制

- `deliverables/D4_DEPLOYMENT_FAILURE_ROUTE_FREEZE_20260807.md` §2.2.5（单列 PK 原文）、§3.5（三元组查询）
- `deliverables/D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817.md` FRZ-IPC-005（三元组作用域）
- `memory-service/pipeline/fingerprint.py:66`（`user_id:{key}` 去重键）
- `deliverables/D4_DB_INITIAL_REQUIREMENTS_20260817.md` §二 FR-DB-001、附录 A（v1.3 已按复合 PK 写）

本 ADR 为文档/契约决策，不新增 Runtime 事实。批准记录：E 决策选方案 A（2026-08-17）；Reviewer D 签署确认后正式生效并回写冻结 §2.2.5（复合主键）。
