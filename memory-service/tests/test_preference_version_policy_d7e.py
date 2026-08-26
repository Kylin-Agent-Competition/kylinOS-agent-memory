"""
test_preference_version_policy_d7e.py — Day7E 偏好版本变更规划策略单元测试

对齐任务卡：day7-e-02-preference-version-policy-v1
（实现纯业务层 Preference 版本变更规划策略：CREATE / COEXIST / UPDATE /
NO_OP / ROLLBACK 五种偏好业务行为，+ REJECTED fail-closed 防御态；
不写库、不修改 current_version、不实现持久化）。

覆盖范围（对齐 Plan 批准方案与验收标准）：
- 模块可导入；公开类型可引用；PreferenceVersionPolicy 为单一入口。
- PreferenceVersionAction 六值（CREATE/COEXIST/UPDATE/NO_OP/ROLLBACK +
  REJECTED 防御态）。
- PreferenceVersionPlan / PreferenceVersionIntent / PreferenceRollbackIntent
  字段集合固定且 extra="forbid"；所有可达 reason_code 与固定权威集合一致。
- CREATE：同 key+scope 无 active 当前记录 → action=CREATE, next_version=1,
  previous_version_id=None。
- NO_OP：同 key+scope+value 相同 → action=NO_OP, next_version=None,
  current_version 不增（不制造版本膨胀）。
- UPDATE：同 key+scope 不同 value → action=UPDATE,
  next_version == current.version+1（严格 +1），previous_version_id =
  current.preference_id（保留历史，不原地覆盖），current_preference_id/
  current_version 填充。
- COEXIST：同 key 不同 scope → action=COEXIST, next_version=1,
  coexist_with_scopes 含旧 scope，旧 scope active 偏好不被 supersede。
- 不同 key → 独立 CREATE（各自版本链）。
- 跨 user → REJECTED(rejected_cross_user)，不形成跨用户版本关系。
- 不可长期化（decision.should_store=False）→ REJECTED(rejected_not_persistable)，
  不产生 CREATE/UPDATE。
- ROLLBACK 合法历史版本 → action=ROLLBACK, target_perference_id/version 填充，
  next_version=None（D 轨负责 current_version 切换与持久化）。
- ROLLBACK 跨 scope / 跨 key / 跨 user 全部被拒绝（unrelated/cross_user）。
- ROLLBACK 未来版本（target.version > current.version）与当前版本
  （target.version == current.version）→ rejected_rollback_future_or_current_version。
- ROLLBACK target 不存在 → rejected_rollback_target_not_found。
- ROLLBACK target 链无 active 且集合无任何 active → rejected_no_active_chain。
- 无副作用：两次 plan 间 current_preferences 与其对象 model_dump() 不变。
- 确定性：同输入两次 plan 结果 model_dump() 完全相等。
- 不 import 上游门禁（candidate_governance / source_admission / providers）。
- 不在 service.__all__（守护既有门禁）。
- 复用契约 identity：Preference is domain.Preference，
  PreferenceBusinessDecision is service.preference_business_policy 内对象。
- 不读正文/不泄露密钥：value 与 decision 中密钥样串不出现在 plan 字段。
- 类型准入：plan_preference(None) / plan_rollback(None) → REJECTED。

测试纪律：
- 不使用 Mock、skip、xfail 或固定 PASS；不修改任何既有测试。
- 测试数据仅使用合成用户 ID（user_demo_d7e）、合成事件 ID（evt_d7e_*）
  与脱敏/虚构样本。
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import domain  # noqa: E402
import service  # noqa: E402
from domain.enums import (  # noqa: E402
    ExpressionType,
    MemoryStatus,
    PreferenceScope,
)
from service.preference_business_policy import (  # noqa: E402
    PreferenceBusinessDecision,
)
from service.preference_version_policy import (  # noqa: E402
    REASON_CODES,
    PreferenceRollbackIntent,
    PreferenceVersionAction,
    PreferenceVersionIntent,
    PreferenceVersionPlan,
    PreferenceVersionPolicy,
)

# ── 合成数据基座（不含任何真实用户数据/密钥） ──

USER = "user_demo_d7e"
OTHER_USER = "user_demo_d7e_other"
T0 = datetime(2026, 8, 24, 9, 0, 0, tzinfo=timezone.utc)
POLICY = PreferenceVersionPolicy()

# 固定 reason_code 权威集合（本任务内部定义的 13 个可达判定码）
EXPECTED_REASON_CODES = {
    "create_first_version",
    "coexist_different_scope",
    "update_value_changed",
    "no_op_same_value",
    "rollback_to_history_version",
    "rejected_not_persistable",
    "rejected_cross_user",
    "rejected_rollback_target_not_found",
    "rejected_rollback_unrelated_version",
    "rejected_rollback_future_or_current_version",
    "rejected_no_active_chain",
    "rejected_invalid_input",
    "rejected_intent_decision_inconsistent",
}

SCOPES = ("global", "topic", "tool", "session", "time_window")


# ── helper 构造器 ──


def make_preference(**overrides) -> domain.Preference:
    """构造合成 Preference Domain（已存在偏好记录）。

    version>1 时自动补默认 previous_version_id（D3 §7.2 version chain）。
    """
    data = {
        "preference_id": "pref_d7e_01",
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
        "evidence_event_ids": ["evt_d7e_pref_01"],
        "version": 1,
        "created_at": T0,
        "updated_at": T0,
        "requires_confirmation": False,
    }
    data.update(overrides)
    if data["version"] > 1 and data.get("previous_version_id") is None:
        data["previous_version_id"] = "pref_prev"
    return domain.Preference(**data)


def make_decision(**overrides) -> PreferenceBusinessDecision:
    """构造 D7E-01 长期化门禁决策（只消费其 should_store 与结构化引用）。"""
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
        "source_event_id": "evt_d7e_pref_01",
    }
    data.update(overrides)
    return PreferenceBusinessDecision(**data)


def make_intent(**overrides) -> PreferenceVersionIntent:
    """构造 plan_preference 输入。

    当调用方未显式提供 decision 时，默认按最终的 preference_key/scope
    同步生成 identity 一致的 decision（保持真实业务 identity 一致）；
    显式传入 decision 时保持原样（用于构造 key/scope mismatch 的负向用例）。
    """
    has_decision = "decision" in overrides
    if has_decision:
        decision = overrides.pop("decision")
    data = {
        "user_id": USER,
        "preference_key": "demo_response_style",
        "scope": "global",
        "value": "concise",
    }
    data.update(overrides)
    if has_decision:
        data["decision"] = decision
    else:
        data["decision"] = make_decision(
            candidate_key=data["preference_key"], scope=data["scope"])
    return PreferenceVersionIntent(**data)


def make_rollback_intent(**overrides) -> PreferenceRollbackIntent:
    """构造 plan_rollback 输入。"""
    data = {
        "user_id": USER,
        "target_preference_id": "pref_d7e_01",
    }
    data.update(overrides)
    return PreferenceRollbackIntent(**data)


# ── 模块与结果结构 ──


def test_module_importable_and_types_exposed():
    """模块可导入，公开入口与类型可引用。"""
    import service.preference_version_policy as mod

    assert isinstance(POLICY, PreferenceVersionPolicy)
    for name in (
        "PreferenceVersionPolicy",
        "PreferenceVersionAction",
        "PreferenceVersionPlan",
        "PreferenceVersionIntent",
        "PreferenceRollbackIntent",
    ):
        assert hasattr(mod, name)


def test_action_has_five_business_values_plus_rejected():
    """PreferenceVersionAction 六值：五业务动作 + REJECTED 防御态（非业务动作）。"""
    values = {a.value for a in PreferenceVersionAction}
    assert values == {
        "create", "coexist", "update", "no_op", "rollback", "rejected",
    }
    business = {
        PreferenceVersionAction.CREATE,
        PreferenceVersionAction.COEXIST,
        PreferenceVersionAction.UPDATE,
        PreferenceVersionAction.NO_OP,
        PreferenceVersionAction.ROLLBACK,
    }
    assert len(business) == 5
    assert PreferenceVersionAction.REJECTED not in business


def test_plan_model_fields_fixed_and_forbid_extra():
    """PreferenceVersionPlan 字段集合固定且 extra="forbid"。"""
    assert set(PreferenceVersionPlan.model_fields) == {
        "action", "reason_code", "user_id", "preference_key", "scope",
        "next_version", "previous_version_id", "current_preference_id",
        "current_version", "target_preference_id", "target_version",
        "coexist_with_scopes",
    }
    assert PreferenceVersionPlan.model_config.get("extra") == "forbid"


def test_intent_models_forbid_extra():
    """两个 Intent 均 extra="forbid"，拒绝未声明字段。"""
    assert PreferenceVersionIntent.model_config.get("extra") == "forbid"
    assert PreferenceRollbackIntent.model_config.get("extra") == "forbid"
    assert set(PreferenceVersionIntent.model_fields) == {
        "user_id", "preference_key", "scope", "value", "decision",
    }
    assert set(PreferenceRollbackIntent.model_fields) == {
        "user_id", "target_preference_id",
    }


def test_reason_codes_match_authoritative_set():
    """所有可达 reason_code 集合与固定权威集合（12 个）完全一致。"""
    assert REASON_CODES == EXPECTED_REASON_CODES
    assert len(REASON_CODES) == 13


# ── CREATE ──


def test_create_first_version():
    """同 key+scope 无 active 当前记录 → 首版 CREATE。"""
    plan = POLICY.plan_preference(make_intent(), [])
    assert plan.action == PreferenceVersionAction.CREATE
    assert plan.reason_code == "create_first_version"
    assert plan.next_version == 1
    assert plan.previous_version_id is None
    assert plan.current_preference_id is None


# ── NO_OP ──


def test_no_op_same_value():
    """同 key+scope+value 相同 → NO_OP，不增版本。"""
    current = make_preference(preference_id="pref_d7e_01", version=3)
    plan = POLICY.plan_preference(make_intent(), [current])
    assert plan.action == PreferenceVersionAction.NO_OP
    assert plan.reason_code == "no_op_same_value"
    assert plan.next_version is None
    assert plan.current_preference_id == "pref_d7e_01"
    assert plan.current_version == 3


def test_no_op_over_action_all_scopes():
    """五值 scope 上，同 key+scope+value 均 NO_OP（不误判为 COEXIST/CREATE）。"""
    for scope in SCOPES:
        scope_enum = PreferenceScope(scope)
        current = make_preference(
            preference_id=f"pref_{scope}", preference_scope=scope_enum,
            version=1,
        )
        intent = make_intent(scope=scope, value="concise")
        plan = POLICY.plan_preference(intent, [current])
        assert plan.action == PreferenceVersionAction.NO_OP
        assert plan.reason_code == "no_op_same_value"


# ── UPDATE ──


def test_update_value_changed_next_version_strict_plus_one():
    """同 key+scope 不同 value → UPDATE，next_version 严格 == current.version+1。"""
    current = make_preference(preference_id="pref_d7e_02", version=2)
    intent = make_intent(value="detailed")
    plan = POLICY.plan_preference(intent, [current])
    assert plan.action == PreferenceVersionAction.UPDATE
    assert plan.reason_code == "update_value_changed"
    assert plan.next_version == current.version + 1 == 3
    assert plan.current_preference_id == "pref_d7e_02"
    assert plan.current_version == 2


def test_update_preserves_history_not_in_place():
    """UPDATE 保留 previous_version_id 指向被更新版本，不原地覆盖。"""
    current = make_preference(
        preference_id="pref_d7e_02", preference_value="concise", version=2,
    )
    intent = make_intent(value="detailed")
    snapshot_before = current.model_dump()
    plan = POLICY.plan_preference(intent, [current])
    assert plan.action == PreferenceVersionAction.UPDATE
    assert plan.previous_version_id == current.preference_id
    assert plan.next_version != current.version  # 新版本，不覆盖旧版本号
    # 被更新版本对象未被修改（原地覆盖会产生副作用，此处 assert 不变）
    assert current.model_dump() == snapshot_before


# ── COEXIST ──


def test_coexist_different_scope():
    """同 key 不同 scope → COEXIST，旧 scope active 不被 supersede。"""
    global_active = make_preference(
        preference_id="pref_d7e_global", preference_scope=PreferenceScope.GLOBAL,
        preference_value="concise", version=1,
    )
    intent = make_intent(scope="tool", value="concise")
    snapshot_before = global_active.model_dump()
    plan = POLICY.plan_preference(intent, [global_active])
    assert plan.action == PreferenceVersionAction.COEXIST
    assert plan.reason_code == "coexist_different_scope"
    assert plan.next_version == 1
    assert plan.previous_version_id is None
    assert "global" in plan.coexist_with_scopes
    # 旧 scope active 偏好未被 supersede（对象不变，仍存在）
    assert global_active.model_dump() == snapshot_before
    assert global_active.memory_status == MemoryStatus.ACTIVE


def test_coexist_with_multiple_old_scopes():
    """多个同 key 不同 scope 的 active 均被收集，不被 supersede。"""
    existing = [
        make_preference(preference_id="p_global", preference_scope=PreferenceScope.GLOBAL, version=1),
        make_preference(preference_id="p_topic", preference_scope=PreferenceScope.TOPIC, version=1),
    ]
    intent = make_intent(scope="session", value="concise")
    plan = POLICY.plan_preference(intent, existing)
    assert plan.action == PreferenceVersionAction.COEXIST
    assert "global" in plan.coexist_with_scopes
    assert "topic" in plan.coexist_with_scopes


# ── 不同 key → 独立 CREATE ──


def test_different_key_independent_create():
    """不同 preference_key 属不同业务偏好 → 独立 CREATE，不得误判为同一版本链。"""
    existing = make_preference(
        preference_id="pref_style", preference_key="demo_response_style",
        preference_value="concise", version=1,
    )
    intent = make_intent(preference_key="demo_theme", value="dark")
    plan = POLICY.plan_preference(intent, [existing])
    assert plan.action == PreferenceVersionAction.CREATE
    assert plan.preference_key == "demo_theme"
    assert plan.next_version == 1
    assert plan.previous_version_id is None


# ── 跨用户 ──


def test_cross_user_rejected():
    """current_preferences 含不同 user_id → REJECTED(rejected_cross_user)。"""
    other = make_preference(
        preference_id="pref_other_user", user_id=OTHER_USER, version=1,
    )
    plan = POLICY.plan_preference(make_intent(), [other])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_cross_user"


# ── 不可长期化 ──


def test_not_persistable_rejected():
    """decision.should_store=False → REJECTED(rejected_not_persistable)，
    不得产生 CREATE/UPDATE。"""
    decision = make_decision(should_store=False)
    intent = make_intent(decision=decision)
    # 即使无 active 记录也不得 CREATE
    plan = POLICY.plan_preference(intent, [])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_not_persistable"
    # 即使有 active 记录也不得 UPDATE
    current = make_preference(version=1, preference_value="old")
    plan2 = POLICY.plan_preference(make_intent(decision=decision, value="new"), [current])
    assert plan2.action == PreferenceVersionAction.REJECTED
    assert plan2.reason_code == "rejected_not_persistable"


# ── ROLLBACK 合法历史版本 ──


def test_rollback_valid_history_version():
    """同 user+key+scope 的历史版本 → ROLLBACK，输出计划（不写库）。"""
    active_v3 = make_preference(
        preference_id="pref_v3", version=3, preference_value="detailed",
    )
    history_v1 = make_preference(
        preference_id="pref_v1", version=1, preference_value="concise",
        previous_version_id=None,
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
        evidence_event_ids=["evt_d7e_pref_01"],
    )
    history_v2 = make_preference(
        preference_id="pref_v2", version=2, preference_value="concise",
        previous_version_id="pref_v1",
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
        evidence_event_ids=["evt_d7e_pref_01"],
    )
    snapshot = [active_v3.model_dump(), history_v1.model_dump(), history_v2.model_dump()]
    intent = make_rollback_intent(target_preference_id="pref_v1")
    plan = POLICY.plan_rollback(intent, [active_v3, history_v1, history_v2])
    assert plan.action == PreferenceVersionAction.ROLLBACK
    assert plan.reason_code == "rollback_to_history_version"
    assert plan.target_preference_id == "pref_v1"
    assert plan.target_version == 1
    assert plan.current_preference_id == "pref_v3"
    assert plan.current_version == 3
    assert plan.next_version is None  # 不创建新版本，D 轨负责切换
    # 无副作用：对象未被修改
    assert [active_v3.model_dump(), history_v1.model_dump(), history_v2.model_dump()] == snapshot


# ── ROLLBACK 各种拒绝 ──


def test_rollback_cross_scope_rejected():
    """rollback 目标与当前 active 不同 scope → REJECTED(unrelated_version)。"""
    global_active = make_preference(
        preference_id="pref_global", preference_scope=PreferenceScope.GLOBAL,
        version=1,
    )
    history_tool = make_preference(
        preference_id="pref_tool_hist", preference_scope=PreferenceScope.TOOL,
        version=1,
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
    )
    intent = make_rollback_intent(target_preference_id="pref_tool_hist")
    plan = POLICY.plan_rollback(intent, [global_active, history_tool])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_rollback_unrelated_version"


def test_rollback_cross_key_rejected():
    """rollback 目标与当前 active 不同 key → REJECTED(unrelated_version)。"""
    style_active = make_preference(
        preference_id="pref_style", preference_key="demo_response_style",
        preference_scope=PreferenceScope.GLOBAL, version=1,
    )
    theme_history = make_preference(
        preference_id="pref_theme", preference_key="demo_theme",
        preference_scope=PreferenceScope.GLOBAL, version=1,
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
    )
    intent = make_rollback_intent(target_preference_id="pref_theme")
    plan = POLICY.plan_rollback(intent, [style_active, theme_history])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_rollback_unrelated_version"


def test_rollback_cross_user_rejected():
    """rollback 目标属于不同 user → REJECTED(cross_user)。"""
    own_active = make_preference(preference_id="pref_own", version=2)
    other_history = make_preference(
        preference_id="pref_other_hist", user_id=OTHER_USER, version=1,
    )
    intent = make_rollback_intent(target_preference_id="pref_other_hist")
    plan = POLICY.plan_rollback(intent, [own_active, other_history])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_cross_user"


def test_rollback_future_version_rejected():
    """rollback 目标为未来版本（target.version > current.version）→ REJECTED。"""
    active_v3 = make_preference(preference_id="pref_v3", version=3)
    future_v4 = make_preference(
        preference_id="pref_v4", version=4,
        previous_version_id="pref_v3",
        evidence_event_ids=["evt_d7e_pref_01"],
    )
    intent = make_rollback_intent(target_preference_id="pref_v4")
    plan = POLICY.plan_rollback(intent, [active_v3, future_v4])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_rollback_future_or_current_version"


def test_rollback_current_version_rejected():
    """rollback 目标为当前版本（target.version == current.version）→ REJECTED。"""
    active_v3 = make_preference(preference_id="pref_v3", version=3)
    # 同一版本号的另一个记录（同 key+scope, non-active）
    current_hist = make_preference(
        preference_id="pref_v3_dup", version=3,
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
        previous_version_id="pref_v2",
        evidence_event_ids=["evt_d7e_pref_01"],
    )
    intent = make_rollback_intent(target_preference_id="pref_v3_dup")
    plan = POLICY.plan_rollback(intent, [active_v3, current_hist])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_rollback_future_or_current_version"


def test_rollback_target_not_found_rejected():
    """rollback 目标不存在 → REJECTED(target_not_found)。"""
    current = make_preference(preference_id="pref_v2", version=2)
    intent = make_rollback_intent(target_preference_id="pref_does_not_exist")
    plan = POLICY.plan_rollback(intent, [current])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_rollback_target_not_found"


def test_rollback_target_with_no_active_chain_rejected():
    """target 链无 active 且集合无任何 active → REJECTED(no_active_chain)。"""
    history = make_preference(
        preference_id="pref_v1", version=1,
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
    )
    intent = make_rollback_intent(target_preference_id="pref_v1")
    plan = POLICY.plan_rollback(intent, [history])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_no_active_chain"


# ── 无副作用 ──


def test_no_side_effects():
    """两次 plan 之间 current_preferences 与其对象 model_dump() 不变。"""
    current = make_preference(preference_id="pref_d7e_02", version=2, preference_value="concise")
    history = make_preference(
        preference_id="pref_d7e_01", version=1, preference_value="concise",
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
    )
    prefs = [current, history]
    snapshot = [p.model_dump() for p in prefs]
    _ = POLICY.plan_preference(make_intent(value="detailed"), prefs)
    _ = POLICY.plan_preference(make_intent(value="detailed"), prefs)
    _ = POLICY.plan_rollback(
        make_rollback_intent(target_preference_id="pref_d7e_01"), prefs,
    )
    assert [p.model_dump() for p in prefs] == snapshot


# ── 确定性 ──


def test_deterministic_same_input_same_output():
    """同输入两次 plan 结果 model_dump() 完全相等。"""
    current = make_preference(preference_id="pref_d7e_02", version=2, preference_value="concise")
    assert (
        POLICY.plan_preference(make_intent(value="detailed"), [current]).model_dump()
        == POLICY.plan_preference(make_intent(value="detailed"), [current]).model_dump()
    )
    history = make_preference(
        preference_id="pref_d7e_01", version=1, preference_value="concise",
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
    )
    active = make_preference(preference_id="pref_d7e_02", version=2, preference_value="concise")
    assert (
        POLICY.plan_rollback(
            make_rollback_intent(target_preference_id="pref_d7e_01"),
            [active, history],
        ).model_dump()
        == POLICY.plan_rollback(
            make_rollback_intent(target_preference_id="pref_d7e_01"),
            [active, history],
        ).model_dump()
    )


# ── 不 import 上游门禁 ──


def test_does_not_import_upstream():
    """策略模块不 import candidate_governance / source_admission / providers。"""
    import ast

    import service.preference_version_policy as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.add(node.module)
    assert "candidate_governance" not in imported_names
    assert "source_admission" not in imported_names
    assert "providers" not in imported_names
    assert all("extraction_provider" not in n for n in imported_names)


# ── 门禁守护 ──


def test_policy_not_in_service_all():
    """新增类型均不在 service.__all__ 内（守护既有严格门禁）。"""
    for name in (
        "PreferenceVersionPolicy",
        "PreferenceVersionAction",
        "PreferenceVersionPlan",
        "PreferenceVersionIntent",
        "PreferenceRollbackIntent",
    ):
        assert name not in service.__all__


# ── 复用契约 identity ──


def test_reuses_contract_identity():
    """策略模块引用的 Preference / PreferenceBusinessDecision 为既有对象。"""
    import service.preference_version_policy as mod

    assert mod.Preference is domain.Preference
    assert mod.PreferenceBusinessDecision is PreferenceBusinessDecision


# ── 不读正文 / 不泄露密钥 ──


def test_does_not_read_body_or_leak_secrets():
    """value 与 decision 中密钥样串不出现在 reason_code 与 plan 任何 str 字段。"""
    secret_like = "sk-demo-abcdefghijklmnopqrstuvwxyz123456"
    intent = make_intent(
        value=f"api_key={secret_like}（虚构）",
        decision=make_decision(
            scope="global",
            source_event_id=f"evt-{secret_like}",
        ),
    )
    plan = POLICY.plan_preference(intent, [])
    # 可长期化 → 正常产出 CREATE（结构引用，不含正文/密钥）
    assert plan.action == PreferenceVersionAction.CREATE
    for value in plan.model_dump().values():
        if isinstance(value, str):
            assert secret_like not in value
    # reason_code 固定集合，不泄露
    assert secret_like not in plan.reason_code


# ── 类型准入（fail-closed） ──


def test_invalid_input_rejected():
    """plan_preference(None) / plan_rollback(None) → REJECTED(invalid_input)。"""
    plan_pref = POLICY.plan_preference(None, [])
    assert plan_pref.action == PreferenceVersionAction.REJECTED
    assert plan_pref.reason_code == "rejected_invalid_input"
    plan_rb = POLICY.plan_rollback(None, [])
    assert plan_rb.action == PreferenceVersionAction.REJECTED
    assert plan_rb.reason_code == "rejected_invalid_input"


# ── PR #58 审查问题 #1：非法 scope 契约校验（fail-closed） ──


def test_invalid_scope_rejected_at_construction():
    """非法 scope 在 PreferenceVersionIntent 构造阶段即被拒绝
    （直接复用 PreferenceScope 枚举校验，非第二套 scope 字符串常量），
    不会进入 CREATE/COEXIST/UPDATE/NO_OP/ROLLBACK 业务规划。"""
    with pytest.raises(ValidationError):
        PreferenceVersionIntent(
            user_id=USER,
            preference_key="demo_response_style",
            scope="invalid_scope_not_in_enum",
            value="concise",
            decision=make_decision(),
        )


def test_empty_scope_rejected_at_construction():
    """空字符串 scope 不在 PreferenceScope 五值内 → 构造阶段拒绝。"""
    with pytest.raises(ValidationError):
        PreferenceVersionIntent(
            user_id=USER,
            preference_key="demo_response_style",
            scope="",
            value="concise",
            decision=make_decision(),
        )


def test_intent_scope_reuses_preference_scope_enum():
    """PreferenceVersionIntent.scope 字段直接复用 PreferenceScope 枚举
    （PR #58 审查问题 #1：复用现有契约，非第二套 scope 字符串常量）。
    合法字符串经 Pydantic 转换为 PreferenceScope 枚举成员。"""
    for scope_str in SCOPES:
        intent = make_intent(scope=scope_str)
        assert isinstance(intent.scope, PreferenceScope)
        assert intent.scope == PreferenceScope(scope_str)
        assert intent.scope.value == scope_str


# ── PR #58 审查问题 #2：coexist_with_scopes 无共享可变默认值 ──


def test_coexist_with_scopes_default_independent_instances():
    """coexist_with_scopes 使用 Field(default_factory=list)，
    两个默认实例的列表互相独立（PR #58 审查问题 #2：无共享可变默认值）。"""
    plan1 = PreferenceVersionPlan(
        action=PreferenceVersionAction.CREATE,
        reason_code="create_first_version",
        user_id=USER,
        preference_key="demo_key",
        scope="global",
    )
    plan2 = PreferenceVersionPlan(
        action=PreferenceVersionAction.CREATE,
        reason_code="create_first_version",
        user_id=USER,
        preference_key="demo_key",
        scope="global",
    )
    assert plan1.coexist_with_scopes == []
    assert plan2.coexist_with_scopes == []
    plan1.coexist_with_scopes.append("topic")
    assert "topic" not in plan2.coexist_with_scopes
    assert plan2.coexist_with_scopes == []


