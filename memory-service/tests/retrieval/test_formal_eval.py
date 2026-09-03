"""D13B 正式检索评测账本 L0/L1 测试（纯数据，无 VM 依赖）。

覆盖 PR #123 三轮 Review：
- 首轮（R1–R6）：positive-answerable 分母、corpus 严格校验、护栏全局唯一计数、
  NO_VALID_QUERIES、按通道延迟、provenance 强校验、Top-K 唯一/长度。
- 第二轮（N1–N3）：采样参数显式 provenance；有结果必须带 latency；latency 有限性。
"""

from __future__ import annotations

import math

import pytest

from domain.enums import MemoryStatus
from pipeline.schemas import SensitivityLevel

import retrieval.formal_eval as formal_eval_module
from retrieval.formal_eval import (
    CRITICAL_ZERO_CATEGORIES,
    FROZEN_CONFIG_VERSION,
    FROZEN_K,
    CorpusIndex,
    CorpusRow,
    EvalBundleConfig,
    QueryRecord,
    compute_official_report,
    guardrail_accounting,
    serialize_ref,
)

COMMIT = "a" * 40
DS_SHA = "d" * 64
GOLD_SHA = "e" * 64

CONFIG = {
    "config_version": FROZEN_CONFIG_VERSION,
    "dataset_version": "d9-dataset-v2-test",
    "gold_label_version": "d9-gold-v2-test",
    "implementation_commit": COMMIT,
    "environment": "unit-test",
    "evidence_reference": "unittest/formal-eval",
    "dataset_sha256": DS_SHA,
    "gold_sha256": GOLD_SHA,
    "statistics_method": "p50_and_p95",
    "warmup_count": 0,
    "repeat_count": 1,
    "concurrency": 1,
}


def _row(user, memory, status="active", sensitivity="none",
         conflict="none", is_current=True, version="v1"):
    return {
        "user_id": user,
        "memory_id": memory,
        "version_id": version,
        "memory_status": status,
        "sensitivity": sensitivity,
        "conflict_state": conflict,
        "is_current": is_current,
    }


def _ref(memory, version="v1"):
    return {"memory_id": memory, "version_id": version}


def _corpus_records():
    return [
        _row("u1", "m1"),                          # positive
        _row("u1", "m2", sensitivity="low"),       # positive
        _row("u1", "m3", status="removed"),        # removed_or_forgotten
        _row("u2", "m4"),                          # cross_user for u1
        _row("u1", "m5", status="expired"),        # expired
        _row("u1", "m6", sensitivity="high"),      # sensitive_recall_prohibited
        _row("u1", "m7", status="candidate"),      # candidate
        _row("u1", "m8", conflict="unresolved"),   # unresolved_conflict
        _row("u1", "m9", status="superseded", is_current=False),  # superseded
        _row("u1", "m10", status="deprecated"),    # deprecated
        _row("u1", "m11", is_current=False),       # stale active / not current
    ]


