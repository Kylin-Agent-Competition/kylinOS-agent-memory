"""L1 tests for the Main→Data M2 production import boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest
import rfc8785

from db import repositories as repo
from db.engine import create_db_engine, init_schema
from service.main_to_data_import import MainToDataImporter, TransportValidationError, build_static_scope_resolver


USER = "m2-user"
PRINCIPAL = "m2-principal"
EVENT_ID = "m2-source-1"
SOURCE_REF = "main://source/m2-source-1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture()
def env(tmp_path):
    engine = create_db_engine(str(tmp_path / "m2.db"))
    # Importing MainToDataImporter registers M2 tables on shared metadata, so
    # test/dev create_all matches the production Alembic migration shape.
    init_schema(engine)
    now = _now()
    with engine.begin() as conn:
        repo.insert_source_event(
            conn,
            user_id=USER,
            event_id=EVENT_ID,
            actor_id=USER,
            session_id="m2-session",
            turn_id=None,
            tool_call_id=None,
            source_type="manual_config",
            event_type="user_message",
            schema_version="0.1",
            trace_id="m2-trace",
            source_reference=SOURCE_REF,
            raw_payload_ref=None,
            content_summary="real admitted provenance for M2 L1",
            idempotency_key="source-idem-1",
            consent_scope="memory_only",
            source_business_status="success",
            sensitivity="none",
            is_sensitive_matched=0,
            should_ignore=0,
            payload_security_checked=1,
            memory_type=None,
            requires_embedding=0,
            has_structured_payload=1,
            language_tag="en",
            occurred_at=now,
            captured_at=now,
            content_fingerprint="m2-source-fingerprint",
            dedup_group=None,
            duplicate_of=None,
            admission_decision="allow_extraction",
            admission_reason_code="ok",
            processing_status="pending",
            created_at=now,
            updated_at=now,
        )
    importer = MainToDataImporter(
        engine,
        principal_scope_resolver=build_static_scope_resolver({PRINCIPAL: [USER]}),
    )
    yield engine, importer
    engine.dispose()


def _record(**overrides):
    value = {
        "data_record_id": "os_kb_test_0001",
        "user_id": USER,
        "knowledge_type": "fact",
        "memory_status": "candidate",
        "scope": "user",
        "content": {"content_summary": "M2 trusted knowledge"},
        "confidence": 0.9,
        "source": {
            "source_event_id": EVENT_ID,
            "source_type": "manual_config",
            "source_business_status": "success",
            "source_reference": SOURCE_REF,
        },
        "idempotency_key": "m2-import-idem-1",
        "topic_key": "m2",
        "trace_id": "m2-import-trace",
    }
    value.update(overrides)
    return value


def _request(record):
    jsonl = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    manifest = {
        "schema": "main_to_data_source_manifest",
        "schema_version": "1",
        "data_rc_sha256": hashlib.sha256(jsonl).hexdigest(),
        "record_count": 1,
    }
    manifest_sha = hashlib.sha256(rfc8785.dumps(manifest)).hexdigest()
    return jsonl, manifest, manifest_sha


def _run(importer, record, *, request_id="req-1"):
    jsonl, manifest, manifest_sha = _request(record)
    return importer.import_request(
        request_id=request_id,
        source_manifest_sha256=manifest_sha,
        source_manifest=manifest,
        authenticated_principal=PRINCIPAL,
        jsonl_bytes=jsonl,
    )[0]


def _counts(engine):
    with engine.connect() as conn:
        return {
            "memory": conn.exec_driver_sql("SELECT COUNT(*) FROM memory_entries WHERE entry_type='knowledge'").scalar_one(),
            "relation": conn.exec_driver_sql("SELECT COUNT(*) FROM memory_relation WHERE relation_type='evidence'").scalar_one(),
            "outbox": conn.exec_driver_sql("SELECT COUNT(*) FROM outbox").scalar_one(),
            "registry": conn.exec_driver_sql("SELECT COUNT(*) FROM main_to_data_import_registry").scalar_one(),
            "manifest": conn.exec_driver_sql("SELECT COUNT(*) FROM main_to_data_manifest_registry").scalar_one(),
        }


def test_first_acceptance_readback_and_same_request_replay_are_separate(env):
    engine, importer = env
    first = _run(importer, _record())
    assert first["accepted"] is True
    assert first["replayed"] is False
    assert first["accepted_version"] == 1
    assert first["accepted_version_id"] == "v1"
    assert first["accepted_memory_status"] == "candidate"
    before = _counts(engine)
    assert before == {"memory": 1, "relation": 1, "outbox": 1, "registry": 1, "manifest": 1}

    # A legal Main lifecycle change must not rewrite the frozen acceptance receipt.
    with engine.begin() as conn:
        row = repo.get_lifecycle_memory(conn, user_id=USER, knowledge_id=first["knowledge_id"])
        assert row is not None
        assert repo.update_lifecycle_memory(
            conn,
            user_id=USER,
            knowledge_id=first["knowledge_id"],
            expected_row_revision=int(row["row_revision"]),
            memory_status="superseded",
        ) == 1

    current = importer.readback(
        authenticated_principal=PRINCIPAL,
        user_id=USER,
        knowledge_id=first["knowledge_id"],
    )
    assert current["current_version"] == 1
    assert current["current_version_id"] == "v1"
    assert current["current_memory_status"] == "superseded"

    replay = _run(importer, _record(), request_id="req-2")
    assert replay["accepted"] is True
    assert replay["replayed"] is True
    for field in (
        "knowledge_id",
        "memory_id",
        "accepted_version",
        "accepted_version_id",
        "accepted_memory_status",
        "source_event_id",
    ):
        assert replay[field] == first[field]
    assert replay["accepted_memory_status"] == "candidate"
    assert _counts(engine) == before


def test_same_key_different_request_conflicts_without_side_effects(env):
    engine, importer = env
    first = _run(importer, _record())
    assert first["accepted"] is True
    before = _counts(engine)

    changed = _record(content={"content_summary": "different canonical request"})
    conflict = _run(importer, changed, request_id="req-conflict")
    assert conflict == {
        "data_record_id": "os_kb_test_0001",
        "accepted": False,
        "replayed": False,
        "reason_code": "idempotency_conflict",
        "reason_detail": "idempotency key reused for a different request",
    }
    assert _counts(engine) == before


def test_scope_and_source_descriptor_fail_closed(env):
    engine, importer = env
    unauthorized = _run(importer, _record(user_id="other-user"))
    assert unauthorized["accepted"] is False
    assert unauthorized["reason_code"] == "unauthorized_scope"

    bad_source = _record()
    bad_source["source"] = dict(bad_source["source"], source_reference="main://wrong")
    rejected = _run(importer, bad_source, request_id="req-source")
    assert rejected["accepted"] is False
    assert rejected["reason_code"] == "source_not_admitted"
    assert _counts(engine) == {"memory": 0, "relation": 0, "outbox": 0, "registry": 0, "manifest": 0}


def test_transport_integrity_is_fail_closed(env):
    _engine, importer = env
    record = _record()
    jsonl, manifest, manifest_sha = _request(record)
    with pytest.raises(TransportValidationError):
        importer.import_request(
            request_id="req-bad",
            source_manifest_sha256="0" * 64,
            source_manifest=manifest,
            authenticated_principal=PRINCIPAL,
            jsonl_bytes=jsonl,
        )
    with pytest.raises(TransportValidationError):
        importer.import_request(
            request_id="req-bad-bytes",
            source_manifest_sha256=manifest_sha,
            source_manifest=manifest,
            authenticated_principal=PRINCIPAL,
            jsonl_bytes=jsonl + b" ",
        )


def test_registry_has_no_ttl_and_survives_removed_state(env):
    engine, importer = env
    first = _run(importer, _record())
    with engine.begin() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(main_to_data_import_registry)")}
        assert "expires_at" not in columns
        row = repo.get_lifecycle_memory(conn, user_id=USER, knowledge_id=first["knowledge_id"])
        assert row is not None
        assert repo.update_lifecycle_memory(
            conn,
            user_id=USER,
            knowledge_id=first["knowledge_id"],
            expected_row_revision=int(row["row_revision"]),
            memory_status="removed",
        ) == 1

    replay = _run(importer, _record(), request_id="req-after-remove")
    assert replay["accepted"] is True
    assert replay["replayed"] is True
    assert replay["accepted_memory_status"] == "candidate"
    current = importer.readback(
        authenticated_principal=PRINCIPAL,
        user_id=USER,
        knowledge_id=first["knowledge_id"],
    )
    assert current["current_memory_status"] == "removed"
    assert _counts(engine)["registry"] == 1
