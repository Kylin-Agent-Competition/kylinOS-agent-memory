"""test_d13d_forget_state_binding.py — binding artifact V1 静态校验单测。

只校验 artifact 结构/身份/SHA/禁填项；不连接 DB、不读取 Gold/expected。
契约：docs/day13/27_d13d_forget_state_binding_contract_20260906.md。
"""

import json

from evaluation.d13d_forget_state_binding import (
    BINDING_VERSION,
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


def test_json_roundtrip_stable():
    payload = _retrieval_attach(_valid_artifact())
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    reloaded = json.loads(text)
    assert validate_artifact(reloaded) == []
