#!/usr/bin/env python3
"""Verify that a D14B evidence root has a closed SHA256SUMS manifest."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path


LINE_RE = re.compile(r"^([0-9a-f]{64})  (.+)$")


class ManifestError(ValueError):
    """Evidence bytes or its manifest are not a one-to-one closure."""


def verify(evidence_root: Path) -> None:
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
        actual = hashlib.sha256((evidence_root / relative_name).read_bytes()).hexdigest()
        if actual != expected:
            raise ManifestError(f"SHA256 不匹配: {relative_name}")


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
