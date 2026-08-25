"""
preference_version_policy.py — Day7E 偏好版本变更规划策略（E 轨 service 内部）

标记：D7E_PREFERENCE_VERSION_POLICY / NOT_PERSISTENCE / NOT_IPC_CONTRACT
      / NOT_EXTRACTION / NOT_SHARED_CONTRACT

职责（任务 day7-e-02-preference-version-policy-v1，方案 PLAN_READY）：
- 在 D7E-01 长期化门禁（PreferenceBusinessDecision）与既有 active 偏好记录
  （domain.Preference）之上，规划 CREATE / COEXIST / UPDATE / NO_OP / ROLLBACK
  五种**纯业务**版本动作；
- 一律不写数据库、不修改 current_version 指针、不实现 Repository / UoW /
  Migration / Outbox、不实现真实 rollback 事务（由 D 轨负责事务与持久化）；
- 所有输出仅为业务计划，供下游消费，不产生任何持久化副作用。

严格边界：
- 只读消费 domain.Preference 与 service.preference_business_policy
  .PreferenceBusinessDecision，不 import providers.extraction_provider /
  candidate_governance / source_admission；
- 不修改 domain.Preference / domain.enums，不建立平行共享 Schema 或第二套
  共享枚举；
- 新增类型（PreferenceVersionAction / PreferenceVersionIntent /
  PreferenceRollbackIntent / PreferenceVersionPlan）仅属于本 service 内部，
  不声明为 IPC / 数据库 / Provider 共享契约。

不读正文红线（与 D7E-01 一致）：
- 本策略只读取 Preference 的结构化字段（user_id / preference_key /
  preference_value / preference_scope / version / preference_id /
  previous_version_id / memory_status）与 decision.should_store；
- 不读取 evidence_event_ids 展开或 extracted_entities 等正文/实体敏感字段；
- reason_code 取自身固定字符串集合，不拼接正文 / Token / 密钥 / 敏感载荷。

业务语义（D3_MEMORY_BUSINESS_CONTRACT_V1 §7.1 / §7.2 / §7.9）：
- CREATE：同 user_id + 同 preference_key + 同 scope 无 active 当前记录 → 首版。
- NO_OP：同 user_id + 同 preference_key + 同 scope 且 value 完全相同
  → 不增版本，不制造无意义版本膨胀。
- UPDATE：同 user_id + 同 preference_key + 同 scope 且 value 变化
  → next_version = current.version + 1，previous_version_id = current.preference_id，
  保留历史，不原地覆盖。
- COEXIST：同 preference_key 但 scope 不同 → 新 scope 创建独立首版，
  旧 scope active 偏好不被 supersede。
- ROLLBACK：同 user_id + 同 preference_key + 同 scope 的历史版本
  → 输出回滚计划（D 轨负责事务 / current_version 切换 / 历史持久化）。
- fail-closed 拒绝：跨 user_id、未来版本、无关版本、不可长期化候选、
  版本意图与长期化决策 key/scope 不一致 → REJECTED。

判定优先级（fail-closed，首个命中即返回）：
- plan_preference：类型准入 → 长期化门禁(should_store=False) → 跨用户 →
  版本意图与决策 key/scope 一致性 → 同 key+同 scope active（NO_OP / UPDATE）
  → 同 key 不同 scope（COEXIST）→ CREATE。
- plan_rollback：类型准入 → target 存在 → 跨用户 → 同 key+scope active 定位 →
  无关版本二次防御 → 未来/当前版本防御 → ROLLBACK。
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from domain.preference import Preference
from domain.enums import MemoryStatus, PreferenceScope
from service.preference_business_policy import PreferenceBusinessDecision


# ── 固定 reason_code 权威集合（本任务内部定义，不冒充已冻结契约） ──

REASON_CREATE_FIRST_VERSION = "create_first_version"
REASON_COEXIST_DIFFERENT_SCOPE = "coexist_different_scope"
REASON_UPDATE_VALUE_CHANGED = "update_value_changed"
REASON_NO_OP_SAME_VALUE = "no_op_same_value"
REASON_ROLLBACK_TO_HISTORY_VERSION = "rollback_to_history_version"
REASON_REJECTED_NOT_PERSISTABLE = "rejected_not_persistable"
REASON_REJECTED_CROSS_USER = "rejected_cross_user"
REASON_REJECTED_ROLLBACK_TARGET_NOT_FOUND = (
    "rejected_rollback_target_not_found"
)
REASON_REJECTED_ROLLBACK_UNRELATED_VERSION = (
    "rejected_rollback_unrelated_version"
)
REASON_REJECTED_ROLLBACK_FUTURE_OR_CURRENT = (
    "rejected_rollback_future_or_current_version"
)
REASON_REJECTED_NO_ACTIVE_CHAIN = "rejected_no_active_chain"
REASON_REJECTED_INVALID_INPUT = "rejected_invalid_input"
REASON_REJECTED_INTENT_DECISION_INCONSISTENT = (
    "rejected_intent_decision_inconsistent"
)

REASON_CODES: frozenset = frozenset({
    REASON_CREATE_FIRST_VERSION,
    REASON_COEXIST_DIFFERENT_SCOPE,
    REASON_UPDATE_VALUE_CHANGED,
    REASON_NO_OP_SAME_VALUE,
    REASON_ROLLBACK_TO_HISTORY_VERSION,
    REASON_REJECTED_NOT_PERSISTABLE,
    REASON_REJECTED_CROSS_USER,
    REASON_REJECTED_ROLLBACK_TARGET_NOT_FOUND,
    REASON_REJECTED_ROLLBACK_UNRELATED_VERSION,
    REASON_REJECTED_ROLLBACK_FUTURE_OR_CURRENT,
    REASON_REJECTED_NO_ACTIVE_CHAIN,
    REASON_REJECTED_INVALID_INPUT,
    REASON_REJECTED_INTENT_DECISION_INCONSISTENT,
})


class PreferenceVersionAction(str, Enum):
    """偏好版本业务动作（service 内部）。

    前五值为**业务动作**（任务"五种结构化业务动作"）：
    - CREATE：创建首版
    - COEXIST：同 key 不同 scope 并行共存
    - UPDATE：同 key+scope 值变化，版本递增
    - NO_OP：同 key+scope 值相同，不增版本
    - ROLLBACK：回滚到历史版本（仅输出计划）

    REJECTED 是 fail-closed **防御态**，不属于业务动作。
    """

    CREATE = "create"
    COEXIST = "coexist"
    UPDATE = "update"
    NO_OP = "no_op"
    ROLLBACK = "rollback"
    REJECTED = "rejected"


class PreferenceVersionIntent(BaseModel):
    """plan_preference 输入（service 内部）。

    - user_id：外部传入（PreferenceCandidate / PreferenceBusinessDecision
      均无 user_id 字段）。
    - preference_key / scope / value：候选的业务结构化输入（可源自
      decision.candidate_key / decision.scope；value 为决策独立承载）。
    - decision：D7E-01 长期化门禁结果（should_store 是准入依据）。
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str
    preference_key: str
    scope: PreferenceScope
    value: str
    decision: PreferenceBusinessDecision


