"""L1 tests for D13D's read-only Safety execution observation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from db import repositories as repo
from db.engine import create_db_engine, init_schema
from db.uow import UnitOfWork
from gateway.handlers import register_default_handlers, register_event_ingest_handler
from gateway.registry import HandlerRegistry, RequestContext
from service.d13d_safety_observability import observe_safety_execution


USER = "d13d-safety-user"
OTHER_USER = "d13d-safety-other"
TRACE = "d13d-safety-trace"


@pytest.fixture()
def environment(tmp_path):
    engine = create_db_engine(str(tmp_path / "safety.db"))
    init_schema(engine)
    registry = HandlerRegistry()
    register_default_handlers(registry)
    register_event_ingest_handler(registry, uow_factory=lambda: UnitOfWork(engine))
    return engine, registry


def _ingest(registry: HandlerRegistry, *, event_id: str, content_summary: str) -> None:
    now = datetime.now(timezone.utc)
    handler = registry.route("event.ingest")
    handler(
        {
            "schema_version": "0.1",
            "event_id": event_id,
            "user_id": USER,
            "actor_id": USER,
            "session_id": "d13d-safety-session",
            "idempotency_key": f"idem-{event_id}",
            "source_type": "chat",
            "event_type": "user_message",
            "occurred_at": (now - timedelta(minutes=1)).isoformat(),
            "captured_at": now.isoformat(),
            "content_summary": content_summary,
            "consent_scope": "memory_only",
        },
        RequestContext(
            request_id=f"req-{event_id}",
            trace_id=TRACE,
            method="event.ingest",
            deadline_ms=5000,
            idempotency_key=f"idem-{event_id}",
        ),
    )


def test_observation_uses_persisted_critical_admission_facts(environment):
    engine, registry = environment
    _ingest(registry, event_id="d13d-safety-critical", content_summary="api_key placeholder")

    with engine.connect() as conn:
        observed = observe_safety_execution(
            conn, user_id=USER, trace_id=TRACE, foreign_user_id=OTHER_USER
        )

    assert observed == {
        "critical_gate_bypass_count": 0,
        "normal_memory_write_count": 0,
        "audit_plaintext_leak_count": 0,
        "cross_user_violation_count": 0,
        "observed_event_count": 1,
        "trace_reference": f"source-events:{TRACE}",
    }


def test_observation_detects_persisted_admission_or_privacy_regression(environment):
    engine, registry = environment
    _ingest(registry, event_id="d13d-safety-regression", content_summary="api_key placeholder")
    with engine.begin() as conn:
        conn.execute(
            repo.source_events.update()
            .where(repo.source_events.c.event_id == "d13d-safety-regression")
            .values(
                admission_decision="allow_extraction",
                content_summary="unexpected stored content",
            )
        )
    with engine.connect() as conn:
        observed = observe_safety_execution(
            conn, user_id=USER, trace_id=TRACE, foreign_user_id=OTHER_USER
        )

    assert observed["critical_gate_bypass_count"] == 1
    assert observed["audit_plaintext_leak_count"] == 1


def test_observation_rejects_missing_trace_or_non_foreign_probe(environment):
    engine, _ = environment
    with engine.connect() as conn:
        with pytest.raises(ValueError, match="no source_events"):
            observe_safety_execution(
                conn, user_id=USER, trace_id=TRACE, foreign_user_id=OTHER_USER
            )
        with pytest.raises(ValueError, match="must differ"):
            observe_safety_execution(
                conn, user_id=USER, trace_id="another-trace", foreign_user_id=USER
            )
