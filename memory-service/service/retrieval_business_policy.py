"""
retrieval_business_policy.py — Day9E 标准 Memory Context 检索业务策略骨架（E 轨 service 内部）

标记：D9E_POLICY_SKELETON / NOT_IPC_CONTRACT / NOT_PERSISTENCE
      / NOT_B_TRACK_REIMPLEMENTATION

职责（任务 day9-e-03-retrieval-business-policy-skeleton-v1，方案 PLAN_READY）：
- 为"标准 knowledge context 只允许业务上当前有效的 active/current 记忆进入
  正常上下文"这一业务约束提供唯一确定性构造入口 build_standard_filter()，
  产出 B 轨既有契约 RetrievalFilter；
- 提供逐状态准入判定 admit_memory_status()，输出稳定
  policy_version / reason_code 可解释决策（ContextStatusDecision），不暴露
  候选正文；
- 保留最终权重注入点 build_weighted_rerank_policy() / DEFAULT_RERANK_POLICY，
  默认走 rrf-v1 等权路径，不冻结最终权重（权重要由开发集选择后另行任务注入）。

复用约束（复用不复制）：
- 只复用 retrieval.contracts 的 RetrievalFilter / KnowledgeFilter / ObjectType /
  RerankPolicy / Channel 与 domain.enums.MemoryStatus 六值；
- 不复制 RRF、Filter、共享枚举或权重校验逻辑：正数/有限/双通道完备性校验由
  RerankPolicy 自身 validator 承担，异常原样传播；
- current-version 唯一不变量（每个 memory_id 唯一 is_current=True 版本）与
  unresolved conflict 硬过滤由 B 轨 retrieval.fusion 承担
  （fusion.py `_hard_filter` 与唯一 current version 聚合），本策略不复制、
  不提供绕过入口：
    - conflict_policy 恒钉 STANDARD_CONFLICT_POLICY="exclude_unresolved"；
    - object_types 恒钉 [ObjectType.KNOWLEDGE]；
    - allowed_memory_statuses 恒钉 ["active"]；
    - user_id 只做最小非空校验，通配用户 / 作用域深校验归 B 轨
      validate_retrieval_filter；
    - 敏感度等 B 轨既有安全边界只能通过 options 进一步收窄，API 上不存在
      放宽通道（options extra="forbid"，不暴露 status/conflict/object_types）。

负向状态口径来源：
- candidate / superseded / expired / removed 与 unresolved conflict 的拒绝语义
  直接来自任务卡 day9-e-03 与 evaluation/D9_RETRIEVAL_GOLD_SPEC_V1.md
  negative_guardrail（removed/expired/superseded/candidate/unresolved_conflict/
  cross_user/sensitive_recall_prohibited）七类边界；
- deprecated 在 D9 Gold 中列为 boundary（检索语义待 B 轨确认），本策略按任务卡
  要求负向拒绝，属 E 轨业务策略层的进一步约束，不改动 B 轨行为；后续 B 轨冻结
  deprecated 检索语义时通过 POLICY_VERSION 升版调整，不改 B 轨。

不读正文红线：
- ContextStatusDecision 仅承载 memory_status / admitted / reason_code /
  policy_version，不含 content / evidence / 任意 ID 或载荷；
- reason_code 取自身固定字符串集合（REASON_CODES），不拼接正文 / Token / 密钥；
- 本模块不输出任何日志语句。

非契约声明：
- POLICY_VERSION 与 reason_code 集合为本任务内部定义，未冻结为团队基线；
- 默认权重不冻结（DEFAULT_RERANK_POLICY=None 即 B 轨 rrf-v1 等权路径语义）。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from domain.enums import MemoryStatus
from retrieval.contracts import (
    Channel,
    KnowledgeFilter,
    ObjectType,
    RerankPolicy,
    RetrievalFilter,
)


# ── 稳定策略常量（本任务内部定义，非冻结团队契约） ──

POLICY_VERSION = "knowledge-context-policy/v1"
STANDARD_ALLOWED_MEMORY_STATUSES = ("active",)  # 只允许 active 进入正常上下文
STANDARD_CONFLICT_POLICY = "exclude_unresolved"  # fail-closed，与 B 轨硬过滤一致


# ── 固定 reason_code 权威集合（固定字符串，不拼接正文/ID/载荷） ──

REASON_ADMITTED_STANDARD_CONTEXT = "admitted_standard_context"
REASON_REJECTED_CANDIDATE = "rejected_candidate_status"
REASON_REJECTED_SUPERSEDED = "rejected_superseded_status"
REASON_REJECTED_DEPRECATED = "rejected_deprecated_status"
REASON_REJECTED_EXPIRED = "rejected_expired_status"
REASON_REJECTED_REMOVED = "rejected_removed_status"
REASON_REJECTED_UNKNOWN = "rejected_unknown_status"  # 非六值冻结集合 → fail-closed

REASON_CODES: frozenset = frozenset({
    REASON_ADMITTED_STANDARD_CONTEXT,
    REASON_REJECTED_CANDIDATE,
    REASON_REJECTED_SUPERSEDED,
    REASON_REJECTED_DEPRECATED,
    REASON_REJECTED_EXPIRED,
    REASON_REJECTED_REMOVED,
    REASON_REJECTED_UNKNOWN,
})

_FROZEN_MEMORY_STATUS_VALUES = frozenset(status.value for status in MemoryStatus)

_REASON_BY_STATUS_VALUE = {
    MemoryStatus.CANDIDATE.value: REASON_REJECTED_CANDIDATE,
    MemoryStatus.SUPERSEDED.value: REASON_REJECTED_SUPERSEDED,
    MemoryStatus.DEPRECATED.value: REASON_REJECTED_DEPRECATED,
    MemoryStatus.EXPIRED.value: REASON_REJECTED_EXPIRED,
    MemoryStatus.REMOVED.value: REASON_REJECTED_REMOVED,
}


class ContextStatusDecision(BaseModel):
    """逐状态准入的确定性决策（结构化，不含候选正文/ID，仅承载可解释字段）。

    仅属于 E 轨 service 内部语义，非 IPC / 持久化 / Provider 共享契约。
    reason_code 为固定字符串集合成员，policy_version 恒为 POLICY_VERSION。
    """

    model_config = ConfigDict(extra="forbid")

    memory_status: str
    admitted: bool
    reason_code: str
    policy_version: str


class StandardKnowledgeContextOptions(BaseModel):
    """标准 knowledge context 构造选项：只能进一步收窄，不存在放宽通道。

    extra="forbid" 结构性杜绝放宽：不暴露 allowed_memory_statuses /
    conflict_policy / object_types 等字段。默认空白名单 = 不额外约束，
    与 B 轨融合行为保持一致。
    """

    model_config = ConfigDict(extra="forbid")

    knowledge: KnowledgeFilter = Field(default_factory=KnowledgeFilter)
    memory_types: List[str] = Field(default_factory=list)
    allowed_sensitivity: List[str] = Field(default_factory=list)


class KnowledgeContextPolicy:
    """标准 knowledge context 检索策略入口（无状态、纯函数式、确定性）。

    build_standard_filter() 把业务约束收敛为唯一 RetrievalFilter 构造路径；
    admit_memory_status() 提供逐状态准入判定与稳定 reason_code。
    不调用 B 轨编排，不写库，不触发检索，不输出日志。
    """

    def build_standard_filter(
        self,
        user_id: str,
        as_of: datetime,
        options: Optional[StandardKnowledgeContextOptions] = None,
    ) -> RetrievalFilter:
        """构造标准 knowledge context RetrievalFilter（B 轨契约，只收窄不放宽）。

        - user_id 空/纯空白 → ValueError（最小非空约束，确定性中文错误信息）；
        - as_of 必须显式传入（策略内禁止 datetime.now()），naive datetime 由
          RetrievalFilter 的时区 validator 抛错，原样传播；
        - 产出字段钉死：object_types=[KNOWLEDGE]、
          allowed_memory_statuses=["active"]、conflict_policy="exclude_unresolved"。
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id 不得为空或纯空白")
        effective = options or StandardKnowledgeContextOptions()
        return RetrievalFilter(
            user_id=user_id,
            object_types=[ObjectType.KNOWLEDGE],
            memory_types=effective.memory_types,
            allowed_memory_statuses=list(STANDARD_ALLOWED_MEMORY_STATUSES),
            allowed_sensitivity=effective.allowed_sensitivity,
            conflict_policy=STANDARD_CONFLICT_POLICY,
            as_of=as_of,
            knowledge=effective.knowledge,
        )

    def admit_memory_status(self, memory_status: str) -> ContextStatusDecision:
        """逐状态准入判定：仅 active 通过，其余六值状态/未知一律 fail-closed。

        未知字符串（含带空白/大小写漂移的取值）视为 rejected_unknown_status，
        不猜测归属，不读取任何正文。
        """
        if memory_status == MemoryStatus.ACTIVE.value:
            return ContextStatusDecision(
                memory_status=memory_status,
                admitted=True,
                reason_code=REASON_ADMITTED_STANDARD_CONTEXT,
                policy_version=POLICY_VERSION,
            )
        if memory_status in _FROZEN_MEMORY_STATUS_VALUES:
            return ContextStatusDecision(
                memory_status=memory_status,
                admitted=False,
                reason_code=_REASON_BY_STATUS_VALUE[memory_status],
                policy_version=POLICY_VERSION,
            )
        return ContextStatusDecision(
            memory_status=memory_status,
            admitted=False,
            reason_code=REASON_REJECTED_UNKNOWN,
            policy_version=POLICY_VERSION,
        )


