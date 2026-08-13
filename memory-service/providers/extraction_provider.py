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
   - LLM 返回非 dict / 缺字段 / 类型错 → 进审计，不进入正常 candidates（R4）
   - source_event_id 由系统可信字段强制附加，LLM 无法伪造（R3）
   - 候选正文命中 high/critical 敏感 → 拒绝进审计（R5）
   - 整体返回规则路径真实结果或空列表（非固定样例，TABLE 54）。
4. 超时降级：按 Day3 契约，LLM 超时返回空候选列表（不阻塞 Turn 事件处理）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipeline.schemas import NormalizedEvent, SourceType, SourceBusinessStatus
from pipeline.sensitive import detect_sensitivity, is_high_or_critical

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
    # R3/H1: source_event_id 为系统可信 provenance（归一化层附加），
    # 禁止由 LLM 生成/覆盖；None 时由 Provider 用 session_id 派生并提示。
    source_event_id: Optional[str] = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    collected_at: datetime = field(default_factory=lambda: datetime.now().astimezone())

    @property
    def trusted_source_event_id(self) -> str:
        """R3: 返回可信 source_event_id（系统附加）；缺失时以 session_id 兜底并标记。"""
        return self.source_event_id or f"turn:{self.session_id}"


# ── 抽取候选（Pydantic v2 校验模型：非法输出降级用） ──


