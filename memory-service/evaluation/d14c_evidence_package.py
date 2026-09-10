"""Integrity validation for a completed-or-failed D14C evidence package.

This validates package integrity only.  A package marked ``FAILED`` may pass
this validator, but that never means its runtime result passed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_ROOT_NAME = re.compile(r"^d14c_[A-Za-z0-9][A-Za-z0-9_.-]*$")
_STATUSES = frozenset({"VERIFIED", "FAILED", "BLOCKED", "UNVERIFIED"})
_REQUIRED_ROLES = frozenset({"run_identity", "commands", "exit_codes"})
_SUCCESS_ROLES = frozenset({"runtime_capture", "evaluator_report"})


class D14CEvidenceError(ValueError):
    """Evidence package cannot be accepted as integrity-checked."""


def _read_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise D14CEvidenceError(f"{label} must be readable UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise D14CEvidenceError(f"{label} must be a JSON object")
    return data


def _safe_file(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise D14CEvidenceError(f"{label} must be a non-empty relative path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise D14CEvidenceError(f"{label} must be a safe relative path")
    resolved = (root / relative).resolve()
    if root.resolve() not in resolved.parents or not resolved.is_file():
        raise D14CEvidenceError(f"{label} must resolve to a regular file inside evidence root")
    return relative


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checksums(root: Path) -> dict[Path, str]:
    path = root / "SHA256SUMS"
    if not path.is_file():
        raise D14CEvidenceError("SHA256SUMS is required")
    entries: dict[Path, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise D14CEvidenceError(f"SHA256SUMS line {number} has invalid format")
        relative = _safe_file(root, match.group(2), f"SHA256SUMS line {number}")
        if relative in entries:
            raise D14CEvidenceError("SHA256SUMS must not contain duplicate paths")
        entries[relative] = match.group(1)
    if not entries:
        raise D14CEvidenceError("SHA256SUMS must not be empty")
    return entries


def validate_evidence_package(root: Path) -> dict[str, str]:
    """Check manifest identities, required roles, and every package checksum."""
    root = root.resolve()
    if not root.is_dir() or not _ROOT_NAME.fullmatch(root.name):
        raise D14CEvidenceError("evidence root must be an existing d14c_* directory")
    manifest = _read_json(root / "manifest.json", "manifest.json")
    if manifest.get("schema_version") != "d14c-evidence-manifest/v1":
        raise D14CEvidenceError("manifest schema_version is invalid")
    status = manifest.get("run_status")
    if status not in _STATUSES:
        raise D14CEvidenceError("manifest run_status is invalid")
    commit = manifest.get("tested_commit")
    if not isinstance(commit, str) or not _GIT_SHA.fullmatch(commit):
        raise D14CEvidenceError("manifest tested_commit must be a full lowercase Git SHA")
    environment_id = manifest.get("environment_id")
    if not isinstance(environment_id, str) or not environment_id:
        raise D14CEvidenceError("manifest environment_id must be a non-empty string")
    files = manifest.get("files")
    if not isinstance(files, dict) or not _REQUIRED_ROLES <= set(files):
        raise D14CEvidenceError("manifest lacks required evidence roles")
    if status == "VERIFIED" and not _SUCCESS_ROLES <= set(files):
        raise D14CEvidenceError("VERIFIED package lacks runtime_capture or evaluator_report")
    if status != "VERIFIED" and not isinstance(manifest.get("failure_summary"), str):
        raise D14CEvidenceError("non-VERIFIED package requires failure_summary")
    roles = {name: _safe_file(root, path, f"manifest.files.{name}") for name, path in files.items()}
    identity = _read_json(root / roles["run_identity"], "run identity")
    if identity.get("tested_commit") != commit or identity.get("environment_id") != environment_id:
        raise D14CEvidenceError("run identity must equal manifest tested_commit and environment_id")
    entries = _checksums(root)
    actual_files = {path.relative_to(root) for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS"}
    if set(entries) != actual_files:
        raise D14CEvidenceError("SHA256SUMS must cover every regular file exactly once")
    for relative, expected in entries.items():
        if _sha256(root / relative) != expected:
            raise D14CEvidenceError(f"SHA256SUMS mismatch for {relative.as_posix()}")
    return {"status": "PACKAGE_INTEGRITY_VERIFIED", "run_status": status, "tested_commit": commit, "environment_id": environment_id}
