"""D13B 正式检索评测 CLI（B 轨）。

读取评测输入 bundle JSON（config + corpus + queries），按冻结口径
（d9-retrieval-eval-config/v1）计算正式指标与护栏统计，输出 JSON 报告。
fail-closed：provenance/采样参数不完整或非法、config_version 不符、返回 ref 重复或
超过 top_k、有结果但缺 latency、latency 非有限、0 个有效 positive query 时，
不输出可被误读为正式的指标。

用法：
    PYTHONPATH=memory-service python scripts/run_d13b_formal_eval.py <bundle.json> [--output report.json]

bundle JSON 结构：
    {
      "config": {
        "config_version": "d9-retrieval-eval-config/v1",
        "dataset_version": "...",
        "gold_label_version": "...",
        "implementation_commit": "<40 hex>",
        "environment": "...",
        "evidence_reference": "...",
        "dataset_sha256": "<64 hex>",
        "gold_sha256": "<64 hex>",
        "statistics_method": "p50_and_p95",
        "warmup_count": 0,
        "repeat_count": 1,
        "concurrency": 1
      },
      "corpus": [
        {"user_id": "...", "memory_id": "...", "version_id": "...",
         "memory_status": "active", "sensitivity": "none",
         "conflict_state": "none", "is_current": true}
      ],
      "queries": [
        {
          "query_id": "q1", "user_id": "...",
          "relevant_refs": [{"memory_id": "...", "version_id": "..."}],
          "forbidden_refs": [],
          "results": {
            "fts5":  [{"memory_id": "...", "version_id": "..."}],
            "vector": [...],
            "rrf_v1": [...]
          },
          "latency_ms": {"fts5": 5.0, "vector": 8.0, "rrf_v1": 12.5}
        }
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "memory-service"))

from retrieval.formal_eval import (  # noqa: E402
    EvalBundleConfig,
    compute_official_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="D13B formal retrieval evaluation")
    parser.add_argument("input", help="bundle JSON input file")
    parser.add_argument("--output", "-o", help="optional output JSON file")
    args = parser.parse_args()

    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    config = EvalBundleConfig.from_mapping(raw.get("config", {}))
    report = compute_official_report(
        raw.get("corpus", []),
        raw.get("queries", []),
        config,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())