def _queries():
    return [
        {
            "query_id": "q1",
            "user_id": "u1",
            "relevant_refs": [_ref("m1"), _ref("m2")],
            "forbidden_refs": [],
            "results": {"rrf_v1": [_ref("m1"), _ref("m2")], "fts5": [_ref("m1")]},
            "latency_ms": {"rrf_v1": 10.0, "fts5": 5.0},
        },
        {
            "query_id": "q2",
            "user_id": "u1",
            "relevant_refs": [_ref("m3")],  # removed → guardrail exclusion
            "forbidden_refs": [],
            "results": {},
        },
        {
            "query_id": "q3",
            "user_id": "u1",
            "relevant_refs": [],
            "forbidden_refs": [],
            "results": {"rrf_v1": []},
            "latency_ms": {"rrf_v1": 0.0},
        },
        {
            "query_id": "q4",
            "user_id": "u1",
            "relevant_refs": [],
            "forbidden_refs": [_ref("m4")],  # cross_user
            "results": {"rrf_v1": [_ref("m1")]},
            "latency_ms": {"rrf_v1": 1.0},
        },
        {
            "query_id": "q5",
            "user_id": "u1",
            "relevant_refs": [_ref("m1")],
            "forbidden_refs": [_ref("m6")],  # sensitive
            "results": {"rrf_v1": [_ref("m1"), _ref("m6")]},
            "latency_ms": {"rrf_v1": 20.0},
        },
        {
            "query_id": "q6",
            "user_id": "u1",
            "relevant_refs": [_ref("m1")],
            "forbidden_refs": [],
            "results": {"rrf_v1": [_ref("m4")]},  # 返回跨用户 → violation
            "latency_ms": {"rrf_v1": 30.0},
        },
        {
            "query_id": "q7",
            "user_id": "u1",
            "relevant_refs": [_ref("m1")],
            "forbidden_refs": [],
            "results": {"rrf_v1": [_ref("m4"), _ref("m6")]},  # 同时两类 violation
            "latency_ms": {"rrf_v1": 40.0},
        },
        {
            "query_id": "q11",
            "user_id": "u1",
            "relevant_refs": [_ref("m11")],  # stale active/current=false
            "forbidden_refs": [],
            "results": {},
        },
        {
            "query_id": "q12",
            "user_id": "u1",
            "relevant_refs": [_ref("m1"), _ref("m11")],
            "forbidden_refs": [],
            "results": {},
        },
    ]


# ── 基础：serialize_ref / CorpusRow ──────────────────────────────


def test_serialize_ref_requires_nonempty_keys():
    assert serialize_ref({"memory_id": "m1", "version_id": "v2"}) == "m1::v2"
    with pytest.raises(ValueError):
        serialize_ref({"memory_id": "", "version_id": "v1"})
    with pytest.raises(ValueError):
        serialize_ref({"memory_id": "m1"})


def test_positive_answerable_matrix():
    assert CorpusRow("u1", "m1", "v1", "active", "none", "none", True).positive_answerable()
    assert not CorpusRow("u1", "m1", "v1", "active", "high", "none", True).positive_answerable()
    assert not CorpusRow("u1", "m1", "v1", "removed", "none", "none", True).positive_answerable()
    assert not CorpusRow("u1", "m1", "v1", "active", "none", "unresolved", True).positive_answerable()
    assert not CorpusRow("u1", "m1", "v1", "active", "none", "none", False).positive_answerable()


def test_guardrail_category_and_boundary_matrix():
    def cat(status="active", sensitivity="none", conflict="none", user="u1", query_user="u1"):
        return CorpusRow(user, "m", "v1", status, sensitivity, conflict, True).guardrail_category(query_user)

    assert cat() is None
    assert cat(user="u2", query_user="u1") == "cross_user"
    assert cat(sensitivity="high") == "sensitive_recall_prohibited"
    assert cat(sensitivity="critical") == "sensitive_recall_prohibited"
    assert cat(status="removed") == "removed_or_forgotten"
    assert cat(status="expired") == "expired"
    assert cat(status="superseded") == "superseded"
    assert cat(status="deprecated") == "deprecated"
    assert cat(status="candidate") == "candidate"
    assert cat(conflict="unresolved") == "unresolved_conflict"
    stale = CorpusRow("u1", "m", "v1", "active", "none", "none", False)
    assert stale.guardrail_category("u1") is None
    assert stale.boundary_reason() == "not_current_version"
    positive = CorpusRow("u1", "m", "v1", "active", "none", "none", True)
    assert positive.boundary_reason() is None
    removed = CorpusRow("u1", "m", "v1", "removed", "none", "none", True)
    assert removed.boundary_reason() is None  # guardrail 已覆盖


# ── corpus 严格校验（R1） ─────────────────────────────────────────


