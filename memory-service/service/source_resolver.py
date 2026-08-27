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
            logger.warning(
                "resolver 未命中 source_reference=%s（返回 None，调用方按 INTERNAL_ERROR）",
                source_reference,
            )
            return None
        return content


# 生产占位（BLOCKED_BY_HOST_MAPPING）：真实正文通道待 C 轨 TurnExtractionAdapter
# 接入（R-ARCH-05）；未就绪前不提供 production resolver，production 路由也不注册
# turn.finalized（ADR-010 activation 方案 A+B），杜绝「协议 SUPPORTED 但生产必然
# INTERNAL_ERROR」的矛盾。
PRODUCTION_RESOLVER_STATUS = "BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED"
