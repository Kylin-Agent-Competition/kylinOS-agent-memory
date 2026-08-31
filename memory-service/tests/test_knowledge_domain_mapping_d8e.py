"""
test_knowledge_domain_mapping_d8e.py — Day8 E 轨六类知识结构化字段无损承载测试

对齐任务卡：day8-e-01-knowledge-domain-structure-v1
（TD-017 关闭：KnowledgeCandidate v0.2 六类共 13 个结构化可选字段在
Candidate Governance 转换为 E 轨 Knowledge Domain 时无损、向后兼容承载）。

覆盖范围：
- 六种 KnowledgeType 均有 Candidate→Governance→Knowledge 映射覆盖；
- 13 个结构化可选字段（conditions / evidence / steps / expected_result /
  problem / outcome / reproducible / template_body / parameters / priority /
  failure_reason / avoid_condition / alternative）在非空时逐字段保留且值不被改写；
- workflow 的 steps/expected_result、case 的 problem/outcome/reproducible、
  template 的 template_body/parameters、constraint 的 priority、
  failure_experience 的 failure_reason/avoid_condition/alternative 均有正向测试；
- conditions / evidence 作为通用结构化字段有独立回归测试；
- 已有 Knowledge 构造方式仍可通过（不携带结构化字段时为 None，向后兼容）；
- 未知 extra 字段仍被拒绝（extra="forbid" fail-closed 保持）；
- content_summary 非拼接，user_id 只来自 ctx，source_event_id 直接相等，
  confidence_score 数值不变，memory_status 恒 candidate。

不在本任务范围内（保持不修改/不验证）：
- 不改 A 轨抽取契约（extraction_provider.py / knowledge_rules.py）；
- 不新增第二套 KnowledgeType 或共享知识分类枚举；
- 不涉及 SQLite / Repository / Migration / Outbox / Vector / FTS5 / IPC / C++ / QML；
- 不涉及 Day7E preference_business_policy / preference_version_policy。

测试纪律：
- 不使用 Mock、skip、xfail、条件跳过或弱化断言；
- 正向值验证使用精确 `==` 比较（非 `is not None`），默认 None 场景除外；
- 测试数据仅使用合成用户 ID（user_demo_d8e）、合成事件 ID（evt_d8e_*）、
  合成实体 ID（kn_d8e_*）与脱敏内容。
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import domain  # noqa: E402
from domain.enums import KnowledgeType, MemoryStatus  # noqa: E402
from pipeline.schemas import (  # noqa: E402
    EventType,
    MemorySourceEvent,
    MemoryType,
    SensitivityLevel,
    SourceBusinessStatus,
    SourceType,
)
from providers import extraction_provider  # noqa: E402
from service.candidate_governance import (  # noqa: E402
    CandidateGovernanceService,
)
from service.contracts import ServiceRequestContext  # noqa: E402

# ── 合成数据基座（不含任何真实用户数据/密钥） ──

USER = "user_demo_d8e"
ACTOR = "actor_demo_d8e"
T0 = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)

# 六类分类 → 每类应携带的结构化字段（用于覆盖六类映射）
CATEGORY_STRUCTURED_FIELDS = {
    "workflow": ("steps", "expected_result"),
    "case": ("problem", "outcome", "reproducible"),
    "template": ("template_body", "parameters"),
    "constraint": ("priority",),
    "failure_experience": ("failure_reason", "avoid_condition", "alternative"),
    "fact": (),
}

# 13 个结构化字段全表
ALL_STRUCTURED_FIELDS = (
    "conditions",
    "evidence",
    "steps",
    "expected_result",
    "problem",
    "outcome",
    "reproducible",
    "template_body",
    "parameters",
    "priority",
    "failure_reason",
    "avoid_condition",
    "alternative",
)


def make_ctx() -> ServiceRequestContext:
    """可信业务上下文（user_id 唯一来源）。"""
    return ServiceRequestContext(user_id=USER, actor_id=ACTOR)


def make_event(
    event_id: str,
    source_business_status=SourceBusinessStatus.COMPLETED,
    **overrides,
) -> MemorySourceEvent:
    """构造合成 MemorySourceEvent（pipeline.schemas 真实模型）。"""
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
        "session_id": "sess_d8e_01",
    }
    data.update(overrides)
    return MemorySourceEvent(**data)


def make_know_candidate(**overrides) -> extraction_provider.KnowledgeCandidate:
    """构造合成 KnowledgeCandidate（A 轨真实模型，非重定义）。"""
    data = {
        "fact": "演示知识：六类结构化字段无损承载（脱敏）",
        "category": "workflow",
        "confidence": 0.6,
        "source_event_id": "evt_d8e_kn_01",
    }
    data.update(overrides)
    return extraction_provider.KnowledgeCandidate(**data)


def _admit(
    gov: CandidateGovernanceService,
    candidate: extraction_provider.KnowledgeCandidate,
    event: MemorySourceEvent,
) -> domain.Knowledge:
    """经公开 admit_with_event() 事件门禁转换为 Knowledge Domain。"""
    result = gov.admit_with_event(
        candidate,
        event,
        make_ctx(),
        entity_id="kn_d8e_map",
        memory_type=MemoryType.SHORT_TERM,
    )
    assert isinstance(result, domain.Knowledge)
    return result


# ── 六种 KnowledgeType 映射覆盖 ──


def test_d8e_six_knowledge_types_mapping():
    """六种 KnowledgeType 均有 Candidate→Governance→Knowledge 映射覆盖。

    failure_experience 使用 FAILED 事件（真实失败语义路径），其余使用 COMPLETED。
    """
    gov = CandidateGovernanceService()
    ctx_user = USER
    cases = {
        "fact": (SourceBusinessStatus.COMPLETED, {"fact": "演示事实（脱敏）"}),
        "workflow": (SourceBusinessStatus.COMPLETED, {"fact": "演示流程（脱敏）"}),
        "case": (SourceBusinessStatus.COMPLETED, {"fact": "演示案例（脱敏）"}),
        "template": (SourceBusinessStatus.COMPLETED, {"fact": "演示模板（脱敏）"}),
        "constraint": (SourceBusinessStatus.COMPLETED, {"fact": "演示约束（脱敏）"}),
        "failure_experience": (
            SourceBusinessStatus.FAILED,
            {"fact": "演示失败经验（脱敏）"},
        ),
    }
    for category, (status, extra) in cases.items():
        event_id = f"evt_d8e_type_{category}"
        cand = make_know_candidate(
            category=category,
            source_event_id=event_id,
            **extra,
        )
        event = make_event(event_id=event_id, source_business_status=status)
        result = _admit(gov, cand, event)
        assert result.knowledge_type is KnowledgeType(category)
        assert result.user_id == ctx_user  # user_id 只来自 ctx
    # 六类确实是有值映射（非空集校验：六类都存在于枚举）
    assert len(cases) == 6


# ── 各类别结构化字段正向无损承载 ──


def test_d8e_workflow_steps_expected_result_preserved():
    """workflow 的 steps / expected_result 正向无损保留。"""
    gov = CandidateGovernanceService()
    event_id = "evt_d8e_workflow_01"
    cand = make_know_candidate(
        category="workflow",
        source_event_id=event_id,
        steps="步骤一：备份；步骤二：升级（脱敏）",
        expected_result="升级成功且数据无缺失（脱敏）",
    )
    result = _admit(gov, cand, make_event(event_id=event_id))
    assert result.steps == "步骤一：备份；步骤二：升级（脱敏）"
    assert result.expected_result == "升级成功且数据无缺失（脱敏）"


def test_d8e_case_problem_outcome_reproducible_preserved():
    """case 的 problem / outcome / reproducible 正向无损保留。"""
    gov = CandidateGovernanceService()
    event_id = "evt_d8e_case_01"
    cand = make_know_candidate(
        category="case",
        source_event_id=event_id,
        problem="备份任务突然中断（脱敏）",
        outcome="回滚至上一版本后恢复（脱敏）",
        reproducible="可复现（脱敏）",
    )
    result = _admit(gov, cand, make_event(event_id=event_id))
    assert result.problem == "备份任务突然中断（脱敏）"
    assert result.outcome == "回滚至上一版本后恢复（脱敏）"
    assert result.reproducible == "可复现（脱敏）"


def test_d8e_template_body_parameters_preserved():
    """template 的 template_body / parameters 正向无损保留。"""
    gov = CandidateGovernanceService()
    event_id = "evt_d8e_template_01"
    cand = make_know_candidate(
        category="template",
        source_event_id=event_id,
        template_body="## 周报\n- 完成事项\n- 待办事项（脱敏）",
        parameters="project={P}; owner={O}（脱敏）",
    )
    result = _admit(gov, cand, make_event(event_id=event_id))
    assert result.template_body == "## 周报\n- 完成事项\n- 待办事项（脱敏）"
    assert result.parameters == "project={P}; owner={O}（脱敏）"


def test_d8e_constraint_priority_preserved():
    """constraint 的 priority 正向无损保留。"""
    gov = CandidateGovernanceService()
    event_id = "evt_d8e_constraint_01"
    cand = make_know_candidate(
        category="constraint",
        source_event_id=event_id,
        priority="high（脱敏）",
    )
    result = _admit(gov, cand, make_event(event_id=event_id))
    assert result.priority == "high（脱敏）"


def test_d8e_failure_experience_fields_preserved():
    """failure_experience 的 failure_reason / avoid_condition / alternative 正向无损保留。"""
    gov = CandidateGovernanceService()
    event_id = "evt_d8e_failure_01"
    cand = make_know_candidate(
        category="failure_experience",
        source_event_id=event_id,
        failure_reason="磁盘空间不足（脱敏）",
        avoid_condition="升级前预留充足磁盘（脱敏）",
        alternative="改用增量备份（脱敏）",
    )
    event = make_event(event_id=event_id, source_business_status=SourceBusinessStatus.FAILED)
    result = _admit(gov, cand, event)
    assert result.failure_reason == "磁盘空间不足（脱敏）"
    assert result.avoid_condition == "升级前预留充足磁盘（脱敏）"
    assert result.alternative == "改用增量备份（脱敏）"


# ── 通用结构化字段独立回归 ──


def test_d8e_common_conditions_preserved():
    """conditions 作为通用结构化字段跨类别独立回归。"""
    gov = CandidateGovernanceService()
    for category, status in (
        ("workflow", SourceBusinessStatus.COMPLETED),
        ("constraint", SourceBusinessStatus.COMPLETED),
        ("failure_experience", SourceBusinessStatus.FAILED),
    ):
        event_id = f"evt_d8e_cond_{category}"
        cand = make_know_candidate(
            category=category,
            source_event_id=event_id,
            fact=f"演示{category}（脱敏）",
            conditions="仅在目标环境满足时适用（脱敏）",
        )
        result = _admit(gov, cand, make_event(event_id=event_id, source_business_status=status))
        assert result.conditions == "仅在目标环境满足时适用（脱敏）"


def test_d8e_common_evidence_preserved():
    """evidence 作为通用结构化字段跨类别独立回归（R3 系统可信来源承载）。"""
    gov = CandidateGovernanceService()
    for category, status in (
        ("workflow", SourceBusinessStatus.COMPLETED),
        ("case", SourceBusinessStatus.COMPLETED),
        ("failure_experience", SourceBusinessStatus.FAILED),
    ):
        event_id = f"evt_d8e_evid_{category}"
        cand = make_know_candidate(
            category=category,
            source_event_id=event_id,
            fact=f"演示{category}（脱敏）",
            evidence="系统工具输出：已验证命令成功（脱敏）",
        )
        result = _admit(gov, cand, make_event(event_id=event_id, source_business_status=status))
        assert result.evidence == "系统工具输出：已验证命令成功（脱敏）"


# ── 13 个字段完整无损 + 值不被改写 ──


def test_d8e_all_13_fields_preserved_together():
    """13 个结构化字段在非空时可逐字段保留且值不被改写。"""
    gov = CandidateGovernanceService()
    event_id = "evt_d8e_all_01"
    structured = {
        "conditions": "演示适用条件（脱敏）",
        "evidence": "演示证据：真实工具输出（脱敏）",
        "steps": "演示步骤（脱敏）",
        "expected_result": "演示期望结果（脱敏）",
        "problem": "演示问题（脱敏）",
        "outcome": "演示结果（脱敏）",
        "reproducible": "演示是否复现（脱敏）",
        "template_body": "演示模板正文（脱敏）",
        "parameters": "演示参数（脱敏）",
        "priority": "演示优先级（脱敏）",
        "failure_reason": "演示失败原因（脱敏）",
        "avoid_condition": "演示避免条件（脱敏）",
        "alternative": "演示替代方案（脱敏）",
    }
    cand = make_know_candidate(category="workflow", source_event_id=event_id, **structured)
    result = _admit(gov, cand, make_event(event_id=event_id))
    for field in ALL_STRUCTURED_FIELDS:
        assert getattr(result, field) == structured[field], field


def test_d8e_fields_not_rewritten():
    """结构化字段值不被改写：特殊字符 / 空格 / 中文逐字节完全相等。"""
    gov = CandidateGovernanceService()
    event_id = "evt_d8e_no_rewrite_01"
    # 值含前导/尾随空格、特殊符号、换行、中文，验证非截断、非修剪、非拼接
    cand = make_know_candidate(
        category="template",
        source_event_id=event_id,
        conditions="  条件含空格与符号：A & B | C  ",
        steps=" 步骤一\n步骤二\n(含特殊符号：$ @ #) ",
        template_body="模板正文：标题 {{T}}\nbody 使用 <- and -> （脱敏）",
        parameters='{"key": "value", "nested": [1, 2]}（脱敏）',
    )
    result = _admit(gov, cand, make_event(event_id=event_id))
    assert result.conditions == "  条件含空格与符号：A & B | C  "
    assert result.steps == " 步骤一\n步骤二\n(含特殊符号：$ @ #) "
    assert result.template_body == "模板正文：标题 {{T}}\nbody 使用 <- and -> （脱敏）"
    assert result.parameters == '{"key": "value", "nested": [1, 2]}（脱敏）'


# ── 向后兼容：不携带结构化字段 ──


def test_d8e_backward_compatible_no_structured_fields():
    """既有 Knowledge 构造方式（不带结构化字段）仍可通过，13 字段为 None。"""
    gov = CandidateGovernanceService()
    event_id = "evt_d8e_legacy_01"
    cand = make_know_candidate(category="fact", source_event_id=event_id)
    result = _admit(gov, cand, make_event(event_id=event_id))
    for field in ALL_STRUCTURED_FIELDS:
        assert getattr(result, field) is None, field


def test_d8e_structured_fields_default_none_in_domain():
    """Domain 层向后兼容：直接构造 Knowledge 不提供结构化字段时均为 None。"""
    kn = domain.Knowledge(
        knowledge_id="kn_d8e_none_01",
        user_id=USER,
        knowledge_type=KnowledgeType.FACT,
        memory_type=MemoryType.SHORT_TERM,
        memory_status=MemoryStatus.CANDIDATE,
        source_event_id="evt_d8e_none_01",
        content_summary="演示事实（脱敏）",
        confidence_score=0.5,
        requires_embedding=True,
        is_outdated=False,
        created_at=T0,
        updated_at=T0,
    )
    for field in ALL_STRUCTURED_FIELDS:
        assert getattr(kn, field) is None, field


def test_d8e_knowledge_domain_extra_field_still_rejected():
    """未知 extra 字段仍被拒绝（extra="forbid" fail-closed 保持）。

    新增 13 个结构化字段为已声明字段，非静默接受未知字段：
    未声明的 unexpected_field 依旧触发 ValidationError。
    """
    with pytest.raises(ValidationError):
        domain.Knowledge(
            knowledge_id="kn_d8e_extra_01",
            user_id=USER,
            knowledge_type=KnowledgeType.FACT,
            memory_type=MemoryType.SHORT_TERM,
            memory_status=MemoryStatus.CANDIDATE,
            source_event_id="evt_d8e_extra_01",
            content_summary="演示事实（脱敏）",
            confidence_score=0.5,
            requires_embedding=True,
            is_outdated=False,
            created_at=T0,
            updated_at=T0,
            unexpected_field="x",
        )


# ── failed 事件 + failure_experience 端到端 ──


def test_d8e_failure_experience_with_failed_event_admission():
    """FAILED 事件 + failure_experience 结构字段端到端：门禁通过且无损保留。"""
    gov = CandidateGovernanceService()
    event_id = "evt_d8e_failed_e2e_01"
    structured = {
        "failure_reason": "磁盘满导致备份失败（脱敏）",
        "avoid_condition": "备份前检查磁盘（脱敏）",
        "alternative": "改用增量备份（脱敏）",
    }
    cand = make_know_candidate(
        category="failure_experience",
        source_event_id=event_id,
        **structured,
    )
    event = make_event(event_id=event_id, source_business_status=SourceBusinessStatus.FAILED)
    result = _admit(gov, cand, event)
    assert result.knowledge_type is KnowledgeType.FAILURE_EXPERIENCE
    assert result.failure_reason == "磁盘满导致备份失败（脱敏）"
    assert result.avoid_condition == "备份前检查磁盘（脱敏）"
    assert result.alternative == "改用增量备份（脱敏）"


# ── 核心字段映射不受结构化字段影响 ──


def test_d8e_core_fields_unchanged_with_structured():
    """携带结构化字段时，核心字段映射不受影响（content_summary 非拼接、user_id 来自 ctx、
    source_event_id 直接相等、confidence 不变、memory_status 恒 candidate）。"""
    gov = CandidateGovernanceService()
    event_id = "evt_d8e_core_01"
    fact_text = "演示事实正文：左右或对照（脱敏）"
    lifetime = {
        "conditions": "演示条件（脱敏）",
        "steps": "演示步骤（脱敏）",
        "evidence": "演示证据（脱敏）",
        "priority": "演示优先级（脱敏）",
    }
    cand = make_know_candidate(
        category="workflow",
        source_event_id=event_id,
        fact=fact_text,
        confidence=0.42,
        **lifetime,
    )
    result = _admit(gov, cand, make_event(event_id=event_id))
    # content_summary 精确等于 fact，绝不拼接结构化字段伪装无损承载
    assert result.content_summary == fact_text
    assert result.source_event_id == event_id  # 直接相等（R3）
    assert result.user_id == USER  # user_id 只来自 ctx
    assert result.confidence_score == 0.42  # 数值不变
    assert result.memory_status is MemoryStatus.CANDIDATE
    # 结构化字段仍无损保留（拼接行为不吞字段）
    assert result.steps == "演示步骤（脱敏）"
    assert result.conditions == "演示条件（脱敏）"
