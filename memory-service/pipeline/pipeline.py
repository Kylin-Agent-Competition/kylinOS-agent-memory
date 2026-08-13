"""
pipeline.py — 轨道 A Day6 事件管线编排（架构 6.2 六步串联）

流程：raw dict → 清洗(cleaner) → 敏感识别(sensitive) → 指纹(fingerprint)
     → 质量评分(quality) → 提取门控(Gate)

安全 Gate（R2 修复，Reviewer BLOCKED）：
- 命中 high/critical 敏感 → fail-close：
    should_ignore=true + source_business_status=ignored + eligible_for_extraction=false
  （D3 安全契约 §7.7：命中 S-01..S-04/S-08 的 Turn 必须 should_ignore=true +
   source_business_status=ignored，不得进入后续抽取与存储）
- 安全 Gate 优先于 Quality Gate：即使质量分高，敏感事件也不得重新放行。
- ignored 事件只保留最小审计（event 仍返回供审计/脱敏处理），不进入 Extraction。

输出：PipelineResult（清洗事件 + 质量评分 + 门控结果 + 安全 Gate 标记）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict

from pipeline.cleaner import EventCleaner
from pipeline.fingerprint import fill_event_fingerprint
from pipeline.quality import QualityScorer
from pipeline.schemas import (
    EventValidationError,
    NormalizedEvent,
    ProcessingStatus,
    QualityScore,
    SensitivityLevel,
    SourceBusinessStatus,
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
    security_gate_triggered: bool = False  # R2: 安全 Gate 是否 fail-close 拦截


@dataclass
class EventPipeline:
    """统一事件管线（清洗 → 敏感 → 指纹 → 评分 → 安全 Gate → 质量 Gate）。"""

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

        # 4. 质量评分（六维 + overall）
        scorer = self.scorer or QualityScorer()
        quality = scorer.score(event)

        # 5. 安全 Gate（R2：优先于质量 Gate，fail-close）
        #    high/critical 敏感事件（或输入已标 should_ignore）→ 强制 ignored，
        #    不得进入 Extraction / Storage / Vector / MemoryContext 路径。
        security_gate_triggered = False
        if (event.sensitivity in (SensitivityLevel.HIGH, SensitivityLevel.CRITICAL)
                or event.should_ignore):
            security_gate_triggered = True
            event = event.model_copy(update={
                "should_ignore": True,
                "source_business_status": SourceBusinessStatus.IGNORED,
                "processing_status": ProcessingStatus.REJECTED,
                "requires_embedding": False,  # 不生成向量
            })
            quality = quality.model_copy(update={
                "eligible_for_extraction": False,  # 安全 Gate 覆盖质量 Gate
            })

        # 6. 提取门控（质量 Gate：低质量事件不进入提取；安全 Gate 已拦截时保持 false）
        eligible = quality.eligible_for_extraction

        return PipelineResult(
            event=event,
            quality=quality,
            eligible_for_extraction=eligible,
            sensitivity_updated=sensitivity_updated,
            security_gate_triggered=security_gate_triggered,
        )

    def process_many(self, raws: list[Dict[str, Any]]) -> list[PipelineResult]:
        """批量处理（顺序、确定性）。单条失败抛 EventValidationError。"""
        return [self.process(raw) for raw in raws]
