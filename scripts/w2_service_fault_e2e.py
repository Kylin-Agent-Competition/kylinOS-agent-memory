"""W2 服务故障结构化降级（麒麟 VM）。

停 vector 服务 -> 真实错误 code=3 -> 映射 provider_unavailable ->
FTS5 命中仍返回（降级）-> 恢复服务后重试成功。
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone

from retrieval.contracts import ObjectType, RetrievalFilter
from retrieval.fts5 import Fts5Index
from retrieval.fusion import TruthRecord, retrieve_graceful
from retrieval.real_vector_provider import VectorCliClient, VectorCliError
from retrieval.vector_sdk_errors import map_sdk_status

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
USER = "alice"
SERVICE = "kylin-ai-vector-engine.service"


def run_svc(action: str) -> None:
    subprocess.run(["systemctl", "--user", action, SERVICE], check=True)


def main() -> int:
    collection = f"w2_fault_{int(time.time())}"
    truth = {
        (USER, "mem-a", "v1"): TruthRecord(
            memory_id="mem-a", version_id="v1", user_id=USER,
            object_type=ObjectType.KNOWLEDGE, memory_type="long_term",
            memory_status="active", content="apple banana cherry",
            sensitivity="internal", conflict_state="resolved", is_current=True,
        ),
        (USER, "mem-b", "v1"): TruthRecord(
            memory_id="mem-b", version_id="v1", user_id=USER,
            object_type=ObjectType.KNOWLEDGE, memory_type="long_term",
            memory_status="active", content="apple banana",
            sensitivity="internal", conflict_state="resolved", is_current=True,
        ),
    }

    fts5 = Fts5Index()
    for (_, mid, _), rec in truth.items():
        fts5.upsert(mid, rec.version_id, rec.content, USER)

    cli = VectorCliClient(cli_path="./vector_cli", expected_dimension=4)
    cli.drop_collection(collection)
    cli.create_collection(collection, 4)
    cli.insert(
        collection,
        [1, 2],
        [[1, 0, 0, 0], [0, 1, 0, 0]],
        user_ids=[USER] * 2,
        version_ids=["v1"] * 2,
        scene_ids=[""] * 2,
        memory_statuses=["active"] * 2,
        deleted_flags=[False] * 2,
    )

    flt = RetrievalFilter(
        user_id=USER, object_types=[ObjectType.KNOWLEDGE],
        allowed_memory_statuses=["active"], allowed_sensitivity=["internal"],
        conflict_policy="resolve", as_of=NOW,
    )

    def fts5_search():
        return fts5.search("apple", USER, top_n=5, now=NOW)

    def vector_search():
        return cli.search(collection, [1.0, 0.0, 0.0, 0.0], top_n=5, user_id=USER, now=NOW)

    # 正常路径
    normal = retrieve_graceful(fts5_search=fts5_search, vector_search=vector_search, truth=truth, flt=flt)
    print(f"[W2] normal candidates: {[c.memory_id for c in normal.candidates]} degraded={normal.degraded}")

    # 停服务 -> 真实错误
    print("[W2] stopping vector service...")
    run_svc("stop")
    try:
        vector_search()
        print("[W2] UNEXPECTED: vector search did not fail after stop"); return 1
    except VectorCliError as exc:
        print(f"[W2] caught VectorCliError code={exc.code} message={exc.message}")
        err = map_sdk_status(exc.code, exc.message)
        print(f"[W2] mapped -> {err.code.value} (retryable={err.retryable})")

    # 降级：FTS5 命中仍返回
    degraded = retrieve_graceful(fts5_search=fts5_search, vector_search=vector_search, truth=truth, flt=flt)
    print(f"[W2] degraded candidates: {[c.memory_id for c in degraded.candidates]}")
    print(f"[W2] degraded_channels: {degraded.degraded_channels}")
    assert {c.memory_id for c in degraded.candidates} == {"mem-a", "mem-b"}
    assert "vector" in degraded.degraded_channels

    # 恢复服务 -> 自愈
    print("[W2] restarting vector service...")
    run_svc("start")
    time.sleep(2)
    recovered = retrieve_graceful(fts5_search=fts5_search, vector_search=vector_search, truth=truth, flt=flt)
    print(f"[W2] recovered candidates: {[c.memory_id for c in recovered.candidates]} degraded={recovered.degraded}")
    assert not recovered.degraded

    cli.drop_collection(collection)
    print("[W2] PASS: service fault degrades gracefully and recovers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
