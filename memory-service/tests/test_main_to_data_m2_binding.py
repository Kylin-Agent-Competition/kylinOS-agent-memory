"""L1 tests for the M2 RC10 source binding and controlled provisioning boundary."""

from __future__ import annotations

import json

import pytest

from db.engine import create_db_engine, init_schema
from service.main_to_data_binding import (
    BindingError,
    ControlledSourceProvisioner,
    M2BindingService,
    build_static_scope_resolver,
    import_idempotency_key_for,
    parse_candidate_jsonl,
    sha256_lf,
)
from service.main_to_data_import import TransportValidationError


USER = "m2-rc10-user"
PRINCIPAL = "m2-rc10-principal"
REQUIRED_FROM_MAIN = [
    "user_id",
    "source_event_id",
    "source_type",
    "source_business_status",
    "source_reference",
    "idempotency_key",
    "admission_decision=allow_extraction",
]


def _candidate(index: int) -> dict:
    local = f"os_kb_{index:04d}"
    return {
        "data_record_id": f"data-prebinding:{local}",
        "local_candidate_id": local,
        "knowledge_type": "fact",
        "content_summary": f"m2 controlled authored knowledge {index}",
        "primary_category": "tech_dev",
        "language_tag": "zh-CN",
        "candidate_provenance": {
            "source": "os_controlled_authored",
            "retrieval_sample": f"retr_d1c_{index:04d}",
            "scenario_spec_id": "OSRETR-01",
        },
        "candidate_source": {"file": "test", "line": index},
        "production_binding_status": "PRODUCTION_BINDING_PENDING",
        "main_binding": {
            "user_id": None,
            "source_event_id": None,
            "source_type": None,
            "source_business_status": None,
            "source_reference": None,
            "idempotency_key": None,
            "required_source_admission": "allow_extraction",
        },
    }


def _jsonl_bytes(rows) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows
    ).encode("utf-8")


def _binding_request(candidates_bytes: bytes, candidates) -> dict:
    return {
        "schema": "main_to_data_m2_prebinding_request",
        "schema_version": "1",
        "state": "PREBINDING_NOT_IMPORTABLE",
        "m2_gate_status": "BLOCKED_MAIN_SOURCE_BINDING",
        "record_count": len(candidates),
        "candidate_file": "m2_prebinding_candidates_10.jsonl",
        "candidate_file_sha256": sha256_lf(candidates_bytes),
        "required_main_conditions": [],
        "prohibited_actions": [],
        "records": [
            {
                "data_record_id": candidate["data_record_id"],
                "local_candidate_id": candidate["local_candidate_id"],
                "required_from_main": list(REQUIRED_FROM_MAIN),
            }
            for candidate in candidates
        ],
    }


@pytest.fixture()
def env(tmp_path):
    engine = create_db_engine(str(tmp_path / "m2_binding.db"))
    init_schema(engine)
    yield engine
    engine.dispose()


def _provision(engine, candidates):
    provisioner = ControlledSourceProvisioner(engine, user_id=USER)
    return provisioner.provision(candidates)


def _service(engine):
    return M2BindingService(
        engine,
        principal_scope_resolver=build_static_scope_resolver({PRINCIPAL: [USER]}),
    )


def test_provision_and_bind_success_is_idempotent(env):
    candidates = [_candidate(1), _candidate(2)]
    candidates_bytes = _jsonl_bytes(candidates)
    provisioning = _provision(env, candidates)
    assert provisioning["record_count"] == 2
    assert all(row["admission_decision"] == "allow_extraction" for row in provisioning["records"])
    assert all(row["ingest_replayed"] is False for row in provisioning["records"])

    replay = _provision(env, candidates)
    assert all(row["ingest_replayed"] is True for row in replay["records"])
    assert [row["source_event_row_id"] for row in replay["records"]] == [
        row["source_event_row_id"] for row in provisioning["records"]
    ]

    response = _service(env).bind(
        binding_request=_binding_request(candidates_bytes, candidates),
        candidates_bytes=candidates_bytes,
        provisioning_results=provisioning,
        authenticated_principal=PRINCIPAL,
    )
    assert response["bound_count"] == 2
    assert response["checks"] == {
        "cross_user": 0,
        "source_not_admitted": 0,
        "provenance_mismatch": 0,
        "fabricated_event": 0,
    }
    for row, candidate in zip(response["records"], candidates):
        assert row["local_candidate_id"] == candidate["local_candidate_id"]
        assert row["user_id"] == USER
        assert row["source_event_id"] == f"m2-rc10-src-{candidate['local_candidate_id']}"
        assert row["source_type"] == "manual_config"
        assert row["source_business_status"] == "success"
        assert row["source_reference"] == (
            f"os_controlled_authored://OSRETR-01/{candidate['candidate_provenance']['retrieval_sample']}"
        )
        assert row["idempotency_key"] == import_idempotency_key_for(candidate["local_candidate_id"])
        assert row["admission_decision"] == "allow_extraction"

    with env.connect() as conn:
        knowledge_rows = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM memory_entries WHERE entry_type='knowledge'"
        ).scalar_one()
    assert knowledge_rows == 0


