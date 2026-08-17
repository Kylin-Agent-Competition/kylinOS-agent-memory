"""B 轨 Provider 输入与状态校验纯函数（`docs/day3/08` §6/§7/§10，`09` T 条目）。

只做可本地复现的校验，不依赖 SDK / SQLite / 麒麟宿主。
"""

from __future__ import annotations

import math
from typing import Any, Optional

from retrieval.contracts import (
    ActivationMode,
    IndexState,
    IndexStatus,
    ObjectType,
    RetrievalErrorCode,
    RetrievalFilter,
)

_SENSITIVE_LOG_KEYS = {
    "content",
    "body",
    "text",
    "credential",
    "credentials",
    "password",
    "token",
    "secret",
    "api_key",
    "user_id",
    "user",
    "query_vector",
    "vector",
}

_WILDCARD_USERS = {"all", "*", "any"}


def validate_vector(vector: list[float], dimension: int) -> list[float]:
    """校验向量维度与有限性；返回 float 列表。"""
    if len(vector) != dimension:
        raise ValueError(RetrievalErrorCode.DIMENSION_MISMATCH.value)
    for item in vector:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)):
            raise ValueError(RetrievalErrorCode.INVALID_ARGUMENT.value)
    return [float(item) for item in vector]


def validate_top_n(top_n: int, max_top_n: Optional[int] = None) -> int:
    if top_n <= 0:
        raise ValueError(RetrievalErrorCode.INVALID_ARGUMENT.value)
    if max_top_n is not None and top_n > max_top_n:
        raise ValueError(RetrievalErrorCode.INVALID_ARGUMENT.value)
    return top_n


def validate_finite_score(score: Optional[float]) -> Optional[float]:
    if score is not None and not math.isfinite(score):
        raise ValueError(RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR.value)
    return score


def validate_object_memory_type(object_type: ObjectType, memory_type: Optional[str]) -> Optional[str]:
    """`memory_type` 不得复用作对象判别（preference/knowledge 属于 object_type）。"""
    if object_type not in (ObjectType.PREFERENCE, ObjectType.KNOWLEDGE):
        raise ValueError(RetrievalErrorCode.INVALID_ARGUMENT.value)
    if memory_type in {"preference", "knowledge"}:
        raise ValueError(RetrievalErrorCode.INVALID_ARGUMENT.value)
    return memory_type


def validate_retrieval_filter(
    flt: RetrievalFilter,
    allowed_scope_term_keys: frozenset[str],
    max_scope_terms_length: int = 32,
) -> RetrievalFilter:
    """校验 typed filter：user_id 非空非通配、scope_terms 键受控、值数组限长。"""
    if not flt.user_id or flt.user_id.lower() in _WILDCARD_USERS:
        raise ValueError(RetrievalErrorCode.USER_SCOPE_VIOLATION.value)
    for key, values in flt.scope_terms.items():
        if key not in allowed_scope_term_keys:
            raise ValueError(RetrievalErrorCode.INVALID_ARGUMENT.value)
        if len(values) > max_scope_terms_length:
            raise ValueError(RetrievalErrorCode.INVALID_ARGUMENT.value)
    if not flt.object_types:
        raise ValueError(RetrievalErrorCode.INVALID_ARGUMENT.value)
    return flt


def resolve_activation_mode(supports_atomic: bool, requested: ActivationMode) -> ActivationMode:
    """未取得原子切换宿主证据时不得选择 `atomic_switch`。"""
    if requested is ActivationMode.ATOMIC_SWITCH and not supports_atomic:
        raise ValueError(RetrievalErrorCode.INVALID_ARGUMENT.value)
    return requested


def validate_index_state(state: IndexState) -> IndexState:
    """校验 `IndexState` 的关键不变量（不改变传入对象）。"""
    if state.status is IndexStatus.READY:
        if not state.serving_generation or not state.schema_version or state.applied_watermark is None:
            raise ValueError(RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR.value)
    if state.status is IndexStatus.EMPTY:
        if state.record_count != 0:
            raise ValueError(RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR.value)
    if state.status in (IndexStatus.UNAVAILABLE, IndexStatus.FAILED) and state.is_queryable:
        raise ValueError(RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR.value)
    return state


def sensitive_log_keys(value: Any) -> list[str]:
    """返回日志结构里命中的敏感键（正文、凭据、跨用户明文）。"""
    found: list[str] = []
    if isinstance(value, dict):
        for key, sub in value.items():
            if str(key).lower() in _SENSITIVE_LOG_KEYS:
                found.append(str(key))
            found.extend(sensitive_log_keys(sub))
    elif isinstance(value, (list, tuple)):
        for sub in value:
            found.extend(sensitive_log_keys(sub))
    return found


def is_log_safe(value: Any) -> bool:
    return not sensitive_log_keys(value)