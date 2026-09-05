"""D13E 正式评测 CLI（候选实现）。

正式执行路径完全离线：Runner 只读取本地证据目录中的 Bundle、Manifest、
阈值、四类 raw、D13D execution attestation，以及两个由 D 轨外部流程冻结并
签名的 Seal 工件：

- D13E_REVIEW_SEAL_V1.json / D13E_REVIEW_SEAL_V1.sig
- D13D_EXECUTION_SEAL_V1.json / D13D_EXECUTION_SEAL_V1.sig

Runner 不访问 GitHub API；被审批工件（Dataset / Gold / Threshold / Runner /
Manifest）也不保存“谁批准 / 哪个 Review 批准 / 当前是否批准”等自报字段。
“谁有权生成 APPROVED / FROZEN 这两个事实”由以下结构证明：

- D / D13D 私钥对 canonical payload 做 Ed25519 detached signature；
- 公钥只来自 D13D 冻结的、位于 evidence root 之外的 frozen trust store；
- Runner 在无网络 VM 中离线验签。

被审批工件与两个 Seal/.sig 必须位于同一 D13D 唯一证据目录；Trust Root 必须
位于该证据目录之外。任何签名、路径、provenance、哈希或指标失败都会 fail-closed，
非零退出且不写正式报告。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFETY_HARD_ZERO_COUNTERS = frozenset(
    {
        "critical_gate_bypass_count",
        "normal_memory_write_count",
        "audit_plaintext_leak_count",
        "cross_user_violation_count",
    }
)
_FORGET_HARD_ZERO_COUNTERS = frozenset(
    {
        "missed_target_items",
        "wrongly_deleted_items",
        "cross_user_violation_count",
        "residual_after_realtime_query",
        "residual_after_full_rebuild",
    }
)
_GITHUB_REVIEW_REFERENCE = re.compile(
    r"^https://github\.com/Kylin-Agent-Competition/kylinOS-agent-memory/pull/148#pullrequestreview-([0-9]+)$"
)
_TRUSTED_D_REVIEWER_IDENTITIES = frozenset({"Ducknesses"})
_REVIEW_SEAL_VERSION = "d13e-review-seal/v1"
_D13D_EXECUTION_SEAL_VERSION = "d13d-execution-seal/v1"
_TRUST_STORE_VERSION = "d13e-trust-roots/v1"
_SIGNATURE_SCHEME = "ed25519"
_DEFAULT_TRUST_ROOT = Path("/etc/kylin-memory/trust")
_TRUST_STORE_FILE = "D13E_TRUST_ROOTS_V1.json"
_REVIEW_TRUST_KEY = "review"
_D13D_TRUST_KEY = "d13d_execution"

# --- Ed25519 常量（RFC 8032） ---
_ED25519_P = 2**255 - 19
_ED25519_L = 2**252 + 27742317777372353535851937790883648493
_ED25519_D = (-121665 * pow(121666, _ED25519_P - 2, _ED25519_P)) % _ED25519_P
_ED25519_SQRT_M1 = pow(2, (_ED25519_P - 1) // 4, _ED25519_P)
_ED25519_BY = (4 * pow(5, _ED25519_P - 2, _ED25519_P)) % _ED25519_P


def _ed25519_recover_x(y: int, sign: int) -> int:
    p = _ED25519_P
    d = _ED25519_D
    x2 = ((y * y - 1) * pow(d * y * y + 1, p - 2, p)) % p
    if x2 == 0:
        x = 0
    else:
        x = pow(x2, (p + 3) // 8, p)
        if (x * x - x2) % p != 0:
            x = (x * _ED25519_SQRT_M1) % p
        if (x * x - x2) % p != 0:
            raise ValueError("无法恢复 Ed25519 点的 x 坐标")
    if (x & 1) != sign:
        x = p - x
    return x


def _ed25519_point_add(p1: tuple[int, int], p2: tuple[int, int]) -> tuple[int, int]:
    p = _ED25519_P
    d = _ED25519_D
    x1, y1 = p1
    x2, y2 = p2
    x1y2 = (x1 * y2) % p
    y1x2 = (y1 * x2) % p
    y1y2 = (y1 * y2) % p
    x1x2 = (x1 * x2) % p
    d_x1x2y1y2 = (d * x1x2 * y1y2) % p
    x3 = ((x1y2 + y1x2) * pow(1 + d_x1x2y1y2, p - 2, p)) % p
    y3 = ((y1y2 + x1x2) * pow(1 - d_x1x2y1y2, p - 2, p)) % p
    return x3, y3


def _ed25519_scalar_mult(scalar: int, point: tuple[int, int]) -> tuple[int, int]:
    result: tuple[int, int] = (0, 1)  # identity
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = _ed25519_point_add(result, addend)
        addend = _ed25519_point_add(addend, addend)
        scalar >>= 1
    return result


def _ed25519_point_decode(encoded: bytes) -> tuple[int, int]:
    if len(encoded) != 32:
        raise ValueError("Ed25519 点编码长度必须为 32 字节")
    y = int.from_bytes(encoded, "little") & ((1 << 255) - 1)
    if y >= _ED25519_P:
        raise ValueError("Ed25519 点 y 坐标越界")
    sign = (encoded[31] >> 7) & 1
    return _ed25519_recover_x(y, sign), y


def _ed25519_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """RFC 8032 Ed25519 验签（纯 Python，供离线 Runner 使用）。"""
    if len(public_key) != 32 or len(signature) != 64:
        return False
    r_encoded = signature[:32]
    s_bytes = signature[32:]
    s = int.from_bytes(s_bytes, "little")
    if s >= _ED25519_L:
        return False
    try:
        a_point = _ed25519_point_decode(public_key)
        r_point = _ed25519_point_decode(r_encoded)
    except ValueError:
        return False
    digest = hashlib.sha512(r_encoded + public_key + message).digest()
    h = int.from_bytes(digest, "little") % _ED25519_L
    sb = _ed25519_scalar_mult(s, (_ED25519_BX, _ED25519_BY))
    ha = _ed25519_scalar_mult(h, a_point)
    r_plus_ha = _ed25519_point_add(r_point, ha)
    return sb == r_plus_ha


_ED25519_BX = _ed25519_recover_x(_ED25519_BY, 0)


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """签名合同：稳定 key 顺序、紧凑分隔符、UTF-8，不含 signature 自身。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_ed25519_public_key_pem(pem_bytes: bytes) -> bytes:
    """解析 PKIX 'BEGIN PUBLIC KEY' 中的 Ed25519 32 字节原始公钥。"""
    text = pem_bytes.decode("utf-8", errors="strict")
    if "-----BEGIN PUBLIC KEY-----" not in text or "-----END PUBLIC KEY-----" not in text:
        raise ValueError("trust root 公钥必须是 PEM 格式（BEGIN PUBLIC KEY）")
    b64 = "".join(
        line.strip()
        for line in text.splitlines()
        if line.strip() and "-----" not in line
    )
    try:
        der = base64.b64decode(b64, validate=True)
    except Exception as exc:  # noqa: BLE001 -- 统一按 trust root 无效处理
        raise ValueError("trust root 公钥 PEM base64 解码失败") from exc
    # 顶层 SEQUENCE 内的第二个元素应为 BIT STRING(0x03)。
    if len(der) < 8 or der[0] != 0x30:
        raise ValueError("trust root 公钥 DER 不是 SEQUENCE")
    pos = 2
    if der[1] & 0x80:
        length_bytes = der[1] & 0x7F
        pos += length_bytes
    # 遍历顶层子元素，找到 BIT STRING。
    while pos < len(der):
        if der[pos] != 0x03:
            tag_len = der[pos + 1] if pos + 1 < len(der) else 0
            pos += 2 + (tag_len if not (tag_len & 0x80) else (tag_len & 0x7F) + 1)
            continue
        bit_string_header = pos + 1
        if bit_string_header >= len(der):
            raise ValueError("trust root 公钥 DER BIT STRING 缺失")
        length = der[bit_string_header]
        value_start = bit_string_header + 1
        if length & 0x80:
            count = length & 0x7F
            length = int.from_bytes(der[bit_string_header + 1 : bit_string_header + 1 + count], "big")
            value_start = bit_string_header + 1 + count
        value = der[value_start : value_start + length]
        if len(value) == 33 and value[0] == 0:
            raw = value[1:]
            if len(raw) == 32:
                return raw
        break
    raise ValueError("trust root 公钥 DER 中未找到 Ed25519 BIT STRING")


