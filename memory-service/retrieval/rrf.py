"""`rrf-v1` 纯函数（`docs/adr/001-application-layer-rrf.md`）。

只做确定性融合，不依赖 SQLite、FTS5、Vector SDK、Outbox 或任何生产组件。
输入必须已经完成 Provider 结构校验、精确版本去重、SQLite 回源与全部硬过滤。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from retrieval.contracts import Channel, RetrievalHit

RRF_DEFAULT_K = 60


def rrf_terms(
    ranks: Dict[Channel, int], k: int = RRF_DEFAULT_K
) -> Dict[Channel, float]:
    """返回各命中通道的 `1/(k+rank)` 分项。"""
    if k <= 0:
        raise ValueError("k 必须为正整数")
    terms: Dict[Channel, float] = {}
    for channel, rank in ranks.items():
        if rank < 1:
            raise ValueError("rank 必须从 1 开始")
        terms[channel] = 1.0 / (k + rank)
    return terms


def rrf_score(ranks: Dict[Channel, int], k: int = RRF_DEFAULT_K) -> float:
    """返回 `sum(1/(k+rank))`，只统计实际命中通道。"""
    return sum(rrf_terms(ranks, k).values())


def dedupe_exact_version(hits: Iterable[RetrievalHit]) -> List[RetrievalHit]:
    """同一通道内仅对精确 `(memory_id, version_id)` 去重，保留最小 rank。

    rank 相同时按 `(memory_id, version_id)` 稳定选择；本函数不按 `memory_id`
    提前去重，也不做版本校验。
    """
    best: Dict[tuple, RetrievalHit] = {}
    for hit in hits:
        key = (hit.channel, hit.memory_id, hit.version_id)
        current = best.get(key)
        if current is None or hit.rank < current.rank:
            best[key] = hit
        elif hit.rank == current.rank and (hit.memory_id, hit.version_id) < (current.memory_id, current.version_id):
            best[key] = hit
    return list(best.values())


def aggregate_by_memory(hits: Iterable[RetrievalHit]) -> Dict[str, Dict[Channel, int]]:
    """对已通过 SQLite 回源与硬过滤的合法命中按 `memory_id` 聚合。

    每个通道只保留最小合法 rank；不同 `version_id` 的陈旧版本应在调用前移除。
    """
    aggregated: Dict[str, Dict[Channel, int]] = {}
    for hit in hits:
        ranks = aggregated.setdefault(hit.memory_id, {})
        current = ranks.get(hit.channel)
        if current is None or hit.rank < current:
            ranks[hit.channel] = hit.rank
    return aggregated


@dataclass(frozen=True)
class AggregatedCandidate:
    """聚合后的逻辑记忆候选，用于确定性 tie-break 排序。"""

    memory_id: str
    ranks: Dict[Channel, int]

    @property
    def final_score(self) -> float:
        return rrf_score(self.ranks)

    @property
    def channel_count(self) -> int:
        return len(self.ranks)

    @property
    def best_rank(self) -> int:
        return min(self.ranks.values())


def rrf_rank(
    candidates: Iterable[AggregatedCandidate], k: int = RRF_DEFAULT_K
) -> List[AggregatedCandidate]:
    """按 final_score 降序、通道数降序、最佳 rank 升序、memory_id 升序排序。

    显式使用 k 计算 RRF 分数，确保调用方传入的 k 真正生效。
    """
    return sorted(
        candidates,
        key=lambda c: (-rrf_score(c.ranks, k), -c.channel_count, c.best_rank, c.memory_id),
    )
