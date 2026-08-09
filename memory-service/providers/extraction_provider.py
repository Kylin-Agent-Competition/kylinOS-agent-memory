"""
extraction_provider.py — 轨道 A Day6 结构化抽取 Provider（Day3 契约对齐）

职责（docs/day3/06_provider_contract_v1.md §ExtractionProvider）：
- extract_preferences(event) -> list[PreferenceCandidate]
- extract_knowledge(event) -> list[KnowledgeCandidate]

策略（架构 2.1 已批准）：规则优先 + LLM 结构化抽取 + Pydantic 校验。

本实现（D6 阶段，无真实 LLM 凭证）：
1. 规则路径（真实可解释规则，独立工作）：
   - 偏好：显式表述（"我喜欢/我偏好/请总是/以后都" + 宾语）→ PreferenceCandidate
   - 知识：Tool 成功结果 / 事实断言 → KnowledgeCandidate
2. LLM 路径：接口预留（llm_extractor 可注入）；未注入时规则路径独立返回。
3. Pydantic 非法输出降级（架构 6.2 第 1 步 + 台账 D6-A）：
   - LLM 返回非 dict / 缺字段 / 类型错 → 候选标记 validation_failed=True 进审计，
     不进入业务真源；整体返回规则路径真实结果或空列表（非固定样例，TABLE 54）。
4. 超时降级：按 Day3 契约，LLM 超时返回空候选列表（不阻塞 Turn 事件处理）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipeline.schemas import NormalizedEvent, SourceType, SourceBusinessStatus

# ── Day3 契约数据结构（docs/day3/06_provider_contract_v1.md） ──


@dataclass
class ToolResult:
    tool_name: str
    arguments: dict
    status: str  # success | failure | cancelled
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass
class TurnFinalizedEvent:
    session_id: str
    user_text: str
    assistant_text: str
    tool_results: Optional[List[ToolResult]] = None
    source: Literal["chat", "tool_result", "manual_config"] = "chat"
    occurred_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    collected_at: datetime = field(default_factory=lambda: datetime.now().astimezone())


# ── 抽取候选（Pydantic v2 校验模型：非法输出降级用） ──


class PreferenceCandidate(BaseModel):
    """偏好候选（Day3 契约字段 + D6 审计字段）。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    scope: Literal["global", "session", "project"] = "session"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)
    # D6 审计字段：LLM 输出校验失败标记（非法候选不进业务真源）
    validation_failed: bool = False
    validation_error: Optional[str] = None


class KnowledgeCandidate(BaseModel):
    """知识候选（Day3 契约字段 + D6 审计字段）。"""

    model_config = ConfigDict(extra="forbid")

    fact: str = Field(min_length=1)
    category: Literal["fact", "procedure", "case", "template", "constraint"] = "fact"
    conditions: Optional[str] = None
    source_event_id: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    validation_failed: bool = False
    validation_error: Optional[str] = None


# LLM 抽取器接口（可注入；返回 raw dict 候选列表，由本 Provider 做 Pydantic 校验）
LLMExtractor = Callable[[str, str], List[Dict[str, Any]]]

# ── 显式偏好规则（真实可解释，非样例） ──

_PREFERENCE_EXPLICIT = re.compile(
    r"(?i)(我喜欢|我偏好|我习惯|请总是|以后都|尽量|希望|偏好|更倾向|prefer|like to|always|"
    r"make sure|i want)\s*[:：]?\s*(.{2,60}?)(?=[，。！？.!?；;]|$)"
)


def _extract_preferences_rules(event: TurnFinalizedEvent,
                               source_event_id: str) -> List[PreferenceCandidate]:
    """规则路径：从用户文本提取显式偏好候选（真实规则，可解释）。"""
    candidates: List[PreferenceCandidate] = []
    text = event.user_text or ""
    for m in _PREFERENCE_EXPLICIT.finditer(text):
        value = m.group(2).strip("，。！？,.!?；; ")
        if not value:
            continue
        candidates.append(PreferenceCandidate(
            key="user_preference",
            value=value,
            scope="session",
            confidence=0.7,  # 显式表述置信度基线（E 轨评测后可调）
            evidence=text[:120],
            source_event_id=source_event_id,
        ))
    return candidates


def _extract_knowledge_rules(event: TurnFinalizedEvent,
                             source_event_id: str) -> List[KnowledgeCandidate]:
    """规则路径：从 Tool 成功结果提取知识候选（失败 Tool 不生成成功知识，架构 8 章）。"""
    candidates: List[KnowledgeCandidate] = []
    if event.tool_results:
        for tr in event.tool_results:
            if tr.status != "success" or not tr.result:
                continue  # 失败/取消 Tool 不沉淀为成功知识
            fact = tr.result.strip()
            if not fact or len(fact) < 8:
                continue
            candidates.append(KnowledgeCandidate(
                fact=fact,
                category="fact",
                conditions=f"tool={tr.tool_name}",
                source_event_id=source_event_id,
                confidence=0.85,  # 真实 Tool 成功结果高可信（架构 6.3）
            ))
    return candidates


