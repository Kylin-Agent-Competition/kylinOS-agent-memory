"""
schemas.py — 轨道 A Day6 统一事件模型与清洗输出 Schema（Pydantic v2）

对齐基线：
- E 轨业务 Schema v0.1（docs/architecture/MEMORY_BUSINESS_SCHEMA_V0.1.md §3.1 MemorySourceEvent）
- 总体架构 v1 §6.2 数据质量流水线（六步）与 §6.1 统一事件模型

设计要点：
1. MemorySourceEvent 为外部输入模型（raw 事件），校验拒绝字段缺失/类型错误/未知高风险字段。
2. NormalizedEvent 为清洗后内部事件（时间/状态已标准化、敏感已标记、指纹已附）。
3. QualityScore 为六维质量评分（架构 6.2 第 5 步：completeness/validity/reliability/
   freshness/consistency/extractability）。
4. 全部 Pydantic v2（架构批准技术栈）；时间统一为 aware UTC ISO8601。

注：E 轨 Schema 中部分字段标注 UNVERIFIED（待 C 轨麒麟取证），本实现按 v0.1 冻结
字段结构落地，取值枚举对齐文档 §2 枚举编号；枚举后续随 E 轨 Schema 更新同步。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── 枚举（对齐 E 轨 Schema v0.1 §2 枚举编号） ──


class SourceType(str, Enum):
    """来源类型（§2.1 七值规范集合）。"""

    CHAT = "chat"
    TOOL_RESULT = "tool_result"
    MANUAL_CONFIG = "manual_config"
    RECOLLECT = "recollect"
    FILE = "file"
    MEETING = "meeting"
    VOICE = "voice"


class EventType(str, Enum):
    """事件消息粒度类型（§2.2，与 source_type 不同层级）。"""

    USER_MESSAGE = "user_message"
    AGENT_RESPONSE = "agent_response"
    SYSTEM_MESSAGE = "system_message"


class SourceBusinessStatus(str, Enum):
    """来源事件业务结果状态（§2.3）。"""

    RAW = "raw"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


class ProcessingStatus(str, Enum):
    """内部处理流水线状态（§2.4，技术候选）。"""

    PENDING = "pending"
    CLEANED = "cleaned"
    QUALITY_CHECKED = "quality_checked"
    EXTRACTED = "extracted"
    REJECTED = "rejected"


class MemoryType(str, Enum):
    """记忆类型（§2.7）。"""

    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"


class SensitivityLevel(str, Enum):
    """敏感度等级（§2.10）。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# 敏感等级顺序（用于等级比较，避免字典序陷阱）
_SENSITIVITY_ORDER = {
    SensitivityLevel.LOW: 0,
    SensitivityLevel.MEDIUM: 1,
    SensitivityLevel.HIGH: 2,
    SensitivityLevel.CRITICAL: 3,
}


class ConsentScope(str, Enum):
    """数据使用与遗忘同意范围。"""

    MEMORY_ONLY = "memory_only"
    MEMORY_AND_ANALYTICS = "memory_and_analytics"
    NONE = "none"


# ── 输入模型：MemorySourceEvent（E 轨 Schema v0.1 §3.1） ──

# 高敏字段正则（架构 6.2 第 3 步：API Key/Token/密码/私钥/手机号/身份证/敏感路径）
_SENSITIVE_PATTERNS: List[re.Pattern] = [
    re.compile(r"(?i)\b(api[_-]?key|secret|token|passwd|password|pwd|private[_-]?key)\b"),
    re.compile(r"\b[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\b"),  # JWT
    re.compile(r"\b1[3-9]\d{9}\b"),  # 中国大陆手机号
    re.compile(r"\b\d{17}[\dXx]\b"),  # 身份证
    re.compile(r"(?i)(/etc/passwd|/etc/shadow|\.ssh/|id_rsa|id_ed25519)"),  # 敏感路径（无 \b：/ 为非单词字符）
    re.compile(r"\b[A-Za-z0-9]{32,}\b"),  # 疑似长密钥（32+ 位）
]


