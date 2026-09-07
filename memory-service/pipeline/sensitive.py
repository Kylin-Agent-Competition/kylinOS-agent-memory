"""
sensitive.py — 轨道 A Day6 敏感信息识别（架构 6.2 第 3 步 + D3 安全契约）

职责：识别 API Key/Token/密码/私钥/手机号/身份证/敏感路径，
输出 sensitivity 等级（none/low/medium/high/critical）与 is_sensitive_matched 标记。

等级判定（R5 强化，D3 安全契约 §7.7 语义）：
- CRITICAL：凭据类（API Key 前缀 / JWT / 长密钥 / 密码 leetspeak / 凭据关键词）
- HIGH：身份类（手机号 / 身份证 / 敏感路径）
- MEDIUM：其余命中（弱匹配）

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

# 凭据类关键词（命中即 critical）
_CRITICAL_KEYWORDS = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|private[_-]?key|BEGIN.*PRIVATE KEY)")
# 身份类关键词（命中升 high）
_IDENTITY_KEYWORDS = re.compile(r"(?i)(phone|手机|身份证|id[_-]?card)")
# 密码 leetspeak 变体（P@ssw0rd 等）→ critical
_PASSWORD_LEET = re.compile(r"(?i)\b(?:p[a@]ssw[o0]rd|p[a@]ss|p[a@]ssw0rd)[^\s]{0,12}\b")
# 云厂商 API Key 前缀（sk_/pk_/ak_/rk_）→ critical
_API_KEY_PREFIX = re.compile(r"\b(?:sk|pk|ak|rk)_[A-Za-z0-9_\-]{16,}\b")
# 连字符云厂商 Key（sk-demo-…；P2-A safety-001 裁定：Dataset 语义=critical）→ critical
_API_KEY_PREFIX_HYPHEN = re.compile(r"(?i)\b(?:sk|pk|ak|rk)-[A-Za-z0-9_\-]{12,}\b")
# JWT 结构（三段 base64url）→ critical
_JWT_PATTERN = re.compile(
    r"\b[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\b")
# 长密钥（32+ 位）→ critical
_LONG_SECRET = re.compile(r"\b[A-Za-z0-9]{32,}\b")
# 手机号 → high
_PHONE = re.compile(r"\b1[3-9]\d{9}\b")
# 身份证 → high
_ID_CARD = re.compile(r"\b\d{17}[\dXx]\b")
# 敏感路径 → high
_SENSITIVE_PATH = re.compile(r"(?i)(/etc/passwd|/etc/shadow|\.ssh/|id_rsa|id_ed25519)")
# 明确的越权指令属于关键安全事件；只做确定性标记，由既有安全 Gate 拒绝。
_PROMPT_INJECTION = re.compile(
    r"(?i)(ignore\s+(?:all\s+)?(?:previous|prior).*?(?:rule|instruction)|"
    r"忽略之前.*?(?:安全规则|规则|指令))"
)


def detect_sensitivity(text: Optional[str]) -> tuple[SensitivityLevel, bool]:
    """识别正文敏感度。

    Returns:
        (sensitivity, is_sensitive_matched)
    """
    if not text:
        return SensitivityLevel.NONE, False

    matched = False
    # 凭据类 → critical
    if (_CRITICAL_KEYWORDS.search(text) or _PROMPT_INJECTION.search(text)
            or _PASSWORD_LEET.search(text)
            or _API_KEY_PREFIX.search(text) or _API_KEY_PREFIX_HYPHEN.search(text)
            or _LONG_SECRET.search(text)):
        return SensitivityLevel.CRITICAL, True
    # 身份类 → high
    if (_IDENTITY_KEYWORDS.search(text) or _PHONE.search(text)
            or _ID_CARD.search(text) or _SENSITIVE_PATH.search(text)):
        return SensitivityLevel.HIGH, True
    # 其余（兜底扫描 _SENSITIVE_PATTERNS）
    for pat in _SENSITIVE_PATTERNS:
        if pat.search(text):
            matched = True
            break
    if matched:
        return SensitivityLevel.MEDIUM, True
    return SensitivityLevel.NONE, False


def is_high_or_critical(level: SensitivityLevel) -> bool:
    """高敏/关键敏（用于上游决定是否进检索/摘要）。"""
    return level in (SensitivityLevel.HIGH, SensitivityLevel.CRITICAL)