# ── PR #58 第二轮 Low 问题：意图与长期化决策 key/scope 一致性（fail-closed） ──


def test_rejected_when_decision_candidate_key_missing():
    """decision.candidate_key 缺失（None）/空 → REJECTED
    (rejected_intent_decision_inconsistent)，不得进入 CREATE。"""
    decision = make_decision(candidate_key=None)
    plan = POLICY.plan_preference(make_intent(decision=decision), [])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_intent_decision_inconsistent"
    # 空字符串同样视为缺失
    decision_empty = make_decision(candidate_key="")
    plan_empty = POLICY.plan_preference(
        make_intent(decision=decision_empty), [])
    assert plan_empty.action == PreferenceVersionAction.REJECTED
    assert plan_empty.reason_code == "rejected_intent_decision_inconsistent"


def test_rejected_when_decision_candidate_key_mismatch():
    """decision.candidate_key 与 intent.preference_key 不符 → REJECTED
    (rejected_intent_decision_inconsistent)，不得进入 CREATE。"""
    decision = make_decision(
        candidate_key="some_other_key", scope="global")
    intent = make_intent(decision=decision)
    assert intent.preference_key == "demo_response_style"
    plan = POLICY.plan_preference(intent, [])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_intent_decision_inconsistent"


def test_rejected_when_decision_scope_mismatch():
    """decision.scope 与 intent.scope.value 不符 → REJECTED
    (rejected_intent_decision_inconsistent)，不得进入 CREATE。"""
    decision = make_decision(
        candidate_key="demo_response_style", scope="tool")
    intent = make_intent(scope="global", decision=decision)
    assert intent.scope.value == "global"
    assert decision.scope == "tool"
    plan = POLICY.plan_preference(intent, [])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_intent_decision_inconsistent"


