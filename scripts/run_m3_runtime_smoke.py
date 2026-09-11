"""Run the reproducible, isolated M3 runtime smoke and write its evidence.

This runner deliberately exercises the real ``event.ingest`` handler against a
new SQLite database.  It is an isolated Main runtime check, not a claim about a
remote Kylin host or system-wide production readiness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "memory-service"))

from db.engine import create_db_engine, init_schema  # noqa: E402
from db.schema import source_events  # noqa: E402
from db.uow import UnitOfWork  # noqa: E402
from gateway.handlers import register_default_handlers, register_event_ingest_handler  # noqa: E402
from gateway.registry import HandlerRegistry, RequestContext  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _git(*args: str, binary: bool = False) -> str | bytes:
    completed = subprocess.run(
        ["git", "-C", str(REPOSITORY_ROOT), *args],
        check=True,
        capture_output=True,
    )
    return completed.stdout if binary else completed.stdout.decode("utf-8").strip()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _counts(engine: Any) -> dict[str, int]:
    with engine.connect() as conn:
        return {"source_events": len(conn.execute(select(source_events.c.id)).all())}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated M3 runtime smoke")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise SystemExit("output directory must not already exist")
    if _git("status", "--porcelain"):
        raise SystemExit("worktree must be clean before an M3 smoke run")

    tested_commit = str(_git("rev-parse", "HEAD"))
    source_tree_sha256 = hashlib.sha256(_git("archive", "--format=tar", "HEAD", binary=True)).hexdigest()
    output_dir.mkdir(parents=True)
    stdout_path = output_dir / "stdout.log"
    stderr_path = output_dir / "stderr.log"
    command = f'"{sys.executable}" "{Path(__file__).resolve()}" --output-dir "{output_dir}"'
    (output_dir / "runner_command.txt").write_text(command + "\n", encoding="utf-8", newline="\n")

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "0.1",
        "event_id": "m3-runtime-tool-event-001",
        "user_id": "m3_runtime_user",
        "actor_id": "m3_runtime_user",
        "session_id": "m3-runtime-session-001",
        "idempotency_key": "m3-runtime-idem-001",
        "source_type": "tool_result",
        "event_type": "agent_response",
        "source_business_status": "success",
        "occurred_at": now,
        "captured_at": now,
        "content_summary": "M3 isolated runtime probe: file-status tool completed successfully.",
        "tool_call_id": "m3-tool-call-001",
        # A tool-result source is accepted only after the upstream raw-payload
        # security check.  This is a true contract input, not a bypass.
        "payload_security_checked": True,
        "consent_scope": "memory_only",
    }
    _write_json(output_dir / "input_script.json", {"method": "event.ingest", "payload": payload})

    trace: list[dict[str, Any]] = []
    with stdout_path.open("w", encoding="utf-8", newline="\n") as stdout, stderr_path.open("w", encoding="utf-8", newline="\n") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr), tempfile.TemporaryDirectory(prefix="m3-runtime-state-") as state_dir:
            db_path = Path(state_dir) / "m3-runtime.sqlite"
            engine = create_db_engine(str(db_path))
            init_schema(engine)
            registry = HandlerRegistry()
            register_default_handlers(registry)
            register_event_ingest_handler(registry, uow_factory=lambda: UnitOfWork(engine))
            handler = registry.route("event.ingest")
            before = _counts(engine)
            _write_json(output_dir / "side_effect_before.json", before)
            trace.append({"step": "before", "source_events": before["source_events"], "utc": now})
            context = RequestContext(
                request_id="m3-runtime-request-001",
                trace_id="m3-runtime-trace-001",
                method="event.ingest",
                deadline_ms=5000,
                user_id=payload["user_id"],
                session_id=payload["session_id"],
                idempotency_key=payload["idempotency_key"],
            )
            response = handler(payload, context)
            if response.get("admission_decision") != "allow_extraction":
                raise RuntimeError("M3 tool-result probe was not admitted for extraction")
            with engine.connect() as conn:
                row = conn.execute(
                    select(
                        source_events.c.event_id,
                        source_events.c.user_id,
                        source_events.c.tool_call_id,
                        source_events.c.admission_decision,
                        source_events.c.source_business_status,
                    ).where(source_events.c.event_id == payload["event_id"])
                ).mappings().one()
            after = _counts(engine)
            if before["source_events"] != 0 or after["source_events"] != 1:
                raise RuntimeError("unexpected source_events side effect count")
            if row["tool_call_id"] != payload["tool_call_id"]:
                raise RuntimeError("persisted tool_call_id does not match input")
            after_evidence = {**after, "persisted_event": dict(row)}
            _write_json(output_dir / "side_effect_after.json", after_evidence)
            trace.append({"step": "event.ingest", "response": response, "utc": datetime.now(timezone.utc).isoformat()})
            trace.append({"step": "after", **after_evidence, "utc": datetime.now(timezone.utc).isoformat()})
            # Windows keeps an SQLite handle open until SQLAlchemy's pool is
            # disposed; release it before TemporaryDirectory cleanup.
            engine.dispose()

    trace_path = output_dir / "raw_trace.jsonl"
    trace_path.write_text("".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in trace), encoding="utf-8", newline="\n")
    receipt = {
        "receipt_version": "m3-runtime-receipt/v1",
        "status": "PASS",
        "execution_scope": "isolated_local_sqlite",
        "tested_commit": tested_commit,
        "build_sha256": source_tree_sha256,
        "runtime_execution_real": True,
        "mock_used": False,
        "trace_present": True,
        "actual_status_evidenced": True,
        "side_effect_evidenced": True,
        "checkpoint_chain_complete": True,
        "tool_call_id_present": True,
        "tool_not_applicable": False,
        "tool_call_id": payload["tool_call_id"],
        "actual_status": "event.ingest completed with allow_extraction; persisted source event admission is recorded in side_effect_after.json",
        "limits": [
            "No remote Kylin host deployment was exercised.",
            "This receipt does not claim system production readiness or authorize Runtime160 execution.",
        ],
        "artifacts": {name: _sha256(output_dir / name) for name in (
            "runner_command.txt", "input_script.json", "raw_trace.jsonl",
            "side_effect_before.json", "side_effect_after.json", "stdout.log", "stderr.log",
        )},
    }
    _write_json(output_dir / "runtime_smoke_receipt.json", receipt)
    print(json.dumps({"status": "PASS", "output_dir": str(output_dir), "tested_commit": tested_commit}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
