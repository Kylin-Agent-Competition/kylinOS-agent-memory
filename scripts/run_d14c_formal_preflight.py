"""Validate a D14C formal-run handoff without creating evidence or dispatching."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "memory-service"))

from evaluation.d14c_l3_harness import D14CPreflightError, load_and_validate_handoff  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="D14C formal L3 preflight")
    parser.add_argument("handoff", type=Path, help="formal handoff JSON")
    args = parser.parse_args()
    try:
        report = load_and_validate_handoff(args.handoff, repository_root=REPOSITORY_ROOT)
    except D14CPreflightError as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
