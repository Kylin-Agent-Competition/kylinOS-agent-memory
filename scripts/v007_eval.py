"""V007 检索评测 CLI（B 轨脚本）。

读取 B 轨消费的评测输入 JSON，分别计算 FTS5-only / Vector-only / rrf-v1 的
Recall@K、MRR、nDCG@K、P50、P95，并绑定配置版本输出 JSON 报告。

注意：
- Gold Label / 封存集由 E 轨提供并锁定哈希；本脚本只消费结构，不生产标签。
- K 值、p95 口径等均为 TEAM_DEFINED，必须通过 config 显式登记。
- 当前无封存集，本脚本不会伪造任何达标结论；未提供数据时指标为空/0 样本。

用法：
    PYTHONPATH=memory-service python scripts/v007_eval.py <input.json> [--output report.json]

输入 JSON 结构：
    {
      "config": {
        "dataset_version": "...",
        "gold_label_version": "...",
        "implementation_commit": "...",
        "environment": "...",
        "k": 10,
        "rrf_k": 60
      },
      "queries": [
        {
          "query_id": "q1",
          "relevant_ids": ["kn1", "kn2"],
          "fts5_ranked_ids": ["kn1", "kn3"],
          "vector_ranked_ids": ["kn2", "kn1"],
          "rrf_ranked_ids": ["kn1", "kn2"],
          "latency_ms": 120.5
        }
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "memory-service"))

from retrieval.evaluation import (  # noqa: E402
    ChannelMode,
    EvalConfig,
    QueryEvalResult,
    evaluate_queries,
    report_to_dict,
)


def _build_queries(raw_queries: list[dict], mode: ChannelMode) -> list[QueryEvalResult]:
    key = {
        ChannelMode.FTS5_ONLY: "fts5_ranked_ids",
        ChannelMode.VECTOR_ONLY: "vector_ranked_ids",
        ChannelMode.RRF_V1: "rrf_ranked_ids",
    }[mode]
    out = []
    for item in raw_queries:
        out.append(
            QueryEvalResult(
                query_id=item["query_id"],
                ranked_ids=tuple(item.get(key, [])),
                relevant_ids=frozenset(item.get("relevant_ids", [])),
                latency_ms=item.get("latency_ms"),
            )
        )
    return out


def _config(raw: dict, mode: ChannelMode) -> EvalConfig:
    return EvalConfig(
        channel_mode=mode,
        k=int(raw.get("k", 10)),
        top_k=int(raw.get("top_k", raw.get("k", 10))),
        rrf_k=int(raw.get("rrf_k", 60)),
        dataset_version=str(raw.get("dataset_version", "UNKNOWN")),
        gold_label_version=str(raw.get("gold_label_version", "UNKNOWN")),
        implementation_commit=str(raw.get("implementation_commit", "UNKNOWN")),
        environment=str(raw.get("environment", "UNKNOWN")),
        evidence_reference=str(raw.get("evidence_reference", "")),
        statistics_method=str(raw.get("statistics_method", "p95")),
        warmup_count=int(raw.get("warmup_count", 0)),
        repeat_count=int(raw.get("repeat_count", 1)),
        concurrency=int(raw.get("concurrency", 1)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="V007 retrieval evaluation")
    parser.add_argument("input", help="JSON input file")
    parser.add_argument("--output", "-o", help="optional output JSON file")
    args = parser.parse_args()

    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    raw_config = raw.get("config", {})
    raw_queries = raw.get("queries", [])

    result: dict[str, Any] = {
        "status": "UNVERIFIED" if not raw_queries else "SCRIPT_OUTPUT",
        "channels": {},
    }
    for mode in (ChannelMode.FTS5_ONLY, ChannelMode.VECTOR_ONLY, ChannelMode.RRF_V1):
        report = evaluate_queries(_build_queries(raw_queries, mode), _config(raw_config, mode))
        result["channels"][mode.value] = report_to_dict(report)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