def test_not_persistable_priority_beats_consistency():
    """should_store=False 且 decision 不一致 → 优先
    rejected_not_persistable（不失守，先于一致性门禁）。"""
    decision = make_decision(
        should_store=False, candidate_key="other", scope="tool")
    plan = POLICY.plan_preference(make_intent(decision=decision), [])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_not_persistable"


def test_cross_user_priority_beats_consistency():
    """跨用户且 decision 不一致 → 优先 rejected_cross_user
    （用户隔离先行，不失守）。"""
    decision = make_decision(
        candidate_key="other", scope="tool")
    other = make_preference(
        preference_id="pref_other_user", user_id=OTHER_USER, version=1,
    )
    plan = POLICY.plan_preference(
        make_intent(decision=decision), [other])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_cross_user"


# ── PR #58 复审 Medium #1：跨用户 Rollback 拒绝载荷不回显目标用户 key/scope ──
#
# 修复 day7-e-pr58-fix-05-rollback-cross-user-redaction-v1：
# plan_rollback 步骤 3 跨用户拒绝时，不得将 target 用户（其他用户）的
# preference_key 与 preference_scope.value 回显到拒绝载荷；
# fail-closed（rejected_cross_user）与 user_id 仅保留请求方不变。
# 下列为负向安全测试与回归守卫测试，不修改任何既有测试函数。


