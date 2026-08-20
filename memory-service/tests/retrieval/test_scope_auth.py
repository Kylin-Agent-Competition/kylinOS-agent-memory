"""L1_FAKE 契约测试：Scope 授权边界/过期/操作隔离/摘要轮换。

对应 docs/day3/09：T042,T043,T044,T045,T046,T047,T048。
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from retrieval import contracts as c
from fakes import FakeGenerationBuild, FakeVectorProvider, sign_request_payload

DIG = "hmac-sha256:k1:" + "6" * 64
DIG2 = "hmac-sha256:k2:" + "7" * 64
KEY1 = b"historical-k1-secret"
KEY2 = b"active-k2-secret"
NOW = datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc)


def make_wm(scope_id: str, value: int) -> c.Watermark:
    return c.Watermark(
        domain=c.WatermarkDomain(scope_id=scope_id, stream="out", partition="0", source_generation="g0"),
        kind=c.WatermarkKind.MONOTONIC_INT,
        value=value,
    )


def make_scope(scope_id="s1", kind="user", user_id="alpha", fingerprint=DIG) -> c.IndexScope:
    return c.IndexScope(
        scope_id=scope_id,
        kind=c.ScopeKind(kind),
        user_id=user_id if kind == "user" else None,
        shard_id=None,
        scope_fingerprint=fingerprint,
    )


def make_auth(p, scope_id="s1", operations=("get_index_state",), expires_at=None):
    return c.ScopeAuthorization(
        actor_ref="a",
        authorization_ref="ar",
        scope_id=scope_id,
        allowed_operations=list(operations),
        expires_at=expires_at or (p.clock.now + timedelta(minutes=5)),
    )


def make_state_request(p, *, scope=None, auth=None):
    scope = scope or make_scope()
    auth = auth or make_auth(p)
    return c.IndexStateRequest(request_id="r1", trace_id="t1", scope=scope, scope_authorization=auth, deadline_at=p.clock.now + timedelta(minutes=5))


# T043 scope_id 不匹配拒绝
def test_scope_id_mismatch_denied():
    p = FakeVectorProvider()
    auth = make_auth(p, scope_id="s2")
    res = p.get_index_state(make_state_request(p, scope=make_scope("s1"), auth=auth))
    assert not res.ok and res.error.code is c.RetrievalErrorCode.AUTHORIZATION_DENIED


# T045 操作隔离：get_index_state 授权不得执行 rebuild，反之亦然
def test_get_index_state_auth_cannot_rebuild():
    p = FakeVectorProvider()
    auth = make_auth(p, operations=["get_index_state"])
    rebuild = sign_request_payload(c.VectorRebuildRequest(
        request_id="r1", trace_id="t1", user_id="alpha", deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key="ik", payload_hash=DIG, source_snapshot_id="snap", source_watermark=make_wm("s1", 1),
        target_generation="g2", schema_version="v1", reason=c.RebuildReason.BOOTSTRAP,
        scope=make_scope("s1"), scope_authorization=auth,
    ))
    res = p.rebuild(rebuild)
    assert not res.ok and res.error.code is c.RetrievalErrorCode.AUTHORIZATION_DENIED


def test_rebuild_auth_cannot_get_index_state():
    p = FakeVectorProvider()
    auth = make_auth(p, operations=["rebuild"])
    res = p.get_index_state(make_state_request(p, auth=auth))
    assert not res.ok and res.error.code is c.RetrievalErrorCode.AUTHORIZATION_DENIED


# T046 授权过期：expires_at 相等或已过期拒绝
def test_authorization_expired():
    p = FakeVectorProvider()
    auth = make_auth(p, expires_at=p.clock.now)
    res = p.get_index_state(make_state_request(p, auth=auth))
    assert not res.ok and res.error.code is c.RetrievalErrorCode.AUTHORIZATION_EXPIRED


# T044 密钥轮换保持 scope_id 稳定，仅 fingerprint 变化
def test_scope_id_stable_across_key_rotation():
    a = make_scope("s1", fingerprint=DIG)
    b = make_scope("s1", fingerprint=DIG2)
    assert a.scope_id == b.scope_id
    assert a.scope_fingerprint != b.scope_fingerprint


def test_scope_rotation_preserves_generation_watermark_and_count():
    p = FakeVectorProvider(
        generation_builds={
            ("s1", "g2"): FakeGenerationBuild(
                source_watermark=make_wm("s1", 5),
                record_digests=(DIG2, DIG2),
                expected_record_count=2,
            )
        }
    )
    original_scope = make_scope("s1", fingerprint=DIG)
    rebuild = sign_request_payload(c.VectorRebuildRequest(
        request_id="r1", trace_id="t1", user_id="alpha", deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key="ik", payload_hash=DIG, source_snapshot_id="snap",
        source_watermark=make_wm("s1", 5), target_generation="g2", schema_version="v1",
        reason=c.RebuildReason.SCHEMA_CHANGE, scope=original_scope,
        scope_authorization=make_auth(p, operations=["rebuild"]),
    ))
    assert p.rebuild(rebuild).ok

    rotated_scope = make_scope("s1", fingerprint=DIG2)
    state = p.get_index_state(make_state_request(p, scope=rotated_scope))
    assert state.ok
    assert state.value.scope.scope_fingerprint == DIG2
    assert state.value.serving_generation == "g2"
    assert state.value.applied_watermark == make_wm("s1", 5)
    assert state.value.record_count == 2


def make_rebuild_for_scope_rotation(p, *, key_id, key, fingerprint):
    request = c.VectorRebuildRequest(
        request_id="r1",
        trace_id="t1",
        user_id="alpha",
        deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key="ik-rebuild",
        payload_hash=f"hmac-sha256:{key_id}:" + "0" * 64,
        source_snapshot_id="snap",
        source_watermark=make_wm("s1", 5),
        target_generation="g2",
        schema_version="v1",
        reason=c.RebuildReason.SCHEMA_CHANGE,
        scope=make_scope("s1", fingerprint=fingerprint),
        scope_authorization=make_auth(p, operations=["rebuild"]),
    )
    return sign_request_payload(request, key_id=key_id, key=key)


def test_scope_rotation_preserves_rebuild_idempotency_replay():
    p = FakeVectorProvider(digest_keys={"k1": KEY1, "k2": KEY2})
    first_request = make_rebuild_for_scope_rotation(
        p, key_id="k1", key=KEY1, fingerprint=DIG
    )
    replay_request = make_rebuild_for_scope_rotation(
        p, key_id="k2", key=KEY2, fingerprint=DIG2
    )

    first = p.rebuild(first_request)
    replay = p.rebuild(replay_request)

    assert first.ok and replay.ok and replay.value == first.value
    assert p.rebuild_effect_count == 1


# T047 历史验证 key 支持轮换后的幂等重放
def make_upsert(p, *, key_id="k1", key=KEY1, version_id="v1"):
    rec = c.VectorRecord(memory_id="m1", version_id=version_id, user_id="alpha", vector=[0.0] * 768, object_type=c.ObjectType.KNOWLEDGE, memory_type="long_term", index_text_hash=DIG)
    request = c.VectorUpsertRequest(
        request_id="r1", trace_id="t1", user_id="alpha", deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key="ik", payload_hash=f"hmac-sha256:{key_id}:" + "0" * 64,
        index_generation="g1", source_watermark=make_wm("alpha", 1), records=[rec],
    )
    semantic_payload = request.model_dump(
        mode="json", exclude={"request_id", "trace_id", "deadline_at", "payload_hash"}
    )
    return request.model_copy(
        update={"payload_hash": c.digest_from_canonical(key_id, key, semantic_payload)}
    )


def test_key_rotation_same_semantics_replays_without_second_side_effect():
    p = FakeVectorProvider(digest_keys={"k1": KEY1, "k2": KEY2})
    req1 = make_upsert(p, key_id="k1", key=KEY1)
    req2 = make_upsert(p, key_id="k2", key=KEY2)
    first = p.upsert(req1)
    replay = p.upsert(req2)
    assert first.ok and replay.ok and replay.value == first.value
    assert p.write_effect_count == 1


def test_key_rotation_different_semantics_conflicts():
    p = FakeVectorProvider(digest_keys={"k1": KEY1, "k2": KEY2})
    assert p.upsert(make_upsert(p, key_id="k1", key=KEY1, version_id="v1")).ok
    res = p.upsert(make_upsert(p, key_id="k2", key=KEY2, version_id="v2"))
    assert not res.ok and res.error.code is c.RetrievalErrorCode.CONFLICT
    assert p.write_effect_count == 1


def test_key_rotation_without_historical_key_fails_closed():
    p = FakeVectorProvider(digest_keys={"k1": KEY1, "k2": KEY2})
    req1 = make_upsert(p, key_id="k1", key=KEY1)
    req2 = make_upsert(p, key_id="k2", key=KEY2)
    assert p.upsert(req1).ok
    del p.digest_keys["k1"]
    res = p.upsert(req2)
    assert not res.ok and res.error.code is c.RetrievalErrorCode.DIGEST_KEY_UNAVAILABLE
    assert p.write_effect_count == 1


# T048 generation 内不得混用 digest key-id
def test_rebuild_mixed_key_generation_rejected():
    values = ({"memory_id": "m1", "index_text": "one"}, {"memory_id": "m2", "index_text": "two"})
    digests = (
        c.digest_from_canonical("k1", KEY1, values[0]),
        c.digest_from_canonical("k2", KEY2, values[1]),
    )
    p = FakeVectorProvider(
        digest_keys={"k1": KEY1, "k2": KEY2},
        generation_builds={
            "g2": FakeGenerationBuild(
                source_watermark=make_wm("s1", 1),
                record_values=values,
                record_digests=digests,
                expected_record_count=2,
            )
        },
    )
    auth = make_auth(p, operations=["rebuild"])
    rebuild = c.VectorRebuildRequest(
        request_id="r1", trace_id="t1", user_id="alpha", deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key="ik", payload_hash=DIG, source_snapshot_id="snap", source_watermark=make_wm("s1", 1),
        target_generation="g2", schema_version="v1", reason=c.RebuildReason.SCHEMA_CHANGE,
        scope=make_scope("s1"), scope_authorization=auth,
    )
    res = p.rebuild(sign_request_payload(rebuild, key_id="k2", key=KEY2))
    assert not res.ok and res.error.code is c.RetrievalErrorCode.CONFLICT
    assert "s1" not in p.serving


def test_rebuild_new_key_generation_activates_only_after_complete_verification():
    values = ({"memory_id": "m1", "index_text": "one"}, {"memory_id": "m2", "index_text": "two"})
    digests = tuple(c.digest_from_canonical("k2", KEY2, value) for value in values)
    p = FakeVectorProvider(
        digest_keys={"k1": KEY1, "k2": KEY2},
        generation_builds={
            "g2": FakeGenerationBuild(
                source_watermark=make_wm("s1", 1),
                record_values=values,
                record_digests=digests,
                expected_record_count=2,
            )
        },
    )
    auth = make_auth(p, operations=["rebuild"])
    rebuild = c.VectorRebuildRequest(
        request_id="r1", trace_id="t1", user_id="alpha", deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key="ik", payload_hash=DIG2, source_snapshot_id="snap", source_watermark=make_wm("s1", 1),
        target_generation="g2", schema_version="v1", reason=c.RebuildReason.SCHEMA_CHANGE,
        scope=make_scope("s1"), scope_authorization=auth,
    )
    result = p.rebuild(sign_request_payload(rebuild, key_id="k2", key=KEY2))
    assert result.ok and result.value.verified and result.value.activated

    state = p.get_index_state(make_state_request(p))
    assert state.ok
    assert state.value.serving_generation == "g2"
    assert state.value.applied_watermark == make_wm("s1", 1)
    assert state.value.record_count == 2


def test_rebuild_tampered_record_digest_is_not_activated():
    value = {"memory_id": "m1", "index_text": "one"}
    p = FakeVectorProvider(
        digest_keys={"k2": KEY2},
        generation_builds={
            "g2": FakeGenerationBuild(
                source_watermark=make_wm("s1", 1),
                record_values=(value,),
                record_digests=(DIG2,),
                expected_record_count=1,
            )
        },
    )
    rebuild = c.VectorRebuildRequest(
        request_id="r1", trace_id="t1", user_id="alpha", deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key="ik", payload_hash=DIG2, source_snapshot_id="snap", source_watermark=make_wm("s1", 1),
        target_generation="g2", schema_version="v1", reason=c.RebuildReason.SCHEMA_CHANGE,
        scope=make_scope("s1"), scope_authorization=make_auth(p, operations=["rebuild"]),
    )
    result = p.rebuild(sign_request_payload(rebuild, key_id="k2", key=KEY2))
    assert not result.ok and result.error.code is c.RetrievalErrorCode.CONFLICT
    assert "s1" not in p.serving


def test_rebuild_without_record_semantics_is_not_activated():
    digest = c.digest_from_canonical("k2", KEY2, {"memory_id": "m1", "index_text": "one"})
    p = FakeVectorProvider(
        digest_keys={"k2": KEY2},
        generation_builds={
            "g2": FakeGenerationBuild(
                source_watermark=make_wm("s1", 1),
                record_digests=(digest,),
                expected_record_count=1,
            )
        },
    )
    rebuild = c.VectorRebuildRequest(
        request_id="r1", trace_id="t1", user_id="alpha", deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key="ik", payload_hash=DIG2, source_snapshot_id="snap", source_watermark=make_wm("s1", 1),
        target_generation="g2", schema_version="v1", reason=c.RebuildReason.SCHEMA_CHANGE,
        scope=make_scope("s1"), scope_authorization=make_auth(p, operations=["rebuild"]),
    )
    result = p.rebuild(sign_request_payload(rebuild, key_id="k2", key=KEY2))
    assert not result.ok and result.error.code is c.RetrievalErrorCode.STALE_INDEX
    assert "s1" not in p.serving


# T042 删除确认/豁免的类型约束
def test_delete_exemption_only_single_item():
    with pytest.raises(ValidationError):
        c.ResolvedDeleteSelector(
            user_id="alpha", memory_ids=["m1", "m2"], version_ids=["v1", "v2"],
            selection_mode=c.SelectionMode.RESOLVED_BATCH, selection_hash=DIG, resolved_by=c.ResolvedBy.SYSTEM,
            preview_ref="pr", preview_hash=DIG, confirmation_mode=c.ConfirmationMode.POLICY_EXEMPT,
            confirmation_ref=None,
            exemption=c.DeleteExemption(policy_id="p", policy_version="1", decision_ref="d"),
        )


def test_delete_explicit_requires_confirmation_ref():
    with pytest.raises(ValidationError):
        c.ResolvedDeleteSelector(
            user_id="alpha", memory_ids=["m1"], version_ids=["v1"],
            selection_mode=c.SelectionMode.SINGLE_ITEM, selection_hash=DIG, resolved_by=c.ResolvedBy.SYSTEM,
            preview_ref="pr", preview_hash=DIG, confirmation_mode=c.ConfirmationMode.EXPLICIT,
            confirmation_ref=None, exemption=None,
        )
