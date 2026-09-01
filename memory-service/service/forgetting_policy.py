"""D10E 精准遗忘业务状态机（E 轨 service 内部）。

本模块只编排已创建的 ``ForgetPlan`` 的业务状态，不负责自然语言解析、目标
解析、确认令牌验证、SQLite 事务、Outbox、Vector/FTS5 删除或审计持久化。
这些职责仍分别属于 C/D/B 轨的已声明接口边界。

确认边界：确认令牌的绑定、过期与验签由 D 轨负责。本模块在该适配器接线前
对 ``awaiting_confirmation → executing`` 失败关闭，绝不接收调用方可伪造的布尔值。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from domain import ForgetPlan, ForgetPlanStatus


_ALLOWED_TRANSITIONS = {
    ForgetPlanStatus.PENDING: frozenset({ForgetPlanStatus.PREVIEWING}),
    ForgetPlanStatus.PREVIEWING: frozenset({ForgetPlanStatus.AWAITING_CONFIRMATION}),
    ForgetPlanStatus.AWAITING_CONFIRMATION: frozenset(),
}


class ForgetPlanTransitionError(ValueError):
    """遗忘计划不能按请求方式推进时抛出（不包含 selector 或正文）。"""


class ForgetPlanStateMachine:
    """无副作用的 ForgetPlan 状态机。

    ``transition`` 返回经 Domain 重新校验的全新 ``ForgetPlan``，不修改传入对象。
    所有权在进入持久化或删除通道前再次校验，防止跨用户推进遗忘计划。
    """

    def transition(
        self,
        plan: ForgetPlan,
        next_status: ForgetPlanStatus,
        *,
        actor_user_id: str,
        executed_at: Optional[datetime] = None,
    ) -> ForgetPlan:
        """推进一个合法的遗忘计划状态。

        在 D 轨将确认令牌校验接入执行通道前，不能由此公共业务 seam 推进
        ``awaiting_confirmation → executing``。执行及终态收口全部由 D 轨适配器
        在令牌验证和事务边界内处理。
        """
        if not isinstance(plan, ForgetPlan):
            raise ForgetPlanTransitionError("invalid_forget_plan")
        if not isinstance(next_status, ForgetPlanStatus):
            raise ForgetPlanTransitionError("invalid_next_status")
        if actor_user_id != plan.user_id:
            raise ForgetPlanTransitionError("forget_plan_owner_mismatch")
        if plan.status not in _ALLOWED_TRANSITIONS:
            raise ForgetPlanTransitionError("execution_transition_owned_by_d")
        if next_status not in _ALLOWED_TRANSITIONS[plan.status]:
            raise ForgetPlanTransitionError("invalid_forget_plan_transition")
        if (
            plan.status is ForgetPlanStatus.PREVIEWING
            and next_status is ForgetPlanStatus.AWAITING_CONFIRMATION
            and (
                plan.resolved_target_ids is None
                or plan.affected_count is None
            )
        ):
            raise ForgetPlanTransitionError("preview_snapshot_required")
        if executed_at is not None:
            raise ForgetPlanTransitionError("pre_confirmation_transition_forbids_executed_at")

        return ForgetPlan.model_validate({**plan.model_dump(), "status": next_status})


__all__ = ["ForgetPlanStateMachine", "ForgetPlanTransitionError"]
