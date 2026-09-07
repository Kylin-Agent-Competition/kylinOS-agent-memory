"""L1 contract tests for the D13D dual-channel observation profile."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from db import repositories as repo
from db.engine import create_db_engine, init_schema
from embedding.embedding_service import EmbeddingService
from evaluation.d13d_execution_adapter import OBSERVATION_PROFILES
from evaluation.d13d_forget_dual_channel_observer import (
    PROFILE_ID,
    D13DForgetDualChannelObserver,
    build_dual_channel_forget_consumer,
)
from evaluation.d13d_forget_fts_observer import _content_text
from evaluation.d13d_forget_index_producer import (
    D13D_INDEX_DIGEST_KEY,
    D13D_INDEX_DIGEST_KEY_ID,
)
from providers import EmbeddingResult, ProviderError, ProviderErrorCode
from retrieval.contracts import (
    Channel,
    KnowledgeFilter,
    ObjectType,
    RetrievalFilter,
    SceneFilter,
    ScoreSemantics,
    VectorSearchRequest,
    digest_from_canonical,
)
from retrieval.real_vector_provider import VectorCliError
from retrieval.sqlite_vector_provider import SqliteVectorProvider

USER_ID = "user_d13e_alpha"


class _FakeEmbeddingProvider:
    """Deterministic local Embedding stub used only for L1 failure injection."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def start(self) -> None:
        return None

    def close(self) -> None:
        return None

    def get_dimension(self) -> int:
        return 768

    def embed(self, text: str, *, timeout_ms: int = 5000) -> EmbeddingResult:
        if self.fail:
            raise ProviderError(ProviderErrorCode.ERR_EMBED_FAILED, "injected failure")
        value = 1.0 / (768 ** 0.5)
        return EmbeddingResult([value] * 768, 768, 1.0)


class _FakeVectorClient:
    """In-memory Vector CLI stub for L1 provider/observer contract checks."""

    def __init__(self, *, fail_search: bool = False, fail_rebuild: bool = False) -> None:
        self.collections: dict[str, list[dict]] = {}
        self.delete_calls = 0
        self.fail_search = fail_search
        self.fail_rebuild = fail_rebuild

    def create_collection(self, name: str, dimension: int) -> dict:
        self.collections.setdefault(name, [])
        return {"ok": True}

    def insert(
        self,
        name: str,
        ids: list[int],
        vectors: list[list[float]],
        *,
        user_ids: list[str],
        version_ids: list[str],
        scene_ids: list[str],
        memory_statuses: list[str],
        deleted_flags: list[bool],
        **_metadata: object,
    ) -> dict:
        if self.fail_rebuild:
            raise VectorCliError(-1, "injected rebuild failure")
        records = self.collections.setdefault(name, [])
        for index, memory_id in enumerate(ids):
            records.append({
                "memory_id": memory_id,
                "version_id": version_ids[index],
                "user_id": user_ids[index],
                "memory_status": memory_statuses[index],
                "deleted": deleted_flags[index],
            })
        return {"ok": True}

    def delete(
        self,
        name: str,
        ids: list[int],
        *,
        user_id: str,
        version_ids: list[str],
        **_metadata: object,
    ) -> dict:
        self.delete_calls += 1
        deleted = 0
        for record in self.collections.get(name, []):
            if (
                record["user_id"] == user_id
                and record["memory_id"] in ids
                and record["version_id"] in version_ids
                and not record["deleted"]
            ):
                record["deleted"] = True
                deleted += 1
        return {"ok": True, "deleted": deleted}

    def drop_collection(self, name: str) -> dict:
        self.collections.pop(name, None)
        return {"ok": True}

    def search(
        self,
        name: str,
        _vector: list[float],
        top_n: int,
        *,
        user_id: str,
        filter: RetrievalFilter,
        **_metadata: object,
    ):
        if self.fail_search:
            raise VectorCliError(-1, "injected search failure")
        if filter.user_id != user_id:
            raise ValueError("RetrievalFilter.user_id must match search user_id")
        hits = []
        fingerprint = digest_from_canonical("test", b"test", {"collection": name})
        for record in self.collections.get(name, []):
            if record["user_id"] != user_id or record["deleted"]:
                continue
            if record["memory_status"] not in filter.allowed_memory_statuses:
                continue
            hits.append((
                record["memory_id"],
                record["version_id"],
            ))
        return [
            {
                "memory_id": str(memory_id),
                "version_id": version_id,
                "user_id": user_id,
                "channel": Channel.VECTOR,
                "rank": rank,
                "raw_score": 1.0,
                "score_semantics": ScoreSemantics.SDK_SCORE_UNVERIFIED,
                "provider": "fake_vector_cli",
                "index_generation": name,
                "retrieved_at": datetime.now(timezone.utc),
                "filter_fingerprint": fingerprint,
            }
            for rank, (memory_id, version_id) in enumerate(hits, start=1)
        ]


