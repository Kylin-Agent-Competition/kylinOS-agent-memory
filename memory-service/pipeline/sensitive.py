"""
sensitive.py — 轨道 A Day6 敏感信息识别（架构 6.2 第 3 步）

职责：识别 API Key/Token/密码/私钥/手机号/身份证/敏感路径，
输出 sensitivity 等级（low/medium/high/critical）与 is_sensitive_matched 标记。

设计要点：
- 只做标记（is_sensitive_matched/sensitivity），不落明文日志、不输出原文。
- 规则由 schemas._SENSITIVE_PATTERNS 提供（正则，确定性）。
- 输入正文为 content_summary / raw 载荷引用字段（不扫描全量原始载荷——
  原始载荷持久化与脱敏属 D 轨 D6 范围，此处为管线内识别）。
"""

from __future__ import annotations

import re
from typing import Optional

from pipeline.schemas import (
    SensitivityLevel,
    _SENSITIVE_PATTERNS,
)

# 命中模式数 → 等级映射（critical 模式命中即 critical）
_CRITICAL_KEYWORDS = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|private[_-]?key|BEGIN.*PRIVATE KEY)")
_IDENTITY_KEYWORDS = re.compile(r"(?i)(phone|手机|身份证|id[_-]?card|sensitive|敏感)")


def detect_sensitivity(text: Optional[str]) -> tuple[SensitivityLevel, bool]:
    """识别正文敏感度。

    Returns:
        (sensitivity, is_sensitive_matched)
    """
    if not text:
        return SensitivityLevel.LOW, False

    hits = 0
    for pat in _SENSITIVE_PATTERNS:
        if pat.search(text):
            hits += 1

    if hits == 0:
        return SensitivityLevel.LOW, False

    # 命中关键凭据关键词 → critical
    if _CRITICAL_KEYWORDS.search(text):
        return SensitivityLevel.CRITICAL, True
    # 命中身份类 → high
    if _IDENTITY_KEYWORDS.search(text):
        return SensitivityLevel.HIGH, True
    # 其余命中（长密钥/手机号/身份证等模式）→ medium
    return SensitivityLevel.MEDIUM, True


def is_high_or_critical(level: SensitivityLevel) -> bool:
    """高敏/关键敏（用于上游决定是否进检索/摘要）。"""
    return level in (SensitivityLevel.HIGH, SensitivityLevel.CRITICAL)
