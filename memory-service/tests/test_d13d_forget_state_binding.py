"""test_d13d_forget_state_binding.py — binding artifact V1 静态校验单测。

只校验 artifact 结构/身份/SHA/禁填项；不连接 DB、不读取 Gold/expected。
契约：docs/day13/27_d13d_forget_state_binding_contract_20260906.md。
"""

import json

from evaluation.d13d_forget_state_binding import (
    BINDING_VERSION,
    BINDING_VERSION_V2,
    compute_artifact_sha256,
    validate_artifact,
)

TEST_COMMIT = "dc58e83479d718c8e3fbbbbb5d3b3f046f651973"


def _retrieval(marker):
    return {
        "entrypoint": f"memory-service:observe_forget_execution:{marker}",
        "trace_reference": f"forget/{marker}/trace.json",
        "snapshot": f"snapshot-{marker}",
        "watermark": f"watermark-{marker}",
    }


def _samples():
    base = {
        "user_id": "user_d13e_alpha",
        "same_user_controls": [{"memory_entry_id": 2001}],
        "foreign_user_controls": [{"user_id": "user_d13e_beta", "memory_entry_id": 9001}],
    }
    return [
        {
            "sample_id": "d13e-forget-001",
            "forget_mode": "single_item",
            "target_selector": {"memory_id": "d13e-memory-001"},
            "target_identity": {"db_id": 1001, "memory_id": "d13e-memory-001",
                                "stable_identity": "memory_entries/1001"},
            "prerequisite_facts": {"active": True},
            **base,
        },
        {
            "sample_id": "d13e-forget-002",
            "forget_mode": "session",
            "target_selector": {"session_id": "d13e-session-001"},
            "target_identity": {"session_id": "d13e-session-001", "db_id": 2002},
            "prerequisite_facts": {"session_entry_count": 3},
            **base,
        },
        {
            "sample_id": "d13e-forget-003",
            "forget_mode": "topic",
            "target_selector": {"topic": "d13e-topic"},
            "target_identity": {"topic_key": "d13e-topic", "db_id": 3003},
            "prerequisite_facts": {"topic_entry_count": 2},
            **base,
        },
        {
            "sample_id": "d13e-forget-004",
            "forget_mode": "time_window",
            "target_selector": {"from": "2026-09-01T00:00:00+08:00",
                                "to": "2026-09-02T00:00:00+08:00"},
            "target_identity": {"window_entry_ids": [4001, 4002], "db_id": 4004},
            "prerequisite_facts": {"events_in_window": 2, "events_outside_window": 1},
            **base,
        },
        {
            "sample_id": "d13e-forget-005",
            "forget_mode": "full_reset",
            "target_selector": {},
            "target_identity": {"user_scope": "user_d13e_alpha", "db_id": 5005},
            "prerequisite_facts": {"knowledge_count": 1, "preference_count": 1},
            **base,
            "same_user_controls": [],
        },
    ]


def _artifact_without_sha():
    return {
        "binding_version": BINDING_VERSION,
        "owner": "B（高翌哲）",
        "approved_by": "D/E",
        "approval_reference": "D/E 2026-09-06 B-2 ACCEPTED",
        "applicable_source_commit": TEST_COMMIT,
        "environment_id": "d13d-env-candidate-1",
        "vm_snapshot": {"vm": "Kylin-V11-2603-BTrack-Base",
                        "snapshot": "d14d-clean-base-20260906-r2",
                        "snapshot_uuid": "c5e3c3de-0000-0000-0000-000000000000"},
        "state_root": "/var/lib/kylin-memory/state",
        "db_identity": {"path": "/var/lib/kylin-memory/state/memory.db",
                        "sha256": "0" * 64},
        "retrieval_profile": "d13d-validation-profile-v1",
        "created_at_utc": "2026-09-06T00:00:00Z",
        "created_by": "B（高翌哲）",
        "samples": _samples(),
    }


def _valid_artifact():
    payload = _retrieval_attach(_artifact_without_sha())
    payload["artifact_sha256"] = compute_artifact_sha256(payload)
    return payload


def _retrieval_attach(payload):
    for sample in payload["samples"]:
        sample["realtime_retrieval"] = _retrieval(sample["sample_id"])
        sample["rebuild_retrieval"] = _retrieval(sample["sample_id"] + "-rebuild")
    return payload


def test_valid_artifact_passes():
    payload = _retrieval_attach(_valid_artifact())
    assert validate_artifact(payload) == []


def test_sha_mismatch_detected():
    payload = _retrieval_attach(_valid_artifact())
    payload["artifact_sha256"] = "f" * 64
    assert any("artifact_sha256 mismatch" in err for err in validate_artifact(payload))


def test_sha_is_order_independent():
    payload_a = _retrieval_attach(_valid_artifact())
    # 顶层层序变化不应改变 canonical SHA
    items = list(payload_a.items())
    payload_b = dict(items[::-1])
    payload_b["artifact_sha256"] = compute_artifact_sha256(payload_b)
    assert validate_artifact(payload_b) == []


def test_missing_top_level_field():
    payload = _retrieval_attach(_valid_artifact())
    del payload["state_root"]
    assert any("missing top-level field: state_root" in e for e in validate_artifact(payload))


