"""
test_candidate_governance_d5e.py — Day5 E 轨 Candidate→Domain 业务治理单元测试

对齐任务卡：day5-e-01-candidate-domain-governance-v1
（复用 A 轨 Candidate，建立最小业务准入，构造 E 轨正式 Domain）。

覆盖范围：
- 正向 Preference：返回 Preference Domain、user_id 来自 ctx、
  evidence_event_ids 包含原 source_event_id、confidence 数值不变、字段映射、
  candidate 状态保持、now 确定性。
- 正向 Knowledge：返回 Knowledge Domain、source_event_id 直接相等、
  user_id 来自 ctx、confidence 数值不变、六值 category 映射、memory_type
  默认与覆盖、candidate 状态保持。
- 边界（不无依据提升）：临时 / 不持久偏好仍为 candidate、非 active。
- 非法转换路径：非候选类型 / None / 非法 ctx / 空 entity_id /
  非 candidate 状态防御（model_construct 模拟污染候选）/ Domain 构造失败包装。
- 导入契约：治理服务不进入 service.__all__（守护既有严格门禁）；
  复用的是 A 轨 Candidate 类型与 E 轨 Domain 类（identity/isinstance）。

测试纪律：
- 不使用 Mock、skip、xfail 或固定 PASS 结果。
- model_construct 仅用于模拟"被污染 / DB 载入"候选，验证 B2 防御守卫，
  不冒充真实业务验证。
- 测试数据仅使用合成用户 ID（user_demo_d5e）、合成事件 ID（evt_d5e_*）与脱敏内容。
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
    KnowledgeType,
    MemoryStatus,
    PreferenceScope,
)
from pipeline.schemas import MemoryType  # noqa: E402
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


def make_ctx() -> ServiceRequestContext:
    """可信业务上下文（user_id 唯一来源）。"""
    return ServiceRequestContext(user_id=USER, actor_id=ACTOR)


def make_pref_candidate(**overrides) -> extraction_provider.PreferenceCandidate:
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
        "source_event_id": "evt_d5e_pref_01",
    }
    data.update(overrides)
    return extraction_provider.PreferenceCandidate(**data)


def make_know_candidate(**overrides) -> extraction_provider.KnowledgeCandidate:
    """构造合成 KnowledgeCandidate（A 轨真实模型，非重定义）。"""
    data = {
        "fact": "演示知识：按修改日期降序排列文件（脱敏）",
        "category": "workflow",
        "confidence": 0.6,
        "source_event_id": "evt_d5e_kn_01",
    }
    data.update(overrides)
    return extraction_provider.KnowledgeCandidate(**data)


def make_preference_domain() -> domain.Preference:
    """构造合成 Preference Domain 实例（用于非法类型准入测试）。"""
    return domain.Preference(
        preference_id="pref_d5e_domain",
        user_id=USER,
        expression_type=ExpressionType.EXPLICIT,
        preference_scope=PreferenceScope.TOPIC,
        preference_key="demo_sort_order",
        preference_value="by_modified_desc",
        confidence_score=0.8,
        memory_status=MemoryStatus.ACTIVE,
        is_active=True,
        is_temporary=False,
        should_persist=True,
        should_decay=False,
        evidence_event_ids=["evt_d5e_pref_01"],
        version=1,
        created_at=T0,
        updated_at=T0,
        requires_confirmation=False,
    )


# ── 正向：PreferenceCandidate → Preference ──


def test_admit_preference_returns_preference_domain():
    gov = CandidateGovernanceService()
    result = gov.admit(make_pref_candidate(), make_ctx(), entity_id="pref_d5e_01")
    assert isinstance(result, domain.Preference)


def test_admit_preference_user_id_from_context():
    gov = CandidateGovernanceService()
    result = gov.admit(make_pref_candidate(), make_ctx(), entity_id="pref_d5e_02")
    assert result.user_id == USER
    # 候选模型无 user_id 字段，不存在正文推导路径
    assert "user_id" not in extraction_provider.PreferenceCandidate.model_fields


def test_admit_preference_evidence_contains_source_event_id():
    gov = CandidateGovernanceService()
    cand = make_pref_candidate(source_event_id="evt_d5e_pref_03")
    result = gov.admit(cand, make_ctx(), entity_id="pref_d5e_03")
    assert result.evidence_event_ids == ["evt_d5e_pref_03"]


def test_admit_preference_confidence_score_unchanged():
    """Candidate confidence → Domain confidence_score，数值含义不变（含 strict 边界值）。"""
    gov = CandidateGovernanceService()
    ctx = make_ctx()
    for confidence in (0.0, 1.0, 0.5):
        cand = make_pref_candidate(confidence=confidence)
        result = gov.admit(cand, ctx, entity_id="pref_d5e_conf")
        assert result.confidence_score == confidence


def test_admit_preference_field_mapping():
    gov = CandidateGovernanceService()
    cand = make_pref_candidate(
        key="demo_sort_order",
        value="by_modified_desc",
        scope="global",
        explicitness="implicit",
        is_temporary=False,
        should_persist=True,
    )
    result = gov.admit(cand, make_ctx(), entity_id="pref_d5e_map")
    assert result.preference_key == "demo_sort_order"
    assert result.preference_value == "by_modified_desc"
    assert result.preference_scope is PreferenceScope.GLOBAL
    assert result.expression_type is ExpressionType.IMPLICIT
    assert result.is_temporary is False
    assert result.should_persist is True


def test_admit_preference_candidate_status_preserved():
    """Candidate 业务状态保持：恒 candidate、未激活、v1、需确认。"""
    gov = CandidateGovernanceService()
    result = gov.admit(make_pref_candidate(), make_ctx(), entity_id="pref_d5e_st")
    assert result.memory_status is MemoryStatus.CANDIDATE
    assert result.is_active is False
    assert result.version == 1
    assert result.previous_version_id is None
    assert result.requires_confirmation is True
    assert result.should_decay is False


def test_admit_preference_now_override_deterministic():
    gov = CandidateGovernanceService()
    result = gov.admit(
        make_pref_candidate(), make_ctx(), entity_id="pref_d5e_now", now=T0
    )
    assert result.created_at == T0
    assert result.updated_at == T0


# ── 正向：KnowledgeCandidate → Knowledge ──


def test_admit_knowledge_returns_knowledge_domain():
    gov = CandidateGovernanceService()
    result = gov.admit(make_know_candidate(), make_ctx(), entity_id="kn_d5e_01")
    assert isinstance(result, domain.Knowledge)


def test_admit_knowledge_source_event_id_equal():
    """Knowledge.source_event_id 与原 Candidate.source_event_id 直接相等（R3）。"""
    gov = CandidateGovernanceService()
    cand = make_know_candidate(source_event_id="evt_d5e_kn_02")
    result = gov.admit(cand, make_ctx(), entity_id="kn_d5e_02")
    assert result.source_event_id == "evt_d5e_kn_02"


def test_admit_knowledge_user_id_from_context():
    gov = CandidateGovernanceService()
    result = gov.admit(make_know_candidate(), make_ctx(), entity_id="kn_d5e_03")
    assert result.user_id == USER
    assert "user_id" not in extraction_provider.KnowledgeCandidate.model_fields


def test_admit_knowledge_confidence_unchanged():
    gov = CandidateGovernanceService()
    ctx = make_ctx()
    for confidence in (0.0, 1.0, 0.42):
        cand = make_know_candidate(confidence=confidence)
        result = gov.admit(cand, ctx, entity_id="kn_d5e_conf")
        assert result.confidence_score == confidence


def test_admit_knowledge_field_mapping():
    """knowledge_type ← category 六值各覆盖一例；memory_type 默认 SHORT_TERM 且可覆盖。"""
    gov = CandidateGovernanceService()
    ctx = make_ctx()
    facts = {
        "fact": "演示事实：中国农历闰年有 366 天（脱敏）",
        "workflow": "演示流程：先备份再升级（脱敏）",
        "case": "演示案例：昨日升级失败后回滚（脱敏）",
        "template": "演示模板：项目周报模板（脱敏）",
        "constraint": "演示约束：部署前必须备份（脱敏）",
        "failure_experience": "演示失败经验：磁盘满导致备份失败（脱敏）",
    }
    for category, fact in facts.items():
        cand = make_know_candidate(fact=fact, category=category)
        result = gov.admit(cand, ctx, entity_id=f"kn_d5e_{category}")
        assert isinstance(result, domain.Knowledge)
        assert result.knowledge_type is KnowledgeType(category)
        assert result.content_summary == fact
        assert result.memory_type is MemoryType.SHORT_TERM  # 默认最保守分类
    # memory_type 可由调用方覆盖（业务分类，非身份推导）
    cand = make_know_candidate(category="fact")
    result = gov.admit(
        cand, ctx, entity_id="kn_d5e_override", memory_type=MemoryType.LONG_TERM
    )
    assert result.memory_type is MemoryType.LONG_TERM


def test_admit_knowledge_candidate_status_preserved():
    gov = CandidateGovernanceService()
    result = gov.admit(make_know_candidate(), make_ctx(), entity_id="kn_d5e_st")
    assert result.memory_status is MemoryStatus.CANDIDATE
    assert result.is_outdated is False
    assert result.requires_embedding is True


# ── 边界：不无依据提升 ──


def test_admit_temporary_preference_stays_candidate():
    gov = CandidateGovernanceService()
    cand = make_pref_candidate(is_temporary=True, should_persist=False)
    result = gov.admit(cand, make_ctx(), entity_id="pref_d5e_temp")
    assert result.memory_status is MemoryStatus.CANDIDATE
    assert result.is_active is False
    assert result.is_temporary is True
    assert result.should_persist is False  # 非稳定长期状态


def test_admit_no_persist_preference_stays_candidate():
    gov = CandidateGovernanceService()
    cand = make_pref_candidate(is_temporary=False, should_persist=False)
    result = gov.admit(cand, make_ctx(), entity_id="pref_d5e_np")
    assert result.memory_status is MemoryStatus.CANDIDATE
    assert result.is_active is False
    assert result.should_persist is False


def test_admit_temporary_preference_not_active():
    gov = CandidateGovernanceService()
    cand = make_pref_candidate(is_temporary=True)
    result = gov.admit(cand, make_ctx(), entity_id="pref_d5e_temp2")
    assert result.memory_status is not MemoryStatus.ACTIVE
    assert result.memory_status is MemoryStatus.CANDIDATE


# ── 非法转换路径 ──


def test_admit_rejects_non_candidate_type():
    gov = CandidateGovernanceService()
    ctx = make_ctx()
    for bad in ({}, make_preference_domain()):
        with pytest.raises(CandidateAdmissionError) as ei:
            gov.admit(bad, ctx, entity_id="pref_d5e_bad")
        assert ei.value.code == "invalid_candidate_type"


def test_admit_rejects_none_candidate():
    gov = CandidateGovernanceService()
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit(None, make_ctx(), entity_id="pref_d5e_none")
    assert ei.value.code == "invalid_candidate_type"


def test_admit_rejects_invalid_context():
    gov = CandidateGovernanceService()
    cand = make_pref_candidate()
    for bad_ctx in ({}, None):
        with pytest.raises(CandidateAdmissionError) as ei:
            gov.admit(cand, bad_ctx, entity_id="pref_d5e_ctx")
        assert ei.value.code == "invalid_context"


def test_admit_rejects_empty_entity_id():
    gov = CandidateGovernanceService()
    cand = make_pref_candidate()
    for bad_id in ("", "   ", 123, None):
        with pytest.raises(CandidateAdmissionError) as ei:
            gov.admit(cand, make_ctx(), entity_id=bad_id)
        assert ei.value.code == "empty_entity_id"


def test_admit_rejects_non_candidate_status_defensive():
    """model_construct 模拟被污染 / DB 载入候选 → B2 防御拒绝（非 Mock 冒充业务）。"""
    polluted = extraction_provider.PreferenceCandidate.model_construct(
        key="demo_key",
        value="demo_value",
        confidence=0.5,
        evidence="demo",
        source_event_id="evt_d5e_pref_01",
        memory_status="active",
    )
    gov = CandidateGovernanceService()
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit(polluted, make_ctx(), entity_id="pref_d5e_polluted")
    assert ei.value.code == "candidate_status_violation"


def test_admit_knowledge_rejects_non_candidate_status_defensive():
    polluted = extraction_provider.KnowledgeCandidate.model_construct(
        fact="demo fact",
        confidence=0.5,
        source_event_id="evt_d5e_kn_01",
        memory_status="verified",
    )
    gov = CandidateGovernanceService()
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit(polluted, make_ctx(), entity_id="kn_d5e_polluted")
    assert ei.value.code == "candidate_status_violation"


def test_admit_wraps_domain_validation_error():
    """Domain 构造失败包装为 domain_construction_failed 且保留 __cause__。

    model_construct 跳过模型层校验：字段被污染（key 为空串）后进入
    Domain 构造路径，验证 ValidationError 包装契约（非 Mock 冒充业务）。
    """
    polluted = extraction_provider.PreferenceCandidate.model_construct(
        key="",
        value="demo_value",
        confidence=0.5,
        evidence="demo",
        source_event_id="evt_d5e_pref_01",
        memory_status="candidate",
    )
    gov = CandidateGovernanceService()
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit(polluted, make_ctx(), entity_id="pref_d5e_polluted2")
    assert ei.value.code == "domain_construction_failed"
    assert ei.value.__cause__ is not None


def test_admission_error_str_does_not_leak_candidate_content():
    """错误 __str__ 为 "[code] message"，且不输出候选正文原文。"""
    cand = make_pref_candidate(value="非常敏感的用户偏好内容")
    gov = CandidateGovernanceService()
    with pytest.raises(CandidateAdmissionError) as ei:
        gov.admit(cand, make_ctx(), entity_id="")
    assert str(ei.value) == "[empty_entity_id] entity_id must be a non-blank string"
    assert "非常敏感的用户偏好内容" not in str(ei.value)


# ── 导入与边界契约 ──


def test_candidate_governance_not_in_service_all():
    """治理服务不进入 service.__all__（守护 test_business_boundaries 严格门禁）。"""
    assert "CandidateGovernanceService" not in service.__all__
    assert "CandidateAdmissionError" not in service.__all__


def test_candidate_governance_reuses_a_track_candidate_types():
    """治理层引用的 Candidate 类型即 providers 模块内对象（identity，非第二套）。"""
    import service.candidate_governance as cg

    assert cg.PreferenceCandidate is extraction_provider.PreferenceCandidate
    assert cg.KnowledgeCandidate is extraction_provider.KnowledgeCandidate


def test_candidate_governance_reuses_e_track_domain():
    """构造结果为 domain 包内类实例（isinstance，复用 E 轨正式 Domain）。"""
    from domain import Knowledge as DomainKnowledge
    from domain import Preference as DomainPreference

    gov = CandidateGovernanceService()
    ctx = make_ctx()
    pref = gov.admit(make_pref_candidate(), ctx, entity_id="pref_d5e_reuse")
    kn = gov.admit(make_know_candidate(), ctx, entity_id="kn_d5e_reuse")
    assert isinstance(pref, DomainPreference)
    assert isinstance(kn, DomainKnowledge)