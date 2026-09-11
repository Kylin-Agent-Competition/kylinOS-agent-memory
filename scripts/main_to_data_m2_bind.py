#!/usr/bin/env python3
"""Controlled Main source-binding runner for the Data M2 RC10 prebinding request.

Read-only with respect to production state: it resolves each Data candidate to
its real, admitted, same-user Main source event and fails closed on any missing,
cross-user, unadmitted, descriptor-mismatched, or provenance-incompatible
binding.  It never creates source events and never allocates production
knowledge identities.
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
    M2BindingService,
    build_static_scope_resolver,
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
    parser.add_argument("--binding-request", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--provisioning-results", type=Path, required=True)
    parser.add_argument("--principal", required=True, help="Trusted authenticated principal")
    parser.add_argument(
        "--scope-map",
        type=Path,
        required=True,
        help="Trusted JSON mapping: principal -> authorized user_id array",
    )
    parser.add_argument("--result", type=Path, default=None)
    args = parser.parse_args()

    try:
        binding_request = _load_object(args.binding_request)
        provisioning_results = _load_object(args.provisioning_results)
        candidates_bytes = args.candidates.read_bytes()
        scope_map = _load_object(args.scope_map)
        if any(not isinstance(users, list) for users in scope_map.values()):
            raise ValueError("scope-map values must be arrays")

        engine = create_db_engine(str(args.db))
        service = M2BindingService(
            engine,
            principal_scope_resolver=build_static_scope_resolver(scope_map),
        )
        response = service.bind(
            binding_request=binding_request,
            candidates_bytes=candidates_bytes,
            provisioning_results=provisioning_results,
            authenticated_principal=args.principal,
        )
        _write_json(args.result, response)
        return 0 if response["bound_count"] == response["record_count"] else 2
    except (OSError, json.JSONDecodeError, ValueError, TransportValidationError, BindingError) as exc:
        print(f"M2_BINDING_FAILED: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # fail closed; no internal traceback in production evidence
        print(f"M2_BINDING_FAILED: {type(exc).__name__}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
