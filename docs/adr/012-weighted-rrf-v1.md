# ADR-012：`weighted-rrf/v1` 显式加权融合

- **状态**：提议
- **日期**：2026-08-31
- **相关决策**：[ADR-001：应用层 RRF](001-application-layer-rrf.md)

## 背景

ADR-001 冻结 `rrf-v1` 为 FTS5 与 Vector 等权的默认融合算法。通道权重会改变
最终排序，不能以 `rrf-v1` 的名义静默启用。本 ADR 为显式选择的试验性加权融合
建立独立算法身份、解释字段与评测留痕；它不改变产品默认算法。

## 决策

当且仅当请求显式传入版本固定为 `weighted-rrf/v1` 的策略，并同时提供 FTS5、
Vector 两个有限正权重时，使用下式排序：

```text
rrf_score(d) = Σ 1 / (k + rank_c(d))
final_score(d) = Σ weight_c × 1 / (k + rank_c(d))
```

排序键与 ADR-001 保持一致：`final_score` 降序、命中通道数降序、最佳单路 rank
升序、`memory_id` 升序。`rrf_score` 保留为未加权诊断基线，`final_score` 为本算法
实际排序分数。

每个加权候选的 `explanation` 必须记录：

- `algorithm_version="weighted-rrf/v1"`；
- 通道权重、公式和“分数越高越靠前”的方向；
- 加权前 `rrf_score` 与加权后 `final_score`。

评测配置必须记录 `algorithm_version` 和 `channel_weights`，并使用独立的
`weighted_rrf_v1` 通道模式。没有锁定数据集、Gold Label、Recall@K、MRR、nDCG@K
与 P95 对照证据时，`weighted-rrf/v1` 不得替换 `rrf-v1` 默认值，也不得宣称效果
提升或 D9 全部验收完成。

## 影响与回滚

默认 `rerank_policy=None` 继续使用 ADR-001 的 `rrf-v1`，`rrf_score == final_score`。
加权策略只在显式传入时生效，可通过停止传入该策略立即回退；不涉及原生 Hybrid、
索引、SQLite 真源或硬过滤边界。

## 证据

本 PR 仅提供公式、解释、契约和开发级回归测试；正式开发集/Gold Label/麒麟宿主
证据仍待 E 轨数据与后续 L2 验证，当前没有性能或质量优于默认算法的结论。
