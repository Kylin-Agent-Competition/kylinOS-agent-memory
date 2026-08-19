"""
test_cross_session_business_case_d5e.py — Day5 E 轨跨会话偏好业务样例回归测试

对齐任务卡：day5-e-03-cross-session-business-case-v1
（使用合成但契约真实的两个 session 事件，验证显式长期偏好 Candidate 经过
 E 轨治理后形成可追溯 Preference Domain，且其 scope 与生命周期语义允许
 后续跨会话复用；同时验证临时偏好不能错误获得跨会话持久化资格）。

覆盖范围（对齐 8 项验收标准）：
- AC1：Session A 的长期显式偏好进入 Preference Domain（admit_with_event 治理产出
  domain.Preference，memory_status 保持 candidate，不无依据提升）。
- AC2：Preference 可追溯回 Session A source_event_id（evidence_event_ids）。
- AC3：Preference.user_id 保持可信用户归属（来自 ServiceRequestContext，候选模型
  无 user_id 字段，不存在正文推导路径）。
- AC4：Preference scope=global 且 should_persist=true / is_temporary=false /
  requires_confirmation=true 语义允许未来跨 session 复用（资格判定 helper）。
- AC5：Session B 具有与 Session A 不同的 session_id（同一 user_id 归属）。
- AC6：同一 user_id 下证明长期 Preference 不是 session 临时偏好（资格对比）。
- AC7：临时偏好（is_temporary=true）与 should_persist=false 负例不得被标记为
  稳定跨会话偏好。
- AC8：测试文字明确声明本 Task 不验证实际检索、数据库持久化或 Context 注入。

明确不验证（本测试不做任何检索/存储/注入断言）：
- 不验证向量检索 / Vector 检索（README 明确未完成，B 轨范围）；
- 不验证数据库持久化（SQLite 持久化属 D 轨，README 明确未完成）；
- 不验证 MemoryContext 注入（官方 AI 助手 Memory Context 属 C 轨，README
  明确未完成）；
- 不调用真实 LLM（LLM 真实调用 / LLM real invocation 不在本任务范围）；
- 不验证麒麟 Runtime（本任务为纯 WSL 单元测试，runtime_required=false）；
- 不验证 OS Agent Hook（官方 AI 助手 Hook 未集成，README 明确未完成）。

跨会话资格判定说明：
- "跨会话稳定持久化资格"为从 D3 §7.9（临时边界）+ Schema §2.9（scope 语义）
  合成的业务判定，非已冻结的显式契约：should_persist=true AND is_temporary=false
  AND preference_scope=global 三者同时满足才具备资格。
- memory_status=CANDIDATE 不影响资格判定——资格是"语义允许未来复用"，
  不是"已激活"（candidate→active 晋升流程属 DEFERRED，本测试不声称已实现）。

测试纪律：
- 不使用 Mock、skip、xfail 或固定 PASS 结果。
- 只复用现有真实契约类型（PreferenceCandidate / MemorySourceEvent /
  ServiceRequestContext / Preference），不创建测试专用平行 Schema。
- 测试数据仅使用合成 user_id（user_demo_d5e）、合成 event_id（evt_d5e_cs_*）、
  合成 session_id（sess_d5e_cs_*）与脱敏内容，不使用真实用户敏感数据。
- 不依赖网络、真实 LLM 或数据库。
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import domain  # noqa: E402
import service  # noqa: E402
from domain.enums import ExpressionType, MemoryStatus, PreferenceScope  # noqa: E402
from pipeline.schemas import (  # noqa: E402
    EventType,
    MemorySourceEvent,
    SensitivityLevel,
    SourceBusinessStatus,
    SourceType,
)
from providers import extraction_provider  # noqa: E402
from service.candidate_governance import CandidateGovernanceService  # noqa: E402
from service.contracts import ServiceRequestContext  # noqa: E402

# ── 合成数据基座（不含任何真实用户数据/密钥） ──

USER = "user_demo_d5e"
ACTOR = "actor_demo_d5e"
SESSION_A = "sess_d5e_cs_a"
SESSION_B = "sess_d5e_cs_b"
EVT_A = "evt_d5e_cs_a_01"
EVT_B = "evt_d5e_cs_b_01"
T0 = datetime(2026, 8, 20, 9, 0, 0, tzinfo=timezone.utc)   # Session A
T1 = datetime(2026, 8, 20, 14, 0, 0, tzinfo=timezone.utc)  # Session B


def make_ctx(session_id: str, user_id: str = USER) -> ServiceRequestContext:
    """可信业务上下文（user_id 唯一来源；session_id 承载跨会话区分）。"""
    return ServiceRequestContext(user_id=user_id, actor_id=ACTOR, session_id=session_id)


def make_pref_candidate(source_event_id: str, **overrides) -> extraction_provider.PreferenceCandidate:
    """构造合成 PreferenceCandidate（A 轨真实模型，非重定义）。"""
    data = {
        "key": "demo_sort_order",
        "value": "by_modified_desc",
        "category": "presentation",
        "scope": "global",
        "confidence": 0.85,
        "explicitness": "explicit",
        "is_temporary": False,
        "should_persist": True,
        "evidence": "演示证据（脱敏）",
        "source_event_id": source_event_id,
    }
    data.update(overrides)
    return extraction_provider.PreferenceCandidate(**data)


def make_event(
    event_id: str,
    session_id: str,
    user_id: str = USER,
    occurred_at: datetime = T0,
    **overrides,
) -> MemorySourceEvent:
    """构造合成 MemorySourceEvent（pipeline.schemas 真实模型）。

    source_type 默认 CHAT（无需 tool_call_id）；source_business_status 默认
    COMPLETED（已完成事件，非 failed/cancelled/timeout/ignored）。
    """
    data = {
        "event_id": event_id,
        "user_id": user_id,
        "actor_id": ACTOR,
        "source_type": SourceType.CHAT,
        "event_type": EventType.USER_MESSAGE,
        "idempotency_key": f"idem_{event_id}",
        "source_business_status": SourceBusinessStatus.COMPLETED,
        "should_ignore": False,
        "sensitivity": SensitivityLevel.NONE,
        "occurred_at": occurred_at,
        "captured_at": occurred_at,
        "session_id": session_id,
    }
    data.update(overrides)
    return MemorySourceEvent(**data)


def _qualifies_for_cross_session_stable(pref: domain.Preference) -> bool:
    """跨会话稳定持久化资格判定（D3 §7.9 + Schema §2.9 合成推导，非冻结契约）。

    语义：should_persist=true 且 is_temporary=false 且 preference_scope=global
    三者同时满足，才具备"未来跨 session 复用"的资格；candidate 状态不影响
    资格判定（资格 ≠ 已激活）。
    """
    return (
        pref.should_persist
        and not pref.is_temporary
        and pref.preference_scope is PreferenceScope.GLOBAL
    )


def _admit_session_a() -> domain.Preference:
    """Session A 长期显式偏好候选 → 治理产出 Preference Domain（共用正例路径）。"""
    gov = CandidateGovernanceService()
    event = make_event(event_id=EVT_A, session_id=SESSION_A, occurred_at=T0)
    cand = make_pref_candidate(
        source_event_id=EVT_A,
        key="language",
        value="zh-CN",
        scope="global",
        explicitness="explicit",
        is_temporary=False,
        should_persist=True,
        confidence=0.85,
        evidence="演示证据：用户明确表达语言偏好（脱敏）",
    )
    return gov.admit_with_event(
        cand, event, make_ctx(session_id=SESSION_A), entity_id="pref_d5e_cs_a", now=T0
    )


def _admit_session_b_temporary() -> domain.Preference:
    """Session B 临时偏好候选（负例）→ 治理产出 Preference Domain。"""
    gov = CandidateGovernanceService()
    event = make_event(event_id=EVT_B, session_id=SESSION_B, occurred_at=T1)
    cand = make_pref_candidate(
        source_event_id=EVT_B,
        key="response_length",
        value="three_sentences_only",
        scope="session",
        explicitness="explicit",
        is_temporary=True,
        should_persist=False,
        confidence=0.5,
        evidence="演示证据：本次会话临时指令（脱敏）",
    )
    return gov.admit_with_event(
        cand, event, make_ctx(session_id=SESSION_B), entity_id="pref_d5e_cs_b", now=T1
    )


# ── AC1–AC4：Session A 长期显式偏好正例 ──


def test_session_a_long_term_preference_enters_preference_domain():
    """AC1：Session A 的长期显式偏好能够进入 Preference Domain。"""
    result = _admit_session_a()
    assert isinstance(result, domain.Preference)
    # 治理产出恒 candidate：不无依据提升为 active/verified
    assert result.memory_status is MemoryStatus.CANDIDATE
    assert result.is_active is False


def test_preference_traceable_to_session_a_source_event():
    """AC2：Preference 可追溯回 Session A source_event_id。"""
    result = _admit_session_a()
    assert result.evidence_event_ids == [EVT_A]
    assert EVT_A in result.evidence_event_ids


def test_preference_user_id_from_trusted_context():
    """AC3：Preference.user_id 保持可信用户归属（来自 ctx，非正文推导）。"""
    result = _admit_session_a()
    assert result.user_id == USER
    # 候选模型无 user_id 字段：不存在正文推导路径
    assert "user_id" not in extraction_provider.PreferenceCandidate.model_fields


def test_preference_scope_and_persist_allow_cross_session_reuse():
    """AC4：Preference scope 与 should_persist 语义允许未来跨 session 复用。"""
    result = _admit_session_a()
    assert result.preference_scope is PreferenceScope.GLOBAL  # 跨会话跨主题
    assert result.should_persist is True
    assert result.is_temporary is False
    # 候选需确认后方可提升——语义允许未来跨会话复用（并非已激活）
    assert result.requires_confirmation is True
    assert _qualifies_for_cross_session_stable(result) is True


# ── AC5–AC6：Session B 跨会话上下文 ──


def test_session_b_different_session_id_same_user_id():
    """AC5：Session B 与 Session A 具有不同 session_id（同一 user_id 归属）。"""
    event_a = make_event(event_id=EVT_A, session_id=SESSION_A, occurred_at=T0)
    event_b = make_event(event_id=EVT_B, session_id=SESSION_B, occurred_at=T1)
    assert SESSION_A != SESSION_B
    assert event_a.session_id != event_b.session_id
    assert event_a.user_id == event_b.user_id == USER


def test_preference_not_session_temporary_under_same_user():
    """AC6：同一 user_id 下证明长期 Preference 不是 session 临时偏好。"""
    pref_a = _admit_session_a()
    pref_b = _admit_session_b_temporary()
    assert pref_a.user_id == pref_b.user_id == USER  # 同一用户归属下对比
    assert _qualifies_for_cross_session_stable(pref_a) is True
    assert _qualifies_for_cross_session_stable(pref_b) is False
    assert pref_a.preference_scope is PreferenceScope.GLOBAL
    assert pref_b.preference_scope is PreferenceScope.SESSION


# ── AC7：负例不得获得跨会话稳定持久化资格 ──


def test_temporary_preference_not_stable_cross_session():
    """AC7a：临时偏好（is_temporary=true, should_persist=false, scope=session）
    不得被标记为稳定跨会话偏好。"""
    result = _admit_session_b_temporary()
    assert isinstance(result, domain.Preference)  # 通过治理构造为 Domain
    assert result.memory_status is MemoryStatus.CANDIDATE  # 不是 active
    assert result.is_active is False
    assert result.is_temporary is True
    assert result.should_persist is False
    assert _qualifies_for_cross_session_stable(result) is False  # 无跨会话资格


def test_no_persist_preference_not_stable_cross_session():
    """AC7b：should_persist=false 且 is_temporary=false 的候选也不具备
    跨会话稳定持久化资格（应持久化语义缺位即无资格）。"""
    gov = CandidateGovernanceService()
    event = make_event(event_id=EVT_B, session_id=SESSION_B, occurred_at=T1)
    cand = make_pref_candidate(
        source_event_id=EVT_B,
        key="response_length",
        value="three_sentences_only",
        scope="session",
        is_temporary=False,   # 与 AC7a 区别：非临时但仍不持久化
        should_persist=False,
        confidence=0.5,
        evidence="演示证据：不持久化偏好的负例（脱敏）",
    )
    result = gov.admit_with_event(
        cand, event, make_ctx(session_id=SESSION_B),
        entity_id="pref_d5e_cs_b_np", now=T1,
    )
    assert isinstance(result, domain.Preference)
    assert result.should_persist is False
    assert result.memory_status is MemoryStatus.CANDIDATE
    assert _qualifies_for_cross_session_stable(result) is False


# ── AC8：明确边界声明 ──


def test_explicit_scope_boundary_declaration():
    """AC8：测试文字明确声明本 Task 不验证实际检索、数据库持久化或 Context 注入。

    防止该声明被意外删除：断言模块 docstring 含全部关键不验证项。
    """
    doc = __doc__ or ""
    for keyword in (
        "向量检索",
        "数据库持久化",
        "MemoryContext 注入",
        "LLM 真实调用",
        "麒麟 Runtime",
        "OS Agent Hook",
    ):
        assert keyword in doc, f"模块 docstring 必须声明不验证：{keyword}"
    assert "明确不验证" in doc