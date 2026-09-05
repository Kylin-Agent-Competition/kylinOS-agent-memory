"""D13E 正式评测 Runner 的 CLI 公共契约测试。"""

from __future__ import annotations

import hashlib
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


class D13EFormalEvalCliTests(unittest.TestCase):
    def _run(self, bundle: Path, output: Path) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ, PYTHONPATH=str(REPOSITORY_ROOT / "memory-service"))
        return subprocess.run([sys.executable, str(RUNNER), str(bundle), "--output", str(output)], cwd=REPOSITORY_ROOT, env=environment, capture_output=True, text=True, check=False)

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _write_complete_bundle(self, root: Path) -> Path:
        dataset = [{"sample_id": f"{metric}-1", "metric": metric, "inclusion_status": "valid"} for metric in METRICS]
        gold = [
            {"sample_id": "preference-1", "metric": "preference", "evaluation_status": "valid", "expected": {"record_count": 1}},
            {"sample_id": "conflict-1", "metric": "conflict", "evaluation_status": "valid", "expected": {"action": "keep_left"}},
            {"sample_id": "safety-1", "metric": "safety", "evaluation_status": "valid", "expected": {"critical_violation_count": 0}},
            {"sample_id": "forget-1", "metric": "forget", "evaluation_status": "valid", "expected": {"missed_target_items": 0}},
        ]
        dataset_path, gold_path = root / "dataset.jsonl", root / "gold.jsonl"
        dataset_path.write_text("\n".join(json.dumps(row) for row in dataset) + "\n", encoding="utf-8")
        gold_path.write_text("\n".join(json.dumps(row) for row in gold) + "\n", encoding="utf-8")
        raw_files = {}
        actuals = ({"record_count": 1}, {"action": "keep_left"}, {"critical_violation_count": 0}, {"missed_target_items": 0})
        for metric, actual in zip(METRICS, actuals, strict=True):
            path = root / f"{metric}.jsonl"
            path.write_text(json.dumps({"sample_id": f"{metric}-1", "metric": metric, "actual": actual}) + "\n", encoding="utf-8")
            raw_files[metric] = path.name
        evidence_reference = "evidence/l2-kylin-vm/d13d_20260905T000000Z"
        manifest = {
            "manifest_version": "d13e-formal-manifest/v1", "seal_status": "SEALED_BY_D_REVIEWER",
            "dataset_version": "d13e-formal-v1", "gold_label_version": "d13e-gold-v1",
            "dataset_file": dataset_path.name, "dataset_sha256": self._sha(dataset_path),
            "gold_file": gold_path.name, "gold_sha256": self._sha(gold_path),
            "sample_count": {**{metric: 1 for metric in METRICS}, "total": 4},
            "provenance": {"status": "FROZEN_BY_D13D", "implementation_commit": "a" * 40, "environment_id": "Kylin-D13D-test", "dependency_version_reference": "deps-lock-test", "data_version_reference": "data-lock-test", "evidence_root": evidence_reference, "evidence_reference": evidence_reference},
            "review": {"status": "APPROVED_BY_D_NON_AUTHOR_REVIEWER", "gold_review_status": "APPROVED_BY_D_NON_AUTHOR_REVIEWER", "approval_reference": "https://example.test/pr/148#review"},
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        bundle = {"bundle_version": "d13e-formal-bundle/v1", "formal_result_status": "READY_FOR_FORMAL_EVALUATION", "manifest_file": "manifest.json", "dataset_version": manifest["dataset_version"], "gold_label_version": manifest["gold_label_version"], "dataset_file": dataset_path.name, "gold_file": gold_path.name, "evidence_reference": evidence_reference, "raw_result_files": raw_files}
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

    def test_runner_outputs_four_computed_metrics_for_complete_matching_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "report.json"
            result = self._run(self._write_complete_bundle(root), output)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "COMPUTED")
            for metric in METRICS:
                self.assertEqual(report[metric]["status"], "COMPUTED")
                self.assertEqual(report[metric]["correct_count"], 1)
