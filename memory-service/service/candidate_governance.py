"""
candidate_governance.py — Day5 E 轨最小 Candidate 业务准入与 Domain 转换服务

标记：D5E_CANDIDATE_GOVERNANCE / NOT_PERSISTENCE / NOT_EXTRACTION

职责（任务 day5-e-01-candidate-domain-governance-v1，方案 PLAN_READY）：
- 复用 A 轨 providers.extraction_provider.PreferenceCandidate / KnowledgeCandidate
  （只读消费，不复制、不重定义任何 Candidate 模型）；
- 通过单一准入入口 admit() 对 Candidate 执行最小业务准入校验；
- 构造 E 轨正式业务 Domain（domain.Preference / domain.Knowledge），
  不建立平行业务 Schema。

本服务明确不做（NOT_EXTRACTION / NOT_PERSISTENCE）：
- 不实现抽取算法（抽取属 A 轨 providers）；
- 不写数据库、不定义 Repository / UoW / Outbox / Vector / FTS5 / RRF；
- 不做冲突消解、遗忘执行、检索；
- 不生成/覆盖 source_event_id（R3：作为已有可信 provenance 只读消费）；
- 不从 Candidate 正文 / LLM 输出 / 默认常量推导 user_id（必须来自
  ServiceRequestContext）；
- 不接受外部传入 target_memory_status（API 无此参数，物理隔绝无依据可信升级）。

生命周期边界（B2 保持）：
- 转换结果 memory_status 恒为 MemoryStatus.CANDIDATE，不无依据提升为
  active / verified 等正式可信状态；
- 临时偏好 / should_persist=false 偏好仍可构造为 candidate Domain，
  但不形成 active 稳定长期状态（由 Domain._temporary_boundary 校验器
  与治理层恒置 candidate 共同保证）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Union

from pydantic import ValidationError

from domain import Knowledge, Preference
from domain.enums import ExpressionType, KnowledgeType, MemoryStatus, PreferenceScope
from pipeline.schemas import MemoryType
from providers.extraction_provider import KnowledgeCandidate, PreferenceCandidate
from service.contracts import ServiceRequestContext


class CandidateAdmissionError(Exception):
    """Candidate 业务准入失败（结构化错误码，消息不携带候选正文原文）。

    code 取值：
    - invalid_candidate_type      候选不是 PreferenceCandidate/KnowledgeCandidate
    - invalid_context             ctx 不是可信 ServiceRequestContext
    - empty_entity_id             entity_id 缺失/非 str/纯空白
    - candidate_status_violation  memory_status 非 candidate（B2 防御）
    - domain_construction_failed  Domain 构造校验失败（保留 __cause__）
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        # cause 作为普通属性保留；raise ... from exc 时 __cause__ 由解释器设置
        self.cause = cause

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class CandidateGovernanceService:
    """单一 Candidate 业务准入与 Domain 转换入口（Day5 最小治理）。

    不持有状态（stateless）；不实现抽取、存储、冲突、遗忘或检索逻辑。
    """

    def admit(
        self,
        candidate: Union[PreferenceCandidate, KnowledgeCandidate],
        ctx: ServiceRequestContext,
        *,
        entity_id: str,
        now: Optional[datetime] = None,
        memory_type: MemoryType = MemoryType.SHORT_TERM,
    ) -> Union[Preference, Knowledge]:
        """准入校验并按 Candidate 类型分派构造正式 Domain。

        Args:
            candidate: A 轨抽取候选（PreferenceCandidate / KnowledgeCandidate）。
            ctx: 可信业务上下文；user_id 只能来自此上下文，禁止从候选正文推导。
            entity_id: 新 Domain 的实体 ID（调用方提供；治理层不生成、不写库）。
            now: 构造时间戳；None → datetime.now(timezone.utc)，结果 aware UTC。
            memory_type: Knowledge 的记忆分层（业务分类，非用户身份；默认
                SHORT_TERM 为"不无依据提升"的最保守选择，可由调用方覆盖）。

        Raises:
            CandidateAdmissionError: 准入失败（code 见类 docstring）。
        """
        # 1. Candidate 类型准入（单一入口按类型分派的前提）
        if not isinstance(candidate, (PreferenceCandidate, KnowledgeCandidate)):
            raise CandidateAdmissionError(
                "invalid_candidate_type",
                "candidate must be a PreferenceCandidate or KnowledgeCandidate",
            )
        # 2. 可信上下文准入（user_id 来源边界）
        if not isinstance(ctx, ServiceRequestContext):
            raise CandidateAdmissionError(
                "invalid_context",
                "ctx must be a trusted ServiceRequestContext",
            )
        # 3. entity_id 准入（比 Domain NonEmptyStr 更严：拒绝纯空白）
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise CandidateAdmissionError(
                "empty_entity_id",
                "entity_id must be a non-blank string",
            )
        # 4. candidate 生命周期状态准入（B2 防御：模型层 Literal["candidate"]
        #    已强制，此处防御 model_construct / DB 载入 / 未来漂移导致的污染对象）
        if candidate.memory_status != "candidate":
            raise CandidateAdmissionError(
                "candidate_status_violation",
                "candidate.memory_status must be 'candidate' (B2)",
            )

        ts = now if now is not None else datetime.now(timezone.utc)
        try:
            if isinstance(candidate, PreferenceCandidate):
                return self._build_preference(candidate, ctx, entity_id, ts)
            return self._build_knowledge(candidate, ctx, entity_id, ts, memory_type)
        except ValidationError as exc:
            # 5. Domain 构造校验失败 → 包装为 domain_construction_failed（保留原因）
            raise CandidateAdmissionError(
                "domain_construction_failed",
                "candidate failed Domain construction validation",
                cause=exc,
            ) from exc

    def _build_preference(
        self,
        candidate: PreferenceCandidate,
        ctx: ServiceRequestContext,
        entity_id: str,
        ts: datetime,
    ) -> Preference:
        """PreferenceCandidate → Preference（字段映射见任务方案）。

        - user_id 来自 ctx（禁止从候选正文/LLM/默认常量推导）；
        - source_event_id 作为可信 provenance 进入 evidence_event_ids，
          不重新生成、不被候选模型覆盖；
        - memory_status 恒 candidate，is_active=False，requires_confirmation=True
          （候选需确认后方可提升）；
        - candidate.evidence 文本 / category 为抽取侧细节，不映射进 Domain
          （Domain 仅以 evidence_event_ids 引用事件）。
        """
        return Preference(
            preference_id=entity_id,
            user_id=ctx.user_id,
            expression_type=ExpressionType(candidate.explicitness),  # C-01 归一
            preference_scope=PreferenceScope(candidate.scope),  # 五值同源
            preference_key=candidate.key,
            preference_value=candidate.value,
            confidence_score=candidate.confidence,  # 数值含义不变（strict [0,1]）
            memory_status=MemoryStatus.CANDIDATE,  # 恒 candidate，不无依据提升
            is_active=False,  # 候选未激活
            is_temporary=candidate.is_temporary,
            should_persist=candidate.should_persist,
            should_decay=False,  # 过渡字段，未配置衰减
            evidence_event_ids=[candidate.source_event_id],  # R3 可信 provenance
            version=1,  # 新候选首版
            previous_version_id=None,  # v1 无前版
            created_at=ts,
            updated_at=ts,
            requires_confirmation=True,  # 候选需确认后方可提升
        )

    def _build_knowledge(
        self,
        candidate: KnowledgeCandidate,
        ctx: ServiceRequestContext,
        entity_id: str,
        ts: datetime,
        memory_type: MemoryType,
    ) -> Knowledge:
        """KnowledgeCandidate → Knowledge（字段映射见任务方案）。

        - source_event_id 直接相等，不重新生成/覆盖（R3）；
        - user_id 来自 ctx（可信归属）；
        - memory_status 恒 candidate，requires_embedding=True（候选将来需嵌入）；
        - candidate.conditions / evidence(文本) / 六类结构化字段为抽取侧细节，
          不映射进 Domain（Domain content_ref 待 D 设计存储）。
        """
        return Knowledge(
            knowledge_id=entity_id,
            user_id=ctx.user_id,
            knowledge_type=KnowledgeType(candidate.category),  # 六值同源
            memory_type=memory_type,  # 业务分类；默认 SHORT_TERM（不无依据提升）
            memory_status=MemoryStatus.CANDIDATE,  # 恒 candidate
            source_event_id=candidate.source_event_id,  # 直接相等（R3）
            content_summary=candidate.fact,  # 可检索摘要
            confidence_score=candidate.confidence,  # 数值含义不变
            requires_embedding=True,  # 候选将来需要嵌入
            is_outdated=False,  # 过渡字段
            created_at=ts,
            updated_at=ts,
        )


__all__ = ["CandidateGovernanceService", "CandidateAdmissionError"]