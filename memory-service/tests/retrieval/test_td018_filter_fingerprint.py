"""TD-018：检索命中 filter_fingerprint 必须绑定请求过滤器的真实 digest。

覆盖：helper 确定性/区分性；FTS5 与 Vector 两层命中均携带请求过滤器 digest，
不再使用固定假值 `hmac-sha256:k1:` + `"a"*64`。
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

import pytest

from retrieval.contracts import (
    ObjectType,
    RetrievalFilter,
    SceneFilter,
    filter_fingerprint_digest,
)
from retrieval.fts5 import Fts5Index
from retrieval.real_vector_provider import VectorCliClient

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
OLD_FAKE = "hmac-sha256:k1:" + "a" * 64


def _filter(*, user_id="alice", scene_ids=None, include_unscoped=True, statuses=None):
    return RetrievalFilter(
        user_id=user_id,
        scene=SceneFilter(allowed_scene_ids=scene_ids or [], include_unscoped=include_unscoped),
        object_types=[ObjectType.KNOWLEDGE],
        allowed_memory_statuses=statuses or [],
        conflict_policy="exclude_unresolved",
        as_of=NOW,
    )


# ── helper 层 ──

def test_helper_deterministic_and_key_id_bound():
    flt = _filter()
    first = filter_fingerprint_digest(flt)
    assert filter_fingerprint_digest(flt) == first
    assert first.startswith("hmac-sha256:k1:")
    assert len(first.split(":")[-1]) == 64
    assert first != OLD_FAKE


def test_helper_distinguishes_filters():
    flt_a = _filter(statuses=["active"])
    flt_b = _filter(statuses=["candidate"])
    assert filter_fingerprint_digest(flt_a) != filter_fingerprint_digest(flt_b)


def test_helper_accepts_minimal_user_payload():
    dig = filter_fingerprint_digest({"user_id": "alice"})
    assert dig.startswith("hmac-sha256:k1:")


# ── FTS5 层 ──

def _fts_index():
    idx = Fts5Index()
    idx.upsert("m1", "v1", "hello memory", "alice")
    idx.upsert("m2", "v2", "hello memory", "alice")
    return idx


def test_fts5_hits_carry_request_filter_digest():
    idx = _fts_index()
    flt = _filter(statuses=[])  # scene 不参与 FTS5 SQL，仅作为请求过滤器承载
    hits = idx.search("hello", "alice", top_n=10, now=NOW, filter=flt)
    assert len(hits) == 2
    expected = filter_fingerprint_digest(flt)
    assert all(hit.filter_fingerprint == expected for hit in hits)
    assert all(hit.filter_fingerprint != OLD_FAKE for hit in hits)


def test_fts5_fingerprint_changes_with_request_filter():
    idx = _fts_index()
    flt_a = _filter(scene_ids=[])
    flt_b = _filter(scene_ids=["work"])
    hits_a = idx.search("hello", "alice", top_n=10, now=NOW, filter=flt_a)
    hits_b = idx.search("hello", "alice", top_n=10, now=NOW, filter=flt_b)
    assert hits_a[0].filter_fingerprint == filter_fingerprint_digest(flt_a)
    assert hits_b[0].filter_fingerprint == filter_fingerprint_digest(flt_b)
    assert hits_a[0].filter_fingerprint != hits_b[0].filter_fingerprint


def test_fts5_without_filter_stamps_user_scoped_digest():
    idx = _fts_index()
    hits = idx.search("hello", "alice", top_n=10, now=NOW)
    assert hits
    assert hits[0].filter_fingerprint == filter_fingerprint_digest({"user_id": "alice"})


# ── Vector CLI 层 ──

class _FakeCompleted:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _vector_hits(monkeypatch, flt):
    calls = []

    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        calls.append((cmd, input))
        return _FakeCompleted(json.dumps({
            "ok": True,
            "code": 0,
            "hits": [{"id": 1, "score": 0.9, "user_id": "alice", "version_id": "v1"}],
        }))

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = VectorCliClient(cli_path="vector_cli", expected_dimension=4)
    hits = client.search("c", [1, 0, 0, 0], 3, now=NOW, user_id="alice", filter=flt)
    assert len(hits) == 1
    return hits[0]


def test_vector_hits_carry_request_filter_digest(monkeypatch):
    flt = _filter(statuses=["active"])
    hit = _vector_hits(monkeypatch, flt)
    assert hit.filter_fingerprint == filter_fingerprint_digest(flt)
    assert hit.filter_fingerprint != OLD_FAKE


def test_vector_fingerprint_changes_with_request_filter(monkeypatch):
    flt_a = _filter(statuses=["active"])
    flt_b = _filter(statuses=["candidate"])
    hit_a = _vector_hits(monkeypatch, flt_a)
    hit_b = _vector_hits(monkeypatch, flt_b)
    assert hit_a.filter_fingerprint != hit_b.filter_fingerprint
