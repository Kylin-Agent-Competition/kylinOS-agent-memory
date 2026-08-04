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
