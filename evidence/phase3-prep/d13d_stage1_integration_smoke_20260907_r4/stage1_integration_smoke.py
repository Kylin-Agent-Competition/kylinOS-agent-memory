
import hashlib
import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(os.environ["D13D_STAGE1_ROOT"])
MEMORY_SERVICE = ROOT / "memory-service"
G5_PREP = os.environ["D13D_G5_PREP"]
G6_CLI = os.environ["D13D_G6_CLI"]
USER_ID = "d13d-stage1-user"
KEY_ID = "stage1-ephemeral"

sys.path.insert(0, str(MEMORY_SERVICE))
sys.path.insert(1, G5_PREP)


def digest(value: str, key: bytes):
    from retrieval.contracts import digest_from_canonical
    return digest_from_canonical(KEY_ID, key, value)


def run():
    from db.engine import create_db_engine, init_schema
    from db.schema import memory_entries, vector_index_entries, vector_index_generations
    from providers import EmbeddingProvider
    from retrieval.contracts import (
        ConfirmationMode,
        KnowledgeFilter,
        ObjectType,
        ResolvedBy,
        ResolvedDeleteSelector,
        RetrievalFilter,
        SceneFilter,
        ScopeKind,
        SelectionMode,
        VectorDeleteRequest,
        VectorRecord,
        VectorUpsertRequest,
        Watermark,
        WatermarkDomain,
        WatermarkKind,
        digest_from_canonical,
    )
    from retrieval.real_vector_provider import VectorCliClient
    from retrieval.sqlite_vector_provider import SqliteVectorProvider
    from sqlalchemy import select

    import secrets
    key = secrets.token_bytes(32)
    index_text = "D13D stage one isolated runtime smoke target"
    content = json.dumps({"index_text": index_text}, ensure_ascii=False)
    db_path = ROOT / "runtime.db"
    engine = create_db_engine(str(db_path))
    init_schema(engine)
    with engine.begin() as conn:
        conn.execute(memory_entries.insert().values(
            id=1,
            user_id=USER_ID,
            entry_type="knowledge",
            content=content,
            confidence=0.9,
            version=1,
            is_deleted=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            trace_id="stage1-smoke",
            knowledge_id="stage1-knowledge-1",
            knowledge_type="fact",
            memory_status="active",
            memory_type="medium_term",
            evidence_tier="user_explicit_config_latest",
        ))

    provider = EmbeddingProvider()
    provider.start()
    try:
        embedding = provider.embed(index_text, timeout_ms=30000)
        vector = list(embedding.vector)
        embedding_dimension = provider.get_dimension()
        embedding_norm = float(sum(value * value for value in vector) ** 0.5)
        model_info = provider.model_info()
    finally:
        provider.close()

    if embedding_dimension != 768 or len(vector) != 768:
        raise RuntimeError(
            f"embedding dimension mismatch: provider={embedding_dimension}, vector={len(vector)}"
        )
    if not 0.99 <= embedding_norm <= 1.01:
        raise RuntimeError(f"embedding norm out of expected range: {embedding_norm}")

    client = VectorCliClient(cli_path=G6_CLI, expected_dimension=embedding_dimension)
    sqlite_provider = SqliteVectorProvider(
        engine,
        vector_client=client,
        digest_keys={KEY_ID: key},
        dimension=embedding_dimension,
    )

    watermark = Watermark(
        domain=WatermarkDomain(
            scope_id=f"user:{USER_ID}",
            stream="stage1-smoke",
            partition="default",
            source_generation="stage1",
        ),
        kind=WatermarkKind.MONOTONIC_INT,
        value=1,
    )
    upsert_request = VectorUpsertRequest(
        request_id="stage1-upsert-1",
        trace_id="stage1-smoke",
        user_id=USER_ID,
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=2),
        idempotency_key="stage1-upsert-1",
        payload_hash=digest(index_text, key),
        index_generation="stage1-generation",
        source_watermark=watermark,
        records=[
            VectorRecord(
                memory_id="1",
                version_id="v1",
                user_id=USER_ID,
                vector=vector,
                object_type=ObjectType.KNOWLEDGE,
                index_text_hash=digest(index_text, key),
                knowledge={
                    "knowledge_type": "fact",
                    "source_event_id": "stage1-source-event",
                    "memory_status": "active",
                },
            )
        ],
    )
    upsert_request = upsert_request.model_copy(update={
        "payload_hash": digest_from_canonical(
            KEY_ID,
            key,
            upsert_request.model_dump(
                mode="json",
                exclude={"request_id", "trace_id", "deadline_at", "payload_hash"},
            ),
        )
    })
    upsert_result = sqlite_provider.upsert(upsert_request)
    if not upsert_result.ok:
        raise RuntimeError(f"vector upsert failed: {upsert_result.error.model_dump(mode='json')}")

    with engine.connect() as conn:
        collection_name = conn.execute(
            select(vector_index_generations.c.collection_name).where(
                vector_index_generations.c.scope_id == f"user:{USER_ID}",
                vector_index_generations.c.generation == "stage1-generation",
            )
        ).scalar_one()
        active_before_delete = conn.execute(
            select(vector_index_entries.c.is_active).where(
                vector_index_entries.c.scope_id == f"user:{USER_ID}",
                vector_index_entries.c.generation == "stage1-generation",
                vector_index_entries.c.memory_entry_id == 1,
                vector_index_entries.c.version_id == "v1",
            )
        ).scalar_one()

    retrieval_filter = RetrievalFilter(
        user_id=USER_ID,
        scene=SceneFilter(include_unscoped=True),
        knowledge=KnowledgeFilter(),
        object_types=[ObjectType.KNOWLEDGE],
        allowed_memory_statuses=["active"],
        conflict_policy="latest_wins",
        as_of=datetime.now(timezone.utc),
    )
    pre_delete_hits = client.search(
        collection_name,
        vector,
        5,
        user_id=USER_ID,
        filter=retrieval_filter,
    )
    if [hit.memory_id for hit in pre_delete_hits] != ["1"]:
        raise RuntimeError(
            f"pre-delete vector hit mismatch: {[(h.memory_id, h.version_id) for h in pre_delete_hits]}"
        )
    if active_before_delete != 1:
        raise RuntimeError(f"active ledger before delete mismatch: {active_before_delete}")

    delete_watermark = watermark.model_copy(update={"value": 2})
    selector = ResolvedDeleteSelector(
        user_id=USER_ID,
        memory_ids=["1"],
        version_ids=["v1"],
        selection_mode=SelectionMode.SINGLE_ITEM,
        selection_hash=digest("stage1-selection", key),
        resolved_by=ResolvedBy.SYSTEM,
        preview_ref="stage1-preview-1",
        preview_hash=digest("stage1-preview", key),
        confirmation_mode=ConfirmationMode.EXPLICIT,
        confirmation_ref="stage1-confirmation-1",
    )
    delete_request = VectorDeleteRequest(
        request_id="stage1-delete-1",
        trace_id="stage1-smoke",
        user_id=USER_ID,
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=2),
        idempotency_key="stage1-delete-1",
        payload_hash=digest("stage1-delete", key),
        index_generation="stage1-generation",
        source_watermark=delete_watermark,
        selector=selector,
    )
    delete_request = delete_request.model_copy(update={
        "payload_hash": digest_from_canonical(
            KEY_ID,
            key,
            delete_request.model_dump(
                mode="json",
                exclude={"request_id", "trace_id", "deadline_at", "payload_hash"},
            ),
        )
    })
    delete_result = sqlite_provider.delete(delete_request)
    if not delete_result.ok:
        raise RuntimeError(f"vector delete failed: {delete_result.error.model_dump(mode='json')}")

    with engine.connect() as conn:
        active_after_delete = conn.execute(
            select(vector_index_entries.c.is_active).where(
                vector_index_entries.c.scope_id == f"user:{USER_ID}",
                vector_index_entries.c.generation == "stage1-generation",
                vector_index_entries.c.memory_entry_id == 1,
                vector_index_entries.c.version_id == "v1",
            )
        ).scalar_one()
    post_delete_hits = client.search(
        collection_name,
        vector,
        5,
        user_id=USER_ID,
        filter=retrieval_filter,
    )
    if post_delete_hits:
        raise RuntimeError(f"post-delete vector still returned hits: {post_delete_hits}")
    if active_after_delete != 0:
        raise RuntimeError(f"active ledger after delete mismatch: {active_after_delete}")

    drop_result = client.drop_collection(collection_name)
    if not drop_result.get("ok"):
        raise RuntimeError(f"collection cleanup failed: {drop_result}")

    result = {
        "ok": True,
        "stage": "P2-T1.4_INTEGRATION_SMOKE",
        "classification": "PREPARATION_NON_FORMAL",
        "memory_entry_id": "1",
        "version_id": "v1",
        "collection_name": collection_name,
        "collection_dropped": True,
        "embedding": {
            "dimension": embedding_dimension,
            "l2_norm": embedding_norm,
            "model": model_info.name,
            "loaded": model_info.loaded,
            "ondevice": model_info.ondevice,
            "so_path": provider.sdk_so_path,
        },
        "vector_cli": {"path": G6_CLI},
        "upsert": upsert_result.value.model_dump(mode="json"),
        "pre_delete_hits": [
            {"memory_id": hit.memory_id, "version_id": hit.version_id, "rank": hit.rank}
            for hit in pre_delete_hits
        ],
        "delete": delete_result.value.model_dump(mode="json"),
        "post_delete_hit_count": len(post_delete_hits),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


try:
    run()
except Exception as exc:
    print(json.dumps({
        "ok": False,
        "error": {"type": type(exc).__name__, "message": str(exc)},
    }, ensure_ascii=False, sort_keys=True))
    traceback.print_exc()
    raise
