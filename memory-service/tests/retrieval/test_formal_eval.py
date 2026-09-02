"""D13B 正式检索评测账本 L0/L1 测试（纯数据，无 VM 依赖）。"""

from __future__ import annotations

import pytest

from retrieval.formal_eval import (
    CRITICAL_ZERO_CATEGORIES,
    FROZEN_CONFIG_VERSION,
    FROZEN_K,
    FROZEN_RRF_K,
    FROZEN_TOP_K,
    CorpusIndex,
    CorpusRow,
    EvalBundleConfig,
    QueryRecord,
    classify_queries,
    compute_official_report,
    guardrail_accounting,
    serialize_ref,
)

CONFIG = {
    "config_version": FROZEN_CONFIG_VERSION,
    "dataset_version": "d9-dataset-v2-test",
    "gold_label_version": "d9-gold-v2-test",
    "implementation_commit": "a" * 40,
    "environment": "unit-test",
    "evidence_reference": "unittest/formal-eval",
    "dataset_sha256": "d" * 64,
    "gold_sha256": "e" * 64,
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
    ]


def _queries():
    return [
        {
            "query_id": "q1",
            "user_id": "u1",
            "relevant_refs": [_ref("m1"), _ref("m2")],
            "forbidden_refs": [],
            "results": {"rrf_v1": [_ref("m1"), _ref("m2")], "fts5": [_ref("m1")]},
            "latency_ms": 10.0,
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
        },
        {
            "query_id": "q4",
            "user_id": "u1",
            "relevant_refs": [],
            "forbidden_refs": [_ref("m4")],  # cross_user
            "results": {"rrf_v1": [_ref("m1")]},
        },
        {
            "query_id": "q5",
            "user_id": "u1",
            "relevant_refs": [_ref("m1")],
            "forbidden_refs": [_ref("m6")],  # sensitive
            "results": {"rrf_v1": [_ref("m1"), _ref("m6")]},
            "latency_ms": 20.0,
        },
        {
            "query_id": "q6",
            "user_id": "u1",
            "relevant_refs": [_ref("m1")],
            "forbidden_refs": [],
            "results": {"rrf_v1": [_ref("m4")]},  # 返回跨用户 → violation
            "latency_ms": 30.0,
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


def test_guardrail_category_matrix():
    def cat(status="active", sensitivity="none", conflict="none", user="u1", query_user="u1"):
        row = CorpusRow(user, "m", "v1", status, sensitivity, conflict, True)
        return row.guardrail_category(query_user)

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


def test_corpus_index_rejects_unknown_and_duplicate():
    records = [_row("u1", "m1")]
    index = CorpusIndex.from_records(records)
    with pytest.raises(ValueError):
        index.resolve(_ref("ghost"))
    with pytest.raises(ValueError):
        CorpusIndex.from_records([_row("u1", "m1"), _row("u1", "m1")])


# ── config fail-closed ───────────────────────────────────────────


def test_config_valid_binds_all_provenance():
    cfg = EvalBundleConfig.from_mapping(CONFIG)
    assert cfg.config_version == FROZEN_CONFIG_VERSION
    assert cfg.dataset_version == "d9-dataset-v2-test"
    assert cfg.dataset_sha256 == "d" * 64


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


def test_config_rejects_non_frozen_parameters():
    with pytest.raises(ValueError, match="k"):
        EvalBundleConfig.from_mapping(dict(CONFIG, k=5))
    with pytest.raises(ValueError, match="top_k"):
        EvalBundleConfig.from_mapping(dict(CONFIG, top_k=5))
    with pytest.raises(ValueError, match="rrf_k"):
        EvalBundleConfig.from_mapping(dict(CONFIG, rrf_k=30))


# ── QueryRecord 解析 ─────────────────────────────────────────────


def test_query_record_rejects_unsupported_channel_and_bad_latency():
    with pytest.raises(ValueError, match="通道"):
        QueryRecord.from_mapping(
            {"query_id": "q", "user_id": "u", "results": {"weighted_rrf_v1": []}}
        )
    with pytest.raises(ValueError, match="latency_ms"):
        QueryRecord.from_mapping(
            {"query_id": "q", "user_id": "u", "latency_ms": -1}
        )
    with pytest.raises(ValueError, match="query_id"):
        QueryRecord.from_mapping({"user_id": "u"})


# ── 端到端报告 ───────────────────────────────────────────────────


def _compute():
    return compute_official_report(
        _corpus_records(),
        _queries(),
        EvalBundleConfig.from_mapping(CONFIG),
    )


def test_official_report_accounting():
    report = _compute()
    accounting = report["accounting"]
    assert accounting["total_query_count"] == 6
    assert accounting["valid_query_count"] == 3
    assert accounting["excluded_query_count"] == 3
    assert accounting["exclusions"]["empty_gold"] == 1
    assert accounting["exclusions"]["environmental_anomaly"] == 0
    guardrail_ex = accounting["exclusions"]["negative_guardrail"]
    assert guardrail_ex["removed_or_forgotten"] == 1
    assert guardrail_ex["cross_user"] == 1


def test_official_report_rrf_metrics_hand_computed():
    report = _compute()
    rrf = report["channels"]["rrf_v1"]
    assert rrf["status"] == "COMPUTED"
    assert rrf["query_count"] == 3
    assert rrf["hit_count"] == 2
    assert rrf["recall_at_k"] == pytest.approx(2 / 3)
    assert rrf["mrr"] == pytest.approx(2 / 3)
    assert rrf["ndcg_at_k"] == pytest.approx(2 / 3)
    assert rrf["p50_ms"] == pytest.approx(20.0)
    assert rrf["mean_ms"] == pytest.approx(20.0)
    assert rrf["max_ms"] == pytest.approx(30.0)
    assert rrf["latency_sample_count"] == 3
    assert rrf["k_value"] == FROZEN_K


def test_official_report_fts5_incomplete_when_channel_absent():
    report = _compute()
    fts5 = report["channels"]["fts5"]
    # 仅 q1 提供 fts5 结果；q5/q6 无该通道 → INCOMPLETE，recall=1/2
    assert fts5["status"] == "INCOMPLETE_SKIPPED_QUERIES"
    assert fts5["query_count"] == 1
    assert fts5["skipped_query_count"] == 2
    assert fts5["recall_at_k"] == pytest.approx(0.5)


def test_official_report_guardrail_accounting():
    report = _compute()
    guardrail = report["guardrail"]
    assert guardrail["channel"] == "rrf_v1"
    assert guardrail["participating_query_count"] == 5
    assert guardrail["returned_item_count"] == 6
    assert guardrail["violation_query_count"] == 2
    assert guardrail["violation_item_count"] == 2
    assert guardrail["critical_zero_ok"] is False
    cross_user = guardrail["per_category"]["cross_user"]
    assert cross_user["violation_query_count"] == 1
    assert cross_user["violation_item_count"] == 1
    sensitive = guardrail["per_category"]["sensitive_recall_prohibited"]
    assert sensitive["violation_query_count"] == 1
    assert sensitive["violation_item_count"] == 1
    assert cross_user["violation_query_rate"] == pytest.approx(1 / 5)
    assert cross_user["violation_item_rate"] == pytest.approx(1 / 6)
    assert set(guardrail["critical_zero_categories"]) == set(CRITICAL_ZERO_CATEGORIES)


def test_official_report_per_query_detail():
    report = _compute()
    by_id = {d["query_id"]: d for d in report["per_query_detail"]}
    assert len(by_id) == 6
    assert by_id["q1"]["metric_valid"] is True
    assert by_id["q1"]["exclusion_reason"] is None
    assert by_id["q2"]["metric_valid"] is False
    assert by_id["q2"]["exclusion_reason"] == "negative_guardrail:removed_or_forgotten"
    assert by_id["q3"]["exclusion_reason"] == "empty_gold"
    assert by_id["q4"]["exclusion_reason"] == "negative_guardrail:cross_user"
    assert by_id["q5"]["metric_valid"] is True  # 正解合法；forbidden 只用于护栏
    assert by_id["q5"]["resolved_forbidden_categories"] == ["sensitive_recall_prohibited"]


def test_official_report_unknown_ref_fails_closed():
    queries = [
        {
            "query_id": "qx",
            "user_id": "u1",
            "relevant_refs": [_ref("ghost")],
            "forbidden_refs": [],
            "results": {"rrf_v1": []},
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
    assert report["per_category"]["cross_user"]["violation_query_rate"] is None
    assert report["critical_zero_ok"] is True