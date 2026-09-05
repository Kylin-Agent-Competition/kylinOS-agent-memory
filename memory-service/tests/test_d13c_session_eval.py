"""D13C 端到端会话评测账本 L1 测试（纯数据，无 VM 依赖）。

覆盖：
- A1~A8：成功 bundle 各指标正确（step_completion / isolation / method_coverage /
  stop_retry / cross_session / latency / critical_zero）。
- E1~E4：provenance / config_version / latency / statistics_method fail-closed。
- S1~S3：guardrail critical（cross_user / sensitive）与非 critical（unresolved_conflict）。
- R1~R4：NO_VALID_SESSIONS / 重复 step_id / 重复 session_id / invalid_config。
- N1~N5：stability_repeat 默认 / retry_of_turn_id=turn_id 违反 / stop 缺 stop_reason /
  deadline timeout 正确 failed / deadline timeout 错误 stage 违反。
"""

from __future__ import annotations

import math

import pytest

from evaluation.d13c_session_eval import (
    CRITICAL_ZERO_CATEGORIES,
    DEFAULT_DEADLINE_MS,
    DEFAULT_STABILITY_REPEAT,
    FROZEN_CONFIG_VERSION,
    REPORT_VERSION,
    REQUIRED_IPC_METHODS,
    EvalSessionConfig,
    SessionRecord,
    StepRecord,
    compute_session_report,
)

COMMIT = "a" * 40
DS_SHA = "d" * 64
GOLD_SHA = "e" * 64

CONFIG = {
    "config_version": FROZEN_CONFIG_VERSION,
    "dataset_version": "d13c-dataset-v1-test",
    "gold_label_version": "d13c-gold-v1-test",
    "implementation_commit": COMMIT,
    "environment": "unit-test",
    "evidence_reference": "unittest/d13c-session-eval",
    "dataset_sha256": DS_SHA,
    "gold_sha256": GOLD_SHA,
    "statistics_method": "p50_and_p95",
    "warmup_count": 0,
    "repeat_count": 5,
    "concurrency": 1,
    "stability_repeat": 5,
    "deadline_ms": 5000,
}


def _step(
    step_id,
    method,
    *,
    response_status="ok",
    stage_final="ready",
    transitions=None,
    latency_ms=12.0,
    iso_ou=True,
    iso_ic=True,
    iso_mr=True,
    violations=None,
    deadline_ms=5000,
    timed_out=False,
    finalization_reason="",
    stop_reason="",
    retry_of_turn_id="",
    turn_id="turn-0001",
):
    return {
        "step_id": step_id,
        "method": method,
        "response_status": response_status,
        "stage_final": stage_final,
        "stage_transitions": transitions or ["idle", "querying", "ready"],
        "latency_ms": latency_ms,
        "isolation": {
            "original_user_text_isolated": iso_ou,
            "injected_context_present": iso_ic,
            "model_request_clean": iso_mr,
        },
        "guardrail_violations": violations or [],
        "deadline_ms": deadline_ms,
        "timed_out": timed_out,
        "finalization_reason": finalization_reason,
        "stop_reason": stop_reason,
        "retry_of_turn_id": retry_of_turn_id,
        "turn_id": turn_id,
    }


def _happy_steps(turn_id="turn-0001", finalization_reason="normal",
                 stop_reason="", retry_of_turn_id=""):
    """D11-C 5 步主演示 7 个 IPC step（forget 拆 preview+execute）。"""
    return [
        _step("step1_prechat", "memory.retrieve", latency_ms=12.0),
        _step(
            "step2_postturn", "turn.finalized", latency_ms=8.0,
            finalization_reason=finalization_reason,
            stop_reason=stop_reason,
            retry_of_turn_id=retry_of_turn_id,
            turn_id=turn_id,
            transitions=["idle", "sending", "ready"],
        ),
        _step("step3_tool", "tool.execution", latency_ms=15.0,
              transitions=["idle", "sending", "ready"]),
        _step("step4a_conflict", "conflict.compare", latency_ms=6.0,
              transitions=["idle", "querying", "ready"]),
        _step("step4b_lifecycle", "lifecycle.status", latency_ms=5.0,
              transitions=["idle", "querying", "ready"]),
        _step("step5a_forget_preview", "forget.preview", latency_ms=9.0,
              transitions=["idle", "previewing", "awaiting_confirmation"]),
        _step("step5b_forget_execute", "forget.execute", latency_ms=11.0,
              stage_final="completed",
              transitions=["idle", "executing", "completed"]),
    ]


