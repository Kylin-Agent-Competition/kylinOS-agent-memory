"""D14C L3 formal-run preparation helpers.

This module does not launch a service, create an evidence directory, or judge a
runtime result.  It only rejects an attempted formal run when its external
handoff is incomplete.  The evaluator remains ``d13c_session_eval``; the
converter below merely preserves a real VM capture's D13C-compatible payload.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Mapping


_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EVIDENCE_ROOT = re.compile(r"^evidence/l3-kylin-vm/d14c_[A-Za-z0-9][A-Za-z0-9_.-]*$")
REQUIRED_ROUTES = (
    "turn.finalized",
    "event.ingest",
    "forget.preview",
    "forget.execute",
)
HANDOFF_SCHEMA_VERSION = "d14c-formal-handoff/v1"
CAPTURE_SCHEMA_VERSION = "d14c-runtime-capture/v1"
TRUSTED_HOST_APPROVAL_SCHEMA = "d14c-trusted-host-approval/v1"
ROUTE_ACTIVATION_SCHEMA = "d14c-route-activation/v1"
MEMORY_CONTEXT_FREEZE_SCHEMA = "d14c-memory-context-freeze/v1"
CANONICAL_FORMAL_HANDOFF_PATH = Path("release/handoff/d14c-formal-handoff.json")


class D14CPreflightError(ValueError):
    """The requested formal run is not safe to start."""


class D14CBundleError(ValueError):
    """A runtime capture cannot be passed to the existing D13C evaluator."""


def _git(repository_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode:
        raise D14CPreflightError("Git identity check failed")
    return completed.stdout.strip()


def _git_blob(repository_root: Path, head: str, relative_path: Path) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), "show", f"{head}:{relative_path.as_posix()}"],
        check=False,
        capture_output=True,
        timeout=15,
    )
    if completed.returncode:
        raise D14CPreflightError("canonical handoff is absent from expected control_head")
    return completed.stdout


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise D14CPreflightError(f"{label} must be an object")
    return value


def _required_text(data: Mapping[str, Any], key: str, label: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise D14CPreflightError(f"{label}.{key} must be a non-empty string")
    return value.strip()


def _sha256(data: Mapping[str, Any], key: str, label: str) -> None:
    value = _required_text(data, key, label)
    if not _SHA256.fullmatch(value):
        raise D14CPreflightError(f"{label}.{key} must be a lowercase SHA-256")


def _resolve_evidence_reference(root: Path, value: str, label: str) -> Path:
    """Resolve one existing repository-local evidence reference fail-closed."""

    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise D14CPreflightError(f"{label} must be a safe repository-relative path")
    resolved = (root / relative).resolve()
    if root not in resolved.parents:
        raise D14CPreflightError(f"{label} must stay inside repository_root")
    if not resolved.exists():
        raise D14CPreflightError(f"{label} must reference an existing path")
    return resolved


def _verify_control_head_authority(control_root: Path, expected_control_head: str) -> Path:
    """Require a clean control checkout at the reviewer-approved commit."""

    if not _GIT_SHA.fullmatch(expected_control_head):
        raise D14CPreflightError("expected_control_head must be a full lowercase Git SHA")
    root = control_root.resolve()
    if not (root / ".git").exists():
        raise D14CPreflightError("control_root is not a Git worktree")
    if _git(root, "rev-parse", "HEAD") != expected_control_head:
        raise D14CPreflightError("control_root HEAD must equal expected_control_head")
    if _git(root, "status", "--porcelain"):
        raise D14CPreflightError("control_root worktree must be clean")
    return root


def _require_control_tracked_handoff(
    control_root: Path,
    supplied_path: Path,
    expected_control_head: str,
) -> bytes:
    """Bind the supplied handoff to the canonical reviewed Git blob byte-for-byte."""

    canonical_relative = CANONICAL_FORMAL_HANDOFF_PATH
    try:
        canonical = (control_root / canonical_relative).resolve(strict=True)
        supplied = supplied_path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise D14CPreflightError("canonical handoff must be an existing regular file") from exc
    try:
        canonical.relative_to(control_root)
    except ValueError as exc:
        raise D14CPreflightError("canonical handoff must stay inside control_root") from exc
    if supplied != canonical:
        raise D14CPreflightError(
            "handoff must use the control-root canonical path: "
            f"{canonical_relative.as_posix()}"
        )
    if supplied_path.is_symlink() or not supplied.is_file():
        raise D14CPreflightError("canonical handoff must be a regular file, not a symlink")
    try:
        _git(control_root, "ls-files", "--error-unmatch", canonical_relative.as_posix())
    except D14CPreflightError as exc:
        raise D14CPreflightError("canonical handoff must be tracked by control_root") from exc
    actual = supplied.read_bytes()
    expected = _git_blob(control_root, expected_control_head, canonical_relative)
    if actual != expected:
        raise D14CPreflightError("canonical handoff bytes must equal expected control_head Git blob")
    return actual


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_file_sha256(
    root: Path,
    path_value: str,
    expected_sha256: str,
    label: str,
    *,
    sha_key: str = "sha256",
) -> Path:
    """Bind a declared artifact identity to existing regular-file bytes."""

    path = _resolve_evidence_reference(root, path_value, f"{label}.path")
    if not path.is_file():
        raise D14CPreflightError(f"{label}.path must reference a regular file")
    if _sha256_file(path) != expected_sha256:
        raise D14CPreflightError(f"{label}.{sha_key} does not match file bytes")
    return path


def _load_reference_object(root: Path, path_value: str, label: str) -> tuple[Mapping[str, Any], bytes]:
    """Load a repository-local regular JSON reference and retain its exact bytes."""

    path = _resolve_evidence_reference(root, path_value, label)
    if not path.is_file():
        raise D14CPreflightError(f"{label} must reference a regular JSON file")
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise D14CPreflightError(f"{label} must be readable UTF-8 JSON") from exc
    return _object(value, label), raw


def _require_same_identity(
    data: Mapping[str, Any],
    *,
    label: str,
    tested_commit: str,
    environment_id: str,
    service_package_sha256: str,
) -> None:
    if _required_text(data, "tested_commit", label) != tested_commit:
        raise D14CPreflightError(f"{label}.tested_commit must equal formal_tested_commit")
    if _required_text(data, "environment_id", label) != environment_id:
        raise D14CPreflightError(f"{label}.environment_id must equal vm.environment_id")
    _sha256(data, "service_package_sha256", label)
    if data["service_package_sha256"] != service_package_sha256:
        raise D14CPreflightError(f"{label}.service_package_sha256 must equal artifacts.memory_service.sha256")


def validate_formal_handoff(
    handoff: Mapping[str, Any],
    *,
    repository_root: Path,
    git_runner: Callable[..., str] = _git,
) -> dict[str, str]:
    """Validate every D14C formal gate without creating any runtime state.

    A caller must provide a D13D/D14D/host-identity/MemoryContext handoff.  The
    output is deliberately just identity metadata; it cannot be mistaken for
    a formal result.
    """

    if handoff.get("schema_version") != HANDOFF_SCHEMA_VERSION:
        raise D14CPreflightError("schema_version is not d14c-formal-handoff/v1")
    root = repository_root.resolve()
    if not (root / ".git").exists():
        raise D14CPreflightError("repository_root is not a Git worktree")
    if git_runner(root, "status", "--porcelain"):
        raise D14CPreflightError("worktree must be clean")

    tested_commit = _required_text(handoff, "formal_tested_commit", "handoff")
    if not _GIT_SHA.fullmatch(tested_commit):
        raise D14CPreflightError("formal_tested_commit must be a full lowercase Git SHA")
    try:
        git_runner(root, "cat-file", "-e", f"{tested_commit}^{{commit}}")
    except D14CPreflightError as exc:
        raise D14CPreflightError("formal_tested_commit must resolve to an existing commit") from exc
    runner_commit = _required_text(handoff, "preflight_runner_commit", "handoff")
    if not _GIT_SHA.fullmatch(runner_commit):
        raise D14CPreflightError("preflight_runner_commit must be a full lowercase Git SHA")
    try:
        git_runner(root, "cat-file", "-e", f"{runner_commit}^{{commit}}")
        git_runner(root, "merge-base", "--is-ancestor", runner_commit, "HEAD")
    except D14CPreflightError as exc:
        raise D14CPreflightError(
            "preflight_runner_commit must resolve to an ancestor of control HEAD"
        ) from exc

    d14d_gate: Mapping[str, Any] | None = None
    for gate_name, expected_status in (("d13d", "FROZEN"), ("d14d", "L3_READY")):
        gate = _object(handoff.get(gate_name), gate_name)
        if gate.get("status") != expected_status:
            raise D14CPreflightError(f"{gate_name}.status must be {expected_status}")
        if gate_name == "d13d" and gate.get("frozen") is not True:
            raise D14CPreflightError("d13d.frozen must be true")
        if gate_name == "d14d" and gate.get("l3_ready") is not True:
            raise D14CPreflightError("d14d.l3_ready must be true")
        gate_commit = _required_text(gate, "tested_commit", gate_name)
        if not _GIT_SHA.fullmatch(gate_commit):
            raise D14CPreflightError(f"{gate_name}.tested_commit must be a full lowercase Git SHA")
        if gate_commit != tested_commit:
            raise D14CPreflightError(f"{gate_name}.tested_commit must equal formal_tested_commit")
        if gate_name == "d14d":
            d14d_gate = gate
        reference, _ = _load_reference_object(
            root,
            _required_text(gate, "evidence_reference", gate_name),
            f"{gate_name}.evidence_reference",
        )
        if reference.get("status") != expected_status:
            raise D14CPreflightError(
                f"{gate_name}.evidence_reference.status must be {expected_status}"
            )
        if gate_name == "d13d" and reference.get("frozen") is not True:
            raise D14CPreflightError("d13d.evidence_reference.frozen must be true")
        if gate_name == "d14d" and reference.get("l3_ready") is not True:
            raise D14CPreflightError("d14d.evidence_reference.l3_ready must be true")
        if _required_text(reference, "tested_commit", f"{gate_name}.evidence_reference") != tested_commit:
            raise D14CPreflightError(
                f"{gate_name}.evidence_reference.tested_commit must equal formal_tested_commit"
            )

    release = _object(handoff.get("release_package"), "release_package")
    for key in ("path", "version"):
        _required_text(release, key, "release_package")
    _sha256(release, "sha256", "release_package")
    _sha256(release, "manifest_sha256", "release_package")
    source_commit = _required_text(release, "source_commit", "release_package")
    if not _GIT_SHA.fullmatch(source_commit):
        raise D14CPreflightError("release_package.source_commit must be a full lowercase Git SHA")
    if source_commit != tested_commit:
        raise D14CPreflightError("release_package.source_commit must equal formal_tested_commit")
    assert d14d_gate is not None
    d14d_package_sha = _required_text(d14d_gate, "package_tar_sha256", "d14d")
    if not _SHA256.fullmatch(d14d_package_sha):
        raise D14CPreflightError("d14d.package_tar_sha256 must be a lowercase SHA-256")
    if d14d_package_sha != release["sha256"]:
        raise D14CPreflightError("d14d.package_tar_sha256 must equal release_package.sha256")
    _verify_file_sha256(root, release["path"], release["sha256"], "release_package")
    manifest_path = _required_text(release, "manifest_path", "release_package")
    _verify_file_sha256(
        root,
        manifest_path,
        release["manifest_sha256"],
        "release_package.manifest",
        sha_key="manifest_sha256",
    )
    manifest, _ = _load_reference_object(root, manifest_path, "release_package.manifest")
    if _required_text(manifest, "source_commit", "release_package.manifest") != tested_commit:
        raise D14CPreflightError(
            "release_package.manifest.source_commit must equal formal_tested_commit"
        )
    if _required_text(d14d_gate, "package_tar_sha256", "d14d") != _required_text(
        _load_reference_object(
            root,
            _required_text(d14d_gate, "evidence_reference", "d14d"),
            "d14d.evidence_reference",
        )[0],
        "package_tar_sha256",
        "d14d.evidence_reference",
    ):
        raise D14CPreflightError(
            "d14d.evidence_reference.package_tar_sha256 must equal d14d.package_tar_sha256"
        )

    artifacts = _object(handoff.get("artifacts"), "artifacts")
    for name in ("ai_assistant", "memory_client", "memory_service"):
        artifact = _object(artifacts.get(name), f"artifacts.{name}")
        for key in ("path", "version"):
            _required_text(artifact, key, f"artifacts.{name}")
        _sha256(artifact, "sha256", f"artifacts.{name}")
        _verify_file_sha256(root, artifact["path"], artifact["sha256"], f"artifacts.{name}")

    vm = _object(handoff.get("vm"), "vm")
    for key in ("environment_id", "name", "uuid", "snapshot", "snapshot_uuid"):
        _required_text(vm, key, "vm")
    environment_id = vm["environment_id"]

    identity = _object(handoff.get("trusted_host_identity"), "trusted_host_identity")
    if identity.get("status") != "APPROVED":
        raise D14CPreflightError("trusted_host_identity.status must be APPROVED")
    for key in ("approval_reference", "process_identity", "db_identity"):
        _required_text(identity, key, "trusted_host_identity")
    _sha256(identity, "identity_sha256", "trusted_host_identity")
    _require_same_identity(
        identity,
        label="trusted_host_identity",
        tested_commit=tested_commit,
        environment_id=environment_id,
        service_package_sha256=artifacts["memory_service"]["sha256"],
    )
    approval, approval_bytes = _load_reference_object(
        root,
        identity["approval_reference"],
        "trusted_host_identity.approval_reference",
    )
    if approval.get("schema") != TRUSTED_HOST_APPROVAL_SCHEMA:
        raise D14CPreflightError("trusted_host_identity.approval_reference.schema is invalid")
    if approval.get("status") != "APPROVED":
        raise D14CPreflightError("trusted_host_identity.approval_reference.status must be APPROVED")
    _require_same_identity(
        approval,
        label="trusted_host_identity.approval_reference",
        tested_commit=tested_commit,
        environment_id=environment_id,
        service_package_sha256=artifacts["memory_service"]["sha256"],
    )
    for key in ("process_identity", "db_identity"):
        if _required_text(approval, key, "trusted_host_identity.approval_reference") != identity[key]:
            raise D14CPreflightError(
                f"trusted_host_identity.approval_reference.{key} must equal trusted_host_identity.{key}"
            )
    if hashlib.sha256(approval_bytes).hexdigest() != identity["identity_sha256"]:
        raise D14CPreflightError(
            "trusted_host_identity.identity_sha256 does not match approval_reference bytes"
        )

    routes = _object(handoff.get("production_routes"), "production_routes")
    for method in REQUIRED_ROUTES:
        route_label = f"production_routes.{method}"
        route = _object(routes.get(method), route_label)
        if route.get("status") != "ACTIVE":
            raise D14CPreflightError(f"{route_label}.status must be ACTIVE")
        _require_same_identity(
            route,
            label=route_label,
            tested_commit=tested_commit,
            environment_id=environment_id,
            service_package_sha256=artifacts["memory_service"]["sha256"],
        )
        reference, _ = _load_reference_object(
            root,
            _required_text(route, "activation_reference", route_label),
            f"{route_label}.activation_reference",
        )
        if reference.get("schema") != ROUTE_ACTIVATION_SCHEMA:
            raise D14CPreflightError(f"{route_label}.activation_reference.schema is invalid")
        if _required_text(reference, "method", f"{route_label}.activation_reference") != method:
            raise D14CPreflightError(f"{route_label}.activation_reference.method must equal route method")
        if reference.get("status") != "ACTIVE":
            raise D14CPreflightError(f"{route_label}.activation_reference.status must be ACTIVE")
        _require_same_identity(
            reference,
            label=f"{route_label}.activation_reference",
            tested_commit=tested_commit,
            environment_id=environment_id,
            service_package_sha256=artifacts["memory_service"]["sha256"],
        )

    context = _object(handoff.get("memory_context"), "memory_context")
    if context.get("status") != "FROZEN":
        raise D14CPreflightError("memory_context.status must be FROZEN")
    for key in ("schema_version", "schema_path", "freeze_reference", "no_match_semantics", "failure_semantics"):
        _required_text(context, key, "memory_context")
    _sha256(context, "schema_sha256", "memory_context")
    _require_same_identity(
        context,
        label="memory_context",
        tested_commit=tested_commit,
        environment_id=environment_id,
        service_package_sha256=artifacts["memory_service"]["sha256"],
    )
    _verify_file_sha256(root, context["schema_path"], context["schema_sha256"], "memory_context", sha_key="schema_sha256")
    freeze, _ = _load_reference_object(root, context["freeze_reference"], "memory_context.freeze_reference")
    if freeze.get("schema") != MEMORY_CONTEXT_FREEZE_SCHEMA:
        raise D14CPreflightError("memory_context.freeze_reference.schema is invalid")
    if freeze.get("status") != "FROZEN":
        raise D14CPreflightError("memory_context.freeze_reference.status must be FROZEN")
    _require_same_identity(
        freeze,
        label="memory_context.freeze_reference",
        tested_commit=tested_commit,
        environment_id=environment_id,
        service_package_sha256=artifacts["memory_service"]["sha256"],
    )
    if _required_text(
        freeze, "memory_context_schema_sha256", "memory_context.freeze_reference"
    ) != context["schema_sha256"]:
        raise D14CPreflightError(
            "memory_context.freeze_reference.memory_context_schema_sha256 must equal memory_context.schema_sha256"
        )

    relative_evidence_root = _required_text(handoff, "evidence_root", "handoff")
    if not _EVIDENCE_ROOT.fullmatch(relative_evidence_root):
        raise D14CPreflightError("evidence_root must be a new evidence/l3-kylin-vm/d14c_* path")
    evidence_root = (root / relative_evidence_root).resolve()
    if root not in evidence_root.parents or evidence_root.exists():
        raise D14CPreflightError("evidence_root must be a new path inside the repository")

    return {
        "status": "PREFLIGHT_ONLY",
        "tested_commit": tested_commit,
        "preflight_runner_commit": runner_commit,
        "environment_id": environment_id,
        "evidence_root": relative_evidence_root,
        "formal_dispatch": "NOT_STARTED",
    }


def load_and_validate_handoff(path: Path, *, repository_root: Path) -> dict[str, str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise D14CPreflightError("handoff must be readable UTF-8 JSON") from exc
    return validate_formal_handoff(_object(raw, "handoff"), repository_root=repository_root)


def load_and_validate_authoritative_handoff(
    handoff_path: Path,
    *,
    control_root: Path,
    expected_control_head: str,
) -> dict[str, str]:
    """Load only the reviewer-pinned canonical handoff from a control checkout."""

    root = _verify_control_head_authority(control_root, expected_control_head)
    supplied = handoff_path if handoff_path.is_absolute() else root / handoff_path
    raw = _require_control_tracked_handoff(root, supplied, expected_control_head)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise D14CPreflightError("canonical handoff must be readable UTF-8 JSON") from exc
    return validate_formal_handoff(_object(value, "handoff"), repository_root=root)


def convert_runtime_capture(capture: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact existing D13C evaluator input from a real VM capture.

    It intentionally accepts no pass/fail field and rejects a capture until the
    VM collector has marked it as raw evidence.  The D13C evaluator remains the
    sole owner of all session metrics.
    """

    if capture.get("schema_version") != CAPTURE_SCHEMA_VERSION:
        raise D14CBundleError("schema_version is not d14c-runtime-capture/v1")
    if capture.get("capture_status") != "VM_RAW_CAPTURED":
        raise D14CBundleError("capture_status must be VM_RAW_CAPTURED")
    provenance = capture.get("provenance")
    if not isinstance(provenance, dict):
        raise D14CBundleError("provenance must be an object")
    for key in ("tested_commit", "environment_id", "evidence_root"):
        if not isinstance(provenance.get(key), str) or not provenance[key]:
            raise D14CBundleError(f"provenance.{key} must be a non-empty string")
    if not _GIT_SHA.fullmatch(provenance["tested_commit"]):
        raise D14CBundleError("provenance.tested_commit must be a full lowercase Git SHA")
    config = capture.get("d13c_config")
    sessions = capture.get("sessions")
    if not isinstance(config, dict) or not isinstance(sessions, list):
        raise D14CBundleError("d13c_config must be an object and sessions must be an array")
    if config.get("implementation_commit") != provenance["tested_commit"]:
        raise D14CBundleError("d13c_config.implementation_commit must equal provenance.tested_commit")
    if config.get("environment") != provenance["environment_id"]:
        raise D14CBundleError("d13c_config.environment must equal provenance.environment_id")
    if config.get("evidence_reference") != provenance["evidence_root"]:
        raise D14CBundleError("d13c_config.evidence_reference must equal provenance.evidence_root")
    raw_references = capture.get("raw_evidence_references")
    if not isinstance(raw_references, list) or not raw_references:
        raise D14CBundleError("raw_evidence_references must be a non-empty array")
    for reference in raw_references:
        if not isinstance(reference, str) or not reference.strip():
            raise D14CBundleError("raw_evidence_references entries must be non-empty strings")
        relative = Path(reference)
        if relative.is_absolute() or ".." in relative.parts:
            raise D14CBundleError("raw_evidence_references entries must be safe relative paths")
    return {"config": config, "sessions": sessions}
