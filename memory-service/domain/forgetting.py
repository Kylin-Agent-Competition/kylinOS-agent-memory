"""
forgetting.py — Day4 E 轨业务 Domain：ForgetPlan（遗忘计划）Pydantic v2 模型

对齐 D3_MEMORY_BUSINESS_CONTRACT_V1.md §5.5（ForgetPlan 字段逐项处置）。
字段处置说明（D3）：
- resolved_target_ids：FROZEN，*禁止模型生成，须经「先预览再确认」流程
  （D3 §7.6、SEC-FORGET-01）；本模型仅结构承载，不实现目标解析。
- is_cascade：DEFERRED（级联范围待 E，HD-SCHEMA-06）。
- has_vector_cleanup：DEFERRED（Vector 同步清理策略待 B，HD-SCHEMA-05）。
- requires_confirmation：FROZEN，最终判定 *禁止模型生成（D3 §7.10）。
- affected_count：FROZEN，最终值 *禁止模型生成（D3 §7.10）。

业务校验器（D3 已冻结语义）：
1. mode_conditional：single_item→target_id 必填；session→target_session_id 必填；
   topic→target_topic 必填；time_window→target_time_range 必填（D3 §5.5、
   SEC-FORGET-03：不得跨 forget_mode 边界扩展删除范围）。
2. execution_consistency：status ∈ {completed, failed, rolled_back} 时必须携带
   executed_at。
3. time_order：executed_at 若存在，不得早于 created_at。

本模型不实现目标解析或真实删除（D3 §8.2 删除/遗忘物理执行逻辑待 D）。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .common import AwareDatetime, NonEmptyStr
from .enums import ForgetMode, ForgetPlanStatus, TargetType


_MODE_SELECTOR_FIELDS = {
    ForgetMode.SINGLE_ITEM: "target_id",
    ForgetMode.SESSION: "target_session_id",
    ForgetMode.TOPIC: "target_topic",
    ForgetMode.TIME_WINDOW: "target_time_range",
}
_SELECTOR_FIELDS = frozenset(_MODE_SELECTOR_FIELDS.values())


class ForgetPlan(BaseModel):
    """遗忘计划记录（E 轨 Domain 骨架，D3 §5.5 字段落地）。

    仅业务记录定义；不实现目标解析、真实删除、级联或 Vector 清理。
    """

    model_config = ConfigDict(extra="forbid")

    # ── D3 §5.5 FROZEN_BUSINESS_SEMANTIC 必填字段 ──
    forget_plan_id: NonEmptyStr
    user_id: NonEmptyStr  # 外部输入，*禁止模型生成（D3 §7.10）
    forget_mode: ForgetMode
    target_selector: NonEmptyStr  # 用户输入选择器
    target_type: TargetType
    status: ForgetPlanStatus
    is_cascade: bool  # DEFERRED：级联范围待 E（HD-SCHEMA-06）
    has_vector_cleanup: bool  # DEFERRED：Vector 策略待 B（HD-SCHEMA-05）
    requires_confirmation: bool  # 最终判定 *禁止模型生成（D3 §7.10）
    created_at: AwareDatetime

    # ── D3 §5.5 FROZEN / 条件字段 ──
    resolved_target_ids: Optional[List[NonEmptyStr]] = None  # *禁止模型生成（D3 §7.6）
    target_id: Optional[NonEmptyStr] = None  # conditional: forget_mode=single_item 必填
    target_session_id: Optional[NonEmptyStr] = None  # conditional: forget_mode=session 必填
    target_topic: Optional[NonEmptyStr] = None  # conditional: forget_mode=topic 必填
    target_time_range: Optional[NonEmptyStr] = None  # conditional: forget_mode=time_window 必填
    executed_at: Optional[AwareDatetime] = None
    affected_count: Optional[int] = Field(default=None, ge=0)  # *禁止模型生成
    rollback_plan_id: Optional[NonEmptyStr] = None  # 回滚计划引用（事务可行性待 D），存在时须非空非纯空白

    @field_validator(
        "target_selector",
        "target_id",
        "target_session_id",
        "target_topic",
        "target_time_range",
    )
    @classmethod
    def _selectors_must_not_be_whitespace_only(
        cls, value: Optional[str]
    ) -> Optional[str]:
        """保留原 selector 文本，但拒绝不能表达范围的纯空白输入。"""
        if value is not None and not value.strip():
            raise ValueError("forget target selector must not be whitespace only")
        return value

    @field_validator("resolved_target_ids")
    @classmethod
    def _resolved_ids_must_not_be_whitespace_only(
        cls, value: Optional[List[str]]
    ) -> Optional[List[str]]:
        """系统解析出的 ID 不能以纯空白占位。"""
        if value is not None and any(not target_id.strip() for target_id in value):
            raise ValueError("resolved target id must not be whitespace only")
        return value

    @model_validator(mode="after")
    def _mode_conditional(self) -> "ForgetPlan":
        """模式相关条件字段：不得跨 forget_mode 边界扩展删除范围（SEC-FORGET-03）。"""
        required_field = _MODE_SELECTOR_FIELDS.get(self.forget_mode)
        supplied_fields = {
            field_name
            for field_name in _SELECTOR_FIELDS
            if getattr(self, field_name) is not None
        }
        if required_field is None:
            # full_reset 的 target_type 与级联边界尚待 E/D 书面确认
            # （HD-SCHEMA-06），但 TD-015 仍禁止它混入任意具体 selector。
            if supplied_fields:
                raise ValueError(
                    "forget_mode=full_reset forbids concrete target selectors (TD-015)"
                )
            return self
        if required_field not in supplied_fields:
            raise ValueError(
                f"forget_mode={self.forget_mode.value} requires {required_field} (D3 §5.5)"
            )
        if supplied_fields != {required_field}:
            raise ValueError(
                "forget_mode only permits its matching target selector (TD-015)"
            )
        return self

    @model_validator(mode="after")
    def _execution_consistency(self) -> "ForgetPlan":
        """终态执行状态必须携带 executed_at。"""
        if self.status in (
            ForgetPlanStatus.COMPLETED,
            ForgetPlanStatus.FAILED,
            ForgetPlanStatus.ROLLED_BACK,
        ) and self.executed_at is None:
            raise ValueError(
                "status completed/failed/rolled_back requires executed_at (D3 §5.5)")
        return self

    @model_validator(mode="after")
    def _resolved_target_consistency(self) -> "ForgetPlan":
        """解析结果必须是精确、去重且可审计的预览集合（SEC-FORGET-01）。"""
        if self.resolved_target_ids is None:
            return self
        if self.affected_count is None:
            raise ValueError(
                "resolved_target_ids requires affected_count (SEC-FORGET-01)"
            )
        if len(set(self.resolved_target_ids)) != len(self.resolved_target_ids):
            raise ValueError("resolved_target_ids must not contain duplicates")
        if self.affected_count != len(self.resolved_target_ids):
            raise ValueError(
                "affected_count must match resolved_target_ids (SEC-FORGET-01)"
            )
        return self

    @model_validator(mode="after")
    def _time_order(self) -> "ForgetPlan":
        """执行时间不得早于计划创建时间。"""
        if self.executed_at is not None and self.executed_at < self.created_at:
            raise ValueError("executed_at must be >= created_at")
        return self
