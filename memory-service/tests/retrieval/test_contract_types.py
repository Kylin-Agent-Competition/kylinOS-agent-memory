"""L0 契约测试：类型/字段/向量/filter/score/object-type/log-safety/兼容性。

对应 docs/day3/09：T001,T002,T003,T004,T014,T015,T033,T034。
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from retrieval import contracts as c
from retrieval import validation as v

T = datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc)
DIG = "hmac-sha256:k1:" + "a" * 64


def make_filter(**overrides):
    data = dict(
        user_id="alpha",
        scene=c.SceneFilter(allowed_scene_ids=["scene1"], include_unscoped=False),
        scope_terms={"topic": ["a"]},
        object_types=[c.ObjectType.KNOWLEDGE],
        memory_types=["long_term"],
        allowed_memory_statuses=["active"],
        allowed_sensitivity=["normal"],
        conflict_policy="drop_unresolved",
        as_of=T,
    )
    data.update(overrides)
    return c.RetrievalFilter(**data)


def make_search_request(**overrides):
    data = dict(
        request_id="r1",
        trace_id="tr1",
        user_id="alpha",
        deadline_at=T,
        query_vector=[0.0] * 768,
        filter=make_filter(),
        top_n=10,
    )
    data.update(overrides)
    return c.VectorSearchRequest(**data)


def make_hit(**overrides):
    data = dict(
        memory_id="m1",
        version_id="v1",
        user_id="alpha",
        channel=c.Channel.VECTOR,
        rank=1,
        raw_score=0.5,
        score_semantics=c.ScoreSemantics.SDK_SCORE_UNVERIFIED,
        provider="fake",
        retrieved_at=T,
        filter_fingerprint=DIG,
    )
    data.update(overrides)
    return c.RetrievalHit(**data)


# T001 契约版本
def test_contract_version_defaults_v1():
    assert make_search_request().contract_version == "vector-retrieval/v1"


def test_unknown_contract_version_rejected():
    with pytest.raises(ValidationError):
        make_search_request(contract_version="vector-retrieval/v2")


# T002 公共字段
def test_complete_public_fields_ok():
    req = make_search_request()
    assert req.request_id and req.trace_id and req.user_id and req.deadline_at


@pytest.mark.parametrize("missing", ["request_id", "trace_id", "user_id", "deadline_at"])
def test_missing_public_field_rejected(missing):
    data = dict(
        request_id="r1",
        trace_id="tr1",
        user_id="alpha",
        deadline_at=T,
        query_vector=[0.0] * 768,
        filter=make_filter(),
        top_n=10,
    )
    del data[missing]
    with pytest.raises(ValidationError):
        c.VectorSearchRequest(**data)


# T003 向量校验
def test_vector_dimension_ok():
    assert len(v.validate_vector([0.0] * 768, 768)) == 768


def test_vector_dimension_mismatch_rejected():
    with pytest.raises(ValueError) as exc:
        v.validate_vector([0.0] * 3, 768)
    assert "dimension_mismatch" in str(exc.value)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_vector_nonfinite_rejected(bad):
    with pytest.raises(ValueError):
        v.validate_vector([0.0] * 767 + [bad], 768)


# T004 typed filter
def test_filter_allowed_keys_ok():
    flt = make_filter(scope_terms={"topic": ["a"]})
    assert v.validate_retrieval_filter(flt, frozenset({"topic"})) is flt


def test_filter_unknown_key_rejected():
    flt = make_filter(scope_terms={"unknown": ["x"]})
    with pytest.raises(ValueError):
        v.validate_retrieval_filter(flt, frozenset({"topic"}))


def test_filter_wildcard_user_rejected():
    flt = make_filter(user_id="all")
    with pytest.raises(ValueError):
        v.validate_retrieval_filter(flt, frozenset({"topic"}))


def test_filter_too_many_terms_rejected():
    flt = make_filter(scope_terms={"topic": ["x"] * 33})
    with pytest.raises(ValueError):
        v.validate_retrieval_filter(flt, frozenset({"topic"}), max_scope_terms_length=32)


# T014 raw score
def test_raw_score_finite_ok():
    assert make_hit(raw_score=0.5).raw_score == 0.5


def test_raw_score_nan_rejected():
    with pytest.raises(ValidationError):
        make_hit(raw_score=float("nan"))


def test_validate_finite_score_rejects_nonfinite():
    with pytest.raises(ValueError):
        v.validate_finite_score(float("inf"))


# T015 object/memory 类型
def test_object_memory_independent_ok():
    assert v.validate_object_memory_type(c.ObjectType.KNOWLEDGE, "long_term") == "long_term"


def test_memory_type_knowledge_rejected():
    with pytest.raises(ValueError):
        v.validate_object_memory_type(c.ObjectType.KNOWLEDGE, "knowledge")


# T033 日志安全
def test_log_safe_details():
    assert v.is_log_safe({"memory_id": "m1", "rank": 1, "count": 2, "elapsed_ms": 3, "hash": "x"})


def test_log_content_rejected():
    assert not v.is_log_safe({"content": "hello"})


def test_log_credential_rejected():
    assert not v.is_log_safe({"password": "secret"})


# T034 兼容性
def test_optional_fields_compatible():
    assert make_hit(raw_score=None, index_generation=None).raw_score is None


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        c.RetrievalHit(
            memory_id="m",
            version_id="v",
            user_id="u",
            channel=c.Channel.VECTOR,
            rank=1,
            score_semantics=c.ScoreSemantics.SDK_SCORE_UNVERIFIED,
            provider="p",
            retrieved_at=T,
            filter_fingerprint=DIG,
            bogus_field=1,
        )


def test_semantic_change_rejected():
    with pytest.raises(ValidationError):
        make_hit(rank="1")