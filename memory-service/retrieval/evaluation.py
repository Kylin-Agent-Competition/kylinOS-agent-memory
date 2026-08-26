"""V007/D13-B：检索评测指标（Recall@K / MRR / nDCG@K / P95 等）。

纯函数实现，不依赖 numpy / 检索运行时 / 麒麟宿主。

口径来源：evaluation/D3_GOLD_LABEL_AND_METRICS_SPEC_V1.md。
注意：K 值、p95 统计口径、warmup/重复次数等均为 TEAM_DEFINED，未冻结前由
调用方在 EvalConfig 中显式登记实际取值，本模块只计算、不把默认值写成正式契约。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ChannelMode(str, Enum):
    """评测通道：FTS5-only / Vector-only / rrf-v1。"""

    FTS5_ONLY = "fts5"
    VECTOR_ONLY = "vector"
    RRF_V1 = "rrf_v1"


@dataclass(frozen=True)
class EvalConfig:
    """评测配置版本绑定（所有未冻结项显式登记，防止不同配置静默混用）。"""

    channel_mode: ChannelMode
    k: int = 10
    top_k: int = 10
    rrf_k: int = 60
    dataset_version: str = "UNKNOWN"
    gold_label_version: str = "UNKNOWN"
    implementation_commit: str = "UNKNOWN"
    environment: str = "UNKNOWN"
    evidence_reference: str = ""
    statistics_method: str = "p95"  # TEAM_DEFINED：建议 p50 与 p95 同时报告
    warmup_count: int = 0  # TEAM_DEFINED
    repeat_count: int = 1  # TEAM_DEFINED
    concurrency: int = 1  # TEAM_DEFINED：默认单并发
    target_threshold: float = 0.85  # M2 知识检索召回率 OFFICIAL_REQUIREMENT >=85%；E 轨 Gold Label 落地后按配置版本传入

    def __post_init__(self) -> None:
        if self.k <= 0:
            raise ValueError("k 必须为正整数")
        if self.top_k <= 0:
            raise ValueError("top_k 必须为正整数")
        if self.rrf_k <= 0:
            raise ValueError("rrf_k 必须为正整数")
        if self.warmup_count < 0 or self.repeat_count < 1:
            raise ValueError("warmup_count >= 0 且 repeat_count >= 1")
        if not 0.0 <= self.target_threshold <= 1.0:
            raise ValueError("target_threshold 必须在 [0,1]")


@dataclass(frozen=True)
class QueryEvalResult:
    """单条查询的评测输入：排名结果 + Gold Label 正解 + 可选延迟。"""

    query_id: str
    ranked_ids: tuple[str, ...]
    relevant_ids: frozenset[str]
    latency_ms: Optional[float] = None


@dataclass
class QueryMetric:
    """单查询明细，用于 per_query_detail。"""

    query_id: str
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float
    hit: bool
    hit_rank: Optional[int]
    relevant_count: int
    latency_ms: Optional[float]


@dataclass
class EvalReport:
    """聚合后的评测报告（字段对齐 M2/M3 输出要求）。"""

    config: EvalConfig
    query_count: int
    recall_at_k: float
    mean_recall_at_k: float
    mrr: float
    ndcg_at_k: float
    hit_count: int
    target_threshold: float
    k_value: int
    p50_ms: Optional[float]
    p95_ms: Optional[float]
    mean_ms: Optional[float]
    max_ms: Optional[float]
    sample_count: int
    per_query_detail: list[QueryMetric] = field(default_factory=list)
    gold_label_version: str = "UNKNOWN"
    dataset_version: str = "UNKNOWN"
    implementation_commit: str = "UNKNOWN"
    environment: str = "UNKNOWN"
    evidence_reference: str = ""

    @property
    def metric_name(self) -> str:
        return f"knowledge_retrieval_recall_{self.config.channel_mode.value}"


def recall_at_k(relevant_ids: frozenset[str], ranked_ids: tuple[str, ...], k: int) -> float:
    """Recall@K：Top-K 命中的正解数 / 正解总数。正解为空时返回 1.0（无召回目标）。"""
    if k <= 0:
        raise ValueError("k 必须为正整数")
    if not relevant_ids:
        return 1.0
    hits = sum(1 for rid in ranked_ids[:k] if rid in relevant_ids)
    return hits / len(relevant_ids)


def reciprocal_rank(relevant_ids: frozenset[str], ranked_ids: tuple[str, ...]) -> float:
    """MRR 单查询分量：首个命中正解的倒数排名，未命中为 0。"""
    for index, rid in enumerate(ranked_ids, 1):
        if rid in relevant_ids:
            return 1.0 / index
    return 0.0


def _dcg_at_k(relevant_ids: frozenset[str], ranked_ids: tuple[str, ...], k: int) -> float:
    dcg = 0.0
    for index, rid in enumerate(ranked_ids[:k], 1):
        if rid in relevant_ids:
            dcg += 1.0 / math.log2(index + 1)
    return dcg


def ndcg_at_k(relevant_ids: frozenset[str], ranked_ids: tuple[str, ...], k: int) -> float:
    """nDCG@K（二元相关度：命中=1，否则=0）。正解为空时返回 1.0。"""
    if not relevant_ids:
        return 1.0
    dcg = _dcg_at_k(relevant_ids, ranked_ids, k)
    ideal_hits = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def percentile(sorted_values: list[float], p: float) -> float:
    """线性插值百分位（numpy percentile 默认 linear 口径）。空列表抛异常。"""
    if not sorted_values:
        raise ValueError("无法对空列表计算百分位")
    if not 0.0 <= p <= 100.0:
        raise ValueError("p 必须在 [0,100]")
    values = sorted(sorted_values)
    if p == 0.0:
        return values[0]
    if p == 100.0:
        return values[-1]
    rank = (p / 100.0) * (len(values) - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return values[lower]
    weight = rank - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def evaluate_queries(
    queries: list[QueryEvalResult],
    config: EvalConfig,
) -> EvalReport:
    """按 config 聚合查询级结果，输出 Recall@K/MRR/nDCG@K/P50/P95。"""
    details: list[QueryMetric] = []
    recall_sum = 0.0
    mrr_sum = 0.0
    ndcg_sum = 0.0
    hit_count = 0
    latencies: list[float] = []

    for q in queries:
        rec = recall_at_k(q.relevant_ids, q.ranked_ids, config.k)
        rr = reciprocal_rank(q.relevant_ids, q.ranked_ids)
        ndcg = ndcg_at_k(q.relevant_ids, q.ranked_ids, config.k)
        recall_sum += rec
        mrr_sum += rr
        ndcg_sum += ndcg

        hit_rank: Optional[int] = None
        for index, rid in enumerate(q.ranked_ids[: config.k], 1):
            if rid in q.relevant_ids:
                hit_rank = index
                break
        if hit_rank is not None:
            hit_count += 1
        if q.latency_ms is not None:
            latencies.append(q.latency_ms)

        details.append(
            QueryMetric(
                query_id=q.query_id,
                recall_at_k=rec,
                reciprocal_rank=rr,
                ndcg_at_k=ndcg,
                hit=hit_rank is not None,
                hit_rank=hit_rank,
                relevant_count=len(q.relevant_ids),
                latency_ms=q.latency_ms,
            )
        )

    query_count = len(queries)
    mean_recall = recall_sum / query_count if query_count else 0.0
    mean_mrr = mrr_sum / query_count if query_count else 0.0
    mean_ndcg = ndcg_sum / query_count if query_count else 0.0

    return EvalReport(
        config=config,
        query_count=query_count,
        recall_at_k=mean_recall,
        mean_recall_at_k=mean_recall,
        mrr=mean_mrr,
        ndcg_at_k=mean_ndcg,
        hit_count=hit_count,
        target_threshold=config.target_threshold,
        k_value=config.k,
        p50_ms=percentile(latencies, 50.0) if latencies else None,
        p95_ms=percentile(latencies, 95.0) if latencies else None,
        mean_ms=_mean(latencies) if latencies else None,
        max_ms=max(latencies) if latencies else None,
        sample_count=len(latencies),
        per_query_detail=details,
        gold_label_version=config.gold_label_version,
        dataset_version=config.dataset_version,
        implementation_commit=config.implementation_commit,
        environment=config.environment,
        evidence_reference=config.evidence_reference,
    )


def report_to_dict(report: EvalReport) -> dict:
    """把报告转成可序列化 dict（JSON 输出 / 评测记录元数据）。"""
    return {
        "metric_name": report.metric_name,
        "channel_mode": report.config.channel_mode.value,
        "query_count": report.query_count,
        "recall_at_k": report.recall_at_k,
        "mean_recall_at_k": report.mean_recall_at_k,
        "mrr": report.mrr,
        "ndcg_at_k": report.ndcg_at_k,
        "hit_count": report.hit_count,
        "target_threshold": report.target_threshold,
        "k_value": report.k_value,
        "p50_ms": report.p50_ms,
        "p95_ms": report.p95_ms,
        "mean_ms": report.mean_ms,
        "max_ms": report.max_ms,
        "sample_count": report.sample_count,
        "rrf_k": report.config.rrf_k,
        "statistics_method": report.config.statistics_method,
        "warmup_count": report.config.warmup_count,
        "repeat_count": report.config.repeat_count,
        "concurrency": report.config.concurrency,
        "gold_label_version": report.gold_label_version,
        "dataset_version": report.dataset_version,
        "implementation_commit": report.implementation_commit,
        "environment": report.environment,
        "evidence_reference": report.evidence_reference,
        "per_query_detail": [
            {
                "query_id": d.query_id,
                "recall_at_k": d.recall_at_k,
                "reciprocal_rank": d.reciprocal_rank,
                "ndcg_at_k": d.ndcg_at_k,
                "hit": d.hit,
                "hit_rank": d.hit_rank,
                "relevant_count": d.relevant_count,
                "latency_ms": d.latency_ms,
            }
            for d in report.per_query_detail
        ],
    }
