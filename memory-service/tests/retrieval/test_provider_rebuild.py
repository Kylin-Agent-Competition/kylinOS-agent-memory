"""L1_FAKE 契约测试：Rebuild 代次/失败保旧/水位校验。

对应 docs/day3/09：T020,T021,T022。
"""

from datetime import datetime, timedelta, timezone

from retrieval import contracts as c
from fakes import FakeGenerationBuild, FakeVectorProvider, sign_request_payload

DIG = "hmac-sha256:k1:" + "2" * 64
KEY1 = b"review-key-1"
NOW = datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc)


def make_wm(scope_id: str, value: int) -> c.Watermark:
    return c.Watermark(
        domain=c.WatermarkDomain(scope_id=scope_id, stream="out", partition="0", source_generation="g0"),
        kind=c.WatermarkKind.MONOTONIC_INT,
        value=value,
    )


def make_scope(scope_id="s1", kind="user", user_id="alpha") -> c.IndexScope:
    return c.IndexScope(
        scope_id=scope_id,
        kind=c.ScopeKind(kind),
        user_id=user_id if kind == "user" else None,
        shard_id=None,
        scope_fingerprint=DIG,
    )


def make_auth(p, scope_id="s1", operations=("rebuild",)):
    return c.ScopeAuthorization(
        actor_ref="actor",
        authorization_ref="ar",
        scope_id=scope_id,
        allowed_operations=list(operations),
        expires_at=p.clock.now + timedelta(minutes=5),
    )


def make_rebuild(p, *, target="g2", scope_id="s1", scope=None, auth=None, reason="bootstrap"):
    scope = scope or make_scope(scope_id)
    auth = auth or make_auth(p, scope_id)
    request = c.VectorRebuildRequest(
        request_id="r1",
        trace_id="t1",
        user_id="alpha",
        deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key="ik",
        payload_hash=DIG,
        source_snapshot_id="snap1",
        source_watermark=make_wm(scope_id, 1),
        target_generation=target,
        schema_version="v1",
        reason=c.RebuildReason(reason),
        scope=scope,
        scope_authorization=auth,
    )
    return sign_request_payload(request)


def sign_request(request: c.VectorRebuildRequest, *, key_id: str = "k1", key: bytes = KEY1):
    return sign_request_payload(request, key_id=key_id, key=key)


# T020 新代次激活；目标不得覆盖 serving
def test_rebuild_activates_new_generation():
    p = FakeVectorProvider()
    res = p.rebuild(make_rebuild(p, target="g2"))
    assert res.ok and res.value.activated is True
    assert p.serving["s1"] == "g2"


def test_rebuild_exact_replay_returns_first_result_without_second_effect():
    p = FakeVectorProvider()
    first = p.rebuild(make_rebuild(p, target="g2"))
    second = p.rebuild(make_rebuild(p, target="g2"))

    assert first.ok and second.ok
    assert second.value == first.value
    assert p.rebuild_effect_count == 1


def test_rebuild_outcome_unknown_replays_first_result_without_second_effect():
    p = FakeVectorProvider(backend_failure=RuntimeError("sdk disconnected"))
    first = p.rebuild(make_rebuild(p, target="g2"))
    second = p.rebuild(make_rebuild(p, target="g2"))

    assert first.ok and second.ok
    assert first.value.outcome == "outcome_unknown"
    assert second.value == first.value
    assert p.rebuild_effect_count == 1


def test_rebuild_rejects_payload_hash_not_derived_from_semantics_before_effect():
    p = FakeVectorProvider(digest_keys={"k1": KEY1})

    res = p.rebuild(make_rebuild(p, target="g2"))

    assert not res.ok and res.error.code is c.RetrievalErrorCode.CONFLICT
    assert p.rebuild_effect_count == 0
    assert p.generation_states == {} and p.serving == {}


def test_rebuild_same_domain_different_semantics_conflicts_without_second_effect():
    p = FakeVectorProvider(digest_keys={"k1": KEY1})
    first = sign_request(make_rebuild(p, target="g2", reason="bootstrap"))
    changed = sign_request(make_rebuild(p, target="g2", reason="repair"))

    assert p.rebuild(first).ok
    res = p.rebuild(changed)

    assert not res.ok and res.error.code is c.RetrievalErrorCode.CONFLICT
    assert p.rebuild_effect_count == 1


def test_rebuild_same_bare_key_is_independent_across_target_generations():
    p = FakeVectorProvider(digest_keys={"k1": KEY1})
    first = sign_request(make_rebuild(p, target="g2"))
    next_generation = sign_request(make_rebuild(p, target="g3"))

    assert p.rebuild(first).ok
    assert p.rebuild(next_generation).ok
    assert p.rebuild_effect_count == 2
    assert p.serving["s1"] == "g3"


def test_rebuild_same_bare_key_is_independent_across_scopes():
    p = FakeVectorProvider(digest_keys={"k1": KEY1})
    scope_one = sign_request(make_rebuild(p, scope_id="s1", target="g2"))
    scope_two = sign_request(make_rebuild(p, scope_id="s2", target="g2"))

    assert p.rebuild(scope_one).ok
    assert p.rebuild(scope_two).ok
    assert p.rebuild_effect_count == 2
    assert p.serving == {"s1": "g2", "s2": "g2"}


# T021 构建失败保留旧 serving generation
def test_rebuild_failure_keeps_old_generation():
    p = FakeVectorProvider()
    assert p.rebuild(make_rebuild(p, target="g1")).ok
    p.backend_failure = RuntimeError("build failed")
    res = p.rebuild(make_rebuild(p, target="g2"))
    assert res.ok and res.value.verified is False and res.value.activated is False
    assert p.serving["s1"] == "g1"


# T022 水位/计数不符不激活
def test_rebuild_watermark_mismatch_not_activated():
    p = FakeVectorProvider(
        generation_builds={
            "g2": FakeGenerationBuild(
                source_watermark=make_wm("s1", 2),
                record_digests=(DIG,),
                expected_record_count=1,
            )
        }
    )
    res = p.rebuild(make_rebuild(p, target="g2"))
    assert not res.ok and res.error.code is c.RetrievalErrorCode.STALE_INDEX
    assert "s1" not in p.serving


def test_rebuild_record_count_mismatch_not_activated():
    p = FakeVectorProvider(
        generation_builds={
            "g2": FakeGenerationBuild(
                source_watermark=make_wm("s1", 1),
                record_digests=(DIG,),
                expected_record_count=2,
            )
        }
    )
    res = p.rebuild(make_rebuild(p, target="g2"))
    assert not res.ok and res.error.code is c.RetrievalErrorCode.STALE_INDEX
    assert "s1" not in p.serving
