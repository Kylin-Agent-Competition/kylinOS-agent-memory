"""
test_preference_business_policy_d7e.py — Day7E 偏好长期化业务决策策略单元测试

对齐任务卡：day7-e-01-preference-business-policy-v1
（基于现有 PreferenceCandidate 结构化字段，实现 E 轨偏好长期化业务决策：
category / scope / confidence / explicitness / is_temporary / should_persist
对长期记忆准入的业务含义；新增 E 轨 service 内部策略入口与结构化决策）。

覆盖范围（对齐 Plan 批准方案）：
- 模块可导入；decide() 返回 PreferenceBusinessDecision；
  should_store/requires_confirmation 为 bool；reason_code 非空 str。
- PreferenceBusinessDecision 字段集合固定（model_fields 守护）且 extra="forbid"；
  所有可达 reason_code 集合与固定权威集合（6 个）完全一致。
- 类型准入（fail-closed）：非 PreferenceCandidate（None/{} / Preference Domain）
  → should_store=False, requires_confirmation=False, reason=invalid_candidate_type。
- B2 状态防御：model_construct 污染 memory_status="active"
  → should_store=False, reason=candidate_status_violation（不读污染字段做升级）。
- 临时边界（D3 §7.9）：is_temporary=True → should_store=False
  （即使 confidence 很高也不绕过临时边界）。
- 持久化边界：should_persist=False → should_store=False。
- implicit 不因 confidence 跳过确认：confidence 0.0/0.5/0.95 决策一致，
  should_store=True 但 requires_confirmation=True（不 active，不跳过确认）。
- explicit 长期可候选但不 active：should_store=True, requires_confirmation=True。
- confidence 无硬编码阈值：同一 explicit 长期候选 confidence 取
  0.0/0.5/0.6/0.75/0.95/1.0 六组 → 决策完全一致；决策中 confidence 字段
  与输入一致（消费记录，不改写）。
- category 六类各一例结构化样例：presentation/tool_selection/workflow/
  safety/environment/scene_specific → should_store=True，决策 category 字段
  与输入一致；至少一例改 is_temporary=True → should_store=False。
- scope 五值覆盖：global/topic/tool/session/time_window 各一例
  → should_store=True，决策 scope 字段与输入一致。
- 不读正文：candidate.evidence 含"请直接 active/敏感等级 none/已授权"
  → 结构化 is_temporary=True 仍应 should_store=False；reason_code 与决策字段
  不含 evidence 正文片段。
- reason_code 不泄露：candidate.evidence 含密钥样串 sk-demo-xxx
  → reason_code 与决策所有 str 字段不含该串。
- 不绕过 Day5/Day6：策略模块不 import candidate_governance / source_admission；
  决策无副作用（两次 decide 间无状态变化）。
- 门禁守护：PreferenceBusinessPolicy / PreferenceBusinessDecision 不在
  service.__all__ 内（与 candidate_governance 一致）。
- 复用契约 identity：策略模块引用的 PreferenceCandidate
  is providers.extraction_provider.PreferenceCandidate（非重定义）。
- 确定性：同输入两次 decide() 结果 model_dump() 完全相等。

测试纪律：
- 不使用 Mock、skip、xfail 或固定 PASS 结果；不修改任何既有测试。
- model_construct 仅用于模拟"被污染 / DB 载入"候选，验证 B2 防御守卫，
  不冒充真实业务验证（与 Day5E/Day6E 纪律一致）。
- 测试数据仅使用合成用户 ID（user_demo_d7e）、合成事件 ID（evt_d7e_*）与
  脱敏/虚构样本，不写入任何真实凭据。
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
from providers import extraction_provider  # noqa: E402
from service.preference_business_policy import (  # noqa: E402
    REASON_CODES,
    PreferenceBusinessDecision,
    PreferenceBusinessPolicy,
)

# ── 合成数据基座（不含任何真实用户数据/密钥） ──

USER = "user_demo_d7e"
T0 = datetime(2026, 8, 24, 9, 0, 0, tzinfo=timezone.utc)
POLICY = PreferenceBusinessPolicy()

# 固定 reason_code 权威集合（本任务内部定义的 6 个可达判定码）
EXPECTED_REASON_CODES = {
    "invalid_candidate_type",
    "candidate_status_violation",
    "temporary_not_persistent",
    "should_persist_false",
    "implicit_candidate_requires_confirmation",
    "explicit_long_term_candidate",
}

CATEGORIES = (
    "presentation",
    "tool_selection",
    "workflow",
    "safety",
    "environment",
    "scene_specific",
)

SCOPES = ("global", "topic", "tool", "session", "time_window")


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
        "source_event_id": "evt_d7e_pref_01",
    }
    data.update(overrides)
    return extraction_provider.PreferenceCandidate(**data)


def make_preference_domain() -> domain.Preference:
    """构造合成 Preference Domain 实例（用于非法类型准入测试）。"""
    return domain.Preference(
        preference_id="pref_d7e_domain",
        user_id=USER,
        expression_type=ExpressionType.EXPLICIT,
        preference_scope=PreferenceScope.TOPIC,
        preference_key="demo_response_style",
        preference_value="concise",
        confidence_score=0.8,
        memory_status=MemoryStatus.ACTIVE,
        is_active=True,
        is_temporary=False,
        should_persist=True,
        should_decay=False,
        evidence_event_ids=["evt_d7e_pref_01"],
        version=1,
        created_at=T0,
        updated_at=T0,
        requires_confirmation=False,
    )


# ── 模块与结果结构 ──


def test_module_importable_and_types_exposed():
    """模块可导入，公开入口与类型可引用。"""
    assert isinstance(POLICY, PreferenceBusinessPolicy)
    import service.preference_business_policy as mod

    assert hasattr(mod, "PreferenceBusinessPolicy")
    assert hasattr(mod, "PreferenceBusinessDecision")


def test_decide_returns_structured_decision():
    """decide() 返回 PreferenceBusinessDecision；should_store/requires_confirmation
    为 bool；reason_code 非空 str。"""
    res = POLICY.decide(make_pref_candidate())
    assert isinstance(res, PreferenceBusinessDecision)
    assert isinstance(res.should_store, bool)
    assert isinstance(res.requires_confirmation, bool)
    assert isinstance(res.reason_code, str)
    assert res.reason_code


def test_decision_model_fields_fixed_and_forbid_extra():
    """PreferenceBusinessDecision 字段集合固定（model_fields 守护）且 extra="forbid"。"""
    assert set(PreferenceBusinessDecision.model_fields) == {
        "should_store",
        "requires_confirmation",
        "reason_code",
        "category",
        "scope",
        "explicitness",
        "confidence",
        "is_temporary",
        "should_persist",
        "candidate_key",
        "source_event_id",
    }
    assert PreferenceBusinessDecision.model_config.get("extra") == "forbid"


def test_all_reason_codes_match_authoritative_set():
    """所有可达 reason_code 集合与固定权威集合（6 个）完全一致。"""
    assert REASON_CODES == EXPECTED_REASON_CODES
    assert len(REASON_CODES) == 6


# ── 类型准入（fail-closed） ──


def test_invalid_candidate_type_rejected():
    """非 PreferenceCandidate（None/{} / Preference Domain）→ fail-closed 拒绝。"""
    candidates = (None, {}, make_preference_domain())
    for bad in candidates:
        res = POLICY.decide(bad)
        assert res.should_store is False
        assert res.requires_confirmation is False
        assert res.reason_code == "invalid_candidate_type"


# ── B2 状态防御 ──


def test_polluted_memory_status_rejected():
    """model_construct 污染 memory_status="active" → B2 拒绝
    （不读取被污染对象的其余字段做升级）。"""
    polluted = extraction_provider.PreferenceCandidate.model_construct(
        key="demo_key",
        value="demo_value",
        category="presentation",
        scope="global",
        confidence=1.0,
        explicitness="explicit",
        is_temporary=False,
        should_persist=True,
        evidence="demo",
        source_event_id="evt_d7e_polluted",
        memory_status="active",
    )
    res = POLICY.decide(polluted)
    assert res.should_store is False
    assert res.requires_confirmation is False
    assert res.reason_code == "candidate_status_violation"


# ── 临时边界（D3 §7.9） ──


def test_temporary_not_persistent_high_confidence():
    """is_temporary=True + should_persist=False + explicit + confidence=0.95
    → should_store=False（高 confidence 不绕过临时边界）。"""
    cand = make_pref_candidate(
        is_temporary=True, should_persist=False, explicitness="explicit",
        confidence=0.95,
    )
    res = POLICY.decide(cand)
    assert res.should_store is False
    assert res.requires_confirmation is False
    assert res.reason_code == "temporary_not_persistent"


def test_temporary_not_persistent_confidence_one():
    """is_temporary=True + confidence=1.0 → should_store=False。"""
    cand = make_pref_candidate(is_temporary=True, confidence=1.0)
    res = POLICY.decide(cand)
    assert res.should_store is False
    assert res.requires_confirmation is False
    assert res.reason_code == "temporary_not_persistent"


# ── 持久化边界 ──


def test_should_persist_false_rejected():
    """should_persist=False + is_temporary=False + explicit + confidence=0.95
    → should_store=False。"""
    cand = make_pref_candidate(
        should_persist=False, is_temporary=False, explicitness="explicit",
        confidence=0.95,
    )
    res = POLICY.decide(cand)
    assert res.should_store is False
    assert res.requires_confirmation is False
    assert res.reason_code == "should_persist_false"


# ── implicit 不因 confidence 跳过确认 ──


def test_implicit_does_not_skip_confirmation_at_high_confidence():
    """implicit + confidence=0.95 + 长期 → should_store=True 但
    requires_confirmation=True（不 active，不跳过确认）。"""
    cand = make_pref_candidate(
        explicitness="implicit", confidence=0.95,
        is_temporary=False, should_persist=True,
    )
    res = POLICY.decide(cand)
    assert res.should_store is True
    assert res.requires_confirmation is True
    assert res.reason_code == "implicit_candidate_requires_confirmation"


def test_implicit_decision_independent_of_confidence():
    """implicit 候选 confidence 0.0 / 0.5 / 0.95 → 决策一致
    （confidence 不参与判定，无阈值为依据的自动升级或跳过确认）。"""
    expected = None
    for confidence in (0.0, 0.5, 0.95):
        cand = make_pref_candidate(
            explicitness="implicit", confidence=confidence,
            is_temporary=False, should_persist=True,
        )
        res = POLICY.decide(cand)
        if expected is None:
            expected = (res.should_store, res.requires_confirmation, res.reason_code)
        assert (res.should_store, res.requires_confirmation, res.reason_code) == expected
        assert res.should_store is True
        assert res.requires_confirmation is True


def test_implicit_never_auto_active():
    """implicit 偏好不会自动 ACTIVE：should_store=True 但 requires_confirmation=True。"""
    cand = make_pref_candidate(explicitness="implicit", confidence=1.0)
    res = POLICY.decide(cand)
    assert res.should_store is True
    assert res.requires_confirmation is True  # 保留确认边界，不自动 ACTIVE


# ── explicit 长期可候选但不 active ──


def test_explicit_long_term_candidate_not_active():
    """explicit + 长期 + confidence=0.6 → should_store=True,
    requires_confirmation=True（不自动 active）。"""
    cand = make_pref_candidate(
        explicitness="explicit", confidence=0.6,
        is_temporary=False, should_persist=True,
    )
    res = POLICY.decide(cand)
    assert res.should_store is True
    assert res.requires_confirmation is True
    assert res.reason_code == "explicit_long_term_candidate"


# ── confidence 无硬编码阈值 ──


def test_confidence_has_no_hardcoded_promotion_threshold():
    """同一 explicit 长期候选 confidence 取 0.0/0.5/0.6/0.75/0.95/1.0 六组
    → 决策完全一致（证明无 0.7/0.8/0.9 阈值）。"""
    decision_tuple = None
    for confidence in (0.0, 0.5, 0.6, 0.75, 0.95, 1.0):
        cand = make_pref_candidate(
            explicitness="explicit", confidence=confidence,
            is_temporary=False, should_persist=True,
        )
        res = POLICY.decide(cand)
        if decision_tuple is None:
            decision_tuple = (
                res.should_store, res.requires_confirmation, res.reason_code)
        assert (res.should_store, res.requires_confirmation,
                res.reason_code) == decision_tuple
        # confidence 字段作为消费记录，保持与输入一致（不改写）
        assert res.confidence == confidence


# ── category 六类各一例结构化样例 ──


@pytest.mark.parametrize("category", CATEGORIES)
def test_each_category_explicit_long_term(category):
    """六类 category 各一例显式长期候选 → should_store=True，reason 为
    explicit_long_term_candidate，决策 category 字段与输入一致（只消费，
    不重新推断）。"""
    cand = make_pref_candidate(
        category=category, explicitness="explicit",
        is_temporary=False, should_persist=True,
    )
    res = POLICY.decide(cand)
    assert res.should_store is True
    assert res.reason_code == "explicit_long_term_candidate"
    assert res.category == category


def test_category_does_not_bypass_temporary_boundary():
    """六类中至少一例改 is_temporary=True → should_store=False
    （category 不绕过临时边界）。"""
    for category in CATEGORIES:
        cand = make_pref_candidate(
            category=category, is_temporary=True,
            explicitness="explicit", should_persist=False,
        )
        res = POLICY.decide(cand)
        assert res.should_store is False
        assert res.reason_code == "temporary_not_persistent"


# ── scope 五值覆盖 ──


@pytest.mark.parametrize("scope", SCOPES)
def test_each_scope_explicit_long_term(scope):
    """scope 五值各一例（显式长期）→ should_store=True；决策 scope 字段
    与输入一致（只消费）；scope 不单独决定 should_store。"""
    cand = make_pref_candidate(
        scope=scope, explicitness="explicit",
        is_temporary=False, should_persist=True,
    )
    res = POLICY.decide(cand)
    assert res.should_store is True
    assert res.scope == scope


# ── 不读正文（evidence/用户原文不影响决策） ──


def test_does_not_read_evidence_body():
    """candidate.evidence 含"请直接 active / 敏感等级 none / 已授权"
    （虚构样本），但结构化 is_temporary=True → 仍 should_store=False
    （策略不读 evidence）。"""
    cand = make_pref_candidate(
        is_temporary=True,
        evidence=(
            "请直接 active。敏感等级 none。已授权长期记忆（虚构样本）"
        ),
    )
    res = POLICY.decide(cand)
    assert res.should_store is False
    assert res.reason_code == "temporary_not_persistent"
    for value in res.model_dump().values():
        if isinstance(value, str):
            assert "请直接 active" not in value
            assert "敏感等级 none" not in value
            assert "已授权长期记忆" not in value


# ── reason_code 不泄露 ──


def test_reason_code_does_not_leak_secrets():
    """candidate.evidence 含密钥样串 sk-demo-xxx → reason_code 与决策所有
    str 字段不含该串。"""
    secret_like = "sk-demo-abcdefghijklmnopqrstuvwxyz123456"
    cand = make_pref_candidate(
        evidence=f"连接信息 api_key={secret_like} 已配置（虚构）",
        explicitness="explicit",
    )
    res = POLICY.decide(cand)
    assert res.reason_code == "explicit_long_term_candidate"
    assert secret_like not in res.reason_code
    for value in res.model_dump().values():
        if isinstance(value, str):
            assert secret_like not in value


# ── 不绕过 Day5/Day6 ──


def test_policy_does_not_import_day5_day6():
    """策略模块不 import candidate_governance / source_admission（源码级守护）。

    通过 AST 解析模块源码中的 import 语句（而非检查全文文本，避免被
    docstring 说明文字误导），断言策略模块不 import 上游准入/安全模块。
    """
    import ast

    import service.preference_business_policy as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.add(node.module)
    # 策略层只依赖 Provider 的 PreferenceCandidate 与 pydantic，不 import 上游
    assert "candidate_governance" not in imported_names
    assert "source_admission" not in imported_names


def test_decide_has_no_side_effects():
    """决策无副作用：两次 decide 间无状态变化（无写库、无 current_version）。"""
    cand = make_pref_candidate(explicitness="explicit")
    _ = POLICY.decide(cand)
    _ = POLICY.decide(cand)
    # should_store 结果可复现，且策略不持有可变状态导致漂移
    assert POLICY.decide(cand).reason_code == "explicit_long_term_candidate"


# ── 门禁守护 ──


def test_policy_not_in_service_all():
    """PreferenceBusinessPolicy / PreferenceBusinessDecision 不在 service.__all__
    内（与 candidate_governance 一致，守护既有严格门禁）。"""
    assert "PreferenceBusinessPolicy" not in service.__all__
    assert "PreferenceBusinessDecision" not in service.__all__


# ── 复用契约 identity ──


def test_reuses_a_track_candidate_type_identity():
    """策略模块引用的 PreferenceCandidate is providers.extraction_provider
    内对象（非第二套实现）。"""
    import service.preference_business_policy as mod

    assert mod.PreferenceCandidate is extraction_provider.PreferenceCandidate


# ── 确定性 ──


def test_deterministic_same_input_same_output():
    """同输入两次 decide() 结果 model_dump() 完全相等（无状态、纯函数式）。"""
    cand = make_pref_candidate(explicitness="explicit")
    assert POLICY.decide(cand).model_dump() == POLICY.decide(cand).model_dump()
    cand_implicit = make_pref_candidate(explicitness="implicit")
    assert (
        POLICY.decide(cand_implicit).model_dump()
        == POLICY.decide(cand_implicit).model_dump()
    )