def test_rollback_cross_user_rejected_key_scope_empty():
    """跨用户 rollback 拒绝（target 属其他用户）时 key/scope 为空、
    user_id 为请求方，fail-closed 语义不变。"""
    own_active = make_preference(
        preference_id="pref_own", user_id=USER, version=2,
        preference_key="demo_response_style",
        preference_scope=PreferenceScope.GLOBAL,
        preference_value="concise",
    )
    # 目标用户使用独特 key/value/scope，验证不被回显
    other_history = make_preference(
        preference_id="pref_other_hist", user_id=OTHER_USER, version=1,
        preference_key="other_user_secret_key",
        preference_scope=PreferenceScope.TIME_WINDOW,
        preference_value="other_secret_value",
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
    )
    intent = make_rollback_intent(target_preference_id="pref_other_hist")
    plan = POLICY.plan_rollback(intent, [own_active, other_history])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_cross_user"
    # 关键修复：不回显目标用户 key/scope
    assert plan.preference_key == ""
    assert plan.scope == ""
    # user_id 仅保留请求方
    assert plan.user_id == USER
    assert plan.user_id != OTHER_USER


def test_rollback_cross_user_rejected_no_target_leak_in_dump():
    """跨用户 rollback 拒绝的全量 model_dump() 不含目标用户
    key/value/scope/user_id；target 引用字段全为 None。"""
    own_active = make_preference(
        preference_id="pref_own", user_id=USER, version=2,
        preference_key="demo_response_style",
        preference_scope=PreferenceScope.GLOBAL,
        preference_value="concise",
    )
    other_secret_key = "other_user_secret_key"
    other_secret_value = "other_secret_value"
    other_secret_scope = "time_window"  # 目标用户 scope value
    other_history = make_preference(
        preference_id="pref_other_hist", user_id=OTHER_USER, version=1,
        preference_key=other_secret_key,
        preference_scope=PreferenceScope.TIME_WINDOW,
        preference_value=other_secret_value,
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
    )
    intent = make_rollback_intent(target_preference_id="pref_other_hist")
    plan = POLICY.plan_rollback(intent, [own_active, other_history])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_cross_user"
    # 全量 dump，逐一断言任何 str 值都不含目标用户敏感片段
    dump = plan.model_dump()
    for value in dump.values():
        if isinstance(value, str):
            assert other_secret_key not in value
            assert other_secret_value not in value
            assert other_secret_scope not in value
            assert OTHER_USER not in value
    # target 引用字段不泄露 target ID / version
    assert dump["target_preference_id"] is None
    assert dump["target_version"] is None
    # key/scope 明确为空
    assert dump["preference_key"] == ""
    assert dump["scope"] == ""


