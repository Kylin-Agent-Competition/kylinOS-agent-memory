"""D13C 端到端会话评测账本 L1 测试（纯数据，无 VM 依赖）。

覆盖：
- 成功 bundle 各指标（step_completion / isolation / method_coverage / retry /
  cross_session / latency / critical_zero）。
- fail-closed：provenance / config / latency / 类型错误 / 无 comparable pair。
- guardrail critical（cross_user / sensitive）与非 critical（unresolved_conflict）。
- NR-1 stability cohort：A/B 双 cohort × 5 轮（同 round 不判 duplicate，
  每 cohort 独立覆盖 1..N），cross-session pair 只比较同 round A/B。
- NR-2 repeat_count 不再作为 D13C formal provenance 声明。
- NR-3 finalization_reason 不冻结业务枚举（ended/truncated/filtered/未来值均允许），
  只保留 retry 跨字段约束。
- NR-5 无 comparable pair → 顶层 fail-closed。
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
    "concurrency": 1,
    "stability_repeat": 1,
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


def _happy_steps(turn_id="turn-0001", finalization_reason="", stop_reason="",
                 retry_of_turn_id=""):
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
    session_id="session-A",
    scenario="cross_session",
    steps=None,
    injected_context_text="[CTX] A 内容",
    execution_record_id=None,
):
    return {
        "session_id": session_id,
        "execution_record_id": execution_record_id or f"rec-{session_id}",
        "scenario": scenario,
        "injected_context_text": injected_context_text,
        "steps": steps if steps is not None else _happy_steps(),
    }


def _tag(session, group="demo-stability-run-001", cohort="session-A", round_no=1):
    """给 session 增加 NR-1 轮次证据三字段（返回新 dict，不改原对象）。"""
    s = dict(session)
    s["execution_group_id"] = group
    s["stability_cohort_id"] = cohort
    s["stability_round"] = round_no
    return s


def _cohort_session(cohort, round_no, *, group="demo-stability-run-001",
                    scenario="cross_session", ctx=None, session_id=None,
                    execution_record_id=None):
    sid = session_id or f"{cohort}-round-{round_no}"
    return _tag(
        _session(
            session_id=sid,
            scenario=scenario,
            injected_context_text=ctx or f"[CTX] {cohort} round {round_no}",
            execution_record_id=execution_record_id,
        ),
        group=group, cohort=cohort, round_no=round_no,
    )


def _peer(session_a, *, peer_ctx="[CTX] B 内容"):
    """主会话 A + 同 scenario、不同 context 的干净 peer，使 bundle 含可比较 pair。"""
    a = dict(session_a)
    scen = a.get("scenario", "cross_session")
    peer = _session(
        session_id="peer-session", scenario=scen,
        injected_context_text=peer_ctx,
    )
    return [a, peer]


def _bundle(sessions, config=None):
    return {
        "config": config if config is not None else CONFIG,
        "sessions": sessions,
    }


def _report(sessions, config=None):
    cfg = EvalSessionConfig.from_mapping(config if config is not None else CONFIG)
    return compute_session_report(sessions, cfg)


def _stability_config(repeat):
    cfg = dict(CONFIG)
    cfg["stability_repeat"] = repeat
    return cfg


def _stable_ab(repeat=5, scenario="cross_session", group="demo-stability-run-001",
               ctx_a="[CTX] A", ctx_b="[CTX] B"):
    """真实形态：A/B 各固定逻辑 session_id 复用 × N 轮（每轮不同 execution_record_id）。"""
    sessions = []
    for r in range(1, repeat + 1):
        sessions.append(_cohort_session(
            "A", r, group=group, scenario=scenario,
            session_id="session-stab-0001", execution_record_id=f"stab-A-r{r}",
            ctx=f"{ctx_a} r{r}"))
        sessions.append(_cohort_session(
            "B", r, group=group, scenario=scenario,
            session_id="session-stab-0002", execution_record_id=f"stab-B-r{r}",
            ctx=f"{ctx_b} r{r}"))
    return sessions


# ── A. 成功 bundle 各指标（bundle 必须含可比较 A/B pair）──────────


def test_a1_happy_pair_all_metrics_computed():
    report = _report(_peer(_session()))
    assert report["report_version"] == REPORT_VERSION
    assert report["aggregate_metrics"] is not None
    assert report["fail_closed_reasons"] == []
    assert report["aggregate_metrics"]["session_count"] == 2


def test_a2_step_completion_rate_full():
    report = _report(_peer(_session()))
    assert report["aggregate_metrics"]["step_completion_rate"] == 1.0
    assert report["aggregate_metrics"]["total_step_count"] == 14


def test_a2b_step_completion_rate_partial():
    steps = _happy_steps()
    steps[2] = _step("step3_tool", "tool.execution", response_status="error",
                     stage_final="failed", latency_ms=0.0,
                     transitions=["idle", "sending", "failed"])
    report = _report(_peer(_session(steps=steps)))
    per_a = report["per_session_metrics"][0]
    assert per_a["step_completion_rate"] == pytest.approx(6 / 7)
    # peer 全成功 → 聚合 (6+7)/14
    assert report["aggregate_metrics"]["step_completion_rate"] == pytest.approx(13 / 14)


def test_a3_isolation_pass_rate_full():
    report = _report(_peer(_session()))
    assert report["aggregate_metrics"]["isolation_pass_rate"] == 1.0


def test_a4_ipc_method_coverage_complete():
    report = _report(_peer(_session()))
    cov = report["aggregate_metrics"]["ipc_method_coverage"]
    assert cov["coverage_complete"] is True
    assert cov["missing"] == []
    assert set(cov["present"]) >= set(REQUIRED_IPC_METHODS)


def test_a5_retry_no_violation_on_normal_turn():
    report = _report(_peer(_session()))
    assert report["aggregate_metrics"]["stop_retry_violation_count"] == 0


def test_a7_latency_p50_p95_known_values():
    # 单 session 7 步 latency: 12,8,15,6,5,9,11 → sorted: 5,6,8,9,11,12,15
    report = _report(_peer(_session()))
    lat = report["per_session_metrics"][0]["latency"]
    assert lat["sample_count"] == 7
    assert lat["p50_ms"] == 9.0
    assert lat["p95_ms"] == 15.0
    assert lat["max_ms"] == 15.0
    assert lat["mean_ms"] == pytest.approx(sum([12, 8, 15, 6, 5, 9, 11]) / 7)


def test_a8_critical_zero_ok_true_when_no_violations():
    report = _report(_peer(_session()))
    assert report["aggregate_metrics"]["critical_zero_ok"] is True
    assert report["aggregate_metrics"]["guardrail_critical_count"] == 0
    assert report["critical_zero_ok"] is True


# ── NR-2：repeat_count 不再是 D13C formal provenance ───────────────


def test_nr2_config_has_no_repeat_count_field():
    cfg = EvalSessionConfig.from_mapping(CONFIG)
    assert not hasattr(cfg, "repeat_count")
    report = _report(_peer(_session()))
    assert "repeat_count" not in report["config"]


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
    report = _report(_peer(_session(steps=steps)))
    assert report["aggregate_metrics"]["critical_zero_ok"] is False
    assert report["aggregate_metrics"]["guardrail_critical_count"] == 1
    assert "cross_user" in CRITICAL_ZERO_CATEGORIES


def test_s2_guardrail_sensitive_critical():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve", violations=["sensitive"])
    report = _report(_peer(_session(steps=steps)))
    assert report["aggregate_metrics"]["critical_zero_ok"] is False
    assert report["aggregate_metrics"]["guardrail_critical_count"] == 1


def test_s3_guardrail_unresolved_conflict_non_critical():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve",
                     violations=["unresolved_conflict"])
    report = _report(_peer(_session(steps=steps)))
    assert report["aggregate_metrics"]["critical_zero_ok"] is True
    per_a = report["per_session_metrics"][0]
    assert per_a["guardrail_violation_step_count"] == 1
    assert per_a["guardrail_per_category"]["unresolved_conflict"]["violation_item_count"] == 1


# ── R. fail-closed：empty / duplicate / invalid config ────────────


def test_r1_no_sessions_returns_fail_closed_report():
    report = _report([])
    assert report["aggregate_metrics"] is None
    assert report["fail_closed_reasons"] == ["NO_VALID_SESSIONS"]
    assert report["per_session_metrics"] == []


def test_r2_duplicate_step_id_in_session_raises():
    steps = _happy_steps()
    steps[1] = _step("step1_prechat", "turn.finalized")
    with pytest.raises(ValueError, match="重复 step_id"):
        _report([_session(steps=steps)])


def test_r3_duplicate_execution_record_id_in_bundle_raises():
    sessions = [
        _session("session-A", execution_record_id="rec-dup"),
        _session("session-B", execution_record_id="rec-dup"),
    ]
    with pytest.raises(ValueError, match="execution_record_id"):
        _report(sessions)


def test_r4_invalid_stability_repeat_raises():
    bad = dict(CONFIG)
    bad["stability_repeat"] = 0
    with pytest.raises(ValueError, match="stability_repeat"):
        EvalSessionConfig.from_mapping(bad)


def test_n1_stability_repeat_default_when_absent():
    cfg = dict(CONFIG)
    del cfg["stability_repeat"]
    config = EvalSessionConfig.from_mapping(cfg)
    assert config.stability_repeat == DEFAULT_STABILITY_REPEAT
    assert config.deadline_ms == DEFAULT_DEADLINE_MS


# ── N. retry / deadline 边界（NR-3 后只保留 retry 语义约束）────────


def test_n2_retry_of_turn_id_equals_turn_id_violation():
    steps = _happy_steps(turn_id="turn-0002", finalization_reason="retry",
                         retry_of_turn_id="turn-0002")
    report = _report(_peer(_session(steps=steps)))
    assert report["aggregate_metrics"]["stop_retry_violation_count"] == 1


def test_nr3_retry_missing_parent_still_violation():
    steps = _happy_steps(finalization_reason="retry", retry_of_turn_id="")
    report = _report(_peer(_session(steps=steps)))
    assert report["aggregate_metrics"]["stop_retry_violation_count"] == 1


def test_n4_deadline_timeout_correct_failed_stage_no_violation():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve",
                     response_status="timeout", stage_final="failed",
                     latency_ms=0.0, timed_out=True,
                     transitions=["idle", "querying", "failed"])
    report = _report(_peer(_session(steps=steps)))
    assert report["aggregate_metrics"]["deadline_violation_count"] == 0


def test_n5b_deadline_timeout_wrong_transition_tail_violation():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve",
                     response_status="timeout", stage_final="failed",
                     latency_ms=0.0, timed_out=True,
                     transitions=["idle", "querying", "ready"])
    report = _report(_peer(_session(steps=steps)))
    assert report["aggregate_metrics"]["deadline_violation_count"] == 1


# ── NR-3：finalization_reason 不冻结业务枚举 ───────────────────────


@pytest.mark.parametrize("reason", ["ended", "truncated", "filtered", "custom_future_value"])
def test_finalization_reason_open_enum_allowed(reason):
    steps = _happy_steps(finalization_reason=reason, stop_reason="stop")
    report = _report(_peer(_session(steps=steps)))
    assert report["aggregate_metrics"]["stop_retry_violation_count"] == 0
    assert report["aggregate_metrics"] is not None


@pytest.mark.parametrize("reason,stop", [
    ("ended", "stop"),
    ("truncated", "length"),
    ("filtered", "content_filter"),
    ("ended", "tool_use"),
])
def test_finalization_reason_cpp_s2_combos_allowed(reason, stop):
    # 与 C++ S2 一致：finalization_reason 与 stop_reason 是两个独立体系
    steps = _happy_steps(finalization_reason=reason, stop_reason=stop)
    report = _report(_peer(_session(steps=steps)))
    assert report["aggregate_metrics"]["stop_retry_violation_count"] == 0


def test_finalization_reason_non_string_rejected():
    steps = _happy_steps()
    steps[1] = _step("step2_postturn", "turn.finalized",
                     finalization_reason=123)
    with pytest.raises(ValueError, match="必须是字符串"):
        _report([_session(steps=steps)])


# ── R3：状态组合矩阵（本轮不重写，保持通过）───────────────────────


def test_state_combo_error_ready_rejected():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve",
                     response_status="error", stage_final="ready")
    with pytest.raises(ValueError, match="状态组合"):
        _report([_session(steps=steps)])


def test_state_combo_timeout_ready_rejected():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve",
                     response_status="timeout", stage_final="ready",
                     timed_out=True)
    with pytest.raises(ValueError, match="状态组合"):
        _report([_session(steps=steps)])


def test_state_combo_timeout_timed_out_false_rejected():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve",
                     response_status="timeout", stage_final="failed",
                     latency_ms=0.0, timed_out=False,
                     transitions=["idle", "querying", "failed"])
    with pytest.raises(ValueError, match="状态组合"):
        _report([_session(steps=steps)])


def test_state_combo_disconnected_completed_rejected():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve",
                     response_status="disconnected", stage_final="completed")
    with pytest.raises(ValueError, match="状态组合"):
        _report([_session(steps=steps)])


def test_state_combo_unsupported_method_completed_rejected():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve",
                     response_status="unsupported_method",
                     stage_final="completed")
    with pytest.raises(ValueError, match="状态组合"):
        _report([_session(steps=steps)])


def test_state_combo_awaiting_confirmation_requires_forget_preview():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve",
                     stage_final="awaiting_confirmation")
    with pytest.raises(ValueError, match="状态组合"):
        _report([_session(steps=steps)])


def test_state_combo_error_failed_allowed_not_completed():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve",
                     response_status="error", stage_final="failed",
                     latency_ms=0.0, transitions=["idle", "sending", "failed"])
    report = _report(_peer(_session(steps=steps)))
    per_a = report["per_session_metrics"][0]
    assert per_a["completed_step_count"] == 6


# ── NR-1：stability cohort（A/B 双 cohort × N 轮）──────────────────


def test_stability_two_cohorts_5_rounds_pass():
    sessions = _stable_ab(5)
    report = _report(sessions, _stability_config(5))
    assert report["aggregate_metrics"]["session_count"] == 10
    assert report["aggregate_metrics"]["cross_session_pair_count"] == 5
    assert report["aggregate_metrics"]["cross_session_isolation_ok"] is True
    assert report["fail_closed_reasons"] == []


def test_stability_same_round_across_cohorts_allowed():
    # repeat=1：A1/B1 同 round 不同 cohort → 合法（不判 duplicate）
    sessions = [_cohort_session("A", 1), _cohort_session("B", 1)]
    report = _report(sessions, _stability_config(1))
    assert report["aggregate_metrics"]["session_count"] == 2
    assert report["aggregate_metrics"]["cross_session_pair_count"] == 1
    assert report["fail_closed_reasons"] == []


def test_stability_duplicate_round_inside_same_cohort_fail():
    a = [_cohort_session("A", r) for r in (1, 2, 3, 4, 5)]
    a.append(_tag(_session(session_id="A-extra-3", scenario="cross_session",
                           injected_context_text="[CTX] A dup r3"),
                  cohort="A", round_no=3))
    b = [_cohort_session("B", r) for r in range(1, 6)]
    with pytest.raises(ValueError, match="duplicate"):
        _report(a + b, _stability_config(5))


def test_stability_missing_round_in_cohort_b_fail():
    a = [_cohort_session("A", r) for r in range(1, 6)]
    b = [_cohort_session("B", r) for r in (1, 2, 3, 5)]
    with pytest.raises(ValueError, match="missing"):
        _report(a + b, _stability_config(5))


def test_stability_out_of_range_round_fail():
    a = [_cohort_session("A", r) for r in range(1, 7)]  # round 6 越界
    b = [_cohort_session("B", r) for r in range(1, 6)]
    with pytest.raises(ValueError, match="out_of_range"):
        _report(a + b, _stability_config(5))


def test_stability_mixed_tagged_untagged_fail():
    sessions = [_cohort_session("A", 1), _session()]
    with pytest.raises(ValueError, match="混用"):
        _report(sessions, _stability_config(1))


def test_stability_round0_rejected():
    s = _tag(_session(), round_no=0)
    with pytest.raises(ValueError, match="stability_round"):
        _report([s], _stability_config(1))


def test_stability_evidence_three_fields_all_or_none():
    s = _session()
    s["execution_group_id"] = "g"
    s["stability_cohort_id"] = "A"  # 缺 stability_round
    with pytest.raises(ValueError, match="三项必须同时"):
        _report([s], _stability_config(1))


# ── NR-1：cross-session pair 按 round 对齐 ──────────────────────────


def test_cross_session_pairs_are_round_scoped():
    # 3 轮 A/B → 只应有 3 个 pair（A_r vs B_r），不是 9 个全两两
    sessions = _stable_ab(3)
    report = _report(sessions, _stability_config(3))
    iso = report["cross_session_isolation"]
    assert iso["pair_count"] == 3
    for pair in iso["pairs"]:
        assert pair["cohort_a"] == "A"
        assert pair["cohort_b"] == "B"
        assert pair["session_a"] == "session-stab-0001"
        assert pair["session_b"] == "session-stab-0002"
        assert pair["stability_round"] in (1, 2, 3)
    assert report["aggregate_metrics"]["cross_session_isolation_ok"] is True


def test_cross_session_same_cohort_cross_round_not_compared():
    # 只有 cohort A 1..5 → 无跨 cohort pair → 顶层 fail-closed
    sessions = [_cohort_session("A", r) for r in range(1, 6)]
    report = _report(sessions, _stability_config(5))
    assert report["aggregate_metrics"] is None
    assert report["fail_closed_reasons"] == ["NO_COMPARABLE_CROSS_SESSION_PAIR"]


def test_cross_session_same_round_a_b_equal_fail():
    a = _tag(_session(session_id="A-1", injected_context_text="[CTX] SAME"),
             cohort="A", round_no=1)
    b = _tag(_session(session_id="B-1", injected_context_text="[CTX] SAME"),
             cohort="B", round_no=1)
    report = _report([a, b], _stability_config(1))
    assert report["aggregate_metrics"] is not None
    assert report["aggregate_metrics"]["cross_session_isolation_ok"] is False


def test_cross_session_empty_context_fail():
    a = _tag(_session(session_id="A-1", injected_context_text="[CTX] A"),
             cohort="A", round_no=1)
    b = _tag(_session(session_id="B-1", injected_context_text=""),
             cohort="B", round_no=1)
    report = _report([a, b], _stability_config(1))
    assert report["aggregate_metrics"]["cross_session_isolation_ok"] is False


# ── NR-5：无 comparable pair → 顶层 fail-closed ────────────────────


def test_no_comparable_pair_single_session_top_level_fail_closed():
    report = _report([_session()])
    assert report["aggregate_metrics"] is None
    assert report["fail_closed_reasons"] == ["NO_COMPARABLE_CROSS_SESSION_PAIR"]


def test_no_comparable_pair_different_scenarios_top_level_fail_closed():
    sessions = [
        _session("session-A", "scenario_A", injected_context_text="[CTX] A"),
        _session("session-B", "scenario_B", injected_context_text="[CTX] B"),
    ]
    report = _report(sessions)
    assert report["aggregate_metrics"] is None
    assert report["fail_closed_reasons"] == ["NO_COMPARABLE_CROSS_SESSION_PAIR"]


# ── isolation partial / parse 拒绝（不涉及 pair 计算，单 session 即可）──


def test_isolation_partial_failure_lowers_pass_rate():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve", iso_mr=False)
    report = _report(_peer(_session(steps=steps)))
    per_a = report["per_session_metrics"][0]
    assert per_a["isolation_pass_rate"] == pytest.approx(6 / 7)


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
        "original_user_text_isolated": "true",
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

# ── P1-01：execution_record_id 唯一键 / 真实 session_id 跨轮复用 ────


def test_p1_01_real_fixed_session_id_across_5_rounds_pass():
    # 真实形态：A/B 各固定 session_id × 5 轮，每轮不同 execution_record_id
    sessions = _stable_ab(5)
    ids = [s["session_id"] for s in sessions]
    assert ids.count("session-stab-0001") == 5
    assert ids.count("session-stab-0002") == 5
    recs = [s["execution_record_id"] for s in sessions]
    assert len(set(recs)) == 10
    report = _report(sessions, _stability_config(5))
    assert report["aggregate_metrics"] is not None
    assert report["aggregate_metrics"]["cross_session_pair_count"] == 5
    assert report["fail_closed_reasons"] == []


def test_p1_01_missing_execution_record_id_rejected():
    s = _session()
    del s["execution_record_id"]
    with pytest.raises(ValueError, match="execution_record_id"):
        _report([s])


def test_p1_01_duplicate_execution_record_id_fails():
    sessions = [
        _session("session-A", execution_record_id="rec-x"),
        _session("session-B", execution_record_id="rec-x"),
    ]
    with pytest.raises(ValueError, match="execution_record_id"):
        _report(sessions)


def test_p1_01_duplicate_position_group_cohort_round_session_fails():
    # 同一执行位置 (group, cohort, round, session) 重复提交两条 evidence
    a1 = _cohort_session("A", 1, session_id="session-stab-0001",
                         execution_record_id="a1")
    a1_dup = _cohort_session("A", 1, session_id="session-stab-0001",
                             execution_record_id="a1-dup")
    b1 = _cohort_session("B", 1, session_id="session-stab-0002",
                         execution_record_id="b1")
    with pytest.raises(ValueError, match="同一执行位置"):
        _report([a1, a1_dup, b1], _stability_config(1))


# ── P1-02：step.deadline_ms 与 config.deadline_ms 绑定 ───────────────


def test_p1_02_deadline_all_match_pass():
    sessions = _peer(_session())
    report = _report(sessions)
    assert report["aggregate_metrics"] is not None


def test_p1_02_single_step_mismatch_fail_closed():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve", deadline_ms=3000)
    with pytest.raises(ValueError, match="DEADLINE_CONFIG_EVIDENCE_MISMATCH"):
        _report(_peer(_session(steps=steps)))


def test_p1_02_last_round_mismatch_fail_closed():
    sessions = _stable_ab(5)
    for s in sessions:
        if s["execution_record_id"] == "stab-A-r5":
            steps = s["steps"]
            steps[0] = dict(steps[0])
            steps[0]["deadline_ms"] = 3000
            s["steps"] = steps
    with pytest.raises(ValueError, match="DEADLINE_CONFIG_EVIDENCE_MISMATCH"):
        _report(sessions, _stability_config(5))


def test_p1_02_cohort_b_round3_mismatch_fail_closed():
    sessions = _stable_ab(5)
    for s in sessions:
        if s["execution_record_id"] == "stab-B-r3":
            steps = s["steps"]
            steps[0] = dict(steps[0])
            steps[0]["deadline_ms"] = 6000
            s["steps"] = steps
    with pytest.raises(ValueError, match="DEADLINE_CONFIG_EVIDENCE_MISMATCH"):
        _report(sessions, _stability_config(5))


def test_p1_02_config_3000_all_steps_3000_pass():
    cfg = dict(CONFIG)
    cfg["deadline_ms"] = 3000
    steps = _happy_steps()
    for st in steps:
        st["deadline_ms"] = 3000
    a = _session(session_id="A-3000", steps=steps, injected_context_text="[CTX] A")
    b = _session(session_id="B-3000", steps=steps, injected_context_text="[CTX] B")
    report = _report([a, b], cfg)
    assert report["aggregate_metrics"] is not None


def test_p1_02_deadline_bool_rejected():
    steps = _happy_steps()
    steps[0] = _step("step1_prechat", "memory.retrieve", deadline_ms=True)
    with pytest.raises(ValueError, match="deadline_ms 必须是整数"):
        _report([_session(steps=steps)])
