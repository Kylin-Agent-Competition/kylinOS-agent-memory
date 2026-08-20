"""L1_FAKE 契约测试：deadline / 取消 / 错误映射。

对应 docs/day3/09：T030,T031,T032。
"""

from datetime import datetime, timedelta, timezone

from retrieval import contracts as c
from fakes import FakeVectorProvider, sign_request_payload

DIG = "hmac-sha256:k1:" + "3" * 64
NOW = datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc)


def make_filter(user_id="alpha") -> c.RetrievalFilter:
    return c.RetrievalFilter(
        user_id=user_id,
        scene=c.SceneFilter(allowed_scene_ids=["s"], include_unscoped=False),
        object_types=[c.ObjectType.KNOWLEDGE],
        conflict_policy="drop_unresolved",
        as_of=NOW,
    )


def make_search(p, *, user_id="alpha", deadline_at=None):
    return c.VectorSearchRequest(
        request_id="r1",
        trace_id="t1",
        user_id=user_id,
        deadline_at=deadline_at or (p.clock.now + timedelta(minutes=5)),
        query_vector=[0.0] * 768,
        filter=make_filter(user_id),
        top_n=10,
    )


def make_wm(scope_id="alpha", value=1):
    return c.Watermark(
        domain=c.WatermarkDomain(scope_id=scope_id, stream="out", partition="0", source_generation="g0"),
        kind=c.WatermarkKind.MONOTONIC_INT,
        value=value,
    )


def make_record(memory_id="m1"):
    return c.VectorRecord(
        memory_id=memory_id,
        version_id="v1",
        user_id="alpha",
        vector=[0.0] * 768,
        object_type=c.ObjectType.KNOWLEDGE,
        index_text_hash=DIG,
    )


# T030 绝对 deadline 到期不启动新副作用
def test_deadline_expired_no_side_effect():
    p = FakeVectorProvider()
    req = make_search(p, deadline_at=p.clock.now)
    res = p.search(req)
    assert not res.ok and res.error.code is c.RetrievalErrorCode.DEADLINE_EXCEEDED
    assert p.index == {}


def test_upsert_deadline_expired_before_write_side_effect():
    p = FakeVectorProvider()
    request = c.VectorUpsertRequest(
        request_id="u1", trace_id="t1", user_id="alpha", deadline_at=p.clock.now,
        idempotency_key="ik", payload_hash=DIG, index_generation="g1",
        source_watermark=make_wm(), records=[make_record()],
    )
    result = p.upsert(request)
    assert not result.ok and result.error.code is c.RetrievalErrorCode.DEADLINE_EXCEEDED
    assert p.write_effect_count == 0 and p.index == {}


def test_delete_deadline_expired_before_write_side_effect():
    p = FakeVectorProvider()
    seed = sign_request_payload(c.VectorUpsertRequest(
        request_id="u1", trace_id="t1", user_id="alpha", deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key="seed", payload_hash=DIG, index_generation="g1",
        source_watermark=make_wm(), records=[make_record()],
    ))
    assert p.upsert(seed).ok
    effects_before = p.write_effect_count
    selector = c.ResolvedDeleteSelector(
        user_id="alpha", memory_ids=["m1"], version_ids=["v1"],
        selection_mode=c.SelectionMode.SINGLE_ITEM, selection_hash=DIG,
        resolved_by=c.ResolvedBy.SYSTEM, preview_ref="pr", preview_hash=DIG,
        confirmation_mode=c.ConfirmationMode.EXPLICIT, confirmation_ref="cr",
    )
    request = c.VectorDeleteRequest(
        request_id="d1", trace_id="t1", user_id="alpha", deadline_at=p.clock.now,
        idempotency_key="ik", payload_hash=DIG, index_generation="g1",
        source_watermark=make_wm(value=2), selector=selector,
    )
    result = p.delete(request)
    assert not result.ok and result.error.code is c.RetrievalErrorCode.DEADLINE_EXCEEDED
    assert p.write_effect_count == effects_before
    assert ("alpha", "m1") in p.index


def test_rebuild_deadline_expired_before_generation_side_effect():
    p = FakeVectorProvider()
    scope = c.IndexScope(
        scope_id="s1", kind=c.ScopeKind.USER, user_id="alpha", scope_fingerprint=DIG,
    )
    auth = c.ScopeAuthorization(
        actor_ref="a", authorization_ref="ar", scope_id="s1", allowed_operations=["rebuild"],
        expires_at=p.clock.now + timedelta(minutes=5),
    )
    request = c.VectorRebuildRequest(
        request_id="b1", trace_id="t1", user_id="alpha", deadline_at=p.clock.now,
        idempotency_key="ik", payload_hash=DIG, source_snapshot_id="snap",
        source_watermark=make_wm("s1"), target_generation="g2", schema_version="v1",
        reason=c.RebuildReason.BOOTSTRAP, scope=scope, scope_authorization=auth,
    )
    result = p.rebuild(request)
    assert not result.ok and result.error.code is c.RetrievalErrorCode.DEADLINE_EXCEEDED
    assert p.generation_states == {} and p.serving == {}


# T031 协作取消返回 cancelled，且与超时可区分
def test_cancel_returns_cancelled():
    p = FakeVectorProvider(cancel_check=lambda: True)
    res = p.search(make_search(p))
    assert not res.ok and res.error.code is c.RetrievalErrorCode.CANCELLED


def test_cancel_distinct_from_deadline():
    p = FakeVectorProvider(cancel_check=lambda: True)
    cancelled = p.search(make_search(p, deadline_at=p.clock.now + timedelta(minutes=5)))
    assert cancelled.error.code is c.RetrievalErrorCode.CANCELLED

    p2 = FakeVectorProvider()
    expired = p2.search(make_search(p2, deadline_at=p2.clock.now))
    assert expired.error.code is c.RetrievalErrorCode.DEADLINE_EXCEEDED


# T032 底层异常归一为稳定错误码，不泄漏私有异常
def test_backend_exception_maps_to_provider_unavailable():
    p = FakeVectorProvider(backend_failure=RuntimeError("sdk boom"))
    res = p.search(make_search(p))
    assert not res.ok and res.error.code is c.RetrievalErrorCode.PROVIDER_UNAVAILABLE
    assert "sdk boom" not in res.error.message
