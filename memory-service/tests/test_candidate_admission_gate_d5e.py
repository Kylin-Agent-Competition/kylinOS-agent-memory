"""
test_candidate_admission_gate_d5e.py — Day5 E 轨事件与 Candidate 真实性业务准入门禁单元测试

对齐任务卡：day5-e-02-event-candidate-admission-gate-v1
（在 Candidate 进入正式 E 轨 Domain 前，基于 MemorySourceEvent / Candidate
 provenance / 安全标记 / 业务状态实施 fail-closed 准入校验；拒绝返回结构化
 可测试 reason，不允许静默丢弃）。

覆盖范围（对齐 PLan 批准方案）：
- 正向：合法 completed 事件 + Preference → Preference Domain；
  合法 success TOOL_RESULT + Knowledge(fact) → Knowledge Domain；
  failed TOOL_RESULT + Knowledge(failure_experience) → Knowledge Domain 且
  knowledge_type 保持 FAILURE_EXPERIENCE（失败语义保留，不被改写为成功知识）。
- 负向（每条验收/约束对应一条，验证结构化错误码）：
  - event 非 MemorySourceEvent → invalid_event（fail-closed 前置防御）
  - case.source_event_id != event.event_id → source_event_id_mismatch（验收①）
  - ctx.user_id != event.user_id → user_id_mismatch（验收②）
  - event.should_ignore=true → event_should_ignore（验收④ / 约束⑥）
  - source_business_status=ignored（防御纵深，model_construct 绕过 Schema 条件校验）
    → event_status_ignored（验收③）
  - sensitivity=high / critical → event_sensitive_blocked（约束⑦）
  - source_business_status=cancelled → event_status_cancelled（验收⑤）
  - source_business_status=timeout → event_status_timeout（约束④）
  - failed 事件 + Knowledge(fact/workflow) → failed_event_success_knowledge_forbidden
    （验收⑥⑧）
  - failed 事件 + Preference → failed_event_preference_blocked
  - 候选正文 evidence 声称"成功"但事件 source_business_status=failed → 拒绝
    （验收⑧：真实 Event/Tool 状态优先于 LLM/正文声明）
- 边界：错误 __str__ 格式与不泄露候选正文原文；failure_experience 不被改写；
  admit_with_event 不进入 service.__all__；门禁消费 pipeline.schemas 内对象
  （identity，不新建平行类型）；既有 admit()（不带 event）仍可正常调用（向后兼容）。

测试纪律：
- 不使用 Mock、skip、xfail 或固定 PASS 结果。
- model_construct 仅用于模拟"被污染 / DB 载入"事件，验证 fail-closed 防御守卫，
  不冒充真实业务验证（与既有 test_admit_rejects_non_candidate_status_defensive
  model_construct 纪律一致）。
- 测试数据仅使用合成用户 ID（user_demo_d5e）、合成事件 ID（evt_d5e_*）与脱敏内容。
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import domain  # noqa: E402
import service  # noqa: E402
from domain.enums import KnowledgeType  # noqa: E402
from pipeline.schemas import (  # noqa: E402
    ConsentScope,
    EventType,
    MemorySourceEvent,
    MemoryType,
    SensitivityLevel,
    SourceBusinessStatus,
    SourceType,
)
from pipeline import schemas as pipeline_schemas  # noqa: E402
from providers import extraction_provider  # noqa: E402
from service.candidate_governance import (  # noqa: E402
    CandidateAdmissionError,
    CandidateGovernanceService,
)
from service.contracts import ServiceRequestContext  # noqa: E402

# ── 合成数据基座（不含任何真实用户数据/密钥） ──

USER = "user_demo_d5e"
ACTOR = "actor_demo_d5e"
T0 = datetime(2026, 8, 20, 9, 0, 0, tzinfo=timezone.utc)


def make_ctx(user_id=USER) -> ServiceRequestContext:
    """可信业务上下文（user_id 唯一来源）。"""
    return ServiceRequestContext(user_id=user_id, actor_id=ACTOR)


def make_pref_candidate(source_event_id="evt_d5e_pref_01", **overrides):
    """构造合成 PreferenceCandidate（A 轨真实模型，非重定义）。"""
    data = {
        "key": "demo_sort_order",
        "value": "by_modified_desc",
        "category": "presentation",
        "scope": "global",
        "confidence": 0.85,
        "explicitness": "implicit",
        "is_temporary": False,
        "should_persist": True,
        "evidence": "演示证据（脱敏）",
        "source_event_id": source_event_id,
    }
    data.update(overrides)
    return extraction_provider.PreferenceCandidate(**data)


def make_know_candidate(source_event_id="evt_d5e_kn_01", category="fact", **overrides):
    """构造合成 KnowledgeCandidate（A 轨真实模型，非重定义）。"""
    data = {
        "fact": "演示知识：按修改日期降序排列文件（脱敏）",
        "category": category,
        "confidence": 0.6,
        "source_event_id": source_event_id,
    }
    data.update(overrides)
    return extraction_provider.KnowledgeCandidate(**data)


def make_event(
    event_id="evt_d5e_ev_01",
    user_id=USER,
    source_business_status=SourceBusinessStatus.COMPLETED,
    should_ignore=False,
    sensitivity=SensitivityLevel.NONE,
    source_type=SourceType.CHAT,
    **overrides,
):
    """构造合成 MemorySourceEvent（pipeline.schemas 真实模型）。

    event_type 默认 USER_MESSAGE；tool_result 场景需显式传 tool_call_id。
    """
    data = {
        "event_id": event_id,
        "user_id": user_id,
        "actor_id": ACTOR,
        "source_type": source_type,
        "event_type": EventType.USER_MESSAGE,
        "idempotency_key": f"idem_{event_id}",
        "source_business_status": source_business_status,
        "should_ignore": should_ignore,
        "sensitivity": sensitivity,
        "occurred_at": T0,
        "captured_at": T0,
        "session_id": "sess_d5e_01",
    }
    data.update(overrides)
    return MemorySourceEvent(**data)


# ── 正向：合法事件 + 合法 Candidate ──


def test_admit_with_event_preference_valid():
    """合法 completed 事件 + 合法 Preference → Preference Domain（验收⑨）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_ev_01",
        source_business_status=SourceBusinessStatus.COMPLETED,
    )
    cand = make_pref_candidate(source_event_id="evt_d5e_ev_01")
    result = gov.admit_with_event(cand, event, make_ctx(), entity_id="pref_d5e_ev_01")
    assert isinstance(result, domain.Preference)
    assert result.user_id == USER


