"""Validate a captured D14C evidence package without interpreting runtime success."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "memory-service"))
from evaluation.d14c_evidence_package import D14CEvidenceError, validate_evidence_package  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="D14C evidence package verifier")
    parser.add_argument("evidence_root", type=Path)
    args = parser.parse_args()
    try:
        report = validate_evidence_package(args.evidence_root)
    except D14CEvidenceError as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