def test_binding_fails_closed_when_source_event_is_missing(env):
    candidates = [_candidate(1)]
    candidates_bytes = _jsonl_bytes(candidates)
    provisioning = _provision(env, candidates)
    with env.begin() as conn:
        conn.exec_driver_sql("DELETE FROM source_events WHERE event_id='m2-rc10-src-os_kb_0001'")
    with pytest.raises(BindingError) as exc:
        _service(env).bind(
            binding_request=_binding_request(candidates_bytes, candidates),
            candidates_bytes=candidates_bytes,
            provisioning_results=provisioning,
            authenticated_principal=PRINCIPAL,
        )
    assert exc.value.reason_code == "source_not_admitted"


def test_binding_fails_closed_on_content_and_reference_drift(env):
    candidates = [_candidate(1)]
    candidates_bytes = _jsonl_bytes(candidates)
    provisioning = _provision(env, candidates)

    with env.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE source_events SET content_summary='different content' WHERE event_id='m2-rc10-src-os_kb_0001'"
        )
    with pytest.raises(BindingError) as exc:
        _service(env).bind(
            binding_request=_binding_request(candidates_bytes, candidates),
            candidates_bytes=candidates_bytes,
            provisioning_results=provisioning,
            authenticated_principal=PRINCIPAL,
        )
    assert exc.value.reason_code == "provenance_mismatch"

    with env.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE source_events SET content_summary=?, source_reference='os_controlled_authored://OSRETR-01/retr_d1c_9999' "
            "WHERE event_id='m2-rc10-src-os_kb_0001'",
            (candidates[0]["content_summary"],),
        )
    with pytest.raises(BindingError) as exc:
        _service(env).bind(
            binding_request=_binding_request(candidates_bytes, candidates),
            candidates_bytes=candidates_bytes,
            provisioning_results=provisioning,
            authenticated_principal=PRINCIPAL,
        )
    assert exc.value.reason_code == "provenance_mismatch"


def test_binding_fails_closed_on_unadmitted_event(env):
    candidates = [_candidate(1)]
    candidates_bytes = _jsonl_bytes(candidates)
    provisioning = _provision(env, candidates)
    with env.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE source_events SET admission_decision='audit_only' WHERE event_id='m2-rc10-src-os_kb_0001'"
        )
    with pytest.raises(BindingError) as exc:
        _service(env).bind(
            binding_request=_binding_request(candidates_bytes, candidates),
            candidates_bytes=candidates_bytes,
            provisioning_results=provisioning,
            authenticated_principal=PRINCIPAL,
        )
    assert exc.value.reason_code == "source_not_admitted"


def test_candidate_with_prefilled_binding_is_rejected():
    candidate = _candidate(1)
    candidate["main_binding"]["source_event_id"] = "fabricated"
    with pytest.raises(BindingError) as exc:
        parse_candidate_jsonl(_jsonl_bytes([candidate]))
    assert exc.value.reason_code == "fabricated_binding"


def test_binding_request_and_scope_fail_closed(env):
    candidates = [_candidate(1)]
    candidates_bytes = _jsonl_bytes(candidates)
    provisioning = _provision(env, candidates)

    tampered_request = _binding_request(candidates_bytes, candidates)
    tampered_request["candidate_file_sha256"] = "0" * 64
    with pytest.raises(TransportValidationError):
        _service(env).bind(
            binding_request=tampered_request,
            candidates_bytes=candidates_bytes,
            provisioning_results=provisioning,
            authenticated_principal=PRINCIPAL,
        )

    other_principal = M2BindingService(
        env,
        principal_scope_resolver=build_static_scope_resolver({"other": ["other-user"]}),
    )
    with pytest.raises(TransportValidationError):
        other_principal.bind(
            binding_request=_binding_request(candidates_bytes, candidates),
            candidates_bytes=candidates_bytes,
            provisioning_results=provisioning,
            authenticated_principal="other",
        )


def test_provisioning_uses_real_admission_pipeline(env):
    candidates = [_candidate(1)]
    provisioning = _provision(env, candidates)
    assert provisioning["records"][0]["source_event_row_id"] > 0
    with env.connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT source_type, source_business_status, admission_decision, admission_reason_code, "
            "content_summary, source_reference, consent_scope FROM source_events "
            "WHERE event_id='m2-rc10-src-os_kb_0001'"
        ).first()
    assert row is not None
    assert row[0] == "manual_config"
    assert row[1] == "success"
    assert row[2] == "allow_extraction"
    assert row[3] == "ok"
    assert row[4] == candidates[0]["content_summary"]
    assert row[5] == "os_controlled_authored://OSRETR-01/retr_d1c_0001"
    assert row[6] == "memory_only"
