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


def _truth(memory_id, version_id="v1", user_id="alice", status="active", sensitivity="internal", content="x", object_type=ObjectType.KNOWLEDGE, conflict_state="resolved"):
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
