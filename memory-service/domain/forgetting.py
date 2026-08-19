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

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import AwareDatetime, NonEmptyStr
from .enums import ForgetMode, ForgetPlanStatus, TargetType


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
    resolved_target_ids: Optional[List[str]] = None  # *禁止模型生成（D3 §7.6）
    target_id: Optional[str] = None  # conditional: forget_mode=single_item 必填
    target_session_id: Optional[str] = None  # conditional: forget_mode=session 必填
    target_topic: Optional[str] = None  # conditional: forget_mode=topic 必填
    target_time_range: Optional[str] = None  # conditional: forget_mode=time_window 必填
    executed_at: Optional[AwareDatetime] = None
    affected_count: Optional[int] = Field(default=None, ge=0)  # *禁止模型生成
    rollback_plan_id: Optional[str] = None  # 回滚计划引用（事务可行性待 D）

    @model_validator(mode="after")
    def _mode_conditional(self) -> "ForgetPlan":
        """模式相关条件字段：不得跨 forget_mode 边界扩展删除范围（SEC-FORGET-03）。"""
        if self.forget_mode == ForgetMode.SINGLE_ITEM and self.target_id is None:
            raise ValueError(
                "forget_mode=single_item requires target_id (D3 §5.5)")
        if self.forget_mode == ForgetMode.SESSION and self.target_session_id is None:
            raise ValueError(
                "forget_mode=session requires target_session_id (D3 §5.5)")
        if self.forget_mode == ForgetMode.TOPIC and self.target_topic is None:
            raise ValueError(
                "forget_mode=topic requires target_topic (D3 §5.5)")
        if self.forget_mode == ForgetMode.TIME_WINDOW and self.target_time_range is None:
            raise ValueError(
                "forget_mode=time_window requires target_time_range (D3 §5.5)")
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
    def _time_order(self) -> "ForgetPlan":
        """执行时间不得早于计划创建时间。"""
        if self.executed_at is not None and self.executed_at < self.created_at:
            raise ValueError("executed_at must be >= created_at")
        return self