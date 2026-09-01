"""D10-B：SQLite 真源快照读取器测试。"""

from __future__ import annotations

import pytest

from db.engine import create_db_engine, init_schema
from db.schema import memory_entries
from retrieval.contracts import Watermark, WatermarkDomain, WatermarkKind
from retrieval.sqlite_vector_snapshot import SqliteVectorSnapshotReader


@pytest.fixture()
def engine(tmp_path):
    value = create_db_engine(str(tmp_path / "snapshot.db"))
    init_schema(value)
    yield value
    value.dispose()


def _watermark() -> Watermark:
    return Watermark(
        domain=WatermarkDomain(
            scope_id="scope-alice",
            stream="sqlite-outbox",
            partition="alice",
            source_generation="sqlite-20260901",
        ),
        kind=WatermarkKind.MONOTONIC_INT,
        value=42,
    )


def _insert(conn, *, entry_id, user_id, version=1, is_deleted=0, content='{"index_text":"可索引"}'):
    conn.execute(
        memory_entries.insert().values(
            id=entry_id,
            user_id=user_id,
            entry_type="knowledge",
            content=content,
            confidence=0.8,
            version=version,
            is_deleted=is_deleted,
            created_at="2026-09-01T00:00:00+00:00",
            updated_at="2026-09-01T00:00:00+00:00",
            trace_id=None,
        )
    )


def _index_text(payload):
    return payload.get("index_text")


def test_reads_active_entries_in_primary_key_order_and_keeps_snapshot_metadata(engine):
    with engine.begin() as conn:
        _insert(conn, entry_id=10, user_id="alice", version=3, content='{"index_text":"后写入"}')
        _insert(conn, entry_id=2, user_id="alice", version=7, content='{"index_text":"先输出"}')
        _insert(conn, entry_id=3, user_id="bob", content='{"index_text":"不得泄露"}')
        _insert(conn, entry_id=4, user_id="alice", is_deleted=1)

    with engine.begin() as conn:
        snapshot = SqliteVectorSnapshotReader(_index_text).read(
            conn,
            user_id="alice",
            source_snapshot_id="snapshot-42",
            source_watermark=_watermark(),
        )

    assert snapshot.source_snapshot_id == "snapshot-42"
    assert snapshot.source_watermark == _watermark()
    assert [(record.memory_entry_id, record.source_version, record.index_text) for record in snapshot.records] == [
        (2, 7, "先输出"),
        (10, 3, "后写入"),
    ]
    assert snapshot.rejections == []


def test_rejects_malformed_or_unindexable_content_without_expanding_scope(engine):
    with engine.begin() as conn:
        _insert(conn, entry_id=1, user_id="alice", content="{")
        _insert(conn, entry_id=2, user_id="alice", content='{"index_text":"   "}')
        _insert(conn, entry_id=3, user_id="alice", content="[]")
        _insert(conn, entry_id=4, user_id="bob", content="{")

    with engine.begin() as conn:
        snapshot = SqliteVectorSnapshotReader(_index_text).read(
            conn,
            user_id="alice",
            source_snapshot_id="snapshot-43",
            source_watermark=_watermark(),
        )

    assert snapshot.records == []
    assert [(item.memory_entry_id, item.reason) for item in snapshot.rejections] == [
        (1, "content_json_invalid"),
        (2, "index_text_unavailable"),
        (3, "content_json_not_object"),
    ]


def test_rejects_resolver_exception_per_entry_and_continues_other_entries(engine):
    def resolver(payload):
        if payload["index_text"] == "坏记录":
            raise ValueError("解析失败")
        return payload["index_text"]

    with engine.begin() as conn:
        _insert(conn, entry_id=1, user_id="alice", content='{"index_text":"坏记录"}')
        _insert(conn, entry_id=2, user_id="alice", content='{"index_text":"好记录"}')

    with engine.begin() as conn:
        snapshot = SqliteVectorSnapshotReader(resolver).read(
            conn,
            user_id="alice",
            source_snapshot_id="snapshot-44",
            source_watermark=_watermark(),
        )

    assert [(record.memory_entry_id, record.index_text) for record in snapshot.records] == [(2, "好记录")]
    assert [(item.memory_entry_id, item.reason) for item in snapshot.rejections] == [
        (1, "index_text_unavailable"),
    ]


def test_rejects_nonpositive_source_version(engine):
    with engine.begin() as conn:
        _insert(conn, entry_id=1, user_id="alice", version=0)

    with engine.begin() as conn:
        snapshot = SqliteVectorSnapshotReader(_index_text).read(
            conn,
            user_id="alice",
            source_snapshot_id="snapshot-45",
            source_watermark=_watermark(),
        )

    assert snapshot.records == []
    assert [(item.memory_entry_id, item.reason) for item in snapshot.rejections] == [
        (1, "source_version_invalid"),
    ]


def test_requires_preopened_transaction_and_nonempty_snapshot_identity(engine):
    reader = SqliteVectorSnapshotReader(_index_text)
    with engine.connect() as conn:
        with pytest.raises(ValueError, match="SQLite 事务"):
            reader.read(
                conn,
                user_id="alice",
                source_snapshot_id="snapshot-46",
                source_watermark=_watermark(),
            )

    with engine.begin() as conn:
        with pytest.raises(ValueError, match="用户"):
            reader.read(
                conn,
                user_id=" ",
                source_snapshot_id="snapshot-46",
                source_watermark=_watermark(),
            )
        with pytest.raises(ValueError, match="快照标识"):
            reader.read(
                conn,
                user_id="alice",
                source_snapshot_id="",
                source_watermark=_watermark(),
            )
