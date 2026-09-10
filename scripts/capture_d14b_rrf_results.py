#!/usr/bin/env python3
"""Capture D14B RRF output through the production fusion entrypoint."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "memory-service") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "memory-service"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from retrieval.contracts import (  # noqa: E402
    Channel,
    KnowledgeIndexMetadata,
    ObjectType,
    RetrievalFilter,
    RetrievalHit,
    ScoreSemantics,
)
from retrieval.fusion import TruthRecord, retrieve_graceful  # noqa: E402
from scripts.d14b_capture_runner_common import (  # noqa: E402
    CaptureRunnerError,
    fetch_active_entries,
    identity_map,
    load_json,
    load_source_binding,
    open_readonly_sqlite,
    production_identity,
    require_text,
    sha256_file,
    validate_source_binding,
    write_artifact_and_receipt,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--fts5-results", type=Path, required=True)
    parser.add_argument("--vector-results", type=Path, required=True)
    parser.add_argument("--sensitivity", default="none")
    parser.add_argument("--conflict-state", default="none")
    parser.add_argument("--tested-commit", required=True)
    parser.add_argument("--capture-handoff", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    return parser.parse_args()


def _load_channel_artifact(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path, "channel results")
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        raise CaptureRunnerError(f"{path} 必须包含非空 queries")
    return queries


def _parse_hits(
    queries: list[dict[str, Any]],
    channel: Channel,
    mapping: dict[str, str],
    expected_user_id: str,
) -> dict[str, list[RetrievalHit]]:
    parsed: dict[str, list[RetrievalHit]] = {}
    now = datetime.now(timezone.utc)
    for query in queries:
        query_id = require_text(query.get("query_id"), "channel query_id")
        if query_id in parsed:
            raise CaptureRunnerError(f"channel 存在重复 query_id: {query_id}")
        hits: list[RetrievalHit] = []
        results = query.get("results")
        if not isinstance(results, list):
            raise CaptureRunnerError(f"{query_id}.results 必须是数组")
        for result in results:
            if not isinstance(result, dict):
                raise CaptureRunnerError(f"{query_id}.results 项必须是 object")
            stable_id = require_text(result.get("stable_id"), f"{query_id}.stable_id")
            if stable_id not in mapping:
                raise CaptureRunnerError(f"{query_id}.stable_id 不在 production truth 中")
            user_id = require_text(result.get("user_id"), f"{query_id}.user_id")
            if user_id != expected_user_id:
                raise CaptureRunnerError(f"{query_id}.stable_id 归属用户与 runner 不一致")
            version_id = require_text(result.get("version_id"), f"{query_id}.version_id")
            rank = result.get("rank")
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                raise CaptureRunnerError(f"{query_id}.rank 必须是正整数")
            hits.append(
                RetrievalHit(
                    memory_id=mapping[stable_id],
                    version_id=version_id,
                    user_id=user_id,
                    channel=channel,
                    rank=rank,
                    score_semantics=(
                        ScoreSemantics.BM25
                        if channel is Channel.FTS5
                        else ScoreSemantics.SDK_SCORE_UNVERIFIED
                    ),
                    provider="d14b_production_capture",
                    retrieved_at=now,
                    filter_fingerprint="hmac-sha256:k1:" + "a" * 64,
                )
            )
        parsed[query_id] = hits
    return parsed


def _primary_source_event(connection: sqlite3.Connection, user_id: str, knowledge_id: str) -> str:
    row = connection.execute(
        """
        SELECT right_endpoint_id
          FROM memory_relation
         WHERE user_id = ?
           AND relation_type = 'evidence'
           AND is_primary = 1
           AND left_endpoint_type = 'knowledge'
           AND left_endpoint_id = ?
           AND right_endpoint_type = 'source_event'
        """,
        (user_id, knowledge_id),
    ).fetchone()
    if row is None:
        raise CaptureRunnerError(f"knowledge {knowledge_id} 缺少 primary evidence relation")
    return require_text(row["right_endpoint_id"], "memory_relation.source_event_id")


def _build_truth(
    connection: sqlite3.Connection,
    *,
    args: argparse.Namespace,
) -> dict[tuple[str, str, str], TruthRecord]:
    truth: dict[tuple[str, str, str], TruthRecord] = {}
    for row in fetch_active_entries(connection, args.user_id):
        if row["entry_type"] != "knowledge":
            raise CaptureRunnerError(
                f"D14B RRF capture 只支持 production knowledge entries: {row['id']}"
            )
        content = row["content"]
        if not isinstance(content, str) or not content.strip():
            raise CaptureRunnerError(f"memory_entry {row['id']} content 为空")
        try:
            parsed_content = json.loads(content)
        except json.JSONDecodeError as error:
            raise CaptureRunnerError(f"memory_entry {row['id']} content JSON 非法") from error
        if not isinstance(parsed_content, dict):
            raise CaptureRunnerError(f"memory_entry {row['id']} content 必须是 JSON object")
        knowledge_id = require_text(row["knowledge_id"], "memory_entries.knowledge_id")
        knowledge_type = require_text(row["knowledge_type"], "memory_entries.knowledge_type")
        memory_status = require_text(row["memory_status"], "memory_entries.memory_status")
        truth[(args.user_id, str(row["id"]), f"v{int(row['version'])}")] = TruthRecord(
            memory_id=str(row["id"]),
            version_id=f"v{int(row['version'])}",
            user_id=args.user_id,
            object_type=ObjectType.KNOWLEDGE,
            memory_type=row["memory_type"],
            memory_status=memory_status,
            content=content,
            sensitivity=args.sensitivity,
            conflict_state=args.conflict_state,
            is_current=True,
            knowledge=KnowledgeIndexMetadata(
                knowledge_type=knowledge_type,
                source_event_id=_primary_source_event(connection, args.user_id, knowledge_id),
                memory_status=memory_status,
            ),
        )
    if not truth:
        raise CaptureRunnerError("production truth 为空，禁止采集 RRF")
    return truth


def run(args: argparse.Namespace) -> int:
    binding = load_source_binding("rrf", args.capture_handoff)
    validate_source_binding(binding, "rrf", db_path=args.db_path)
    fts5_input_sha256 = sha256_file(args.fts5_results)
    vector_input_sha256 = sha256_file(args.vector_results)
    fts_queries = _load_channel_artifact(args.fts5_results)
    vector_queries = _load_channel_artifact(args.vector_results)
    connection = open_readonly_sqlite(args.db_path)
    try:
        rows = fetch_active_entries(connection, args.user_id)
        mapping = identity_map(rows)
        truth = _build_truth(connection, args=args)
    finally:
        connection.close()

    fts_hits = _parse_hits(fts_queries, Channel.FTS5, mapping, args.user_id)
    vector_hits = _parse_hits(vector_queries, Channel.VECTOR, mapping, args.user_id)
    if set(fts_hits) != set(vector_hits):
        raise CaptureRunnerError("FTS5 与 Vector artifact 的 query_id 集合不一致")

    now = datetime.now(timezone.utc)
    flt = RetrievalFilter(
        user_id=args.user_id,
        object_types=[ObjectType.KNOWLEDGE],
        allowed_memory_statuses=["active"],
        allowed_sensitivity=[args.sensitivity],
        conflict_policy="exclude_unresolved",
        as_of=now,
    )
    rendered: list[dict[str, Any]] = []
    for query_id, fts_hits_for_query in fts_hits.items():
        outcome = retrieve_graceful(
            fts5_search=lambda hits=fts_hits_for_query: hits,
            vector_search=lambda hits=vector_hits[query_id]: hits,
            truth=truth,
            flt=flt,
            k=60,
            top_k=10,
        )
        results: list[dict[str, Any]] = []
        reverse_mapping = {memory_id: stable_id for stable_id, memory_id in mapping.items()}
        for rank, candidate in enumerate(outcome.candidates, 1):
            stable_id = reverse_mapping.get(candidate.memory_id)
            if stable_id is None:
                raise CaptureRunnerError("RRF candidate 不在 production truth 中")
            _, _, version_suffix = stable_id.rpartition("-v")
            if version_suffix != candidate.version_id.removeprefix("v"):
                raise CaptureRunnerError("RRF candidate version 与 production truth 不一致")
            results.append(
                {
                    "stable_id": stable_id,
                    "user_id": candidate.user_id,
                    "version_id": candidate.version_id,
                    "rank": rank,
                }
            )
        rendered.append({"query_id": query_id, "results": results})

    write_artifact_and_receipt(
        channel="rrf",
        tested_commit=args.tested_commit,
        capture_handoff=args.capture_handoff,
        runner_file=Path(__file__),
        artifact_path=args.output,
        receipt_path=args.receipt_output,
        artifact={"queries": rendered},
        extra_receipt_fields={
            "fts5_input_sha256": fts5_input_sha256,
            "vector_input_sha256": vector_input_sha256,
        },
    )
    return 0


def main() -> int:
    try:
        return run(parse_args())
    except CaptureRunnerError as error:
        print(f"D14B_RRF_CAPTURE_FAIL: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
