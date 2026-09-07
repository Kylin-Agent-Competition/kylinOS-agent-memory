"""D13D validation seam: rebuild the seeded vector index through the formal outbox.

The D13D state preparation writes memory rows only; it does not publish
``memory.upserted`` events.  This helper is used by the approved validation
profile to bootstrap knowledge vectors in an isolated runtime clone.  It is not
a mock path: callers must inject a real vector provider and embedding service.
Preference is deliberately outside vector semantics (G4), so the helper
refuses to index it rather than silently dropping it.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from sqlalchemy import select

from db import repositories as repo
from db.schema import outbox
from embedding.embedding_service import EmbeddingService
from outbox.index_consumer import build_index_consumer
from outbox.router import OutboxRouter
from outbox.worker import OutboxWorker
from retrieval.contracts import ObjectType, digest_from_canonical


D13D_INDEX_DIGEST_KEY_ID = "d13d-internal"
_DIGEST_KEY = b"kylin-memory-d13d-internal"
D13D_INDEX_DIGEST_KEY = _DIGEST_KEY


def index_knowledge_docs(
    engine: Any,
    *,
    user_id: str,
    docs: Iterable[Mapping[str, Any]],
    embedding_service: EmbeddingService,
    vector_provider: Any,
    index_generation: str,
) -> tuple[int, int]:
    """Index active knowledge docs via ``memory.upserted`` and return (ok, skipped).

    Each document becomes one outbox event and is consumed by the formal
    OutboxWorker/Router/index-consumer path.  Any consumer failure raises, so
    the caller cannot treat a partially indexed state as successful.
    """
    if not user_id.strip():
        raise ValueError("user_id must be non-blank")
    if not index_generation.strip():
        raise ValueError("index_generation must be non-blank")

    ok = 0
    skipped = 0
    router = OutboxRouter()
    router.register(
        repo.EVENT_MEMORY_UPSERTED,
        build_index_consumer(
            vector_provider,
            digest_key_id=D13D_INDEX_DIGEST_KEY_ID,
            digest_key=_DIGEST_KEY,
            index_generation=index_generation,
        ),
    )
    worker = OutboxWorker(
        engine,
        poll_interval_s=1,
        max_retries=0,
        consumer=router.route,
    )
    try:
        for doc in docs:
            tagged_id = str(doc["tagged_id"])
            if not tagged_id.startswith("knowledge:"):
                skipped += 1
                continue
            memory_id = tagged_id.rpartition(":")[2]
            if not memory_id.isdecimal():
                raise ValueError(f"knowledge doc has invalid id: {tagged_id}")
            version_id = str(doc["version_id"])
            index_text = str(doc["text"])
            response = embedding_service.embed(index_text)
            vector = (response.get("result") or {}).get("vector")
            if response.get("degraded") or not isinstance(vector, list) or not vector:
                raise RuntimeError(
                    f"embedding is unavailable for pre-delete vector probe: {tagged_id}"
                )
            with engine.begin() as conn:
                previous_watermark = conn.execute(
                    select(outbox.c.id).order_by(outbox.c.id.desc()).limit(1)
                ).scalar_one_or_none()
                source_watermark_value = int(previous_watermark or 0) + 1
                event_id = f"d13d-index-{tagged_id}-{index_generation}"
                payload = {
                    "event_id": event_id,
                    "trace_id": f"d13d-index:{index_generation}:{tagged_id}",
                    "memory_id": memory_id,
                    "version_id": version_id,
                    "user_id": user_id,
                    "vector": vector,
                    "object_type": ObjectType.KNOWLEDGE.value,
                    "index_text_hash": digest_from_canonical(
                        D13D_INDEX_DIGEST_KEY_ID,
                        _DIGEST_KEY,
                        {
                            "memory_id": memory_id,
                            "version_id": version_id,
                            "index_text": index_text,
                        },
                    ),
                    "index_generation": index_generation,
                    "source_watermark_value": source_watermark_value,
                    "idempotency_key": f"memory:{memory_id}:{version_id}",
                }
                repo.enqueue_outbox(
                    conn,
                    aggregate_type="memory",
                    aggregate_id=memory_id,
                    event_type=repo.EVENT_MEMORY_UPSERTED,
                    payload=payload,
                )
            worker._poll_once()
            ok += 1
    finally:
        worker.stop()
    return ok, skipped
