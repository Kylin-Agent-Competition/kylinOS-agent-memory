"""V007：检索评测指标单元测试（纯函数，无 VM 依赖）。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from retrieval.evaluation import (
    ChannelMode,
    EvalConfig,
    ForgetResidualPhase,
    ForgetResidualSample,
    QueryEvalResult,
    evaluate_forget_residual,
    evaluate_queries,
    ndcg_at_k,
    percentile,
    recall_at_k,
    reciprocal_rank,
    report_to_dict,
)
from retrieval.contracts import Watermark, WatermarkDomain, WatermarkKind


def _q(rid, ranked, relevant, latency=None):
    return QueryEvalResult(
        query_id=rid,
        ranked_ids=tuple(ranked),
        relevant_ids=frozenset(relevant),
        latency_ms=latency,
    )


def test_recall_at_k_golden():
    assert recall_at_k(frozenset({"a", "c"}), ("a", "b", "c"), 3) == 1.0
    assert recall_at_k(frozenset({"a", "c"}), ("a", "b", "d"), 3) == 0.5
    assert recall_at_k(frozenset(), ("a", "b"), 3) == 1.0


def test_reciprocal_rank_golden():
    assert reciprocal_rank(frozenset({"a"}), ("a", "b", "c")) == 1.0
    assert reciprocal_rank(frozenset({"c"}), ("a", "b", "c")) == pytest.approx(1 / 3)
    assert reciprocal_rank(frozenset({"x"}), ("a", "b")) == 0.0


def test_ndcg_golden():
    # 两个正解都在前两位 = 理想排序
    assert ndcg_at_k(frozenset({"a", "b"}), ("a", "b", "c"), 3) == 1.0
    # 命中排第 1 和第 3，理想是第 1 和第 2
    got = ndcg_at_k(frozenset({"a", "b"}), ("a", "c", "b"), 3)
    assert got == pytest.approx(1.0 / (1.0 / 1.0 + 1.0 / 1.5849625007211563) * (1.0 + 1.0 / 2.0), rel=1e-9)


def test_percentile():
    assert percentile([1.0, 2.0, 3.0, 4.0], 50.0) == 2.5
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.0) == 1.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 100.0) == 4.0


def test_evaluate_queries_aggregates():
    config = EvalConfig(channel_mode=ChannelMode.RRF_V1, k=3)
    queries = [
        _q("q1", ["a", "b", "c"], {"a", "c"}, latency=10.0),
        _q("q2", ["a", "b", "c"], {"x"}, latency=20.0),
    ]
    report = evaluate_queries(queries, config)
    assert report.query_count == 2
    assert report.recall_at_k == 0.5  # (1.0 + 0.0) / 2
    assert report.mrr == pytest.approx((1.0 + 0.0) / 2)
    assert report.hit_count == 1
    assert report.p95_ms == pytest.approx(19.5)
    assert report.sample_count == 2


def test_report_to_dict():
    config = EvalConfig(channel_mode=ChannelMode.FTS5_ONLY, k=2, dataset_version="dev-1", gold_label_version="gl-1")
    report = evaluate_queries([_q("q1", ["a", "b"], {"a"})], config)
    d = report_to_dict(report)
    assert d["channel_mode"] == "fts5"
    assert d["dataset_version"] == "dev-1"
    assert d["gold_label_version"] == "gl-1"
    assert d["query_count"] == 1


def test_weighted_rrf_evaluation_records_algorithm_and_weight_configuration():
    config = EvalConfig(
        channel_mode=ChannelMode.WEIGHTED_RRF_V1,
        algorithm_version="weighted-rrf/v1",
        channel_weights={"fts5": 0.5, "vector": 2.0},
    )
    report = evaluate_queries([_q("q1", ["a"], {"a"})], config)
    data = report_to_dict(report)

    assert data["channel_mode"] == "weighted_rrf_v1"
    assert data["algorithm_version"] == "weighted-rrf/v1"
    assert data["channel_weights"] == {"fts5": 0.5, "vector": 2.0}


def test_forget_residual_rate_counts_confirmed_targets_seen_in_retrieval_results():
    """D10-B：残留率按确认目标观测值计算，并绑定重建快照与数据集版本。"""
    watermark = Watermark(
        domain=WatermarkDomain(
            scope_id="scope-alice",
            stream="forget-outbox",
            partition="alice",
            source_generation="sqlite-d10",
        ),
        kind=WatermarkKind.MONOTONIC_INT,
        value=7,
    )
    report = evaluate_forget_residual(
        [
            ForgetResidualSample("before-rebuild", ("42", "43"), ("11", "42")),
            ForgetResidualSample("after-rebuild", ("44",), ("11", "12")),
        ],
        phase=ForgetResidualPhase.REBUILD,
        dataset_version="forget-gold-v1",
        source_snapshot_id="snapshot-2",
        source_watermark=watermark,
    )

    assert report.target_observation_count == 3
    assert report.residual_target_count == 1
    assert report.residual_rate == pytest.approx(1 / 3)
    assert report.phase is ForgetResidualPhase.REBUILD
    assert report.dataset_version == "forget-gold-v1"
    assert report.source_snapshot_id == "snapshot-2"


def test_v007_eval_keeps_each_channel_algorithm_metadata_separate():
    script = Path(__file__).resolve().parents[3] / "scripts" / "v007_eval.py"
    spec = importlib.util.spec_from_file_location("v007_eval", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    raw = {
        "algorithm_version": "weighted-rrf/v1",
        "channel_weights": {"fts5": 0.5, "vector": 2.0},
    }

    assert module._config(raw, ChannelMode.FTS5_ONLY).algorithm_version == "fts5-only/v1"
    assert module._config(raw, ChannelMode.FTS5_ONLY).channel_weights == {}
    assert module._config(raw, ChannelMode.VECTOR_ONLY).algorithm_version == "vector-only/v1"
    assert module._config(raw, ChannelMode.RRF_V1).algorithm_version == "rrf-v1"
    weighted = module._config(raw, ChannelMode.WEIGHTED_RRF_V1)
    assert weighted.algorithm_version == "weighted-rrf/v1"
    assert weighted.channel_weights == {"fts5": 0.5, "vector": 2.0}
