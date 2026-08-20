"""L1_FAKE 契约测试：Search 无命中/排名/去重/隔离/回源/版本组合。

对应 docs/day3/09：T009,T010,T011,T012,T013,T035。
"""

from datetime import datetime, timedelta, timezone

from retrieval import contracts as c
from retrieval.rrf import dedupe_exact_version
from fakes import FakeVectorProvider, TruthRecord, resolve_candidates, sign_request_payload

DIG = "hmac-sha256:k1:" + "f" * 64
NOW = datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc)


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


def make_filter(user_id: str = "alpha") -> c.RetrievalFilter:
    return c.RetrievalFilter(
        user_id=user_id,
        scene=c.SceneFilter(allowed_scene_ids=["s"], include_unscoped=False),
        scope_terms={"topic": ["a"]},
        object_types=[c.ObjectType.KNOWLEDGE],
        conflict_policy="drop_unresolved",
        as_of=NOW,
    )


def make_search(provider, *, user_id="alpha", query_vector=None, top_n=10):
    return c.VectorSearchRequest(
        request_id="r1",
        trace_id="tr1",
        user_id=user_id,
        deadline_at=provider.clock.now + timedelta(minutes=5),
        query_vector=query_vector if query_vector is not None else [0.0] * 768,
        filter=make_filter(user_id),
        top_n=top_n,
    )


def make_hit(memory_id: str, version_id: str, user_id: str = "alpha", rank: int = 1) -> c.RetrievalHit:
    return c.RetrievalHit(
        memory_id=memory_id,
        version_id=version_id,
        user_id=user_id,
        channel=c.Channel.VECTOR,
        rank=rank,
        score_semantics=c.ScoreSemantics.SDK_SCORE_UNVERIFIED,
        provider="fake_vector",
        retrieved_at=NOW,
        filter_fingerprint=DIG,
    )


# T009 无命中是成功空列表
def test_search_no_hits_is_success_empty():
    p = FakeVectorProvider()
    res = p.search(make_search(p))
    assert res.ok
    assert res.value.hits == []


# T010 排名从 1 起始
def test_search_rank_starts_at_one():
    p = FakeVectorProvider()
    p.upsert(
        sign_request_payload(c.VectorUpsertRequest(
            request_id="u1", trace_id="t1", user_id="alpha", deadline_at=NOW + timedelta(minutes=5),
            idempotency_key="ik1", payload_hash=DIG, index_generation="g1", source_watermark=make_wm("alpha", 1),
            records=[make_record("m1"), make_record("m2")],
        ))
    )
    res = p.search(make_search(p))
    assert [h.rank for h in res.value.hits] == [1, 2]


# T011 精确 (memory_id, version_id) 去重，保留最佳 rank
def test_search_exact_version_dedupe_best_rank():
    hits = [make_hit("m1", "v1", rank=2), make_hit("m1", "v1", rank=1), make_hit("m1", "v2", rank=3)]
    deduped = dedupe_exact_version(hits)
    assert {(h.memory_id, h.version_id, h.rank) for h in deduped} == {("m1", "v1", 1), ("m1", "v2", 3)}


# T012 跨用户同向量诱饵丢弃
def test_search_user_isolation():
    p = FakeVectorProvider()
    p.upsert(
        sign_request_payload(c.VectorUpsertRequest(
            request_id="u1", trace_id="t1", user_id="alpha", deadline_at=NOW + timedelta(minutes=5),
            idempotency_key="ik1", payload_hash=DIG, index_generation="g1", source_watermark=make_wm("alpha", 1),
            records=[make_record("m1", "alpha")],
        ))
    )
    p.upsert(
        sign_request_payload(c.VectorUpsertRequest(
            request_id="u2", trace_id="t2", user_id="beta", deadline_at=NOW + timedelta(minutes=5),
            idempotency_key="ik1", payload_hash=DIG, index_generation="g1", source_watermark=make_wm("beta", 1),
            records=[make_record("m2", "beta")],
        ))
    )
    res = p.search(make_search(p, user_id="alpha"))
    assert [h.memory_id for h in res.value.hits] == ["m1"]


# T013 SQLite 回源：不存在/旧版本/已遗忘丢弃
def test_search_truth_resolution_drops_invalid():
    truth = {
        ("alpha", "m1"): TruthRecord("m1", "alpha", "v1", "active", c.ObjectType.KNOWLEDGE, "long_term", "ok"),
        ("alpha", "m2"): TruthRecord("m2", "alpha", "v2", "active", c.ObjectType.KNOWLEDGE, "long_term", "ok"),
        ("alpha", "m3"): TruthRecord("m3", "alpha", "v1", "forgotten", c.ObjectType.KNOWLEDGE, "long_term", "ok"),
    }
    hits = [
        make_hit("m1", "v1"),  # 当前版本保留
        make_hit("m2", "v1", rank=2),  # 旧版本丢弃
        make_hit("m3", "v1"),  # 已遗忘丢弃
        make_hit("m4", "v1"),  # 不存在丢弃
    ]
    resolved = resolve_candidates(hits, truth, "alpha")
    assert [(h.memory_id, h.version_id) for h in resolved] == [("m1", "v1")]


# T035 旧 v1 rank1 过滤后当前 v2 rank2 保留
def test_search_old_version_rank1_filtered_keeps_current_v2():
    truth = {("alpha", "m1"): TruthRecord("m1", "alpha", "v2", "active", c.ObjectType.KNOWLEDGE, "long_term", "ok")}
    hits = [make_hit("m1", "v1", rank=1), make_hit("m1", "v2", rank=2)]
    resolved = resolve_candidates(hits, truth, "alpha")
    assert [(h.memory_id, h.version_id, h.rank) for h in resolved] == [("m1", "v2", 2)]
