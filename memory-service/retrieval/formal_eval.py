"""D13B 正式检索评测账本：冻结口径下的指标计算、查询剔除与护栏统计（B 轨）。

定位
----
本模块在 D13D 环境冻结、D13E 封存测试集与 Gold 哈希就绪后，对同一 Commit、
同一麒麟 VM 的检索结果计算正式指标。它只消费数据、不执行检索、不生产 Gold；
dataset/gold/commit/environment 任一项未绑定或 config_version 不符时 fail-closed，
不输出任何可被当作正式指标的数值。

冻结口径来源
------------
- evaluation/D9_RETRIEVAL_GOLD_POLICY_V2.json：
  config v1（k=10/top_k=10/rrf_k=60/top_k==k）、empty_gold_rule、
  negative_guardrail_scope、guardrail_violation_accounting、retrieval_ref_schema。
- evaluation/D9_RETRIEVAL_DATASET_README_V2.md：positive-answerable 定义。
- memory-service/retrieval/evaluation.py：Recall@K / MRR / nDCG@K / 延迟分位。

说明：本文件为 B 轨评测实现，不修改 Vector/FTS5/RRF 生产链路、SQLite 真源或
其他轨道交付物。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from retrieval.evaluation import (
    ChannelMode,
    EvalConfig,
    QueryEvalResult,
    evaluate_queries,
)

FROZEN_CONFIG_VERSION = "d9-retrieval-eval-config/v1"
FROZEN_K = 10
FROZEN_TOP_K = 10
FROZEN_RRF_K = 60
REPORT_VERSION = "d13b-retrieval-eval-report/v1"
DEFAULT_GUARDRAIL_CHANNEL = "rrf_v1"

# 通道字符串 -> ChannelMode（正式对照通道；weighted-rrf/v1 未冻结前不进正式集）
CHANNEL_MODES: dict[str, ChannelMode] = {
    "fts5": ChannelMode.FTS5_ONLY,
    "vector": ChannelMode.VECTOR_ONLY,
    "rrf_v1": ChannelMode.RRF_V1,
}

# 负向护栏类别（D9 negative_guardrail_scope），顺序即判定优先级
GUARDRAIL_CATEGORIES: tuple[str, ...] = (
    "cross_user",
    "sensitive_recall_prohibited",
    "removed_or_forgotten",
    "expired",
    "superseded",
    "deprecated",
    "candidate",
    "unresolved_conflict",
)

# 负向护栏类别名 -> 正式 category_id（D9 negative_guardrail_scope.category_id）
GUARDRAIL_CATEGORY_IDS: dict[str, str] = {
    "cross_user": "cross_user",
    "sensitive_recall_prohibited": "sensitive_recall_prohibited",
    "removed_or_forgotten": "removed_or_forgotten",
    "expired": "expired",
    "superseded": "superseded",
    "deprecated": "deprecated",
    "candidate": "candidate",
    "unresolved_conflict": "unresolved_conflict",
}

CRITICAL_ZERO_CATEGORIES: tuple[str, ...] = (
    "cross_user",
    "sensitive_recall_prohibited",
)

_POSITIVE_MEMORY_STATUSES = frozenset({"active"})
_POSITIVE_SENSITIVITIES = frozenset({"none", "low", "medium"})
_POSITIVE_CONFLICT_STATES = frozenset({"none", "resolved"})

_REQUIRED_REF_KEYS = ("memory_id", "version_id")


def serialize_ref(ref: Mapping[str, Any]) -> str:
    """把 retrieval_ref=(memory_id, version_id) 序列化为不透明判定键。"""
    for key in _REQUIRED_REF_KEYS:
        value = ref.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"retrieval_ref 缺少非空字段 {key!r}")
    return f"{ref['memory_id']}::{ref['version_id']}"


@dataclass(frozen=True)
class CorpusRow:
    """封存语料中一条可判定行（对齐 D9 数据集字段）。"""

    user_id: str
    memory_id: str
    version_id: str
    memory_status: str
    sensitivity: str = "none"
    conflict_state: str = "none"
    is_current: bool = True

    @property
    def key(self) -> str:
        return f"{self.memory_id}::{self.version_id}"

    def positive_answerable(self) -> bool:
        return (
            self.memory_status in _POSITIVE_MEMORY_STATUSES
            and self.is_current
            and self.conflict_state in _POSITIVE_CONFLICT_STATES
            and self.sensitivity in _POSITIVE_SENSITIVITIES
        )

    def guardrail_category(self, query_user_id: Optional[str] = None) -> Optional[str]:
        """按 D9 negative_guardrail_scope 判定该行的禁止类别；无则 None。"""
        if query_user_id is not None and self.user_id != query_user_id:
            return "cross_user"
        if self.sensitivity in ("high", "critical"):
            return "sensitive_recall_prohibited"
        if self.memory_status == "removed":
            return "removed_or_forgotten"
        if self.memory_status == "expired":
            return "expired"
        if self.memory_status == "superseded":
            return "superseded"
        if self.memory_status == "deprecated":
            return "deprecated"
        if self.memory_status == "candidate":
            return "candidate"
        if self.conflict_state == "unresolved":
            return "unresolved_conflict"
        return None


class CorpusIndex:
    """按 (memory_id, version_id) 索引语料行；未知 ref 一律失败关闭。"""

    def __init__(self, rows: Iterable[CorpusRow]) -> None:
        index: dict[str, CorpusRow] = {}
        for row in rows:
            if row.key in index:
                raise ValueError(f"语料存在重复判定键 {row.key!r}")
            index[row.key] = row
        self._index = index

    @classmethod
    def from_records(cls, records: Iterable[Mapping[str, Any]]) -> "CorpusIndex":
        rows = []
        for record in records:
            required = ("user_id", "memory_id", "version_id", "memory_status")
            for key in required:
                value = record.get(key)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"corpus 记录缺少非空字段 {key!r}")
            rows.append(
                CorpusRow(
                    user_id=record["user_id"],
                    memory_id=record["memory_id"],
                    version_id=record["version_id"],
                    memory_status=record["memory_status"],
                    sensitivity=str(record.get("sensitivity", "none")),
                    conflict_state=str(record.get("conflict_state", "none")),
                    is_current=bool(record.get("is_current", True)),
                )
            )
        return cls(rows)

    def resolve(self, ref: Mapping[str, Any]) -> CorpusRow:
        key = serialize_ref(ref)
        try:
            return self._index[key]
        except KeyError as exc:  # pragma: no cover - defensive
            raise ValueError(f"ref 未在语料中解析：{key!r}") from exc

    def __len__(self) -> int:
        return len(self._index)


@dataclass(frozen=True)
class EvalBundleConfig:
    """评测运行绑定配置（fail-closed：不可为 UNKNOWN/缺失）。"""

    config_version: str
    dataset_version: str
    gold_label_version: str
    implementation_commit: str
    environment: str
    evidence_reference: str = ""
    dataset_sha256: str = ""
    gold_sha256: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "EvalBundleConfig":
        config_version = str(raw.get("config_version", "")).strip()
        if config_version != FROZEN_CONFIG_VERSION:
            raise ValueError(
                f"config_version 必须为冻结值 {FROZEN_CONFIG_VERSION!r}，实际 {config_version!r}"
            )
        fields = {
            "dataset_version": "dataset_version",
            "gold_label_version": "gold_label_version",
            "implementation_commit": "implementation_commit",
            "environment": "environment",
        }
        normalized: dict[str, str] = {"config_version": config_version}
        for field_name, raw_key in fields.items():
            value = str(raw.get(raw_key, "")).strip()
            if not value or value.upper() == "UNKNOWN":
                raise ValueError(f"正式评测必须绑定 {raw_key!r}，不得为空或 UNKNOWN")
            normalized[field_name] = value
        for raw_key in ("evidence_reference", "dataset_sha256", "gold_sha256"):
            normalized[raw_key] = str(raw.get(raw_key, "")).strip()
        for frozen_key, frozen_value in (
            ("k", FROZEN_K),
            ("top_k", FROZEN_TOP_K),
            ("rrf_k", FROZEN_RRF_K),
        ):
            if frozen_key in raw and int(raw[frozen_key]) != frozen_value:
                raise ValueError(
                    f"正式评测 {frozen_key} 必须等于冻结值 {frozen_value}，"
                    f"实际 {raw[frozen_key]!r}"
                )
        return cls(**normalized)


@dataclass(frozen=True)
class QueryRecord:
    """一条已执行查询：Gold refs + 每通道返回 refs + 延迟。"""

    query_id: str
    user_id: str
    relevant_refs: tuple[Mapping[str, str], ...] = ()
    forbidden_refs: tuple[Mapping[str, str], ...] = ()
    channel_results: Mapping[str, tuple[Mapping[str, str], ...]] = ()
    latency_ms: Optional[float] = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "QueryRecord":
        query_id = str(raw.get("query_id", "")).strip()
        user_id = str(raw.get("user_id", "")).strip()
        if not query_id or not user_id:
            raise ValueError("query 缺少非空 query_id / user_id")

        def parse_refs(items: Any, label: str) -> tuple[Mapping[str, str], ...]:
            if items is None:
                return ()
            if not isinstance(items, list):
                raise ValueError(f"{label} 必须是 ref 数组")
            parsed = []
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError(f"{label} 中的 ref 必须是对象")
                # 仅消费两个判定键；多余键不参与判定（不影响冻结判定键）
                parsed.append(
                    {
                        "memory_id": str(item.get("memory_id", "")).strip(),
                        "version_id": str(item.get("version_id", "")).strip(),
                    }
                )
            return tuple(parsed)

        results: dict[str, tuple[Mapping[str, str], ...]] = {}
        raw_results = raw.get("results", {})
        if not isinstance(raw_results, dict):
            raise ValueError("results 必须是 {channel: [ref,...]} 对象")
        for channel, items in raw_results.items():
            if channel not in CHANNEL_MODES:
                raise ValueError(f"不支持的评测通道 {channel!r}")
            results[channel] = parse_refs(items, f"results.{channel}")

        latency = raw.get("latency_ms")
        if latency is not None:
            latency = float(latency)
            if latency < 0:
                raise ValueError("latency_ms 不得为负数")

        return cls(
            query_id=query_id,
            user_id=user_id,
            relevant_refs=parse_refs(raw.get("relevant_refs"), "relevant_refs"),
            forbidden_refs=parse_refs(raw.get("forbidden_refs"), "forbidden_refs"),
            channel_results=results,
            latency_ms=latency,
        )


@dataclass(frozen=True)
class QueryAccount:
    """单条查询的账本判定结果。"""

    query_id: str
    metric_valid: bool
    exclusion_reason: Optional[str]  # empty_gold / negative_guardrail:<cat> / environmental_anomaly
    guardrail_categories_in_relevant: tuple[str, ...] = ()
    resolved_forbidden_categories: tuple[str, ...] = ()


def _resolve_ref_set(
    refs: Iterable[Mapping[str, str]],
    index: CorpusIndex,
    query_user_id: str,
) -> dict[str, str]:
    """ref key -> category；category None 表示 positive-answerable 行。"""
    out: dict[str, Optional[str]] = {}
    for ref in refs:
        row = index.resolve(ref)
        out[row.key] = row.guardrail_category(query_user_id)
    # 返回值只保留有类别的（forbidden）；positive 由调用方按集合判断
    return {key: cat for key, cat in out.items() if cat is not None}


def _positive_keys(refs: Iterable[Mapping[str, str]], index: CorpusIndex) -> set[str]:
    return {index.resolve(ref).key for ref in refs}


def classify_queries(
    queries: Iterable[QueryRecord],
    index: CorpusIndex,
) -> list[QueryAccount]:
    accounts = []
    for query in queries:
        relevant_keys = _positive_keys(query.relevant_refs, index)
        forbidden_by_cat = _resolve_ref_set(query.forbidden_refs, index, query.user_id)
        relevant_cats: dict[str, str] = {}
        for ref in query.relevant_refs:
            row = index.resolve(ref)
            category = row.guardrail_category(query.user_id)
            if category is not None:
                relevant_cats[row.key] = category

        metric_valid = bool(relevant_keys) and not relevant_cats
        reason: Optional[str] = None
        if not metric_valid:
            if not query.relevant_refs and not query.forbidden_refs:
                reason = "empty_gold"
            else:
                # relevant 含护栏类别或 guardrail-only 查询
                first_cat = next(iter(relevant_cats.values()), None)
                if first_cat is None and query.forbidden_refs:
                    first_cat = next(iter(forbidden_by_cat.values()), None)
                reason = f"negative_guardrail:{first_cat}" if first_cat else "environmental_anomaly"
        accounts.append(
            QueryAccount(
                query_id=query.query_id,
                metric_valid=metric_valid,
                exclusion_reason=reason,
                guardrail_categories_in_relevant=tuple(dict.fromkeys(relevant_cats.values())),
                resolved_forbidden_categories=tuple(dict.fromkeys(forbidden_by_cat.values())),
            )
        )
    return accounts

def _channel_report(
    valid_queries: list[QueryRecord],
    index: CorpusIndex,
    channel: str,
    config: EvalBundleConfig,
) -> dict[str, Any]:
    """对有效查询计算单一通道的 Recall@K / MRR / nDCG@K 与延迟统计。"""
    mode = CHANNEL_MODES[channel]
    algorithm_version = {
        "fts5": "fts5-only/v1",
        "vector": "vector-only/v1",
        "rrf_v1": "rrf-v1",
    }[channel]
    eval_config = EvalConfig(
        channel_mode=mode,
        k=FROZEN_K,
        top_k=FROZEN_TOP_K,
        rrf_k=FROZEN_RRF_K,
        algorithm_version=algorithm_version,
        dataset_version=config.dataset_version,
        gold_label_version=config.gold_label_version,
        implementation_commit=config.implementation_commit,
        environment=config.environment,
        evidence_reference=config.evidence_reference,
        statistics_method="p95",
        warmup_count=0,
        repeat_count=1,
        concurrency=1,
        target_threshold=0.85,
    )
    results: list[QueryEvalResult] = []
    skipped_query_count = 0
    for query in valid_queries:
        refs = query.channel_results.get(channel)
        if refs is None:
            skipped_query_count += 1
            continue
        results.append(
            QueryEvalResult(
                query_id=query.query_id,
                ranked_ids=tuple(serialize_ref(ref) for ref in refs),
                relevant_ids=frozenset(_positive_keys(query.relevant_refs, index)),
                latency_ms=query.latency_ms,
            )
        )
    report = evaluate_queries(results, eval_config)
    status = "COMPUTED" if skipped_query_count == 0 else "INCOMPLETE_SKIPPED_QUERIES"
    return {
        "status": status,
        "query_count": report.query_count,
        "skipped_query_count": skipped_query_count,
        "recall_at_k": report.recall_at_k,
        "mrr": report.mrr,
        "ndcg_at_k": report.ndcg_at_k,
        "hit_count": report.hit_count,
        "k_value": report.k_value,
        "p50_ms": report.p50_ms,
        "p95_ms": report.p95_ms,
        "mean_ms": report.mean_ms,
        "max_ms": report.max_ms,
        "latency_sample_count": report.sample_count,
    }


def guardrail_accounting(
    queries: Iterable[QueryRecord],
    index: CorpusIndex,
    channel: str = DEFAULT_GUARDRAIL_CHANNEL,
) -> dict[str, Any]:
    """统计指定通道 Top-K 返回中的负向护栏违规（对齐 guardrail_violation_accounting）。

    说明：item 按返回序列逐条累计；query 在同一类别内只计一次；rate 分母采用
    D9 建议口径（query rate=违规查询/参与查询总数，item rate=违规条目/返回条目
    总数），随 D13E 正式冻结后以冻结口径为准。
    """
    per_category: dict[str, dict[str, int]] = {
        category: {"violation_query_count": 0, "violation_item_count": 0}
        for category in GUARDRAIL_CATEGORIES
    }
    participating_query_count = 0
    returned_item_count = 0
    for query in queries:
        refs = query.channel_results.get(channel)
        if refs is None:
            continue
        participating_query_count += 1
        query_categories: set[str] = set()
        for ref in refs:
            returned_item_count += 1
            row = index.resolve(ref)
            category = row.guardrail_category(query.user_id)
            if category is None:
                continue
            per_category[category]["violation_item_count"] += 1
            query_categories.add(category)
        for category in query_categories:
            per_category[category]["violation_query_count"] += 1

    violation_query_count = sum(
        per_category[category]["violation_query_count"]
        for category in GUARDRAIL_CATEGORIES
    )
    violation_item_count = sum(
        per_category[category]["violation_item_count"]
        for category in GUARDRAIL_CATEGORIES
    )

    def rate(numerator: int, denominator: int) -> Optional[float]:
        return numerator / denominator if denominator else None

    breakdown: dict[str, dict[str, Any]] = {}
    for category in GUARDRAIL_CATEGORIES:
        entry = per_category[category]
        breakdown[category] = {
            "violation_query_count": entry["violation_query_count"],
            "violation_item_count": entry["violation_item_count"],
            "violation_query_rate": rate(
                entry["violation_query_count"], participating_query_count
            ),
            "violation_item_rate": rate(
                entry["violation_item_count"], returned_item_count
            ),
        }

    critical_zero_ok = all(
        per_category[category]["violation_query_count"] == 0
        and per_category[category]["violation_item_count"] == 0
        for category in CRITICAL_ZERO_CATEGORIES
    )
    return {
        "channel": channel,
        "participating_query_count": participating_query_count,
        "returned_item_count": returned_item_count,
        "violation_query_count": violation_query_count,
        "violation_item_count": violation_item_count,
        "critical_zero_categories": list(CRITICAL_ZERO_CATEGORIES),
        "critical_zero_ok": critical_zero_ok,
        "per_category": breakdown,
        "rate_denominator_note": (
            "query rate = 违规查询数/参与护栏统计的查询总数；"
            "item rate = 违规条目数/同批 Top-K 返回条目总数（D9 建议口径，待正式冻结）"
        ),
    }


def compute_official_report(
    corpus_records: Iterable[Mapping[str, Any]],
    query_records: Iterable[Mapping[str, Any]],
    config: EvalBundleConfig,
) -> dict[str, Any]:
    """计算 D13B 正式评测报告（冻结口径、fail-closed）。"""
    index = CorpusIndex.from_records(corpus_records)
    parsed_queries = [QueryRecord.from_mapping(raw) for raw in query_records]
    accounts = classify_queries(parsed_queries, index)
    account_by_id = {account.query_id: account for account in accounts}
    if len(account_by_id) != len(accounts):
        raise ValueError("query_id 必须全局唯一")

    valid_queries = [
        query for query in parsed_queries if account_by_id[query.query_id].metric_valid
    ]

    exclusions: dict[str, Any] = {
        "empty_gold": 0,
        "environmental_anomaly": 0,
        "negative_guardrail": {category: 0 for category in GUARDRAIL_CATEGORIES},
    }
    for account in accounts:
        reason = account.exclusion_reason or ""
        if reason == "empty_gold":
            exclusions["empty_gold"] += 1
        elif reason == "environmental_anomaly":
            exclusions["environmental_anomaly"] += 1
        elif reason.startswith("negative_guardrail:"):
            category = reason.split(":", 1)[1]
            if category not in exclusions["negative_guardrail"]:
                raise ValueError(f"未知护栏类别 {category!r}")
            exclusions["negative_guardrail"][category] += 1
        # metric_valid 查询无 exclusion_reason

    excluded_count = len(accounts) - len(valid_queries)

    channels: dict[str, Any] = {}
    for channel in CHANNEL_MODES:
        channels[channel] = _channel_report(valid_queries, index, channel, config)

    guardrail = guardrail_accounting(parsed_queries, index)

    per_query_detail = []
    for query in parsed_queries:
        account = account_by_id[query.query_id]
        per_query_detail.append(
            {
                "query_id": query.query_id,
                "metric_valid": account.metric_valid,
                "exclusion_reason": account.exclusion_reason,
                "guardrail_categories_in_relevant": list(
                    account.guardrail_categories_in_relevant
                ),
                "resolved_forbidden_categories": list(
                    account.resolved_forbidden_categories
                ),
            }
        )

    return {
        "report_version": REPORT_VERSION,
        "config": {
            "config_version": config.config_version,
            "dataset_version": config.dataset_version,
            "gold_label_version": config.gold_label_version,
            "implementation_commit": config.implementation_commit,
            "environment": config.environment,
            "evidence_reference": config.evidence_reference,
            "dataset_sha256": config.dataset_sha256,
            "gold_sha256": config.gold_sha256,
        },
        "accounting": {
            "total_query_count": len(accounts),
            "valid_query_count": len(valid_queries),
            "excluded_query_count": excluded_count,
            "exclusions": exclusions,
        },
        "channels": channels,
        "guardrail": guardrail,
        "per_query_detail": per_query_detail,
    }
