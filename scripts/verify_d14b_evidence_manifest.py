#!/usr/bin/env python3
"""Verify that a D14B evidence root has closed bytes and provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


LINE_RE = re.compile(r"^([0-9a-f]{64})  (.+)$")
CHANNELS = ("sqlite", "fts5", "vector", "rrf")
RECEIPT_NAMES = {
    "sqlite": "sqlite-truth.receipt.json",
    "fts5": "fts5-results.receipt.json",
    "vector": "vector-results.receipt.json",
    "rrf": "rrf-results.receipt.json",
}
CHECKPOINT_INVENTORY_RELPATH = "CHECKPOINTS.json"


class ManifestError(ValueError):
    """Evidence bytes or its manifest are not a one-to-one closure."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sha256_closure(evidence_root: Path) -> dict[str, str]:
    manifest = evidence_root / "SHA256SUMS"
    if not evidence_root.is_dir() or not manifest.is_file():
        raise ManifestError("evidence root 或 SHA256SUMS 不存在")
    entries: dict[str, str] = {}
    for number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        matched = LINE_RE.fullmatch(line)
        if matched is None:
            raise ManifestError(f"SHA256SUMS 第 {number} 行格式非法")
        digest, relative_name = matched.groups()
        path = Path(relative_name)
        if path.is_absolute() or ".." in path.parts or relative_name == "SHA256SUMS":
            raise ManifestError(f"SHA256SUMS 第 {number} 行路径非法")
        if relative_name in entries:
            raise ManifestError(f"SHA256SUMS 存在重复路径: {relative_name}")
        entries[relative_name] = digest
    if not entries:
        raise ManifestError("SHA256SUMS 不能为空")
    actual_files = {
        path.relative_to(evidence_root).as_posix()
        for path in evidence_root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }
    declared_files = set(entries)
    if actual_files - declared_files:
        raise ManifestError(f"发现未登记 evidence 文件: {sorted(actual_files - declared_files)}")
    if declared_files - actual_files:
        raise ManifestError(f"SHA256SUMS 声明了不存在文件: {sorted(declared_files - actual_files)}")
    for relative_name, expected in entries.items():
        if sha256(evidence_root / relative_name) != expected:
            raise ManifestError(f"SHA256 不匹配: {relative_name}")
    return entries


