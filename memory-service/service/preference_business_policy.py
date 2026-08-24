"""
preference_business_policy.py — Day7E 偏好长期化业务决策策略（E 轨 service 内部）

标记：D7E_PREFERENCE_BUSINESS_POLICY / NOT_EXTRACTION / NOT_PERSISTENCE
      / NOT_IPC_CONTRACT

职责（任务 day7-e-01-preference-business-policy-v1，方案 PLAN_READY）：
- 在 Candidate 已通过 Day5 Candidate Governance 准入与 Day6 Source Admission
  安全门禁之后，基于 PreferenceCandidate 的**结构化字段**判定该偏好候选是否
  可以作为长期偏好候选（memory_status=candidate，非 active）保留；
- 明确 category / scope / confidence / explicitness / is_temporary /
  should_persist 对长期记忆准入的业务含义；
- 所有允许长期化的结果仍只是长期偏好候选，不产生数据库写入或
  current_version 变化。

复用约束：
- 只读消费 providers.extraction_provider.PreferenceCandidate（复用，不重定义）；
- 不复制 domain / providers 的共享 Schema，不建立平行公共 Schema 或第二套
  共享枚举；
- 新增类型（PreferenceBusinessDecision）仅属于 E 轨 service 内部，不声明为
  IPC / 数据库 / Provider 共享契约。

不读正文红线（与 Day6 SourceAdmissionPolicy 一致）：
- 本策略只读取 candidate 的结构化字段（key/value/category/scope/confidence/
  explicitness/is_temporary/should_persist/source_event_id/memory_status）；
- 绝不读取 candidate.evidence 或用户正文重新推断 category / scope /
  temporality / explicitness，也绝不根据用户正文重新执行偏好抽取；
- reason_code 取自身固定字符串集合，不拼接正文 / evidence / Token / 密钥或
  敏感载荷。

不绕过上游边界：
- 不调用 Day5 CandidateGovernanceService，不调用 Day6 SourceAdmissionPolicy；
- 不写库、不改变 current_version、不修改任何持久化或 IPC 结构。

业务语义（D3_MEMORY_BUSINESS_CONTRACT_V1 §7.4 / §7.5 / §7.9）：
- is_temporary=true 或 should_persist=false → 不得进入稳定长期偏好
  （内存 status 恒 candidate/expired，§7.9）；
- confidence 仅作为"已有证据强度字段"消费，**不参与判定逻辑**，不存在
  0.7/0.8/0.9 等硬编码晋升阈值；不凭高 confidence 绕过临时/安全边界，
  也不把候选自动升级为 active；
- explicitness=implicit：即使用户确认，现阶段仍保留 candidate 与确认边界，
  不得因 confidence 较高自动 ACTIVE 或跳过确认（§7.5 第 6 档）；
- explicitness=explicit 且通过临时/持久化边界：可长期化为 candidate
  （should_store=True），但 requires_confirmation=True，不自动 active（§7.4）。

判定优先级（fail-closed，首个命中即返回）：
1. 类型准入：非 PreferenceCandidate
   -> invalid_candidate_type（should_store=False, requires_confirmation=False）
2. B2 状态防御：memory_status != "candidate"
   -> candidate_status_violation（不读取被污染对象的其余字段做升级）
3. 临时边界（§7.9）：is_temporary=True -> temporary_not_persistent
4. 持久化边界（§7.9）：should_persist=False -> should_persist_false
5. implicit 显式性边界（§7.5 第 6 档 + §7.4）：
   explicitness="implicit" -> implicit_candidate_requires_confirmation
   （should_store=True, requires_confirmation=True，不跳过确认）
6. explicit 长期（§7.9 / §7.4）：
   explicitness="explicit" -> explicit_long_term_candidate
   （should_store=True, requires_confirmation=True，不自动 active）

关键不变量：
- should_store=True 恒 ⟹ requires_confirmation=True（不自动 active）。
- 失败决策（should_store=False）仍记录候选的结构化字段引用
  （category/scope/explicitness/confidence/is_temporary/should_persist/
  candidate_key/source_event_id），供审计可测试，但不含 evidence 正文。
- confidence 不参与判定逻辑，仅作为结构化字段消费记录在决策中。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from providers.extraction_provider import PreferenceCandidate


# ── 固定 reason_code 权威集合（本任务内部定义，不冒充已冻结契约） ──

REASON_INVALID_CANDIDATE_TYPE = "invalid_candidate_type"
REASON_CANDIDATE_STATUS_VIOLATION = "candidate_status_violation"
REASON_TEMPORARY_NOT_PERSISTENT = "temporary_not_persistent"
REASON_SHOULD_PERSIST_FALSE = "should_persist_false"
REASON_IMPLICIT_REQUIRES_CONFIRMATION = (
    "implicit_candidate_requires_confirmation"
)
REASON_EXPLICIT_LONG_TERM_CANDIDATE = "explicit_long_term_candidate"

REASON_CODES: frozenset = frozenset({
    REASON_INVALID_CANDIDATE_TYPE,
    REASON_CANDIDATE_STATUS_VIOLATION,
    REASON_TEMPORARY_NOT_PERSISTENT,
    REASON_SHOULD_PERSIST_FALSE,
    REASON_IMPLICIT_REQUIRES_CONFIRMATION,
    REASON_EXPLICIT_LONG_TERM_CANDIDATE,
})


class PreferenceBusinessDecision(BaseModel):
    """E 轨偏好长期化业务决策结果（结构化，不含正文/密钥）。

    仅属于 E 轨 service 内部语义，非 IPC / 数据库 / Provider 共享契约。
    字段 category/scope/explicitness/confidence 为"只消费"的结构化字段引用
    （非正文，审计可测试）；confidence 作为证据强度字段记录，不做晋升判定。
    """

    model_config = ConfigDict(extra="forbid")

    should_store: bool  # 是否可长期化为 candidate（非 active）
    requires_confirmation: bool  # 是否需用户确认才能晋升 active
    reason_code: str  # 固定字符串集合，不拼接正文/Token/密钥
    # ── 只消费的结构化字段引用（非正文，审计可测试） ──
    category: str  # 六类（presentation/tool_selection/workflow/safety/...）
    scope: str  # 五值（global/topic/tool/session/time_window）
    explicitness: str  # explicit/implicit
    confidence: float = Field(ge=0.0, le=1.0)  # 证据强度字段，消费记录，不做晋升阈值
    is_temporary: bool
    should_persist: bool
    candidate_key: Optional[str] = None  # 结构化审计引用（业务语义键，非正文）
    source_event_id: Optional[str] = None  # 结构化审计引用（R3 provenance，非正文）


class PreferenceBusinessPolicy:
    """E 轨偏好长期化业务决策策略入口（无状态、纯函数式、确定性）。

    decide() 只读消费 PreferenceCandidate 结构化字段，不读 evidence/正文，
    不调用 candidate_governance/source_admission，不写库，不改 current_version。
    """

    def decide(self, candidate: PreferenceCandidate) -> PreferenceBusinessDecision:
        # 1. 类型准入（fail-closed 前置）
        if not isinstance(candidate, PreferenceCandidate):
            return self._decision(
                should_store=False,
                requires_confirmation=False,
                reason_code=REASON_INVALID_CANDIDATE_TYPE,
                candidate=candidate,
            )
        # 2. B2 状态防御：memory_status 必须是 "candidate"
        #    （model_construct / DB 载入 / 未来漂移的污染对象，不读其余字段做升级）
        if candidate.memory_status != "candidate":
            return self._decision(
                should_store=False,
                requires_confirmation=False,
                reason_code=REASON_CANDIDATE_STATUS_VIOLATION,
                candidate=candidate,
            )
        # 3. 临时边界（D3 §7.9）：临时要求不得长期化
        if candidate.is_temporary:
            return self._decision(
                should_store=False,
                requires_confirmation=False,
                reason_code=REASON_TEMPORARY_NOT_PERSISTENT,
                candidate=candidate,
            )
        # 4. 持久化边界（D3 §7.9）：不持久化偏好不得长期化
        if not candidate.should_persist:
            return self._decision(
                should_store=False,
                requires_confirmation=False,
                reason_code=REASON_SHOULD_PERSIST_FALSE,
                candidate=candidate,
            )
        # 5. implicit 显式性边界（D3 §7.5 第 6 档 + §7.4）：
        #    隐式偏好不因 confidence 较高跳过确认，不自动 active。
        if candidate.explicitness == "implicit":
            return self._decision(
                should_store=True,
                requires_confirmation=True,
                reason_code=REASON_IMPLICIT_REQUIRES_CONFIRMATION,
                candidate=candidate,
            )
        # 6. explicit 长期（D3 §7.9 / §7.4）：
        #    可长期化为 candidate，但 requires_confirmation=True，不自动 active。
        return self._decision(
            should_store=True,
            requires_confirmation=True,
            reason_code=REASON_EXPLICIT_LONG_TERM_CANDIDATE,
            candidate=candidate,
        )

    @staticmethod
    def _decision(
        *,
        should_store: bool,
        requires_confirmation: bool,
        reason_code: str,
        candidate: Optional[PreferenceCandidate],
    ) -> PreferenceBusinessDecision:
        """构造决策，并复制候选的结构化审计引用（不含 evidence 正文）。

        类型准入路径 candidate 可能为 None/非法类型：此时结构化引用留空。
        """
        if isinstance(candidate, PreferenceCandidate):
            return PreferenceBusinessDecision(
                should_store=should_store,
                requires_confirmation=requires_confirmation,
                reason_code=reason_code,
                category=candidate.category,
                scope=candidate.scope,
                explicitness=candidate.explicitness,
                confidence=candidate.confidence,
                is_temporary=candidate.is_temporary,
                should_persist=candidate.should_persist,
                candidate_key=candidate.key,
                source_event_id=candidate.source_event_id,
            )
        return PreferenceBusinessDecision(
            should_store=should_store,
            requires_confirmation=requires_confirmation,
            reason_code=reason_code,
            category="",
            scope="",
            explicitness="",
            confidence=0.0,
            is_temporary=False,
            should_persist=False,
        )


__all__ = ["PreferenceBusinessPolicy", "PreferenceBusinessDecision"]
