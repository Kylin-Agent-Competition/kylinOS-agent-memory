#!/usr/bin/env python3
"""Capture D14B FTS5 results from the production SQLite FTS5 virtual table."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.d14b_capture_runner_common import (
    CaptureRunnerError,
    fetch_active_entries,
    identity_map,
    load_queries,
    open_readonly_sqlite,
    write_artifact_and_receipt,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--queries-file", type=Path, required=True)
    parser.add_argument("--tested-commit", required=True)
    parser.add_argument("--capture-handoff", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    return parser.parse_args()


def _positive_limit(value: Any, query_id: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CaptureRunnerError(f"{query_id}.limit 必须是正整数")
    return value


def run(args: argparse.Namespace) -> int:
    queries = load_queries(args.queries_file, required_key="match")
    connection = open_readonly_sqlite(args.db_path)
    rendered: list[dict[str, Any]] = []
    try:
        for query in queries:
            if query["user_id"] != args.user_id:
                raise CaptureRunnerError("query user_id 与 runner --user-id 不一致")
            limit = _positive_limit(query.get("limit", 10), query["query_id"])
            rows = connection.execute(
                """
                SELECT e.id, e.user_id, e.knowledge_id, e.version
                  FROM memory_fts AS f
                  JOIN memory_entries AS e ON e.id = f.rowid
                 WHERE memory_fts MATCH ?
                   AND f.user_id = ?
                   AND e.user_id = ?
                   AND e.is_deleted = 0
                   AND e.memory_status = 'active'
                 ORDER BY bm25(memory_fts) ASC, e.id ASC
                 LIMIT ?
                """,
                (query["match"], args.user_id, args.user_id, limit),
            ).fetchall()
            mapping = identity_map(fetch_active_entries(connection, args.user_id))
            results: list[dict[str, Any]] = []
            for rank, row in enumerate(rows, 1):
                stable_id = f"{row['knowledge_id']}-v{int(row['version'])}"
                if stable_id not in mapping:
                    raise CaptureRunnerError(
                        f"FTS hit {row['id']} 不在 production active truth 中"
                    )
                results.append(
                    {
                        "stable_id": stable_id,
                        "user_id": row["user_id"],
                        "version_id": f"v{int(row['version'])}",
                        "rank": rank,
                    }
                )
            rendered.append({"query_id": query["query_id"], "results": results})
    except sqlite3.Error as error:
        raise CaptureRunnerError(f"production FTS5 查询失败: {error}") from error
    finally:
        connection.close()

    write_artifact_and_receipt(
        channel="fts5",
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
        print(f"D14B_FTS5_CAPTURE_FAIL: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
