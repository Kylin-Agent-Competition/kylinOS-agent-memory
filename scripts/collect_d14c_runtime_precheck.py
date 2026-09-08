"""Collect a D14C read-only runtime precheck observation from a VM host."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "memory-service"))

from evaluation.d14c_runtime_precheck import (  # noqa: E402
    D14CPrecheckError,
    SystemRuntimeProbe,
    collect_precheck_observation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="D14C read-only runtime precheck collector")
    parser.add_argument("request", type=Path, help="precheck request JSON")
    parser.add_argument("--output", "-o", type=Path, required=True, help="observation JSON output")
    args = parser.parse_args()
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise D14CPrecheckError("request root must be an object")
        observation = collect_precheck_observation(request, probe=SystemRuntimeProbe())
    except (OSError, json.JSONDecodeError, D14CPrecheckError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    args.output.write_text(json.dumps(observation, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PRECHECK_OBSERVATION", "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
