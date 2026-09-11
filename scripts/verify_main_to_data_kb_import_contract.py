#!/usr/bin/env python3
"""Fail-closed verifier for the frozen Main → Data M1-KB import contract.

This is intentionally dependency-free so CI can detect receipt-hash drift and
the narrow Canonical/replay/retention invariants before service dependencies
are installed.  It verifies the frozen interface; it does not claim that M2
has executed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = Path("interfaces/main_to_data/kb_import_contract.json")
DEFAULT_RECEIPT = Path("interfaces/main_to_data/kb_import_contract_receipt.json")
DEFAULT_SNAPSHOT = Path("interfaces/main_to_data/schema_snapshot.json")
EXPECTED_KNOWLEDGE_TYPES = {
    "workflow", "case", "template", "fact", "constraint", "failure_experience"
}
EXPECTED_MEMORY_STATUSES = {
    "active", "superseded", "deprecated", "expired", "removed", "candidate"
}


class VerificationError(ValueError):
    """Raised for every contract or receipt invariant violation."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"{path} must contain a JSON object")
    return payload


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _value_set(snapshot: dict[str, Any], section: str, name: str) -> set[str]:
    try:
        values = snapshot["canonical"][section][name]["values"]
    except (KeyError, TypeError) as exc:
        raise VerificationError(f"snapshot missing canonical {name} values") from exc
    _require(isinstance(values, list) and all(isinstance(value, str) for value in values),
             f"snapshot {name} values must be a string list")
    return set(values)


def verify(*, contract_path: Path, receipt_path: Path, snapshot_path: Path) -> None:
    contract = _load_json(contract_path)
    receipt = _load_json(receipt_path)
    snapshot = _load_json(snapshot_path)

    _require(contract.get("schema") == "main_to_data_kb_import_contract", "unexpected contract schema")
    _require(contract.get("schema_version") == "2", "contract schema_version must be 2")
    _require(contract.get("status") == "FROZEN", "contract status must be FROZEN")
    _require(receipt.get("gate") == "M1-KB" and receipt.get("status") == "PASS", "receipt must be PASS for M1-KB")
    _require(receipt.get("contract_schema_version") == "2", "receipt schema version drift")
    actual_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    _require(receipt.get("contract_sha256") == actual_sha, "receipt contract_sha256 does not match contract bytes")

    required = contract["record_contract"]["accepted_record_result"]["required_fields"]
    _require({"accepted_version", "accepted_version_id", "accepted_memory_status"}.issubset(required),
             "accepted result must expose acceptance snapshot fields")
    _require(not {"version", "version_id", "memory_status"}.intersection(required),
             "accepted result must not present current-state fields")
    _require(set(required["accepted_memory_status"].get("enum", [])) == EXPECTED_MEMORY_STATUSES,
             "accepted_memory_status canonical values drift")

    _require(_value_set(snapshot, "additional_stable_value_sets", "knowledge_type") == EXPECTED_KNOWLEDGE_TYPES,
             "snapshot knowledge_type canonical values drift")
    _require(_value_set(snapshot, "core_value_sets", "memory_status") == EXPECTED_MEMORY_STATUSES,
             "snapshot memory_status canonical values drift")
    input_fields = contract["record_contract"]["required_input_fields"]
    _require(set(input_fields["knowledge_type"].get("enum", [])) == EXPECTED_KNOWLEDGE_TYPES,
             "contract knowledge_type values drift from Canonical snapshot")

    registry = contract["admission_and_idempotency"]["idempotency_registry"]
    replay = registry.get("replay_result_semantics", {})
    _require(replay.get("kind") == "acceptance_receipt_snapshot", "replay must return acceptance snapshot")
    _require(replay.get("current_row_lookup") == "prohibited", "replay must not return current row state")
    _require(set(replay.get("returns", [])) >= {"accepted_version", "accepted_version_id", "accepted_memory_status"},
             "replay snapshot fields incomplete")
    retention = registry.get("durable_retention", {})
    _require(retention.get("registry_kind") == "durable_import_identity_registry", "registry must be durable")
    _require(retention.get("ttl") == "none", "registry must not have a TTL")
    _require("must not reuse" in retention.get("request_cache_relation", ""),
             "registry must explicitly reject idempotency_cache reuse")
    _require("removed, expired, and superseded do not release" in retention.get("terminal_lifecycle", ""),
             "terminal lifecycle replay retention is not frozen")
    _require(contract["admission_and_idempotency"]["authorized_current_state_readback"].get("separate_from_import_response") is True,
             "current readback must be separate from import result")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=ROOT / DEFAULT_CONTRACT)
    parser.add_argument("--receipt", type=Path, default=ROOT / DEFAULT_RECEIPT)
    parser.add_argument("--snapshot", type=Path, default=ROOT / DEFAULT_SNAPSHOT)
    args = parser.parse_args()
    try:
        verify(contract_path=args.contract, receipt_path=args.receipt, snapshot_path=args.snapshot)
    except VerificationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: M1-KB contract receipt, Canonical enums, replay snapshot, and durable retention")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
