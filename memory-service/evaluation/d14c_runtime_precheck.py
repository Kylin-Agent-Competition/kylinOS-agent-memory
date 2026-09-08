"""Read-only D14C runtime identity and three-component precheck collector.

The collector is deliberately an observation seam.  It records process and
deployment identity without reading user or assistant content, and never
returns a runtime verdict or creates a formal evidence root.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import platform
import re
import subprocess
from typing import Any, Mapping, Protocol


_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
SCHEMA_VERSION = "d14c-runtime-precheck/v1"


class D14CPrecheckError(ValueError):
    """The caller did not provide a safe, complete precheck request."""


class RuntimeProbe(Protocol):
    """Read-only host inspection boundary used by the collector."""

    def os_release(self) -> Mapping[str, Any]: ...

    def file_identity(self, path: str) -> Mapping[str, Any]: ...

    def process_identity(self, pid: int) -> Mapping[str, Any]: ...

    def systemd_show(self, unit: str) -> Mapping[str, Any]: ...

    def path_identity(self, path: str) -> Mapping[str, Any]: ...


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_identity(path: str, *, include_sha256: bool) -> dict[str, Any]:
    target = Path(path)
    try:
        metadata = target.stat()
    except OSError as exc:
        return {"path": path, "exists": False, "reason": type(exc).__name__}
    identity: dict[str, Any] = {
        "path": path,
        "exists": True,
        "owner_uid": metadata.st_uid,
        "mode": f"{metadata.st_mode & 0o7777:04o}",
    }
    if include_sha256 and target.is_file():
        try:
            identity["sha256"] = _sha256_file(target)
        except OSError as exc:
            identity["sha256_error"] = type(exc).__name__
    return identity


class SystemRuntimeProbe:
    """Linux/VM implementation of :class:`RuntimeProbe`, with safe failures."""

    def os_release(self) -> Mapping[str, Any]:
        release: dict[str, Any] = {"kernel": platform.release(), "kylin_release_id": None}
        try:
            entries = {}
            for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator:
                    entries[key] = value.strip().strip('"')
            release["kylin_release_id"] = entries.get("ID") or entries.get("PRETTY_NAME")
        except OSError as exc:
            release["os_release_reason"] = type(exc).__name__
        return release

    def file_identity(self, path: str) -> Mapping[str, Any]:
        return _path_identity(path, include_sha256=True)

    def path_identity(self, path: str) -> Mapping[str, Any]:
        return _path_identity(path, include_sha256=False)

    def process_identity(self, pid: int) -> Mapping[str, Any]:
        process = Path("/proc") / str(pid)
        try:
            metadata = process.stat()
            raw_cmdline = (process / "cmdline").read_bytes()
        except OSError as exc:
            return {"pid": pid, "running": False, "reason": type(exc).__name__}
        identity: dict[str, Any] = {
            "pid": pid,
            "running": True,
            "owner_uid": metadata.st_uid,
            "cmdline_sha256": hashlib.sha256(raw_cmdline).hexdigest(),
            "cmdline_length": len(raw_cmdline),
        }
        try:
            identity["cwd"] = os.readlink(process / "cwd")
        except OSError:
            pass
        return identity

    def systemd_show(self, unit: str) -> Mapping[str, Any]:
        command = (
            "systemctl",
            "--user",
            "show",
            unit,
            "--property=FragmentPath,MainPID,ActiveEnterTimestamp,ExecStart",
        )
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"unit": unit, "exit_code": None, "reason": type(exc).__name__}
        if completed.returncode:
            return {"unit": unit, "exit_code": completed.returncode, "reason": "SYSTEMD_SHOW_FAILED"}
        fields = dict(line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line)
        exec_start = fields.get("ExecStart", "")
        return {
            "unit": unit,
            "exit_code": 0,
            "fragment_path": fields.get("FragmentPath") or None,
            "main_pid": int(fields["MainPID"]) if fields.get("MainPID", "").isdigit() else None,
            "active_enter_timestamp": fields.get("ActiveEnterTimestamp") or None,
            "exec_start_sha256": hashlib.sha256(exec_start.encode("utf-8")).hexdigest(),
            "exec_start_length": len(exec_start),
        }


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise D14CPrecheckError(f"{label} must be an object")
    return value


def _text(data: Mapping[str, Any], key: str, label: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise D14CPrecheckError(f"{label}.{key} must be a non-empty string")
    return value.strip()


def _pid(data: Mapping[str, Any], key: str, label: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or value <= 0:
        raise D14CPrecheckError(f"{label}.{key} must be a positive integer")
    return value


def _safe_process(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in ("pid", "running", "owner_uid", "cwd", "cmdline_sha256", "cmdline_length", "reason") if key in value}


def _safe_systemd(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in ("unit", "exit_code", "fragment_path", "main_pid", "active_enter_timestamp", "exec_start_sha256", "exec_start_length", "reason") if key in value}


def collect_precheck_observation(request: Mapping[str, Any], *, probe: RuntimeProbe) -> dict[str, Any]:
    """Collect a safe, read-only three-component runtime observation.

    The returned object is intentionally not compatible with formal runtime
    evidence and is fixed at ``PRECHECK_OBSERVATION``.
    """

    run_id = _text(request, "run_id", "request")
    tested_commit = _text(request, "tested_commit", "request")
    if not _GIT_SHA.fullmatch(tested_commit):
        raise D14CPrecheckError("request.tested_commit must be a full lowercase Git SHA")
    environment_id = _text(request, "environment_id", "request")
    vm = _object(request.get("vm"), "vm")
    assistant = _object(request.get("ai_assistant"), "ai_assistant")
    client = _object(request.get("memory_client"), "memory_client")
    service = _object(request.get("memory_service"), "memory_service")
    runtime_ids = _object(request.get("runtime_ids"), "runtime_ids")
    command = _object(request.get("command"), "command")

    assistant_path, assistant_pid = _text(assistant, "path", "ai_assistant"), _pid(assistant, "pid", "ai_assistant")
    client_path, client_pid = _text(client, "path", "memory_client"), _pid(client, "pid", "memory_client")
    service_package, service_pid = _text(service, "package_path", "memory_service"), _pid(service, "pid", "memory_service")
    service_unit = _text(service, "unit", "memory_service")
    socket_path, db_path = _text(request, "socket_path", "request"), _text(request, "db_path", "request")
    vm_identity = {key: _text(vm, key, "vm") for key in ("name", "uuid", "snapshot", "snapshot_uuid")}
    for key in ("session_id", "trace_id", "turn_id", "event_id", "execution_record_id"):
        _text(runtime_ids, key, "runtime_ids")
    _text(command, "name", "command")
    if not isinstance(command.get("exit_code"), int):
        raise D14CPrecheckError("command.exit_code must be an integer")

    started_at = datetime.now(timezone.utc)
    observation = {
        "schema_version": SCHEMA_VERSION,
        "status": "PRECHECK_OBSERVATION",
        "formal_dispatch": "NOT_STARTED",
        "provenance": {
            "run_id": run_id,
            "tested_commit": tested_commit,
            "environment_id": environment_id,
            "evidence_root": None,
            "evidence_root_status": "NOT_CREATED_BY_DESIGN",
        },
        "vm": {**vm_identity, **dict(probe.os_release())},
        "components": {
            "ai_assistant": {
                "binary": dict(probe.file_identity(assistant_path)),
                "version": _text(assistant, "version", "ai_assistant"),
                "process": _safe_process(probe.process_identity(assistant_pid)),
            },
            "memory_client": {
                "binary": dict(probe.file_identity(client_path)),
                "build_id": _text(client, "build_id", "memory_client"),
                "process": _safe_process(probe.process_identity(client_pid)),
            },
            "memory_service": {
                "package": dict(probe.file_identity(service_package)),
                "process": _safe_process(probe.process_identity(service_pid)),
                "systemd": _safe_systemd(probe.systemd_show(service_unit)),
            },
        },
        "socket": dict(probe.path_identity(socket_path)),
        "database": {"path": db_path, "identity": dict(probe.path_identity(db_path)), "checkpoint_references": []},
        "runtime_ids": dict(runtime_ids),
        "command": {"name": command["name"], "exit_code": command["exit_code"]},
        "safety": {"user_plaintext_recorded": False, "assistant_plaintext_recorded": False},
    }
    finished_at = datetime.now(timezone.utc)
    observation["timing"] = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "latency_ms": round((finished_at - started_at).total_seconds() * 1000, 3),
    }
    return observation
