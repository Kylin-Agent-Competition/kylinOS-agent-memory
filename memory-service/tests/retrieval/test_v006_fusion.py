"""V006：FTS5 + Vector 融合编排测试（回源硬过滤 + rrf-v1 + 统一候选）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from retrieval.contracts import (
    Channel,
    ObjectType,
    RetrievalFilter,
    RetrievalHit,
    SceneFilter,
    ScoreSemantics,
)
from retrieval.fusion import TruthRecord, fuse_retrieval
from retrieval.fts5 import Fts5Index

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


def _hit(memory_id, version_id, channel, rank, user_id="alice", raw_score=0.0):
    return RetrievalHit(
        memory_id=memory_id,
        version_id=version_id,
        user_id=user_id,
        channel=channel,
        rank=rank,
        raw_score=raw_score,
        score_semantics=ScoreSemantics.BM25 if channel is Channel.FTS5 else ScoreSemantics.SDK_SCORE_UNVERIFIED,
        provider="test",
        retrieved_at=NOW,
        filter_fingerprint="hmac-sha256:k1:" + "a" * 64,
    )


def _truth(
    memory_id,
    version_id="v1",
    user_id="alice",
    status="active",
    sensitivity="internal",
    content="x",
    object_type=ObjectType.KNOWLEDGE,
    conflict_state="resolved",
    is_current=True,
    scene_id=None,
    scope_terms=None,
    valid_from=None,
    valid_to=None,
):
    validity = {}
    if valid_from is not None:
        validity["valid_from"] = valid_from
    if valid_to is not None:
        validity["valid_to"] = valid_to
    return TruthRecord(
        memory_id=memory_id,
        version_id=version_id,
        user_id=user_id,
        object_type=object_type,
        memory_type="long_term",
        memory_status=status,
        content=content,
        sensitivity=sensitivity,
        conflict_state=conflict_state,
        is_current=is_current,
        scene_id=scene_id,
        scope_terms=scope_terms,
        **validity,
    )


def _flt(
    statuses=None,
    sensitivity=None,
    object_types=None,
    allowed_scene_ids=None,
    include_unscoped=False,
    scope_terms=None,
):
    return RetrievalFilter(
        user_id="alice",
        scene=SceneFilter(
            allowed_scene_ids=allowed_scene_ids or [],
            include_unscoped=include_unscoped,
        ),
        scope_terms=scope_terms or {},
        object_types=object_types or [ObjectType.KNOWLEDGE],
        allowed_memory_statuses=statuses or ["active"],
        allowed_sensitivity=sensitivity or ["internal"],
        conflict_policy="resolve",
        as_of=NOW,
    )


def test_preference_validity_interval_is_half_open_at_as_of():
    hits = [
        _hit("effective", "v1", Channel.FTS5, 1),
        _hit("expired-at-boundary", "v1", Channel.FTS5, 2),
        _hit("future", "v1", Channel.FTS5, 3),
    ]
    truth = {
        ("alice", "effective", "v1"): _truth(
            "effective",
            object_type=ObjectType.PREFERENCE,
            valid_from=NOW,
            valid_to=NOW + timedelta(seconds=1),
        ),
        ("alice", "expired-at-boundary", "v1"): _truth(
            "expired-at-boundary",
            object_type=ObjectType.PREFERENCE,
            valid_to=NOW,
        ),
        ("alice", "future", "v1"): _truth(
            "future",
            object_type=ObjectType.PREFERENCE,
            valid_from=NOW + timedelta(seconds=1),
        ),
    }

    out = fuse_retrieval(
        fts5_hits=hits,
        vector_hits=[],
        truth=truth,
        flt=_flt(
            object_types=[ObjectType.PREFERENCE],
            include_unscoped=True,
        ),
    )

    assert [candidate.memory_id for candidate in out] == ["effective"]


def test_preference_validity_requires_timezone_and_normalizes_to_utc():
    with pytest.raises(ValueError, match="valid_from 必须带时区"):
        _truth(
            "naive",
            object_type=ObjectType.PREFERENCE,
            valid_from=datetime(2026, 8, 22, 12, 0, 0),
        )

    offset_time = datetime(
        2026, 8, 22, 20, 0, 0, tzinfo=timezone(timedelta(hours=8))
    )
    truth = {
        ("alice", "normalized", "v1"): _truth(
            "normalized",
            object_type=ObjectType.PREFERENCE,
            valid_from=offset_time,
        )
    }
    out = fuse_retrieval(
        fts5_hits=[_hit("normalized", "v1", Channel.FTS5, 1)],
        vector_hits=[],
        truth=truth,
        flt=_flt(
            object_types=[ObjectType.PREFERENCE],
            include_unscoped=True,
        ),
    )

    assert out[0].valid_from == NOW
    assert out[0].valid_from.tzinfo is timezone.utc


def test_preference_with_multiple_current_versions_fails_closed():
    hits = [
        _hit("pref", "v1", Channel.FTS5, 1),
        _hit("pref", "v2", Channel.FTS5, 2),
    ]
    truth = {
        ("alice", "pref", "v1"): _truth(
            "pref", version_id="v1", object_type=ObjectType.PREFERENCE
        ),
        ("alice", "pref", "v2"): _truth(
            "pref", version_id="v2", object_type=ObjectType.PREFERENCE
        ),
    }

    out = fuse_retrieval(
        fts5_hits=hits,
        vector_hits=[],
        truth=truth,
        flt=_flt(
            object_types=[ObjectType.PREFERENCE],
            include_unscoped=True,
        ),
    )

    assert out == []


def test_multiple_current_versions_preserve_existing_knowledge_selection():
    hits = [
        _hit("knowledge", "v1", Channel.FTS5, 1),
        _hit("knowledge", "v2", Channel.FTS5, 2),
    ]
    truth = {
        ("alice", "knowledge", "v1"): _truth(
            "knowledge", version_id="v1"
        ),
        ("alice", "knowledge", "v2"): _truth(
            "knowledge", version_id="v2"
        ),
    }

    out = fuse_retrieval(
        fts5_hits=hits,
        vector_hits=[],
        truth=truth,
        flt=_flt(),
    )

    assert [candidate.version_id for candidate in out] == ["v2"]


def test_preference_scene_match_honors_allowed_scenes_and_unscoped_policy():
    hits = [
        _hit("work", "v1", Channel.FTS5, 1),
        _hit("global", "v1", Channel.FTS5, 2),
        _hit("home", "v1", Channel.FTS5, 3),
    ]
    truth = {
        ("alice", "work", "v1"): _truth(
            "work", object_type=ObjectType.PREFERENCE, scene_id="work"
        ),
        ("alice", "global", "v1"): _truth(
            "global", object_type=ObjectType.PREFERENCE
        ),
        ("alice", "home", "v1"): _truth(
            "home", object_type=ObjectType.PREFERENCE, scene_id="home"
        ),
    }

    scoped_only = fuse_retrieval(
        fts5_hits=hits,
        vector_hits=[],
        truth=truth,
        flt=_flt(
            object_types=[ObjectType.PREFERENCE],
            allowed_scene_ids=["work"],
            include_unscoped=False,
        ),
    )
    with_global = fuse_retrieval(
        fts5_hits=hits,
        vector_hits=[],
        truth=truth,
        flt=_flt(
            object_types=[ObjectType.PREFERENCE],
            allowed_scene_ids=["work"],
            include_unscoped=True,
        ),
    )

    assert [candidate.memory_id for candidate in scoped_only] == ["work"]
    assert [candidate.memory_id for candidate in with_global] == ["work", "global"]


def test_preference_scope_terms_require_each_key_and_an_intersecting_value():
    hits = [
        _hit("topic-a", "v1", Channel.FTS5, 1),
        _hit("topic-b", "v1", Channel.FTS5, 2),
        _hit("missing-tool-context", "v1", Channel.FTS5, 3),
        _hit("global", "v1", Channel.FTS5, 4),
    ]
    truth = {
        ("alice", "topic-a", "v1"): _truth(
            "topic-a",
            object_type=ObjectType.PREFERENCE,
            scope_terms={"topic": ["project-a"]},
        ),
        ("alice", "topic-b", "v1"): _truth(
            "topic-b",
            object_type=ObjectType.PREFERENCE,
            scope_terms={"topic": ["project-b"]},
        ),
        ("alice", "missing-tool-context", "v1"): _truth(
            "missing-tool-context",
            object_type=ObjectType.PREFERENCE,
            scope_terms={"tool": ["terminal"]},
        ),
        ("alice", "global", "v1"): _truth(
            "global", object_type=ObjectType.PREFERENCE
        ),
    }

    out = fuse_retrieval(
        fts5_hits=hits,
        vector_hits=[],
        truth=truth,
        flt=_flt(
            object_types=[ObjectType.PREFERENCE],
            include_unscoped=True,
            scope_terms={"topic": ["project-a"]},
        ),
    )

    assert [candidate.memory_id for candidate in out] == ["topic-a", "global"]


def test_preference_candidate_explains_rrf_and_passed_hard_filters():
    truth = {
        ("alice", "pref", "v2"): _truth(
            "pref",
            version_id="v2",
            object_type=ObjectType.PREFERENCE,
            scene_id="work",
            scope_terms={"topic": ["project-a"]},
            valid_from=NOW,
        )
    }

    out = fuse_retrieval(
        fts5_hits=[_hit("pref", "v2", Channel.FTS5, 1)],
        vector_hits=[_hit("pref", "v2", Channel.VECTOR, 2)],
        truth=truth,
        flt=_flt(
            object_types=[ObjectType.PREFERENCE],
            allowed_scene_ids=["work"],
            scope_terms={"topic": ["project-a"]},
        ),
        k=10,
    )

    assert len(out) == 1
    assert out[0].explanation == {
        "algorithm_version": "rrf-v1",
        "rrf_k": 10,
        "rrf_terms": pytest.approx({"fts5": 1 / 11, "vector": 1 / 12}),
        "degraded_channels": [],
        "rerank_version": None,
        "hard_filter": {
            "policy_version": "preference-filter/v1",
            "current_version": "passed",
            "validity": "passed",
            "scene": "allowed_scene",
            "scope": "terms_matched",
        },
    }


def test_adr001_golden_ordering():
    fts5 = [
        _hit("mem-a", "v1", Channel.FTS5, 1),
        _hit("mem-b", "v1", Channel.FTS5, 2),
        _hit("mem-c", "v1", Channel.FTS5, 1),
    ]
    vector = [
        _hit("mem-a", "v1", Channel.VECTOR, 3),
        _hit("mem-b", "v1", Channel.VECTOR, 2),
        _hit("mem-d", "v1", Channel.VECTOR, 1),
    ]
    truth = {
        ("alice", "mem-a", "v1"): _truth("mem-a", content="alpha"),
        ("alice", "mem-b", "v1"): _truth("mem-b", content="beta"),
        ("alice", "mem-c", "v1"): _truth("mem-c", content="gamma"),
        ("alice", "mem-d", "v1"): _truth("mem-d", content="delta"),
    }
    out = fuse_retrieval(fts5_hits=fts5, vector_hits=vector, truth=truth, flt=_flt())
    assert [c.memory_id for c in out] == ["mem-a", "mem-b", "mem-c", "mem-d"]
    assert out[0].rrf_score == pytest.approx(0.0322664585, abs=1e-9)
    assert out[1].rrf_score == pytest.approx(0.0322580645, abs=1e-9)
    assert out[2].rrf_score == pytest.approx(0.0163934426, abs=1e-9)
    assert out[3].rrf_score == pytest.approx(0.0163934426, abs=1e-9)


def test_stale_version_removed_before_aggregate():
    # ADR-001 golden case：stale v1 rank=1，current v2 rank=2，v1 必须在聚合前移除。
    fts5 = [_hit("mem-a", "v1", Channel.FTS5, 1), _hit("mem-a", "v2", Channel.FTS5, 2)]
    truth = {
        ("alice", "mem-a", "v1"): _truth("mem-a", version_id="v1", is_current=False),
        ("alice", "mem-a", "v2"): _truth("mem-a", version_id="v2", is_current=True),
    }
    out = fuse_retrieval(fts5_hits=fts5, vector_hits=[], truth=truth, flt=_flt())
    assert len(out) == 1
    assert out[0].version_id == "v2"
    assert out[0].rrf_score == pytest.approx(1 / 62, abs=1e-9)  # 仅 v2 rank=2


def test_cross_channel_cross_version_not_mixed():
    # FTS5 v1 + Vector v2，truth 有 v1/v2；current 唯一确定 v2，v1 rank 不得混入。
    fts5 = [_hit("mem-a", "v1", Channel.FTS5, 1)]
    vector = [_hit("mem-a", "v2", Channel.VECTOR, 1)]
    truth = {
        ("alice", "mem-a", "v1"): _truth("mem-a", version_id="v1", is_current=False),
        ("alice", "mem-a", "v2"): _truth("mem-a", version_id="v2", is_current=True),
    }
    out = fuse_retrieval(fts5_hits=fts5, vector_hits=vector, truth=truth, flt=_flt())
    assert len(out) == 1
    assert out[0].version_id == "v2"
    assert out[0].rrf_score == pytest.approx(1 / 61, abs=1e-9)  # 仅 v2 Vector rank=1
    assert out[0].channels == [Channel.VECTOR]


def test_stale_version_dropped():
    hits = [_hit("mem-a", "v1", Channel.FTS5, 1)]
    truth = {("alice", "mem-a", "v2"): _truth("mem-a", version_id="v2")}
    out = fuse_retrieval(fts5_hits=hits, vector_hits=[], truth=truth, flt=_flt())
    assert out == []


def test_cross_user_dropped():
    hits = [_hit("mem-a", "v1", Channel.FTS5, 1, user_id="bob")]
    truth = {("bob", "mem-a", "v1"): _truth("mem-a", user_id="bob")}
    out = fuse_retrieval(fts5_hits=hits, vector_hits=[], truth=truth, flt=_flt())
    assert out == []


def test_forgotten_status_dropped():
    hits = [_hit("mem-a", "v1", Channel.FTS5, 1)]
    truth = {("alice", "mem-a", "v1"): _truth("mem-a", status="forgotten")}
    out = fuse_retrieval(fts5_hits=hits, vector_hits=[], truth=truth, flt=_flt())
    assert out == []


def test_unresolved_conflict_dropped():
    # 未解决冲突命中必须在融合前消失（ADR-001 输入边界第 5 步）。
    hits = [_hit("mem-a", "v1", Channel.FTS5, 1)]
    truth = {("alice", "mem-a", "v1"): _truth("mem-a", conflict_state="unresolved")}
    out = fuse_retrieval(fts5_hits=hits, vector_hits=[], truth=truth, flt=_flt())
    assert out == []


def test_resolved_conflict_kept():
    # 已解决冲突命中可以保留。
    hits = [_hit("mem-a", "v1", Channel.FTS5, 1)]
    truth = {("alice", "mem-a", "v1"): _truth("mem-a", conflict_state="resolved")}
    out = fuse_retrieval(fts5_hits=hits, vector_hits=[], truth=truth, flt=_flt())
    assert [c.memory_id for c in out] == ["mem-a"]


def test_empty_result():
    out = fuse_retrieval(fts5_hits=[], vector_hits=[], truth={}, flt=_flt())
    assert out == []


def test_top_k_truncation():
    fts5 = [_hit("mem-a", "v1", Channel.FTS5, 1), _hit("mem-b", "v1", Channel.FTS5, 2)]
    truth = {
        ("alice", "mem-a", "v1"): _truth("mem-a"),
        ("alice", "mem-b", "v1"): _truth("mem-b"),
    }
    out = fuse_retrieval(fts5_hits=fts5, vector_hits=[], truth=truth, flt=_flt(), top_k=1)
    assert [c.memory_id for c in out] == ["mem-a"]


def test_fts5_index_returns_ranked_hits():
    idx = Fts5Index()
    idx.upsert("mem-a", "v1", "apple banana cherry", "alice")
    idx.upsert("mem-b", "v1", "apple banana", "alice")
    hits = idx.search("apple", "alice", top_n=5, now=NOW)
    assert all(h.channel is Channel.FTS5 for h in hits)
    assert [h.rank for h in hits] == [1, 2]



def test_rrf_k_param_actually_changes_score():
    # MEDIUM-4：k 必须真正传递到 RRF 评分，不同 k 得到不同分数。
    fts5 = [_hit("mem-a", "v1", Channel.FTS5, 1)]
    vector = [_hit("mem-a", "v1", Channel.VECTOR, 1)]
    truth = {("alice", "mem-a", "v1"): _truth("mem-a")}
    out10 = fuse_retrieval(fts5_hits=fts5, vector_hits=vector, truth=truth, flt=_flt(), k=10)
    out60 = fuse_retrieval(fts5_hits=fts5, vector_hits=vector, truth=truth, flt=_flt(), k=60)
    out100 = fuse_retrieval(fts5_hits=fts5, vector_hits=vector, truth=truth, flt=_flt(), k=100)
    assert out10[0].rrf_score == pytest.approx(1 / 11 + 1 / 11, abs=1e-9)
    assert out60[0].rrf_score == pytest.approx(1 / 61 + 1 / 61, abs=1e-9)
    assert out100[0].rrf_score == pytest.approx(1 / 101 + 1 / 101, abs=1e-9)
    assert out10[0].rrf_score > out60[0].rrf_score > out100[0].rrf_score


def test_fts5_user_isolation_before_topn():
    # MEDIUM-5：Bob 高分结果不能挤占 Alice 的 Top-N。
    idx = Fts5Index()
    idx.upsert("bob-1", "v1", "apple apple apple apple", "bob")
    idx.upsert("alice-1", "v1", "apple", "alice")
    hits = idx.search("apple", "alice", top_n=1, now=NOW)
    assert [h.memory_id for h in hits] == ["alice-1"]
