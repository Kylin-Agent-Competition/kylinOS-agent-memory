"""D13D FTS + Vector dual-channel Forget observation profile.

The approved FTS-only profile remains unchanged.  This profile is explicitly
registered as ``d13d-validation-profile-v2-dual-channel`` and uses the real
Embedding and Vector provider injected by its controlled builder.  Per the E
ruling, Vector indexes only active Knowledge; Preference remains a FTS-only
observation and is never claimed as Vector-supported.
"""

from __future__ import annotations

import hashlib
import logging
import math
import secrets
import sys
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from embedding.embedding_service import EmbeddingService
from evaluation.d13d_forget_fts_observer import (
    D13DForgetFtsDeletionProvider,
    D13DForgetFtsObserver,
    _active_docs,
    _content_text,
    _ValidationNoEmbeddingProvider,
    _ValidationNoExtractionCache,
)
from evaluation.d13d_forget_index_producer import (
    D13D_INDEX_DIGEST_KEY as _DIGEST_KEY,
)
from evaluation.d13d_forget_index_producer import (
    D13D_INDEX_DIGEST_KEY_ID as _DIGEST_KEY_ID,
)
from evaluation.d13d_forget_index_producer import index_knowledge_docs
from outbox.deletion_consumer import build_forget_consumer
from retrieval.contracts import (
    IndexScope,
    KnowledgeFilter,
    ObjectType,
    RebuildReason,
    RetrievalFilter,
    SceneFilter,
    ScopeAuthorization,
    ScopeKind,
    SelectionMode,
    VectorDeleteRequest,
    VectorDeleteResult,
    VectorRebuildRequest,
    VectorSearchRequest,
    Watermark,
    WatermarkDomain,
    WatermarkKind,
    digest_from_canonical,
)
from retrieval.evaluation import ForgetResidualPhase
from retrieval.real_vector_provider import VectorCliClient
from retrieval.sqlite_vector_provider import SqliteVectorProvider
from service.d13d_forget_observability import ForgetRetrievalObservation

logger = logging.getLogger(__name__)

PROFILE_ID = "d13d-validation-profile-v2-dual-channel"
_EXPECTED_EMBEDDING_DIMENSION = 768


