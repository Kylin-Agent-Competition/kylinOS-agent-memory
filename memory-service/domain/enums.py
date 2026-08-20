"""
enums.py — Day4 E 轨业务 Domain 公共枚举（Pydantic v2 友好 str, Enum）

对齐来源：
- D3_MEMORY_BUSINESS_CONTRACT_V1.md §5.6（13 组候选枚举处置，FROZEN_BUSINESS_SEMANTIC 值冻结）
- D3_MEMORY_SECURITY_ACCEPTANCE_V1.md（安全红线；*禁止模型生成 字段不在此处承载取值）
- MEMORY_BUSINESS_SCHEMA_V0.1.md §2（候选枚举的来源基准，仅补充字段来源，不覆盖 D3 决议）

范围边界：
- 本文件只定义 E 轨四个核心业务对象（Preference / Knowledge / Conflict / ForgetPlan）
  直接服务的公共枚举。
- MemoryType（short_term/medium_term/long_term/ephemeral）已在
  memory-service/pipeline/schemas.py 中定义且被现有流水线使用，禁止在本包重复定义；
  domain/knowledge.py 通过 `from pipeline.schemas import MemoryType` 显式复用。
- 不得在此定义 MemorySourceEvent / NormalizedEvent / PreferenceCandidate /
  KnowledgeCandidate 等流水线/Provider 共享类型的第二套同名实现。
"""

from __future__ import annotations

from enum import Enum


class ExpressionType(str, Enum):
    """偏好表达类型（D3 §5.6 expression_type：explicit/implicit 二值冻结）。

    依据 D3 契约：修订2 已将 inferred 归一为 implicit，candidate 不作为表达类型值，
    候选偏好状态由 memory_status=candidate 承载（D3 §5.6 / §6 REJECTED 项）。
    """

    EXPLICIT = "explicit"
    IMPLICIT = "implicit"


class PreferenceScope(str, Enum):
    """偏好作用域（D3 §5.6 preference_scope 五值冻结）。

    全局/主题/工具/会话/时间窗口五值业务语义冻结；与 A Provider 前向草稿
    `scope` 取值差异不在此处固化（D3 契约九、跨文档冲突登记 C-05）。
    """

    GLOBAL = "global"
    TOPIC = "topic"
    TOOL = "tool"
    SESSION = "session"
    TIME_WINDOW = "time_window"


class KnowledgeType(str, Enum):
    """知识子类型（D3 §5.6 knowledge_type 六值冻结）。

    primary_category 为开放业务分类标签，不得替代 knowledge_type（D3 §3.3/§5.3）。
    """

    WORKFLOW = "workflow"
    CASE = "case"
    TEMPLATE = "template"
    FACT = "fact"
    CONSTRAINT = "constraint"
    FAILURE_EXPERIENCE = "failure_experience"


class MemoryStatus(str, Enum):
    """记忆统一生命周期状态（D3 §5.6 memory_status 六值冻结，唯一优先字段）。

    is_active/is_outdated/should_decay 等布尔字段为过渡字段，待 D/E 统一后移除
    （D3 §3.6 Lifecycle、§7.4、HD-SCHEMA-13）。candidate 不参与用户级检索与冲突判定。
    """

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"
    EXPIRED = "expired"
    REMOVED = "removed"
    CANDIDATE = "candidate"


class ConflictType(str, Enum):
    """冲突类型（D3 §5.6 conflict_type 五值冻结）。

    contradiction/temporal_inconsistency 的判定阈值算法属 B 轨道实现层，
    本任务不实现任何冲突判定逻辑（D3 §5.4 REJECTED → DEFERRED，HD-SCHEMA-04）。
    """

    CONTRADICTION = "contradiction"
    TEMPORAL_INCONSISTENCY = "temporal_inconsistency"
    SOURCE_CONFLICT = "source_conflict"
    PREFERENCE_CONFLICT = "preference_conflict"
    SCOPE_AMBIGUITY = "scope_ambiguity"


class ResolutionStatus(str, Enum):
    """冲突消解状态（D3 §5.6 resolution_status 六值冻结）。

    最终结果值（resolved_auto/resolved_manual/unresolvable）*禁止模型生成，
    必须由消解规则引擎或系统计算产出（D3 §7.10、SEC-LLM-04）。
    """

    DETECTED = "detected"
    ANALYZING = "analyzing"
    RESOLVED_AUTO = "resolved_auto"
    RESOLVED_MANUAL = "resolved_manual"
    DEFERRED = "deferred"
    UNRESOLVABLE = "unresolvable"


class ForgetMode(str, Enum):
    """遗忘模式/粒度（D3 §5.6 forget_mode 五值冻结）。

    full_reset 安全边界待 E/D 确认（HD-SCHEMA-06）；本任务不实现任何遗忘执行逻辑。
    """

    SINGLE_ITEM = "single_item"
    SESSION = "session"
    TOPIC = "topic"
    TIME_WINDOW = "time_window"
    FULL_RESET = "full_reset"


class ForgetPlanStatus(str, Enum):
    """遗忘计划执行状态（D3 §5.5 status 七值冻结，SEC-FORGET-02 状态机）。

    状态机：pending→previewing→awaiting_confirmation→executing→
    completed/failed/rolled_back；本任务只定义取值，不实现状态机流转。
    """

    PENDING = "pending"
    PREVIEWING = "previewing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class TargetType(str, Enum):
    """遗忘目标业务类型（D3 §5.5 target_type 四值冻结）。"""

    KNOWLEDGE = "knowledge"
    PREFERENCE = "preference"
    EVENT = "event"
    ALL = "all"