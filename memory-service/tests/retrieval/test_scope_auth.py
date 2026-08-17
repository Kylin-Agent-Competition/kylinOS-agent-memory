"""L1_FAKE 契约测试：Scope 授权边界/过期/操作隔离/摘要轮换。

对应 docs/day3/09：T042,T043,T044,T045,T046,T047,T048。
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from retrieval import contracts as c
from fakes import FakeVectorProvider

DIG = "hmac-sha256:k1:" + "6" * 64
DIG2 = "hmac-sha256:k2:" + "7" * 64
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
    rebuild = c.VectorRebuildRequest(
        request_id="r1", trace_id="t1", user_id="alpha", deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key="ik", payload_hash=DIG, source_snapshot_id="snap", source_watermark=make_wm("s1", 1),
        target_generation="g2", schema_version="v1", reason=c.RebuildReason.BOOTSTRAP,
        scope=make_scope("s1"), scope_authorization=auth,
    )
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


# T047 key-id 改变导致同域重复副作用被识别为 conflict
def test_key_id_change_rejected_as_conflict():
    p = FakeVectorProvider()
    rec = c.VectorRecord(memory_id="m1", version_id="v1", user_id="alpha", vector=[0.0] * 768, object_type=c.ObjectType.KNOWLEDGE, memory_type="long_term", index_text_hash=DIG)
    req1 = c.VectorUpsertRequest(
        request_id="r1", trace_id="t1", user_id="alpha", deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key="ik", payload_hash=DIG, index_generation="g1", source_watermark=make_wm("alpha", 1), records=[rec],
    )
    req2 = req1.model_copy(update={"payload_hash": DIG2})
    assert p.upsert(req1).ok
    res = p.upsert(req2)
    assert not res.ok and res.error.code is c.RetrievalErrorCode.CONFLICT


# T048 未重建即激活 / 混用 key-id 失败
def test_rebuild_mixed_key_generation_rejected():
    p = FakeVectorProvider(rebuild_hook=lambda req: c.RetrievalErrorCode.DIGEST_KEY_UNAVAILABLE)
    auth = make_auth(p, operations=["rebuild"])
    rebuild = c.VectorRebuildRequest(
        request_id="r1", trace_id="t1", user_id="alpha", deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key="ik", payload_hash=DIG, source_snapshot_id="snap", source_watermark=make_wm("s1", 1),
        target_generation="g2", schema_version="v1", reason=c.RebuildReason.SCHEMA_CHANGE,
        scope=make_scope("s1"), scope_authorization=auth,
    )
    res = p.rebuild(rebuild)
    assert not res.ok and res.error.code is c.RetrievalErrorCode.DIGEST_KEY_UNAVAILABLE
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