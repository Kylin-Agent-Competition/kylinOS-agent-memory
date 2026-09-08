"""L1 tests for D14C preparation only; no service or formal evidence is created."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from evaluation.d14c_l3_harness import (
    D14CBundleError,
    D14CPreflightError,
    HANDOFF_SCHEMA_VERSION,
    convert_runtime_capture,
    validate_formal_handoff,
)


HEAD = "a" * 40
SHA = "b" * 64


def _git(_root: Path, *args: str) -> str:
    if args == ("status", "--porcelain"):
        return ""
    if args == ("rev-parse", "HEAD"):
        return HEAD
    raise AssertionError(args)


def _handoff() -> dict:
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "formal_tested_commit": HEAD,
        "preflight_runner_commit": HEAD,
        "d13d": {"status": "FROZEN", "frozen": True, "tested_commit": HEAD, "evidence_reference": "d13d/final"},
        "d14d": {"status": "L3_READY", "l3_ready": True, "tested_commit": HEAD, "package_tar_sha256": SHA, "evidence_reference": "d14d/final"},
        "release_package": {"path": "/tmp/pkg.tar", "version": "1", "sha256": SHA, "manifest_sha256": SHA, "source_commit": HEAD},
        "artifacts": {
            name: {"path": f"/tmp/{name}", "version": "1", "sha256": SHA}
            for name in ("ai_assistant", "memory_client", "memory_service")
        },
        "vm": {"environment_id": "kylin-vm-01", "name": "Kylin", "uuid": "vm-uuid", "snapshot": "clean", "snapshot_uuid": "snap-uuid"},
        "trusted_host_identity": {"status": "APPROVED", "approval_reference": "D-approval", "process_identity": "assistant", "db_identity": "chat-db", "identity_sha256": SHA},
        "production_routes": {method: "ACTIVE" for method in ("turn.finalized", "event.ingest", "forget.preview", "forget.execute")},
        "memory_context": {"status": "FROZEN", "schema_version": "v1", "freeze_reference": "CDE-ADR", "no_match_semantics": "skipped", "failure_semantics": "fail-closed", "schema_sha256": SHA},
        "evidence_root": "evidence/l3-kylin-vm/d14c_20260907T000000Z_aaaaaaaa",
    }


def test_preflight_accepts_complete_handoff_without_creating_root(tmp_path):
    (tmp_path / ".git").mkdir()
    report = validate_formal_handoff(_handoff(), repository_root=tmp_path, git_runner=_git)
    assert report["status"] == "PREFLIGHT_ONLY"
    assert not (tmp_path / "evidence").exists()


def test_preflight_accepts_frozen_runtime_commit_with_current_preflight_runner(tmp_path):
    """Docs/evidence-only runner changes must not rewrite the frozen package identity."""

    (tmp_path / ".git").mkdir()
    handoff = _handoff()
    handoff["formal_tested_commit"] = "c" * 40
    handoff["release_package"]["source_commit"] = "c" * 40
    handoff["d13d"]["tested_commit"] = "c" * 40
    handoff["d14d"]["tested_commit"] = "c" * 40

    report = validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)

    assert report["tested_commit"] == "c" * 40


def test_preflight_rejects_d14d_handoff_from_another_runtime_commit(tmp_path):
    """D14D L3 readiness is consumable only for the frozen runtime commit."""

    (tmp_path / ".git").mkdir()
    handoff = _handoff()
    handoff["d14d"]["tested_commit"] = "c" * 40

    with pytest.raises(D14CPreflightError, match="d14d.tested_commit must equal formal_tested_commit"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_d14d_handoff_with_another_package(tmp_path):
    """D14D L3 readiness is consumable only for the frozen release package."""

    (tmp_path / ".git").mkdir()
    handoff = _handoff()
    handoff["d14d"]["package_tar_sha256"] = "c" * 64

    with pytest.raises(D14CPreflightError, match="d14d.package_tar_sha256 must equal release_package.sha256"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda item: item.__setitem__("formal_tested_commit", "bad"), "full lowercase Git SHA"),
        (lambda item: item["d13d"].__setitem__("status", "BLOCKED"), "d13d.status"),
        (lambda item: item["trusted_host_identity"].__setitem__("status", "PENDING"), "trusted_host_identity.status"),
        (lambda item: item["production_routes"].__setitem__("forget.execute", "BLOCKED"), "forget.execute"),
        (lambda item: item["memory_context"].__setitem__("status", "PENDING"), "memory_context.status"),
        (lambda item: item.__setitem__("evidence_root", "evidence/l3-kylin-vm/not-d14c"), "d14c_"),
    ],
)
def test_preflight_rejects_incomplete_gate(tmp_path, mutate, message):
    (tmp_path / ".git").mkdir()
    handoff = _handoff()
    mutate(handoff)
    with pytest.raises(D14CPreflightError, match=message):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_dirty_worktree(tmp_path):
    (tmp_path / ".git").mkdir()

    def dirty(_root: Path, *args: str) -> str:
        return " M docs" if args[0] == "status" else HEAD

    with pytest.raises(D14CPreflightError, match="worktree must be clean"):
        validate_formal_handoff(_handoff(), repository_root=tmp_path, git_runner=dirty)


def test_preflight_rejects_d13d_raw_ready_pending_seals(tmp_path):
    """Raw evidence is not a substitute for the D13D frozen handoff."""

    (tmp_path / ".git").mkdir()
    handoff = _handoff()
    handoff["d13d"]["status"] = "RAW_READY_PENDING_SEALS"

    with pytest.raises(D14CPreflightError, match="d13d.status must be FROZEN"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_issued_d13d_execution_seal_without_freeze(tmp_path):
    """An execution seal cannot be promoted into the final freeze by D14C."""

    (tmp_path / ".git").mkdir()
    handoff = _handoff()
    handoff["d13d"].update({"execution_seal_status": "ISSUED", "frozen": False})

    with pytest.raises(D14CPreflightError, match="d13d.frozen must be true"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_d14d_gates_without_l3_ready(tmp_path):
    """Completed preliminary VM gates are not the final D14D L3 handoff."""

    (tmp_path / ".git").mkdir()
    handoff = _handoff()
    handoff["d14d"].update({"g0_g6_status": "PASS", "l3_ready": False})

    with pytest.raises(D14CPreflightError, match="d14d.l3_ready must be true"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_release_package_from_another_commit(tmp_path):
    """A formal package must be built from the exact tested commit."""

    (tmp_path / ".git").mkdir()
    handoff = _handoff()
    handoff["release_package"]["source_commit"] = "c" * 40

    with pytest.raises(D14CPreflightError, match="release_package.source_commit must equal formal_tested_commit"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def _capture() -> dict:
    return {
        "schema_version": "d14c-runtime-capture/v1",
        "capture_status": "VM_RAW_CAPTURED",
        "provenance": {"tested_commit": HEAD, "environment_id": "kylin-vm-01", "evidence_root": "evidence/l3-kylin-vm/d14c_x"},
        "d13c_config": {"implementation_commit": HEAD, "environment": "kylin-vm-01", "evidence_reference": "evidence/l3-kylin-vm/d14c_x"},
        "raw_evidence_references": ["raw/session_capture.jsonl"],
        "sessions": [],
    }


def test_converter_preserves_d13c_evaluator_input_only():
    bundle = convert_runtime_capture(_capture())
    assert set(bundle) == {"config", "sessions"}
    assert bundle["config"]["implementation_commit"] == HEAD


def test_converter_rejects_non_vm_or_mismatched_provenance():
    pending = _capture()
    pending["capture_status"] = "PRE_RUN"
    with pytest.raises(D14CBundleError, match="VM_RAW_CAPTURED"):
        convert_runtime_capture(pending)
    mismatched = _capture()
    mismatched["d13c_config"]["environment"] = "other-vm"
    with pytest.raises(D14CBundleError, match="environment"):
        convert_runtime_capture(mismatched)


def test_converter_rejects_missing_or_unsafe_raw_references():
    missing = _capture()
    del missing["raw_evidence_references"]
    with pytest.raises(D14CBundleError, match="raw_evidence_references"):
        convert_runtime_capture(missing)
    unsafe = _capture()
    unsafe["raw_evidence_references"] = ["../other/raw.log"]
    with pytest.raises(D14CBundleError, match="safe relative"):
        convert_runtime_capture(unsafe)
