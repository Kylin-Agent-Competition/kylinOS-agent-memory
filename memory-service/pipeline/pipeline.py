"""
pipeline.py — 轨道 A Day6 事件管线编排（架构 6.2 六步串联）

流程：raw dict → 清洗(cleaner) → 敏感识别(sensitive) → 指纹(fingerprint)
     → 质量评分(quality) → 提取门控(Gate)

输出：PipelineResult（清洗事件 + 质量评分 + 是否进入提取 + 审计标记）
低质量事件（eligible_for_extraction=False）只保留最小审计，不进入提取
（架构 6.2 第 6 步）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict

from pipeline.cleaner import EventCleaner
from pipeline.fingerprint import fill_event_fingerprint
from pipeline.quality import QualityScorer
from pipeline.schemas import (
    EventValidationError,
    NormalizedEvent,
    QualityScore,
    _SENSITIVITY_ORDER,
)
from pipeline.sensitive import detect_sensitivity


class PipelineResult(BaseModel):
    """管线输出（清洗 + 评分 + 门控）。"""

    model_config = ConfigDict(extra="forbid")

    event: NormalizedEvent
    quality: QualityScore
    eligible_for_extraction: bool
    sensitivity_updated: bool = False  # 敏感识别是否提升了等级


@dataclass
class EventPipeline:
    """统一事件管线（清洗 → 敏感 → 指纹 → 评分 → 门控）。"""

    cleaner: EventCleaner = field(default_factory=EventCleaner)
    scorer: Optional[QualityScorer] = None

    def process(self, raw: Dict[str, Any]) -> PipelineResult:
        """处理单个 raw 事件。

        Raises:
            EventValidationError: 校验/清洗失败（结构化错误，不吞掉）。
        """
        # 1. 清洗（校验 + 时间/状态标准化）
        event = self.cleaner.clean(raw)

        # 2. 敏感识别（提升等级与标记）
        sensitivity_updated = False
        level, matched = detect_sensitivity(
            (event.content_summary or "") + " " + (event.raw_payload_ref or ""))
        if matched and (_SENSITIVITY_ORDER[level] > _SENSITIVITY_ORDER[event.sensitivity]):
            event = event.model_copy(update={
                "sensitivity": level, "is_sensitive_matched": True})
            sensitivity_updated = True
        elif matched:
            event = event.model_copy(update={"is_sensitive_matched": True})

        # 3. 内容指纹（确定性）
        event = fill_event_fingerprint(event)

        # 4. 质量评分 + 提取门控
        scorer = self.scorer or QualityScorer()
        quality = scorer.score(event)

        return PipelineResult(
            event=event,
            quality=quality,
            eligible_for_extraction=quality.eligible_for_extraction,
            sensitivity_updated=sensitivity_updated,
        )

    def process_many(self, raws: list[Dict[str, Any]]) -> list[PipelineResult]:
        """批量处理（顺序、确定性）。单条失败抛 EventValidationError。"""
        return [self.process(raw) for raw in raws]
