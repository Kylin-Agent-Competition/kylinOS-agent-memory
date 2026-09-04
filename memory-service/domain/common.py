"""
common.py — Day4 E 轨业务 Domain 公共值对象/约束类型

只承载为 Preference / Knowledge / Conflict / ForgetPlan 四个核心业务对象服务的
公共约束类型，不承载流水线/Provider 共享类型（后者见 pipeline.schemas 与
providers.extraction_provider）。

对齐来源：
- D3_MEMORY_BUSINESS_CONTRACT_V1.md §5.2-§5.5（confidence_score 等边界语义）
- D3_MEMORY_SECURITY_ACCEPTANCE_V1.md（时间统一 aware UTC；敏感/隔离红线不在此层实现）
- MEMORY_BUSINESS_SCHEMA_V0.1.md §3（字段来源补充）

约束：
- ConfidenceScore：strict float，禁止 bool/str 自动转换（对齐
  providers/extraction_provider.py PreferenceCandidate.confidence 的 HIGH-03 模式）；
  边界 [0.0, 1.0]。
- NonEmptyStr：至少 1 个字符，拒绝空串与纯空白（空格/Tab/换行等）非法输入
  制造成合法业务对象；含有效字符的原值原样保留，不做 strip。
- AwareDatetime：时间统一为 aware UTC（缺失 tzinfo 补 UTC，再统一转 UTC）。
- NonEmptyIdList：至少 1 个元素，且每个元素为非空字符串。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, List

from pydantic import AfterValidator, Field


def _ensure_aware_utc(value: datetime) -> datetime:
    """时间统一为 aware UTC：tzinfo 缺失时补 UTC，再统一转换。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ensure_non_blank(value: str) -> str:
    """拒绝空串与纯空白输入（TD-013）：strip 后为空即拒绝，否则原样返回。

    只做空白判定，不修改原值——带首尾空格但含有效字符的输入必须逐字保留。
    """
    if not value.strip():
        raise ValueError("string must not be empty or whitespace only")
    return value


ConfidenceScore = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]
"""置信度评分：strict float（拒绝 bool/str 自动转换），边界 [0.0, 1.0]。"""

NonEmptyStr = Annotated[str, Field(min_length=1), AfterValidator(_ensure_non_blank)]
"""非空字符串：min_length=1 拒绝空串，AfterValidator 拒绝纯空白；原值不 strip。"""

AwareDatetime = Annotated[datetime, AfterValidator(_ensure_aware_utc)]
"""aware UTC 时间：Pydantic 解析后再统一为 aware UTC。"""

NonEmptyIdList = Annotated[List[NonEmptyStr], Field(min_length=1)]
"""非空 ID 列表：至少 1 个元素，且每个元素为非空字符串。"""