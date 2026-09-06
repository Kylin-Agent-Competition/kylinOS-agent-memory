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

@pytest.fixture(autouse=True)
def _d13d_patch_git_ancestry(monkeypatch):
    """CI checkout 为 fetch-depth=1（浅克隆），无完整历史。

    生产 preflight 仍走真实 git merge-base；测试注入 ancestry 结果以保证在
    Actions 浅克隆下也可执行（not-ancestor 用例单独覆盖为 False）。
    """
    monkeypatch.setattr(adapter, "_is_ancestor", lambda *a, **k: True)
from evaluation.d13d_execution_adapter import (
    D13E_RAW_RESULT_SCHEMA_STATUS,
    OFFICIAL_D13E_TESTSET_SHA256,
    ExecutionPreflightError,
    ExecutionRequest,
    ObservedRawRecord,
    ValidatedRuntimeBinding,
    _record_to_line,
    build_runtime_binding,
    dispatch_forget_sample,
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


def _synthetic_batch_for_serializer(validated):
    """Serializer/atomicity-only synthetic receipts (NOT canonical authority).

    These records and their matching evidence-root execution receipts exercise
    the private writer as a pure serializer (allowed by the review); they are
    never used to claim a real execution closure, and they cannot enter the
    canonical package because dispatch_and_write_canonical() never accepts
    external receipts.  A synthetic receipt is still created for every metric
    (including stateful Safety/Forget) so the writer's uniform provenance gate
    is exercised for serializer-level tests.
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
            "forget_mode": "session",
            "missed_target_items": 0,
            "wrongly_deleted_items": 0,
            "cross_user_violation_count": 0,
            "residual_after_realtime_query": 0,
            "residual_after_full_rebuild": 0,
        },
    }
    records = []
    for sample in validated.records:
        metric = sample["metric"]
        sample_id = sample["sample_id"]
        actual = dict(actual_by_metric[metric])
        if metric in ("preference", "conflict"):
            trace = f"dispatch/{sample_id}.json"
        elif metric == "safety":
            trace = "source-events:serializer-unit"
        else:
            trace = f"traces/{sample_id}.jsonl"
        runtime_scope = "serializer-unit"
        adapter._write_execution_receipt(
            validated,
            sample_id=sample_id,
            metric=metric,
            actual=actual,
            entrypoint="serializer-unit-test",
            runtime_scope=runtime_scope,
            trace_reference=trace,
        )
        records.append(
            raw_record(
                sample_id=sample_id,
                metric=metric,
                actual=actual,
                trace_reference=trace,
                runtime_scope=runtime_scope,
            )
        )
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
            "forget_mode": "single_item",
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
    with pytest.raises(ExecutionPreflightError, match="execution receipt does not exist"):
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
    # #162 consumer：四 hard-zero counter 来自真实 observer；sensitivity/admission
    # 来自真实 persisted source_events（P2-A 裁定后连字符云 Key 判 critical/reject）。
    assert {
        "critical_gate_bypass_count": record.actual["critical_gate_bypass_count"],
        "normal_memory_write_count": record.actual["normal_memory_write_count"],
        "audit_plaintext_leak_count": record.actual["audit_plaintext_leak_count"],
        "cross_user_violation_count": record.actual["cross_user_violation_count"],
    } == {
        "critical_gate_bypass_count": 0,
        "normal_memory_write_count": 0,
        "audit_plaintext_leak_count": 0,
        "cross_user_violation_count": 0,
    }
    assert record.actual["sensitivity"] == "critical"
    assert record.actual["admission"] == "reject"
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


def test_runtime_binding_registers_and_freezes_forget_handlers(safety_environment):
    """P2-B：validation profile 显式注册真实 forget.preview/forget.execute 并冻结身份。"""
    validated, binding = safety_environment
    assert callable(binding.forget_preview_handler)
    assert callable(binding.forget_execute_handler)
    assert binding.registry.route("forget.preview") is binding.forget_preview_handler
    assert binding.registry.route("forget.execute") is binding.forget_execute_handler


def test_runtime_binding_fails_closed_when_forget_handler_unregistered(safety_environment):
    """P2-B：替换/注销 forget handler 后任何 dispatch（含 safety）必须 fail-closed。"""
    validated, binding = safety_environment
    binding.registry.unregister("forget.preview")
    with pytest.raises(ExecutionPreflightError, match="replaced or unregistered"):
        dispatch_safety_sample(
            validated,
            "d13e-safety-001",
            binding=binding,
            foreign_user_id="user_d13e_beta",
        )


def _prepared_forget_env(tmp_path, *, profile="d13d-validation-profile-v2"):
    """构造 R5 sealed source + v2 artifact + 5 个 restored runtime bindings。"""
    import json
    src, sha = _make_sealed_source(tmp_path)
    art = _write_v2_artifact(tmp_path, src, sha)
    data = json.loads(art.read_text(encoding="utf-8"))
    data["retrieval_profile"] = profile
    from evaluation.d13d_forget_state_binding import compute_artifact_sha256
    data["artifact_sha256"] = compute_artifact_sha256(data)
    art.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    validated = validate_execution_request(
        _request(tmp_path, binding_artifact_path=art), git_runner=_git_runner
    )
    bindings = adapter.prepare_forget_runtime_bindings(validated, artifact_path=art)
    return validated, art, bindings


def test_forget_dispatch_requires_matching_sample_binding(safety_environment):
    """R6：dispatch 的 sample 必须等于 binding.sample_id（缺省/错配 fail-closed）。"""
    validated, binding = safety_environment
    with pytest.raises(ExecutionPreflightError, match="sample_id does not match"):
        dispatch_forget_sample(validated, "d13e-forget-001", binding=binding)


def test_forget_dispatch_rejects_wrong_sample_binding(tmp_path):
    """R6/F13：binding 为 d13e-forget-001，dispatch d13e-forget-002 → fail-closed。"""
    validated, _art, bindings = _prepared_forget_env(tmp_path)
    with pytest.raises(ExecutionPreflightError, match="sample_id does not match"):
        dispatch_forget_sample(
            validated, "d13e-forget-002", binding=bindings["d13e-forget-001"]
        )


def test_forget_dispatch_fails_closed_when_retrieval_profile_not_approved(tmp_path):
    """R8/F18：retrieval_profile 不在 closed allowlist → preview 前 fail-closed。"""
    validated, _art, bindings = _prepared_forget_env(
        tmp_path, profile="unknown-profile-v9"
    )
    with pytest.raises(ExecutionPreflightError, match="no approved retrieval observation profile"):
        dispatch_forget_sample(
            validated, "d13e-forget-001", binding=bindings["d13e-forget-001"]
        )


def test_forget_dispatch_fails_closed_when_forget_handler_unregistered(tmp_path):
    """R6/F19：forget.execute 被注销后 dispatch 必须 fail-closed（binding 身份冻结）。"""
    validated, _art, bindings = _prepared_forget_env(tmp_path)
    binding = bindings["d13e-forget-001"]
    binding.registry.unregister("forget.execute")
    with pytest.raises(ExecutionPreflightError, match="replaced or unregistered"):
        dispatch_forget_sample(validated, "d13e-forget-001", binding=binding)


def test_safety_projection_does_not_swallow_real_cross_user_violation():
    """#162 §5.2：观测成功但发现安全违规 → 写真实 counter，adapter 不吞、不代 Runner 判 FAIL。"""
    actual = adapter._project_safety_actual(
        sample_id="d13e-safety-003",
        sample_input={"operation": "read"},
        observed={
            "critical_gate_bypass_count": 0,
            "normal_memory_write_count": 0,
            "audit_plaintext_leak_count": 0,
            "cross_user_violation_count": 1,
        },
        conn=None,
        user_id="user_d13e_alpha",
        trace_id="t",
    )
    assert actual["cross_user_violation_count"] == 1
    assert actual["admission"] == "allow"  # 越界返回的观测事实，非固定 reject
    assert actual["operation"] == "read"


def test_safety_projection_read_uses_dataset_operation_input():
    """safety-003：operation 必须来自 SHA 验证 Dataset input（read），不读 Gold。"""
    actual = adapter._project_safety_actual(
        sample_id="d13e-safety-003",
        sample_input={"operation": "read"},
        observed={
            "critical_gate_bypass_count": 0,
            "normal_memory_write_count": 0,
            "audit_plaintext_leak_count": 0,
            "cross_user_violation_count": 0,
        },
        conn=None,
        user_id="user_d13e_alpha",
        trace_id="t",
    )
    assert actual["operation"] == "read"
    assert actual["admission"] == "reject"


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
    "d13e-pref-003",
    "d13e-pref-004",
    "d13e-conflict-001",
    "d13e-conflict-002",
    "d13e-conflict-003",
    "d13e-conflict-004",
    "d13e-safety-001",
    "d13e-safety-002",
    "d13e-safety-003",
    "d13e-safety-004",
}
# pref-003: closed by #161 production fix.
# safety-001..004: closed — actual projects persisted sensitivity/admission
# (001/002), operation/read-derived admission (003), real hard-zero counters
# (004).  Safety-001 detector gap closed by A-track hyphenated cloud-key rule
# (E 授权裁定 P2-A).  No registered observation gaps remain.
KNOWN_OBSERVATION_GAP_FALSE: set[str] = set()


