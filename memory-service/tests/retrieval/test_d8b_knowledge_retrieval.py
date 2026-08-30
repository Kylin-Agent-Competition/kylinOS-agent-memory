from dataclasses import replace
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from retrieval import contracts as c
from retrieval.fusion import TruthRecord, fuse_retrieval, retrieve_graceful
from retrieval.fts5 import Fts5Index
from retrieval.real_vector_provider import VectorCliClient
import retrieval.real_vector_provider as real_vector_provider

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)
DIGEST = "hmac-sha256:k1:" + "a" * 64


def test_knowledge_filter_normalizes_query_metadata():
    knowledge = c.KnowledgeFilter(
        knowledge_types=["case", "fact", "case"],
        primary_categories=["operations", "operations"],
        source_event_ids=["event-b", "event-a", "event-b"],
        version_ids=["v2", "v1", "v2"],
        required_relation_ids=["relation-b", "relation-a", "relation-b"],
    )

    assert knowledge.knowledge_types == ["case", "fact"]
    assert knowledge.primary_categories == ["operations"]
    assert knowledge.source_event_ids == ["event-a", "event-b"]
    assert knowledge.version_ids == ["v1", "v2"]
    assert knowledge.required_relation_ids == ["relation-a", "relation-b"]


@pytest.mark.parametrize(
    "field",
    [
        "knowledge_types",
        "primary_categories",
        "source_event_ids",
        "version_ids",
        "required_relation_ids",
    ],
)
def test_knowledge_filter_rejects_blank_metadata(field):
    with pytest.raises(ValidationError):
        c.KnowledgeFilter(**{field: [" "]})


def test_knowledge_filter_is_part_of_retrieval_contract():
    filter_ = c.RetrievalFilter(
        user_id="alice",
        object_types=[c.ObjectType.KNOWLEDGE],
        allowed_memory_statuses=["active"],
        conflict_policy="exclude_unresolved",
        as_of=NOW,
        knowledge=c.KnowledgeFilter(knowledge_types=["fact"]),
    )

    assert filter_.knowledge.knowledge_types == ["fact"]


def test_knowledge_query_metadata_requires_knowledge_object_type():
    with pytest.raises(ValidationError, match="Knowledge 查询条件"):
        c.RetrievalFilter(
            user_id="alice",
            object_types=[c.ObjectType.PREFERENCE],
            conflict_policy="exclude_unresolved",
            as_of=NOW,
            knowledge=c.KnowledgeFilter(source_event_ids=["event-a"]),
        )


def test_vector_record_carries_normalized_knowledge_index_metadata():
    record = c.VectorRecord(
        memory_id="knowledge-1",
        version_id="v3",
        user_id="alice",
        vector=[0.1, 0.2],
        object_type=c.ObjectType.KNOWLEDGE,
        memory_type="long_term",
        index_text_hash=DIGEST,
        knowledge=c.KnowledgeIndexMetadata(
            knowledge_type="fact",
            primary_category="operations",
            source_event_id="event-1",
            memory_status="active",
            relation_ids=["relation-b", "relation-a", "relation-b"],
        ),
    )

    assert record.knowledge.relation_ids == ["relation-a", "relation-b"]


def test_vector_record_rejects_knowledge_metadata_for_preference():
    with pytest.raises(ValidationError, match="Knowledge 索引元数据"):
        c.VectorRecord(
            memory_id="preference-1",
            version_id="v1",
            user_id="alice",
            vector=[0.1, 0.2],
            object_type=c.ObjectType.PREFERENCE,
            memory_type="long_term",
            index_text_hash=DIGEST,
            knowledge=c.KnowledgeIndexMetadata(
                knowledge_type="fact",
                source_event_id="event-1",
                memory_status="active",
            ),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("knowledge_type", " "),
        ("primary_category", " "),
        ("source_event_id", " "),
        ("memory_status", " "),
        ("relation_ids", [" "]),
    ],
)
def test_knowledge_index_metadata_rejects_blank_values(field, value):
    data = {
        "knowledge_type": "fact",
        "source_event_id": "event-1",
        "memory_status": "active",
        field: value,
    }
    with pytest.raises(ValidationError):
        c.KnowledgeIndexMetadata(**data)