class PreferenceRollbackIntent(BaseModel):
    """plan_rollback 输入（service 内部）。"""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    target_preference_id: str


class PreferenceVersionPlan(BaseModel):
    """偏好版本规划结果（service 内部，仅业务计划，无持久化副作用）。

    字段为结构化审计引用（user_id / key / scope / id / version），不含正文/密钥。
    """

    model_config = ConfigDict(extra="forbid")

    action: PreferenceVersionAction
    reason_code: str
    user_id: str
    preference_key: str
    scope: str
    next_version: Optional[int] = None
    previous_version_id: Optional[str] = None
    current_preference_id: Optional[str] = None
    current_version: Optional[int] = None
    target_preference_id: Optional[str] = None
    target_version: Optional[int] = None
    coexist_with_scopes: List[str] = Field(default_factory=list)


class PreferenceVersionPolicy:
    """E 轨偏好版本变更规划策略入口（无状态、纯函数式、确定性）。

    plan_preference() / plan_rollback() 只读消费偏好记录，不修改
    current_preferences 或其任何 Preference 对象，不写库，不改 current_version，
    不读正文/实体敏感字段。
    """

    def plan_preference(
        self,
        intent: PreferenceVersionIntent,
        current_preferences: List[Preference],
    ) -> PreferenceVersionPlan:
        # 1. 类型准入（fail-closed 前置）
        if not isinstance(intent, PreferenceVersionIntent):
            return self._reject(
                REASON_REJECTED_INVALID_INPUT, intent.user_id if isinstance(
                    intent, BaseModel) else "", "", ""
            )
        # 2. 长期化门禁（D3 §7.9）：不可持久化候选不得产生 CREATE/UPDATE
        if intent.decision.should_store is not True:
            return self._reject(
                REASON_REJECTED_NOT_PERSISTABLE,
                intent.user_id, intent.preference_key, intent.scope,
            )
        # 3. 跨用户防御（D3 §7.1 用户隔离硬约束）
        if any(p.user_id != intent.user_id for p in current_preferences):
            return self._reject(
                REASON_REJECTED_CROSS_USER,
                intent.user_id, intent.preference_key, intent.scope,
            )
        # 3.5 版本意图与长期化决策 key/scope 一致性（fail-closed）：
        #     已通过 should_store=True 与同用户两道门禁后，decision 必须与
        #     intent 的 key/scope 指向同一业务偏好，否则拒绝，不得进入
        #     CREATE/COEXIST/UPDATE/NO_OP（防止"决策针对 A 偏好、版本写到 B"）。
        #     只消费结构化字段 candidate_key/scope，不读 value/evidence。
        decision = intent.decision
        if (
            not decision.candidate_key
            or decision.candidate_key != intent.preference_key
            or decision.scope != intent.scope.value
        ):
            return self._reject(
                REASON_REJECTED_INTENT_DECISION_INCONSISTENT,
                intent.user_id, intent.preference_key, intent.scope,
            )
        # 4. 查找同 key + 同 scope 的 active 当前版本
        current = self._find_active_same_key_scope(
            current_preferences, intent.user_id,
            intent.preference_key, intent.scope,
        )
        if current is not None:
            if current.preference_value == intent.value:
                # NO_OP：同 key+scope+value，不增版本
                return self._no_op(intent, current)
            # UPDATE：同 key+scope 值变化，版本递增，保留历史
            return self._update(intent, current)
        # 5. 同 key 不同 scope → COEXIST；否则 CREATE
        coexist_scopes = self._find_active_same_key_diff_scope_scopes(
            current_preferences, intent.user_id, intent.preference_key,
            intent.scope,
        )
        if coexist_scopes:
            return PreferenceVersionPlan(
                action=PreferenceVersionAction.COEXIST,
                reason_code=REASON_COEXIST_DIFFERENT_SCOPE,
                user_id=intent.user_id,
                preference_key=intent.preference_key,
                scope=intent.scope,
                next_version=1,
                previous_version_id=None,
                coexist_with_scopes=sorted(coexist_scopes),
            )
        return PreferenceVersionPlan(
            action=PreferenceVersionAction.CREATE,
            reason_code=REASON_CREATE_FIRST_VERSION,
            user_id=intent.user_id,
            preference_key=intent.preference_key,
            scope=intent.scope,
            next_version=1,
            previous_version_id=None,
        )

    def plan_rollback(
        self,
        intent: PreferenceRollbackIntent,
        current_preferences: List[Preference],
    ) -> PreferenceVersionPlan:
        # 1. 类型准入（fail-closed 前置）
        if not isinstance(intent, PreferenceRollbackIntent):
            return self._reject(
                REASON_REJECTED_INVALID_INPUT, intent.user_id if isinstance(
                    intent, BaseModel) else "", "", ""
            )
        # 2. target 存在性
        target = self._find_by_id(current_preferences, intent.target_preference_id)
        if target is None:
            return self._reject(
                REASON_REJECTED_ROLLBACK_TARGET_NOT_FOUND,
                intent.user_id, "", "",
            )
        # 3. 跨用户防御
        if target.user_id != intent.user_id or any(
            p.user_id != intent.user_id for p in current_preferences
        ):
            return self._reject(
                REASON_REJECTED_CROSS_USER, intent.user_id, target.preference_key,
                target.preference_scope.value,
            )
        # 4. 定位同 key+scope 的 active 当前版本
        current = self._find_active_same_key_scope(
            current_preferences, intent.user_id,
            target.preference_key, target.preference_scope.value,
        )
        if current is None:
            # target 自身链无 active。区分两种防御：
            # - 存在其他（不同 key/scope）active → target 属无关链版本；
            # - 集合在任何 active → 无活动版本链可回滚。
            if self._has_any_active(current_preferences, intent.user_id):
                return self._reject(
                    REASON_REJECTED_ROLLBACK_UNRELATED_VERSION,
                    intent.user_id, target.preference_key,
                    target.preference_scope.value,
                )
            return self._reject(
                REASON_REJECTED_NO_ACTIVE_CHAIN, intent.user_id,
                target.preference_key, target.preference_scope.value,
            )
        # 5. 无关版本二次防御（与 current 同 key+scope 已由步骤 4 保证，显式校验）
        if (
            target.preference_key != current.preference_key
            or target.preference_scope.value != current.preference_scope.value
        ):
            return self._reject(
                REASON_REJECTED_ROLLBACK_UNRELATED_VERSION,
                intent.user_id, target.preference_key, target.preference_scope.value,
            )
        # 6. 未来/当前版本防御：只能回滚到历史版本
        if target.version >= current.version:
            return self._reject(
                REASON_REJECTED_ROLLBACK_FUTURE_OR_CURRENT,
                intent.user_id, target.preference_key, target.preference_scope.value,
            )
        # 7. 通过：输出 ROLLBACK 计划（D 轨负责 current_version 切换与持久化）
        return PreferenceVersionPlan(
            action=PreferenceVersionAction.ROLLBACK,
            reason_code=REASON_ROLLBACK_TO_HISTORY_VERSION,
            user_id=intent.user_id,
            preference_key=target.preference_key,
            scope=target.preference_scope.value,
            current_preference_id=current.preference_id,
            current_version=current.version,
            target_preference_id=target.preference_id,
            target_version=target.version,
        )

    # ── 内部 helper（纯只读，不改动输入） ──

    @staticmethod
    def _find_by_id(preferences: List[Preference], preference_id: str) -> Optional[Preference]:
        for p in preferences:
            if p.preference_id == preference_id:
                return p
        return None

    @staticmethod
    def _has_any_active(preferences: List[Preference], user_id: str) -> bool:
        """该 user 是否存在任意 active 偏好记录（跨 key/scope）。"""
        return any(
            p.user_id == user_id and p.memory_status == MemoryStatus.ACTIVE
            for p in preferences
        )

    @staticmethod
    def _find_active_same_key_scope(
        preferences: List[Preference], user_id: str,
        key: str, scope: str,
    ) -> Optional[Preference]:
        """定位同 user_id + 同 key + 同 scope 的 active 记录（version 最大者）。

        正常数据同 key+scope 至多一个 active；若出现多个，取 version 最大者
        作为 current（合理防御，测试仅构造单个 active）。
        """
        candidates = [
            p for p in preferences
            if p.user_id == user_id
            and p.preference_key == key
            and p.preference_scope.value == scope
            and p.memory_status == MemoryStatus.ACTIVE
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.version)

    @staticmethod
    def _find_active_same_key_diff_scope_scopes(
        preferences: List[Preference], user_id: str,
        key: str, scope: str,
    ) -> List[str]:
        """收集同 user_id + 同 key 但 scope 不同的 active 记录之 scope 值。"""
        scopes = {
            p.preference_scope.value for p in preferences
            if p.user_id == user_id
            and p.preference_key == key
            and p.preference_scope.value != scope
            and p.memory_status == MemoryStatus.ACTIVE
        }
        return list(scopes)

    @staticmethod
    def _no_op(intent: PreferenceVersionIntent, current: Preference) -> PreferenceVersionPlan:
        return PreferenceVersionPlan(
            action=PreferenceVersionAction.NO_OP,
            reason_code=REASON_NO_OP_SAME_VALUE,
            user_id=intent.user_id,
            preference_key=intent.preference_key,
            scope=intent.scope,
            next_version=None,
            current_preference_id=current.preference_id,
            current_version=current.version,
        )

    @staticmethod
    def _update(intent: PreferenceVersionIntent, current: Preference) -> PreferenceVersionPlan:
        return PreferenceVersionPlan(
            action=PreferenceVersionAction.UPDATE,
            reason_code=REASON_UPDATE_VALUE_CHANGED,
            user_id=intent.user_id,
            preference_key=intent.preference_key,
            scope=intent.scope,
            next_version=current.version + 1,
            previous_version_id=current.preference_id,
            current_preference_id=current.preference_id,
            current_version=current.version,
        )

    @staticmethod
    def _reject(reason_code: str, user_id: str, key: str, scope: str) -> PreferenceVersionPlan:
        return PreferenceVersionPlan(
            action=PreferenceVersionAction.REJECTED,
            reason_code=reason_code,
            user_id=user_id,
            preference_key=key,
            scope=scope,
        )


__all__ = [
    "PreferenceVersionPolicy",
    "PreferenceVersionAction",
    "PreferenceVersionPlan",
    "PreferenceVersionIntent",
    "PreferenceRollbackIntent",
]
