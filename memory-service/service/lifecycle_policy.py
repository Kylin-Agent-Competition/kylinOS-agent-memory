"""
lifecycle_policy.py — Day8 E 轨知识短中长期生命周期业务决策策略

标记：D8E_LIFECYCLE_POLICY / NOT_PERSISTENCE / NOT_EXECUTION

职责（任务 day8-e-03-lifecycle-policy-v1，方案 PLAN_READY）：
- 新增纯业务生命周期策略：以 memory_status（domain.enums 六值冻结）作为
  唯一优先生命周期真源，输出 short/medium/long 提升（PROMOTE）、降级
  （DEMOTE）、过期（EXPIRE）与归档（ARCHIVE_REQUEST）的可解释决策计划；
- 所有次数/时间/置信度阈值必须通过显式 PolicyConfig 注入，不得把
  7 天/30 天/90 天或固定次数固化为不可配置业务常量；
- 决策为纯函数式、无状态、确定性：同 (snapshot, now, config) 输入永远
  输出相同计划；PROMOTE/DEMOTE 只输出目标 MemoryType 计划，EXPIRE 只
  输出目标 MemoryStatus 计划，均不直接写库；
- ARCHIVE_REQUEST 仅为给 D 轨存储层的 disposition/request，本策略不新增
  MemoryStatus.ARCHIVED 业务状态（domain/enums.py 六值冻结，不修改）；
- fail-closed：CANDIDATE/SUPERSEDED/DEPRECATED/EXPIRED/REMOVED 不因高
  confidence 或高证据档位自动恢复 ACTIVE；模型单独推测
  （EvidenceTier.MODEL_INFERENCE）不得触发自动长期化；
- 所有决策返回固定 action（LifecycleAction 六值）与固定 reason_code
  （13 值权威集合），不拼接任何用户正文/密钥/Token。

本策略明确不做（NOT_PERSISTENCE / NOT_EXECUTION）：
- 不写 SQLite、不执行存储迁移、删除、归档或 Vector 重建；
- 不修改 domain/enums.py、pipeline/schemas.py、domain/* 或共享枚举；
- 不依赖 is_active / is_outdated / should_decay 过渡字段做最终决策
  （LifecycleSnapshot 不含这些字段，extra="forbid" 拒绝传入）；
- 不涉及 IPC、systemd、D-Bus、权限或任何系统依赖（runtime_required=false）。

复用约束：
- NonEmptyStr / AwareDatetime / ConfidenceScore 复用自 domain.common（只读）；
- MemoryStatus 复用自 domain.enums（六值冻结，唯一优先真源）；
- MemoryType 复用自 pipeline.schemas（四值冻结，不在本包重复定义）；
- EvidenceTier 从 service.conflict_resolution_policy 只读导入（同一 D3
  冻结六档证据语义，不复制 Enum；EvidenceTier.priority 为唯一派生优先级
  真源，本模块消费之，不另建数值表）；
- 本模块不复制任何既有 Enum / Pydantic 模型。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from domain.common import AwareDatetime, ConfidenceScore, NonEmptyStr
from domain.enums import MemoryStatus
from pipeline.schemas import MemoryType
from service.conflict_resolution_policy import EvidenceTier  # 只读导入 D3 冻结六档


def _non_negative_timedelta(value: timedelta) -> timedelta:
    """拒绝负时长（ge=0），与 domain/common.py 的 AfterValidator 模式一致。"""
    if value < timedelta(0):
        raise ValueError("timedelta must be non-negative (>= 0)")
    return value


NonNegTimedelta = Annotated[timedelta, AfterValidator(_non_negative_timedelta)]
"""非负时长：解析后校验 >= timedelta(0)，负时长拒绝。"""


class PolicyConfig(BaseModel):
    """生命周期阈值配置（全部必填、无默认值；正式冻结值由部署侧注入）。

    - 提升阈值（inclusive 边界：>= 触发）。
    - 降级阈值（inclusive 边界：<= 触发）。
    - 过期阈值（inclusive 边界：>= 触发）。
    - 归档阈值（inclusive 边界：>= 触发）。
    """

    model_config = ConfigDict(extra="forbid")

    promote_min_confidence: ConfidenceScore
    promote_min_access_count: int = Field(ge=0)
    promote_min_age: NonNegTimedelta
    promote_required_evidence_tier: EvidenceTier

    demote_inactivity_period: NonNegTimedelta
    demote_max_access_count: int = Field(ge=0)
    demote_max_confidence: ConfidenceScore

    expire_after_age: NonNegTimedelta

    archive_after_expired: NonNegTimedelta

    @model_validator(mode="after")
    def _model_inference_not_allowed_for_promotion(self) -> "PolicyConfig":
        """模型单独推测（最低档）不得作为自动提升的可信证据要求档。"""
        if self.promote_required_evidence_tier is EvidenceTier.MODEL_INFERENCE:
            raise ValueError(
                "promote_required_evidence_tier must not be MODEL_INFERENCE "
                "(model-only inference must not trigger auto-promotion)"
            )
        return self


class LifecycleSnapshot(BaseModel):
    """知识生命周期输入快照（审计引用仅含结构化 ID，不含正文/密钥/载荷）。

    - memory_status 为唯一优先生命周期真源（domain.enums 六值冻结）。
    - 明确不含 is_active / is_outdated / should_decay 过渡字段；
      extra="forbid" 保证传入这些字段会触发 ValidationError。
    - access_count / last_accessed_at 为可选的观察事实；缺失时按
      fail-closed 处理（不因缺证据自动提升/降级）。
    """

    model_config = ConfigDict(extra="forbid")

    knowledge_id: NonEmptyStr
    user_id: NonEmptyStr
    memory_type: MemoryType
    memory_status: MemoryStatus
    evidence_tier: EvidenceTier
    confidence_score: ConfidenceScore
    access_count: Optional[int] = Field(default=None, ge=0)
    last_accessed_at: Optional[AwareDatetime] = None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class LifecycleAction(str, Enum):
    """生命周期决策动作（固定六值，不依赖自然语言随机生成）。"""

    PROMOTE = "promote"
    """提升到更高记忆分层（SHORT_TERM→MEDIUM_TERM / MEDIUM_TERM→LONG_TERM）。"""
    DEMOTE = "demote"
    """降级到更低记忆分层（LONG_TERM→MEDIUM_TERM / MEDIUM_TERM→SHORT_TERM）。"""
    EXPIRE = "expire"
    """过期（输出目标 MemoryStatus 计划，不直接执行删除）。"""
    ARCHIVE_REQUEST = "archive_request"
    """归档请求（D 轨存储层 disposition，不新增 ARCHIVED 业务状态）。"""
    HOLD = "hold"
    """保持现状（无可执行动作或需人工/确认信号）。"""
    REJECT = "reject"
    """fail-closed 拒绝（非法输入）。"""


class LifecycleDecision(BaseModel):
    """生命周期决策计划（固定 action + reason_code，不含用户正文）。

    - action：固定决策动作（LifecycleAction 枚举值）。
    - reason_code：固定字符串集合成员，不拼接用户正文/密钥/Token。
    - target_memory_type：仅 PROMOTE / DEMOTE 时非空（目标记忆分层）。
    - target_memory_status：仅 EXPIRE 时非空（目标状态，当前固定 EXPIRED）。
    """

    model_config = ConfigDict(extra="forbid")

    action: LifecycleAction
    reason_code: str
    target_memory_type: Optional[MemoryType] = None
    target_memory_status: Optional[MemoryStatus] = None


class LifecyclePolicy:
    """E 轨知识生命周期决策入口（无状态、纯函数式、确定性）。

    decide(snapshot, *, now) 按 fail-closed 优先级逐段判定，首命中即返回：
    1. 类型准入：snapshot 非 LifecycleSnapshot 或 now 非 datetime →
       REJECT(invalid_input)；now 归一化为 aware UTC；
    2. 非 ACTIVE 状态 fail-closed（不得自动恢复 ACTIVE）：
       - REMOVED → ARCHIVE_REQUEST(removed_cold_data)；
       - EXPIRED → (now - updated_at) >= archive_after_expired ?
         ARCHIVE_REQUEST(expired_cold_data) : HOLD(expired_pending_archive)；
       - CANDIDATE → HOLD(candidate_requires_confirmation)（不因高
         confidence 自动提升）；
       - SUPERSEDED → HOLD(superseded_no_auto_recovery)；
       - DEPRECATED → HOLD(deprecated_no_auto_recovery)；
    3. ACTIVE：
       - (a) PROMOTE（仅 SHORT_TERM→MEDIUM_TERM、MEDIUM_TERM→LONG_TERM）：
         age >= promote_min_age 且 access_count 非 None 且 >=
         promote_min_access_count 且 confidence >= promote_min_confidence
         且证据档位不低（EvidenceTier.priority 数值 <= required，inclusive；
         模型单独推测 priority=5 > 任何非 MODEL_INFERENCE 要求档 → 不满足）
         → PROMOTE(credible_evidence_threshold)，target_memory_type=目标分层；
       - (b) EXPIRE：age >= expire_after_age →
         EXPIRE(age_threshold_reached)，target_memory_status=EXPIRED；
       - (c) DEMOTE（仅 LONG_TERM→MEDIUM_TERM、MEDIUM_TERM→SHORT_TERM）：
         inactivity >= demote_inactivity_period → DEMOTE(inactivity_threshold)；
         否则 access_count 非 None 且 <= demote_max_access_count →
         DEMOTE(low_usage_threshold)；否则 confidence <=
         demote_max_confidence → DEMOTE(confidence_decay_threshold)；
       - (d) 其余 → HOLD(no_threshold_met)。

    优先级设计依据：有可信证据 + 高使用率的有价值旧知识优先提升而非过期；
    已达过期年龄的终态动作优先于中间降级。
    """

    def __init__(self, config: PolicyConfig) -> None:
        if not isinstance(config, PolicyConfig):
            raise TypeError("config must be a PolicyConfig instance")
        self._config = config

    def decide(
        self, snapshot: LifecycleSnapshot, *, now: datetime
    ) -> LifecycleDecision:
        # 1. 类型准入（fail-closed 前置，避免属性访问异常或借用伪造字段）
        if not isinstance(snapshot, LifecycleSnapshot) or not isinstance(
            now, datetime
        ):
            return self._reject()

        # now 归一化为 aware UTC（缺失 tzinfo 补 UTC 再统一转 UTC，
        # 与 AwareDatetime 一致；负时长自然 fail 所有 >= 比较 → 安全落 HOLD）
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)

        # 2. 非 ACTIVE 状态 fail-closed：不得自动恢复 ACTIVE
        if snapshot.memory_status is MemoryStatus.REMOVED:
            return self._archive_request("removed_cold_data")
        if snapshot.memory_status is MemoryStatus.EXPIRED:
            if now - snapshot.updated_at >= self._config.archive_after_expired:
                return self._archive_request("expired_cold_data")
            return self._hold("expired_pending_archive")
        if snapshot.memory_status is MemoryStatus.CANDIDATE:
            return self._hold("candidate_requires_confirmation")
        if snapshot.memory_status is MemoryStatus.SUPERSEDED:
            return self._hold("superseded_no_auto_recovery")
        if snapshot.memory_status is MemoryStatus.DEPRECATED:
            return self._hold("deprecated_no_auto_recovery")

        # 3. ACTIVE：PROMOTE → EXPIRE → DEMOTE → HOLD（首命中即返回）
        promotion = self._check_promotion(snapshot, now)
        if promotion is not None:
            return promotion

        if now - snapshot.created_at >= self._config.expire_after_age:
            return self._expire()

        demotion = self._check_demotion(snapshot, now)
        if demotion is not None:
            return demotion

        return self._hold("no_threshold_met")

    def _check_promotion(
        self, snapshot: LifecycleSnapshot, now: datetime
    ) -> Optional[LifecycleDecision]:
        """ACTIVE 提升检查：仅 SHORT_TERM→MEDIUM_TERM / MEDIUM_TERM→LONG_TERM。"""
        if snapshot.memory_type is MemoryType.SHORT_TERM:
            target = MemoryType.MEDIUM_TERM
        elif snapshot.memory_type is MemoryType.MEDIUM_TERM:
            target = MemoryType.LONG_TERM
        else:
            return None  # LONG_TERM / EPHEMERAL 无提升路径

        if now - snapshot.created_at < self._config.promote_min_age:
            return None
        if snapshot.access_count is None:
            return None  # fail-closed：无使用证据不自动长期化
        if snapshot.access_count < self._config.promote_min_access_count:
            return None
        if snapshot.confidence_score < self._config.promote_min_confidence:
            return None
        required_priority = self._config.promote_required_evidence_tier.priority
        # 数值小=档位高；当前档位数值 > 要求档数值 → 证据不足，不满足
        if snapshot.evidence_tier.priority > required_priority:
            return None
        return self._promote(target)

    def _check_demotion(
        self, snapshot: LifecycleSnapshot, now: datetime
    ) -> Optional[LifecycleDecision]:
        """ACTIVE 降级检查：仅 LONG_TERM→MEDIUM_TERM / MEDIUM_TERM→SHORT_TERM。

        三子条件互斥检查（inactivity → low_usage → confidence_decay），
        首命中即返回；inactivity 以 last_accessed_at 为最后活动，缺失时
        以 created_at 兜底（无观察事实时仍可判定不活跃）。
        """
        if snapshot.memory_type is MemoryType.LONG_TERM:
            target = MemoryType.MEDIUM_TERM
        elif snapshot.memory_type is MemoryType.MEDIUM_TERM:
            target = MemoryType.SHORT_TERM
        else:
            return None  # SHORT_TERM / EPHEMERAL 无降级路径

        if snapshot.last_accessed_at is not None:
            inactivity = now - snapshot.last_accessed_at
        else:
            inactivity = now - snapshot.created_at

        if inactivity >= self._config.demote_inactivity_period:
            return self._demote(target, "inactivity_threshold")
        if (
            snapshot.access_count is not None
            and snapshot.access_count <= self._config.demote_max_access_count
        ):
            return self._demote(target, "low_usage_threshold")
        if snapshot.confidence_score <= self._config.demote_max_confidence:
            return self._demote(target, "confidence_decay_threshold")
        return None

    @staticmethod
    def _promote(target: MemoryType) -> LifecycleDecision:
        return LifecycleDecision(
            action=LifecycleAction.PROMOTE,
            reason_code="credible_evidence_threshold",
            target_memory_type=target,
        )

    @staticmethod
    def _demote(target: MemoryType, reason_code: str) -> LifecycleDecision:
        return LifecycleDecision(
            action=LifecycleAction.DEMOTE,
            reason_code=reason_code,
            target_memory_type=target,
        )

    @staticmethod
    def _expire() -> LifecycleDecision:
        return LifecycleDecision(
            action=LifecycleAction.EXPIRE,
            reason_code="age_threshold_reached",
            target_memory_status=MemoryStatus.EXPIRED,
        )

    @staticmethod
    def _archive_request(reason_code: str) -> LifecycleDecision:
        return LifecycleDecision(
            action=LifecycleAction.ARCHIVE_REQUEST,
            reason_code=reason_code,
        )

    @staticmethod
    def _hold(reason_code: str) -> LifecycleDecision:
        return LifecycleDecision(
            action=LifecycleAction.HOLD,
            reason_code=reason_code,
        )

    @staticmethod
    def _reject() -> LifecycleDecision:
        return LifecycleDecision(
            action=LifecycleAction.REJECT,
            reason_code="invalid_input",
        )


__all__ = [
    "LifecycleAction",
    "LifecycleSnapshot",
    "PolicyConfig",
    "LifecycleDecision",
    "LifecyclePolicy",
]