def test_admit_with_event_knowledge_valid():
    """合法 success TOOL_RESULT 事件 + 合法 Knowledge(fact) → Knowledge Domain（验收⑨）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_kn_ev_01",
        source_business_status=SourceBusinessStatus.SUCCESS,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d5e_01",
    )
    cand = make_know_candidate(
        source_event_id="evt_d5e_kn_ev_01", category="fact"
    )
    result = gov.admit_with_event(cand, event, make_ctx(), entity_id="kn_d5e_ev_01")
    assert isinstance(result, domain.Knowledge)
    assert result.source_event_id == "evt_d5e_kn_ev_01"


def test_admit_with_event_delegates_domain_construction():
    """门禁通过后委托 admit 构造的 Domain 字段正确（user_id/source_event_id/memory_status）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_del_01",
        source_business_status=SourceBusinessStatus.COMPLETED,
    )
    cand = make_pref_candidate(source_event_id="evt_d5e_del_01")
    result = gov.admit_with_event(cand, event, make_ctx(), entity_id="pref_d5e_del_01")
    assert result.evidence_event_ids == ["evt_d5e_del_01"]
    assert result.memory_status is domain.MemoryStatus.CANDIDATE
    assert result.memory_status.value == "candidate"


# ── 正向/边界：失败语义保留（验收⑦） ──


