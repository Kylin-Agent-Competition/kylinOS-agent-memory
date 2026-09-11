"""Production Main→Data M2 knowledge import service.

This module implements the frozen M1-KB v2 boundary:

* authenticated principal → explicit user scope resolution;
* RFC 8785 manifest and per-record canonical request hashing;
* exact JSONL-byte SHA-256 and record-count verification;
* strict fail-closed record/source validation;
* Main-only production identity allocation through ``insert_knowledge_entry``;
* durable, no-TTL first-acceptance replay registry;
* authorized current-state readback kept separate from import receipts.

It deliberately does not manufacture RC10 binding/evidence.  Real M2 evidence
must be produced against admitted Main source events and the final Data RC10.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set

import rfc8785
from sqlalchemy import and_, insert, select, text
from sqlalchemy.exc import IntegrityError

from db import repositories as repo
from db.m2_schema import main_to_data_import_registry, main_to_data_manifest_registry
from db.uow import UnitOfWork


_KNOWLEDGE_TYPES = {"workflow", "case", "template", "fact", "constraint", "failure_experience"}
_MEMORY_STATUSES = {"active", "superseded", "deprecated", "expired", "removed", "candidate"}
_SOURCE_TYPES = {"chat", "tool_result", "manual_config", "recollect", "file", "meeting", "voice"}
_SOURCE_STATUSES = {"raw", "completed", "success", "partial", "failed", "cancelled", "timeout", "ignored"}
_RECORD_REQUIRED = {
    "data_record_id",
    "user_id",
    "knowledge_type",
    "memory_status",
    "scope",
    "content",
    "confidence",
    "source",
    "idempotency_key",
}
_RECORD_OPTIONAL = {"conditions", "topic_key", "trace_id"}
_RECORD_ALLOWED = _RECORD_REQUIRED | _RECORD_OPTIONAL
_CONTENT_REQUIRED = {"content_summary"}
_CONTENT_OPTIONAL = {"content_ref", "primary_category", "language_tag", "extracted_entities"}
_SOURCE_REQUIRED = {"source_event_id", "source_type", "source_business_status", "source_reference"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TransportValidationError(ValueError):
    """Request-level failure: no per-record acceptance results may be emitted."""


class RecordRejected(ValueError):
    """Fail-closed per-record rejection with a stable reason code."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code
        self.detail = detail


PrincipalScopeResolver = Callable[[str], Iterable[str]]


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _jcs_sha256(value: Any) -> str:
    try:
        canonical = rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
        raise ValueError("value cannot be RFC8785 canonicalized") from exc
    return _sha256(canonical)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_object(raw: bytes, *, context: str) -> Dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TransportValidationError(f"invalid {context} JSON") from exc
    if not isinstance(value, dict):
        raise TransportValidationError(f"{context} must be a JSON object")
    return value


def _strict_keys(value: Mapping[str, Any], *, required: Set[str], allowed: Set[str], context: str) -> None:
    missing = required - set(value)
    unknown = set(value) - allowed
    if missing:
        raise RecordRejected("invalid_input", f"{context} missing required fields")
    if unknown:
        raise RecordRejected("unknown_field", f"{context} contains unknown fields")


def _validate_nullable_nonblank(value: Any, *, field: str) -> None:
    if value is not None and not _nonempty(value):
        raise RecordRejected("invalid_input", f"{field} must be non-blank when present")


