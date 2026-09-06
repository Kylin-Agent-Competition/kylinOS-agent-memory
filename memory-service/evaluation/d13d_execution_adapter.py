"""Fail-closed preflight and raw projection for the versioned D13D execution adapter.

This module deliberately validates only the public formal Dataset inputs and the
Gold-independent raw projection schema (:data:`D13E_RAW_RESULT_SCHEMA_V1`), which is
CANDIDATE_PENDING_D13E_REVIEW and not frozen: the Safety cross-track projection
contract still needs a D13E Runner/Gold decision before Safety raw can be treated
as Gate-9 complete.  The module imports no evaluator-owned decision artifact and
never decides whether an observed result passes.  Dispatch and raw production
stay behind the separately frozen VM execution gate described in the D13D task
card; the adapter only consumes observations produced by the real production
seams it dispatches.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import shutil
import subprocess
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

from sqlalchemy import and_, select
from db.schema import source_events

from db.engine import create_db_engine, init_schema
from db.uow import UnitOfWork
from gateway.forget_handlers import register_forget_handlers
from gateway.handlers import register_default_handlers, register_event_ingest_handler
from gateway.preference_handlers import register_preference_handlers
from gateway.registry import HandlerRegistry, RequestContext
from providers.extraction_provider import ExtractionProvider, TurnFinalizedEvent
from service.conflict_resolution_policy import ConflictResolutionPolicy, ConflictSide
from evaluation.d13d_forget_state_binding import (
    BINDING_VERSION_V2,
    FORGET_SAMPLE_MODES,
    verify_artifact_file,
)
from service.d13d_forget_observability import (
    capture_forget_execution_snapshot,
    observe_forget_execution,
)
from service.d13d_safety_observability import observe_safety_execution


_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
OFFICIAL_D13E_TESTSET_SHA256 = (
    "9740c00f4a9d91471bec8e6fa8aeeeb52f890f8680d83f740a84db2b1701a44b"
)
_SAMPLE_ID = re.compile(r"^d13e-(pref|conflict|safety|forget)-\d{3}$")
_METRICS = frozenset({"preference", "conflict", "safety", "forget"})
_EXPECTED_DISTRIBUTION = {
    "preference": 4,
    "conflict": 4,
    "safety": 4,
    "forget": 5,
}
_RAW_FILENAMES = {
    "preference": "preference_raw.jsonl",
    "conflict": "conflict_raw.jsonl",
    "safety": "safety_raw.jsonl",
    "forget": "forget_raw.jsonl",
}

# Candidate, Gold-independent raw projection contract for the formal Runner.
#
# STATUS: CANDIDATE_PENDING_D13E_REVIEW (not frozen).  The Safety allowed-field
# set below mirrors only the hard-zero counters that the sealed Runner accepts
# for every Safety sample.  The current formal Gold additionally expects
# sensitivity/admission (safety-001/002/003) observation fields, so Safety raw
# is NOT Gate-9 complete until a D13E Runner/Gold re-baseline decides the
# projection contract; I3b stays BLOCKED_PARTIAL.  Preference/Conflict/Forget
# sets are stable top-level fields never wrapped in nested record lists.
#
# ``actual`` is validated against the per-metric ``required``/``allowed`` sets
# below (strict whitelist: any field outside ``allowed`` is rejected before it
# can become a canonical raw record), and no evaluation artifact
# (Gold/expected/threshold) is read to build ``actual``.
D13E_RAW_RESULT_SCHEMA_STATUS = "CANDIDATE_PENDING_D13E_REVIEW"
D13E_RAW_RESULT_SCHEMA_V1 = {
    "status": D13E_RAW_RESULT_SCHEMA_STATUS,
    "schema_version": "d13e-raw-result-schema/v1",
    "metrics": {
        "preference": {
            "required": ("record_count",),
            "allowed": (
                "record_count",
                "key",
                "scope",
                "is_temporary",
                "should_persist",
                "explicitness",
            ),
        },
        "conflict": {
            "required": ("action", "winner_id", "reason_code"),
            "allowed": ("action", "winner_id", "reason_code"),
        },
        "safety": {
            "required": (
                "critical_gate_bypass_count",
                "normal_memory_write_count",
                "audit_plaintext_leak_count",
                "cross_user_violation_count",
            ),
            "allowed": (
                "critical_gate_bypass_count",
                "normal_memory_write_count",
                "audit_plaintext_leak_count",
                "cross_user_violation_count",
                "sensitivity",
                "admission",
                "operation",
            ),
        },
        "forget": {
            "required": (
                "forget_mode",
                "missed_target_items",
                "wrongly_deleted_items",
                "cross_user_violation_count",
                "residual_after_realtime_query",
                "residual_after_full_rebuild",
            ),
            "allowed": (
                "forget_mode",
                "missed_target_items",
                "wrongly_deleted_items",
                "cross_user_violation_count",
                "residual_after_realtime_query",
                "residual_after_full_rebuild",
            ),
        },
    },
}
_FORGET_MODES = frozenset(
    {"single_item", "session", "topic", "time_window", "full_reset"}
)
_COUNTER_FIELDS = frozenset(
    {
        "record_count",
        "critical_gate_bypass_count",
        "normal_memory_write_count",
        "audit_plaintext_leak_count",
        "cross_user_violation_count",
        "missed_target_items",
        "wrongly_deleted_items",
        "residual_after_realtime_query",
        "residual_after_full_rebuild",
    }
)
_FORBIDDEN_EVALUATION_TOKENS = frozenset(
    {"gold", "expected", "threshold", "pass", "fail", "formal_result", "formal_pass"}
)


_ENGINE_BINDING_TOKENS: dict[int, str] = {}

# R8：Forget realtime/rebuild observation provider closed allowlist。
# key = artifact retrieval_profile；value = callable(binding, artifact, sample_id)
# -> (realtime_observation, rebuild_observation)。空字典 = 尚未批准任何 profile，
# dispatch 遇到未知/缺失 profile 一律 fail-closed，禁止调用方注入任意 Callable。
OBSERVATION_PROFILES: dict[str, Any] = {}


class ExecutionPreflightError(ValueError):
    """An invocation is not safe to dispatch against an isolated environment."""


@dataclass(frozen=True)
class ExecutionRequest:
    """All identity and isolation inputs required before any D13D dispatch."""

    repository_root: Path
    tested_commit: str
    testset_path: Path
    testset_sha256: str
    execution_evidence_root: Path
    state_root: Path
    binding_artifact_path: Optional[Path] = None


@dataclass(frozen=True)
class ValidatedExecution:
    """A validated Dataset and the immutable identity used to validate it."""

    request: ExecutionRequest
    records: tuple[Mapping[str, Any], ...]


def _run_git(repository_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise ExecutionPreflightError("Git identity check failed")
    return completed.stdout.strip()


def _canonical_path(path: Path, *, label: str) -> Path:
    if not path.is_absolute():
        raise ExecutionPreflightError(f"{label} must be an absolute path")
    return path.resolve(strict=False)


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _validate_isolation(request: ExecutionRequest) -> ExecutionRequest:
    repository_root = _canonical_path(request.repository_root, label="repository_root")
    if not (repository_root / ".git").exists():
        raise ExecutionPreflightError("repository_root is not a Git worktree")
    execution_evidence_root = _canonical_path(
        request.execution_evidence_root, label="execution_evidence_root"
    )
    state_root = _canonical_path(request.state_root, label="state_root")
    binding_artifact_path = (
        _canonical_path(request.binding_artifact_path, label="binding_artifact_path")
        if request.binding_artifact_path is not None
        else None
    )
    roots = {
        "execution_evidence_root": execution_evidence_root,
        "state_root": state_root,
    }
    for label, path in roots.items():
        if path.exists():
            raise ExecutionPreflightError(f"{label} must not already exist")
        if _paths_overlap(repository_root, path):
            raise ExecutionPreflightError(f"{label} must not overlap repository_root")
    root_items = tuple(roots.items())
    for index, (left_label, left_path) in enumerate(root_items):
        for right_label, right_path in root_items[index + 1 :]:
            if _paths_overlap(left_path, right_path):
                raise ExecutionPreflightError(
                    f"{left_label} and {right_label} must not overlap"
                )
    return ExecutionRequest(
        repository_root=repository_root,
        tested_commit=request.tested_commit,
        testset_path=_canonical_path(request.testset_path, label="testset_path"),
        testset_sha256=request.testset_sha256,
        binding_artifact_path=binding_artifact_path,
        execution_evidence_root=execution_evidence_root,
        state_root=state_root,
    )


def _validate_git_identity(request: ExecutionRequest, git_runner: Callable[..., str]) -> None:
    if not _GIT_SHA.fullmatch(request.tested_commit):
        raise ExecutionPreflightError("tested_commit must be a full lowercase Git SHA")
    if git_runner(request.repository_root, "status", "--porcelain"):
        raise ExecutionPreflightError("worktree must be clean")
    head = git_runner(request.repository_root, "rev-parse", "HEAD")
    if head != request.tested_commit:
        raise ExecutionPreflightError("tested_commit must equal HEAD")


def _parse_jsonl(testset_bytes: bytes) -> list[dict[str, Any]]:
    try:
        lines = testset_bytes.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ExecutionPreflightError("testset must be valid UTF-8") from exc
    if not lines:
        raise ExecutionPreflightError("testset must not be empty")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise ExecutionPreflightError(f"testset line {line_number} must not be blank")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExecutionPreflightError(f"testset line {line_number} is not JSON") from exc
        if not isinstance(record, dict):
            raise ExecutionPreflightError(f"testset line {line_number} must be an object")
        records.append(record)
    return records


def _deep_freeze(value: Any) -> Any:
    """Recursively freeze validated Dataset records.

    ``tuple(...)`` only freezes the container; nested sample/input dicts must
    also be immutable (dict -> MappingProxyType, list -> tuple) so that after
    the official Dataset SHA-256 is verified no caller can mutate a sample and
    dispatch it under the official Dataset identity.
    """
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _deep_freeze(nested) for key, nested in value.items()}
        )
    if isinstance(value, list):
        return tuple(_deep_freeze(nested) for nested in value)
    if isinstance(value, tuple):
        return tuple(_deep_freeze(nested) for nested in value)
    if isinstance(value, set):
        return frozenset(_deep_freeze(nested) for nested in value)
    return value


def _require_input_shape(metric: str, value: object) -> None:
    if not isinstance(value, dict):
        raise ExecutionPreflightError(f"{metric} sample input must be an object")
    if metric == "preference":
        required = {"turn_id", "user_id", "user_text"}
    elif metric == "conflict":
        required = {"left", "right"}
        for side in required:
            side_value = value.get(side)
            if not isinstance(side_value, dict) or set(side_value) != {
                "knowledge_id", "user_id", "evidence_tier", "scope"
            }:
                raise ExecutionPreflightError("conflict sample sides must use the frozen input shape")
    elif metric == "safety":
        has_text_case = set(value) == {"user_id", "text"}
        has_read_case = set(value) == {"actor_user_id", "target_user_id", "operation"}
        if not (has_text_case or has_read_case):
            raise ExecutionPreflightError("safety sample must be a text or cross-user read input")
        return
    else:
        required = {"user_id", "forget_mode", "target_selector"}
        selector = value.get("target_selector")
        if not isinstance(selector, dict):
            raise ExecutionPreflightError("forget target_selector must be an object")
    if set(value) != required:
        raise ExecutionPreflightError(f"{metric} sample uses an unexpected input shape")


def _validate_records(records: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    materialized = tuple(records)
    if len(materialized) != 17:
        raise ExecutionPreflightError("testset must contain exactly 17 samples")
    sample_ids: set[str] = set()
    metrics: list[str] = []
    for record in materialized:
        if set(record) != {
            "sample_id",
            "metric",
            "scenario",
            "input",
            "source_basis",
            "synthetic_data",
            "inclusion_status",
        }:
            raise ExecutionPreflightError("testset record uses an unexpected top-level shape")
        sample_id = record.get("sample_id")
        metric = record.get("metric")
        if not isinstance(sample_id, str) or not _SAMPLE_ID.fullmatch(sample_id):
            raise ExecutionPreflightError("testset sample_id is invalid")
        if sample_id in sample_ids:
            raise ExecutionPreflightError("testset sample_id must be unique")
        if metric not in _METRICS:
            raise ExecutionPreflightError("testset metric is invalid")
        if record.get("inclusion_status") != "valid":
            raise ExecutionPreflightError("testset sample must be valid for formal execution")
        _require_input_shape(metric, record.get("input"))
        sample_ids.add(sample_id)
        metrics.append(metric)
    if Counter(metrics) != _EXPECTED_DISTRIBUTION:
        raise ExecutionPreflightError("testset metric distribution is invalid")
    return materialized


def validate_execution_request(
    request: ExecutionRequest,
    *,
    git_runner: Callable[..., str] = _run_git,
) -> ValidatedExecution:
    """Validate all pre-dispatch invariants without creating any artifacts."""
    normalized = _validate_isolation(request)
    if not re.fullmatch(r"[0-9a-f]{64}", normalized.testset_sha256):
        raise ExecutionPreflightError("testset_sha256 must be a lowercase SHA-256")
    if normalized.testset_sha256 != OFFICIAL_D13E_TESTSET_SHA256:
        raise ExecutionPreflightError(
            "testset_sha256 must equal the approved D13E Dataset SHA-256"
        )
    try:
        testset_bytes = normalized.testset_path.read_bytes()
    except OSError as exc:
        raise ExecutionPreflightError("testset cannot be read") from exc
    actual_digest = hashlib.sha256(testset_bytes).hexdigest()
    if actual_digest != OFFICIAL_D13E_TESTSET_SHA256:
        raise ExecutionPreflightError("testset content SHA-256 does not match approved Dataset")
    records = _deep_freeze(_validate_records(_parse_jsonl(testset_bytes)))
    _validate_git_identity(normalized, git_runner)
    return ValidatedExecution(request=normalized, records=records)


def _validate_evaluation_free(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            if not isinstance(key, str) or key.lower() in _FORBIDDEN_EVALUATION_TOKENS:
                raise ExecutionPreflightError("raw actual contains a forbidden evaluation field")
            _validate_evaluation_free(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            _validate_evaluation_free(nested_value)
    elif isinstance(value, str) and value.upper() in {"PASS", "FAIL"}:
        raise ExecutionPreflightError("raw actual contains a forbidden evaluation value")


def _schema_for(metric: str) -> dict[str, Any]:
    try:
        return D13E_RAW_RESULT_SCHEMA_V1["metrics"][metric]
    except KeyError as exc:
        raise ExecutionPreflightError("testset metric is invalid") from exc


def _validate_actual(metric: str, actual: Mapping[str, Any]) -> None:
    """Validate ``actual`` against the candidate per-metric raw projection schema.

    This is a strict whitelist contract, not a "required fields exist + anything
    else is allowed" check: every field in ``actual`` must be declared by
    :data:`D13E_RAW_RESULT_SCHEMA_V1` for that metric.
    """
    schema = _schema_for(metric)
    allowed = frozenset(schema["allowed"])
    required = frozenset(schema["required"])
    _validate_evaluation_free(actual)
    unknown = set(actual) - allowed
    if unknown:
        raise ExecutionPreflightError(
            "raw actual contains fields outside the candidate schema: "
            + ", ".join(sorted(unknown))
        )
    missing = required.difference(actual)
    if missing:
        raise ExecutionPreflightError("raw actual is missing required fields")
    if metric == "forget" and actual.get("forget_mode") not in _FORGET_MODES:
        raise ExecutionPreflightError(
            "forget_mode must be one of the five frozen forget modes"
        )
    for key, value in actual.items():
        if key in _COUNTER_FIELDS and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise ExecutionPreflightError("raw counter fields must be non-negative integers")
    try:
        json.dumps(dict(actual), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ExecutionPreflightError("raw actual must be JSON serializable") from exc


@dataclass(frozen=True)
class ObservedRawRecord:
    """An immutable, strong-typed raw record produced by a real D13D dispatch.

    ``actual`` is an immutable :class:`types.MappingProxyType` snapshot taken at
    creation time, so it cannot be mutated after dispatch.  Every record also
    carries ``actual_digest`` (SHA-256 of the canonical actual bytes); the
    writer re-validates the full record and the digest before any canonical
    file is written.  ``runtime_scope`` binds the record to the dispatch that
    produced it: ``"stateless:<metric>"`` for Preference/Conflict or the
    :class:`ValidatedRuntimeBinding` binding id for Safety.
    """

    sample_id: str
    metric: str
    actual: Mapping[str, Any]
    trace_reference: str
    runtime_scope: str
    actual_digest: str

    def as_canonical_mapping(self) -> dict[str, Any]:
        """Top-level mapping consumed by the formal Runner (no provenance)."""
        return {
            "sample_id": self.sample_id,
            "metric": self.metric,
            "actual": dict(self.actual),
            "trace_reference": self.trace_reference,
        }


def _canonical_actual_bytes(actual: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(actual), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _actual_digest(actual: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_actual_bytes(actual)).hexdigest()


def _snapshot_actual(actual: Mapping[str, Any]) -> MappingProxyType:
    """Deep-copy and freeze an actual so it cannot change after dispatch."""
    return MappingProxyType(json.loads(_canonical_actual_bytes(actual).decode("utf-8")))


def _validate_trace_reference(metric: str, sample_id: str, trace_reference: str) -> None:
    """A trace must be a relative record under evidence_root or a stable ID."""
    if not isinstance(trace_reference, str) or not trace_reference.strip():
        raise ExecutionPreflightError("raw record requires a trace_reference")
    if trace_reference.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", trace_reference):
        raise ExecutionPreflightError("raw record trace_reference must be relative or an opaque trace ID")
    if ".." in Path(trace_reference).parts:
        raise ExecutionPreflightError("raw record trace_reference must not escape the evidence root")
    if metric in ("preference", "conflict"):
        if trace_reference != f"dispatch/{sample_id}.json":
            raise ExecutionPreflightError(
                "trace_reference does not bind the dispatched sample evidence record"
            )
    elif metric == "safety" and not trace_reference.startswith("source-events:"):
        raise ExecutionPreflightError("safety trace_reference must reference the source-events trace")


def _write_execution_receipt(
    validated: ValidatedExecution,
    *,
    sample_id: str,
    metric: str,
    actual: Mapping[str, Any],
    entrypoint: str,
    runtime_scope: str,
    trace_reference: str,
) -> str:
    """Persist one real execution receipt under the evidence root (all metrics).

    ``<evidence_root>/dispatch/<sample_id>.json`` is written with exclusive
    create so a repeated dispatch of the same sample can never silently
    overwrite the first execution evidence.  The receipt binds sample_id,
    metric, full tested_commit, actual_digest, UTC, entrypoint, runtime_scope
    (binding identity for stateful dispatch) and the raw trace_reference, so an
    independent reviewer can re-locate the real execution facts.
    """
    if not isinstance(validated, ValidatedExecution):
        raise TypeError("validated must be a ValidatedExecution")
    if not isinstance(runtime_scope, str) or not runtime_scope.strip():
        raise ExecutionPreflightError("execution receipt requires a runtime scope")
    if not isinstance(trace_reference, str) or not trace_reference.strip():
        raise ExecutionPreflightError("execution receipt requires a trace_reference")
    evidence_root = _canonical_path(
        validated.request.execution_evidence_root, label="execution_evidence_root"
    )
    digest = _actual_digest(actual)
    receipt = {
        "receipt_version": "d13d-execution-receipt/v1",
        "sample_id": sample_id,
        "metric": metric,
        "tested_commit": validated.request.tested_commit,
        "actual_digest": digest,
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "entrypoint": entrypoint,
        "runtime_scope": runtime_scope,
        "trace_reference": trace_reference,
    }
    trace_path = evidence_root / "dispatch" / f"{sample_id}.json"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with trace_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise ExecutionPreflightError(
            f"execution receipt already exists and must not be overwritten: {trace_path.name}"
        ) from exc
    return f"dispatch/{sample_id}.json"


def _verify_execution_receipt(validated: ValidatedExecution, record: ObservedRawRecord) -> None:
    """Fail closed unless this record has evidence-root-backed dispatch provenance.

    Every canonical record (stateless Preference/Conflict, stateful
    Safety/Forget) must have a matching execution receipt under
    ``<evidence_root>/dispatch/<sample_id>.json`` that binds the same
    sample_id/metric/tested_commit/actual_digest/runtime_scope/trace_reference.
    A synthetic or hand-constructed receipt without real execution provenance
    therefore cannot enter the canonical package.
    """
    evidence_root = _canonical_path(
        validated.request.execution_evidence_root, label="execution_evidence_root"
    )
    target = (evidence_root / "dispatch" / f"{record.sample_id}.json").resolve(strict=False)
    if not _is_under(target, evidence_root):
        raise ExecutionPreflightError("execution receipt target escapes the evidence root")
    if not target.exists():
        raise ExecutionPreflightError(
            "execution receipt does not exist under the evidence root for sample "
            + record.sample_id
        )
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
        receipt = json.loads(lines[0]) if lines else None
    except (OSError, ValueError, IndexError) as exc:
        raise ExecutionPreflightError("execution receipt target is not a readable receipt") from exc
    if not isinstance(receipt, dict):
        raise ExecutionPreflightError("execution receipt target is not a JSON receipt object")
    if receipt.get("sample_id") != record.sample_id:
        raise ExecutionPreflightError("execution receipt belongs to a different sample")
    if receipt.get("metric") != record.metric:
        raise ExecutionPreflightError("execution receipt belongs to a different metric")
    if receipt.get("tested_commit") != validated.request.tested_commit:
        raise ExecutionPreflightError("execution receipt belongs to a different tested_commit")
    if receipt.get("actual_digest") != record.actual_digest:
        raise ExecutionPreflightError("execution receipt digest does not match the record")
    if receipt.get("runtime_scope") != record.runtime_scope:
        raise ExecutionPreflightError(
            "execution receipt runtime scope does not match the record"
        )
    if receipt.get("trace_reference") != record.trace_reference:
        raise ExecutionPreflightError(
            "execution receipt trace_reference does not match the record"
        )


def _raw_record(
    *,
    sample_id: str,
    metric: str,
    actual: dict[str, Any],
    trace_reference: str,
    runtime_scope: str,
) -> ObservedRawRecord:
    """Internal construction seam for dispatch receipts (not a provenance gate)."""
    if not _SAMPLE_ID.fullmatch(sample_id) or metric not in _METRICS:
        raise ExecutionPreflightError("raw record identity is invalid")
    if not isinstance(actual, dict) or not actual:
        raise ExecutionPreflightError("raw record actual must be a non-empty object")
    _validate_actual(metric, actual)
    _validate_trace_reference(metric, sample_id, trace_reference)
    if not isinstance(runtime_scope, str) or not runtime_scope.strip():
        raise ExecutionPreflightError("raw record requires a runtime scope from real dispatch")
    digest = _actual_digest(actual)
    return ObservedRawRecord(
        sample_id=sample_id,
        metric=metric,
        actual=_snapshot_actual(actual),
        trace_reference=trace_reference,
        runtime_scope=runtime_scope,
        actual_digest=digest,
    )


def _record_to_line(record: ObservedRawRecord) -> str:
    """Serialize one observed record to the canonical raw JSONL line."""
    return json.dumps(
        record.as_canonical_mapping(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _sample_by_id(validated: ValidatedExecution, sample_id: str) -> Mapping[str, Any]:
    if not isinstance(validated, ValidatedExecution):
        raise TypeError("validated must be a ValidatedExecution")
    for sample in validated.records:
        if sample["sample_id"] == sample_id:
            return sample
    raise ExecutionPreflightError("sample_id is not present in the validated Dataset")


def _preference_actual(sample: Mapping[str, Any]) -> dict[str, Any]:
    """Project real provider observations to stable top-level Runner fields.

    The formal Runner consumes top-level fields only; nested record lists are
    never a canonical actual.  A zero-candidate observation projects
    ``record_count=0`` with ``should_persist=false``; a single-candidate
    observation is flattened to the candidate's stable fields.  More than one
    candidate cannot be projected without losing the Runner contract, so the
    adapter fails closed instead of manufacturing a partial projection.
    """
    sample_input = sample["input"]
    event = TurnFinalizedEvent(
        session_id=sample_input["turn_id"],
        user_text=sample_input["user_text"],
        assistant_text="",
        source_event_id=sample["sample_id"],
    )
    provider = ExtractionProvider()
    try:
        candidates = provider.extract_preferences(event)
    finally:
        provider.close()
    if len(candidates) == 0:
        return {"record_count": 0, "should_persist": False}
    if len(candidates) != 1:
        raise ExecutionPreflightError(
            "preference observation must project a single canonical candidate"
        )
    candidate = candidates[0]
    return {
        "record_count": 1,
        "key": candidate.key,
        "scope": candidate.scope,
        "is_temporary": candidate.is_temporary,
        "should_persist": candidate.should_persist,
        "explicitness": candidate.explicitness,
    }


def _conflict_actual(sample: Mapping[str, Any]) -> dict[str, Any]:
    sample_input = sample["input"]
    decision = ConflictResolutionPolicy().resolve(
        ConflictSide.model_validate(sample_input["left"]),
        ConflictSide.model_validate(sample_input["right"]),
    )
    return {
        "action": decision.action.value,
        "winner_id": decision.winner_id,
        "reason_code": decision.reason_code,
    }


def dispatch_stateless_sample(
    validated: ValidatedExecution, sample_id: str
) -> ObservedRawRecord:
    """Dispatch one validated Preference or Conflict sample through production code.

    Stateful Safety and Forget samples require a separately validated isolated
    runtime binding. They intentionally fail closed here rather than accepting
    a caller-created database, target mapping, or retrieval observation.
    """
    sample = _sample_by_id(validated, sample_id)
    metric = sample["metric"]
    if metric == "preference":
        actual = _preference_actual(sample)
    elif metric == "conflict":
        actual = _conflict_actual(sample)
    else:
        raise ExecutionPreflightError("metric requires an isolated runtime binding")
    trace_reference = f"dispatch/{sample_id}.json"
    _write_execution_receipt(
        validated,
        sample_id=sample_id,
        metric=metric,
        actual=actual,
        entrypoint="dispatch_stateless_sample",
        runtime_scope=f"stateless:{metric}",
        trace_reference=trace_reference,
    )
    return _raw_record(
        sample_id=sample_id,
        metric=metric,
        actual=actual,
        trace_reference=trace_reference,
        runtime_scope=f"stateless:{metric}",
    )


@dataclass(frozen=True)
class ValidatedRuntimeBinding:
    """An opaque Safety/Forget dispatch runtime bound to one validated state root.

    The binding is the only object a stateful dispatcher accepts: the engine,
    the handler registry and the canonical DB path are created together by
    :func:`build_runtime_binding` under ``validated.request.state_root``, so a
    caller can no longer hand the dispatcher an arbitrary ``conn`` + ``registry``
    that was never verified against the validated isolation state.
    """

    validated: ValidatedExecution
    binding_id: str
    db_path: Path
    engine: Any
    registry: HandlerRegistry
    event_ingest_handler: Any
    run_token_sha256: str
    forget_preview_handler: Any = None
    forget_execute_handler: Any = None
    binding_artifact_sha256: Optional[str] = None
    state_preparation_commit: Optional[str] = None
    source_db_sha256: Optional[str] = None
    runtime_db_initial_sha256: Optional[str] = None
    sample_id: Optional[str] = None
    restore_id: Optional[str] = None


def _is_under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def build_runtime_binding(
    validated: ValidatedExecution,
    *,
    database_name: str = "d13d-safety.db",
) -> ValidatedRuntimeBinding:
    """Create an isolated runtime binding under the validated ``state_root``.

    The canonical DB path is always ``state_root/runtime/<database_name>`` and
    must not already exist (preflight guarantees the state root itself is new),
    so a normal/user or previously used database can never be reused.  The
    handler registry is constructed here from the same engine, closing the
    "validated state root" / "actual dispatch DB" gap.
    """
    if not isinstance(validated, ValidatedExecution):
        raise TypeError("validated must be a ValidatedExecution")
    if not isinstance(database_name, str) or not database_name.strip():
        raise ExecutionPreflightError("runtime database_name must be a non-empty name")
    if "/" in database_name or "\\" in database_name or database_name in (".", ".."):
        raise ExecutionPreflightError("runtime database_name must be a plain basename")
    state_root = _canonical_path(validated.request.state_root, label="state_root")
    runtime_root = state_root / "runtime"
    db_path = (runtime_root / database_name).resolve(strict=False)
    if not _is_under(db_path, state_root):
        raise ExecutionPreflightError("runtime binding db must live under validated state_root")
    if db_path.exists():
        raise ExecutionPreflightError("runtime binding db must not already exist")
    runtime_root.mkdir(parents=True, exist_ok=False)
    engine = create_db_engine(str(db_path))
    init_schema(engine)
    registry = HandlerRegistry()
    register_default_handlers(registry)
    register_event_ingest_handler(registry, uow_factory=lambda: UnitOfWork(engine))
    register_preference_handlers(registry, uow_factory=lambda: UnitOfWork(engine))
    # D/E P2-B 裁定：validation profile 显式注册真实 forget.preview/forget.execute
    # handler（生产 default 不注册，本 binding 即该 profile 的受控注册点）。
    register_forget_handlers(registry, uow_factory=lambda: UnitOfWork(engine))
    # Bind engine <-> registry <-> canonical db path with an unforgeable run
    # token: the engine is registered under its object id and the registry
    # carries the same token, so a caller-constructed binding with a foreign
    # engine or registry cannot pass _validate_binding().
    run_token = secrets.token_hex(32)
    _ENGINE_BINDING_TOKENS[id(engine)] = run_token
    setattr(registry, "d13d_runtime_token", run_token)
    binding_id = (
        f"d13d-runtime-binding/v1:{validated.request.tested_commit[:12]}:{database_name}"
    )
    # Freeze the production event.ingest callable identity created by this
    # builder; _validate_binding() requires registry.route() to return exactly
    # this object, so a later register()/unregister() overwrite cannot swap in
    # a fake handler before real dispatch.
    event_ingest_handler = registry.route("event.ingest")
    # P2-B：同时冻结 forget.preview / forget.execute 的真实 handler 身份。
    forget_preview_handler = registry.route("forget.preview")
    forget_execute_handler = registry.route("forget.execute")
    return ValidatedRuntimeBinding(
        validated=validated,
        binding_id=binding_id,
        db_path=db_path,
        engine=engine,
        registry=registry,
        event_ingest_handler=event_ingest_handler,
        forget_preview_handler=forget_preview_handler,
        forget_execute_handler=forget_execute_handler,
        run_token_sha256=hashlib.sha256(run_token.encode("ascii")).hexdigest(),
    )


def _is_ancestor(repository_root: Path, ancestor: str) -> bool:
    """state_preparation/minimum commit 是否为 repository HEAD 的祖先。"""
    completed = subprocess.run(
        ["git", "-C", str(repository_root), "merge-base", "--is-ancestor",
         ancestor, "HEAD"],
        capture_output=True, text=True,
    )
    return completed.returncode == 0


def _sqlite_integrity_ok(db_path: Path) -> bool:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = con.execute("PRAGMA quick_check(1)").fetchone()
    finally:
        con.close()
    return bool(row) and str(row[0]).lower() == "ok"


def _sqlite_schema_fingerprint(db_path: Path) -> str:
    """sqlite_master canonical SHA-256（schema 兼容现场校验）。"""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT type || '|' || name || '|' || COALESCE(sql, '') "
            "FROM sqlite_master ORDER BY name"
        ).fetchall()
    finally:
        con.close()
    canonical = "\n".join(row[0] for row in rows).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _load_forget_artifact_v2(artifact_path: Path) -> dict[str, Any]:
    if artifact_path is None:
        raise ExecutionPreflightError("forget dispatch requires the D13D forget state binding artifact")
    ok, errors = verify_artifact_file(str(artifact_path))
    if not ok:
        raise ExecutionPreflightError(
            "forget state binding artifact failed validation: " + "; ".join(errors[:3])
        )
    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    if artifact.get("binding_version") != BINDING_VERSION_V2:
        raise ExecutionPreflightError(
            "forget dispatch requires binding_version " + BINDING_VERSION_V2
        )
    return artifact


def _verify_sealed_source(artifact: Mapping[str, Any]) -> Path:
    """V2 sealed source DB：拒绝 symlink、SHA/字节数/schema/integrity 现场复核。"""
    source = artifact.get("source_state")
    if not isinstance(source, Mapping):
        raise ExecutionPreflightError("artifact source_state is missing")
    raw_path = source.get("sealed_db_path")
    db_path = Path(raw_path)
    if db_path.is_symlink():
        raise ExecutionPreflightError("source DB must not be a symlink")
    if not db_path.exists():
        raise ExecutionPreflightError("source DB does not exist")
    if hashlib.sha256(db_path.read_bytes()).hexdigest() != source.get("sealed_db_sha256"):
        raise ExecutionPreflightError("source DB SHA-256 does not match the artifact")
    if db_path.stat().st_size != int(source.get("db_size_bytes", -1)):
        raise ExecutionPreflightError("source DB size does not match the artifact")
    try:
        fingerprint = _sqlite_schema_fingerprint(db_path)
        integrity_ok = _sqlite_integrity_ok(db_path)
    except sqlite3.Error as exc:
        raise ExecutionPreflightError(
            "source DB is not a valid sqlite database"
        ) from exc
    if fingerprint != source.get("sqlite_schema_fingerprint"):
        raise ExecutionPreflightError("source DB schema fingerprint does not match the artifact")
    if not integrity_ok:
        raise ExecutionPreflightError("source DB integrity check failed")
    return db_path


def prepare_forget_runtime_bindings(
    validated: ValidatedExecution,
    *,
    artifact_path: Path,
) -> dict[str, ValidatedRuntimeBinding]:
    """R5：sealed source → 每 sample 独立 isolated runtime clone（带 provenance）。

    - 校验 artifact（v2）、source DB（SHA/size/schema/integrity/拒绝 symlink）；
    - state_preparation_commit 与 execution_compatibility.minimum_commit 必须是
      repository HEAD 祖先；
    - 每个 Forget sample 在 state_root/runtime/<sample_id>/runtime.db 生成 fresh
      copy（初始 SHA == source SHA），并注册冻结真实 handlers；
    - ValidatedRuntimeBinding 携带 provenance（artifact sha / state_prep commit /
      source sha / initial sha / sample_id / restore_id）。
    """
    artifact = _load_forget_artifact_v2(Path(artifact_path))
    exec_compat = artifact.get("execution_compatibility") or {}
    if exec_compat.get("policy") != "descendant-and-contract-compatible":
        raise ExecutionPreflightError("execution_compatibility.policy is unsupported")
    repository_root = _canonical_path(
        validated.request.repository_root, label="repository_root"
    )
    sp_commit = artifact.get("state_preparation_commit")
    min_commit = exec_compat.get("minimum_commit")
    if not _is_ancestor(repository_root, sp_commit):
        raise ExecutionPreflightError(
            "state_preparation_commit is not an ancestor of repository HEAD"
        )
    if not _is_ancestor(repository_root, min_commit):
        raise ExecutionPreflightError(
            "execution_compatibility.minimum_commit is not an ancestor of repository HEAD"
        )
    source_db = _verify_sealed_source(artifact)

    state_root = _canonical_path(validated.request.state_root, label="state_root")
    runtime_root = state_root / "runtime"
    if runtime_root.exists():
        raise ExecutionPreflightError("runtime root must not already exist")
    runtime_root.mkdir(parents=True, exist_ok=False)

    artifact_sha = artifact.get("artifact_sha256")
    source_sha = artifact["source_state"]["sealed_db_sha256"]
    bindings: dict[str, ValidatedRuntimeBinding] = {}
    for sample_id in sorted(FORGET_SAMPLE_MODES):
        sample_root = runtime_root / sample_id
        sample_root.mkdir(parents=False)
        db_path = sample_root / "runtime.db"
        shutil.copyfile(source_db, db_path)
        initial_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()
        if initial_sha != source_sha:
            raise ExecutionPreflightError("runtime clone initial SHA does not match source")
        engine = create_db_engine(str(db_path))
        registry = HandlerRegistry()
        register_default_handlers(registry)
        register_event_ingest_handler(registry, uow_factory=lambda: UnitOfWork(engine))
        register_preference_handlers(registry, uow_factory=lambda: UnitOfWork(engine))
        register_forget_handlers(registry, uow_factory=lambda: UnitOfWork(engine))
        run_token = secrets.token_hex(32)
        _ENGINE_BINDING_TOKENS[id(engine)] = run_token
        setattr(registry, "d13d_runtime_token", run_token)
        binding_id = (
            f"d13d-runtime-binding/v2:{validated.request.tested_commit[:12]}:{sample_id}"
        )
        event_ingest_handler = registry.route("event.ingest")
        forget_preview_handler = registry.route("forget.preview")
        forget_execute_handler = registry.route("forget.execute")
        bindings[sample_id] = ValidatedRuntimeBinding(
            validated=validated,
            binding_id=binding_id,
            db_path=db_path,
            engine=engine,
            registry=registry,
            event_ingest_handler=event_ingest_handler,
            forget_preview_handler=forget_preview_handler,
            forget_execute_handler=forget_execute_handler,
            run_token_sha256=hashlib.sha256(run_token.encode("ascii")).hexdigest(),
            binding_artifact_sha256=artifact_sha,
            state_preparation_commit=sp_commit,
            source_db_sha256=source_sha,
            runtime_db_initial_sha256=initial_sha,
            sample_id=sample_id,
            restore_id=f"restore:{sample_id}:{secrets.token_hex(6)}",
        )
    return bindings

def _validate_binding(
    binding: ValidatedRuntimeBinding, validated: ValidatedExecution
) -> None:
    """Fail closed unless the binding is bound to this validated isolation state.

    The engine's canonical DB path must equal ``binding.db_path``, the engine
    must be one created by :func:`build_runtime_binding` (run-token registry),
    and the handler registry must carry the same run token.  A caller-constructed
    binding with a foreign engine/registry can therefore never pass.
    """
    if not isinstance(binding, ValidatedRuntimeBinding):
        raise ExecutionPreflightError("safety dispatch requires a ValidatedRuntimeBinding")
    if binding.validated != validated:
        raise ExecutionPreflightError(
            "runtime binding was not created from this validated execution"
        )
    state_root = _canonical_path(validated.request.state_root, label="state_root")
    db_path = _canonical_path(binding.db_path, label="binding.db_path")
    if not _is_under(db_path, state_root):
        raise ExecutionPreflightError(
            "runtime binding db must live under validated state_root"
        )
    if not db_path.exists():
        raise ExecutionPreflightError("runtime binding db does not exist")
    if binding.engine is None or binding.registry is None:
        raise ExecutionPreflightError("runtime binding is incomplete")

    database = getattr(binding.engine, "url", None)
    database_path = getattr(database, "database", None)
    if not isinstance(database_path, str) or not database_path:
        raise ExecutionPreflightError(
            "runtime binding engine must expose a canonical file database"
        )
    engine_db = _canonical_path(Path(database_path), label="engine.url.database")
    if engine_db != db_path:
        raise ExecutionPreflightError(
            "runtime binding engine is not connected to binding.db_path"
        )

    registered_token = _ENGINE_BINDING_TOKENS.get(id(binding.engine))
    if not isinstance(registered_token, str) or not registered_token:
        raise ExecutionPreflightError(
            "runtime binding engine was not created by the controlled builder"
        )
    if hashlib.sha256(registered_token.encode("ascii")).hexdigest() != binding.run_token_sha256:
        raise ExecutionPreflightError(
            "runtime binding engine token does not match the binding"
        )
    registry_token = getattr(binding.registry, "d13d_runtime_token", None)
    if registry_token != registered_token:
        raise ExecutionPreflightError(
            "runtime binding registry is not bound to the same engine/run"
        )
    try:
        routed_ingest = binding.registry.route("event.ingest")
    except Exception:  # noqa: BLE001 -- unregistered handler is a replaced binding
        routed_ingest = None
    if routed_ingest is not binding.event_ingest_handler:
        raise ExecutionPreflightError(
            "runtime binding event.ingest handler was replaced or unregistered"
        )
    for method, frozen in (
        ("forget.preview", binding.forget_preview_handler),
        ("forget.execute", binding.forget_execute_handler),
    ):
        try:
            routed = binding.registry.route(method)
        except Exception:  # noqa: BLE001 -- unregistered handler is a replaced binding
            routed = None
        if routed is not frozen:
            raise ExecutionPreflightError(
                f"runtime binding {method} handler was replaced or unregistered"
            )
    # R5：带 provenance 的 Forget runtime binding 进一步校验 sample/restore 身份。
    if binding.sample_id is not None:
        if binding.sample_id not in FORGET_SAMPLE_MODES:
            raise ExecutionPreflightError("runtime binding sample_id is invalid")
        expected_dir = state_root / "runtime" / binding.sample_id
        if not _is_under(db_path, expected_dir):
            raise ExecutionPreflightError(
                "runtime binding db is not under its sample runtime dir"
            )
        for attr in (
            "binding_artifact_sha256",
            "state_preparation_commit",
            "source_db_sha256",
            "runtime_db_initial_sha256",
            "restore_id",
        ):
            if not getattr(binding, attr):
                raise ExecutionPreflightError(f"runtime binding missing provenance: {attr}")


def _persisted_safety_event_fields(conn, *, user_id: str, trace_id: str) -> tuple[str, str]:
    """真实持久化 source_events 的 (sensitivity, admission_decision)。

    必须唯一可确定：无事件、多值或冲突 → 抛 ValueError（fail-closed）。
    """
    rows = conn.execute(
        select(
            source_events.c.sensitivity,
            source_events.c.admission_decision,
        )
        .where(
            and_(
                source_events.c.user_id == user_id,
                source_events.c.trace_id == trace_id,
            )
        )
        .order_by(source_events.c.id.asc())
    ).mappings().all()
    if not rows:
        raise ValueError("no persisted source event for the safety trace")
    sensitivities = {row["sensitivity"] for row in rows}
    admissions = {row["admission_decision"] for row in rows}
    if len(sensitivities) != 1 or len(admissions) != 1:
        raise ValueError("persisted safety observation is conflicting or not unique")
    return sensitivities.pop(), admissions.pop()


def _project_safety_actual(
    *,
    sample_id: str,
    sample_input: Mapping[str, Any],
    observed: Mapping[str, Any],
    conn: Any,
    user_id: str,
    trace_id: str,
) -> dict[str, Any]:
    """把真实观测投影为 Safety raw actual（消费 #162 frozen contract）。

    - safety-001/002：+ sensitivity/admission（来自真实 persisted source_events）；
    - safety-003：+ operation/admission（operation 来自 SHA 验证 Dataset input；
      admission 由真实 user-scoped repository read observation 推导，不固定 reject）；
    - safety-004：仅四 hard-zero counter（真实来源）。
    观测缺失/冲突 fail-closed；真实安全违规（cross_user_violation_count>0）原样写入，
    不吞 raw、不代 Runner 判 FAIL。
    """
    actual = {
        "critical_gate_bypass_count": observed["critical_gate_bypass_count"],
        "normal_memory_write_count": observed["normal_memory_write_count"],
        "audit_plaintext_leak_count": observed["audit_plaintext_leak_count"],
        "cross_user_violation_count": observed["cross_user_violation_count"],
    }
    if sample_id in ("d13e-safety-001", "d13e-safety-002"):
        sensitivity, admission = _persisted_safety_event_fields(
            conn, user_id=user_id, trace_id=trace_id
        )
        actual["sensitivity"] = sensitivity
        actual["admission"] = admission
    elif sample_id == "d13e-safety-003":
        actual["operation"] = sample_input["operation"]
        # user-scoped repository read observation：越界返回（violation）≠ 观测不可用。
        actual["admission"] = (
            "reject" if actual["cross_user_violation_count"] == 0 else "allow"
        )
    return actual

def dispatch_safety_sample(
    validated: ValidatedExecution,
    sample_id: str,
    *,
    binding: ValidatedRuntimeBinding,
    foreign_user_id: str | None = None,
) -> ObservedRawRecord:
    """Run one Safety sample through real ingestion and observation boundaries.

    The dispatcher only accepts a :class:`ValidatedRuntimeBinding` whose DB is
    canonical under the validated ``state_root``; bare caller-supplied
    connections and registries are not accepted.  A foreign-user control is an
    explicit runtime binding, never an adapter-created fixture.  The function
    leaves raw persistence to the orchestration path so no record can enter the
    canonical package unless it was produced by this real dispatch.
    """
    sample = _sample_by_id(validated, sample_id)
    if sample["metric"] != "safety":
        raise ExecutionPreflightError("sample is not a safety metric")
    _validate_binding(binding, validated)
    sample_input = sample["input"]
    if "text" in sample_input:
        user_id = sample_input["user_id"]
        content_summary = sample_input["text"]
        if not isinstance(foreign_user_id, str) or not foreign_user_id.strip():
            raise ExecutionPreflightError("safety text sample requires a foreign_user_id binding")
    else:
        user_id = sample_input["actor_user_id"]
        foreign_user_id = sample_input["target_user_id"]
        if sample_input["operation"] != "read":
            raise ExecutionPreflightError("safety cross-user sample must be a read operation")
        content_summary = "D13D controlled cross-user read probe"
    trace_id = f"d13d-safety-{sample_id}"
    now = datetime.now(timezone.utc)
    payload = {
        "schema_version": "0.1",
        "event_id": f"d13d-event-{sample_id}",
        "user_id": user_id,
        "actor_id": user_id,
        "session_id": f"d13d-session-{sample_id}",
        "idempotency_key": f"d13d-idem-{sample_id}",
        "source_type": "chat",
        "event_type": "user_message",
        "occurred_at": (now - timedelta(seconds=1)).isoformat(),
        "captured_at": now.isoformat(),
        "content_summary": content_summary,
        "consent_scope": "memory_only",
    }
    context = RequestContext(
        request_id=f"d13d-request-{sample_id}",
        trace_id=trace_id,
        method="event.ingest",
        deadline_ms=5000,
        user_id=user_id,
        session_id=payload["session_id"],
        idempotency_key=payload["idempotency_key"],
    )
    try:
        with binding.engine.begin() as conn:
            binding.event_ingest_handler(payload, context)
            observed = observe_safety_execution(
                conn,
                user_id=user_id,
                trace_id=trace_id,
                foreign_user_id=foreign_user_id,
            )
            actual = _project_safety_actual(
                sample_id=sample_id,
                sample_input=sample_input,
                observed=observed,
                conn=conn,
                user_id=user_id,
                trace_id=trace_id,
            )
    except Exception as exc:
        raise ExecutionPreflightError("safety dispatch failed") from exc
    trace_reference = observed["trace_reference"]
    _write_execution_receipt(
        validated,
        sample_id=sample_id,
        metric="safety",
        actual=actual,
        entrypoint="dispatch_safety_sample",
        runtime_scope=binding.binding_id,
        trace_reference=trace_reference,
    )
    return _raw_record(
        sample_id=sample_id,
        metric="safety",
        actual=actual,
        trace_reference=trace_reference,
        runtime_scope=binding.binding_id,
    )


def _tagged_confirmed(mode: str, resolved: list[str]) -> list[str]:
    """把 preview 解析结果规范成 observer 需要的 tagged 目标 ID。

    single_item/session/topic/time_window 解析为裸 memory_entries.id；
    full_reset 已带 knowledge:/preference: 标签。
    """
    if mode == "full_reset":
        return list(resolved)
    return [f"knowledge:{rid}" for rid in resolved]


def dispatch_forget_sample(
    validated: ValidatedExecution,
    sample_id: str,
    *,
    binding: ValidatedRuntimeBinding,
) -> ObservedRawRecord:
    """Run one Forget sample through the real production preview/execute chain.

    - binding 必须是本 sample 的 restored runtime binding（R5）：sample_id 匹配 +
      provenance（artifact sha / state_prep commit / source sha / initial sha / restore id）。
    - artifact 必须是 v2（ExecutionRequest.binding_artifact_path）；HEAD == tested_commit
      由 preflight 锁定；不再存在单一 applicable_source_commit equality。
    - confirmation token 由真实 forget.preview 一次性返回，execute 只消费该凭据；
      adapter 不创建/修补目标、不从 Dataset 推导 DB ID、不伪造 observation。
    - realtime/rebuild observation 只来自 closed allowlist OBSERVATION_PROFILES[
      artifact.retrieval_profile]；缺失/未知 profile 即 fail-closed，不写 canonical raw。
    """
    sample = _sample_by_id(validated, sample_id)
    if sample["metric"] != "forget":
        raise ExecutionPreflightError("sample is not a forget metric")
    if binding.sample_id != sample_id:
        raise ExecutionPreflightError(
            "forget runtime binding sample_id does not match the dispatched sample"
        )
    _validate_binding(binding, validated)
    artifact = _load_forget_artifact_v2(validated.request.binding_artifact_path)
    entry = next(
        (s for s in artifact.get("samples", []) if s.get("sample_id") == sample_id), None
    )
    if entry is None:
        raise ExecutionPreflightError(f"binding artifact has no entry for {sample_id}")
    builder = OBSERVATION_PROFILES.get(artifact.get("retrieval_profile"))
    if builder is None:
        raise ExecutionPreflightError(
            "no approved retrieval observation profile: "
            + str(artifact.get("retrieval_profile"))
        )

    mode = entry["forget_mode"]
    user_id = entry["user_id"]
    foreign_user_id = "user_d13e_beta"
    selector = entry.get("target_selector") or sample["input"].get("target_selector") or {}
    target_selector = json.dumps(selector, ensure_ascii=False)
    target_id = target_session_id = target_topic = target_time_range = None
    target_type = "knowledge"
    if mode == "single_item":
        target_id = str(entry["target_identity"]["db_id"])
    elif mode == "session":
        target_session_id = entry["target_identity"]["session_id"]
    elif mode == "topic":
        target_topic = entry["target_identity"]["topic_key"]
    elif mode == "time_window":
        target_time_range = json.dumps(selector, ensure_ascii=False)
    elif mode == "full_reset":
        target_type = "all"
    else:
        raise ExecutionPreflightError(f"unsupported forget mode: {mode}")

    forget_plan_id = f"d13d-plan-{sample_id}-{secrets.token_hex(6)}"
    trace_id = f"d13d-forget-{sample_id}"
    session_id = target_session_id or f"d13d-session-{sample_id}"

    def _ctx(method: str, idem: str) -> RequestContext:
        return RequestContext(
            request_id=f"d13d-request-{sample_id}",
            trace_id=trace_id,
            method=method,
            deadline_ms=10000,
            user_id=user_id,
            session_id=session_id,
            idempotency_key=idem,
        )

    preview_payload = {
        "forget_plan_id": forget_plan_id,
        "user_id": user_id,
        "forget_mode": mode,
        "target_selector": target_selector,
        "target_type": target_type,
        "target_id": target_id,
        "target_session_id": target_session_id,
        "target_topic": target_topic,
        "target_time_range": target_time_range,
        "requires_confirmation": True,
        "is_cascade": False,
        "delete_mode": "soft",
    }
    try:
        with binding.engine.begin() as conn:
            preview = binding.forget_preview_handler(
                preview_payload, _ctx("forget.preview", f"d13d-preview-{sample_id}")
            )
            confirmation_token = preview.get("confirmation_token")
            resolved = list(preview.get("resolved_target_ids") or [])
            if not confirmation_token or not resolved:
                raise ExecutionPreflightError(
                    "forget.preview did not return a one-time confirmation credential / targets"
                )
            confirmed = _tagged_confirmed(mode, resolved)
            snapshot = capture_forget_execution_snapshot(
                conn,
                user_id=user_id,
                foreign_user_id=foreign_user_id,
                confirmed_target_ids=confirmed,
            )
        # execute 使用真实 preview 凭据（独立事务，预删除快照之后）
        with binding.engine.begin() as conn:
            binding.forget_execute_handler(
                {
                    "forget_plan_id": forget_plan_id,
                    "user_id": user_id,
                    "confirmation_token": confirmation_token,
                },
                _ctx("forget.execute", f"d13d-execute-{sample_id}"),
            )
        realtime_observation, rebuild_observation = builder(binding, artifact, sample_id)
        with binding.engine.connect() as conn:
            observed = observe_forget_execution(
                conn,
                snapshot=snapshot,
                realtime_observation=realtime_observation,
                rebuild_observation=rebuild_observation,
            )
    except ExecutionPreflightError:
        raise
    except Exception as exc:  # noqa: BLE001 -- dispatch envelope keeps errors safe
        raise ExecutionPreflightError("forget dispatch failed") from exc

    actual = {"forget_mode": mode, **observed}
    trace_reference = f"dispatch/{sample_id}.json"
    _write_execution_receipt(
        validated,
        sample_id=sample_id,
        metric="forget",
        actual=actual,
        entrypoint="dispatch_forget_sample",
        runtime_scope=binding.binding_id,
        trace_reference=trace_reference,
    )
    return _raw_record(
        sample_id=sample_id,
        metric="forget",
        actual=actual,
        trace_reference=trace_reference,
        runtime_scope=binding.binding_id,
    )

def _write_text_file(path: Path, content: str) -> None:
    """I/O seam for raw writes (injected by the atomicity fault test)."""
    path.write_text(content, encoding="utf-8", newline="\n")


def _validate_receipt(
    record: ObservedRawRecord,
    *,
    expected_metric_by_id: Mapping[str, str],
    validated: ValidatedExecution,
) -> None:
    """Re-run the full record/actual/trace contract before canonical writing.

    The receipt is re-validated here so that an actual mutated or forged after
    dispatch can never reach a canonical raw file: the actual must be an
    immutable dispatch snapshot, its digest must match, and every field must
    still satisfy the candidate schema whitelist.
    """
    if not isinstance(record, ObservedRawRecord):
        raise ExecutionPreflightError(
            "raw record must be an ObservedRawRecord produced by real dispatch"
        )
    sample_id = record.sample_id
    if expected_metric_by_id.get(sample_id) != record.metric:
        raise ExecutionPreflightError("raw sample_id and metric must match the Dataset")
    if not isinstance(record.actual, Mapping) or type(record.actual) is not MappingProxyType:
        raise ExecutionPreflightError(
            "raw record actual must be an immutable dispatch snapshot"
        )
    _validate_actual(record.metric, dict(record.actual))
    if record.actual_digest != _actual_digest(record.actual):
        raise ExecutionPreflightError("raw record actual digest does not match its content")
    _validate_trace_reference(record.metric, sample_id, record.trace_reference)
    if not isinstance(record.runtime_scope, str) or not record.runtime_scope.strip():
        raise ExecutionPreflightError("raw record has no runtime dispatch scope")
    _verify_execution_receipt(validated, record)


def _write_raw_records(
    validated: ValidatedExecution,
    raw_records: Iterable[ObservedRawRecord],
) -> dict[str, Path]:
    """Private serializer of dispatch receipts into the four canonical raw files.

    PRIVATE: the only public production entry for the canonical package is
    dispatch_and_write_canonical(), which dispatches inside one controlled call
    and never accepts externally supplied receipts.  This serializer re-validates
    every immutable receipt (actual/digest/trace/runtime scope), requires
    stateless trace targets to exist under the evidence root, writes ``raw/``
    into a sibling temporary directory and atomically renames it into the
    execution evidence root so an I/O failure can never leave a partial
    package.  Both ``dispatch/`` receipts and ``raw/`` canonical files live
    under the same execution evidence root, matching the formal Runner's
    evidence-directory path gate.
    """
    if not isinstance(validated, ValidatedExecution):
        raise TypeError("validated must be a ValidatedExecution")
    expected_metric_by_id = {
        sample["sample_id"]: sample["metric"] for sample in validated.records
    }
    grouped: dict[str, list[ObservedRawRecord]] = {metric: [] for metric in _METRICS}
    seen_sample_ids: set[str] = set()
    for source_record in raw_records:
        _validate_receipt(
            source_record,
            expected_metric_by_id=expected_metric_by_id,
            validated=validated,
        )
        sample_id = source_record.sample_id
        if sample_id in seen_sample_ids:
            raise ExecutionPreflightError("raw sample_id must be unique")
        seen_sample_ids.add(sample_id)
        grouped[source_record.metric].append(source_record)
    if seen_sample_ids != set(expected_metric_by_id):
        raise ExecutionPreflightError("raw samples do not match the complete Dataset")
    evidence_root = _canonical_path(
        validated.request.execution_evidence_root, label="execution_evidence_root"
    )
    raw_root = evidence_root / "raw"
    if raw_root.exists():
        raise ExecutionPreflightError(
            "raw package must not already exist under the execution evidence root"
        )

    tmp_raw_root = evidence_root / f".raw.tmp-{os.getpid()}-{secrets.token_hex(4)}"
    written_tmp: dict[str, Path] = {}
    try:
        tmp_raw_root.mkdir(parents=True)
        for metric, filename in _RAW_FILENAMES.items():
            path = tmp_raw_root / filename
            serialized = "".join(_record_to_line(record) + "\n" for record in grouped[metric])
            _write_text_file(path, serialized)
            written_tmp[metric] = path
        for metric in _METRICS:
            if len(grouped[metric]) != _EXPECTED_DISTRIBUTION[metric]:
                raise ExecutionPreflightError("raw package distribution is incomplete")
        tmp_raw_root.rename(raw_root)
    except Exception:
        shutil.rmtree(tmp_raw_root, ignore_errors=True)
        raise
    return {
        metric: evidence_root / "raw" / _RAW_FILENAMES[metric] for metric in _METRICS
    }




def dispatch_and_write_canonical(validated: ValidatedExecution) -> dict[str, Path]:
    """Formal canonical raw package production (orchestration-only entry).

    This is the ONLY public production entry for the canonical package and it
    never accepts externally supplied raw receipts: all 17 samples are
    dispatched through the real dispatchers inside one controlled call and then
    serialized by the private `_write_raw_records`.  Forget still requires the
    externally supplied state binding (BLOCKED), so this call currently fails
    closed before any output is created.
    """
    if not isinstance(validated, ValidatedExecution):
        raise TypeError("validated must be a ValidatedExecution")
    if any(sample["metric"] == "forget" for sample in validated.records):
        raise ExecutionPreflightError(
            "canonical dispatch is BLOCKED: forget requires an external state binding"
        )
    raise ExecutionPreflightError(
        "canonical dispatch is not executable until every sample can be dispatched"
    )
