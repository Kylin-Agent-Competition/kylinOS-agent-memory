#!/usr/bin/env python3
"""Build the Main-side same-key/different-request conflict probe for M2 evidence.

The probe reuses every final RC record identity and ``idempotency_key`` but
changes the canonical request content.  It is a negative replay input: the
production importer must return ``idempotency_conflict`` for every record and
must not create any additional production state.  This file is never a valid
import source and is stored only as negative-test evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROBE_SUFFIX = " [m2-conflict-probe]"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-jsonl", type=Path, required=True)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    args = parser.parse_args()

    try:
        records: list[dict[str, Any]] = []
        for line in args.input_jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("final RC records must be JSON objects")
            content = record.get("content")
            if not isinstance(content, dict) or not isinstance(content.get("content_summary"), str):
                raise ValueError("final RC record lacks content.content_summary")
            probe = json.loads(json.dumps(record, ensure_ascii=False))
            probe["content"]["content_summary"] = content["content_summary"] + PROBE_SUFFIX
            records.append(probe)
        if not records:
            raise ValueError("final RC input is empty")
        args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with args.output_jsonl.open("w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"M2_CONFLICT_PROBE_FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
