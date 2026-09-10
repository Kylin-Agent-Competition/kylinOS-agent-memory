#!/usr/bin/env python3
"""Capture D14B SQLite truth through the production repository table."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.d14b_capture_runner_common import (
    CaptureRunnerError,
    fetch_active_entries,
    open_readonly_sqlite,
    production_identity,
    write_artifact_and_receipt,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--tested-commit", required=True)
    parser.add_argument("--capture-handoff", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    connection = open_readonly_sqlite(args.db_path)
    try:
        rows = fetch_active_entries(connection, args.user_id)
        stable_ids = sorted({production_identity(row) for row in rows})
        active_version_ids = sorted({f"v{int(row['version'])}" for row in rows})
        artifact = {"stable_ids": stable_ids, "active_version_ids": active_version_ids}
    finally:
        connection.close()

    write_artifact_and_receipt(
        channel="sqlite_truth",
        tested_commit=args.tested_commit,
        capture_handoff=args.capture_handoff,
        runner_file=Path(__file__),
        artifact_path=args.output,
        receipt_path=args.receipt_output,
        artifact=artifact,
    )
    return 0


def main() -> int:
    try:
        return run(parse_args())
    except CaptureRunnerError as error:
        print(f"D14B_SQLITE_CAPTURE_FAIL: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