def test_corpus_index_strict_validation():
    missing_is_current = {
        "user_id": "u1", "memory_id": "m1", "version_id": "v1",
        "memory_status": "active", "sensitivity": "none", "conflict_state": "none",
    }
    with pytest.raises(ValueError, match="缺少字段"):
        CorpusIndex.from_records([missing_is_current])
    with pytest.raises(ValueError, match="sensitivity"):
        CorpusIndex.from_records([_row("u1", "m1", sensitivity="unknown")])
    with pytest.raises(ValueError, match="memory_status"):
        CorpusIndex.from_records([_row("u1", "m1", status="bogus")])
    with pytest.raises(ValueError, match="conflict_state"):
        CorpusIndex.from_records([_row("u1", "m1", conflict="bogus")])
    with pytest.raises(ValueError, match="is_current"):
        CorpusIndex.from_records([_row("u1", "m1", is_current="false")])
    with pytest.raises(ValueError, match="重复判定键"):
        CorpusIndex.from_records([_row("u1", "m1"), _row("u1", "m1")])
    with pytest.raises(ValueError):
        CorpusIndex.from_records([_row("u1", "m1")]).resolve(_ref("ghost"))


# ── config fail-closed（R5 / N1） ─────────────────────────────────


def test_config_valid_binds_all_provenance():
    cfg = EvalBundleConfig.from_mapping(CONFIG)
    assert cfg.statistics_method == "p50_and_p95"
    assert cfg.warmup_count == 0
    assert cfg.repeat_count == 1
    assert cfg.concurrency == 1


def test_config_rejects_wrong_or_missing_binding():
    with pytest.raises(ValueError, match="config_version"):
        EvalBundleConfig.from_mapping({})
    bad = dict(CONFIG, config_version="d9-retrieval-eval-config/v2")
    with pytest.raises(ValueError, match="config_version"):
        EvalBundleConfig.from_mapping(bad)
    missing_env = {k: v for k, v in CONFIG.items() if k != "environment"}
    with pytest.raises(ValueError, match="environment"):
        EvalBundleConfig.from_mapping(missing_env)
    unknown_ds = dict(CONFIG, dataset_version="UNKNOWN")
    with pytest.raises(ValueError, match="dataset_version"):
        EvalBundleConfig.from_mapping(unknown_ds)


def test_config_rejects_incomplete_provenance():
    no_evidence = {k: v for k, v in CONFIG.items() if k != "evidence_reference"}
    with pytest.raises(ValueError, match="evidence_reference"):
        EvalBundleConfig.from_mapping(no_evidence)
    no_ds_sha = dict(CONFIG, dataset_sha256="")
    with pytest.raises(ValueError, match="dataset_sha256"):
        EvalBundleConfig.from_mapping(no_ds_sha)
    bad_commit = dict(CONFIG, implementation_commit="not-a-commit")
    with pytest.raises(ValueError, match="implementation_commit"):
        EvalBundleConfig.from_mapping(bad_commit)


def test_config_sampling_parameters_must_be_explicit_and_valid():
    missing = {k: v for k, v in CONFIG.items() if k != "statistics_method"}
    with pytest.raises(ValueError, match="statistics_method"):
        EvalBundleConfig.from_mapping(missing)
    with pytest.raises(ValueError, match="statistics_method"):
        EvalBundleConfig.from_mapping(dict(CONFIG, statistics_method="UNKNOWN"))
    with pytest.raises(ValueError, match="statistics_method"):
        EvalBundleConfig.from_mapping(dict(CONFIG, statistics_method="PENDING"))
    with pytest.raises(ValueError, match="statistics_method"):
        EvalBundleConfig.from_mapping(dict(CONFIG, statistics_method="bogus"))
    with pytest.raises(ValueError, match="warmup_count"):
        EvalBundleConfig.from_mapping({k: v for k, v in CONFIG.items() if k != "warmup_count"})
    with pytest.raises(ValueError, match="warmup_count"):
        EvalBundleConfig.from_mapping(dict(CONFIG, warmup_count=-1))
    with pytest.raises(ValueError, match="warmup_count"):
        EvalBundleConfig.from_mapping(dict(CONFIG, warmup_count=True))
    with pytest.raises(ValueError, match="repeat_count"):
        EvalBundleConfig.from_mapping(dict(CONFIG, repeat_count=0))
    with pytest.raises(ValueError, match="repeat_count"):
        EvalBundleConfig.from_mapping(dict(CONFIG, repeat_count=1.5))
    with pytest.raises(ValueError, match="concurrency"):
        EvalBundleConfig.from_mapping(dict(CONFIG, concurrency=0))
    with pytest.raises(ValueError, match="concurrency"):
        EvalBundleConfig.from_mapping({k: v for k, v in CONFIG.items() if k != "concurrency"})