def _make_observer(tmp_path: Path, *, allow_knowledge_only: bool = True):
    db_path = tmp_path / "runtime.db"
    engine = create_db_engine(str(db_path))
    init_schema(engine)
    with engine.begin() as conn:
        repo.insert_memory_entry(
            conn,
            user_id=USER_ID,
            entry_type="knowledge",
            content={"value": "d13d dual channel target"},
        )
        repo.save_preference_version(
            conn,
            user_id=USER_ID,
            preference_key="response.language",
            preference_scope="global",
            preference_value="zh-CN",
            memory_status="active",
            evidence_fingerprint="evidence-d13d",
            idempotency_key="d13d-preference-v1",
            request_fingerprint="request-d13d",
        )
    embedding_provider = _FakeEmbeddingProvider()
    embedding_service = EmbeddingService(provider=embedding_provider)
    vector_client = _FakeVectorClient()
    provider = SqliteVectorProvider(
        engine,
        vector_client=vector_client,
        digest_keys={D13D_INDEX_DIGEST_KEY_ID: D13D_INDEX_DIGEST_KEY},
        embedding_service=embedding_service,
        index_text_resolver=_content_text,
        dimension=768,
        allow_knowledge_only_rebuild=allow_knowledge_only,
    )
    observer = D13DForgetDualChannelObserver(
        engine,
        user_id=USER_ID,
        fts_db=str(db_path.with_name("fts.db")),
        embedding_service=embedding_service,
        vector_provider=provider,
        index_generation="d13d-l1-vector-g1",
        allow_knowledge_only_rebuild=allow_knowledge_only,
        embedding_metadata={"provider": "L1-fake", "dimension": 768},
        vector_metadata={"provider": "L1-fake-vector-cli"},
    )
    observer.initialize()
    return observer, vector_client, embedding_provider


def test_dual_channel_positive_closes_realtime_and_rebuild(tmp_path):
    observer, _vector_client, _embedding_provider = _make_observer(tmp_path)
    confirmed = ("knowledge:1", "preference:1")
    observer.probe_pre_delete(confirmed)

    consumer, _embedding_service = build_dual_channel_forget_consumer(observer)
    consumer(repo.EVENT_FORGET_EXECUTED, {
        "event_id": "d13d-event-1",
        "user_id": USER_ID,
        "resolved_target_ids": list(confirmed),
        "version_ids": ["v1", "v1"],
        "selection_hash": hashlib.sha256(b"selection").hexdigest(),
        "forget_plan_id": "d13d-plan-1",
        "target_type": "all",
        "forget_mode": "single_item",
        "source_watermark_value": 999,
    })

    with observer._engine.begin() as conn:
        repo.soft_delete_memory_entry(
            conn,
            entry_id=1,
            user_id=USER_ID,
            current_version=1,
            current_row_revision=1,
        )
        repo.save_preference_version(
            conn,
            user_id=USER_ID,
            preference_key="response.language",
            preference_scope="global",
            preference_value="zh-CN",
            memory_status="removed",
            evidence_fingerprint="evidence-d13d-removed",
            idempotency_key="d13d-preference-removed",
            request_fingerprint="request-d13d-removed",
        )

    realtime = observer.realtime(confirmed)
    rebuild = observer.rebuild(confirmed)
    assert realtime.sample.ranked_ids == ()
    assert rebuild.sample.ranked_ids == ()
    assert observer.channel_results["realtime"]["fts"]["residual"] == 0
    assert observer.channel_results["realtime"]["vector"]["residual"] == 0
    assert observer.channel_results["rebuild"]["fts"]["residual"] == 0
    assert observer.channel_results["rebuild"]["vector"]["residual"] == 0


