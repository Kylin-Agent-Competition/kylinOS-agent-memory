"""L0 契约测试：rrf-v1 golden / 稳定性 / 降级。

对应 docs/day3/09：T027,T028,T029。
"""

import pytest

from retrieval.contracts import Channel
from retrieval.rrf import AggregatedCandidate, rrf_rank, rrf_score


# T027 RRF golden
@pytest.mark.parametrize(
    "ranks,expected",
    [
        ({Channel.FTS5: 1, Channel.VECTOR: 3}, 0.0322664585),
        ({Channel.FTS5: 2, Channel.VECTOR: 2}, 0.0322580645),
        ({Channel.FTS5: 1}, 0.0163934426),
        ({Channel.VECTOR: 1}, 0.0163934426),
    ],
)
def test_golden_scores(ranks, expected):
    assert rrf_score(ranks) == pytest.approx(expected, abs=1e-9)


def test_golden_ordering():
    a = AggregatedCandidate("mem-a", {Channel.FTS5: 1, Channel.VECTOR: 3})
    b = AggregatedCandidate("mem-b", {Channel.FTS5: 2, Channel.VECTOR: 2})
    c = AggregatedCandidate("mem-c", {Channel.FTS5: 1})
    d = AggregatedCandidate("mem-d", {Channel.VECTOR: 1})
    ordered = rrf_rank([d, b, c, a])
    assert [x.memory_id for x in ordered] == ["mem-a", "mem-b", "mem-c", "mem-d"]


# T028 RRF 稳定性
def test_rrf_input_order_stable():
    a = AggregatedCandidate("mem-a", {Channel.FTS5: 1, Channel.VECTOR: 3})
    b = AggregatedCandidate("mem-b", {Channel.FTS5: 2, Channel.VECTOR: 2})
    out1 = [x.memory_id for x in rrf_rank([a, b])]
    out2 = [x.memory_id for x in rrf_rank([b, a])]
    assert out1 == out2


def test_rrf_nonpositive_rank_rejected():
    with pytest.raises(ValueError):
        rrf_score({Channel.FTS5: 0})


# T029 RRF 降级
def test_fts5_only():
    assert rrf_score({Channel.FTS5: 1}) == pytest.approx(1 / 61, abs=1e-9)


def test_vector_only():
    assert rrf_score({Channel.VECTOR: 2}) == pytest.approx(1 / 62, abs=1e-9)


def test_no_channels_zero_score():
    assert rrf_score({}) == 0.0