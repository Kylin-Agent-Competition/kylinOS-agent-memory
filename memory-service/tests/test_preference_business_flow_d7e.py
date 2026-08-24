"""
test_preference_business_flow_d7e.py — Day7E 偏好业务链路回归测试（跨 Day5/Day6/Day7A/Day7E）

对齐任务卡：day7-e-03-preference-business-flow-regression-v1
（建立跨 Day5 Candidate Governance、Day6 Source Admission、Day7A 抽取、
 Day7E 长期化与版本规划的全链路偏好业务回归，证明 Day7E 新增长期化/版本
 策略不会绕过上游来源安全门禁、Candidate 治理与 Domain 生命周期边界）。

覆盖范围（对齐 Plan 批准方案与 14 条验收标准）：
- Gate A（Day6 SourceAdmission，消费 NormalizedEvent/PipelineResult）：
  跨用户 / high / critical / cancelled / timeout 仍 fail-closed 拒绝；
  合格 completed 事件仍 ALLOW_EXTRACTION(ok) 三值全开。
- Gate B（Day5 CandidateGovernance，消费 MemorySourceEvent）：
  跨用户 / high / critical / cancelled / timeout / failed+Preference 仍拒绝。
- CandidateGovernance 输出不变量：memory_status=candidate、is_active=false、
  requires_confirmation=true、version=1、previous_version_id=None
  （Day7E 不改变生命周期边界）。
- Day7E PreferenceBusinessPolicy：显式长期可长期化但不自动 active；
  临时 / 不持久化不进入长期；implicit 不跳过确认。
- Day7E PreferenceVersionPolicy：CREATE / NO_OP / UPDATE / COEXIST / ROLLBACK
  五种业务动作 + REJECTED 防御态（不可长期化与跨用户拒绝）。
- 端到端回归：显式长期全链路 CREATE；临时指令即使 A 轨生成候选也不进入
  稳定长期 CREATE；上游 Gate 拦截使 Day7E 不可达。
- 纪律与不变量：无 Mock/skip/xfail/固定结果（AST 守卫）、合成数据、
  model_construct 仅用于污染防御、无副作用、确定性、复用身份 identity、
  两个 Gate 事件模型不同（无伪造 NormalizedEvent→MemorySourceEvent 桥接）。

关键架构约束（两个 Gate 使用不同事件模型，仓库无正式桥接）：
- SourceAdmissionPolicy.evaluate() 消费 PipelineResult（内含 NormalizedEvent，
  清洗后内部事件）。
- CandidateGovernanceService.admit_with_event() 消费 MemorySourceEvent
  （外部输入原始事件）。
- 本测试分别验证两个 Gate，不构造也不宣称存在 NormalizedEvent→
  MemorySourceEvent 生产桥接。

明确不验证边界（本测试不做，且不冒充）：
- 不验证真实宿主 / Vector / SQLite / IPC / systemd / D-Bus / 麒麟 Runtime。
- 不验证真实 LLM 抽取或真实宿主安全门禁（属 L2/L3 与真实环境）。

测试纪律：
- 不使用 Mock、skip、xfail 或固定 PASS 结果；不修改任何既有测试与生产代码。
- model_construct 仅用于模拟"被污染结果对象 / DB 载入对象"，验证 fail-closed
  防御守卫，不冒充真实业务验证（与 Day5E/Day6E 纪律一致）。
- 测试数据仅使用合成用户 ID（user_demo_d7e_flow*）、合成事件 ID
  （evt_d7e_flow_*）、合成偏好 ID（pref_d7e_flow_*）与脱敏/虚构样本；
  密钥样串仅用占位标记 sk-demo-*。
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import domain  # noqa: E402
import service  # noqa: E402
from domain.enums import (  # noqa: E402
    ExpressionType,
    MemoryStatus,
    PreferenceScope,
)
from pipeline import schemas as pipeline_schemas  # noqa: E402
from pipeline.pipeline import PipelineResult  # noqa: E402
from pipeline.schemas import (  # noqa: E402
    ConsentScope,
    EventType,
    MemorySourceEvent,
    NormalizedEvent,
    ProcessingStatus,
    QualityScore,
    SensitivityLevel,
    SourceBusinessStatus,
    SourceType,
)
from providers import extraction_provider  # noqa: E402
from security.source_admission import (  # noqa: E402
    ExtractionKind,
    SourceAdmissionDecision,
    SourceAdmissionPolicy,
)
from service.candidate_governance import (  # noqa: E402
    CandidateAdmissionError,
    CandidateGovernanceService,
)
from service.contracts import ServiceRequestContext  # noqa: E402
from service.preference_business_policy import (  # noqa: E402
    PreferenceBusinessDecision,
    PreferenceBusinessPolicy,
)
from service.preference_version_policy import (  # noqa: E402
    PreferenceRollbackIntent,
    PreferenceVersionAction,
    PreferenceVersionIntent,
    PreferenceVersionPlan,
    PreferenceVersionPolicy,
)

# ── 合成数据基座（不含任何真实用户数据/密钥） ──

USER = "user_demo_d7e_flow"
OTHER_USER = "user_demo_d7e_flow_other"
ACTOR = "actor_demo_d7e_flow"
T0 = datetime(2026, 8, 24, 9, 0, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 8, 24, 10, 0, 0, tzinfo=timezone.utc)

SOURCE_ADMISSION = SourceAdmissionPolicy()
GOV = CandidateGovernanceService()
BUSINESS = PreferenceBusinessPolicy()
VERSION = PreferenceVersionPolicy()

FULL_KINDS = {
    ExtractionKind.PREFERENCE,
    ExtractionKind.SUCCESS_KNOWLEDGE,
    ExtractionKind.FAILURE_EXPERIENCE,
}


# ── helper 构造器（合成数据，与既有 Day5E/Day6E/Day7E 测试同源模式） ──


def make_ctx(user_id=USER) -> ServiceRequestContext:
    """可信业务上下文（user_id 唯一来源）。"""
    return ServiceRequestContext(user_id=user_id, actor_id=ACTOR)


def make_memory_source_event(
    event_id: str,
    source_business_status=SourceBusinessStatus.COMPLETED,
    **overrides,
) -> MemorySourceEvent:
    """构造合成 MemorySourceEvent（CandidateGovernance Gate 输入）。

    默认 CHAT + COMPLETED（无 tool_call_id 条件要求）；tool_result 场景
    需显式传 source_type/tool_call_id/payload_security_checked。
    """
    data = {
        "event_id": event_id,
        "user_id": USER,
        "actor_id": ACTOR,
        "source_type": SourceType.CHAT,
        "event_type": EventType.USER_MESSAGE,
        "idempotency_key": f"idem_{event_id}",
        "source_business_status": source_business_status,
        "should_ignore": False,
        "sensitivity": SensitivityLevel.NONE,
        "occurred_at": T0,
        "captured_at": T0,
        "session_id": "sess_d7e_flow_01",
    }
    data.update(overrides)
    return MemorySourceEvent(**data)


def make_normalized_event(
    event_id="evt_d7e_flow_01",
    user_id=USER,
    source_type=SourceType.CHAT,
    source_business_status=SourceBusinessStatus.COMPLETED,
    sensitivity=SensitivityLevel.NONE,
    should_ignore=False,
    payload_security_checked=False,
    content_summary=None,
    **overrides,
) -> NormalizedEvent:
    """构造合成 NormalizedEvent（SourceAdmission Gate 输入）。"""
    data = {
        "event_id": event_id,
        "user_id": user_id,
        "actor_id": ACTOR,
        "source_type": source_type,
        "schema_version": "0.1",
        "trace_id": None,
        "event_type": EventType.USER_MESSAGE,
        "source_reference": None,
        "consent_scope": ConsentScope.MEMORY_ONLY,
        "idempotency_key": f"idem_{event_id}",
        "source_business_status": source_business_status,
        "processing_status": ProcessingStatus.EXTRACTING,
        "memory_type": None,
        "occurred_at": T0,
        "captured_at": T0,
        "session_id": "sess_d7e_flow_01",
        "raw_payload_ref": None,
        "content_summary": content_summary,
        "turn_id": None,
        "tool_call_id": None,
        "sensitivity": sensitivity,
        "is_sensitive_matched": False,
        "should_ignore": should_ignore,
        "payload_security_checked": payload_security_checked,
        "requires_embedding": True,
        "has_structured_payload": True,
        "language_tag": None,
    }
    data.update(overrides)
    return NormalizedEvent(**data)


def make_quality_score(eligible=True, **overrides) -> QualityScore:
    """构造合成 QualityScore（六维 0.0–1.0 + 提取 Gate）。"""
    data = {
        "completeness": 0.9,
        "validity": 0.9,
        "reliability": 0.9,
        "freshness": 0.9,
        "consistency": 0.9,
        "extractability": 1.0,
        "overall": 0.9,
        "eligible_for_extraction": eligible,
    }
    data.update(overrides)
    return QualityScore(**data)


def make_pipeline_result(
    event=None,
    eligible=True,
    security_gate_triggered=False,
    **event_overrides,
) -> PipelineResult:
    """构造合成 PipelineResult（直接构造，用于逐条隔离判定）。"""
    if event is None:
        event = make_normalized_event(**event_overrides)
    score = make_quality_score(eligible=eligible)
    return PipelineResult(
        event=event,
        quality=score,
        eligible_for_extraction=eligible,
        sensitivity_updated=False,
        security_gate_triggered=security_gate_triggered,
    )


def make_pref_candidate(**overrides) -> extraction_provider.PreferenceCandidate:
    """构造合成 PreferenceCandidate（A 轨真实模型，非重定义）。"""
    data = {
        "key": "demo_response_style",
        "value": "concise",
        "category": "presentation",
        "scope": "global",
        "confidence": 0.85,
        "explicitness": "explicit",
        "is_temporary": False,
        "should_persist": True,
        "evidence": "演示证据（脱敏）",
        "source_event_id": "evt_d7e_flow_pref_01",
    }
    data.update(overrides)
    return extraction_provider.PreferenceCandidate(**data)


def make_preference(**overrides) -> domain.Preference:
    """构造合成 Preference Domain（已存在的偏好记录，version>1 自动补前版）。"""
    data = {
        "preference_id": "pref_d7e_flow_01",
        "user_id": USER,
        "expression_type": ExpressionType.EXPLICIT,
        "preference_scope": PreferenceScope.GLOBAL,
        "preference_key": "demo_response_style",
        "preference_value": "concise",
        "confidence_score": 0.85,
        "memory_status": MemoryStatus.ACTIVE,
        "is_active": True,
        "is_temporary": False,
        "should_persist": True,
        "should_decay": False,
        "evidence_event_ids": ["evt_d7e_flow_pref_01"],
        "version": 1,
        "created_at": T0,
        "updated_at": T0,
        "requires_confirmation": False,
    }
    data.update(overrides)
    if data["version"] > 1 and data.get("previous_version_id") is None:
        data["previous_version_id"] = "pref_d7e_flow_prev"
    return domain.Preference(**data)


def make_decision(**overrides) -> PreferenceBusinessDecision:
    """构造 D7E-01 长期化门禁决策（只消费 should_store 与结构化引用）。"""
    data = {
        "should_store": True,
        "requires_confirmation": True,
        "reason_code": "explicit_long_term_candidate",
        "category": "presentation",
        "scope": "global",
        "explicitness": "explicit",
        "confidence": 0.85,
        "is_temporary": False,
        "should_persist": True,
        "candidate_key": "demo_response_style",
        "source_event_id": "evt_d7e_flow_pref_01",
    }
    data.update(overrides)
    return PreferenceBusinessDecision(**data)


def make_intent(**overrides) -> PreferenceVersionIntent:
    """构造 plan_preference 输入。"""
    data = {
        "user_id": USER,
        "preference_key": "demo_response_style",
        "scope": "global",
        "value": "concise",
        "decision": make_decision(),
    }
    data.update(overrides)
    return PreferenceVersionIntent(**data)


def make_rollback_intent(**overrides) -> PreferenceRollbackIntent:
    """构造 plan_rollback 输入。"""
    data = {
        "user_id": USER,
        "target_preference_id": "pref_d7e_flow_01",
    }
    data.update(overrides)
    return PreferenceRollbackIntent(**data)


# ═══════════════════════════════════════════════════════════════════════
# Gate A：Day6 SourceAdmission 安全门禁不被绕过（NormalizedEvent 路径）
# ═══════════════════════════════════════════════════════════════════════


def test_source_admission_cross_user_rejected():
    """Gate A：ctx.user_id 与 event.user_id 不一致 → REJECT(user_id_mismatch)。"""
    res = SOURCE_ADMISSION.evaluate(
        make_pipeline_result(user_id=OTHER_USER), make_ctx())
    assert res.decision is SourceAdmissionDecision.REJECT
    assert res.reason_code == "user_id_mismatch"
    assert res.allowed_extraction_kinds == set()


def test_source_admission_high_sensitivity_rejected():
    """Gate A：sensitivity=high → REJECT(event_sensitive_high)。"""
    res = SOURCE_ADMISSION.evaluate(
        make_pipeline_result(sensitivity=SensitivityLevel.HIGH), make_ctx())
    assert res.decision is SourceAdmissionDecision.REJECT
    assert res.reason_code == "event_sensitive_high"
    assert res.allowed_extraction_kinds == set()


def test_source_admission_critical_sensitivity_rejected():
    """Gate A：sensitivity=critical → REJECT(event_sensitive_critical)。"""
    res = SOURCE_ADMISSION.evaluate(
        make_pipeline_result(sensitivity=SensitivityLevel.CRITICAL), make_ctx())
    assert res.decision is SourceAdmissionDecision.REJECT
    assert res.reason_code == "event_sensitive_critical"
    assert res.allowed_extraction_kinds == set()


def test_source_admission_cancelled_rejected():
    """Gate A：cancelled → REJECT(event_status_cancelled)。"""
    res = SOURCE_ADMISSION.evaluate(
        make_pipeline_result(source_business_status=SourceBusinessStatus.CANCELLED),
        make_ctx())
    assert res.decision is SourceAdmissionDecision.REJECT
    assert res.reason_code == "event_status_cancelled"
    assert res.allowed_extraction_kinds == set()


def test_source_admission_timeout_rejected():
    """Gate A：timeout → REJECT(event_status_timeout)。"""
    res = SOURCE_ADMISSION.evaluate(
        make_pipeline_result(source_business_status=SourceBusinessStatus.TIMEOUT),
        make_ctx())
    assert res.decision is SourceAdmissionDecision.REJECT
    assert res.reason_code == "event_status_timeout"
    assert res.allowed_extraction_kinds == set()


def test_source_admission_positive_control():
    """Gate A：合格 completed 事件 → ALLOW_EXTRACTION(ok)，三种抽取范围全开。"""
    res = SOURCE_ADMISSION.evaluate(
        make_pipeline_result(
            source_type=SourceType.CHAT,
            source_business_status=SourceBusinessStatus.COMPLETED,
            sensitivity=SensitivityLevel.NONE,
            eligible=True,
        ),
        make_ctx())
    assert res.decision is SourceAdmissionDecision.ALLOW_EXTRACTION
    assert res.reason_code == "ok"
    assert res.allowed_extraction_kinds == FULL_KINDS


# ═══════════════════════════════════════════════════════════════════════
# Gate B：Day5 CandidateGovernance 安全门禁不被绕过（MemorySourceEvent 路径）
# ═══════════════════════════════════════════════════════════════════════


def test_governance_cross_user_rejected():
    """Gate B：ctx.user_id 与 event.user_id 不一致 → user_id_mismatch。"""
    cand = make_pref_candidate(source_event_id="evt_d7e_flow_cross_01")
    event = make_memory_source_event(event_id="evt_d7e_flow_cross_01")
    ctx = make_ctx(user_id=OTHER_USER)
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(cand, event, ctx, entity_id="pref_d7e_flow_cross_01")
    assert ei.value.code == "user_id_mismatch"


def test_governance_high_sensitivity_rejected():
    """Gate B：sensitivity=high → event_sensitive_blocked。"""
    cand = make_pref_candidate(source_event_id="evt_d7e_flow_high_01")
    event = make_memory_source_event(
        event_id="evt_d7e_flow_high_01", sensitivity=SensitivityLevel.HIGH)
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(
            cand, event, make_ctx(), entity_id="pref_d7e_flow_high_01")
    assert ei.value.code == "event_sensitive_blocked"


def test_governance_critical_sensitivity_rejected():
    """Gate B：sensitivity=critical → event_sensitive_blocked。"""
    cand = make_pref_candidate(source_event_id="evt_d7e_flow_crit_01")
    event = make_memory_source_event(
        event_id="evt_d7e_flow_crit_01", sensitivity=SensitivityLevel.CRITICAL)
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(
            cand, event, make_ctx(), entity_id="pref_d7e_flow_crit_01")
    assert ei.value.code == "event_sensitive_blocked"


def test_governance_cancelled_rejected():
    """Gate B：cancelled → event_status_cancelled。"""
    cand = make_pref_candidate(source_event_id="evt_d7e_flow_cancel_01")
    event = make_memory_source_event(
        event_id="evt_d7e_flow_cancel_01",
        source_business_status=SourceBusinessStatus.CANCELLED)
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(
            cand, event, make_ctx(), entity_id="pref_d7e_flow_cancel_01")
    assert ei.value.code == "event_status_cancelled"


def test_governance_timeout_rejected():
    """Gate B：timeout → event_status_timeout。"""
    cand = make_pref_candidate(source_event_id="evt_d7e_flow_timeout_01")
    event = make_memory_source_event(
        event_id="evt_d7e_flow_timeout_01",
        source_business_status=SourceBusinessStatus.TIMEOUT)
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(
            cand, event, make_ctx(), entity_id="pref_d7e_flow_timeout_01")
    assert ei.value.code == "event_status_timeout"


def test_governance_failed_event_preference_blocked():
    """Gate B：failed 事件 + PreferenceCandidate → failed_event_preference_blocked。"""
    cand = make_pref_candidate(source_event_id="evt_d7e_flow_failed_01")
    event = make_memory_source_event(
        event_id="evt_d7e_flow_failed_01",
        source_business_status=SourceBusinessStatus.FAILED)
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(
            cand, event, make_ctx(), entity_id="pref_d7e_flow_failed_01")
    assert ei.value.code == "failed_event_preference_blocked"


# ═══════════════════════════════════════════════════════════════════════
# CandidateGovernance 输出不变量（Day7E 不改变 candidate 状态边界）
# ═══════════════════════════════════════════════════════════════════════


def test_governance_explicit_long_term_output_still_candidate():
    """显式长期候选经治理 → 仍为 candidate / 未激活 / 需确认 / v1。"""
    cand = make_pref_candidate(
        explicitness="explicit", is_temporary=False, should_persist=True,
        source_event_id="evt_d7e_flow_out_01",
    )
    event = make_memory_source_event(event_id="evt_d7e_flow_out_01")
    pref = GOV.admit_with_event(
        cand, event, make_ctx(), entity_id="pref_d7e_flow_out_01", now=T0)
    assert pref.memory_status is MemoryStatus.CANDIDATE
    assert pref.is_active is False
    assert pref.requires_confirmation is True
    assert pref.version == 1
    assert pref.previous_version_id is None


def test_governance_temporary_output_still_candidate():
    """临时候选经治理 → 仍为 candidate / 未激活（不无依据提升）。"""
    cand = make_pref_candidate(
        is_temporary=True, source_event_id="evt_d7e_flow_out_temp_01")
    event = make_memory_source_event(event_id="evt_d7e_flow_out_temp_01")
    pref = GOV.admit_with_event(
        cand, event, make_ctx(), entity_id="pref_d7e_flow_out_temp_01", now=T0)
    assert pref.memory_status is MemoryStatus.CANDIDATE
    assert pref.is_active is False
    assert pref.is_temporary is True


def test_governance_no_persist_output_still_candidate():
    """should_persist=false 候选经治理 → 仍为 candidate / 未激活。"""
    cand = make_pref_candidate(
        should_persist=False, source_event_id="evt_d7e_flow_out_np_01")
    event = make_memory_source_event(event_id="evt_d7e_flow_out_np_01")
    pref = GOV.admit_with_event(
        cand, event, make_ctx(), entity_id="pref_d7e_flow_out_np_01", now=T0)
    assert pref.memory_status is MemoryStatus.CANDIDATE
    assert pref.is_active is False
    assert pref.should_persist is False


# ═══════════════════════════════════════════════════════════════════════
# Day7E PreferenceBusinessPolicy：长期化策略不绕过生命周期边界
# ═══════════════════════════════════════════════════════════════════════


def test_business_policy_explicit_long_term_not_auto_active():
    """显式长期 → should_store=True 但 requires_confirmation=True（不自动 active）。"""
    cand = make_pref_candidate(
        explicitness="explicit", is_temporary=False, should_persist=True)
    res = BUSINESS.decide(cand)
    assert res.should_store is True
    assert res.requires_confirmation is True
    assert res.reason_code == "explicit_long_term_candidate"


def test_business_policy_temporary_not_persistent():
    """临时指令 → should_store=False（即使 A 轨生成候选也不长期化）。"""
    cand = make_pref_candidate(is_temporary=True)
    res = BUSINESS.decide(cand)
    assert res.should_store is False
    assert res.requires_confirmation is False
    assert res.reason_code == "temporary_not_persistent"


def test_business_policy_should_persist_false_rejected():
    """should_persist=false → should_store=False。"""
    cand = make_pref_candidate(should_persist=False)
    res = BUSINESS.decide(cand)
    assert res.should_store is False
    assert res.requires_confirmation is False
    assert res.reason_code == "should_persist_false"


def test_business_policy_implicit_requires_confirmation():
    """implicit → should_store=True 但 requires_confirmation=True（不跳过确认）。"""
    cand = make_pref_candidate(explicitness="implicit")
    res = BUSINESS.decide(cand)
    assert res.should_store is True
    assert res.requires_confirmation is True
    assert res.reason_code == "implicit_candidate_requires_confirmation"


# ═══════════════════════════════════════════════════════════════════════
# Day7E PreferenceVersionPolicy：五种版本业务动作 + REJECTED 防御态
# ═══════════════════════════════════════════════════════════════════════


def test_version_create_first_version():
    """同 key+scope 无 active 当前记录 → CREATE 首版。"""
    plan = VERSION.plan_preference(make_intent(), [])
    assert plan.action == PreferenceVersionAction.CREATE
    assert plan.reason_code == "create_first_version"
    assert plan.next_version == 1
    assert plan.previous_version_id is None


def test_version_no_op_same_value():
    """同 key+scope+value 重复事件 → NO_OP，不增版本。"""
    current = make_preference(preference_id="pref_d7e_flow_noop_01", version=3)
    plan = VERSION.plan_preference(make_intent(), [current])
    assert plan.action == PreferenceVersionAction.NO_OP
    assert plan.reason_code == "no_op_same_value"
    assert plan.next_version is None
    assert plan.current_preference_id == "pref_d7e_flow_noop_01"
    assert plan.current_version == 3


def test_version_update_value_changed():
    """同 key+scope 不同 value → UPDATE，版本严格 +1，保留历史引用。"""
    current = make_preference(preference_id="pref_d7e_flow_upd_01", version=2)
    intent = make_intent(value="detailed")
    plan = VERSION.plan_preference(intent, [current])
    assert plan.action == PreferenceVersionAction.UPDATE
    assert plan.reason_code == "update_value_changed"
    assert plan.next_version == current.version + 1 == 3
    assert plan.previous_version_id == current.preference_id
    assert plan.current_preference_id == current.preference_id
    assert plan.current_version == 2


def test_version_coexist_different_scope():
    """同 key 不同 scope → COEXIST，旧 scope active 偏好仍保留。"""
    global_active = make_preference(
        preference_id="pref_d7e_flow_global_01",
        preference_scope=PreferenceScope.GLOBAL, version=1)
    snapshot_before = global_active.model_dump()
    intent = make_intent(scope="tool", value="concise")
    plan = VERSION.plan_preference(intent, [global_active])
    assert plan.action == PreferenceVersionAction.COEXIST
    assert plan.reason_code == "coexist_different_scope"
    assert plan.next_version == 1
    assert plan.previous_version_id is None
    assert "global" in plan.coexist_with_scopes
    # 旧 scope active 偏好未被 supersede
    assert global_active.model_dump() == snapshot_before
    assert global_active.memory_status is MemoryStatus.ACTIVE


def test_version_rollback_history_version():
    """历史版本 → ROLLBACK 业务计划（target/current 均已填充，不写库）。"""
    active_v3 = make_preference(
        preference_id="pref_d7e_flow_v3_01", version=3, preference_value="detailed")
    history_v1 = make_preference(
        preference_id="pref_d7e_flow_v1_01", version=1, preference_value="concise",
        previous_version_id=None,
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
        evidence_event_ids=["evt_d7e_flow_pref_01"],
    )
    snapshot = [active_v3.model_dump(), history_v1.model_dump()]
    intent = make_rollback_intent(target_preference_id="pref_d7e_flow_v1_01")
    plan = VERSION.plan_rollback(intent, [active_v3, history_v1])
    assert plan.action == PreferenceVersionAction.ROLLBACK
    assert plan.reason_code == "rollback_to_history_version"
    assert plan.target_preference_id == "pref_d7e_flow_v1_01"
    assert plan.target_version == 1
    assert plan.current_preference_id == "pref_d7e_flow_v3_01"
    assert plan.current_version == 3
    assert plan.next_version is None
    # 无副作用：输入对象未被修改
    assert [active_v3.model_dump(), history_v1.model_dump()] == snapshot


def test_version_not_persistable_rejected():
    """decision.should_store=False → REJECTED(rejected_not_persistable)
    （不可长期化候选不得产生 CREATE/UPDATE）。"""
    decision = make_decision(should_store=False)
    plan = VERSION.plan_preference(make_intent(decision=decision), [])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_not_persistable"
    assert plan.next_version is None
    # 即使有 active 记录也不得 UPDATE
    current = make_preference(
        preference_id="pref_d7e_flow_np_01", version=1, preference_value="old")
    plan2 = VERSION.plan_preference(
        make_intent(decision=decision, value="new"), [current])
    assert plan2.action == PreferenceVersionAction.REJECTED
    assert plan2.reason_code == "rejected_not_persistable"


def test_version_cross_user_rejected():
    """current_preferences 含其他 user → REJECTED(rejected_cross_user)。"""
    other = make_preference(
        preference_id="pref_d7e_flow_other_01", user_id=OTHER_USER, version=1)
    plan = VERSION.plan_preference(make_intent(), [other])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_cross_user"


# ═══════════════════════════════════════════════════════════════════════
# 端到端回归：Day7E 链路不绕过上游 Gate
# ═══════════════════════════════════════════════════════════════════════


def test_e2e_explicit_long_term_full_chain_create():
    """显式长期全链路：治理 → 长期化决策 → CREATE 计划，
    Day7E 全程不把 candidate 直接变为 active。"""
    cand = make_pref_candidate(
        key="demo_response_style", value="concise", scope="global",
        explicitness="explicit", is_temporary=False, should_persist=True,
        source_event_id="evt_d7e_flow_e2e_01",
    )
    event = make_memory_source_event(event_id="evt_d7e_flow_e2e_01")
    pref = GOV.admit_with_event(
        cand, event, make_ctx(), entity_id="pref_d7e_flow_e2e_01", now=T0)
    # CandidateGovernance 输出仍保持 candidate / 未激活 / 需确认
    assert pref.memory_status is MemoryStatus.CANDIDATE
    assert pref.is_active is False
    assert pref.requires_confirmation is True
    assert pref.version == 1
    assert pref.previous_version_id is None
    # Day7E 业务决策：可长期化但不自动 active
    decision = BUSINESS.decide(cand)
    assert decision.should_store is True
    assert decision.requires_confirmation is True
    assert decision.reason_code == "explicit_long_term_candidate"
    # 版本规划：空 current_preferences → CREATE 首版
    intent = PreferenceVersionIntent(
        user_id=USER, preference_key=cand.key, scope=cand.scope,
        value=cand.value, decision=decision,
    )
    plan = VERSION.plan_preference(intent, [])
    assert plan.action == PreferenceVersionAction.CREATE
    assert plan.reason_code == "create_first_version"
    assert plan.next_version == 1
    assert plan.previous_version_id is None
    # Day7E 全程未把 candidate 提升为 active
    assert pref.memory_status is not MemoryStatus.ACTIVE
    assert decision.requires_confirmation is True


def test_e2e_temporary_candidate_not_persistable_rejected():
    """临时指令即使 A 轨生成 PreferenceCandidate，也不进入稳定长期版本 CREATE。"""
    cand = make_pref_candidate(
        key="demo_response_style", value="concise", scope="session",
        explicitness="explicit", is_temporary=True, should_persist=False,
        source_event_id="evt_d7e_flow_temp_e2e_01",
    )
    event = make_memory_source_event(event_id="evt_d7e_flow_temp_e2e_01")
    # 治理层可构造 candidate Domain（生命周期边界允许 candidate）
    pref = GOV.admit_with_event(
        cand, event, make_ctx(), entity_id="pref_d7e_flow_temp_e2e_01", now=T0)
    assert pref.memory_status is MemoryStatus.CANDIDATE
    assert pref.is_active is False
    # 但 Day7E 长期化决策拒绝：不得进入稳定长期版本
    decision = BUSINESS.decide(cand)
    assert decision.should_store is False
    assert decision.reason_code == "temporary_not_persistent"
    intent = PreferenceVersionIntent(
        user_id=USER, preference_key=cand.key, scope=cand.scope,
        value=cand.value, decision=decision,
    )
    plan = VERSION.plan_preference(intent, [])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_not_persistable"
    assert plan.next_version is None


def test_e2e_cross_user_blocked_at_governance_gate():
    """跨用户候选在 CandidateGovernance 即被 fail-closed 拒绝，
    Day7E BusinessPolicy / VersionPolicy 不可达。"""
    cand = make_pref_candidate(source_event_id="evt_d7e_flow_cross_e2e_01")
    event = make_memory_source_event(event_id="evt_d7e_flow_cross_e2e_01")
    ctx = make_ctx(user_id=OTHER_USER)  # ctx 与 event 用户不一致（跨用户）
    blocked = True
    try:
        GOV.admit_with_event(
            cand, event, ctx, entity_id="pref_d7e_flow_cross_e2e_01")
        blocked = False
    except CandidateAdmissionError as ei:
        assert ei.code == "user_id_mismatch"
    # 治理门禁拦截即中止：Day7E 决策/版本规划不可达
    assert blocked


def test_e2e_high_sensitivity_blocked_at_both_gates():
    """high 敏感来源：两个 Gate 均 fail-closed 拒绝，Day7E 不可达。"""
    # Gate A：SourceAdmission（NormalizedEvent 路径）
    res = SOURCE_ADMISSION.evaluate(
        make_pipeline_result(sensitivity=SensitivityLevel.HIGH), make_ctx())
    assert res.decision is SourceAdmissionDecision.REJECT
    assert res.reason_code == "event_sensitive_high"
    assert res.allowed_extraction_kinds == set()
    # Gate B：CandidateGovernance（MemorySourceEvent 路径）
    cand = make_pref_candidate(source_event_id="evt_d7e_flow_high_e2e_01")
    event = make_memory_source_event(
        event_id="evt_d7e_flow_high_e2e_01", sensitivity=SensitivityLevel.HIGH)
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(
            cand, event, make_ctx(), entity_id="pref_d7e_flow_high_e2e_01")
    assert ei.value.code == "event_sensitive_blocked"


def test_e2e_cancelled_blocked_at_both_gates():
    """cancelled 来源：两个 Gate 均拒绝，Day7E 不可达。"""
    res = SOURCE_ADMISSION.evaluate(
        make_pipeline_result(source_business_status=SourceBusinessStatus.CANCELLED),
        make_ctx())
    assert res.decision is SourceAdmissionDecision.REJECT
    assert res.reason_code == "event_status_cancelled"
    cand = make_pref_candidate(source_event_id="evt_d7e_flow_cancel_e2e_01")
    event = make_memory_source_event(
        event_id="evt_d7e_flow_cancel_e2e_01",
        source_business_status=SourceBusinessStatus.CANCELLED)
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(
            cand, event, make_ctx(), entity_id="pref_d7e_flow_cancel_e2e_01")
    assert ei.value.code == "event_status_cancelled"


def test_e2e_timeout_blocked_at_both_gates():
    """timeout 来源：两个 Gate 均拒绝，Day7E 不可达。"""
    res = SOURCE_ADMISSION.evaluate(
        make_pipeline_result(source_business_status=SourceBusinessStatus.TIMEOUT),
        make_ctx())
    assert res.decision is SourceAdmissionDecision.REJECT
    assert res.reason_code == "event_status_timeout"
    cand = make_pref_candidate(source_event_id="evt_d7e_flow_timeout_e2e_01")
    event = make_memory_source_event(
        event_id="evt_d7e_flow_timeout_e2e_01",
        source_business_status=SourceBusinessStatus.TIMEOUT)
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(
            cand, event, make_ctx(), entity_id="pref_d7e_flow_timeout_e2e_01")
    assert ei.value.code == "event_status_timeout"


# ═══════════════════════════════════════════════════════════════════════
# 不变量与纪律守护
# ═══════════════════════════════════════════════════════════════════════


def test_e2e_no_side_effects():
    """全链路调用前后 current_preferences 及对象 model_dump() 不变。"""
    current = make_preference(
        preference_id="pref_d7e_flow_side_01", version=2,
        preference_value="concise")
    history = make_preference(
        preference_id="pref_d7e_flow_side_02", version=1,
        preference_value="concise", previous_version_id=None,
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
        evidence_event_ids=["evt_d7e_flow_side_01"],
    )
    prefs = [current, history]
    snapshot = [p.model_dump() for p in prefs]
    # 全链路：治理 → 业务决策 → 版本规划（含 UPDATE 与 ROLLBACK 路径）
    cand = make_pref_candidate(
        key="demo_response_style", value="detailed", scope="global",
        source_event_id="evt_d7e_flow_side_01",
    )
    event = make_memory_source_event(event_id="evt_d7e_flow_side_01")
    _ = GOV.admit_with_event(
        cand, event, make_ctx(), entity_id="pref_d7e_flow_side_03", now=T0)
    decision = BUSINESS.decide(cand)
    intent = PreferenceVersionIntent(
        user_id=USER, preference_key=cand.key, scope=cand.scope,
        value=cand.value, decision=decision,
    )
    _ = VERSION.plan_preference(intent, prefs)
    _ = VERSION.plan_preference(intent, prefs)
    _ = VERSION.plan_rollback(
        make_rollback_intent(target_preference_id="pref_d7e_flow_side_02"), prefs)
    assert [p.model_dump() for p in prefs] == snapshot


def test_e2e_deterministic():
    """同输入两次全链路结果完全相等（治理/决策/版本规划确定性）。"""
    cand = make_pref_candidate(
        key="demo_response_style", value="detailed", scope="global",
        explicitness="explicit", is_temporary=False, should_persist=True,
        source_event_id="evt_d7e_flow_det_01",
    )
    event = make_memory_source_event(event_id="evt_d7e_flow_det_01")
    ctx = make_ctx()
    entity_id = "pref_d7e_flow_det_01"
    pref_a = GOV.admit_with_event(cand, event, ctx, entity_id=entity_id, now=T0)
    pref_b = GOV.admit_with_event(cand, event, ctx, entity_id=entity_id, now=T0)
    assert pref_a.model_dump() == pref_b.model_dump()
    decision = BUSINESS.decide(cand)
    assert BUSINESS.decide(cand).model_dump() == decision.model_dump()
    current = make_preference(version=2, preference_value="concise")
    intent = PreferenceVersionIntent(
        user_id=USER, preference_key=cand.key, scope=cand.scope,
        value=cand.value, decision=decision,
    )
    assert (
        VERSION.plan_preference(intent, [current]).model_dump()
        == VERSION.plan_preference(intent, [current]).model_dump()
    )


def test_all_components_real_identity():
    """本测试复用的全部组件均为仓库真实生产对象（identity 守护，非第二套）。"""
    import security.source_admission as sa
    import service.candidate_governance as cg
    import service.preference_business_policy as bp
    import service.preference_version_policy as vp

    # Provider 候选类型
    assert cg.PreferenceCandidate is extraction_provider.PreferenceCandidate
    assert bp.PreferenceCandidate is extraction_provider.PreferenceCandidate
    # E 轨 Domain 类型
    assert cg.Preference is domain.Preference
    assert vp.Preference is domain.Preference
    # 两个 Gate 的事件模型（真实 pipeline.schemas 类型）
    assert cg.MemorySourceEvent is pipeline_schemas.MemorySourceEvent
    assert sa.NormalizedEvent is pipeline_schemas.NormalizedEvent
    assert sa.PipelineResult is PipelineResult
    # 业务决策类型
    assert vp.PreferenceBusinessDecision is bp.PreferenceBusinessDecision


def test_no_mock_skip_xfail_in_module():
    """AST 守卫：本文件不含 Mock / skip / xfail / patch / MagicMock。"""
    import ast

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module)
    assert "unittest.mock" not in imported_modules
    assert "mock" not in imported_modules
    assert not any(m.startswith("unittest.mock") for m in imported_modules)
    forbidden = {"skip", "xfail", "patch", "MagicMock"}
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in forbidden:
            violations.append(node.attr)
        if isinstance(node, ast.Name) and node.id == "MagicMock":
            violations.append(node.id)
    assert violations == []


def test_two_gates_use_different_event_models():
    """两个 Gate 消费不同事件模型（无伪造 NormalizedEvent→MemorySourceEvent 桥接）。

    行为证据：SourceAdmission 只接受 NormalizedEvent（经 PipelineResult）；
    CandidateGovernance 只接受 MemorySourceEvent；两者互不为对方输入。
    """
    assert NormalizedEvent is not MemorySourceEvent
    assert not isinstance(
        make_memory_source_event(event_id="evt_d7e_flow_gate_01"), NormalizedEvent)
    assert not isinstance(
        make_normalized_event(event_id="evt_d7e_flow_gate_02"), MemorySourceEvent)
    # Gate A 类型准入：PipelineResult 内 event 非 NormalizedEvent → fail-closed
    polluted = PipelineResult.model_construct(
        event=make_memory_source_event(event_id="evt_d7e_flow_gate_03"),
        quality=make_quality_score(),
        eligible_for_extraction=True,
        security_gate_triggered=False,
    )
    res = SOURCE_ADMISSION.evaluate(polluted, make_ctx())
    assert res.decision is SourceAdmissionDecision.REJECT
    assert res.reason_code == "invalid_pipeline_result"
    # Gate B 类型准入：event 非 MemorySourceEvent → invalid_event
    cand = make_pref_candidate(source_event_id="evt_d7e_flow_gate_04")
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(
            cand, make_normalized_event(event_id="evt_d7e_flow_gate_04"),
            make_ctx(), entity_id="pref_d7e_flow_gate_04")
    assert ei.value.code == "invalid_event"