class D13DForgetVectorDeletionProvider:
    """Knowledge-only deletion adapter in front of the real SQLite provider."""

    provider = "d13d-dual-channel-vector"

    def __init__(
        self,
        observer: D13DForgetDualChannelObserver,
        fts_provider: D13DForgetFtsDeletionProvider,
    ) -> None:
        self._observer = observer
        self._fts_provider = fts_provider

    def delete(self, request: VectorDeleteRequest) -> Any:
        observer = self._observer
        if request.user_id != observer.user_id or not observer.initialized:
            return self._failure(request, "Vector deletion provider is not bound to the observer")

        # The formal consumer must not ACK until both real channels have
        # removed their own index state.  Preference has no Vector state, so
        # its removal is proven by the FTS result.
        fts_result = self._fts_provider.delete(request)
        if not fts_result.ok:
            return fts_result

        memory_kinds = request.selector.memory_kinds
        if memory_kinds is not None and len(memory_kinds) != len(request.selector.memory_ids):
            return self._failure(request, "Vector deletion memory_kinds are not aligned")
        version_ids = request.selector.version_ids or [""] * len(request.selector.memory_ids)
        kinds = memory_kinds or [None] * len(request.selector.memory_ids)
        selected = list(zip(request.selector.memory_ids, version_ids, kinds))
        knowledge_pairs = [
            (memory_id, version_id)
            for memory_id, version_id, memory_kind in selected
            if not memory_kind or memory_kind == ObjectType.KNOWLEDGE.value
        ]
        if not knowledge_pairs:
            # Preference is intentionally not a Vector object.  The combined
            # observation still covers it through the FTS channel.
            return fts_result

        # The wrapped provider revalidates the signed request and performs the
        # real Vector CLI delete plus SQLite generation ledger updates.
        scoped_request = request.model_copy(
            update={
                "selector": request.selector.model_copy(
                    update={
                        "memory_ids": [memory_id for memory_id, _ in knowledge_pairs],
                        "version_ids": [version_id for _, version_id in knowledge_pairs],
                        "memory_kinds": [ObjectType.KNOWLEDGE.value] * len(knowledge_pairs),
                        "selection_mode": (
                            SelectionMode.SINGLE_ITEM if len(knowledge_pairs) == 1
                            else SelectionMode.RESOLVED_BATCH
                        ),
                    }
                ),
                "source_watermark": request.source_watermark.model_copy(
                    update={
                        "domain": request.source_watermark.domain.model_copy(
                            update={"stream": "memory_upserted"}
                        )
                    }
                ),
            }
        )
        scoped_request = scoped_request.model_copy(
            update={
                "payload_hash": digest_from_canonical(
                    _DIGEST_KEY_ID,
                    _DIGEST_KEY,
                    scoped_request.model_dump(
                        mode="json",
                        exclude={"request_id", "trace_id", "deadline_at", "payload_hash"},
                    ),
                )
            }
        )
        result = observer.vector_provider.delete(scoped_request)
        if not result.ok:
            return result
        value: VectorDeleteResult = result.value
        if value.matched_count != len(knowledge_pairs) or value.deleted_count != len(knowledge_pairs):
            return self._failure(
                request,
                "Vector delete did not remove every confirmed knowledge target",
            )
        return result

    @staticmethod
    def _no_op(request: VectorDeleteRequest) -> Any:
        from datetime import datetime, timezone

        from retrieval.contracts import Outcome, ProviderResult

        return ProviderResult(
            ok=True,
            value=VectorDeleteResult(
                matched_count=0,
                deleted_count=0,
                not_matched_ids=list(request.selector.memory_ids),
                index_generation=request.index_generation,
                applied_watermark=request.source_watermark,
                outcome=Outcome.NO_OP,
            ),
            provider="d13d-dual-channel-vector",
            request_id=request.request_id,
            elapsed_ms=0,
            completed_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _failure(request: VectorDeleteRequest, message: str) -> Any:
        from datetime import datetime, timezone

        from retrieval.contracts import (
            ProviderResult,
            RetrievalError,
            RetrievalErrorCode,
        )

        return ProviderResult(
            ok=False,
            error=RetrievalError(
                code=RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR,
                message=message,
                retryable=False,
                stage="delete",
                provider="d13d-dual-channel-vector",
            ),
            provider="d13d-dual-channel-vector",
            request_id=request.request_id,
            elapsed_ms=0,
            completed_at=datetime.now(timezone.utc),
        )


class D13DForgetDualChannelObserver:
    """Compose FTS and real-Vector observations with an explicit union residual."""

    def __init__(
        self,
        engine: Engine,
        *,
        user_id: str,
        fts_db: str,
        embedding_service: EmbeddingService,
        vector_provider: SqliteVectorProvider,
        index_generation: str,
        allow_knowledge_only_rebuild: bool,
        embedding_metadata: Mapping[str, Any],
        vector_metadata: Mapping[str, Any],
    ) -> None:
        if not isinstance(engine, Engine):
            raise TypeError("engine must be a SQLAlchemy Engine")
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be non-blank")
        if not isinstance(embedding_service, EmbeddingService):
            raise TypeError("embedding_service must be an EmbeddingService")
        if not isinstance(vector_provider, SqliteVectorProvider):
            raise TypeError("vector_provider must be a SqliteVectorProvider")
        if not index_generation.strip():
            raise ValueError("index_generation must be non-blank")

        self._engine = engine
        self.user_id = user_id
        self._fts = D13DForgetFtsObserver(engine, user_id=user_id, fts_db=fts_db)
        self._embedding_service = embedding_service
        self.vector_provider = vector_provider
        self.vector_index_generation = index_generation
        self.allow_knowledge_only_rebuild = allow_knowledge_only_rebuild
        self.embedding_metadata = dict(embedding_metadata)
        self.vector_metadata = dict(vector_metadata)
        self._docs: dict[str, dict[str, str]] = {}
        self._initialized = False
        self._realtime_generation = 0
        self._rebuild_generation = 0
        self._rebuild_result: Any | None = None
        self._rebuild_source_watermark: Watermark | None = None
        self.channel_results: dict[str, dict[str, Any]] = {}

    @property
    def initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> None:
        """Bootstrap FTS and Knowledge-only Vector through their real paths."""
        if self._initialized:
            return
        self._fts.initialize()
        with self._engine.connect() as conn:
            raw_docs = _active_docs(conn, user_id=self.user_id)
        docs = [
            {
                "tagged_id": doc.tagged_id,
                "version_id": doc.version_id,
                "text": doc.text,
            }
            for doc in raw_docs
        ]
        ok_count, skipped_count = index_knowledge_docs(
            self._engine,
            user_id=self.user_id,
            docs=docs,
            embedding_service=self._embedding_service,
            vector_provider=self.vector_provider,
            index_generation=self.vector_index_generation,
        )
        self._docs = {doc["tagged_id"]: dict(doc) for doc in docs if doc["tagged_id"].startswith("knowledge:")}
        self._initialized = True
        self.channel_results["initialization"] = {
            "knowledge_indexed": ok_count,
            "knowledge_skipped": skipped_count,
            "preference_vector_indexed": 0,
            "index_generation": self.vector_index_generation,
        }

    def close(self) -> None:
        self._embedding_service.close()

    def probe_pre_delete(self, confirmed: tuple[str, ...]) -> None:
        """Require every confirmed target to hit FTS and Knowledge to hit Vector."""
        if not self._initialized:
            raise ValueError("dual-channel observer must be initialized")
        self._fts.probe_pre_delete(confirmed)

        knowledge_targets = [target for target in confirmed if target.startswith("knowledge:")]
        for tagged_id in knowledge_targets:
            doc = self._docs.get(tagged_id)
            if doc is None:
                raise ValueError(f"pre-delete vector probe miss: {tagged_id}")
            hits = self._search_vector(self._embed(doc["text"]), "pre_delete")
            if not hits or not any(
                f"knowledge:{hit.memory_id}" == tagged_id for hit in hits
            ):
                raise ValueError(f"pre-delete vector probe miss: {tagged_id}")
        self.channel_results["pre_delete"] = {
            "fts_confirmed_targets": list(confirmed),
            "vector_confirmed_targets": knowledge_targets,
            "preference_vector_scope": "not_supported_by_approved_vector_semantics",
        }

    def realtime(self, confirmed: tuple[str, ...]) -> ForgetRetrievalObservation:
        """Observe both channels after the adapter has proven real worker ACK."""
        if not self._initialized:
            raise ValueError("dual-channel observer must be initialized")
        fts_observation = self._fts.realtime(confirmed)
        self._realtime_generation += 1
        vector_hits: list[Any] = []
        for tagged_id in sorted(self._docs):
            vector_hits.extend(self._search_vector(self._embed(self._docs[tagged_id]["text"]), "realtime"))
        vector_ranked = tuple(sorted({f"knowledge:{hit.memory_id}" for hit in vector_hits}))
        vector_observation = self._partial_observation(
            ForgetResidualPhase.REALTIME_DELETE,
            confirmed,
            vector_ranked,
            f"vector:{self.user_id}:realtime:g{self._realtime_generation}",
        )
        observation = self._combine(fts_observation, vector_observation)
        self.channel_results["realtime"] = self._channel_detail(
            confirmed, fts_observation, vector_observation
        )
        return observation

    def rebuild(self, confirmed: tuple[str, ...]) -> ForgetRetrievalObservation:
        """Perform a real Vector rebuild and combine it with a new FTS generation."""
        if not self._initialized:
            raise ValueError("dual-channel observer must be initialized")
        fts_observation = self._fts.rebuild(confirmed)
        self._rebuild_generation += 1

        source_snapshot_id = f"sqlite:{self.user_id}:d13d-rebuild:g{self._rebuild_generation}"
        source_watermark = Watermark(
            domain=WatermarkDomain(
                scope_id=f"user:{self.user_id}",
                stream="d13d_vector_rebuild",
                partition="default",
                source_generation=self.vector_index_generation,
            ),
            kind=WatermarkKind.MONOTONIC_INT,
            value=self._rebuild_generation,
        )
        scope = IndexScope(
            scope_id=f"user:{self.user_id}",
            kind=ScopeKind.USER,
            user_id=self.user_id,
            scope_fingerprint=digest_from_canonical(
                _DIGEST_KEY_ID,
                _DIGEST_KEY,
                {"scope_id": f"user:{self.user_id}"},
            ),
        )
        request = VectorRebuildRequest(
            request_id=f"d13d-vector-rebuild-{secrets.token_hex(8)}",
            trace_id=f"d13d-vector-rebuild:{self.user_id}",
            user_id=self.user_id,
            deadline_at=datetime.now(timezone.utc) + timedelta(minutes=2),
            idempotency_key=f"d13d-vector-rebuild:{secrets.token_hex(8)}",
            payload_hash="hmac-sha256:placeholder:" + "0" * 64,
            source_snapshot_id=source_snapshot_id,
            source_watermark=source_watermark,
            target_generation=f"d13d-vector-rebuild-{self._rebuild_generation}-{secrets.token_hex(8)}",
            schema_version="vector-retrieval/v1",
            reason=RebuildReason.REPAIR,
            scope=scope,
            scope_authorization=ScopeAuthorization(
                actor_ref="d13d-dual-channel-observer",
                authorization_ref=f"d13d-rebuild-{self._rebuild_generation}",
                scope_id=scope.scope_id,
                allowed_operations=["rebuild"],
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
            ),
        )
        semantic_payload = request.model_dump(
            mode="json",
            exclude={"request_id", "trace_id", "deadline_at", "payload_hash"},
        )
        semantic_payload["scope"].pop("scope_fingerprint", None)
        request = request.model_copy(
            update={
                "payload_hash": digest_from_canonical(
                    _DIGEST_KEY_ID,
                    _DIGEST_KEY,
                    semantic_payload,
                )
            }
        )
        result = self.vector_provider.rebuild(request)
        if not result.ok:
            raise ValueError(f"Vector rebuild failed: {result.error.message if result.error else 'unknown'}")
        value = result.value
        if not value.verified or not value.activated or value.rejected_count:
            raise ValueError("Vector rebuild did not activate a verified generation")
        self._rebuild_result = value
        self._rebuild_source_watermark = source_watermark

        vector_hits: list[Any] = []
        for tagged_id in sorted(self._docs):
            vector_hits.extend(self._search_vector(self._embed(self._docs[tagged_id]["text"]), "rebuild"))
        vector_ranked = tuple(sorted({f"knowledge:{hit.memory_id}" for hit in vector_hits}))
        vector_observation = self._partial_observation(
            ForgetResidualPhase.REBUILD,
            confirmed,
            vector_ranked,
            f"vector:{self.user_id}:rebuild:{value.target_generation}",
        )
        observation = self._combine(fts_observation, vector_observation)
        detail = self._channel_detail(confirmed, fts_observation, vector_observation)
        detail["collection_namespace"] = f"{scope.scope_id}:{value.target_generation}"
        detail["index_generation"] = value.target_generation
        detail["source_snapshot_id"] = value.source_snapshot_id
        detail["source_watermark"] = value.source_watermark.model_dump(mode="json")
        self.channel_results["rebuild"] = detail
        return observation

    def _embed(self, text: str) -> list[float]:
        response = self._embedding_service.embed(text, timeout_ms=30000)
        if not response.get("ok") or response.get("degraded"):
            raise ValueError("pre-delete embedding is unavailable")
        result = response.get("result") or {}
        vector = result.get("vector")
        dimension = result.get("dimension")
        norm = result.get("l2_norm")
        if (
            not isinstance(vector, list)
            or dimension != _EXPECTED_EMBEDDING_DIMENSION
            or len(vector) != _EXPECTED_EMBEDDING_DIMENSION
            or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in vector)
        ):
            raise ValueError("pre-delete embedding dimension mismatch")
        calculated_norm = math.sqrt(sum(float(value) ** 2 for value in vector))
        if not isinstance(norm, (int, float)) or not math.isfinite(float(norm)) or not 0.99 <= calculated_norm <= 1.01:
            raise ValueError("pre-delete embedding norm is outside the accepted range")
        return [float(value) for value in vector]

    def _search_vector(self, query_vector: list[float], phase: str) -> list[Any]:
        request = VectorSearchRequest(
            request_id=f"d13d-vector-search-{secrets.token_hex(8)}",
            trace_id=f"d13d-vector-search:{phase}:{self.user_id}",
            user_id=self.user_id,
            deadline_at=datetime.now(timezone.utc) + timedelta(seconds=30),
            query_vector=query_vector,
            filter=RetrievalFilter(
                user_id=self.user_id,
                scene=SceneFilter(include_unscoped=True),
                knowledge=KnowledgeFilter(),
                object_types=[ObjectType.KNOWLEDGE],
                allowed_memory_statuses=["active"],
                conflict_policy="latest_wins",
                as_of=datetime.now(timezone.utc),
            ),
            top_n=20,
        )
        result = self.vector_provider.search(request)
        if not result.ok:
            raise ValueError(f"Vector search failed: {result.error.message if result.error else 'unknown'}")
        return list(result.value.hits)

    def _partial_observation(
        self,
        phase: ForgetResidualPhase,
        confirmed: tuple[str, ...],
        ranked: tuple[str, ...],
        snapshot_id: str,
    ) -> ForgetRetrievalObservation:
        return ForgetRetrievalObservation(
            sample=replace(
                self._fts._observation(phase, confirmed, ranked, snapshot_id).sample,
            ),
            dataset_version="d13d-forget-v2-dual-channel",
            source_snapshot_id=snapshot_id,
            source_watermark=Watermark(
                domain=WatermarkDomain(
                    scope_id=f"user:{self.user_id}",
                    stream=f"forget_vector_{phase.value}",
                    partition="default",
                    source_generation=snapshot_id,
                ),
                kind=WatermarkKind.MONOTONIC_INT,
                value=self._rebuild_generation if phase is ForgetResidualPhase.REBUILD else self._realtime_generation,
            ),
        )

    def _combine(
        self,
        fts_observation: ForgetRetrievalObservation,
        vector_observation: ForgetRetrievalObservation,
    ) -> ForgetRetrievalObservation:
        if fts_observation.sample.confirmed_target_ids != vector_observation.sample.confirmed_target_ids:
            raise ValueError("dual-channel observations are not bound to the same targets")
        ranked = tuple(sorted(set(fts_observation.sample.ranked_ids) | set(vector_observation.sample.ranked_ids)))
        snapshot_id = f"dual-channel:{fts_observation.source_snapshot_id}+{vector_observation.source_snapshot_id}"
        return ForgetRetrievalObservation(
            sample=replace(fts_observation.sample, ranked_ids=ranked),
            dataset_version="d13d-forget-v2-dual-channel",
            source_snapshot_id=snapshot_id,
            source_watermark=Watermark(
                domain=WatermarkDomain(
                    scope_id=f"user:{self.user_id}",
                    stream="d13d_forget_dual_channel",
                    partition="default",
                    source_generation=snapshot_id,
                ),
                kind=WatermarkKind.MONOTONIC_INT,
                value=fts_observation.source_watermark.value,
            ),
        )

    def _channel_detail(
        self,
        confirmed: tuple[str, ...],
        fts_observation: ForgetRetrievalObservation,
        vector_observation: ForgetRetrievalObservation,
    ) -> dict[str, Any]:
        return {
            "fts": {
                "ranked_ids": list(fts_observation.sample.ranked_ids),
                "residual": _residual_count(fts_observation, confirmed),
                "snapshot_id": fts_observation.source_snapshot_id,
            },
            "vector": {
                "ranked_ids": list(vector_observation.sample.ranked_ids),
                "residual": _residual_count(vector_observation, confirmed),
                "snapshot_id": vector_observation.source_snapshot_id,
                "embedding": self.embedding_metadata,
                "provider": self.vector_metadata,
            },
        }


