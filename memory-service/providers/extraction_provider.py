"""
extraction_provider.py — 轨道 A 结构化抽取 Provider（Day3 契约对齐，Day7 深化）

职责（docs/day3/06_provider_contract_v1.md §ExtractionProvider）：
- extract_preferences(event) -> list[PreferenceCandidate]
- extract_knowledge(event) -> list[KnowledgeCandidate]

策略（架构 2.1 已批准）：规则优先 + LLM 结构化抽取 + Pydantic 校验。

D6 阶段（PR #27 已合并）：规则路径 + LLM 接口预留 + Pydantic 非法输出降级
（R3 系统可信 provenance / R4 非法候选隔离 / R5 敏感防御 / B1 成功知识门控 /
B2 memory_status=candidate 恒置）。

D7 阶段（本版）：
1. 规则路径深化（providers/preference_rules.py，架构 TABLE 19/20 + E 轨 Schema）：
   - 偏好六类识别（presentation/tool_selection/workflow/safety/environment/scene_specific）
   - 临时指令 vs 长期偏好（is_temporary/should_persist，TABLE 20）
   - scope 推导（E 轨 §2.9 五值：global/topic/tool/session/time_window）
   - 类别键派生（key，E 轨 §3.2 preference_key 语义）+ explicitness（§2.5）
2. 规则 + LLM 协同：合并去重（同 key 规则优先，LLM 重复/冲突候选进 audit）。
3. 缓存：LRU 抽取缓存（键 = kind + source_event_id + 内容指纹），返回深拷贝。
4. 超时：LLM 调用显式超时包装（llm_timeout_ms，超时 → 空候选 + audit，
   Day3 契约降级，不阻塞 Turn 事件处理）。
5. 非法字段降级：可选字段非法值 → 剥离 + 默认值 + audit（候选仍返回）；
   必需字段缺失/类型错误 → 候选级拒绝（R4 保持）。
6. 评测输出：PreferenceExtractionOutput + export_preference_records() JSONL
   + to_evaluation_record() 字段级统一结果格式（供 E 轨 D7 偏好准确率评测）。

安全（保持 D6 全部红线）：
- R3：source_event_id 系统可信，LLM 无法伪造/覆盖
- R4：非法候选不进入正常 candidates（仅可选字段做字段级降级）
- R5：候选正文命中 high/critical 敏感 → 拒绝进审计（规则/LLM 双路径）
- B1：成功知识必须建立在真实 success ToolResult 之上（knowledge LLM 门控）
- B2：memory_status 恒 candidate，LLM 不能自封 verified
- 缓存键基于内容指纹，不含原始载荷全文；缓存副本不落明文日志
"""

from __future__ import annotations

import concurrent.futures
import json
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipeline.fingerprint import content_fingerprint
from pipeline.sensitive import detect_sensitivity, is_high_or_critical
from providers.preference_rules import (
    PREFERENCE_EXPLICIT_PATTERN,
    PREFERENCE_INSTRUCTION_PATTERN,
    classify_preference_category,
    classify_temporality,
    derive_preference_key,
    derive_preference_scope,
    has_long_term_marker,
    rule_confidence,
)

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

# 偏好类别（架构 TABLE 19 六类）/ scope（E 轨 §2.9）/ 表达类型（E 轨 §2.5）
PreferenceCategory = Literal[
    "presentation", "tool_selection", "workflow", "safety", "environment", "scene_specific"]
PreferenceScope = Literal["global", "topic", "tool", "session", "time_window"]
Explicitness = Literal["explicit", "implicit"]


