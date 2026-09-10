"""D15B merge-time finalization state and identity guard."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _json(relative_path: str) -> dict[str, object]:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def _sha256(relative_path: str) -> str:
    return hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()


def test_d15b_status_and_identity_are_consistent() -> None:
    inventory = _json("docs/day15/d15b_btrack_inventory.json")
    inputs = _json("release/btrack/D15B_RETRIEVAL_EVAL_INPUTS.json")
    manifest = _json("release/btrack/D15B_BTRACK_MANIFEST.json")
    handoff = _json("release/btrack/D15B_BTRACK_HANDOFF.json")

    expected_base = "a7abb1e71c03c4f1558e5c6a9eff2b9f36437993"
    expected_formal_runtime = "ba3b50e1bdeea185bca9daee9d1d45958f62a636"

    assert inventory["assessment_base_commit"] == expected_base
    assert inputs["assessment_base_commit"] == expected_base
    assert manifest["assessment_base_commit"] == expected_base
    assert manifest["d14b"]["merge_sha"] == expected_base
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["d15b_source_head"])

    assert inputs["formal_runtime_tested_commit"] == expected_formal_runtime
    assert manifest["d14b"]["formal_runtime_tested_commit"] == expected_formal_runtime
    assert handoff["formal_runtime_tested_commit"] == expected_formal_runtime
    assert inputs["formal_execution_commit"] is None
    assert handoff["d15b_formal_execution_commit"] is None

    assert manifest["d14b"]["formal_l3_result"] != "PASS"
    assert manifest["manifest_status"] == "NOT_FROZEN"
    assert manifest["formal_metrics"] is None
    assert manifest["d15b_pr_merge_eligibility"] == "PASS_WITH_DEBT"
    assert manifest["b_track_release_readiness"] == "BLOCKED_NOT_COMPLETE"
    assert manifest["b_track_complete"] == "NO"
    assert handoff["d15b_pr_merge_eligibility"] == "PASS_WITH_DEBT"
    assert handoff["b_track_release_readiness"] == "BLOCKED_NOT_COMPLETE"
    assert handoff["b_track_status"] == "BLOCKED_NOT_COMPLETE"


def test_d15b_waiver_is_limited_to_pr_merge_status() -> None:
    manifest = _json("release/btrack/D15B_BTRACK_MANIFEST.json")
    waiver = manifest["waiver"]

    assert waiver["authority"] == "WAIVED_BY_OWNER"
    assert waiver["source"] == "PR #124 / docs/day14/21_d14b_formal_l3_intake_blockers_20260909.md"
    assert waiver["scope"] == [
        "d13d/d14d handoff",
        "frozen tar",
        "four production capture runners",
        "D14D clean VM/snapshot",
    ]
    assert waiver["applicability"] == "PR #173 merge-status documentation for the same missing formal inputs only"
    assert set(waiver["does_not_apply_to"]) >= {
        "retrieval eval-input freeze",
        "final metrics",
        "B-track manifest freeze",
        "B_TRACK_COMPLETE",
        "release_ready",
        "production_ready",
    }


def test_d15b_inputs_and_execution_binding_do_not_form_a_cycle() -> None:
    inputs = _json("release/btrack/D15B_RETRIEVAL_EVAL_INPUTS.json")

    assert inputs["input_freeze_status"] == "NOT_FROZEN"
    assert inputs["execution_binding_status"] == "NOT_BOUND"
    assert inputs["formal_metrics"] is None
    freeze_requirements = " ".join(inputs["required_before_input_freeze"]).lower()
    assert "raw results" not in freeze_requirements
    assert "latency samples" not in freeze_requirements
    assert "environment" not in freeze_requirements
    assert "formal execution" not in freeze_requirements
    assert inputs["required_before_formal_execution"]


def test_d15b_paths_and_hashes_are_verifiable() -> None:
    inputs = _json("release/btrack/D15B_RETRIEVAL_EVAL_INPUTS.json")
    manifest = _json("release/btrack/D15B_BTRACK_MANIFEST.json")
    handoff = _json("release/btrack/D15B_BTRACK_HANDOFF.json")

    for relative_path, expected_hash in (
        (inputs["dataset"]["path"], inputs["dataset"]["sha256"]),
        (inputs["queries"]["path"], inputs["queries"]["sha256"]),
        (inputs["gold_policy"]["path"], inputs["gold_policy"]["sha256"]),
        (inputs["evaluator"]["cli_path"], inputs["evaluator"]["cli_sha256"]),
        (inputs["evaluator"]["ledger_path"], inputs["evaluator"]["ledger_sha256"]),
        (manifest["d14b"]["intake_blocker_record"]["path"], manifest["d14b"]["intake_blocker_record"]["sha256"]),
        (manifest["evidence"]["d14d_l3_reference"]["path"], manifest["evidence"]["d14d_l3_reference"]["sha256"]),
    ):
        assert _sha256(relative_path) == expected_hash

    for relative_path in (
        "docs/day15/03_d15b_retrieval_release_finalization_task_card_20260909.md",
        "docs/day15/04_d15b_btrack_final_report_20260909.md",
        inventory_path := "docs/day15/d15b_btrack_inventory.json",
        handoff["retrieval_eval_inputs_manifest"],
        handoff["btrack_manifest"],
        handoff["final_report"],
    ):
        assert (ROOT / relative_path).is_file()
    assert inventory_path == "docs/day15/d15b_btrack_inventory.json"
    assert "current_ssot" in manifest["evidence"]["d14d_l3_reference"]


def test_d15b_formal_input_remediation_remains_package_blocked() -> None:
    manifest = _json("release/btrack/D15B_BTRACK_MANIFEST.json")
    remediation = manifest["d14b"]["formal_input_remediation"]

    assert remediation["control_head"] == "c5573c1ce75ad08427b86e3551074e18ed806279"
    assert remediation["status"] == "PARTIALLY_REMEDIATED"
    for handoff in ("d13d_handoff", "d14d_handoff", "capture_handoff"):
        entry = remediation[handoff]
        assert _sha256(entry["path"]) == entry["sha256"]
    assert manifest["release_package"]["actual_tar_bytes_available"] is False
    rebuilt_tar = manifest["release_package"]["rebuilt_tar"]
    assert _sha256(rebuilt_tar["path"]) == rebuilt_tar["sha256"]
    assert rebuilt_tar["status"] == "PROVENANCE_LABELED_REBUILD_NOT_ORIGINAL_FROZEN_BYTES"
