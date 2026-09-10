"""CLI tests for the D14C read-only runtime precheck collector."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts" / "collect_d14c_runtime_precheck.py"
HEAD = "a" * 40


def _request() -> dict:
    return {
        "run_id": "precheck-20260908-cli",
        "tested_commit": HEAD,
        "environment_id": "kylin-vm-01",
        "vm": {"name": "Kylin VM", "uuid": "vm-uuid", "snapshot": "clean", "snapshot_uuid": "snapshot-uuid"},
        "ai_assistant": {"path": "/missing/assistant", "version": "1", "pid": 1},
        "memory_client": {"path": "/missing/client", "build_id": "build-1", "pid": 1},
        "memory_service": {"package_path": "/missing/package", "pid": 1, "unit": "kylin-memory.service"},
        "socket_path": "/missing/socket",
        "db_path": "/missing/database.db",
        "runtime_ids": {"session_id": "s", "trace_id": "t", "turn_id": "turn", "event_id": "event", "execution_record_id": "record"},
        "command": {"name": "three-component-precheck", "exit_code": 0},
    }


def test_cli_writes_precheck_observation_without_promoting_missing_components(tmp_path):
    request = tmp_path / "request.json"
    output = tmp_path / "observation.json"
    request.write_text(json.dumps(_request()), encoding="utf-8")

    completed = subprocess.run([sys.executable, str(CLI), str(request), "--output", str(output)], capture_output=True, text=True, timeout=30)

    observation = json.loads(output.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert observation["status"] == "PRECHECK_OBSERVATION"
    assert observation["formal_dispatch"] == "NOT_STARTED"
    assert observation["components"]["ai_assistant"]["binary"]["exists"] is False


def test_cli_rejects_incomplete_request_without_creating_output(tmp_path):
    request = tmp_path / "request.json"
    output = tmp_path / "observation.json"
    request.write_text("{}", encoding="utf-8")

    completed = subprocess.run([sys.executable, str(CLI), str(request), "--output", str(output)], capture_output=True, text=True, timeout=30)

    assert completed.returncode == 2
    assert json.loads(completed.stdout)["status"] == "REJECTED"
    assert not output.exists()


def test_cli_rejects_unsupported_runtime_ids_without_echoing_plaintext(tmp_path):
    request = tmp_path / "request.json"
    output = tmp_path / "observation.json"
    payload = _request()
    payload["runtime_ids"].update(
        {
            "user_text": "USER_SECRET_123",
            "assistant_text": "ASSISTANT_SECRET_456",
            "token": "TOKEN_SECRET_789",
            "secret": "TOP_SECRET",
        }
    )
    request.write_text(json.dumps(payload), encoding="utf-8")

    completed = subprocess.run([sys.executable, str(CLI), str(request), "--output", str(output)], capture_output=True, text=True, timeout=30)

    assert completed.returncode == 2
    assert json.loads(completed.stdout)["status"] == "REJECTED"
    assert not output.exists()
    for plaintext in ("USER_SECRET_123", "ASSISTANT_SECRET_456", "TOKEN_SECRET_789", "TOP_SECRET"):
        assert plaintext not in completed.stdout
        assert plaintext not in completed.stderr
