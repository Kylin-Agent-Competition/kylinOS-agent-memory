#!/usr/bin/env python3
"""Capture D14B Vector results through the production SQLite Vector provider."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "memory-service") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "memory-service"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine  # noqa: E402

from retrieval.contracts import (  # noqa: E402
    ObjectType,
    RetrievalFilter,
    VectorSearchRequest,
)
from retrieval.real_vector_provider import VectorCliClient  # noqa: E402
from retrieval.sqlite_vector_provider import SqliteVectorProvider  # noqa: E402
from scripts.d14b_capture_runner_common import (  # noqa: E402
    CaptureRunnerError,
    fetch_active_entries,
    identity_map,
    load_queries,
    open_readonly_sqlite,
    production_identity,
    write_artifact_and_receipt,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--queries-file", type=Path, required=True)
    parser.add_argument("--vector-cli", default="vector_cli")
    parser.add_argument("--dimension", type=int, default=768)
    parser.add_argument("--tested-commit", required=True)
    parser.add_argument("--capture-handoff", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    return parser.parse_args()


def _query_vector(value: Any, query_id: str, dimension: int) -> list[float]:
    if not isinstance(value, list) or len(value) != dimension:
        raise CaptureRunnerError(f"{query_id}.vector 必须是长度 {dimension} 的数组")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise CaptureRunnerError(f"{query_id}.vector 只能包含数字")
    return [float(item) for item in value]


def _top_n(value: Any, query_id: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CaptureRunnerError(f"{query_id}.top_n 必须是正整数")
    return value


def run(args: argparse.Namespace) -> int:
    queries = load_queries(args.queries_file, required_key="vector", required_kind="array")
    if args.dimension <= 0:
        raise CaptureRunnerError("--dimension 必须是正整数")

    engine = create_engine(f"sqlite:///{args.db_path.resolve().as_posix()}")
    provider = SqliteVectorProvider(
        engine,
        vector_client=VectorCliClient(args.vector_cli, expected_dimension=args.dimension),
        digest_keys={"d10b-search-filter": b"kylin-memory-d10b-search-filter"},
        dimension=args.dimension,
    )
    memory_to_stable: dict[str, str] = {}
    connection = open_readonly_sqlite(args.db_path)
    try:
        rows = fetch_active_entries(connection, args.user_id)
        identity_map(rows)
        memory_to_stable = {str(row["id"]): production_identity(row) for row in rows}
    finally:
        connection.close()

    rendered: list[dict[str, Any]] = []
    try:
        for query in queries:
            query_id = query["query_id"]
            if query["user_id"] != args.user_id:
                raise CaptureRunnerError("query user_id 与 runner --user-id 不一致")
            now = datetime.now(timezone.utc)
            request = VectorSearchRequest(
                request_id=query_id,
                trace_id=f"d14b-vector-capture:{query_id}",
                user_id=args.user_id,
                deadline_at=now + timedelta(seconds=5),
                query_vector=_query_vector(query["vector"], query_id, args.dimension),
                filter=RetrievalFilter(
                    user_id=args.user_id,
                    object_types=[ObjectType.KNOWLEDGE],
                    allowed_memory_statuses=["active"],
                    conflict_policy="exclude_unresolved",
                    as_of=now,
                ),
                top_n=_top_n(query.get("top_n", 10), query_id),
            )
            result = provider.search(request)
            if not result.ok or result.value is None:
                detail = result.error.message if result.error else "unknown"
                raise CaptureRunnerError(f"production Vector 查询失败: {detail}")
            results: list[dict[str, Any]] = []
            for hit in result.value.hits:
                stable_id = memory_to_stable.get(hit.memory_id)
                if stable_id is None:
                    raise CaptureRunnerError(
                        f"Vector hit {hit.memory_id} 不在 production active truth 中"
                    )
                _, _, version_suffix = stable_id.rpartition("-v")
                if version_suffix != hit.version_id.removeprefix("v"):
                    raise CaptureRunnerError(
                        f"Vector hit {hit.memory_id}/{hit.version_id} 与 production truth 不一致"
                    )
                results.append(
                    {
                        "stable_id": stable_id,
                        "user_id": hit.user_id,
                        "version_id": hit.version_id,
                        "rank": int(hit.rank),
                    }
                )
            rendered.append({"query_id": query_id, "results": results})
    finally:
        engine.dispose()

    write_artifact_and_receipt(
        channel="vector",
        tested_commit=args.tested_commit,
        capture_handoff=args.capture_handoff,
        runner_file=Path(__file__),
        artifact_path=args.output,
        receipt_path=args.receipt_output,
        artifact={"queries": rendered},
    )
    return 0


def main() -> int:
    try:
        return run(parse_args())
    except CaptureRunnerError as error:
        print(f"D14B_VECTOR_CAPTURE_FAIL: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
