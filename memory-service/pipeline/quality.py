"""
quality.py — 轨道 A Day6 质量评分（架构 6.2 第 5-6 步）

六维评分（0.0–1.0）：
- completeness  完整性：必填/条件字段是否齐全
- validity      有效性：字段值是否符合枚举/格式约束
- reliability   可靠性：来源可信度基线（架构 6.3，TABLE 19 语义）
- freshness     新鲜度：occurred_at 距 now 的时效（指数衰减，半衰期 7 天）
- consistency   一致性：内部字段交叉一致（event_type/source_type 组合）
- extractability 可提取性：是否有可抽取的结构化载荷

Gate 判定（第 6 步）：低质量事件不进入提取——overall 低于阈值时
eligible_for_extraction=False，只保留最小审计，不生成长期记忆。
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone

from pipeline.schemas import (
    EventType,
    NormalizedEvent,
    QualityScore,
    SensitivityLevel,
    SourceType,
    _SOURCE_RELIABILITY,
)

# 进入提取的 overall 阈值（架构不硬编码，作为可调参数；默认 0.5）
DEFAULT_EXTRACTION_THRESHOLD = 0.5
# 可靠性下限：低于此可信度的来源不进入提取（架构 6.3 低可信基线）
MIN_RELIABILITY = 0.4
# 新鲜度半衰期（秒，7 天）
FRESHNESS_HALF_LIFE = 7 * 24 * 3600

# event_type/source_type 合法组合（一致性维度）
_VALID_TYPE_COMBOS = {
    (SourceType.CHAT, EventType.USER_MESSAGE),
    (SourceType.CHAT, EventType.AGENT_RESPONSE),
    (SourceType.TOOL_RESULT, EventType.AGENT_RESPONSE),
    (SourceType.MANUAL_CONFIG, EventType.SYSTEM_MESSAGE),
    (SourceType.RECOLLECT, EventType.SYSTEM_MESSAGE),
    (SourceType.FILE, EventType.SYSTEM_MESSAGE),
    (SourceType.MEETING, EventType.SYSTEM_MESSAGE),
    (SourceType.VOICE, EventType.SYSTEM_MESSAGE),
}


class QualityScorer:
    """六维质量评分器。纯函数式（不持状态），同一事件评分确定。"""

    def __init__(self, extraction_threshold: float = DEFAULT_EXTRACTION_THRESHOLD,
                 now: Optional[datetime] = None) -> None:
        self._threshold = extraction_threshold
        self._now = now  # 测试可注入固定时间，保证确定性

    def score(self, event: NormalizedEvent) -> QualityScore:
        completeness = self._completeness(event)
        validity = self._validity(event)
        reliability = self._reliability(event)
        freshness = self._freshness(event)
        consistency = self._consistency(event)
        extractability = self._extractability(event)

        # overall：加权平均（各维权重：完整/有效/可靠 较高，新鲜/一致 中，可提取 中）
        weights = {
            "completeness": 0.25,
            "validity": 0.20,
            "reliability": 0.20,
            "freshness": 0.10,
            "consistency": 0.10,
            "extractability": 0.15,
        }
        overall = (
            completeness * weights["completeness"]
            + validity * weights["validity"]
            + reliability * weights["reliability"]
            + freshness * weights["freshness"]
            + consistency * weights["consistency"]
            + extractability * weights["extractability"]
        )
        # 提取门控（架构 6.2 第 6 步）：
        # 1. overall 达阈值（默认 0.5）
        # 2. 可靠性下限：低可信来源（如 recollect 0.3）即使其他维度高也不进入提取
        eligible = overall >= self._threshold and reliability >= MIN_RELIABILITY

        return QualityScore(
            completeness=round(completeness, 4),
            validity=round(validity, 4),
            reliability=round(reliability, 4),
            freshness=round(freshness, 4),
            consistency=round(consistency, 4),
            extractability=round(extractability, 4),
            overall=round(overall, 4),
            eligible_for_extraction=eligible,
        )

    # ── 各维度 ──

    @staticmethod
    def _completeness(event: NormalizedEvent) -> float:
        """完整性：必填字段齐全 = 1.0；缺失可选关键字段扣分。"""
        score = 1.0
        # 必填（E 轨 Schema required）
        for f in ("event_id", "user_id", "actor_id", "source_type", "event_type",
                  "idempotency_key", "occurred_at", "captured_at", "session_id"):
            if getattr(event, f) in (None, ""):
                return 0.0
        # 条件字段：tool_result 必须带 tool_call_id；chat 建议带 turn_id
        if event.source_type == SourceType.TOOL_RESULT and not event.tool_call_id:
            score -= 0.3
        if event.event_type in (EventType.USER_MESSAGE, EventType.AGENT_RESPONSE) \
                and not event.turn_id:
            score -= 0.1
        # 建议字段
        if not event.content_summary and not event.raw_payload_ref:
            score -= 0.2
        return max(0.0, min(1.0, score))

    @staticmethod
    def _validity(event: NormalizedEvent) -> float:
        """有效性：字段值格式/枚举合法。Pydantic 已保证枚举合法，检查交叉/范围。"""
        score = 1.0
        if event.occurred_at > event.captured_at:
            # occurred_at 晚于 captured_at：时序异常，扣分
            score -= 0.4
        if event.sensitivity == SensitivityLevel.CRITICAL:
            # critical 敏感事件整体有效性受限（进入提取前需人工/规则复核）
            score -= 0.2
        return max(0.0, min(1.0, score))

    @staticmethod
    def _reliability(event: NormalizedEvent) -> float:
        """可靠性：来源可信度基线（架构 6.3）。"""
        base = _SOURCE_RELIABILITY.get(event.source_type.value, 0.5)
        # Tool 失败/取消降可信度（失败知识不沉淀为成功知识，架构 8 章）
        if event.source_type == SourceType.TOOL_RESULT:
            if event.source_business_status.value in ("failed", "cancelled", "timeout"):
                base *= 0.5
        return max(0.0, min(1.0, base))

    def _freshness(self, event: NormalizedEvent) -> float:
        """新鲜度：半衰期指数衰减 exp(-ln2 * dt / half_life)（M1 修正）。

        标准半衰期语义：经过一个半衰期（7 天）freshness = 0.5。
        """
        now = self._now or datetime.now(timezone.utc)
        occurred = event.occurred_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        dt = max(0.0, (now - occurred).total_seconds())
        return math.exp(-math.log(2) * dt / FRESHNESS_HALF_LIFE)

    @staticmethod
    def _consistency(event: NormalizedEvent) -> float:
        """一致性：event_type/source_type 组合是否合法。"""
        combo = (event.source_type, event.event_type)
        if combo in _VALID_TYPE_COMBOS:
            return 1.0
        return 0.4  # 非标准组合：可疑，扣分但允许（待 E 轨 Schema 收紧）

    @staticmethod
    def _extractability(event: NormalizedEvent) -> float:
        """可提取性：有可抽取结构化载荷 = 1.0；仅摘要 = 0.6；空 = 0.2。"""
        if event.has_structured_payload:
            return 1.0
        if event.content_summary or event.raw_payload_ref:
            return 0.6
        return 0.2
