"""Fail-closed preflight for the versioned D13D execution adapter.

This module deliberately validates only the public formal Dataset inputs.  It
does not import any evaluator-owned decision artifacts, and it does not decide
whether an observed result passes. Dispatch and raw production are held behind
the separately frozen VM execution gate described in the D13D task card.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Iterable, Mapping

from providers.extraction_provider import ExtractionProvider, TurnFinalizedEvent
from service.conflict_resolution_policy import ConflictResolutionPolicy, ConflictSide
from service.d13d_safety_observability import observe_safety_execution
from gateway.registry import HandlerRegistry, RequestContext


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
_REQUIRED_ACTUAL_FIELDS = {
    "preference": frozenset({"record_count"}),
    "conflict": frozenset({"action", "winner_id", "reason_code"}),
    "safety": frozenset(
        {
            "critical_gate_bypass_count",
            "normal_memory_write_count",
            "audit_plaintext_leak_count",
            "cross_user_violation_count",
        }
    ),
    "forget": frozenset(
        {
            "missed_target_items",
            "wrongly_deleted_items",
            "cross_user_violation_count",
            "residual_after_realtime_query",
            "residual_after_full_rebuild",
        }
    ),
}
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


class ExecutionPreflightError(ValueError):
    """An invocation is not safe to dispatch against an isolated environment."""


@dataclass(frozen=True)
class ExecutionRequest:
    """All identity and isolation inputs required before any D13D dispatch."""

    repository_root: Path
    tested_commit: str
    testset_path: Path
    testset_sha256: str
    output_root: Path
    state_root: Path
    evidence_root: Path


@dataclass(frozen=True)
class ValidatedExecution:
    """A validated Dataset and the immutable identity used to validate it."""

    request: ExecutionRequest
    records: tuple[dict[str, Any], ...]


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
    output_root = _canonical_path(request.output_root, label="output_root")
    state_root = _canonical_path(request.state_root, label="state_root")
    evidence_root = _canonical_path(request.evidence_root, label="evidence_root")
    roots = {
        "output_root": output_root,
        "state_root": state_root,
        "evidence_root": evidence_root,
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
        output_root=output_root,
        state_root=state_root,
        evidence_root=evidence_root,
    )


def _validate_git_identity(request: ExecutionRequest, git_runner: Callable[..., str]) -> None:
    if not _GIT_SHA.fullmatch(request.tested_commit):
        raise ExecutionPreflightError("tested_commit must be a full lowercase Git SHA")
    if git_runner(request.repository_root, "status", "--porcelain"):
        raise ExecutionPreflightError("worktree must be clean")
    head = git_runner(request.repository_root, "rev-parse", "HEAD")
    if head != request.tested_commit:
        raise ExecutionPreflightError("tested_commit must equal HEAD")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ExecutionPreflightError("testset does not exist") from exc
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
    records = _validate_records(_read_jsonl(normalized.testset_path))
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


def _validate_actual(metric: str, actual: Mapping[str, Any]) -> None:
    missing = _REQUIRED_ACTUAL_FIELDS[metric].difference(actual)
    if missing:
        raise ExecutionPreflightError("raw actual is missing required fields")
    for key, value in actual.items():
        if key in _COUNTER_FIELDS and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise ExecutionPreflightError("raw counter fields must be non-negative integers")
    _validate_evaluation_free(actual)
    try:
        json.dumps(actual, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ExecutionPreflightError("raw actual must be JSON serializable") from exc


def raw_record(*, sample_id: str, metric: str, actual: dict[str, Any], trace_reference: str) -> dict[str, Any]:
    """Create the only permitted raw record shape after a real execution."""
    if not _SAMPLE_ID.fullmatch(sample_id) or metric not in _METRICS:
        raise ExecutionPreflightError("raw record identity is invalid")
    if not isinstance(actual, dict) or not actual:
        raise ExecutionPreflightError("raw record actual must be a non-empty object")
    _validate_actual(metric, actual)
    if not isinstance(trace_reference, str) or not trace_reference.strip():
        raise ExecutionPreflightError("raw record requires a trace_reference")
    if trace_reference.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", trace_reference):
        raise ExecutionPreflightError("raw record trace_reference must be relative or an opaque trace ID")
    return {
        "sample_id": sample_id,
        "metric": metric,
        "actual": actual,
        "trace_reference": trace_reference,
    }


def _sample_by_id(validated: ValidatedExecution, sample_id: str) -> Mapping[str, Any]:
    if not isinstance(validated, ValidatedExecution):
        raise TypeError("validated must be a ValidatedExecution")
    for sample in validated.records:
        if sample["sample_id"] == sample_id:
            return sample
    raise ExecutionPreflightError("sample_id is not present in the validated Dataset")


def _preference_actual(sample: Mapping[str, Any]) -> dict[str, Any]:
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
    return {
        "record_count": len(candidates),
        "records": [
            {
                "key": candidate.key,
                "value": candidate.value,
                "scope": candidate.scope,
                "is_temporary": candidate.is_temporary,
                "should_persist": candidate.should_persist,
                "explicitness": candidate.explicitness,
            }
            for candidate in candidates
        ],
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
) -> dict[str, Any]:
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
    return raw_record(
        sample_id=sample_id,
        metric=metric,
        actual=actual,
        trace_reference=f"{metric}:{sample_id}",
    )


def dispatch_safety_sample(
    validated: ValidatedExecution,
    sample_id: str,
    *,
    registry: HandlerRegistry,
    conn: Any,
    foreign_user_id: str | None = None,
) -> dict[str, Any]:
    """Run one Safety sample through real ingestion and observation boundaries.

    The caller supplies an already-isolated database and a production handler
    registry. A foreign-user control is an explicit runtime binding, never an
    adapter-created fixture. The function leaves raw persistence to
    ``write_raw_records`` after all samples have been observed.
    """
    sample = _sample_by_id(validated, sample_id)
    if sample["metric"] != "safety":
        raise ExecutionPreflightError("sample is not a safety metric")
    if not isinstance(registry, HandlerRegistry):
        raise ExecutionPreflightError("safety dispatch requires a handler registry")
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
        registry.route("event.ingest")(payload, context)
        observed = observe_safety_execution(
            conn,
            user_id=user_id,
            trace_id=trace_id,
            foreign_user_id=foreign_user_id,
        )
    except Exception as exc:
        raise ExecutionPreflightError("safety dispatch failed") from exc
    actual = {
        "critical_gate_bypass_count": observed["critical_gate_bypass_count"],
        "normal_memory_write_count": observed["normal_memory_write_count"],
        "audit_plaintext_leak_count": observed["audit_plaintext_leak_count"],
        "cross_user_violation_count": observed["cross_user_violation_count"],
    }
    return raw_record(
        sample_id=sample_id,
        metric="safety",
        actual=actual,
        trace_reference=observed["trace_reference"],
    )


def _validated_raw_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if set(record) != {"sample_id", "metric", "actual", "trace_reference"}:
        raise ExecutionPreflightError("raw record uses an unexpected top-level shape")
    return raw_record(
        sample_id=record["sample_id"],
        metric=record["metric"],
        actual=record["actual"],
        trace_reference=record["trace_reference"],
    )


def write_raw_records(
    validated: ValidatedExecution,
    raw_records: Iterable[Mapping[str, Any]],
) -> dict[str, Path]:
    """Write the four canonical raw files after complete, fail-closed validation.

    Callers supply observations returned by real production dispatch. This seam
    neither dispatches production code nor manufactures `actual` values. It
    validates every record before creating the new output root so an invalid
    batch cannot leave a partial canonical raw package behind.
    """
    if not isinstance(validated, ValidatedExecution):
        raise TypeError("validated must be a ValidatedExecution")
    expected_metric_by_id = {
        sample["sample_id"]: sample["metric"] for sample in validated.records
    }
    grouped: dict[str, list[dict[str, Any]]] = {metric: [] for metric in _METRICS}
    seen_sample_ids: set[str] = set()
    for source_record in raw_records:
        if not isinstance(source_record, Mapping):
            raise ExecutionPreflightError("raw record must be an object")
        record = _validated_raw_record(source_record)
        sample_id = record["sample_id"]
        if sample_id in seen_sample_ids:
            raise ExecutionPreflightError("raw sample_id must be unique")
        if expected_metric_by_id.get(sample_id) != record["metric"]:
            raise ExecutionPreflightError("raw sample_id and metric must match the Dataset")
        seen_sample_ids.add(sample_id)
        grouped[record["metric"]].append(record)
    if seen_sample_ids != set(expected_metric_by_id):
        raise ExecutionPreflightError("raw samples do not match the complete Dataset")
    if validated.request.output_root.exists():
        raise ExecutionPreflightError("output_root must not already exist")

    raw_root = validated.request.output_root / "raw"
    raw_root.mkdir(parents=True)
    written: dict[str, Path] = {}
    for metric, filename in _RAW_FILENAMES.items():
        path = raw_root / filename
        serialized = "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            for record in grouped[metric]
        )
        path.write_text(serialized, encoding="utf-8", newline="\n")
        written[metric] = path
    return written
