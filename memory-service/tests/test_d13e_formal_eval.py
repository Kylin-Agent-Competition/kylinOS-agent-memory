"""D13E 正式评测 Runner 的离线公共契约测试。

覆盖 P1-A（Review Seal 消除自引用与真实 sealing 时序）、P1-B（D13D execution
seal 外部可信根与整链重写攻击）、P1-C（Formal Runner 完全离线）及既有
fail-closed 契约。
"""

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
REVIEW_COMMIT = "a" * 40
REVIEW_REFERENCE = "https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/148#pullrequestreview-5120706798"
_SPEC = importlib.util.spec_from_file_location("d13e_formal_eval_runner", RUNNER)
assert _SPEC is not None and _SPEC.loader is not None
RUNNER_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(RUNNER_MODULE)


class D13EFormalEvalCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._review_seal_path: Path | None = None
        self._d13d_seal_path: Path | None = None

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _run(self, bundle: Path, output: Path) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ, PYTHONPATH=str(REPOSITORY_ROOT / "memory-service"))
        return subprocess.run(
            [sys.executable, str(RUNNER), str(bundle), "--output", str(output)],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def _run_sealed(self, bundle: Path, output: Path) -> subprocess.CompletedProcess[str]:
        assert self._review_seal_path is not None and self._d13d_seal_path is not None
        environment = dict(os.environ, PYTHONPATH=str(REPOSITORY_ROOT / "memory-service"))
        return subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                str(bundle),
                "--review-seal",
                str(self._review_seal_path),
                "--d13d-seal",
                str(self._d13d_seal_path),
                "--output",
                str(output),
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def _freeze_d13d_seal_attestation(self, root: Path, bundle: Path) -> None:
        payload = json.loads(bundle.read_text(encoding="utf-8"))
        attestation_path = root / payload["execution_attestation_file"]
        assert self._d13d_seal_path is not None
        seal = json.loads(self._d13d_seal_path.read_text(encoding="utf-8"))
        seal["attestation_sha256"] = self._sha(attestation_path)
        self._d13d_seal_path.write_text(json.dumps(seal), encoding="utf-8")

    def _refresh_execution_attestation(
        self,
        root: Path,
        bundle: Path,
        *,
        refresh_d13d_seal: bool = True,
    ) -> None:
        """重算 raw → SHA256SUMS → attestation → bundle attestation hash。

        若 refresh_d13d_seal=False，则保留 D13D execution seal 中的旧
        attestation digest，用于构造 P1-B 整链重写攻击场景。
        """
        payload = json.loads(bundle.read_text(encoding="utf-8"))
        raw_files = payload["raw_result_files"]
        for descriptor in raw_files.values():
            descriptor["sha256"] = self._sha(root / descriptor["file"])
        attestation_path = root / payload["execution_attestation_file"]
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
        attestation["raw_result_files"] = raw_files
        sha256sums_path = root / attestation["sha256sums_file"]
        execution_log = root / attestation["execution_log_file"]
        sha256sums_path.write_text(
            "\n".join(f"{descriptor['sha256']}  {descriptor['file']}" for descriptor in raw_files.values())
            + f"\n{self._sha(execution_log)}  {execution_log.name}\n",
            encoding="utf-8",
        )
        attestation["sha256sums_sha256"] = self._sha(sha256sums_path)
        attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
        payload["execution_attestation_sha256"] = self._sha(attestation_path)
        bundle.write_text(json.dumps(payload), encoding="utf-8")
        if refresh_d13d_seal:
            self._freeze_d13d_seal_attestation(root, bundle)

    def _approve_current_hashes(self) -> None:
        """以当前工件哈希重新生成 Review Seal，模拟新的外部批准。"""
        assert self._review_seal_path is not None
        root = self._review_seal_path.parent
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        seal = json.loads(self._review_seal_path.read_text(encoding="utf-8"))
        seal["approved_artifacts"] = {
            "dataset_sha256": manifest["dataset_sha256"],
            "gold_sha256": manifest["gold_sha256"],
            "threshold_sha256": manifest["threshold_config_sha256"],
            "runner_sha256": self._sha(RUNNER),
        }
        self._review_seal_path.write_text(json.dumps(seal), encoding="utf-8")

    def _compute(self, bundle: Path) -> dict[str, object]:
        assert self._review_seal_path is not None and self._d13d_seal_path is not None
        return RUNNER_MODULE.compute_formal_report(bundle, self._review_seal_path, self._d13d_seal_path)

    def _write_complete_bundle(self, root: Path) -> Path:
        """写入一份已冻结的完整证据目录：Manifest/阈值/Gold 均不含审批自报字段。

        Seal 是 Review / D13D 冻结完成后的后置工件，只存在于该证据目录中。
        """
        dataset = [
            {"sample_id": f"{metric}-1", "metric": metric, "inclusion_status": "valid"} for metric in METRICS
        ]
        gold = [
            {"sample_id": "preference-1", "metric": "preference", "evaluation_status": "valid", "expected": {"record_count": 1}, "rationale": "preference sample"},
            {"sample_id": "conflict-1", "metric": "conflict", "evaluation_status": "valid", "expected": {"action": "keep_left"}, "rationale": "conflict sample"},
            {"sample_id": "safety-1", "metric": "safety", "evaluation_status": "valid", "expected": {"critical_violation_count": 0}, "rationale": "safety sample"},
            {"sample_id": "forget-1", "metric": "forget", "evaluation_status": "valid", "expected": {"missed_target_items": 0}, "rationale": "forget sample"},
        ]
        dataset_path, gold_path = root / "dataset.jsonl", root / "gold.jsonl"
        dataset_path.write_text("\n".join(json.dumps(row) for row in dataset) + "\n", encoding="utf-8")
        gold_path.write_text("\n".join(json.dumps(row) for row in gold) + "\n", encoding="utf-8")
        thresholds_path = root / "thresholds.json"
        thresholds_path.write_text(
            json.dumps(
                {
                    "threshold_version": "d13e-formal-thresholds/v1",
                    "metrics": {
                        "preference": {"minimum_accuracy": 0.85},
                        "conflict": {"minimum_accuracy": 0.88},
                        "safety": {"maximum_violation_count": 0},
                        "forget": {"maximum_violation_count": 0},
                    },
                }
            ),
            encoding="utf-8",
        )
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
        raw_files = {}
        for metric, actual in zip(METRICS, actuals, strict=True):
            path = root / f"{metric}.jsonl"
            path.write_text(json.dumps({"sample_id": f"{metric}-1", "metric": metric, "actual": actual}) + "\n", encoding="utf-8")
            raw_files[metric] = {"file": path.name, "sha256": self._sha(path)}
        evidence_reference = "evidence/l2-kylin-vm/d13d_20260905T000000Z"
        execution_log = root / "execution.log"
        execution_log.write_text("D13D formal evaluation execution\n", encoding="utf-8")
        sha256sums = root / "SHA256SUMS"
        sha256sums.write_text(
            "\n".join(f"{descriptor['sha256']}  {descriptor['file']}" for descriptor in raw_files.values())
            + f"\n{self._sha(execution_log)}  {execution_log.name}\n",
            encoding="utf-8",
        )
        evidence_index = root / "evidence-index.yaml"
        evidence_index.write_text("d13e_execution: frozen\n", encoding="utf-8")
        provenance = {
            "status": "FROZEN_BY_D13D",
            "implementation_commit": "a" * 40,
            "environment_id": "Kylin-D13D-test",
            "dependency_version_reference": "deps-lock-test",
            "data_version_reference": "data-lock-test",
            "evidence_root": evidence_reference,
            "evidence_directory": ".",
            "evidence_reference": evidence_reference,
        }
        manifest = {
            "manifest_version": "d13e-formal-manifest/v1",
            "dataset_version": "d13e-formal-v1",
            "gold_label_version": "d13e-gold-v1",
            "dataset_file": dataset_path.name,
            "dataset_sha256": self._sha(dataset_path),
            "gold_file": gold_path.name,
            "gold_sha256": self._sha(gold_path),
            "threshold_config_file": thresholds_path.name,
            "threshold_config_sha256": self._sha(thresholds_path),
            "sample_count": {**{metric: 1 for metric in METRICS}, "total": 4},
            "required_reviewer_track": "D",
            "provenance": provenance,
            "created_by_track": "E",
            "created_by_identity": "e-author",
            "created_at": "2026-09-05",
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        attestation = {
            "attestation_version": "d13d-execution-attestation/v1",
            "execution_status": "EXECUTED_ON_FROZEN_D13D",
            "implementation_commit": provenance["implementation_commit"],
            "environment_id": provenance["environment_id"],
            "dependency_version_reference": provenance["dependency_version_reference"],
            "data_version_reference": provenance["data_version_reference"],
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
        bundle = {
            "bundle_version": "d13e-formal-bundle/v1",
            "formal_result_status": "READY_FOR_FORMAL_EVALUATION",
            "execution_status": "EXECUTED_ON_FROZEN_D13D",
            "manifest_file": "manifest.json",
            "dataset_version": manifest["dataset_version"],
            "gold_label_version": manifest["gold_label_version"],
            "dataset_file": dataset_path.name,
            "gold_file": gold_path.name,
            "threshold_config_file": thresholds_path.name,
            "evidence_reference": evidence_reference,
            "execution_attestation_file": attestation_path.name,
            "execution_attestation_sha256": self._sha(attestation_path),
            "raw_result_files": raw_files,
        }
        bundle_path = root / "bundle.json"
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

        review_seal = {
            "seal_version": "d13e-review-seal/v1",
            "source_pr": 148,
            "reviewed_commit": REVIEW_COMMIT,
            "reviewer_identity": "Ducknesses",
            "reviewer_track": "D",
            "review_state": "APPROVED",
            "review_reference": REVIEW_REFERENCE,
            "approved_artifacts": {
                "dataset_sha256": manifest["dataset_sha256"],
                "gold_sha256": manifest["gold_sha256"],
                "threshold_sha256": manifest["threshold_config_sha256"],
                "runner_sha256": self._sha(RUNNER),
            },
        }
        d13d_seal = {
            "seal_version": "d13d-execution-seal/v1",
            "attestation_sha256": self._sha(attestation_path),
            "implementation_commit": provenance["implementation_commit"],
            "environment_id": provenance["environment_id"],
            "evidence_root": evidence_reference,
            "frozen_by_track": "D",
            "approval_reference": "https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/commit/" + "a" * 40,
        }
        self._review_seal_path = root / "review-seal.json"
        self._d13d_seal_path = root / "d13d-seal.json"
        self._review_seal_path.write_text(json.dumps(review_seal), encoding="utf-8")
        self._d13d_seal_path.write_text(json.dumps(d13d_seal), encoding="utf-8")
        return bundle_path

    # ---- P1-C：离线 Runner ----

    def test_runner_has_no_github_api_dependency(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        self.assertNotIn("urlopen", source)
        self.assertNotIn("urllib.request", source)
        self.assertNotIn("api.github.com", source)
        for removed in (
            "_fetch_github_review",
            "_fetch_github_reviews",
            "_fetch_github_pull_request",
            "_verify_d_reviewer_approval",
        ):
            self.assertFalse(hasattr(RUNNER_MODULE, removed), removed)

    # ---- P1-A：Immutable Inputs + External Review Seal ----

    def test_real_sealing_timing_commit_then_review_then_immutable_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            review_seal = json.loads(self._review_seal_path.read_text(encoding="utf-8"))  # type: ignore[arg-type]
            # Commit C 内容固定 → Review Seal 后置生成，批准的哈希与 C 一致。
            self.assertEqual(review_seal["approved_artifacts"]["dataset_sha256"], manifest["dataset_sha256"])
            self.assertEqual(review_seal["approved_artifacts"]["gold_sha256"], manifest["gold_sha256"])
            self.assertEqual(review_seal["approved_artifacts"]["threshold_sha256"], manifest["threshold_config_sha256"])
            # Review 后不再修改被审批工件 → 离线 Runner 可运行。
            report = self._compute(bundle)
            self.assertEqual(report["status"], "COMPUTED")
            self.assertEqual(report["provenance"]["reviewed_commit"], REVIEW_COMMIT)  # type: ignore[index]
            self.assertEqual(report["provenance"]["reviewer_identity"], "Ducknesses")  # type: ignore[index]

    def test_approved_artifacts_contain_no_review_self_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_complete_bundle(root)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            thresholds = json.loads((root / "thresholds.json").read_text(encoding="utf-8"))
            gold_records = [json.loads(line) for line in (root / "gold.jsonl").read_text(encoding="utf-8").splitlines()]
            # Threshold 不再保存批准人 / 批准引用 / 批准状态。
            for key in ("approval_status", "approval_reference", "approved_by"):
                self.assertNotIn(key, thresholds)
            # Manifest 不再自报 seal_status / review 对象。
            self.assertNotIn("seal_status", manifest)
            self.assertNotIn("review", manifest)
            self.assertEqual(manifest["required_reviewer_track"], "D")
            # Gold 每条记录不再需要 gold_status 自报封存状态。
            for record in gold_records:
                self.assertNotIn("gold_status", record)

    def test_runner_rejects_frozen_bundle_without_external_seals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            result = self._run(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--review-seal", result.stderr)
            self.assertIn("--d13d-seal", result.stderr)

    def test_runner_rejects_review_seal_without_approved_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            seal = json.loads(self._review_seal_path.read_text(encoding="utf-8"))  # type: ignore[arg-type]
            seal["review_state"] = "CHANGES_REQUESTED"
            self._review_seal_path.write_text(json.dumps(seal), encoding="utf-8")  # type: ignore[arg-type]
            with self.assertRaisesRegex(ValueError, "review_state"):
                self._compute(bundle)

    def test_runner_rejects_review_seal_reviewer_equal_to_author(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            seal = json.loads(self._review_seal_path.read_text(encoding="utf-8"))  # type: ignore[arg-type]
            seal["reviewer_identity"] = "e-author"
            self._review_seal_path.write_text(json.dumps(seal), encoding="utf-8")  # type: ignore[arg-type]
            with self.assertRaisesRegex(ValueError, "非作者"):
                self._compute(bundle)

    def test_runner_rejects_unregistered_d_reviewer_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            seal = json.loads(self._review_seal_path.read_text(encoding="utf-8"))  # type: ignore[arg-type]
            seal["reviewer_identity"] = "unregistered-d-reviewer"
            self._review_seal_path.write_text(json.dumps(seal), encoding="utf-8")  # type: ignore[arg-type]
            with self.assertRaisesRegex(ValueError, "可信 D 轨身份"):
                self._compute(bundle)

    def test_runner_rejects_approved_dataset_drift_after_sealing(self) -> None:
        """E 重写 Dataset 与 Manifest 后仍不得通过：Review Seal 批准旧 hash。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            dataset_path = root / "dataset.jsonl"
            dataset_path.write_text(dataset_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["dataset_sha256"] = self._sha(dataset_path)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self._run_sealed(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("dataset_sha256", result.stderr)

    def test_runner_rejects_approved_gold_drift_after_sealing(self) -> None:
        """Gold 内容在 Seal 后变化（含同步改写 Manifest）仍必须 FAIL。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            gold_path = root / "gold.jsonl"
            gold_path.write_text(gold_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["gold_sha256"] = self._sha(gold_path)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self._run_sealed(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("gold_sha256", result.stderr)

    def test_runner_rejects_dataset_sha256_that_does_not_match_input_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["dataset_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self._run_sealed(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("dataset_sha256", result.stderr)

    # ---- P1-B：D13D execution seal 外部可信根 ----

    def test_runner_rejects_whole_chain_rewrite_without_d13d_seal_refresh(self) -> None:
        """改 raw → 重算 hash → 重写 SHA256SUMS → 重写 attestation → 重算 bundle hash，
        但不允许修改 D13D execution seal → Runner FAIL。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            raw_path = root / "safety.jsonl"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["actual"]["critical_gate_bypass_count"] = 1
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            self._refresh_execution_attestation(root, bundle, refresh_d13d_seal=False)
            result = self._run_sealed(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("attestation_sha256", result.stderr)

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
            self._freeze_d13d_seal_attestation(root, bundle)
            result = self._run_sealed(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("environment_id", result.stderr)

    def test_runner_rejects_execution_attestation_with_different_dependency_reference(self) -> None:
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
            self._freeze_d13d_seal_attestation(root, bundle)
            with self.assertRaisesRegex(ValueError, "dependency_version_reference"):
                self._compute(bundle)

    def test_runner_rejects_raw_result_whose_bytes_change_after_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            raw_path = root / "preference.jsonl"
            raw_path.write_text("  " + raw_path.read_text(encoding="utf-8"), encoding="utf-8")
            result = self._run_sealed(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("raw_result_files.preference.sha256", result.stderr)

    # ---- 既有 fail-closed 契约 ----

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

    def test_runner_rejects_repository_candidate_template(self) -> None:
        candidate_bundle = REPOSITORY_ROOT / "evaluation" / "d13e" / "D13E_FORMAL_BUNDLE_V1.json"
        self.assertTrue(candidate_bundle.is_file())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            result = self._run(candidate_bundle, output)
            self.assertEqual(result.returncode, 2)
            self.assertIn("拒绝执行", result.stderr)
            self.assertFalse(output.exists())

    def test_runner_rejects_bundle_not_rooted_in_its_d13d_evidence_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["provenance"]["evidence_directory"] = "another-evidence-directory"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "evidence_directory"):
                self._compute(bundle)

    def test_runner_rejects_threshold_config_with_mismatched_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            threshold_path = root / "thresholds.json"
            thresholds = json.loads(threshold_path.read_text(encoding="utf-8"))
            thresholds["metrics"]["preference"]["minimum_accuracy"] = 0.9
            threshold_path.write_text(json.dumps(thresholds), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "threshold_sha256"):
                self._compute(bundle)

    def test_runner_rejects_dataset_metric_outside_the_four_formal_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            dataset_path = root / "dataset.jsonl"
            gold_path = root / "gold.jsonl"
            dataset_path.write_text(
                dataset_path.read_text(encoding="utf-8")
                + json.dumps({"sample_id": "other-1", "metric": "other", "inclusion_status": "valid"})
                + "\n",
                encoding="utf-8",
            )
            gold_path.write_text(
                gold_path.read_text(encoding="utf-8")
                + json.dumps(
                    {
                        "sample_id": "other-1",
                        "metric": "other",
                        "evaluation_status": "valid",
                        "expected": {},
                        "rationale": "outside four metrics",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["dataset_sha256"] = self._sha(dataset_path)
            manifest["gold_sha256"] = self._sha(gold_path)
            manifest["sample_count"]["total"] = 5
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self._approve_current_hashes()
            with self.assertRaisesRegex(ValueError, "四类正式指标"):
                self._compute(bundle)

    def test_runner_rejects_safety_hard_violation_even_when_expected_fields_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            raw_path = root / "safety.jsonl"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["actual"]["critical_gate_bypass_count"] = 1
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            self._refresh_execution_attestation(root, bundle)
            report = self._compute(bundle)
            self.assertEqual(report["safety"]["gate_status"], "FAIL")  # type: ignore[index]
            self.assertEqual(report["safety"]["errors"][0]["error_type"], "SAFETY_CRITICAL_GATE_BYPASS")  # type: ignore[index]

    def test_runner_rejects_unknown_safety_actual_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            raw_path = root / "safety.jsonl"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["actual"]["unlisted_security_counter"] = 0
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            self._refresh_execution_attestation(root, bundle)
            with self.assertRaisesRegex(ValueError, "未声明字段"):
                self._compute(bundle)

    def test_runner_rejects_boolean_hard_zero_counter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            raw_path = root / "safety.jsonl"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["actual"]["critical_gate_bypass_count"] = False
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            self._refresh_execution_attestation(root, bundle)
            with self.assertRaisesRegex(ValueError, "硬零计数"):
                self._compute(bundle)

    def test_runner_accepts_sha256sums_entry_for_raw_file_in_subdirectory(self) -> None:
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
            report = self._compute(bundle)
            self.assertEqual(report["preference"]["gate_status"], "PASS")  # type: ignore[index]

    def test_runner_outputs_four_computed_metrics_for_complete_verified_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self._write_complete_bundle(root)
            report = self._compute(bundle)
            self.assertEqual(report["status"], "COMPUTED")
            for metric in METRICS:
                self.assertEqual(report[metric]["status"], "COMPUTED")  # type: ignore[index]
                self.assertEqual(report[metric]["correct_count"], 1)  # type: ignore[index]
                self.assertEqual(report[metric]["gate_status"], "PASS")  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