class PreferenceCandidate(BaseModel):
    """偏好候选（Day3 契约字段 + D6 审计字段）。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    scope: Literal["global", "session", "project"] = "session"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)  # R3: 系统可信 provenance，禁止 LLM 生成/覆盖


class KnowledgeCandidate(BaseModel):
    """知识候选（Day3 契约字段 + D6 审计字段）。"""

    model_config = ConfigDict(extra="forbid")

    fact: str = Field(min_length=1)
    category: Literal["fact", "procedure", "case", "template", "constraint"] = "fact"
    conditions: Optional[str] = None
    source_event_id: str = Field(min_length=1)  # R3: 系统可信 provenance，禁止 LLM 生成/覆盖
    confidence: float = Field(ge=0.0, le=1.0)


# LLM 抽取器接口（可注入；返回 raw dict 候选列表，由本 Provider 做 Pydantic 校验）
LLMExtractor = Callable[[str, str], List[Dict[str, Any]]]

# ── 显式偏好规则（真实可解释，非样例） ──

_PREFERENCE_EXPLICIT = re.compile(
    r"(?i)(我喜欢|我偏好|我习惯|请总是|以后都|尽量|希望|偏好|更倾向|prefer|like to|always|"
    r"make sure|i want)\s*[:：]?\s*(.{2,60}?)(?=[，。！？.!?；;]|$)"
)


def _extract_preferences_rules(event: TurnFinalizedEvent,
                               source_event_id: str) -> List[PreferenceCandidate]:
    """规则路径：从用户文本提取显式偏好候选（真实规则，可解释）。

    R5 安全：候选 value/evidence 若命中 high/critical 敏感原文 → 拒绝
    （不进入正常候选；由调用方决定审计）。
    """
    candidates: List[PreferenceCandidate] = []
    text = event.user_text or ""
    for m in _PREFERENCE_EXPLICIT.finditer(text):
        value = m.group(2).strip("，。！？,.!?；; ")
        if not value:
            continue
        evidence = text[:120]
        # R5 防御性敏感复核：候选内容含高敏原文 → 不进入正常候选
        if _contains_high_sensitivity(value) or _contains_high_sensitivity(evidence):
            continue
        candidates.append(PreferenceCandidate(
            key="user_preference",
            value=value,
            scope="session",
            confidence=0.7,  # 显式表述置信度基线（E 轨评测后可调）
            evidence=evidence,
            source_event_id=source_event_id,
        ))
    return candidates


def _extract_knowledge_rules(event: TurnFinalizedEvent,
                             source_event_id: str) -> List[KnowledgeCandidate]:
    """规则路径：从 Tool 成功结果提取知识候选（失败 Tool 不生成成功知识，架构 8 章）。

    R5 安全：Tool result 若含 high/critical 敏感原文 → 拒绝进入候选。
    """
    candidates: List[KnowledgeCandidate] = []
    if event.tool_results:
        for tr in event.tool_results:
            if tr.status != "success" or not tr.result:
                continue  # 失败/取消 Tool 不沉淀为成功知识
            fact = tr.result.strip()
            if not fact or len(fact) < 8:
                continue
            # R5 防御性敏感复核：Tool 结果含高敏原文（API Key/JWT 等）→ 拒绝
            if _contains_high_sensitivity(fact):
                continue
            candidates.append(KnowledgeCandidate(
                fact=fact,
                category="fact",
                conditions=f"tool={tr.tool_name}",
                source_event_id=source_event_id,
                confidence=0.85,  # 真实 Tool 成功结果高可信（架构 6.3）
            ))
    return candidates


def _contains_high_sensitivity(text: str) -> bool:
    """R5：内容是否命中 high/critical 敏感（API Key/JWT/密码/私钥/手机号/身份证等）。"""
    if not text:
        return False
    level, matched = detect_sensitivity(text)
    return matched and is_high_or_critical(level)


class ExtractionProvider:
    """偏好/知识提取 Provider（Day3 契约接口）。

    规则优先路径独立工作；LLM 路径可注入（llm_extractor），输出经 Pydantic
    校验——非法候选进审计（R4），不进入正常返回；source_event_id 系统可信
    （R3）；敏感候选防御性拒绝（R5）。
    """

    def __init__(self, llm_extractor: Optional[LLMExtractor] = None) -> None:
        self._llm = llm_extractor
        self._audit: List[Dict[str, Any]] = []  # 非法候选审计（最小审计，不落原文）

    # ── 契约接口（H1：Day3 单参数 event；R3：source_event_id 系统可信） ──

    def extract_preferences(
        self, event: TurnFinalizedEvent
    ) -> List[PreferenceCandidate]:
        """提取偏好候选（Day3 契约：extract_preferences(event)）。

        R3: source_event_id 来自 event.trusted_source_event_id（系统侧），
        不允许由 LLM 生成/覆盖。R5: 敏感候选在规则/LLM 路径均被拒绝。
        """
        trusted_id = event.trusted_source_event_id
        rule_candidates = _extract_preferences_rules(event, trusted_id)
        if self._llm is None:
            return rule_candidates

        llm_candidates = self._run_llm("preference", event, trusted_id)
        return rule_candidates + llm_candidates

    def extract_knowledge(
        self, event: TurnFinalizedEvent
    ) -> List[KnowledgeCandidate]:
        """提取知识候选（Day3 契约：extract_knowledge(event)）。

        R3/R5 同 extract_preferences。
        """
        trusted_id = event.trusted_source_event_id
        rule_candidates = _extract_knowledge_rules(event, trusted_id)
        if self._llm is None:
            return rule_candidates

        llm_candidates = self._run_llm("knowledge", event, trusted_id)
        return rule_candidates + llm_candidates

    # ── LLM 路径（Pydantic 非法输出降级 + R4 隔离 + R5 敏感复核） ──

    def _run_llm(self, kind: str,
                 event: TurnFinalizedEvent,
                 trusted_source_event_id: str) -> List[Any]:
        """调用注入的 LLM 抽取器，输出经 Pydantic 校验。

        降级语义（Day3 契约 + 台账 D6-A）：
        - LLM 抛异常/超时 → 空列表（真实降级，不阻塞）
        - 输出非 list / 元素非 dict / 校验失败 → 进审计（R4：不返回非法候选）
        - 敏感候选（R5）→ 进审计，不进入正常返回
        """
        assert self._llm is not None
        try:
            raw_list = self._llm(kind, event.user_text or event.assistant_text or "")
        except Exception:
            # 超时/异常 → 返回空候选列表（Day3 契约降级）
            return []

        if not isinstance(raw_list, list):
            self._audit.append({"kind": kind, "event_id": trusted_source_event_id,
                                "error": "not-a-list"})
            return []

        out: List[Any] = []
        for raw in raw_list:
            validated = self._validate_candidate(kind, raw, event,
                                                 trusted_source_event_id)
            if validated is not None:
                out.append(validated)
        return out

    def _validate_candidate(self, kind: str, raw: Any,
                            event: TurnFinalizedEvent,
                            trusted_source_event_id: str) -> Optional[Any]:
        """Pydantic 校验单个 LLM 输出候选（R3/R4/R5）。

        Returns:
            合法且非敏感候选；非法/敏感候选写入 audit 并返回 None
            （R4：非法候选不进入正常 candidates，不允许下游过滤）。

        R3: source_event_id 由系统强制附加——剥离 LLM 提供的任何值。
        R5: 候选内容命中 high/critical 敏感 → 拒绝进审计。
        """
        if not isinstance(raw, dict):
            self._audit.append({"kind": kind, "event_id": trusted_source_event_id,
                                "error": "not-dict"})
            return None

        # R3: 从 LLM 输出剥离 source_event_id（禁止伪造 provenance）
        raw = {k: v for k, v in raw.items() if k != "source_event_id"}
        # 系统可信字段强制附加（LLM 无法覆盖）
        merged = {**raw, "source_event_id": trusted_source_event_id}

        model = PreferenceCandidate if kind == "preference" else KnowledgeCandidate
        try:
            cand = model.model_validate(merged)
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {}
            loc = ".".join(str(x) for x in first.get("loc", []))
            msg = first.get("msg", str(exc))
            # R4: 非法候选只进审计，不构造候选返回
            self._audit.append({
                "kind": kind,
                "event_id": trusted_source_event_id,
                "error": f"validation: {loc}: {msg}",
            })
            return None

        # R5: 敏感复核（候选正文含 high/critical 敏感原文 → 拒绝）
        text = cand.value if kind == "preference" else cand.fact
        if _contains_high_sensitivity(text):
            self._audit.append({
                "kind": kind,
                "event_id": trusted_source_event_id,
                "error": "sensitive-content-rejected",
            })
            return None

        return cand

    @property
    def audit(self) -> List[Dict[str, Any]]:
        """非法候选审计（最小审计，不含正文原文）。"""
        return list(self._audit)
