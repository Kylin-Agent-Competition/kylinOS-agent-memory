"""M2 Main→Data RC10 source binding and controlled source provisioning.

The M2 worklist requires one real, same-user, ``allow_extraction`` Main source
event per Data RC record.  When no pre-existing provenance-compatible event
exists, the sanctioned path is Main's normal source-event ingestion/admission
pipeline -- never a manual ``source_events`` INSERT and never a hand-set
admission decision.

This module implements two cooperating boundaries:

* :class:`ControlledSourceProvisioner` drives the canonical ``event.ingest``
  handler (the same pipeline + ``SourceAdmissionPolicy`` + repository write path
  used by the validation profile) for OS controlled-authored RC content.  It is
  deterministic and idempotent: every candidate gets a stable ``event_id``,
  ingest ``idempotency_key``, ``source_reference`` and authored timestamp, so
  re-running provisioning replays the same real events instead of creating
  duplicates.
* :class:`M2BindingService` is read-only.  It validates the Data prebinding
  request and candidate file, then resolves each candidate to its real Main
  source event and fails closed on any missing, cross-user, unadmitted,
  descriptor-mismatched, or provenance-incompatible binding.

Neither boundary allocates a production ``knowledge_id``/``memory_id``/
``version``; that remains exclusive to the M1-KB v2 production importer.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence, Set

from db import repositories as repo
from db.uow import UnitOfWork
from gateway.handlers import register_default_handlers, register_event_ingest_handler
from gateway.registry import HandlerRegistry, RequestContext
from service.main_to_data_import import TransportValidationError


SCHEMA_PROVISIONING = "main_to_data_m2_source_provisioning"
SCHEMA_BINDING_RESPONSE = "main_to_data_m2_binding_response"
SCHEMA_VERSION = "1"
PROVISIONING_STATE = "CONTROLLED_SOURCES_PROVISIONED"
BINDING_STATE = "MAIN_SOURCE_BINDING_COMPLETE"
BINDING_GATE_STATUS = "READY_FOR_FINAL_RC"

CONTROLLED_AUTHORING_SOURCE_LAYER = "os_controlled_authored"
CONTROLLED_AUTHORING_SESSION_ID = "m2-rc10-controlled-authoring"
CONTROLLED_SOURCE_TYPE = "manual_config"
CONTROLLED_SOURCE_BUSINESS_STATUS = "success"
CONTROLLED_EVENT_TYPE = "system_message"
CONTROLLED_LANGUAGE_TAG = "zh-CN"
CONTROLLED_CONSENT_SCOPE = "memory_only"
DEFAULT_AUTHORED_AT = "2026-09-11T00:00:00+00:00"

EVENT_ID_PREFIX = "m2-rc10-src-"
INGEST_IDEMPOTENCY_PREFIX = "m2-rc10-ingest-"
IMPORT_IDEMPOTENCY_PREFIX = "m2-rc10-import-"

KNOWLEDGE_TYPES = {"workflow", "case", "template", "fact", "constraint", "failure_experience"}
_REQUIRED_PROVENANCE = ("source", "scenario_spec_id", "retrieval_sample")
_REQUIRED_MAIN_BINDING = (
    "user_id",
    "source_event_id",
    "source_type",
    "source_business_status",
    "source_reference",
    "idempotency_key",
)
_REQUIRED_FROM_MAIN = list(_REQUIRED_MAIN_BINDING) + ["admission_decision=allow_extraction"]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

PrincipalScopeResolver = Callable[[str], Iterable[str]]


class BindingError(ValueError):
    """Fail-closed binding/provisioning rejection with a stable reason code."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code
        self.detail = detail


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def sha256_lf(data: bytes) -> str:
    """Data-repo canonical hash basis: SHA-256 over LF-normalized bytes."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def event_id_for(local_candidate_id: str) -> str:
    return EVENT_ID_PREFIX + local_candidate_id


def ingest_idempotency_key_for(local_candidate_id: str) -> str:
    return INGEST_IDEMPOTENCY_PREFIX + local_candidate_id


def import_idempotency_key_for(local_candidate_id: str) -> str:
    return IMPORT_IDEMPOTENCY_PREFIX + local_candidate_id


def expected_source_reference(candidate: Mapping[str, Any]) -> str:
    """Derive the immutable Main source reference from Data candidate provenance."""
    provenance = candidate.get("candidate_provenance")
    if not isinstance(provenance, dict):
        raise BindingError("invalid_input", "candidate_provenance must be an object")
    source = provenance.get("source")
    if source != CONTROLLED_AUTHORING_SOURCE_LAYER:
        raise BindingError("invalid_input", "unsupported candidate provenance source layer")
    for field in ("scenario_spec_id", "retrieval_sample"):
        if not _nonempty(provenance.get(field)):
            raise BindingError("invalid_input", f"candidate_provenance.{field} must be non-empty")
    return f"{source}://{provenance['scenario_spec_id']}/{provenance['retrieval_sample']}"


def parse_candidate_jsonl(data: bytes) -> List[Dict[str, Any]]:
    """Parse and fail-closed validate the Data prebinding candidate JSONL."""
    try:
        text_value = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BindingError("invalid_input", "candidate JSONL must be UTF-8") from exc
    lines = text_value.splitlines()
    if not lines or any(not line.strip() for line in lines):
        raise BindingError("invalid_input", "candidate JSONL must contain no blank lines")
    candidates: List[Dict[str, Any]] = []
    seen_data_ids: Set[str] = set()
    seen_local_ids: Set[str] = set()
    for line in lines:
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BindingError("invalid_input", "candidate JSONL framing is invalid") from exc
        if not isinstance(candidate, dict):
            raise BindingError("invalid_input", "every candidate row must be an object")
        data_record_id = candidate.get("data_record_id")
        local_id = candidate.get("local_candidate_id")
        if not _nonempty(data_record_id) or not _nonempty(local_id):
            raise BindingError("invalid_input", "candidate identity fields must be non-empty")
        if data_record_id in seen_data_ids or local_id in seen_local_ids:
            raise BindingError("invalid_input", "candidate identities must be unique")
        seen_data_ids.add(data_record_id)
        seen_local_ids.add(local_id)
        if candidate.get("knowledge_type") not in KNOWLEDGE_TYPES:
            raise BindingError("invalid_input", f"{local_id}: unsupported knowledge_type")
        if not _nonempty(candidate.get("content_summary")):
            raise BindingError("invalid_input", f"{local_id}: content_summary must be non-empty")
        if candidate.get("production_binding_status") != "PRODUCTION_BINDING_PENDING":
            raise BindingError("invalid_input", f"{local_id}: candidate is not pending production binding")
        main_binding = candidate.get("main_binding")
        if not isinstance(main_binding, dict):
            raise BindingError("invalid_input", f"{local_id}: main_binding must be an object")
        for field in _REQUIRED_MAIN_BINDING:
            if main_binding.get(field) is not None:
                raise BindingError("fabricated_binding", f"{local_id}: main_binding.{field} must be null before Main binding")
        if main_binding.get("required_source_admission") != "allow_extraction":
            raise BindingError("invalid_input", f"{local_id}: required_source_admission must be allow_extraction")
        expected_source_reference(candidate)
        candidates.append(candidate)
    return candidates


def _parse_authored_at(value: str) -> datetime:
    if not _nonempty(value):
        raise BindingError("invalid_input", "authored_at must be non-empty")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BindingError("invalid_input", "authored_at must be ISO-8601") from exc
    if timestamp.tzinfo is None:
        raise BindingError("invalid_input", "authored_at must be timezone-aware")
    return timestamp.astimezone(timezone.utc)


class ControlledSourceProvisioner:
    """Create real Main source events through the canonical event.ingest path."""

    def __init__(
        self,
        engine,
        *,
        user_id: str,
        authored_at: str = DEFAULT_AUTHORED_AT,
    ) -> None:
        if not _nonempty(user_id):
            raise BindingError("invalid_input", "provisioning user_id must be non-empty")
        self._engine = engine
        self._user_id = user_id
        self._authored_at = _parse_authored_at(authored_at)
        registry = HandlerRegistry()
        register_default_handlers(registry)
        register_event_ingest_handler(registry, uow_factory=lambda: UnitOfWork(engine))
        self._handler = registry.route("event.ingest")

    def _payload(self, candidate: Mapping[str, Any], index: int) -> Dict[str, Any]:
        local_id = candidate["local_candidate_id"]
        occurred_at = (self._authored_at + timedelta(seconds=index)).isoformat()
        return {
            "schema_version": "0.1",
            "event_id": event_id_for(local_id),
            "user_id": self._user_id,
            "actor_id": self._user_id,
            "session_id": CONTROLLED_AUTHORING_SESSION_ID,
            "idempotency_key": ingest_idempotency_key_for(local_id),
            "source_type": CONTROLLED_SOURCE_TYPE,
            "event_type": CONTROLLED_EVENT_TYPE,
            "source_reference": expected_source_reference(candidate),
            "consent_scope": CONTROLLED_CONSENT_SCOPE,
            "source_business_status": CONTROLLED_SOURCE_BUSINESS_STATUS,
            "occurred_at": occurred_at,
            "captured_at": occurred_at,
            "content_summary": candidate["content_summary"],
            "sensitivity": "none",
            "payload_security_checked": True,
            "has_structured_payload": False,
            "language_tag": candidate.get("language_tag") or CONTROLLED_LANGUAGE_TAG,
        }

    def provision(self, candidates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        """Provision (or idempotently replay) one real source event per candidate."""
        records: List[Dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            local_id = candidate["local_candidate_id"]
            payload = self._payload(candidate, index)
            with self._engine.connect() as conn:
                existing = repo.get_source_event_by_event_id(
                    conn, user_id=self._user_id, event_id=payload["event_id"]
                )
            replayed = existing is not None
            if existing is None:
                ctx = RequestContext(
                    request_id=f"m2-rc10-provision-{local_id}",
                    trace_id=f"m2-rc10-trace-{local_id}",
                    method="event.ingest",
                    deadline_ms=30000,
                    idempotency_key=None,
                )
                response = self._handler(payload, ctx)
                admission = response.get("admission_decision")
                if admission != "allow_extraction":
                    raise BindingError(
                        "source_not_admitted",
                        f"{local_id}: event.ingest admission_decision={admission}",
                    )
            with self._engine.connect() as conn:
                row = repo.get_source_event_by_event_id(
                    conn, user_id=self._user_id, event_id=payload["event_id"]
                )
            if row is None:
                raise BindingError("source_not_admitted", f"{local_id}: source event missing after ingest")
            if row["admission_decision"] != "allow_extraction":
                raise BindingError("source_not_admitted", f"{local_id}: persisted admission is not allow_extraction")
            if row["content_summary"] != candidate["content_summary"]:
                raise BindingError("provenance_mismatch", f"{local_id}: persisted content differs from candidate")
            if row["source_reference"] != payload["source_reference"]:
                raise BindingError("provenance_mismatch", f"{local_id}: persisted source_reference differs")
            records.append(
                {
                    "data_record_id": candidate["data_record_id"],
                    "local_candidate_id": local_id,
                    "event_id": payload["event_id"],
                    "source_event_row_id": int(row["id"]),
                    "user_id": self._user_id,
                    "source_type": row["source_type"],
                    "source_business_status": row["source_business_status"],
                    "source_reference": row["source_reference"],
                    "admission_decision": row["admission_decision"],
                    "ingest_replayed": replayed,
                }
            )
        return {
            "schema": SCHEMA_PROVISIONING,
            "schema_version": SCHEMA_VERSION,
            "state": PROVISIONING_STATE,
            "user_id": self._user_id,
            "source_layer": CONTROLLED_AUTHORING_SOURCE_LAYER,
            "session_id": CONTROLLED_AUTHORING_SESSION_ID,
            "source_type": CONTROLLED_SOURCE_TYPE,
            "source_business_status": CONTROLLED_SOURCE_BUSINESS_STATUS,
            "event_type": CONTROLLED_EVENT_TYPE,
            "language_tag": CONTROLLED_LANGUAGE_TAG,
            "consent_scope": CONTROLLED_CONSENT_SCOPE,
            "authored_at": self._authored_at.isoformat(),
            "record_count": len(records),
            "records": records,
        }


def _validate_binding_request(binding_request: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(binding_request, dict):
        raise TransportValidationError("binding_request must be a JSON object")
    if binding_request.get("schema") != "main_to_data_m2_prebinding_request":
        raise TransportValidationError("unsupported binding_request schema")
    if binding_request.get("schema_version") != SCHEMA_VERSION:
        raise TransportValidationError("unsupported binding_request schema_version")
    if binding_request.get("state") != "PREBINDING_NOT_IMPORTABLE":
        raise TransportValidationError("binding_request is not in the prebinding state")
    if binding_request.get("m2_gate_status") != "BLOCKED_MAIN_SOURCE_BINDING":
        raise TransportValidationError("binding_request is not blocked on Main source binding")
    candidate_sha = binding_request.get("candidate_file_sha256")
    if not isinstance(candidate_sha, str) or not _SHA256_RE.fullmatch(candidate_sha):
        raise TransportValidationError("binding_request.candidate_file_sha256 is invalid")
    count = binding_request.get("record_count")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise TransportValidationError("binding_request.record_count must be a positive integer")
    records = binding_request.get("records")
    if not isinstance(records, list) or len(records) != count:
        raise TransportValidationError("binding_request.records does not match record_count")
    for record in records:
        if not isinstance(record, dict):
            raise TransportValidationError("binding_request.records entries must be objects")
        if not _nonempty(record.get("data_record_id")) or not _nonempty(record.get("local_candidate_id")):
            raise TransportValidationError("binding_request record identity must be non-empty")
        required = record.get("required_from_main")
        if not isinstance(required, list) or any(item not in required for item in _REQUIRED_FROM_MAIN):
            raise TransportValidationError("binding_request record does not require the full Main binding")
    return dict(binding_request)


def _validate_provisioning_results(
    provisioning_results: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(provisioning_results, dict):
        raise TransportValidationError("provisioning_results must be a JSON object")
    if provisioning_results.get("schema") != SCHEMA_PROVISIONING:
        raise TransportValidationError("unsupported provisioning_results schema")
    if provisioning_results.get("schema_version") != SCHEMA_VERSION:
        raise TransportValidationError("unsupported provisioning_results schema_version")
    if provisioning_results.get("state") != PROVISIONING_STATE:
        raise TransportValidationError("provisioning_results is not in the provisioned state")
    if provisioning_results.get("source_layer") != CONTROLLED_AUTHORING_SOURCE_LAYER:
        raise TransportValidationError("provisioning_results source layer is not controlled authoring")
    if provisioning_results.get("source_type") != CONTROLLED_SOURCE_TYPE:
        raise TransportValidationError("provisioning_results source_type is not the controlled descriptor")
    if provisioning_results.get("source_business_status") != CONTROLLED_SOURCE_BUSINESS_STATUS:
        raise TransportValidationError("provisioning_results source_business_status is not the controlled descriptor")
    if provisioning_results.get("session_id") != CONTROLLED_AUTHORING_SESSION_ID:
        raise TransportValidationError("provisioning_results session_id is not the controlled authoring session")
    if not _nonempty(provisioning_results.get("user_id")):
        raise TransportValidationError("provisioning_results.user_id must be non-empty")
    records = provisioning_results.get("records")
    if not isinstance(records, list) or len(records) != len(candidates):
        raise TransportValidationError("provisioning_results.records does not match candidate count")
    by_local: Dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or not _nonempty(record.get("local_candidate_id")):
            raise TransportValidationError("provisioning_results record is malformed")
        local_id = record["local_candidate_id"]
        if local_id in by_local:
            raise TransportValidationError("provisioning_results record identity is duplicated")
        by_local[local_id] = record
    for candidate in candidates:
        local_id = candidate["local_candidate_id"]
        record = by_local.get(local_id)
        if record is None:
            raise TransportValidationError(f"provisioning_results is missing {local_id}")
        if record.get("event_id") != event_id_for(local_id):
            raise TransportValidationError(f"provisioning_results {local_id} event_id is not the controlled identity")
        if record.get("user_id") != provisioning_results["user_id"]:
            raise TransportValidationError(f"provisioning_results {local_id} crosses the provisioning user")
        if record.get("admission_decision") != "allow_extraction":
            raise TransportValidationError(f"provisioning_results {local_id} is not admitted")
        if record.get("source_reference") != expected_source_reference(candidate):
            raise TransportValidationError(f"provisioning_results {local_id} source_reference is not provenance-derived")
    return {"provisioning": dict(provisioning_results), "by_local": by_local}


class M2BindingService:
    """Read-only Main source binding resolver for the Data prebinding request."""

    def __init__(self, engine, *, principal_scope_resolver: PrincipalScopeResolver) -> None:
        self._engine = engine
        self._principal_scope_resolver = principal_scope_resolver

    def _authorized_users(self, principal: str) -> Set[str]:
        if not _nonempty(principal):
            raise TransportValidationError("authenticated_principal must be non-empty")
        try:
            users = {str(value) for value in self._principal_scope_resolver(principal)}
        except Exception as exc:
            raise TransportValidationError("authenticated principal cannot be resolved") from exc
        users = {value for value in users if value.strip()}
        if not users:
            raise TransportValidationError("authenticated principal has no binding scope")
        return users

    def bind(
        self,
        *,
        binding_request: Mapping[str, Any],
        candidates_bytes: bytes,
        provisioning_results: Mapping[str, Any],
        authenticated_principal: str,
    ) -> Dict[str, Any]:
        """Resolve every candidate to its real admitted Main source event."""
        request = _validate_binding_request(binding_request)
        if sha256_lf(candidates_bytes) != request["candidate_file_sha256"]:
            raise TransportValidationError("candidate file SHA-256 (LF) does not match binding_request")
        candidates = parse_candidate_jsonl(candidates_bytes)
        if len(candidates) != request["record_count"]:
            raise TransportValidationError("candidate count does not match binding_request.record_count")
        request_by_local = {record["local_candidate_id"]: record for record in request["records"]}
        for candidate in candidates:
            request_record = request_by_local.get(candidate["local_candidate_id"])
            if request_record is None:
                raise TransportValidationError("binding_request is missing a candidate")
            if request_record["data_record_id"] != candidate["data_record_id"]:
                raise TransportValidationError("binding_request/candidate data_record_id mismatch")
        validated = _validate_provisioning_results(provisioning_results, candidates)
        provisioning = validated["provisioning"]
        authorized = self._authorized_users(authenticated_principal)
        if provisioning["user_id"] not in authorized:
            raise TransportValidationError("provisioning user is outside the authenticated binding scope")

        bound_records: List[Dict[str, Any]] = []
        with self._engine.connect() as conn:
            for candidate in candidates:
                local_id = candidate["local_candidate_id"]
                provisioning_record = validated["by_local"][local_id]
                event = repo.get_source_event_by_event_id(
                    conn, user_id=provisioning["user_id"], event_id=provisioning_record["event_id"]
                )
                if event is None:
                    raise BindingError("source_not_admitted", f"{local_id}: source event does not exist")
                if event["admission_decision"] != "allow_extraction":
                    raise BindingError("source_not_admitted", f"{local_id}: source event is not admitted")
                expected_reference = expected_source_reference(candidate)
                if event["source_reference"] != expected_reference:
                    raise BindingError("provenance_mismatch", f"{local_id}: source_reference mismatch")
                if event["content_summary"] != candidate["content_summary"]:
                    raise BindingError("provenance_mismatch", f"{local_id}: source content mismatch")
                if (
                    event["source_type"] != provisioning["source_type"]
                    or event["source_business_status"] != provisioning["source_business_status"]
                ):
                    raise BindingError("provenance_mismatch", f"{local_id}: source descriptor mismatch")
                bound_records.append(
                    {
                        "data_record_id": candidate["data_record_id"],
                        "local_candidate_id": local_id,
                        "user_id": event["user_id"],
                        "source_event_id": event["event_id"],
                        "source_type": event["source_type"],
                        "source_business_status": event["source_business_status"],
                        "source_reference": event["source_reference"],
                        "idempotency_key": import_idempotency_key_for(local_id),
                        "admission_decision": event["admission_decision"],
                        "provenance_basis": "content_summary_exact_match+source_reference_match",
                    }
                )

        return {
            "schema": SCHEMA_BINDING_RESPONSE,
            "schema_version": SCHEMA_VERSION,
            "state": BINDING_STATE,
            "m2_gate_status": BINDING_GATE_STATUS,
            "candidate_file_sha256": request["candidate_file_sha256"],
            "binding_request_record_count": request["record_count"],
            "record_count": len(bound_records),
            "bound_count": len(bound_records),
            "checks": {
                "cross_user": 0,
                "source_not_admitted": 0,
                "provenance_mismatch": 0,
                "fabricated_event": 0,
            },
            "records": bound_records,
        }


def build_static_scope_resolver(mapping: Mapping[str, Sequence[str]]) -> PrincipalScopeResolver:
    """Build a deterministic trusted-principal resolver for controlled binding jobs."""
    frozen = {str(principal): tuple(str(user) for user in users) for principal, users in mapping.items()}

    def _resolve(principal: str) -> Iterable[str]:
        return frozen.get(principal, ())

    return _resolve