def test_admit_with_event_failure_experience_preserved():
    """failed TOOL_RESULT + Knowledge(failure_experience) 放行，且保留失败语义。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_fail_kn_01",
        source_business_status=SourceBusinessStatus.FAILED,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d5e_fail_kn",
    )
    cand = make_know_candidate(
        source_event_id="evt_d5e_fail_kn_01",
        category="failure_experience",
        fact="演示失败经验：磁盘满导致备份失败（脱敏）",
    )
    result = gov.admit_with_event(cand, event, make_ctx(), entity_id="kn_d5e_fail_01")
    assert isinstance(result, domain.Knowledge)
    # 失败语义保留：不被改写成成功知识
    assert result.knowledge_type is KnowledgeType.FAILURE_EXPERIENCE
    assert result.content_summary == "演示失败经验：磁盘满导致备份失败（脱敏）"


# ── 负向：每个验收/约束对应一条结构化拒绝 ──


def test_gate_rejects_invalid_event_type():
    """event 非 MemorySourceEvent → invalid_event（fail-closed 前置防御）。"""
    gov = CandidateGovernanceService()
    cand = make_pref_candidate(source_event_id="evt_d5e_pref_01")
    for bad_event in (None, {"event_id": "evt_d5e_pref_01"}):
        with pytest.raises(CandidateAdmissionError) as ei:
            gov.admit_with_event(cand, bad_event, make_ctx(), entity_id="pref_d5e_bad_ev")
        assert ei.value.code == "invalid_event"


def test_gate_rejects_source_event_id_mismatch():
    """Candidate.source_event_id 与 event.event_id 不一致 → 拒绝（验收①）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_ev_a",
        source_business_status=SourceBusinessStatus.COMPLETED,
    )
    cand = make_pref_candidate(source_event_id="evt_d5e_ev_b")
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit_with_event(cand, event, make_ctx(), entity_id="pref_d5e_mismatch")
    assert ei.value.code == "source_event_id_mismatch"


def test_gate_rejects_user_id_mismatch():
    """ctx.user_id 与 event.user_id 不一致 → 拒绝（验收②）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_ev_01",
        user_id="user_demo_other",
        source_business_status=SourceBusinessStatus.COMPLETED,
    )
    cand = make_pref_candidate(source_event_id="evt_d5e_ev_01")
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit_with_event(cand, event, make_ctx(), entity_id="pref_d5e_cross_user")
    assert ei.value.code == "user_id_mismatch"


def test_gate_rejects_should_ignore_true():
    """should_ignore=true 事件拒绝稳定记忆准入（验收④ / 约束⑥）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_ev_01",
        source_business_status=SourceBusinessStatus.RAW,
        should_ignore=True,
    )
    cand = make_pref_candidate(source_event_id="evt_d5e_ev_01")
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit_with_event(cand, event, make_ctx(), entity_id="pref_d5e_ignore")
    assert ei.value.code == "event_should_ignore"


def test_gate_rejects_ignored_status_defensive():
    """defense-in-depth：model_construct 污染事件 IGNORED + should_ignore=false
    仍拦截（Schema 条件校验被绕过场景，验收③ 防御纵深）。"""
    polluted = pipeline_schemas.MemorySourceEvent.model_construct(
        event_id="evt_d5e_ignored_01",
        user_id=USER,
        actor_id=ACTOR,
        source_type=SourceType.CHAT,
        source_business_status=SourceBusinessStatus.IGNORED,
        should_ignore=False,  # 污染：正常 Pydantic 构造被 Schema 条件校验拒绝
        sensitivity=SensitivityLevel.NONE,
        occurred_at=T0,
        captured_at=T0,
        idempotency_key="idem",
        event_type=EventType.USER_MESSAGE,
        session_id="sess",
    )
    gov = CandidateGovernanceService()
    cand = make_pref_candidate(source_event_id="evt_d5e_ignored_01")
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit_with_event(
            cand, polluted, make_ctx(), entity_id="pref_d5e_ignored_status"
        )
    assert ei.value.code == "event_status_ignored"


