#!/usr/bin/env python3
"""Assemble a read-only D14B retrieval checkpoint from production artifacts.

The caller obtains SQLite truth and the FTS5/Vector/RRF result artifacts by the
already approved production Repository/API/service paths.  Every source
artifact must carry a machine-verifiable capture receipt bound to the approved
capture handoff; this command validates and records those bytes only.  It
never calls a service, writes a database, or changes an index.

The produced checkpoint records the full provenance chain (checkpoint ->
receipt -> handoff -> pinned runner): per source it keeps artifact SHA,
receipt SHA, command id and runner SHA, plus the capture-handoff SHA.  The
raw handoff/receipt bytes are retained by the formal evidence root and closed
by the existing SHA256SUMS verifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
CHANNELS = ("fts5", "vector", "rrf")
TRUTH_CHANNEL = "sqlite"
ALL_CHANNELS = (TRUTH_CHANNEL, *CHANNELS)
RECEIPT_FIELDS = (
    "channel",
    "tested_commit",
    "command_id",
    "runner_path",
    "runner_sha256",
    "artifact_path",
    "artifact_sha256",
    "captured_at_utc",
)


class CaptureError(ValueError):
    """The proposed checkpoint cannot be recorded safely."""


def _load(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaptureError(f"无法读取 {label}: {error}") from error
    if not isinstance(value, dict):
        raise CaptureError(f"{label} 必须是 JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaptureError(f"{label} 必须是非空字符串")
    return value.strip()


def _truth(value: dict[str, Any]) -> dict[str, list[str]]:
    stable_ids = value.get("stable_ids")
    active_versions = value.get("active_version_ids")
    for field, values in (("stable_ids", stable_ids), ("active_version_ids", active_versions)):
        if not isinstance(values, list) or not values or not all(
            isinstance(item, str) and item.strip() for item in values
        ):
            raise CaptureError(f"sqlite truth.{field} 必须是非空字符串数组")
        if len(set(values)) != len(values):
            raise CaptureError(f"sqlite truth.{field} 不得重复")
    return {"stable_ids": stable_ids, "active_version_ids": active_versions}


def _channel(value: dict[str, Any], label: str) -> dict[str, list[dict[str, Any]]]:
    queries = value.get("queries")
    if not isinstance(queries, list) or not queries:
        raise CaptureError(f"{label}.queries 必须是非空数组")
    seen_query_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for query in queries:
        if not isinstance(query, dict):
            raise CaptureError(f"{label}.queries 项必须是 object")
        query_id = _text(query.get("query_id"), f"{label}.query_id")
        if query_id in seen_query_ids:
            raise CaptureError(f"{label} 存在重复 query_id: {query_id}")
        seen_query_ids.add(query_id)
        results = query.get("results")
        if not isinstance(results, list):
            raise CaptureError(f"{label}.{query_id}.results 必须是数组")
        rendered_results: list[dict[str, Any]] = []
        for result in results:
            if not isinstance(result, dict):
                raise CaptureError(f"{label}.{query_id}.results 项必须是 object")
            rank = result.get("rank")
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                raise CaptureError(f"{label}.{query_id}.rank 必须是正整数")
            rendered_results.append(
                {
                    "stable_id": _text(result.get("stable_id"), f"{label}.{query_id}.stable_id"),
                    "user_id": _text(result.get("user_id"), f"{label}.{query_id}.user_id"),
                    "version_id": _text(result.get("version_id"), f"{label}.{query_id}.version_id"),
                    "rank": rank,
                }
            )
        normalized.append({"query_id": query_id, "results": rendered_results})
    return {"queries": normalized}


def _verify_receipts(
    *,
    tested_commit: str,
    capture_handoff: dict[str, Any],
    capture_handoff_sha: str,
    artifact_hashes: dict[str, str],
    artifact_paths: dict[str, Path],
    receipt_paths: dict[str, Path],
) -> dict[str, dict[str, str]]:
    """Bind every source artifact to its receipt and the handoff.

    Returns per-channel provenance: artifact_sha256, receipt_sha256,
    command_id, runner_sha256, runner_path.  Receipt hashes are computed over
    the raw receipt bytes, never over a re-serialised object.
    """

    if not isinstance(capture_handoff, dict):
        raise CaptureError("d14b-capture-handoff 必须是 JSON object")
    handoff_commit = _text(capture_handoff.get("tested_commit"), "capture-handoff.tested_commit")
    if handoff_commit != tested_commit:
        raise CaptureError("capture-handoff.tested_commit 与 requested tested_commit 不一致")
    captures = capture_handoff.get("captures")
    if not isinstance(captures, dict) or set(captures) != set(ALL_CHANNELS):
        raise CaptureError("capture-handoff.captures 必须声明 sqlite/fts5/vector/rrf 四类 runner")

    provenance: dict[str, dict[str, str]] = {}
    for channel in ALL_CHANNELS:
        handoff_entry = captures[channel]
        if not isinstance(handoff_entry, dict):
            raise CaptureError(f"capture-handoff.captures.{channel} 必须是 object")
        receipt_path = receipt_paths[channel]
        if receipt_path is None:
            raise CaptureError(f"{channel} 缺少 capture receipt，禁止无 provenance 采集")
        receipt, receipt_sha = _load(receipt_path, f"{channel} receipt")
        for field in RECEIPT_FIELDS:
            if field not in receipt:
                raise CaptureError(f"{channel} receipt 缺少字段 {field}")
        if _text(receipt.get("channel"), f"{channel} receipt.channel") != channel:
            raise CaptureError(f"{channel} receipt.channel 与通道不一致")
        if _text(receipt.get("tested_commit"), f"{channel} receipt.tested_commit") != tested_commit:
            raise CaptureError(f"{channel} receipt.tested_commit 与 requested tested_commit 不一致")
        if (
            _text(receipt.get("command_id"), f"{channel} receipt.command_id")
            != _text(handoff_entry.get("command_id"), f"capture-handoff.{channel}.command_id")
        ):
            raise CaptureError(f"{channel} receipt.command_id 与 capture-handoff 不一致")
        if (
            _text(receipt.get("runner_path"), f"{channel} receipt.runner_path")
            != _text(handoff_entry.get("runner_path"), f"capture-handoff.{channel}.runner_path")
        ):
            raise CaptureError(f"{channel} receipt.runner_path 与 capture-handoff 不一致")
        if (
            _text(receipt.get("runner_sha256"), f"{channel} receipt.runner_sha256")
            != _text(handoff_entry.get("runner_sha256"), f"capture-handoff.{channel}.runner_sha256")
        ):
            raise CaptureError(f"{channel} receipt.runner_sha256 与 capture-handoff 不一致")
        if (
            Path(_text(receipt.get("artifact_path"), f"{channel} receipt.artifact_path")).name
            != artifact_paths[channel].name
        ):
            raise CaptureError(f"{channel} receipt.artifact_path 与本次 artifact 不一致")
        if (
            _text(receipt.get("artifact_sha256"), f"{channel} receipt.artifact_sha256")
            != artifact_hashes[channel]
        ):
            raise CaptureError(f"{channel} receipt.artifact_sha256 与实际 artifact 不一致")
        provenance[channel] = {
            "artifact_sha256": artifact_hashes[channel],
            "receipt_sha256": receipt_sha,
            "command_id": _text(receipt.get("command_id"), f"{channel} receipt.command_id"),
            "runner_sha256": _text(receipt.get("runner_sha256"), f"{channel} receipt.runner_sha256"),
            "runner_path": _text(receipt.get("runner_path"), f"{channel} receipt.runner_path"),
        }
    provenance["capture_handoff_sha256"] = capture_handoff_sha
    return provenance


def build_checkpoint(
    *,
    tested_commit: str,
    checkpoint: str,
    user_id: str,
    captured_at_utc: str,
    truth: dict[str, Any],
    channels: dict[str, dict[str, Any]],
    provenance: dict[str, dict[str, str]],
) -> dict[str, Any]:
    if not COMMIT_RE.fullmatch(tested_commit):
        raise CaptureError("tested_commit 必须是 40 位小写十六进制")
    if not captured_at_utc.endswith("Z"):
        raise CaptureError("captured_at_utc 必须是 UTC Z 时间戳")
    checkpoint_value = _text(checkpoint, "checkpoint")
    user_value = _text(user_id, "user_id")
    result: dict[str, Any] = {
        "tested_commit": tested_commit,
        "checkpoint": checkpoint_value,
        "captured_at_utc": captured_at_utc,
        "user_id": user_value,
        "sqlite": _truth(truth),
        "capture_sources": provenance,
    }
    for channel in CHANNELS:
        result[channel] = _channel(channels[channel], channel)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tested-commit", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--captured-at-utc", required=True)
    parser.add_argument("--capture-handoff", type=Path, default=None)
    parser.add_argument("--sqlite-truth", type=Path, required=True)
    parser.add_argument("--fts5-results", type=Path, required=True)
    parser.add_argument("--vector-results", type=Path, required=True)
    parser.add_argument("--rrf-results", type=Path, required=True)
    parser.add_argument("--sqlite-receipt", type=Path, default=None)
    parser.add_argument("--fts5-receipt", type=Path, default=None)
    parser.add_argument("--vector-receipt", type=Path, default=None)
    parser.add_argument("--rrf-receipt", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.output.exists():
            raise CaptureError("checkpoint output 已存在，禁止覆盖 evidence")
        if not args.output.parent.is_dir():
            raise CaptureError("checkpoint output 父目录不存在")
        truth, truth_hash = _load(args.sqlite_truth, "sqlite truth")
        channels: dict[str, dict[str, Any]] = {}
        source_hashes = {"sqlite_truth": truth_hash}
        artifact_paths = {"sqlite": args.sqlite_truth}
        artifact_hashes = {"sqlite": truth_hash}
        receipt_paths = {
            "sqlite": args.sqlite_receipt,
            "fts5": args.fts5_receipt,
            "vector": args.vector_receipt,
            "rrf": args.rrf_receipt,
        }
        for channel, path in (
            ("fts5", args.fts5_results),
            ("vector", args.vector_results),
            ("rrf", args.rrf_results),
        ):
            channels[channel], source_hashes[channel] = _load(path, f"{channel} results")
            artifact_paths[channel] = path
            artifact_hashes[channel] = source_hashes[channel]
        if args.capture_handoff is None:
            raise CaptureError("缺少 d14b-capture-handoff：禁止无 provenance 采集")
        capture_handoff, capture_handoff_sha = _load(args.capture_handoff, "d14b-capture-handoff")
        provenance = _verify_receipts(
            tested_commit=args.tested_commit,
            capture_handoff=capture_handoff,
            capture_handoff_sha=capture_handoff_sha,
            artifact_hashes=artifact_hashes,
            artifact_paths=artifact_paths,
            receipt_paths=receipt_paths,
        )
        output = build_checkpoint(
            tested_commit=args.tested_commit,
            checkpoint=args.checkpoint,
            user_id=args.user_id,
            captured_at_utc=args.captured_at_utc,
            truth=truth,
            channels=channels,
            provenance=provenance,
        )
        args.output.write_text(
            json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except CaptureError as error:
        print(f"D14B_CAPTURE_FAIL: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())