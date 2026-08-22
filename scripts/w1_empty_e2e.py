"""W1 空库端到端验证（麒麟 VM）。

空 FTS5 表 + 空 Vector collection -> 结构化空结果，退出码 0，不产出伪候选。
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from retrieval.contracts import ObjectType, RetrievalFilter
from retrieval.fts5 import Fts5Index
from retrieval.fusion import fuse_retrieval
from retrieval.real_vector_provider import VectorCliClient

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
USER = "alice"


def main() -> int:
    collection = "w1_empty"

    # W1-1 空 FTS5
    fts5 = Fts5Index()
    fts5_hits = fts5.search("apple", USER, top_n=5, now=NOW)
    print(f"[W1] empty FTS5 hits: {len(fts5_hits)} -> {fts5_hits}")

    # W1-2 空 Vector collection（create 但不 insert）
    cli = VectorCliClient(cli_path="./vector_cli")
    cli.drop_collection(collection)
    cli.create_collection(collection, 4)
    vector_hits = cli.search(collection, [1.0, 0.0, 0.0, 0.0], top_n=5, user_id=USER, now=NOW)
    print(f"[W1] empty Vector hits: {len(vector_hits)} -> {vector_hits}")

    # W1-3/W1-5 融合 -> 可解释空结果
    flt = RetrievalFilter(
        user_id=USER,
        object_types=[ObjectType.KNOWLEDGE],
        allowed_memory_statuses=["active"],
        allowed_sensitivity=["internal"],
        conflict_policy="resolve",
        as_of=NOW,
    )
    candidates = fuse_retrieval(fts5_hits=fts5_hits, vector_hits=vector_hits, truth={}, flt=flt)
    print(f"[W1] fused candidates: {len(candidates)} -> {'EMPTY (解释为空库无匹配)' if not candidates else candidates}")

    assert fts5_hits == [], "empty FTS5 should return no hits"
    assert vector_hits == [], "empty collection should return no hits"
    assert candidates == [], "empty library should return no candidates"

    cli.drop_collection(collection)
    print("[W1] PASS: empty library returns explainable empty result, exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