def test_config_rejects_non_frozen_parameters():
    with pytest.raises(ValueError, match="k"):
        EvalBundleConfig.from_mapping(dict(CONFIG, k=5))
    with pytest.raises(ValueError, match="top_k"):
        EvalBundleConfig.from_mapping(dict(CONFIG, top_k=5))
    with pytest.raises(ValueError, match="rrf_k"):
        EvalBundleConfig.from_mapping(dict(CONFIG, rrf_k=30))


# ── QueryRecord 解析（R4/R6/N2/N3） ───────────────────────────────


def test_query_record_rejects_unsupported_channel():
    with pytest.raises(ValueError, match="通道"):
        QueryRecord.from_mapping(
            {"query_id": "q", "user_id": "u", "results": {"weighted_rrf_v1": []}}
        )


def test_query_record_requires_per_channel_latency_when_results_present():
    with pytest.raises(ValueError, match="latency_ms"):
        QueryRecord.from_mapping({"query_id": "q", "user_id": "u", "latency_ms": 12.0})
    missing_latency = {
        "query_id": "q",
        "user_id": "u",
        "results": {"rrf_v1": [_ref("m1")]},
    }
    with pytest.raises(ValueError, match="缺少 latency_ms.rrf_v1"):
        QueryRecord.from_mapping(missing_latency)
    empty_without_latency = {
        "query_id": "q",
        "user_id": "u",
        "results": {"rrf_v1": []},
    }
    with pytest.raises(ValueError, match="缺少 latency_ms.rrf_v1"):
        QueryRecord.from_mapping(empty_without_latency)


def test_query_record_rejects_non_finite_latency():
    for bad in (float("nan"), float("inf"), float("-inf"), True, "12"):
        with pytest.raises(ValueError, match="latency_ms.rrf_v1"):
            QueryRecord.from_mapping(
                {"query_id": "q", "user_id": "u", "latency_ms": {"rrf_v1": bad}}
            )


def test_query_record_rejects_duplicate_or_oversized_results():
    duplicate = {
        "query_id": "q",
        "user_id": "u",
        "results": {"rrf_v1": [_ref("m1"), _ref("m1")]},
        "latency_ms": {"rrf_v1": 1.0},
    }
    with pytest.raises(ValueError, match="重复"):
        QueryRecord.from_mapping(duplicate)
    oversized = {
        "query_id": "q",
        "user_id": "u",
        "results": {"rrf_v1": [_ref(f"m{i}") for i in range(11)]},
        "latency_ms": {"rrf_v1": 1.0},
    }
    with pytest.raises(ValueError, match="超过冻结 top_k"):
        QueryRecord.from_mapping(oversized)


def test_query_record_rejects_malformed_ref_and_missing_id():
    with pytest.raises(ValueError, match="query_id"):
        QueryRecord.from_mapping({"user_id": "u"})
    extra_key = {
        "query_id": "q",
        "user_id": "u",
        "relevant_refs": [{"memory_id": "m1", "version_id": "v1", "extra": 1}],
    }
    with pytest.raises(ValueError, match="只能包含"):
        QueryRecord.from_mapping(extra_key)


# ── 端到端报告 ───────────────────────────────────────────────────


def _compute():
    return compute_official_report(
        _corpus_records(),
        _queries(),
        EvalBundleConfig.from_mapping(CONFIG),
    )


def test_official_report_accounting_includes_boundary():
    report = _compute()
    accounting = report["accounting"]
    assert accounting["total_query_count"] == 9
    assert accounting["valid_query_count"] == 4  # q1/q5/q6/q7
    assert accounting["excluded_query_count"] == 5
    assert accounting["exclusions"]["empty_gold"] == 1
    assert accounting["exclusions"]["environmental_anomaly"] == 0
    assert accounting["exclusions"]["boundary"] == {"not_current_version": 2}
    guardrail_ex = accounting["exclusions"]["negative_guardrail"]
    assert guardrail_ex["removed_or_forgotten"] == 1
    assert guardrail_ex["cross_user"] == 1


