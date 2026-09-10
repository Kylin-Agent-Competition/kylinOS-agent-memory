"""L1 integrity tests for future D14C evidence packages."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evaluation.d14c_evidence_package import D14CEvidenceError, validate_evidence_package

COMMIT = "a" * 40


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _package(tmp_path: Path, status: str = "FAILED") -> Path:
    root = tmp_path / "d14c_20260907T000000Z_aaaaaaaa"
    (root / "identity").mkdir(parents=True)
    (root / "raw").mkdir()
    (root / "identity" / "run_identity.json").write_text(json.dumps({"tested_commit": COMMIT, "environment_id": "kylin-vm-01"}), encoding="utf-8")
    (root / "raw" / "commands.log").write_text("output", encoding="utf-8")
    (root / "raw" / "exit_codes.json").write_text("{}", encoding="utf-8")
    files = {"run_identity": "identity/run_identity.json", "commands": "raw/commands.log", "exit_codes": "raw/exit_codes.json"}
    if status == "VERIFIED":
        (root / "raw" / "runtime_capture.json").write_text("{}", encoding="utf-8")
        (root / "reports").mkdir()
        (root / "reports" / "d13c.json").write_text("{}", encoding="utf-8")
        files.update({"runtime_capture": "raw/runtime_capture.json", "evaluator_report": "reports/d13c.json"})
    manifest = {"schema_version": "d14c-evidence-manifest/v1", "run_status": status, "tested_commit": COMMIT, "environment_id": "kylin-vm-01", "files": files}
    if status != "VERIFIED":
        manifest["failure_summary"] = "route remained blocked"
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    lines = [f"{_digest(path)}  {path.relative_to(root).as_posix()}" for path in sorted(item for item in root.rglob("*") if item.is_file())]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def test_failed_package_integrity_is_not_runtime_pass(tmp_path):
    report = validate_evidence_package(_package(tmp_path))
    assert report["status"] == "PACKAGE_INTEGRITY_VERIFIED"
    assert report["run_status"] == "FAILED"


def test_verified_package_requires_capture_and_evaluator(tmp_path):
    root = _package(tmp_path, "VERIFIED")
    assert validate_evidence_package(root)["run_status"] == "VERIFIED"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    del manifest["files"]["evaluator_report"]
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(D14CEvidenceError, match="lacks runtime_capture"):
        validate_evidence_package(root)


def test_checksums_must_match_and_cover_every_file(tmp_path):
    root = _package(tmp_path)
    (root / "raw" / "commands.log").write_text("tampered", encoding="utf-8")
    with pytest.raises(D14CEvidenceError, match="mismatch"):
        validate_evidence_package(root)
    root = _package(tmp_path / "other")
    (root / "extra.log").write_text("not listed", encoding="utf-8")
    with pytest.raises(D14CEvidenceError, match="cover every regular file"):
        validate_evidence_package(root)


def test_non_verified_package_requires_failure_summary(tmp_path):
    root = _package(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    del manifest["failure_summary"]
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(D14CEvidenceError, match="failure_summary"):
        validate_evidence_package(root)