def _residual_count(observation: ForgetRetrievalObservation, confirmed: tuple[str, ...]) -> int:
    return len(set(observation.sample.confirmed_target_ids) & set(observation.sample.ranked_ids))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"dual-channel runtime config requires lowercase {label} sha256")
    return value


def build_dual_channel_observer(
    binding: Any,
    artifact: Mapping[str, Any],
    sample_id: str,
) -> D13DForgetDualChannelObserver:
    """Controlled profile builder for ``OBSERVATION_PROFILES``.

    Runtime binaries and the Embedding module are verified against artifact
    SHAs.  The builder never falls back to a deterministic provider.
    """
    entry = next(
        (sample for sample in artifact.get("samples", []) if sample.get("sample_id") == sample_id),
        None,
    )
    if entry is None:
        raise ValueError(f"artifact has no entry for {sample_id}")
    config = artifact.get("dual_channel_runtime")
    if not isinstance(config, Mapping):
        raise TypeError("dual-channel profile requires dual_channel_runtime artifact configuration")

    dimension_value = config.get("embedding_dimension")
    if dimension_value != _EXPECTED_EMBEDDING_DIMENSION:
        raise ValueError("dual-channel profile requires the approved 768-dimensional Embedding")

    embedding_path_value = config.get("embedding_module_path")
    vector_cli_path_value = config.get("vector_cli_path")
    if not isinstance(embedding_path_value, str) or not embedding_path_value:
        raise ValueError("dual-channel profile requires embedding_module_path")
    if not isinstance(vector_cli_path_value, str) or not vector_cli_path_value:
        raise ValueError("dual-channel profile requires vector_cli_path")
    embedding_path = Path(embedding_path_value)
    vector_cli_path = Path(vector_cli_path_value)
    if not embedding_path.is_file():
        raise ValueError("configured Embedding module does not exist")
    if not vector_cli_path.is_file():
        raise ValueError("configured vector_bridge_cli does not exist")
    embedding_sha = _require_sha256(config.get("embedding_module_sha256"), "embedding module")
    vector_sha = _require_sha256(config.get("vector_cli_sha256"), "vector bridge")
    if _sha256_file(embedding_path) != embedding_sha:
        raise ValueError("Embedding module SHA-256 mismatch")
    if _sha256_file(vector_cli_path) != vector_sha:
        raise ValueError("vector_bridge_cli SHA-256 mismatch")

    module_parent = str(embedding_path.parent)
    if module_parent not in sys.path:
        sys.path.insert(0, module_parent)
    from providers import EmbeddingProvider

    provider = EmbeddingProvider()
    provider.start()
    embedding_service = EmbeddingService(provider=provider)
    vector_client = VectorCliClient(
        cli_path=str(vector_cli_path),
        expected_dimension=_EXPECTED_EMBEDDING_DIMENSION,
    )
    if provider.get_dimension() != _EXPECTED_EMBEDDING_DIMENSION:
        provider.close()
        raise ValueError("runtime Embedding dimension is not 768")

    mode = str(entry["forget_mode"])
    index_generation = f"d13d-vector-predelete-{sample_id}-{secrets.token_hex(6)}"
    vector_provider = SqliteVectorProvider(
        binding.engine,
        vector_client=vector_client,
        digest_keys={_DIGEST_KEY_ID: _DIGEST_KEY},
        embedding_service=embedding_service,
        index_text_resolver=_content_text,
        dimension=_EXPECTED_EMBEDDING_DIMENSION,
        allow_knowledge_only_rebuild=(mode != "full_reset"),
    )
    try:
        observer = D13DForgetDualChannelObserver(
            binding.engine,
            user_id=str(entry["user_id"]),
            fts_db=str(binding.db_path.with_name("fts.db")),
            embedding_service=embedding_service,
            vector_provider=vector_provider,
            index_generation=index_generation,
            allow_knowledge_only_rebuild=(mode != "full_reset"),
            embedding_metadata={
                "provider": "kylin_embedding",
                "module_path": str(embedding_path),
                "module_sha256": embedding_sha,
                "dimension": _EXPECTED_EMBEDDING_DIMENSION,
            },
            vector_metadata={
                "provider": "SqliteVectorProvider + VectorCliClient",
                "binary_path": str(vector_cli_path),
                "binary_sha256": vector_sha,
                "digest_key_id": _DIGEST_KEY_ID,
            },
        )
        observer.initialize()
        return observer
    except Exception:
        try:
            embedding_service.close()
        except Exception:
            logger.warning("dual-channel embedding cleanup failed", exc_info=True)
        raise


def build_dual_channel_forget_consumer(
    observer: D13DForgetDualChannelObserver,
) -> tuple[Any, EmbeddingService]:
    """Build the formal forget.executed consumer for the dual-channel profile."""
    no_embedding_service = EmbeddingService(provider=_ValidationNoEmbeddingProvider())
    no_embedding_service.set_cache_invalidator(_ValidationNoExtractionCache())
    fts_provider = D13DForgetFtsDeletionProvider(
        observer._fts,
        digest_key_id=_DIGEST_KEY_ID,
        digest_key=_DIGEST_KEY,
    )
    deletion_provider = D13DForgetVectorDeletionProvider(observer, fts_provider)
    consumer = build_forget_consumer(
        no_embedding_service,
        vector_provider=deletion_provider,
        digest_key_id=_DIGEST_KEY_ID,
        digest_key=_DIGEST_KEY,
        index_generation=observer.vector_index_generation,
    )
    return consumer, no_embedding_service
