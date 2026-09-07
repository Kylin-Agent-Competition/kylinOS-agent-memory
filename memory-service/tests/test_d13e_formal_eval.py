"""D13E 正式评测 Runner 的离线公共契约测试（第三轮：签名 Seal + Frozen Trust Root）。

覆盖第三轮剩余 P1（Review Seal / D13D Execution Seal 可离线认证、actual_pr_author
签名绑定、Seal 路径 fail-closed）以及全部既有 fail-closed 回归契约。

测试使用 TEST-ONLY Ed25519 私钥（仅存在于本测试文件），CI 与正式流程绝不使用
正式 D/D13D 私钥；Trust Root 放在 evidence root 之外，用于模拟 D13D 冻结的外部
可信公钥存储。
"""

from __future__ import annotations

import contextlib
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
REVIEW_KEY_ID = "d13e-review-key-v1"
D13D_KEY_ID = "d13d-execution-key-v1"
# TEST-ONLY 种子：禁止用于任何正式环境。
REVIEW_SEED = bytes(range(1, 33))
D13D_SEED = bytes(range(33, 65))
ATTACKER_SEED = bytes(range(65, 97))
_SPEC = importlib.util.spec_from_file_location("d13e_formal_eval_runner", RUNNER)
assert _SPEC is not None and _SPEC.loader is not None
RUNNER_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(RUNNER_MODULE)

# --- TEST-ONLY 纯 Python Ed25519（sign / keygen；verify 与 Runner 内实现同公式） ---
_ED25519_P = 2**255 - 19
_ED25519_L = 2**252 + 27742317777372353535851937790883648493
_ED25519_D = (-121665 * pow(121666, _ED25519_P - 2, _ED25519_P)) % _ED25519_P
_ED25519_SQRT_M1 = pow(2, (_ED25519_P - 1) // 4, _ED25519_P)
_ED25519_BY = (4 * pow(5, _ED25519_P - 2, _ED25519_P)) % _ED25519_P
_ED25519_BX = 15112221349535400772501151409588531511454012693041857206046113283949847762202


def _ed25519_recover_x(y: int, sign: int) -> int:
    p = _ED25519_P
    x2 = ((y * y - 1) * pow(_ED25519_D * y * y + 1, p - 2, p)) % p
    if x2 == 0:
        x = 0
    else:
        x = pow(x2, (p + 3) // 8, p)
        if (x * x - x2) % p != 0:
            x = (x * _ED25519_SQRT_M1) % p
        if (x * x - x2) % p != 0:
            raise ValueError("recover x failed")
    if (x & 1) != sign:
        x = p - x
    return x


def _ed25519_point_add(p1: tuple[int, int], p2: tuple[int, int]) -> tuple[int, int]:
    p = _ED25519_P
    x1, y1 = p1
    x2, y2 = p2
    x3 = ((x1 * y2 + y1 * x2) * pow(1 + _ED25519_D * x1 * x2 * y1 * y2, p - 2, p)) % p
    y3 = ((y1 * y2 + x1 * x2) * pow(1 - _ED25519_D * x1 * x2 * y1 * y2, p - 2, p)) % p
    return x3, y3


def _ed25519_scalar_mult(scalar: int, point: tuple[int, int]) -> tuple[int, int]:
    result: tuple[int, int] = (0, 1)
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = _ed25519_point_add(result, addend)
        addend = _ed25519_point_add(addend, addend)
        scalar >>= 1
    return result


def _ed25519_encode_point(point: tuple[int, int]) -> bytes:
    x, y = point
    encoded = bytearray(int.to_bytes(y, 32, "little"))
    encoded[31] |= (x & 1) << 7
    return bytes(encoded)


def _ed25519_public_key(seed: bytes) -> bytes:
    digest = hashlib.sha512(seed).digest()
    scalar = bytearray(digest[:32])
    scalar[0] &= 248
    scalar[31] &= 127
    scalar[31] |= 64
    point = _ed25519_scalar_mult(int.from_bytes(scalar, "little"), (_ED25519_BX, _ED25519_BY))
    return _ed25519_encode_point(point)


def _ed25519_sign(seed: bytes, message: bytes) -> bytes:
    digest = hashlib.sha512(seed).digest()
    prefix = digest[32:]
    scalar = bytearray(digest[:32])
    scalar[0] &= 248
    scalar[31] &= 127
    scalar[31] |= 64
    public_key = _ed25519_public_key(seed)
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _ED25519_L
    r_point = _ed25519_scalar_mult(r, (_ED25519_BX, _ED25519_BY))
    r_encoded = _ed25519_encode_point(r_point)
    h = int.from_bytes(hashlib.sha512(r_encoded + public_key + message).digest(), "little") % _ED25519_L
    s = (r + h * int.from_bytes(scalar, "little")) % _ED25519_L
    return r_encoded + int.to_bytes(s, 32, "little")


def _der_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(encoded)]) + encoded


