from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import build_vector_provider
from db import repositories as repo
from db.engine import create_db_engine, init_schema
from db.schema import vector_index_entries, vector_index_generations, vector_index_receipts
from outbox.worker import OutboxWorker
from retrieval.contracts import (
    ObjectType,
    VectorRecord,
    VectorUpsertRequest,
    Watermark,
    WatermarkDomain,
    WatermarkKind,
    digest_from_canonical,
)
from retrieval.sqlite_vector_provider import SqliteVectorProvider


KEY_ID = "d9d-internal"
KEY = b"kylin-memory-d9d-internal"


class RecordingVectorClient:
    def __init__(self) -> None:
        self.create_calls: list[tuple[str, int]] = []
        self.insert_calls: list[tuple[str, list[int], list[list[float]], dict]] = []

    def create_collection(self, name: str, dimension: int) -> dict:
        self.create_calls.append((name, dimension))
        return {"ok": True}

    def insert(self, name: str, ids: list[int], vectors: list[list[float]], **metadata) -> dict:
        self.insert_calls.append((name, ids, vectors, metadata))
        return {"ok": True}


def _watermark(value: int = 1) -> Watermark:
    return Watermark(
        domain=WatermarkDomain(
            scope_id="user:alice",
            stream="memory_upserted",
            partition="default",
            source_generation="v1",
        ),
        kind=WatermarkKind.MONOTONIC_INT,
        value=value,
    )


def _request(*, idempotency_key: str = "memory:42:v1") -> VectorUpsertRequest:
    request = VectorUpsertRequest(
        request_id="request-42",
        trace_id="trace-42",
        user_id="alice",
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        idempotency_key=idempotency_key,
        payload_hash="hmac-sha256:d9d-internal:" + "0" * 64,
        index_generation="d13a-live",
        source_watermark=_watermark(),
        records=[
            VectorRecord(
                memory_id="42",
                version_id="v1",
                user_id="alice",
                vector=[0.6, 0.8],
                object_type=ObjectType.KNOWLEDGE,
                index_text_hash="hmac-sha256:d9d-internal:" + "1" * 64,
            )
        ],
    )
    return request.model_copy(update={
        "payload_hash": digest_from_canonical(
            KEY_ID,
            KEY,
            request.model_dump(
                mode="json",
                exclude={"request_id", "trace_id", "deadline_at", "payload_hash"},
            ),
        )
    })


def test_real_provider_upsert_writes_vector_and_sqlite_ledger(tmp_path):
    engine = create_db_engine(str(tmp_path / "chain.db"))
    init_schema(engine)
    client = RecordingVectorClient()
    provider = SqliteVectorProvider(
        engine,
        vector_client=client,
        digest_keys={KEY_ID: KEY},
        dimension=2,
    )

    first = provider.upsert(_request())
    replay = provider.upsert(_request())

    assert first.ok and replay.ok
    assert replay.value == first.value
    assert len(client.create_calls) == 1
    assert len(client.insert_calls) == 1
    with engine.connect() as conn:
        entry = conn.execute(select(vector_index_entries)).mappings().one()
        receipt = conn.execute(select(vector_index_receipts)).mappings().one()
        generation = conn.execute(select(vector_index_generations)).mappings().one()
    assert entry["memory_entry_id"] == 42
    assert entry["is_active"] == 1
    assert receipt["operation"] == "upsert"
    assert generation["status"] == "ready"
    assert generation["record_count"] == 1


def test_worker_routes_memory_upserted_to_real_provider(tmp_path):
    engine = create_db_engine(str(tmp_path / "worker.db"))
    init_schema(engine)
    client = RecordingVectorClient()
    provider = SqliteVectorProvider(
        engine,
        vector_client=client,
        digest_keys={KEY_ID: KEY},
        dimension=2,
    )
    from outbox.router import build_outbox_router

    request = _request()
    payload = {
        "event_id": "evt-42",
        "trace_id": "trace-42",
        "memory_id": "42",
        "version_id": "v1",
        "user_id": "alice",
        "vector": [0.6, 0.8],
        "object_type": "knowledge",
        "index_text_hash": "hmac-sha256:d9d-internal:" + "1" * 64,
        "index_generation": request.index_generation,
        "source_watermark_value": 1,
        "idempotency_key": request.idempotency_key,
    }
    with engine.begin() as conn:
        repo.enqueue_outbox(
            conn,
            aggregate_type="memory",
            aggregate_id="42",
            event_type=repo.EVENT_MEMORY_UPSERTED,
            payload=payload,
        )

    worker = OutboxWorker(
        engine,
        poll_interval_s=1,
        max_retries=0,
        consumer=build_outbox_router(vector_provider=provider).route,
    )
    worker._poll_once()
    assert worker.metrics()["backlog"] == 0
    assert worker.metrics()["dead_letter"] == 0
    assert len(client.insert_calls) == 1
    worker.stop()


def test_app_builds_real_provider_only_when_vector_cli_is_configured(tmp_path):
    engine = create_db_engine(str(tmp_path / "app.db"))
    init_schema(engine)

    assert build_vector_provider(engine, cli_path=None, dimension=None) is None
    provider = build_vector_provider(engine, cli_path="/usr/local/bin/vector_cli", dimension=2)
    assert isinstance(provider, SqliteVectorProvider)
    assert provider._vector_client.cli_path == "/usr/local/bin/vector_cli"
    assert provider._dimension == 2
