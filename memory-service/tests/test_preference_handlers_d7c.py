"""D7C 偏好 IPC handler：create/update/rollback/history/list 与用户隔离、幂等测试。"""

from __future__ import annotations

import pytest

from db import repositories as repo
from db.engine import create_db_engine, init_schema
from db.uow import UnitOfWork
from gateway.handlers import register_default_handlers
from gateway.preference_handlers import register_preference_handlers
from gateway.protocol import RequestValidationError
from gateway.registry import HandlerRegistry, RequestContext, UnsupportedMethodError


@pytest.fixture()
def engine(tmp_path):
    result = create_db_engine(str(tmp_path / "d7c.db"))
    init_schema(result, fts=False)
    return result


@pytest.fixture()
def registry(engine):
    def uow_factory():
        return UnitOfWork(engine)

    reg = HandlerRegistry()
    register_preference_handlers(reg, uow_factory)
    return reg


def _ctx(method: str, idempotency_key=None) -> RequestContext:
    return RequestContext(
        request_id="r1",
        trace_id="t1",
        method=method,
        deadline_ms=5000,
        idempotency_key=idempotency_key,
        extras={},
    )


def _call(registry, method: str, payload, idempotency_key=None):
    return registry.route(method)(payload, _ctx(method, idempotency_key))


def test_create_first_version(engine, registry):
    data = _call(
        registry,
        "preference.create",
        {
            "user_id": "u1",
            "preference_key": "response.language",
            "preference_scope": "global",
            "preference_value": "中文",
        },
        idempotency_key="idem-1",
    )
    assert data["created"] is True
    assert data["action"] == "create"
    item = data["item"]
    assert item["version"] == 1
    assert item["preference_key"] == "response.language"
    assert item["preference_scope"] == "global"
    assert item["is_current"] is True
    assert item["memory_status"] == "active"
    assert item["previous_version_id"] is None

    listed = _call(
        registry, "preference.list", {"user_id": "u1", "include_history": True}
    )
    assert len(listed["items"]) == 1
    assert listed["items"][0]["current"]["version"] == 1
    assert len(listed["items"][0]["history"]) == 1


def test_update_appends_version_and_noop_on_same_value(engine, registry):
    first = _call(
        registry,
        "preference.create",
        {"user_id": "u1", "preference_key": "k", "preference_scope": "global", "preference_value": "v1"},
        idempotency_key="idem-1",
    )
    second = _call(
        registry,
        "preference.update",
        {"user_id": "u1", "preference_key": "k", "preference_scope": "global", "new_value": "v2"},
        idempotency_key="idem-2",
    )
    assert second["created"] is True
    assert second["item"]["version"] == 2
    assert second["item"]["previous_version_id"] == first["item"]["preference_version_id"]

    history = _call(
        registry,
        "preference.history",
        {"user_id": "u1", "preference_key": "k", "preference_scope": "global"},
    )
    assert [(i["version"], i["is_current"], i["memory_status"]) for i in history["items"]] == [
        (1, False, "superseded"),
        (2, True, "active"),
    ]

    noop = _call(
        registry,
        "preference.update",
        {"user_id": "u1", "preference_key": "k", "preference_scope": "global", "new_value": "v2"},
        idempotency_key="idem-3",
    )
    assert noop["created"] is False
    assert noop["action"] == "no_op"
    assert noop["item"]["version"] == 2


def test_update_missing_item_rejected(engine, registry):
    with pytest.raises(RequestValidationError):
        _call(
            registry,
            "preference.update",
            {"user_id": "u1", "preference_key": "k", "preference_scope": "global", "new_value": "v1"},
        )


def test_rollback_appends_current_and_preserves_history(engine, registry):
    _call(
        registry,
        "preference.create",
        {"user_id": "u1", "preference_key": "k", "preference_scope": "global", "preference_value": "v1"},
        idempotency_key="idem-1",
    )
    v2 = _call(
        registry,
        "preference.update",
        {"user_id": "u1", "preference_key": "k", "preference_scope": "global", "new_value": "v2"},
        idempotency_key="idem-2",
    )
    rb = _call(
        registry,
        "preference.rollback",
        {"user_id": "u1", "preference_key": "k", "preference_scope": "global", "target_version": 1},
        idempotency_key="idem-3",
    )
    assert rb["created"] is True
    assert rb["item"]["version"] == 3
    assert rb["item"]["preference_value"] == "v1"
    assert rb["item"]["rollback_of_version_id"] == v2["item"]["previous_version_id"]
    assert [i["version"] for i in rb["history"]] == [1, 2, 3]
    assert rb["history"][-1]["is_current"] is True


def test_rollback_missing_target_rejected(engine, registry):
    _call(
        registry,
        "preference.create",
        {"user_id": "u1", "preference_key": "k", "preference_scope": "global", "preference_value": "v1"},
        idempotency_key="idem-1",
    )
    with pytest.raises(RequestValidationError):
        _call(
            registry,
            "preference.rollback",
            {"user_id": "u1", "preference_key": "k", "preference_scope": "global", "target_version": 9},
            idempotency_key="idem-2",
        )


