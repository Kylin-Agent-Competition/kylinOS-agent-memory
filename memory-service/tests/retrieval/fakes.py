"""L1_FAKE 测试替身：FakeClock、FakeVectorProvider 与回源过滤 helper。

这些替身只用于契约逻辑测试，不代表麒麟宿主行为。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from retrieval.contracts import (
    ActivationMode,
    Availability,
    Channel,
    EvidenceLevel,
    IndexState,
    IndexScope,
    IndexStateRequest,
    IndexStatus,
    ObjectType,
    ProviderResult,
    RetrievalError,
    RetrievalErrorCode,
    RetrievalHit,
    ScopeAuthorization,
    ScoreSemantics,
    VectorCapabilities,
    VectorDeleteRequest,
    VectorDeleteResult,
    VectorRebuildRequest,
    VectorRebuildResult,
    VectorRecord,
    VectorSearchRequest,
    VectorSearchResult,
    VectorUpsertRequest,
    VectorUpsertResult,
    VectorUpsertRejection,
    VectorDeleteRejection,
    Watermark,
    digest_from_canonical,
)
from retrieval.provider import VectorProvider
from retrieval.rrf import dedupe_exact_version

DEFAULT_NOW = datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, now: datetime = DEFAULT_NOW) -> None:
        self.now = now

    def advance(self, seconds: int) -> None:
        self.now = self.now.replace(second=(self.now.second + seconds) % 60)


@dataclass(frozen=True)
class FakeGenerationBuild:
    """Fake SQLite snapshot streamed into one target generation."""

    source_watermark: Watermark
    record_values: tuple[Any, ...] = ()
    record_digests: tuple[str, ...] = ()
    expected_record_count: Optional[int] = None
    rejected_count: int = 0
    rejection_reasons: tuple[str, ...] = ()

    @property
    def read_count(self) -> int:
        return self.expected_record_count if self.expected_record_count is not None else len(self.record_digests)


def _err(code: RetrievalErrorCode, message: str, *, retryable: bool = False, stage: str = "provider") -> RetrievalError:
    return RetrievalError(code=code, message=message, retryable=retryable, stage=stage, provider="fake_vector")


class FakeVectorProvider(VectorProvider):
    def __init__(
        self,
        *,
        dimension: int = 768,
        clock: Optional[FakeClock] = None,
        supports_atomic: bool = False,
        cancel_check: Optional[Callable[[], bool]] = None,
        backend_failure: Optional[Exception] = None,
        digest_keys: Optional[dict[str, bytes]] = None,
        generation_builds: Optional[dict[str | tuple[str, str], FakeGenerationBuild]] = None,
        truth_owners: Optional[dict[str, str]] = None,
    ) -> None:
        self.dimension = dimension
        self.clock = clock or FakeClock()
        self.supports_atomic = supports_atomic
        self.cancel_check = cancel_check
        self.backend_failure = backend_failure
        self.digest_keys = digest_keys
        self.generation_builds = generation_builds or {}
        self.truth_owners = truth_owners or {}

        self.index: Dict[tuple[str, str], dict] = {}  # (user_id, memory_id) -> {record, rank}
        self.idempotency: Dict[tuple, Dict[str, Any]] = {}
        self.serving: Dict[str, str] = {}
        self.applied: Dict[str, Watermark] = {}
        self.record_counts: Dict[str, int] = {}
        self.source_snapshots: Dict[str, str] = {}
        self.last_success: Dict[str, datetime] = {}
        self.generation_states: Dict[tuple[str, str], dict[str, Any]] = {}
        self._order: list[tuple[str, str]] = []
        self.write_effect_count = 0

    # ── helpers ──
    def _ok(self, value: Any, request_id: str, *, partial: bool = False) -> ProviderResult:
        return ProviderResult(
            ok=True,
            value=value,
            provider="fake_vector",
            request_id=request_id,
            elapsed_ms=0,
            completed_at=self.clock.now,
            partial=partial,
        )

    def _fail(self, code: RetrievalErrorCode, request_id: str, message: str) -> ProviderResult:
        return ProviderResult(
            ok=False,
            error=_err(code, message),
            provider="fake_vector",
            request_id=request_id,
            elapsed_ms=0,
            completed_at=self.clock.now,
        )

    def _deadline_expired(self, deadline_at: datetime) -> bool:
        return self.clock.now >= deadline_at

    def _cancelled(self) -> bool:
        return bool(self.cancel_check and self.cancel_check())

    @staticmethod
    def _digest_key_id(digest: str) -> str:
        return digest.split(":", 2)[1]

    @staticmethod
    def _semantic_payload(request: Any) -> dict[str, Any]:
        return request.model_dump(
            mode="json",
            exclude={"request_id", "trace_id", "deadline_at", "payload_hash"},
        )

    def capabilities(self) -> VectorCapabilities:
        return VectorCapabilities(
            provider="fake_vector",
            provider_version="0",
            dimension=self.dimension,
            score_semantics=ScoreSemantics.SDK_SCORE_UNVERIFIED,
            supports_scalar_filter=True,
            supports_delete=True,
            supports_rebuild=True,
            supports_atomic_generation_switch=self.supports_atomic,
            evidence_level=EvidenceLevel.UNTESTED,
            availability=Availability.AVAILABLE,
            availability_checked_at=self.clock.now,
        )

    def _check_backend(self) -> Optional[ProviderResult]:
        if self.backend_failure is not None:
            return self._fail(RetrievalErrorCode.PROVIDER_UNAVAILABLE, "backend", "provider unavailable")
        return None

    def _check_watermark(self, request_id: str, source: Watermark, scope_id: str) -> Optional[ProviderResult]:
        current = self.applied.get(scope_id)
        if current is None:
            return None
        try:
            cmp = source.compare(current)
        except ValueError:
            return self._fail(RetrievalErrorCode.INVALID_ARGUMENT, request_id, "cross-domain watermark")
        if cmp < 0:
            return self._fail(RetrievalErrorCode.STALE_INDEX, request_id, "stale watermark")
        return None

    # ── upsert ──
    def upsert(self, request: VectorUpsertRequest) -> ProviderResult[VectorUpsertResult]:
        if self._deadline_expired(request.deadline_at):
            return self._fail(RetrievalErrorCode.DEADLINE_EXCEEDED, request.request_id, "deadline")
        if self._cancelled():
            return self._fail(RetrievalErrorCode.CANCELLED, request.request_id, "cancelled")

        composite = (request.user_id, "upsert", "fake_vector", request.index_generation, request.idempotency_key)
        semantic_payload = self._semantic_payload(request)
        if self.digest_keys is not None:
            request_key_id = self._digest_key_id(request.payload_hash)
            request_key = self.digest_keys.get(request_key_id)
            if request_key is None:
                return self._fail(
                    RetrievalErrorCode.DIGEST_KEY_UNAVAILABLE,
                    request.request_id,
                    "request digest key unavailable",
                )
            if digest_from_canonical(request_key_id, request_key, semantic_payload) != request.payload_hash:
                return self._fail(RetrievalErrorCode.CONFLICT, request.request_id, "payload digest mismatch")

        existing = self.idempotency.get(composite)
        if existing is not None:
            if existing["payload_hash"] == request.payload_hash:
                return self._ok(existing["result"], request.request_id)
            old_key_id = self._digest_key_id(existing["payload_hash"])
            new_key_id = self._digest_key_id(request.payload_hash)
            if old_key_id != new_key_id and self.digest_keys is not None:
                old_key = self.digest_keys.get(old_key_id)
                if old_key is None:
                    return self._fail(
                        RetrievalErrorCode.DIGEST_KEY_UNAVAILABLE,
                        request.request_id,
                        "historical digest key unavailable",
                    )
                historical_digest = digest_from_canonical(old_key_id, old_key, semantic_payload)
                if existing["payload_hash"] == historical_digest:
                    return self._ok(existing["result"], request.request_id)
            return self._fail(RetrievalErrorCode.CONFLICT, request.request_id, "payload conflict")

        wm = self._check_watermark(request.request_id, request.source_watermark, request.user_id)
        if wm is not None:
            return wm

        rejections: list[VectorUpsertRejection] = []
        accepted: list[VectorRecord] = []
        for record in request.records:
            if record.user_id != request.user_id:
                rejections.append(VectorUpsertRejection(memory_id=record.memory_id, reason="user_scope_violation"))
                continue
            if len(record.vector) != self.dimension:
                rejections.append(VectorUpsertRejection(memory_id=record.memory_id, reason="dimension_mismatch"))
                continue
            accepted.append(record)

        for record in accepted:
            self.index[(record.user_id, record.memory_id)] = {"record": record, "rank": 0}
            if (record.user_id, record.memory_id) not in self._order:
                self._order.append((record.user_id, record.memory_id))

        if accepted:
            self.write_effect_count += 1

        self.applied[request.user_id] = request.source_watermark
        result = VectorUpsertResult(
            accepted_count=len(accepted),
            upserted_count=len(accepted),
            unchanged_count=0,
            rejected=rejections,
            index_generation=request.index_generation,
            applied_watermark=request.source_watermark,
            outcome="partial" if rejections else "applied",
        )
        self.idempotency[composite] = {
            "payload_hash": request.payload_hash,
            "result": result,
        }
        return self._ok(result, request.request_id)

    # ── search ──
    def search(self, request: VectorSearchRequest) -> ProviderResult[VectorSearchResult]:
        if self._deadline_expired(request.deadline_at):
            return self._fail(RetrievalErrorCode.DEADLINE_EXCEEDED, request.request_id, "deadline")
        if self._cancelled():
            return self._fail(RetrievalErrorCode.CANCELLED, request.request_id, "cancelled")
        if request.filter.user_id != request.user_id:
            return self._fail(RetrievalErrorCode.USER_SCOPE_VIOLATION, request.request_id, "filter user mismatch")
        if len(request.query_vector) != self.dimension:
            return self._fail(RetrievalErrorCode.DIMENSION_MISMATCH, request.request_id, "dimension")
        backend = self._check_backend()
        if backend is not None:
            return backend

        hits: list[RetrievalHit] = []
        rank = 0
        for (user_id, memory_id) in self._order:
            if user_id != request.user_id:
                continue
            rank += 1
            entry = self.index[(user_id, memory_id)]
            record: VectorRecord = entry["record"]
            hits.append(
                RetrievalHit(
                    memory_id=memory_id,
                    version_id=record.version_id,
                    user_id=user_id,
                    channel=Channel.VECTOR,
                    rank=rank,
                    raw_score=0.9 - rank * 0.01,
                    score_semantics=ScoreSemantics.SDK_SCORE_UNVERIFIED,
                    provider="fake_vector",
                    index_generation=request.required_generation or self.serving.get(user_id),
                    retrieved_at=self.clock.now,
                    filter_fingerprint="hmac-sha256:k1:" + "c" * 64,
                )
            )
        return self._ok(
            VectorSearchResult(
                hits=hits,
                raw_hit_count=len(hits),
                valid_hit_count=len(hits),
                dropped_hit_count=0,
                filter_fingerprint="hmac-sha256:k1:" + "d" * 64,
            ),
            request.request_id,
        )

    # ── delete ──
    def delete(self, request: VectorDeleteRequest) -> ProviderResult[VectorDeleteResult]:
        if self._deadline_expired(request.deadline_at):
            return self._fail(RetrievalErrorCode.DEADLINE_EXCEEDED, request.request_id, "deadline")
        if self._cancelled():
            return self._fail(RetrievalErrorCode.CANCELLED, request.request_id, "cancelled")
        if request.selector.user_id != request.user_id:
            return self._fail(RetrievalErrorCode.USER_SCOPE_VIOLATION, request.request_id, "selector user mismatch")
        if request.selector.selection_mode == "full_reset":
            if not request.authorization_ref or not request.selector.confirmation_ref:
                return self._fail(RetrievalErrorCode.INVALID_ARGUMENT, request.request_id, "full_reset gate")

        for memory_id in request.selector.memory_ids:
            if memory_id in ("", "*") or not memory_id.strip():
                return self._fail(RetrievalErrorCode.INVALID_ARGUMENT, request.request_id, "wildcard/empty selector")

        composite = (request.user_id, "delete", "fake_vector", request.index_generation, request.idempotency_key)
        existing = self.idempotency.get(composite)
        if existing is not None:
            if existing["payload_hash"] == request.payload_hash:
                return self._ok(existing["result"], request.request_id)
            return self._fail(RetrievalErrorCode.CONFLICT, request.request_id, "payload conflict")

        matched: list[str] = []
        not_matched: list[str] = []
        rejected: list[VectorDeleteRejection] = []
        for memory_id in request.selector.memory_ids:
            truth_owner = self.truth_owners.get(memory_id)
            if truth_owner is not None and truth_owner != request.user_id:
                rejected.append(VectorDeleteRejection(memory_id=memory_id, reason="user_scope_violation"))
                continue
            if memory_id == "*" or memory_id == "":
                not_matched.append(memory_id)
                continue
            if (request.user_id, memory_id) in self.index:
                matched.append(memory_id)
                del self.index[(request.user_id, memory_id)]
            else:
                not_matched.append(memory_id)

        if matched:
            self.write_effect_count += 1

        result = VectorDeleteResult(
            matched_count=len(matched),
            deleted_count=len(matched),
            not_matched_ids=not_matched,
            rejected=rejected,
            index_generation=request.index_generation,
            applied_watermark=request.source_watermark,
            outcome="partial" if rejected else ("applied" if matched else "no_op"),
        )
        self.idempotency[composite] = {"payload_hash": request.payload_hash, "result": result}
        return self._ok(result, request.request_id)

    # ── rebuild ──
    def rebuild(self, request: VectorRebuildRequest) -> ProviderResult[VectorRebuildResult]:
        if self._deadline_expired(request.deadline_at):
            return self._fail(RetrievalErrorCode.DEADLINE_EXCEEDED, request.request_id, "deadline")
        auth = request.scope_authorization
        if auth.scope_id != request.scope.scope_id:
            return self._fail(RetrievalErrorCode.AUTHORIZATION_DENIED, request.request_id, "scope mismatch")
        if "rebuild" not in auth.allowed_operations:
            return self._fail(RetrievalErrorCode.AUTHORIZATION_DENIED, request.request_id, "op denied")
        if self.clock.now >= auth.expires_at:
            return self._fail(RetrievalErrorCode.AUTHORIZATION_EXPIRED, request.request_id, "expired")
        if request.target_generation == self.serving.get(request.scope.scope_id):
            return self._fail(RetrievalErrorCode.CONFLICT, request.request_id, "target equals serving")
        old = self.serving.get(request.scope.scope_id)
        build = self.generation_builds.get((request.scope.scope_id, request.target_generation))
        if build is None:
            build = self.generation_builds.get(request.target_generation)
        if build is None:
            build = FakeGenerationBuild(source_watermark=request.source_watermark)
        generation_key = (request.scope.scope_id, request.target_generation)
        generation_state = {
            "digest_key_id": None,
            "read_count": build.read_count,
            "indexed_count": len(build.record_digests),
            "rejected_count": build.rejected_count,
            "verified": False,
            "activated": False,
        }
        self.generation_states[generation_key] = generation_state

        # 模拟构建失败由 backend_failure 注入
        if self.backend_failure is not None:
            return self._ok(
                VectorRebuildResult(
                    scope=request.scope,
                    target_generation=request.target_generation,
                    source_snapshot_id=request.source_snapshot_id,
                    source_watermark=request.source_watermark,
                    read_count=0,
                    indexed_count=0,
                    rejected_count=0,
                    verified=False,
                    activated=False,
                    activation_mode=ActivationMode.ROUTING_SWITCH,
                    previous_generation=old,
                    outcome="outcome_unknown",
                ),
                request.request_id,
            )

        try:
            watermark_matches = build.source_watermark.compare(request.source_watermark) == 0
        except ValueError:
            watermark_matches = False
        if not watermark_matches:
            return self._fail(RetrievalErrorCode.STALE_INDEX, request.request_id, "snapshot watermark mismatch")

        if build.read_count != len(build.record_digests) or build.rejected_count:
            return self._fail(RetrievalErrorCode.STALE_INDEX, request.request_id, "generation record validation failed")
        if self.digest_keys is not None and len(build.record_values) != len(build.record_digests):
            return self._fail(RetrievalErrorCode.STALE_INDEX, request.request_id, "generation record/digest count mismatch")

        digest_key_ids = {self._digest_key_id(digest) for digest in build.record_digests}
        if len(digest_key_ids) > 1:
            return self._fail(RetrievalErrorCode.CONFLICT, request.request_id, "generation mixes digest key ids")
        if digest_key_ids:
            digest_key_id = next(iter(digest_key_ids))
            generation_state["digest_key_id"] = digest_key_id
            if self.digest_keys is not None:
                digest_key = self.digest_keys.get(digest_key_id)
                if digest_key is None:
                    return self._fail(
                        RetrievalErrorCode.DIGEST_KEY_UNAVAILABLE,
                        request.request_id,
                        "generation digest key unavailable",
                    )
                for value, digest in zip(build.record_values, build.record_digests):
                    if digest_from_canonical(digest_key_id, digest_key, value) != digest:
                        return self._fail(
                            RetrievalErrorCode.CONFLICT,
                            request.request_id,
                            "generation record digest mismatch",
                        )

        self.serving[request.scope.scope_id] = request.target_generation
        self.applied[request.scope.scope_id] = request.source_watermark
        self.record_counts[request.scope.scope_id] = len(build.record_digests)
        self.source_snapshots[request.scope.scope_id] = request.source_snapshot_id
        self.last_success[request.scope.scope_id] = self.clock.now
        generation_state["verified"] = True
        generation_state["activated"] = True
        return self._ok(
            VectorRebuildResult(
                scope=request.scope,
                target_generation=request.target_generation,
                source_snapshot_id=request.source_snapshot_id,
                source_watermark=request.source_watermark,
                read_count=build.read_count,
                indexed_count=len(build.record_digests),
                rejected_count=build.rejected_count,
                rejection_reasons=list(build.rejection_reasons),
                verified=True,
                activated=True,
                activation_mode=ActivationMode.ROUTING_SWITCH,
                previous_generation=old,
                outcome="applied",
            ),
            request.request_id,
        )

    # ── get_index_state ──
    def get_index_state(self, request: IndexStateRequest) -> ProviderResult[IndexState]:
        if self._deadline_expired(request.deadline_at):
            return self._fail(RetrievalErrorCode.DEADLINE_EXCEEDED, request.request_id, "deadline")
        auth = request.scope_authorization
        if auth.scope_id != request.scope.scope_id:
            return self._fail(RetrievalErrorCode.AUTHORIZATION_DENIED, request.request_id, "scope mismatch")
        if "get_index_state" not in auth.allowed_operations:
            return self._fail(RetrievalErrorCode.AUTHORIZATION_DENIED, request.request_id, "op denied")
        if self.clock.now >= auth.expires_at:
            return self._fail(RetrievalErrorCode.AUTHORIZATION_EXPIRED, request.request_id, "expired")

        scope = request.scope
        serving = self.serving.get(scope.scope_id)
        if serving is None:
            state = IndexState(
                provider="fake_vector",
                scope=scope,
                status=IndexStatus.EMPTY,
                is_queryable=True,
                schema_version="v1",
                record_count=0,
                last_checked_at=self.clock.now,
                evidence_level=EvidenceLevel.UNTESTED,
                availability=Availability.AVAILABLE,
            )
        else:
            state = IndexState(
                provider="fake_vector",
                scope=scope,
                status=IndexStatus.READY,
                is_queryable=True,
                schema_version="v1",
                serving_generation=serving,
                source_snapshot_id=self.source_snapshots.get(scope.scope_id),
                applied_watermark=self.applied.get(scope.scope_id),
                record_count=self.record_counts.get(scope.scope_id, 0),
                last_success_at=self.last_success.get(scope.scope_id),
                last_checked_at=self.clock.now,
                evidence_level=EvidenceLevel.UNTESTED,
                availability=Availability.AVAILABLE,
            )
        return self._ok(state, request.request_id)


@dataclass
class TruthRecord:
    memory_id: str
    user_id: str
    version_id: str
    status: str
    object_type: ObjectType
    memory_type: Optional[str]
    content: str


def resolve_candidates(
    hits: list[RetrievalHit],
    truth: Dict[tuple[str, str], TruthRecord],
    user_id: str,
) -> list[RetrievalHit]:
    """模拟 SQLite 回源：丢弃跨用户、不存在、旧版本、已遗忘命中。"""
    out: list[RetrievalHit] = []
    for hit in dedupe_exact_version(hits):
        if hit.user_id != user_id:
            continue
        tr = truth.get((user_id, hit.memory_id))
        if tr is None or tr.version_id != hit.version_id or tr.status == "forgotten":
            continue
        out.append(hit)
    return out