def _validate_record_shape(record: Dict[str, Any]) -> None:
    _strict_keys(record, required=_RECORD_REQUIRED, allowed=_RECORD_ALLOWED, context="record")

    for field in ("data_record_id", "user_id", "idempotency_key"):
        if not _nonempty(record[field]):
            raise RecordRejected("invalid_input", f"{field} must be non-empty")
    if record["knowledge_type"] not in _KNOWLEDGE_TYPES:
        raise RecordRejected("unknown_enum", "unknown knowledge_type")
    if record["memory_status"] != "candidate":
        raise RecordRejected("unknown_enum", "memory_status must be candidate")
    if record["scope"] != "user":
        raise RecordRejected("unauthorized_scope", "scope must be user")

    confidence = record["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise RecordRejected("invalid_input", "confidence must be a number in [0,1]")

    content = record["content"]
    if not isinstance(content, dict):
        raise RecordRejected("invalid_input", "content must be an object")
    _strict_keys(
        content,
        required=_CONTENT_REQUIRED,
        allowed=_CONTENT_REQUIRED | _CONTENT_OPTIONAL,
        context="content",
    )
    if not _nonempty(content["content_summary"]):
        raise RecordRejected("invalid_input", "content_summary must be non-empty")
    for field in ("content_ref", "primary_category", "language_tag"):
        if field in content:
            _validate_nullable_nonblank(content[field], field=f"content.{field}")
    if "extracted_entities" in content and content["extracted_entities"] is not None:
        entities = content["extracted_entities"]
        if not isinstance(entities, list) or any(not isinstance(item, str) for item in entities):
            raise RecordRejected("invalid_input", "content.extracted_entities must be a string array")

    source = record["source"]
    if not isinstance(source, dict):
        raise RecordRejected("invalid_input", "source must be an object")
    _strict_keys(source, required=_SOURCE_REQUIRED, allowed=_SOURCE_REQUIRED, context="source")
    for field in _SOURCE_REQUIRED:
        if not _nonempty(source[field]):
            raise RecordRejected("invalid_input", f"source.{field} must be non-empty")
    if source["source_type"] not in _SOURCE_TYPES:
        raise RecordRejected("unknown_enum", "unknown source_type")
    if source["source_business_status"] not in _SOURCE_STATUSES:
        raise RecordRejected("unknown_enum", "unknown source_business_status")

    for field in ("conditions", "topic_key", "trace_id"):
        if field in record:
            _validate_nullable_nonblank(record[field], field=field)


def _canonical_request_projection(record: Dict[str, Any]) -> Dict[str, Any]:
    fields = [
        "data_record_id",
        "user_id",
        "knowledge_type",
        "memory_status",
        "scope",
        "content",
        "confidence",
        "source",
        "idempotency_key",
        "conditions",
        "topic_key",
    ]
    return {field: record[field] for field in fields if field in record}


def _rejected(data_record_id: Any, reason_code: str, detail: str) -> Dict[str, Any]:
    return {
        "data_record_id": data_record_id if isinstance(data_record_id, str) else None,
        "accepted": False,
        "replayed": False,
        "reason_code": reason_code,
        "reason_detail": detail,
    }


class MainToDataImporter:
    """Strict M1-KB v2 production importer bound to a trusted principal resolver."""

    def __init__(self, engine, *, principal_scope_resolver: PrincipalScopeResolver) -> None:
        self._engine = engine
        self._principal_scope_resolver = principal_scope_resolver

    def _authorized_users(self, principal: str) -> Set[str]:
        if not _nonempty(principal):
            raise TransportValidationError("authenticated_principal must be non-empty")
        try:
            users = {str(value) for value in self._principal_scope_resolver(principal)}
        except Exception as exc:  # fail closed at the authentication boundary
            raise TransportValidationError("authenticated principal cannot be resolved") from exc
        users = {value for value in users if value.strip()}
        if not users:
            raise TransportValidationError("authenticated principal has no import scope")
        return users

    @staticmethod
    def _validate_manifest(manifest: Dict[str, Any], manifest_sha256: str, jsonl_bytes: bytes) -> int:
        if not _SHA256_RE.fullmatch(manifest_sha256 or ""):
            raise TransportValidationError("source_manifest_sha256 must be lowercase SHA-256")
        expected = {"schema", "schema_version", "data_rc_sha256", "record_count"}
        if set(manifest) != expected:
            raise TransportValidationError("source_manifest fields do not match contract")
        if manifest.get("schema") != "main_to_data_source_manifest" or manifest.get("schema_version") != "1":
            raise TransportValidationError("unsupported source_manifest schema")
        data_sha = manifest.get("data_rc_sha256")
        if not isinstance(data_sha, str) or not _SHA256_RE.fullmatch(data_sha):
            raise TransportValidationError("source_manifest.data_rc_sha256 is invalid")
        count = manifest.get("record_count")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise TransportValidationError("source_manifest.record_count must be a positive integer")
        if _jcs_sha256(manifest) != manifest_sha256:
            raise TransportValidationError("source_manifest_sha256 mismatch")
        if _sha256(jsonl_bytes) != data_sha:
            raise TransportValidationError("exact JSONL SHA-256 mismatch")
        return count

    @staticmethod
    def _parse_jsonl(jsonl_bytes: bytes, expected_count: int) -> List[Dict[str, Any]]:
        try:
            text_value = jsonl_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TransportValidationError("JSONL must be UTF-8") from exc
        lines = text_value.splitlines()
        if any(not line.strip() for line in lines):
            raise TransportValidationError("blank JSONL records are not allowed")
        if len(lines) != expected_count:
            raise TransportValidationError("source_manifest.record_count mismatch")
        records: List[Dict[str, Any]] = []
        for line in lines:
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TransportValidationError("invalid JSONL framing") from exc
            if not isinstance(value, dict):
                raise TransportValidationError("every JSONL record must be an object")
            records.append(value)
        return records

    def import_request(
        self,
        *,
        request_id: str,
        source_manifest_sha256: str,
        source_manifest: Dict[str, Any],
        authenticated_principal: str,
        jsonl_bytes: bytes,
    ) -> List[Dict[str, Any]]:
        """Execute a production import request and return one result per JSONL record."""
        if not _nonempty(request_id):
            raise TransportValidationError("request_id must be non-empty")
        authorized_users = self._authorized_users(authenticated_principal)
        expected_count = self._validate_manifest(source_manifest, source_manifest_sha256, jsonl_bytes)
        records = self._parse_jsonl(jsonl_bytes, expected_count)

        seen_data_ids: Set[str] = set()
        results: List[Dict[str, Any]] = []
        for record in records:
            raw_id = record.get("data_record_id")
            if isinstance(raw_id, str) and raw_id in seen_data_ids:
                results.append(_rejected(raw_id, "duplicate_data_record", "duplicate data_record_id in manifest"))
                continue
            if isinstance(raw_id, str):
                seen_data_ids.add(raw_id)
            try:
                _validate_record_shape(record)
                if record["user_id"] not in authorized_users:
                    raise RecordRejected("unauthorized_scope", "record user_id is outside authenticated scope")
                results.append(self._import_one(record, source_manifest_sha256))
            except RecordRejected as exc:
                results.append(_rejected(raw_id, exc.reason_code, exc.detail))
            except Exception:
                # Do not expose SQLite/implementation details across the import boundary.
                results.append(_rejected(raw_id, "persistence_failure", "production persistence failed"))
        return results

    def _stored_replay(self, row: Mapping[str, Any], *, canonical_hash: str, data_record_id: str) -> Dict[str, Any]:
        if row["canonical_request_sha256"] != canonical_hash or row["data_record_id"] != data_record_id:
            raise RecordRejected("idempotency_conflict", "idempotency key reused for a different request")
        receipt = json.loads(row["receipt_json"])
        receipt["replayed"] = True
        return receipt

    def _import_one(self, record: Dict[str, Any], manifest_sha256: str) -> Dict[str, Any]:
        canonical_hash = _jcs_sha256(_canonical_request_projection(record))
        # A cross-process unique-key race rolls back the losing transaction.  One
        # retry then observes the durable winner and returns its immutable receipt.
        for attempt in range(2):
            try:
                with UnitOfWork(self._engine) as uow:
                    conn = uow.conn
                    existing = conn.execute(
                        select(main_to_data_import_registry).where(
                            and_(
                                main_to_data_import_registry.c.user_id == record["user_id"],
                                main_to_data_import_registry.c.idempotency_key == record["idempotency_key"],
                            )
                        )
                    ).mappings().first()
                    if existing is not None:
                        return self._stored_replay(
                            existing,
                            canonical_hash=canonical_hash,
                            data_record_id=record["data_record_id"],
                        )

                    manifest_row = conn.execute(
                        select(main_to_data_manifest_registry).where(
                            and_(
                                main_to_data_manifest_registry.c.user_id == record["user_id"],
                                main_to_data_manifest_registry.c.source_manifest_sha256 == manifest_sha256,
                                main_to_data_manifest_registry.c.data_record_id == record["data_record_id"],
                            )
                        )
                    ).mappings().first()
                    if manifest_row is not None:
                        if manifest_row["canonical_request_sha256"] != canonical_hash:
                            raise RecordRejected("duplicate_data_record", "manifest record identity reused with different request")
                        receipt = json.loads(manifest_row["receipt_json"])
                        receipt["replayed"] = True
                        return receipt

                    source = record["source"]
                    event = repo.get_source_event_by_event_id(
                        conn,
                        user_id=record["user_id"],
                        event_id=source["source_event_id"],
                    )
                    if event is None or event.get("admission_decision") != "allow_extraction":
                        raise RecordRejected("source_not_admitted", "source event is missing or not admitted")
                    if (
                        event.get("source_type") != source["source_type"]
                        or event.get("source_business_status") != source["source_business_status"]
                        or event.get("source_reference") != source["source_reference"]
                    ):
                        raise RecordRejected("source_not_admitted", "source descriptor does not match Main registry")

                    knowledge_id = uuid.uuid4().hex
                    try:
                        persisted = repo.insert_knowledge_entry(
                            conn,
                            user_id=record["user_id"],
                            knowledge_id=knowledge_id,
                            knowledge_type=record["knowledge_type"],
                            source_event_id=source["source_event_id"],
                            content=record["content"],
                            confidence=float(record["confidence"]),
                            conditions=record.get("conditions"),
                            trace_id=record.get("trace_id"),
                            topic_key=record.get("topic_key"),
                        )
                    except ValueError as exc:
                        raise RecordRejected("source_not_admitted", "source event cannot persist this knowledge record") from exc

                    current = conn.execute(
                        text(
                            "SELECT id, version, memory_status FROM memory_entries "
                            "WHERE user_id=:user_id AND knowledge_id=:knowledge_id AND entry_type='knowledge'"
                        ),
                        {"user_id": record["user_id"], "knowledge_id": knowledge_id},
                    ).mappings().first()
                    if current is None:
                        raise RuntimeError("accepted knowledge row cannot be read back in transaction")
                    if int(current["version"]) != 1 or current["memory_status"] != "candidate":
                        raise RuntimeError("first acceptance must be v1/candidate")
                    memory_id = str(current["id"])
                    if persisted.get("memory_id") != memory_id or persisted.get("version_id") != "v1":
                        raise RuntimeError("repository production identity mismatch")

                    receipt = {
                        "data_record_id": record["data_record_id"],
                        "accepted": True,
                        "knowledge_id": knowledge_id,
                        "memory_id": memory_id,
                        "accepted_version": 1,
                        "accepted_version_id": "v1",
                        "accepted_memory_status": "candidate",
                        "user_id": record["user_id"],
                        "scope": "user",
                        "knowledge_type": record["knowledge_type"],
                        "source_event_id": source["source_event_id"],
                        "replayed": False,
                    }
                    receipt_json = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    created_at = _utc_now()
                    conn.execute(
                        insert(main_to_data_import_registry).values(
                            user_id=record["user_id"],
                            idempotency_key=record["idempotency_key"],
                            canonical_request_sha256=canonical_hash,
                            data_record_id=record["data_record_id"],
                            knowledge_id=knowledge_id,
                            memory_id=memory_id,
                            accepted_version=1,
                            accepted_version_id="v1",
                            accepted_memory_status="candidate",
                            source_event_id=source["source_event_id"],
                            result_status="accepted",
                            receipt_json=receipt_json,
                            created_at=created_at,
                        )
                    )
                    conn.execute(
                        insert(main_to_data_manifest_registry).values(
                            user_id=record["user_id"],
                            source_manifest_sha256=manifest_sha256,
                            data_record_id=record["data_record_id"],
                            canonical_request_sha256=canonical_hash,
                            idempotency_key=record["idempotency_key"],
                            receipt_json=receipt_json,
                            created_at=created_at,
                        )
                    )
                    return receipt
            except IntegrityError:
                if attempt == 0:
                    continue
                raise
        raise RuntimeError("unreachable import retry state")

    def readback(
        self,
        *,
        authenticated_principal: str,
        user_id: str,
        knowledge_id: str,
    ) -> Dict[str, Any]:
        """Authorized current-state readback, intentionally separate from import replay."""
        if user_id not in self._authorized_users(authenticated_principal):
            raise PermissionError("user_id is outside authenticated scope")
        if not _nonempty(knowledge_id):
            raise ValueError("knowledge_id must be non-empty")
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id, version, memory_status FROM memory_entries "
                    "WHERE user_id=:user_id AND knowledge_id=:knowledge_id AND entry_type='knowledge'"
                ),
                {"user_id": user_id, "knowledge_id": knowledge_id},
            ).mappings().first()
        if row is None:
            raise LookupError("knowledge record not found in authorized scope")
        return {
            "knowledge_id": knowledge_id,
            "memory_id": str(row["id"]),
            "current_version": int(row["version"]),
            "current_version_id": f"v{int(row['version'])}",
            "current_memory_status": row["memory_status"],
            "user_id": user_id,
            "scope": "user",
        }


def build_static_scope_resolver(mapping: Mapping[str, Sequence[str]]) -> PrincipalScopeResolver:
    """Build a deterministic trusted-principal resolver for controlled import jobs."""
    frozen = {str(principal): tuple(str(user) for user in users) for principal, users in mapping.items()}

    def _resolve(principal: str) -> Iterable[str]:
        return frozen.get(principal, ())

    return _resolve
