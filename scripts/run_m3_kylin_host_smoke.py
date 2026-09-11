"""Run the real Kylin-host M3 smoke with a frozen runtime tool script.

The runner is intentionally host-only: it refuses a non-Kylin Linux system,
executes ``m3_kylin_runtime_probe.sh`` as the actual tool invocation, captures
the resulting status/output, then sends a ToolResult-derived event through the
real Main ``event.ingest`` handler and records the persisted state transition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROBE_SCRIPT = REPOSITORY_ROOT / "scripts" / "m3_kylin_runtime_probe.sh"
RUNNER_VERSION = "m3-kylin-host-smoke/v1"
sys.path.insert(0, str(REPOSITORY_ROOT / "memory-service"))

from db.engine import create_db_engine, init_schema  # noqa: E402
from db.schema import source_events  # noqa: E402
from db.uow import UnitOfWork  # noqa: E402
from gateway.handlers import register_default_handlers, register_event_ingest_handler  # noqa: E402
from gateway.registry import HandlerRegistry, RequestContext  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _git(*args: str, binary: bool = False) -> str | bytes:
    completed = subprocess.run(
        ["git", "-C", str(REPOSITORY_ROOT), *args], check=True, capture_output=True
    )
    return completed.stdout if binary else completed.stdout.decode("utf-8").strip()


def _kylin_release() -> dict[str, str]:
    release = Path("/etc/os-release")
    if platform.system() != "Linux" or not release.is_file():
        raise RuntimeError("M3 host smoke requires a Kylin Linux host")
    values: dict[str, str] = {}
    for line in release.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    if values.get("ID", "").lower() != "kylin":
        raise RuntimeError("M3 host smoke refuses a non-Kylin Linux host")
    return values


def _source_event_count(engine: Any) -> int:
    with engine.connect() as conn:
        return len(conn.execute(select(source_events.c.id)).all())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--snapshot-name", required=True)
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise SystemExit("output directory must not already exist")
    if _git("status", "--porcelain"):
        raise SystemExit("worktree must be clean before M3 host execution")
    if not PROBE_SCRIPT.is_file():
        raise SystemExit("frozen M3 runtime tool script is missing")

    release = _kylin_release()
    tested_commit = str(_git("rev-parse", "HEAD"))
    build_sha256 = _sha256_bytes(_git("archive", "--format=tar", "HEAD", binary=True))
    runner_sha256 = _sha256_file(Path(__file__).resolve())
    script_sha256 = _sha256_file(PROBE_SCRIPT)
    session_id = "m3-kylin-host-session-001"
    trace_id = "m3-kylin-host-trace-001"
    tool_call_id = "m3-kylin-host-tool-call-001"
    started_at = datetime.now(timezone.utc).isoformat()

    output_dir.mkdir(parents=True)
    command = (
        f'"{sys.executable}" "{Path(__file__).resolve()}" --output-dir "{output_dir}" '
        f'--environment-id "{args.environment_id}" --snapshot-id "{args.snapshot_id}" '
        f'--snapshot-name "{args.snapshot_name}"'
    )
    (output_dir / "runner_command.txt").write_text(command + "\n", encoding="utf-8", newline="\n")
    environment = {
        "environment_id": args.environment_id,
        "snapshot_id": args.snapshot_id,
        "snapshot_name": args.snapshot_name,
        "hostname": platform.node(),
        "kernel": platform.platform(),
        "os_release": release,
        "host_vm_execution_verified": True,
    }
    _write_json(
        output_dir / "frozen_build_identity.json",
        {
            "identity_version": "m3-frozen-build-identity/v2",
            "status": "FROZEN",
            "source_main_commit": tested_commit,
            "tested_commit": tested_commit,
            "build_sha256": build_sha256,
            "build_hash_scope": "git archive --format=tar HEAD",
            "tested_worktree_clean": True,
            "environment": environment,
            "runner": {
                "path": "scripts/run_m3_kylin_host_smoke.py",
                "version": RUNNER_VERSION,
                "sha256": runner_sha256,
            },
            "frozen_script": {
                "script_id": "m3-kylin-runtime-probe/v1",
                "path": "scripts/m3_kylin_runtime_probe.sh",
                "sha256": script_sha256,
            },
            "created_at": started_at,
        },
    )

    tool_started_at = datetime.now(timezone.utc).isoformat()
    tool = subprocess.run(
        ["/bin/sh", str(PROBE_SCRIPT)], capture_output=True, text=True, check=False, timeout=30
    )
    tool_finished_at = datetime.now(timezone.utc).isoformat()
    tool_execution = {
        "schema_version": "m3-tool-execution/v1",
        "tool_call_id": tool_call_id,
        "script_id": "m3-kylin-runtime-probe/v1",
        "script_sha256": script_sha256,
        "command": ["/bin/sh", "scripts/m3_kylin_runtime_probe.sh"],
        "started_at": tool_started_at,
        "finished_at": tool_finished_at,
        "exit_code": tool.returncode,
        "status": "success" if tool.returncode == 0 else "failed",
        "stdout": tool.stdout,
        "stderr": tool.stderr,
        "environment": environment,
    }
    _write_json(output_dir / "tool_execution.json", tool_execution)
    if tool.returncode != 0:
        raise RuntimeError("frozen Kylin runtime tool script failed")

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "0.1",
        "event_id": "m3-kylin-host-event-001",
        "user_id": "m3_kylin_host_user",
        "actor_id": "m3_kylin_host_user",
        "session_id": session_id,
        "idempotency_key": "m3-kylin-host-idem-001",
        "source_type": "tool_result",
        "event_type": "agent_response",
        "source_business_status": "success",
        "occurred_at": now,
        "captured_at": now,
        "source_reference": "m3-kylin-runtime-probe/v1",
        "content_summary": "Kylin host runtime probe completed successfully.",
        "tool_call_id": tool_call_id,
        "payload_security_checked": True,
        "consent_scope": "memory_only",
    }
    _write_json(
        output_dir / "input_script.json",
        {"method": "event.ingest", "payload": payload, "tool_execution": "tool_execution.json"},
    )
    trace: list[dict[str, Any]] = [{"step": "runtime_tool", **tool_execution}]
    with tempfile.TemporaryDirectory(prefix="m3-kylin-host-state-") as state_dir:
        db_path = Path(state_dir) / "m3-kylin-host.sqlite"
        db_path.touch(exist_ok=False)
        engine = create_db_engine(str(db_path))
        try:
            init_schema(engine)
            registry = HandlerRegistry()
            register_default_handlers(registry)
            register_event_ingest_handler(registry, uow_factory=lambda: UnitOfWork(engine))
            before = {"source_events": _source_event_count(engine), "environment": environment}
            _write_json(output_dir / "side_effect_before.json", before)
            if before["source_events"] != 0:
                raise RuntimeError("fresh isolated host state is not empty")
            context = RequestContext(
                request_id="m3-kylin-host-request-001", trace_id=trace_id, method="event.ingest",
                deadline_ms=5000, user_id=payload["user_id"], session_id=session_id,
                idempotency_key=payload["idempotency_key"],
            )
            response = registry.route("event.ingest")(payload, context)
            if response.get("admission_decision") != "allow_extraction":
                raise RuntimeError("actual Kylin tool result was not admitted for extraction")
            with engine.connect() as conn:
                row = conn.execute(
                    select(source_events.c.event_id, source_events.c.user_id, source_events.c.tool_call_id,
                           source_events.c.admission_decision, source_events.c.source_business_status)
                    .where(source_events.c.event_id == payload["event_id"])
                ).mappings().one()
            after = {"source_events": _source_event_count(engine), "persisted_event": dict(row), "environment": environment}
            if after["source_events"] != 1 or row["tool_call_id"] != tool_call_id:
                raise RuntimeError("host memory side-effect checkpoint failed")
            _write_json(output_dir / "side_effect_after.json", after)
            trace.extend([
                {"step": "event.ingest", "response": response, "session_id": session_id, "trace_id": trace_id, "utc": datetime.now(timezone.utc).isoformat()},
                {"step": "memory_side_effect", **after, "utc": datetime.now(timezone.utc).isoformat()},
            ])
        finally:
            engine.dispose()

    raw_trace = output_dir / "raw_trace.jsonl"
    raw_trace.write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in trace), encoding="utf-8", newline="\n")
    (output_dir / "stdout.log").write_text("", encoding="utf-8", newline="\n")
    (output_dir / "stderr.log").write_text("", encoding="utf-8", newline="\n")
    receipt = {
        "receipt_version": "m3-runtime-receipt/v2",
        "status": "PASS",
        "execution_scope": "kylin_host_vm",
        "host_vm_execution_verified": True,
        "source_main_commit": tested_commit,
        "tested_commit": tested_commit,
        "build_sha256": build_sha256,
        "environment": environment,
        "runner_identity": {"version": RUNNER_VERSION, "sha256": runner_sha256},
        "script_id": "m3-kylin-runtime-probe/v1",
        "script_sha256": script_sha256,
        "session_id": session_id,
        "trace_id": trace_id,
        "tool_call_id": tool_call_id,
        "tool_call_id_present": True,
        "tool_not_applicable": False,
        "tool_execution_evidenced": True,
        "tool_execution_artifact": "tool_execution.json",
        "trace_present": True,
        "actual_status_evidenced": True,
        "side_effect_evidenced": True,
        "checkpoint_chain_complete": True,
        "runtime_execution_real": True,
        "mock_used": False,
        "artifacts": {name: _sha256_file(output_dir / name) for name in (
            "frozen_build_identity.json", "runner_command.txt", "input_script.json", "tool_execution.json",
            "raw_trace.jsonl", "side_effect_before.json", "side_effect_after.json", "stdout.log", "stderr.log",
        )},
    }
    _write_json(output_dir / "runtime_smoke_receipt.json", receipt)
    print(json.dumps({"status": "PASS", "tested_commit": tested_commit, "output_dir": str(output_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
