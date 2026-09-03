"""
conflict.py — Day4 E 轨业务 Domain：Conflict（冲突）Pydantic v2 模型

对齐 D3_MEMORY_BUSINESS_CONTRACT_V1.md §5.4（Conflict 字段逐项处置）。
字段处置说明（D3）：
- resolution_strategy：DEFERRED（策略集合与优先级待 B/E），不冻结为枚举，
  本模型实现为 Optional[str]。
- is_auto_resolvable：DEFERRED（判定标准待 B/E），本模型仅定义 bool 字段，
  不实现判定逻辑。
- resolution_confidence：DEFERRED（计算方式待 B/E），*最终值禁止模型生成；
  本模型只做 [0,1] 边界 + strict float 校验。
- conflict_type 中 contradiction/temporal_inconsistency 的判定阈值算法：
  E 轨道不可冻结（REJECTED → DEFERRED 待 B，HD-SCHEMA-04）；本模型不实现
  任何冲突判定算法。

业务校验器（D3 已冻结语义）：
1. no_self_conflict：left_knowledge_id != right_knowledge_id。
2. resolution_consistency：resolution_status ∈ {resolved_auto, resolved_manual}
   时必须携带 resolved_at 且 resolved_by 非空（D3 §5.4）。
3. time_order：resolved_at 若存在，不得早于 detected_at。

冲突仅在同 user_id 边界内产生（D3 §3.5、SEC-UI-04 派生归属）；本模型不实现
隔离判定，user_id 字段承载业务隔离键语义。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, model_validator

from .common import AwareDatetime, ConfidenceScore, NonEmptyStr
from .enums import ConflictType, ResolutionStatus


class Conflict(BaseModel):
    """知识/偏好冲突记录（E 轨 Domain 骨架，D3 §5.4 字段落地）。

    仅业务记录定义；不实现冲突检测/消解算法（待 B，HD-SCHEMA-04）。
    """

    model_config = ConfigDict(extra="forbid")

    # ── D3 §5.4 FROZEN_BUSINESS_SEMANTIC 必填字段 ──
    conflict_id: NonEmptyStr
    user_id: NonEmptyStr  # 从涉及条目派生归属，*禁止模型生成（D3 §7.10）
    conflict_type: ConflictType
    left_knowledge_id: NonEmptyStr
    right_knowledge_id: NonEmptyStr
    conflict_summary: NonEmptyStr
    resolution_status: ResolutionStatus
    is_auto_resolvable: bool  # DEFERRED：判定标准待 B/E
    detected_at: AwareDatetime

    # ── D3 §5.4 DEFERRED / FROZEN 可选字段 ──
    involved_knowledge_ids: Optional[List[NonEmptyStr]] = None  # 多知识冲突 ID；存在时元素须非空非纯空白
    resolution_strategy: Optional[str] = None  # DEFERRED：不冻结为枚举
    resolution_confidence: Optional[ConfidenceScore] = None  # DEFERRED，*禁止模型生成
    resolved_at: Optional[AwareDatetime] = None
    resolved_by: Optional[NonEmptyStr] = None  # 消解执行方标识，*禁止模型生成；存在时须非空非纯空白

    @model_validator(mode="after")
    def _no_self_conflict(self) -> "Conflict":
        """同一用户边界内的冲突必须涉及两条不同条目。"""
        if self.left_knowledge_id == self.right_knowledge_id:
            raise ValueError(
                "left_knowledge_id must differ from right_knowledge_id "
                "(D3 §5.4 no self-conflict)")
        return self

    @model_validator(mode="after")
    def _resolution_consistency(self) -> "Conflict":
        """已消解状态必须携带消解时间与消解执行方。"""
        if self.resolution_status in (
            ResolutionStatus.RESOLVED_AUTO,
            ResolutionStatus.RESOLVED_MANUAL,
        ) and (self.resolved_at is None or self.resolved_by is None):
            raise ValueError(
                "resolution_status resolved_auto/resolved_manual requires "
                "resolved_at and resolved_by (D3 §5.4)")
        return self

    @model_validator(mode="after")
    def _time_order(self) -> "Conflict":
        """消解时间不得早于检测时间。"""
        if self.resolved_at is not None and self.resolved_at < self.detected_at:
            raise ValueError("resolved_at must be >= detected_at")
        return self