def test_official_report_rrf_metrics_hand_computed():
    report = _compute()
    rrf = report["channels"]["rrf_v1"]
    assert rrf["status"] == "COMPUTED"
    assert rrf["query_count"] == 4
    assert rrf["hit_count"] == 2
    assert rrf["recall_at_k"] == pytest.approx(0.5)
    assert rrf["mrr"] == pytest.approx(0.5)
    assert rrf["ndcg_at_k"] == pytest.approx(0.5)
    assert rrf["p50_ms"] == pytest.approx(25.0)
    assert rrf["mean_ms"] == pytest.approx(25.0)
    assert rrf["max_ms"] == pytest.approx(40.0)
    assert rrf["latency_sample_count"] == 4
    assert rrf["k_value"] == FROZEN_K


def test_official_report_per_channel_latency_distinct():
    report = _compute()
    fts5 = report["channels"]["fts5"]
    assert fts5["status"] == "INCOMPLETE_SKIPPED_QUERIES"
    assert fts5["query_count"] == 1
    assert fts5["skipped_query_count"] == 3
    assert fts5["recall_at_k"] == pytest.approx(0.5)
    assert fts5["p50_ms"] == pytest.approx(5.0)  # 与 rrf 延迟 10/20/30/40 独立
    vector = report["channels"]["vector"]
    assert vector["status"] == "NO_CHANNEL_RESULTS"
    assert vector["recall_at_k"] is None


def test_official_report_config_includes_sampling_provenance():
    report = _compute()
    cfg = report["config"]
    assert cfg["statistics_method"] == "p50_and_p95"
    assert cfg["warmup_count"] == 0
    assert cfg["repeat_count"] == 1
    assert cfg["concurrency"] == 1


def test_official_report_guardrail_global_query_count_unique_per_query():
    report = _compute()
    guardrail = report["guardrail"]
    assert guardrail["channel"] == "rrf_v1"
    assert guardrail["participating_query_count"] == 6
    assert guardrail["returned_item_count"] == 8
    # q5(敏感)、q6(cross)、q7(cross+敏感)：全局 query count 只计 3
    assert guardrail["violation_query_count"] == 3
    assert guardrail["violation_item_count"] == 4
    assert guardrail["critical_zero_ok"] is False
    cross_user = guardrail["per_category"]["cross_user"]
    assert cross_user["violation_query_count"] == 2  # q6/q7
    assert cross_user["violation_item_count"] == 2
    sensitive = guardrail["per_category"]["sensitive_recall_prohibited"]
    assert sensitive["violation_query_count"] == 2  # q5/q7
    assert sensitive["violation_item_count"] == 2
    assert cross_user["violation_query_rate"] == pytest.approx(2 / 6)
    assert cross_user["violation_item_rate"] == pytest.approx(2 / 8)
    assert set(guardrail["critical_zero_categories"]) == set(CRITICAL_ZERO_CATEGORIES)


def test_official_report_per_query_detail():
    report = _compute()
    by_id = {d["query_id"]: d for d in report["per_query_detail"]}
    assert len(by_id) == 9
    assert by_id["q1"]["metric_valid"] is True
    assert by_id["q1"]["exclusion_reason"] is None
    assert by_id["q2"]["exclusion_reason"] == "negative_guardrail:removed_or_forgotten"
    assert by_id["q3"]["exclusion_reason"] == "empty_gold"
    assert by_id["q4"]["exclusion_reason"] == "negative_guardrail:cross_user"
    assert by_id["q5"]["metric_valid"] is True
    assert by_id["q5"]["resolved_forbidden_categories"] == ["sensitive_recall_prohibited"]
    assert by_id["q11"]["exclusion_reason"] == "boundary:not_current_version"
    assert by_id["q11"]["boundary_reasons"] == ["not_current_version"]
    assert by_id["q12"]["exclusion_reason"] == "boundary:not_current_version"
    assert by_id["q12"]["metric_valid"] is False


