"""D13E 正式评测 Runner 的 CLI 公共契约测试。"""

from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPOSITORY_ROOT / "scripts" / "run_d13e_formal_eval.py"


class D13EFormalEvalCliTests(unittest.TestCase):
    def _run(self, bundle: Path, output: Path) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(REPOSITORY_ROOT / "memory-service")
        return subprocess.run(
            [sys.executable, str(RUNNER), str(bundle), "--output", str(output)],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def _write_valid_provenance_manifest(tmp_path: Path, **overrides: object) -> None:
        manifest = {
            "manifest_version": "d13e-formal-manifest/v1",
            "dataset_version": "d13e-formal-v1",
            "gold_label_version": "d13e-gold-v1",
            "dataset_file": "dataset.jsonl",
            "dataset_sha256": "0" * 64,
            "gold_file": "gold.jsonl",
            "gold_sha256": "1" * 64,
            "sample_count": {"preference": 1, "conflict": 1, "safety": 1, "forget": 1, "total": 4},
            "provenance": {
                "status": "FROZEN_BY_D13D",
                "implementation_commit": "a" * 40,
                "environment_id": "Kylin-D13D-test",
                "dependency_version_reference": "deps-lock-test",
                "data_version_reference": "data-lock-test",
                "evidence_root": "evidence/day13/d13e",
            },
        }
        manifest.update(overrides)
        (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    @staticmethod
    def _write_bundle(tmp_path: Path) -> Path:
        bundle = tmp_path / "bundle.json"
        bundle.write_text(
            json.dumps(
                {
                    "bundle_version": "d13e-formal-bundle/v1",
                    "manifest_file": "manifest.json",
                    "dataset_file": "dataset.jsonl",
                    "gold_file": "gold.jsonl",
                    "raw_result_files": {
                        "preference": None,
                        "conflict": None,
                        "safety": None,
                        "forget": None,
                    },
                }
            ),
            encoding="utf-8",
        )
        return bundle

    def test_runner_rejects_candidate_bundle_without_d13d_provenance(self) -> None:
        """缺少冻结 Commit 时必须失败，且不得留下可误读的正式输出。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            bundle = tmp_path / "bundle.json"
            output = tmp_path / "formal-report.json"
            bundle.write_text(
        json.dumps(
            {
                "bundle_version": "d13e-formal-bundle/v1",
                "manifest_file": "manifest.json",
                "dataset_file": "dataset.jsonl",
                "gold_file": "gold.jsonl",
                "raw_result_files": {
                    "preference": None,
                    "conflict": None,
                    "safety": None,
                    "forget": None,
                },
            }
        ),
                encoding="utf-8",
            )
            (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": "d13e-formal-manifest/v1",
                "dataset_version": "d13e-formal-v1",
                "gold_label_version": "d13e-gold-v1",
                "dataset_file": "dataset.jsonl",
                "dataset_sha256": "0" * 64,
                "gold_file": "gold.jsonl",
                "gold_sha256": "1" * 64,
                "sample_count": {"preference": 1, "conflict": 1, "safety": 1, "forget": 1, "total": 4},
                "provenance": {"status": "PENDING_D13D", "implementation_commit": None},
            }
        ),
                encoding="utf-8",
            )

            result = self._run(bundle, output)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("implementation_commit", result.stderr)
            self.assertFalse(output.exists())

    def test_runner_rejects_dataset_sha256_that_does_not_match_input_file(self) -> None:
        """格式正确但与 Dataset 实体不一致的哈希也不能产生正式报告。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            (tmp_path / "dataset.jsonl").write_text('{"sample_id":"p1"}\n', encoding="utf-8")
            (tmp_path / "gold.jsonl").write_text('{"sample_id":"p1"}\n', encoding="utf-8")
            self._write_valid_provenance_manifest(tmp_path)
            bundle = self._write_bundle(tmp_path)
            output = tmp_path / "formal-report.json"

            result = self._run(bundle, output)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("dataset_sha256", result.stderr)
            self.assertFalse(output.exists())

    def test_runner_outputs_four_computed_metrics_for_complete_matching_bundle(self) -> None:
        """四类有效样本及真实逐样本结果齐全时，指标可重复计算。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            dataset_rows = [
                {"sample_id": "pref-1", "metric": "preference", "inclusion_status": "valid"},
                {"sample_id": "conflict-1", "metric": "conflict", "inclusion_status": "valid"},
                {"sample_id": "safety-1", "metric": "safety", "inclusion_status": "valid"},
                {"sample_id": "forget-1", "metric": "forget", "inclusion_status": "valid"},
            ]
            gold_rows = [
                {"sample_id": "pref-1", "metric": "preference", "expected": {"record_count": 1}},
                {"sample_id": "conflict-1", "metric": "conflict", "expected": {"action": "keep_left"}},
                {"sample_id": "safety-1", "metric": "safety", "expected": {"critical_violation_count": 0}},
                {"sample_id": "forget-1", "metric": "forget", "expected": {"missed_target_items": 0}},
            ]
            dataset_path = tmp_path / "dataset.jsonl"
            gold_path = tmp_path / "gold.jsonl"
            dataset_path.write_text("\n".join(json.dumps(row) for row in dataset_rows) + "\n", encoding="utf-8")
            gold_path.write_text("\n".join(json.dumps(row) for row in gold_rows) + "\n", encoding="utf-8")
            raw_files = {}
            for metric, sample_id, actual in (
                ("preference", "pref-1", {"record_count": 1}),
                ("conflict", "conflict-1", {"action": "keep_left"}),
                ("safety", "safety-1", {"critical_violation_count": 0}),
                ("forget", "forget-1", {"missed_target_items": 0}),
            ):
                path = tmp_path / f"{metric}.jsonl"
                path.write_text(json.dumps({"sample_id": sample_id, "metric": metric, "actual": actual}) + "\n", encoding="utf-8")
                raw_files[metric] = path.name

            self._write_valid_provenance_manifest(
                tmp_path,
                dataset_sha256=hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
                gold_sha256=hashlib.sha256(gold_path.read_bytes()).hexdigest(),
            )
            bundle = self._write_bundle(tmp_path)
            raw_bundle = json.loads(bundle.read_text(encoding="utf-8"))
            raw_bundle["raw_result_files"] = raw_files
            bundle.write_text(json.dumps(raw_bundle), encoding="utf-8")
            output = tmp_path / "formal-report.json"

            result = self._run(bundle, output)

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "COMPUTED")
            self.assertEqual(set(report), {"status", "provenance", "preference", "conflict", "safety", "forget"})
            for metric in ("preference", "conflict", "safety", "forget"):
                self.assertEqual(report[metric]["status"], "COMPUTED")
                self.assertEqual(report[metric]["sample_count"], 1)
                self.assertEqual(report[metric]["correct_count"], 1)
