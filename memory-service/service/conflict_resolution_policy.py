"""
conflict_resolution_policy.py — Day8 E 轨知识冲突六档证据优先级业务裁决策略

标记：D8E_CONFLICT_RESOLUTION / NOT_PERSISTENCE / NOT_DETECTION

职责（任务 day8-e-02-conflict-resolution-policy-v1，方案 PLAN_READY）：
- 新增纯业务冲突裁决策略：按既有六档证据可信优先级（用户最新显式配置 >
  用户明确确认 > 真实 Tool 执行结果 > 多次一致行为 > 单次行为推断 >
  模型自身推测）对**同用户**知识冲突给出可解释、固定 reason_code 的
  保留（KEEP_LEFT / KEEP_RIGHT）、共存（COEXIST）或延后（DEFER）决策；
- 保证真实 Tool 事实高于模型自述；模型自身推测（Tier 6）不得覆盖
  Tier 1-5 任何来源；
- 跨 user_id 输入 fail-closed 拒绝；同等优先级且无法依据已冻结规则决胜时
  必须 DEFER，不得用 confidence 或模型自由推理强行决胜；
- 仅同为用户显式配置（Tier 1 同档）时允许使用可信时间事实（recorded_at）
  判断最新配置；时间事实不得由模型生成；
- 策略输出固定 action 与 reason_code，不拼接任何用户正文。

本策略明确不做（NOT_PERSISTENCE / NOT_DETECTION）：
- 不实现冲突候选发现、语义相似度、向量相似度、
  contradiction/temporal_inconsistency 检测阈值（属 B/上游能力，
  HD-SCHEMA-04）；
- 不修改 domain/conflict.py、domain/enums.py 或共享
  ConflictType / ResolutionStatus；
- 不写 SQLite memory_conflict 持久化、事务、Outbox、Vector、FTS5；
- 不涉及 IPC、systemd、D-Bus、权限或任何系统依赖（runtime_required=false）。

复用约束：
- NonEmptyStr / AwareDatetime 复用自 domain.common（只读，不修改）；
- 不从 domain.enums 导入 ConflictType / ResolutionStatus（本策略不依赖
  冲突类型枚举）；
- EvidenceTier / DecisionAction 仅为本 service policy 局部业务类型，
  不进入 service/__init__.py.__all__，不进入 domain.enums；
- 本模块不复制任何既有 Enum / Pydantic 模型；
- 六档证据优先级唯一派生真源为 EvidenceTier.priority（从声明顺序派生，
  数值越小优先级越高）；conflict_resolution_policy 与 lifecycle_policy
  均消费该单一派生产物，任何策略不得另建独立优先级映射。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict

from domain.common import AwareDatetime, NonEmptyStr


class EvidenceTier(str, Enum):
    """六档证据可信优先级（仅属于本 service policy 的局部业务类型）。

    数值语义：数字越小优先级越高（见本类 priority 属性，从声明顺序派生）。
    声明顺序即优先级顺序（1 → 6，从高到低）。
    """

    USER_EXPLICIT_CONFIG_LATEST = "user_explicit_config_latest"
    """第 1 档（最高）：用户最新显式配置。"""
    USER_CONFIRMED = "user_confirmed"
    """第 2 档：用户明确确认。"""
    TOOL_EXECUTION_RESULT = "tool_execution_result"
    """第 3 档：真实 Tool 执行结果。"""
    CONSISTENT_BEHAVIOR_MULTIPLE = "consistent_behavior_multiple"
    """第 4 档：多次一致行为。"""
    BEHAVIOR_INFERENCE_SINGLE = "behavior_inference_single"
    """第 5 档：单次行为推断。"""
    MODEL_INFERENCE = "model_inference"
    """第 6 档（最低）：模型自身推测（不得覆盖 Tier 1-5 任何来源）。"""

    @property
    def priority(self) -> int:
        """唯一派生证据优先级（0..5，声明顺序即档位顺序）。

        数值越小优先级越高：USER_EXPLICIT_CONFIG_LATEST=0（最高）…
        MODEL_INFERENCE=5（最低）。纯从声明顺序派生，禁止各策略另建数值表。
        """
        return list(EvidenceTier).index(self)


class DecisionAction(str, Enum):
    """裁决动作（仅属于本 service policy 的局部业务类型）。

    action 为固定枚举值，不依赖自然语言随机生成。
    """

    KEEP_LEFT = "keep_left"
    """保留左侧，右侧被替代。"""
    KEEP_RIGHT = "keep_right"
    """保留右侧，左侧被替代。"""
    COEXIST = "coexist"
    """作用域可区分，共存。"""
    DEFER = "defer"
    """无法依据已冻结规则决胜，延后。"""
    REJECT = "reject"
    """fail-closed 拒绝（跨用户或非法输入）。"""


class ConflictSide(BaseModel):
    """冲突一侧输入（审计引用仅含结构化 ID，不含正文/密钥/载荷）。

    - knowledge_id：知识 ID（审计引用）。
    - user_id：用户归属隔离键（*禁止模型生成，D3 §7.1）。
    - evidence_tier：该侧证据档位。
    - scope：业务作用域（用于 COEXIST 判定；None 表示未定义）。
    - recorded_at：可信时间事实（*禁止模型生成；仅 Tier 1 同档时用于
      判断最新显式配置，其余档位不参与决胜）。
    """

    model_config = ConfigDict(extra="forbid")

    knowledge_id: NonEmptyStr
    user_id: NonEmptyStr
    evidence_tier: EvidenceTier
    scope: Optional[str] = None
    recorded_at: Optional[AwareDatetime] = None


class ConflictDecision(BaseModel):
    """裁决结果（固定 action + reason_code，不含用户正文）。

    - action：固定裁决动作（DecisionAction 枚举值）。
    - reason_code：固定字符串集合成员，不拼接用户正文/密钥/Token。
    - winner_id：仅 KEEP_LEFT / KEEP_RIGHT 时非空（获胜侧 knowledge_id）。
    """

    model_config = ConfigDict(extra="forbid")

    action: DecisionAction
    reason_code: str
    winner_id: Optional[str] = None


class ConflictResolutionPolicy:
    """E 轨知识冲突六档证据优先级裁决入口（无状态、纯函数式、确定性）。

    resolve(left, right) 按 fail-closed 优先级逐段判定，首个命中即返回：
    1. 类型准入：left/right 非 ConflictSide → REJECT(invalid_input)；
    2. 跨用户隔离：left.user_id != right.user_id →
       REJECT(cross_user_blocked)；
    3. 作用域可区分：left.scope 与 right.scope 均非 None 且不等 →
       COEXIST(scope_distinguishable)（不得无条件覆盖）；
    4. 证据优先级比较（EvidenceTier.priority，数值小=高档）：
       - 高档侧保留，低档侧被替代 → KEEP_LEFT / KEEP_RIGHT
         (evidence_tier_priority)，winner_id 为高档侧 knowledge_id；
       - （自动满足：Tier 6 不得覆盖 Tier 1-5；真实 Tool 胜模型自述）；
    5. 同档决胜（仅 Tier 1 USER_EXPLICIT_CONFIG_LATEST，仅依据可信时间
       事实 recorded_at）：
       - 两侧 recorded_at 均非 None 且不等 → 保留较新侧
         KEEP_LEFT / KEEP_RIGHT(latest_explicit_config_wins)；
       - 时间相等或任一侧缺失 → DEFER(same_tier_undecidable)；
       - 其余同档（Tier 2-6）→ DEFER(same_tier_undecidable)，不得用
         confidence 或模型自由推理强行决胜。
    """

    def resolve(
        self, left: ConflictSide, right: ConflictSide
    ) -> ConflictDecision:
        # 1. 类型准入（fail-closed 前置，避免属性访问异常或借用伪造字段）
        if not isinstance(left, ConflictSide) or not isinstance(
            right, ConflictSide
        ):
            return self._reject("invalid_input")

        # 2. 跨用户隔离（D3 §7.1：user_id 为归属隔离键，跨用户 fail-closed）
        if left.user_id != right.user_id:
            return self._reject("cross_user_blocked")

        # 3. 作用域可区分 → 共存（业务上可区分时优先 COEXIST，不无条件覆盖）
        if (
            left.scope is not None
            and right.scope is not None
            and left.scope != right.scope
        ):
            return self._coexist()

        # 4. 证据优先级比较（数值小=高档；Tier 6 自动无法覆盖 Tier 1-5）
        pri_left = left.evidence_tier.priority
        pri_right = right.evidence_tier.priority
        if pri_left < pri_right:
            return self._keep_left(left.knowledge_id)
        if pri_right < pri_left:
            return self._keep_right(right.knowledge_id)

        # 5. 同档决胜：仅 Tier 1 允许按可信时间事实判断最新显式配置
        if left.evidence_tier is EvidenceTier.USER_EXPLICIT_CONFIG_LATEST:
            if (
                left.recorded_at is not None
                and right.recorded_at is not None
            ):
                if left.recorded_at > right.recorded_at:
                    return self._keep_left(
                        left.knowledge_id, "latest_explicit_config_wins"
                    )
                if right.recorded_at > left.recorded_at:
                    return self._keep_right(
                        right.knowledge_id, "latest_explicit_config_wins"
                    )
            # 时间相等或任一侧时间事实缺失 → 不可决
            return self._defer()

        # 其余同档（Tier 2-6）：不得用 confidence/自由推理强行决胜 → DEFER
        return self._defer()

    @staticmethod
    def _keep_left(
        knowledge_id: str, reason_code: str = "evidence_tier_priority"
    ) -> ConflictDecision:
        """保留左侧（默认按证据优先级；Tier 1 决胜时传最新配置码）。"""
        return ConflictDecision(
            action=DecisionAction.KEEP_LEFT,
            reason_code=reason_code,
            winner_id=knowledge_id,
        )

    @staticmethod
    def _keep_right(
        knowledge_id: str, reason_code: str = "evidence_tier_priority"
    ) -> ConflictDecision:
        """保留右侧（默认按证据优先级；Tier 1 决胜时传最新配置码）。"""
        return ConflictDecision(
            action=DecisionAction.KEEP_RIGHT,
            reason_code=reason_code,
            winner_id=knowledge_id,
        )

    @staticmethod
    def _coexist() -> ConflictDecision:
        """作用域可区分 → 共存。"""
        return ConflictDecision(
            action=DecisionAction.COEXIST,
            reason_code="scope_distinguishable",
        )

    @staticmethod
    def _defer() -> ConflictDecision:
        """不可决 → 延后（同档且无法依据已冻结规则决胜）。"""
        return ConflictDecision(
            action=DecisionAction.DEFER,
            reason_code="same_tier_undecidable",
        )

    @staticmethod
    def _reject(reason_code: str) -> ConflictDecision:
        """fail-closed 拒绝（跨用户或非法输入）。"""
        return ConflictDecision(
            action=DecisionAction.REJECT,
            reason_code=reason_code,
        )


__all__ = [
    "EvidenceTier",
    "DecisionAction",
    "ConflictSide",
    "ConflictDecision",
    "ConflictResolutionPolicy",
]