class PreferenceCandidate(BaseModel):
    """偏好候选 v0.2（Day3 契约字段 + D7 字段级深化 + D6 审计字段）。

    D7 契约演进（见 docs/day7/01_task_card.md）：
    - scope: Day3 global/session/project → E 轨 §2.9 五值（权威业务 Schema）
    - 新增 category（TABLE 19 六类）/ explicitness（§2.5）/
      is_temporary/should_persist（§3.2，TABLE 20 临时 vs 长期）
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)  # 业务语义键（E 轨 §3.2 preference_key）
    value: str = Field(min_length=1)
    category: PreferenceCategory = "presentation"  # 架构 TABLE 19 六类
    scope: PreferenceScope = "session"  # E 轨 §2.9 五值
    confidence: float = Field(ge=0.0, le=1.0)
    explicitness: Explicitness = "explicit"  # E 轨 §2.5
    is_temporary: bool = False  # TABLE 20：临时指令 vs 长期偏好
    should_persist: bool = True  # E 轨 §3.2
    evidence: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)  # R3: 系统可信 provenance，禁止 LLM 生成/覆盖
    # B2-mini: 可信级标记——候选仅为 candidate，系统强制设置，LLM 不能改成 verified
    memory_status: Literal["candidate"] = "candidate"


class KnowledgeCandidate(BaseModel):
    """知识候选（Day3 契约字段 + D6 审计字段 + B2 可信级标记）。"""

    model_config = ConfigDict(extra="forbid")

    fact: str = Field(min_length=1)
    category: Literal["fact", "procedure", "case", "template", "constraint"] = "fact"
    conditions: Optional[str] = None
    source_event_id: str = Field(min_length=1)  # R3: 系统可信 provenance，禁止 LLM 生成/覆盖
    confidence: float = Field(ge=0.0, le=1.0)
    # B2-mini: 可信级标记——候选仅为 candidate，系统强制设置，LLM 不能改成 verified
    memory_status: Literal["candidate"] = "candidate"


# LLM 抽取器接口（可注入；返回 raw dict 候选列表，由本 Provider 做 Pydantic 校验）
LLMExtractor = Callable[[str, str], List[Dict[str, Any]]]

# ── 可选字段降级默认值（D7：非法字段降级，R4 必需字段隔离不变） ──

_VALID_CATEGORIES = {"presentation", "tool_selection", "workflow",
                     "safety", "environment", "scene_specific"}
_VALID_SCOPES = {"global", "topic", "tool", "session", "time_window"}
_VALID_EXPLICITNESS = {"explicit", "implicit"}


def _degrade_optional_fields(raw: Dict[str, Any], kind: str,
                             trusted_id: str,
                             audit: List[Dict[str, Any]]) -> Dict[str, Any]:
    """可选字段非法值降级：剥离/替换为默认值 + audit（D7）。

    - category/scope/explicitness 非枚举 → 默认值 + audit
    - is_temporary/should_persist 非 bool → 剥离（用 Pydantic 默认值）+ audit

    仅作用于偏好路径的可选字段；必需字段（key/value/evidence/confidence）
    缺失或类型错误仍由 Pydantic 校验拒绝（R4：非法候选不进入业务真源）。
    confidence 为契约 required 字段（Day3 契约 + E 轨 §3.2 confidence_score），
    非法值（非数值/越界/缺失）一律 candidate-level reject，不做默认值替换
    （PR #36 HIGH-02：不得把非法 required 字段重新制造成合法业务值）。
    """
    out = dict(raw)
    for fname, valid, default in (
            ("category", _VALID_CATEGORIES, "presentation"),
            ("scope", _VALID_SCOPES, "session"),
            ("explicitness", _VALID_EXPLICITNESS, "explicit")):
        v = out.get(fname)
        # isinstance(v, str) 防止 list/dict 等 unhashable 值在集合成员检查时抛 TypeError
        if v is not None and (not isinstance(v, str) or v not in valid):
            out[fname] = default
            audit.append({"kind": kind, "event_id": trusted_id,
                          "error": f"field-degraded:{fname}"})
    for fname in ("is_temporary", "should_persist"):
        v = out.get(fname)
        if v is not None and not isinstance(v, bool):
            out.pop(fname, None)
            audit.append({"kind": kind, "event_id": trusted_id,
                          "error": f"field-degraded:{fname}"})
    return out


# ── 规则路径：偏好（D7 深化：六类/临时长期/scope/key/explicitness） ──


def _extract_preferences_rules(event: TurnFinalizedEvent,
                               source_event_id: str) -> List[PreferenceCandidate]:
    """规则路径：从用户文本提取偏好候选（真实规则，可解释，独立工作）。

    D7：类别识别（TABLE 19）、临时/长期（TABLE 20）、scope 推导（E 轨 §2.9）、
    类别键派生、显式置信度基线——全部来自 providers/preference_rules.py。

    两阶段规则入口（PR #36 HIGH-01 修复）：
    1. 显式偏好词（PREFERENCE_EXPLICIT_PATTERN，如 我喜欢/以后/希望…）
    2. 显式词未命中时，尝试指令式表达（PREFERENCE_INSTRUCTION_PATTERN，
       如 TABLE 20 原句 "这次只用三句话回答"——时态限定词 + 指令动词）
    两阶段均非硬编码特判；阶段 1 命中时不再执行阶段 2（避免重复候选）。

    R5 安全：候选 value/evidence 若命中 high/critical 敏感原文 → 拒绝
    （不进入正常候选；由调用方决定审计）。
    """
    candidates: List[PreferenceCandidate] = []
    text = event.user_text or ""
    explicit_matches = list(PREFERENCE_EXPLICIT_PATTERN.finditer(text))
    if explicit_matches:
        for m in explicit_matches:
            cand = _build_preference_rule_candidate(
                m.group(2), text, source_event_id)
            if cand is not None:
                candidates.append(cand)
        return candidates
    # TABLE 20 临时指令式表达：显式偏好词未命中时启用指令模式
    for m in PREFERENCE_INSTRUCTION_PATTERN.finditer(text):
        cand = _build_preference_rule_candidate(
            m.group(1), text, source_event_id)
        if cand is not None:
            candidates.append(cand)
    return candidates


def _build_preference_rule_candidate(value: str, text: str,
                                     source_event_id: str
                                     ) -> Optional[PreferenceCandidate]:
    """规则路径候选构造（显式/指令两阶段共用）。

    R5 安全：候选 value/evidence 命中 high/critical 敏感原文 → None（拒绝）。
    """
    value = value.strip("，。！？,.!?；; ")
    if not value:
        return None
    evidence = text[:120]
    if _contains_high_sensitivity(value) or _contains_high_sensitivity(evidence):
        return None
    category = classify_preference_category(text)
    scope = derive_preference_scope(text)
    is_temporary, should_persist = classify_temporality(text)
    key = derive_preference_key(category, text)
    confidence = rule_confidence(
        is_temporary=is_temporary,
        has_long_term_marker=has_long_term_marker(text))
    return PreferenceCandidate(
        key=key,
        value=value,
        category=category,
        scope=scope,
        confidence=confidence,
        explicitness="explicit",  # 规则路径仅处理显式/明确指令表述（E 轨 §2.5）
        is_temporary=is_temporary,
        should_persist=should_persist,
        evidence=evidence,
        source_event_id=source_event_id,
    )


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


# ── 事件内容指纹（缓存键用；不含原始载荷全文） ──


def _event_content_text(event: TurnFinalizedEvent) -> str:
    """事件内容文本（user_text + assistant_text + Tool 结果），用于缓存键指纹。"""
    parts = [event.user_text or "", event.assistant_text or ""]
    for tr in event.tool_results or []:
        parts.append(f"{tr.tool_name}:{tr.status}:{tr.result or ''}:{tr.error or ''}")
    return "\n".join(parts)


def _preference_cache_key(event: TurnFinalizedEvent) -> Tuple[str, str, str]:
    """偏好抽取缓存键：kind + 可信 source_event_id + 内容指纹。"""
    return ("preference", event.trusted_source_event_id,
            content_fingerprint(_event_content_text(event)))


# ── LRU 抽取缓存（D7） ──


class PreferenceExtractionCache:
    """LRU 抽取结果缓存（键 = kind + source_event_id + 内容指纹）。

    - 返回深拷贝：调用方修改候选不影响缓存（防污染）。
    - 空列表也缓存：避免同一事件重复触发 LLM 调用。
    - TTL 可选（None = 不过期）；容量满时淘汰最久未用（LRU）。
    - 统计：hits / misses / size（供评测与可观测性）。
    """

    _MISS = object()  # 未命中哨兵（None 返回表示未命中；[] 是合法的"缓存了空结果"）

    def __init__(self, capacity: int = 256,
                 ttl_seconds: Optional[float] = None) -> None:
        assert capacity > 0, "cache capacity must be > 0"
        self._capacity = capacity
        self._ttl = ttl_seconds
        self._data: "OrderedDict[Tuple[str, str, str], Tuple[float, List[PreferenceCandidate]]]" = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: Tuple[str, str, str]) -> Optional[List[Any]]:
        """按缓存键取结果；None = 未命中（不含"缓存了空列表"）。

        返回深拷贝（调用方修改不影响缓存）。偏好/知识候选均为 Pydantic
        模型，深拷贝语义一致。
        """
        entry = self._data.get(key, self._MISS)
        if entry is self._MISS:
            self._misses += 1
            return None
        ts, candidates = entry
        if self._ttl is not None and (time.monotonic() - ts) > self._ttl:
            del self._data[key]
            self._misses += 1
            return None
        self._hits += 1
        self._data.move_to_end(key)
        return [c.model_copy(deep=True) for c in candidates]

    def set(self, key: Tuple[str, str, str], candidates: List[Any]) -> None:
        """写入缓存（深拷贝存储）。"""
        self._data[key] = (time.monotonic(),
                           [c.model_copy(deep=True) for c in candidates])
        self._data.move_to_end(key)
        while len(self._data) > self._capacity:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> Dict[str, int]:
        """缓存统计（size/hits/misses）。"""
        return {"size": len(self._data), "hits": self._hits, "misses": self._misses}


# ── 评测输出（D7：偏好字段级评测统一结果格式，供 E 轨偏好评测） ──

ProviderMode = Literal["rules", "llm", "coop"]  # rules=无 LLM；coop=规则+LLM 协同；llm 预留


class PreferenceExtractionOutput(BaseModel):
    """一次偏好提取的完整输出（含元信息，供评测与可观测性）。"""

    model_config = ConfigDict(extra="forbid")

    event_id: str  # 可信 source_event_id（R3）
    provider_mode: ProviderMode
    candidates: List[PreferenceCandidate]
    cache_hit: bool = False
    llm_timeout: bool = False
    duration_ms: float = 0.0


def to_evaluation_record(candidate: PreferenceCandidate) -> Dict[str, Any]:
    """单候选 → 字段级统一评测结果格式（E 轨 D7 偏好评测口径）。

    字段与 E 轨 Schema §3.2 / 架构 TABLE 19 对齐：key/value/category/scope/
    confidence/explicitness/is_temporary/should_persist/evidence/source_event_id/
    memory_status——供偏好准确率评测（Gold Label 比对）。
    """
    return {
        "key": candidate.key,
        "value": candidate.value,
        "category": candidate.category,
        "scope": candidate.scope,
        "confidence": candidate.confidence,
        "explicitness": candidate.explicitness,
        "is_temporary": candidate.is_temporary,
        "should_persist": candidate.should_persist,
        "evidence": candidate.evidence,
        "source_event_id": candidate.source_event_id,
        "memory_status": candidate.memory_status,
    }


def export_preference_records(events: List[TurnFinalizedEvent],
                              provider: "ExtractionProvider",
                              path: str) -> int:
    """批量提取并导出 JSONL 评测记录（每行一个 PreferenceExtractionOutput）。

    Args:
        events: Turn 事件列表。
        provider: ExtractionProvider 实例。
        path: 输出文件路径（UTF-8 JSONL）。

    Returns:
        写出的事件记录数。
    """
    written = 0
    with open(path, "w", encoding="utf-8") as f:
        for ev in events:
            out = provider.extract_preferences_with_meta(ev)
            f.write(json.dumps(out.model_dump(mode="json"),
                               ensure_ascii=False) + "\n")
            written += 1
    return written


class ExtractionProvider:
    """偏好/知识提取 Provider（Day3 契约接口，D7 深化）。

    规则优先路径独立工作；LLM 路径可注入（llm_extractor），输出经 Pydantic
    校验——非法候选进审计（R4），不进入正常返回；source_event_id 系统可信
    （R3）；敏感候选防御性拒绝（R5）；B1 成功知识门控；B2 恒 candidate。
    D7：缓存（PreferenceExtractionCache）、超时（llm_timeout_ms）、
    可选字段降级、规则+LLM 合并去重、评测输出（extract_preferences_with_meta）。
    """

    def __init__(self, llm_extractor: Optional[LLMExtractor] = None,
                 *, llm_timeout_ms: float = 5000.0,
                 cache: Optional[PreferenceExtractionCache] = None) -> None:
        self._llm = llm_extractor
        self._llm_timeout_ms = llm_timeout_ms
        self._cache = cache if cache is not None else PreferenceExtractionCache()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="llm-extract")
        self._closed = False
        # Review 修复：跟踪超时后仍在运行的 in-flight LLM 任务。
        # 单 worker 池中挂起的任务会阻塞后续 submit 排队（排队时间计入 deadline），
        # 导致每次新调用都超时——挂起期间跳过新 LLM 调用（llm-busy-skip）而非排队拖死。
        self._in_flight: Optional[concurrent.futures.Future] = None
        self._audit: List[Dict[str, Any]] = []  # 非法候选审计（最小审计，不落原文）

    def close(self) -> None:
        """关闭 LLM 执行器（幂等）。关闭后 extract_* 走规则路径并降级 LLM。"""
        if not self._closed:
            self._executor.shutdown(wait=False)
            self._closed = True

    # ── 契约接口（H1：Day3 单参数 event；R3：source_event_id 系统可信） ──

    def extract_preferences(
        self, event: TurnFinalizedEvent
    ) -> List[PreferenceCandidate]:
        """提取偏好候选（Day3 契约：extract_preferences(event)）。

        R3: source_event_id 来自 event.trusted_source_event_id（系统侧），
        不允许由 LLM 生成/覆盖。R5: 敏感候选在规则/LLM 路径均被拒绝。
        D7: 带缓存 + 规则/LLM 协同 + 可选字段降级（细节见
        extract_preferences_with_meta）。
        """
        return self.extract_preferences_with_meta(event).candidates

    def extract_preferences_with_meta(
        self, event: TurnFinalizedEvent
    ) -> PreferenceExtractionOutput:
        """提取偏好候选 + 元信息（D7：缓存命中/模式/超时/耗时）。

        流程：缓存查找 → 规则路径 →（LLM 协同 + 合并去重）→ 写缓存。
        """
        start = time.monotonic()
        trusted_id = event.trusted_source_event_id
        cache_key = _preference_cache_key(event)

        cached = self._cache.get(cache_key)
        if cached is not None:
            return PreferenceExtractionOutput(
                event_id=trusted_id,
                provider_mode=self._provider_mode,
                candidates=cached,
                cache_hit=True,
                duration_ms=(time.monotonic() - start) * 1000.0,
            )

        rule_candidates = _extract_preferences_rules(event, trusted_id)
        llm_candidates: List[PreferenceCandidate] = []
        llm_timeout = False
        if self._llm is not None:
            llm_candidates, llm_timeout = self._run_llm(
                "preference", event, trusted_id)
        merged = self._merge_rule_and_llm(
            rule_candidates, llm_candidates, trusted_id)
        self._cache.set(cache_key, merged)

        return PreferenceExtractionOutput(
            event_id=trusted_id,
            provider_mode=self._provider_mode,
            candidates=merged,
            cache_hit=False,
            llm_timeout=llm_timeout,
            duration_ms=(time.monotonic() - start) * 1000.0,
        )

    def extract_knowledge(
        self, event: TurnFinalizedEvent
    ) -> List[KnowledgeCandidate]:
        """提取知识候选（Day3 契约：extract_knowledge(event)）。

        R3/R5 同 extract_preferences。
        B1: 成功知识必须建立在真实 success ToolResult 之上——knowledge LLM 路径
        仅在事件含至少一个 success ToolResult 时执行；否则 LLM 输出全部拒绝
        （模型自述成功 ≠ 真实 Tool 执行成功，不得沉淀为知识）。
        D7: knowledge 路径同样使用缓存与超时包装（一致性）。
        """
        trusted_id = event.trusted_source_event_id
        cache_key = ("knowledge", trusted_id,
                     content_fingerprint(_event_content_text(event)))

        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # 类型同构（KnowledgeCandidate 列表，深拷贝由缓存负责）

        rule_candidates = _extract_knowledge_rules(event, trusted_id)
        if self._llm is None:
            self._cache.set(cache_key, rule_candidates)
            return rule_candidates

        # B1 门控：必须有真实 success Tool evidence 才允许 knowledge LLM 提取
        has_success_tool = any(
            tr.status == "success" and tr.result for tr in (event.tool_results or []))
        if not has_success_tool:
            # 无真实 success Tool evidence：LLM 输出不得形成成功知识（进审计）
            self._audit.append({
                "kind": "knowledge",
                "event_id": trusted_id,
                "error": "no-success-tool-evidence: llm knowledge rejected",
            })
            self._cache.set(cache_key, rule_candidates)
            return rule_candidates

        llm_candidates, _timeout = self._run_llm("knowledge", event, trusted_id)
        merged = rule_candidates + llm_candidates
        self._cache.set(cache_key, merged)
        return merged

    # ── 规则 + LLM 协同（D7：合并去重，规则优先） ──

    def _merge_rule_and_llm(
        self, rule_candidates: List[PreferenceCandidate],
        llm_candidates: List[PreferenceCandidate],
        trusted_id: str,
    ) -> List[PreferenceCandidate]:
        """规则优先合并：完全重复（key+value+scope）去重；同 key 不同 value
        规则优先（LLM 冲突候选进 audit，不进入正常返回）。

        审计标签区分来源：rule 与 LLM 重复 → dedup-rule-wins/conflict-rule-wins；
        LLM 候选之间重复/冲突 → dedup-llm/conflict-llm。
        """
        rule_full = {(c.key, c.value, c.scope) for c in rule_candidates}
        rule_keys = {c.key for c in rule_candidates}
        merged = list(rule_candidates)
        seen_full = set(rule_full)
        seen_keys = set(rule_keys)
        for c in llm_candidates:
            full = (c.key, c.value, c.scope)
            if full in seen_full:
                label = "dedup-rule-wins" if full in rule_full else "dedup-llm"
                self._audit.append({"kind": "preference", "event_id": trusted_id,
                                    "error": label})
                continue
            if c.key in rule_keys:
                self._audit.append({"kind": "preference", "event_id": trusted_id,
                                    "error": "conflict-rule-wins"})
                continue
            if c.key in seen_keys:
                # LLM 候选之间同 key 不同 value：保守丢弃（避免未复核冲突入候选）
                self._audit.append({"kind": "preference", "event_id": trusted_id,
                                    "error": "conflict-llm"})
                continue
            merged.append(c)
            seen_full.add(full)
            seen_keys.add(c.key)
        return merged

    @property
    def _provider_mode(self) -> ProviderMode:
        """rules=无 LLM（规则路径独立工作）；coop=规则+LLM 协同。"""
        return "rules" if self._llm is None else "coop"

    # ── LLM 路径（D7 超时包装 + Pydantic 非法输出降级 + R4 隔离 + R5 敏感复核） ──

    def _run_llm(self, kind: str,
                 event: TurnFinalizedEvent,
                 trusted_source_event_id: str) -> Tuple[List[Any], bool]:
        """调用注入的 LLM 抽取器，输出经 Pydantic 校验。

        降级语义（Day3 契约 + 台账 D7-A）：
        - LLM 超时（超过 llm_timeout_ms）→ 空候选 + audit(timeout)（真实降级，
          不阻塞；后台线程结果被丢弃）
        - LLM 抛异常 → 空列表（真实降级，不阻塞）
        - 输出非 list / 元素非 dict / 必需字段校验失败 → 进审计（R4：
          不返回非法候选；可选字段非法值 → 字段级降级）
        - 敏感候选（R5）→ 进审计，不进入正常返回

        Returns:
            (合法候选列表, 是否发生 LLM 超时)
        """
        assert self._llm is not None

        def _invoke() -> Any:
            return self._llm(kind, event.user_text or event.assistant_text or "")

        if self._closed:
            return [], False  # Provider 已关闭：LLM 降级为空（规则路径仍可用）

        # 上一次 LLM 调用超时后仍在运行 → 跳过本次调用（避免在单 worker 池中排队拖死），
        # 记 audit；挂起任务完成后自动恢复。
        if self._in_flight is not None and not self._in_flight.done():
            self._audit.append({"kind": kind, "event_id": trusted_source_event_id,
                                "error": "llm-busy-skip"})
            return [], False

        try:
            future = self._executor.submit(_invoke)
            self._in_flight = future
            raw_list = future.result(timeout=self._llm_timeout_ms / 1000.0)
        except concurrent.futures.TimeoutError:
            # 超时：返回空候选列表 + 审计（Day3 契约降级；后台线程结果丢弃，
            # in_flight 保留——下次调用会 skip 直至其完成）
            self._audit.append({"kind": kind, "event_id": trusted_source_event_id,
                                "error": "timeout"})
            return [], True
        except Exception:
            self._in_flight = None  # LLM 内部异常：任务已结束，清除 in-flight
            # LLM 内部异常 → 返回空候选列表（Day3 契约降级）
            return [], False
        finally:
            # 仅在任务确实完成时清空 in-flight；超时未完成的任务保留
            if self._in_flight is not None and self._in_flight.done():
                self._in_flight = None

        if not isinstance(raw_list, list):
            self._audit.append({"kind": kind, "event_id": trusted_source_event_id,
                                "error": "not-a-list"})
            return [], False

        out: List[Any] = []
        for raw in raw_list:
            validated = self._validate_candidate(kind, raw, event,
                                                 trusted_source_event_id)
            if validated is not None:
                out.append(validated)
        return out, False

    def _validate_candidate(self, kind: str, raw: Any,
                            event: TurnFinalizedEvent,
                            trusted_source_event_id: str) -> Optional[Any]:
        """Pydantic 校验单个 LLM 输出候选（R3/R4/R5 + D7 字段级降级）。

        Returns:
            合法且非敏感候选；非法/敏感候选写入 audit 并返回 None
            （R4：非法候选不进入正常 candidates，不允许下游过滤）。

        R3: source_event_id 由系统强制附加——剥离 LLM 提供的任何值。
        R5: 候选内容命中 high/critical 敏感 → 拒绝进审计。
        D7: 偏好路径可选字段非法值先做字段级降级（剥离/默认值 + audit）；
            必需字段（key/value/evidence）缺失/类型错误仍候选级拒绝（R4）。
        """
        if not isinstance(raw, dict):
            self._audit.append({"kind": kind, "event_id": trusted_source_event_id,
                                "error": "not-dict"})
            return None

        # R3: 从 LLM 输出剥离 source_event_id（禁止伪造 provenance）
        raw = {k: v for k, v in raw.items() if k != "source_event_id"}
        # B2: 剥离 LLM 提供的 memory_status（LLM 不能自封 verified），系统强制 candidate
        raw = {k: v for k, v in raw.items() if k != "memory_status"}
        # D7: 偏好路径可选字段非法值降级（候选仍可返回；audit 记录）
        if kind == "preference":
            raw = _degrade_optional_fields(raw, kind, trusted_source_event_id,
                                           self._audit)
        # 系统可信字段强制附加（LLM 无法覆盖）
        merged = {**raw, "source_event_id": trusted_source_event_id,
                  "memory_status": "candidate"}

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

        # MEDIUM-01（PR #36）：is_temporary=True && should_persist=True 业务矛盾
        # → 按 E 轨 §3.2 语义规范化（临时指令不得持久化为正式偏好）+ audit。
        if kind == "preference" and cand.is_temporary and cand.should_persist:
            cand = cand.model_copy(update={"should_persist": False})
            self._audit.append({"kind": kind,
                                "event_id": trusted_source_event_id,
                                "error": "temporary-implies-no-persist"})

        # R5: 敏感复核（候选正文含 high/critical 敏感原文 → 拒绝）
        # 与规则路径（_extract_preferences_rules 复核 value+evidence）一致：
        # preference 复核 value+evidence；knowledge 复核 fact+conditions。
        if kind == "preference":
            check_text = f"{cand.value} {cand.evidence}"
        else:
            check_text = f"{cand.fact} {cand.conditions or ''}"
        if _contains_high_sensitivity(check_text):
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

    @property
    def cache_stats(self) -> Dict[str, int]:
        """抽取缓存统计（size/hits/misses）。"""
        return self._cache.stats
