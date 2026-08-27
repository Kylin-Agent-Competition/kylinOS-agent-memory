"""source_resolver.py — 原文解析 seam（ADR-010，service/ 新增文件）

契约要点（docs/adr/010-turn-finalized-method.md）：
  - 接口：`resolve(source_reference) -> Optional[ResolvedContent]`
  - `original_user_text` 唯一来源 = 受控 resolver 解析 `source_reference` 所得正文；
    事件**不内嵌正文**（保持原文隔离，[02 §4.1]）
  - resolver 结果只用于落库 `original_user_text`，不进入日志/异常消息/响应
  - INSERT 路径调用 resolver：成功 → 写入 original_user_text；失败 → INTERNAL_ERROR
    （safe）；禁止编造正文、禁止以空串替代（turns.original_user_text NOT NULL 冻结语义）
  - UPDATE/refinalize 路径**不调用** resolver（正文已在首次 INSERT 落库）
  - 生产实现状态 = **BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED**（与 C 轨
    TurnExtractionAdapter 一致）；PR-2 只交付测试/纯内存 resolver，
    不声称真实正文通道已支持
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Protocol, runtime_checkable

from observability.json_logging import sanitize_message

logger = logging.getLogger(__name__)


@dataclass
class ResolvedContent:
    """resolver 解析结果（ADR-010）。"""

    original_user_text: str
    model_request: Optional[str] = None
    model_response: Optional[str] = None


@runtime_checkable
class SourceResolver(Protocol):
    """原文解析接口（ADR-010 seam）。"""

    def resolve(self, source_reference: str) -> Optional[ResolvedContent]:
        """按受控引用解析原文。

        Returns:
            ResolvedContent；无法解析返回 None（调用方按 INTERNAL_ERROR 处理，
            禁止编造正文）。
        """
        ...


class InMemorySourceResolver:
    """PR-2 交付的测试/纯内存 resolver（production 不注册，见 ADR-010 activation）。

    用途：L1 契约测试 + PR-3 L2 test profile 显式注入，验证服务端写链路
    （Gateway → UoW → SQLite+Outbox 真实落库），不声称真实正文通道已支持。
    """

    def __init__(self, mapping: Optional[Dict[str, ResolvedContent]] = None) -> None:
        self._mapping: Dict[str, ResolvedContent] = dict(mapping or {})

    def register(self, source_reference: str, content: ResolvedContent) -> None:
        """注册引用 → 正文映射（测试夹具）。"""
        self._mapping[source_reference] = content

    def resolve(self, source_reference: str) -> Optional[ResolvedContent]:
        content = self._mapping.get(source_reference)
        if content is None:
            # M4.5：外部引用经 sanitize_message 脱敏后入日志（防止原文泄漏）
            logger.warning(
                "resolver 未命中 source_reference=%s（返回 None，调用方按 INTERNAL_ERROR）",
                sanitize_message(source_reference),
            )
            return None
        return content


def load_resolver_from_json(path: str) -> InMemorySourceResolver:
    """从 JSON 文件加载 InMemorySourceResolver 映射（M6.1 可加载 mapping）。

    JSON 结构（validation profile --validation-sources）：
        {
          "ref://turn/H-1": {
            "original_user_text": "...",
            "model_request": {},        # 可选
            "model_response": {}        # 可选
          }
        }

    仅供 test/validation profile（--register-turn-finalized）使用；
    production 不加载（ADR-010 activation 方案 A+B）。
    """
    import json as _json
    from pathlib import Path

    raw = _json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("resolver mapping must be a JSON object")
    mapping: Dict[str, ResolvedContent] = {}
    for ref, content in raw.items():
        if not isinstance(content, dict) or not isinstance(content.get("original_user_text"), str):
            raise ValueError(f"invalid resolver entry for {ref!r}: expected object with "
                             "original_user_text string")
        mapping[ref] = ResolvedContent(
            original_user_text=content["original_user_text"],
            model_request=content.get("model_request"),
            model_response=content.get("model_response"),
        )
    return InMemorySourceResolver(mapping)


# 生产占位（BLOCKED_BY_HOST_MAPPING）：真实正文通道待 C 轨 TurnExtractionAdapter
# 接入（R-ARCH-05）；未就绪前不提供 production resolver，production 路由也不注册
# turn.finalized（ADR-010 activation 方案 A+B），杜绝「协议 SUPPORTED 但生产必然
# INTERNAL_ERROR」的矛盾。
PRODUCTION_RESOLVER_STATUS = "BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED"