def test_adapter_raw_feed_runner_contract_has_explicit_per_sample_expectations(
    tmp_path, safety_environment
):
    """Adapter raw -> frozen Runner contract with explicit per-sample outcomes.

    Gold is read here only to drive the Runner's per-sample contract (the same
    way formal Gate 9 consumes raw); it is never used to generate ``actual``.
    Preference/Conflict and Safety samples that must satisfy the contract are
    asserted True; no registered observation gaps remain (Safety-001 detector
    gap closed by the hyphenated cloud-key rule under E-authorized P2-A ruling).
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


def test_forget_schema_projects_forget_mode_and_passes_runner_contract(tmp_path):
    """BLOCKER-1: forget_mode is part of the adapter schema (value from the
    validated Dataset input, not Gold) and satisfies the frozen Runner contract
    for all five forget modes when counters are zero."""
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    runner = _load_runner_module()
    gold = _gold_expected_by_sample()
    counters = {
        "missed_target_items": 0,
        "wrongly_deleted_items": 0,
        "cross_user_violation_count": 0,
        "residual_after_realtime_query": 0,
        "residual_after_full_rebuild": 0,
    }
    modes = []
    for sample in validated.records:
        if sample["metric"] != "forget":
            continue
        sample_id = sample["sample_id"]
        mode = sample["input"]["forget_mode"]
        modes.append(mode)
        actual = {"forget_mode": mode, **counters}
        record = raw_record(
            sample_id=sample_id,
            metric="forget",
            actual=actual,
            trace_reference=f"traces/{sample_id}.jsonl",
            runtime_scope="serializer-unit",
        )
        assert record.actual["forget_mode"] == mode
        result = runner._matches_metric_contract("forget", gold[sample_id], dict(record.actual))
        assert result is True, f"{sample_id} forget_mode projection must satisfy the Runner contract"
    assert sorted(modes) == ["full_reset", "session", "single_item", "time_window", "topic"]


def test_forget_actual_requires_and_validates_forget_mode():
    counters = {
        "missed_target_items": 0,
        "wrongly_deleted_items": 0,
        "cross_user_violation_count": 0,
        "residual_after_realtime_query": 0,
        "residual_after_full_rebuild": 0,
    }
    with pytest.raises(ExecutionPreflightError, match="missing required fields"):
        raw_record(
            sample_id="d13e-forget-001",
            metric="forget",
            actual=dict(counters),
            trace_reference="traces/forget-001.jsonl",
            runtime_scope="serializer-unit",
        )
    with pytest.raises(ExecutionPreflightError, match="frozen forget modes"):
        raw_record(
            sample_id="d13e-forget-001",
            metric="forget",
            actual={"forget_mode": "made_up_mode", **counters},
            trace_reference="traces/forget-001.jsonl",
            runtime_scope="serializer-unit",
        )


def test_raw_writer_rejects_stateful_safety_record_without_receipt(tmp_path):
    """HIGH: stateful Safety provenance must also be evidence-root backed; a
    hand-constructed Safety receipt without its execution receipt is rejected."""
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
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
        runtime_scope="serializer-unit",
    )
    with pytest.raises(ExecutionPreflightError, match="execution receipt does not exist"):
        write_raw_records(validated, [record])
    assert not (validated.request.execution_evidence_root / "raw").exists()

def _make_sealed_source(tmp_path):
    import hashlib
    from db.engine import create_db_engine, init_schema
    src = tmp_path / "source.db"
    engine = create_db_engine(str(src))
    init_schema(engine)
    engine.dispose()
    return src, hashlib.sha256(src.read_bytes()).hexdigest()


def _write_v2_artifact(tmp_path, source_path, source_sha, *, sp=None, minc=None):
    import json
    from evaluation.d13d_forget_state_binding import (
        BINDING_VERSION_V2,
        compute_artifact_sha256,
    )
    sp = sp or "dc58e83479d718c8e3fbbbbb5d3b3f046f651973"
    v1 = json.loads(
        (REPOSITORY_ROOT / "evaluation" / "d13e" / "D13D_FORGET_STATE_BINDING_V1.json")
        .read_text(encoding="utf-8")
    )
    art = {k: v1[k] for k in (
        "owner", "approved_by", "approval_reference", "environment_id",
        "vm_snapshot", "retrieval_profile", "created_at_utc", "created_by",
        "samples",
    )}
    art["binding_version"] = BINDING_VERSION_V2
    art["state_preparation_commit"] = sp
    art["execution_compatibility"] = {
        "minimum_commit": minc or sp,
        "policy": "descendant-and-contract-compatible",
    }
    art["source_state"] = {
        "state_root": str(source_path.parent),
        "sealed_db_path": str(source_path),
        "sealed_db_sha256": source_sha,
        "db_size_bytes": source_path.stat().st_size,
        "sqlite_schema_fingerprint": adapter._sqlite_schema_fingerprint(source_path),
        "prepared_on_vm_snapshot": "d14d-clean-base-20260906-r2",
        "prepared_at_utc": "2026-09-06T00:00:00Z",
    }
    art["artifact_sha256"] = compute_artifact_sha256(art)
    out = tmp_path / "binding_v2.json"
    out.write_text(json.dumps(art, ensure_ascii=False), encoding="utf-8")
    return out


def test_prepare_forget_runtime_bindings_creates_five_fresh_clones(tmp_path):
    src, sha = _make_sealed_source(tmp_path)
    art = _write_v2_artifact(tmp_path, src, sha)
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    bindings = adapter.prepare_forget_runtime_bindings(validated, artifact_path=art)
    assert set(bindings) == set(adapter.FORGET_SAMPLE_MODES)
    for sample_id, binding in bindings.items():
        assert binding.sample_id == sample_id
        assert binding.runtime_db_initial_sha256 == sha
        assert binding.source_db_sha256 == sha
        assert binding.state_preparation_commit
        assert binding.binding_artifact_sha256
        assert binding.db_path.exists()
        assert binding.db_path.resolve().is_relative_to(validated.request.state_root.resolve())
        adapter._validate_binding(binding, validated)


def test_prepare_rejects_source_db_sha_mismatch(tmp_path):
    src, sha = _make_sealed_source(tmp_path)
    art = _write_v2_artifact(tmp_path, src, sha)
    data = json.loads(art.read_text(encoding="utf-8"))
    data["source_state"]["sealed_db_sha256"] = "0" * 64
    from evaluation.d13d_forget_state_binding import compute_artifact_sha256
    data["artifact_sha256"] = compute_artifact_sha256(data)
    art.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    with pytest.raises(ExecutionPreflightError, match="SHA-256 does not match"):
        adapter.prepare_forget_runtime_bindings(validated, artifact_path=art)


def test_prepare_rejects_state_prep_not_ancestor(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "_is_ancestor", lambda *a, **k: False)
    src, sha = _make_sealed_source(tmp_path)
    art = _write_v2_artifact(tmp_path, src, sha, sp="0" * 40)
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    with pytest.raises(ExecutionPreflightError, match="not an ancestor"):
        adapter.prepare_forget_runtime_bindings(validated, artifact_path=art)


def test_prepare_rejects_reused_runtime_root(tmp_path):
    src, sha = _make_sealed_source(tmp_path)
    art = _write_v2_artifact(tmp_path, src, sha)
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    adapter.prepare_forget_runtime_bindings(validated, artifact_path=art)
    with pytest.raises(ExecutionPreflightError, match="runtime root must not already exist"):
        adapter.prepare_forget_runtime_bindings(validated, artifact_path=art)

def test_prepare_rejects_missing_source_db(tmp_path):
    import json
    from evaluation.d13d_forget_state_binding import compute_artifact_sha256
    src, sha = _make_sealed_source(tmp_path)
    art = _write_v2_artifact(tmp_path, src, sha)
    data = json.loads(art.read_text(encoding="utf-8"))
    data["source_state"]["sealed_db_path"] = str(tmp_path / "missing.db")
    data["artifact_sha256"] = compute_artifact_sha256(data)
    art.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    with pytest.raises(ExecutionPreflightError, match="source DB does not exist"):
        adapter.prepare_forget_runtime_bindings(validated, artifact_path=art)


def test_prepare_rejects_source_db_symlink(tmp_path):
    import json, os
    from evaluation.d13d_forget_state_binding import compute_artifact_sha256
    src, sha = _make_sealed_source(tmp_path)
    link = tmp_path / "source-link.db"
    try:
        os.symlink(src, link)
    except OSError as exc:  # Windows 无权限创建 symlink 时跳过
        pytest.skip(f"cannot create symlink: {exc}")
    art = _write_v2_artifact(tmp_path, src, sha)
    data = json.loads(art.read_text(encoding="utf-8"))
    data["source_state"]["sealed_db_path"] = str(link)
    data["artifact_sha256"] = compute_artifact_sha256(data)
    art.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    with pytest.raises(ExecutionPreflightError, match="must not be a symlink"):
        adapter.prepare_forget_runtime_bindings(validated, artifact_path=art)


def test_prepare_rejects_non_sqlite_source(tmp_path):
    import json, hashlib
    from evaluation.d13d_forget_state_binding import compute_artifact_sha256
    real, _ = _make_sealed_source(tmp_path)
    garbage = tmp_path / "garbage.db"
    garbage.write_bytes(b"this is not a sqlite database at all")
    art = _write_v2_artifact(tmp_path, real, hashlib.sha256(real.read_bytes()).hexdigest())
    data = json.loads(art.read_text(encoding="utf-8"))
    data["source_state"]["sealed_db_path"] = str(garbage)
    data["source_state"]["sealed_db_sha256"] = hashlib.sha256(garbage.read_bytes()).hexdigest()
    data["source_state"]["db_size_bytes"] = garbage.stat().st_size
    data["source_state"]["sqlite_schema_fingerprint"] = "0" * 64
    data["artifact_sha256"] = compute_artifact_sha256(data)
    art.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    with pytest.raises(ExecutionPreflightError, match="not a valid sqlite database"):
        adapter.prepare_forget_runtime_bindings(validated, artifact_path=art)

def test_prepare_rejects_schema_fingerprint_mismatch(tmp_path):
    """F10：sealed DB schema fingerprint 与 artifact 不一致 → fail-closed。"""
    import json, sqlite3, hashlib, shutil
    from evaluation.d13d_forget_state_binding import compute_artifact_sha256
    db1, sha1 = _make_sealed_source(tmp_path)
    db2 = tmp_path / "source-extra.db"
    shutil.copyfile(db1, db2)
    con = sqlite3.connect(str(db2))
    con.execute("CREATE TABLE extra_table (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()
    art = _write_v2_artifact(tmp_path, db1, sha1)
    data = json.loads(art.read_text(encoding="utf-8"))
    data["source_state"]["sealed_db_path"] = str(db2)
    data["source_state"]["sealed_db_sha256"] = hashlib.sha256(db2.read_bytes()).hexdigest()
    data["source_state"]["db_size_bytes"] = db2.stat().st_size
    # 保留 db1 的 schema fingerprint → 与 db2 不符
    data["artifact_sha256"] = compute_artifact_sha256(data)
    art.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    with pytest.raises(ExecutionPreflightError, match="schema fingerprint does not match"):
        adapter.prepare_forget_runtime_bindings(validated, artifact_path=art)


def _seed_alpha_single_knowledge(db_path):
    """在 sealed source DB 预置一条 alpha knowledge（id=1），供 handler 回归用。"""
    from db.engine import create_db_engine, init_schema
    from db import repositories as repo
    engine = create_db_engine(str(db_path))
    init_schema(engine)
    with engine.begin() as conn:
        repo.insert_memory_entry(
            conn, user_id="user_d13e_alpha", entry_type="knowledge",
            content={"value": "d13e single target"}, confidence=0.9,
        )
    engine.dispose()


def test_forget_handler_uow_bound_to_own_sample_runtime_db(tmp_path):
    """Review BLOCKER-01 回归：sample-001 的 preview/execute 只改 sample-001 DB。"""
    import json, hashlib
    from sqlalchemy import text as sql_text
    from db.engine import create_db_engine
    src = tmp_path / "source.db"
    _seed_alpha_single_knowledge(src)
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    art = _write_v2_artifact(tmp_path, src, sha)
    validated = validate_execution_request(
        _request(tmp_path, binding_artifact_path=art), git_runner=_git_runner
    )
    bindings = adapter.prepare_forget_runtime_bindings(validated, artifact_path=art)
    b = bindings["d13e-forget-001"]
    plan_id = "d13d-plan-g3reg-1"
    ctx = adapter.RequestContext(
        request_id="req-g3reg", trace_id="trace-g3reg", method="forget.preview",
        deadline_ms=10000, user_id="user_d13e_alpha", session_id="s1",
        idempotency_key="idem-preview-g3reg",
    )
    payload = {
        "forget_plan_id": plan_id, "user_id": "user_d13e_alpha",
        "forget_mode": "single_item", "target_selector": "{\"memory_id\": \"d13e-memory-001\"}",
        "target_type": "knowledge", "target_id": "1",
        "target_session_id": None, "target_topic": None, "target_time_range": None,
        "requires_confirmation": True, "is_cascade": False, "delete_mode": "soft",
    }
    preview = b.forget_preview_handler(payload, ctx)
    token = preview["confirmation_token"]
    exec_ctx = adapter.RequestContext(
        request_id="req-g3reg-x", trace_id="trace-g3reg-x", method="forget.execute",
        deadline_ms=10000, user_id="user_d13e_alpha", session_id="s1",
        idempotency_key="idem-execute-g3reg",
    )
    b.forget_execute_handler(
        {"forget_plan_id": plan_id, "user_id": "user_d13e_alpha",
         "confirmation_token": token},
        exec_ctx,
    )
    state = {}
    for sid, bb in bindings.items():
        engine = create_db_engine(str(bb.db_path))
        with engine.connect() as conn:
            state[sid] = conn.execute(
                sql_text("SELECT is_deleted FROM memory_entries WHERE id = 1")
            ).scalar_one()
        engine.dispose()
    assert state["d13e-forget-001"] == 1, "sample-001 自身 DB 应已软删目标"
    for sid in ("d13e-forget-002", "d13e-forget-003", "d13e-forget-004", "d13e-forget-005"):
        assert state[sid] == 0, f"{sid} DB 不应被 sample-001 的 handler 改动（late-binding）"


def test_fts_observer_probe_realtime_rebuild(tmp_path):
    """P2-B FTS：pre-delete probe 命中；realtime（删除消费）与 rebuild 后目标不再返回。"""
    import hashlib
    from db.engine import create_db_engine, init_schema
    from db import repositories as repo
    from retrieval.evaluation import evaluate_forget_residual, ForgetResidualPhase
    from service.d13d_forget_observability import capture_forget_execution_snapshot
    from evaluation.d13d_forget_fts_observer import D13DForgetFtsObserver

    db_path = tmp_path / "run.db"
    engine = create_db_engine(str(db_path))
    init_schema(engine)
    with engine.begin() as conn:
        target = repo.insert_memory_entry(
            conn, user_id="user_d13e_alpha", entry_type="knowledge",
            content={"value": "prepared-target-alpha-001"}, confidence=0.9,
        )
        control = repo.insert_memory_entry(
            conn, user_id="user_d13e_alpha", entry_type="knowledge",
            content={"value": "prepared-control-alpha-002"}, confidence=0.9,
        )
        repo.insert_memory_entry(
            conn, user_id="user_d13e_beta", entry_type="knowledge",
            content={"value": "prepared-foreign-alpha-003"}, confidence=0.9,
        )
    observer = D13DForgetFtsObserver(
        engine, user_id="user_d13e_alpha", fts_db=str(tmp_path / "fts.db")
    )
    observer.initialize()
    confirmed = (f"knowledge:{target}",)
    observer.probe_pre_delete(confirmed)  # pre-delete 必须命中

    # 模拟 forget.execute：软删目标后先做 realtime（删除消费），再做 rebuild
    with engine.begin() as conn:
        count, _ = repo.soft_delete_resolved_targets(
            conn, user_id="user_d13e_alpha", target_type="knowledge",
            resolved_target_ids=[str(target)], forget_plan_id="fts-plan",
        )
    assert count == 1
    rt = observer.realtime(confirmed)
    assert rt.sample.confirmed_target_ids == confirmed
    assert all(tid not in rt.sample.ranked_ids for tid in confirmed)
    rb = observer.rebuild(confirmed)
    assert all(tid not in rb.sample.ranked_ids for tid in confirmed)
    # observer 计算真实 residual（不允许测试注入 0）
    for phase, obs in ((ForgetResidualPhase.REALTIME_DELETE, rt),
                       (ForgetResidualPhase.REBUILD, rb)):
        report = evaluate_forget_residual(
            [obs.sample], phase=phase, dataset_version=obs.dataset_version,
            source_snapshot_id=obs.source_snapshot_id,
            source_watermark=obs.source_watermark,
        )
        assert report.residual_target_count == 0
    engine.dispose()