def test_rollback_cross_user_via_collection_key_scope_empty():
    """跨用户拒绝由集合含其他用户偏好触发（target 自身同用户）时
    key/scope 同样置空、user_id 为请求方。"""
    # target 为请求方自己的历史，但集合混入其他用户的 active → 跨用户失败
    own_history = make_preference(
        preference_id="pref_own_hist", user_id=USER, version=1,
        preference_key="demo_response_style",
        preference_scope=PreferenceScope.GLOBAL,
        preference_value="concise",
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
    )
    other_active = make_preference(
        preference_id="pref_other_active", user_id=OTHER_USER, version=1,
        preference_key="other_user_secret_key",
        preference_scope=PreferenceScope.GLOBAL,
        preference_value="other_secret_value",
    )
    intent = make_rollback_intent(target_preference_id="pref_own_hist")
    plan = POLICY.plan_rollback(intent, [own_history, other_active])
    assert plan.action == PreferenceVersionAction.REJECTED
    assert plan.reason_code == "rejected_cross_user"
    assert plan.preference_key == ""
    assert plan.scope == ""
    assert plan.user_id == USER


def test_rollback_non_cross_user_rejections_still_echo_key_scope():
    """回归守卫：非跨用户拒绝路径仍正常回显 target key/scope，
    本修复不应改变同用户拒绝语义。"""
    # 场景 A：unrelated_version（target 与 active 不同 scope，同用户）
    active_global = make_preference(
        preference_id="pref_active", user_id=USER, version=2,
        preference_key="demo_response_style",
        preference_scope=PreferenceScope.GLOBAL,
        preference_value="concise",
    )
    history_tool = make_preference(
        preference_id="pref_tool_hist", user_id=USER, version=1,
        preference_key="demo_response_style",
        preference_scope=PreferenceScope.TOOL,
        preference_value="concise",
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
    )
    plan_a = POLICY.plan_rollback(
        make_rollback_intent(target_preference_id="pref_tool_hist"),
        [active_global, history_tool],
    )
    assert plan_a.action == PreferenceVersionAction.REJECTED
    assert plan_a.reason_code == "rejected_rollback_unrelated_version"
    assert plan_a.preference_key == "demo_response_style"
    assert plan_a.scope == "tool"

    # 场景 B：no_active_chain（target 链无 active 且集合无任何 active，同用户）
    history_only = make_preference(
        preference_id="pref_v1", user_id=USER, version=1,
        preference_key="demo_response_style",
        preference_scope=PreferenceScope.GLOBAL,
        preference_value="concise",
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
    )
    plan_b = POLICY.plan_rollback(
        make_rollback_intent(target_preference_id="pref_v1"), [history_only])
    assert plan_b.action == PreferenceVersionAction.REJECTED
    assert plan_b.reason_code == "rejected_no_active_chain"
    assert plan_b.preference_key == "demo_response_style"
    assert plan_b.scope == "global"


def test_rollback_valid_history_unchanged_after_cross_user_fix():
    """回归守卫：合法同用户 rollback 不因跨用户修复退化。"""
    active_v3 = make_preference(
        preference_id="pref_v3", user_id=USER, version=3,
        preference_key="demo_response_style",
        preference_scope=PreferenceScope.GLOBAL,
        preference_value="detailed",
    )
    history_v1 = make_preference(
        preference_id="pref_v1", user_id=USER, version=1,
        preference_key="demo_response_style",
        preference_scope=PreferenceScope.GLOBAL,
        preference_value="concise",
        previous_version_id=None,
        memory_status=MemoryStatus.SUPERSEDED, is_active=False,
    )
    plan = POLICY.plan_rollback(
        make_rollback_intent(target_preference_id="pref_v1"),
        [active_v3, history_v1],
    )
    assert plan.action == PreferenceVersionAction.ROLLBACK
    assert plan.reason_code == "rollback_to_history_version"
    assert plan.preference_key == "demo_response_style"
    assert plan.scope == "global"
    assert plan.target_preference_id == "pref_v1"
    assert plan.target_version == 1
    assert plan.current_preference_id == "pref_v3"
    assert plan.current_version == 3
    assert plan.next_version is None