def test_cross_user_isolation(engine, registry):
    _call(
        registry,
        "preference.create",
        {"user_id": "u1", "preference_key": "k", "preference_scope": "global", "preference_value": "v1"},
        idempotency_key="idem-1",
    )
    listed = _call(registry, "preference.list", {"user_id": "u2", "include_history": True})
    assert listed["items"] == []
    history = _call(
        registry,
        "preference.history",
        {"user_id": "u2", "preference_key": "k", "preference_scope": "global"},
    )
    assert history["items"] == []
    with pytest.raises(RequestValidationError):
        _call(
            registry,
            "preference.rollback",
            {"user_id": "u2", "preference_key": "k", "preference_scope": "global", "target_version": 1},
            idempotency_key="idem-2",
        )


def test_idempotent_replay_returns_same_version(engine, registry):
    first = _call(
        registry,
        "preference.create",
        {"user_id": "u1", "preference_key": "k", "preference_scope": "global", "preference_value": "v1"},
        idempotency_key="idem-1",
    )
    replay = _call(
        registry,
        "preference.create",
        {"user_id": "u1", "preference_key": "k", "preference_scope": "global", "preference_value": "v1"},
        idempotency_key="idem-1",
    )
    assert replay["created"] is False
    assert replay["item"]["preference_version_id"] == first["item"]["preference_version_id"]


def test_same_evidence_different_value_fails_closed(engine, registry):
    _call(
        registry,
        "preference.create",
        {
            "user_id": "u1",
            "preference_key": "k",
            "preference_scope": "global",
            "preference_value": "v1",
            "evidence_event_ids": ["ev-1"],
        },
        idempotency_key="idem-1",
    )
    with pytest.raises(RequestValidationError):
        _call(
            registry,
            "preference.create",
            {
                "user_id": "u1",
                "preference_key": "k",
                "preference_scope": "global",
                "preference_value": "v2",
                "evidence_event_ids": ["ev-1"],
            },
            idempotency_key="idem-2",
        )


def test_temporary_preference_defaults_to_candidate(engine, registry):
    data = _call(
        registry,
        "preference.create",
        {
            "user_id": "u1",
            "preference_key": "k",
            "preference_scope": "session",
            "preference_value": "temp",
            "is_temporary": True,
            "should_persist": False,
        },
        idempotency_key="idem-1",
    )
    assert data["item"]["memory_status"] == "candidate"


def test_string_boolean_flags_rejected(engine, registry):
    """[MEDIUM-2] is_temporary/should_persist 传字符串 "false" 必须拒绝，不得被 bool() 转为 True。"""
    with pytest.raises(RequestValidationError):
        _call(
            registry,
            "preference.create",
            {"user_id": "u1", "preference_key": "k", "preference_scope": "global",
             "preference_value": "v", "is_temporary": "false"},
        )
    with pytest.raises(RequestValidationError):
        _call(
            registry,
            "preference.create",
            {"user_id": "u1", "preference_key": "k", "preference_scope": "global",
             "preference_value": "v", "should_persist": "false"},
        )
    with pytest.raises(RequestValidationError):
        _call(
            registry,
            "preference.create",
            {"user_id": "u1", "preference_key": "k", "preference_scope": "global",
             "preference_value": "v", "is_temporary": 1},
        )


def test_default_registry_does_not_register_preference_methods():
    """[HIGH-1] 契约冻结前（CANDIDATE_SYNC/ADR-016 待立项）production 默认注册表不得包含 preference.*；
    未注册方法路由 → UNSUPPORTED_METHOD。"""
    reg = HandlerRegistry()
    register_default_handlers(reg)
    assert "preference.create" not in reg.methods()
    assert "preference.list" not in reg.methods()
    with pytest.raises(UnsupportedMethodError):
        reg.route("preference.create")


def test_validation_errors(engine, registry):
    with pytest.raises(RequestValidationError):
        _call(registry, "preference.create", {"preference_key": "k", "preference_scope": "global", "preference_value": "v"})
    with pytest.raises(RequestValidationError):
        _call(registry, "preference.create", {"user_id": "u1", "preference_key": "", "preference_scope": "global", "preference_value": "v"})
    with pytest.raises(RequestValidationError):
        _call(registry, "preference.create", {"user_id": "u1", "preference_key": "k", "preference_scope": "bogus", "preference_value": "v"})
    with pytest.raises(RequestValidationError):
        _call(registry, "preference.create", {"user_id": "u1", "preference_key": "k", "preference_scope": "global", "preference_value": "v", "memory_status": "nope"})
    with pytest.raises(RequestValidationError):
        _call(registry, "preference.rollback", {"user_id": "u1", "preference_key": "k", "preference_scope": "global", "target_version": "x"})
