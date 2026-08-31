"""V006 端到端演示：FTS5 + vector_cli 子进程桥 + rrf-v1 融合。

在麒麟 VM 上运行：真实 SQLite FTS5 + 真实 Vector SDK（经 vector_cli）+ RRF。
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

from retrieval.contracts import (
    KnowledgeIndexMetadata,
    ObjectType,
    RetrievalFilter,
    SceneFilter,
)
from retrieval.fts5 import Fts5Index
from retrieval.fusion import TruthRecord, fuse_retrieval
from retrieval.real_vector_provider import VectorCliClient

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
USER_ID = "alice"


def build_truth() -> dict:
    rows = [
        ("1", "apple banana cherry"),
        ("2", "apple banana"),
        ("3", "cherry only"),
    ]
    return {
        (USER_ID, mid, "v1"): TruthRecord(
            memory_id=mid,
            version_id="v1",
            user_id=USER_ID,
            object_type=ObjectType.KNOWLEDGE,
            memory_type="long_term",
            memory_status="active",
            content=content,
            sensitivity="internal",
            conflict_state="resolved",
            is_current=True,
            knowledge=KnowledgeIndexMetadata(
                knowledge_type="workflow",
                primary_category="operations",
                source_event_id=f"v006-e2e-{mid}",
                memory_status="active",
            ),
        )
        for mid, content in rows
    }


def knowledge_index_fields(records: list[TruthRecord]) -> dict[str, list[str]]:
    metadata = [record.knowledge for record in records]
    if any(value is None for value in metadata):
        raise RuntimeError("V006 Knowledge truth must include index metadata")
    return {
        "object_types": [record.object_type.value for record in records],
        "knowledge_types": [value.knowledge_type for value in metadata],
        "primary_categories": [value.primary_category or "" for value in metadata],
        "source_event_ids": [value.source_event_id for value in metadata],
    }


def main() -> int:
    collection = f"v006_e2e_{int(time.time())}"
    truth = build_truth()
    records = list(truth.values())

    fts5 = Fts5Index()
    for (_, mid, _), rec in truth.items():
        fts5.upsert(
            mid,
            rec.version_id,
            content_summary=rec.content,
            user_id=USER_ID,
            object_type=rec.object_type,
            knowledge=rec.knowledge,
        )

    cli = VectorCliClient(cli_path="./vector_cli", expected_dimension=4)
    print(f"[V006] collection={collection}")
    print("[V006] drop (best-effort clean):", cli.drop_collection(collection).get("ok"))
    print("[V006] create:", cli.create_collection(collection, 4).get("ok"))
    print("[V006] insert:", cli.insert(
        collection,
        [1, 2, 3],
        [[1, 0, 0, 0], [0, 1, 0, 0], [-1, 0, 0, 0]],
        user_ids=[USER_ID] * 3,
        version_ids=["v1"] * 3,
        scene_ids=[""] * 3,
        memory_statuses=["active"] * 3,
        deleted_flags=[False] * 3,
        **knowledge_index_fields(records),
    ).get("ok"))

    flt = RetrievalFilter(
        user_id=USER_ID,
        scene=SceneFilter(allowed_scene_ids=[], include_unscoped=True),
        object_types=[ObjectType.KNOWLEDGE],
        allowed_memory_statuses=["active"],
        allowed_sensitivity=["internal"],
        conflict_policy="resolve",
        as_of=NOW,
    )
    fts5_hits = fts5.search("apple", USER_ID, top_n=5, now=NOW)
    vector_hits = cli.search(
        collection, [1.0, 0.0, 0.0, 0.0], top_n=5, user_id=USER_ID, filter=flt, now=NOW
    )

    print("[V006] FTS5 hits:  ", [(h.memory_id, h.rank) for h in fts5_hits])
    print("[V006] Vector hits:", [(h.memory_id, h.rank, h.raw_score) for h in vector_hits])

    candidates = fuse_retrieval(
        fts5_hits=fts5_hits, vector_hits=vector_hits, truth=truth, flt=flt
    )

    print("[V006] RRF fused candidates (rank order):")
    for c in candidates:
        print(
            f"  {c.memory_id}: rrf={c.rrf_score:.9f} channels={[ch.value for ch in c.channels]} content={c.content!r}"
        )

    candidate_ids = {candidate.memory_id for candidate in candidates}
    assert {"1", "2"}.issubset(candidate_ids), (
        "V006 expected FTS5 Knowledge candidates were filtered before RRF"
    )

    print("[V006] final drop:", cli.drop_collection(collection).get("ok"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
