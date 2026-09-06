"""d13d_forget_state_binding.py — D13D Forget state binding artifact 校验模块。

纯标准库，只做 artifact 的**静态结构/身份/SHA 校验**，不连接 DB、不读取
Gold/expected、不产生任何正式 raw。live 文件/DB 校验由 adapter 的 runtime
layer 执行（见 docs/day13/28_…v2 契约与 PR #160 R5）。

版本：
- v1（d13d-forget-state-binding/v1）= HISTORICAL / SUPERSEDED（V1 artifact 仅作
  state-preparation evidence，见 27_ 契约与 26_ §9.5）。
- v2（d13d-forget-state-binding/v2）= CURRENT NORMATIVE：拆开
  state_preparation_commit 与 execution_compatibility.minimum_commit，并携带
  source_state（sealed source DB）身份。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Mapping

BINDING_VERSION = "d13d-forget-state-binding/v1"
BINDING_VERSION_V2 = "d13d-forget-state-binding/v2"
_VERSIONS = frozenset({BINDING_VERSION, BINDING_VERSION_V2})

# D13E Dataset 的五个 Forget sample 与 mode（顺序无关，集合相等即可）
FORGET_SAMPLE_MODES: Dict[str, str] = {
    "d13e-forget-001": "single_item",
    "d13e-forget-002": "session",
    "d13e-forget-003": "topic",
    "d13e-forget-004": "time_window",
    "d13e-forget-005": "full_reset",
}

_V1_TOP_LEVEL_REQUIRED = (
    "binding_version",
    "artifact_sha256",
    "owner",
    "approved_by",
    "approval_reference",
    "applicable_source_commit",
    "environment_id",
    "vm_snapshot",
    "state_root",
    "db_identity",
    "retrieval_profile",
    "created_at_utc",
    "created_by",
    "samples",
)
_V2_TOP_LEVEL_REQUIRED = (
    "binding_version",
    "artifact_sha256",
    "owner",
    "approved_by",
    "approval_reference",
    "state_preparation_commit",
    "execution_compatibility",
    "environment_id",
    "vm_snapshot",
    "source_state",
    "retrieval_profile",
    "created_at_utc",
    "created_by",
    "samples",
)

VM_SNAPSHOT_REQUIRED = ("vm", "snapshot", "snapshot_uuid")
DB_IDENTITY_REQUIRED = ("path", "sha256")
EXEC_COMPAT_REQUIRED = ("minimum_commit", "policy")
SOURCE_STATE_REQUIRED = (
    "state_root",
    "sealed_db_path",
    "sealed_db_sha256",
    "db_size_bytes",
    "sqlite_schema_fingerprint",
    "prepared_on_vm_snapshot",
    "prepared_at_utc",
)

SAMPLE_REQUIRED = (
    "sample_id",
    "user_id",
    "forget_mode",
    "target_selector",
    "target_identity",
    "same_user_controls",
    "foreign_user_controls",
    "prerequisite_facts",
    "realtime_retrieval",
    "rebuild_retrieval",
)

RETRIEVAL_REQUIRED = ("entrypoint", "trace_reference", "snapshot", "watermark")

# 禁止出现在 artifact 字段名/值中的敏感/评测判定物（fail-closed 黑名单）
_FORBIDDEN_KEY_TOKENS = (
    "gold", "expected", "threshold", "pass", "fail",
    "confirmation", "private_key", "secret", "credential",
    "api_key", "password", "token", "user_text", "content",
)
_PRIVATE_KEY_BANNER_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


def canonical_payload(data: Mapping[str, Any]) -> Dict[str, Any]:
    """canonical payload = 去除 artifact_sha256 自身字段后的结构。"""
    return {k: v for k, v in data.items() if k != "artifact_sha256"}


def canonical_bytes(data: Mapping[str, Any]) -> bytes:
    """固定序列化口径（v1 契约 §7 / v2 契约沿用同一口径）。"""
    return json.dumps(
        canonical_payload(data),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def compute_artifact_sha256(data: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(data)).hexdigest()


def _iter_keys(value: Any, path: str, errors: List[str]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            full = f"{path}.{key}" if path else str(key)
            lower = str(key).lower()
            for token in _FORBIDDEN_KEY_TOKENS:
                if token in lower:
                    errors.append(f"forbidden key: {full} (contains {token!r})")
                    break
            _iter_keys(child, full, errors)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _iter_keys(child, f"{path}[{i}]", errors)
    elif isinstance(value, str):
        if _PRIVATE_KEY_BANNER_RE.search(value):
            errors.append(f"private key material detected at {path}")


def _sha_and_sample_checks(data: Mapping[str, Any], errors: List[str]) -> None:
    """SHA-256 复核 + samples 结构 + 禁填扫描（v1/v2 共用）。"""
    if "artifact_sha256" in data:
        expected = data["artifact_sha256"]
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            errors.append("artifact_sha256 must be a 64-char hex string")
        else:
            actual = compute_artifact_sha256(data)
            if actual != expected:
                errors.append(
                    f"artifact_sha256 mismatch: declared={expected} computed={actual}"
                )

    samples = data.get("samples")
    if not isinstance(samples, list):
        errors.append("samples must be a list")
        samples = []
    seen: List[str] = []
    for idx, sample in enumerate(samples):
        if not isinstance(sample, Mapping):
            errors.append(f"samples[{idx}] must be an object")
            continue
        sample_id = sample.get("sample_id")
        if sample_id is None:
            errors.append(f"samples[{idx}] missing sample_id")
            continue
        seen.append(sample_id)
        for key in SAMPLE_REQUIRED:
            if key not in sample:
                errors.append(f"{sample_id} missing field: {key}")
        mode = sample.get("forget_mode")
        if mode != FORGET_SAMPLE_MODES.get(sample_id):
            errors.append(
                f"{sample_id} forget_mode mismatch: expected "
                f"{FORGET_SAMPLE_MODES.get(sample_id)!r}, got {mode!r}"
            )
        if sample_id == "d13e-forget-001":
            tid = sample.get("target_identity")
            if not isinstance(tid, Mapping) or not isinstance(tid.get("db_id"), int):
                errors.append(f"{sample_id} target_identity.db_id must be a real integer DB id")
        for grp in ("same_user_controls", "foreign_user_controls"):
            val = sample.get(grp)
            if not isinstance(val, list):
                errors.append(f"{sample_id} {grp} must be a list")
            elif not val:
                # full_reset 以整用户为作用域：同用户 control 语义为空；foreign 必须非空。
                if grp != "same_user_controls" or sample_id != "d13e-forget-005":
                    errors.append(f"{sample_id} {grp} must be a non-empty list")
        for grp in ("realtime_retrieval", "rebuild_retrieval"):
            ret = sample.get(grp)
            if not isinstance(ret, Mapping):
                errors.append(f"{sample_id} {grp} must be an object")
                continue
            for key in RETRIEVAL_REQUIRED:
                if not ret.get(key):
                    errors.append(f"{sample_id} {grp} missing {key}")

    if len(set(seen)) != len(FORGET_SAMPLE_MODES) or set(seen) != set(FORGET_SAMPLE_MODES):
        errors.append(
            f"samples must cover exactly {sorted(FORGET_SAMPLE_MODES)}; got {sorted(seen)}"
        )

    _iter_keys(data, "", errors)


def _validate_v1(data: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    for key in _V1_TOP_LEVEL_REQUIRED:
        if key not in data:
            errors.append(f"missing top-level field: {key}")
    if data.get("binding_version") != BINDING_VERSION:
        errors.append(f"binding_version must be {BINDING_VERSION!r}")
    if isinstance(data.get("vm_snapshot"), Mapping):
        for key in VM_SNAPSHOT_REQUIRED:
            if key not in data["vm_snapshot"]:
                errors.append(f"vm_snapshot missing: {key}")
    if isinstance(data.get("db_identity"), Mapping):
        for key in DB_IDENTITY_REQUIRED:
            if key not in data["db_identity"]:
                errors.append(f"db_identity missing: {key}")
    _sha_and_sample_checks(data, errors)
    return errors


def _validate_v2(data: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    for key in _V2_TOP_LEVEL_REQUIRED:
        if key not in data:
            errors.append(f"missing top-level field: {key}")
    if data.get("binding_version") != BINDING_VERSION_V2:
        errors.append(f"binding_version must be {BINDING_VERSION_V2!r}")
    if "applicable_source_commit" in data:
        errors.append("v2 must not use legacy applicable_source_commit")
    if isinstance(data.get("vm_snapshot"), Mapping):
        for key in VM_SNAPSHOT_REQUIRED:
            if key not in data["vm_snapshot"]:
                errors.append(f"vm_snapshot missing: {key}")
    if isinstance(data.get("execution_compatibility"), Mapping):
        for key in EXEC_COMPAT_REQUIRED:
            if key not in data["execution_compatibility"]:
                errors.append(f"execution_compatibility missing: {key}")
    if isinstance(data.get("source_state"), Mapping):
        for key in SOURCE_STATE_REQUIRED:
            if key not in data["source_state"]:
                errors.append(f"source_state missing: {key}")
    _sha_and_sample_checks(data, errors)
    return errors


def validate_artifact(data: Any) -> List[str]:
    """返回错误列表；空列表 = 静态校验通过（v1 legacy / v2 normative）。"""
    if not isinstance(data, Mapping):
        return ["artifact must be a JSON object"]
    version = data.get("binding_version")
    if version == BINDING_VERSION:
        return _validate_v1(data)
    if version == BINDING_VERSION_V2:
        return _validate_v2(data)
    return [f"binding_version must be one of {sorted(_VERSIONS)}"]


def verify_artifact_file(path: str) -> tuple[bool, List[str]]:
    """读取并静态校验 artifact 文件。"""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"cannot load artifact: {exc}"]
    errors = validate_artifact(data)
    return (not errors), errors


__all__ = [
    "BINDING_VERSION",
    "BINDING_VERSION_V2",
    "FORGET_SAMPLE_MODES",
    "canonical_payload",
    "canonical_bytes",
    "compute_artifact_sha256",
    "validate_artifact",
    "verify_artifact_file",
]