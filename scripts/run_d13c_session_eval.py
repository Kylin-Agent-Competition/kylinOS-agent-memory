"""D13C 端到端会话评测 CLI（C 轨）。

读取会话评测输入 bundle JSON（config + sessions[]），按冻结口径
（d13c-session-eval-config/v2）计算会话级指标与护栏统计，输出 JSON 报告。
fail-closed：provenance/采样参数不完整或非法、config_version 不符、
0 个有效 session 时，不输出可被误读为正式的指标。
R2/NR-1：config.stability_repeat>1 时，sessions 必须携带 execution_group_id +
stability_cohort_id + stability_round（A/B 每 cohort 覆盖 1..stability_repeat；
缺轮/重复轮/越界均 fail-closed）。

用法：
    PYTHONPATH=memory-service python scripts/run_d13c_session_eval.py <bundle.json> [--output report.json]

bundle JSON 结构：
    {
      "config": {
        "config_version": "d13c-session-eval-config/v2",
        "dataset_version": "...",
        "gold_label_version": "...",
        "implementation_commit": "<40 hex>",
        "environment": "...",
        "evidence_reference": "...",
        "dataset_sha256": "<64 hex>",
        "gold_sha256": "<64 hex>",
        "statistics_method": "p50_and_p95",
        "warmup_count": 0,
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
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "memory-service"))

from evaluation.d13c_session_eval import (  # noqa: E402
    REPORT_VERSION,
    EvalSessionConfig,
    compute_session_report,
)


def _error_report(reason: str, raw_config) -> dict:
    """R4：统一受控 fail-closed 错误报告（aggregate_metrics=null、无 traceback）。"""
    return {
        "report_version": REPORT_VERSION,
        "config": raw_config if isinstance(raw_config, dict) else {},
        "aggregate_metrics": None,
        "per_session_metrics": [],
        "cross_session_isolation": None,
        "critical_zero_ok": None,
        "fail_closed_reasons": [reason],
        "provenance": {
            "note": (
                "fail-closed：输入读取/JSON 解析/类型校验/配置/计算任一环节失败或"
                "证据不足，不输出任何可被误读为正式的指标；"
                "未取得麒麟 VM 实测前 Runtime 结论 UNVERIFIED。"
            )
        },
    }


def _emit(report: dict, output: Optional[str]) -> int:
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        print(text)
    # fail-closed 报告（aggregate_metrics=null）统一 exit 2
    return 2 if report.get("aggregate_metrics") is None else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="D13C end-to-end session evaluation (C track)"
    )
    parser.add_argument("input", help="bundle JSON input file")
    parser.add_argument(
        "--output", "-o", help="optional output JSON file (default: stdout)"
    )
    args = parser.parse_args()

    # R4：读取文件 → json.loads → root 类型 → config 类型 → sessions 类型 →
    #      EvalSessionConfig → compute_session_report 全链受控异常，无 traceback。
    try:
        raw_text = Path(args.input).read_text(encoding="utf-8")
    except OSError as exc:
        return _emit(_error_report(f"READ_FAILED:{exc}", None), args.output)

    try:
        root = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return _emit(_error_report(f"INVALID_JSON:{exc}", None), args.output)

    if not isinstance(root, dict):
        return _emit(
            _error_report("ROOT_NOT_OBJECT:根节点必须是 JSON 对象", None),
            args.output,
        )
    if "config" not in root:
        return _emit(_error_report("MISSING_CONFIG:bundle 缺少 config", None), args.output)
    if "sessions" not in root:
        return _emit(
            _error_report("MISSING_SESSIONS:bundle 缺少 sessions", root["config"]),
            args.output,
        )
    if not isinstance(root["config"], dict):
        return _emit(
            _error_report("CONFIG_NOT_OBJECT:config 必须是 JSON 对象", root["config"]),
            args.output,
        )
    if not isinstance(root["sessions"], list):
        return _emit(
            _error_report("SESSIONS_NOT_ARRAY:sessions 必须是 JSON 数组", root["config"]),
            args.output,
        )

    try:
        config = EvalSessionConfig.from_mapping(root["config"])
        report = compute_session_report(root["sessions"], config)
    except ValueError as exc:
        return _emit(
            _error_report(f"INVALID_INPUT:{exc}", root.get("config")),
            args.output,
        )

    # compute 级 fail-closed（NO_VALID_SESSIONS / 轮次证据不足 / 无跨会话 pair 等）
    return _emit(report, args.output)

if __name__ == "__main__":
    raise SystemExit(main())
