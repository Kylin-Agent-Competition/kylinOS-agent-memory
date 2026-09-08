"""Create a real D13D Forget V2 source state on the current Kylin VM.

This is a Phase 2 preparation utility.  It uses production Repository APIs to
seed synthetic state and fails closed before sealing if resolver targets do not
exist.  It does not read Gold/Threshold/Runner artifacts and does not dispatch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(os.environ["D13D_REPO_ROOT"]) / "memory-service"))

from db import repositories as repo  # noqa: E402
from db.engine import create_db_engine, init_schema  # noqa: E402
from evaluation.d13d_forget_state_binding import (  # noqa: E402
    BINDING_VERSION_V2,
    compute_artifact_sha256,
)
from service.forgetting import resolve_forget_targets  # noqa: E402


ALPHA = "user_d13e_alpha"
BETA = "user_d13e_beta"
NOW = datetime.now(timezone.utc).isoformat()
WINDOW_OCCURRENCE = "2026-09-01T04:00:00+00:00"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sqlite_schema_fingerprint(path: Path) -> str:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT type || '|' || name || '|' || COALESCE(sql, '') "
            "FROM sqlite_master ORDER BY name"
        ).fetchall()
    finally:
        con.close()
    return hashlib.sha256("\n".join(row[0] for row in rows).encode()).hexdigest()


def _checkpoint_sqlite(path: Path) -> None:
    """Move WAL contents into the main DB so the sealed file is self-contained."""
    con = sqlite3.connect(str(path), timeout=5)
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("PRAGMA journal_mode=DELETE")
    finally:
        con.close()


def _source_event(
    conn,
    *,
    user_id: str,
    seq: int,
    session_id: str,
    occurred_at: str,
) -> str:
    event_id = f"d13e-state-event-{seq:03d}"
    repo.insert_source_event(
        conn,
        user_id=user_id,
        event_id=event_id,
        actor_id=user_id,
        session_id=session_id,
        turn_id=None,
        tool_call_id=None,
        source_type="manual_config",
        event_type="manual_config",
        schema_version="0.1",
        trace_id=f"d13e-state-trace-{seq:03d}",
        source_reference="d13e/synthetic/state-preparation",
        raw_payload_ref=None,
        content_summary=f"d13e synthetic manual config {seq:03d}",
        idempotency_key=f"d13e-state-idem-{seq:03d}",
        consent_scope="memory_only",
        source_business_status="success",
        sensitivity="none",
        is_sensitive_matched=0,
        should_ignore=0,
        payload_security_checked=1,
        memory_type="short_term",
        requires_embedding=0,
        has_structured_payload=1,
        language_tag="zh-CN",
        occurred_at=occurred_at,
        captured_at=NOW,
        content_fingerprint=None,
        dedup_group=None,
        duplicate_of=None,
        admission_decision="allow_extraction",
        admission_reason_code="synthetic_controlled_state_preparation",
        processing_status="extracted",
        created_at=NOW,
        updated_at=NOW,
    )
    return event_id


def _knowledge(
    conn,
    *,
    user_id: str,
    seq: int,
    event_id: str,
    value: str,
    topic_key: str | None = None,
) -> int:
    return int(
        repo.insert_knowledge_entry(
            conn,
            user_id=user_id,
            knowledge_id=f"d13e-memory-{seq:03d}",
            knowledge_type="fact",
            source_event_id=event_id,
            content={"value": value},
            confidence=0.98,
            topic_key=topic_key,
            trace_id=f"d13e-state-trace-{seq:03d}",
        )["memory_entry_id"]
    )


def _seed(engine) -> dict[str, object]:
    knowledge_ids: dict[str, int] = {}
    with engine.begin() as conn:
        alpha_pref = repo.save_preference_version(
            conn,
            user_id=ALPHA,
            preference_key="d13e-pref-alpha",
            preference_scope="global",
            preference_value="d13e synthetic alpha preference control",
            memory_status="active",
            evidence_fingerprint="d13e-state-preference-alpha-v1",
            idempotency_key="d13e-state-pref-alpha-1",
            request_fingerprint="d13e-state-pref-alpha-request-1",
            trace_id="d13e-state-trace-pref-alpha",
        )

        event_id = _source_event(conn, user_id=ALPHA, seq=1,
                                 session_id="d13e-state-session-001", occurred_at=NOW)
        knowledge_ids["001"] = _knowledge(conn, user_id=ALPHA, seq=1,
                                          event_id=event_id, value="d13e single item target")
        event_id = _source_event(conn, user_id=ALPHA, seq=2,
                                 session_id="d13e-state-session-001", occurred_at=NOW)
        knowledge_ids["002"] = _knowledge(conn, user_id=ALPHA, seq=2,
                                          event_id=event_id, value="d13e single item control")
        event_id = _source_event(conn, user_id=BETA, seq=3,
                                 session_id="d13e-state-session-003", occurred_at=NOW)
        knowledge_ids["003"] = _knowledge(conn, user_id=BETA, seq=3,
                                          event_id=event_id, value="d13e foreign single control")

        conversation_id = repo.upsert_conversation(
            conn, user_id=ALPHA, session_id="d13e-session-001"
        )
        turn_1 = repo.insert_turn(
            conn,
            session_id="d13e-session-001",
            turn_index=1,
            original_user_text="d13e synthetic session turn one",
            is_end=1,
            trace_id="d13e-state-trace-session-1",
            host_turn_id="d13e-state-host-turn-1",
        )
        turn_2 = repo.insert_turn(
            conn,
            session_id="d13e-session-001",
            turn_index=2,
            original_user_text="d13e synthetic session turn two",
            is_end=1,
            trace_id="d13e-state-trace-session-2",
            host_turn_id="d13e-state-host-turn-2",
        )
        knowledge_ids["004"] = repo.insert_memory_entry(
            conn,
            user_id=ALPHA,
            entry_type="knowledge",
            content={"value": "d13e session target one"},
            source_turn_id=turn_1,
            confidence=0.98,
            trace_id="d13e-state-trace-session-1",
        )
        knowledge_ids["005"] = repo.insert_memory_entry(
            conn,
            user_id=ALPHA,
            entry_type="knowledge",
            content={"value": "d13e session target two"},
            source_turn_id=turn_2,
            confidence=0.98,
            trace_id="d13e-state-trace-session-2",
        )
        knowledge_ids["006"] = repo.insert_memory_entry(
            conn,
            user_id=ALPHA,
            entry_type="knowledge",
            content={"value": "d13e session control"},
            confidence=0.98,
            trace_id="d13e-state-trace-session-control",
        )
        knowledge_ids["007"] = repo.insert_memory_entry(
            conn,
            user_id=BETA,
            entry_type="knowledge",
            content={"value": "d13e foreign session control"},
            confidence=0.98,
            trace_id="d13e-state-trace-session-foreign",
        )

        event_id = _source_event(conn, user_id=ALPHA, seq=8,
                                 session_id="d13e-state-session-008", occurred_at=NOW)
        knowledge_ids["008"] = _knowledge(conn, user_id=ALPHA, seq=8,
                                          event_id=event_id,
                                          value="d13e topic target",
                                          topic_key="d13e-topic")
        event_id = _source_event(conn, user_id=ALPHA, seq=9,
                                 session_id="d13e-state-session-009", occurred_at=NOW)
        knowledge_ids["009"] = _knowledge(conn, user_id=ALPHA, seq=9,
                                          event_id=event_id,
                                          value="d13e topic control")
        event_id = _source_event(conn, user_id=BETA, seq=10,
                                 session_id="d13e-state-session-010", occurred_at=NOW)
        knowledge_ids["010"] = _knowledge(conn, user_id=BETA, seq=10,
                                          event_id=event_id,
                                          value="d13e foreign topic control",
                                          topic_key="d13e-topic")

        event_id = _source_event(conn, user_id=ALPHA, seq=11,
                                 session_id="d13e-state-session-011",
                                 occurred_at=WINDOW_OCCURRENCE)
        knowledge_ids["011"] = _knowledge(conn, user_id=ALPHA, seq=11,
                                          event_id=event_id,
                                          value="d13e time window target")
        event_id = _source_event(conn, user_id=ALPHA, seq=12,
                                 session_id="d13e-state-session-012", occurred_at=NOW)
        knowledge_ids["012"] = _knowledge(conn, user_id=ALPHA, seq=12,
                                          event_id=event_id,
                                          value="d13e time window control")
        event_id = _source_event(conn, user_id=BETA, seq=13,
                                 session_id="d13e-state-session-013", occurred_at=NOW)
        knowledge_ids["013"] = _knowledge(conn, user_id=BETA, seq=13,
                                          event_id=event_id,
                                          value="d13e foreign time window control")

        event_id = _source_event(conn, user_id=ALPHA, seq=14,
                                 session_id="d13e-state-session-014", occurred_at=NOW)
        knowledge_ids["014"] = _knowledge(conn, user_id=ALPHA, seq=14,
                                          event_id=event_id,
                                          value="d13e full reset target")
        event_id = _source_event(conn, user_id=BETA, seq=15,
                                 session_id="d13e-state-session-015", occurred_at=NOW)
        knowledge_ids["015"] = _knowledge(conn, user_id=BETA, seq=15,
                                          event_id=event_id,
                                          value="d13e foreign full reset control")

        beta_pref = repo.save_preference_version(
            conn,
            user_id=BETA,
            preference_key="d13e-pref-beta",
            preference_scope="global",
            preference_value="d13e synthetic beta preference control",
            memory_status="active",
            evidence_fingerprint="d13e-state-preference-beta-v1",
            idempotency_key="d13e-state-pref-beta-1",
            request_fingerprint="d13e-state-pref-beta-request-1",
            trace_id="d13e-state-trace-pref-beta",
        )

    return {
        "knowledge_ids": knowledge_ids,
        "alpha_preference_item_id": int(alpha_pref["memory_item_id"]),
        "beta_preference_item_id": int(beta_pref["memory_item_id"]),
        "conversation_id": conversation_id,
        "session_turn_ids": [turn_1, turn_2],
    }


def _verify_resolvers(engine, seeded: dict[str, object]) -> dict[str, object]:
    knowledge_ids = seeded["knowledge_ids"]
    with engine.connect() as conn:
        single = resolve_forget_targets(
            conn, user_id=ALPHA, forget_mode="single_item", target_type="knowledge",
            target_id=str(knowledge_ids["001"]), target_session_id=None,
        )
        session = resolve_forget_targets(
            conn, user_id=ALPHA, forget_mode="session", target_type="knowledge",
            target_id=None, target_session_id="d13e-session-001",
        )
        topic = resolve_forget_targets(
            conn, user_id=ALPHA, forget_mode="topic", target_type="knowledge",
            target_id=None, target_session_id=None, target_topic="d13e-topic",
        )
        window = resolve_forget_targets(
            conn, user_id=ALPHA, forget_mode="time_window", target_type="knowledge",
            target_id=None, target_session_id=None,
            target_time_range=json.dumps({
                "from": "2026-09-01T00:00:00+08:00",
                "to": "2026-09-02T00:00:00+08:00",
            }),
        )
        full_reset = resolve_forget_targets(
            conn, user_id=ALPHA, forget_mode="full_reset", target_type="all",
            target_id=None, target_session_id=None,
        )
    expected_single = [str(knowledge_ids["001"])]
    expected_session = [str(knowledge_ids[x]) for x in ("004", "005")]
    expected_topic = [str(knowledge_ids["008"])]
    expected_window = [str(knowledge_ids["011"])]
    if single != expected_single:
        raise RuntimeError(f"single resolver mismatch: {single}")
    if session != expected_session:
        raise RuntimeError(f"session resolver mismatch: {session}")
    if topic != expected_topic:
        raise RuntimeError(f"topic resolver mismatch: {topic}")
    if window != expected_window:
        raise RuntimeError(f"time_window resolver mismatch: {window}")
    if [x for x in full_reset if x.startswith("knowledge:")] != [
        f"knowledge:{knowledge_ids[x]}" for x in sorted(knowledge_ids) if x not in {"003", "007", "010", "013", "015"}
    ]:
        raise RuntimeError(f"full_reset knowledge resolver mismatch: {full_reset}")
    if not any(x == f"preference:{seeded['alpha_preference_item_id']}" for x in full_reset):
        raise RuntimeError("full_reset preference target missing")
    return {
        "single": single,
        "session": session,
        "topic": topic,
        "time_window": window,
        "full_reset": full_reset,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--vm-name", required=True)
    parser.add_argument("--vm-uuid", required=True)
    parser.add_argument("--snapshot-name", required=True)
    parser.add_argument("--snapshot-uuid", required=True)
    parser.add_argument("--snapshot-label", required=True)
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.state_root.exists():
        raise SystemExit(f"state root already exists: {args.state_root}")
    args.state_root.mkdir(parents=True)
    sealed_dir = args.state_root / "sealed"
    sealed_dir.mkdir()
    source_path = sealed_dir / "p2b-forget-state-v2.db"

    engine = create_db_engine(str(source_path))
    init_schema(engine)
    seeded = _seed(engine)
    engine.dispose()

    _checkpoint_sqlite(source_path)

    verify_engine = create_db_engine(str(source_path))
    resolved = _verify_resolvers(verify_engine, seeded)
    verify_engine.dispose()

    _checkpoint_sqlite(source_path)

    source_path.chmod(0o600)
    source_sha = _sha256(source_path)
    schema_fingerprint = _sqlite_schema_fingerprint(source_path)
    head = subprocess.run(
        ["git", "-C", str(args.repo_root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=15,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(args.repo_root), "status", "--porcelain"],
        check=True, capture_output=True, text=True, timeout=15,
    ).stdout
    if status:
        raise SystemExit("repository worktree must be clean")

    knowledge_ids = seeded["knowledge_ids"]
    session_ids = [knowledge_ids["004"], knowledge_ids["005"]]
    topic_ids = [knowledge_ids["008"]]
    window_ids = [knowledge_ids["011"]]
    artifact = {
        "binding_version": BINDING_VERSION_V2,
        "owner": "B（高翌哲）",
        "approved_by": "D/E",
        "approval_reference": (
            "D/E 2026-09-06 B-2 ACCEPTED + Reviewer E 2026-09-07 phase block lifted"
        ),
        "state_preparation_commit": head,
        "execution_compatibility": {
            "minimum_commit": head,
            "policy": "descendant-and-contract-compatible",
        },
        "environment_id": args.environment_id,
        "vm_snapshot": {
            "vm": args.vm_name,
            "vm_uuid": args.vm_uuid,
            "snapshot": args.snapshot_name,
            "snapshot_uuid": args.snapshot_uuid,
        },
        "source_state": {
            "state_root": str(args.state_root),
            "sealed_db_path": str(source_path),
            "sealed_db_sha256": source_sha,
            "db_size_bytes": source_path.stat().st_size,
            "sqlite_schema_fingerprint": schema_fingerprint,
            "prepared_on_vm_snapshot": args.snapshot_label,
            "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        },
        "retrieval_profile": "d13d-validation-profile-v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "created_by": "B（高翌哲） VM state preparation",
        "samples": [
            {
                "sample_id": "d13e-forget-001",
                "user_id": ALPHA,
                "forget_mode": "single_item",
                "target_selector": {"memory_id": "d13e-memory-001"},
                "target_identity": {
                    "db_id": knowledge_ids["001"],
                    "knowledge_id": "d13e-memory-001",
                    "stable_identity": f"memory_entries/{knowledge_ids['001']}",
                },
                "same_user_controls": [{"id": knowledge_ids["002"], "kind": "knowledge"}],
                "foreign_user_controls": [{"id": knowledge_ids["003"], "kind": "knowledge"}],
                "prerequisite_facts": {"active": True},
                "realtime_retrieval": {
                    "entrypoint": "observe_forget_execution:realtime",
                    "trace_reference": "dispatch/d13e-forget-001.json",
                    "snapshot": "prepared_state_snapshot",
                    "watermark": "prepared_state_watermark",
                },
                "rebuild_retrieval": {
                    "entrypoint": "observe_forget_execution:rebuild",
                    "trace_reference": "dispatch/d13e-forget-001.json",
                    "snapshot": "prepared_state_snapshot",
                    "watermark": "prepared_state_watermark",
                },
            },
            {
                "sample_id": "d13e-forget-002",
                "user_id": ALPHA,
                "forget_mode": "session",
                "target_selector": {"session_id": "d13e-session-001"},
                "target_identity": {
                    "db_ids": session_ids,
                    "session_id": "d13e-session-001",
                },
                "same_user_controls": [{"id": knowledge_ids["006"], "kind": "knowledge"}],
                "foreign_user_controls": [{"id": knowledge_ids["007"], "kind": "knowledge"}],
                "prerequisite_facts": {"session_entry_count": 2},
                "realtime_retrieval": {
                    "entrypoint": "observe_forget_execution:realtime",
                    "trace_reference": "dispatch/d13e-forget-002.json",
                    "snapshot": "prepared_state_snapshot",
                    "watermark": "prepared_state_watermark",
                },
                "rebuild_retrieval": {
                    "entrypoint": "observe_forget_execution:rebuild",
                    "trace_reference": "dispatch/d13e-forget-002.json",
                    "snapshot": "prepared_state_snapshot",
                    "watermark": "prepared_state_watermark",
                },
            },
            {
                "sample_id": "d13e-forget-003",
                "user_id": ALPHA,
                "forget_mode": "topic",
                "target_selector": {"topic": "d13e-topic"},
                "target_identity": {
                    "db_ids": topic_ids,
                    "topic_key": "d13e-topic",
                },
                "same_user_controls": [{"id": knowledge_ids["009"], "kind": "knowledge"}],
                "foreign_user_controls": [{"id": knowledge_ids["010"], "kind": "knowledge"}],
                "prerequisite_facts": {"topic_entry_count": 1},
                "realtime_retrieval": {
                    "entrypoint": "observe_forget_execution:realtime",
                    "trace_reference": "dispatch/d13e-forget-003.json",
                    "snapshot": "prepared_state_snapshot",
                    "watermark": "prepared_state_watermark",
                },
                "rebuild_retrieval": {
                    "entrypoint": "observe_forget_execution:rebuild",
                    "trace_reference": "dispatch/d13e-forget-003.json",
                    "snapshot": "prepared_state_snapshot",
                    "watermark": "prepared_state_watermark",
                },
            },
            {
                "sample_id": "d13e-forget-004",
                "user_id": ALPHA,
                "forget_mode": "time_window",
                "target_selector": {
                    "from": "2026-09-01T00:00:00+08:00",
                    "to": "2026-09-02T00:00:00+08:00",
                },
                "target_identity": {"db_ids": window_ids},
                "same_user_controls": [{"id": knowledge_ids["012"], "kind": "knowledge"}],
                "foreign_user_controls": [{"id": knowledge_ids["013"], "kind": "knowledge"}],
                "prerequisite_facts": {"events_in_window": 1, "events_outside_window": 1},
                "realtime_retrieval": {
                    "entrypoint": "observe_forget_execution:realtime",
                    "trace_reference": "dispatch/d13e-forget-004.json",
                    "snapshot": "prepared_state_snapshot",
                    "watermark": "prepared_state_watermark",
                },
                "rebuild_retrieval": {
                    "entrypoint": "observe_forget_execution:rebuild",
                    "trace_reference": "dispatch/d13e-forget-004.json",
                    "snapshot": "prepared_state_snapshot",
                    "watermark": "prepared_state_watermark",
                },
            },
            {
                "sample_id": "d13e-forget-005",
                "user_id": ALPHA,
                "forget_mode": "full_reset",
                "target_selector": {},
                "target_identity": {
                    "knowledge_ids": [
                        knowledge_ids[x] for x in sorted(knowledge_ids)
                        if x not in {"003", "007", "010", "013", "015"}
                    ],
                    "preference_ids": [seeded["alpha_preference_item_id"]],
                    "user_scope": ALPHA,
                },
                "same_user_controls": [],
                "foreign_user_controls": [
                    {"id": knowledge_ids["015"], "kind": "knowledge"},
                    {"id": seeded["beta_preference_item_id"], "kind": "preference"},
                ],
                "prerequisite_facts": {"knowledge_count": 12, "preference_count": 1},
                "realtime_retrieval": {
                    "entrypoint": "observe_forget_execution:realtime",
                    "trace_reference": "dispatch/d13e-forget-005.json",
                    "snapshot": "prepared_state_snapshot",
                    "watermark": "prepared_state_watermark",
                },
                "rebuild_retrieval": {
                    "entrypoint": "observe_forget_execution:rebuild",
                    "trace_reference": "dispatch/d13e-forget-005.json",
                    "snapshot": "prepared_state_snapshot",
                    "watermark": "prepared_state_watermark",
                },
            },
        ],
    }
    artifact["artifact_sha256"] = compute_artifact_sha256(artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "artifact": str(args.output),
        "artifact_sha256": artifact["artifact_sha256"],
        "source_db": str(source_path),
        "source_db_sha256": source_sha,
        "schema_fingerprint": schema_fingerprint,
        "state_preparation_commit": head,
        "resolved": resolved,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
