"""L1 tests for D14C preparation only; no service or formal evidence is created."""

from __future__ import annotations

import copy
import hashlib
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
    if args[:2] == ("cat-file", "-e"):
        return ""
    raise AssertionError(args)


def _write(root: Path, relative: str, contents: bytes) -> tuple[str, str]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)
    return relative, hashlib.sha256(contents).hexdigest()


def _handoff(root: Path) -> dict:
    d13d_reference, _ = _write(root, "evidence/d13d/final.json", b"d13d")
    d14d_reference, _ = _write(root, "evidence/d14d/final.json", b"d14d")
    package_path, package_sha = _write(root, "release/packages/frozen.tar", b"release-package")
    approval_reference, _ = _write(root, "evidence/approvals/host.json", b"host-approval")
    freeze_reference, _ = _write(root, "evidence/context/freeze.json", b"context-freeze")
    schema_path, schema_sha = _write(root, "contracts/memory-context-v1.json", b"memory-context-schema")
    artifacts = {}
    for name in ("ai_assistant", "memory_client", "memory_service"):
        path, sha = _write(root, f"release/artifacts/{name}.bin", name.encode("utf-8"))
        artifacts[name] = {"path": path, "version": "1", "sha256": sha}
    routes = {}
    for method in ("turn.finalized", "event.ingest", "forget.preview", "forget.execute"):
        reference, _ = _write(root, f"evidence/routes/{method}.json", method.encode("utf-8"))
        routes[method] = {
            "status": "ACTIVE",
            "tested_commit": HEAD,
            "environment_id": "kylin-vm-01",
            "service_package_sha256": artifacts["memory_service"]["sha256"],
            "activation_reference": reference,
        }
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "formal_tested_commit": HEAD,
        "preflight_runner_commit": HEAD,
        "d13d": {"status": "FROZEN", "frozen": True, "tested_commit": HEAD, "evidence_reference": d13d_reference},
        "d14d": {"status": "L3_READY", "l3_ready": True, "tested_commit": HEAD, "package_tar_sha256": package_sha, "evidence_reference": d14d_reference},
        "release_package": {"path": package_path, "version": "1", "sha256": package_sha, "manifest_sha256": SHA, "source_commit": HEAD},
        "artifacts": artifacts,
        "vm": {"environment_id": "kylin-vm-01", "name": "Kylin", "uuid": "vm-uuid", "snapshot": "clean", "snapshot_uuid": "snap-uuid"},
        "trusted_host_identity": {"status": "APPROVED", "tested_commit": HEAD, "environment_id": "kylin-vm-01", "service_package_sha256": artifacts["memory_service"]["sha256"], "approval_reference": approval_reference, "process_identity": "assistant", "db_identity": "chat-db", "identity_sha256": SHA},
        "production_routes": routes,
        "memory_context": {"status": "FROZEN", "tested_commit": HEAD, "environment_id": "kylin-vm-01", "service_package_sha256": artifacts["memory_service"]["sha256"], "schema_version": "v1", "schema_path": schema_path, "freeze_reference": freeze_reference, "no_match_semantics": "skipped", "failure_semantics": "fail-closed", "schema_sha256": schema_sha},
        "evidence_root": "evidence/l3-kylin-vm/d14c_20260907T000000Z_aaaaaaaa",
    }


def test_preflight_accepts_complete_handoff_without_creating_root(tmp_path):
    (tmp_path / ".git").mkdir()
    report = validate_formal_handoff(_handoff(tmp_path), repository_root=tmp_path, git_runner=_git)
    assert report["status"] == "PREFLIGHT_ONLY"
    assert not (tmp_path / "evidence/l3-kylin-vm").exists()


def test_preflight_accepts_frozen_runtime_commit_with_current_preflight_runner(tmp_path):
    """Docs/evidence-only runner changes must not rewrite the frozen package identity."""

    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["formal_tested_commit"] = "c" * 40
    handoff["release_package"]["source_commit"] = "c" * 40
    handoff["d13d"]["tested_commit"] = "c" * 40
    handoff["d14d"]["tested_commit"] = "c" * 40
    handoff["trusted_host_identity"]["tested_commit"] = "c" * 40
    handoff["memory_context"]["tested_commit"] = "c" * 40
    for route in handoff["production_routes"].values():
        route["tested_commit"] = "c" * 40

    report = validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)

    assert report["tested_commit"] == "c" * 40