class ExtractionProvider:
    """偏好/知识提取 Provider（Day3 契约接口）。

    规则优先路径独立工作；LLM 路径可注入（llm_extractor），输出经 Pydantic
    校验——非法候选 validation_failed=True 进审计，不进入业务真源。
    """

    def __init__(self, llm_extractor: Optional[LLMExtractor] = None) -> None:
        self._llm = llm_extractor
        self._audit: List[Dict[str, Any]] = []  # 非法候选审计（最小审计，不落原文）

    # ── 契约接口 ──

    def extract_preferences(
        self, event: TurnFinalizedEvent, source_event_id: str
    ) -> List[PreferenceCandidate]:
        """提取偏好候选（规则优先 + 可选 LLM + Pydantic 降级）。"""
        rule_candidates = _extract_preferences_rules(event, source_event_id)
        if self._llm is None:
            return rule_candidates

        llm_candidates = self._run_llm("preference", event)
        return rule_candidates + llm_candidates  # 非法候选已标记，不进真源

    def extract_knowledge(
        self, event: TurnFinalizedEvent, source_event_id: str
    ) -> List[KnowledgeCandidate]:
        """提取知识候选（规则优先 + 可选 LLM + Pydantic 降级）。"""
        rule_candidates = _extract_knowledge_rules(event, source_event_id)
        if self._llm is None:
            return rule_candidates

        llm_candidates = self._run_llm("knowledge", event)
        return rule_candidates + llm_candidates

    # ── LLM 路径（Pydantic 非法输出降级） ──

    def _run_llm(self, kind: str,
                 event: TurnFinalizedEvent) -> List[Any]:
        """调用注入的 LLM 抽取器，输出经 Pydantic 校验。

        降级语义（Day3 契约 + 台账 D6-A）：
        - LLM 抛异常/超时 → 空列表（真实降级，不阻塞）
        - 输出非 list / 元素非 dict / 校验失败 → 标记 validation_failed 进审计
        """
        assert self._llm is not None
        try:
            raw_list = self._llm(kind, event.user_text or event.assistant_text or "")
        except Exception:
            # 超时/异常 → 返回空候选列表（Day3 契约降级）
            return []

        if not isinstance(raw_list, list):
            self._audit.append({"kind": kind, "error": "not-a-list"})
            return []

        out: List[Any] = []
        for raw in raw_list:
            validated = self._validate_candidate(kind, raw, event)
            if validated is not None:
                out.append(validated)
        return out

    def _validate_candidate(self, kind: str, raw: Any,
                            event: TurnFinalizedEvent) -> Optional[Any]:
        """Pydantic 校验单个 LLM 输出候选。

        Returns:
            合法候选（validation_failed=False）；非法候选写入审计并返回
            validation_failed=True 的候选（供上层识别），不进入业务真源。
        """
        if not isinstance(raw, dict):
            self._audit.append({"kind": kind, "error": "not-dict"})
            return None

        base = {"source_event_id": event.session_id or "unknown"}
        merged = {**base, **raw}
        model = PreferenceCandidate if kind == "preference" else KnowledgeCandidate
        try:
            cand = model.model_validate(merged)
            return cand
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {}
            loc = ".".join(str(x) for x in first.get("loc", []))
            msg = first.get("msg", str(exc))
            # 非法候选：标记 validation_failed=True，写入审计，不进入业务真源。
            # 用 model_construct 绕过字段约束（非法候选本身字段值非法，
            # 直接构造仅用于上层识别与审计，不参与业务持久化）。
            if kind == "preference":
                cand = PreferenceCandidate.model_construct(
                    key=str(raw.get("key", "unknown")),
                    value=str(raw.get("value", "")),
                    scope="session",
                    confidence=0.0,
                    evidence=str(raw.get("evidence", "")),
                    source_event_id=event.session_id or "unknown",
                    validation_failed=True,
                    validation_error=f"{loc}: {msg}",
                )
            else:
                cand = KnowledgeCandidate.model_construct(
                    fact=str(raw.get("fact", "")),
                    category="fact",
                    conditions=str(raw.get("conditions", "")),
                    source_event_id=event.session_id or "unknown",
                    confidence=0.0,
                    validation_failed=True,
                    validation_error=f"{loc}: {msg}",
                )
            self._audit.append({
                "kind": kind,
                "event_id": event.session_id,
                "error": f"{loc}: {msg}",
            })
            return cand

    @property
    def audit(self) -> List[Dict[str, Any]]:
        """非法候选审计（最小审计，不含正文原文）。"""
        return list(self._audit)
