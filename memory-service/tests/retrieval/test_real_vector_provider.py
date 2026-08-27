"""V006：vector_cli 子进程桥的 Python 包装测试（subprocess mock）。"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

import pytest

from retrieval.contracts import Channel, ObjectType, RetrievalFilter, SceneFilter
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
            "hits": [
                {"id": 1, "score": 1.0, "user_id": "alice", "version_id": "v1"},
                {"id": 2, "score": 0.0, "user_id": "alice", "version_id": "v1"},
                {"id": 3, "score": -1.0, "user_id": "alice", "version_id": "v1"},
            ],
        }))

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = VectorCliClient(cli_path="vector_cli", expected_dimension=4)
    hits = client.search("c", [1, 0, 0, 0], 3, now=NOW, user_id="alice")

    assert len(hits) == 3
    assert [h.rank for h in hits] == [1, 2, 3]
    assert [h.memory_id for h in hits] == ["1", "2", "3"]
    assert all(h.channel is Channel.VECTOR for h in hits)
    assert hits[0].raw_score == 1.0
    assert calls[0][0][0] == "vector_cli"


def test_search_scopes_request_to_user_and_uses_returned_metadata(monkeypatch):
    """D6-B：真实桥必须请求服务端 user 过滤，且不得伪造命中的元数据。"""
    calls = []

    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        calls.append((cmd, input))
        return _FakeCompleted(json.dumps({
            "ok": True,
            "code": 0,
            "hits": [{
                "id": 7,
                "score": 0.75,
                "user_id": "alice",
                "version_id": "v3",
            }],
        }))

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = VectorCliClient(cli_path="vector_cli", expected_dimension=4)

    hits = client.search("d6_collection", [1, 0, 0, 0], 3, user_id="alice", now=NOW)

    assert json.loads(calls[0][1]) == {
        "vector": [1, 0, 0, 0],
        "filter": {
            "user_id": "alice",
            "allowed_scene_ids": [],
            "include_unscoped": False,
            "allowed_memory_statuses": [],
            "exclude_deleted": True,
        },
    }
    assert [(hit.memory_id, hit.version_id, hit.user_id) for hit in hits] == [
        ("7", "v3", "alice"),
    ]


def test_search_forwards_typed_scene_and_status_filter(monkeypatch):
    """D6-B：场景、状态与删除门禁由服务端以受控 filter 表达。"""
    calls = []

    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        calls.append((cmd, input))
        return _FakeCompleted(json.dumps({"ok": True, "code": 0, "hits": []}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    filter_ = RetrievalFilter(
        user_id="alice",
        scene=SceneFilter(allowed_scene_ids=["work", "home"], include_unscoped=True),
        object_types=[ObjectType.KNOWLEDGE],
        allowed_memory_statuses=["active", "candidate"],
        conflict_policy="exclude_unresolved",
        as_of=NOW,
    )

    VectorCliClient(cli_path="vector_cli", expected_dimension=4).search(
        "d6_collection",
        [1, 0, 0, 0],
        3,
        user_id="alice",
        filter=filter_,
        now=NOW,
    )

    assert json.loads(calls[0][1]) == {
        "vector": [1, 0, 0, 0],
        "filter": {
            "user_id": "alice",
            "allowed_scene_ids": ["home", "work"],
            "include_unscoped": True,
            "allowed_memory_statuses": ["active", "candidate"],
            "exclude_deleted": True,
        },
    }


def test_insert_forwards_filterable_metadata(monkeypatch):
    """D6-B：写入必须把检索所需标量元数据一同交给 Collection。"""
    calls = []

    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        calls.append((cmd, input))
        return _FakeCompleted(json.dumps({"ok": True, "code": 0}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    VectorCliClient(cli_path="vector_cli").insert(
        "d6_collection",
        [7],
        [[1, 0, 0, 0]],
        user_ids=["alice"],
        version_ids=["v3"],
        scene_ids=["work"],
        memory_statuses=["active"],
        deleted_flags=[False],
    )

    assert json.loads(calls[0][1]) == {
        "ids": [7],
        "vectors": [[1, 0, 0, 0]],
        "user_ids": ["alice"],
        "version_ids": ["v3"],
        "scene_ids": ["work"],
        "memory_statuses": ["active"],
        "deleted_flags": [False],
    }


def test_insert_rejects_empty_vector_before_invoking_cli(monkeypatch):
    """D6-B：空向量不是可写入的索引记录，必须在桥接前拒绝。"""
    def unexpected_cli(*args, **kwargs):
        raise AssertionError("empty vector must not reach vector_cli")

    monkeypatch.setattr(subprocess, "run", unexpected_cli)

    with pytest.raises(ValueError, match="向量不能为空"):
        VectorCliClient(cli_path="vector_cli").insert(
            "d6_collection",
            [7],
            [[]],
            user_ids=["alice"],
            version_ids=["v3"],
            scene_ids=["work"],
            memory_statuses=["active"],
            deleted_flags=[False],
        )


def test_insert_rejects_mismatched_dimension_before_invoking_cli(monkeypatch):
    """D6-B：写入维度不符合 Provider 配置时，必须在桥接前失败关闭。"""
    def unexpected_cli(*args, **kwargs):
        raise AssertionError("wrong-dimension vector must not reach vector_cli")

    monkeypatch.setattr(subprocess, "run", unexpected_cli)

    with pytest.raises(ValueError, match="写入向量维度必须等于 4"):
        VectorCliClient(cli_path="vector_cli", expected_dimension=4).insert(
            "d6_collection",
            [7],
            [[1, 0, 0]],
            user_ids=["alice"],
            version_ids=["v3"],
            scene_ids=["work"],
            memory_statuses=["active"],
            deleted_flags=[False],
        )


def test_search_rejects_mismatched_filter_user_before_invoking_cli(monkeypatch):
    """D6-B：调用参数与 typed filter 的用户不一致时必须 fail-close。"""
    def unexpected_cli(*args, **kwargs):
        raise AssertionError("mismatched user filter must not reach vector_cli")

    monkeypatch.setattr(subprocess, "run", unexpected_cli)
    filter_ = RetrievalFilter(
        user_id="bob",
        object_types=[ObjectType.KNOWLEDGE],
        conflict_policy="exclude_unresolved",
        as_of=NOW,
    )

    with pytest.raises(ValueError, match="必须与搜索 user_id 一致"):
        VectorCliClient(cli_path="vector_cli", expected_dimension=4).search(
            "d6_collection",
            [1, 0, 0, 0],
            3,
            user_id="alice",
            filter=filter_,
            now=NOW,
        )


@pytest.mark.parametrize(
    ("vector", "top_n", "message"),
    [
        ([], 3, "查询向量不能为空"),
        ([float("inf")], 3, "查询向量元素必须是有限实数"),
        ([1, 0, 0], 3, "查询向量维度必须等于 4"),
        ([1, 0, 0, 0], 0, "top_n 必须大于 0"),
    ],
)
def test_search_rejects_invalid_request_before_invoking_cli(monkeypatch, vector, top_n, message):
    """D6-B：无效搜索输入不能抵达 Vector CLI。"""
    def unexpected_cli(*args, **kwargs):
        raise AssertionError("invalid search request must not reach vector_cli")

    monkeypatch.setattr(subprocess, "run", unexpected_cli)

    with pytest.raises(ValueError, match=message):
        VectorCliClient(cli_path="vector_cli", expected_dimension=4).search(
            "d6_collection",
            vector,
            top_n,
            user_id="alice",
            now=NOW,
        )


def test_search_drops_malformed_or_cross_user_hits(monkeypatch):
    """D6-B：一个畸形或跨用户命中不得压制同批合法命中。"""
    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        return _FakeCompleted(json.dumps({
            "ok": True,
            "code": 0,
            "hits": [
                {"id": 1, "score": 0.9, "user_id": "alice", "version_id": "v1"},
                {"id": 2, "score": float("nan"), "user_id": "alice", "version_id": "v2"},
                {"id": 3, "score": 0.8, "user_id": "bob", "version_id": "v3"},
                {"id": 4, "score": 0.7, "user_id": "alice"},
            ],
        }))

    monkeypatch.setattr(subprocess, "run", fake_run)

    hits = VectorCliClient(cli_path="vector_cli", expected_dimension=4).search(
        "d6_collection", [1, 0, 0, 0], 10, user_id="alice", now=NOW,
    )

    assert [(hit.memory_id, hit.version_id, hit.user_id) for hit in hits] == [("1", "v1", "alice")]
    assert hits[0].diagnostics == {
        "raw_hit_count": 4,
        "valid_hit_count": 1,
        "dropped_hit_count": 3,
    }


def test_search_error_raises(monkeypatch):
    def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None):
        return _FakeCompleted(json.dumps({"ok": False, "code": 1002, "message": "collection not found"}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = VectorCliClient(expected_dimension=4)
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
        cli.insert(
            "c",
            [1],
            [[1, 0, 0, 0]],
            user_ids=["alice"],
            version_ids=["v1"],
            scene_ids=[""],
            memory_statuses=["active"],
            deleted_flags=[False],
        )


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
