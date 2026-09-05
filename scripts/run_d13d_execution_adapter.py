"""Validate a future D13D execution invocation without dispatching it.

Formal dispatch remains disabled until the independently frozen VM environment
and evidence authority specified by the D13D task card are available.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "memory-service"))

from evaluation.d13d_execution_adapter import (  # noqa: E402
    ExecutionPreflightError,
    ExecutionRequest,
    validate_execution_request,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="D13D versioned execution adapter preflight")
    parser.add_argument("--tested-commit", required=True)
    parser.add_argument("--testset", required=True, type=Path)
    parser.add_argument("--testset-sha256", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        validated = validate_execution_request(
            ExecutionRequest(
                repository_root=REPOSITORY_ROOT,
                tested_commit=args.tested_commit,
                testset_path=args.testset,
                testset_sha256=args.testset_sha256,
                output_root=args.output_root,
                state_root=args.state_root,
                evidence_root=args.evidence_root,
            )
        )
    except ExecutionPreflightError as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}))
        return 2
    print(
        json.dumps(
            {
                "status": "PREFLIGHT_ONLY",
                "tested_commit": validated.request.tested_commit,
                "sample_count": len(validated.records),
                "formal_dispatch": "DISABLED_PENDING_FROZEN_VM",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
