"""D10E 精准遗忘业务状态机的公共行为测试。

测试 seam：service.forgetting_policy.ForgetPlanStateMachine.transition。
该策略只编排已验证的业务状态，不持久化、不发 Outbox、不调用 Vector/FTS5，
也不把确认布尔值当作 D 轨确认令牌的替代品；D 轨适配器接线前拒绝进入执行。
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain import ForgetMode, ForgetPlan, ForgetPlanStatus, TargetType  # noqa: E402
from service.forgetting_policy import (  # noqa: E402
    ForgetPlanStateMachine,
    ForgetPlanTransitionError,
)


USER = "user_demo_d10e"
T0 = datetime(2026, 9, 1, 9, 0, 0, tzinfo=timezone.utc)


def make_pending_plan(**overrides) -> ForgetPlan:
    data = {
        "forget_plan_id": "fgp_d10e_01",
        "user_id": USER,
        "forget_mode": ForgetMode.SINGLE_ITEM,
        "target_selector": "删除演示偏好",
        "target_type": TargetType.PREFERENCE,
        "status": ForgetPlanStatus.PENDING,
        "is_cascade": False,
        "has_vector_cleanup": False,
        "requires_confirmation": True,
        "created_at": T0,
        "target_id": "pref_d10e_01",
    }
    data.update(overrides)
    return ForgetPlan(**data)


def test_pending_plan_can_enter_preview_for_its_owner():
    """SEC-FORGET-02：遗忘必须先进入预览，且由同一用户推进。"""
    policy = ForgetPlanStateMachine()

    previewing = policy.transition(
        make_pending_plan(),
        ForgetPlanStatus.PREVIEWING,
        actor_user_id=USER,
    )

    assert previewing.status is ForgetPlanStatus.PREVIEWING
    assert previewing.user_id == USER


def _advance_to_awaiting_confirmation(
    policy: ForgetPlanStateMachine,
    **plan_overrides,
) -> ForgetPlan:
    previewing = policy.transition(
        make_pending_plan(**plan_overrides),
        ForgetPlanStatus.PREVIEWING,
        actor_user_id=USER,
    )
    return policy.transition(
        previewing,
        ForgetPlanStatus.AWAITING_CONFIRMATION,
        actor_user_id=USER,
    )


@pytest.mark.parametrize(
    "plan_overrides",
    [
        {},
        {"affected_count": 0},
    ],
)
def test_awaiting_confirmation_requires_a_resolved_target_snapshot(plan_overrides):
    """SEC-FORGET-01/02：未产生精准预览快照时不得请求用户确认。"""
    with pytest.raises(ForgetPlanTransitionError, match="preview_snapshot_required"):
        _advance_to_awaiting_confirmation(ForgetPlanStateMachine(), **plan_overrides)


@pytest.mark.parametrize(
    "plan_overrides",
    [
        {"resolved_target_ids": [], "affected_count": 0},
        {"resolved_target_ids": ["pref_d10e_01"], "affected_count": 1},
    ],
)
def test_awaiting_confirmation_accepts_zero_or_nonempty_resolved_target_snapshot(
    plan_overrides,
):
    """零结果和非空结果都是可供用户确认的精准预览。"""
    plan = _advance_to_awaiting_confirmation(
        ForgetPlanStateMachine(), **plan_overrides
    )
    assert plan.status is ForgetPlanStatus.AWAITING_CONFIRMATION


def test_transition_rejects_cross_user_actor():
    """SEC-FORGET-04：其它用户不能推进本用户的遗忘计划。"""
    with pytest.raises(ForgetPlanTransitionError, match="forget_plan_owner_mismatch"):
        ForgetPlanStateMachine().transition(
            make_pending_plan(),
            ForgetPlanStatus.PREVIEWING,
            actor_user_id="user_demo_d10e_other",
        )


def test_transition_cannot_skip_preview_or_confirmation():
    """SEC-FORGET-02：不得从 pending 跳到 awaiting_confirmation 或 executing。"""
    policy = ForgetPlanStateMachine()

    for next_status in (
        ForgetPlanStatus.AWAITING_CONFIRMATION,
        ForgetPlanStatus.EXECUTING,
    ):
        with pytest.raises(ForgetPlanTransitionError, match="invalid_forget_plan_transition"):
            policy.transition(
                make_pending_plan(), next_status, actor_user_id=USER
            )


def test_execution_is_fail_closed_until_d_confirmation_adapter_is_integrated():
    """SEC-FORGET-02：公共 E 轨 seam 不得以调用方输入绕过确认进入执行。"""
    policy = ForgetPlanStateMachine()
    awaiting_confirmation = _advance_to_awaiting_confirmation(
        policy,
        resolved_target_ids=[],
        affected_count=0,
    )

    with pytest.raises(ForgetPlanTransitionError, match="invalid_forget_plan_transition"):
        policy.transition(
            awaiting_confirmation, ForgetPlanStatus.EXECUTING, actor_user_id=USER
        )


def test_execution_and_terminal_transitions_are_owned_by_d_adapter():
    """伪造 executing 计划也不能绕过 D 的令牌验证/事务适配器。"""
    policy = ForgetPlanStateMachine()
    executing = make_pending_plan(status=ForgetPlanStatus.EXECUTING)

    with pytest.raises(ForgetPlanTransitionError, match="execution_transition_owned_by_d"):
        policy.transition(
            executing,
            ForgetPlanStatus.COMPLETED,
            actor_user_id=USER,
            executed_at=datetime(2026, 9, 1, 9, 5, 0, tzinfo=timezone.utc),
        )
