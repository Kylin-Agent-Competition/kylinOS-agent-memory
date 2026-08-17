"""L0 契约测试：canonical-json/v1 规范摘要。

对应 docs/day3/09：T039。
"""

import pytest

from retrieval import contracts as c


def test_canonical_map_reorder_same_digest():
    assert c.canonical_json_v1({"b": 1, "a": 2}) == c.canonical_json_v1({"a": 2, "b": 1})


def test_canonical_set_array_dedupe_sorted():
    assert c.canonical_json_v1({"ids": ["b", "a", "b"]}, set_paths=("ids",)) == c.canonical_json_v1(
        {"ids": ["a", "b"]}, set_paths=("ids",)
    )


def test_canonical_ordered_array_reorder_differs():
    assert c.canonical_json_v1({"ids": ["a", "b"]}) != c.canonical_json_v1({"ids": ["b", "a"]})


def test_canonical_nfc_equivalent():
    composed = "\u00C1"  # Á
    decomposed = "A\u0301"
    assert c.canonical_json_v1({"s": composed}) == c.canonical_json_v1({"s": decomposed})


def test_canonical_rejects_nan():
    with pytest.raises(ValueError):
        c.canonical_json_v1({"x": float("nan")})

# ── L1_FAKE：T038 幂等复合域 ──

import pytest
from datetime import datetime, timedelta, timezone
from retrieval import contracts as c2
from fakes import FakeVectorProvider

DIG2 = "hmac-sha256:k1:" + "4" * 64
DIG3 = "hmac-sha256:k1:" + "5" * 64
NOW = datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc)


def make_wm(scope_id: str, value: int) -> c2.Watermark:
    return c2.Watermark(
        domain=c2.WatermarkDomain(scope_id=scope_id, stream="out", partition="0", source_generation="g0"),
        kind=c2.WatermarkKind.MONOTONIC_INT,
        value=value,
    )


def make_record(memory_id: str, user_id: str = "alpha") -> c2.VectorRecord:
    return c2.VectorRecord(
        memory_id=memory_id, version_id="v1", user_id=user_id, vector=[0.0] * 768,
        object_type=c2.ObjectType.KNOWLEDGE, memory_type="long_term", index_text_hash=DIG2,
    )


def make_upsert(p, *, user_id="alpha", idem="ik1", payload_hash=DIG2, index_generation="g1", records=None):
    return c2.VectorUpsertRequest(
        request_id="r1", trace_id="t1", user_id=user_id, deadline_at=p.clock.now + timedelta(minutes=5),
        idempotency_key=idem, payload_hash=payload_hash, index_generation=index_generation,
        source_watermark=make_wm(user_id, 1), records=records or [make_record("m1", user_id)],
    )


def test_idempotency_same_domain_replay():
    p = FakeVectorProvider()
    r1 = p.upsert(make_upsert(p))
    r2 = p.upsert(make_upsert(p))
    assert r1.value == r2.value


def test_idempotency_cross_user_same_key_independent():
    p = FakeVectorProvider()
    assert p.upsert(make_upsert(p, user_id="alpha", idem="ik")).ok
    assert p.upsert(make_upsert(p, user_id="beta", idem="ik")).ok


def test_idempotency_same_domain_different_hash_conflict():
    p = FakeVectorProvider()
    assert p.upsert(make_upsert(p, idem="ik", payload_hash=DIG2)).ok
    res = p.upsert(make_upsert(p, idem="ik", payload_hash=DIG3))
    assert not res.ok and res.error.code is c2.RetrievalErrorCode.CONFLICT


# ── L1_FAKE：T040 水位比较域 ──

def test_watermark_same_domain_progression():
    a = make_wm("s1", 1)
    b = make_wm("s1", 2)
    assert a.compare(b) == -1 and b.compare(a) == 1 and a.compare(a) == 0


def test_watermark_cross_domain_rejected():
    a = make_wm("s1", 1)
    b = c2.Watermark(
        domain=c2.WatermarkDomain(scope_id="s2", stream="out", partition="0", source_generation="g0"),
        kind=c2.WatermarkKind.MONOTONIC_INT,
        value=2,
    )
    with pytest.raises(ValueError):
        a.compare(b)

