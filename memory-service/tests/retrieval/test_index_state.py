"""L0 契约测试：激活能力与 IndexState 不变量。

对应 docs/day3/09：T023,T024,T025,T041。
"""

from datetime import datetime, timezone

import pytest

from retrieval import contracts as c
from retrieval import validation as v
from fakes import FakeGenerationBuild, FakeVectorProvider

T = datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc)
DIG = "hmac-sha256:k1:" + "b" * 64


def make_scope(scope_id="s1", *, kind=c.ScopeKind.USER, user_id="alpha", shard_id=None, fingerprint=DIG):
    return c.IndexScope(
        scope_id=scope_id,
        kind=kind,
        user_id=user_id if kind is c.ScopeKind.USER else None,
        shard_id=shard_id if kind is c.ScopeKind.SHARD else None,
        scope_fingerprint=fingerprint,
    )


def make_wm(value: int, scope_id="s1"):
    return c.Watermark(
        domain=c.WatermarkDomain(scope_id=scope_id, stream="out", partition="0", source_generation="g0"),
        kind=c.WatermarkKind.MONOTONIC_INT,
        value=value,
    )


def make_auth(scope_id, operation):
    return c.ScopeAuthorization(
        actor_ref="a", authorization_ref="ar", scope_id=scope_id,
        allowed_operations=[operation], expires_at=datetime(2026, 8, 17, 11, 0, 0, tzinfo=timezone.utc),
    )


def rebuild_scope(p, scope, *, target="shared-generation", watermark_value=1):
    return p.rebuild(
        c.VectorRebuildRequest(
            request_id=f"rebuild-{scope.scope_id}", trace_id="t1",
            user_id=scope.user_id or "system", deadline_at=datetime(2026, 8, 17, 11, 0, 0, tzinfo=timezone.utc),
            idempotency_key="ik", payload_hash=DIG, source_snapshot_id=f"snap-{scope.scope_id}",
            source_watermark=make_wm(watermark_value, scope.scope_id), target_generation=target,
            schema_version="v1", reason=c.RebuildReason.BOOTSTRAP, scope=scope,
            scope_authorization=make_auth(scope.scope_id, "rebuild"),
        )
    )


def read_state(p, scope):
    return p.get_index_state(
        c.IndexStateRequest(
            request_id=f"state-{scope.scope_id}", trace_id="t1", scope=scope,
            scope_authorization=make_auth(scope.scope_id, "get_index_state"),
            deadline_at=datetime(2026, 8, 17, 11, 0, 0, tzinfo=timezone.utc),
        )
    ).value


def make_state(**overrides):
    data = dict(
        provider="fake",
        scope=make_scope(),
        status=c.IndexStatus.READY,
        is_queryable=True,
        schema_version="v1",
        serving_generation="g1",
        applied_watermark=make_wm(1),
        record_count=10,
        last_checked_at=T,
        evidence_level=c.EvidenceLevel.UNTESTED,
        availability=c.Availability.AVAILABLE,
    )
    data.update(overrides)
    return c.IndexState(**data)


def make_capabilities(**overrides):
    data = dict(
        provider="fake",
        provider_version="1",
        dimension=768,
        supports_scalar_filter=True,
        supports_delete=True,
        supports_rebuild=True,
        evidence_level=c.EvidenceLevel.UNTESTED,
        availability=c.Availability.AVAILABLE,
        availability_checked_at=T,
    )
    data.update(overrides)
    return c.VectorCapabilities(**data)


# T023 激活能力
def test_atomic_switch_default_false():
    assert make_capabilities().supports_atomic_generation_switch is False


def test_atomic_switch_requires_capability():
    with pytest.raises(ValueError):
        v.resolve_activation_mode(False, c.ActivationMode.ATOMIC_SWITCH)


def test_non_atomic_modes_ok():
    assert v.resolve_activation_mode(False, c.ActivationMode.ROUTING_SWITCH) is c.ActivationMode.ROUTING_SWITCH


# T024 IndexState ready
def test_ready_requires_serving_generation():
    with pytest.raises(ValueError):
        v.validate_index_state(make_state(serving_generation=None))


def test_ready_requires_watermark():
    with pytest.raises(ValueError):
        v.validate_index_state(make_state(applied_watermark=None))


# T025 IndexState empty
def test_empty_verified_zero_count():
    state = make_state(
        status=c.IndexStatus.EMPTY,
        serving_generation=None,
        applied_watermark=None,
        record_count=0,
        is_queryable=True,
    )
    assert v.validate_index_state(state).status is c.IndexStatus.EMPTY


