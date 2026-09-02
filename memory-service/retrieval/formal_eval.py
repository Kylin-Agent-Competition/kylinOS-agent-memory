"""D13B 正式检索评测账本：冻结口径下的指标计算、查询剔除与护栏统计（B 轨）。

定位
----
本模块在 D13D 环境冻结、D13E 封存测试集与 Gold 哈希就绪后，对同一 Commit、
同一麒麟 VM 的检索结果计算正式指标。它只消费数据、不执行检索、不生产 Gold；
provenance（dataset/gold 哈希、commit、environment、evidence）未完整绑定或
config_version 不符时 fail-closed，不输出任何可被当作正式指标的数值。

冻结口径来源
------------
- evaluation/D9_RETRIEVAL_GOLD_POLICY_V2.json：
  config v1（k=10/top_k=10/rrf_k=60/top_k==k）、empty_gold_rule、
  negative_guardrail_scope、guardrail_violation_accounting、retrieval_ref_schema。
- evaluation/D9_RETRIEVAL_DATASET_README_V2.md：positive-answerable 定义。
- memory-service/retrieval/evaluation.py：Recall@K / MRR / nDCG@K / 延迟分位。

v2（吸收 PR #123 首轮 Review REQUEST_CHANGES）
--------------------------------------------
- 正式分母显式基于 row.positive_answerable()；stale（is_current=false）不进入分母，
  归入 boundary:not_current_version 剔除。
- corpus 解析严格校验类型与枚举（is_current 必须为真布尔；字段不允许默认放宽）。
- 全局 guardrail violation query count 使用违规 query 唯一集合，避免跨类别重复累计。
- valid_query_count == 0 或通道无样本时返回 NO_VALID_QUERIES / NO_CHANNEL_RESULTS，
  指标为 null，而不是 0.0。
- 延迟改为按通道记录 latency_ms: {channel: ms}，分通道独立汇总。
- provenance 强校验：commit 为 40 位 Git SHA；dataset/gold 为 64 位 SHA-256；evidence 必填。
- 每个通道返回 ref 必须唯一且长度不超过冻结 top_k=10。
"""

from __future__ import annotations

import re
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
REPORT_VERSION = "d13b-retrieval-eval-report/v2"
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

CRITICAL_ZERO_CATEGORIES: tuple[str, ...] = (
    "cross_user",
    "sensitive_recall_prohibited",
)

_MEMORY_STATUSES = frozenset({"active", "candidate", "superseded", "expired", "removed", "deprecated"})
_SENSITIVITIES = frozenset({"none", "low", "medium", "high", "critical"})
_CONFLICT_STATES = frozenset({"none", "resolved", "unresolved"})

_POSITIVE_MEMORY_STATUSES = frozenset({"active"})
_POSITIVE_SENSITIVITIES = frozenset({"none", "low", "medium"})
_POSITIVE_CONFLICT_STATES = frozenset({"none", "resolved"})

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_REQUIRED_REF_KEYS = ("memory_id", "version_id")


def serialize_ref(ref: Mapping[str, Any]) -> str:
    """把 retrieval_ref=(memory_id, version_id) 序列化为不透明判定键。"""
    for key in _REQUIRED_REF_KEYS:
        value = ref.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"retrieval_ref 缺少非空字段 {key!r}")
    return f"{ref['memory_id']}::{ref['version_id']}"


def _validate_ref_object(item: Any, label: str) -> Mapping[str, str]:
    """严格校验一个 ref 对象：仅允许 memory_id/version_id 两个非空字段。"""
    if not isinstance(item, dict):
        raise ValueError(f"{label} 中的 ref 必须是对象")
    if set(item.keys()) != set(_REQUIRED_REF_KEYS):
        raise ValueError(f"{label} 中的 ref 必须且只能包含 memory_id/version_id")
    for key in _REQUIRED_REF_KEYS:
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} 中的 ref.{key} 必须是非空字符串")
    return {"memory_id": item["memory_id"], "version_id": item["version_id"]}


