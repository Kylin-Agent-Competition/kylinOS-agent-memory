"""V006/D5-B：FTS5 + Vector 融合编排（回源硬过滤 + rrf-v1 + 统一候选）。

只做编排，不依赖 SDK；输入是已结构化的 RetrievalHit 与回源真值表。
复用 retrieval.rrf 的纯函数完成去重、按 memory 聚合与确定性排序。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from retrieval.contracts import (
    Channel,
    ContentSource,
    ObjectType,
    RetrievalCandidate,
    RetrievalFilter,
    RetrievalHit,
)
from retrieval.rrf import AggregatedCandidate, aggregate_by_memory, dedupe_exact_version, rrf_rank

RRF_DEFAULT_K = 60


@dataclass(frozen=True)
class TruthRecord:
    """SQLite 回源真值行（正文/归属/版本/状态/遗忘/敏感度的最小承载）。"""

    memory_id: str
    version_id: str
    user_id: str
    object_type: ObjectType
    memory_type: Optional[str]
    memory_status: str
    content: str
    sensitivity: str
    conflict_state: str
    scene_id: Optional[str] = None
    scope_terms: Optional[dict[str, list[str]]] = None


def _hard_filter(
    rec: Optional[TruthRecord],
    flt: RetrievalFilter,
) -> bool:
    """融合前硬过滤：回源缺失/跨用户/状态/敏感度/对象类型/未解决冲突均丢弃。"""
    if rec is None:
        return False
    if rec.user_id != flt.user_id:
        return False
    if rec.object_type not in flt.object_types:
        return False
    if flt.allowed_memory_statuses and rec.memory_status not in flt.allowed_memory_statuses:
        return False
    if flt.allowed_sensitivity and rec.sensitivity not in flt.allowed_sensitivity:
        return False
    if flt.memory_types and rec.memory_type not in flt.memory_types:
        return False
    # 未解决冲突硬过滤：不注入上下文（ADR-001 输入边界第 5 步）。
    # conflict_policy 当前默认 exclude_unresolved；其他策略需新增 ADR 后才可放宽。
    if rec.conflict_state == "unresolved":
        return False
    return True


def fuse_retrieval(
    *,
    fts5_hits: list[RetrievalHit],
    vector_hits: list[RetrievalHit],
    truth: dict[tuple[str, str, str], TruthRecord],
    flt: RetrievalFilter,
    k: int = RRF_DEFAULT_K,
    top_k: Optional[int] = None,
) -> list[RetrievalCandidate]:
    """融合 FTS5 与 Vector 命中，回源硬过滤，rrf-v1 融合，返回统一候选。

    - 同一通道按精确 (memory_id, version_id) 去重后取最佳 rank；
    - 回源 truth[(user_id, memory_id, version_id)] 并做硬过滤；
    - 过滤后的合法命中按 memory_id 聚合、RRF 排序；
    - 输出 RetrievalCandidate，rrf_score == final_score（v1 不做业务重排）。
    """
    deduped = dedupe_exact_version(list(fts5_hits) + list(vector_hits))
    legal: list[RetrievalHit] = []
    for hit in deduped:
        rec = truth.get((hit.user_id, hit.memory_id, hit.version_id))
        if _hard_filter(rec, flt):
            legal.append(hit)

    aggregated = aggregate_by_memory(legal)
    agg_candidates = [
        AggregatedCandidate(memory_id=mid, ranks=ranks) for mid, ranks in aggregated.items()
    ]
    ranked = rrf_rank(agg_candidates)
    if top_k is not None:
        ranked = ranked[:top_k]

    out: list[RetrievalCandidate] = []
    for agg in ranked:
        version_id = next(
            h.version_id for h in legal if h.memory_id == agg.memory_id
        )
        rec = truth[(flt.user_id, agg.memory_id, version_id)]
        channels = sorted(agg.ranks.keys())
        out.append(
            RetrievalCandidate(
                memory_id=agg.memory_id,
                version_id=version_id,
                object_type=rec.object_type,
                user_id=rec.user_id,
                memory_type=rec.memory_type,
                memory_status=rec.memory_status,
                scene_id=rec.scene_id,
                scope_terms=rec.scope_terms or {},
                content=rec.content,
                content_source=ContentSource.SQLITE_CURRENT,
                channels=channels,
                ranks={ch.value: rank for ch, rank in agg.ranks.items()},
                raw_scores={
                    ch.value: next(
                        (h.raw_score for h in legal if h.memory_id == agg.memory_id and h.channel is ch),
                        None,
                    )
                    for ch in channels
                },
                score_semantics={
                    ch.value: next(
                        (h.score_semantics for h in legal if h.memory_id == agg.memory_id and h.channel is ch),
                    )
                    for ch in channels
                },
                rrf_score=agg.final_score,
                final_score=agg.final_score,
                sensitivity=rec.sensitivity,
                conflict_state=rec.conflict_state,
                estimated_tokens=max(1, len(rec.content)),
            )
        )
    return out



@dataclass
class RetrievalOutcome:
    """检索结果 + 降级通道说明（服务故障时单路降级不中断整体）。"""

    candidates: list[RetrievalCandidate]
    degraded_channels: dict[str, str] = field(default_factory=dict)

    @property
    def degraded(self) -> bool:
        return bool(self.degraded_channels)


def retrieve_graceful(
    *,
    fts5_search,
    vector_search,
    truth: dict[tuple[str, str, str], TruthRecord],
    flt: RetrievalFilter,
    k: int = RRF_DEFAULT_K,
    top_k: Optional[int] = None,
) -> RetrievalOutcome:
    """执行两路召回并融合；单路故障时降级为空命中的该路，不抛未捕获异常。

    - fts5_search / vector_search 均为无参可调用对象，返回 list[RetrievalHit]。
    - 某路抛出异常时，该路命中记为空，并把错误登记到 degraded_channels。
    - 正常那路命中仍参与融合，保证服务故障时可解释降级而非整体崩溃。
    """
    degraded: dict[str, str] = {}
    try:
        fts5_hits = list(fts5_search())
    except Exception as exc:  # noqa: BLE001 - 编排层统一捕获单路故障
        fts5_hits = []
        degraded["fts5"] = f"{type(exc).__name__}: {exc}"
    try:
        vector_hits = list(vector_search())
    except Exception as exc:  # noqa: BLE001
        vector_hits = []
        degraded["vector"] = f"{type(exc).__name__}: {exc}"

    candidates = fuse_retrieval(
        fts5_hits=fts5_hits,
        vector_hits=vector_hits,
        truth=truth,
        flt=flt,
        k=k,
        top_k=top_k,
    )
    return RetrievalOutcome(candidates=candidates, degraded_channels=degraded)
