#!/usr/bin/env python3
"""Build and verify the Main-side M2 RC10 production import receipt.

The receipt is a deterministic function of the evidence package.  It records
only Main-side evidence readiness: ``M2 = PASS`` remains a Data-R adjudication
after independent review of this package.
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

from service.main_to_data_binding import parse_candidate_jsonl, sha256_lf  # noqa: E402


def _fail(message: str) -> None:
    raise SystemExit(f"M2_RECEIPT_FAILED: {message}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            _require(isinstance(value, dict), f"{path.name}: JSONL rows must be objects")
            records.append(value)
    return records


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_exit_code(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def collect(
    evidence_dir: Path,
    contract_path: Path,
    *,
    source_main_commit: str,
    source_main_commit_dirty: bool,
) -> dict[str, Any]:
    data_in = evidence_dir / "data_in"
    main_out = evidence_dir / "main_out"
    final_rc = evidence_dir / "final_rc"
    import_run = evidence_dir / "import_run"

    contract_bytes = contract_path.read_bytes()
    contract = json.loads(contract_bytes.decode("utf-8"))
    _require(contract.get("schema_version") == "2", "M1-KB contract schema_version must be 2")
    _require(contract.get("status") == "FROZEN", "M1-KB contract must be FROZEN")

    binding_request_path = data_in / "m2_main_binding_request.json"
    binding_request_bytes = binding_request_path.read_bytes()
    binding_request = json.loads(binding_request_bytes.decode("utf-8"))
    candidates_bytes = (data_in / "m2_prebinding_candidates_10.jsonl").read_bytes()
    candidates = parse_candidate_jsonl(candidates_bytes)
    _require(sha256_lf(candidates_bytes) == binding_request["candidate_file_sha256"], "candidate file SHA-256 (LF) mismatch")
    _require(binding_request["record_count"] == len(candidates) == 10, "binding request must cover 10 candidates")
    prebinding_manifest = _load_json(data_in / "m2_prebinding_manifest.json")
    _require(
        prebinding_manifest["prebinding_candidate_file_sha256"] == binding_request["candidate_file_sha256"],
        "prebinding manifest candidate SHA mismatch",
    )
    admission = _load_json(data_in / "v4.1_M2_DATAR_ADMISSION_20260911.json")
    _require(admission["status"] == "APPROVED_FOR_M2_RC_PREBINDING_ONLY", "Data-R admission is not the approved prebinding state")
    _require(
        admission["prebinding_candidate_file_sha256_lf"] == binding_request["candidate_file_sha256"],
        "Data-R admission candidate SHA mismatch",
    )
    _require(
        admission["approved_local_candidate_ids"] == [row["local_candidate_id"] for row in candidates],
        "Data-R approved candidate set does not match the candidate file",
    )

    provisioning = _load_json(main_out / "provisioning_results.json")
    _require(provisioning["record_count"] == 10, "provisioning must cover 10 candidates")
    _require(provisioning["source_type"] == "manual_config", "provisioning source_type is not the controlled descriptor")
    _require(
        provisioning["source_business_status"] == "success",
        "provisioning source_business_status is not the controlled descriptor",
    )
    provisioning_by_local = {row["local_candidate_id"]: row for row in provisioning["records"]}
    _require(set(provisioning_by_local) == {row["local_candidate_id"] for row in candidates}, "provisioning candidate set mismatch")

    binding = _load_json(main_out / "m2_rc_binding_response.json")
    _require(binding["schema"] == "main_to_data_m2_binding_response", "unexpected binding response schema")
    _require(binding["record_count"] == binding["bound_count"] == 10, "binding response must bind 10 records")
    _require(binding["candidate_file_sha256"] == binding_request["candidate_file_sha256"], "binding response candidate SHA mismatch")
    _require(binding["checks"] == {"cross_user": 0, "source_not_admitted": 0, "provenance_mismatch": 0, "fabricated_event": 0}, "binding checks are not all zero")
    binding_by_data_id = {row["data_record_id"]: row for row in binding["records"]}
    _require(len(binding_by_data_id) == 10, "binding response data_record_id values must be unique")
    bound_users = {row["user_id"] for row in binding["records"]}
    _require(len(bound_users) == 1, "binding must resolve to exactly one same-user scope")
    for candidate in candidates:
        bound = binding_by_data_id.get(candidate["data_record_id"])
        _require(bound is not None, "binding response is missing a candidate")
        _require(bound["local_candidate_id"] == candidate["local_candidate_id"], "binding local_candidate_id mismatch")
        _require(bound["admission_decision"] == "allow_extraction", "bound source is not admitted")
        _require(bound["source_event_id"] == provisioning_by_local[candidate["local_candidate_id"]]["event_id"], "bound source event mismatch")
        _require(bound["source_reference"] and bound["idempotency_key"], "binding lacks source_reference/idempotency_key")

    input_bytes = (final_rc / "input_rc_10.jsonl").read_bytes()
    manifest = _load_json(final_rc / "source_manifest.json")
    manifest_sha256 = (final_rc / "manifest_sha256.txt").read_text(encoding="utf-8").strip()
    _require(manifest["schema"] == "main_to_data_source_manifest" and manifest["schema_version"] == "1", "unexpected source manifest schema")
    _require(manifest["record_count"] == 10, "source manifest record_count must be 10")
    _require(_sha256(input_bytes) == manifest["data_rc_sha256"], "exact JSONL SHA-256 does not match source manifest")
    _require(_sha256(rfc8785.dumps(manifest)) == manifest_sha256, "RFC8785 source manifest SHA-256 mismatch")
    final_records = _load_jsonl(final_rc / "input_rc_10.jsonl")
    _require(len(final_records) == 10, "final RC must contain 10 records")
    candidate_by_data_id = {row["data_record_id"]: row for row in candidates}
    for record in final_records:
        bound = binding_by_data_id.get(record["data_record_id"])
        _require(bound is not None, "final RC record is not bound")
        candidate = candidate_by_data_id[record["data_record_id"]]
        _require(record["user_id"] == bound["user_id"], "final RC user_id differs from binding")
        _require(record["idempotency_key"] == bound["idempotency_key"], "final RC idempotency_key differs from binding")
        _require(
            record["source"]
            == {
                "source_event_id": bound["source_event_id"],
                "source_type": bound["source_type"],
                "source_business_status": bound["source_business_status"],
                "source_reference": bound["source_reference"],
            },
            "final RC source descriptor differs from binding",
        )
        _require(record["knowledge_type"] == candidate["knowledge_type"], "final RC knowledge_type differs from candidate")
        _require(record["memory_status"] == "candidate" and record["scope"] == "user", "final RC must enter as user/candidate")
        _require(0 <= float(record["confidence"]) <= 1, "final RC confidence must be within [0,1]")
        _require(record["content"]["content_summary"] == candidate["content_summary"], "final RC content differs from candidate")
    final_receipt = _load_json(final_rc / "m2_final_rc_receipt.json")
    _require(final_receipt.get("production_knowledge_id_generated") is False, "final RC must not generate production identities")

    results = _load_json(import_run / "per_record_results.json")
    _require(len(results) == 10, "import must return 10 per-record results")
    results_by_data_id = {row["data_record_id"]: row for row in results}
    _require(set(results_by_data_id) == set(binding_by_data_id), "import results do not match the binding set")
    knowledge_ids: set[str] = set()
    memory_ids: set[str] = set()
    for row in results:
        _require(row["accepted"] is True and row["replayed"] is False, "first acceptance must be accepted and not replayed")
        _require(row["accepted_version"] == 1 and row["accepted_version_id"] == "v1", "first acceptance must be v1")
        _require(row["accepted_memory_status"] == "candidate", "first acceptance must be candidate")
        _require(row["source_event_id"] == binding_by_data_id[row["data_record_id"]]["source_event_id"], "import source_event_id mismatch")
        knowledge_ids.add(row["knowledge_id"])
        memory_ids.add(row["memory_id"])
    _require(len(knowledge_ids) == 10 and len(memory_ids) == 10, "production identities must be unique")

    readbacks = _load_json(import_run / "readback.json")
    _require(len(readbacks) == 10, "readback must cover 10 accepted records")
    readback_by_knowledge = {row["knowledge_id"]: row for row in readbacks}
    for row in results:
        readback = readback_by_knowledge.get(row["knowledge_id"])
        _require(readback is not None, "readback is missing an accepted knowledge_id")
        _require(readback["memory_id"] == row["memory_id"], "readback memory_id mismatch")
        _require(readback["current_version"] == 1 and readback["current_version_id"] == "v1", "readback current version must be v1")
        _require(readback["current_memory_status"] == "candidate", "readback current status must be candidate")
        _require(readback["user_id"] == row["user_id"] and readback["scope"] == "user", "readback scope mismatch")

    replay = _load_json(import_run / "replay_results.json")
    _require(len(replay) == 10, "same-request replay must cover 10 records")
    for row in replay:
        original = results_by_data_id[row["data_record_id"]]
        _require(row["accepted"] is True and row["replayed"] is True, "same-request replay must set replayed=true")
        for field in (
            "knowledge_id",
            "memory_id",
            "accepted_version",
            "accepted_version_id",
            "accepted_memory_status",
            "source_event_id",
        ):
            _require(row[field] == original[field], f"same-request replay changed {field}")

    conflict = _load_json(import_run / "conflict_results.json")
    _require(len(conflict["records"]) == 10, "conflict replay must cover 10 records")
    for row in conflict["records"]:
        _require(row["accepted"] is False, "conflict probe must not be accepted")
        _require(row["reason_code"] == "idempotency_conflict", "conflict probe must return idempotency_conflict")
    _require(
        conflict["production_state_counts_before"] == conflict["production_state_counts_after"],
        "conflict replay changed production state",
    )

    state = _load_json(import_run / "state_counts.json")
    _require(
        state["production_state_counts_after_import"] == state["production_state_counts_after_replay"],
        "same-request replay changed production state",
    )
    _require(state.get("conflict_zero_extra_production_state") is True, "conflict probe did not prove zero extra state")
    _require(
        state["production_state_counts_after_import"]["knowledge_rows"] == 10
        and state["production_state_counts_after_import"]["evidence_relations"] == 10,
        "production import did not create exactly 10 knowledge rows and evidence relations",
    )

    _require(_read_exit_code(main_out / "provision_exit_code.txt") == "0", "provisioning runner did not exit 0")
    _require(_read_exit_code(main_out / "binding_exit_code.txt") == "0", "binding runner did not exit 0")
    _require(_read_exit_code(import_run / "exit_code.txt") == "0", "import runner did not exit 0")

    artifact_names = [
        "data_in/m2_main_binding_request.json",
        "data_in/m2_prebinding_candidates_10.jsonl",
        "data_in/v4.1_M2_DATAR_ADMISSION_20260911.json",
        "main_out/provisioning_results.json",
        "main_out/m2_rc_binding_response.json",
        "final_rc/input_rc_10.jsonl",
        "final_rc/source_manifest.json",
        "final_rc/m2_final_rc_receipt.json",
        "import_run/per_record_results.json",
        "import_run/readback.json",
        "import_run/replay_results.json",
        "import_run/conflict_results.json",
        "import_run/state_counts.json",
    ]
    artifact_sha256 = {
        name: sha256_lf((evidence_dir / name).read_bytes()) for name in artifact_names
    }

    return {
        "gate": "M2",
        "status": "PASS",
        "main_m2_evidence_ready": True,
        "final_m2_adjudication": "PENDING_DATA_R_REVIEW",
        "source_main_commit": source_main_commit,
        "source_main_commit_dirty": source_main_commit_dirty,
        "m1_contract_path": contract_path.relative_to(ROOT).as_posix(),
        "m1_contract_schema_version": contract["schema_version"],
        "m1_contract_sha256": sha256_lf(contract_bytes),
        "binding_request_sha256": sha256_lf(binding_request_bytes),
        "candidate_file_sha256": binding_request["candidate_file_sha256"],
        "data_rc_sha256": manifest["data_rc_sha256"],
        "source_manifest_sha256": manifest_sha256,
        "final_rc_receipt_sha256": sha256_lf((final_rc / "m2_final_rc_receipt.json").read_bytes()),
        "record_count": len(final_records),
        "binding_count": binding["bound_count"],
        "bound_user_count": len(bound_users),
        "imported_count": len(results),
        "rejected_count": 0,
        "readback_verified": True,
        "same_request_replay_verified": True,
        "conflict_replay_verified": True,
        "zero_extra_production_state": True,
        "production_path_used": True,
        "mock_used": False,
        "registry_kind": "durable_import_identity_registry",
        "registry_ttl": "none",
        "evidence_root": evidence_dir.relative_to(ROOT).as_posix(),
        "artifact_sha256": artifact_sha256,
        "notes": (
            "Main-side M2 evidence is ready. M2=PASS is not claimed by Main; "
            "Data-R performs the one-time final adjudication after independent review."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=ROOT / "interfaces/main_to_data/kb_import_contract.json")
    parser.add_argument("--source-main-commit", default=None)
    parser.add_argument("--source-main-dirty", action="store_true")
    parser.add_argument("--output", type=Path, default=None, help="Receipt output path (build mode)")
    parser.add_argument("--check", type=Path, default=None, help="Existing receipt to verify (check mode)")
    args = parser.parse_args()

    if args.check is not None:
        expected = json.loads(args.check.read_text(encoding="utf-8"))
        source_main_commit = expected.get("source_main_commit", args.source_main_commit)
        source_main_commit_dirty = bool(expected.get("source_main_commit_dirty", args.source_main_dirty))
    else:
        if not args.source_main_commit:
            parser.error("--source-main-commit is required in build mode")
        source_main_commit = args.source_main_commit
        source_main_commit_dirty = args.source_main_dirty

    evidence_dir = args.evidence_dir if args.evidence_dir.is_absolute() else ROOT / args.evidence_dir
    contract_path = args.contract if args.contract.is_absolute() else ROOT / args.contract
    receipt = collect(
        evidence_dir,
        contract_path,
        source_main_commit=source_main_commit,
        source_main_commit_dirty=source_main_commit_dirty,
    )
    encoded = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.check is not None:
        if json.loads(args.check.read_text(encoding="utf-8")) != receipt:
            _fail(f"receipt does not match evidence: {args.check}")
        print(f"M2_RECEIPT_CHECK_PASS: {args.check}")
        return 0

    if args.output is None:
        sys.stdout.write(encoded)
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8", newline="\n")
    print(f"WROTE {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