def test_no_valid_queries_returns_null_metrics():
    corpus = _corpus_records()
    empty_gold_queries = [
        {"query_id": "e1", "user_id": "u1", "relevant_refs": [], "forbidden_refs": [], "results": {"rrf_v1": []}, "latency_ms": {"rrf_v1": 0.0}},
        {"query_id": "e2", "user_id": "u1", "relevant_refs": [], "forbidden_refs": [], "results": {}},
    ]
    report = compute_official_report(corpus, empty_gold_queries, EvalBundleConfig.from_mapping(CONFIG))
    assert report["accounting"]["valid_query_count"] == 0
    rrf = report["channels"]["rrf_v1"]
    assert rrf["status"] == "NO_VALID_QUERIES"
    assert rrf["recall_at_k"] is None
    assert rrf["mrr"] is None
    assert rrf["ndcg_at_k"] is None
    assert rrf["hit_count"] is None

    guardrail_only = [
        {"query_id": "g1", "user_id": "u1", "relevant_refs": [], "forbidden_refs": [_ref("m4")], "results": {"rrf_v1": [_ref("m1")]}, "latency_ms": {"rrf_v1": 1.0}},
    ]
    report2 = compute_official_report(corpus, guardrail_only, EvalBundleConfig.from_mapping(CONFIG))
    assert report2["accounting"]["valid_query_count"] == 0
    assert report2["channels"]["rrf_v1"]["status"] == "NO_VALID_QUERIES"
    assert report2["channels"]["rrf_v1"]["recall_at_k"] is None


def test_unknown_ref_fails_closed():
    queries = [
        {
            "query_id": "qx",
            "user_id": "u1",
            "relevant_refs": [_ref("ghost")],
            "forbidden_refs": [],
            "results": {"rrf_v1": []},
            "latency_ms": {"rrf_v1": 0.0},
        }
    ]
    with pytest.raises(ValueError, match="未在语料中解析"):
        compute_official_report(
            _corpus_records(), queries, EvalBundleConfig.from_mapping(CONFIG)
        )


def test_guardrail_accounting_no_participants_returns_none_rates():
    queries = [QueryRecord.from_mapping({"query_id": "q", "user_id": "u", "results": {}})]
    index = CorpusIndex.from_records([])
    report = guardrail_accounting(queries, index)
    assert report["participating_query_count"] == 0
    assert report["returned_item_count"] == 0
    assert report["violation_query_count"] == 0
    assert report["per_category"]["cross_user"]["violation_query_rate"] is None
    assert report["critical_zero_ok"] is True


# ── D12 字段漂移治理：评测接受的枚举必须与 Canonical 运行时枚举同源（TD-SCHEMA-B-001）──


def test_eval_memory_status_set_matches_canonical_domain_enum():
    """formal_eval 语料校验的 memory_status 值集必须等于 domain.enums.MemoryStatus 六值。"""
    assert formal_eval_module._MEMORY_STATUSES == frozenset(
        status.value for status in MemoryStatus
    )
    assert formal_eval_module._POSITIVE_MEMORY_STATUSES <= formal_eval_module._MEMORY_STATUSES


def test_eval_sensitivity_set_matches_canonical_pipeline_enum():
    """formal_eval 语料校验的 sensitivity 值集必须等于 pipeline SensitivityLevel 五级。"""
    assert formal_eval_module._SENSITIVITIES == frozenset(
        level.value for level in SensitivityLevel
    )
    assert formal_eval_module._POSITIVE_SENSITIVITIES <= formal_eval_module._SENSITIVITIES


def test_eval_conflict_state_is_eval_only_normalization_not_production_enum():
    """conflict_state 是 D9 v2 明确标注的评测归一化字段，不是生产共享枚举，禁止并入 Canonical。"""
    assert formal_eval_module._CONFLICT_STATES == frozenset(
        {"none", "resolved", "unresolved"}
    )
    assert not (formal_eval_module._CONFLICT_STATES & formal_eval_module._MEMORY_STATUSES)
