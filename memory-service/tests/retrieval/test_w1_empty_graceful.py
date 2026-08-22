"""W1：空库返回可解释空结果（L1 契约测试，不依赖 VM）。"""

from __future__ import annotations

from datetime import datetime, timezone

from retrieval.contracts import ObjectType, RetrievalFilter
from retrieval.fts5 import Fts5Index
from retrieval.fusion import TruthRecord, fuse_retrieval

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


def _flt():
    return RetrievalFilter(
        user_id="alice",
        object_types=[ObjectType.KNOWLEDGE],
        allowed_memory_statuses=["active"],
        allowed_sensitivity=["internal"],
        conflict_policy="resolve",
        as_of=NOW,
    )


def _truth(mid):
    return TruthRecord(
        memory_id=mid,
        version_id="v1",
        user_id="alice",
        object_type=ObjectType.KNOWLEDGE,
        memory_type="long_term",
        memory_status="active",
        content="content-" + mid,
        sensitivity="internal",
        conflict_state="resolved",
    )


def test_empty_fts5_returns_no_hits():
    # W1-1：空 FTS5 索引不插入任何行，search 返回空。
    idx = Fts5Index()
    assert idx.search("apple", "alice", top_n=5, now=NOW) == []


def test_empty_both_channels_fuse_returns_empty():
    # W1-3：空 FTS5 + 空 Vector 走融合，返回空候选。
    out = fuse_retrieval(fts5_hits=[], vector_hits=[], truth={}, flt=_flt())
    assert out == []


def test_empty_hits_but_truth_present_returns_empty():
    # W1-4：没有任何命中，但 truth 表非空（回源无命中），仍返回空。
    truth = {
        ("alice", "mem-a", "v1"): _truth("mem-a"),
        ("alice", "mem-b", "v1"): _truth("mem-b"),
    }
    out = fuse_retrieval(fts5_hits=[], vector_hits=[], truth=truth, flt=_flt())
    assert out == []


def test_empty_result_is_stable_and_typed():
    # 空结果必须仍是 list[RetrievalCandidate]，而不是 None 或异常。
    out = fuse_retrieval(fts5_hits=[], vector_hits=[], truth={}, flt=_flt())
    assert isinstance(out, list)
    assert len(out) == 0
