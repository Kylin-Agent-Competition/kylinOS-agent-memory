# 架构设计

## 当前草案

| 文档 | 状态 | 说明 |
|---|---|---|
| [D1-B-03 应用层 RetrievalCandidate 与 RRF 默认方案草案](d1-b-retrieval-candidate-rrf-draft.md) | 作者侧完成，待 D 主审 | D1 调查产物；字段与参数须在 D3 冻结 |
| [D2 FTS5 / Vector 统一候选字段样例](d2-retrieval-candidate-unified.md) | D2 样例完成，待 D 主审 | 已结合真实 Vector 用户过滤验证；仍非 D3 冻结契约 |
| [D3-B Vector 检索与索引契约 v1](../day3/08_vector_retrieval_contract_v1.md) | 冻结候选，待 D 主审/E 补审 | 冻结 Provider、候选、索引状态、过滤、删除与重建技术语义 |
| [D3-B 检索契约审查与 D4 测试矩阵](../day3/09_retrieval_contract_review_matrix.md) | 待独立审查 | 登记 30 个 Gate P0 条目、跨轨待决项及 D4/L2 验证队列 |

## 当前状态

**D3-B 检索与索引契约已形成冻结候选；通过 D 主审和 E 补审前不得标记为正式接受。**

## 计划内容

- 总体架构图与模块划分
- 数据流设计（Turn → Hook → MemoryService → SQLite/Vector → Context）
- IPC 协议设计（UDS + 长度前缀 JSON）
- 组件交互时序
