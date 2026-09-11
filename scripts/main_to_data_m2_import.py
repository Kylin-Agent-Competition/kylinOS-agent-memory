#!/usr/bin/env python3
"""Controlled production runner for Main→Data M2 imports.

The runner is intentionally file-driven: the authenticated principal scope map,
final Data manifest and exact JSONL bytes are explicit evidence inputs.  It does
not create source events or repair provenance.  Missing/unadmitted/mismatched
Main source events fail closed in the production importer.

``--conflict-jsonl`` additionally executes a same-key/different-request negative
replay against the real production database and requires ``idempotency_conflict``
for every record with zero extra production state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import rfc8785

ROOT = Path(__file__).resolve().parents[1]
MEMORY_SERVICE = ROOT / "memory-service"
if str(MEMORY_SERVICE) not in sys.path:
    sys.path.insert(0, str(MEMORY_SERVICE))

from db.engine import create_db_engine  # noqa: E402
from service.main_to_data_import import (  # noqa: E402
    MainToDataImporter,
    TransportValidationError,
    build_static_scope_resolver,
)


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


def _state_counts(engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {
            "knowledge_rows": int(
                conn.exec_driver_sql(
                    "SELECT COUNT(*) FROM memory_entries WHERE entry_type='knowledge'"
                ).scalar_one()
            ),
            "evidence_relations": int(
                conn.exec_driver_sql(
                    "SELECT COUNT(*) FROM memory_relation WHERE relation_type='evidence'"
                ).scalar_one()
            ),
            "outbox_events": int(conn.exec_driver_sql("SELECT COUNT(*) FROM outbox").scalar_one()),
            "import_registry_rows": int(
                conn.exec_driver_sql("SELECT COUNT(*) FROM main_to_data_import_registry").scalar_one()
            ),
            "manifest_registry_rows": int(
                conn.exec_driver_sql("SELECT COUNT(*) FROM main_to_data_manifest_registry").scalar_one()
            ),
        }


def _manifest_for(jsonl_bytes: bytes, record_count: int) -> tuple[dict[str, Any], str]:
    manifest = {
        "schema": "main_to_data_source_manifest",
        "schema_version": "1",
        "data_rc_sha256": hashlib.sha256(jsonl_bytes).hexdigest(),
        "record_count": record_count,
    }
    manifest_sha = hashlib.sha256(rfc8785.dumps(manifest)).hexdigest()
    return manifest, manifest_sha


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="Migrated Main SQLite database")
    parser.add_argument("--principal", required=True, help="Trusted authenticated principal")
    parser.add_argument(
        "--scope-map",
        type=Path,
        required=True,
        help="Trusted JSON mapping: principal -> authorized user_id array",
    )
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--input-jsonl", type=Path, required=True)
    parser.add_argument("--result", type=Path, default=None)
    parser.add_argument("--readback", type=Path, default=None)
    parser.add_argument(
        "--verify-replay",
        action="store_true",
        help="Immediately replay the same request and require every accepted record to replay",
    )
    parser.add_argument("--replay-result", type=Path, default=None)
    parser.add_argument(
        "--conflict-jsonl",
        type=Path,
        default=None,
        help="Same-key/different-request negative replay input (must conflict for every record)",
    )
    parser.add_argument("--conflict-result", type=Path, default=None)
    parser.add_argument("--state-result", type=Path, default=None)
    args = parser.parse_args()

    try:
        scope_map = _load_object(args.scope_map)
        if any(not isinstance(users, list) for users in scope_map.values()):
            raise ValueError("scope-map values must be arrays")
        manifest = _load_object(args.manifest)
        jsonl_bytes = args.input_jsonl.read_bytes()

        engine = create_db_engine(str(args.db))
        importer = MainToDataImporter(
            engine,
            principal_scope_resolver=build_static_scope_resolver(scope_map),
        )
        state: dict[str, Any] = {"production_state_counts_before": _state_counts(engine)}
        results = importer.import_request(
            request_id=args.request_id,
            source_manifest_sha256=args.manifest_sha256,
            source_manifest=manifest,
            authenticated_principal=args.principal,
            jsonl_bytes=jsonl_bytes,
        )
        _write_json(args.result, results)
        state["production_state_counts_after_import"] = _state_counts(engine)

        accepted = [item for item in results if item.get("accepted") is True]
        if args.readback is not None:
            readbacks = [
                importer.readback(
                    authenticated_principal=args.principal,
                    user_id=item["user_id"],
                    knowledge_id=item["knowledge_id"],
                )
                for item in accepted
            ]
            _write_json(args.readback, readbacks)

        if args.verify_replay:
            replay = importer.import_request(
                request_id=args.request_id + ":replay",
                source_manifest_sha256=args.manifest_sha256,
                source_manifest=manifest,
                authenticated_principal=args.principal,
                jsonl_bytes=jsonl_bytes,
            )
            original_by_id = {item["data_record_id"]: item for item in accepted}
            for item in replay:
                if item.get("accepted") is True and item["data_record_id"] in original_by_id:
                    first = original_by_id[item["data_record_id"]]
                    if not item.get("replayed"):
                        raise RuntimeError("same-request replay did not set replayed=true")
                    for field in (
                        "knowledge_id",
                        "memory_id",
                        "accepted_version",
                        "accepted_version_id",
                        "accepted_memory_status",
                    ):
                        if item[field] != first[field]:
                            raise RuntimeError(f"same-request replay changed {field}")
            _write_json(args.replay_result, replay)
            state["production_state_counts_after_replay"] = _state_counts(engine)

        if args.conflict_jsonl is not None:
            conflict_bytes = args.conflict_jsonl.read_bytes()
            conflict_records = conflict_bytes.decode("utf-8").splitlines()
            conflict_manifest, conflict_manifest_sha = _manifest_for(
                conflict_bytes, len([line for line in conflict_records if line.strip()])
            )
            state["production_state_counts_before_conflict"] = _state_counts(engine)
            conflict_results = importer.import_request(
                request_id=args.request_id + ":conflict",
                source_manifest_sha256=conflict_manifest_sha,
                source_manifest=conflict_manifest,
                authenticated_principal=args.principal,
                jsonl_bytes=conflict_bytes,
            )
            for item in conflict_results:
                if item.get("accepted") is not False or item.get("reason_code") != "idempotency_conflict":
                    raise RuntimeError("same-key/different-request probe did not conflict")
            state["production_state_counts_after_conflict"] = _state_counts(engine)
            if state["production_state_counts_after_conflict"] != state["production_state_counts_before_conflict"]:
                raise RuntimeError("conflict replay changed production state")
            state["conflict_zero_extra_production_state"] = True
            _write_json(
                args.conflict_result,
                {
                    "request_id": args.request_id + ":conflict",
                    "records": conflict_results,
                    "production_state_counts_before": state["production_state_counts_before_conflict"],
                    "production_state_counts_after": state["production_state_counts_after_conflict"],
                },
            )

        if args.state_result is not None:
            _write_json(args.state_result, state)

        return 0 if all(item.get("accepted") is True for item in results) else 2
    except (OSError, json.JSONDecodeError, ValueError, TransportValidationError) as exc:
        print(f"M2_IMPORT_FAILED: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # fail closed; no internal traceback in production evidence stdout
        print(f"M2_IMPORT_FAILED: {type(exc).__name__}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
