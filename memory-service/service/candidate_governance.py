"""
candidate_governance.py — Day5 E 轨 Candidate 业务准入与 Domain 转换服务

标记：D5E_CANDIDATE_GOVERNANCE / NOT_PERSISTENCE / NOT_EXTRACTION

职责（任务 day5-e-01-candidate-domain-governance-v1 与
day5-e-02-event-candidate-admission-gate-v1，方案 PLAN_READY）：
- 复用 A 轨 providers.extraction_provider.PreferenceCandidate / KnowledgeCandidate
  （只读消费，不复制、不重定义任何 Candidate 模型）；
- 通过唯一公开准入入口 admit_with_event() 在 Candidate 进入正式 E 轨 Domain 前，
  基于 pipeline.schemas.MemorySourceEvent / SourceBusinessStatus / SensitivityLevel
  实施事件级 fail-closed 准入（provenance 一致性、用户归属一致性、
  安全标记与业务状态），拒绝后返回结构化可测试 reason；
- 内部 _admit() 仅在事件门禁成功后由本服务调用，不作为公开兼容 API
  （PR #47 High 旁路关闭：不再提供可绕过事件 Gate 的 public admit() 生产入口）；
- 构造 E 轨正式业务 Domain（domain.Preference / domain.Knowledge），
  不建立平行业务 Schema、不新建平行 Event Schema。

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
from pipeline.schemas import (
    MemorySourceEvent,
    MemoryType,
    SensitivityLevel,
    SourceBusinessStatus,
)
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
    - invalid_event               event 不是 MemorySourceEvent（fail-closed 前置）
    - source_event_id_mismatch    candidate.source_event_id 与 event.event_id 不一致
    - user_id_mismatch            ctx.user_id 与 event.user_id 不一致（跨用户）
    - event_should_ignore         event.should_ignore=true（D3 安全契约拒绝）
    - event_status_ignored        source_business_status=ignored（防御纵深）
    - event_sensitive_blocked     event.sensitivity=high/critical（上游安全标记拒绝）
    - event_status_cancelled      source_business_status=cancelled（未完成事件）
    - event_status_timeout        source_business_status=timeout（未完成事件）
    - failed_event_success_knowledge_forbidden  failed 事件不得形成成功知识
    - failed_event_preference_blocked          failed 事件不得形成稳定偏好记忆
    - missing_knowledge_memory_type  Knowledge 转换未显式提供 memory_type
                                       （不再隐式默认 SHORT_TERM，PR #47）
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

    def _admit(
        self,
        candidate: Union[PreferenceCandidate, KnowledgeCandidate],
        ctx: ServiceRequestContext,
        *,
        entity_id: str,
        now: Optional[datetime] = None,
        memory_type: Optional[MemoryType] = None,
    ) -> Union[Preference, Knowledge]:
        """内部准入校验并按 Candidate 类型分派构造正式 Domain。

        仅由 admit_with_event() 在事件级 fail-closed 门禁成功后调用，
        不作为公开兼容 API（PR #47 High 旁路关闭：无事件转换必须不可达）。

        Args:
            candidate: A 轨抽取候选（PreferenceCandidate / KnowledgeCandidate）。
            ctx: 可信业务上下文；user_id 只能来自此上下文，禁止从候选正文推导。
            entity_id: 新 Domain 的实体 ID（调用方提供；治理层不生成、不写库）。
            now: 构造时间戳；None → datetime.now(timezone.utc)，结果 aware UTC。
            memory_type: Knowledge 的记忆分层（业务分类，非用户身份）。不再
                隐式默认 SHORT_TERM：KnowledgeCandidate 路径必须由调用方显式
                提供，缺失时拒绝（missing_knowledge_memory_type）；Preference
                路径不使用该参数，None 无影响。

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
        # 5. Knowledge memory_type 必须显式提供（不隐式默认 SHORT_TERM，PR #47）。
        #    结构化准入要求，非 Domain 构造错误，置于 try 块之外，不被
        #    except ValidationError 捕获。
        if isinstance(candidate, KnowledgeCandidate) and memory_type is None:
            raise CandidateAdmissionError(
                "missing_knowledge_memory_type",
                "Knowledge conversion requires explicit memory_type",
            )
        try:
            if isinstance(candidate, PreferenceCandidate):
                return self._build_preference(candidate, ctx, entity_id, ts)
            return self._build_knowledge(candidate, ctx, entity_id, ts, memory_type)
        except ValidationError as exc:
            # 6. Domain 构造校验失败 → 包装为 domain_construction_failed（保留原因）
            raise CandidateAdmissionError(
                "domain_construction_failed",
                "candidate failed Domain construction validation",
                cause=exc,
            ) from exc

    def admit_with_event(
        self,
        candidate: Union[PreferenceCandidate, KnowledgeCandidate],
        event: MemorySourceEvent,
        ctx: ServiceRequestContext,
        *,
        entity_id: str,
        now: Optional[datetime] = None,
        memory_type: Optional[MemoryType] = None,
    ) -> Union[Preference, Knowledge]:
        """事件级 fail-closed 准入门禁 + Domain 构造（Day5-e-02）。

        在 Candidate 进入正式 E 轨 Domain 前，基于 MemorySourceEvent、
        Candidate provenance、安全标记和业务状态实施 fail-closed 准入校验。
        所有检查通过后委托内部 _admit() 完成 Domain 构造（不提供可绕过
        事件 Gate 的公开 admit() 入口——PR #47 High 旁路关闭）。

        治理层只读消费 event.source_business_status / event.should_ignore /
        event.sensitivity 作为真实状态来源，不依据 candidate 正文 / evidence /
        fact / assistant_text / LLM 声明覆盖真实 Tool/Event 状态。

        Args:
            candidate: A 轨抽取候选（PreferenceCandidate / KnowledgeCandidate）。
            event: 来源 MemorySourceEvent（真实状态与安全标记的唯一来源；
                禁止以 LLM 声明或候选正文覆盖）。
            ctx: 可信业务上下文；user_id 只能来自此上下文，且须与 event.user_id
                一致（跨用户候选 fail-closed 拒绝）。
            entity_id: 新 Domain 的实体 ID（调用方提供；治理层不生成、不写库）。
            now: 构造时间戳；None → datetime.now(timezone.utc)，结果 aware UTC。
            memory_type: Knowledge 的记忆分层（业务分类，非用户身份）。不再
                隐式默认 SHORT_TERM：KnowledgeCandidate 路径必须显式提供，
                缺失时拒绝（missing_knowledge_memory_type）；Preference 路径
                不使用该参数，None 无影响。

        Raises:
            CandidateAdmissionError: 准入失败（code 见类 docstring）。
        """
        # 1. event 类型准入（fail-closed 前置：真实状态来源必须可信）
        if not isinstance(event, MemorySourceEvent):
            raise CandidateAdmissionError(
                "invalid_event",
                "event must be a MemorySourceEvent",
            )
        # 2. Candidate 类型准入（复用 _admit() 防御语义；前置避免后续属性访问异常）
        if not isinstance(candidate, (PreferenceCandidate, KnowledgeCandidate)):
            raise CandidateAdmissionError(
                "invalid_candidate_type",
                "candidate must be a PreferenceCandidate or KnowledgeCandidate",
            )
        # 3. 可信上下文准入（复用 _admit() 防御语义）
        if not isinstance(ctx, ServiceRequestContext):
            raise CandidateAdmissionError(
                "invalid_context",
                "ctx must be a trusted ServiceRequestContext",
            )
        # 4-11. 事件级真实性/安全/业务状态校验（首个失败即拒绝，fail-closed）
        self._validate_event_admission(candidate, event, ctx)
        # 门禁通过：委托内部 _admit() 复用 entity_id 校验 + candidate 状态防御
        # + Knowledge memory_type 显式要求 + Domain 构造
        return self._admit(
            candidate, ctx, entity_id=entity_id, now=now, memory_type=memory_type
        )

    def _validate_event_admission(
        self,
        candidate: Union[PreferenceCandidate, KnowledgeCandidate],
        event: MemorySourceEvent,
        ctx: ServiceRequestContext,
    ) -> None:
        """事件级 fail-closed 准入检查（前置：candidate/event/ctx 类型已校验）。

        检查顺序（首个失败即拒绝）：
        1. candidate.source_event_id 与 event.event_id 一致性（来源证据一致）；
        2. ctx.user_id 与 event.user_id 一致性（用户归属一致）；
        3. event.should_ignore=true 拒绝（D3 安全契约标记）；
        4. source_business_status=ignored 拒绝（防御纵深：即便 Schema 条件校验
           被 model_construct/DB 载入绕过，状态本身仍拦截）；
        5. sensitivity=high/critical 拒绝（上游安全 Gate 标记，治理层不得重新放行）；
        6. source_business_status=cancelled 拒绝（未完成事件，无结论）；
        7. source_business_status=timeout 拒绝（未完成事件）。
        8. source_business_status=failed：仅允许 KnowledgeCandidate 且
           category=failure_experience 按真实失败语义保留；其余 Knowledge（成功
           知识语义）与 Preference 一律拒绝（failed 事件不得形成稳定成功知识）。
        """
        if candidate.source_event_id != event.event_id:
            raise CandidateAdmissionError(
                "source_event_id_mismatch",
                "candidate.source_event_id must equal event.event_id",
            )
        if ctx.user_id != event.user_id:
            raise CandidateAdmissionError(
                "user_id_mismatch",
                "ctx.user_id must equal event.user_id",
            )
        if event.should_ignore:
            raise CandidateAdmissionError(
                "event_should_ignore",
                "event.should_ignore=true rejected by admission gate",
            )
        if event.source_business_status == SourceBusinessStatus.IGNORED:
            raise CandidateAdmissionError(
                "event_status_ignored",
                "source_business_status=ignored rejected by admission gate",
            )
        if event.sensitivity in (SensitivityLevel.HIGH, SensitivityLevel.CRITICAL):
            raise CandidateAdmissionError(
                "event_sensitive_blocked",
                "event.sensitivity high/critical rejected by admission gate",
            )
        if event.source_business_status == SourceBusinessStatus.CANCELLED:
            raise CandidateAdmissionError(
                "event_status_cancelled",
                "source_business_status=cancelled rejected by admission gate",
            )
        if event.source_business_status == SourceBusinessStatus.TIMEOUT:
            raise CandidateAdmissionError(
                "event_status_timeout",
                "source_business_status=timeout rejected by admission gate",
            )
        if event.source_business_status == SourceBusinessStatus.FAILED:
            # failed 事件不得形成成功知识；A 轨已明确形成的 failure_experience
            # 候选按其真实失败语义保留（不改写为成功知识）。
            if isinstance(candidate, KnowledgeCandidate):
                if candidate.category != "failure_experience":
                    raise CandidateAdmissionError(
                        "failed_event_success_knowledge_forbidden",
                        "failed event cannot form success knowledge "
                        "(only failure_experience allowed)",
                    )
                return
            # fail-closed：failed 事件不得形成稳定偏好记忆（任务约束，不放宽）
            raise CandidateAdmissionError(
                "failed_event_preference_blocked",
                "failed event cannot form stable preference memory",
            )

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
        - 结构化承载缺口（TD-017，Medium/Open）如实声明：KnowledgeCandidate 六类
          扩展结构字段（conditions / evidence / steps / expected_result / problem /
          outcome / reproducible / template_body / parameters / priority /
          failure_reason / avoid_condition / alternative，共 13 个 Optional[str]）
          当前尚未无损进入 Domain——content_summary 仅承载 fact 文本、
          primary_category 为开放分类标签，不得宣称已完整保留结构化语义；
          正式结构化承载契约（字段级映射或 content_ref 存储形态）待 D 设计
          （Domain content_ref DEFERRED）。
        """
        return Knowledge(
            knowledge_id=entity_id,
            user_id=ctx.user_id,
            knowledge_type=KnowledgeType(candidate.category),  # 六值同源
            memory_type=memory_type,  # 业务分类；由调用方显式提供（PR #47 不再隐式默认）
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