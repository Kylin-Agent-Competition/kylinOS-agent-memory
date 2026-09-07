"""Convert a captured D14C VM record to the existing D13C evaluator bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "memory-service"))

from evaluation.d14c_l3_harness import D14CBundleError, convert_runtime_capture  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="D14C to D13C evaluator bundle converter")
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", "-o", type=Path, required=True)
    args = parser.parse_args()
    try:
        capture = json.loads(args.capture.read_text(encoding="utf-8"))
        if not isinstance(capture, dict):
            raise D14CBundleError("capture root must be an object")
        bundle = convert_runtime_capture(capture)
    except (OSError, json.JSONDecodeError, D14CBundleError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "CONVERTED", "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