def load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ManifestError(f"{label} 必须是 regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ManifestError(f"{label} 不是合法 JSON: {path}") from error
    if not isinstance(value, dict):
        raise ManifestError(f"{label} 顶层必须是 JSON object: {path}")
    return value


def require_manifest_file(root: Path, entries: dict[str, str], path: Path, label: str) -> None:
    relative = path.relative_to(root).as_posix()
    if not path.is_file() or path.is_symlink():
        raise ManifestError(f"缺少必需 {label}: {relative}")
    if relative not in entries:
        raise ManifestError(f"必需 {label} 未进入 SHA256SUMS: {relative}")


def load_checkpoint_inventory(root: Path, entries: dict[str, str]) -> list[str]:
    inventory_path = root / CHECKPOINT_INVENTORY_RELPATH
    require_manifest_file(root, entries, inventory_path, "checkpoint inventory")
    raw = inventory_path.read_text(encoding="utf-8")
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ManifestError(f"checkpoint inventory 不是合法 JSON: {inventory_path}") from error
    if not isinstance(value, list):
        raise ManifestError("checkpoint inventory 必须是 JSON array")

    relpaths: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ManifestError("checkpoint inventory 项必须是非空字符串")
        relpath = item.strip()
        path = Path(relpath)
        if (
            path.is_absolute()
            or ".." in path.parts
            or relpath in {"SHA256SUMS", CHECKPOINT_INVENTORY_RELPATH}
        ):
            raise ManifestError(f"checkpoint inventory 路径非法: {relpath}")
        relpaths.append(relpath)
    if len(set(relpaths)) != len(relpaths):
        raise ManifestError("checkpoint inventory 存在重复路径")
    return relpaths


def load_checkpoint(
    root: Path, entries: dict[str, str], relpath: str
) -> tuple[Path, dict[str, Any]]:
    path = root / relpath
    require_manifest_file(root, entries, path, "checkpoint")
    value = load_object(path, "checkpoint")
    required = {"tested_commit", "checkpoint", "capture_sources", *CHANNELS}
    missing = sorted(required - value.keys())
    if missing:
        raise ManifestError(f"checkpoint schema 缺少字段 {missing}: {relpath}")
    return path, value


def ensure_no_unlisted_checkpoints(root: Path, inventory: set[str]) -> None:
    inventory_path = root / CHECKPOINT_INVENTORY_RELPATH
    for path in root.rglob("*.json"):
        if path == inventory_path or path.is_symlink():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(value, dict) and "capture_sources" in value:
            relpath = path.relative_to(root).as_posix()
            if relpath not in inventory:
                raise ManifestError(f"未登记 D14B checkpoint: {relpath}")


def require_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise ManifestError(f"provenance 不一致: {label}")


def verify_checkpoint_provenance(
    *, root: Path, entries: dict[str, str], checkpoint_path: Path, checkpoint: dict[str, Any]
) -> None:
    checkpoint_name = checkpoint["checkpoint"]
    sources = checkpoint["capture_sources"]
    if not isinstance(checkpoint_name, str) or not checkpoint_name:
        raise ManifestError(f"checkpoint 名称非法: {checkpoint_path.relative_to(root)}")
    if not isinstance(sources, dict):
        raise ManifestError(f"capture_sources 非 object: {checkpoint_path.relative_to(root)}")
    handoff_path = root / "provenance" / "d14b-capture-handoff.json"
    require_manifest_file(root, entries, handoff_path, "capture handoff")
    handoff = load_object(handoff_path, "capture handoff")
    require_equal(sha256(handoff_path), sources.get("capture_handoff_sha256"), "handoff SHA-256")
    require_equal(handoff.get("tested_commit"), checkpoint["tested_commit"], "handoff.tested_commit")
    captures = handoff.get("captures")
    if not isinstance(captures, dict):
        raise ManifestError("capture handoff.captures 非 object")
    receipt_directory = checkpoint_path.parent / "provenance" / checkpoint_name
    for channel in CHANNELS:
        source = sources.get(channel)
        if not isinstance(source, dict):
            raise ManifestError(f"capture_sources 缺少 {channel}")
        receipt_path = receipt_directory / RECEIPT_NAMES[channel]
        require_manifest_file(root, entries, receipt_path, f"{channel} receipt")
        receipt = load_object(receipt_path, f"{channel} receipt")
        require_equal(sha256(receipt_path), source.get("receipt_sha256"), f"{channel} receipt SHA-256")
        for field in ("tested_commit", "command_id", "runner_path", "runner_sha256", "artifact_sha256"):
            expected = checkpoint["tested_commit"] if field == "tested_commit" else source.get(field)
            require_equal(receipt.get(field), expected, f"{channel} receipt.{field}")
        handoff_capture = captures.get(channel)
        if not isinstance(handoff_capture, dict):
            raise ManifestError(f"capture handoff 缺少 {channel}")
        for field in ("command_id", "runner_path", "runner_sha256"):
            require_equal(handoff_capture.get(field), receipt.get(field), f"{channel} handoff.{field}")


def verify(evidence_root: Path) -> None:
    entries = verify_sha256_closure(evidence_root)
    inventory_rels = load_checkpoint_inventory(evidence_root, entries)
    for relpath in inventory_rels:
        checkpoint_path, checkpoint = load_checkpoint(evidence_root, entries, relpath)
        verify_checkpoint_provenance(
            root=evidence_root, entries=entries, checkpoint_path=checkpoint_path, checkpoint=checkpoint
        )
    ensure_no_unlisted_checkpoints(evidence_root, set(inventory_rels))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        verify(args.evidence_root)
    except (ManifestError, OSError, UnicodeDecodeError) as error:
        print(f"D14B_EVIDENCE_MANIFEST_FAIL: {error}", file=sys.stderr)
        return 2
    print("D14B evidence SHA256SUMS closure: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
