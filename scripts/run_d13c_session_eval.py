"""D13C 端到端会话评测 CLI（C 轨）。

读取会话评测输入 bundle JSON（config + sessions[]），按冻结口径
（d13c-session-eval-config/v1）计算会话级指标与护栏统计，输出 JSON 报告。
fail-closed：provenance/采样参数不完整或非法、config_version 不符、
0 个有效 session 时，不输出可被误读为正式的指标。

用法：
    PYTHONPATH=memory-service python scripts/run_d13c_session_eval.py <bundle.json> [--output report.json]

bundle JSON 结构：
    {
      "config": {
        "config_version": "d13c-session-eval-config/v1",
        "dataset_version": "...",
        "gold_label_version": "...",
        "implementation_commit": "<40 hex>",
        "environment": "...",
        "evidence_reference": "...",
        "dataset_sha256": "<64 hex>",
        "gold_sha256": "<64 hex>",
        "statistics_method": "p50_and_p95",
        "warmup_count": 0,
        "repeat_count": 5,
        "concurrency": 1,
        "stability_repeat": 5,
        "deadline_ms": 5000
      },
      "sessions": [
        {
          "session_id": "session-demo-0001",
          "scenario": "cross_session_A",
          "injected_context_text": "[MEMORY-CONTEXT] ...",
          "steps": [
            {
              "step_id": "step1_prechat",
              "method": "memory.retrieve",
              "response_status": "ok",
              "stage_final": "ready",
              "stage_transitions": ["idle", "querying", "ready"],
              "latency_ms": 12.0,
              "isolation": {
                "original_user_text_isolated": true,
                "injected_context_present": true,
                "model_request_clean": true
              },
              "guardrail_violations": [],
              "deadline_ms": 5000,
              "timed_out": false,
              "finalization_reason": "",
              "stop_reason": "",
              "retry_of_turn_id": "",
              "turn_id": "turn-0001"
            }
          ]
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

from evaluation.d13c_session_eval import (  # noqa: E402
    EvalSessionConfig,
    compute_session_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="D13C end-to-end session evaluation (C track)"
    )
    parser.add_argument("input", help="bundle JSON input file")
    parser.add_argument(
        "--output", "-o", help="optional output JSON file (default: stdout)"
    )
    args = parser.parse_args()

    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    try:
        config = EvalSessionConfig.from_mapping(raw.get("config", {}))
        report = compute_session_report(raw.get("sessions", []), config)
    except ValueError as exc:
        # fail-closed：解析或校验失败，输出结构化错误而非零指标报告
        error_report = {
            "report_version": "d13c-session-eval-report/v1",
            "config": raw.get("config", {}),
            "aggregate_metrics": None,
            "per_session_metrics": [],
            "critical_zero_ok": None,
            "fail_closed_reasons": [f"INVALID_INPUT:{exc}"],
            "provenance": {
                "note": (
                    "fail-closed：输入解析/校验失败，不输出任何指标；"
                    "未取得麒麟 VM 实测前 Runtime 结论 UNVERIFIED。"
                )
            },
        }
        text = json.dumps(error_report, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        else:
            print(text)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