@dataclass(frozen=True)
class CorpusRow:
    """封存语料中一条可判定行（formal 模式字段全部显式提供）。"""

    user_id: str
    memory_id: str
    version_id: str
    memory_status: str
    sensitivity: str
    conflict_state: str
    is_current: bool

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

    def boundary_reason(self) -> Optional[str]:
        """非护栏、非 positive 的边界剔除原因（当前仅 stale 版本）。"""
        if self.guardrail_category() is not None or self.positive_answerable():
            return None
        if not self.is_current:
            return "not_current_version"
        return "not_positive"


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
        """formal 模式严格解析：字段必填、类型与枚举校验，不允许默认放宽。"""
        rows = []
        for position, record in enumerate(records):
            if not isinstance(record, dict):
                raise ValueError(f"corpus 第 {position} 行必须是对象")
            required = (
                "user_id",
                "memory_id",
                "version_id",
                "memory_status",
                "sensitivity",
                "conflict_state",
                "is_current",
            )
            for key in required:
                if key not in record:
                    raise ValueError(f"corpus 第 {position} 行缺少字段 {key!r}（formal 模式不允许默认放宽）")
            for key in ("user_id", "memory_id", "version_id", "memory_status", "sensitivity", "conflict_state"):
                value = record[key]
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"corpus 第 {position} 行 {key!r} 必须是非空字符串")
            if not isinstance(record["is_current"], bool):
                raise ValueError(f"corpus 第 {position} 行 is_current 必须是布尔值")
            memory_status = record["memory_status"]
            sensitivity = record["sensitivity"]
            conflict_state = record["conflict_state"]
            if memory_status not in _MEMORY_STATUSES:
                raise ValueError(f"corpus 第 {position} 行非法 memory_status {memory_status!r}")
            if sensitivity not in _SENSITIVITIES:
                raise ValueError(f"corpus 第 {position} 行非法 sensitivity {sensitivity!r}")
            if conflict_state not in _CONFLICT_STATES:
                raise ValueError(f"corpus 第 {position} 行非法 conflict_state {conflict_state!r}")
            rows.append(
                CorpusRow(
                    user_id=record["user_id"],
                    memory_id=record["memory_id"],
                    version_id=record["version_id"],
                    memory_status=memory_status,
                    sensitivity=sensitivity,
                    conflict_state=conflict_state,
                    is_current=record["is_current"],
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
    """评测运行绑定配置（fail-closed：provenance 必须完整且格式合法）。"""

    config_version: str
    dataset_version: str
    gold_label_version: str
    implementation_commit: str
    environment: str
    evidence_reference: str
    dataset_sha256: str
    gold_sha256: str

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "EvalBundleConfig":
        config_version = str(raw.get("config_version", "")).strip()
        if config_version != FROZEN_CONFIG_VERSION:
            raise ValueError(
                f"config_version 必须为冻结值 {FROZEN_CONFIG_VERSION!r}，实际 {config_version!r}"
            )
        text_fields = {
            "dataset_version": "dataset_version",
            "gold_label_version": "gold_label_version",
            "environment": "environment",
            "evidence_reference": "evidence_reference",
        }
        normalized: dict[str, str] = {"config_version": config_version}
        for field_name, raw_key in text_fields.items():
            value = str(raw.get(raw_key, "")).strip()
            if not value or value.upper() == "UNKNOWN":
                raise ValueError(f"正式评测必须绑定 {raw_key!r}，不得为空或 UNKNOWN")
            normalized[field_name] = value
        commit = str(raw.get("implementation_commit", "")).strip()
        if not _GIT_SHA_RE.match(commit):
            raise ValueError("implementation_commit 必须是 40 位小写十六进制 Git SHA")
        normalized["implementation_commit"] = commit
        for raw_key in ("dataset_sha256", "gold_sha256"):
            digest = str(raw.get(raw_key, "")).strip()
            if not _SHA256_RE.match(digest):
                raise ValueError(f"{raw_key} 必须是非空 64 位小写十六进制 SHA-256")
            normalized[raw_key] = digest
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


def _parse_refs(items: Any, label: str) -> tuple[Mapping[str, str], ...]:
    if items is None:
        return ()
    if not isinstance(items, list):
        raise ValueError(f"{label} 必须是 ref 数组")
    return tuple(_validate_ref_object(item, label) for item in items)


@dataclass(frozen=True)
class QueryRecord:
    """一条已执行查询：Gold refs + 每通道返回 refs + 每通道延迟。"""

    query_id: str
    user_id: str
    relevant_refs: tuple[Mapping[str, str], ...] = ()
    forbidden_refs: tuple[Mapping[str, str], ...] = ()
    channel_results: Mapping[str, tuple[Mapping[str, str], ...]] = ()
    channel_latency_ms: Mapping[str, float] = ()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "QueryRecord":
        query_id = str(raw.get("query_id", "")).strip()
        user_id = str(raw.get("user_id", "")).strip()
        if not query_id or not user_id:
            raise ValueError("query 缺少非空 query_id / user_id")

        results: dict[str, tuple[Mapping[str, str], ...]] = {}
        raw_results = raw.get("results", {})
        if not isinstance(raw_results, dict):
            raise ValueError("results 必须是 {channel: [ref,...]} 对象")
        for channel, items in raw_results.items():
            if channel not in CHANNEL_MODES:
                raise ValueError(f"不支持的评测通道 {channel!r}")
            parsed = _parse_refs(items, f"results.{channel}")
            keys = [serialize_ref(ref) for ref in parsed]
            if len(keys) != len(set(keys)):
                raise ValueError(f"results.{channel} 不允许重复返回同一 ref")
            if len(parsed) > FROZEN_TOP_K:
                raise ValueError(
                    f"results.{channel} 长度 {len(parsed)} 超过冻结 top_k={FROZEN_TOP_K}"
                )
            results[channel] = parsed

        latencies: dict[str, float] = {}
        raw_latency = raw.get("latency_ms")
        if raw_latency is not None:
            if not isinstance(raw_latency, dict):
                raise ValueError("latency_ms 必须是按通道的对象 {channel: ms}")
            for channel, value in raw_latency.items():
                if channel not in CHANNEL_MODES:
                    raise ValueError(f"latency_ms 含不支持的通道 {channel!r}")
                latency = float(value)
                if latency < 0:
                    raise ValueError(f"latency_ms.{channel} 不得为负数")
                latencies[channel] = latency

        return cls(
            query_id=query_id,
            user_id=user_id,
            relevant_refs=_parse_refs(raw.get("relevant_refs"), "relevant_refs"),
            forbidden_refs=_parse_refs(raw.get("forbidden_refs"), "forbidden_refs"),
            channel_results=results,
            channel_latency_ms=latencies,
        )


@dataclass(frozen=True)
class QueryAccount:
    """单条查询的账本判定结果。"""

    query_id: str
    metric_valid: bool
    exclusion_reason: Optional[str]
    guardrail_categories_in_relevant: tuple[str, ...] = ()
    resolved_forbidden_categories: tuple[str, ...] = ()
    boundary_reasons: tuple[str, ...] = ()


def classify_queries(
    queries: Iterable[QueryRecord],
    index: CorpusIndex,
) -> list[QueryAccount]:
    """按 D9 v2 口径分类查询：有效 positive / empty_gold / guardrail / boundary / 异常。"""
    accounts = []
    for query in queries:
        relevant_categories: list[str] = []
        boundary_reasons: list[str] = []
        for ref in query.relevant_refs:
            row = index.resolve(ref)
            category = row.guardrail_category(query.user_id)
            if category is not None:
                relevant_categories.append(category)
            else:
                reason = row.boundary_reason()
                if reason is not None:
                    boundary_reasons.append(reason)
        forbidden_categories: list[str] = []
        for ref in query.forbidden_refs:
            row = index.resolve(ref)
            category = row.guardrail_category(query.user_id)
            if category is not None:
                forbidden_categories.append(category)

        metric_valid = False
        reason: Optional[str] = None
        if query.relevant_refs:
            if relevant_categories:
                first_category = next(
                    (c for c in GUARDRAIL_CATEGORIES if c in relevant_categories), None
                )
                reason = f"negative_guardrail:{first_category}"
            elif boundary_reasons:
                reason = f"boundary:{boundary_reasons[0]}"
            else:
                # 全部 relevant 均为 positive-answerable 且无护栏类别
                metric_valid = True
        else:
            if query.forbidden_refs:
                if forbidden_categories:
                    first_category = next(
                        (c for c in GUARDRAIL_CATEGORIES if c in forbidden_categories), None
                    )
                    reason = f"negative_guardrail:{first_category}"
                else:
                    reason = "environmental_anomaly"
            else:
                reason = "empty_gold"

        accounts.append(
            QueryAccount(
                query_id=query.query_id,
                metric_valid=metric_valid,
                exclusion_reason=reason,
                guardrail_categories_in_relevant=tuple(dict.fromkeys(relevant_categories)),
                resolved_forbidden_categories=tuple(dict.fromkeys(forbidden_categories)),
                boundary_reasons=tuple(dict.fromkeys(boundary_reasons)),
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
    if not valid_queries:
        return _empty_channel_status("NO_VALID_QUERIES")
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
                relevant_ids=frozenset(
                    index.resolve(ref).key for ref in query.relevant_refs
                ),
                latency_ms=query.channel_latency_ms.get(channel),
            )
        )
    if not results:
        return _empty_channel_status("NO_CHANNEL_RESULTS", skipped_query_count)
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


def _empty_channel_status(status: str, skipped_query_count: int = 0) -> dict[str, Any]:
    """无有效查询或通道无样本：指标为 null，绝不以 0.0 冒充正式结果。"""
    return {
        "status": status,
        "query_count": 0,
        "skipped_query_count": skipped_query_count,
        "recall_at_k": None,
        "mrr": None,
        "ndcg_at_k": None,
        "hit_count": None,
        "k_value": FROZEN_K,
        "p50_ms": None,
        "p95_ms": None,
        "mean_ms": None,
        "max_ms": None,
        "latency_sample_count": 0,
    }


def guardrail_accounting(
    queries: Iterable[QueryRecord],
    index: CorpusIndex,
    channel: str = DEFAULT_GUARDRAIL_CHANNEL,
) -> dict[str, Any]:
    """统计指定通道 Top-K 返回中的负向护栏违规（对齐 guardrail_violation_accounting）。

    - 一条 query 只要 Top-K 出现任一 forbidden ref，全局 violation query count 只计 1；
    - per-category 独立统计 query/item 计数；
    - rate 分母采用 D9 建议口径（query rate=违规查询/参与查询总数，item rate=违规条目/
      返回条目总数），随 D13E 正式冻结后以冻结口径为准。
    """
    per_category: dict[str, dict[str, Any]] = {
        category: {"violating_query_ids": set(), "violation_item_count": 0}
        for category in GUARDRAIL_CATEGORIES
    }
    participating_query_count = 0
    returned_item_count = 0
    for query in queries:
        refs = query.channel_results.get(channel)
        if refs is None:
            continue
        participating_query_count += 1
        for ref in refs:
            returned_item_count += 1
            row = index.resolve(ref)
            category = row.guardrail_category(query.user_id)
            if category is None:
                continue
            per_category[category]["violating_query_ids"].add(query.query_id)
            per_category[category]["violation_item_count"] += 1

    violating_query_ids: set[str] = set()
    violation_item_count = 0
    breakdown: dict[str, dict[str, Any]] = {}
    for category in GUARDRAIL_CATEGORIES:
        entry = per_category[category]
        query_count = len(entry["violating_query_ids"])
        item_count = entry["violation_item_count"]
        violating_query_ids.update(entry["violating_query_ids"])
        violation_item_count += item_count
        breakdown[category] = {
            "violation_query_count": query_count,
            "violation_item_count": item_count,
            "violation_query_rate": (
                query_count / participating_query_count
                if participating_query_count
                else None
            ),
            "violation_item_rate": (
                item_count / returned_item_count if returned_item_count else None
            ),
        }

    critical_zero_ok = all(
        per_category[category]["violation_item_count"] == 0
        and not per_category[category]["violating_query_ids"]
        for category in CRITICAL_ZERO_CATEGORIES
    )
    return {
        "channel": channel,
        "participating_query_count": participating_query_count,
        "returned_item_count": returned_item_count,
        "violation_query_count": len(violating_query_ids),
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
        "boundary": {},
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
        elif reason.startswith("boundary:"):
            boundary_reason = reason.split(":", 1)[1]
            exclusions["boundary"][boundary_reason] = (
                exclusions["boundary"].get(boundary_reason, 0) + 1
            )

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
                "boundary_reasons": list(account.boundary_reasons),
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