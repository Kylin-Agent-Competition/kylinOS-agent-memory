"""Validate a D14C formal-run handoff without creating evidence or dispatching."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "memory-service"))

from evaluation.d14c_l3_harness import (  # noqa: E402
    CANONICAL_FORMAL_HANDOFF_PATH,
    D14CPreflightError,
    load_and_validate_authoritative_handoff,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="D14C formal L3 preflight")
    parser.add_argument("--control-root", type=Path, required=True)
    parser.add_argument("--expected-control-head", required=True)
    parser.add_argument("--handoff", type=Path, default=CANONICAL_FORMAL_HANDOFF_PATH)
    args = parser.parse_args()
    try:
        report = load_and_validate_authoritative_handoff(
            args.handoff,
            control_root=args.control_root,
            expected_control_head=args.expected_control_head,
        )
    except D14CPreflightError as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
