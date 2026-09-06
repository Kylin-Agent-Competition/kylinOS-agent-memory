"""L1 tests for D13D execution-adapter preflight; no formal execution occurs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import ast
import subprocess
import sys

import pytest

from types import MappingProxyType

from db import repositories as repo
import evaluation.d13d_execution_adapter as adapter
from evaluation.d13d_execution_adapter import (
    D13E_RAW_RESULT_SCHEMA_STATUS,
    OFFICIAL_D13E_TESTSET_SHA256,
    ExecutionPreflightError,
    ExecutionRequest,
    ObservedRawRecord,
    ValidatedRuntimeBinding,
    _record_to_line,
    build_runtime_binding,
    dispatch_safety_sample,
    dispatch_stateless_sample,
    validate_execution_request,
)

# Serializer-level aliases to the private construction seam / writer.  These are
# NOT provenance authority: only the formal orchestrator
# (adapter.dispatch_and_write_canonical) may produce the canonical package.
raw_record = adapter._raw_record
write_raw_records = adapter._write_raw_records


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TESTSET = REPOSITORY_ROOT / "evaluation" / "d13e" / "D13E_FORMAL_TESTSET_V1.jsonl"
TESTSET_SHA256 = OFFICIAL_D13E_TESTSET_SHA256
HEAD = "17dce3696066213b54e9dcbe6b87c4944cb41c8c"


def _git_runner(_root: Path, *args: str) -> str:
    if args == ("status", "--porcelain"):
        return ""
    if args == ("rev-parse", "HEAD"):
        return HEAD
    raise AssertionError(args)


def _request(tmp_path: Path, **overrides) -> ExecutionRequest:
    canonical_testset = tmp_path / "D13E_FORMAL_TESTSET_V1.jsonl"
    canonical_bytes = TESTSET.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(canonical_bytes).hexdigest() == TESTSET_SHA256
    canonical_testset.write_bytes(canonical_bytes)
    values = {
        "repository_root": REPOSITORY_ROOT,
        "tested_commit": HEAD,
        "testset_path": canonical_testset,
        "testset_sha256": TESTSET_SHA256,
        "execution_evidence_root": tmp_path / "evidence",
        "state_root": tmp_path / "state",
    }
    values.update(overrides)
    return ExecutionRequest(**values)


def test_valid_dataset_preflight_is_read_only_and_has_all_17_samples(tmp_path):
    request = _request(tmp_path)
    before = sorted(tmp_path.iterdir())
    validated = validate_execution_request(request, git_runner=_git_runner)
    assert len(validated.records) == 17
    assert before == sorted(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"tested_commit": "bad"}, "full lowercase Git SHA"),
        ({"tested_commit": "0" * 40}, "equal HEAD"),
        ({"testset_sha256": "0" * 64}, "must equal the approved"),
        ({"execution_evidence_root": REPOSITORY_ROOT / "generated"}, "overlap repository_root"),
    ],
)
def test_preflight_rejects_untrusted_identity_or_nonisolated_paths(tmp_path, overrides, message):
    with pytest.raises(ExecutionPreflightError, match=message):
        validate_execution_request(_request(tmp_path, **overrides), git_runner=_git_runner)


def test_preflight_rejects_dirty_worktree(tmp_path):
    def dirty_git(_root: Path, *args: str) -> str:
        return " M production.py" if args[0] == "status" else HEAD

    with pytest.raises(ExecutionPreflightError, match="worktree must be clean"):
        validate_execution_request(_request(tmp_path), git_runner=dirty_git)


def test_preflight_rejects_nested_isolation_roots(tmp_path):
    with pytest.raises(ExecutionPreflightError, match="must not overlap"):
        validate_execution_request(
            _request(tmp_path, state_root=tmp_path / "evidence" / "nested"),
            git_runner=_git_runner,
        )


def test_preflight_rejects_altered_dataset_even_when_caller_recomputes_sha(tmp_path):
    records = [json.loads(line) for line in TESTSET.read_text(encoding="utf-8").splitlines()]
    records[-1]["sample_id"] = records[0]["sample_id"]
    altered = tmp_path / "altered.jsonl"
    altered.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
    with pytest.raises(ExecutionPreflightError, match="must equal the approved D13E Dataset SHA-256"):
        validate_execution_request(
            _request(
                tmp_path,
                testset_path=altered,
                testset_sha256=hashlib.sha256(altered.read_bytes()).hexdigest(),
            ),
            git_runner=_git_runner,
        )


def test_preflight_rejects_missing_dataset_as_a_structured_error(tmp_path):
    with pytest.raises(ExecutionPreflightError, match="testset cannot be read"):
        validate_execution_request(
            _request(tmp_path, testset_path=tmp_path / "missing.jsonl"),
            git_runner=_git_runner,
        )


def _validate_altered_dataset(tmp_path, monkeypatch, content: str):
    altered = tmp_path / "altered.jsonl"
    altered.write_text(content, encoding="utf-8")
    altered_sha = hashlib.sha256(altered.read_bytes()).hexdigest()
    monkeypatch.setattr(adapter, "OFFICIAL_D13E_TESTSET_SHA256", altered_sha)
    return validate_execution_request(
        _request(tmp_path, testset_path=altered, testset_sha256=altered_sha),
        git_runner=_git_runner,
    )


def test_preflight_rejects_malformed_jsonl_after_identity_validation(tmp_path, monkeypatch):
    with pytest.raises(ExecutionPreflightError, match="line 1 is not JSON"):
        _validate_altered_dataset(tmp_path, monkeypatch, "not-json\n")


def test_preflight_rejects_unknown_metric_after_identity_validation(tmp_path, monkeypatch):
    records = [json.loads(line) for line in TESTSET.read_text(encoding="utf-8").splitlines()]
    records[0]["metric"] = "unknown"

    with pytest.raises(ExecutionPreflightError, match="metric is invalid"):
        _validate_altered_dataset(
            tmp_path,
            monkeypatch,
            "\n".join(json.dumps(record) for record in records),
        )


def test_preflight_rejects_wrong_metric_distribution_after_identity_validation(tmp_path, monkeypatch):
    records = [json.loads(line) for line in TESTSET.read_text(encoding="utf-8").splitlines()]
    records[0]["metric"] = "conflict"
    records[0]["sample_id"] = "d13e-conflict-005"
    records[0]["input"] = records[4]["input"]

    with pytest.raises(ExecutionPreflightError, match="metric distribution is invalid"):
        _validate_altered_dataset(
            tmp_path,
            monkeypatch,
            "\n".join(json.dumps(record) for record in records),
        )


@pytest.mark.parametrize("root_name", ["state_root", "execution_evidence_root"])
def test_preflight_rejects_existing_isolation_root(tmp_path, root_name):
    existing_root = tmp_path / root_name
    existing_root.mkdir()

    with pytest.raises(ExecutionPreflightError, match=f"{root_name} must not already exist"):
        validate_execution_request(
            _request(tmp_path, **{root_name: existing_root}),
            git_runner=_git_runner,
        )


@pytest.mark.parametrize("root_name", ["execution_evidence_root", "state_root"])
def test_preflight_rejects_relative_isolation_root(tmp_path, root_name):
    with pytest.raises(ExecutionPreflightError, match=f"{root_name} must be an absolute path"):
        validate_execution_request(
            _request(tmp_path, **{root_name: Path("relative-isolation-root")}),
            git_runner=_git_runner,
        )


def test_cli_reports_missing_dataset_as_structured_rejection(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "run_d13d_execution_adapter.py"),
            "--tested-commit",
            HEAD,
            "--testset",
            str(tmp_path / "missing.jsonl"),
            "--testset-sha256",
            TESTSET_SHA256,
            "--execution-evidence-root",
            str(tmp_path / "evidence"),
            "--state-root",
            str(tmp_path / "state"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert json.loads(completed.stdout) == {
        "status": "REJECTED",
        "reason": "testset cannot be read",
    }
    assert "Traceback" not in completed.stderr


def _dispatchable_stateless(validated):
    """Real dispatch receipts for the stateless Preference/Conflict samples."""
    return [
        dispatch_stateless_sample(validated, sample["sample_id"])
        for sample in validated.records
        if sample["metric"] in ("preference", "conflict")
    ]


def _write_synthetic_stateless_evidence(validated, records_meta):
    """Create evidence-backed stateless trace files for serializer-only tests."""
    for sample_id, metric, actual in records_meta:
        adapter._write_stateless_execution_receipt(
            validated,
            sample_id=sample_id,
            metric=metric,
            actual=actual,
            entrypoint="serializer-unit-test",
        )


def _synthetic_batch_for_serializer(validated):
    """Serializer/atomicity-only synthetic receipts (NOT canonical authority).

    These records and their evidence trace files exercise the private writer as
    a pure serializer (allowed by the review); they are never used to claim a
    real execution closure, and they cannot enter the canonical package because
    dispatch_and_write_canonical() never accepts external receipts.
    """
    actual_by_metric = {
        "preference": {
            "record_count": 1,
            "key": "k",
            "scope": "global",
            "is_temporary": False,
            "should_persist": True,
            "explicitness": "explicit",
        },
        "conflict": {"action": "defer", "winner_id": None, "reason_code": "same_tier"},
        "safety": {
            "critical_gate_bypass_count": 0,
            "normal_memory_write_count": 0,
            "audit_plaintext_leak_count": 0,
            "cross_user_violation_count": 0,
        },
        "forget": {
            "missed_target_items": 0,
            "wrongly_deleted_items": 0,
            "cross_user_violation_count": 0,
            "residual_after_realtime_query": 0,
            "residual_after_full_rebuild": 0,
        },
    }
    stateless_evidence = []
    records = []
    for sample in validated.records:
        metric = sample["metric"]
        sample_id = sample["sample_id"]
        actual = dict(actual_by_metric[metric])
        if metric in ("preference", "conflict"):
            stateless_evidence.append((sample_id, metric, actual))
            trace = f"dispatch/{sample_id}.json"
        elif metric == "safety":
            trace = "source-events:serializer-unit"
        else:
            trace = "traces/serializer-unit.jsonl"
        records.append(
            raw_record(
                sample_id=sample_id,
                metric=metric,
                actual=actual,
                trace_reference=trace,
                runtime_scope="serializer-unit",
            )
        )
    _write_synthetic_stateless_evidence(validated, stateless_evidence)
    return records


def test_raw_record_canonical_top_level_is_runner_contract():
    record = raw_record(
        sample_id="d13e-safety-001",
        metric="safety",
        actual={
            "critical_gate_bypass_count": 0,
            "normal_memory_write_count": 0,
            "audit_plaintext_leak_count": 0,
            "cross_user_violation_count": 0,
        },
        trace_reference="source-events:controlled-trace",
        runtime_scope="stateless:safety",
    )
    assert isinstance(record, ObservedRawRecord)
    assert type(record.actual) is MappingProxyType
    assert len(record.actual_digest) == 64
    assert set(record.as_canonical_mapping()) == {
        "sample_id",
        "metric",
        "actual",
        "trace_reference",
    }
    line = json.loads(_record_to_line(record))
    assert set(line) == {"sample_id", "metric", "actual", "trace_reference"}
    assert line["actual"] == dict(record.actual)


def test_raw_record_rejects_missing_trace_reference():
    with pytest.raises(ExecutionPreflightError, match="requires a trace_reference"):
        raw_record(
            sample_id="d13e-safety-001",
            metric="safety",
            actual={
                "critical_gate_bypass_count": 0,
                "normal_memory_write_count": 0,
                "audit_plaintext_leak_count": 0,
                "cross_user_violation_count": 0,
            },
            trace_reference="",
            runtime_scope="stateless:safety",
        )


def test_raw_record_rejects_empty_runtime_scope():
    with pytest.raises(ExecutionPreflightError, match="runtime scope"):
        raw_record(
            sample_id="d13e-safety-001",
            metric="safety",
            actual={
                "critical_gate_bypass_count": 0,
                "normal_memory_write_count": 0,
                "audit_plaintext_leak_count": 0,
                "cross_user_violation_count": 0,
            },
            trace_reference="source-events:controlled-trace",
            runtime_scope="",
        )


def test_raw_record_rejects_wrong_sample_trace_binding():
    with pytest.raises(ExecutionPreflightError, match="does not bind the dispatched sample"):
        raw_record(
            sample_id="d13e-pref-001",
            metric="preference",
            actual={"record_count": 1},
            trace_reference="dispatch/d13e-pref-002.json",
            runtime_scope="stateless:preference",
        )


@pytest.mark.parametrize(
    ("metric", "actual", "message"),
    [
        ("safety", {"critical_gate_bypass_count": 0}, "missing required fields"),
        ("forget", {"missed_target_items": 0}, "missing required fields"),
        (
            "safety",
            {
                "critical_gate_bypass_count": -1,
                "normal_memory_write_count": 0,
                "audit_plaintext_leak_count": 0,
                "cross_user_violation_count": 0,
            },
            "non-negative integer",
        ),
        ("preference", {"record_count": 1, "formal_result": "PASS"}, "forbidden"),
        (
            "preference",
            {"record_count": 1, "records": [{"key": "k"}]},
            "candidate schema",
        ),
    ],
)
def test_raw_record_rejects_incomplete_or_evaluation_shaped_actual(metric, actual, message):
    with pytest.raises(ExecutionPreflightError, match=message):
        raw_record(
            sample_id=f"d13e-{metric if metric != 'preference' else 'pref'}-001",
            metric=metric,
            actual=actual,
            trace_reference=(
                "dispatch/d13e-pref-001.json"
                if metric == "preference"
                else "source-events:controlled-trace"
            ),
            runtime_scope="stateless:test",
        )


def test_raw_writer_serializer_layout_is_canonical():
    # Pure serializer unit coverage: the private writer is the serializer of the
    # formal orchestration path, not by itself evidence of a real closure.
    record = raw_record(
        sample_id="d13e-forget-001",
        metric="forget",
        actual={
            "missed_target_items": 0,
            "wrongly_deleted_items": 0,
            "cross_user_violation_count": 0,
            "residual_after_realtime_query": 0,
            "residual_after_full_rebuild": 0,
        },
        trace_reference="traces/forget-001.jsonl",
        runtime_scope="serializer-unit",
    )
    line = json.loads(_record_to_line(record))
    assert set(line) == {"sample_id", "metric", "actual", "trace_reference"}
    assert line["actual"] == dict(record.actual)


def test_raw_writer_rejects_hand_built_raw_mapping(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    forged = {
        "sample_id": "d13e-pref-001",
        "metric": "preference",
        "actual": {"record_count": 1},
        "trace_reference": "dispatch/d13e-pref-001.json",
    }
    with pytest.raises(ExecutionPreflightError, match="ObservedRawRecord produced by real dispatch"):
        write_raw_records(validated, [forged])
    assert not validated.request.execution_evidence_root.exists()


def test_raw_writer_rejects_hand_constructed_plain_dict_actual(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    forged = ObservedRawRecord(
        sample_id="d13e-pref-001",
        metric="preference",
        actual={"record_count": 1},
        trace_reference="dispatch/d13e-pref-001.json",
        runtime_scope="stateless:preference",
        actual_digest="0" * 64,
    )
    with pytest.raises(ExecutionPreflightError, match="immutable dispatch snapshot"):
        write_raw_records(validated, [forged])


def test_receipt_actual_is_immutable_after_dispatch(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    record = dispatch_stateless_sample(validated, "d13e-pref-001")
    assert type(record.actual) is MappingProxyType
    with pytest.raises(TypeError):
        record.actual["gold"] = "tampered"  # type: ignore[index]


def test_raw_writer_revalidates_actual_before_writing(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    forged = ObservedRawRecord(
        sample_id="d13e-pref-001",
        metric="preference",
        actual=MappingProxyType({"record_count": 1, "gold": "tampered"}),
        trace_reference="dispatch/d13e-pref-001.json",
        runtime_scope="stateless:preference",
        actual_digest="0" * 64,
    )
    with pytest.raises(ExecutionPreflightError, match="forbidden"):
        write_raw_records(validated, [forged])
    assert not validated.request.execution_evidence_root.exists()


def test_raw_writer_rejects_wrong_sample_trace_reference(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    forged = ObservedRawRecord(
        sample_id="d13e-pref-001",
        metric="preference",
        actual=MappingProxyType({"record_count": 1}),
        trace_reference="dispatch/d13e-pref-002.json",
        runtime_scope="stateless:preference",
        actual_digest=adapter._actual_digest({"record_count": 1}),
    )
    with pytest.raises(ExecutionPreflightError, match="does not bind the dispatched sample"):
        write_raw_records(validated, [forged])
    assert not validated.request.execution_evidence_root.exists()


def test_raw_writer_rejects_stateless_record_without_evidence_trace(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    record = raw_record(
        sample_id="d13e-pref-001",
        metric="preference",
        actual={"record_count": 1},
        trace_reference="dispatch/d13e-pref-001.json",
        runtime_scope="stateless:preference",
    )
    with pytest.raises(ExecutionPreflightError, match="does not exist under evidence_root"):
        write_raw_records(validated, [record])
    assert not validated.request.execution_evidence_root.exists()


def test_raw_writer_rejects_stateless_trace_of_another_commit(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    digest = adapter._actual_digest({"record_count": 1})
    trace_path = validated.request.execution_evidence_root / "dispatch" / "d13e-pref-001.json"
    trace_path.parent.mkdir(parents=True)
    trace_path.write_text(
        json.dumps(
            {
                "receipt_version": "d13d-execution-receipt/v1",
                "sample_id": "d13e-pref-001",
                "metric": "preference",
                "tested_commit": "0" * 40,
                "actual_digest": digest,
                "utc": "2026-09-06T00:00:00Z",
                "entrypoint": "other-commit",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    record = raw_record(
        sample_id="d13e-pref-001",
        metric="preference",
        actual={"record_count": 1},
        trace_reference="dispatch/d13e-pref-001.json",
        runtime_scope="stateless:preference",
    )
    with pytest.raises(ExecutionPreflightError, match="different tested_commit"):
        write_raw_records(validated, [record])
    assert not (validated.request.execution_evidence_root / "raw").exists()


def test_raw_writer_fails_closed_when_dispatch_is_not_complete(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    stateless = _dispatchable_stateless(validated)
    assert len(stateless) == 8
    with pytest.raises(ExecutionPreflightError, match="raw samples do not match"):
        write_raw_records(validated, stateless)
    assert not (validated.request.execution_evidence_root / "raw").exists()


def test_raw_writer_serializer_full_batch_layout_is_four_files(tmp_path):
    # Serializer-only positive layout: proves the canonical JSONL shape and the
    # atomic temp->rename path, not a real execution closure.
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    batch = _synthetic_batch_for_serializer(validated)
    assert len(batch) == 17
    written = write_raw_records(validated, batch)
    assert set(written) == {"preference", "conflict", "safety", "forget"}
    expected_lines = {"preference": 4, "conflict": 4, "safety": 4, "forget": 5}
    for metric, path in written.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) == expected_lines[metric]


def test_raw_writer_never_leaves_partial_output_on_io_failure(tmp_path, monkeypatch):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    batch = _synthetic_batch_for_serializer(validated)
    calls = {"count": 0}

    def flaky_write(_path, _content):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("injected io failure")

    monkeypatch.setattr(adapter, "_write_text_file", flaky_write)
    with pytest.raises(OSError, match="injected io failure"):
        write_raw_records(validated, batch)
    # dispatch receipts already created the execution evidence root; the raw
    # package itself must never appear as a partial canonical dir.
    leftovers = [p for p in validated.request.execution_evidence_root.glob(".*.tmp-*")]
    assert leftovers == []
    assert not (validated.request.execution_evidence_root / "raw").exists()


def test_canonical_orchestrator_is_blocked_and_never_accepts_external_receipts(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    with pytest.raises(ExecutionPreflightError, match="forget requires an external state binding"):
        adapter.dispatch_and_write_canonical(validated)
    assert not validated.request.execution_evidence_root.exists()


def test_dispatch_stateless_preference_projects_top_level_fields(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)

    record = dispatch_stateless_sample(validated, "d13e-pref-001")

    assert record.sample_id == "d13e-pref-001"
    assert record.metric == "preference"
    assert type(record.actual) is MappingProxyType
    assert "records" not in record.actual
    assert record.actual == {
        "record_count": 1,
        "key": "response.language",
        "scope": "global",
        "is_temporary": False,
        "should_persist": True,
        "explicitness": "explicit",
    }
    assert record.trace_reference == "dispatch/d13e-pref-001.json"
    assert record.runtime_scope == "stateless:preference"
    receipt = json.loads(
        (validated.request.execution_evidence_root / "dispatch" / "d13e-pref-001.json")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert receipt["sample_id"] == "d13e-pref-001"
    assert receipt["metric"] == "preference"
    assert receipt["tested_commit"] == HEAD
    assert receipt["actual_digest"] == record.actual_digest


def test_dispatch_stateless_conflict_calls_the_real_policy(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)

    record = dispatch_stateless_sample(validated, "d13e-conflict-001")

    assert record.sample_id == "d13e-conflict-001"
    assert record.metric == "conflict"
    assert record.actual == {
        "action": "keep_left",
        "winner_id": "d13e-c-001-left",
        "reason_code": "evidence_tier_priority",
    }
    assert record.trace_reference == "dispatch/d13e-conflict-001.json"
    assert record.runtime_scope == "stateless:conflict"


def test_dispatch_stateless_rejects_stateful_metrics_without_an_environment_binding(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)

    with pytest.raises(ExecutionPreflightError, match="isolated runtime binding"):
        dispatch_stateless_sample(validated, "d13e-forget-001")


def test_validated_dataset_records_are_recursively_immutable(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    by_id = {sample["sample_id"]: sample for sample in validated.records}
    pref = by_id["d13e-pref-001"]
    conflict = by_id["d13e-conflict-001"]
    forget = by_id["d13e-forget-001"]
    with pytest.raises(TypeError):
        pref["sample_id"] = "altered"  # type: ignore[index]
    with pytest.raises(TypeError):
        pref["input"]["user_text"] = "altered after SHA validation"  # type: ignore[index]
    with pytest.raises(TypeError):
        conflict["input"]["left"]["evidence_tier"] = "altered"  # type: ignore[index]
    with pytest.raises(TypeError):
        forget["input"]["target_selector"]["knowledge_id"] = "altered"  # type: ignore[index]
    # Dispatch still observes the immutable official input.
    record = dispatch_stateless_sample(validated, "d13e-pref-001")
    assert record.actual["key"] == "response.language"


@pytest.fixture()
def safety_environment(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    binding = build_runtime_binding(validated)
    with binding.engine.begin() as conn:
        repo.insert_memory_entry(
            conn,
            user_id="user_d13e_beta",
            entry_type="knowledge",
            content={"value": "controlled foreign probe"},
        )
    return validated, binding


def test_runtime_binding_lives_under_the_validated_state_root(safety_environment):
    validated, binding = safety_environment
    assert binding.db_path.resolve().is_relative_to(validated.request.state_root.resolve())
    assert binding.db_path.exists()
    assert binding.binding_id.startswith("d13d-runtime-binding/v1:")
    assert len(binding.run_token_sha256) == 64
    assert callable(binding.event_ingest_handler)


def test_runtime_binding_cannot_reuse_an_existing_database(safety_environment):
    validated, _binding = safety_environment
    with pytest.raises(ExecutionPreflightError, match="must not already exist"):
        build_runtime_binding(validated)


def test_dispatch_safety_uses_real_event_ingest_and_observer(safety_environment):
    validated, binding = safety_environment

    record = dispatch_safety_sample(
        validated,
        "d13e-safety-001",
        binding=binding,
        foreign_user_id="user_d13e_beta",
    )

    assert record.sample_id == "d13e-safety-001"
    assert record.metric == "safety"
    assert record.actual == {
        "critical_gate_bypass_count": 0,
        "normal_memory_write_count": 0,
        "audit_plaintext_leak_count": 0,
        "cross_user_violation_count": 0,
    }
    assert record.trace_reference == "source-events:d13d-safety-d13e-safety-001"
    assert record.runtime_scope == binding.binding_id


def test_dispatch_safety_cross_user_sample_uses_real_user_scoped_probe(safety_environment):
    validated, binding = safety_environment

    record = dispatch_safety_sample(validated, "d13e-safety-003", binding=binding)

    assert record.actual["cross_user_violation_count"] == 0
    assert record.trace_reference == "source-events:d13d-safety-d13e-safety-003"


def test_dispatch_safety_fails_closed_without_the_foreign_control(safety_environment):
    validated, binding = safety_environment
    with binding.engine.begin() as conn:
        conn.execute(repo.memory_entries.delete())
    with pytest.raises(ExecutionPreflightError, match="safety dispatch failed"):
        dispatch_safety_sample(
            validated,
            "d13e-safety-001",
            binding=binding,
            foreign_user_id="user_d13e_beta",
        )


def test_dispatch_safety_fails_closed_when_ingest_handler_replaced(safety_environment):
    validated, binding = safety_environment
    calls = {"count": 0}

    def fake_ingest(_payload, _ctx):
        calls["count"] += 1
        return {}

    binding.registry.register("event.ingest", fake_ingest)
    with pytest.raises(ExecutionPreflightError, match="handler was replaced"):
        dispatch_safety_sample(
            validated,
            "d13e-safety-001",
            binding=binding,
            foreign_user_id="user_d13e_beta",
        )
    assert calls["count"] == 0


def test_dispatch_safety_fails_closed_when_ingest_handler_unregistered(safety_environment):
    validated, binding = safety_environment
    binding.registry.unregister("event.ingest")
    with pytest.raises(ExecutionPreflightError, match="replaced or unregistered"):
        dispatch_safety_sample(
            validated,
            "d13e-safety-001",
            binding=binding,
            foreign_user_id="user_d13e_beta",
        )


def _other_binding(tmp_path):
    (tmp_path / "other").mkdir()
    other = validate_execution_request(_request(tmp_path / "other"), git_runner=_git_runner)
    return build_runtime_binding(other)


def test_dispatch_safety_rejects_binding_outside_validated_state_root(safety_environment, tmp_path):
    validated, binding = safety_environment
    forged = ValidatedRuntimeBinding(
        validated=validated,
        binding_id="forged",
        db_path=tmp_path / "outside-state-root.db",
        engine=binding.engine,
        registry=binding.registry,
        event_ingest_handler=binding.event_ingest_handler,
        run_token_sha256=binding.run_token_sha256,
    )
    with pytest.raises(ExecutionPreflightError, match="validated state_root"):
        dispatch_safety_sample(
            validated,
            "d13e-safety-001",
            binding=forged,
            foreign_user_id="user_d13e_beta",
        )


def test_dispatch_safety_rejects_binding_from_a_different_validated_execution(
    safety_environment, tmp_path
):
    validated, _binding = safety_environment
    other_binding = _other_binding(tmp_path)
    with pytest.raises(ExecutionPreflightError, match="not created from this validated execution"):
        dispatch_safety_sample(
            validated,
            "d13e-safety-001",
            binding=other_binding,
            foreign_user_id="user_d13e_beta",
        )


def test_dispatch_safety_rejects_engine_pointing_to_another_database(
    safety_environment, tmp_path
):
    validated, binding = safety_environment
    other_binding = _other_binding(tmp_path)
    forged = ValidatedRuntimeBinding(
        validated=validated,
        binding_id="forged",
        db_path=binding.db_path,
        engine=other_binding.engine,
        registry=other_binding.registry,
        event_ingest_handler=other_binding.event_ingest_handler,
        run_token_sha256=other_binding.run_token_sha256,
    )
    with pytest.raises(ExecutionPreflightError, match="not connected to binding.db_path"):
        dispatch_safety_sample(
            validated,
            "d13e-safety-001",
            binding=forged,
            foreign_user_id="user_d13e_beta",
        )


def test_dispatch_safety_rejects_registry_bound_to_another_engine(safety_environment, tmp_path):
    validated, binding = safety_environment
    other_binding = _other_binding(tmp_path)
    forged = ValidatedRuntimeBinding(
        validated=validated,
        binding_id="forged",
        db_path=binding.db_path,
        engine=binding.engine,
        registry=other_binding.registry,
        event_ingest_handler=binding.event_ingest_handler,
        run_token_sha256=binding.run_token_sha256,
    )
    with pytest.raises(ExecutionPreflightError, match="registry is not bound to the same engine/run"):
        dispatch_safety_sample(
            validated,
            "d13e-safety-001",
            binding=forged,
            foreign_user_id="user_d13e_beta",
        )


def test_dispatch_safety_requires_an_explicit_runtime_binding(safety_environment):
    validated, _binding = safety_environment
    with pytest.raises(ExecutionPreflightError, match="ValidatedRuntimeBinding"):
        dispatch_safety_sample(
            validated,
            "d13e-safety-001",
            binding=None,  # type: ignore[arg-type]
            foreign_user_id="user_d13e_beta",
        )


def test_adapter_module_does_not_import_evaluator_owned_artifacts():
    source = (REPOSITORY_ROOT / "memory-service" / "evaluation" / "d13d_execution_adapter.py").read_text(
        encoding="utf-8"
    )
    imports = [
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    ] + [
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    ]
    assert all(not name.startswith("evaluation.d13e") for name in imports)


RUNNER_SCRIPT = REPOSITORY_ROOT / "scripts" / "run_d13e_formal_eval.py"
GOLD_FILE = REPOSITORY_ROOT / "evaluation" / "d13e" / "D13E_GOLD_V1.jsonl"


def _load_runner_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("d13e_formal_eval_runner_for_adapter", RUNNER_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _gold_expected_by_sample():
    expected = {}
    for line in GOLD_FILE.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        expected[str(record["sample_id"])] = record["expected"]
    return expected


MUST_MATCH_TRUE = {
    "d13e-pref-001",
    "d13e-pref-002",
    "d13e-pref-004",
    "d13e-conflict-001",
    "d13e-conflict-002",
    "d13e-conflict-003",
    "d13e-conflict-004",
}
# pref-003: the current provider extracts zero candidates while the frozen D13E
# Gold expects one tool-selection preference.  This is a registered observation
# gap (Dataset/pipeline alignment), not a schema blocker; the Runner correctly
# computes it as False and we pin that outcome so it is not silently treated as
# complete.
KNOWN_OBSERVATION_GAP_FALSE = {"d13e-pref-003"}
SAFETY_CROSS_TRACK_BLOCKED = {
    "d13e-safety-001",
    "d13e-safety-002",
    "d13e-safety-003",
    "d13e-safety-004",
}


def test_adapter_raw_feed_runner_contract_has_explicit_per_sample_expectations(
    tmp_path, safety_environment
):
    """Adapter raw -> frozen Runner contract with explicit per-sample outcomes.

    Gold is read here only to drive the Runner's per-sample contract (the same
    way formal Gate 9 consumes raw); it is never used to generate ``actual``.
    Preference/Conflict samples that must satisfy the contract are asserted
    True, the registered observation gap is asserted False, and Safety samples
    are asserted shape-legal but explicitly NOT treated as complete because the
    sensitivity/admission/operation projection contract is still pending a D13E
    Runner/Gold decision (schema status CANDIDATE_PENDING_D13E_REVIEW).
    """
    validated, binding = safety_environment
    assert D13E_RAW_RESULT_SCHEMA_STATUS == "CANDIDATE_PENDING_D13E_REVIEW"
    runner = _load_runner_module()
    gold = _gold_expected_by_sample()
    results = {}
    for sample in validated.records:
        if sample["metric"] == "forget":
            continue
        sample_id = sample["sample_id"]
        metric = sample["metric"]
        if metric == "safety":
            if "text" in sample["input"]:
                record = dispatch_safety_sample(
                    validated, sample_id, binding=binding, foreign_user_id="user_d13e_beta"
                )
            else:
                record = dispatch_safety_sample(validated, sample_id, binding=binding)
        else:
            record = dispatch_stateless_sample(validated, sample_id)
        results[sample_id] = runner._matches_metric_contract(
            metric, gold[sample_id], dict(record.actual)
        )
    for sample_id in MUST_MATCH_TRUE:
        assert results[sample_id] is True, f"{sample_id} must satisfy the Runner contract"
    for sample_id in KNOWN_OBSERVATION_GAP_FALSE:
        assert results[sample_id] is False, (
            f"{sample_id} is a registered observation gap and must not be treated as complete"
        )
    for sample_id in SAFETY_CROSS_TRACK_BLOCKED:
        assert isinstance(results[sample_id], bool)
        # No schema-shape exception, but Safety raw is NOT Gate-9 complete while
        # the cross-track projection contract is pending D13E review.


RAW_FILENAMES = {
    "preference": "preference_raw.jsonl",
    "conflict": "conflict_raw.jsonl",
    "safety": "safety_raw.jsonl",
    "forget": "forget_raw.jsonl",
}


def test_canonical_package_lives_under_execution_evidence_root_and_passes_runner_resolver(tmp_path):
    """BLOCKER lifecycle: raw + dispatch receipts share ONE evidence root and the
    resulting raw descriptors satisfy the formal Runner's evidence-root path gate
    (raw_result_files.*.file resolves inside the D13D unique evidence directory)."""
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    root = validated.request.execution_evidence_root
    batch = _synthetic_batch_for_serializer(validated)
    written = write_raw_records(validated, batch)
    assert {metric: path.relative_to(root) for metric, path in written.items()} == {
        metric: Path("raw") / filename for metric, filename in RAW_FILENAMES.items()
    }
    runner = _load_runner_module()
    for metric, filename in RAW_FILENAMES.items():
        resolved = runner._relative_file(root, f"raw/{filename}", f"raw_result_files.{metric}.file")
        assert resolved == written[metric].resolve()
        assert resolved.is_relative_to(root.resolve())
        assert resolved.exists()


def test_stateless_receipt_is_exclusive_and_never_silently_overwritten(tmp_path):
    """MEDIUM-1: a repeated dispatch of the same sample must fail closed instead of
    silently overwriting the first execution receipt."""
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    first = dispatch_stateless_sample(validated, "d13e-pref-001")
    trace_path = (
        validated.request.execution_evidence_root / "dispatch" / "d13e-pref-001.json"
    )
    assert trace_path.exists()
    before = trace_path.read_bytes()
    with pytest.raises(ExecutionPreflightError, match="must not be overwritten"):
        dispatch_stateless_sample(validated, "d13e-pref-001")
    assert trace_path.read_bytes() == before
    assert first.trace_reference == "dispatch/d13e-pref-001.json"