def _session(
    session_id="session-demo-0001",
    scenario="cross_session_A",
    steps=None,
    injected_context_text="[MEMORY-CONTEXT] session-A context",
):
    return {
        "session_id": session_id,
        "scenario": scenario,
        "injected_context_text": injected_context_text,
        "steps": steps if steps is not None else _happy_steps(),
    }


def _bundle(sessions, config=None):
    return {
        "config": config if config is not None else CONFIG,
        "sessions": sessions,
    }


def _report(sessions, config=None):
    cfg = EvalSessionConfig.from_mapping(config if config is not None else CONFIG)
    return compute_session_report(sessions, cfg)


# ── A. 成功 bundle 各指标 ─────────────────────────────────────────


def test_a1_happy_bundle_all_metrics_computed():
    report = _report([_session()])
    assert report["report_version"] == REPORT_VERSION
    assert report["aggregate_metrics"] is not None
    assert report["fail_closed_reasons"] == []


def test_a2_step_completion_rate_full():
    report = _report([_session()])
    assert report["aggregate_metrics"]["step_completion_rate"] == 1.0
    assert report["aggregate_metrics"]["total_step_count"] == 7


def test_a2b_step_completion_rate_partial():
    steps = _happy_steps()
    steps[2] = _step("step3_tool", "tool.execution", response_status="error",
                     stage_final="failed", latency_ms=0.0,
                     transitions=["idle", "sending", "failed"])
    report = _report([_session(steps=steps)])
    # 6/7 completed
    assert report["aggregate_metrics"]["step_completion_rate"] == pytest.approx(6 / 7)


def test_a3_isolation_pass_rate_full():
    report = _report([_session()])
    assert report["aggregate_metrics"]["isolation_pass_rate"] == 1.0


def test_a4_ipc_method_coverage_complete():
    report = _report([_session()])
    cov = report["aggregate_metrics"]["ipc_method_coverage"]
    assert cov["coverage_complete"] is True
    assert cov["missing"] == []
    assert set(cov["present"]) >= set(REQUIRED_IPC_METHODS)


def test_a5_stop_retry_no_violation_on_normal_turn():
    report = _report([_session()])
    assert report["aggregate_metrics"]["stop_retry_violation_count"] == 0


def test_a6_cross_session_isolation_ok():
    sessions = [
        _session("session-A", "cross_session_A",
                 injected_context_text="[CTX] A 内容"),
        _session("session-B", "cross_session_B",
                 injected_context_text="[CTX] B 内容"),
    ]
    report = _report(sessions)
    # 不同 scenario 不会被 pair 比对；改为同 scenario 验证可区分
    assert report["aggregate_metrics"]["cross_session_isolation_ok"] is True


def test_a6b_cross_session_isolation_distinct_same_scenario():
    sessions = [
        _session("session-A", "cross_session",
                 injected_context_text="[CTX] A 内容"),
        _session("session-B", "cross_session",
                 injected_context_text="[CTX] B 内容"),
    ]
    report = _report(sessions)
    assert report["aggregate_metrics"]["cross_session_isolation_ok"] is True
    assert report["cross_session_isolation"]["pair_count"] == 1


