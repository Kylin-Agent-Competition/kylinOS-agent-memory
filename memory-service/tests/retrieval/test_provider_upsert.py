"""L1_FAKE 契约测试：Upsert 幂等/水位/隔离/部分失败。

对应 docs/day3/09：T005,T006,T007,T008。
"""

from datetime import timedelta

from retrieval import contracts as c
from fakes import FakeVectorProvider

DIG = "hmac-sha256:k1:" + "e" * 64


def make_wm(scope_id: str, value: int) -> c.Watermark:
    return c.Watermark(
        domain=c.WatermarkDomain(scope_id=scope_id, stream="out", partition="0", source_generation="g0"),
        kind=c.WatermarkKind.MONOTONIC_INT,
        value=value,
    )


def make_record(memory_id: str, user_id: str = "alpha", version_id: str = "v1") -> c.VectorRecord:
    return c.VectorRecord(
        memory_id=memory_id,
        version_id=version_id,
        user_id=user_id,
        vector=[0.0] * 768,
        object_type=c.ObjectType.KNOWLEDGE,
        memory_type="long_term",
        index_text_hash=DIG,
    )


def make_upsert(provider, *, user_id="alpha", idem="ik1", records=None, index_generation="g1", watermark=None):
    records = records if records is not None else [make_record("m1", user_id)]
    return c.VectorUpsertRequest(
        request_id="r1",
        trace_id="tr1",
        user_id=user_id,
        deadline_at=provider.clock.now + timedelta(minutes=5),
        idempotency_key=idem,
        payload_hash=DIG,
        index_generation=index_generation,
        source_watermark=watermark or make_wm(user_id, 1),
        records=records,
    )


def test_upsert_idempotent_replay_same_result():
    p = FakeVectorProvider()
    first = p.upsert(make_upsert(p))
    assert first.ok and first.value.upserted_count == 1
    assert len(p.index) == 1

    second = p.upsert(make_upsert(p))
    assert second.ok
    assert second.value.upserted_count == 1
    assert len(p.index) == 1


def test_upsert_watermark_stale_rejected():
    p = FakeVectorProvider()
    assert p.upsert(make_upsert(p, watermark=make_wm("alpha", 2))).ok
    stale = p.upsert(make_upsert(p, idem="ik2", watermark=make_wm("alpha", 1)))
    assert not stale.ok and stale.error.code is c.RetrievalErrorCode.STALE_INDEX

    newer = p.upsert(make_upsert(p, idem="ik3", watermark=make_wm("alpha", 3)))
    assert newer.ok


def test_upsert_batch_cross_user_partial():
    p = FakeVectorProvider()
    records = [make_record("m1", "alpha"), make_record("m2", "beta")]
    res = p.upsert(make_upsert(p, records=records))
    assert res.ok and res.value.outcome is c.Outcome.PARTIAL
    assert res.value.accepted_count == 1
    assert [r.memory_id for r in res.value.rejected] == ["m2"]
    assert ("alpha", "m1") in p.index
    assert ("beta", "m2") not in p.index


def test_upsert_batch_all_same_user_applied():
    p = FakeVectorProvider()
    records = [make_record("m1", "alpha"), make_record("m2", "alpha")]
    res = p.upsert(make_upsert(p, records=records))
    assert res.ok and res.value.outcome is c.Outcome.APPLIED
    assert res.value.accepted_count == 2
    assert res.value.rejected == []