def test_gate_rejects_sensitivity_high():
    """sensitivity=high 事件 → 拒绝（约束⑦：上游安全 Gate 标记不放行）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_ev_01",
        source_business_status=SourceBusinessStatus.COMPLETED,
        sensitivity=SensitivityLevel.HIGH,
    )
    cand = make_pref_candidate(source_event_id="evt_d5e_ev_01")
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit_with_event(cand, event, make_ctx(), entity_id="pref_d5e_high")
    assert ei.value.code == "event_sensitive_blocked"


def test_gate_rejects_sensitivity_critical():
    """sensitivity=critical 事件 → 拒绝（约束⑦）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_ev_01",
        source_business_status=SourceBusinessStatus.COMPLETED,
        sensitivity=SensitivityLevel.CRITICAL,
    )
    cand = make_pref_candidate(source_event_id="evt_d5e_ev_01")
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit_with_event(cand, event, make_ctx(), entity_id="pref_d5e_crit")
    assert ei.value.code == "event_sensitive_blocked"


def test_gate_rejects_cancelled_status():
    """cancelled Tool 事件不能形成完成/成功知识（验收⑤）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_cancel_01",
        source_business_status=SourceBusinessStatus.CANCELLED,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d5e_cancel",
    )
    cand = make_know_candidate(
        source_event_id="evt_d5e_cancel_01", category="workflow"
    )
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit_with_event(cand, event, make_ctx(), entity_id="kn_d5e_cancel")
    assert ei.value.code == "event_status_cancelled"


def test_gate_rejects_timeout_status():
    """timeout 事件不得形成稳定成功知识（约束④）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_timeout_01",
        source_business_status=SourceBusinessStatus.TIMEOUT,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d5e_timeout",
    )
    cand = make_know_candidate(
        source_event_id="evt_d5e_timeout_01", category="workflow"
    )
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit_with_event(cand, event, make_ctx(), entity_id="kn_d5e_timeout")
    assert ei.value.code == "event_status_timeout"


def test_gate_rejects_failed_event_non_failure_knowledge():
    """failed Tool 不能形成成功知识：Knowledge(fact) 拒绝（验收⑥）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_fail_kn_02",
        source_business_status=SourceBusinessStatus.FAILED,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d5e_fail_kn_02",
    )
    cand = make_know_candidate(source_event_id="evt_d5e_fail_kn_02", category="fact")
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit_with_event(cand, event, make_ctx(), entity_id="kn_d5e_fail_fact")
    assert ei.value.code == "failed_event_success_knowledge_forbidden"


def test_gate_rejects_failed_event_workflow_knowledge():
    """failed Tool 不能形成成功知识：Knowledge(workflow) 拒绝（验收⑥）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_fail_kn_03",
        source_business_status=SourceBusinessStatus.FAILED,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d5e_fail_kn_03",
    )
    cand = make_know_candidate(
        source_event_id="evt_d5e_fail_kn_03", category="workflow"
    )
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit_with_event(cand, event, make_ctx(), entity_id="kn_d5e_fail_flow")
    assert ei.value.code == "failed_event_success_knowledge_forbidden"


def test_gate_rejects_failed_event_preference():
    """failed 事件 + Preference → 拒绝（fail-closed：错误事件不形成稳定偏好记忆）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_fail_pf_01",
        source_business_status=SourceBusinessStatus.FAILED,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d5e_fail_pf",
    )
    cand = make_pref_candidate(source_event_id="evt_d5e_fail_pf_01")
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit_with_event(cand, event, make_ctx(), entity_id="pref_d5e_fail_pf")
    assert ei.value.code == "failed_event_preference_blocked"


def test_gate_real_status_overrides_llm_claim():
    """模型文本声称成功但真实事件 failed → 拒绝（验收⑧：真实状态优先）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_llm_claim_01",
        source_business_status=SourceBusinessStatus.FAILED,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d5e_llm_claim",
    )
    # candidate.evidence 声称"成功"（LLM/正文声明），但真实事件状态为 failed。
    cand = make_know_candidate(
        source_event_id="evt_d5e_llm_claim_01",
        category="fact",
        evidence="操作成功完成（模型声称，非真实 Tool 证据）",
    )
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit_with_event(cand, event, make_ctx(), entity_id="kn_d5e_llm_claim")
    assert ei.value.code == "failed_event_success_knowledge_forbidden"


