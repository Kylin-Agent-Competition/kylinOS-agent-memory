"""L1_FAKE 契约测试：Delete 单条/隔离/重放/full reset 门禁。

对应 docs/day3/09：T016,T017,T018,T019。
"""

from datetime import datetime, timedelta, timezone

from retrieval import contracts as c
from fakes import DEFAULT_DIGEST_KEY, FakeVectorProvider, sign_request_payload

DIG = "hmac-sha256:k1:" + "1" * 64
KEY1 = b"review-key-1"
KEY2 = b"review-key-2"
NOW = datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc)


def make_wm(scope_id: str, value: int) -> c.Watermark:
    return c.Watermark(
        domain=c.WatermarkDomain(scope_id=scope_id, stream="out", partition="0", source_generation="g0"),
        kind=c.WatermarkKind.MONOTONIC_INT,
        value=value,
    )


def make_record(memory_id: str, user_id: str = "alpha", version_id: str = "v1") -> c.VectorRecord:
    return c.VectorRecord(
        memory_id=memory_id, version_id=version_id, user_id=user_id, vector=[0.0] * 768,
        object_type=c.ObjectType.KNOWLEDGE, memory_type="long_term", index_text_hash=DIG,
    )


def seed(
    p: FakeVectorProvider,
    user_id: str = "alpha",
    memory_id: str = "m1",
    *,
    key: bytes = DEFAULT_DIGEST_KEY,
) -> None:
    p.upsert(
        sign_request_payload(c.VectorUpsertRequest(
            request_id="u1", trace_id="t1", user_id=user_id, deadline_at=NOW + timedelta(minutes=5),
            idempotency_key="seed", payload_hash=DIG, index_generation="g1", source_watermark=make_wm(user_id, 1),
            records=[make_record(memory_id, user_id)],
        ), key=key)
    )


def make_selector(user_id="alpha", memory_ids=None, selection_mode="single_item", confirmation_mode="explicit", confirmation_ref="cr", version_ids=None):
    memory_ids = memory_ids if memory_ids is not None else ["m1"]
    version_ids = version_ids if version_ids is not None else ["v1"]
    return c.ResolvedDeleteSelector(
        user_id=user_id,
        memory_ids=memory_ids,
        version_ids=version_ids,
        selection_mode=selection_mode,
        selection_hash=DIG,
        resolved_by=c.ResolvedBy.SYSTEM,
        preview_ref="pr",
        preview_hash=DIG,
        confirmation_mode=confirmation_mode,
        confirmation_ref=confirmation_ref,
    )


def make_delete(p, *, user_id="alpha", selector=None, idem="ik1", index_generation="g1", authorization_ref=None):
    request = c.VectorDeleteRequest(
        request_id="r1", trace_id="t1", user_id=user_id, deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key=idem, payload_hash=DIG, index_generation=index_generation,
        source_watermark=make_wm(user_id, 2), selector=selector or make_selector(user_id),
        authorization_ref=authorization_ref,
    )
    return sign_request_payload(request)


# T016 单条幂等删除；空/通配拒绝
def test_delete_single_item_idempotent():
    p = FakeVectorProvider()
    seed(p)
    first = p.delete(make_delete(p))
    assert first.ok and first.value.deleted_count == 1
    second = p.delete(make_delete(p))
    assert second.ok and second.value.deleted_count == 1  # 幂等重放返回记录结果


def test_delete_rejects_payload_hash_not_derived_from_semantics_before_effect():
    p = FakeVectorProvider(digest_keys={"k1": KEY1})
    seed(p, key=KEY1)
    effects_before = p.write_effect_count

    tampered = make_delete(p).model_copy(update={"payload_hash": DIG})
    res = p.delete(tampered)

    assert not res.ok and res.error.code is c.RetrievalErrorCode.CONFLICT
    assert p.write_effect_count == effects_before
    assert ("alpha", "m1") in p.index


def test_delete_key_rotation_replays_historical_result_without_second_effect():
    p = FakeVectorProvider(digest_keys={"k1": KEY1, "k2": KEY2})
    seed(p, key=KEY1)
    first_request = sign_request_payload(make_delete(p), key_id="k1", key=KEY1)
    replay_request = sign_request_payload(make_delete(p), key_id="k2", key=KEY2)

    first = p.delete(first_request)
    replay = p.delete(replay_request)

    assert first.ok and replay.ok and replay.value == first.value
    assert p.write_effect_count == 2  # seed + first delete only


def test_delete_wildcard_rejected():
    p = FakeVectorProvider()
    selector = make_selector(memory_ids=["*"], version_ids=["v1"])
    res = p.delete(make_delete(p, selector=selector))
    assert not res.ok and res.error.code is c.RetrievalErrorCode.INVALID_ARGUMENT


# T017 跨用户拒绝
def test_delete_cross_user_selector_rejected():
    p = FakeVectorProvider()
    res = p.delete(make_delete(p, user_id="alpha", selector=make_selector(user_id="beta")))
    assert not res.ok and res.error.code is c.RetrievalErrorCode.USER_SCOPE_VIOLATION


def test_delete_unknown_resolved_id_is_not_matched_without_service_truth_source():
    p = FakeVectorProvider()
    seed(p, user_id="beta", memory_id="m2")
    res = p.delete(make_delete(p, user_id="alpha", selector=make_selector(user_id="alpha", memory_ids=["m2"], version_ids=["v1"])))
    assert res.ok
    assert res.value.not_matched_ids == ["m2"]
    assert res.value.rejected == []
    assert ("beta", "m2") in p.index


# T018 重放与 not_matched 不掩盖越权
def test_delete_replay_not_matched_accurate():
    p = FakeVectorProvider()
    seed(p)
    first = p.delete(make_delete(p, selector=make_selector(memory_ids=["m1", "m9"], version_ids=["v1", "v9"], selection_mode="resolved_batch")))
    assert first.ok and first.value.not_matched_ids == ["m9"]
    assert first.value.deleted_count == 1


# T019 full reset 门禁
def test_full_reset_requires_authorization_and_confirmation():
    p = FakeVectorProvider()
    selector = make_selector(selection_mode="full_reset", memory_ids=["m1"], version_ids=["v1"])
    res = p.delete(make_delete(p, selector=selector, authorization_ref=None))
    assert not res.ok and res.error.code is c.RetrievalErrorCode.INVALID_ARGUMENT


def test_full_reset_ok_when_both_refs_present():
    p = FakeVectorProvider()
    selector = make_selector(selection_mode="full_reset", memory_ids=["m1"], version_ids=["v1"], confirmation_ref="cr")
    res = p.delete(make_delete(p, selector=selector, authorization_ref="ar"))
    assert res.ok
