"""L1 tests for D13D execution-adapter preflight; no formal execution occurs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import ast
import subprocess
import sys

import pytest

from db import repositories as repo
import evaluation.d13d_execution_adapter as adapter
from evaluation.d13d_execution_adapter import (
    OFFICIAL_D13E_TESTSET_SHA256,
    ExecutionPreflightError,
    ExecutionRequest,
    ObservedRawRecord,
    ValidatedRuntimeBinding,
    _record_to_line,
    build_runtime_binding,
    dispatch_safety_sample,
    dispatch_stateless_sample,
    raw_record,
    validate_execution_request,
    write_raw_records,
)


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
        "output_root": tmp_path / "output",
        "state_root": tmp_path / "state",
        "evidence_root": tmp_path / "evidence",
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
        ({"output_root": REPOSITORY_ROOT / "generated"}, "overlap repository_root"),
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
            _request(tmp_path, state_root=tmp_path / "output" / "nested"),
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


@pytest.mark.parametrize("root_name", ["state_root", "evidence_root"])
def test_preflight_rejects_existing_isolation_root(tmp_path, root_name):
    existing_root = tmp_path / root_name
    existing_root.mkdir()

    with pytest.raises(ExecutionPreflightError, match=f"{root_name} must not already exist"):
        validate_execution_request(
            _request(tmp_path, **{root_name: existing_root}),
            git_runner=_git_runner,
        )


@pytest.mark.parametrize("root_name", ["output_root", "state_root", "evidence_root"])
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
            "--output-root",
            str(tmp_path / "output"),
            "--state-root",
            str(tmp_path / "state"),
            "--evidence-root",
            str(tmp_path / "evidence"),
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
    assert set(record.as_canonical_mapping()) == {
        "sample_id",
        "metric",
        "actual",
        "trace_reference",
    }
    line = json.loads(_record_to_line(record))
    assert set(line) == {"sample_id", "metric", "actual", "trace_reference"}
    assert line["actual"] == record.actual


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
            "frozen schema",
        ),
    ],
)
def test_raw_record_rejects_incomplete_or_evaluation_shaped_actual(metric, actual, message):
    with pytest.raises(ExecutionPreflightError, match=message):
        raw_record(
            sample_id=f"d13e-{metric if metric != 'preference' else 'pref'}-001",
            metric=metric,
            actual=actual,
            trace_reference="traces/sample-001.jsonl",
            runtime_scope="stateless:test",
        )


def test_raw_writer_serializer_layout_is_canonical():
    # Pure serializer unit coverage: write_raw_records is the internal
    # serializer of the formal orchestration path and is not, by itself,
    # evidence of a real execution closure (see its docstring).
    record = ObservedRawRecord(
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
    assert line["actual"] == record.actual


def test_raw_writer_rejects_hand_built_raw_mapping(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    forged = {
        "sample_id": "d13e-pref-001",
        "metric": "preference",
        "actual": {"record_count": 1},
        "trace_reference": "preference:d13e-pref-001",
    }
    with pytest.raises(ExecutionPreflightError, match="ObservedRawRecord produced by real dispatch"):
        write_raw_records(validated, [forged])
    assert not validated.request.output_root.exists()


def test_raw_writer_fails_closed_when_dispatch_is_not_complete(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    stateless = _dispatchable_stateless(validated)
    assert len(stateless) == 8
    with pytest.raises(ExecutionPreflightError, match="raw samples do not match"):
        write_raw_records(validated, stateless)
    assert not validated.request.output_root.exists()


def test_dispatch_stateless_preference_projects_top_level_fields(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)

    record = dispatch_stateless_sample(validated, "d13e-pref-001")

    assert record.sample_id == "d13e-pref-001"
    assert record.metric == "preference"
    assert "records" not in record.actual
    assert record.actual == {
        "record_count": 1,
        "key": "response.language",
        "scope": "global",
        "is_temporary": False,
        "should_persist": True,
        "explicitness": "explicit",
    }
    assert record.trace_reference == "preference:d13e-pref-001"
    assert record.runtime_scope == "stateless:preference"


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
    assert record.trace_reference == "conflict:d13e-conflict-001"
    assert record.runtime_scope == "stateless:conflict"


def test_dispatch_stateless_rejects_stateful_metrics_without_an_environment_binding(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)

    with pytest.raises(ExecutionPreflightError, match="isolated runtime binding"):
        dispatch_stateless_sample(validated, "d13e-forget-001")


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


def test_dispatch_safety_rejects_binding_outside_validated_state_root(safety_environment, tmp_path):
    validated, binding = safety_environment
    forged = ValidatedRuntimeBinding(
        validated=validated,
        binding_id="forged",
        db_path=tmp_path / "outside-state-root.db",
        engine=binding.engine,
        registry=binding.registry,
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
    (tmp_path / "other").mkdir()
    other = validate_execution_request(_request(tmp_path / "other"), git_runner=_git_runner)
    other_binding = build_runtime_binding(other)
    with pytest.raises(ExecutionPreflightError, match="not created from this validated execution"):
        dispatch_safety_sample(
            validated,
            "d13e-safety-001",
            binding=other_binding,
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


def test_adapter_raw_feed_does_not_fail_the_runner_field_contract(tmp_path, safety_environment):
    """Adapter raw -> frozen Runner contract: no per-sample field-shape failure.

    Gold is read here only to drive the Runner's per-sample allowed-field
    contract (the same way formal Gate 9 consumes raw); it is never used to
    generate `actual`. Forget is intentionally excluded because its external
    state binding is still BLOCKED.
    """
    validated, binding = safety_environment
    runner = _load_runner_module()
    gold = _gold_expected_by_sample()
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
        expected = gold[sample_id]
        result = runner._matches_metric_contract(metric, expected, record.actual)
        assert isinstance(result, bool)
