"""
test_domain_models_d4e.py — Day4 E 轨业务 Domain Schema 骨架单元测试

覆盖范围：
- Preference / Knowledge / Conflict / ForgetPlan 四类业务对象：
  正向合法构造 + 枚举值全覆盖 + 反向非法输入拒绝（Schema 层校验）。
- 校验重点（对齐 D3 契约）：
  - 空 ID 拒绝（min_length=1）
  - 非法枚举拒绝
  - confidence_score 越界拒绝 + strict float 拒绝 bool 自动转换
  - 临时偏好矛盾拒绝（is_temporary=true / should_persist=false + active）
  - 非法版本链拒绝（version=1 带 previous_version_id / version>1 缺 previous_version_id）
  - Conflict 自冲突拒绝、已消解状态缺 resolved_at/resolved_by 拒绝
  - ForgetPlan 缺模式条件字段拒绝、终态缺 executed_at 拒绝
  - extra="forbid" 拒绝未声明字段
  - 共享 NonEmptyStr 约束（TD-013）：空串与纯空白（空格/Tab/换行/混合）拒绝，
    含有效字符的原值逐字保留（不 strip）；NonEmptyIdList 元素级同规则。
  - Optional ID/Reference/Selector（TD-014）：previous_version_id / content_ref /
    superseded_by_id / rollback_plan_id / resolved_by 存在时拒绝空串与纯空白；
    involved_knowledge_ids 元素级同规则；字段缺失（None）Optional 语义不变。
- 导入契约：domain 不导出/不定义 MemorySourceEvent、NormalizedEvent、
  PreferenceCandidate、KnowledgeCandidate；MemoryType 复用自 pipeline.schemas。

测试纪律：
- 不使用 Mock、skip、xfail 或弱化断言。
- 测试数据仅使用合成用户 ID（*_demo_*）、合成事件 ID（evt_d4e_*）与脱敏内容。
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain import (  # noqa: E402
    Conflict,
    ConflictType,
    ExpressionType,
    ForgetMode,
    ForgetPlan,
    ForgetPlanStatus,
    Knowledge,
    KnowledgeType,
    MemoryStatus,
    Preference,
    PreferenceScope,
    ResolutionStatus,
    TargetType,
)
from domain.common import NonEmptyIdList, NonEmptyStr  # noqa: E402
from pipeline.schemas import MemoryType  # noqa: E402

# ── 合成数据基座（不含任何真实用户数据/密钥） ──

T0 = datetime(2026, 7, 30, 14, 30, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 7, 30, 15, 0, 0, tzinfo=timezone.utc)


def base_preference(**overrides):
    data = {
        "preference_id": "pref_d4e_01",
        "user_id": "user_demo_01",
        "expression_type": ExpressionType.EXPLICIT,
        "preference_scope": PreferenceScope.TOPIC,
        "preference_key": "demo_sort_order",
        "preference_value": "by_modified_desc",
        "confidence_score": 0.85,
        "memory_status": MemoryStatus.ACTIVE,
        "is_active": True,
        "is_temporary": False,
        "should_persist": True,
        "should_decay": False,
        "evidence_event_ids": ["evt_d4e_01", "evt_d4e_02"],
        "version": 1,
        "created_at": T0,
        "updated_at": T1,
        "requires_confirmation": False,
    }
    data.update(overrides)
    return data


def base_knowledge(**overrides):
    data = {
        "knowledge_id": "kn_d4e_01",
        "user_id": "user_demo_01",
        "knowledge_type": KnowledgeType.WORKFLOW,
        "memory_type": MemoryType.MEDIUM_TERM,
        "memory_status": MemoryStatus.ACTIVE,
        "source_event_id": "evt_d4e_01",
        "content_summary": "用户演示：按修改日期降序排列文件（脱敏摘要）",
        "confidence_score": 0.72,
        "requires_embedding": True,
        "is_outdated": False,
        "created_at": T0,
        "updated_at": T1,
    }
    data.update(overrides)
    return data


def base_conflict(**overrides):
    data = {
        "conflict_id": "cfl_d4e_01",
        "user_id": "user_demo_01",
        "conflict_type": ConflictType.TEMPORAL_INCONSISTENCY,
        "left_knowledge_id": "kn_d4e_01",
        "right_knowledge_id": "kn_d4e_02",
        "conflict_summary": "两条演示知识对排序方式给出不同结论（合成数据）",
        "resolution_status": ResolutionStatus.DETECTED,
        "is_auto_resolvable": False,
        "detected_at": T0,
    }
    data.update(overrides)
    return data


def base_forget_plan(**overrides):
    data = {
        "forget_plan_id": "fgp_d4e_01",
        "user_id": "user_demo_01",
        "forget_mode": ForgetMode.SINGLE_ITEM,
        "target_selector": "忘掉关于演示排序的合成偏好",
        "target_type": TargetType.PREFERENCE,
        "status": ForgetPlanStatus.PENDING,
        "is_cascade": False,
        "has_vector_cleanup": False,
        "requires_confirmation": True,
        "created_at": T0,
        "target_id": "pref_d4e_01",
    }
    data.update(overrides)
    return data


# ── 正向测试：四类对象合法构造 ──


def test_preference_valid_construction():
    pref = Preference(**base_preference())
    assert pref.preference_id == "pref_d4e_01"
    assert pref.user_id == "user_demo_01"
    assert pref.version == 1
    assert pref.memory_status is MemoryStatus.ACTIVE


def test_preference_implicit_candidate_valid():
    # 隐式候选偏好：memory_status=candidate，版本链完整
    pref = Preference(
        **base_preference(
            version=2,
            previous_version_id="pref_d4e_00",
            is_temporary=True,
            should_persist=False,
            memory_status=MemoryStatus.CANDIDATE,
            expression_type=ExpressionType.IMPLICIT,
            confidence_score=0.6,
        )
    )
    assert pref.expression_type is ExpressionType.IMPLICIT
    assert pref.memory_status is MemoryStatus.CANDIDATE


def test_knowledge_valid_construction():
    kn = Knowledge(**base_knowledge())
    assert kn.knowledge_id == "kn_d4e_01"
    assert kn.memory_type is MemoryType.MEDIUM_TERM  # 复用 pipeline.schemas.MemoryType


def test_conflict_valid_construction():
    cfl = Conflict(**base_conflict())
    assert cfl.conflict_id == "cfl_d4e_01"
    assert cfl.left_knowledge_id != cfl.right_knowledge_id


def test_conflict_resolved_manual_valid():
    cfl = Conflict(
        **base_conflict(
            resolution_status=ResolutionStatus.RESOLVED_MANUAL,
            resolved_at=T1,
            resolved_by="conflict_resolver_v1",
            resolution_strategy="keep_higher_confidence",
        )
    )
    assert cfl.resolution_status is ResolutionStatus.RESOLVED_MANUAL
    assert cfl.resolved_by == "conflict_resolver_v1"


def test_forget_plan_valid_construction():
    fgp = ForgetPlan(**base_forget_plan())
    assert fgp.forget_plan_id == "fgp_d4e_01"
    assert fgp.forget_mode is ForgetMode.SINGLE_ITEM


def test_forget_plan_full_reset_valid():
    # full_reset 无模式条件字段要求
    fgp = ForgetPlan(
        **base_forget_plan(
            forget_mode=ForgetMode.FULL_RESET,
            target_type=TargetType.ALL,
            target_id=None,
        )
    )
    assert fgp.forget_mode is ForgetMode.FULL_RESET


def test_models_are_pydantic_v2():
    from pydantic import BaseModel

    for model in (Preference, Knowledge, Conflict, ForgetPlan):
        assert issubclass(model, BaseModel)
        assert model.model_config.get("extra") == "forbid"


# ── 枚举值全覆盖（D3 §5.6 FROZEN 值） ──


@pytest.mark.parametrize(
    "enum_class, expected_values",
    [
        (ExpressionType, {"explicit", "implicit"}),
        (PreferenceScope, {"global", "topic", "tool", "session", "time_window"}),
        (
            KnowledgeType,
            {"workflow", "case", "template", "fact", "constraint", "failure_experience"},
        ),
        (MemoryStatus, {"active", "superseded", "deprecated", "expired", "removed", "candidate"}),
        (
            ConflictType,
            {"contradiction", "temporal_inconsistency", "source_conflict",
             "preference_conflict", "scope_ambiguity"},
        ),
        (
            ResolutionStatus,
            {"detected", "analyzing", "resolved_auto", "resolved_manual",
             "deferred", "unresolvable"},
        ),
        (
            ForgetMode,
            {"single_item", "session", "topic", "time_window", "full_reset"},
        ),
        (
            ForgetPlanStatus,
            {"pending", "previewing", "awaiting_confirmation", "executing",
             "completed", "failed", "rolled_back"},
        ),
        (TargetType, {"knowledge", "preference", "event", "all"}),
    ],
)
def test_enum_values_match_d3_frozen(enum_class, expected_values):
    actual = {member.value for member in enum_class}
    assert actual == expected_values


# ── 反向测试：Preference ──


def test_preference_empty_id_rejected():
    with pytest.raises(ValidationError):
        Preference(**base_preference(preference_id=""))


def test_preference_invalid_expression_type_rejected():
    with pytest.raises(ValidationError):
        Preference(**base_preference(expression_type="inferred"))


def test_preference_confidence_out_of_bounds_rejected():
    for bad in (-0.1, 1.1):
        with pytest.raises(ValidationError):
            Preference(**base_preference(confidence_score=bad))


def test_preference_confidence_bool_rejected_strict():
    # strict=True：bool 不得自动转换为 1.0
    with pytest.raises(ValidationError):
        Preference(**base_preference(confidence_score=True))


def test_preference_temporary_conflict_rejected():
    # is_temporary=true + memory_status=active → 拒绝（D3 §7.9）
    with pytest.raises(ValidationError):
        Preference(
            **base_preference(
                is_temporary=True, should_persist=True, memory_status=MemoryStatus.ACTIVE
            )
        )


def test_preference_no_persist_conflict_rejected():
    # should_persist=false + memory_status=active → 拒绝（D3 §7.9）
    with pytest.raises(ValidationError):
        Preference(
            **base_preference(
                should_persist=False, is_temporary=False, memory_status=MemoryStatus.ACTIVE
            )
        )


def test_preference_version_chain_missing_previous_rejected():
    # version=2 缺 previous_version_id → 拒绝（D3 §7.2）
    with pytest.raises(ValidationError):
        Preference(**base_preference(version=2))


def test_preference_version_one_with_previous_rejected():
    # version=1 携带 previous_version_id → 拒绝（D3 §7.2）
    with pytest.raises(ValidationError):
        Preference(
            **base_preference(version=1, previous_version_id="pref_d4e_prev")
        )


def test_preference_time_order_rejected():
    with pytest.raises(ValidationError):
        Preference(**base_preference(created_at=T1, updated_at=T0))


def test_preference_extra_field_rejected():
    with pytest.raises(ValidationError):
        Preference(**base_preference(unexpected_field="x"))


def test_preference_empty_evidence_id_rejected():
    with pytest.raises(ValidationError):
        Preference(**base_preference(evidence_event_ids=["", "evt_d4e_01"]))


# ── 反向测试：Knowledge ──


def test_knowledge_empty_id_rejected():
    with pytest.raises(ValidationError):
        Knowledge(**base_knowledge(knowledge_id=""))


def test_knowledge_invalid_type_rejected():
    with pytest.raises(ValidationError):
        Knowledge(**base_knowledge(knowledge_type="unknown_type"))


def test_knowledge_confidence_out_of_bounds_rejected():
    for bad in (-0.1, 1.1):
        with pytest.raises(ValidationError):
            Knowledge(**base_knowledge(confidence_score=bad))


def test_knowledge_time_order_rejected():
    with pytest.raises(ValidationError):
        Knowledge(**base_knowledge(created_at=T1, updated_at=T0))


def test_knowledge_extra_field_rejected():
    with pytest.raises(ValidationError):
        Knowledge(**base_knowledge(unexpected_field="x"))


def test_knowledge_invalid_memory_type_rejected():
    with pytest.raises(ValidationError):
        Knowledge(**base_knowledge(memory_type="ultra_long"))


def test_knowledge_negative_access_count_rejected():
    with pytest.raises(ValidationError):
        Knowledge(**base_knowledge(access_count=-1))


# ── 反向测试：Conflict ──


def test_conflict_empty_id_rejected():
    with pytest.raises(ValidationError):
        Conflict(**base_conflict(conflict_id=""))


def test_conflict_invalid_type_rejected():
    with pytest.raises(ValidationError):
        Conflict(**base_conflict(conflict_type="made_up_conflict"))


def test_conflict_self_conflict_rejected():
    with pytest.raises(ValidationError):
        Conflict(
            **base_conflict(
                left_knowledge_id="kn_d4e_01", right_knowledge_id="kn_d4e_01"
            )
        )


def test_conflict_resolved_without_metadata_rejected():
    # resolved_auto 缺 resolved_at / resolved_by → 拒绝（D3 §5.4）
    with pytest.raises(ValidationError):
        Conflict(**base_conflict(resolution_status=ResolutionStatus.RESOLVED_AUTO))


def test_conflict_resolution_confidence_out_of_bounds_rejected():
    with pytest.raises(ValidationError):
        Conflict(**base_conflict(resolution_confidence=1.5))


def test_conflict_time_order_rejected():
    with pytest.raises(ValidationError):
        Conflict(
            **base_conflict(
                resolution_status=ResolutionStatus.RESOLVED_MANUAL,
                resolved_at=T0,
                resolved_by="conflict_resolver_v1",
                detected_at=T1,
            )
        )


def test_conflict_extra_field_rejected():
    with pytest.raises(ValidationError):
        Conflict(**base_conflict(unexpected_field="x"))


# ── 反向测试：ForgetPlan ──


def test_forget_plan_empty_id_rejected():
    with pytest.raises(ValidationError):
        ForgetPlan(**base_forget_plan(forget_plan_id=""))


def test_forget_plan_invalid_mode_rejected():
    with pytest.raises(ValidationError):
        ForgetPlan(**base_forget_plan(forget_mode="everything"))


def test_forget_plan_single_item_missing_target_rejected():
    with pytest.raises(ValidationError):
        ForgetPlan(**base_forget_plan(target_id=None))


@pytest.mark.parametrize(
    "mode, matching_field",
    [
        (ForgetMode.SINGLE_ITEM, "target_id"),
        (ForgetMode.SESSION, "target_session_id"),
        (ForgetMode.TOPIC, "target_topic"),
        (ForgetMode.TIME_WINDOW, "target_time_range"),
    ],
)
def test_forget_plan_rejects_empty_matching_selector(mode, matching_field):
    """精准遗忘的模式 selector 不能以空串绕过必填检查。"""
    selectors = {
        "target_id": None,
        "target_session_id": None,
        "target_topic": None,
        "target_time_range": None,
    }
    selectors[matching_field] = ""
    with pytest.raises(ValidationError):
        ForgetPlan(**base_forget_plan(forget_mode=mode, **selectors))


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_selector": " \t "},
        {"target_id": " \n "},
        {"resolved_target_ids": ["  "], "affected_count": 1},
    ],
)
def test_forget_plan_rejects_whitespace_only_selectors_and_resolved_ids(overrides):
    """精准遗忘 selector 与解析 ID 不得以纯空白伪装为有效值。"""
    with pytest.raises(ValidationError):
        ForgetPlan(**base_forget_plan(**overrides))


def test_forget_plan_single_item_cross_mode_selector_rejected():
    """TD-015：单条遗忘不得携带会话 selector 以扩大删除范围。"""
    with pytest.raises(ValidationError):
        ForgetPlan(**base_forget_plan(target_session_id="session_d10e_other"))


@pytest.mark.parametrize(
    "mode, target_type, matching_field, matching_value",
    [
        (ForgetMode.SINGLE_ITEM, TargetType.PREFERENCE, "target_id", "pref_d10e_01"),
        (ForgetMode.SESSION, TargetType.ALL, "target_session_id", "session_d10e_01"),
        (ForgetMode.TOPIC, TargetType.KNOWLEDGE, "target_topic", "演示主题"),
        (ForgetMode.TIME_WINDOW, TargetType.EVENT, "target_time_range", "2026-09-01/2026-09-02"),
    ],
)
def test_forget_plan_accepts_only_its_matching_selector(
    mode, target_type, matching_field, matching_value
):
    """TD-015：每种具有专属 selector 的模式只接受自己的 selector。"""
    selectors = {
        "target_id": None,
        "target_session_id": None,
        "target_topic": None,
        "target_time_range": None,
    }
    if matching_field is not None:
        selectors[matching_field] = matching_value
    plan = ForgetPlan(
        **base_forget_plan(
            forget_mode=mode,
            target_type=target_type,
            **selectors,
        )
    )
    assert plan.forget_mode is mode


@pytest.mark.parametrize(
    "mode, required_field, required_value, extra_field",
    [
        (ForgetMode.SINGLE_ITEM, "target_id", "pref_d10e_01", "target_session_id"),
        (ForgetMode.SESSION, "target_session_id", "session_d10e_01", "target_topic"),
        (ForgetMode.TOPIC, "target_topic", "演示主题", "target_time_range"),
        (ForgetMode.TIME_WINDOW, "target_time_range", "2026-09-01/2026-09-02", "target_id"),
    ],
)
def test_forget_plan_rejects_every_cross_mode_selector(
    mode, required_field, required_value, extra_field
):
    """TD-015：任意额外 selector 都会拒绝，不能悄然扩大精准删除范围。"""
    selectors = {
        "target_id": None,
        "target_session_id": None,
        "target_topic": None,
        "target_time_range": None,
    }
    selectors[required_field] = required_value
    selectors[extra_field] = "unexpected_d10e_selector"
    with pytest.raises(ValidationError):
        ForgetPlan(**base_forget_plan(forget_mode=mode, **selectors))


@pytest.mark.parametrize(
    "target_type",
    [
        TargetType.ALL,
        TargetType.PREFERENCE,
    ],
)
def test_forget_plan_preserves_unresolved_full_reset_type_boundary(target_type):
    """HD-SCHEMA-06：E/D 未书面确认前，不由 Domain 冻结 full_reset 类型细节。"""
    plan = ForgetPlan(
        **base_forget_plan(
            forget_mode=ForgetMode.FULL_RESET,
            target_type=target_type,
            target_id=None,
        )
    )
    assert plan.forget_mode is ForgetMode.FULL_RESET


@pytest.mark.parametrize(
    "selector_field",
    ["target_id", "target_session_id", "target_topic", "target_time_range"],
)
def test_forget_plan_full_reset_rejects_every_concrete_selector(selector_field):
    """TD-015：没有专属 selector 的 full_reset 不得夹带局部目标。"""
    selectors = {
        "target_id": None,
        "target_session_id": None,
        "target_topic": None,
        "target_time_range": None,
    }
    selectors[selector_field] = "unexpected_d10e_selector"
    with pytest.raises(ValidationError):
        ForgetPlan(
            **base_forget_plan(
                forget_mode=ForgetMode.FULL_RESET,
                **selectors,
            )
        )


@pytest.mark.parametrize(
    "resolved_target_ids, affected_count",
    [
        ([""], 1),
        (["pref_d10e_01", "pref_d10e_01"], 2),
        (["pref_d10e_01"], 2),
        (["pref_d10e_01"], None),
    ],
)
def test_forget_plan_resolved_targets_require_precise_preview_metadata(
    resolved_target_ids, affected_count
):
    """SEC-FORGET-01：解析结果必须无空/重复 ID，并与预览计数一一对应。"""
    with pytest.raises(ValidationError):
        ForgetPlan(
            **base_forget_plan(
                resolved_target_ids=resolved_target_ids,
                affected_count=affected_count,
            )
        )


def test_forget_plan_empty_resolution_has_zero_affected_count():
    """空解析结果可预览，但必须明确记为零影响。"""
    plan = ForgetPlan(
        **base_forget_plan(resolved_target_ids=[], affected_count=0)
    )
    assert plan.resolved_target_ids == []
    assert plan.affected_count == 0


def test_forget_plan_session_missing_target_rejected():
    with pytest.raises(ValidationError):
        ForgetPlan(
            **base_forget_plan(
                forget_mode=ForgetMode.SESSION, target_id=None, target_session_id=None
            )
        )


def test_forget_plan_topic_missing_target_rejected():
    with pytest.raises(ValidationError):
        ForgetPlan(
            **base_forget_plan(
                forget_mode=ForgetMode.TOPIC, target_id=None, target_topic=None
            )
        )


def test_forget_plan_time_window_missing_target_rejected():
    with pytest.raises(ValidationError):
        ForgetPlan(
            **base_forget_plan(
                forget_mode=ForgetMode.TIME_WINDOW,
                target_id=None,
                target_time_range=None,
            )
        )


def test_forget_plan_completed_without_executed_at_rejected():
    with pytest.raises(ValidationError):
        ForgetPlan(
            **base_forget_plan(
                status=ForgetPlanStatus.COMPLETED,
                executed_at=None,
            )
        )


def test_forget_plan_executed_before_created_rejected():
    with pytest.raises(ValidationError):
        ForgetPlan(
            **base_forget_plan(
                status=ForgetPlanStatus.COMPLETED,
                executed_at=T0,
                created_at=T1,
            )
        )


def test_forget_plan_extra_field_rejected():
    with pytest.raises(ValidationError):
        ForgetPlan(**base_forget_plan(unexpected_field="x"))


# ── 共享 NonEmptyStr 约束（TD-013）：空串与纯空白拒绝，原值不 strip ──


@pytest.mark.parametrize(
    "blank_value",
    [
        "",
        " ",
        "\t",
        "\n",
        "\r",
        " \t\n\r ",
        "\u3000",  # 全角空格（str.strip 口径）
        " \u3000\t ",
    ],
)
def test_non_empty_str_rejects_empty_and_whitespace_only(blank_value):
    """TD-013：空串与纯空白（空格/Tab/换行/混合/全角空格）一律拒绝。"""
    with pytest.raises(ValidationError):
        TypeAdapter(NonEmptyStr).validate_python(blank_value)


@pytest.mark.parametrize(
    "valid_value",
    [
        "pref_d4e_01",
        "  padded  ",  # 带首尾空格但含有效字符：必须原值保留，不得 strip
        "\tleading-tab",
        "trailing-newline\n",
        " 中 文 空 格 内 部 ",
    ],
)
def test_non_empty_str_preserves_original_value(valid_value):
    """TD-013：含有效字符的输入通过，且返回值与输入逐字相等（不 strip）。"""
    assert TypeAdapter(NonEmptyStr).validate_python(valid_value) == valid_value


def test_non_empty_id_list_rejects_whitespace_only_element():
    """TD-013：NonEmptyIdList 元素级继承收紧——纯空白元素拒绝。"""
    with pytest.raises(ValidationError):
        TypeAdapter(NonEmptyIdList).validate_python(["pref_d4e_01", "  "])
    with pytest.raises(ValidationError):
        TypeAdapter(NonEmptyIdList).validate_python(["\t"])


def test_non_empty_id_list_preserves_padded_element():
    """TD-013：NonEmptyIdList 含有效字符的元素原值保留。"""
    result = TypeAdapter(NonEmptyIdList).validate_python(["  pref_d4e_01  "])
    assert result == ["  pref_d4e_01  "]


@pytest.mark.parametrize(
    "model_factory, field, base_data",
    [
        (Preference, "preference_id", base_preference()),
        (Knowledge, "knowledge_id", base_knowledge()),
        (Conflict, "conflict_id", base_conflict()),
        (ForgetPlan, "forget_plan_id", base_forget_plan()),
    ],
)
def test_domain_rejects_whitespace_only_non_empty_str_field(
    model_factory, field, base_data
):
    """TD-013：四模型 NonEmptyStr 字段传纯空白 → ValidationError。"""
    for blank in (" ", "\t", "\n", " \t\n "):
        with pytest.raises(ValidationError):
            model_factory(**{**base_data, field: blank})


@pytest.mark.parametrize(
    "model_factory, field, base_data",
    [
        (Preference, "preference_key", base_preference()),
        (Knowledge, "content_summary", base_knowledge()),
        (Conflict, "conflict_summary", base_conflict()),
        (ForgetPlan, "target_selector", base_forget_plan()),
    ],
)
def test_domain_preserves_padded_non_empty_str_field(
    model_factory, field, base_data
):
    """TD-013：含首尾空格但含有效字符的字段值构造成功且逐字保留。"""
    padded = "  padded-value  "
    obj = model_factory(**{**base_data, field: padded})
    assert getattr(obj, field) == padded


# ── TD-014：Optional ID / Reference / Selector 存在时须非空非纯空白 ──


@pytest.mark.parametrize(
    "blank_value",
    [
        "",
        " \t ",
    ],
)
def test_preference_optional_previous_version_id_rejects_blank(blank_value):
    """TD-014：前版 ID 存在时不得为空串或纯空白（version 链必填不变量不变）。"""
    with pytest.raises(ValidationError):
        Preference(**base_preference(version=2, previous_version_id=blank_value))


@pytest.mark.parametrize(
    "field, blank_value",
    [
        ("content_ref", ""),
        ("superseded_by_id", " "),
    ],
)
def test_knowledge_optional_reference_rejects_blank(field, blank_value):
    """TD-014：content_ref / superseded_by_id 存在时不得为空串或纯空白。"""
    with pytest.raises(ValidationError):
        Knowledge(**base_knowledge(**{field: blank_value}))


@pytest.mark.parametrize(
    "involved_ids",
    [
        ["", "kn_d4e_03"],
        ["  "],
        ["\t"],
        [" \u3000"],
    ],
)
def test_conflict_involved_knowledge_ids_reject_blank_element(involved_ids):
    """TD-014：involved_knowledge_ids 元素必须非空且非纯空白。"""
    with pytest.raises(ValidationError):
        Conflict(**base_conflict(involved_knowledge_ids=involved_ids))


def test_conflict_resolved_by_rejects_whitespace_only():
    """TD-014：resolved_by 存在时不得为纯空白（resolved 状态仍须携带执行方）。"""
    with pytest.raises(ValidationError):
        Conflict(
            **base_conflict(
                resolution_status=ResolutionStatus.RESOLVED_MANUAL,
                resolved_at=T1,
                resolved_by=" ",
            )
        )


@pytest.mark.parametrize(
    "blank_value",
    [
        "",
        "\n",
    ],
)
def test_forget_plan_rollback_plan_id_rejects_blank(blank_value):
    """TD-014：rollback_plan_id 存在时不得为空串或纯空白。"""
    with pytest.raises(ValidationError):
        ForgetPlan(**base_forget_plan(rollback_plan_id=blank_value))


def test_optional_id_reference_fields_missing_still_default_to_none():
    """TD-014：Optional ID/Reference 缺失（None）语义保持不变。"""
    pref = Preference(**base_preference())
    assert pref.previous_version_id is None
    assert pref.extracted_entities is None

    kn = Knowledge(**base_knowledge())
    assert kn.content_ref is None
    assert kn.superseded_by_id is None

    cfl = Conflict(**base_conflict())
    assert cfl.involved_knowledge_ids is None
    assert cfl.resolved_by is None

    fgp = ForgetPlan(**base_forget_plan())
    assert fgp.rollback_plan_id is None


def test_conflict_involved_knowledge_ids_accepts_non_blank_elements():
    """TD-014：involved_knowledge_ids 携带合法非空元素构造成功。"""
    cfl = Conflict(**base_conflict(involved_knowledge_ids=["kn_d4e_03"]))
    assert cfl.involved_knowledge_ids == ["kn_d4e_03"]


# ── 导入契约：domain 不承载第二套共享类型 ──


def test_domain_does_not_re_export_pipeline_shared_types():
    import domain

    for forbidden in (
        "MemorySourceEvent",
        "NormalizedEvent",
        "PreferenceCandidate",
        "KnowledgeCandidate",
    ):
        assert not hasattr(domain, forbidden), (
            f"domain 不得导出/定义第二套 {forbidden}"
        )


def test_domain_does_not_define_memory_type_copy():
    import domain

    # MemoryType 由 domain/knowledge.py 从 pipeline.schemas 复用，禁止在 domain 重复定义
    assert not hasattr(domain, "MemoryType")


def test_knowledge_memory_type_reuses_pipeline_schema():
    # Knowledge.memory_type 解析自 pipeline.schemas.MemoryType（复用而非复制）
    kn = Knowledge(**base_knowledge(memory_type=MemoryType.LONG_TERM))
    assert kn.memory_type is MemoryType.LONG_TERM