def test_preflight_rejects_d14d_handoff_from_another_runtime_commit(tmp_path):
    """D14D L3 readiness is consumable only for the frozen runtime commit."""

    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["d14d"]["tested_commit"] = "c" * 40

    with pytest.raises(D14CPreflightError, match="d14d.tested_commit must equal formal_tested_commit"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_d14d_handoff_with_another_package(tmp_path):
    """D14D L3 readiness is consumable only for the frozen release package."""

    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
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
    handoff = _handoff(tmp_path)
    mutate(handoff)
    with pytest.raises(D14CPreflightError, match=message):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_dirty_worktree(tmp_path):
    (tmp_path / ".git").mkdir()

    def dirty(_root: Path, *args: str) -> str:
        return " M docs" if args[0] == "status" else HEAD

    with pytest.raises(D14CPreflightError, match="worktree must be clean"):
        validate_formal_handoff(_handoff(tmp_path), repository_root=tmp_path, git_runner=dirty)


def test_preflight_rejects_d13d_raw_ready_pending_seals(tmp_path):
    """Raw evidence is not a substitute for the D13D frozen handoff."""

    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["d13d"]["status"] = "RAW_READY_PENDING_SEALS"

    with pytest.raises(D14CPreflightError, match="d13d.status must be FROZEN"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_issued_d13d_execution_seal_without_freeze(tmp_path):
    """An execution seal cannot be promoted into the final freeze by D14C."""

    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["d13d"].update({"execution_seal_status": "ISSUED", "frozen": False})

    with pytest.raises(D14CPreflightError, match="d13d.frozen must be true"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_d14d_gates_without_l3_ready(tmp_path):
    """Completed preliminary VM gates are not the final D14D L3 handoff."""

    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["d14d"].update({"g0_g6_status": "PASS", "l3_ready": False})

    with pytest.raises(D14CPreflightError, match="d14d.l3_ready must be true"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_release_package_from_another_commit(tmp_path):
    """A formal package must be built from the exact tested commit."""

    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["release_package"]["source_commit"] = "c" * 40

    with pytest.raises(D14CPreflightError, match="release_package.source_commit must equal formal_tested_commit"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_formal_commit_that_is_not_in_git(tmp_path):
    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["formal_tested_commit"] = "d" * 40
    handoff["release_package"]["source_commit"] = "d" * 40
    handoff["d13d"]["tested_commit"] = "d" * 40
    handoff["d14d"]["tested_commit"] = "d" * 40

    def missing_commit(_root: Path, *args: str) -> str:
        if args[:2] == ("cat-file", "-e"):
            raise D14CPreflightError("missing commit")
        return _git(_root, *args)

    with pytest.raises(D14CPreflightError, match="formal_tested_commit must resolve"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=missing_commit)


@pytest.mark.parametrize("gate_name", ("d13d", "d14d"))
def test_preflight_rejects_missing_gate_evidence_reference(tmp_path, gate_name):
    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff[gate_name]["evidence_reference"] = "evidence/missing.json"

    with pytest.raises(D14CPreflightError, match=f"{gate_name}.evidence_reference"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_evidence_reference_that_escapes_repository(tmp_path):
    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["d13d"]["evidence_reference"] = "../outside.json"

    with pytest.raises(D14CPreflightError, match="d13d.evidence_reference must be a safe repository-relative path"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_release_package_with_mismatched_bytes(tmp_path):
    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["release_package"]["sha256"] = "c" * 64
    handoff["d14d"]["package_tar_sha256"] = "c" * 64

    with pytest.raises(D14CPreflightError, match="release_package.sha256 does not match file bytes"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


@pytest.mark.parametrize("artifact_name", ("ai_assistant", "memory_client", "memory_service"))
def test_preflight_rejects_component_artifact_with_mismatched_bytes(tmp_path, artifact_name):
    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["artifacts"][artifact_name]["sha256"] = "c" * 64

    with pytest.raises(D14CPreflightError, match=f"artifacts.{artifact_name}.sha256 does not match file bytes"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("tested_commit", "c" * 40),
        ("environment_id", "other-vm"),
        ("service_package_sha256", "c" * 64),
    ),
)
def test_preflight_rejects_trusted_host_identity_from_another_runtime(tmp_path, key, value):
    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["trusted_host_identity"][key] = value

    with pytest.raises(D14CPreflightError, match=f"trusted_host_identity.{key} must equal"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_trusted_host_identity_with_missing_approval_reference(tmp_path):
    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["trusted_host_identity"]["approval_reference"] = "evidence/approvals/missing.json"

    with pytest.raises(D14CPreflightError, match="trusted_host_identity.approval_reference"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("tested_commit", "c" * 40),
        ("environment_id", "other-vm"),
        ("service_package_sha256", "c" * 64),
        ("activation_reference", "evidence/routes/missing.json"),
    ),
)
def test_preflight_rejects_active_route_without_matching_runtime_evidence(tmp_path, key, value):
    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["production_routes"]["turn.finalized"][key] = value

    with pytest.raises(D14CPreflightError, match=f"production_routes.turn.finalized.{key}"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_memory_context_with_mismatched_schema_bytes(tmp_path):
    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["memory_context"]["schema_sha256"] = "c" * 64

    with pytest.raises(D14CPreflightError, match="memory_context.schema_sha256 does not match file bytes"):
        validate_formal_handoff(handoff, repository_root=tmp_path, git_runner=_git)


def test_preflight_rejects_memory_context_from_another_runtime_environment(tmp_path):
    (tmp_path / ".git").mkdir()
    handoff = _handoff(tmp_path)
    handoff["memory_context"]["environment_id"] = "other-vm"

    with pytest.raises(D14CPreflightError, match="memory_context.environment_id must equal vm.environment_id"):
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
