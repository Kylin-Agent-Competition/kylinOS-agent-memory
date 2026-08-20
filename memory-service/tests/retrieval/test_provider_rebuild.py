"""L1_FAKE 契约测试：Rebuild 代次/失败保旧/水位校验。

对应 docs/day3/09：T020,T021,T022。
"""

from datetime import datetime, timedelta, timezone

from retrieval import contracts as c
from fakes import FakeGenerationBuild, FakeVectorProvider

DIG = "hmac-sha256:k1:" + "2" * 64
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
    return c.VectorRebuildRequest(
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


# T020 新代次激活；目标不得覆盖 serving
def test_rebuild_activates_new_generation():
    p = FakeVectorProvider()
    res = p.rebuild(make_rebuild(p, target="g2"))
    assert res.ok and res.value.activated is True
    assert p.serving["s1"] == "g2"


def test_rebuild_target_equals_serving_rejected():
    p = FakeVectorProvider()
    assert p.rebuild(make_rebuild(p, target="g2")).ok
    res = p.rebuild(make_rebuild(p, target="g2"))
    assert not res.ok and res.error.code is c.RetrievalErrorCode.CONFLICT


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
