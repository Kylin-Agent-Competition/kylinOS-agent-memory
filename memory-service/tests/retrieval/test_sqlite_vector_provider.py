"""D10-B：SQLite 真源与真实 Vector CLI 的生产 Provider 接线测试。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from db.engine import create_db_engine, init_schema
from db.schema import memory_entries, vector_index_entries, vector_index_generations
from retrieval.contracts import (
    ConfirmationMode,
    IndexScope,
    IndexStateRequest,
    IndexStatus,
    RebuildReason,
    ResolvedBy,
    ResolvedDeleteSelector,
    SelectionMode,
    ScopeAuthorization,
    ScopeKind,
    VectorDeleteRequest,
    VectorRebuildRequest,
    Watermark,
    WatermarkDomain,
    WatermarkKind,
)
from retrieval.sqlite_vector_provider import SqliteVectorProvider
from fakes import DEFAULT_DIGEST_KEY, sign_request_payload


DIGEST = "hmac-sha256:k1:" + "a" * 64


class RecordingVectorClient:
    """Vector CLI 的外部边界替身，只记录已经受控的删除请求。"""

    def __init__(self) -> None:
        self.delete_calls: list[tuple[str, list[int], str, list[str]]] = []
        self.create_calls: list[tuple[str, int]] = []
        self.insert_calls: list[tuple[str, list[int], list[list[float]], dict]] = []
        self.drop_calls: list[str] = []
        self.fail_insert = False

    def delete(self, collection, ids, *, user_id, version_ids):
        self.delete_calls.append((collection, ids, user_id, version_ids))
        return {"ok": True, "code": 0}

    def create_collection(self, name, dim):
        self.create_calls.append((name, dim))
        return {"ok": True, "code": 0}

    def insert(self, name, ids, vectors, **metadata):
        self.insert_calls.append((name, ids, vectors, metadata))
        if self.fail_insert:
            raise RuntimeError("模拟 Vector 写入失败")
        return {"ok": True, "code": 0}

    def drop_collection(self, name):
        self.drop_calls.append(name)
        return {"ok": True, "code": 0}


class RecordingEmbeddingService:
    """A 轨批量 Embedding 接缝替身，返回真实协议形状的向量。"""

    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed_batch(self, texts, *, timeout_ms=30000):
        self.texts.extend(texts)
        return {
            "ok": True,
            "result": {
                "vectors": [
                    {"vector": [0.6, 0.8], "dimension": 2, "l2_norm": 1.0}
                    for _ in texts
                ]
            },
        }


@pytest.fixture()
def engine(tmp_path):
    value = create_db_engine(str(tmp_path / "provider.db"))
    init_schema(value)
    yield value
    value.dispose()


def _watermark() -> Watermark:
    return Watermark(
        domain=WatermarkDomain(
            scope_id="scope-alice",
            stream="forget-outbox",
            partition="alice",
            source_generation="sqlite-d10",
        ),
        kind=WatermarkKind.MONOTONIC_INT,
        value=7,
    )


def _delete_request() -> VectorDeleteRequest:
    selector = ResolvedDeleteSelector(
        user_id="alice",
        memory_ids=["42"],
        version_ids=["v1"],
        selection_mode=SelectionMode.SINGLE_ITEM,
        selection_hash=DIGEST,
        resolved_by=ResolvedBy.SYSTEM,
        preview_ref="preview-42",
        preview_hash=DIGEST,
        confirmation_mode=ConfirmationMode.EXPLICIT,
        confirmation_ref="confirmation-42",
    )
    request = VectorDeleteRequest(
        request_id="delete-42",
        trace_id="trace-42",
        user_id="alice",
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        idempotency_key="idem-42",
        payload_hash=DIGEST,
        index_generation="generation-1",
        source_watermark=_watermark(),
        selector=selector,
    )
    return sign_request_payload(request, key=DEFAULT_DIGEST_KEY)


def _batch_delete_without_versions_request() -> VectorDeleteRequest:
    selector = ResolvedDeleteSelector(
        user_id="alice",
        memory_ids=["42"],
        version_ids=None,
        selection_mode=SelectionMode.RESOLVED_BATCH,
        selection_hash=DIGEST,
        resolved_by=ResolvedBy.SYSTEM,
        preview_ref="preview-batch-42",
        preview_hash=DIGEST,
        confirmation_mode=ConfirmationMode.EXPLICIT,
        confirmation_ref="confirmation-batch-42",
    )
    request = VectorDeleteRequest(
        request_id="delete-batch-42",
        trace_id="trace-batch-42",
        user_id="alice",
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        idempotency_key="idem-batch-42",
        payload_hash=DIGEST,
        index_generation="generation-1",
        source_watermark=_watermark(),
        selector=selector,
    )
    return sign_request_payload(request, key=DEFAULT_DIGEST_KEY)


def _rebuild_request() -> VectorRebuildRequest:
    scope = IndexScope(
        scope_id="scope-alice",
        kind=ScopeKind.USER,
        user_id="alice",
        scope_fingerprint=DIGEST,
    )
    request = VectorRebuildRequest(
        request_id="rebuild-2",
        trace_id="trace-rebuild-2",
        user_id="alice",
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        idempotency_key="rebuild-idem-2",
        payload_hash=DIGEST,
        source_snapshot_id="snapshot-2",
        source_watermark=_watermark(),
        target_generation="generation-2",
        schema_version="vector-schema-v1",
        reason=RebuildReason.REPAIR,
        scope=scope,
        scope_authorization=ScopeAuthorization(
            actor_ref="d-forget-worker",
            authorization_ref="authorization-2",
            scope_id="scope-alice",
            allowed_operations=["rebuild"],
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        ),
    )
    return sign_request_payload(request, key=DEFAULT_DIGEST_KEY)


def _index_state_request() -> IndexStateRequest:
    return IndexStateRequest(
        request_id="state-1",
        trace_id="trace-state-1",
        scope=IndexScope(
            scope_id="scope-alice",
            kind=ScopeKind.USER,
            user_id="alice",
            scope_fingerprint=DIGEST,
        ),
        scope_authorization=ScopeAuthorization(
            actor_ref="d-forget-worker",
            authorization_ref="authorization-state-1",
            scope_id="scope-alice",
            allowed_operations=["get_index_state"],
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        ),
        required_watermark=_watermark(),
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )


def test_delete_maps_confirmed_soft_deleted_memory_to_numeric_vector_primary_key(engine):
    """D10-B：软删已提交后仍按确认版本精确清理 Vector，不以当前版本覆盖它。"""
    client = RecordingVectorClient()
    with engine.begin() as conn:
        conn.execute(
            memory_entries.insert().values(
                id=42,
                user_id="alice",
                entry_type="knowledge",
                content='{"index_text":"已遗忘内容"}',
                confidence=0.8,
                version=2,
                is_deleted=1,
                created_at="2026-09-01T00:00:00+00:00",
                updated_at="2026-09-01T00:01:00+00:00",
                trace_id="trace-42",
            )
        )
        conn.execute(
            vector_index_generations.insert().values(
                scope_id="scope-alice",
                generation="generation-1",
                collection_name="d10b_scope_alice_generation_1",
                status="ready",
            )
        )
        conn.execute(
            vector_index_entries.insert().values(
                scope_id="scope-alice",
                generation="generation-1",
                user_id="alice",
                memory_entry_id=42,
                version_id="v1",
                is_active=1,
            )
        )

    result = SqliteVectorProvider(
        engine,
        vector_client=client,
        digest_keys={"k1": DEFAULT_DIGEST_KEY},
    ).delete(_delete_request())

    assert result.ok
    assert result.value.matched_count == 1
    assert result.value.deleted_count == 1
    assert result.value.not_matched_ids == []
    assert client.delete_calls == [
        ("d10b_scope_alice_generation_1", [42], "alice", ["v1"])
    ]
    with engine.connect() as conn:
        active = conn.execute(
            vector_index_entries.select().with_only_columns(vector_index_entries.c.is_active)
        ).scalar_one()
        stored_watermark = conn.execute(
            vector_index_generations.select()
            .with_only_columns(vector_index_generations.c.source_watermark)
        ).scalar_one()
    assert active == 0
    assert Watermark.model_validate(json.loads(stored_watermark)) == _watermark()


def test_delete_replays_persisted_result_without_second_vector_effect(engine):
    """D10-B：同一确认删除的重放返回首次账本结果，不重复调用 Vector。"""
    client = RecordingVectorClient()
    with engine.begin() as conn:
        conn.execute(
            memory_entries.insert().values(
                id=42,
                user_id="alice",
                entry_type="knowledge",
                content='{"index_text":"已遗忘内容"}',
                confidence=0.8,
                version=2,
                is_deleted=1,
                created_at="2026-09-01T00:00:00+00:00",
                updated_at="2026-09-01T00:01:00+00:00",
                trace_id="trace-42",
            )
        )
        conn.execute(
            vector_index_generations.insert().values(
                scope_id="scope-alice",
                generation="generation-1",
                collection_name="d10b_scope_alice_generation_1",
                status="ready",
            )
        )
        conn.execute(
            vector_index_entries.insert().values(
                scope_id="scope-alice",
                generation="generation-1",
                user_id="alice",
                memory_entry_id=42,
                version_id="v1",
                is_active=1,
            )
        )

    provider = SqliteVectorProvider(
        engine,
        vector_client=client,
        digest_keys={"k1": DEFAULT_DIGEST_KEY},
    )
    first = provider.delete(_delete_request())
    replay = provider.delete(_delete_request())

    assert first.ok and replay.ok
    assert replay.value == first.value
    assert len(client.delete_calls) == 1


def test_delete_rejects_batch_selector_without_paired_versions_before_vector_effect(engine):
    """D10-B：无法精确匹配版本的确认批次不得抵达 Vector CLI。"""
    client = RecordingVectorClient()

    result = SqliteVectorProvider(
        engine,
        vector_client=client,
        digest_keys={"k1": DEFAULT_DIGEST_KEY},
    ).delete(_batch_delete_without_versions_request())

    assert not result.ok
    assert result.error.code.value == "invalid_argument"
    assert client.delete_calls == []


def test_rebuild_uses_sqlite_snapshot_and_embedding_then_switches_serving_generation(engine):
    """D10-B：重建仅在快照、向量写入和账本校验完成后才切换 serving 代次。"""
    client = RecordingVectorClient()
    embedding = RecordingEmbeddingService()
    with engine.begin() as conn:
        conn.execute(
            memory_entries.insert().values(
                id=11,
                user_id="alice",
                entry_type="knowledge",
                content='{"index_text":"可重建索引文本"}',
                confidence=0.8,
                version=3,
                is_deleted=0,
                created_at="2026-09-01T00:00:00+00:00",
                updated_at="2026-09-01T00:00:00+00:00",
                trace_id="trace-rebuild-2",
            )
        )
        conn.execute(
            vector_index_generations.insert().values(
                scope_id="scope-alice",
                generation="generation-1",
                collection_name="d10b_scope_alice_generation_1",
                status="ready",
                is_serving=1,
            )
        )

    result = SqliteVectorProvider(
        engine,
        vector_client=client,
        embedding_service=embedding,
        index_text_resolver=lambda payload: payload.get("index_text"),
        dimension=2,
        digest_keys={"k1": DEFAULT_DIGEST_KEY},
    ).rebuild(_rebuild_request())

    assert result.ok
    assert result.value.read_count == 1
    assert result.value.indexed_count == 1
    assert result.value.rejected_count == 0
    assert result.value.verified is True
    assert result.value.activated is True
    assert result.value.previous_generation == "generation-1"
    assert embedding.texts == ["可重建索引文本"]
    assert client.create_calls == [("d10b_scope_alice_generation_2", 2)]
    assert client.insert_calls[0][0] == "d10b_scope_alice_generation_2"
    assert client.insert_calls[0][1] == [11]
    assert client.insert_calls[0][2] == [[0.6, 0.8]]
    with engine.connect() as conn:
        serving = conn.execute(
            vector_index_generations.select()
            .with_only_columns(vector_index_generations.c.generation)
            .where(vector_index_generations.c.scope_id == "scope-alice")
            .where(vector_index_generations.c.is_serving == 1)
        ).scalar_one()
        indexed = conn.execute(
            vector_index_entries.select()
            .with_only_columns(vector_index_entries.c.version_id)
            .where(vector_index_entries.c.generation == "generation-2")
        ).scalar_one()
        snapshot_digest = conn.execute(
            vector_index_generations.select()
            .with_only_columns(vector_index_generations.c.record_digest)
            .where(vector_index_generations.c.generation == "generation-2")
        ).scalar_one()
    assert serving == "generation-2"
    assert indexed == "v3"
    assert snapshot_digest.startswith("hmac-sha256:k1:")


def test_rebuild_failure_keeps_previous_serving_generation(engine):
    """D10-B：新代次写入失败时必须回收候选集合，旧 serving 代次保持可用。"""
    client = RecordingVectorClient()
    client.fail_insert = True
    embedding = RecordingEmbeddingService()
    with engine.begin() as conn:
        conn.execute(
            memory_entries.insert().values(
                id=11,
                user_id="alice",
                entry_type="knowledge",
                content='{"index_text":"可重建索引文本"}',
                confidence=0.8,
                version=3,
                is_deleted=0,
                created_at="2026-09-01T00:00:00+00:00",
                updated_at="2026-09-01T00:00:00+00:00",
                trace_id="trace-rebuild-failure",
            )
        )
        conn.execute(
            vector_index_generations.insert().values(
                scope_id="scope-alice",
                generation="generation-1",
                collection_name="d10b_scope_alice_generation_1",
                status="ready",
                is_serving=1,
            )
        )

    result = SqliteVectorProvider(
        engine,
        vector_client=client,
        embedding_service=embedding,
        index_text_resolver=lambda payload: payload.get("index_text"),
        dimension=2,
        digest_keys={"k1": DEFAULT_DIGEST_KEY},
    ).rebuild(_rebuild_request())

    assert not result.ok
    assert result.error.code.value == "provider_unavailable"
    assert client.drop_calls == ["d10b_scope_alice_generation_2"]
    with engine.connect() as conn:
        serving = conn.execute(
            vector_index_generations.select()
            .with_only_columns(vector_index_generations.c.generation)
            .where(vector_index_generations.c.scope_id == "scope-alice")
            .where(vector_index_generations.c.is_serving == 1)
        ).scalar_one()
        failed = conn.execute(
            vector_index_generations.select()
            .with_only_columns(vector_index_generations.c.status)
            .where(vector_index_generations.c.generation == "generation-2")
        ).scalar_one()
    assert serving == "generation-1"
    assert failed == "failed"


def test_rebuild_replays_persisted_result_without_second_embedding_or_collection(engine):
    """D10-B：同一重建请求的重放只返回首次结果，不重复产生外部副作用。"""
    client = RecordingVectorClient()
    embedding = RecordingEmbeddingService()
    with engine.begin() as conn:
        conn.execute(
            memory_entries.insert().values(
                id=11,
                user_id="alice",
                entry_type="knowledge",
                content='{"index_text":"可重建索引文本"}',
                confidence=0.8,
                version=3,
                is_deleted=0,
                created_at="2026-09-01T00:00:00+00:00",
                updated_at="2026-09-01T00:00:00+00:00",
                trace_id="trace-rebuild-2",
            )
        )
        conn.execute(
            vector_index_generations.insert().values(
                scope_id="scope-alice",
                generation="generation-1",
                collection_name="d10b_scope_alice_generation_1",
                status="ready",
                is_serving=1,
            )
        )

    provider = SqliteVectorProvider(
        engine,
        vector_client=client,
        embedding_service=embedding,
        index_text_resolver=lambda payload: payload.get("index_text"),
        dimension=2,
        digest_keys={"k1": DEFAULT_DIGEST_KEY},
    )
    request = _rebuild_request()
    first = provider.rebuild(request)
    replay = provider.rebuild(request)

    assert first.ok and replay.ok
    assert replay.value == first.value
    assert embedding.texts == ["可重建索引文本"]
    assert len(client.create_calls) == 1


def test_get_index_state_reads_serving_generation_without_vector_side_effect(engine):
    """D10-B：索引状态读取只返回 SQLite 账本，不触发 Vector 或 Embedding。"""
    client = RecordingVectorClient()
    with engine.begin() as conn:
        conn.execute(
            vector_index_generations.insert().values(
                scope_id="scope-alice",
                generation="generation-2",
                collection_name="d10b_scope_alice_generation_2",
                status="ready",
                schema_version="vector-schema-v1",
                source_snapshot_id="snapshot-2",
                source_watermark=json.dumps(_watermark().model_dump(mode="json")),
                record_count=3,
                is_serving=1,
            )
        )

    result = SqliteVectorProvider(
        engine,
        vector_client=client,
        digest_keys={"k1": DEFAULT_DIGEST_KEY},
    ).get_index_state(_index_state_request())

    assert result.ok
    assert result.value.status is IndexStatus.READY
    assert result.value.is_queryable is True
    assert result.value.serving_generation == "generation-2"
    assert result.value.record_count == 3
    assert result.value.applied_watermark == _watermark()
    assert result.value.required_watermark == _watermark()
    assert client.delete_calls == []
    assert client.create_calls == []



def _expired(request):
    """把已签名请求的截止时间改为过去；deadline_at 不参与摘要，payload_hash 保持有效。"""
    return request.model_copy(
        update={"deadline_at": datetime.now(timezone.utc) - timedelta(minutes=1)}
    )


def test_delete_deadline_exceeded_fails_closed_without_vector_effect(engine):
    """D10-B：删除请求超期后失败关闭，不触碰 Vector CLI。"""
    client = RecordingVectorClient()
    result = SqliteVectorProvider(
        engine, vector_client=client, digest_keys={"k1": DEFAULT_DIGEST_KEY}
    ).delete(_expired(_delete_request()))

    assert not result.ok
    assert result.error.code.value == "deadline_exceeded"
    assert client.delete_calls == []


def test_rebuild_deadline_exceeded_fails_closed_without_side_effect(engine):
    """D10-B：重建请求超期后失败关闭，不创建 Collection、不调用 Embedding。"""
    client = RecordingVectorClient()
    embedding = RecordingEmbeddingService()
    result = SqliteVectorProvider(
        engine,
        vector_client=client,
        embedding_service=embedding,
        index_text_resolver=lambda payload: payload.get("index_text"),
        dimension=2,
        digest_keys={"k1": DEFAULT_DIGEST_KEY},
    ).rebuild(_expired(_rebuild_request()))

    assert not result.ok
    assert result.error.code.value == "deadline_exceeded"
    assert client.create_calls == []
    assert embedding.texts == []


def test_get_index_state_deadline_exceeded_fails_closed(engine):
    """D10-B：状态读取超期后失败关闭，不触发任何外部操作。"""
    client = RecordingVectorClient()
    request = _index_state_request().model_copy(
        update={"deadline_at": datetime.now(timezone.utc) - timedelta(minutes=1)}
    )
    result = SqliteVectorProvider(
        engine, vector_client=client, digest_keys={"k1": DEFAULT_DIGEST_KEY}
    ).get_index_state(request)

    assert not result.ok
    assert result.error.code.value == "deadline_exceeded"
    assert client.create_calls == []
    assert client.delete_calls == []


def test_delete_and_serving_state_recover_after_provider_restart(tmp_path):
    """D10-B：服务重启后，幂等回执与 serving 代次从同一 SQLite 真源恢复，不重复调用 Vector。"""
    db_path = tmp_path / "restart.db"
    engine = create_db_engine(str(db_path))
    init_schema(engine)
    client = RecordingVectorClient()
    with engine.begin() as conn:
        conn.execute(
            memory_entries.insert().values(
                id=42,
                user_id="alice",
                entry_type="knowledge",
                content='{"index_text":"已遗忘内容"}',
                confidence=0.8,
                version=2,
                is_deleted=1,
                created_at="2026-09-01T00:00:00+00:00",
                updated_at="2026-09-01T00:01:00+00:00",
                trace_id="trace-restart-42",
            )
        )
        conn.execute(
            vector_index_generations.insert().values(
                scope_id="scope-alice",
                generation="generation-1",
                collection_name="d10b_scope_alice_generation_1",
                status="ready",
                is_serving=1,
                source_watermark=json.dumps(_watermark().model_dump(mode="json")),
            )
        )
        conn.execute(
            vector_index_entries.insert().values(
                scope_id="scope-alice",
                generation="generation-1",
                user_id="alice",
                memory_entry_id=42,
                version_id="v1",
                is_active=1,
            )
        )

    first = SqliteVectorProvider(
        engine, vector_client=client, digest_keys={"k1": DEFAULT_DIGEST_KEY}
    ).delete(_delete_request())
    assert first.ok
    assert len(client.delete_calls) == 1
    engine.dispose()

    engine2 = create_db_engine(str(db_path))
    try:
        client2 = RecordingVectorClient()
        provider2 = SqliteVectorProvider(
            engine2, vector_client=client2, digest_keys={"k1": DEFAULT_DIGEST_KEY}
        )
        replay = provider2.delete(_delete_request())
        assert replay.ok
        assert replay.value == first.value
        assert client2.delete_calls == []

        state = provider2.get_index_state(_index_state_request())
        assert state.ok
        assert state.value.serving_generation == "generation-1"
        assert state.value.status is IndexStatus.READY
    finally:
        engine2.dispose()
