"""W2：服务故障结构化降级（L1 测试，mock subprocess / 注入故障）。"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

import pytest

from domain.enums import PreferenceScope
from retrieval.contracts import (
    Channel,
    ObjectType,
    RetrievalFilter,
    RetrievalHit,
    ScoreSemantics,
    SceneFilter,
)
from retrieval.fusion import TruthRecord, retrieve_graceful
from retrieval.real_vector_provider import VectorCliClient, VectorCliError

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


def _hit(mid, channel=Channel.FTS5, rank=1):
    return RetrievalHit(
        memory_id=mid,
        version_id="v1",
        user_id="alice",
        channel=channel,
        rank=rank,
        raw_score=0.0,
        score_semantics=ScoreSemantics.BM25 if channel is Channel.FTS5 else ScoreSemantics.SDK_SCORE_UNVERIFIED,
        provider="test",
        retrieved_at=NOW,
        filter_fingerprint="hmac-sha256:k1:" + "a" * 64,
    )


def _truth(mid, object_type=ObjectType.KNOWLEDGE, preference_scope=None):
    return TruthRecord(
        memory_id=mid,
        version_id="v1",
        user_id="alice",
        object_type=object_type,
        memory_type="long_term",
        memory_status="active",
        content="content-" + mid,
        sensitivity="internal",
        conflict_state="resolved",
        is_current=True,
        preference_scope=preference_scope,
    )


def _flt(object_types=None, scope_terms=None):
    return RetrievalFilter(
        user_id="alice",
        scene=SceneFilter(allowed_scene_ids=[], include_unscoped=True),
        scope_terms=scope_terms or {},
        object_types=object_types or [ObjectType.KNOWLEDGE],
        allowed_memory_statuses=["active"],
        allowed_sensitivity=["internal"],
        conflict_policy="resolve",
        as_of=NOW,
    )


class _FakeCompleted:
    def __init__(self, stdout, stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_cli_error_keeps_code_from_stdout_on_nonzero_exit(monkeypatch):
    # W2-2：连接失败时 vector_cli 输出 ok=false JSON 后 exit 1，桥必须保留 code=3。
    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        return _FakeCompleted(
            json.dumps({"ok": False, "code": 3, "message": "Failed to connect uri"}),
            stderr="connect retry failed",
            returncode=1,
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    cli = VectorCliClient(expected_dimension=4)
    with pytest.raises(VectorCliError) as exc:
        cli.search("c", [1, 0, 0, 0], 3, user_id="alice", now=NOW, filter=_flt())
    assert exc.value.code == 3
    assert "Failed to connect" in exc.value.message


def test_cli_error_extracts_json_from_noisy_stdout(monkeypatch):
    # SDK 连接重试日志污染 stdout，协议 JSON 在最后一行；桥必须从多行中提取。
    noisy_stdout = (
        "WARN connect milvus failed, code: 3, msg: Failed to connect uri, retry: 0\n"
        "ERROR connect milvus retry failed, code: 3, msg: Failed to connect uri\n"
        '{"ok": false, "code": 3, "message": "Failed to connect uri"}'
    )

    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        return _FakeCompleted(noisy_stdout, stderr="", returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    cli = VectorCliClient(expected_dimension=4)
    with pytest.raises(VectorCliError) as exc:
        cli.search("c", [1, 0, 0, 0], 3, user_id="alice", now=NOW, filter=_flt())
    assert exc.value.code == 3


def test_retrieve_graceful_vector_fault_keeps_fts5():
    # W2-3：vector 单路故障时，FTS5 命中仍返回，degraded 记录 vector。
    def fts5():
        return [_hit("mem-a", Channel.FTS5, 1)]

    def vector():
        raise VectorCliError(3, "Failed to connect uri")

    truth = {("alice", "mem-a", "v1"): _truth("mem-a")}
    outcome = retrieve_graceful(fts5_search=fts5, vector_search=vector, truth=truth, flt=_flt())
    assert [c.memory_id for c in outcome.candidates] == ["mem-a"]
    assert "vector" in outcome.degraded_channels
    assert outcome.degraded is True


def test_preference_explanation_records_observed_degraded_channel():
    def fts5():
        return [_hit("pref", Channel.FTS5, 1)]

    def vector():
        raise VectorCliError(3, "Failed to connect uri")

    truth = {
        ("alice", "pref", "v1"): _truth(
            "pref",
            object_type=ObjectType.PREFERENCE,
            preference_scope=PreferenceScope.GLOBAL,
        )
    }
    outcome = retrieve_graceful(
        fts5_search=fts5,
        vector_search=vector,
        truth=truth,
        flt=_flt(object_types=[ObjectType.PREFERENCE]),
    )

    assert [candidate.memory_id for candidate in outcome.candidates] == ["pref"]
    assert outcome.candidates[0].explanation["degraded_channels"] == ["vector"]


def test_preference_query_is_validated_before_provider_callbacks():
    called = []

    def fts5():
        called.append("fts5")
        return []

    def vector():
        called.append("vector")
        return []

    with pytest.raises(ValueError, match="invalid_argument"):
        retrieve_graceful(
            fts5_search=fts5,
            vector_search=vector,
            truth={},
            flt=_flt(
                object_types=[ObjectType.PREFERENCE],
                scope_terms={"unknown_scope": ["x"]},
            ),
        )

    assert called == []


def test_retrieve_graceful_both_fault_returns_empty():
    # 两路都故障 -> 空结果 + 两个 degraded 通道，不抛异常。
    def boom():
        raise RuntimeError("down")

    outcome = retrieve_graceful(fts5_search=boom, vector_search=boom, truth={}, flt=_flt())
    assert outcome.candidates == []
    assert set(outcome.degraded_channels) == {"fts5", "vector"}


def test_retrieve_graceful_no_fault_is_clean():
    def fts5():
        return [_hit("mem-a", Channel.FTS5, 1)]

    def vector():
        return []

    truth = {("alice", "mem-a", "v1"): _truth("mem-a")}
    outcome = retrieve_graceful(fts5_search=fts5, vector_search=vector, truth=truth, flt=_flt())
    assert [c.memory_id for c in outcome.candidates] == ["mem-a"]
    assert outcome.degraded is False
