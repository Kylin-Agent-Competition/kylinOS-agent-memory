"""V006：FTS5 + Vector 融合编排测试（回源硬过滤 + rrf-v1 + 统一候选）。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from retrieval.contracts import (
    Channel,
    ObjectType,
    RetrievalFilter,
    RetrievalHit,
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


def _truth(memory_id, version_id="v1", user_id="alice", status="active", sensitivity="internal", content="x", object_type=ObjectType.KNOWLEDGE):
    return TruthRecord(
        memory_id=memory_id,
        version_id=version_id,
        user_id=user_id,
        object_type=object_type,
        memory_type="long_term",
        memory_status=status,
        content=content,
        sensitivity=sensitivity,
        conflict_state="resolved",
    )


def _flt(statuses=None, sensitivity=None):
    return RetrievalFilter(
        user_id="alice",
        object_types=[ObjectType.KNOWLEDGE],
        allowed_memory_statuses=statuses or ["active"],
        allowed_sensitivity=sensitivity or ["internal"],
        conflict_policy="resolve",
        as_of=NOW,
    )


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
    idx.upsert("mem-a", "v1", "apple banana cherry")
    idx.upsert("mem-b", "v1", "apple banana")
    hits = idx.search("apple", "alice", top_n=5, now=NOW)
    assert all(h.channel is Channel.FTS5 for h in hits)
    assert [h.rank for h in hits] == [1, 2]
