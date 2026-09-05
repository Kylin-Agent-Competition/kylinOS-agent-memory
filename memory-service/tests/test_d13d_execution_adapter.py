"""L1 tests for D13D execution-adapter preflight; no formal execution occurs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import ast

import pytest

from evaluation.d13d_execution_adapter import (
    ExecutionPreflightError,
    ExecutionRequest,
    raw_record,
    validate_execution_request,
    write_raw_records,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TESTSET = REPOSITORY_ROOT / "evaluation" / "d13e" / "D13E_FORMAL_TESTSET_V1.jsonl"
TESTSET_SHA256 = "9740c00f4a9d91471bec8e6fa8aeeeb52f890f8680d83f740a84db2b1701a44b"
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
        ({"testset_sha256": "0" * 64}, "SHA-256 does not match"),
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


def test_preflight_rejects_duplicate_sample_id(tmp_path):
    records = [json.loads(line) for line in TESTSET.read_text(encoding="utf-8").splitlines()]
    records[-1]["sample_id"] = records[0]["sample_id"]
    altered = tmp_path / "altered.jsonl"
    altered.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
    with pytest.raises(ExecutionPreflightError, match="sample_id must be unique"):
        validate_execution_request(
            _request(
                tmp_path,
                testset_path=altered,
                testset_sha256=hashlib.sha256(altered.read_bytes()).hexdigest(),
            ),
            git_runner=_git_runner,
        )


def test_raw_record_has_only_formal_runner_contract_fields():
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
    )
    assert set(record) == {"sample_id", "metric", "actual", "trace_reference"}


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
    ],
)
def test_raw_record_rejects_incomplete_or_evaluation_shaped_actual(metric, actual, message):
    with pytest.raises(ExecutionPreflightError, match=message):
        raw_record(
            sample_id=f"d13e-{metric if metric != 'preference' else 'pref'}-001",
            metric=metric,
            actual=actual,
            trace_reference="traces/sample-001.jsonl",
        )


def _raw_records(validated):
    actual_by_metric = {
        "preference": {"record_count": 1},
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
    return [
        raw_record(
            sample_id=sample["sample_id"],
            metric=sample["metric"],
            actual=actual_by_metric[sample["metric"]],
            trace_reference=f"traces/{sample['sample_id']}.jsonl",
        )
        for sample in validated.records
    ]


def test_raw_writer_creates_only_canonical_files_after_complete_validation(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)

    written = write_raw_records(validated, _raw_records(validated))

    assert set(written) == {"preference", "conflict", "safety", "forget"}
    assert {path.relative_to(validated.request.output_root).as_posix() for path in written.values()} == {
        "raw/preference_raw.jsonl",
        "raw/conflict_raw.jsonl",
        "raw/safety_raw.jsonl",
        "raw/forget_raw.jsonl",
    }
    assert [len(path.read_text(encoding="utf-8").splitlines()) for path in written.values()] == [4, 4, 4, 5]
    assert not validated.request.state_root.exists()
    assert not validated.request.evidence_root.exists()


def test_raw_writer_fails_closed_before_creating_output_for_missing_sample(tmp_path):
    validated = validate_execution_request(_request(tmp_path), git_runner=_git_runner)
    records = _raw_records(validated)

    with pytest.raises(ExecutionPreflightError, match="raw samples do not match"):
        write_raw_records(validated, records[:-1])

    assert not validated.request.output_root.exists()


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