def _required_text(mapping: dict[str, Any], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip() or value.upper() == "UNKNOWN":
        raise ValueError(f"{label}.{key} 必须是非空且非 UNKNOWN 的文本")
    return value


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} 文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} 不是合法 JSON：{path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} 顶层必须是 JSON 对象")
    return raw


def _read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ValueError(f"{label} 文件不存在：{path}") from exc
    if not lines:
        raise ValueError(f"{label} 不得为空")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise ValueError(f"{label} 第 {line_number} 行不得为空")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} 第 {line_number} 行不是合法 JSON") from exc
        if not isinstance(record, dict):
            raise ValueError(f"{label} 第 {line_number} 行必须是 JSON 对象")
        records.append(record)
    return records


def _record_map(records: Iterable[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for record in records:
        sample_id = record.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ValueError(f"{label} 每条记录都必须有非空 sample_id")
        if sample_id in mapped:
            raise ValueError(f"{label} sample_id 不得重复：{sample_id}")
        mapped[sample_id] = record
    return mapped


def _relative_file(base: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空相对路径")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{label} 必须位于 bundle 目录内")
    resolved = (base / candidate).resolve()
    if base not in resolved.parents:
        raise ValueError(f"{label} 越出 bundle 目录")
    return resolved


def _require_path_inside_evidence_root(base: Path, path: Path, label: str) -> Path:
    """R4：Seal / .sig 必须位于 bundle/evidence root 内，拒绝绝对外部路径、../ 与 symlink 逃逸。"""
    resolved = path.resolve()
    base_resolved = base.resolve()
    if resolved != base_resolved and base_resolved not in resolved.parents:
        raise ValueError(f"{label} 必须位于 D13D 唯一证据目录内：{resolved}")
    return resolved


def _validated_evidence_directory(bundle_base: Path, provenance: dict[str, Any]) -> Path:
    """正式 Bundle 必须已由 D13D 部署到唯一证据目录的根部。"""
    if provenance.get("evidence_directory") != ".":
        raise ValueError("provenance.evidence_directory 必须为 '.'，即 Bundle 根必须是 D13D 唯一证据目录")
    return bundle_base


def _verify_sha256(path: Path, expected: object, label: str) -> None:
    if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
        raise ValueError(f"{label} 必须是 64 位小写十六进制 SHA-256")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"{label} 与 {path.name} 实际内容不一致")


def _load_trust_root_entry(trust_root_dir: Path, role: str) -> tuple[str, bytes, str]:
    """Gate 0：读取 frozen trust store 中指定角色的 (key_id, 原始公钥, key_sha256)。

    Trust Root 必须位于 evidence root 之外；攻击者替换 evidence 目录内的文件
    无法影响这里的可信公钥。
    """
    if not trust_root_dir.is_dir():
        raise ValueError(f"frozen trust root 目录不存在：{trust_root_dir}")
    store_path = trust_root_dir / _TRUST_STORE_FILE
    store = _read_json(store_path, "trust store")
    if store.get("trust_store_version") != _TRUST_STORE_VERSION:
        raise ValueError("trust store 的 trust_store_version 不正确")
    if store.get("signature_scheme") != _SIGNATURE_SCHEME:
        raise ValueError(f"trust store 的 signature_scheme 必须为 {_SIGNATURE_SCHEME}")
    entry = store.get(role)
    if not isinstance(entry, dict):
        raise ValueError(f"trust store 缺少 {role} 信任根条目")
    key_id = _required_text(entry, "key_id", f"trust store.{role}")
    pem_file_name = _required_text(entry, "public_key_file", f"trust store.{role}")
    key_sha256 = _required_text(entry, "public_key_sha256", f"trust store.{role}")
    if not _SHA256.fullmatch(key_sha256):
        raise ValueError(f"trust store.{role}.public_key_sha256 必须是 64 位 SHA-256")
    pem_path = (trust_root_dir / Path(pem_file_name)).resolve()
    trust_root_resolved = trust_root_dir.resolve()
    if trust_root_resolved not in pem_path.parents:
        raise ValueError(f"trust store.{role}.public_key_file 越出 trust root 目录")
    if not pem_path.is_file():
        raise ValueError(f"trust root 公钥文件不存在：{pem_path}")
    _verify_sha256(pem_path, key_sha256, f"trust store.{role}.public_key_sha256")
    raw_key = _load_ed25519_public_key_pem(pem_path.read_bytes())
    if len(raw_key) != 32:
        raise ValueError(f"trust store.{role} 公钥必须是 32 字节 Ed25519 公钥")
    return key_id, raw_key, key_sha256


def _verify_detached_signature(public_key: bytes, message: bytes, signature_path: Path, label: str) -> None:
    """Gate 2/5：读取 detached signature 并离线验签；异常一律 fail-closed。"""
    if not signature_path.is_file():
        raise ValueError(f"{label} 的 detached signature 文件不存在：{signature_path}")
    try:
        signature = signature_path.read_bytes()
    except OSError as exc:
        raise ValueError(f"{label} 的 detached signature 无法读取") from exc
    if len(signature) != 64:
        raise ValueError(f"{label} 的 detached signature 长度必须为 64 字节（Ed25519）")
    if not _ed25519_verify(public_key, message, signature):
        raise ValueError(f"{label} 的 detached signature 校验失败")


def _seal_signature_path(seal_path: Path) -> Path:
    """D13E_REVIEW_SEAL_V1.json -> D13E_REVIEW_SEAL_V1.sig"""
    return seal_path.with_suffix(".sig")


def _load_and_verify_review_seal(
    seal_path: Path,
    base: Path,
    trust_root_dir: Path,
) -> tuple[dict[str, Any], str, str, str]:
    """R1：Review Seal schema → 路径 → canonical payload → 可信公钥 → 验签 → policy。"""
    seal_path = _require_path_inside_evidence_root(base, seal_path, "Review Seal")
    signature_path = _require_path_inside_evidence_root(base, _seal_signature_path(seal_path), "Review Seal signature")
    seal = _read_json(seal_path, "D13E review seal")
    if seal.get("seal_version") != _REVIEW_SEAL_VERSION:
        raise ValueError("review seal 的 seal_version 必须为 'd13e-review-seal/v1'")
    if seal.get("signature_scheme") != _SIGNATURE_SCHEME:
        raise ValueError(f"review seal 的 signature_scheme 必须为 {_SIGNATURE_SCHEME}")
    source_repo = _required_text(seal, "source_repo", "review seal")
    if source_repo != "Kylin-Agent-Competition/kylinOS-agent-memory":
        raise ValueError("review seal 的 source_repo 不正确")
    if seal.get("source_pr") != 148:
        raise ValueError("review seal 的 source_pr 必须为 148")
    actual_pr_author = _required_text(seal, "actual_pr_author", "review seal")
    reviewer_identity = _required_text(seal, "reviewer_identity", "review seal")
    if seal.get("reviewer_track") != "D":
        raise ValueError("review seal 的 reviewer_track 必须为 D")
    if reviewer_identity == actual_pr_author:
        raise ValueError("D13E 封存 Reviewer 必须与 signed actual_pr_author 不同（非作者）")
    if reviewer_identity not in _TRUSTED_D_REVIEWER_IDENTITIES:
        raise ValueError("review seal 的 Reviewer 不在可信 D 轨身份注册表中")
    if seal.get("review_state") != "APPROVED":
        raise ValueError("review seal 的 review_state 必须为 APPROVED")
    review_reference = _required_text(seal, "review_reference", "review seal")
    if not _GITHUB_REVIEW_REFERENCE.fullmatch(review_reference):
        raise ValueError("review seal 的 review_reference 必须是 PR #148 的 GitHub Review URL")
    reviewed_commit = seal.get("reviewed_commit")
    if not isinstance(reviewed_commit, str) or not _GIT_SHA.fullmatch(reviewed_commit):
        raise ValueError("review seal 的 reviewed_commit 必须是 40 位小写 Git SHA")
    artifacts = seal.get("approved_artifacts")
    required_artifacts = (
        "dataset_sha256",
        "gold_sha256",
        "threshold_sha256",
        "runner_sha256",
        "manifest_sha256",
    )
    if not isinstance(artifacts, dict) or set(artifacts) != set(required_artifacts):
        raise ValueError("review seal 的 approved_artifacts 必须完整包含 Dataset/Gold/阈值/Runner/Manifest 的 SHA-256")
    for key in required_artifacts:
        value = artifacts[key]
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise ValueError(f"review seal 的 approved_artifacts.{key} 必须是 64 位小写 SHA-256")
    key_id = _required_text(seal, "key_id", "review seal")
    trust_key_id, public_key, trust_key_sha256 = _load_trust_root_entry(trust_root_dir, _REVIEW_TRUST_KEY)
    if key_id != trust_key_id:
        raise ValueError("review seal 的 key_id 与 frozen trust root 不一致")
    canonical = _canonical_json_bytes(seal)
    _verify_detached_signature(public_key, canonical, signature_path, "Review Seal")
    return seal, hashlib.sha256(canonical).hexdigest(), key_id, public_key


def _load_and_verify_d13d_execution_seal(
    seal_path: Path,
    base: Path,
    trust_root_dir: Path,
) -> tuple[dict[str, Any], str, str, str]:
    """R2：D13D Seal schema → 路径 → canonical payload → 可信公钥 → 验签。"""
    seal_path = _require_path_inside_evidence_root(base, seal_path, "D13D execution seal")
    signature_path = _require_path_inside_evidence_root(base, _seal_signature_path(seal_path), "D13D execution seal signature")
    seal = _read_json(seal_path, "D13D execution seal")
    if seal.get("seal_version") != _D13D_EXECUTION_SEAL_VERSION:
        raise ValueError("D13D execution seal 的 seal_version 必须为 'd13d-execution-seal/v1'")
    if seal.get("signature_scheme") != _SIGNATURE_SCHEME:
        raise ValueError(f"D13D execution seal 的 signature_scheme 必须为 {_SIGNATURE_SCHEME}")
    attestation_sha256 = seal.get("attestation_sha256")
    if not isinstance(attestation_sha256, str) or not _SHA256.fullmatch(attestation_sha256):
        raise ValueError("D13D execution seal 的 attestation_sha256 必须是 64 位小写 SHA-256")
    implementation_commit = seal.get("implementation_commit")
    if not isinstance(implementation_commit, str) or not _GIT_SHA.fullmatch(implementation_commit):
        raise ValueError("D13D execution seal 的 implementation_commit 必须是 40 位小写 Git SHA")
    for key in (
        "environment_id",
        "dependency_version_reference",
        "data_version_reference",
        "evidence_root",
        "evidence_reference",
    ):
        _required_text(seal, key, "D13D execution seal")
    if seal.get("frozen_by_track") != "D":
        raise ValueError("D13D execution seal 必须由 D 轨冻结（frozen_by_track=D）")
    _required_text(seal, "approval_reference", "D13D execution seal")
    key_id = _required_text(seal, "key_id", "D13D execution seal")
    trust_key_id, public_key, trust_key_sha256 = _load_trust_root_entry(trust_root_dir, _D13D_TRUST_KEY)
    if key_id != trust_key_id:
        raise ValueError("D13D execution seal 的 key_id 与 frozen trust root 不一致")
    canonical = _canonical_json_bytes(seal)
    _verify_detached_signature(public_key, canonical, signature_path, "D13D execution seal")
    return seal, hashlib.sha256(canonical).hexdigest(), key_id, public_key


def _validated_trust_root_dir(trust_root_dir: Path, base: Path) -> Path:
    """Trust Root 必须存在且位于 evidence root 之外，否则 E 可替换公钥伪造 PASS。"""
    resolved = trust_root_dir.resolve()
    base_resolved = base.resolve()
    if resolved == base_resolved or base_resolved in resolved.parents:
        raise ValueError("frozen trust root 不得位于 evidence root 内")
    return resolved


def _expected_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return all(key in actual and actual[key] == value for key, value in expected.items())


def _matches_metric_contract(metric: str, expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    """拒绝未知输出字段，并为 Safety/Forget 明确校验所有硬零计数。"""
    hard_zero_counters = frozenset()
    if metric == "safety":
        hard_zero_counters = _SAFETY_HARD_ZERO_COUNTERS
    elif metric == "forget":
        hard_zero_counters = _FORGET_HARD_ZERO_COUNTERS
    allowed = set(expected) | hard_zero_counters
    unknown = set(actual) - allowed
    if unknown:
        raise ValueError(f"{metric} actual 包含未声明字段：{', '.join(sorted(unknown))}")
    missing_counters = hard_zero_counters - set(actual)
    if missing_counters:
        raise ValueError(f"{metric} actual 缺少硬零计数：{', '.join(sorted(missing_counters))}")
    if any(type(actual[counter]) is not int or actual[counter] < 0 for counter in hard_zero_counters):
        raise ValueError(f"{metric} actual 的硬零计数必须是非负整数")
    if any(actual[counter] != 0 for counter in hard_zero_counters):
        return False
    return _expected_matches(expected, actual)


def _error_type(metric: str, expected: dict[str, Any], actual: dict[str, Any]) -> str:
    if metric == "preference":
        expected_count = expected.get("record_count")
        actual_count = actual.get("record_count")
        if expected_count == 0 and isinstance(actual_count, int) and actual_count > 0:
            return "PREF_FALSE_POSITIVE"
        if isinstance(expected_count, int) and expected_count > 0 and actual_count == 0:
            return "PREF_FALSE_NEGATIVE"
        return "PREF_FIELD_MISMATCH"
    if metric == "conflict":
        if expected.get("action") != actual.get("action"):
            return "CONFLICT_RESOLUTION_WRONG"
        if expected.get("winner_id") != actual.get("winner_id"):
            return "CONFLICT_WINNER_WRONG"
        return "CONFLICT_STATE_WRONG"
    if metric == "safety":
        if actual.get("cross_user_violation_count", 0) != 0:
            return "SAFETY_CROSS_USER_VIOLATION"
        if actual.get("audit_plaintext_leak_count", 0) != 0:
            return "SAFETY_AUDIT_PLAINTEXT_LEAK"
        return "SAFETY_CRITICAL_GATE_BYPASS"
    if actual.get("missed_target_items", 0) != 0:
        return "FORGET_MISSED_TARGET"
    if actual.get("wrongly_deleted_items", 0) != 0:
        return "FORGET_WRONG_DELETE"
    if actual.get("cross_user_violation_count", 0) != 0:
        return "FORGET_CROSS_USER_VIOLATION"
    return "FORGET_RESIDUAL_AFTER_REBUILD"


def _validated_thresholds(bundle: dict[str, Any], manifest: dict[str, Any], base: Path) -> dict[str, dict[str, Any]]:
    """读取经 Review Seal 批准且与 Manifest 绑定的四项正式阈值（纯被审批对象）。"""
    if bundle.get("threshold_config_file") != manifest.get("threshold_config_file"):
        raise ValueError("bundle.threshold_config_file 必须与 manifest 一致")
    path = _relative_file(base, bundle.get("threshold_config_file"), "threshold_config_file")
    _verify_sha256(path, manifest.get("threshold_config_sha256"), "threshold_config_sha256")
    thresholds = _read_json(path, "threshold config")
    if thresholds.get("threshold_version") != "d13e-formal-thresholds/v1":
        raise ValueError("threshold config 的 threshold_version 不正确")
    metrics = thresholds.get("metrics")
    expected_fields = {
        "preference": "minimum_accuracy",
        "conflict": "minimum_accuracy",
        "safety": "maximum_violation_count",
        "forget": "maximum_violation_count",
    }
    if not isinstance(metrics, dict) or set(metrics) != set(expected_fields):
        raise ValueError("threshold config.metrics 必须完整包含四类指标")
    for metric, field in expected_fields.items():
        definition = metrics[metric]
        if not isinstance(definition, dict) or set(definition) != {field}:
            raise ValueError(f"threshold config.metrics.{metric} 必须只包含 {field}")
        value = definition[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"threshold config.metrics.{metric}.{field} 必须是数值")
        if field == "minimum_accuracy" and not 0 <= value <= 1:
            raise ValueError(f"threshold config.metrics.{metric}.{field} 必须在 0 到 1 之间")
        if field == "maximum_violation_count" and (not isinstance(value, int) or value != 0):
            raise ValueError(f"threshold config.metrics.{metric}.{field} 当前正式 Gate 必须为 0")
    return metrics


def _validated_raw_files(
    bundle: dict[str, Any],
    provenance: dict[str, Any],
    base: Path,
    d13d_seal: dict[str, Any],
) -> dict[str, Path]:
    """验证 D13D 冻结执行证明及其四类逐样本 raw 文件。

    attestation digest 同时受 Bundle 与已签名 D13D execution seal（外部可信根）
    双重冻结；E 轨只重写 raw + SHA256SUMS + attestation + bundle 无法制造
    EXECUTED_ON_FROZEN_D13D。
    """
    metrics = ("preference", "conflict", "safety", "forget")
    if bundle.get("execution_status") != "EXECUTED_ON_FROZEN_D13D":
        raise ValueError("bundle.execution_status 必须为 'EXECUTED_ON_FROZEN_D13D'")
    attestation_path = _relative_file(base, bundle.get("execution_attestation_file"), "execution_attestation_file")
    _verify_sha256(attestation_path, d13d_seal.get("attestation_sha256"), "d13d execution seal.attestation_sha256")
    _verify_sha256(attestation_path, bundle.get("execution_attestation_sha256"), "execution_attestation_sha256")
    attestation = _read_json(attestation_path, "D13D execution attestation")
    if attestation.get("attestation_version") != "d13d-execution-attestation/v1":
        raise ValueError("D13D execution attestation 的 attestation_version 不正确")
    if attestation.get("execution_status") != "EXECUTED_ON_FROZEN_D13D":
        raise ValueError("D13D execution attestation 必须声明 EXECUTED_ON_FROZEN_D13D")
    for key in (
        "implementation_commit",
        "environment_id",
        "dependency_version_reference",
        "data_version_reference",
        "evidence_root",
        "evidence_directory",
        "evidence_reference",
    ):
        if attestation.get(key) != provenance.get(key):
            raise ValueError(f"D13D execution attestation.{key} 必须与 provenance 一致")
    for key in (
        "implementation_commit",
        "environment_id",
        "dependency_version_reference",
        "data_version_reference",
        "evidence_root",
        "evidence_reference",
    ):
        if attestation.get(key) != d13d_seal.get(key):
            raise ValueError(f"D13D execution attestation.{key} 必须与 D13D execution seal 一致")

    raw_files = bundle.get("raw_result_files")
    if not isinstance(raw_files, dict) or set(raw_files) != set(metrics):
        raise ValueError("raw_result_files 必须完整包含四类指标")
    if attestation.get("raw_result_files") != raw_files:
        raise ValueError("D13D execution attestation.raw_result_files 必须与 bundle 一致")
    execution_log = _relative_file(base, attestation.get("execution_log_file"), "execution_log_file")
    _verify_sha256(execution_log, attestation.get("execution_log_sha256"), "execution_log_sha256")
    sha256sums = _relative_file(base, attestation.get("sha256sums_file"), "sha256sums_file")
    _verify_sha256(sha256sums, attestation.get("sha256sums_sha256"), "sha256sums_sha256")
    evidence_index = _relative_file(base, attestation.get("evidence_index_file"), "evidence_index_file")
    _verify_sha256(evidence_index, attestation.get("evidence_index_sha256"), "evidence_index_sha256")

    paths: dict[str, Path] = {}
    expected_sums = {Path(attestation["execution_log_file"]).as_posix(): attestation["execution_log_sha256"]}
    for metric in metrics:
        descriptor = raw_files[metric]
        if not isinstance(descriptor, dict) or set(descriptor) != {"file", "sha256"}:
            raise ValueError(f"raw_result_files.{metric} 必须只包含 file 与 sha256")
        path = _relative_file(base, descriptor.get("file"), f"raw_result_files.{metric}.file")
        _verify_sha256(path, descriptor.get("sha256"), f"raw_result_files.{metric}.sha256")
        paths[metric] = path
        expected_sums[Path(descriptor["file"]).as_posix()] = descriptor["sha256"]
    sums: dict[str, str] = {}
    for line in sha256sums.read_text(encoding="utf-8").splitlines():
        digest, separator, filename = line.partition("  ")
        if separator and _SHA256.fullmatch(digest) and filename:
            sums[filename.removeprefix("*")] = digest
    for filename, digest in expected_sums.items():
        if sums.get(filename) != digest:
            raise ValueError(f"SHA256SUMS 缺少或错配受证明文件：{filename}")
    return paths


def _metric_report(
    metric: str,
    dataset_records: list[dict[str, Any]],
    gold_records: dict[str, dict[str, Any]],
    raw_records: dict[str, dict[str, Any]],
    threshold: dict[str, Any],
) -> dict[str, Any]:
    valid = [record for record in dataset_records if record.get("inclusion_status") == "valid"]
    if not valid:
        raise ValueError(f"{metric} 没有有效正式样本")
    expected_ids = {str(record["sample_id"]) for record in valid}
    if set(raw_records) != expected_ids:
        raise ValueError(f"{metric} raw result 的 sample_id 必须与有效 Dataset 完全一致")

    correct_count = 0
    errors = []
    true_positive = true_negative = false_positive = false_negative = 0
    for dataset_record in valid:
        sample_id = str(dataset_record["sample_id"])
        gold = gold_records[sample_id]
        expected = gold.get("expected")
        actual = raw_records[sample_id].get("actual")
        if not isinstance(expected, dict) or not isinstance(actual, dict):
            raise ValueError(f"{metric} sample {sample_id} 的 expected/actual 必须是对象")
        if _matches_metric_contract(metric, expected, actual):
            correct_count += 1
            if metric == "preference":
                if expected.get("record_count") == 0:
                    true_negative += 1
                else:
                    true_positive += 1
            continue
        error_type = _error_type(metric, expected, actual)
        if metric == "preference":
            if error_type == "PREF_FALSE_POSITIVE":
                false_positive += 1
            elif error_type == "PREF_FALSE_NEGATIVE":
                false_negative += 1
            else:
                false_positive += 1
                false_negative += 1
        errors.append(
            {
                "sample_id": sample_id,
                "error_type": error_type,
                "expected": expected,
                "actual": actual,
            }
        )

    sample_count = len(valid)
    report: dict[str, Any] = {
        "status": "COMPUTED",
        "sample_count": sample_count,
        "valid_sample_count": sample_count,
        "correct_count": correct_count,
        "incorrect_count": sample_count - correct_count,
        "accuracy": correct_count / sample_count,
        "errors": errors,
    }
    if metric == "preference":
        report.update(
            {
                "true_positive": true_positive,
                "true_negative": true_negative,
                "false_positive": false_positive,
                "false_negative": false_negative,
                "target_threshold": threshold["minimum_accuracy"],
                "gate_status": "PASS" if report["accuracy"] >= threshold["minimum_accuracy"] else "FAIL",
            }
        )
    elif metric == "conflict":
        report.update(
            {
                "target_threshold": threshold["minimum_accuracy"],
                "gate_status": "PASS" if report["accuracy"] >= threshold["minimum_accuracy"] else "FAIL",
            }
        )
    else:
        report.update(
            {
                "target_violation_count": threshold["maximum_violation_count"],
                "violation_count": sample_count - correct_count,
                "gate_status": "PASS" if sample_count - correct_count <= threshold["maximum_violation_count"] else "FAIL",
            }
        )
    return report


def _validate_approved_artifact_hashes(
    base: Path,
    bundle: dict[str, Any],
    manifest: dict[str, Any],
    review_seal: dict[str, Any],
) -> None:
    """Gate 4：Review Seal 批准的本地工件 SHA-256 必须与实际文件一致。"""
    artifacts = review_seal["approved_artifacts"]
    for key, hash_key in (("dataset_file", "dataset_sha256"), ("gold_file", "gold_sha256")):
        approved = artifacts[hash_key]
        if approved != manifest[hash_key]:
            raise ValueError(f"review seal 批准的 {hash_key} 与 Manifest 不一致")
        path = _relative_file(base, bundle[key], key)
        _verify_sha256(path, approved, f"review seal.approved_artifacts.{hash_key}")
    threshold_approved = artifacts["threshold_sha256"]
    if threshold_approved != manifest["threshold_config_sha256"]:
        raise ValueError("review seal 批准的 threshold_sha256 与 Manifest 不一致")
    threshold_path = _relative_file(base, bundle["threshold_config_file"], "threshold_config_file")
    _verify_sha256(threshold_path, threshold_approved, "review seal.approved_artifacts.threshold_sha256")
    manifest_approved = artifacts["manifest_sha256"]
    manifest_path = _relative_file(base, bundle["manifest_file"], "manifest_file")
    _verify_sha256(manifest_path, manifest_approved, "review seal.approved_artifacts.manifest_sha256")
    runner_path = Path(__file__).resolve()
    if not runner_path.is_file():
        raise ValueError("无法定位正在执行的 Runner 文件")
    _verify_sha256(runner_path, artifacts["runner_sha256"], "review seal.approved_artifacts.runner_sha256")


def validate_formal_bundle(bundle_path: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """Gate 7：验证 D13D provenance 与稳定工件绑定；任何失败都不得让调用方写报告。"""
    bundle_path = bundle_path.resolve()
    bundle = _read_json(bundle_path, "bundle")
    if bundle.get("bundle_version") != "d13e-formal-bundle/v1":
        raise ValueError("bundle_version 必须为 'd13e-formal-bundle/v1'")

    manifest_path = _relative_file(bundle_path.parent, bundle.get("manifest_file"), "manifest_file")
    manifest = _read_json(manifest_path, "manifest")
    if manifest.get("manifest_version") != "d13e-formal-manifest/v1":
        raise ValueError("manifest_version 必须为 'd13e-formal-manifest/v1'")
    if manifest.get("required_reviewer_track") != "D":
        raise ValueError("manifest.required_reviewer_track 必须为 D")
    _required_text(manifest, "created_by_identity", "manifest")
    if bundle.get("formal_result_status") != "READY_FOR_FORMAL_EVALUATION":
        raise ValueError("bundle.formal_result_status 必须为 'READY_FOR_FORMAL_EVALUATION'")
    for key in ("dataset_version", "gold_label_version"):
        if bundle.get(key) != _required_text(manifest, key, "manifest"):
            raise ValueError(f"bundle.{key} 必须与 manifest.{key} 完全一致")

    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("provenance 必须是对象")
    commit = provenance.get("implementation_commit")
    if not isinstance(commit, str) or not _GIT_SHA.fullmatch(commit):
        raise ValueError("implementation_commit 必须是 D13D 冻结的 40 位小写 Git SHA")
    for key in (
        "environment_id",
        "dependency_version_reference",
        "data_version_reference",
        "evidence_root",
    ):
        _required_text(provenance, key, "provenance")
    if provenance.get("status") != "FROZEN_BY_D13D":
        raise ValueError("provenance.status 必须为 'FROZEN_BY_D13D'")
    provenance_evidence = _required_text(provenance, "evidence_reference", "provenance")
    if bundle.get("evidence_reference") != provenance_evidence:
        raise ValueError("bundle.evidence_reference 必须与 D13D provenance 一致")

    for key, hash_key in (("dataset_file", "dataset_sha256"), ("gold_file", "gold_sha256")):
        bundle_value = bundle.get(key)
        manifest_value = manifest.get(key)
        if bundle_value != manifest_value:
            raise ValueError(f"bundle.{key} 必须与 manifest.{key} 完全一致")
        input_path = _relative_file(bundle_path.parent, bundle_value, key)
        if not input_path.is_file():
            raise ValueError(f"{key} 指向的文件不存在：{input_path}")
        _verify_sha256(input_path, manifest.get(hash_key), hash_key)
    return bundle, manifest, bundle_path.parent


def compute_formal_report(
    bundle_path: Path,
    review_seal_path: Path | None = None,
    d13d_seal_path: Path | None = None,
    trust_root_dir: Path | None = None,
) -> dict[str, Any]:
    """离线计算 D13E 四类指标；只消费本地证据与两个已签名 Seal 及 frozen trust root。"""
    bundle, manifest, base = validate_formal_bundle(bundle_path)
    if review_seal_path is None or d13d_seal_path is None:
        raise ValueError("正式评测必须同时提供 --review-seal 与 --d13d-seal")
    if trust_root_dir is None:
        trust_root_dir = _DEFAULT_TRUST_ROOT
    trust_root = _validated_trust_root_dir(Path(trust_root_dir), base)
    review_seal, review_seal_sha256, review_key_id, review_public_key = _load_and_verify_review_seal(
        Path(review_seal_path), base, trust_root
    )
    d13d_seal, d13d_seal_sha256, d13d_key_id, d13d_public_key = _load_and_verify_d13d_execution_seal(
        Path(d13d_seal_path), base, trust_root
    )
    _validate_approved_artifact_hashes(base, bundle, manifest, review_seal)

    dataset_path = _relative_file(base, bundle["dataset_file"], "dataset_file")
    gold_path = _relative_file(base, bundle["gold_file"], "gold_file")
    dataset = _read_jsonl(dataset_path, "dataset")
    gold = _record_map(_read_jsonl(gold_path, "gold"), "gold")
    dataset_by_id = _record_map(dataset, "dataset")
    if set(dataset_by_id) != set(gold):
        raise ValueError("Dataset 与 Gold 的 sample_id 必须一一对应")
    metrics = ("preference", "conflict", "safety", "forget")
    if any(record.get("metric") not in metrics for record in dataset) or any(record.get("metric") not in metrics for record in gold.values()):
        raise ValueError("Dataset 与 Gold 只能包含四类正式指标")
    if any(record.get("inclusion_status") not in {"valid", "boundary"} for record in dataset):
        raise ValueError("Dataset inclusion_status 必须为 valid 或 boundary")
    _validated_evidence_directory(base, manifest["provenance"])
    thresholds = _validated_thresholds(bundle, manifest, base)

    expected_counts = manifest.get("sample_count")
    if not isinstance(expected_counts, dict):
        raise ValueError("manifest.sample_count 必须是对象")
    raw_paths = _validated_raw_files(bundle, manifest["provenance"], base, d13d_seal)

    reports: dict[str, dict[str, Any]] = {}
    for metric in metrics:
        metric_dataset = [record for record in dataset if record.get("metric") == metric]
        if len(metric_dataset) != expected_counts.get(metric):
            raise ValueError(f"manifest.sample_count.{metric} 与 Dataset 实际数量不一致")
        for record in metric_dataset:
            gold_record = gold[str(record["sample_id"])]
            if gold_record.get("metric") != metric:
                raise ValueError(f"{metric} Gold 的 metric 必须与 Dataset 一致")
            if gold_record.get("evaluation_status") not in {"valid", "boundary"}:
                raise ValueError(f"{metric} Gold 必须声明 valid 或 boundary 状态")
            if gold_record["evaluation_status"] != record.get("inclusion_status"):
                raise ValueError(f"{metric} Gold 与 Dataset 的有效/边界状态不一致")
        raw = _record_map(_read_jsonl(raw_paths[metric], f"{metric} raw result"), f"{metric} raw result")
        for record in raw.values():
            if record.get("metric") != metric:
                raise ValueError(f"{metric} raw result 的 metric 不一致")
        reports[metric] = _metric_report(metric, metric_dataset, gold, raw, thresholds[metric])

    if expected_counts.get("total") != len(dataset):
        raise ValueError("manifest.sample_count.total 与 Dataset 实际数量不一致")
    provenance = manifest["provenance"]
    review_signature_path = _seal_signature_path(Path(review_seal_path).resolve())
    d13d_signature_path = _seal_signature_path(Path(d13d_seal_path).resolve())
    return {
        "status": "COMPUTED",
        "provenance": {
            "implementation_commit": provenance["implementation_commit"],
            "environment_id": provenance["environment_id"],
            "dependency_version_reference": provenance["dependency_version_reference"],
            "data_version_reference": provenance["data_version_reference"],
            "evidence_root": provenance["evidence_root"],
            "dataset_sha256": manifest["dataset_sha256"],
            "gold_sha256": manifest["gold_sha256"],
            "reviewed_commit": review_seal["reviewed_commit"],
            "actual_pr_author": review_seal["actual_pr_author"],
            "reviewer_identity": review_seal["reviewer_identity"],
            "review_reference": review_seal["review_reference"],
            "attestation_sha256": d13d_seal["attestation_sha256"],
            "review_seal_sha256": review_seal_sha256,
            "review_signature_sha256": hashlib.sha256(review_signature_path.read_bytes()).hexdigest(),
            "review_key_id": review_key_id,
            "review_key_fingerprint": hashlib.sha256(review_public_key).hexdigest(),
            "d13d_execution_seal_sha256": d13d_seal_sha256,
            "d13d_signature_sha256": hashlib.sha256(d13d_signature_path.read_bytes()).hexdigest(),
            "d13d_key_id": d13d_key_id,
            "d13d_key_fingerprint": hashlib.sha256(d13d_public_key).hexdigest(),
        },
        **reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="D13E formal evaluation（离线，Ed25519 签名 Seal）")
    parser.add_argument("input", nargs="?", help="D13E formal bundle JSON（或使用 --bundle）")
    parser.add_argument("--bundle", dest="bundle_flag", help="D13E formal bundle JSON 路径")
    parser.add_argument("--review-seal", help="D13E_REVIEW_SEAL_V1.json 路径")
    parser.add_argument("--d13d-seal", help="D13D_EXECUTION_SEAL_V1.json 路径")
    parser.add_argument("--trust-roots", help="frozen trust root 目录（默认 /etc/kylin-memory/trust）")
    parser.add_argument("--output", "-o", help="formal report JSON output")
    args = parser.parse_args()

    bundle_value = args.bundle_flag or args.input
    if not bundle_value:
        parser.error("必须提供 D13E formal bundle JSON")

    try:
        report = compute_formal_report(
            Path(bundle_value),
            review_seal_path=Path(args.review_seal) if args.review_seal else None,
            d13d_seal_path=Path(args.d13d_seal) if args.d13d_seal else None,
            trust_root_dir=Path(args.trust_roots) if args.trust_roots else None,
        )
    except ValueError as exc:
        print(f"D13E 正式评测拒绝执行：{exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output).resolve()
        evidence_directory = Path(bundle_value).resolve().parent
        if output_path != evidence_directory and evidence_directory not in output_path.parents:
            print("D13E 正式评测拒绝写出报告：--output 必须位于 D13D 唯一证据目录", file=sys.stderr)
            return 2
        output_path.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
