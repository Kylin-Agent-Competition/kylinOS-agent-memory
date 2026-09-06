"""d13d_forget_state_binding.py — D13D Forget state binding artifact v1（校验模块）。

纯标准库实现，只做 artifact 的**静态结构/身份/SHA 校验**，不连接 DB、不读取
Gold/expected、不产生任何正式 raw。live 存在性核验由 adapter 在真实运行环境
按 binding 引用执行（见 docs/day13/27_d13d_forget_state_binding_contract_20260906.md）。

契约单一真源：docs/day13/27_d13d_forget_state_binding_contract_20260906.md。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Mapping

BINDING_VERSION = "d13d-forget-state-binding/v1"

# D13E Dataset 的五个 Forget sample 与 mode（顺序无关，集合相等即可）
FORGET_SAMPLE_MODES: Dict[str, str] = {
    "d13e-forget-001": "single_item",
    "d13e-forget-002": "session",
    "d13e-forget-003": "topic",
    "d13e-forget-004": "time_window",
    "d13e-forget-005": "full_reset",
}

TOP_LEVEL_REQUIRED = (
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

VM_SNAPSHOT_REQUIRED = ("vm", "snapshot", "snapshot_uuid")
DB_IDENTITY_REQUIRED = ("path", "sha256")

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
    """固定序列化口径（与契约 §7 一致）。"""
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


def validate_artifact(data: Any) -> List[str]:
    """返回错误列表；空列表 = 静态校验通过。"""
    errors: List[str] = []
    if not isinstance(data, Mapping):
        return ["artifact must be a JSON object"]

    for key in TOP_LEVEL_REQUIRED:
        if key not in data:
            errors.append(f"missing top-level field: {key}")

    if data.get("binding_version") != BINDING_VERSION:
        errors.append(f"binding_version must be {BINDING_VERSION!r}")

    # SHA-256 复核（存在时才复算；缺失已在 required 报错）
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

    if isinstance(data.get("vm_snapshot"), Mapping):
        for key in VM_SNAPSHOT_REQUIRED:
            if key not in data["vm_snapshot"]:
                errors.append(f"vm_snapshot missing: {key}")
    if isinstance(data.get("db_identity"), Mapping):
        for key in DB_IDENTITY_REQUIRED:
            if key not in data["db_identity"]:
                errors.append(f"db_identity missing: {key}")

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
        # single_item 必须含真实数字 DB ID（契约 §5）
        if sample_id == "d13e-forget-001":
            tid = sample.get("target_identity")
            if not isinstance(tid, Mapping) or not isinstance(tid.get("db_id"), int):
                errors.append(f"{sample_id} target_identity.db_id must be a real integer DB id")
        for grp in ("same_user_controls", "foreign_user_controls"):
            val = sample.get(grp)
            if not isinstance(val, list):
                errors.append(f"{sample_id} {grp} must be a list")
            elif not val:
                # full_reset 以整用户为作用域：同用户 control 语义为空（全部实体即目标），
                # 但仍要求列表存在；foreign-user control 任何模式都必须非空。
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
    return errors


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
    "FORGET_SAMPLE_MODES",
    "canonical_payload",
    "canonical_bytes",
    "compute_artifact_sha256",
    "validate_artifact",
    "verify_artifact_file",
]
