"""D13C 端到端会话评测账本：冻结口径下的会话指标计算与护栏统计（C 轨）。

定位
----
本模块为 C 轨（memory-client）端到端会话评测账本。它消费会话证据 bundle JSON
（跨会话 / Tool / Stop-Retry / UX 各场景的逐步请求、响应、stage 迁移、原文隔离
与护栏违规记录），按冻结口径计算会话级指标；provenance（dataset/gold 哈希、
commit、environment、evidence、采样参数、stability_repeat、deadline_ms）未完整
绑定或 config_version 不符时 fail-closed，不输出任何可被当作正式指标的数值。

本模块只消费数据、不执行会话、不生产 Gold；真实会话执行需在麒麟 VM 上由
memory-client + Mock Gateway 或已部署的 D 轨 Gateway 完成，未取得 VM 实测前
一切 Runtime / 正式达标结论必须标 UNVERIFIED。

冻结口径来源
------------
- 台账 D13-C：运行端到端跨会话 / Tool / Stop-Retry / UX 会话；收集 UI、请求、
  日志与数据库证据；复测主演示稳定性。
- ADR-010 turn.finalized：Post-Turn 写链路；finalization_reason=retry 必须携带
  metadata.retry_of_turn_id 且 ≠ turn_id（TB-D6C-04）。
- memory_context.v1.json：Pre-Chat 注入契约；injection_status ∈
  {prepared/degraded/failed/skipped}，failed/skipped 不产生伪 Context。
- FRZ-IPC-006：envelope 长度前缀 JSON；客户端死线 5000ms。
- D11-C test_d11c_e2e_orchestrator.cpp：5 步主演示编排（Pre-Chat / Post-Turn /
  Tool / 知识+冲突+生命周期 / 精准遗忘）的 L0 Mock 契约。
- D13-B formal_eval.py：fail-closed 与 provenance 强校验模板。

设计要点（fail-closed）
-----------------------
- provenance 字段缺失 / commit 非 40 hex / sha256 非 64 hex /
  config_version != "d13c-session-eval-config/v1" → INVALID_PROVENANCE，指标 null。
- 任一完成 step 缺 latency_ms 或非有限非负数 → MISSING_LATENCY，该会话指标 null。
- guardrail critical（cross_user / sensitive / unresolved_conflict）> 0 →
  critical_zero_ok=False，仍输出指标但 Critical 标记。
- 0 个有效 session → NO_VALID_SESSIONS，聚合指标 null。
- 重复 step_id（会话内）/ session_id（bundle 内）→ DUPLICATE_* fail-closed。
- stability_repeat < 1 / deadline_ms <= 0 / repeat_count < 1 → INVALID_CONFIG。
- stop_retry 语义违反（retry 缺 retry_of_turn_id / retry_of_turn_id=turn_id /
  stop turn 缺 stop_reason）计入 stop_retry_violation_count，不 null 整体指标
  （便于定位），但 critical_zero_ok 不受其影响。
- 延迟只接受有限非负数（拒绝 bool / NaN / ±Infinity）。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

FROZEN_CONFIG_VERSION = "d13c-session-eval-config/v1"
REPORT_VERSION = "d13c-session-eval-report/v1"
DEFAULT_DEADLINE_MS = 5000
DEFAULT_STABILITY_REPEAT = 5

# D11-C 5 步主演示编排必须出现的 IPC 方法集合（缺一即 method_coverage 不完整）
REQUIRED_IPC_METHODS: tuple[str, ...] = (
    "memory.retrieve",
    "turn.finalized",
    "tool.execution",
    "conflict.compare",
    "lifecycle.status",
    "forget.preview",
    "forget.execute",
)

# 负向护栏类别（C 轨会话视角）；critical_zero 要求前两类 item=0
GUARDRAIL_CATEGORIES: tuple[str, ...] = (
    "cross_user",
    "sensitive",
    "unresolved_conflict",
)
CRITICAL_ZERO_CATEGORIES: tuple[str, ...] = (
    "cross_user",
    "sensitive",
)

# step 完成态：stage_final 落在此集合视为该步成功完成。
# awaiting_confirmation 是 forget.preview 的成功终态（等待用户确认后进入 execute），
# 不是失败；failed/timeout 才是失败终态。
COMPLETED_STAGE_FINALS: frozenset[str] = frozenset(
    {"ready", "completed", "awaiting_confirmation"}
)
# step 失败态：用于 deadline timeout 路径校验（timed_out=True 必须 stage_final=failed）
FAILED_STAGE_FINALS: frozenset[str] = frozenset({"failed", "timeout"})

_VALID_RESPONSE_STATUSES: frozenset[str] = frozenset(
    {"ok", "error", "unsupported_method", "timeout", "disconnected"}
)
_VALID_FINALIZATION_REASONS: frozenset[str] = frozenset(
    {"", "normal", "stop", "retry", "cancelled", "length"}
)

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

SUPPORTED_STATISTICS_METHODS = frozenset({"p50_and_p95", "p50", "p95"})


@dataclass(frozen=True)
class EvalSessionConfig:
    """C 轨会话评测运行绑定配置（fail-closed：provenance 与采样参数必须显式完整）。"""

    config_version: str
    dataset_version: str
    gold_label_version: str
    implementation_commit: str
    environment: str
    evidence_reference: str
    dataset_sha256: str
    gold_sha256: str
    statistics_method: str
    warmup_count: int
    repeat_count: int
    concurrency: int
    stability_repeat: int
    deadline_ms: int

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "EvalSessionConfig":
        config_version = str(raw.get("config_version", "")).strip()
        if config_version != FROZEN_CONFIG_VERSION:
            raise ValueError(
                f"config_version 必须为冻结值 {FROZEN_CONFIG_VERSION!r}，"
                f"实际 {config_version!r}"
            )
        normalized: dict[str, Any] = {"config_version": config_version}
        for field_name, raw_key in (
            ("dataset_version", "dataset_version"),
            ("gold_label_version", "gold_label_version"),
            ("environment", "environment"),
            ("evidence_reference", "evidence_reference"),
        ):
            value = str(raw.get(raw_key, "")).strip()
            if not value or value.upper() == "UNKNOWN":
                raise ValueError(
                    f"正式会话评测必须绑定 {raw_key!r}，不得为空或 UNKNOWN"
                )
            normalized[field_name] = value
        commit = str(raw.get("implementation_commit", "")).strip()
        if not _GIT_SHA_RE.match(commit):
            raise ValueError("implementation_commit 必须是 40 位小写十六进制 Git SHA")
        normalized["implementation_commit"] = commit
        for raw_key in ("dataset_sha256", "gold_sha256"):
            digest = str(raw.get(raw_key, "")).strip()
            if not _SHA256_RE.match(digest):
                raise ValueError(
                    f"{raw_key} 必须是非空 64 位小写十六进制 SHA-256"
                )
            normalized[raw_key] = digest

        statistics_method = str(raw.get("statistics_method", "")).strip().lower()
        if not statistics_method or statistics_method.upper() in ("UNKNOWN", "PENDING"):
            raise ValueError("statistics_method 必须显式登记，不得为 UNKNOWN/PENDING")
        if statistics_method not in SUPPORTED_STATISTICS_METHODS:
            raise ValueError(
                f"不支持的 statistics_method {statistics_method!r}；"
                f"支持 {sorted(SUPPORTED_STATISTICS_METHODS)}"
            )
        normalized["statistics_method"] = statistics_method

        normalized["warmup_count"] = cls._int_field(raw, "warmup_count", minimum=0)
        normalized["repeat_count"] = cls._int_field(raw, "repeat_count", minimum=1)
        normalized["concurrency"] = cls._int_field(raw, "concurrency", minimum=1)
        # stability_repeat：稳定性复跑轮数（D13-C「复测主演示稳定性」），至少 1
        if "stability_repeat" in raw:
            normalized["stability_repeat"] = cls._int_field(
                raw, "stability_repeat", minimum=1
            )
        else:
            normalized["stability_repeat"] = DEFAULT_STABILITY_REPEAT
        # deadline_ms：客户端死线（FRZ-IPC-006 默认 5000ms），必须正数
        if "deadline_ms" in raw:
            normalized["deadline_ms"] = cls._int_field(raw, "deadline_ms", minimum=1)
        else:
            normalized["deadline_ms"] = DEFAULT_DEADLINE_MS
        return cls(**normalized)

    @staticmethod
    def _int_field(raw: Mapping[str, Any], key: str, minimum: int) -> int:
        if key not in raw:
            raise ValueError(f"正式会话评测必须显式提供 {key!r}")
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} 必须是整数（不接受 bool/浮点/字符串）")
        if value < minimum:
            raise ValueError(f"{key} 必须 >= {minimum}")
        return value


@dataclass(frozen=True)
class StepRecord:
    """会话中一步 IPC 交互的证据记录（formal 模式字段全部显式提供）。"""

    step_id: str
    method: str
    response_status: str
    stage_final: str
    stage_transitions: tuple[str, ...]
    latency_ms: float
    isolation_original_user_text: bool
    isolation_injected_context_present: bool
    isolation_model_request_clean: bool
    guardrail_violations: tuple[str, ...]
    deadline_ms: int
    timed_out: bool
    finalization_reason: str
    stop_reason: str
    retry_of_turn_id: str
    turn_id: str

    @property
    def isolation_ok(self) -> bool:
        return (
            self.isolation_original_user_text
            and self.isolation_injected_context_present
            and self.isolation_model_request_clean
        )

    @property
    def completed(self) -> bool:
        return self.stage_final in COMPLETED_STAGE_FINALS

    @classmethod
    def from_mapping(cls, position: int, raw: Mapping[str, Any]) -> "StepRecord":
        if not isinstance(raw, dict):
            raise ValueError(f"steps[{position}] 必须是对象")
        for key in ("step_id", "method", "response_status", "stage_final"):
            value = str(raw.get(key, "")).strip()
            if not value:
                raise ValueError(f"steps[{position}] 缺少非空字段 {key!r}")
            if key == "response_status" and value not in _VALID_RESPONSE_STATUSES:
                raise ValueError(
                    f"steps[{position}] 非法 response_status {value!r}"
                )
            # stage_final 不限枚举（ViewModel 可能引入新状态），但必须非空
        step_id = str(raw["step_id"]).strip()
        method = str(raw["method"]).strip()
        response_status = str(raw["response_status"]).strip()
        stage_final = str(raw["stage_final"]).strip()

        raw_transitions = raw.get("stage_transitions", [])
        if not isinstance(raw_transitions, list):
            raise ValueError(f"steps[{position}].stage_transitions 必须是数组")
        transitions = tuple(str(t).strip() for t in raw_transitions)

        # latency_ms：完成态 step 必须有 latency；失败态可为 0 但仍必须有限非负
        latency = cls._parse_latency(raw.get("latency_ms"), position)
        # 完成态 step 必须有正向 latency 记录（>0 表示真实经过时间；=0 仅允许失败态）
        if stage_final in COMPLETED_STAGE_FINALS and latency <= 0:
            raise ValueError(
                f"steps[{position}] 完成态 stage_final={stage_final!r} "
                f"必须提供正向 latency_ms（>0），实际 {latency!r}"
            )

        isolation = raw.get("isolation", {})
        if not isinstance(isolation, dict):
            raise ValueError(f"steps[{position}].isolation 必须是对象")
        iso_ou = cls._parse_bool(
            isolation.get("original_user_text_isolated"),
            f"steps[{position}].isolation.original_user_text_isolated",
        )
        iso_ic = cls._parse_bool(
            isolation.get("injected_context_present"),
            f"steps[{position}].isolation.injected_context_present",
        )
        iso_mr = cls._parse_bool(
            isolation.get("model_request_clean"),
            f"steps[{position}].isolation.model_request_clean",
        )

        raw_violations = raw.get("guardrail_violations", [])
        if not isinstance(raw_violations, list):
            raise ValueError(f"steps[{position}].guardrail_violations 必须是数组")
        violations: list[str] = []
        for v in raw_violations:
            v_str = str(v).strip()
            if v_str not in GUARDRAIL_CATEGORIES:
                raise ValueError(
                    f"steps[{position}].guardrail_violations 含非法类别 {v_str!r}"
                )
            violations.append(v_str)

        deadline_ms = raw.get("deadline_ms")
        if deadline_ms is None:
            deadline_ms = DEFAULT_DEADLINE_MS
        if isinstance(deadline_ms, bool) or not isinstance(deadline_ms, int):
            raise ValueError(f"steps[{position}].deadline_ms 必须是整数")
        if deadline_ms <= 0:
            raise ValueError(f"steps[{position}].deadline_ms 必须 > 0")

        timed_out = cls._parse_bool(raw.get("timed_out"), f"steps[{position}].timed_out")
        finalization_reason = str(raw.get("finalization_reason", "")).strip()
        if finalization_reason not in _VALID_FINALIZATION_REASONS:
            raise ValueError(
                f"steps[{position}] 非法 finalization_reason {finalization_reason!r}"
            )
        stop_reason = str(raw.get("stop_reason", "")).strip()
        retry_of_turn_id = str(raw.get("retry_of_turn_id", "")).strip()
        turn_id = str(raw.get("turn_id", "")).strip()

        return cls(
            step_id=step_id,
            method=method,
            response_status=response_status,
            stage_final=stage_final,
            stage_transitions=transitions,
            latency_ms=latency,
            isolation_original_user_text=iso_ou,
            isolation_injected_context_present=iso_ic,
            isolation_model_request_clean=iso_mr,
            guardrail_violations=tuple(violations),
            deadline_ms=deadline_ms,
            timed_out=timed_out,
            finalization_reason=finalization_reason,
            stop_reason=stop_reason,
            retry_of_turn_id=retry_of_turn_id,
            turn_id=turn_id,
        )

    @staticmethod
    def _parse_latency(value: Any, position: int) -> float:
        """latency 只接受有限非负数（拒绝 bool / NaN / ±Infinity）。"""
        if value is None:
            raise ValueError(f"steps[{position}].latency_ms 必须显式提供")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"steps[{position}].latency_ms 必须是有限数值")
        latency = float(value)
        if not math.isfinite(latency) or latency < 0:
            raise ValueError(f"steps[{position}].latency_ms 必须是有限非负数")
        return latency

    @staticmethod
    def _parse_bool(value: Any, label: str) -> bool:
        if not isinstance(value, bool):
            raise ValueError(f"{label} 必须是布尔值（不接受字符串/0/1）")
        return value


@dataclass(frozen=True)
class SessionRecord:
    """一条已执行会话：session_id + scenario + steps + injected_context_text。"""

    session_id: str
    scenario: str
    steps: tuple[StepRecord, ...]
    injected_context_text: str

    @classmethod
    def from_mapping(cls, position: int, raw: Mapping[str, Any]) -> "SessionRecord":
        if not isinstance(raw, dict):
            raise ValueError(f"sessions[{position}] 必须是对象")
        session_id = str(raw.get("session_id", "")).strip()
        scenario = str(raw.get("scenario", "")).strip()
        if not session_id or not scenario:
            raise ValueError(
                f"sessions[{position}] 缺少非空 session_id / scenario"
            )
        raw_steps = raw.get("steps", [])
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError(f"sessions[{position}].steps 必须是非空数组")
        steps: list[StepRecord] = []
        seen_step_ids: set[str] = set()
        for idx, step_raw in enumerate(raw_steps):
            step = StepRecord.from_mapping(idx, step_raw)
            if step.step_id in seen_step_ids:
                raise ValueError(
                    f"sessions[{position}] 存在重复 step_id {step.step_id!r}"
                )
            seen_step_ids.add(step.step_id)
            steps.append(step)
        injected = str(raw.get("injected_context_text", "")).strip()
        # injected_context_text 允许空字符串（failed/skipped 注入场景），
        # 但跨会话隔离比对需要非空；空串在 cross_session_isolation 计算时单独处理。
        return cls(
            session_id=session_id,
            scenario=scenario,
            steps=tuple(steps),
            injected_context_text=injected,
        )


# ── 指标计算 ──────────────────────────────────────────────────────────────


def _quantile(sorted_values: list[float], q: float) -> Optional[float]:
    """简单最近邻分位（与 retrieval.evaluation 口径一致）：空列表返回 None。"""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = max(0, min(len(sorted_values) - 1, int(round(q * (len(sorted_values) - 1)))))
    return sorted_values[idx]


def _latency_stats(latencies: list[float]) -> dict[str, Optional[float]]:
    sorted_vals = sorted(latencies)
    if not sorted_vals:
        return {
            "p50_ms": None,
            "p95_ms": None,
            "mean_ms": None,
            "max_ms": None,
            "sample_count": 0,
        }
    return {
        "p50_ms": _quantile(sorted_vals, 0.50),
        "p95_ms": _quantile(sorted_vals, 0.95),
        "mean_ms": sum(sorted_vals) / len(sorted_vals),
        "max_ms": sorted_vals[-1],
        "sample_count": len(sorted_vals),
    }


def _session_metrics(session: SessionRecord) -> dict[str, Any]:
    """计算单会话指标（假定 session 已通过 fail-closed 校验）。"""
    steps = session.steps
    total = len(steps)
    completed = sum(1 for s in steps if s.completed)
    isolation_ok = sum(1 for s in steps if s.isolation_ok)

    # 护栏：会话级违规 step 唯一计数 + per-category item 计数
    per_category: dict[str, dict[str, Any]] = {
        cat: {"violating_step_ids": set(), "violation_item_count": 0}
        for cat in GUARDRAIL_CATEGORIES
    }
    violating_step_ids: set[str] = set()
    for step in steps:
        for cat in step.guardrail_violations:
            per_category[cat]["violating_step_ids"].add(step.step_id)
            per_category[cat]["violation_item_count"] += 1
            violating_step_ids.add(step.step_id)
    critical_item_count = sum(
        per_category[cat]["violation_item_count"] for cat in CRITICAL_ZERO_CATEGORIES
    )

    # IPC 方法覆盖
    present_methods = {s.method for s in steps}
    missing_methods = [m for m in REQUIRED_IPC_METHODS if m not in present_methods]

    # stop_retry 语义违反计数
    stop_retry_violations: list[str] = []
    for step in steps:
        if step.method == "turn.finalized":
            if step.finalization_reason == "retry":
                if not step.retry_of_turn_id:
                    stop_retry_violations.append(
                        f"{step.step_id}: retry 缺 retry_of_turn_id"
                    )
                elif step.retry_of_turn_id == step.turn_id:
                    stop_retry_violations.append(
                        f"{step.step_id}: retry_of_turn_id == turn_id"
                    )
            elif step.finalization_reason == "stop":
                if not step.stop_reason:
                    stop_retry_violations.append(
                        f"{step.step_id}: stop 缺 stop_reason"
                    )

    # deadline 行为违反：timed_out=True 必须 stage_final ∈ failed 且迁移末态为 failed
    deadline_violations: list[str] = []
    for step in steps:
        if step.timed_out:
            if step.stage_final not in FAILED_STAGE_FINALS:
                deadline_violations.append(
                    f"{step.step_id}: timed_out 但 stage_final={step.stage_final!r}"
                )
            elif step.stage_transitions and step.stage_transitions[-1] not in FAILED_STAGE_FINALS:
                deadline_violations.append(
                    f"{step.step_id}: timed_out 但 stage_transitions 末态非 failed"
                )

    latencies = [s.latency_ms for s in steps if s.latency_ms > 0]

    return {
        "session_id": session.session_id,
        "scenario": session.scenario,
        "step_count": total,
        "step_completion_rate": completed / total if total else None,
        "completed_step_count": completed,
        "isolation_pass_rate": isolation_ok / total if total else None,
        "isolation_ok_step_count": isolation_ok,
        "guardrail_critical_count": critical_item_count,
        "guardrail_violation_step_count": len(violating_step_ids),
        "guardrail_per_category": {
            cat: {
                "violation_step_count": len(per_category[cat]["violating_step_ids"]),
                "violation_item_count": per_category[cat]["violation_item_count"],
            }
            for cat in GUARDRAIL_CATEGORIES
        },
        "ipc_method_coverage": {
            "required": list(REQUIRED_IPC_METHODS),
            "present": sorted(present_methods),
            "missing": missing_methods,
            "coverage_complete": len(missing_methods) == 0,
        },
        "stop_retry_violation_count": len(stop_retry_violations),
        "stop_retry_violations": stop_retry_violations,
        "deadline_violation_count": len(deadline_violations),
        "deadline_violations": deadline_violations,
        "latency": _latency_stats(latencies),
    }


def _cross_session_isolation(sessions: list[SessionRecord]) -> dict[str, Any]:
    """跨会话隔离：同 scenario 组的 injected_context_text 必须可区分。

    对每个 scenario 组内 >=2 个 session，两两比对 injected_context_text：
    - 任一为空 → isolation_ok=False（空串不能证明可区分）
    - 两者相等 → isolation_ok=False
    """
    groups: dict[str, list[SessionRecord]] = {}
    for s in sessions:
        groups.setdefault(s.scenario, []).append(s)
    pair_results: list[dict[str, Any]] = []
    overall_ok = True
    for scenario, group in groups.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a = group[i]
                b = group[j]
                ok = bool(a.injected_context_text) and bool(b.injected_context_text) and a.injected_context_text != b.injected_context_text
                pair_results.append({
                    "scenario": scenario,
                    "session_a": a.session_id,
                    "session_b": b.session_id,
                    "isolation_ok": ok,
                })
                if not ok:
                    overall_ok = False
    return {
        "cross_session_isolation_ok": overall_ok,
        "pair_count": len(pair_results),
        "pairs": pair_results,
    }


def compute_session_report(
    session_records: Iterable[Mapping[str, Any]],
    config: EvalSessionConfig,
) -> dict[str, Any]:
    """计算 D13C 端到端会话评测报告（冻结口径、fail-closed）。"""
    # 解析 sessions（解析失败直接抛 ValueError，由调用方决定如何标记 fail-closed）
    parsed: list[SessionRecord] = []
    seen_session_ids: set[str] = set()
    for idx, raw in enumerate(session_records):
        session = SessionRecord.from_mapping(idx, raw)
        if session.session_id in seen_session_ids:
            raise ValueError(
                f"bundle 存在重复 session_id {session.session_id!r}"
            )
        seen_session_ids.add(session.session_id)
        parsed.append(session)

    if not parsed:
        return _empty_report(config, "NO_VALID_SESSIONS")

    per_session = [_session_metrics(s) for s in parsed]

    # 聚合
    total_steps = sum(m["step_count"] for m in per_session)
    total_completed = sum(m["completed_step_count"] for m in per_session)
    total_isolation_ok = sum(m["isolation_ok_step_count"] for m in per_session)
    total_critical = sum(m["guardrail_critical_count"] for m in per_session)
    total_stop_retry_violations = sum(m["stop_retry_violation_count"] for m in per_session)
    total_deadline_violations = sum(m["deadline_violation_count"] for m in per_session)

    # 聚合 IPC 方法覆盖：所有会话 present 的并集 ⊇ REQUIRED
    all_present: set[str] = set()
    for m in per_session:
        all_present.update(m["ipc_method_coverage"]["present"])
    missing_methods = [m for m in REQUIRED_IPC_METHODS if m not in all_present]

    # 聚合延迟：所有 step 的 latency（>0）
    all_latencies: list[float] = []
    for session in parsed:
        for step in session.steps:
            if step.latency_ms > 0:
                all_latencies.append(step.latency_ms)

    cross_iso = _cross_session_isolation(parsed)

    critical_zero_ok = total_critical == 0

    return {
        "report_version": REPORT_VERSION,
        "config": _config_dict(config),
        "aggregate_metrics": {
            "session_count": len(parsed),
            "total_step_count": total_steps,
            "step_completion_rate": (
                total_completed / total_steps if total_steps else None
            ),
            "isolation_pass_rate": (
                total_isolation_ok / total_steps if total_steps else None
            ),
            "guardrail_critical_count": total_critical,
            "critical_zero_ok": critical_zero_ok,
            "critical_zero_categories": list(CRITICAL_ZERO_CATEGORIES),
            "ipc_method_coverage": {
                "required": list(REQUIRED_IPC_METHODS),
                "present": sorted(all_present),
                "missing": missing_methods,
                "coverage_complete": len(missing_methods) == 0,
            },
            "stop_retry_violation_count": total_stop_retry_violations,
            "deadline_violation_count": total_deadline_violations,
            "latency": _latency_stats(all_latencies),
            "cross_session_isolation_ok": cross_iso["cross_session_isolation_ok"],
            "cross_session_pair_count": cross_iso["pair_count"],
        },
        "per_session_metrics": per_session,
        "cross_session_isolation": cross_iso,
        "critical_zero_ok": critical_zero_ok,
        "fail_closed_reasons": [],
        "provenance": {
            "implementation_commit": config.implementation_commit,
            "environment": config.environment,
            "evidence_reference": config.evidence_reference,
            "dataset_version": config.dataset_version,
            "gold_label_version": config.gold_label_version,
            "dataset_sha256": config.dataset_sha256,
            "gold_sha256": config.gold_sha256,
            "note": (
                "本报告为 L0/L1 评测账本计算结果；未取得麒麟 VM 实测前，"
                "Runtime / 正式达标结论必须标 UNVERIFIED。"
            ),
        },
    }


def _config_dict(config: EvalSessionConfig) -> dict[str, Any]:
    return {
        "config_version": config.config_version,
        "dataset_version": config.dataset_version,
        "gold_label_version": config.gold_label_version,
        "implementation_commit": config.implementation_commit,
        "environment": config.environment,
        "evidence_reference": config.evidence_reference,
        "dataset_sha256": config.dataset_sha256,
        "gold_sha256": config.gold_sha256,
        "statistics_method": config.statistics_method,
        "warmup_count": config.warmup_count,
        "repeat_count": config.repeat_count,
        "concurrency": config.concurrency,
        "stability_repeat": config.stability_repeat,
        "deadline_ms": config.deadline_ms,
    }


def _empty_report(config: EvalSessionConfig, reason: str) -> dict[str, Any]:
    """fail-closed 空报告：指标 null，仅保留 config 与原因。"""
    return {
        "report_version": REPORT_VERSION,
        "config": _config_dict(config),
        "aggregate_metrics": None,
        "per_session_metrics": [],
        "cross_session_isolation": None,
        "critical_zero_ok": None,
        "fail_closed_reasons": [reason],
        "provenance": {
            "implementation_commit": config.implementation_commit,
            "environment": config.environment,
            "evidence_reference": config.evidence_reference,
            "note": (
                "fail-closed：不输出可被误读为正式的指标；"
                "未取得麒麟 VM 实测前 Runtime 结论 UNVERIFIED。"
            ),
        },
    }
