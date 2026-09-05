"""L1 tests for D13D's read-only Forget execution observation seam."""

from __future__ import annotations

import pytest

from db import repositories as repo
from db.engine import create_db_engine, init_schema
from db.schema import memory_entries
from retrieval.contracts import Watermark, WatermarkDomain, WatermarkKind
from retrieval.evaluation import ForgetResidualSample
from service.d13d_forget_observability import (
    ForgetRetrievalObservation,
    capture_forget_execution_snapshot,
    observe_forget_execution,
)


USER = "forget-observer-user"
FOREIGN = "forget-observer-foreign"


def _watermark() -> Watermark:
    return Watermark(
        domain=WatermarkDomain(
            scope_id="d13d-test", stream="memory", partition="default", source_generation="g1"
        ),
        kind=WatermarkKind.MONOTONIC_INT,
        value=1,
    )


def _retrieval(
    target_ids: tuple[str, ...] | str, *, ranked_ids: tuple[str, ...] = ()
) -> ForgetRetrievalObservation:
    confirmed = (target_ids,) if isinstance(target_ids, str) else target_ids
    return ForgetRetrievalObservation(
        sample=ForgetResidualSample(
            query_id="controlled-query",
            confirmed_target_ids=confirmed,
            ranked_ids=ranked_ids,
        ),
        dataset_version="d13d-controlled-l1",
        source_snapshot_id="sqlite-controlled-snapshot",
        source_watermark=_watermark(),
    )


@pytest.fixture()
def state(tmp_path):
    engine = create_db_engine(str(tmp_path / "forget-observer.db"))
    init_schema(engine)
    with engine.begin() as conn:
        target = repo.insert_memory_entry(
            conn, user_id=USER, entry_type="knowledge", content={"value": "target"}
        )
        control = repo.insert_memory_entry(
            conn, user_id=USER, entry_type="knowledge", content={"value": "control"}
        )
        foreign = repo.insert_memory_entry(
            conn, user_id=FOREIGN, entry_type="knowledge", content={"value": "foreign"}
        )
    return engine, target, control, foreign


def _snapshot(engine, target: int):
    with engine.connect() as conn:
        return capture_forget_execution_snapshot(
            conn,
            user_id=USER,
            foreign_user_id=FOREIGN,
            confirmed_target_ids=[f"knowledge:{target}"],
        )


def test_observation_uses_pre_execution_controls_and_existing_residual_evaluator(state):
    engine, target, _control, _foreign = state
    snapshot = _snapshot(engine, target)
    with engine.begin() as conn:
        count, _ = repo.soft_delete_resolved_targets(
            conn,
            user_id=USER,
            target_type="knowledge",
            resolved_target_ids=[str(target)],
            forget_plan_id="controlled-plan",
        )
    assert count == 1
    target_id = f"knowledge:{target}"
    with engine.connect() as conn:
        observed = observe_forget_execution(
            conn,
            snapshot=snapshot,
            realtime_observation=_retrieval(target_id),
            rebuild_observation=_retrieval(target_id),
        )
    assert observed == {
        "missed_target_items": 0,
        "wrongly_deleted_items": 0,
        "cross_user_violation_count": 0,
        "residual_after_realtime_query": 0,
        "residual_after_full_rebuild": 0,
    }


def test_observation_detects_missed_target_and_real_query_residual(state):
    engine, target, _control, _foreign = state
    snapshot = _snapshot(engine, target)
    target_id = f"knowledge:{target}"
    with engine.connect() as conn:
        observed = observe_forget_execution(
            conn,
            snapshot=snapshot,
            realtime_observation=_retrieval(target_id, ranked_ids=(target_id,)),
            rebuild_observation=_retrieval(target_id, ranked_ids=(target_id,)),
        )
    assert observed["missed_target_items"] == 1
    assert observed["residual_after_realtime_query"] == 1
    assert observed["residual_after_full_rebuild"] == 1


def test_observation_detects_wrong_deletion_and_cross_user_mutation(state):
    engine, target, control, foreign = state
    snapshot = _snapshot(engine, target)
    target_id = f"knowledge:{target}"
    with engine.begin() as conn:
        conn.execute(
            memory_entries.update()
            .where(memory_entries.c.id.in_([control, foreign]))
            .values(is_deleted=1)
        )
    with engine.connect() as conn:
        observed = observe_forget_execution(
            conn,
            snapshot=snapshot,
            realtime_observation=_retrieval(target_id),
            rebuild_observation=_retrieval(target_id),
        )
    assert observed["wrongly_deleted_items"] == 1
    assert observed["cross_user_violation_count"] == 1


def test_observation_covers_full_reset_tagged_knowledge_and_preference(state):
    engine, target, _control, _foreign = state
    with engine.begin() as conn:
        owner_preference = repo.save_preference_version(
            conn,
            user_id=USER,
            preference_key="theme",
            preference_scope="global",
            preference_value="dark",
            memory_status="active",
            evidence_fingerprint="owner-pref-evidence",
            idempotency_key=None,
            request_fingerprint="owner-pref-request",
        )
        foreign_preference = repo.save_preference_version(
            conn,
            user_id=FOREIGN,
            preference_key="theme",
            preference_scope="global",
            preference_value="light",
            memory_status="active",
            evidence_fingerprint="foreign-pref-evidence",
            idempotency_key=None,
            request_fingerprint="foreign-pref-request",
        )
    owner_item_id = int(owner_preference["memory_item_id"])
    foreign_item_id = int(foreign_preference["memory_item_id"])
    target_ids = (f"knowledge:{target}", f"preference:{owner_item_id}")
    with engine.connect() as conn:
        snapshot = capture_forget_execution_snapshot(
            conn,
            user_id=USER,
            foreign_user_id=FOREIGN,
            confirmed_target_ids=target_ids,
        )
    with engine.begin() as conn:
        count, _ = repo.soft_delete_resolved_targets(
            conn,
            user_id=USER,
            target_type="all",
            resolved_target_ids=list(target_ids),
            forget_plan_id="full-reset-controlled-plan",
        )
    assert count == 2
    with engine.connect() as conn:
        observed = observe_forget_execution(
            conn,
            snapshot=snapshot,
            realtime_observation=_retrieval(target_ids),
            rebuild_observation=_retrieval(target_ids),
        )
        foreign_current = repo.get_current_preference_version(
            conn, user_id=FOREIGN, preference_key="theme", preference_scope="global"
        )
    assert observed == {
        "missed_target_items": 0,
        "wrongly_deleted_items": 0,
        "cross_user_violation_count": 0,
        "residual_after_realtime_query": 0,
        "residual_after_full_rebuild": 0,
    }
    assert foreign_current is not None
    assert foreign_current["memory_status"] == "active"
    assert foreign_item_id > 0


def test_observation_fails_closed_for_missing_or_unbound_retrieval_observation(state):
    engine, target, _control, _foreign = state
    snapshot = _snapshot(engine, target)
    target_id = f"knowledge:{target}"
    with engine.connect() as conn:
        with pytest.raises(ValueError, match="missing realtime"):
            observe_forget_execution(
                conn,
                snapshot=snapshot,
                realtime_observation=None,
                rebuild_observation=_retrieval(target_id),
            )
        with pytest.raises(ValueError, match="not bound"):
            observe_forget_execution(
                conn,
                snapshot=snapshot,
                realtime_observation=_retrieval("knowledge:999"),
                rebuild_observation=_retrieval(target_id),
            )