def build_weighted_rerank_policy(*, fts5_weight: float, vector_weight: float) -> RerankPolicy:
    """构造 weighted-rrf/v1 RerankPolicy 的显式权重注入接口（无默认权重）。

    两个权重参数必须显式传入（签名级无默认值，杜绝拍脑袋冻结权重）。
    正数/有限/双通道完备性由 RerankPolicy 自身 validator 校验，异常原样传播。
    最终通道权重由开发集选择后另行任务注入；本任务只保留注入点。
    """
    return RerankPolicy(
        version="weighted-rrf/v1",
        channel_weights={
            Channel.FTS5: fts5_weight,
            Channel.VECTOR: vector_weight,
        },
    )


# rrf-v1 等权默认路径（None = B 轨 rrf-v1 等权语义，非单位业务权重默认不启用）
DEFAULT_RERANK_POLICY: Optional[RerankPolicy] = None


__all__ = [
    "POLICY_VERSION",
    "STANDARD_ALLOWED_MEMORY_STATUSES",
    "STANDARD_CONFLICT_POLICY",
    "REASON_CODES",
    "REASON_ADMITTED_STANDARD_CONTEXT",
    "REASON_REJECTED_CANDIDATE",
    "REASON_REJECTED_SUPERSEDED",
    "REASON_REJECTED_DEPRECATED",
    "REASON_REJECTED_EXPIRED",
    "REASON_REJECTED_REMOVED",
    "REASON_REJECTED_UNKNOWN",
    "ContextStatusDecision",
    "StandardKnowledgeContextOptions",
    "KnowledgeContextPolicy",
    "build_weighted_rerank_policy",
    "DEFAULT_RERANK_POLICY",
]