"""
fingerprint.py — 轨道 A Day6 内容指纹与重复检测辅助函数（架构 6.2 第 4 步）

职责：
- content_fingerprint(text) -> sha256（归一化正文指纹，用于重复检测）
- is_duplicate(candidate, seen_fingerprints) -> bool（基于内容指纹判重）
- event_duplicate_key(event) -> str（基于 event_id/idempotency_key/tool_call_id 的业务幂等键）

设计要点：
- 指纹基于归一化正文（去空白/大小写折叠），不含原始载荷全文。
- 幂等键语义（E 轨 Schema §3.1）：idempotency_key 是接入侧去重键，
  不可由 event_id 替代——判重优先级 idempotency_key > event_id。
- 确定性：同一正文 → 同一指纹（可复现、可测试）。
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional

from pipeline.schemas import NormalizedEvent

# 归一化：去首尾空白、折叠内部空白、Unicode 大小写折叠
_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS.sub(" ", text.strip()).casefold()


def content_fingerprint(text: str) -> str:
    """正文内容指纹（sha256 hex，归一化后）。

    Args:
        text: 正文（content_summary / 需判重文本）。

    Returns:
        64 位 hex sha256。
    """
    normalized = _normalize(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def is_duplicate(fingerprint: str, seen: set[str]) -> bool:
    """基于内容指纹判重（架构 6.2 第 4 步：内容指纹防止重复写入）。

    Args:
        fingerprint: content_fingerprint() 输出。
        seen: 已见指纹集合（由调用方维护，如内存集合或后续 D 轨持久化）。

    Returns:
        True = 已存在（重复）。
    """
    return fingerprint in seen


def event_duplicate_key(event: NormalizedEvent) -> str:
    """业务幂等键：idempotency_key 优先，缺失时退化 event_id。

    E 轨 Schema 语义：idempotency_key 用于接入侧去重；event_id 是全局标识，
    不可替代 idempotency_key 的去重业务语义。此处组合两者以覆盖
    "同一业务触发" 与 "同事件重放" 两种去重目标。
    """
    key = event.idempotency_key or event.event_id
    return f"{event.user_id}:{key}"


def fingerprint_event(event: NormalizedEvent) -> str:
    """对 NormalizedEvent 生成内容指纹（基于 content_summary 或事件文本字段）。"""
    text = event.content_summary or ""
    if not text and event.raw_payload_ref:
        text = event.raw_payload_ref
    if not text:
        # 无正文内容时用标识字段组合，保证同事件稳定指纹
        text = f"{event.event_id}:{event.idempotency_key}:{event.session_id}"
    return content_fingerprint(text)


def fill_event_fingerprint(event: NormalizedEvent) -> NormalizedEvent:
    """返回附带 content_fingerprint 的 NormalizedEvent（不修改原对象）。"""
    fp = fingerprint_event(event)
    return event.model_copy(update={"content_fingerprint": fp})
