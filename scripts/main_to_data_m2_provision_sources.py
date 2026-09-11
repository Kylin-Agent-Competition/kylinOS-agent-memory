#!/usr/bin/env python3
"""Controlled Main source-event provisioning for the M2 RC10 binding.

Creates real Main source events through the canonical ``event.ingest`` pipeline
and admission path for the Data controlled-authored RC10 candidates.  It never
writes ``source_events`` directly, never invents admission decisions, and never
allocates production knowledge identities.  Re-running is idempotent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MEMORY_SERVICE = ROOT / "memory-service"
if str(MEMORY_SERVICE) not in sys.path:
    sys.path.insert(0, str(MEMORY_SERVICE))

from db.engine import create_db_engine  # noqa: E402
from service.main_to_data_binding import (  # noqa: E402
    BindingError,
    ControlledSourceProvisioner,
    DEFAULT_AUTHORED_AT,
    parse_candidate_jsonl,
    sha256_lf,
)
from service.main_to_data_import import TransportValidationError  # noqa: E402


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path | None, payload: Any) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is None:
        sys.stdout.write(encoded)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="Migrated Main SQLite database")
    parser.add_argument("--candidates", type=Path, required=True, help="Data prebinding candidate JSONL")
    parser.add_argument("--binding-request", type=Path, required=True, help="Data prebinding binding request")
    parser.add_argument("--user-id", required=True, help="Controlled Main user scope for the RC10 sources")
    parser.add_argument("--authored-at", default=DEFAULT_AUTHORED_AT, help="Deterministic ISO-8601 authored time")
    parser.add_argument("--result", type=Path, default=None)
    args = parser.parse_args()

    try:
        binding_request = _load_object(args.binding_request)
        candidates_bytes = args.candidates.read_bytes()
        if sha256_lf(candidates_bytes) != binding_request.get("candidate_file_sha256"):
            raise ValueError("candidate file SHA-256 (LF) does not match binding_request")
        candidates = parse_candidate_jsonl(candidates_bytes)
        if binding_request.get("record_count") != len(candidates):
            raise ValueError("binding_request.record_count does not match candidate file")

        engine = create_db_engine(str(args.db))
        provisioner = ControlledSourceProvisioner(
            engine,
            user_id=args.user_id,
            authored_at=args.authored_at,
        )
        results = provisioner.provision(candidates)
        _write_json(args.result, results)
        return 0 if results["record_count"] == len(candidates) else 2
    except (OSError, json.JSONDecodeError, ValueError, TransportValidationError, BindingError) as exc:
        print(f"M2_PROVISION_FAILED: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # fail closed; no internal traceback in production evidence
        print(f"M2_PROVISION_FAILED: {type(exc).__name__}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
