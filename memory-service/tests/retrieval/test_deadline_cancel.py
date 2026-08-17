"""L1_FAKE 契约测试：deadline / 取消 / 错误映射。

对应 docs/day3/09：T030,T031,T032。
"""

from datetime import datetime, timedelta, timezone

from retrieval import contracts as c
from fakes import FakeVectorProvider

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


# T030 绝对 deadline 到期不启动新副作用
def test_deadline_expired_no_side_effect():
    p = FakeVectorProvider()
    req = make_search(p, deadline_at=p.clock.now)
    res = p.search(req)
    assert not res.ok and res.error.code is c.RetrievalErrorCode.DEADLINE_EXCEEDED
    assert p.index == {}


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