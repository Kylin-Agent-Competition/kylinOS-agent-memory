"""V006/D5-B：FTS5 + Vector 融合编排（回源硬过滤 + rrf-v1 + 统一候选）。

只做编排，不依赖 SDK；输入是已结构化的 RetrievalHit 与回源真值表。
复用 retrieval.rrf 的纯函数完成去重、按 memory 聚合与确定性排序。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from domain.enums import PreferenceScope
from retrieval.contracts import (
    Channel,
    ContentSource,
    KnowledgeIndexMetadata,
    ObjectType,
    RerankPolicy,
    RetrievalCandidate,
    RetrievalFilter,
    RetrievalHit,
)
from retrieval.preference_scope import (
    PREFERENCE_SCOPE_TERM_KEYS,
    PREFERENCE_SCOPE_TERMS_SCHEMA_VERSION,
    preference_scope_terms_match,
)
from retrieval.rrf import (
    AggregatedCandidate,
    aggregate_by_memory,
    dedupe_exact_version,
    rrf_rank,
    rrf_score,
    rrf_terms,
)
from retrieval.validation import validate_retrieval_filter

RRF_DEFAULT_K = 60
TOKEN_ESTIMATOR_VERSION = "character-count/v1"
TOKEN_ESTIMATOR_SEMANTICS = "Unicode code point count; not a model tokenizer"
FILTER_DIAGNOSTICS_POLICY_VERSION = "retrieval-filter-diagnostics/v1"
# 公共 filter_diagnostics 的安全泛化原因码：跨用户命中在普通检索结果中记为
# security_filtered；精确 cross_user 计数仅存在于可信内部 telemetry/debug 边界
# （REWORK #111 MEDIUM-01，方案 A）。
PUBLIC_SECURITY_FILTERED_REASON = "security_filtered"
INTERNAL_CROSS_USER_REASON = "cross_user"


def _final_score(
    ranks: dict[Channel, int],
    k: int,
    rerank_policy: Optional[RerankPolicy],
) -> float:
    if rerank_policy is None:
        return rrf_score(ranks, k)
    return sum(
        term * rerank_policy.channel_weights.get(channel, 1.0)
        for channel, term in rrf_terms(ranks, k).items()
    )


def _rank_aggregated_candidates(
    candidates: list[AggregatedCandidate],
    k: int,
    rerank_policy: Optional[RerankPolicy],
) -> list[AggregatedCandidate]:
    if rerank_policy is None:
        return rrf_rank(candidates, k)
    return sorted(
        candidates,
        key=lambda candidate: (
            -_final_score(candidate.ranks, k, rerank_policy),
            -candidate.channel_count,
            candidate.best_rank,
            candidate.memory_id,
        ),
    )


def _with_rerank_explanation(
    explanation: dict,
    rerank_policy: Optional[RerankPolicy],
    rrf_score_value: float,
    final_score_value: float,
) -> dict:
    if rerank_policy is None:
        return explanation
    return {
        **explanation,
        "algorithm_version": rerank_policy.version,
        "rerank_version": None,
        "weighted_rrf": {
            "policy_version": rerank_policy.version,
            "channel_weights": {
                channel.value: rerank_policy.channel_weights[channel]
                for channel in sorted(Channel)
            },
            "formula": "sum(channel_weight[channel] * 1 / (rrf_k + rank[channel]))",
            "direction": "higher final_score first",
            "rrf_score": rrf_score_value,
            "final_score": final_score_value,
        },
    }


def _validate_query_options(
    *,
    k: int,
    top_k: Optional[int],
    token_budget: Optional[int],
    rerank_policy: Optional[RerankPolicy],
) -> None:
    if type(k) is not int or k <= 0:
        raise ValueError("k 必须是正整数")
    if top_k is not None and (type(top_k) is not int or top_k <= 0):
        raise ValueError("top_k 必须是正整数或 None")
    if token_budget is not None and (
        type(token_budget) is not int or token_budget < 0
    ):
        raise ValueError("token_budget 必须是非负整数或 None")
    if rerank_policy is not None and not isinstance(rerank_policy, RerankPolicy):
        raise ValueError("rerank_policy 必须是 RerankPolicy 或 None")


def _validate_preference_filter(flt: RetrievalFilter) -> None:
    if ObjectType.PREFERENCE in flt.object_types:
        validate_retrieval_filter(flt, PREFERENCE_SCOPE_TERM_KEYS)


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
    is_current: bool = False  # SQLite 当前版本标记；每个 memory_id 唯一一个 True
    scene_id: Optional[str] = None
    scope_terms: Optional[dict[str, list[str]]] = None
    preference_scope: Optional[PreferenceScope] = None
    knowledge: Optional[KnowledgeIndexMetadata] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.preference_scope is not None and not isinstance(
            self.preference_scope, PreferenceScope
        ):
            try:
                object.__setattr__(
                    self,
                    "preference_scope",
                    PreferenceScope(self.preference_scope),
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("preference_scope 必须使用冻结五值") from exc
        for field_name in ("valid_from", "valid_to"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if value.tzinfo is None:
                raise ValueError(f"{field_name} 必须带时区（UTC）")
            object.__setattr__(self, field_name, value.astimezone(timezone.utc))


def _hard_filter_rejection_reason(
    rec: Optional[TruthRecord],
    flt: RetrievalFilter,
) -> Optional[str]:
    """返回硬过滤拒绝原因；``None`` 表示可进入后续 current-version 检查。

    该结果仅用于 D11B 联调诊断的聚合计数：不得携带正文、候选 ID、用户 ID
    或查询内容。原因码稳定且按现有 fail-closed 的检查顺序返回。
    """
    if rec is None:
        return "missing_truth"
    if rec.user_id != flt.user_id:
        return "cross_user"
    if rec.object_type not in flt.object_types:
        return "object_type"
    if flt.allowed_memory_statuses and rec.memory_status not in flt.allowed_memory_statuses:
        return "memory_status"
    if flt.allowed_sensitivity and rec.sensitivity not in flt.allowed_sensitivity:
        return "sensitivity"
    if flt.memory_types and rec.memory_type not in flt.memory_types:
        return "memory_type"
    if rec.object_type is ObjectType.PREFERENCE:
        if rec.scene_id is None:
            if not flt.scene.include_unscoped:
                return "scene"
        elif rec.scene_id not in flt.scene.allowed_scene_ids:
            return "scene"
        if not preference_scope_terms_match(
            preference_scope=rec.preference_scope,
            truth_scope_terms=rec.scope_terms,
            query_scope_terms=flt.scope_terms,
        ):
            return "scope"
        if rec.valid_from is not None and flt.as_of < rec.valid_from:
            return "validity"
        if rec.valid_to is not None and flt.as_of >= rec.valid_to:
            return "validity"
    if rec.object_type is ObjectType.KNOWLEDGE:
        # Knowledge 的结构化真值是 D8-B 的回源边界；缺失时不能让索引命中进入 RRF。
        if rec.knowledge is None:
            return "knowledge_metadata"
        if rec.knowledge.memory_status != rec.memory_status:
            return "knowledge_status_mismatch"
        if flt.knowledge.knowledge_types and (
            rec.knowledge.knowledge_type not in flt.knowledge.knowledge_types
        ):
            return "knowledge_type"
        if flt.knowledge.primary_categories and (
            rec.knowledge.primary_category not in flt.knowledge.primary_categories
        ):
            return "knowledge_category"
        if flt.knowledge.source_event_ids and (
            rec.knowledge.source_event_id not in flt.knowledge.source_event_ids
        ):
            return "knowledge_source_event"
        if (
            flt.knowledge.version_ids
            and rec.version_id not in flt.knowledge.version_ids
        ):
            return "knowledge_version"
        if flt.knowledge.required_relation_ids and (
            not set(flt.knowledge.required_relation_ids).issubset(
                rec.knowledge.relation_ids
            )
        ):
            return "knowledge_relation"
    # 未解决冲突硬过滤：不注入上下文（ADR-001 输入边界第 5 步）。
    # conflict_policy 当前默认 exclude_unresolved；其他策略需新增 ADR 后才可放宽。
    if rec.conflict_state == "unresolved":
        return "unresolved_conflict"
    return None


def _hard_filter(
    rec: Optional[TruthRecord],
    flt: RetrievalFilter,
) -> bool:
    """融合前硬过滤的兼容布尔入口。"""
    return _hard_filter_rejection_reason(rec, flt) is None


def _preference_explanation(
    rec: TruthRecord,
    ranks: dict[Channel, int],
    k: int,
) -> dict:
    return {
        "algorithm_version": "rrf-v1",
        "rrf_k": k,
        "rrf_terms": {
            channel.value: value
            for channel, value in rrf_terms(ranks, k).items()
        },
        "degraded_channels": [],
        "rerank_version": None,
        "hard_filter": {
            "policy_version": "preference-filter/v2",
            "scope_schema_version": PREFERENCE_SCOPE_TERMS_SCHEMA_VERSION,
            "current_version": "passed",
            "validity": "passed",
            "scene": "allowed_scene" if rec.scene_id is not None else "unscoped_included",
            "preference_scope": rec.preference_scope.value,
            "scope": (
                "global"
                if rec.preference_scope is PreferenceScope.GLOBAL
                else "terms_matched"
            ),
        },
    }


def _knowledge_explanation(
    rec: TruthRecord,
    flt: RetrievalFilter,
    ranks: dict[Channel, int],
    k: int,
) -> dict:
    return {
        "algorithm_version": "rrf-v1",
        "rrf_k": k,
        "rrf_terms": {
            channel.value: value
            for channel, value in rrf_terms(ranks, k).items()
        },
        "degraded_channels": [],
        "rerank_version": None,
        "hard_filter": {
            "policy_version": "knowledge-filter/v1",
            "current_version": "passed",
            "knowledge_type": (
                "matched" if flt.knowledge.knowledge_types else "not_requested"
            ),
            "primary_category": (
                "matched" if flt.knowledge.primary_categories else "not_requested"
            ),
            "source": (
                "matched" if flt.knowledge.source_event_ids else "not_requested"
            ),
            "status": (
                "matched" if flt.allowed_memory_statuses else "not_requested"
            ),
            "relations": (
                "matched"
                if flt.knowledge.required_relation_ids
                else "not_requested"
            ),
            "conflict": rec.conflict_state,
        },
    }


def fuse_retrieval(
    *,
    fts5_hits: list[RetrievalHit],
    vector_hits: list[RetrievalHit],
    truth: dict[tuple[str, str, str], TruthRecord],
    flt: RetrievalFilter,
    k: int = RRF_DEFAULT_K,
    top_k: Optional[int] = None,
    token_budget: Optional[int] = None,
    rerank_policy: Optional[RerankPolicy] = None,
) -> list[RetrievalCandidate]:
    """融合 FTS5 与 Vector 命中，回源硬过滤，rrf-v1 融合，返回统一候选。

    - 同一通道按精确 (memory_id, version_id) 去重后取最佳 rank；
    - 回源 truth[(user_id, memory_id, version_id)] 并做硬过滤；
    - 过滤后的合法命中按 memory_id 聚合、RRF 排序；
    - 输出 RetrievalCandidate，rrf_score == final_score（v1 不做业务重排）；
    - 指定 token_budget 时，按最终排序依次保留不超预算的候选。
    """
    candidates, _, _ = _fuse_retrieval_with_diagnostics(
        fts5_hits=fts5_hits,
        vector_hits=vector_hits,
        truth=truth,
        flt=flt,
        k=k,
        top_k=top_k,
        token_budget=token_budget,
        rerank_policy=rerank_policy,
    )
    return candidates


def _fuse_retrieval_with_diagnostics(
    *,
    fts5_hits: list[RetrievalHit],
    vector_hits: list[RetrievalHit],
    truth: dict[tuple[str, str, str], TruthRecord],
    flt: RetrievalFilter,
    k: int,
    top_k: Optional[int],
    token_budget: Optional[int],
    rerank_policy: Optional[RerankPolicy],
) -> tuple[list[RetrievalCandidate], dict[str, object], dict[str, object]]:
    """执行融合并返回预算选择和过滤聚合诊断（均不含正文或标识）。"""
    _validate_preference_filter(flt)
    _validate_query_options(
        k=k,
        top_k=top_k,
        token_budget=token_budget,
        rerank_policy=rerank_policy,
    )

    input_hit_count = len(fts5_hits) + len(vector_hits)
    deduped = dedupe_exact_version(list(fts5_hits) + list(vector_hits))
    dropped_by_reason: dict[str, int] = {}

    def record_drop(reason: str) -> None:
        dropped_by_reason[reason] = dropped_by_reason.get(reason, 0) + 1

    legal: list[RetrievalHit] = []
    for hit in deduped:
        rec = truth.get((hit.user_id, hit.memory_id, hit.version_id))
        rejection_reason = _hard_filter_rejection_reason(rec, flt)
        if rejection_reason is None:
            legal.append(hit)
        else:
            record_drop(rejection_reason)
    hard_filter_passed_hit_count = len(legal)

    # 唯一确定 current version（SQLite 真源）：每个 memory_id 只有 is_current=True 的一个版本。
    # stale version 命中在聚合前移除，避免不同 version 的 rank 混入同一 memory_id（ADR-001 输入边界第 5 步）。
    current_version: dict[tuple[str, str], str] = {}
    current_versions: dict[tuple[str, str], set[str]] = {}
    for (uid, mid, vid), rec in truth.items():
        if rec.is_current:
            current_versions.setdefault((uid, mid), set()).add(vid)
    for key, version_ids in current_versions.items():
        if len(version_ids) == 1:
            current_version[key] = next(iter(version_ids))
    current_legal: list[RetrievalHit] = []
    for hit in legal:
        if current_version.get((hit.user_id, hit.memory_id)) == hit.version_id:
            current_legal.append(hit)
        else:
            record_drop("not_current_version")
    legal = current_legal

    aggregated = aggregate_by_memory(legal)
    agg_candidates = [
        AggregatedCandidate(memory_id=mid, ranks=ranks) for mid, ranks in aggregated.items()
    ]
    ranked = _rank_aggregated_candidates(agg_candidates, k, rerank_policy)

    out: list[RetrievalCandidate] = []
    used_tokens = 0
    skipped_budget_count = 0
    for agg in ranked:
        if top_k is not None and len(out) >= top_k:
            break
        version_id = next(
            h.version_id for h in legal if h.memory_id == agg.memory_id
        )
        rec = truth[(flt.user_id, agg.memory_id, version_id)]
        channels = sorted(agg.ranks.keys())
        rrf_score_value = rrf_score(agg.ranks, k)
        final_score_value = _final_score(agg.ranks, k, rerank_policy)
        estimated_tokens = max(1, len(rec.content))
        next_used_tokens = used_tokens + estimated_tokens
        if token_budget is not None and next_used_tokens > token_budget:
            skipped_budget_count += 1
            continue
        candidate = RetrievalCandidate(
                memory_id=agg.memory_id,
                version_id=version_id,
                object_type=rec.object_type,
                user_id=rec.user_id,
                memory_type=rec.memory_type,
                memory_status=rec.memory_status,
                scene_id=rec.scene_id,
                scope_terms=rec.scope_terms or {},
                knowledge=rec.knowledge,
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
                rrf_score=rrf_score_value,
                final_score=final_score_value,
                sensitivity=rec.sensitivity,
                conflict_state=rec.conflict_state,
                valid_from=rec.valid_from,
                valid_to=rec.valid_to,
                estimated_tokens=estimated_tokens,
                explanation=_with_rerank_explanation(
                    _preference_explanation(rec, agg.ranks, k)
                    if rec.object_type is ObjectType.PREFERENCE
                    else _knowledge_explanation(rec, flt, agg.ranks, k),
                    rerank_policy,
                    rrf_score_value,
                    final_score_value,
                ),
            )
        if token_budget is not None:
            candidate = candidate.model_copy(
                update={
                    "explanation": {
                        **candidate.explanation,
                        "token_budget": {
                            "policy_version": "token-budget/v1",
                            "budget": token_budget,
                            "used": next_used_tokens,
                            "decision": "included",
                            "estimator_version": TOKEN_ESTIMATOR_VERSION,
                            "estimator_semantics": TOKEN_ESTIMATOR_SEMANTICS,
                        },
                    }
                }
            )
        used_tokens = next_used_tokens
        out.append(candidate)
    selection_diagnostics: dict[str, object] = {
        "policy_version": "token-budget/v1",
        "requested_top_k": top_k,
        "token_budget": token_budget,
        "selected_count": len(out),
        "skipped_budget_count": skipped_budget_count,
        "budget_used": used_tokens,
        "budget_remaining": (
            token_budget - used_tokens if token_budget is not None else None
        ),
        "estimator_version": TOKEN_ESTIMATOR_VERSION,
        "estimator_semantics": TOKEN_ESTIMATOR_SEMANTICS,
    }
    filter_diagnostics: dict[str, object] = {
        "policy_version": FILTER_DIAGNOSTICS_POLICY_VERSION,
        "input_hit_count": input_hit_count,
        "deduplicated_hit_count": len(deduped),
        "hard_filter_passed_hit_count": hard_filter_passed_hit_count,
        "current_version_passed_hit_count": len(legal),
        "dropped_by_reason": dict(sorted(dropped_by_reason.items())),
    }
    return out, selection_diagnostics, filter_diagnostics



def _to_public_filter_diagnostics(
    precise: dict[str, object],
) -> dict[str, object]:
    """把内部精确过滤诊断泛化为普通检索 consumer 可见的版本。

    MEDIUM-01（REWORK #111 方案 A）：精确 ``cross_user`` 计数是跨用户存在性
    oracle，普通检索 consumer 可通过 ``cross_user > 0`` 反推召回命中过他人数据，
    因此公共 ``RetrievalOutcome.filter_diagnostics`` 将其泛化为
    ``security_filtered``。精确计数仅保留在可信内部 telemetry/debug 边界
    （``_retrieve_graceful_with_internal_diagnostics``），不进入公共返回。
    """
    dropped_by_reason = dict(precise.get("dropped_by_reason", {}))
    cross_user_count = dropped_by_reason.pop(INTERNAL_CROSS_USER_REASON, 0)
    if cross_user_count:
        dropped_by_reason[PUBLIC_SECURITY_FILTERED_REASON] = (
            dropped_by_reason.get(PUBLIC_SECURITY_FILTERED_REASON, 0)
            + cross_user_count
        )
    return {
        **precise,
        "dropped_by_reason": dict(sorted(dropped_by_reason.items())),
    }


@dataclass
class RetrievalOutcome:
    """检索结果 + 降级通道说明（服务故障时单路降级不中断整体）。

    filter_diagnostics 为普通检索 consumer 可见的聚合过滤诊断：只含计数与泛化
    原因码（如 ``security_filtered``），不含正文、候选标识、用户标识或查询内容；
    精确 ``cross_user`` 等内部原因仅存在于可信内部 telemetry/debug 边界。
    """

    candidates: list[RetrievalCandidate]
    degraded_channels: dict[str, str] = field(default_factory=dict)
    selection_diagnostics: dict[str, object] = field(default_factory=dict)
    filter_diagnostics: dict[str, object] = field(default_factory=dict)

    @property
    def degraded(self) -> bool:
        return bool(self.degraded_channels)


def _retrieve_graceful_impl(
    *,
    fts5_search,
    vector_search,
    truth: dict[tuple[str, str, str], TruthRecord],
    flt: RetrievalFilter,
    k: int,
    top_k: Optional[int],
    token_budget: Optional[int],
    rerank_policy: Optional[RerankPolicy],
) -> tuple[RetrievalOutcome, dict[str, object]]:
    """执行两路召回并融合，返回普通结果与精确内部过滤诊断。

    - fts5_search / vector_search 均为无参可调用对象，返回 list[RetrievalHit]。
    - 某路抛出异常时，该路命中记为空，并把错误登记到 degraded_channels。
    - 正常那路命中仍参与融合，保证服务故障时可解释降级而非整体崩溃。
    - 返回的精确过滤诊断（含 cross_user 计数）仅供可信内部调用方使用；公共
      RetrievalOutcome.filter_diagnostics 已泛化（cross_user → security_filtered）。
    """
    _validate_preference_filter(flt)
    _validate_query_options(
        k=k,
        top_k=top_k,
        token_budget=token_budget,
        rerank_policy=rerank_policy,
    )

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

    candidates, selection_diagnostics, precise_filter_diagnostics = _fuse_retrieval_with_diagnostics(
        fts5_hits=fts5_hits,
        vector_hits=vector_hits,
        truth=truth,
        flt=flt,
        k=k,
        top_k=top_k,
        token_budget=token_budget,
        rerank_policy=rerank_policy,
    )
    degraded_channel_names = sorted(degraded)
    candidates = [
        candidate.model_copy(update={
            "explanation": {
                **candidate.explanation,
                "degraded_channels": degraded_channel_names,
            }
        })
        for candidate in candidates
    ]
    outcome = RetrievalOutcome(
        candidates=candidates,
        degraded_channels=degraded,
        selection_diagnostics=selection_diagnostics,
        filter_diagnostics=_to_public_filter_diagnostics(precise_filter_diagnostics),
    )
    return outcome, precise_filter_diagnostics


def retrieve_graceful(
    *,
    fts5_search,
    vector_search,
    truth: dict[tuple[str, str, str], TruthRecord],
    flt: RetrievalFilter,
    k: int = RRF_DEFAULT_K,
    top_k: Optional[int] = None,
    token_budget: Optional[int] = None,
    rerank_policy: Optional[RerankPolicy] = None,
) -> RetrievalOutcome:
    """执行两路召回并融合；单路故障时降级为空命中的该路，不抛未捕获异常。

    - fts5_search / vector_search 均为无参可调用对象，返回 list[RetrievalHit]。
    - 某路抛出异常时，该路命中记为空，并把错误登记到 degraded_channels。
    - 正常那路命中仍参与融合，保证服务故障时可解释降级而非整体崩溃。
    - filter_diagnostics 为普通检索 consumer 可见的泛化聚合诊断（不含 cross_user
      等内部原因码；跨用户命中记为 security_filtered）。
    """
    outcome, _ = _retrieve_graceful_impl(
        fts5_search=fts5_search,
        vector_search=vector_search,
        truth=truth,
        flt=flt,
        k=k,
        top_k=top_k,
        token_budget=token_budget,
        rerank_policy=rerank_policy,
    )
    return outcome


def _retrieve_graceful_with_internal_diagnostics(
    *,
    fts5_search,
    vector_search,
    truth: dict[tuple[str, str, str], TruthRecord],
    flt: RetrievalFilter,
    k: int = RRF_DEFAULT_K,
    top_k: Optional[int] = None,
    token_budget: Optional[int] = None,
    rerank_policy: Optional[RerankPolicy] = None,
) -> tuple[RetrievalOutcome, dict[str, object]]:
    """可信内部 telemetry/debug 专用入口（internal-only 边界）。

    仅限可信内部 diagnostics/observability 消费者调用：返回的精确过滤诊断
    （含 ``cross_user`` 计数）绝不进入 IPC、C 轨/客户端或用户可观察返回；
    公共 ``RetrievalOutcome.filter_diagnostics`` 仍为泛化版本（cross_user →
    security_filtered）。
    """
    return _retrieve_graceful_impl(
        fts5_search=fts5_search,
        vector_search=vector_search,
        truth=truth,
        flt=flt,
        k=k,
        top_k=top_k,
        token_budget=token_budget,
        rerank_policy=rerank_policy,
    )