def test_sample_coverage_required():
    payload = _retrieval_attach(_valid_artifact())
    payload["samples"] = payload["samples"][:4]
    payload["artifact_sha256"] = compute_artifact_sha256(payload)
    assert any("must cover exactly" in err for err in validate_artifact(payload))


def test_wrong_mode_detected():
    payload = _retrieval_attach(_valid_artifact())
    payload["samples"][0]["forget_mode"] = "session"
    payload["artifact_sha256"] = compute_artifact_sha256(payload)
    assert any("forget_mode mismatch" in err for err in validate_artifact(payload))


def test_single_item_requires_integer_db_id():
    payload = _retrieval_attach(_valid_artifact())
    del payload["samples"][0]["target_identity"]["db_id"]
    payload["artifact_sha256"] = compute_artifact_sha256(payload)
    assert any("db_id must be a real integer" in err for err in validate_artifact(payload))


def test_controls_must_be_non_empty():
    payload = _retrieval_attach(_valid_artifact())
    payload["samples"][1]["foreign_user_controls"] = []
    payload["artifact_sha256"] = compute_artifact_sha256(payload)
    assert any("foreign_user_controls must be a non-empty list" in err
               for err in validate_artifact(payload))


def test_retrieval_requires_snapshot_and_watermark():
    payload = _retrieval_attach(_valid_artifact())
    del payload["samples"][2]["realtime_retrieval"]["watermark"]
    payload["artifact_sha256"] = compute_artifact_sha256(payload)
    assert any("realtime_retrieval missing watermark" in err
               for err in validate_artifact(payload))


def test_forbidden_eval_keys_rejected():
    payload = _retrieval_attach(_valid_artifact())
    payload["samples"][4]["target_identity"]["expected"] = True
    payload["artifact_sha256"] = compute_artifact_sha256(payload)
    assert any("forbidden key" in err for err in validate_artifact(payload))


def test_full_reset_requires_foreign_controls_even_when_same_user_empty():
    payload = _retrieval_attach(_valid_artifact())
    payload["samples"][4]["foreign_user_controls"] = []
    payload["artifact_sha256"] = compute_artifact_sha256(payload)
    assert any("foreign_user_controls must be a non-empty list" in err
               for err in validate_artifact(payload))


def _v2_artifact():
    v1 = _artifact_without_sha()
    payload = {
        "binding_version": BINDING_VERSION_V2,
        "owner": v1["owner"],
        "approved_by": v1["approved_by"],
        "approval_reference": v1["approval_reference"],
        "state_preparation_commit": TEST_COMMIT,
        "execution_compatibility": {
            "minimum_commit": TEST_COMMIT,
            "policy": "descendant-and-contract-compatible",
        },
        "environment_id": v1["environment_id"],
        "vm_snapshot": v1["vm_snapshot"],
        "source_state": {
            "state_root": "/var/lib/kylin-memory/state",
            "sealed_db_path": "/var/lib/kylin-memory/state/p2b-forget-state.db",
            "sealed_db_sha256": "9e8dc27455984bc66369f87deaee3ce22945b2ee3060bed5515c45fdae6e593f",
            "db_size_bytes": 352256,
            "sqlite_schema_fingerprint": "f" * 64,
            "prepared_on_vm_snapshot": "d14d-clean-base-20260906-r2",
            "prepared_at_utc": "2026-09-06T00:00:00Z",
        },
        "retrieval_profile": v1["retrieval_profile"],
        "created_at_utc": v1["created_at_utc"],
        "created_by": v1["created_by"],
        "samples": v1["samples"],
    }
    payload = _retrieval_attach(payload)
    payload["artifact_sha256"] = compute_artifact_sha256(payload)
    return payload


def test_v2_valid_artifact_passes():
    assert validate_artifact(_v2_artifact()) == []


def test_v2_rejects_legacy_applicable_source_commit():
    payload = _v2_artifact()
    payload["applicable_source_commit"] = TEST_COMMIT
    payload["artifact_sha256"] = compute_artifact_sha256(payload)
    assert any("must not use legacy applicable_source_commit" in e
               for e in validate_artifact(payload))


def test_v2_requires_execution_compatibility_minimum_commit():
    payload = _v2_artifact()
    del payload["execution_compatibility"]["minimum_commit"]
    payload["artifact_sha256"] = compute_artifact_sha256(payload)
    assert any("execution_compatibility missing: minimum_commit" in e
               for e in validate_artifact(payload))


def test_v2_requires_source_state_identity():
    payload = _v2_artifact()
    del payload["source_state"]["sealed_db_sha256"]
    payload["artifact_sha256"] = compute_artifact_sha256(payload)
    assert any("source_state missing: sealed_db_sha256" in e
               for e in validate_artifact(payload))


def test_unknown_binding_version_rejected():
    payload = _artifact_without_sha()
    payload["binding_version"] = "d13d-forget-state-binding/v9"
    payload["artifact_sha256"] = compute_artifact_sha256(payload)
    assert any("binding_version must be one of" in e for e in validate_artifact(payload))


def test_json_roundtrip_stable():
    payload = _retrieval_attach(_valid_artifact())
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    reloaded = json.loads(text)
    assert validate_artifact(reloaded) == []
