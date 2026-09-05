#!/usr/bin/env python3
"""Collect D13C D-track L2 evidence from a deployed memory-service.

This collector intentionally uses only active production methods (echo and
memory.retrieve).  Candidate write methods are reported as BLOCKED unless a
separately approved host mapping activates them; it never enables test seams
or mutates the service database while collecting production evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import socket
import sqlite3
import stat
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = "1.0"
REDACTED_FIELDS = frozenset({"confirmation_token", "confirmation_credential", "token"})


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "<REDACTED>" if key.lower() in REDACTED_FIELDS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def percentile(values: list[float], percent: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, (len(ordered) * percent + 99) // 100 - 1))
    return ordered[index]


def recv_frame(connection: socket.socket) -> dict[str, Any]:
    buffer = b""
    while len(buffer) < 4:
        chunk = connection.recv(4096)
        if not chunk:
            raise ConnectionError("socket closed before frame header")
        buffer += chunk
    size = struct.unpack(">I", buffer[:4])[0]
    while len(buffer) < 4 + size:
        chunk = connection.recv(4096)
        if not chunk:
            raise ConnectionError("socket closed before frame body")
        buffer += chunk
    return json.loads(buffer[4 : 4 + size].decode("utf-8"))


def request(socket_path: str, method: str, payload: dict[str, Any], request_id: str) -> tuple[dict[str, Any], float]:
    envelope = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "trace_id": f"d13c-{request_id}",
        "method": method,
        "deadline_ms": 5000,
        "payload": payload,
    }
    body = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    started = time.monotonic()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(6.0)
        connection.connect(socket_path)
        connection.sendall(struct.pack(">I", len(body)) + body)
        response = recv_frame(connection)
    return response, (time.monotonic() - started) * 1000


def result(case_id: str, status: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"id": case_id, "status": status, "detail": detail, **extra}


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(redact(record), ensure_ascii=False, sort_keys=True) + "\n")


def sqlite_environment(db_path: str | None) -> dict[str, Any]:
    info: dict[str, Any] = {"python_sqlite_version": sqlite3.sqlite_version}
    if not db_path:
        return info
    try:
        connection = sqlite3.connect(f"file:{Path(db_path).resolve().as_posix()}?mode=ro", uri=True)
        try:
            tables = connection.execute("select name from sqlite_master where type='table' order by name").fetchall()
            info["tables"] = [row[0] for row in tables]
        finally:
            connection.close()
    except sqlite3.Error as exc:
        info["read_only_query_error"] = str(exc)
    return info


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True, help="deployed memory-service UDS path")
    parser.add_argument("--db", help="deployed SQLite database path, opened read-only")
    parser.add_argument("--output-dir", required=True, help="new evidence output directory")
    parser.add_argument("--iterations", type=int, default=30, help="retrieve latency samples (default: 30)")
    parser.add_argument("--tested-commit", required=True, help="exact deployed source commit SHA")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    socket_path = Path(args.socket)
    now = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    environment = {
        "collected_at": now,
        "tested_commit": args.tested_commit,
        "platform": platform.platform(),
        "python": sys.version,
        "socket": str(socket_path),
        "sqlite": sqlite_environment(args.db),
    }
    if socket_path.exists():
        mode = stat.S_IMODE(socket_path.stat().st_mode)
        results.append(result("D-L2-01", "VERIFIED" if mode == 0o600 else "FAILED", "socket exists", mode=oct(mode)))
    else:
        results.append(result("D-L2-01", "FAILED", "socket file does not exist"))

    try:
        echo, elapsed = request(str(socket_path), "echo", {"method": "echo"}, "d13c-echo")
        records.append({"method": "echo", "request": {"method": "echo"}, "response": echo, "elapsed_ms": elapsed})
        connected = echo.get("status") == "ok"
        results.append(result("D-L2-02", "VERIFIED" if connected else "FAILED", "echo connection result", response_status=echo.get("status")))
        valid_echo = connected and echo.get("data", {}).get("echo", {}).get("method") == "echo"
        results.append(result("D-L2-03", "VERIFIED" if valid_echo else "FAILED", "length-prefixed echo envelope", response=echo))
    except (OSError, ConnectionError, ValueError, json.JSONDecodeError) as exc:
        results.extend([
            result("D-L2-02", "FAILED", f"echo connection failed: {exc}"),
            result("D-L2-03", "FAILED", "echo envelope unavailable"),
        ])

    latencies: list[float] = []
    retrieve_response: dict[str, Any] | None = None
    for index in range(args.iterations):
        try:
            response, elapsed = request(str(socket_path), "memory.retrieve", {"query": "D13C controlled empty-query probe"}, f"d13c-retrieve-{index}")
            records.append({"method": "memory.retrieve", "iteration": index, "response": response, "elapsed_ms": elapsed})
            latencies.append(elapsed)
            retrieve_response = response
        except (OSError, ConnectionError, ValueError, json.JSONDecodeError) as exc:
            records.append({"method": "memory.retrieve", "iteration": index, "error": str(exc)})
            break

    context = retrieve_response.get("data", {}).get("context") if retrieve_response else None
    valid_context = isinstance(context, dict) and {"selected_memory_ids", "context_version", "injection_status"}.issubset(context)
    results.append(result("D-L2-04", "VERIFIED" if valid_context else "FAILED", "MemoryContext schema check", observed_context=context))
    empty_skipped = isinstance(context, dict) and context.get("injection_status") == "skipped" and not context.get("selected_memory_ids")
    results.append(result("D-L2-05", "VERIFIED" if empty_skipped else "FAILED", "empty-query must be skipped empty context", observed_context=context))
    if len(latencies) == args.iterations:
        p50, p95 = percentile(latencies, 50), percentile(latencies, 95)
        results.append(result("D-L2-06", "VERIFIED" if p50 < 300 and p95 < 1000 else "FAILED", "retrieve latency", samples=len(latencies), p50_ms=round(p50, 3), p95_ms=round(p95, 3)))
    else:
        results.append(result("D-L2-06", "FAILED", "could not collect all latency samples", samples=len(latencies)))

    blocked = "requires approved C host mapping and production handler activation; collector does not enable validation seams"
    for case_id in ("D-L2-07", "D-L2-08", "D-L2-09", "D-L2-10", "D-L2-13", "D-L2-14", "D-L2-15", "D-L2-16", "D-L2-17"):
        results.append(result(case_id, "BLOCKED", blocked))
    results.append(result("D-L2-11", "BLOCKED", "requires the C++ MemoryClient timeout state assertion in a Kylin VM"))
    results.append(result("D-L2-12", "BLOCKED", "requires an approved slow handler; no production test method may be registered"))
    for case_id in ("D-L2-18", "D-L2-19", "D-L2-20"):
        results.append(result(case_id, "BLOCKED", "requires C-track five-step orchestration and resetAllPipelines in the deployed client"))

    raw_log = output_dir / "d13c_requests_responses.jsonl"
    write_jsonl(raw_log, records)
    report = {"environment": environment, "results": results, "raw_log": raw_log.name}
    report_path = output_dir / "d13c_l2_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    manifest_path = output_dir / "SHA256SUMS"
    manifest_path.write_text("\n".join(f"{sha256(path)}  {path.name}" for path in (raw_log, report_path)) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"report": str(report_path), "manifest": str(manifest_path), "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
