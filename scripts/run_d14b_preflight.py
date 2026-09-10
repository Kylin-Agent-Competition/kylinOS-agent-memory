#!/usr/bin/env python3
"""Fail-closed D14B formal L3 handoff preflight.

The command only validates a D13D/D14D handoff, the production capture
provenance and the frozen package artifact bytes.  It never creates an
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
from typing import Any, Optional

COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CAPTURE_CHANNELS = ("sqlite", "fts5", "vector", "rrf")


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


def _sha256_file(path: Path, label: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise PreflightError(f"无法读取 {label}: {error}") from error


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
    actual_sha = _sha256_file(candidate, "D14D handoff.runner")
    if actual_sha != expected_sha:
        raise PreflightError("D14B runner SHA-256 与 handoff 不一致")


def _verify_capture_handoff(
    capture_handoff: dict[str, Any],
    repo_root: Path,
    expected_commit: str,
) -> None:
    """Machine gate: the four production capture runners must be pinned.

    SQLite/FTS5/Vector/RRF source artifacts may only be assembled by approved
    runners, so the handoff must pin each runner path, its SHA-256 and a
    non-empty command id, all bound to the tested commit.
    """

    if _commit(
        _required_text(capture_handoff, "tested_commit", "d14b-capture-handoff"),
        "d14b-capture-handoff tested_commit",
    ) != expected_commit:
        raise PreflightError("d14b-capture-handoff tested_commit 与 formal tested_commit 不一致")
    captures = capture_handoff.get("captures")
    if not isinstance(captures, dict):
        raise PreflightError("d14b-capture-handoff.captures 必须是 object")
    if set(captures) != set(CAPTURE_CHANNELS):
        missing = ", ".join(sorted(set(CAPTURE_CHANNELS) - set(captures)))
        extra = ", ".join(sorted(set(captures) - set(CAPTURE_CHANNELS)))
        raise PreflightError(
            "d14b-capture-handoff 必须且只能声明 sqlite/fts5/vector/rrf 四类 runner"
            + (f"；缺失: {missing}" if missing else "")
            + (f"；多余: {extra}" if extra else "")
        )
    for channel in CAPTURE_CHANNELS:
        entry = captures[channel]
        if not isinstance(entry, dict):
            raise PreflightError(f"d14b-capture-handoff.captures.{channel} 必须是 object")
        relative_path = _required_text(entry, "runner_path", f"capture {channel}")
        command_id = _required_text(entry, "command_id", f"capture {channel}")
        expected_sha = _sha256(
            _required_text(entry, "runner_sha256", f"capture {channel}"),
            f"capture {channel}.runner_sha256",
        )
        candidate = (repo_root / relative_path).resolve()
        try:
            candidate.relative_to(repo_root.resolve())
        except ValueError as error:
            raise PreflightError(f"capture {channel}.runner_path 不得越出 repo_root") from error
        if not candidate.is_file():
            raise PreflightError(f"capture {channel}.runner_path 不可定位")
        actual_sha = _sha256_file(candidate, f"capture {channel} runner")
        if actual_sha != expected_sha:
            raise PreflightError(f"capture {channel}.runner_sha256 与实际文件不一致")


def _verify_package_bytes(
    package_tar: Path,
    actual_manifest: Path,
    expected_package: dict[str, str],
    expected_commit: str,
) -> None:
    """Verify the actual frozen package bytes on disk, not only metadata."""

    tar_sha = _sha256_file(package_tar, "actual package tar")
    if tar_sha != expected_package["package_tar_sha256"]:
        raise PreflightError("actual package tar SHA-256 与冻结值不一致")
    manifest_sha = _sha256_file(actual_manifest, "actual package manifest")
    if manifest_sha != expected_package["package_manifest_sha256"]:
        raise PreflightError("actual package manifest SHA-256 与冻结值不一致")
    try:
        manifest = json.loads(actual_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PreflightError(f"actual package manifest 解析失败: {error}") from error
    if not isinstance(manifest, dict):
        raise PreflightError("actual package manifest 必须是 JSON object")
    if _commit(
        _required_text(manifest, "source_commit", "actual package manifest"),
        "actual package manifest source_commit",
    ) != expected_commit:
        raise PreflightError("actual package manifest source_commit 与 formal tested_commit 不一致")
    if (
        _required_text(manifest, "package_version", "actual package manifest")
        != expected_package["package_version"]
    ):
        raise PreflightError("actual package manifest package_version 与冻结值不一致")


def validate_preflight(
    *,
    expected_tested_commit: str,
    d13d: dict[str, Any],
    d14d: dict[str, Any],
    manifest: dict[str, Any],
    repo_root: Path,
    evidence_root: Path,
    capture_handoff: Optional[dict[str, Any]] = None,
    package_tar: Optional[Path] = None,
    actual_package_manifest: Optional[Path] = None,
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

    # Production capture provenance is mandatory: the four source artifacts
    # must be produced by approved, pinned runners (machine gate).
    if capture_handoff is None:
        raise PreflightError("缺少 d14b-capture-handoff：SQLite/FTS5/Vector/RRF 四类 runner 必须机器可验证")
    _verify_capture_handoff(capture_handoff, repo_root, expected)

    # Actual frozen package bytes must be verified on the spot.
    if package_tar is None or actual_package_manifest is None:
        raise PreflightError("缺少 actual package tar/manifest：必须现场校验冻结包字节")
    _verify_package_bytes(package_tar, actual_package_manifest, d14d_package, expected)

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
            "capture_provenance",
            "package_bytes",
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
    parser.add_argument("--capture-handoff", type=Path, default=None)
    parser.add_argument("--package-tar", type=Path, default=None)
    parser.add_argument("--actual-package-manifest", type=Path, default=None)
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
            capture_handoff=(
                _load_object(args.capture_handoff, "d14b-capture-handoff")
                if args.capture_handoff is not None
                else None
            ),
            package_tar=args.package_tar,
            actual_package_manifest=args.actual_package_manifest,
        )
    except PreflightError as error:
        print(f"D14B_PREFLIGHT_FAIL: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())