def test_a7_latency_p50_p95_known_values():
    # 单 session 7 步 latency: 12,8,15,6,5,9,11 → sorted: 5,6,8,9,11,12,15
    report = _report([_session()])
    lat = report["aggregate_metrics"]["latency"]
    assert lat["sample_count"] == 7
    assert lat["max_ms"] == 15.0
    assert lat["mean_ms"] == pytest.approx(sum([12, 8, 15, 6, 5, 9, 11]) / 7)


def test_a8_critical_zero_ok_true_when_no_violations():
    report = _report([_session()])
    assert report["aggregate_metrics"]["critical_zero_ok"] is True
    assert report["aggregate_metrics"]["guardrail_critical_count"] == 0
    assert report["critical_zero_ok"] is True


# ── E. fail-closed：provenance / config / latency ──────────────────


def test_e1_invalid_commit_raises():
    bad = dict(CONFIG)
    bad["implementation_commit"] = "not-a-sha"
    with pytest.raises(ValueError, match="40 位"):
        EvalSessionConfig.from_mapping(bad)


def test_e2_invalid_config_version_raises():
    bad = dict(CONFIG)
    bad["config_version"] = "d13c-wrong/v1"
    with pytest.raises(ValueError, match="config_version"):
        EvalSessionConfig.from_mapping(bad)


def test_e3_missing_latency_on_completed_step_raises():
    steps = _happy_steps()
    bad_step = dict(steps[0])
    bad_step["latency_ms"] = None
    steps[0] = bad_step
    with pytest.raises(ValueError, match="latency_ms 必须显式提供"):
        _report([_session(steps=steps)])


def test_e4_invalid_statistics_method_raises():
    bad = dict(CONFIG)
    bad["statistics_method"] = "team_defined"
    with pytest.raises(ValueError, match="statistics_method"):
        EvalSessionConfig.from_mapping(bad)


# ── S. guardrail critical / 非 critical ────────────────────────────


def test_s1_guardrail_cross_user_critical():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve", violations=["cross_user"])
    report = _report([_session(steps=steps)])
    assert report["aggregate_metrics"]["critical_zero_ok"] is False
    assert report["aggregate_metrics"]["guardrail_critical_count"] == 1
    assert "cross_user" in CRITICAL_ZERO_CATEGORIES


def test_s2_guardrail_sensitive_critical():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve", violations=["sensitive"])
    report = _report([_session(steps=steps)])
    assert report["aggregate_metrics"]["critical_zero_ok"] is False
    assert report["aggregate_metrics"]["guardrail_critical_count"] == 1


def test_s3_guardrail_unresolved_conflict_non_critical():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve",
                     violations=["unresolved_conflict"])
    report = _report([_session(steps=steps)])
    # unresolved_conflict 不在 CRITICAL_ZERO_CATEGORIES → critical_zero_ok 仍 True
    assert report["aggregate_metrics"]["critical_zero_ok"] is True
    # 但 guardrail_violation_step_count 计 1
    per_session = report["per_session_metrics"][0]
    assert per_session["guardrail_violation_step_count"] == 1
    assert per_session["guardrail_per_category"]["unresolved_conflict"]["violation_item_count"] == 1


# ── R. fail-closed：empty / duplicate / invalid config ────────────


def test_r1_no_sessions_returns_fail_closed_report():
    report = _report([])
    assert report["aggregate_metrics"] is None
    assert report["fail_closed_reasons"] == ["NO_VALID_SESSIONS"]
    assert report["per_session_metrics"] == []


def test_r2_duplicate_step_id_in_session_raises():
    steps = _happy_steps()
    steps[1] = _step("step1_prechat", "turn.finalized")  # 与 step[0] 同 step_id
    with pytest.raises(ValueError, match="重复 step_id"):
        _report([_session(steps=steps)])


def test_r3_duplicate_session_id_in_bundle_raises():
    sessions = [_session(), _session()]
    with pytest.raises(ValueError, match="重复 session_id"):
        _report(sessions)


