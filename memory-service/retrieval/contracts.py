"""B 轨 `vector-retrieval/v1` 最小契约类型（Pydantic v2）。

本模块只定义服务内部的契约数据结构与纯函数，不包含：
- 真实 Vector SDK 调用；
- SQLite / FTS5 / Collection 物理 Schema；
- Gateway / IPC / Outbox / Alembic 实现；
- 生产检索、索引写入、部署或发布行为。

字段语义以 `docs/day3/08_vector_retrieval_contract_v1.md` 为唯一依据。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Generic, List, Literal, Optional, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    StrictInt,
    StrictStr,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

CONTRACT_VERSION = "vector-retrieval/v1"


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime 必须带时区（UTC）")
    return value.astimezone(timezone.utc)


def _finite_floats(value: list[float]) -> list[float]:
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)):
            raise ValueError("向量元素必须是有限实数")
    return [float(item) for item in value]


FiniteFloatList = Annotated[List[float], AfterValidator(_finite_floats)]

_DIGEST_RE = re.compile(r"^hmac-sha256:([A-Za-z0-9_-]{1,64}):([0-9a-f]{64})$")


def _validate_digest(value: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.match(value):
        raise ValueError("Digest 必须是 `hmac-sha256:<key_id>:<64 lowercase hex>`")
    return value


Digest = Annotated[str, AfterValidator(_validate_digest)]


# ── 枚举（08 §5-§10） ──


class ScopeKind(str, Enum):
    GLOBAL = "global"
    USER = "user"
    SHARD = "shard"


class WatermarkKind(str, Enum):
    MONOTONIC_INT = "monotonic_int"
    FIXED_WIDTH_LEX = "fixed_width_lex"


class EvidenceLevel(str, Enum):
    HOST_VERIFIED = "host_verified"
    ABI_VERIFIED = "abi_verified"
    UNTESTED = "untested"


class Availability(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class ScoreSemantics(str, Enum):
    BM25 = "bm25"
    SDK_SCORE_UNVERIFIED = "sdk_score_unverified"


class Channel(str, Enum):
    FTS5 = "fts5"
    VECTOR = "vector"


class ObjectType(str, Enum):
    PREFERENCE = "preference"
    KNOWLEDGE = "knowledge"


class IndexStatus(str, Enum):
    UNAVAILABLE = "unavailable"
    EMPTY = "empty"
    BUILDING = "building"
    READY = "ready"
    DEGRADED = "degraded"
    STALE = "stale"
    FAILED = "failed"


class Outcome(str, Enum):
    APPLIED = "applied"
    NO_OP = "no_op"
    PARTIAL = "partial"
    OUTCOME_UNKNOWN = "outcome_unknown"


class ActivationMode(str, Enum):
    ATOMIC_SWITCH = "atomic_switch"
    MAINTENANCE_WINDOW = "maintenance_window"
    ROUTING_SWITCH = "routing_switch"


class RebuildReason(str, Enum):
    BOOTSTRAP = "bootstrap"
    SCHEMA_CHANGE = "schema_change"
    REPAIR = "repair"
    FULL_RESET = "full_reset"


class SelectionMode(str, Enum):
    SINGLE_ITEM = "single_item"
    RESOLVED_BATCH = "resolved_batch"
    FULL_RESET = "full_reset"


class ConfirmationMode(str, Enum):
    EXPLICIT = "explicit"
    POLICY_EXEMPT = "policy_exempt"


class ResolvedBy(str, Enum):
    DETERMINISTIC_RULE_ENGINE = "deterministic_rule_engine"
    SYSTEM = "system"


class ContentSource(str, Enum):
    SQLITE_CURRENT = "sqlite_current"
    SQLITE_SAFE_SUMMARY = "sqlite_safe_summary"


class RetrievalErrorCode(str, Enum):
    INVALID_ARGUMENT = "invalid_argument"
    DIMENSION_MISMATCH = "dimension_mismatch"
    USER_SCOPE_VIOLATION = "user_scope_violation"
    AUTHORIZATION_DENIED = "authorization_denied"
    AUTHORIZATION_EXPIRED = "authorization_expired"
    DIGEST_KEY_UNAVAILABLE = "digest_key_unavailable"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    CANCELLED = "cancelled"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_NOT_READY = "provider_not_ready"
    PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"
    STALE_INDEX = "stale_index"
    CONFLICT = "conflict"
    INTERNAL = "internal"


class UTCBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── 5.6.1 canonical-json/v1 与 Digest ──


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _assert_json_number(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("canonical-json 禁止 NaN / Inf")
    if value == 0.0 and math.copysign(1.0, value) < 0:
        raise ValueError("canonical-json 禁止负零")
    return value


def _jcs_float(value: float) -> str:
    """按 RFC 8785 引用的 ECMAScript 数字格式序列化有限浮点数。"""

    _assert_json_number(value)
    negative = value < 0
    text = repr(abs(value)).lower()

    if "e" not in text:
        if text.endswith(".0"):
            text = text[:-2]
        return f"-{text}" if negative else text

    mantissa, exponent_text = text.split("e", 1)
    exponent = int(exponent_text)
    absolute = abs(value)
    if 1e-6 <= absolute < 1e21:
        integer, dot, fraction = mantissa.partition(".")
        digits = integer + (fraction if dot else "")
        decimal_index = len(integer) + exponent
        if decimal_index <= 0:
            text = "0." + ("0" * -decimal_index) + digits
        elif decimal_index >= len(digits):
            text = digits + ("0" * (decimal_index - len(digits)))
        else:
            text = digits[:decimal_index] + "." + digits[decimal_index:]
    else:
        if mantissa.endswith(".0"):
            mantissa = mantissa[:-2]
        exponent_sign = "+" if exponent >= 0 else "-"
        text = f"{mantissa}e{exponent_sign}{abs(exponent)}"

    return f"-{text}" if negative else text


def _json_string(value: str) -> str:
    normalized = _nfc(value)
    if any(0xD800 <= ord(char) <= 0xDFFF for char in normalized):
        raise ValueError("canonical-json 禁止孤立 UTF-16 surrogate")
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def canonical_json_v1(value: Any, set_paths: tuple[str, ...] = ()) -> str:
    """按 RFC 8785/JCS 生成规范 JSON。

    `set_paths` 用点分路径指定“集合语义数组”，命中的数组先去重再按规范
    JSON 字节序排序；其余数组保持业务顺序。字符串统一 NFC。
    """

    def serialize(node: Any, path: str = "") -> str:
        if isinstance(node, str):
            return _json_string(node)
        if isinstance(node, bool):
            return "true" if node else "false"
        if node is None:
            return "null"
        if isinstance(node, int):
            return str(node)
        if isinstance(node, float):
            return _jcs_float(node)
        if isinstance(node, list):
            is_set = path in set_paths
            items = [serialize(item, path) for item in node]
            if is_set:
                items = sorted(set(items), key=lambda item: item.encode("utf-8"))
            return "[" + ",".join(items) + "]"
        if isinstance(node, dict):
            normalized: dict[str, Any] = {}
            for key, item in node.items():
                if not isinstance(key, str):
                    raise ValueError("canonical-json 对象键必须是字符串")
                normalized_key = _nfc(key)
                if normalized_key in normalized:
                    raise ValueError("canonical-json 对象键 NFC 规范化后冲突")
                normalized[normalized_key] = item
            ordered_keys = sorted(normalized, key=lambda key: key.encode("utf-16-be"))
            pairs = []
            for key in ordered_keys:
                child_path = f"{path}.{key}" if path else key
                pairs.append(f"{_json_string(key)}:{serialize(normalized[key], child_path)}")
            return "{" + ",".join(pairs) + "}"
        raise ValueError(f"canonical-json 不支持类型: {type(node)!r}")

    return serialize(value)


def digest_from_canonical(key_id: str, key: bytes, canonical_value: Any, set_paths: tuple[str, ...] = ()) -> str:
    canonical = canonical_value if isinstance(canonical_value, str) else canonical_json_v1(canonical_value, set_paths)
    payload = canonical.encode("utf-8")
    digest = hmac.new(key, payload, hashlib.sha256).hexdigest()
    return f"hmac-sha256:{key_id}:{digest}"


# ── 5.2 IndexScope / ScopeAuthorization ──


class IndexScope(UTCBaseModel):
    scope_id: str = Field(min_length=1)
    kind: ScopeKind
    user_id: Optional[str] = None
    shard_id: Optional[str] = None
    scope_fingerprint: Digest

    @model_validator(mode="after")
    def _check_scope_binding(self) -> "IndexScope":
        if self.kind is ScopeKind.GLOBAL:
            if self.user_id is not None or self.shard_id is not None:
                raise ValueError("global scope 不允许 user_id/shard_id")
        elif self.kind is ScopeKind.USER:
            if not self.user_id or self.shard_id is not None:
                raise ValueError("user scope 必须 user_id 且不得 shard_id")
        else:  # shard
            if not self.shard_id or self.user_id is not None:
                raise ValueError("shard scope 必须 shard_id 且不得 user_id")
        return self


class ScopeAuthorization(UTCBaseModel):
    actor_ref: str = Field(min_length=1)
    authorization_ref: str = Field(min_length=1)
    scope_id: str = Field(min_length=1)
    allowed_operations: List[Literal["get_index_state", "rebuild"]] = Field(min_length=1)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


# ── 5.6.3 Watermark ──


class WatermarkDomain(UTCBaseModel):
    scope_id: str = Field(min_length=1)
    stream: str = Field(min_length=1)
    partition: str = Field(min_length=1)
    source_generation: str = Field(min_length=1)


class Watermark(UTCBaseModel):
    domain: WatermarkDomain
    kind: WatermarkKind
    value: StrictInt | StrictStr

    @model_validator(mode="after")
    def _check_value_matches_kind(self) -> "Watermark":
        if self.kind is WatermarkKind.MONOTONIC_INT:
            if type(self.value) is not int or self.value < 0:
                raise ValueError("monotonic_int 水位必须是真正的非负整数")
        elif type(self.value) is not str or not self.value.isascii():
            raise ValueError("fixed_width_lex 水位必须是真正的 ASCII 字符串")
        return self

    def compare(self, other: "Watermark") -> Literal[-1, 0, 1]:
        if self.domain != other.domain or self.kind is not other.kind:
            raise ValueError("跨 domain/kind 不得比较水位")
        if self.kind is WatermarkKind.MONOTONIC_INT:
            left, right = self.value, other.value
        else:
            left, right = self.value, other.value
            if len(left) != len(right):
                raise ValueError("fixed_width_lex 要求同 domain 下等宽 ASCII")
            left, right = left.encode("ascii"), right.encode("ascii")
        if left < right:
            return -1
        if left > right:
            return 1
        return 0


# ── 5.4 RetrievalError ──


class RetrievalError(UTCBaseModel):
    code: RetrievalErrorCode
    message: str = Field(min_length=1)
    retryable: bool = False
    stage: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


T = TypeVar("T")


class ProviderResult(UTCBaseModel, Generic[T]):
    ok: bool
    value: Optional[T] = None
    error: Optional[RetrievalError] = None
    partial: bool = False
    provider: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    elapsed_ms: int = Field(ge=0)
    completed_at: datetime

    @field_validator("completed_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)

    @model_validator(mode="after")
    def _check_ok_value(self) -> "ProviderResult":
        if self.ok:
            if self.value is None or self.error is not None:
                raise ValueError("ok=true 时 value 必填且 error 为空")
        else:
            if self.error is None:
                raise ValueError("ok=false 时 error 必填")
            if self.value is not None and not self.partial:
                raise ValueError("ok=false 且非 partial 时 value 必须为空")
        return self


# ── 6.2 VectorCapabilities ──


class VectorCapabilities(UTCBaseModel):
    provider: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    dimension: int = Field(gt=0)
    score_semantics: ScoreSemantics = ScoreSemantics.SDK_SCORE_UNVERIFIED
    supports_scalar_filter: bool
    supports_delete: bool
    supports_rebuild: bool
    supports_atomic_generation_switch: bool = False
    max_top_n: Optional[int] = Field(default=None, ge=1)
    evidence_level: EvidenceLevel
    availability: Availability
    availability_checked_at: datetime

    @field_validator("availability_checked_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


# ── 6.3 Upsert ──


class VectorRecord(UTCBaseModel):
    memory_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    vector: FiniteFloatList
    object_type: ObjectType
    memory_type: Optional[str] = None
    scene_id: Optional[str] = None
    scope_terms: dict[str, List[str]] = Field(default_factory=dict)
    index_text_hash: Digest


class VectorUpsertRequest(UTCBaseModel):
    contract_version: Literal["vector-retrieval/v1"] = CONTRACT_VERSION
    request_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    deadline_at: datetime
    idempotency_key: str = Field(min_length=1)
    payload_hash: Digest
    index_generation: str = Field(min_length=1)
    source_watermark: Watermark
    records: List[VectorRecord] = Field(min_length=1)

    @field_validator("deadline_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


class VectorUpsertRejection(UTCBaseModel):
    memory_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class VectorUpsertResult(UTCBaseModel):
    accepted_count: int = Field(ge=0)
    upserted_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)
    rejected: List[VectorUpsertRejection] = Field(default_factory=list)
    index_generation: str = Field(min_length=1)
    applied_watermark: Watermark
    outcome: Outcome


# ── 7 RetrievalFilter ──


class SceneFilter(UTCBaseModel):
    allowed_scene_ids: List[str] = Field(default_factory=list)
    include_unscoped: bool = False

    @field_validator("allowed_scene_ids")
    @classmethod
    def _dedupe_sorted(cls, value: list[str]) -> list[str]:
        return sorted(set(value))


class RetrievalFilter(UTCBaseModel):
    user_id: str = Field(min_length=1)
    scene: SceneFilter = Field(default_factory=SceneFilter)
    scope_terms: dict[str, List[str]] = Field(default_factory=dict)
    object_types: List[ObjectType] = Field(min_length=1)
    memory_types: List[str] = Field(default_factory=list)
    allowed_memory_statuses: List[str] = Field(default_factory=list)
    allowed_sensitivity: List[str] = Field(default_factory=list)
    conflict_policy: str = Field(min_length=1)
    as_of: datetime

    @field_validator("as_of")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


# ── 8 RetrievalHit / 9 RetrievalCandidate ──


class RetrievalHit(UTCBaseModel):
    memory_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    channel: Channel
    rank: StrictInt = Field(gt=0)
    raw_score: Optional[float] = None
    score_semantics: ScoreSemantics
    provider: str = Field(min_length=1)
    index_generation: Optional[str] = None
    retrieved_at: datetime
    filter_fingerprint: Digest
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @field_validator("retrieved_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)

    @field_validator("raw_score")
    @classmethod
    def _finite_score(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and not math.isfinite(value):
            raise ValueError("raw_score 必须有限")
        return value


class RetrievalCandidate(UTCBaseModel):
    memory_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    object_type: ObjectType
    user_id: str = Field(min_length=1)
    memory_type: Optional[str] = None
    memory_status: str = Field(min_length=1)
    scene_id: Optional[str] = None
    scope_terms: dict[str, List[str]] = Field(default_factory=dict)
    content: str = Field(min_length=1)
    content_source: ContentSource
    channels: List[Channel] = Field(min_length=1)
    ranks: dict[str, int]
    raw_scores: dict[str, Optional[float]] = Field(default_factory=dict)
    score_semantics: dict[str, ScoreSemantics] = Field(default_factory=dict)
    rrf_score: float
    final_score: float
    sensitivity: str = Field(min_length=1)
    conflict_state: str = Field(min_length=1)
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    estimated_tokens: int = Field(ge=0)
    explanation: dict[str, Any] = Field(default_factory=dict)

    @field_validator("rrf_score", "final_score")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("分数必须有限")
        return value


# ── 6.4 Search ──


class IndexStateSummary(UTCBaseModel):
    provider: str = Field(min_length=1)
    scope_id: str = Field(min_length=1)
    status: IndexStatus
    is_queryable: bool
    serving_generation: Optional[str] = None


class VectorSearchRequest(UTCBaseModel):
    contract_version: Literal["vector-retrieval/v1"] = CONTRACT_VERSION
    request_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    deadline_at: datetime
    query_vector: FiniteFloatList
    filter: RetrievalFilter
    top_n: int = Field(gt=0)
    required_generation: Optional[str] = None

    @field_validator("deadline_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


class VectorSearchResult(UTCBaseModel):
    hits: List[RetrievalHit] = Field(default_factory=list)
    index_state: Optional[IndexStateSummary] = None
    raw_hit_count: int = Field(ge=0)
    valid_hit_count: int = Field(ge=0)
    dropped_hit_count: int = Field(ge=0)
    partial: bool = False
    degraded_reason: Optional[str] = None
    filter_fingerprint: Digest


# ── 6.5 Delete ──


class DeleteExemption(UTCBaseModel):
    code: Literal["committed_forget_cleanup"] = "committed_forget_cleanup"
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    decision_ref: str = Field(min_length=1)


class ResolvedDeleteSelector(UTCBaseModel):
    user_id: str = Field(min_length=1)
    memory_ids: List[str] = Field(min_length=1)
    version_ids: Optional[List[str]] = None
    selection_mode: SelectionMode
    selection_hash: Digest
    resolved_by: ResolvedBy
    preview_ref: str = Field(min_length=1)
    preview_hash: Digest
    confirmation_mode: ConfirmationMode
    confirmation_ref: Optional[str] = None
    exemption: Optional[DeleteExemption] = None

    @model_validator(mode="after")
    def _check_confirmation(self) -> "ResolvedDeleteSelector":
        if self.confirmation_mode is ConfirmationMode.EXPLICIT:
            if not self.confirmation_ref or self.exemption is not None:
                raise ValueError("explicit 模式要求 confirmation_ref 且不得 exemption")
        else:  # policy_exempt
            if self.confirmation_ref is not None or self.exemption is None:
                raise ValueError("policy_exempt 模式要求 exemption 且不得 confirmation_ref")
            if self.selection_mode is not SelectionMode.SINGLE_ITEM or len(self.memory_ids) != 1 or not self.version_ids or len(self.version_ids) != 1:
                raise ValueError("policy_exempt 仅允许 single_item")
        if self.selection_mode is SelectionMode.SINGLE_ITEM and (len(self.memory_ids) != 1 or not self.version_ids or len(self.version_ids) != 1):
            raise ValueError("single_item 必须恰好一个 memory_id 和一个 version_id")
        return self


class VectorDeleteRequest(UTCBaseModel):
    contract_version: Literal["vector-retrieval/v1"] = CONTRACT_VERSION
    request_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    deadline_at: datetime
    idempotency_key: str = Field(min_length=1)
    payload_hash: Digest
    index_generation: str = Field(min_length=1)
    source_watermark: Watermark
    selector: ResolvedDeleteSelector
    authorization_ref: Optional[str] = None

    @field_validator("deadline_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


class VectorDeleteRejection(UTCBaseModel):
    memory_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class VectorDeleteResult(UTCBaseModel):
    matched_count: int = Field(ge=0)
    deleted_count: int = Field(ge=0)
    not_matched_ids: List[str] = Field(default_factory=list)
    rejected: List[VectorDeleteRejection] = Field(default_factory=list)
    index_generation: str = Field(min_length=1)
    applied_watermark: Watermark
    outcome: Outcome


# ── 6.6 Rebuild ──


class VectorRebuildRequest(UTCBaseModel):
    contract_version: Literal["vector-retrieval/v1"] = CONTRACT_VERSION
    request_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    deadline_at: datetime
    idempotency_key: str = Field(min_length=1)
    payload_hash: Digest
    source_snapshot_id: str = Field(min_length=1)
    source_watermark: Watermark
    target_generation: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    reason: RebuildReason
    scope: IndexScope
    scope_authorization: ScopeAuthorization

    @field_validator("deadline_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


class VectorRebuildResult(UTCBaseModel):
    scope: IndexScope
    target_generation: str = Field(min_length=1)
    source_snapshot_id: str = Field(min_length=1)
    source_watermark: Watermark
    read_count: int = Field(ge=0)
    indexed_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    rejection_reasons: List[str] = Field(default_factory=list)
    verified: bool
    activated: bool
    activation_mode: ActivationMode
    previous_generation: Optional[str] = None
    outcome: Outcome


# ── 6.7 get_index_state / 10 IndexState ──


class IndexStateRequest(UTCBaseModel):
    contract_version: Literal["vector-retrieval/v1"] = CONTRACT_VERSION
    request_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    scope: IndexScope
    scope_authorization: ScopeAuthorization
    required_watermark: Optional[Watermark] = None
    deadline_at: datetime

    @field_validator("deadline_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


class IndexState(UTCBaseModel):
    provider: str = Field(min_length=1)
    scope: IndexScope
    status: IndexStatus
    is_queryable: bool
    schema_version: str = Field(min_length=1)
    serving_generation: Optional[str] = None
    building_generation: Optional[str] = None
    source_snapshot_id: Optional[str] = None
    applied_watermark: Optional[Watermark] = None
    required_watermark: Optional[Watermark] = None
    record_count: Optional[int] = Field(default=None, ge=0)
    pending_count: Optional[int] = Field(default=None, ge=0)
    stale_count: Optional[int] = Field(default=None, ge=0)
    last_success_at: Optional[datetime] = None
    last_checked_at: datetime
    last_error: Optional[RetrievalError] = None
    evidence_level: EvidenceLevel
    availability: Availability

    @field_validator("last_success_at", "last_checked_at")
    @classmethod
    def _utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return _ensure_utc(value) if value is not None else None


__all__ = [
    "CONTRACT_VERSION",
    "canonical_json_v1",
    "digest_from_canonical",
    "ScopeKind",
    "WatermarkKind",
    "EvidenceLevel",
    "Availability",
    "ScoreSemantics",
    "Channel",
    "ObjectType",
    "IndexStatus",
    "Outcome",
    "ActivationMode",
    "RebuildReason",
    "SelectionMode",
    "ConfirmationMode",
    "ResolvedBy",
    "ContentSource",
    "RetrievalErrorCode",
    "Digest",
    "IndexScope",
    "ScopeAuthorization",
    "WatermarkDomain",
    "Watermark",
    "RetrievalError",
    "ProviderResult",
    "VectorCapabilities",
    "VectorRecord",
    "VectorUpsertRequest",
    "VectorUpsertRejection",
    "VectorUpsertResult",
    "SceneFilter",
    "RetrievalFilter",
    "RetrievalHit",
    "RetrievalCandidate",
    "IndexStateSummary",
    "VectorSearchRequest",
    "VectorSearchResult",
    "DeleteExemption",
    "ResolvedDeleteSelector",
    "VectorDeleteRequest",
    "VectorDeleteRejection",
    "VectorDeleteResult",
    "VectorRebuildRequest",
    "VectorRebuildResult",
    "IndexStateRequest",
    "IndexState",
]
