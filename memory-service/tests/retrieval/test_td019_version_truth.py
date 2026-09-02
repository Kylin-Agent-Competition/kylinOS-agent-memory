"""TD-019：检索版本来自 SQLite 真源，不硬编码 "v1"；陈旧版本被 current-version 规则过滤。

覆盖：
- VectorCliClient.search 不注入/改写版本，透传引擎返回的 version_id（如 v9）；
- fusion 以 SQLite 真源 is_current 唯一确定 current version，陈旧版本命中在聚合前移除。
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

from retrieval.contracts import (
    Channel,
    KnowledgeIndexMetadata,
    ObjectType,
    RetrievalFilter,
    RetrievalHit,
    SceneFilter,
    ScoreSemantics,
)
from retrieval.fusion import TruthRecord, fuse_retrieval
from retrieval.real_vector_provider import VectorCliClient

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
DIG = "hmac-sha256:k1:" + "a" * 64


class _FakeCompleted:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _flt():
    return RetrievalFilter(
        user_id="alice",
        scene=SceneFilter(allowed_scene_ids=[], include_unscoped=True),
        object_types=[ObjectType.KNOWLEDGE],
        allowed_memory_statuses=["active"],
        conflict_policy="exclude_unresolved",
        as_of=NOW,
    )


def _hit(memory_id, version_id, rank):
    return RetrievalHit(
        memory_id=memory_id,
        version_id=version_id,
        user_id="alice",
        channel=Channel.FTS5,
        rank=rank,
        raw_score=0.0,
        score_semantics=ScoreSemantics.BM25,
        provider="fts5",
        retrieved_at=NOW,
        filter_fingerprint=DIG,
    )


def _truth(memory_id, version_id, *, is_current):
    return TruthRecord(
        memory_id=memory_id,
        version_id=version_id,
        user_id="alice",
        object_type=ObjectType.KNOWLEDGE,
        memory_type="long_term",
        memory_status="active",
        content="x",
        sensitivity="internal",
        conflict_state="resolved",
        is_current=is_current,
        knowledge=KnowledgeIndexMetadata(
            knowledge_type="legacy",
            source_event_id="evt",
            memory_status="active",
        ),
    )


# ── 客户端：版本透传，不硬编码 "v1" ──

def test_vector_client_passes_through_engine_version(monkeypatch):
    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        return _FakeCompleted(json.dumps({
            "ok": True, "code": 0,
            "hits": [{"id": 5, "score": 0.8, "user_id": "alice", "version_id": "v9"}],
        }))

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = VectorCliClient(cli_path="vector_cli", expected_dimension=4)
    hits = client.search(
        "c", [1, 0, 0, 0], 3, now=NOW, user_id="alice", filter=_flt()
    )
    assert len(hits) == 1
    assert hits[0].version_id == "v9"  # 不强制改写为 "v1"


# ── fusion：以 SQLite 真源 is_current 剔除陈旧版本 ──

def test_fusion_drops_stale_version_using_truth_current_flag():
    truth = {
        ("alice", "m1", "v1"): _truth("m1", "v1", is_current=False),
        ("alice", "m1", "v2"): _truth("m1", "v2", is_current=True),
    }
    candidates = fuse_retrieval(
        fts5_hits=[_hit("m1", "v1", 1), _hit("m1", "v2", 2)],
        vector_hits=[],
        truth=truth,
        flt=_flt(),
        k=60,
    )
    assert len(candidates) == 1
    assert candidates[0].memory_id == "m1"
    assert candidates[0].version_id == "v2"


def test_fusion_keeps_current_version_single_source():
    truth = {
        ("alice", "m1", "v2"): _truth("m1", "v2", is_current=True),
    }
    candidates = fuse_retrieval(
        fts5_hits=[_hit("m1", "v2", 1)],
        vector_hits=[],
        truth=truth,
        flt=_flt(),
        k=60,
    )
    assert [c.memory_id for c in candidates] == ["m1"]
    assert candidates[0].version_id == "v2"
