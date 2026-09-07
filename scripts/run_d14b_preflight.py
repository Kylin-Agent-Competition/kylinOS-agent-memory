#!/usr/bin/env python3
"""Fail-closed D14B formal L3 handoff preflight.

The command only validates a D13D/D14D handoff.  It never creates an
evidence root or runs a VM command.  A zero exit code is permission to start
the *next* formal-run step, not a D14B result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PreflightError(ValueError):
    """A formal-run prerequisite is absent or inconsistent."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PreflightError(f"无法读取 {label}: {error}") from error
    if not isinstance(value, dict):
        raise PreflightError(f"{label} 必须是 JSON object")
    return value


def _required_text(payload: dict[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PreflightError(f"{label}.{key} 必须是非空字符串")
    return value.strip()


def _commit(value: str, label: str) -> str:
    if not COMMIT_RE.fullmatch(value):
        raise PreflightError(f"{label} 必须是 40 位小写 tested_commit")
    return value


def _sha256(value: str, label: str) -> str:
    if not SHA256_RE.fullmatch(value):
        raise PreflightError(f"{label} 必须是 64 位小写 SHA-256")
    return value


def _reference(value: str, label: str, repo_root: Path) -> str:
    """Accept a reachable repo artifact or an explicit HTTPS evidence URL."""

    if value.startswith("https://"):
        return value
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    if not candidate.exists():
        raise PreflightError(f"{label} 不可定位：须为已有文件/目录或 HTTPS URL")
    return value


def _package(payload: dict[str, Any], label: str) -> dict[str, str]:
    package = payload.get("package") if label == "D14D handoff" else payload
    if not isinstance(package, dict):
        raise PreflightError(f"{label}.package 必须是 object")
    return {
        "package_version": _required_text(package, "package_version", label),
        "package_tar_sha256": _sha256(
            _required_text(package, "package_tar_sha256", label),
            f"{label}.package_tar_sha256",
        ),
        "package_manifest_sha256": _sha256(
            _required_text(package, "package_manifest_sha256", label),
            f"{label}.package_manifest_sha256",
        ),
    }


def _vm(payload: dict[str, Any]) -> dict[str, str]:
    value = payload.get("vm")
    if not isinstance(value, dict):
        raise PreflightError("D14D handoff.vm 必须是 object")
    return {
        key: _required_text(value, key, "D14D handoff")
        for key in ("vm_name", "vm_uuid", "snapshot_name", "snapshot_uuid", "environment_id")
    }


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PreflightError(f"git {' '.join(args)} 失败: {detail}")
    return completed.stdout.strip()


def _verify_runner(d14d: dict[str, Any], repo_root: Path) -> None:
    """Verify an optional, handoff-pinned D14B runner without escaping repo."""

    runner = d14d.get("runner")
    if runner is None:
        return
    if not isinstance(runner, dict):
        raise PreflightError("D14D handoff.runner 必须是 object")
    relative_path = _required_text(runner, "path", "D14D handoff.runner")
    expected_sha = _sha256(
        _required_text(runner, "sha256", "D14D handoff.runner"),
        "D14D handoff.runner.sha256",
    )
    candidate = (repo_root / relative_path).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError as error:
        raise PreflightError("D14D handoff.runner.path 不得越出 repo_root") from error
    if not candidate.is_file():
        raise PreflightError("D14D handoff.runner.path 不可定位")
    actual_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        raise PreflightError("D14B runner SHA-256 与 handoff 不一致")


def validate_preflight(
    *,
    expected_tested_commit: str,
    d13d: dict[str, Any],
    d14d: dict[str, Any],
    manifest: dict[str, Any],
    repo_root: Path,
    evidence_root: Path,
) -> dict[str, Any]:
    """Validate all identity gates and return a deterministic success report."""

    expected = _commit(expected_tested_commit, "requested tested_commit")
    d13d_commit = _commit(_required_text(d13d, "tested_commit", "D13D handoff"), "D13D tested_commit")
    d14d_commit = _commit(_required_text(d14d, "tested_commit", "D14D handoff"), "D14D tested_commit")
    manifest_commit = _commit(
        _required_text(manifest, "source_commit", "package manifest"),
        "package manifest source_commit",
    )
    if len({expected, d13d_commit, d14d_commit, manifest_commit}) != 1:
        raise PreflightError("requested/D13D/D14D/package manifest 的 tested_commit 不一致")

    if _required_text(d13d, "freeze_status", "D13D handoff") != "FROZEN":
        raise PreflightError("D13D freeze_status 必须为 FROZEN")
    if _required_text(d14d, "release_status", "D14D handoff") != "L3_READY":
        raise PreflightError("D14D release_status 必须为 L3_READY")

    d14d_package = _package(d14d, "D14D handoff")
    manifest_package = _package(manifest, "package manifest")
    if d14d_package != manifest_package:
        raise PreflightError("D14D handoff 与 package manifest 的 package identity 不一致")
    _vm(d14d)

    if evidence_root.exists():
        raise PreflightError("formal evidence root 已存在，单次 run 不得复用")
    if not evidence_root.is_absolute():
        raise PreflightError("formal evidence root 必须是绝对路径")
    if not repo_root.is_dir():
        raise PreflightError("repo_root 不存在或不是目录")
    _reference(_required_text(d13d, "freeze_reference", "D13D handoff"), "D13D freeze_reference", repo_root)
    _reference(_required_text(d14d, "evidence_reference", "D14D handoff"), "D14D evidence_reference", repo_root)

    head = _git(repo_root, "rev-parse", "HEAD")
    if head != expected:
        raise PreflightError("worktree HEAD 与 tested_commit 不一致")
    if _git(repo_root, "status", "--porcelain"):
        raise PreflightError("worktree 非干净，formal run 必须停止")
    _verify_runner(d14d, repo_root)

    return {
        "status": "PASS",
        "tested_commit": expected,
        "package": d14d_package,
        "vm": _vm(d14d),
        "checks": [
            "identity",
            "D13D_FROZEN",
            "D14D_L3_READY",
            "package_identity",
            "evidence_root_unused",
            "clean_worktree",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-tested-commit", required=True)
    parser.add_argument("--d13d-handoff", type=Path, required=True)
    parser.add_argument("--d14d-handoff", type=Path, required=True)
    parser.add_argument("--package-manifest", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = validate_preflight(
            expected_tested_commit=args.expected_tested_commit,
            d13d=_load_object(args.d13d_handoff, "D13D handoff"),
            d14d=_load_object(args.d14d_handoff, "D14D handoff"),
            manifest=_load_object(args.package_manifest, "package manifest"),
            repo_root=args.repo_root,
            evidence_root=args.evidence_root,
        )
    except PreflightError as error:
        print(f"D14B_PREFLIGHT_FAIL: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
