"""
knowledge.py — Day4 E 轨业务 Domain：Knowledge（结构化知识）Pydantic v2 模型

对齐 D3_MEMORY_BUSINESS_CONTRACT_V1.md §5.3（Knowledge 字段逐项处置）。
字段处置说明（D3）：
- memory_type：DEFERRED（分层边界/流转条件待 D，HD-SCHEMA-07），但字段业务语义已
  冻结（short/medium/long/ephemeral 四值）；为遵守「不得复制 pipeline.schemas 中
  当前实现正在使用的共享类型」约束，本模型从 pipeline.schemas 显式复用 MemoryType，
  不在 domain 包内重复定义。
- content_ref：DEFERRED（存储形态待 D），本模型仅承载引用字段，不设计存储布局。
- access_count / last_accessed_at：DEFERRED（统计窗口与精度待 D）。
- confidence_score：DEFERRED（量化模型待 A/E，HD-SCHEMA-03），只做 [0,1] 边界 +
  strict float 校验。
- is_outdated：REVISED（过渡字段），待 D/E 统一为 memory_status 后移除。

业务校验器（D3 已冻结语义）：
1. time_order：updated_at >= created_at。
2. access_consistency：last_accessed_at 若存在，不得早于 created_at。

本模型不设计 SQLite 或 Vector 字段布局（D3 §8.2 不可冻结项清单）。
*禁止模型生成字段（D3 §7.10）：user_id 必须由宿主侧业务事件/外部输入产出。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipeline.schemas import MemoryType  # 复用流水线既有共享枚举，不在 domain 重复定义

from .common import AwareDatetime, ConfidenceScore, NonEmptyStr
from .enums import KnowledgeType, MemoryStatus


class Knowledge(BaseModel):
    """结构化知识条目（E 轨 Domain 骨架，D3 §5.3 字段落地）。

    仅业务字段定义；不冻结 SQLite 存储布局、Vector 索引结构或 FTS5 分词策略
    （D3 §8.2、README 技术路线：Vector 可重建非真源）。

    Day8 结构化承载（TD-017 关闭）：模型新增六类结构化字段（conditions /
    evidence / steps / expected_result / problem / outcome / reproducible /
    template_body / parameters / priority / failure_reason / avoid_condition /
    alternative，共 13 个 Optional[str]），由 Candidate Governance 从
    KnowledgeCandidate 1:1 无损映射。全部可选、默认 None，向后兼容既有构造；
    且为已声明模型字段，不改变 extra="forbid" fail-closed 语义（未知字段仍拒绝）。
    """

    model_config = ConfigDict(extra="forbid")

    # ── D3 §5.3 FROZEN_BUSINESS_SEMANTIC / REVISED 必填字段 ──
    knowledge_id: NonEmptyStr
    user_id: NonEmptyStr  # 数据归属隔离键，*禁止模型生成（D3 §7.1/§7.10）
    knowledge_type: KnowledgeType
    memory_type: MemoryType  # 复用 pipeline.schemas.MemoryType（D3 §5.6 四值冻结）
    memory_status: MemoryStatus
    source_event_id: NonEmptyStr  # 关联 MemorySourceEvent.event_id（D3 §3.3）
    content_summary: NonEmptyStr  # 可检索摘要，须经敏感过滤（D3 §3.3/§7.7）
    confidence_score: ConfidenceScore
    requires_embedding: bool
    is_outdated: bool  # 过渡字段（D3 REVISED，待 D/E 移除）
    created_at: AwareDatetime
    updated_at: AwareDatetime

    # ── D3 §5.3 DEFERRED / FROZEN 可选字段 ──
    content_ref: Optional[str] = None  # DEFERRED：存储形态待 D
    primary_category: Optional[str] = None  # 开放分类标签，不得替代 knowledge_type
    language_tag: Optional[str] = None  # BCP 47
    superseded_by_id: Optional[str] = None  # 替代回溯（D3 §7.2）
    access_count: Optional[int] = Field(default=None, ge=0)  # DEFERRED：统计窗口待 D
    last_accessed_at: Optional[AwareDatetime] = None  # DEFERRED：统计窗口待 D
    extracted_entities: Optional[List[str]] = None

    # ── Day8 结构化承载（TD-017 关闭：六类结构化字段无损映射） ──
    # 全部 Optional[str]，默认 None；向后兼容（既有构造不提供这些字段时为 None）。
    # 与 KnowledgeCandidate 六类结构化字段完全同名，实现 1:1 直接映射、无转换、
    # 无改写。extra="forbid" 保持：这些为已声明字段，非静默接受未知字段。
    # 通用：适用条件
    conditions: Optional[str] = None
    # 通用：证据（R3 系统可信来源，非 LLM 自述）
    evidence: Optional[str] = None
    # workflow：步骤 / 流程
    steps: Optional[str] = None
    # workflow：期望结果
    expected_result: Optional[str] = None
    # case：问题
    problem: Optional[str] = None
    # case：结果
    outcome: Optional[str] = None
    # case：是否复现
    reproducible: Optional[str] = None
    # template：模板正文
    template_body: Optional[str] = None
    # template：参数
    parameters: Optional[str] = None
    # constraint：优先级
    priority: Optional[str] = None
    # failure_experience：失败原因
    failure_reason: Optional[str] = None
    # failure_experience：避免条件
    avoid_condition: Optional[str] = None
    # failure_experience：替代方案
    alternative: Optional[str] = None

    @model_validator(mode="after")
    def _time_order(self) -> "Knowledge":
        """时间顺序：updated_at 不得早于 created_at。"""
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be >= created_at")
        return self

    @model_validator(mode="after")
    def _access_consistency(self) -> "Knowledge":
        """访问时间一致性：last_accessed_at 若存在，不得早于 created_at。"""
        if self.last_accessed_at is not None and self.last_accessed_at < self.created_at:
            raise ValueError("last_accessed_at must be >= created_at")
        return self