def _hit(memory_id, *, version_id="v1", rank=1):
    return c.RetrievalHit(
        memory_id=memory_id,
        version_id=version_id,
        user_id="alice",
        channel=c.Channel.FTS5,
        rank=rank,
        raw_score=-1.0,
        score_semantics=c.ScoreSemantics.BM25,
        provider="test",
        retrieved_at=NOW,
        filter_fingerprint=DIGEST,
    )


def _truth(
    memory_id,
    *,
    version_id="v1",
    knowledge_type="fact",
    primary_category="operations",
    source_event_id="event-1",
    memory_status="active",
    indexed_memory_status=None,
    relation_ids=None,
    is_current=True,
):
    return TruthRecord(
        memory_id=memory_id,
        version_id=version_id,
        user_id="alice",
        object_type=c.ObjectType.KNOWLEDGE,
        memory_type="long_term",
        memory_status=memory_status,
        content=memory_id,
        sensitivity="internal",
        conflict_state="resolved",
        is_current=is_current,
        knowledge=c.KnowledgeIndexMetadata(
            knowledge_type=knowledge_type,
            primary_category=primary_category,
            source_event_id=source_event_id,
            memory_status=indexed_memory_status or memory_status,
            relation_ids=relation_ids or [],
        ),
    )


def _filter(*, knowledge=None, statuses=None):
    return c.RetrievalFilter(
        user_id="alice",
        object_types=[c.ObjectType.KNOWLEDGE],
        allowed_memory_statuses=statuses or ["active"],
        allowed_sensitivity=["internal"],
        conflict_policy="exclude_unresolved",
        as_of=NOW,
        knowledge=knowledge or c.KnowledgeFilter(),
    )


def test_knowledge_type_filter_returns_only_allowed_type():
    truth = {
        ("alice", "fact", "v1"): _truth("fact", knowledge_type="fact"),
        ("alice", "case", "v1"): _truth("case", knowledge_type="case"),
    }

    out = fuse_retrieval(
        fts5_hits=[_hit("fact", rank=1), _hit("case", rank=2)],
        vector_hits=[],
        truth=truth,
        flt=_filter(knowledge=c.KnowledgeFilter(knowledge_types=["fact"])),
    )

    assert [candidate.memory_id for candidate in out] == ["fact"]


def test_primary_category_filter_returns_only_allowed_category():
    truth = {
        ("alice", "operations", "v1"): _truth(
            "operations", primary_category="operations"
        ),
        ("alice", "development", "v1"): _truth(
            "development", primary_category="development"
        ),
    }

    out = fuse_retrieval(
        fts5_hits=[_hit("operations", rank=1), _hit("development", rank=2)],
        vector_hits=[],
        truth=truth,
        flt=_filter(
            knowledge=c.KnowledgeFilter(primary_categories=["development"])
        ),
    )

    assert [candidate.memory_id for candidate in out] == ["development"]


def test_source_filter_returns_only_matching_evidence_source():
    truth = {
        ("alice", "from-a", "v1"): _truth("from-a", source_event_id="event-a"),
        ("alice", "from-b", "v1"): _truth("from-b", source_event_id="event-b"),
    }

    out = fuse_retrieval(
        fts5_hits=[_hit("from-a", rank=1), _hit("from-b", rank=2)],
        vector_hits=[],
        truth=truth,
        flt=_filter(
            knowledge=c.KnowledgeFilter(source_event_ids=["event-b"])
        ),
    )

    assert [candidate.memory_id for candidate in out] == ["from-b"]


def test_version_filter_returns_only_requested_current_version():
    truth = {
        ("alice", "old-id", "v1"): _truth("old-id", version_id="v1"),
        ("alice", "new-id", "v2"): _truth("new-id", version_id="v2"),
    }

    out = fuse_retrieval(
        fts5_hits=[
            _hit("old-id", version_id="v1", rank=1),
            _hit("new-id", version_id="v2", rank=2),
        ],
        vector_hits=[],
        truth=truth,
        flt=_filter(knowledge=c.KnowledgeFilter(version_ids=["v2"])),
    )

    assert [(candidate.memory_id, candidate.version_id) for candidate in out] == [
        ("new-id", "v2")
    ]