def test_empty_unknown_count_rejected():
    state = make_state(
        status=c.IndexStatus.EMPTY,
        serving_generation=None,
        applied_watermark=None,
        record_count=None,
    )
    with pytest.raises(ValueError):
        v.validate_index_state(state)


# T041 证据/可用性双轴独立
def test_evidence_availability_independent():
    state = make_state(
        status=c.IndexStatus.UNAVAILABLE,
        is_queryable=False,
        serving_generation=None,
        applied_watermark=None,
        record_count=None,
        evidence_level=c.EvidenceLevel.HOST_VERIFIED,
        availability=c.Availability.UNAVAILABLE,
    )
    out = v.validate_index_state(state)
    assert out.evidence_level is c.EvidenceLevel.HOST_VERIFIED
    assert out.availability is c.Availability.UNAVAILABLE

# ── L1_FAKE：T026 状态查询只读 ──

def test_get_index_state_is_read_only():
    p = FakeVectorProvider()
    auth = c.ScopeAuthorization(
        actor_ref="a", authorization_ref="ar", scope_id="s1",
        allowed_operations=["get_index_state"], expires_at=datetime(2026, 8, 17, 11, 0, 0, tzinfo=timezone.utc),
    )
    req = c.IndexStateRequest(
        request_id="r1", trace_id="t1", scope=make_scope(),
        scope_authorization=auth, deadline_at=T,
    )
    before = p.get_index_state(req).value
    after = p.get_index_state(req).value
    assert before == after
    assert p.serving == {} and p.applied == {} and p.index == {}


# ── L1_FAKE：T036 用户级 scope 隔离 ──

def test_user_scope_isolation_in_state():
    scope_a = make_scope("user-alpha", user_id="alpha")
    scope_b = make_scope("user-beta", user_id="beta")
    p = FakeVectorProvider(
        generation_builds={
            ("user-alpha", "shared-generation"): FakeGenerationBuild(
                source_watermark=make_wm(3, "user-alpha"), record_digests=(DIG,), expected_record_count=1,
            ),
            ("user-beta", "shared-generation"): FakeGenerationBuild(
                source_watermark=make_wm(7, "user-beta"), record_digests=(DIG, DIG, DIG), expected_record_count=3,
            ),
        }
    )
    assert rebuild_scope(p, scope_a, watermark_value=3).ok
    assert rebuild_scope(p, scope_b, watermark_value=7).ok
    state_a = read_state(p, scope_a)
    state_b = read_state(p, scope_b)
    assert state_a.scope.scope_id == "user-alpha"
    assert state_a.scope.user_id == "alpha"
    assert state_a.serving_generation == state_b.serving_generation == "shared-generation"
    assert state_a.applied_watermark == make_wm(3, "user-alpha")
    assert state_b.applied_watermark == make_wm(7, "user-beta")
    assert state_a.record_count == 1
    assert state_b.record_count == 3


# ── L1_FAKE：T037 分片级 scope 独立 ──

def test_shard_scope_independent():
    scope_a = make_scope("scope-shard-a", kind=c.ScopeKind.SHARD, user_id=None, shard_id="shard-a")
    scope_b = make_scope("scope-shard-b", kind=c.ScopeKind.SHARD, user_id=None, shard_id="shard-b")
    p = FakeVectorProvider(
        generation_builds={
            ("scope-shard-a", "shared-generation"): FakeGenerationBuild(
                source_watermark=make_wm(2, "scope-shard-a"), record_digests=(DIG,), expected_record_count=1,
            ),
            ("scope-shard-b", "shared-generation"): FakeGenerationBuild(
                source_watermark=make_wm(4, "scope-shard-b"), record_digests=(DIG, DIG), expected_record_count=2,
            ),
        }
    )
    assert rebuild_scope(p, scope_a, watermark_value=2).ok
    assert rebuild_scope(p, scope_b, watermark_value=4).ok
    state_a = read_state(p, scope_a)
    state_b = read_state(p, scope_b)
    assert state_a.scope.shard_id == "shard-a"
    assert state_b.scope.shard_id == "shard-b"
    assert state_a.serving_generation == state_b.serving_generation == "shared-generation"
    assert state_a.applied_watermark == make_wm(2, "scope-shard-a")
    assert state_b.applied_watermark == make_wm(4, "scope-shard-b")
    assert state_a.record_count == 1
    assert state_b.record_count == 2