def test_r4_invalid_stability_repeat_raises():
    bad = dict(CONFIG)
    bad["stability_repeat"] = 0
    with pytest.raises(ValueError, match="stability_repeat"):
        EvalSessionConfig.from_mapping(bad)


# ── N. edge：默认值 / stop_retry 违反 / deadline 行为 ─────────────


def test_n1_stability_repeat_default_when_absent():
    cfg = dict(CONFIG)
    del cfg["stability_repeat"]
    config = EvalSessionConfig.from_mapping(cfg)
    assert config.stability_repeat == DEFAULT_STABILITY_REPEAT
    assert config.deadline_ms == DEFAULT_DEADLINE_MS


def test_n2_retry_of_turn_id_equals_turn_id_violation():
    steps = _happy_steps(turn_id="turn-0002",
                         finalization_reason="retry",
                         retry_of_turn_id="turn-0002")  # 自违反
    report = _report([_session(steps=steps)])
    assert report["aggregate_metrics"]["stop_retry_violation_count"] == 1


def test_n3_stop_turn_missing_stop_reason_violation():
    steps = _happy_steps(finalization_reason="stop", stop_reason="")  # 缺 stop_reason
    report = _report([_session(steps=steps)])
    assert report["aggregate_metrics"]["stop_retry_violation_count"] == 1


def test_n4_deadline_timeout_correct_failed_stage_no_violation():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve",
                     response_status="timeout", stage_final="failed",
                     latency_ms=0.0, timed_out=True,
                     transitions=["idle", "querying", "failed"])
    report = _report([_session(steps=steps)])
    assert report["aggregate_metrics"]["deadline_violation_count"] == 0


def test_n5_deadline_timeout_wrong_stage_violation():
    steps = _happy_steps()
    # timed_out=True 但 stage_final=ready → 违反
    steps[0] = _step("step1_prechat", "memory.retrieve",
                     stage_final="ready", timed_out=True,
                     transitions=["idle", "querying", "ready"])
    report = _report([_session(steps=steps)])
    assert report["aggregate_metrics"]["deadline_violation_count"] == 1


# ── 边界：isolation 部分失败 / latency NaN 拒绝 ────────────────────


def test_isolation_partial_failure_lowers_pass_rate():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve", iso_mr=False)
    report = _report([_session(steps=steps)])
    # 6/7 isolation ok
    assert report["aggregate_metrics"]["isolation_pass_rate"] == pytest.approx(6 / 7)


def test_latency_nan_rejected():
    steps = _happy_steps()
    bad_step = dict(steps[0])
    bad_step["latency_ms"] = float("nan")
    steps[0] = bad_step
    with pytest.raises(ValueError, match="有限非负数"):
        _report([_session(steps=steps)])


def test_latency_bool_rejected():
    steps = _happy_steps()
    bad_step = dict(steps[0])
    bad_step["latency_ms"] = True
    steps[0] = bad_step
    with pytest.raises(ValueError, match="latency_ms 必须是有限数值"):
        _report([_session(steps=steps)])


def test_iso_field_bool_string_rejected():
    steps = _happy_steps()
    bad_step = dict(steps[0])
    bad_step["isolation"] = {
        "original_user_text_isolated": "true",  # 字符串而非 bool
        "injected_context_present": True,
        "model_request_clean": True,
    }
    steps[0] = bad_step
    with pytest.raises(ValueError, match="必须是布尔值"):
        _report([_session(steps=steps)])


def test_invalid_response_status_rejected():
    steps = _happy_steps()
    bad_step = dict(steps[0])
    bad_step["response_status"] = "weird"
    steps[0] = bad_step
    with pytest.raises(ValueError, match="response_status"):
        _report([_session(steps=steps)])


def test_invalid_guardrail_category_rejected():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve",
                     violations=["unknown_category"])
    with pytest.raises(ValueError, match="guardrail_violations"):
        _report([_session(steps=steps)])
