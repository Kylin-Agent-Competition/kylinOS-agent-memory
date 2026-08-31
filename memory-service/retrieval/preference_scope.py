"""D7B 偏好作用域到检索 term 的版本化映射与纯校验。"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping, Optional, Sequence

from domain.enums import PreferenceScope

PREFERENCE_SCOPE_TERMS_SCHEMA_VERSION = "preference-scope-terms/v1"

# 直接复用 E 轨冻结的 PreferenceScope 五值，不创建第二套 scope 枚举。
PREFERENCE_SCOPE_REQUIRED_TERM_KEYS: Mapping[
    PreferenceScope, frozenset[str]
] = MappingProxyType(
    {
        PreferenceScope.GLOBAL: frozenset(),
        PreferenceScope.TOPIC: frozenset({"topic"}),
        PreferenceScope.TOOL: frozenset({"tool"}),
        PreferenceScope.SESSION: frozenset({"session"}),
        PreferenceScope.TIME_WINDOW: frozenset({"time_window"}),
    }
)

PREFERENCE_SCOPE_TERM_KEYS = frozenset(
    key
    for required_keys in PREFERENCE_SCOPE_REQUIRED_TERM_KEYS.values()
    for key in required_keys
)


def preference_scope_terms_match(
    *,
    preference_scope: Optional[PreferenceScope],
    truth_scope_terms: Optional[Mapping[str, Sequence[str]]],
    query_scope_terms: Mapping[str, Sequence[str]],
) -> bool:
    """按 v1 映射执行 explicit-global 或 AND-key / OR-value 匹配。"""
    if preference_scope is None:
        return False

    truth_terms = truth_scope_terms or {}
    if any(key not in PREFERENCE_SCOPE_TERM_KEYS for key in truth_terms):
        return False

    required_keys = PREFERENCE_SCOPE_REQUIRED_TERM_KEYS[preference_scope]
    if preference_scope is PreferenceScope.GLOBAL:
        return not truth_terms

    if any(not truth_terms.get(key) for key in required_keys):
        return False

    return all(
        bool(values)
        and bool(set(values).intersection(query_scope_terms.get(key, ())))
        for key, values in truth_terms.items()
    )