def test_required_relations_use_and_subset_matching():
    truth = {
        ("alice", "complete", "v1"): _truth(
            "complete", relation_ids=["relation-a", "relation-b"]
        ),
        ("alice", "partial", "v1"): _truth(
            "partial", relation_ids=["relation-a"]
        ),
    }

    out = fuse_retrieval(
        fts5_hits=[_hit("partial", rank=1), _hit("complete", rank=2)],
        vector_hits=[],
        truth=truth,
        flt=_filter(
            knowledge=c.KnowledgeFilter(
                required_relation_ids=["relation-a", "relation-b"]
            )
        ),
    )

    assert [candidate.memory_id for candidate in out] == ["complete"]


def test_knowledge_index_status_mismatch_fails_closed_before_rrf():
    truth = {
        ("alice", "stale-index", "v1"): _truth(
            "stale-index",
            memory_status="active",
            indexed_memory_status="deprecated",
        )
    }

    out = fuse_retrieval(
        fts5_hits=[_hit("stale-index")],
        vector_hits=[],
        truth=truth,
        flt=_filter(statuses=["active"]),
    )

    assert out == []


def test_missing_knowledge_truth_metadata_fails_closed_before_rrf():
    truth = {
        ("alice", "unstructured", "v1"): replace(
            _truth("unstructured"), knowledge=None
        )
    }

    out = fuse_retrieval(
        fts5_hits=[_hit("unstructured")],
        vector_hits=[],
        truth=truth,
        flt=_filter(),
    )

    assert out == []


@pytest.mark.parametrize("versions", [("v1", "v2"), ("v2", "v1")])
def test_knowledge_with_multiple_current_versions_fails_closed_in_any_order(versions):
    truth = {
        ("alice", "duplicate-current", version): _truth(
            "duplicate-current", version_id=version, is_current=True
        )
        for version in versions
    }

    out = fuse_retrieval(
        fts5_hits=[
            _hit("duplicate-current", version_id="v1", rank=1),
            _hit("duplicate-current", version_id="v2", rank=2),
        ],
        vector_hits=[],
        truth=truth,
        flt=_filter(),
    )

    assert out == []


def test_knowledge_candidate_reports_matched_metadata_without_relation_ids_in_explanation():
    truth = {
        ("alice", "knowledge-1", "v1"): _truth(
            "knowledge-1", relation_ids=["relation-a"]
        )
    }
    out = fuse_retrieval(
        fts5_hits=[_hit("knowledge-1")],
        vector_hits=[],
        truth=truth,
        flt=_filter(
            knowledge=c.KnowledgeFilter(
                knowledge_types=["fact"],
                primary_categories=["operations"],
                source_event_ids=["event-1"],
                version_ids=["v1"],
                required_relation_ids=["relation-a"],
            )
        ),
    )

    assert out[0].knowledge.knowledge_type == "fact"
    assert out[0].knowledge.source_event_id == "event-1"
    assert out[0].explanation["hard_filter"] == {
        "policy_version": "knowledge-filter/v1",
        "current_version": "passed",
        "knowledge_type": "matched",
        "primary_category": "matched",
        "source": "matched",
        "status": "matched",
        "relations": "matched",
        "conflict": "resolved",
    }
    assert "relation-a" not in str(out[0].explanation)


def test_knowledge_explanation_reports_degraded_channel_without_error_text():
    truth = {
        ("alice", "knowledge-1", "v1"): _truth("knowledge-1")
    }

    def vector_failure():
        raise RuntimeError("secret-path=C:/private/token")

    outcome = retrieve_graceful(
        fts5_search=lambda: [_hit("knowledge-1")],
        vector_search=vector_failure,
        truth=truth,
        flt=_filter(),
    )

    assert outcome.candidates[0].explanation["degraded_channels"] == ["vector"]
    assert "secret-path" not in str(outcome.candidates[0].explanation)


