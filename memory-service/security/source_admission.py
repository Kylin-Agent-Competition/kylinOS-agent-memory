"""
source_admission.py — Day6 E 轨多源事件级业务准入策略（抽取前）

标记：D6E_SOURCE_ADMISSION / NOT_EXTRACTION / NOT_PERSISTENCE / NOT_IPC_CONTRACT

职责（任务 day6-e-01-source-quality-admission-policy-v1，方案 PLAN_READY）：
- 在 A 轨 EventPipeline 输出 PipelineResult 之后、Provider 抽取之前，把
  安全红线、用户隔离、质量 Gate 与 Tool 真实业务状态统一转换为可测试的
  ALLOW_EXTRACTION / AUDIT_ONLY / REJECT 三值业务决策，并在事件层就限制
  failed / cancelled / timeout / partial 的抽取范围。
- 只消费现有结构化可信结果：PipelineResult / NormalizedEvent / QualityScore
  （经 PipelineResult 暴露）与可信 ServiceRequestContext；绝不重新计算 A 轨
  六维质量分、来源可靠性权重、敏感识别结果或内容指纹。

复用约束：
- PipelineResult 复用自 pipeline.pipeline；
- NormalizedEvent / SensitivityLevel / SourceBusinessStatus / SourceType
  复用自 pipeline.schemas；
- ServiceRequestContext 复用自 service.contracts；
- 本模块不复制任何既有模型/枚举，不建立与 SecurityDecision / Event /
  Candidate 平行的公共真源；新增类型（SourceAdmissionDecision /
  ExtractionKind / SourceAdmissionResult）仅属于 E 轨 source admission 范围。

安全红线（fail-closed，优先级高于质量 Gate）：
- 用户隔离：ctx.user_id 与 event.user_id 不一致 → REJECT；
- 安全红线：should_ignore / source_business_status=ignored /
  security_gate_triggered / sensitivity=high|critical /
  tool_result 且 payload_security_checked=false → REJECT；
- 生命周期保守：cancelled / timeout → REJECT（未完成事件不得产生成功稳定知识）；
- 非安全质量 Gate：eligible_for_extraction=false 且无安全拒绝 → AUDIT_ONLY
  （保留审计语义，不伪装成安全违规）；
- failed Tool 若质量合格仅允许 failure_experience 路径；partial 若质量合格
  仅允许 preference 路径（不含成功稳定知识，与 A 轨 tool_status_knowledge_policy
  保守 skip 语义一致）。

不读正文红线：本策略只读取 event 的结构化可信字段（user_id / source_type /
source_business_status / sensitivity / should_ignore /
payload_security_checked）与 result.security_gate_triggered /
eligible_for_extraction；绝不读取 content_summary / raw_payload_ref /
turn_id / language_tag 或任何 Candidate / LLM 文本来决定任何决策。
reason_code 取自身固定字符串集合，不拼接任何正文/ID/载荷。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Set

from pydantic import BaseModel, ConfigDict, Field

from pipeline.pipeline import PipelineResult
from pipeline.schemas import (
    NormalizedEvent,
    SensitivityLevel,
    SourceBusinessStatus,
    SourceType,
)
from service.contracts import ServiceRequestContext


class SourceAdmissionDecision(str, Enum):
    """事件级业务准入三值决策（仅属于 E 轨 source admission 语义）。"""

    ALLOW_EXTRACTION = "allow_extraction"
    AUDIT_ONLY = "audit_only"
    REJECT = "reject"


class ExtractionKind(str, Enum):
    """抽取范围限定（source admission 层语义，非 Event/Candidate 新真源）。"""

    PREFERENCE = "preference"
    SUCCESS_KNOWLEDGE = "success_knowledge"
    FAILURE_EXPERIENCE = "failure_experience"


class SourceAdmissionResult(BaseModel):
    """结构化业务准入结果（审计引用仅含结构化 ID，不含正文/载荷）。"""

    model_config = ConfigDict(extra="forbid")

    decision: SourceAdmissionDecision
    reason_code: str  # 固定字符串集合，不含用户原文/密钥/Token/完整敏感载荷
    allowed_extraction_kinds: Set[ExtractionKind] = Field(default_factory=set)  # 仅 ALLOW 时非空
    event_id: Optional[str] = None  # 审计引用（结构化 ID，非正文）
    user_id: Optional[str] = None  # 审计引用（结构化 ID，非正文）


class SourceAdmissionPolicy:
    """E 轨多源业务准入策略入口（无状态、纯函数式、确定性）。

    evaluate() 按 fail-closed 优先级逐段判定，首个命中即返回：
    1. 类型准入（result / ctx 必须是可信类型；result.event 必须是
       NormalizedEvent，fail-closed 前置防御）；
    2. 用户隔离（ctx.user_id 必须等于 event.user_id）；
    3. 安全红线（should_ignore / ignored 状态 / security_gate_triggered /
       high / critical / tool_result 且 payload 未安全检查 → REJECT）；
    4. 生命周期保守（cancelled / timeout → REJECT）；
    5. 非安全质量 Gate（eligible_for_extraction=false → AUDIT_ONLY）；
    6. 业务状态 → 抽取范围（failed 仅 failure_experience；partial 仅
       preference；其余安全合格状态三值全开 → ALLOW_EXTRACTION）。
    """

    def evaluate(
        self, result: PipelineResult, ctx: ServiceRequestContext
    ) -> SourceAdmissionResult:
        # 1. 类型准入（fail-closed 前置；event 必须是可信 NormalizedEvent，
        #    避免被污染结果对象导致属性访问异常或借用正文字段）。
        if not isinstance(result, PipelineResult) or not isinstance(
            result.event, NormalizedEvent
        ):
            return self._reject("invalid_pipeline_result")
        if not isinstance(ctx, ServiceRequestContext):
            return self._reject("invalid_context")

        event = result.event
        audit = {"event_id": event.event_id, "user_id": event.user_id}

        # 2. 用户隔离（D3 §7.1：user_id 为归属隔离键，跨用户 fail-closed）。
        if ctx.user_id != event.user_id:
            return self._reject("user_id_mismatch", **audit)

        # 3. 安全红线（优先于质量 Gate，任一命中即 REJECT）。
        if event.should_ignore:
            return self._reject("event_should_ignore", **audit)
        if event.source_business_status == SourceBusinessStatus.IGNORED:
            return self._reject("event_status_ignored", **audit)
        if result.security_gate_triggered:
            return self._reject("security_gate_triggered", **audit)
        if event.sensitivity == SensitivityLevel.HIGH:
            return self._reject("event_sensitive_high", **audit)
        if event.sensitivity == SensitivityLevel.CRITICAL:
            return self._reject("event_sensitive_critical", **audit)
        if (
            event.source_type == SourceType.TOOL_RESULT
            and not event.payload_security_checked
        ):
            return self._reject("tool_payload_unchecked", **audit)

        # 4. 生命周期保守（未完成/无结论事件不得产生成功稳定知识）。
        if event.source_business_status == SourceBusinessStatus.CANCELLED:
            return self._reject("event_status_cancelled", **audit)
        if event.source_business_status == SourceBusinessStatus.TIMEOUT:
            return self._reject("event_status_timeout", **audit)

        # 5. 非安全质量 Gate：低质量 → AUDIT_ONLY（保留审计语义，
        #    不得伪装成安全违规）。
        if not result.eligible_for_extraction:
            return self._audit_only("quality_not_eligible", **audit)

        # 6. 业务状态 → 抽取范围（仅本策略层限定；不产生成功稳定知识之外的语义）。
        if event.source_business_status == SourceBusinessStatus.FAILED:
            # failed Tool：质量合格仅允许 failure_experience；
            # 不得获得 preference 或成功知识语义。
            return self._allow(
                "ok_failed_tool_failure_experience_only",
                {ExtractionKind.FAILURE_EXPERIENCE},
                **audit,
            )
        if event.source_business_status == SourceBusinessStatus.PARTIAL:
            # partial：保守语义，仅允许 preference（不含成功稳定知识，
            # 与 A 轨 tool_status_knowledge_policy("partial")="skip" 一致）。
            return self._allow(
                "ok_partial_preference_only",
                {ExtractionKind.PREFERENCE},
                **audit,
            )
        # 其余安全合格状态（success / completed / raw 等）三值全开。
        return self._allow(
            "ok",
            {
                ExtractionKind.PREFERENCE,
                ExtractionKind.SUCCESS_KNOWLEDGE,
                ExtractionKind.FAILURE_EXPERIENCE,
            },
            **audit,
        )

    @staticmethod
    def _reject(reason_code: str, **audit) -> SourceAdmissionResult:
        """构造 REJECT 结果（allowed_extraction_kinds 保持空集）。"""
        return SourceAdmissionResult(
            decision=SourceAdmissionDecision.REJECT,
            reason_code=reason_code,
            **audit,
        )

    @staticmethod
    def _audit_only(reason_code: str, **audit) -> SourceAdmissionResult:
        """构造 AUDIT_ONLY 结果（保留审计语义，非安全拒绝）。"""
        return SourceAdmissionResult(
            decision=SourceAdmissionDecision.AUDIT_ONLY,
            reason_code=reason_code,
            **audit,
        )

    @staticmethod
    def _allow(
        reason_code: str,
        kinds: Set[ExtractionKind],
        **audit,
    ) -> SourceAdmissionResult:
        """构造 ALLOW_EXTRACTION 结果（allowed_extraction_kinds 非空）。"""
        return SourceAdmissionResult(
            decision=SourceAdmissionDecision.ALLOW_EXTRACTION,
            reason_code=reason_code,
            allowed_extraction_kinds=kinds,
            **audit,
        )


__all__ = [
    "SourceAdmissionPolicy",
    "SourceAdmissionResult",
    "SourceAdmissionDecision",
    "ExtractionKind",
]