"""
preference.py — Day4 E 轨业务 Domain：Preference（偏好）Pydantic v2 模型

对齐 D3_MEMORY_BUSINESS_CONTRACT_V1.md §5.2（Preference 字段逐项处置）。
字段处置说明（D3）：
- confidence_score：DEFERRED（量化模型待 A/E，HD-SCHEMA-03），本任务只做
  [0,1] 边界 + strict float 校验，不实现量化逻辑。
- is_active / should_decay：REVISED（过渡字段），待 D/E 统一为 memory_status 后移除，
  当前按 D3 过渡保留，仍为必填。
- decay_after_at：DEFERRED（衰减策略待 A/E），本模型仅定义字段，不实现衰减。

业务校验器（D3 已冻结语义）：
1. version_chain：version=1 → previous_version_id=None；version>1 → 必填
   （D3 §7.2 版本与回溯）。
2. temporary_boundary：is_temporary=true 或 should_persist=false 时
   memory_status 必须为 candidate/expired，不得晋升为正式长期偏好（D3 §7.9、
   Schema §4.4、SEC-FORGET/LLM 相关红线）。
3. time_order：updated_at >= created_at。

*禁止模型生成字段（D3 §7.10）：user_id 必须由宿主侧业务事件/外部输入产出。
本模型不实现任何生成链路，仅结构承载。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import AwareDatetime, ConfidenceScore, NonEmptyIdList, NonEmptyStr
from .enums import ExpressionType, MemoryStatus, PreferenceScope


class Preference(BaseModel):
    """用户偏好条目（E 轨 Domain 骨架，D3 §5.2 字段落地）。

    extra="forbid"：拒绝未声明字段，防止把未知输入静默制造成合法业务对象。
    """

    model_config = ConfigDict(extra="forbid")

    # ── D3 §5.2 FROZEN_BUSINESS_SEMANTIC / REVISED 必填字段 ──
    preference_id: NonEmptyStr
    user_id: NonEmptyStr  # 数据归属隔离键，*禁止模型生成（D3 §7.1/§7.10）
    expression_type: ExpressionType
    preference_scope: PreferenceScope
    preference_key: NonEmptyStr
    preference_value: NonEmptyStr
    confidence_score: ConfidenceScore
    memory_status: MemoryStatus
    is_active: bool  # 过渡字段（D3 REVISED，待 D/E 移除）
    is_temporary: bool
    should_persist: bool
    should_decay: bool  # 过渡字段（D3 REVISED，待 D/E 移除）
    evidence_event_ids: NonEmptyIdList
    version: int = Field(ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    requires_confirmation: bool

    # ── D3 §5.2 可选字段 ──
    decay_after_at: Optional[AwareDatetime] = None  # DEFERRED：衰减函数待 A/E
    previous_version_id: Optional[NonEmptyStr] = None  # 存在时须非空非纯空白（v1 仍须 None）
    extracted_entities: Optional[List[str]] = None

    @model_validator(mode="after")
    def _version_chain(self) -> "Preference":
        """版本链完整性（D3 §7.2）：v1 必须无 previous_version_id；v>1 必须引上一版。"""
        if self.version == 1 and self.previous_version_id is not None:
            raise ValueError(
                "version=1 must not carry previous_version_id "
                "(D3 §7.2 version chain)")
        if self.version > 1 and self.previous_version_id is None:
            raise ValueError(
                "version>1 requires previous_version_id "
                "(D3 §7.2 version chain)")
        return self

    @model_validator(mode="after")
    def _temporary_boundary(self) -> "Preference":
        """临时要求/不持久化边界（D3 §7.9）：不得携带正式长期偏好状态。"""
        if (self.is_temporary or not self.should_persist) and (
            self.memory_status not in (MemoryStatus.CANDIDATE, MemoryStatus.EXPIRED)
        ):
            raise ValueError(
                "is_temporary=true or should_persist=false requires "
                "memory_status in {candidate, expired} (D3 §7.9)")
        return self

    @model_validator(mode="after")
    def _time_order(self) -> "Preference":
        """时间顺序：updated_at 不得早于 created_at。"""
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be >= created_at")
        return self