def test_fts5_prefilters_knowledge_type_source_version_status_and_category():
    index = Fts5Index()
    index.upsert(
        "knowledge-1",
        "v2",
        "sensor reset procedure",
        "alice",
        object_type=c.ObjectType.KNOWLEDGE,
        knowledge=c.KnowledgeIndexMetadata(
            knowledge_type="workflow",
            primary_category="operations",
            source_event_id="event-1",
            memory_status="active",
        ),
    )
    index.upsert(
        "knowledge-2",
        "v1",
        "sensor reset note",
        "alice",
        object_type=c.ObjectType.KNOWLEDGE,
        knowledge=c.KnowledgeIndexMetadata(
            knowledge_type="fact",
            primary_category="development",
            source_event_id="event-2",
            memory_status="deprecated",
        ),
    )

    hits = index.search(
        "sensor",
        "alice",
        filter=_filter(
            knowledge=c.KnowledgeFilter(
                knowledge_types=["workflow"],
                primary_categories=["operations"],
                source_event_ids=["event-1"],
                version_ids=["v2"],
            ),
            statuses=["active"],
        ),
        now=NOW,
    )

    assert [(hit.memory_id, hit.version_id) for hit in hits] == [
        ("knowledge-1", "v2")
    ]


def test_fts5_indexes_only_explicit_sanitized_content_summary():
    index = Fts5Index()
    index.upsert("knowledge-1", "v1", "public maintenance summary", "alice")

    assert index.search("secret", "alice", now=NOW) == []
    with pytest.raises(TypeError, match="content"):
        index.upsert(
            memory_id="knowledge-2",
            version_id="v1",
            content="raw secret",
            user_id="alice",
        )


def test_vector_insert_sends_knowledge_scalar_index_fields(monkeypatch):
    captured = {}

    def fake_run(command, *, input, text, capture_output, timeout):
        captured["payload"] = json.loads(input)
        return SimpleNamespace(returncode=0, stdout='{"ok":true}\n', stderr="")

    monkeypatch.setattr(real_vector_provider.subprocess, "run", fake_run)
    client = VectorCliClient("vector_cli", expected_dimension=2)

    client.insert(
        "knowledge",
        [1],
        [[0.1, 0.2]],
        user_ids=["alice"],
        version_ids=["v2"],
        scene_ids=[""],
        memory_statuses=["active"],
        deleted_flags=[False],
        object_types=["knowledge"],
        knowledge_types=["workflow"],
        primary_categories=["operations"],
        source_event_ids=["event-1"],
    )

    assert captured["payload"] == {
        "ids": [1],
        "vectors": [[0.1, 0.2]],
        "user_ids": ["alice"],
        "version_ids": ["v2"],
        "scene_ids": [""],
        "memory_statuses": ["active"],
        "deleted_flags": [False],
        "object_types": ["knowledge"],
        "knowledge_types": ["workflow"],
        "primary_categories": ["operations"],
        "source_event_ids": ["event-1"],
    }


def test_vector_search_sends_knowledge_scalar_filters(monkeypatch):
    captured = {}

    def fake_run(command, *, input, text, capture_output, timeout):
        captured["payload"] = json.loads(input)
        return SimpleNamespace(
            returncode=0,
            stdout='{"ok":true,"hits":[]}\n',
            stderr="",
        )

    monkeypatch.setattr(real_vector_provider.subprocess, "run", fake_run)
    client = VectorCliClient("vector_cli", expected_dimension=2)
    filter_ = _filter(
        knowledge=c.KnowledgeFilter(
            knowledge_types=["workflow"],
            primary_categories=["operations"],
            source_event_ids=["event-1"],
            version_ids=["v2"],
        ),
        statuses=["active"],
    )

    client.search(
        "knowledge",
        [0.1, 0.2],
        10,
        user_id="alice",
        filter=filter_,
        now=NOW,
    )

    assert captured["payload"]["filter"] == {
        "user_id": "alice",
        "allowed_scene_ids": [],
        "include_unscoped": False,
        "allowed_memory_statuses": ["active"],
        "exclude_deleted": True,
        "object_types": ["knowledge"],
        "knowledge_types": ["workflow"],
        "primary_categories": ["operations"],
        "source_event_ids": ["event-1"],
        "version_ids": ["v2"],
    }
