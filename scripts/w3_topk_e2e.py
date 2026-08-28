"""W3 Top-K 边界验证（麒麟 VM）。

top_n=1 / 大于命中数 / 超大 / 空库，验证候选数与退出码。
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

from retrieval.contracts import ObjectType, RetrievalFilter, SceneFilter
from retrieval.real_vector_provider import VectorCliClient

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
USER = "alice"


def main() -> int:
    collection = f"w3_topk_{int(time.time())}"
    cli = VectorCliClient(cli_path="./vector_cli", expected_dimension=4)
    flt = RetrievalFilter(
        user_id=USER,
        scene=SceneFilter(allowed_scene_ids=[], include_unscoped=True),
        object_types=[ObjectType.KNOWLEDGE],
        allowed_memory_statuses=["active"],
        conflict_policy="exclude_unresolved",
        as_of=NOW,
    )
    cli.drop_collection(collection)
    cli.create_collection(collection, 4)
    cli.insert(
        collection,
        [1, 2, 3],
        [[1, 0, 0, 0], [0, 1, 0, 0], [-1, 0, 0, 0]],
        user_ids=[USER] * 3,
        version_ids=["v1"] * 3,
        scene_ids=[""] * 3,
        memory_statuses=["active"] * 3,
        deleted_flags=[False] * 3,
    )

    # W3-2: top_n=1 返回恰好 1 条
    hits1 = cli.search(collection, [1.0, 0.0, 0.0, 0.0], top_n=1, user_id=USER, filter=flt, now=NOW)
    print(f"[W3] top_n=1 -> {len(hits1)} hits: {[h.memory_id for h in hits1]}")
    assert len(hits1) == 1

    # W3-3: top_n 大于命中数 -> 实际命中数（3）
    hits_gt = cli.search(collection, [1.0, 0.0, 0.0, 0.0], top_n=10, user_id=USER, filter=flt, now=NOW)
    print(f"[W3] top_n=10(>3) -> {len(hits_gt)} hits")
    assert len(hits_gt) == 3

    # W3-4: 超大 top_n -> 不崩，返回 3
    hits_huge = cli.search(collection, [1.0, 0.0, 0.0, 0.0], top_n=1000, user_id=USER, filter=flt, now=NOW)
    print(f"[W3] top_n=1000 -> {len(hits_huge)} hits")
    assert len(hits_huge) == 3

    # W3-5: 空库 + top_n>0 -> 空
    empty_coll = f"w3_empty_topk_{int(time.time())}"
    cli.drop_collection(empty_coll)
    cli.create_collection(empty_coll, 4)
    hits_empty = cli.search(empty_coll, [1.0, 0.0, 0.0, 0.0], top_n=5, user_id=USER, filter=flt, now=NOW)
    print(f"[W3] empty top_n=5 -> {len(hits_empty)} hits")
    assert hits_empty == []
    cli.drop_collection(empty_coll)

    cli.drop_collection(collection)
    print("[W3] PASS: Top-K boundary behavior verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
