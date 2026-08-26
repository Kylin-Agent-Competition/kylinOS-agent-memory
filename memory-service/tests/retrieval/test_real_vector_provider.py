"""V006：vector_cli 子进程桥的 Python 包装测试（subprocess mock）。"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

import pytest

from retrieval.contracts import Channel
from retrieval.real_vector_provider import VectorCliClient, VectorCliError

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


class _FakeCompleted:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_search_maps_hits(monkeypatch):
    calls = []

    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        calls.append((cmd, input))
        return _FakeCompleted(json.dumps({
            "ok": True, "code": 0,
            "hits": [{"id": 1, "score": 1.0}, {"id": 2, "score": 0.0}, {"id": 3, "score": -1.0}],
        }))

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = VectorCliClient(cli_path="vector_cli")
    hits = client.search("c", [1, 0, 0, 0], 3, now=NOW, user_id="alice")

    assert len(hits) == 3
    assert [h.rank for h in hits] == [1, 2, 3]
    assert [h.memory_id for h in hits] == ["1", "2", "3"]
    assert all(h.channel is Channel.VECTOR for h in hits)
    assert hits[0].raw_score == 1.0
    assert calls[0][0][0] == "vector_cli"


def test_search_error_raises(monkeypatch):
    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        return _FakeCompleted(json.dumps({"ok": False, "code": 1002, "message": "collection not found"}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = VectorCliClient()
    with pytest.raises(VectorCliError) as exc:
        client.search("missing", [1, 0, 0, 0], 3, user_id="alice", now=NOW)
    assert exc.value.code == 1002
    assert "collection not found" in exc.value.message


def test_cli_nonzero_exit_raises(monkeypatch):
    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        return _FakeCompleted("", returncode=1, stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = VectorCliClient()
    with pytest.raises(VectorCliError):
        client.create_collection("c", 4)



def test_create_fails_closed_on_ok_false(monkeypatch):
    # HIGH-1：returncode=0 但 JSON ok=false，create 必须抛错，不能继续。
    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        return _FakeCompleted(json.dumps({"ok": False, "code": 1002, "message": "server failed"}), returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    cli = VectorCliClient()
    with pytest.raises(VectorCliError) as exc:
        cli.create_collection("c", 4)
    assert exc.value.code == 1002


def test_insert_fails_closed_on_ok_false(monkeypatch):
    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        return _FakeCompleted(json.dumps({"ok": False, "code": 1002, "message": "bad dim"}), returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    cli = VectorCliClient()
    with pytest.raises(VectorCliError):
        cli.insert("c", [1], [[1, 0, 0, 0]])


def test_drop_fails_closed_on_ok_false(monkeypatch):
    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        return _FakeCompleted(json.dumps({"ok": False, "code": 1002, "message": "server failed"}), returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    cli = VectorCliClient()
    with pytest.raises(VectorCliError):
        cli.drop_collection("c")


def test_drop_missing_collection_is_idempotent(monkeypatch):
    # drop 已不存在的 collection 是幂等成功，不抛。
    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        return _FakeCompleted(json.dumps({"ok": False, "code": 1002, "message": "collection not found"}), returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    cli = VectorCliClient()
    assert cli.drop_collection("missing")["ok"] is False
