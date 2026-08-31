"""D7D 偏好版本持久化：事务、幂等、回滚与用户隔离测试。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import delete, insert, update
from sqlalchemy.exc import IntegrityError

from db import repositories as repo
from db.engine import create_db_engine, init_schema
from db.schema import memory_items, memory_version_receipts, memory_versions
from db.uow import UnitOfWork


@pytest.fixture()
def engine(tmp_path):
    result = create_db_engine(str(tmp_path / "d7d.db"))
    init_schema(result, fts=False)
    return result


def _save(engine, **overrides):
    values = {
        "user_id": "u1",
        "preference_key": "response.language",
        "preference_scope": "global",
        "preference_value": "中文",
        "memory_status": "active",
        "evidence_fingerprint": "ev-1",
        "idempotency_key": "idem-1",
        "request_fingerprint": "req-1",
    }
    values.update(overrides)
    with UnitOfWork(engine) as uow:
        return repo.save_preference_version(uow.conn, **values)


def test_create_first_version_and_read_current_history(engine):
    created = _save(engine)

    assert created["created"] is True
    assert created["version"] == 1
    assert created["previous_version_id"] is None
    assert created["is_current"] == 1
    assert created["rollback_of_version_id"] is None

    with engine.connect() as conn:
        current = repo.get_current_preference_version(
            conn, user_id="u1", preference_key="response.language", preference_scope="global"
        )
        history = repo.list_preference_versions(
            conn, user_id="u1", preference_key="response.language", preference_scope="global"
        )

    assert current["id"] == created["id"]
    assert [row["version"] for row in history] == [1]


def test_update_creates_new_current_and_preserves_history(engine):
    first = _save(engine)
    second = _save(
        engine,
        preference_value="英文",
        evidence_fingerprint="ev-2",
        idempotency_key="idem-2",
        request_fingerprint="req-2",
    )

    assert second["created"] is True
    assert second["version"] == 2
    assert second["previous_version_id"] == first["id"]

    with engine.connect() as conn:
        history = repo.list_preference_versions(
            conn, user_id="u1", preference_key="response.language", preference_scope="global"
        )
        current = repo.get_current_preference_version(
            conn, user_id="u1", preference_key="response.language", preference_scope="global"
        )

    assert [(row["version"], row["is_current"], row["memory_status"]) for row in history] == [
        (1, 0, "superseded"),
        (2, 1, "active"),
    ]
    assert current["id"] == second["id"]


def test_same_value_is_noop_and_does_not_expand_version_history(engine):
    first = _save(engine)
    same = _save(
        engine,
        evidence_fingerprint="ev-2",
        idempotency_key="idem-2",
        request_fingerprint="req-2",
    )

    assert same["created"] is False
    assert same["id"] == first["id"]
    with engine.connect() as conn:
        history = repo.list_preference_versions(
            conn, user_id="u1", preference_key="response.language", preference_scope="global"
        )
    assert [row["version"] for row in history] == [1]
    with pytest.raises(repo.PreferenceVersionIdempotencyConflictError):
        _save(
            engine,
            evidence_fingerprint="ev-3",
            idempotency_key="idem-2",
            request_fingerprint="req-other",
        )
    with pytest.raises(repo.PreferenceVersionEvidenceConflictError):
        _save(
            engine,
            preference_value="英文",
            evidence_fingerprint="ev-2",
            idempotency_key="idem-3",
            request_fingerprint="req-3",
        )


def test_idempotency_replay_returns_same_version_and_conflicting_key_fails_closed(engine):
    first = _save(engine)
    replay = _save(engine)

    assert replay["created"] is False
    assert replay["id"] == first["id"]
    with pytest.raises(repo.PreferenceVersionIdempotencyConflictError):
        _save(engine, preference_value="英文", evidence_fingerprint="ev-2", request_fingerprint="other")


def test_reused_evidence_with_different_value_fails_closed(engine):
    _save(engine)

    with pytest.raises(repo.PreferenceVersionEvidenceConflictError):
        _save(
            engine,
            preference_value="英文",
            idempotency_key="idem-2",
            request_fingerprint="req-2",
        )


def test_rollback_appends_new_current_without_overwriting_history(engine):
    first = _save(engine)
    second = _save(
        engine,
        preference_value="英文",
        evidence_fingerprint="ev-2",
        idempotency_key="idem-2",
        request_fingerprint="req-2",
    )
    with UnitOfWork(engine) as uow:
        rolled_back = repo.rollback_preference_version(
            uow.conn,
            user_id="u1",
            preference_version_id=first["id"],
            idempotency_key="idem-3",
            request_fingerprint="req-3",
        )

    assert rolled_back["created"] is True
    assert rolled_back["version"] == 3
    assert rolled_back["previous_version_id"] == second["id"]
    assert rolled_back["rollback_of_version_id"] == first["id"]
    assert rolled_back["preference_value"] == "中文"

    with engine.connect() as conn:
        history = repo.list_preference_versions(
            conn, user_id="u1", preference_key="response.language", preference_scope="global"
        )
    assert [(row["version"], row["is_current"]) for row in history] == [(1, 0), (2, 0), (3, 1)]


def test_cross_user_read_and_rollback_are_rejected(engine):
    first = _save(engine)

    with engine.connect() as conn:
        assert repo.get_preference_version(conn, user_id="u2", preference_version_id=first["id"]) is None
        assert repo.list_preference_versions(
            conn, user_id="u2", preference_key="response.language", preference_scope="global"
        ) == []

    with pytest.raises(repo.PreferenceVersionNotFoundError):
        with UnitOfWork(engine) as uow:
            repo.rollback_preference_version(
                uow.conn,
                user_id="u2",
                preference_version_id=first["id"],
                idempotency_key="idem-cross",
                request_fingerprint="req-cross",
            )


def test_transaction_failure_leaves_no_item_or_version(engine):
    with pytest.raises(RuntimeError):
        with UnitOfWork(engine) as uow:
            repo.save_preference_version(
                uow.conn,
                user_id="u1",
                preference_key="response.language",
                preference_scope="global",
                preference_value="中文",
                memory_status="active",
                evidence_fingerprint="ev-1",
                idempotency_key="idem-1",
                request_fingerprint="req-1",
            )
            raise RuntimeError("模拟事务失败")

    with engine.connect() as conn:
        assert repo.get_current_preference_version(
            conn, user_id="u1", preference_key="response.language", preference_scope="global"
        ) is None


def test_database_partial_unique_constraint_prevents_two_current_versions(engine):
    created = _save(engine)
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                insert(memory_versions).values(
                    memory_item_id=created["memory_item_id"],
                    version=99,
                    previous_version_id=created["id"],
                    rollback_of_version_id=None,
                    preference_value="冲突值",
                    memory_status="active",
                    evidence_fingerprint="ev-conflict",
                    idempotency_key="idem-conflict",
                    request_fingerprint="req-conflict",
                    is_current=1,
                    created_at="2026-08-31T00:00:00+00:00",
                )
            )


def test_database_triggers_reject_cross_item_version_links_and_current_pointer(engine):
    first = _save(engine)
    other = _save(
        engine,
        preference_key="response.length",
        preference_value="简短",
        evidence_fingerprint="ev-2",
        idempotency_key="idem-2",
        request_fingerprint="req-2",
    )

    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                insert(memory_versions).values(
                    memory_item_id=first["memory_item_id"],
                    version=2,
                    previous_version_id=other["id"],
                    rollback_of_version_id=None,
                    preference_value="冲突值",
                    memory_status="active",
                    evidence_fingerprint="ev-cross",
                    idempotency_key="idem-cross",
                    request_fingerprint="req-cross",
                    is_current=0,
                    created_at="2026-08-31T00:00:00+00:00",
                )
            )
        with pytest.raises(IntegrityError):
            conn.execute(
                insert(memory_versions).values(
                    memory_item_id=first["memory_item_id"],
                    version=3,
                    previous_version_id=first["id"],
                    rollback_of_version_id=None,
                    preference_value="错误前驱",
                    memory_status="active",
                    evidence_fingerprint="ev-stale",
                    idempotency_key="idem-stale",
                    request_fingerprint="req-stale",
                    is_current=0,
                    created_at="2026-08-31T00:00:00+00:00",
                )
            )
        with pytest.raises(IntegrityError):
            conn.execute(
                update(memory_versions)
                .where(memory_versions.c.id == first["id"])
                .values(rollback_of_version_id=other["id"])
            )
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql(
                "UPDATE memory_items SET current_version_id = ? WHERE id = ?",
                (other["id"], first["memory_item_id"]),
            )
        with pytest.raises(IntegrityError):
            conn.execute(
                insert(memory_items).values(
                    user_id="u3",
                    preference_key="response.language",
                    preference_scope="global",
                    current_version_id=first["id"],
                    created_at="2026-08-31T00:00:00+00:00",
                    updated_at="2026-08-31T00:00:00+00:00",
                )
            )
        with pytest.raises(IntegrityError):
            conn.execute(
                insert(memory_version_receipts).values(
                    memory_item_id=first["memory_item_id"],
                    memory_version_id=other["id"],
                    operation_kind="no_op",
                    preference_value="简短",
                    memory_status="active",
                    evidence_fingerprint="ev-cross-receipt",
                    idempotency_key="idem-cross-receipt",
                    request_fingerprint="req-cross-receipt",
                    created_at="2026-08-31T00:00:00+00:00",
                )
            )
        with pytest.raises(IntegrityError):
            conn.execute(
                insert(memory_version_receipts).values(
                    memory_item_id=first["memory_item_id"],
                    memory_version_id=first["id"],
                    operation_kind="no_op",
                    preference_value="伪造值",
                    memory_status="active",
                    evidence_fingerprint="ev-forged-receipt",
                    idempotency_key="idem-forged-receipt",
                    request_fingerprint="req-forged-receipt",
                    created_at="2026-08-31T00:00:00+00:00",
                )
            )
        with pytest.raises(IntegrityError):
            conn.execute(
                update(memory_versions)
                .where(memory_versions.c.id == first["id"])
                .values(version=2)
            )
        with pytest.raises(IntegrityError):
            conn.execute(
                update(memory_versions)
                .where(memory_versions.c.id == first["id"])
                .values(preference_value="被篡改")
            )
        with pytest.raises(IntegrityError):
            conn.execute(delete(memory_versions).where(memory_versions.c.id == first["id"]))


def test_database_triggers_protect_historical_rows_and_current_leaf(engine):
    first = _save(engine)
    second = _save(
        engine,
        preference_value="英文",
        evidence_fingerprint="ev-2",
        idempotency_key="idem-2",
        request_fingerprint="req-2",
    )

    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                update(memory_versions)
                .where(memory_versions.c.id == first["id"])
                .values(preference_value="被篡改")
            )
        with pytest.raises(IntegrityError):
            conn.execute(
                update(memory_versions)
                .where(memory_versions.c.id == first["id"])
                .values(is_current=1, memory_status="active")
            )
        with pytest.raises(IntegrityError):
            conn.execute(
                update(memory_versions)
                .where(memory_versions.c.id == second["id"])
                .values(is_current=0, memory_status="superseded")
            )
        with pytest.raises(IntegrityError):
            conn.execute(delete(memory_versions).where(memory_versions.c.id == first["id"]))
        with pytest.raises(IntegrityError):
            conn.execute(delete(memory_versions).where(memory_versions.c.id == second["id"]))


def test_database_trigger_activates_verified_successor_without_current_gap(engine):
    first = _save(engine)
    with engine.begin() as conn:
        successor_id = int(
            conn.execute(
                insert(memory_versions).values(
                    memory_item_id=first["memory_item_id"],
                    version=2,
                    previous_version_id=first["id"],
                    rollback_of_version_id=None,
                    preference_value="英文",
                    memory_status="active",
                    evidence_fingerprint="ev-successor",
                    idempotency_key="idem-successor",
                    request_fingerprint="req-successor",
                    is_current=0,
                    created_at="2026-08-31T00:00:00+00:00",
                )
            ).lastrowid
        )
        conn.execute(
            update(memory_versions)
            .where(memory_versions.c.id == first["id"])
            .values(is_current=0, memory_status="superseded")
        )
        current_id = conn.execute(
            memory_items.select()
            .with_only_columns(memory_items.c.current_version_id)
            .where(memory_items.c.id == first["memory_item_id"])
        ).scalar_one()
        assert current_id == successor_id
        assert conn.execute(
            memory_versions.select()
            .with_only_columns(memory_versions.c.is_current)
            .where(memory_versions.c.id == successor_id)
        ).scalar_one() == 1


def test_database_checks_reject_unknown_scope_and_memory_status(engine):
    created = _save(engine)
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                insert(memory_items).values(
                    user_id="u-invalid",
                    preference_key="response.language",
                    preference_scope="whatever",
                    current_version_id=None,
                    created_at="2026-08-31T00:00:00+00:00",
                    updated_at="2026-08-31T00:00:00+00:00",
                )
            )
        with pytest.raises(IntegrityError):
            conn.execute(
                insert(memory_versions).values(
                    memory_item_id=created["memory_item_id"],
                    version=2,
                    previous_version_id=created["id"],
                    rollback_of_version_id=None,
                    preference_value="非法状态",
                    memory_status="hello",
                    evidence_fingerprint="ev-invalid",
                    idempotency_key="idem-invalid",
                    request_fingerprint="req-invalid",
                    is_current=0,
                    created_at="2026-08-31T00:00:00+00:00",
                )
            )


def test_concurrent_updates_are_serialized_and_leave_exactly_one_current_version(engine):
    _save(engine)

    def update_value(value: str, number: int):
        return _save(
            engine,
            preference_value=value,
            evidence_fingerprint=f"ev-{number}",
            idempotency_key=f"idem-{number}",
            request_fingerprint=f"req-{number}",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda item: update_value(*item), [("英文", 2), ("日文", 3)]))

    assert all(result["created"] for result in results)
    with engine.connect() as conn:
        history = repo.list_preference_versions(
            conn, user_id="u1", preference_key="response.language", preference_scope="global"
        )
        item_pointer = conn.exec_driver_sql(
            "SELECT current_version_id FROM memory_items WHERE user_id = 'u1' "
            "AND preference_key = 'response.language' AND preference_scope = 'global'"
        ).scalar_one()

    assert [row["version"] for row in history] == [1, 2, 3]
    current = [row for row in history if row["is_current"] == 1]
    assert len(current) == 1
    assert current[0]["id"] == item_pointer
