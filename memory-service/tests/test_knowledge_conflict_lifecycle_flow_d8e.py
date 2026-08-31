"""
test_knowledge_conflict_lifecycle_flow_d8e.py — Day8E 知识冲突生命周期跨阶段业务回归

对齐任务卡：day8-e-04-business-flow-acceptance-v1
（仅新增跨阶段业务验收测试，串联既有 Day5 Candidate Governance、Day6 多源安全
 准入、Day8A 知识抽取与 Day8E 冲突/生命周期策略，证明 Tool 事实高于模型自述，
 且安全门禁不能被新业务规则绕过）。

调用链（全部使用真实业务函数，不复制 production 逻辑到测试中）：
  Stage 1 (Day6 准入): EventPipeline(scorer=QualityScorer(now=NOW)).process(raw)
                       → SourceAdmissionPolicy().evaluate(PipelineResult, ctx)
  Stage 2 (Day8A 抽取): ExtractionProvider().extract_knowledge(TurnFinalizedEvent)
  Stage 3 (Day5 治理):  CandidateGovernanceService().admit_with_event(...)
  Stage 4 (Day8E 冲突): ConflictResolutionPolicy().resolve(ConflictSide, ConflictSide)
  Stage 5 (Day8E 生命周期): LifecyclePolicy(PolicyConfig).decide(LifecycleSnapshot, now=)

覆盖范围（对齐已批准方案，跨阶段约束一致保持）：
- success Tool 的可复用知识可经抽取与治理进入 Knowledge，并保留 evidence/
  conditions/结构化字段；memory_status 恒 CANDIDATE（B2）。
- failure Tool 只形成 failure_experience（admission 仅 {FAILURE_EXPERIENCE}、
  extraction 仅 failure_experience、governance 保留失败语义）；
  cancelled/timeout 不形成成功知识（admission REJECT + extraction 空）。
- 真实 Tool 事实与模型自述冲突时以真实 Tool 为业务事实（B1 门控 + 冲突 Tier
  优先级双向验证）；用户显式来源（Tier 1）优先于模型推测（Tier 6）。
- 跨 user_id 与 high/critical sensitive 输入 fail-closed（准入 + 治理 + 冲突
  三阶段一致拦截），安全门禁不能被冲突/生命周期新规则绕过。
- 不同 scope 可共存（COEXIST）；同级不可决保持 DEFER（含 Tier 1 时间决胜边界）。
- 生命周期策略在合成配置下可输出 promote/demote/expire/archive_request，
  reason_code 全部属于固定权威集合、可解释。

明确不在本测试范围内（不验证）：
- 不验证 SQLite / Vector / FTS5 / IPC / systemd / D-Bus / 银河麒麟 Runtime
  （runtime_required=false，纯 WSL 业务回归）。
- 不验证 A/B/C/D 轨实现细节、语义相似度检测阈值或持久化执行。

测试纪律：
- 不使用 Mock、skip、xfail、条件跳过或弱化断言；不修改任何 production 代码
  与既有测试。
- 测试必须调用真实项目业务函数/类（ExtractionProvider / EventPipeline /
  SourceAdmissionPolicy / CandidateGovernanceService / ConflictResolutionPolicy /
  LifecyclePolicy）；合成 ToolResult / MemorySourceEvent / TurnFinalizedEvent
  仅作为输入数据对象，不伪造业务结论。
- LLM 注入使用真实 callable 函数（def llm(kind, text) -> [...]），非
  unittest.mock.Mock。
- 测试数据全部为合成、脱敏数据：用户 user_demo_d8e_flow / user_demo_d8e_other，
  事件 evt_d8e_flow_*，知识 kn_d8e_flow_*，正文均标注"（脱敏）"。
- 生命周期阈值均为合成验证值（与 test_lifecycle_policy_d8e.py 同源模式，
  非正式业务冻结值；正式值由部署配置注入）。
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import domain  # noqa: E402
from domain.enums import KnowledgeType, MemoryStatus  # noqa: E402
from pipeline.pipeline import EventPipeline, PipelineResult  # noqa: E402
from pipeline.quality import QualityScorer  # noqa: E402
from pipeline.schemas import (  # noqa: E402
    ConsentScope,
    EventType,
    MemorySourceEvent,
    MemoryType,
    NormalizedEvent,
    ProcessingStatus,
    QualityScore,
    SensitivityLevel,
    SourceBusinessStatus,
    SourceType,
)
from providers import extraction_provider  # noqa: E402
from providers.extraction_provider import (  # noqa: E402
    ExtractionProvider,
    ToolResult,
    TurnFinalizedEvent,
)
from security.source_admission import (  # noqa: E402
    ExtractionKind,
    SourceAdmissionDecision,
    SourceAdmissionPolicy,
)
from service.candidate_governance import (  # noqa: E402
    CandidateAdmissionError,
    CandidateGovernanceService,
)
from service.conflict_resolution_policy import (  # noqa: E402
    ConflictResolutionPolicy,
    ConflictSide,
    DecisionAction,
    EvidenceTier,
)
from service.contracts import ServiceRequestContext  # noqa: E402
from service.lifecycle_policy import (  # noqa: E402
    LifecycleAction,
    LifecyclePolicy,
    LifecycleSnapshot,
    PolicyConfig,
)

# ── 合成数据基座（不含任何真实用户数据/密钥） ──

USER = "user_demo_d8e_flow"
USER_OTHER = "user_demo_d8e_other"  # 跨用户对照用第二合成用户
ACTOR = "actor_demo_d8e_flow"
T0 = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
T_LAST = datetime(2026, 8, 20, 0, 0, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)

POLICY_ADMISSION = SourceAdmissionPolicy()
GOV = CandidateGovernanceService()
CONFLICT = ConflictResolutionPolicy()

FULL_KINDS = {
    ExtractionKind.PREFERENCE,
    ExtractionKind.SUCCESS_KNOWLEDGE,
    ExtractionKind.FAILURE_EXPERIENCE,
}

# 固定 reason_code 权威集合（生命周期策略层所有可达判定码）
EXPECTED_LIFECYCLE_REASON_CODES = {
    "invalid_input",
    "candidate_requires_confirmation",
    "superseded_no_auto_recovery",
    "deprecated_no_auto_recovery",
    "expired_pending_archive",
    "removed_cold_data",
    "expired_cold_data",
    "age_threshold_reached",
    "inactivity_threshold",
    "low_usage_threshold",
    "confidence_decay_threshold",
    "credible_evidence_threshold",
    "no_threshold_met",
}


# ── Helper 构造器（仅构造合成输入数据对象或调用真实业务函数） ──


def make_ctx(user_id=USER) -> ServiceRequestContext:
    """可信业务上下文（user_id 唯一来源）。"""
    return ServiceRequestContext(user_id=user_id, actor_id=ACTOR)


def make_tool_result(tool_name, status, result=None, error=None,
                     arguments=None) -> ToolResult:
    """构造合成 ToolResult（A 轨真实 dataclass，合成/脱敏数据）。"""
    return ToolResult(
        tool_name=tool_name,
        arguments=arguments or {},
        status=status,
        result=result,
        error=error,
    )


def make_turn(tool_results=None, user_text="", assistant_text="", source="chat",
              source_event_id=None) -> TurnFinalizedEvent:
    """构造合成 TurnFinalizedEvent（A 轨真实模型）。"""
    return TurnFinalizedEvent(
        session_id="sess_d8e_flow",
        user_text=user_text,
        assistant_text=assistant_text,
        tool_results=tool_results,
        source=source,
        source_event_id=source_event_id,
    )


def make_raw(event_id, source_type="chat", source_business_status="completed",
             **overrides) -> dict:
    """构造外部 raw 事件 dict（清洗前 MemorySourceEvent 输入，合成数据）。"""
    base = {
        "event_id": event_id,
        "user_id": USER,
        "actor_id": ACTOR,
        "source_type": source_type,
        "event_type": ("agent_response" if source_type == "tool_result"
                       else "user_message"),
        "consent_scope": "memory_only",
        "idempotency_key": f"idem_{event_id}",
        "occurred_at": "2026-08-27T10:00:00Z",
        "captured_at": "2026-08-27T10:00:01Z",
        "session_id": "sess_d8e_flow",
        "turn_id": f"turn_{event_id}",
        "content_summary": "演示：跨阶段业务验收（脱敏）",
        "has_structured_payload": True,
        "source_business_status": source_business_status,
        "payload_security_checked": False,
    }
    base.update(overrides)
    return base


def make_memory_source_event(event_id,
                             source_business_status=SourceBusinessStatus.COMPLETED,
                             source_type=SourceType.CHAT,
                             user_id=USER,
                             **overrides) -> MemorySourceEvent:
    """构造合成 MemorySourceEvent（pipeline.schemas 真实模型）。

    tool_result 场景需显式传 tool_call_id（Schema 条件校验要求）。
    """
    data = {
        "event_id": event_id,
        "user_id": user_id,
        "actor_id": ACTOR,
        "source_type": source_type,
        "event_type": (EventType.AGENT_RESPONSE
                       if source_type == SourceType.TOOL_RESULT
                       else EventType.USER_MESSAGE),
        "idempotency_key": f"idem_{event_id}",
        "source_business_status": source_business_status,
        "should_ignore": False,
        "sensitivity": SensitivityLevel.NONE,
        "occurred_at": T0,
        "captured_at": T0,
        "session_id": "sess_d8e_flow",
    }
    data.update(overrides)
    return MemorySourceEvent(**data)


def make_pipeline_result_via_pipeline(raw) -> PipelineResult:
    """走真实 EventPipeline.process()（真实安全与质量 Gate）。"""
    return EventPipeline(scorer=QualityScorer(now=NOW)).process(raw)


def make_normalized_event(event_id="evt_d8e_flow_01",
                          source_business_status=SourceBusinessStatus.COMPLETED,
                          source_type=SourceType.CHAT,
                          user_id=USER,
                          **overrides) -> NormalizedEvent:
    """构造合成 NormalizedEvent（pipeline.schemas 真实模型）。"""
    data = {
        "event_id": event_id,
        "user_id": user_id,
        "actor_id": ACTOR,
        "source_type": source_type,
        "schema_version": "0.1",
        "trace_id": None,
        "event_type": (EventType.AGENT_RESPONSE
                       if source_type == SourceType.TOOL_RESULT
                       else EventType.USER_MESSAGE),
        "source_reference": None,
        "consent_scope": ConsentScope.MEMORY_ONLY,
        "idempotency_key": f"idem_{event_id}",
        "source_business_status": source_business_status,
        "processing_status": ProcessingStatus.EXTRACTING,
        "memory_type": None,
        "occurred_at": T0,
        "captured_at": T0,
        "session_id": "sess_d8e_flow",
        "raw_payload_ref": None,
        "content_summary": "演示：跨阶段业务验收（脱敏）",
        "turn_id": None,
        "tool_call_id": None,
        "sensitivity": SensitivityLevel.NONE,
        "is_sensitive_matched": False,
        "should_ignore": False,
        "payload_security_checked": False,
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


def make_pipeline_result(event=None, eligible=True,
                         security_gate_triggered=False,
                         **event_overrides) -> PipelineResult:
    """构造合成 PipelineResult（直接构造，用于逐条隔离判定）。"""
    if event is None:
        event = make_normalized_event(**event_overrides)
    score = make_quality_score(eligible=eligible)
    return PipelineResult(
        event=event,
        quality=score,
        eligible_for_extraction=eligible,
        security_gate_triggered=security_gate_triggered,
    )


def make_conflict_side(knowledge_id, user_id=USER,
                       evidence_tier=EvidenceTier.MODEL_INFERENCE,
                       scope=None, recorded_at=None) -> ConflictSide:
    """构造合成 ConflictSide（真实 Pydantic 模型，合成/脱敏数据）。"""
    return ConflictSide(
        knowledge_id=knowledge_id,
        user_id=user_id,
        evidence_tier=evidence_tier,
        scope=scope,
        recorded_at=recorded_at,
    )


def make_lifecycle_config() -> PolicyConfig:
    """构造合成测试阈值（非冻结业务值；正式冻结值由部署配置注入）。"""
    return PolicyConfig(
        promote_min_confidence=0.8,
        promote_min_access_count=5,
        promote_min_age=timedelta(days=7),
        promote_required_evidence_tier=EvidenceTier.CONSISTENT_BEHAVIOR_MULTIPLE,
        demote_inactivity_period=timedelta(days=30),
        demote_max_access_count=2,
        demote_max_confidence=0.3,
        expire_after_age=timedelta(days=90),
        archive_after_expired=timedelta(days=30),
    )


def make_lifecycle_snapshot(**overrides) -> LifecycleSnapshot:
    """构造合成 LifecycleSnapshot（真实 Pydantic 模型，合成/脱敏数据）。"""
    data = {
        "knowledge_id": "kn_d8e_flow_01",
        "user_id": USER,
        "memory_type": MemoryType.SHORT_TERM,
        "memory_status": MemoryStatus.ACTIVE,
        "evidence_tier": EvidenceTier.TOOL_EXECUTION_RESULT,
        "confidence_score": 0.9,
        "access_count": 10,
        "last_accessed_at": T_LAST,
        "created_at": T0,
        "updated_at": T0,
    }
    data.update(overrides)
    return LifecycleSnapshot(**data)


# ── 1. success Tool 跨阶段成功流 ──


def test_success_tool_full_chain_admission_allows_extraction():
    """success Tool → pipeline → admission ALLOW(三值全开) → extraction 产生候选。"""
    raw = make_raw(
        event_id="evt_d8e_flow_success",
        source_type="tool_result",
        event_type="agent_response",
        tool_call_id="tc_d8e_flow_success",
        source_business_status="success",
        payload_security_checked=True,
    )
    result = make_pipeline_result_via_pipeline(raw)
    assert result.security_gate_triggered is False
    assert result.eligible_for_extraction is True
    admission = POLICY_ADMISSION.evaluate(result, make_ctx())
    assert admission.decision is SourceAdmissionDecision.ALLOW_EXTRACTION
    assert admission.reason_code == "ok"
    assert admission.allowed_extraction_kinds == FULL_KINDS
    cands = ExtractionProvider().extract_knowledge(make_turn(
        tool_results=[make_tool_result(
            "file_search", "success", result="/opt/kylin/data 目录存在且可读")],
        source_event_id="evt_d8e_flow_success",
        source="tool_result",
    ))
    assert len(cands) == 1
    assert cands[0].category == "fact"
    assert cands[0].memory_status == "candidate"  # B2


def test_success_tool_governance_produces_knowledge_with_evidence_conditions():
    """success Tool 候选 → 治理 → Knowledge Domain，保留 evidence/conditions/confidence。"""
    event_id = "evt_d8e_flow_success_gov"
    cands = ExtractionProvider().extract_knowledge(make_turn(
        tool_results=[make_tool_result(
            "file_search", "success", result="/opt/kylin/data 目录存在且可读")],
        source_event_id=event_id,
        source="tool_result",
    ))
    assert len(cands) == 1
    cand = cands[0]
    event = make_memory_source_event(
        event_id,
        source_business_status=SourceBusinessStatus.SUCCESS,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d8e_flow_success_gov",
        payload_security_checked=True,
    )
    kn = GOV.admit_with_event(
        cand, event, make_ctx(), entity_id="kn_d8e_flow_success_gov",
        memory_type=MemoryType.SHORT_TERM,
    )
    assert isinstance(kn, domain.Knowledge)
    assert kn.evidence == "/opt/kylin/data 目录存在且可读"  # 结构化证据保留
    assert kn.conditions == "tool=file_search"  # 结构化条件保留
    assert kn.confidence_score == 0.85  # 真实 Tool 成功=高可信
    assert kn.source_event_id == event_id  # R3 直接相等
    assert kn.content_summary == "/opt/kylin/data 目录存在且可读"


def test_success_tool_knowledge_candidate_status_preserved():
    """治理输出 memory_status=CANDIDATE、requires_embedding=True（B2 保持）。"""
    event_id = "evt_d8e_flow_success_st"
    cands = ExtractionProvider().extract_knowledge(make_turn(
        tool_results=[make_tool_result(
            "file_search", "success", result="/opt/kylin/data 目录存在且可读")],
        source_event_id=event_id,
        source="tool_result",
    ))
    event = make_memory_source_event(
        event_id,
        source_business_status=SourceBusinessStatus.SUCCESS,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d8e_flow_success_st",
        payload_security_checked=True,
    )
    kn = GOV.admit_with_event(
        cands[0], event, make_ctx(), entity_id="kn_d8e_flow_success_st",
        memory_type=MemoryType.SHORT_TERM,
    )
    assert kn.memory_status is MemoryStatus.CANDIDATE
    assert kn.requires_embedding is True
    assert kn.is_outdated is False


# ── 2. failure Tool 跨阶段失败流 ──


def test_failure_tool_admission_only_failure_experience():
    """Tool failure → admission ALLOW({FAILURE_EXPERIENCE})，不含成功知识/偏好。"""
    raw = make_raw(
        event_id="evt_d8e_flow_fail",
        source_type="tool_result",
        event_type="agent_response",
        tool_call_id="tc_d8e_flow_fail",
        source_business_status="failed",
        payload_security_checked=True,
    )
    result = make_pipeline_result_via_pipeline(raw)
    assert result.security_gate_triggered is False
    admission = POLICY_ADMISSION.evaluate(result, make_ctx())
    assert admission.decision is SourceAdmissionDecision.ALLOW_EXTRACTION
    assert admission.reason_code == "ok_failed_tool_failure_experience_only"
    assert admission.allowed_extraction_kinds == {ExtractionKind.FAILURE_EXPERIENCE}
    assert ExtractionKind.SUCCESS_KNOWLEDGE not in admission.allowed_extraction_kinds
    assert ExtractionKind.PREFERENCE not in admission.allowed_extraction_kinds


def test_failure_tool_extraction_only_failure_experience():
    """Tool failure → extraction 仅产生 failure_experience（confidence=0.6）。"""
    cands = ExtractionProvider().extract_knowledge(make_turn(
        tool_results=[make_tool_result(
            "install", "failure", error="dependency not found",
            arguments={"pkg": "vim"})],
        source_event_id="evt_d8e_flow_fail_ext",
        source="tool_result",
    ))
    assert len(cands) == 1
    c = cands[0]
    assert c.category == "failure_experience"
    assert c.confidence == 0.6  # 中可信
    assert c.failure_reason == "dependency not found"
    assert "tool=install" in c.conditions
    assert c.avoid_condition  # 避免条件可解释


def test_failure_tool_governance_preserves_failure_semantics():
    """failure_experience 候选 + FAILED 事件 → 治理保留失败语义字段。"""
    event_id = "evt_d8e_flow_fail_gov"
    cands = ExtractionProvider().extract_knowledge(make_turn(
        tool_results=[make_tool_result(
            "install", "failure", error="dependency not found",
            arguments={"pkg": "vim"})],
        source_event_id=event_id,
        source="tool_result",
    ))
    event = make_memory_source_event(
        event_id,
        source_business_status=SourceBusinessStatus.FAILED,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d8e_flow_fail_gov",
        payload_security_checked=True,
    )
    kn = GOV.admit_with_event(
        cands[0], event, make_ctx(), entity_id="kn_d8e_flow_fail_gov",
        memory_type=MemoryType.SHORT_TERM,
    )
    assert isinstance(kn, domain.Knowledge)
    assert kn.knowledge_type is KnowledgeType.FAILURE_EXPERIENCE  # 失败语义不改写
    assert kn.failure_reason == "dependency not found"
    assert kn.avoid_condition is not None
    assert "tool=install" in kn.conditions


def test_failure_tool_no_success_knowledge_types():
    """failure 不产生 fact/workflow/case/template/constraint 成功知识。"""
    cands = ExtractionProvider().extract_knowledge(make_turn(
        tool_results=[make_tool_result("config", "failure", error="perm denied")],
        source_event_id="evt_d8e_flow_fail_types",
        source="tool_result",
    ))
    assert len(cands) == 1
    success_categories = {"fact", "workflow", "case", "template", "constraint"}
    assert cands[0].category == "failure_experience"
    assert all(c.category not in success_categories for c in cands)
    assert all("成功" not in c.fact for c in cands)


# ── 3. cancelled / timeout：不形成成功知识 ──


def test_cancelled_tool_admission_rejected():
    """cancelled → admission REJECT(event_status_cancelled)，抽取范围为空。"""
    result = make_pipeline_result(
        source_business_status=SourceBusinessStatus.CANCELLED,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d8e_flow_cancel",
        payload_security_checked=True,
        sensitivity=SensitivityLevel.NONE,
        eligible=True,
    )
    admission = POLICY_ADMISSION.evaluate(result, make_ctx())
    assert admission.decision is SourceAdmissionDecision.REJECT
    assert admission.reason_code == "event_status_cancelled"
    assert admission.allowed_extraction_kinds == set()


def test_cancelled_tool_extraction_empty():
    """cancelled Tool → extract_knowledge → []（用户中止无结论）。"""
    p = ExtractionProvider()
    ev = make_turn(
        tool_results=[make_tool_result("cmd", "cancelled")],
        source_event_id="evt_d8e_flow_cancel_ext",
        source="tool_result",
    )
    assert p.extract_knowledge(ev) == []


def test_timeout_tool_admission_rejected():
    """timeout → admission REJECT(event_status_timeout)，抽取范围为空。"""
    result = make_pipeline_result(
        source_business_status=SourceBusinessStatus.TIMEOUT,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d8e_flow_timeout",
        payload_security_checked=True,
        sensitivity=SensitivityLevel.NONE,
        eligible=True,
    )
    admission = POLICY_ADMISSION.evaluate(result, make_ctx())
    assert admission.decision is SourceAdmissionDecision.REJECT
    assert admission.reason_code == "event_status_timeout"
    assert admission.allowed_extraction_kinds == set()


def test_timeout_tool_extraction_empty():
    """timeout Tool → extract_knowledge → []（保守跳过，不沉淀知识）。"""
    p = ExtractionProvider()
    ev = make_turn(
        tool_results=[make_tool_result("t", "timeout", result="部分结果")],
        source_event_id="evt_d8e_flow_timeout_ext",
        source="tool_result",
    )
    assert p.extract_knowledge(ev) == []


# ── 4. 模型自述 vs 真实 Tool 事实（B1 门控 + 冲突 Tier 优先级） ──


def test_model_claims_success_but_tool_failed_extraction_rejects_success():
    """failed Tool + 模型自述成功 → 规则路径仅 failure_experience；LLM 声称成功被 B1 拒绝。"""
    ev = make_turn(
        tool_results=[make_tool_result(
            "install", "failure", error="dependency not found",
            arguments={"pkg": "vim"})],
        assistant_text="软件已经成功安装（模型自述，非真实 Tool 证据，脱敏）",
        source_event_id="evt_d8e_flow_fail_claim",
        source="tool_result",
    )
    # rules-only：正文声称成功不影响真实 Tool 状态分派
    p = ExtractionProvider()
    cands = p.extract_knowledge(ev)
    assert len(cands) == 1
    assert cands[0].category == "failure_experience"

    # LLM 路径：注入真实 callable 声称成功 → B1 门控拒绝（无 success Tool evidence）
    def llm(kind, text):
        return [{"fact": "软件安装成功", "category": "fact", "confidence": 0.9}]

    p2 = ExtractionProvider(llm_extractor=llm)
    cands2 = p2.extract_knowledge(ev)
    assert all(c.category == "failure_experience" for c in cands2)
    assert any("no-success-tool-evidence" in a["error"] for a in p2.audit)


def test_model_only_no_tool_evidence_llm_rejected():
    """无 Tool + LLM 声称成功知识 → 空候选 + audit(no-success-tool-evidence)。"""
    def llm(kind, text):
        return [{"fact": "软件安装成功", "category": "fact", "confidence": 0.9}]

    p = ExtractionProvider(llm_extractor=llm)
    ev = make_turn(
        assistant_text="软件已经成功安装（模型自述，非真实 Tool 证据，脱敏）",
        source_event_id="evt_d8e_flow_model_only",
    )
    assert p.extract_knowledge(ev) == []
    assert any("no-success-tool-evidence" in a["error"] for a in p.audit)


def test_conflict_tool_fact_beats_model_claim():
    """真实 Tool 事实（Tier 3）与模型自述（Tier 6）冲突 → 保留 Tool 侧（双向验证）。"""
    tool = make_conflict_side(
        "kn_d8e_flow_tool", evidence_tier=EvidenceTier.TOOL_EXECUTION_RESULT)
    model = make_conflict_side(
        "kn_d8e_flow_model", evidence_tier=EvidenceTier.MODEL_INFERENCE)
    res = CONFLICT.resolve(tool, model)
    assert res.action is DecisionAction.KEEP_LEFT
    assert res.reason_code == "evidence_tier_priority"
    assert res.winner_id == "kn_d8e_flow_tool"
    res = CONFLICT.resolve(model, tool)
    assert res.action is DecisionAction.KEEP_RIGHT
    assert res.reason_code == "evidence_tier_priority"
    assert res.winner_id == "kn_d8e_flow_tool"


def test_conflict_user_explicit_beats_model_inference():
    """用户显式来源（Tier 1）优先于模型推测（Tier 6）。"""
    explicit = make_conflict_side(
        "kn_d8e_flow_explicit",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        recorded_at=T_LAST,
    )
    model = make_conflict_side(
        "kn_d8e_flow_model2", evidence_tier=EvidenceTier.MODEL_INFERENCE)
    res = CONFLICT.resolve(explicit, model)
    assert res.action is DecisionAction.KEEP_LEFT
    assert res.reason_code == "evidence_tier_priority"
    assert res.winner_id == "kn_d8e_flow_explicit"


# ── 5. 跨用户 fail-closed（准入 + 治理 + 冲突三阶段） ──


def test_cross_user_admission_rejected():
    """event user != ctx user → admission REJECT(user_id_mismatch)。"""
    result = make_pipeline_result(user_id=USER_OTHER, eligible=True)
    admission = POLICY_ADMISSION.evaluate(result, make_ctx())
    assert admission.decision is SourceAdmissionDecision.REJECT
    assert admission.reason_code == "user_id_mismatch"
    assert admission.user_id == USER_OTHER


def test_cross_user_governance_rejected():
    """event user != ctx user → governance CandidateAdmissionError(user_id_mismatch)。"""
    event_id = "evt_d8e_flow_cross_gov"
    cand = extraction_provider.KnowledgeCandidate(
        fact="演示事实（脱敏）", category="fact", confidence=0.6,
        source_event_id=event_id,
    )
    event = make_memory_source_event(event_id, user_id=USER_OTHER)
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(
            cand, event, make_ctx(), entity_id="kn_d8e_flow_cross_gov",
            memory_type=MemoryType.SHORT_TERM,
        )
    assert ei.value.code == "user_id_mismatch"


def test_cross_user_conflict_rejected():
    """跨 user_id 冲突 → REJECT(cross_user_blocked)。"""
    a = make_conflict_side(
        "kn_d8e_flow_u1", evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST)
    b = make_conflict_side(
        "kn_d8e_flow_u2", user_id=USER_OTHER,
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST)
    res = CONFLICT.resolve(a, b)
    assert res.action is DecisionAction.REJECT
    assert res.reason_code == "cross_user_blocked"
    assert res.winner_id is None


def test_security_gate_not_bypassed_by_conflict_rule():
    """跨用户知识在准入/治理阶段 fail-closed；冲突新规则不得让其进入裁决。"""
    # Stage 1：准入阶段拦截
    result = make_pipeline_result(user_id=USER_OTHER, eligible=True)
    admission = POLICY_ADMISSION.evaluate(result, make_ctx())
    assert admission.decision is SourceAdmissionDecision.REJECT
    assert admission.reason_code == "user_id_mismatch"
    # Stage 3：治理阶段拦截（即使抽取层可能产生候选）
    event_id = "evt_d8e_flow_gate"
    cand = extraction_provider.KnowledgeCandidate(
        fact="演示事实（脱敏）", category="fact", confidence=0.6,
        source_event_id=event_id,
    )
    event = make_memory_source_event(event_id, user_id=USER_OTHER)
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(
            cand, event, make_ctx(), entity_id="kn_d8e_flow_gate",
            memory_type=MemoryType.SHORT_TERM,
        )
    assert ei.value.code == "user_id_mismatch"
    # 防御纵深：即便构造跨用户 ConflictSide，冲突策略同样 fail-closed REJECT
    side_a = make_conflict_side("kn_d8e_flow_gate_a")
    side_b = make_conflict_side("kn_d8e_flow_gate_b", user_id=USER_OTHER)
    res = CONFLICT.resolve(side_a, side_b)
    assert res.action is DecisionAction.REJECT
    assert res.reason_code == "cross_user_blocked"


# ── 6. 安全敏感 fail-closed（high / critical） ──


def test_high_sensitivity_admission_rejected():
    """sensitivity=HIGH → admission REJECT(event_sensitive_high)。"""
    result = make_pipeline_result(
        sensitivity=SensitivityLevel.HIGH,
        security_gate_triggered=False,
        eligible=True,
    )
    admission = POLICY_ADMISSION.evaluate(result, make_ctx())
    assert admission.decision is SourceAdmissionDecision.REJECT
    assert admission.reason_code == "event_sensitive_high"
    assert admission.allowed_extraction_kinds == set()


def test_high_sensitivity_governance_rejected():
    """sensitivity=HIGH → governance CandidateAdmissionError(event_sensitive_blocked)。"""
    event_id = "evt_d8e_flow_high_gov"
    cand = extraction_provider.KnowledgeCandidate(
        fact="演示事实（脱敏）", category="fact", confidence=0.6,
        source_event_id=event_id,
    )
    event = make_memory_source_event(event_id, sensitivity=SensitivityLevel.HIGH)
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(
            cand, event, make_ctx(), entity_id="kn_d8e_flow_high_gov",
            memory_type=MemoryType.SHORT_TERM,
        )
    assert ei.value.code == "event_sensitive_blocked"


def test_critical_sensitivity_admission_rejected():
    """sensitivity=CRITICAL → admission REJECT(event_sensitive_critical)。"""
    result = make_pipeline_result(
        sensitivity=SensitivityLevel.CRITICAL,
        security_gate_triggered=False,
        eligible=True,
    )
    admission = POLICY_ADMISSION.evaluate(result, make_ctx())
    assert admission.decision is SourceAdmissionDecision.REJECT
    assert admission.reason_code == "event_sensitive_critical"
    assert admission.allowed_extraction_kinds == set()


def test_critical_sensitivity_governance_rejected():
    """sensitivity=CRITICAL → governance CandidateAdmissionError(event_sensitive_blocked)。"""
    event_id = "evt_d8e_flow_crit_gov"
    cand = extraction_provider.KnowledgeCandidate(
        fact="演示事实（脱敏）", category="fact", confidence=0.6,
        source_event_id=event_id,
    )
    event = make_memory_source_event(event_id, sensitivity=SensitivityLevel.CRITICAL)
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(
            cand, event, make_ctx(), entity_id="kn_d8e_flow_crit_gov",
            memory_type=MemoryType.SHORT_TERM,
        )
    assert ei.value.code == "event_sensitive_blocked"


def test_security_gate_not_bypassed_by_lifecycle_rule():
    """高敏事件准入阶段 fail-closed；生命周期新规则不能让其绕过安全门禁。"""
    # 高敏事件在准入阶段即被拒绝（不进入任何业务真源）
    result = make_pipeline_result(
        sensitivity=SensitivityLevel.CRITICAL,
        security_gate_triggered=False,
        eligible=True,
    )
    admission = POLICY_ADMISSION.evaluate(result, make_ctx())
    assert admission.decision is SourceAdmissionDecision.REJECT
    assert admission.reason_code == "event_sensitive_critical"
    # 生命周期策略 fail-closed：CANDIDATE + 高 confidence/最高证据档仍只能 HOLD，
    # 不得因高 confidence 自动提升（安全门禁不被新业务规则绕过）
    policy = LifecyclePolicy(make_lifecycle_config())
    snap = make_lifecycle_snapshot(
        knowledge_id="kn_d8e_flow_lc_cand",
        memory_status=MemoryStatus.CANDIDATE,
        confidence_score=0.99,
        access_count=100,
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
    )
    res = policy.decide(snap, now=NOW)
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "candidate_requires_confirmation"
    assert res.target_memory_type is None
    assert res.target_memory_status is None


# ── 7. 不同 scope 共存 / 同级冲突不可决 ──


def test_different_scope_coexist():
    """不同 scope 可共存 → COEXIST(scope_distinguishable)。"""
    a = make_conflict_side(
        "kn_d8e_flow_scope_a", evidence_tier=EvidenceTier.MODEL_INFERENCE,
        scope="topic:demo_a")
    b = make_conflict_side(
        "kn_d8e_flow_scope_b",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        scope="topic:demo_b")
    res = CONFLICT.resolve(a, b)
    assert res.action is DecisionAction.COEXIST
    assert res.reason_code == "scope_distinguishable"
    assert res.winner_id is None


def test_same_tier_non_explicit_defer():
    """同级（Tier 3 vs Tier 3）不可决 → DEFER(same_tier_undecidable)。"""
    a = make_conflict_side(
        "kn_d8e_flow_st_a", evidence_tier=EvidenceTier.TOOL_EXECUTION_RESULT,
        recorded_at=T_LAST)
    b = make_conflict_side(
        "kn_d8e_flow_st_b", evidence_tier=EvidenceTier.TOOL_EXECUTION_RESULT,
        recorded_at=T0)
    res = CONFLICT.resolve(a, b)
    assert res.action is DecisionAction.DEFER
    assert res.reason_code == "same_tier_undecidable"
    assert res.winner_id is None


def test_same_tier_explicit_latest_wins_by_time():
    """Tier 1 vs Tier 1，recorded_at 不同 → 保留较新侧(latest_explicit_config_wins)。"""
    older = make_conflict_side(
        "kn_d8e_flow_cfg_older",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        recorded_at=T0)
    newer = make_conflict_side(
        "kn_d8e_flow_cfg_newer",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        recorded_at=T_LAST)
    res = CONFLICT.resolve(newer, older)
    assert res.action is DecisionAction.KEEP_LEFT
    assert res.reason_code == "latest_explicit_config_wins"
    assert res.winner_id == "kn_d8e_flow_cfg_newer"
    res = CONFLICT.resolve(older, newer)
    assert res.action is DecisionAction.KEEP_RIGHT
    assert res.reason_code == "latest_explicit_config_wins"
    assert res.winner_id == "kn_d8e_flow_cfg_newer"


def test_same_tier_explicit_same_time_defer():
    """Tier 1 vs Tier 1，recorded_at 相同 → DEFER（同级不可决保持）。"""
    a = make_conflict_side(
        "kn_d8e_flow_cfg_a",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        recorded_at=T_LAST)
    b = make_conflict_side(
        "kn_d8e_flow_cfg_b",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        recorded_at=T_LAST)
    res = CONFLICT.resolve(a, b)
    assert res.action is DecisionAction.DEFER
    assert res.reason_code == "same_tier_undecidable"
    assert res.winner_id is None


# ── 8. 生命周期策略（promote / demote / expire / archive_request） ──

LIFECYCLE_POLICY = LifecyclePolicy(make_lifecycle_config())


def test_lifecycle_promote_credible_evidence():
    """ACTIVE SHORT_TERM + 满足全部提升条件 → PROMOTE(credible_evidence_threshold)。"""
    res = LIFECYCLE_POLICY.decide(
        make_lifecycle_snapshot(knowledge_id="kn_d8e_flow_lc_prom"),
        now=NOW,
    )
    assert res.action is LifecycleAction.PROMOTE
    assert res.reason_code == "credible_evidence_threshold"
    assert res.target_memory_type is MemoryType.MEDIUM_TERM


def test_lifecycle_demote_inactivity():
    """ACTIVE LONG_TERM + inactivity >= 阈值 → DEMOTE(inactivity_threshold)。"""
    res = LIFECYCLE_POLICY.decide(
        make_lifecycle_snapshot(
            knowledge_id="kn_d8e_flow_lc_dem",
            memory_type=MemoryType.LONG_TERM,
            last_accessed_at=NOW - timedelta(days=40),
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.DEMOTE
    assert res.reason_code == "inactivity_threshold"
    assert res.target_memory_type is MemoryType.MEDIUM_TERM


def test_lifecycle_expire_age_threshold():
    """ACTIVE + age >= 阈值 → EXPIRE(age_threshold_reached)，target=EXPIRED。"""
    res = LIFECYCLE_POLICY.decide(
        make_lifecycle_snapshot(
            knowledge_id="kn_d8e_flow_lc_exp",
            memory_type=MemoryType.SHORT_TERM,
            created_at=NOW - timedelta(days=100),
            updated_at=NOW - timedelta(days=100),
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.EXPIRE
    assert res.reason_code == "age_threshold_reached"
    assert res.target_memory_status is MemoryStatus.EXPIRED
    assert res.target_memory_type is None


def test_lifecycle_archive_request_removed():
    """REMOVED → ARCHIVE_REQUEST(removed_cold_data)。"""
    res = LIFECYCLE_POLICY.decide(
        make_lifecycle_snapshot(
            knowledge_id="kn_d8e_flow_lc_arc",
            memory_status=MemoryStatus.REMOVED,
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.ARCHIVE_REQUEST
    assert res.reason_code == "removed_cold_data"
    assert res.target_memory_type is None
    assert res.target_memory_status is None


def test_lifecycle_candidate_no_auto_promote():
    """CANDIDATE + 高 confidence/高 usage → HOLD(candidate_requires_confirmation)。"""
    res = LIFECYCLE_POLICY.decide(
        make_lifecycle_snapshot(
            knowledge_id="kn_d8e_flow_lc_cand2",
            memory_status=MemoryStatus.CANDIDATE,
            confidence_score=0.99,
            access_count=100,
            evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "candidate_requires_confirmation"
    assert res.target_memory_type is None
    assert res.target_memory_status is None


def test_lifecycle_reason_code_explainable():
    """promote/demote/expire/archive 输出 reason_code 均属于固定权威集合、可解释。"""
    snapshots = [
        make_lifecycle_snapshot(knowledge_id="kn_d8e_flow_rc_prom"),
        make_lifecycle_snapshot(
            knowledge_id="kn_d8e_flow_rc_dem",
            memory_type=MemoryType.LONG_TERM,
            last_accessed_at=NOW - timedelta(days=40),
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
        ),
        make_lifecycle_snapshot(
            knowledge_id="kn_d8e_flow_rc_exp",
            created_at=NOW - timedelta(days=100),
            updated_at=NOW - timedelta(days=100),
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
        ),
        make_lifecycle_snapshot(
            knowledge_id="kn_d8e_flow_rc_arc",
            memory_status=MemoryStatus.REMOVED,
        ),
        make_lifecycle_snapshot(
            knowledge_id="kn_d8e_flow_rc_cand",
            memory_status=MemoryStatus.CANDIDATE,
        ),
    ]
    actions = set()
    for snap in snapshots:
        res = LIFECYCLE_POLICY.decide(snap, now=NOW)
        assert res.reason_code in EXPECTED_LIFECYCLE_REASON_CODES
        actions.add(res.action)
    # 覆盖 promote/demote/expire/archive_request 四类可执行动作
    assert LifecycleAction.PROMOTE in actions
    assert LifecycleAction.DEMOTE in actions
    assert LifecycleAction.EXPIRE in actions
    assert LifecycleAction.ARCHIVE_REQUEST in actions


# ── 9. 跨阶段一致性守卫 ──


def test_failed_event_cannot_form_success_knowledge_via_governance():
    """failed 事件 + Knowledge(fact) → 治理拒绝：抽取层遗漏也过不了治理层。"""
    event_id = "evt_d8e_flow_gov_fail"
    cand = extraction_provider.KnowledgeCandidate(
        fact="演示事实（脱敏）", category="fact", confidence=0.85,
        source_event_id=event_id,
    )
    event = make_memory_source_event(
        event_id,
        source_business_status=SourceBusinessStatus.FAILED,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d8e_flow_gov_fail",
        payload_security_checked=True,
    )
    with pytest.raises(CandidateAdmissionError) as ei:
        GOV.admit_with_event(
            cand, event, make_ctx(), entity_id="kn_d8e_flow_gov_fail",
            memory_type=MemoryType.SHORT_TERM,
        )
    assert ei.value.code == "failed_event_success_knowledge_forbidden"


def test_admission_kinds_consistent_with_extraction_output():
    """failed Tool 准入允许 {FAILURE_EXPERIENCE}，抽取输出仅 failure_experience → 一致。"""
    raw = make_raw(
        event_id="evt_d8e_flow_fail_consist",
        source_type="tool_result",
        event_type="agent_response",
        tool_call_id="tc_d8e_flow_fail_consist",
        source_business_status="failed",
        payload_security_checked=True,
    )
    admission = POLICY_ADMISSION.evaluate(
        make_pipeline_result_via_pipeline(raw), make_ctx())
    assert admission.decision is SourceAdmissionDecision.ALLOW_EXTRACTION
    assert admission.allowed_extraction_kinds == {ExtractionKind.FAILURE_EXPERIENCE}
    cands = ExtractionProvider().extract_knowledge(make_turn(
        tool_results=[make_tool_result(
            "install", "failure", error="dependency not found",
            arguments={"pkg": "vim"})],
        source_event_id="evt_d8e_flow_fail_consist",
        source="tool_result",
    ))
    assert len(cands) == 1
    # 抽取实际输出与准入限定的抽取范围一致：不产生准入范围外的成功知识
    assert all(c.category == "failure_experience" for c in cands)
    assert all(c.category != "fact" for c in cands)


def test_success_tool_knowledge_feeds_conflict_resolution():
    """success Tool 知识经治理后与模型推测冲突 → Tool 事实胜出（跨阶段链路完整）。"""
    event_id = "evt_d8e_flow_chain"
    cands = ExtractionProvider().extract_knowledge(make_turn(
        tool_results=[make_tool_result(
            "file_search", "success", result="/opt/kylin/data 目录存在且可读")],
        source_event_id=event_id,
        source="tool_result",
    ))
    assert len(cands) == 1
    event = make_memory_source_event(
        event_id,
        source_business_status=SourceBusinessStatus.SUCCESS,
        source_type=SourceType.TOOL_RESULT,
        tool_call_id="tc_d8e_flow_chain",
        payload_security_checked=True,
    )
    kn = GOV.admit_with_event(
        cands[0], event, make_ctx(), entity_id="kn_d8e_flow_chain",
        memory_type=MemoryType.SHORT_TERM,
    )
    assert isinstance(kn, domain.Knowledge)
    # 治理输出知识作为冲突一侧（真实 Tool 事实 Tier 3），与模型推测（Tier 6）冲突
    tool_side = ConflictSide(
        knowledge_id=kn.knowledge_id,
        user_id=kn.user_id,
        evidence_tier=EvidenceTier.TOOL_EXECUTION_RESULT,
        recorded_at=kn.created_at,
    )
    model_side = ConflictSide(
        knowledge_id="kn_d8e_flow_chain_model",
        user_id=kn.user_id,
        evidence_tier=EvidenceTier.MODEL_INFERENCE,
    )
    res = CONFLICT.resolve(tool_side, model_side)
    assert res.action is DecisionAction.KEEP_LEFT
    assert res.reason_code == "evidence_tier_priority"
    assert res.winner_id == "kn_d8e_flow_chain"
