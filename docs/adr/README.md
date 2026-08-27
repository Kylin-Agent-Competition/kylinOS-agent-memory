# 架构决策记录 (ADR)

本目录存放项目的架构决策记录 (Architecture Decision Records)。

## ADR 模板

```markdown
# ADR-{编号}: {标题}

- **状态**：{提议 | 已采纳 | 已废弃 | 替代}
- **日期**：YYYY-MM-DD
- **背景**：描述需要做出决策的上下文和问题。
- **候选方案**：
  1. 方案 A — 描述
  2. 方案 B — 描述
  3. 方案 C — 描述
- **决策**：选定的方案及概要。
- **原因**：做出此选择的关键理由。
- **影响**：对架构、开发、测试、部署的影响。
- **回滚方式**：如何撤销此决策或迁移到替代方案。
- **证据**：实验数据、评测结果或推理过程。
```

## 当前状态

| ADR | 状态 | 说明 |
|---|---|---|
| [ADR-001：默认使用 Memory Service 应用层 RRF](001-application-layer-rrf.md) | 提议，PR #20 Review 返工中 | `rrf-v1` 默认 `k=60`、等权、硬过滤先于融合；一名独立非作者 Reviewer 的 `APPROVED` 满足人工审批门槛，D/E 为专业关注点 |
| [ADR-004：Gate 0 真实 Tool Result 路线 B 替代架构批准](004-gate0-tool-result-route-b.md) | 已采纳（2026-08-17 起保留为备份路线） | 独立 Qt 演示壳 + 执行日志 Adapter 作为 Gate 0 Tool Result 验证路径；真实 Hook 端到端未通前不撤销、不降级 |
| [ADR-005：DB 层对外错误码与 envelope 采用 IPC 冻结契约](005-db-error-code-envelope.md) | 已采纳（2026-08-17，Reviewer E 2026-08-20 已签） | 方案 A：对外统一冻结 5 枚举 + `status/data/server_ts` envelope |
| [ADR-006：idempotency_cache 采用复合主键](006-db-idempotency-primary-key.md) | 已采纳（2026-08-17，Reviewer E 2026-08-20 已签） | 方案 A：复合主键 `(user_id, session_id, idempotency_key)` |
| [ADR-007：DB 迁移基线命名](007-db-migration-baseline-naming.md) | 已采纳 | 基线迁移命名裁定 |
| [ADR-008：embedding 子服务方法域独立承认](008-embedding-subservice-method-domain.md) | 已采纳（2026-08-25，Reviewer E 谢嘉然已签） | 方案 A：承认 embedding 子服务方法域，Phase 2 统一 Gateway 合并路由（仅 method routing，不涉 socket 方案） |
| [ADR-009：UDS socket ownership 归属裁决](009-socket-ownership.md) | 已采纳（2026-08-25，Reviewer E 谢嘉然已签） | 方案 A：Memory Service/Gateway owns `memory.sock`；Embedding 子服务 owns 私有 `embedding.sock`；echo 属 Gate 0 验证细节（ALIGN-005） |
| [ADR-010：新增 `turn.finalized` IPC 方法](010-turn-finalized-method.md) | ✅ 已采纳（2026-08-27，D 决策 + Reviewer E 签署） | 方案 A1：FRZ-IPC-007 新增写方法；payload 对齐 C 轨 `TurnFinalizedEvent` 候选契约形成 D 轨 IPC 映射；Upsert 落库 + host/db turn_id 区分 + envelope 唯一真源 + 幂等冲突语义 |
| [ADR-011：新增 nullable trace_id / host_turn_id 列](011-trace-id-columns.md) | ✅ 已采纳（2026-08-27，D 决策 + Reviewer E 签署） | 方案 B1：turns 增 trace_id + host_turn_id（部分唯一索引），memory_entries 增 trace_id；迁移 `20260826_add_trace_id.py`（ADR-007 命名，downgrade 表重建合规） |

**ADR-001 已形成 D3-B 冻结候选；独立审查前不得将状态改为“已采纳”。**

## 文件命名

```
adr/
└── 001-memory-ipc-protocol-selection.md
└── 002-embedding-provider-selection.md
└── ...
```

## 参考

- [ADR GitHub 组织建议](https://adr.github.io/)
- [Michael Nygard 的 ADR 文章](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