class MemorySourceEvent(BaseModel):
    """来源事件（外部输入，E 轨 Schema v0.1 §3.1 字段落地）。

    校验策略（架构 6.2 第 1 步）：
    - 必填字段缺失 → ValidationError
    - 类型错误 → ValidationError
    - 未知高风险字段 → extra="forbid"（拒绝）
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    source_type: SourceType
    schema_version: str = "0.1"
    trace_id: Optional[str] = None
    event_type: EventType
    source_reference: Optional[str] = None
    consent_scope: ConsentScope = ConsentScope.MEMORY_ONLY
    idempotency_key: str = Field(min_length=1)
    source_business_status: SourceBusinessStatus = SourceBusinessStatus.RAW
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    memory_type: Optional[MemoryType] = None
    occurred_at: datetime
    captured_at: datetime
    session_id: str = Field(min_length=1)
    raw_payload_ref: Optional[str] = None
    content_summary: Optional[str] = None
    turn_id: Optional[str] = None
    tool_call_id: Optional[str] = None
    sensitivity: SensitivityLevel = SensitivityLevel.LOW
    is_sensitive_matched: bool = False
    requires_embedding: bool = True
    has_structured_payload: bool = False
    language_tag: Optional[str] = None

    # ── 触发条件校验（E 轨 Schema conditional 字段） ──

    @field_validator("turn_id")
    @classmethod
    def _turn_id_conditional(cls, v: Optional[str], info: Any) -> Optional[str]:
        event_type = info.data.get("event_type")
        if v is None and event_type in (EventType.USER_MESSAGE, EventType.AGENT_RESPONSE):
            # 宿主未提供 Turn 边界时为合法 optional；不强制（C 轨取证后收紧）
            return v
        return v

    @field_validator("tool_call_id")
    @classmethod
    def _tool_call_id_conditional(cls, v: Optional[str], info: Any) -> Optional[str]:
        source_type = info.data.get("source_type")
        if v is None and source_type == SourceType.TOOL_RESULT:
            raise ValueError(
                "tool_call_id required when source_type=tool_result (E 轨 Schema §3.1)")
        return v

    @field_validator("occurred_at", "captured_at")
    @classmethod
    def _time_aware_utc(cls, v: datetime) -> datetime:
        """时间统一为 aware UTC（架构 6.2 第 2 步：格式标准化）。"""
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


# ── 清洗输出：NormalizedEvent ──


class NormalizedEvent(BaseModel):
    """清洗后内部事件（确定性：同一输入多次清洗结果一致）。"""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    user_id: str
    actor_id: str
    source_type: SourceType
    schema_version: str
    trace_id: Optional[str]
    event_type: EventType
    source_reference: Optional[str]
    consent_scope: ConsentScope
    idempotency_key: str
    source_business_status: SourceBusinessStatus
    processing_status: ProcessingStatus = ProcessingStatus.CLEANED
    memory_type: Optional[MemoryType]
    occurred_at: datetime
    captured_at: datetime
    session_id: str
    raw_payload_ref: Optional[str]
    content_summary: Optional[str]
    turn_id: Optional[str]
    tool_call_id: Optional[str]
    sensitivity: SensitivityLevel
    is_sensitive_matched: bool
    requires_embedding: bool
    has_structured_payload: bool
    language_tag: Optional[str]
    content_fingerprint: Optional[str] = None  # 架构 6.2 第 4 步：内容指纹


# ── 质量评分：QualityScore（架构 6.2 第 5 步六维） ──


class QualityScore(BaseModel):
    """六维质量评分 + 进入提取的 Gate 判定。

    维度（0.0–1.0）：
    - completeness  完整性：必填/条件字段是否齐全
    - validity      有效性：字段值是否符合枚举/格式约束
    - reliability   可靠性：来源可信度基线（架构 6.3）
    - freshness     新鲜度：occurred_at 距 now 的时效（指数衰减）
    - consistency   一致性：内部字段交叉一致（如 event_type/source_type 组合）
    - extractability 可提取性：是否有可抽取的结构化载荷
    """

    model_config = ConfigDict(extra="forbid")

    completeness: float = Field(ge=0.0, le=1.0)
    validity: float = Field(ge=0.0, le=1.0)
    reliability: float = Field(ge=0.0, le=1.0)
    freshness: float = Field(ge=0.0, le=1.0)
    consistency: float = Field(ge=0.0, le=1.0)
    extractability: float = Field(ge=0.0, le=1.0)
    overall: float = Field(ge=0.0, le=1.0)
    eligible_for_extraction: bool = False  # 低质量事件不进入提取（架构 6.2 第 6 步）


class EventValidationError(Exception):
    """事件校验/清洗失败（结构化错误）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


# ── 工具函数 ──

_SOURCE_RELIABILITY: Dict[str, float] = {
    # 架构 6.3 来源可信度基线（TABLE 19 语义 → 0.0–1.0）
    "manual_config": 0.95,   # 用户显式配置：高
    "tool_result": 0.90,     # 真实 Tool 成功结果：高（失败/取消下调，见 quality.py）
    "chat": 0.45,            # 单次聊天表达：低-中
    "recollect": 0.30,       # Recollect OCR/行为：低
    "file": 0.50,            # 文件事件：中
    "meeting": 0.55,         # 会议事件：中
    "voice": 0.45,           # 语音事件：低-中
}

_MESSAGE_EXTRA: Dict[str, Any] = {}
