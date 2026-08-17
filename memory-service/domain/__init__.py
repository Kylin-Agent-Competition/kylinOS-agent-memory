"""
domain 包 — Day4 E 轨业务 Domain Schema 骨架

承载 E 轨四个核心业务对象的 Pydantic v2 模型及其直接服务的公共枚举：
- Preference / Knowledge / Conflict / ForgetPlan

导入契约：
- 四个模型与公共枚举可从 `domain` 包稳定导入。
- 明确不导出（也不在包内重复定义）：MemorySourceEvent / NormalizedEvent /
  PreferenceCandidate / KnowledgeCandidate —— 这些共享类型分别属于
  memory-service/pipeline/schemas.py 与 memory-service/providers/extraction_provider.py。
- MemoryType 复用自 pipeline.schemas（见 domain.knowledge），不在本包重复定义。

本包只承载 Schema 骨架：不实现服务逻辑、存储、抽取、检索、冲突算法或遗忘执行。
"""

from __future__ import annotations

from .enums import (
    ConflictType,
    ExpressionType,
    ForgetMode,
    ForgetPlanStatus,
    KnowledgeType,
    MemoryStatus,
    PreferenceScope,
    ResolutionStatus,
    TargetType,
)
from .conflict import Conflict
from .forgetting import ForgetPlan
from .knowledge import Knowledge
from .preference import Preference

__all__ = [
    # 四个核心业务对象
    "Preference",
    "Knowledge",
    "Conflict",
    "ForgetPlan",
    # 公共枚举（9 组，D3 §5.6 FROZEN）
    "ExpressionType",
    "PreferenceScope",
    "KnowledgeType",
    "MemoryStatus",
    "ConflictType",
    "ResolutionStatus",
    "ForgetMode",
    "ForgetPlanStatus",
    "TargetType",
]