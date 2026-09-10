#!/usr/bin/env python3
"""Shared fail-closed helpers for D14B production capture runners."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.capture_d14b_retrieval_snapshot import RECEIPT_FIELDS  # noqa: E402


class CaptureRunnerError(ValueError):
    """A capture runner prerequisite or production read failed."""


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaptureRunnerError(f"无法读取 {label}: {error}") from error
    if not isinstance(value, dict):
        raise CaptureRunnerError(f"{label} 必须是 JSON object")
    return value


def require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaptureRunnerError(f"{label} 必须是非空字符串")
    return value.strip()


def sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise CaptureRunnerError(f"无法读取 runner 字节: {error}") from error


def load_capture_handoff(
    *,
    channel: str,
    tested_commit: str,
    capture_handoff: Path,
    runner_file: Path,
) -> dict[str, str]:
    """Bind the calling runner to the formal handoff identity."""

    handoff = load_json(capture_handoff, "d14b-capture-handoff")
    if require_text(handoff.get("tested_commit"), "d14b-capture-handoff.tested_commit") != tested_commit:
        raise CaptureRunnerError("d14b-capture-handoff.tested_commit 与 runner 参数不一致")
    captures = handoff.get("captures")
    if not isinstance(captures, dict):
        raise CaptureRunnerError("d14b-capture-handoff.captures 必须是 object")
    entry = captures.get(channel)
    if not isinstance(entry, dict):
        raise CaptureRunnerError(f"d14b-capture-handoff.captures.{channel} 必须是 object")

    relative_path = require_text(entry.get("runner_path"), f"capture {channel}.runner_path")
    candidate = (REPO_ROOT / relative_path).resolve()
    try:
        candidate.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CaptureRunnerError(f"capture {channel}.runner_path 不得越出 repo") from error
    if candidate != runner_file.resolve():
        raise CaptureRunnerError(f"capture {channel}.runner_path 与调用 runner 不一致")
    expected_sha = require_text(entry.get("runner_sha256"), f"capture {channel}.runner_sha256")
    actual_sha = sha256_file(candidate)
    if actual_sha != expected_sha:
        raise CaptureRunnerError(f"capture {channel}.runner_sha256 与实际 runner 不一致")
    return {
        "command_id": require_text(entry.get("command_id"), f"capture {channel}.command_id"),
        "runner_path": relative_path,
        "runner_sha256": actual_sha,
    }


def utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def exclusive_json_write(path: Path, value: dict[str, Any]) -> None:
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    except FileExistsError as error:
        raise CaptureRunnerError(f"输出已存在，禁止覆盖: {path}") from error
    except OSError as error:
        raise CaptureRunnerError(f"无法写出 {path}: {error}") from error


def write_artifact_and_receipt(
    *,
    channel: str,
    tested_commit: str,
    capture_handoff: Path,
    runner_file: Path,
    artifact_path: Path,
    receipt_path: Path,
    artifact: dict[str, Any],
) -> dict[str, str]:
    identity = load_capture_handoff(
        channel=channel,
        tested_commit=tested_commit,
        capture_handoff=capture_handoff,
        runner_file=runner_file,
    )
    if not artifact_path.parent.is_dir():
        raise CaptureRunnerError(f"artifact 父目录不存在: {artifact_path}")
    if not receipt_path.parent.is_dir():
        raise CaptureRunnerError(f"receipt 父目录不存在: {receipt_path}")
    captured_at_utc = utc_now_z()
    try:
        exclusive_json_write(artifact_path, artifact)
        receipt = {
            "channel": channel,
            "tested_commit": tested_commit,
            "command_id": identity["command_id"],
            "runner_path": identity["runner_path"],
            "runner_sha256": identity["runner_sha256"],
            "artifact_path": artifact_path.name,
            "artifact_sha256": sha256_file(artifact_path),
            "captured_at_utc": captured_at_utc,
        }
        if tuple(receipt) != RECEIPT_FIELDS:
            raise CaptureRunnerError("receipt 字段契约漂移")
        exclusive_json_write(receipt_path, receipt)
    except Exception:
        artifact_path.unlink(missing_ok=True)
        raise
    return identity


def load_queries(
    path: Path,
    *,
    required_key: str,
    required_kind: str = "text",
) -> list[dict[str, Any]]:
    payload = load_json(path, "query specification")
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        raise CaptureRunnerError("query specification.queries 必须是非空数组")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, query in enumerate(queries):
        if not isinstance(query, dict):
            raise CaptureRunnerError(f"queries[{index}] 必须是 object")
        query_id = require_text(query.get("query_id"), f"queries[{index}].query_id")
        user_id = require_text(query.get("user_id"), f"queries[{index}].user_id")
        if query_id in seen:
            raise CaptureRunnerError(f"queries 存在重复 query_id: {query_id}")
        seen.add(query_id)
        if required_kind == "text":
            require_text(query.get(required_key), f"queries[{query_id}].{required_key}")
        elif required_kind == "array":
            value = query.get(required_key)
            if not isinstance(value, list) or not value:
                raise CaptureRunnerError(
                    f"queries[{query_id}].{required_key} 必须是非空数组"
                )
        else:
            raise CaptureRunnerError(f"未支持的 required_kind: {required_kind}")
        query = dict(query)
        query["query_id"] = query_id
        query["user_id"] = user_id
        normalized.append(query)
    return normalized


def open_readonly_sqlite(db_path: Path, label: str = "SQLite database") -> sqlite3.Connection:
    if not db_path.is_file():
        raise CaptureRunnerError(f"{label} 不可定位: {db_path}")
    uri = db_path.resolve().as_uri() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection
    except sqlite3.Error as error:
        raise CaptureRunnerError(f"{label} 只读连接失败: {error}") from error


def fetch_active_entries(connection: sqlite3.Connection, user_id: str) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT id, user_id, entry_type, content, version, knowledge_id, knowledge_type,
               memory_status, memory_type, is_deleted
          FROM memory_entries
         WHERE user_id = ? AND is_deleted = 0 AND memory_status = 'active'
         ORDER BY id ASC
        """,
        (user_id,),
    ).fetchall()
    if not rows:
        raise CaptureRunnerError("production truth 为空；受控用户必须已通过 production path 写入")
    for row in rows:
        knowledge_id = row["knowledge_id"]
        if not isinstance(knowledge_id, str) or not knowledge_id.strip():
            raise CaptureRunnerError(
                f"memory_entry {row['id']} 缺少 knowledge_id，无法映射受控 stable_id"
            )
    return rows


def production_identity(row: sqlite3.Row | dict[str, Any]) -> str:
    knowledge_id = require_text(row["knowledge_id"], "memory_entries.knowledge_id")
    version = int(row["version"])
    if version < 1:
        raise CaptureRunnerError("memory_entries.version 必须是正整数")
    return f"{knowledge_id}-v{version}"


def identity_map(rows: list[sqlite3.Row]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in rows:
        identity = production_identity(row)
        memory_id = str(row["id"])
        if identity in mapping or memory_id in mapping.values():
            raise CaptureRunnerError("production truth 存在重复受控 identity")
        mapping[identity] = memory_id
    return mapping
