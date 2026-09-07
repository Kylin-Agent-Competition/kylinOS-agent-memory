#!/usr/bin/env python3
"""Compare two D14B retrieval snapshots without mutating any state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class SnapshotError(ValueError):
    """A snapshot cannot be compared safely."""


CHANNELS = ("fts5", "vector", "rrf")
VIOLATIONS = (
    "missing_ids",
    "unexpected_ids",
    "duplicate_ids",
    "rank_changes",
    "cross_user_hits",
    "stale_version_hits",
    "ghost_hits",
)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SnapshotError(f"无法读取 snapshot: {error}") from error
    if not isinstance(value, dict):
        raise SnapshotError("snapshot 必须是 JSON object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SnapshotError(f"{label} 必须是非空字符串")
    return value


def _query_results(snapshot: dict[str, Any], channel: str) -> dict[str, list[dict[str, Any]]]:
    channel_value = snapshot.get(channel)
    if not isinstance(channel_value, dict) or not isinstance(channel_value.get("queries"), list):
        raise SnapshotError(f"{channel}.queries 必须是数组")
    queries: dict[str, list[dict[str, Any]]] = {}
    for query in channel_value["queries"]:
        if not isinstance(query, dict):
            raise SnapshotError(f"{channel}.queries 项必须是 object")
        query_id = _text(query.get("query_id"), f"{channel}.query_id")
        results = query.get("results")
        if not isinstance(results, list):
            raise SnapshotError(f"{channel}.{query_id}.results 必须是数组")
        if query_id in queries:
            raise SnapshotError(f"{channel} 存在重复 query_id: {query_id}")
        normalized: list[dict[str, Any]] = []
        for result in results:
            if not isinstance(result, dict):
                raise SnapshotError(f"{channel}.{query_id}.results 项必须是 object")
            normalized.append(
                {
                    "stable_id": _text(result.get("stable_id"), "result.stable_id"),
                    "user_id": _text(result.get("user_id"), "result.user_id"),
                    "version_id": _text(result.get("version_id"), "result.version_id"),
                    "rank": result.get("rank"),
                }
            )
        queries[query_id] = normalized
    return queries


def _truth(snapshot: dict[str, Any]) -> tuple[str, set[str], set[str]]:
    user_id = _text(snapshot.get("user_id"), "user_id")
    sqlite = snapshot.get("sqlite")
    if not isinstance(sqlite, dict):
        raise SnapshotError("sqlite 必须是 object")
    stable_ids = sqlite.get("stable_ids")
    active_versions = sqlite.get("active_version_ids")
    if not isinstance(stable_ids, list) or not all(isinstance(value, str) and value for value in stable_ids):
        raise SnapshotError("sqlite.stable_ids 必须是非空 stable identity 数组")
    if not isinstance(active_versions, list) or not all(isinstance(value, str) and value for value in active_versions):
        raise SnapshotError("sqlite.active_version_ids 必须是非空 version identity 数组")
    return user_id, set(stable_ids), set(active_versions)


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    if _text(before.get("tested_commit"), "before.tested_commit") != _text(
        after.get("tested_commit"), "after.tested_commit"
    ):
        raise SnapshotError("before/after tested_commit 不一致")
    before_user, _, _ = _truth(before)
    after_user, after_truth_ids, after_versions = _truth(after)
    if before_user != after_user:
        raise SnapshotError("before/after user_id 不一致")

    report: dict[str, Any] = {key: [] for key in VIOLATIONS}
    report["tested_commit"] = before["tested_commit"]
    report["user_id"] = before_user

    for channel in CHANNELS:
        previous_queries = _query_results(before, channel)
        current_queries = _query_results(after, channel)
        for query_id in sorted(set(previous_queries) | set(current_queries)):
            previous = previous_queries.get(query_id, [])
            current = current_queries.get(query_id, [])
            previous_by_id = {item["stable_id"]: item for item in previous}
            current_by_id = {item["stable_id"]: item for item in current}
            previous_ids = set(previous_by_id)
            current_ids = set(current_by_id)
            context = {"channel": channel, "query_id": query_id}

            for stable_id in sorted(previous_ids - current_ids):
                report["missing_ids"].append({**context, "stable_id": stable_id})
            for stable_id in sorted(current_ids - previous_ids):
                report["unexpected_ids"].append({**context, "stable_id": stable_id})

            seen: set[str] = set()
            for result in current:
                stable_id = result["stable_id"]
                if stable_id in seen:
                    report["duplicate_ids"].append({**context, "stable_id": stable_id})
                seen.add(stable_id)
                if result["user_id"] != after_user:
                    report["cross_user_hits"].append({**context, "stable_id": stable_id})
                if result["version_id"] not in after_versions:
                    report["stale_version_hits"].append({**context, "stable_id": stable_id})
                if stable_id not in after_truth_ids:
                    report["ghost_hits"].append({**context, "stable_id": stable_id})

            for stable_id in sorted(previous_ids & current_ids):
                if previous_by_id[stable_id]["rank"] != current_by_id[stable_id]["rank"]:
                    report["rank_changes"].append({**context, "stable_id": stable_id})

    report["status"] = "PASS" if not any(report[key] for key in VIOLATIONS) else "FAIL"
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = compare(_load(args.before), _load(args.after))
    except SnapshotError as error:
        print(f"D14B_SNAPSHOT_COMPARE_FAIL: {error}", file=sys.stderr)
        return 2
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