def _public_key_spki_pem(raw_key: bytes) -> bytes:
    algorithm = bytes.fromhex("300506032b6570")
    bitstring = b"\x03\x21\x00" + raw_key
    content = algorithm + bitstring
    der = b"\x30" + _der_length(len(content)) + content
    import base64
    b64 = base64.b64encode(der).decode("ascii")
    lines = [b64[i : i + 64] for i in range(0, len(b64), 64)]
    body = "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----\n"
    return body.encode("ascii")


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")



class D13EFormalEvalCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._trust_root: Path | None = None
        self._review_seal_path: Path | None = None
        self._d13d_seal_path: Path | None = None

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @contextlib.contextmanager
    def _evidence(self):
        """返回 (evidence_root, trust_root)；Trust Root 位于 evidence root 之外。"""
        with tempfile.TemporaryDirectory() as directory:
            outer = Path(directory)
            evidence = outer / "evidence"
            trust = outer / "trust"
            evidence.mkdir()
            trust.mkdir()
            self._trust_root = trust
            yield evidence, trust

    def _write_trust_store(self, trust_root: Path) -> None:
        review_pem = _public_key_spki_pem(_ed25519_public_key(REVIEW_SEED))
        d13d_pem = _public_key_spki_pem(_ed25519_public_key(D13D_SEED))
        (trust_root / "d13e-review-public.pem").write_bytes(review_pem)
        (trust_root / "d13d-execution-public.pem").write_bytes(d13d_pem)
        store = {
            "trust_store_version": "d13e-trust-roots/v1",
            "signature_scheme": "ed25519",
            "review": {
                "key_id": REVIEW_KEY_ID,
                "public_key_file": "d13e-review-public.pem",
                "public_key_sha256": self._sha(trust_root / "d13e-review-public.pem"),
            },
            "d13d_execution": {
                "key_id": D13D_KEY_ID,
                "public_key_file": "d13d-execution-public.pem",
                "public_key_sha256": self._sha(trust_root / "d13d-execution-public.pem"),
            },
        }
        (trust_root / "D13E_TRUST_ROOTS_V1.json").write_text(json.dumps(store), encoding="utf-8")

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

    def _write_signed_review_seal(self, root: Path, manifest: dict[str, object], *, seed: bytes = REVIEW_SEED, key_id: str = REVIEW_KEY_ID) -> Path:
        payload: dict[str, object] = {
            "seal_version": "d13e-review-seal/v1",
            "signature_scheme": "ed25519",
            "source_repo": "Kylin-Agent-Competition/kylinOS-agent-memory",
            "source_pr": 148,
            "actual_pr_author": "gaoyizhe934",
            "reviewer_identity": "Ducknesses",
            "reviewer_track": "D",
            "review_state": "APPROVED",
            "review_reference": REVIEW_REFERENCE,
            "reviewed_commit": REVIEW_COMMIT,
            "approved_artifacts": {
                "dataset_sha256": manifest["dataset_sha256"],
                "gold_sha256": manifest["gold_sha256"],
                "threshold_sha256": manifest["threshold_config_sha256"],
                "runner_sha256": self._sha(RUNNER),
                "manifest_sha256": self._sha(root / "manifest.json"),
            },
            "key_id": key_id,
        }
        seal_path = root / "review-seal.json"
        seal_path.write_text(json.dumps(payload), encoding="utf-8")
        signature = _ed25519_sign(seed, _canonical(payload))
        seal_path.with_suffix(".sig").write_bytes(signature)
        return seal_path

    def _write_signed_d13d_seal(self, root: Path, attestation_path: Path, provenance: dict[str, object], evidence_reference: str, *, seed: bytes = D13D_SEED, key_id: str = D13D_KEY_ID) -> Path:
        payload: dict[str, object] = {
            "seal_version": "d13d-execution-seal/v1",
            "signature_scheme": "ed25519",
            "attestation_sha256": self._sha(attestation_path),
            "implementation_commit": provenance["implementation_commit"],
            "environment_id": provenance["environment_id"],
            "dependency_version_reference": provenance["dependency_version_reference"],
            "data_version_reference": provenance["data_version_reference"],
            "evidence_root": evidence_reference,
            "evidence_reference": evidence_reference,
            "frozen_by_track": "D",
            "approval_reference": "https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/commit/" + "a" * 40,
            "key_id": key_id,
        }
        seal_path = root / "d13d-seal.json"
        seal_path.write_text(json.dumps(payload), encoding="utf-8")
        signature = _ed25519_sign(seed, _canonical(payload))
        seal_path.with_suffix(".sig").write_bytes(signature)
        return seal_path

    def _refresh_execution_attestation(self, root: Path, bundle: Path, *, refresh_d13d_seal: bool = True) -> None:
        """TEST-ONLY：重算 raw → SHA256SUMS → attestation → bundle hash。

        refresh_d13d_seal=True 模拟 D13D 重新冻结（重新签名）；False 保留旧签名，
        用于构造“无 D13D 私钥的整链重写”攻击。
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
            assert self._d13d_seal_path is not None
            self._d13d_seal_path.unlink()
            self._d13d_seal_path.with_suffix(".sig").unlink()
            provenance = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["provenance"]
            evidence_reference = provenance["evidence_reference"]
            self._d13d_seal_path = self._write_signed_d13d_seal(root, attestation_path, provenance, evidence_reference)

    def _approve_current_hashes(self, root: Path) -> None:
        """TEST-ONLY：以当前工件哈希重新生成并签名 Review Seal，模拟新的外部批准。"""
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        assert self._review_seal_path is not None
        self._review_seal_path.unlink()
        self._review_seal_path.with_suffix(".sig").unlink()
        self._review_seal_path = self._write_signed_review_seal(root, manifest)

    def _compute(self, bundle: Path, *, trust_root: Path | None = None) -> dict[str, object]:
        assert self._review_seal_path is not None and self._d13d_seal_path is not None
        return RUNNER_MODULE._compute_formal_report_with_verified_trust_root(
            bundle,
            self._review_seal_path,
            self._d13d_seal_path,
            trust_root if trust_root is not None else self._trust_root,
        )

    def _write_complete_bundle(self, root: Path, trust_root: Path) -> Path:
        """写入已冻结的完整证据目录 + 签名双 Seal；Trust Root 在 evidence root 之外。"""
        self._write_trust_store(trust_root)
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
        self._review_seal_path = self._write_signed_review_seal(root, manifest)
        self._d13d_seal_path = self._write_signed_d13d_seal(root, attestation_path, provenance, evidence_reference)
        return bundle_path


    # ---- TEST-ONLY Ed25519 正确性 ----

    def test_ed25519_helpers_match_rfc8032_vector(self) -> None:
        seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        public_key = _ed25519_public_key(seed)
        self.assertEqual(
            public_key.hex(),
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        )
        signature = _ed25519_sign(seed, b"")
        self.assertEqual(
            signature.hex(),
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555f"
            "b8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
        )

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

    # ---- P1-A / R1：Review Seal 签名认证 ----

    def test_signed_sealing_timing_commit_then_review_then_immutable_artifacts(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            report = self._compute(bundle)
            self.assertEqual(report["status"], "COMPUTED")
            provenance = report["provenance"]  # type: ignore[index]
            self.assertEqual(provenance["reviewed_commit"], REVIEW_COMMIT)
            self.assertEqual(provenance["actual_pr_author"], "gaoyizhe934")
            self.assertEqual(provenance["reviewer_identity"], "Ducknesses")
            self.assertEqual(provenance["review_key_id"], REVIEW_KEY_ID)
            self.assertRegex(provenance["review_key_fingerprint"], "^[0-9a-f]{64}$")
            self.assertRegex(provenance["d13d_key_fingerprint"], "^[0-9a-f]{64}$")
            for metric in METRICS:
                self.assertEqual(report[metric]["gate_status"], "PASS")  # type: ignore[index]

    def test_approved_artifacts_contain_no_review_self_reference(self) -> None:
        with self._evidence() as (root, trust):
            self._write_complete_bundle(root, trust)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            thresholds = json.loads((root / "thresholds.json").read_text(encoding="utf-8"))
            gold_records = [json.loads(line) for line in (root / "gold.jsonl").read_text(encoding="utf-8").splitlines()]
            for key in ("approval_status", "approval_reference", "approved_by"):
                self.assertNotIn(key, thresholds)
            self.assertNotIn("seal_status", manifest)
            self.assertNotIn("review", manifest)
            self.assertEqual(manifest["required_reviewer_track"], "D")
            for record in gold_records:
                self.assertNotIn("gold_status", record)

    def test_runner_rejects_frozen_bundle_without_external_seals(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            result = self._run(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--review-seal", result.stderr)

    def test_runner_rejects_missing_trust_root_directory(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            missing = trust / "missing"
            with self.assertRaisesRegex(ValueError, "trust root"):
                self._compute(bundle, trust_root=missing)

    def test_review_seal_state_tamper_rejected(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            seal_path = root / "review-seal.json"
            seal = json.loads(seal_path.read_text(encoding="utf-8"))
            seal["review_state"] = "PENDING"
            seal_path.write_text(json.dumps(seal), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "review_state|signature"):
                self._compute(bundle)
            # schema 合法字段（reviewed_commit）被篡改 → 必须因签名不匹配拒绝。
            self._write_signed_review_seal(root, json.loads((root / "manifest.json").read_text(encoding="utf-8")))
            seal = json.loads(seal_path.read_text(encoding="utf-8"))
            seal["reviewed_commit"] = "b" * 40
            seal_path.write_text(json.dumps(seal), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "signature"):
                self._compute(bundle)

    def test_review_seal_actual_pr_author_tamper_rejected(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            seal_path = root / "review-seal.json"
            seal = json.loads(seal_path.read_text(encoding="utf-8"))
            seal["actual_pr_author"] = "someone-else"
            seal_path.write_text(json.dumps(seal), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "signature"):
                self._compute(bundle)

    def test_reviewer_equal_to_actual_pr_author_rejected(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            seal_path = root / "review-seal.json"
            payload = json.loads(seal_path.read_text(encoding="utf-8"))
            payload["actual_pr_author"] = "Ducknesses"
            payload["reviewer_identity"] = "Ducknesses"
            seal_path.write_text(json.dumps(payload), encoding="utf-8")
            (root / "review-seal.sig").write_bytes(_ed25519_sign(REVIEW_SEED, _canonical(payload)))
            with self.assertRaisesRegex(ValueError, "非作者"):
                self._compute(bundle)

    def test_fake_approved_review_without_trusted_key_rejected(self) -> None:
        """T25：引用真实 CHANGES_REQUESTED Review（5120706798）伪造 APPROVED，
        即使签名自洽，只要没有可信 D 私钥 → FAIL(signature)。"""
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            seal_path = root / "review-seal.json"
            payload = json.loads(seal_path.read_text(encoding="utf-8"))
            # 攻击者用自己的 key 签名，但仍声称合法 key_id → 验签必须失败。
            (root / "review-seal.sig").write_bytes(_ed25519_sign(ATTACKER_SEED, _canonical(payload)))
            with self.assertRaisesRegex(ValueError, "signature"):
                self._compute(bundle)

    def test_attacker_review_key_not_in_trust_root_rejected(self) -> None:
        """T29：攻击者把自建公钥放进 evidence root 仍无效；Runner 只信 frozen trust root。"""
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            attacker_public = _ed25519_public_key(ATTACKER_SEED)
            (root / "attacker-review-public.pem").write_bytes(_public_key_spki_pem(attacker_public))
            payload = {
                "seal_version": "d13e-review-seal/v1",
                "signature_scheme": "ed25519",
                "source_repo": "Kylin-Agent-Competition/kylinOS-agent-memory",
                "source_pr": 148,
                "actual_pr_author": "gaoyizhe934",
                "reviewer_identity": "Ducknesses",
                "reviewer_track": "D",
                "review_state": "APPROVED",
                "review_reference": REVIEW_REFERENCE,
                "reviewed_commit": REVIEW_COMMIT,
                "approved_artifacts": {
                    "dataset_sha256": json.loads((root / "manifest.json").read_text(encoding="utf-8"))["dataset_sha256"],
                    "gold_sha256": "0" * 64,
                    "threshold_sha256": "0" * 64,
                    "runner_sha256": "0" * 64,
                    "manifest_sha256": "0" * 64,
                },
                "key_id": "attacker-review-key",
            }
            seal_path = root / "review-seal.json"
            seal_path.write_text(json.dumps(payload), encoding="utf-8")
            (root / "review-seal.sig").write_bytes(_ed25519_sign(ATTACKER_SEED, _canonical(payload)))
            with self.assertRaises(ValueError):
                self._compute(bundle)

    # ---- R3：actual_pr_author 签名绑定 ----

    def test_manifest_sha256_is_approved_and_bound(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            manifest_path = root / "manifest.json"
            # 只改 Manifest（approved_artifacts.manifest_sha256 旧值）→ FAIL。
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["created_at"] = "2026-09-06"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest_sha256"):
                self._compute(bundle)

    # ---- 回归：既有 fail-closed 契约（沿用旧语义，不加同义用例） ----

    def test_runner_rejects_candidate_bundle_without_d13d_provenance(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
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

    def test_runner_rejects_approved_dataset_drift_after_sealing(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            dataset_path = root / "dataset.jsonl"
            dataset_path.write_text(dataset_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["dataset_sha256"] = self._sha(dataset_path)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "dataset_sha256"):
                self._compute(bundle)

    def test_runner_rejects_approved_gold_drift_after_sealing(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            gold_path = root / "gold.jsonl"
            gold_path.write_text(gold_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["gold_sha256"] = self._sha(gold_path)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "gold_sha256"):
                self._compute(bundle)

    def test_runner_rejects_dataset_sha256_that_does_not_match_input_file(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["dataset_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self._run(bundle, root / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("dataset_sha256", result.stderr)

    def test_runner_rejects_raw_result_whose_bytes_change_after_attestation(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            raw_path = root / "preference.jsonl"
            raw_path.write_text("  " + raw_path.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "raw_result_files.preference.sha256"):
                self._compute(bundle)


    # ---- R2：D13D Execution Seal 签名认证 ----

    def test_d13d_seal_whole_chain_rewrite_without_refresh_rejected(self) -> None:
        """T30a：改 raw→重算 hash→重写 SHA256SUMS→attestation→bundle hash，
        不更新 D13D execution seal（无 D13D 私钥）→ FAIL。"""
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            raw_path = root / "safety.jsonl"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["actual"]["critical_gate_bypass_count"] = 1
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            self._refresh_execution_attestation(root, bundle, refresh_d13d_seal=False)
            with self.assertRaisesRegex(ValueError, "attestation_sha256"):
                self._compute(bundle)

    def test_d13d_seal_rewrite_with_attacker_signature_rejected(self) -> None:
        """T30b：攻击者用自建 key 重签 D13D seal → 验签失败。"""
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            payload = json.loads(bundle.read_text(encoding="utf-8"))
            attestation_path = root / payload["execution_attestation_file"]
            provenance = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["provenance"]
            evidence_reference = provenance["evidence_reference"]
            fake_payload = {
                "seal_version": "d13d-execution-seal/v1",
                "signature_scheme": "ed25519",
                "attestation_sha256": self._sha(attestation_path),
                "implementation_commit": provenance["implementation_commit"],
                "environment_id": provenance["environment_id"],
                "dependency_version_reference": provenance["dependency_version_reference"],
                "data_version_reference": provenance["data_version_reference"],
                "evidence_root": evidence_reference,
                "evidence_reference": evidence_reference,
                "frozen_by_track": "D",
                "approval_reference": "https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory/commit/" + "a" * 40,
                "key_id": D13D_KEY_ID,
            }
            seal_path = root / "d13d-seal.json"
            seal_path.write_text(json.dumps(fake_payload), encoding="utf-8")
            (root / "d13d-seal.sig").write_bytes(_ed25519_sign(ATTACKER_SEED, _canonical(fake_payload)))
            with self.assertRaisesRegex(ValueError, "signature"):
                self._compute(bundle)

    def test_attacker_d13d_key_not_in_trust_root_rejected(self) -> None:
        """T31：攻击者自建 D13D key 并放入 evidence root → 仍 FAIL（untrusted key）。"""
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            (root / "attacker-d13d-public.pem").write_bytes(_public_key_spki_pem(_ed25519_public_key(ATTACKER_SEED)))
            payload = json.loads((root / "d13d-seal.json").read_text(encoding="utf-8"))
            payload["key_id"] = "attacker-d13d-key"
            (root / "d13d-seal.json").write_text(json.dumps(payload), encoding="utf-8")
            (root / "d13d-seal.sig").write_bytes(_ed25519_sign(ATTACKER_SEED, _canonical(payload)))
            with self.assertRaises(ValueError):
                self._compute(bundle)

    def test_d13d_seal_identity_tamper_rejected(self) -> None:
        """签名后修改 D13D seal 的 environment_id → FAIL(signature)。"""
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            seal_path = root / "d13d-seal.json"
            seal = json.loads(seal_path.read_text(encoding="utf-8"))
            seal["environment_id"] = "Kylin-D13D-other"
            seal_path.write_text(json.dumps(seal), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "signature"):
                self._compute(bundle)

    # ---- R4：Seal 路径 fail-closed ----

    def test_review_seal_outside_evidence_root_rejected(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            outside = root.parent / "outside"
            outside.mkdir()
            (outside / "review-seal.json").write_bytes((root / "review-seal.json").read_bytes())
            (outside / "review-seal.sig").write_bytes((root / "review-seal.sig").read_bytes())
            with self.assertRaisesRegex(ValueError, "证据目录"):
                RUNNER_MODULE._compute_formal_report_with_verified_trust_root(
                    bundle, outside / "review-seal.json", self._d13d_seal_path, trust
                )

    def test_d13d_seal_outside_evidence_root_rejected(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            outside = root.parent / "outside"
            outside.mkdir()
            (outside / "d13d-seal.json").write_bytes((root / "d13d-seal.json").read_bytes())
            (outside / "d13d-seal.sig").write_bytes((root / "d13d-seal.sig").read_bytes())
            with self.assertRaisesRegex(ValueError, "证据目录"):
                RUNNER_MODULE._compute_formal_report_with_verified_trust_root(
                    bundle, self._review_seal_path, outside / "d13d-seal.json", trust
                )

    # ---- T34：signature 文件异常 fail-closed ----

    def _assert_review_signature_anomaly_rejected(self, mutate) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            mutate(root / "review-seal.sig", root / "review-seal.json")
            with self.assertRaises(ValueError):
                self._compute(bundle)

    def test_missing_review_signature_file_rejected(self) -> None:
        self._assert_review_signature_anomaly_rejected(lambda sig, _: sig.unlink())

    def test_empty_review_signature_file_rejected(self) -> None:
        self._assert_review_signature_anomaly_rejected(lambda sig, _: sig.write_bytes(b""))

    def test_malformed_short_review_signature_rejected(self) -> None:
        self._assert_review_signature_anomaly_rejected(lambda sig, _: sig.write_bytes(b"\x00" * 32))

    def test_wrong_review_signature_rejected(self) -> None:
        self._assert_review_signature_anomaly_rejected(lambda sig, _: sig.write_bytes(b"\x00" * 64))

    def test_wrong_review_key_id_rejected(self) -> None:
        def mutate(sig_path, seal_path):
            seal = json.loads(seal_path.read_text(encoding="utf-8"))
            seal["key_id"] = "attacker-review-key"
            seal_path.write_text(json.dumps(seal), encoding="utf-8")
        self._assert_review_signature_anomaly_rejected(mutate)

    # ---- 回归：既有契约保持不变 ----

    def test_runner_rejects_execution_attestation_for_a_different_environment(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            payload = json.loads(bundle.read_text(encoding="utf-8"))
            attestation_path = root / payload["execution_attestation_file"]
            attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
            attestation["environment_id"] = "Kylin-D13D-other"
            attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
            payload["execution_attestation_sha256"] = self._sha(attestation_path)
            bundle.write_text(json.dumps(payload), encoding="utf-8")
            # D13D 对新的 attestation digest 重新冻结（重新签名）。
            self._d13d_seal_path.unlink()  # type: ignore[union-attr]
            self._d13d_seal_path.with_suffix(".sig").unlink()  # type: ignore[union-attr]
            provenance = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["provenance"]
            self._d13d_seal_path = self._write_signed_d13d_seal(root, attestation_path, provenance, provenance["evidence_reference"])
            with self.assertRaisesRegex(ValueError, "environment_id"):
                self._compute(bundle)

    def test_runner_rejects_execution_attestation_with_different_dependency_reference(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            payload = json.loads(bundle.read_text(encoding="utf-8"))
            attestation_path = root / payload["execution_attestation_file"]
            attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
            attestation["dependency_version_reference"] = "different-dependencies"
            attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
            payload["execution_attestation_sha256"] = self._sha(attestation_path)
            bundle.write_text(json.dumps(payload), encoding="utf-8")
            self._d13d_seal_path.unlink()  # type: ignore[union-attr]
            self._d13d_seal_path.with_suffix(".sig").unlink()  # type: ignore[union-attr]
            provenance = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["provenance"]
            self._d13d_seal_path = self._write_signed_d13d_seal(root, attestation_path, provenance, provenance["evidence_reference"])
            with self.assertRaisesRegex(ValueError, "dependency_version_reference"):
                self._compute(bundle)

    def test_runner_rejects_bundle_not_rooted_in_its_d13d_evidence_directory(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["provenance"]["evidence_directory"] = "another-evidence-directory"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self._approve_current_hashes(root)
            with self.assertRaisesRegex(ValueError, "evidence_directory"):
                self._compute(bundle)

    def test_runner_rejects_threshold_config_with_mismatched_sha256(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            threshold_path = root / "thresholds.json"
            thresholds = json.loads(threshold_path.read_text(encoding="utf-8"))
            thresholds["metrics"]["preference"]["minimum_accuracy"] = 0.9
            threshold_path.write_text(json.dumps(thresholds), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "threshold_sha256"):
                self._compute(bundle)

    def test_runner_rejects_dataset_metric_outside_the_four_formal_metrics(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
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
            self._approve_current_hashes(root)
            with self.assertRaisesRegex(ValueError, "四类正式指标"):
                self._compute(bundle)

    def test_runner_rejects_safety_hard_violation_even_when_expected_fields_match(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            raw_path = root / "safety.jsonl"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["actual"]["critical_gate_bypass_count"] = 1
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            self._refresh_execution_attestation(root, bundle)
            report = self._compute(bundle)
            self.assertEqual(report["safety"]["gate_status"], "FAIL")  # type: ignore[index]
            self.assertEqual(report["safety"]["errors"][0]["error_type"], "SAFETY_CRITICAL_GATE_BYPASS")  # type: ignore[index]

    def test_runner_rejects_unknown_safety_actual_field(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            raw_path = root / "safety.jsonl"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["actual"]["unlisted_security_counter"] = 0
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            self._refresh_execution_attestation(root, bundle)
            with self.assertRaisesRegex(ValueError, "未声明字段"):
                self._compute(bundle)

    def test_runner_rejects_boolean_hard_zero_counter(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            raw_path = root / "safety.jsonl"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["actual"]["critical_gate_bypass_count"] = False
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            self._refresh_execution_attestation(root, bundle)
            with self.assertRaisesRegex(ValueError, "硬零计数"):
                self._compute(bundle)

    def test_runner_accepts_sha256sums_entry_for_raw_file_in_subdirectory(self) -> None:
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
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
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            report = self._compute(bundle)
            self.assertEqual(report["status"], "COMPUTED")
            for metric in METRICS:
                self.assertEqual(report[metric]["status"], "COMPUTED")  # type: ignore[index]
                self.assertEqual(report[metric]["correct_count"], 1)  # type: ignore[index]
                self.assertEqual(report[metric]["gate_status"], "PASS")  # type: ignore[index]


    # ---- 第四轮：Formal Trust Root 固定系统路径（T35–T41） ----

    def test_cli_rejects_trust_roots_override(self) -> None:
        environment = dict(os.environ, PYTHONPATH=str(REPOSITORY_ROOT / "memory-service"))
        result = subprocess.run(
            [sys.executable, str(RUNNER), "bundle.json", "--trust-roots", "/tmp/attacker-trust", "--output", "report.json"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--trust-roots", result.stderr)

    def test_cli_help_has_no_trust_roots_option(self) -> None:
        environment = dict(os.environ, PYTHONPATH=str(REPOSITORY_ROOT / "memory-service"))
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--help"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("--trust-roots", result.stdout)
        self.assertNotIn("trust_root", result.stdout)

    def test_formal_api_has_no_trust_root_override(self) -> None:
        import inspect
        parameters = inspect.signature(RUNNER_MODULE.compute_formal_report).parameters
        self.assertNotIn("trust_root", parameters)
        self.assertNotIn("trust_root_dir", parameters)
        self.assertTrue(hasattr(RUNNER_MODULE, "_compute_formal_report_with_verified_trust_root"))

    def test_attacker_signed_seals_rejected_by_legit_trust_root(self) -> None:
        """T36 lower-level：attacker 用自建私钥签名双 Seal，用固定合法 trust root 验签必须 FAIL。"""
        with self._evidence() as (root, trust):
            bundle = self._write_complete_bundle(root, trust)
            review_payload = json.loads((root / "review-seal.json").read_text(encoding="utf-8"))
            (root / "review-seal.sig").write_bytes(_ed25519_sign(ATTACKER_SEED, _canonical(review_payload)))
            d13d_payload = json.loads((root / "d13d-seal.json").read_text(encoding="utf-8"))
            (root / "d13d-seal.sig").write_bytes(_ed25519_sign(ATTACKER_SEED, _canonical(d13d_payload)))
            with self.assertRaisesRegex(ValueError, "signature"):
                self._compute(bundle)

    def test_trust_metadata_rejects_symlink(self) -> None:
        for want_dir in (True, False):
            with self.assertRaisesRegex(ValueError, "symlink"):
                RUNNER_MODULE._check_trust_metadata(
                    is_symlink=True,
                    is_dir=want_dir,
                    is_file=not want_dir,
                    uid=0,
                    mode=0o700,
                    label="trust path",
                    want_dir=want_dir,
                )

    def test_trust_metadata_rejects_writable_by_group_or_other(self) -> None:
        for mode in (0o777, 0o775, 0o666):
            with self.assertRaisesRegex(ValueError, "group/other"):
                RUNNER_MODULE._check_trust_metadata(
                    is_symlink=False,
                    is_dir=True,
                    is_file=False,
                    uid=0,
                    mode=mode,
                    label="trust path",
                    want_dir=True,
                )

    def test_trust_metadata_rejects_unknown_owner(self) -> None:
        with self.assertRaisesRegex(ValueError, "root"):
            RUNNER_MODULE._check_trust_metadata(
                is_symlink=False,
                is_dir=True,
                is_file=False,
                uid=1000,
                mode=0o700,
                label="trust path",
                want_dir=True,
            )

    def test_trust_metadata_accepts_frozen_directory(self) -> None:
        RUNNER_MODULE._check_trust_metadata(
            is_symlink=False,
            is_dir=True,
            is_file=False,
            uid=0,
            mode=0o700,
            label="trust path",
            want_dir=True,
        )

    @unittest.skipUnless(os.name == "posix", "real-fs metadata gate requires POSIX")
    def test_trust_root_metadata_gate_on_real_fs_posix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "trust"
            target.mkdir(mode=0o777)
            with self.assertRaises(ValueError):
                RUNNER_MODULE._require_trust_metadata(target, want_dir=True, label="trust path")


if __name__ == "__main__":
    unittest.main()
