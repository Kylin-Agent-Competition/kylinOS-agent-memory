"""TD-020：VectorCliClient 使用同一绝对 deadline_at，剩余预算逐层递减、过期 fail-closed。

覆盖：search/insert/delete 在 deadline 已过时不得调用 vector_cli；未过期时把剩余预算
传给 subprocess timeout 与 CLI 搜索 timeout(ms)；未提供 deadline 时保持原默认行为。
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from retrieval.contracts import ObjectType, RetrievalFilter, SceneFilter
from retrieval.real_vector_provider import VectorCliClient, VectorCliError
from retrieval.vector_sdk_errors import VectorSdkStatusCode

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


class _FakeCompleted:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _flt(user_id="alice"):
    return RetrievalFilter(
        user_id=user_id,
        scene=SceneFilter(allowed_scene_ids=[], include_unscoped=True),
        object_types=[ObjectType.KNOWLEDGE],
        allowed_memory_statuses=["active"],
        conflict_policy="exclude_unresolved",
        as_of=NOW,
    )


def _no_cli(*args, **kwargs):
    raise AssertionError("deadline 已过时不得调用 vector_cli")


def _ok_run(calls):
    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        calls.append({"cmd": cmd, "input": input, "timeout": timeout})
        return _FakeCompleted(json.dumps({"ok": True, "code": 0, "hits": [
            {"id": 1, "score": 0.5, "user_id": "alice", "version_id": "v1"},
        ]}))

    return fake_run


def test_search_deadline_expired_fails_closed_before_cli(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _no_cli)
    client = VectorCliClient(cli_path="vector_cli", expected_dimension=4)
    with pytest.raises(VectorCliError) as exc:
        client.search(
            "c", [1, 0, 0, 0], 3, now=NOW, user_id="alice",
            filter=_flt(), deadline_at=NOW,
        )
    assert exc.value.code == int(VectorSdkStatusCode.TIMEOUT)


def test_search_naive_deadline_rejected(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _no_cli)
    client = VectorCliClient(cli_path="vector_cli", expected_dimension=4)
    with pytest.raises(ValueError, match="deadline_at 必须带时区"):
        client.search(
            "c", [1, 0, 0, 0], 3, now=NOW, user_id="alice",
            filter=_flt(), deadline_at=datetime(2026, 8, 22, 12, 0, 0),
        )


def test_search_propagates_remaining_budget(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _ok_run(calls))
    client = VectorCliClient(cli_path="vector_cli", expected_dimension=4)
    hits = client.search(
        "c", [1, 0, 0, 0], 3, now=NOW, user_id="alice",
        filter=_flt(), deadline_at=NOW + timedelta(seconds=2),
    )
    assert len(hits) == 1
    record = calls[0]
    assert 1.9 <= record["timeout"] <= 2.1
    # cmd = [cli, "search", name, top_n, timeout_ms]
    assert record["cmd"][4] == "2000"


def test_search_without_deadline_keeps_defaults(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _ok_run(calls))
    client = VectorCliClient(cli_path="vector_cli", expected_dimension=4)
    client.search("c", [1, 0, 0, 0], 3, now=NOW, user_id="alice", filter=_flt())
    record = calls[0]
    assert record["cmd"][4] == "5000"
    assert record["timeout"] == 120.0


def test_insert_deadline_expired_fails_closed_before_cli(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _no_cli)
    client = VectorCliClient(cli_path="vector_cli")
    with pytest.raises(VectorCliError) as exc:
        client.insert(
            "c", [1], [[1.0, 0.0, 0.0, 0.0]],
            user_ids=["alice"], version_ids=["v1"], scene_ids=[""],
            memory_statuses=["active"], deleted_flags=[False],
            deadline_at=NOW, now=NOW,
        )
    assert exc.value.code == int(VectorSdkStatusCode.TIMEOUT)


def test_delete_deadline_expired_fails_closed_before_cli(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _no_cli)
    client = VectorCliClient(cli_path="vector_cli")
    with pytest.raises(VectorCliError) as exc:
        client.delete(
            "c", [1], user_id="alice", version_ids=["v1"],
            deadline_at=NOW, now=NOW,
        )
    assert exc.value.code == int(VectorSdkStatusCode.TIMEOUT)


def test_insert_propagates_remaining_budget(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _ok_run(calls))
    client = VectorCliClient(cli_path="vector_cli")
    client.insert(
        "c", [1], [[1.0, 0.0, 0.0, 0.0]],
        user_ids=["alice"], version_ids=["v1"], scene_ids=[""],
        memory_statuses=["active"], deleted_flags=[False],
        deadline_at=NOW + timedelta(seconds=5), now=NOW,
    )
    assert 4.9 <= calls[0]["timeout"] <= 5.1


def test_delete_propagates_remaining_budget(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _ok_run(calls))
    client = VectorCliClient(cli_path="vector_cli")
    client.delete(
        "c", [1], user_id="alice", version_ids=["v1"],
        deadline_at=NOW + timedelta(seconds=3), now=NOW,
    )
    assert 2.9 <= calls[0]["timeout"] <= 3.1

def test_subprocess_timeout_maps_to_deadline_exceeded(monkeypatch):
    """CLI 执行中预算耗尽：subprocess.TimeoutExpired 归一为 VectorCliError(TIMEOUT)。"""

    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired("vector_cli", timeout=kwargs.get("timeout", 120))

    monkeypatch.setattr(subprocess, "run", timed_out)
    client = VectorCliClient(cli_path="vector_cli", expected_dimension=4)
    with pytest.raises(VectorCliError) as exc:
        client.search(
            "c", [1, 0, 0, 0], 3, now=NOW, user_id="alice", filter=_flt(),
            deadline_at=NOW + timedelta(seconds=2),
        )
    assert exc.value.code == int(VectorSdkStatusCode.TIMEOUT)
