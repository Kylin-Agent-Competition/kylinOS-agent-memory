# 架构设计

## 当前草案

| 文档 | 状态 | 说明 |
|---|---|---|
| [D1-B-03 应用层 RetrievalCandidate 与 RRF 默认方案草案](d1-b-retrieval-candidate-rrf-draft.md) | 待审查 | D1 调查产物；字段与参数须在 D3 冻结 |

## 当前状态

**目录框架已建立，D1 检索候选草案已加入；总体架构和正式契约尚未冻结。**

## 计划内容

- 总体架构图与模块划分
- 数据流设计（Turn → Hook → MemoryService → SQLite/Vector → Context）
- IPC 协议设计（UDS + 长度前缀 JSON）
- 组件交互时序