def test_preference_only_delete_is_fts_only_and_leaves_vector_state(tmp_path):
    observer, vector_client, _embedding_provider = _make_observer(tmp_path)
    consumer, _embedding_service = build_dual_channel_forget_consumer(observer)
    consumer(repo.EVENT_FORGET_EXECUTED, {
        "event_id": "d13d-event-pref",
        "user_id": USER_ID,
        "resolved_target_ids": ["preference:1"],
        "version_ids": ["v1"],
        "selection_hash": hashlib.sha256(b"preference").hexdigest(),
        "forget_plan_id": "d13d-plan-pref",
        "target_type": "preference",
        "forget_mode": "single_item",
    })

    assert vector_client.delete_calls == 0
    preference_realtime = observer.realtime(("preference:1",))
    assert preference_realtime.sample.ranked_ids == ("knowledge:1",)
    assert len(set(preference_realtime.sample.confirmed_target_ids) & set(preference_realtime.sample.ranked_ids)) == 0


def test_pre_delete_fails_closed_when_vector_probe_misses(tmp_path):
    observer, vector_client, _embedding_provider = _make_observer(tmp_path)
    vector_client.collections.clear()
    with pytest.raises(ValueError, match="pre-delete vector probe miss"):
        observer.probe_pre_delete(("knowledge:1",))


def test_embedding_failure_is_not_treated_as_a_vector_hit(tmp_path):
    observer, _vector_client, embedding_provider = _make_observer(tmp_path)
    embedding_provider.fail = True
    with pytest.raises(ValueError, match="embedding is unavailable"):
        observer._embed("probe")


def test_vector_search_failure_fails_closed(tmp_path):
    observer, vector_client, _embedding_provider = _make_observer(tmp_path)
    vector_client.fail_search = True
    with pytest.raises(ValueError, match="Vector search failed"):
        observer._search_vector(observer._embed("probe"), "realtime")


def test_rebuild_failure_fails_closed(tmp_path):
    observer, vector_client, _embedding_provider = _make_observer(tmp_path)
    vector_client.fail_rebuild = True
    with pytest.raises(ValueError, match="Vector rebuild failed"):
        observer.rebuild(("knowledge:1",))


def test_full_reset_with_active_preference_still_fails_closed(tmp_path):
    observer, _vector_client, _embedding_provider = _make_observer(
        tmp_path, allow_knowledge_only=False
    )
    with pytest.raises(ValueError, match="active preference records"):
        observer.rebuild(("knowledge:1",))


def test_search_rejects_filter_scope_mismatch(tmp_path):
    observer, _vector_client, _embedding_provider = _make_observer(tmp_path)
    request = VectorSearchRequest(
        request_id="scope-mismatch",
        trace_id="scope-mismatch",
        user_id=USER_ID,
        deadline_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        query_vector=observer._embed("probe"),
        filter=RetrievalFilter(
            user_id="user_foreign",
            scene=SceneFilter(include_unscoped=True),
            knowledge=KnowledgeFilter(),
            object_types=[ObjectType.KNOWLEDGE],
            allowed_memory_statuses=["active"],
            conflict_policy="latest_wins",
            as_of=datetime.now(timezone.utc),
        ),
        top_n=20,
    )
    result = observer.vector_provider.search(request)
    assert not result.ok
    assert result.error is not None
    assert result.error.code.value == "user_scope_violation"


def test_profile_allowlist_is_explicit_and_preserves_fts_only_history():
    assert PROFILE_ID in OBSERVATION_PROFILES
    assert OBSERVATION_PROFILES["d13d-validation-profile-v2"] is not None
    assert OBSERVATION_PROFILES["d13d-validation-profile-v1"] is not None
