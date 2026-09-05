"""D13E 正式评测 Runner 的 CLI 公共契约测试。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPOSITORY_ROOT / "scripts" / "run_d13e_formal_eval.py"
METRICS = ("preference", "conflict", "safety", "forget")
_SPEC = importlib.util.spec_from_file_location("d13e_formal_eval_runner", RUNNER)
assert _SPEC is not None and _SPEC.loader is not None
RUNNER_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(RUNNER_MODULE)


class D13EFormalEvalCliTests(unittest.TestCase):
    def _run(self, bundle: Path, output: Path) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ, PYTHONPATH=str(REPOSITORY_ROOT / "memory-service"))
        return subprocess.run([sys.executable, str(RUNNER), str(bundle), "--output", str(output)], cwd=REPOSITORY_ROOT, env=environment, capture_output=True, text=True, check=False)

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _refresh_execution_attestation(self, root: Path, bundle: Path) -> None:
        payload = json.loads(bundle.read_text(encoding="utf-8"))
        raw_files = payload["raw_result_files"]
        for descriptor in raw_files.values():
            descriptor["sha256"] = self._sha(root / descriptor["file"])
        attestation_path = root / payload["execution_attestation_file"]
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
        attestation["raw_result_files"] = raw_files
        sha256sums_path = root / attestation["sha256sums_file"]
        execution_log = root / attestation["execution_log_file"]
        sha256sums_path.write_text("\n".join(f"{descriptor['sha256']}  {descriptor['file']}" for descriptor in raw_files.values()) + f"\n{self._sha(execution_log)}  {execution_log.name}\n", encoding="utf-8")
        attestation["sha256sums_sha256"] = self._sha(sha256sums_path)
        attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
        payload["execution_attestation_sha256"] = self._sha(attestation_path)
        bundle.write_text(json.dumps(payload), encoding="utf-8")

    def _approved_d_review(self, _: str) -> dict[str, object]:
        return self._approved_review_payload

    @staticmethod
    def _approved_review_history() -> list[dict[str, object]]:
        return [{"id": 1, "state": "APPROVED", "submitted_at": "2026-09-05T09:36:15Z", "user": {"login": "Ducknesses"}}]

    @staticmethod
    def _current_pr_metadata() -> dict[str, object]:
        return {"user": {"login": "e-author"}, "head": {"sha": "a" * 40}}

    def _write_complete_bundle(self, root: Path) -> Path:
        dataset = [{"sample_id": f"{metric}-1", "metric": metric, "inclusion_status": "valid"} for metric in METRICS]
        gold = [
            {"sample_id": "preference-1", "metric": "preference", "evaluation_status": "valid", "gold_status": "SEALED_BY_D_REVIEWER", "expected": {"record_count": 1}},
            {"sample_id": "conflict-1", "metric": "conflict", "evaluation_status": "valid", "gold_status": "SEALED_BY_D_REVIEWER", "expected": {"action": "keep_left"}},
            {"sample_id": "safety-1", "metric": "safety", "evaluation_status": "valid", "gold_status": "SEALED_BY_D_REVIEWER", "expected": {"critical_violation_count": 0}},
            {"sample_id": "forget-1", "metric": "forget", "evaluation_status": "valid", "gold_status": "SEALED_BY_D_REVIEWER", "expected": {"missed_target_items": 0}},
        ]
        dataset_path, gold_path = root / "dataset.jsonl", root / "gold.jsonl"
        dataset_path.write_text("\n".join(json.dumps(row) for row in dataset) + "\n", encoding="utf-8")
        gold_path.write_text("\n".join(json.dumps(row) for row in gold) + "\n", encoding="utf-8")
        thresholds_path = root / "thresholds.json"
        thresholds_path.write_text(json.dumps({"threshold_version": "d13e-formal-thresholds/v1", "approval_status": "APPROVED_BY_D_NON_AUTHOR_REVIEWER", "approval_reference": "https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/148#pullrequestreview-1", "source": "D13E formal threshold approval", "approved_by": "Ducknesses", "metrics": {"preference": {"minimum_accuracy": 0.85}, "conflict": {"minimum_accuracy": 0.88}, "safety": {"maximum_violation_count": 0}, "forget": {"maximum_violation_count": 0}}}), encoding="utf-8")
        raw_files = {}
        actuals = (
            {"record_count": 1},
            {"action": "keep_left"},
            {
                "critical_violation_count": 0,
                "critical_gate_bypass_count": 0,
                "normal_memory_write_count": 0,
                "audit_plaintext_leak_count": 0,
                "cross_user_violation_count": 0,
            },
            {
                "missed_target_items": 0,
                "wrongly_deleted_items": 0,
                "cross_user_violation_count": 0,
                "residual_after_realtime_query": 0,
                "residual_after_full_rebuild": 0,
            },
        )
        for metric, actual in zip(METRICS, actuals, strict=True):
            path = root / f"{metric}.jsonl"
            path.write_text(json.dumps({"sample_id": f"{metric}-1", "metric": metric, "actual": actual}) + "\n", encoding="utf-8")
            raw_files[metric] = {"file": path.name, "sha256": self._sha(path)}
        evidence_reference = "evidence/l2-kylin-vm/d13d_20260905T000000Z"
        execution_log = root / "execution.log"
        execution_log.write_text("D13D formal evaluation execution\n", encoding="utf-8")
        sha256sums = root / "SHA256SUMS"
        sha256sums.write_text("\n".join(f"{descriptor['sha256']}  {descriptor['file']}" for descriptor in raw_files.values()) + f"\n{self._sha(execution_log)}  {execution_log.name}\n", encoding="utf-8")
        evidence_index = root / "evidence-index.yaml"
        evidence_index.write_text("d13e_execution: frozen\n", encoding="utf-8")
        manifest = {
            "manifest_version": "d13e-formal-manifest/v1", "seal_status": "SEALED_BY_D_REVIEWER",
            "dataset_version": "d13e-formal-v1", "gold_label_version": "d13e-gold-v1",
            "dataset_file": dataset_path.name, "dataset_sha256": self._sha(dataset_path),
            "gold_file": gold_path.name, "gold_sha256": self._sha(gold_path),
            "threshold_config_file": thresholds_path.name, "threshold_config_sha256": self._sha(thresholds_path),
            "sample_count": {**{metric: 1 for metric in METRICS}, "total": 4},
            "provenance": {"status": "FROZEN_BY_D13D", "implementation_commit": "a" * 40, "environment_id": "Kylin-D13D-test", "dependency_version_reference": "deps-lock-test", "data_version_reference": "data-lock-test", "evidence_root": evidence_reference, "evidence_directory": ".", "evidence_reference": evidence_reference},
            "review": {"required_reviewer_track": "D", "status": "APPROVED_BY_D_NON_AUTHOR_REVIEWER", "gold_review_status": "APPROVED_BY_D_NON_AUTHOR_REVIEWER", "reviewer_identity": "Ducknesses", "reviewer_track": "D", "reviewed_commit": "a" * 40, "approval_reference": "https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/148#pullrequestreview-1"},
            "created_by_identity": "e-author",
        }
        self._approved_review_payload = {
            "id": 1,
            "state": "APPROVED",
            "commit_id": "a" * 40,
            "body": "\n".join(("D13E_FORMAL_SEAL_APPROVAL", f"dataset_sha256: {manifest['dataset_sha256']}", f"gold_sha256: {manifest['gold_sha256']}", f"threshold_config_sha256: {manifest['threshold_config_sha256']}")),
            "user": {"login": "Ducknesses"},
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        attestation = {
            "attestation_version": "d13d-execution-attestation/v1",
            "execution_status": "EXECUTED_ON_FROZEN_D13D",
            "implementation_commit": manifest["provenance"]["implementation_commit"],
            "environment_id": manifest["provenance"]["environment_id"],
            "dependency_version_reference": manifest["provenance"]["dependency_version_reference"],
            "data_version_reference": manifest["provenance"]["data_version_reference"],
            "evidence_root": evidence_reference,
            "evidence_directory": ".",
            "evidence_reference": evidence_reference,
            "raw_result_files": raw_files,
            "execution_log_file": execution_log.name,
            "execution_log_sha256": self._sha(execution_log),
            "sha256sums_file": sha256sums.name,
            "sha256sums_sha256": self._sha(sha256sums),
            "evidence_index_file": evidence_index.name,
            "evidence_index_sha256": self._sha(evidence_index),
        }
        attestation_path = root / "execution-attestation.json"
        attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
        bundle = {"bundle_version": "d13e-formal-bundle/v1", "formal_result_status": "READY_FOR_FORMAL_EVALUATION", "execution_status": "EXECUTED_ON_FROZEN_D13D", "manifest_file": "manifest.json", "dataset_version": manifest["dataset_version"], "gold_label_version": manifest["gold_label_version"], "dataset_file": dataset_path.name, "gold_file": gold_path.name, "threshold_config_file": thresholds_path.name, "evidence_reference": evidence_reference, "execution_attestation_file": attestation_path.name, "execution_attestation_sha256": self._sha(attestation_path), "raw_result_files": raw_files}
        bundle_path = root / "bundle.json"
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
        return bundle_path

    def test_runner_rejects_candidate_bundle_without_d13d_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["provenance"]["implementation_commit"] = None
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            output = root / "report.json"
            result = self._run(bundle, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("implementation_commit", result.stderr)
            self.assertFalse(output.exists())

    def test_runner_rejects_unsealed_or_unreviewed_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["seal_status"] = "CANDIDATE_FOR_SEALING"
            manifest["review"]["status"] = "PENDING_NON_AUTHOR_REVIEW"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self._run(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("seal_status", result.stderr)

    def test_runner_rejects_missing_version_or_evidence_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            raw_bundle = json.loads(bundle.read_text(encoding="utf-8"))
            raw_bundle.pop("evidence_reference")
            bundle.write_text(json.dumps(raw_bundle), encoding="utf-8")
            result = self._run(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("evidence_reference", result.stderr)

    def test_runner_rejects_dataset_sha256_that_does_not_match_input_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["dataset_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self._run(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("dataset_sha256", result.stderr)

    def test_runner_rejects_gold_record_that_is_not_sealed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            gold_path = root / "gold.jsonl"
            records = [json.loads(line) for line in gold_path.read_text(encoding="utf-8").splitlines()]
            records[0]["gold_status"] = "CANDIDATE_FOR_D_REVIEW"
            gold_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["gold_sha256"] = self._sha(gold_path)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self._run(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("gold_status", result.stderr)

    def test_runner_rejects_raw_result_whose_bytes_change_after_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            raw_path = root / "preference.jsonl"
            raw_path.write_text("  " + raw_path.read_text(encoding="utf-8"), encoding="utf-8")
            result = self._run(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("raw_result_files.preference.sha256", result.stderr)

    def test_runner_rejects_safety_hard_violation_even_when_expected_fields_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            raw_path = root / "safety.jsonl"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["actual"]["critical_gate_bypass_count"] = 1
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            self._refresh_execution_attestation(root, bundle)
            report = RUNNER_MODULE.compute_formal_report(bundle, review_fetcher=self._approved_d_review, review_list_fetcher=self._approved_review_history, pull_request_fetcher=self._current_pr_metadata)
            self.assertEqual(report["safety"]["gate_status"], "FAIL")
            self.assertEqual(report["safety"]["errors"][0]["error_type"], "SAFETY_CRITICAL_GATE_BYPASS")

    def test_evaluator_rejects_review_attestation_from_the_artifact_author(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["review"]["reviewer_identity"] = manifest["created_by_identity"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "非作者"):
                RUNNER_MODULE.compute_formal_report(bundle, review_fetcher=self._approved_d_review)

    def test_evaluator_rejects_unregistered_d_reviewer_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["review"]["reviewer_identity"] = "unregistered-d-reviewer"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "可信 D 轨身份"):
                RUNNER_MODULE.compute_formal_report(bundle, review_fetcher=self._approved_d_review)

    def test_runner_rejects_execution_attestation_for_a_different_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            payload = json.loads(bundle.read_text(encoding="utf-8"))
            attestation_path = root / payload["execution_attestation_file"]
            attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
            attestation["environment_id"] = "Kylin-D13D-other"
            attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
            payload["execution_attestation_sha256"] = self._sha(attestation_path)
            bundle.write_text(json.dumps(payload), encoding="utf-8")
            result = self._run(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("environment_id", result.stderr)

    def test_evaluator_rejects_execution_attestation_with_different_dependency_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            payload = json.loads(bundle.read_text(encoding="utf-8"))
            attestation_path = root / payload["execution_attestation_file"]
            attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
            attestation["dependency_version_reference"] = "different-dependencies"
            attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
            payload["execution_attestation_sha256"] = self._sha(attestation_path)
            bundle.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "dependency_version_reference"):
                RUNNER_MODULE.compute_formal_report(bundle, review_fetcher=self._approved_d_review, review_list_fetcher=self._approved_review_history)

    def test_evaluator_rejects_unknown_safety_actual_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            raw_path = root / "safety.jsonl"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["actual"]["unlisted_security_counter"] = 0
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            self._refresh_execution_attestation(root, bundle)
            with self.assertRaisesRegex(ValueError, "未声明字段"):
                RUNNER_MODULE.compute_formal_report(bundle, review_fetcher=self._approved_d_review)

    def test_evaluator_rejects_boolean_hard_zero_counter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            raw_path = root / "safety.jsonl"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["actual"]["critical_gate_bypass_count"] = False
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            self._refresh_execution_attestation(root, bundle)
            with self.assertRaisesRegex(ValueError, "硬零计数"):
                RUNNER_MODULE.compute_formal_report(bundle, review_fetcher=self._approved_d_review, review_list_fetcher=self._approved_review_history, pull_request_fetcher=self._current_pr_metadata)

    def test_evaluator_accepts_sha256sums_entry_for_raw_file_in_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            raw_directory = root / "raw"
            raw_directory.mkdir()
            (root / "preference.jsonl").replace(raw_directory / "preference.jsonl")
            payload = json.loads(bundle.read_text(encoding="utf-8"))
            payload["raw_result_files"]["preference"]["file"] = "raw/preference.jsonl"
            bundle.write_text(json.dumps(payload), encoding="utf-8")
            self._refresh_execution_attestation(root, bundle)
            report = RUNNER_MODULE.compute_formal_report(bundle, review_fetcher=self._approved_d_review, review_list_fetcher=self._approved_review_history, pull_request_fetcher=self._current_pr_metadata)
            self.assertEqual(report["preference"]["gate_status"], "PASS")

    def test_evaluator_rejects_threshold_config_with_mismatched_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            threshold_path = root / "thresholds.json"
            thresholds = json.loads(threshold_path.read_text(encoding="utf-8"))
            thresholds["metrics"]["preference"]["minimum_accuracy"] = 0.9
            threshold_path.write_text(json.dumps(thresholds), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "threshold_config_sha256"):
                RUNNER_MODULE.compute_formal_report(bundle, review_fetcher=self._approved_d_review)

    def test_evaluator_rejects_current_changes_requested_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reviews = self._approved_review_history() + [{"id": 2, "state": "CHANGES_REQUESTED", "submitted_at": "2026-09-05T10:00:00Z", "user": {"login": "other-reviewer"}}]
            with self.assertRaisesRegex(ValueError, "reviewDecision"):
                RUNNER_MODULE.compute_formal_report(self._write_complete_bundle(root), review_fetcher=self._approved_d_review, review_list_fetcher=lambda: reviews, pull_request_fetcher=self._current_pr_metadata)

    def test_evaluator_rejects_dataset_metric_outside_the_four_formal_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            dataset_path = root / "dataset.jsonl"
            gold_path = root / "gold.jsonl"
            dataset_path.write_text(dataset_path.read_text(encoding="utf-8") + json.dumps({"sample_id": "other-1", "metric": "other", "inclusion_status": "valid"}) + "\n", encoding="utf-8")
            gold_path.write_text(gold_path.read_text(encoding="utf-8") + json.dumps({"sample_id": "other-1", "metric": "other", "evaluation_status": "valid", "gold_status": "SEALED_BY_D_REVIEWER", "expected": {}}) + "\n", encoding="utf-8")
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["dataset_sha256"] = self._sha(dataset_path)
            manifest["gold_sha256"] = self._sha(gold_path)
            manifest["sample_count"]["total"] = 5
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self._approved_review_payload["body"] = "\n".join(("D13E_FORMAL_SEAL_APPROVAL", f"dataset_sha256: {manifest['dataset_sha256']}", f"gold_sha256: {manifest['gold_sha256']}", f"threshold_config_sha256: {manifest['threshold_config_sha256']}"))
            with self.assertRaisesRegex(ValueError, "四类正式指标"):
                RUNNER_MODULE.compute_formal_report(bundle, review_fetcher=self._approved_d_review, review_list_fetcher=self._approved_review_history)

    def test_evaluator_rejects_review_when_github_pr_author_matches_reviewer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "GitHub PR 作者"):
                RUNNER_MODULE.compute_formal_report(self._write_complete_bundle(root), review_fetcher=self._approved_d_review, review_list_fetcher=self._approved_review_history, pull_request_fetcher=lambda: {"user": {"login": "Ducknesses"}, "head": {"sha": "a" * 40}})

    def test_evaluator_rejects_bundle_not_rooted_in_its_d13d_evidence_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["provenance"]["evidence_directory"] = "another-evidence-directory"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "evidence_directory"):
                RUNNER_MODULE.compute_formal_report(bundle, review_fetcher=self._approved_d_review, review_list_fetcher=self._approved_review_history, pull_request_fetcher=self._current_pr_metadata)

    def test_evaluator_outputs_four_computed_metrics_for_complete_verified_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = RUNNER_MODULE.compute_formal_report(self._write_complete_bundle(root), review_fetcher=self._approved_d_review, review_list_fetcher=self._approved_review_history, pull_request_fetcher=self._current_pr_metadata)
            self.assertEqual(report["status"], "COMPUTED")
            for metric in METRICS:
                self.assertEqual(report[metric]["status"], "COMPUTED")
                self.assertEqual(report[metric]["correct_count"], 1)