# ── 边界：结构化 reason、错误格式、不泄露正文 ──


def test_rejection_reason_stable_and_testable():
    """所有拒绝路径 errors 均为结构化 CandidateAdmissionError，code 可断言。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_ev_01",
        source_business_status=SourceBusinessStatus.FAILED,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d5e_stable",
    )
    cand = make_know_candidate(source_event_id="evt_d5e_ev_01", category="fact")
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit_with_event(cand, event, make_ctx(), entity_id="kn_d5e_stable")
    assert isinstance(ei.value, CandidateAdmissionError)
    assert ei.value.code == "failed_event_success_knowledge_forbidden"
    assert ei.value.message  # 非空、可测试
    # __str__ 为 "[code] message" 格式
    assert str(ei.value) == (
        f"[{ei.value.code}] {ei.value.message}"
    )


def test_rejection_error_str_does_not_leak_candidate_content():
    """拒绝错误 __str__ 不携带候选正文原文（安全纪律）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_leak_01",
        source_business_status=SourceBusinessStatus.FAILED,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d5e_leak",
    )
    cand = make_know_candidate(
        source_event_id="evt_d5e_leak_01",
        category="fact",
        fact="非常敏感的用户知识内容不应泄露",
    )
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit_with_event(cand, event, make_ctx(), entity_id="kn_d5e_leak")
    assert ei.value.code == "failed_event_success_knowledge_forbidden"
    assert "非常敏感的用户知识内容不应泄露" not in str(ei.value)
    assert "非常敏感的用户知识内容不应泄露" not in ei.value.message


def test_failure_experience_not_rewritten_to_success():
    """failure_experience 候选从 failed 事件通过后 knowledge_type 保持失败语义（验收⑦）。"""
    gov = CandidateGovernanceService()
    event = make_event(
        event_id="evt_d5e_fail_pf_02",
        source_business_status=SourceBusinessStatus.FAILED,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d5e_fail_pf_02",
    )
    cand = make_know_candidate(
        source_event_id="evt_d5e_fail_pf_02",
        category="failure_experience",
        fact="演示失败经验：连接超时导致同步失败（脱敏）",
    )
    result = gov.admit_with_event(cand, event, make_ctx(), entity_id="kn_d5e_fe_02")
    # 未被改写为成功知识语义（如 FACT/WORKFLOW）
    assert result.knowledge_type is KnowledgeType.FAILURE_EXPERIENCE
    assert result.knowledge_type.value == "failure_experience"


def test_admission_gate_not_in_service_all():
    """admit_with_event 作为 method 不进入 service.__all__（守护严格门禁）。"""
    assert "CandidateGovernanceService" not in service.__all__
    assert "CandidateAdmissionError" not in service.__all__
    assert "admit_with_event" not in service.__all__


def test_gate_consumes_pipeline_schema_types():
    """门禁消费 MemorySourceEvent/SourceBusinessStatus/SensitivityLevel 为
    pipeline.schemas 内对象（identity，不新建平行 Schema/枚举）。"""
    import service.candidate_governance as cg

    assert cg.MemorySourceEvent is pipeline_schemas.MemorySourceEvent
    assert cg.SourceBusinessStatus is pipeline_schemas.SourceBusinessStatus
    assert cg.SensitivityLevel is pipeline_schemas.SensitivityLevel


def test_existing_admit_without_event_still_works():
    """既有 admit()（不带 event）仍可正常调用（向后兼容冒烟）。"""
    gov = CandidateGovernanceService()
    result = gov.admit(
        make_pref_candidate(source_event_id="evt_d5e_pref_01"),
        make_ctx(),
        entity_id="pref_d5e_legacy",
    )
    assert isinstance(result, domain.Preference)
    assert result.user_id == USER
