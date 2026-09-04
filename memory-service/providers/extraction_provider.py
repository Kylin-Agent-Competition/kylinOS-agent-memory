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

D8 阶段（本版，台账 R42）：
1. 知识结构化抽取支持（providers/knowledge_rules.py + KnowledgeCandidate v0.2）：
   - category 六值对齐 E 轨 Schema §2.6（fact/workflow/case/template/
     constraint/failure_experience；Day3 五值 procedure → workflow 命名演进）
   - 六类结构化字段（架构 TABLE 21 必须保留的结构）：evidence/steps/
     expected_result/problem/outcome/reproducible/template_body/parameters/
     priority/failure_reason/avoid_condition/alternative（全可选，向后兼容）
2. 不同抽取策略（B1 红线 + 架构 TABLE 17/22）：
   - 成功 Tool → 六类成功知识（高可信 0.85，TABLE 17 真实 Tool 成功=高）
   - 失败 Tool → 仅 failure_experience（失败原因/环境/避免条件/替代方案，
     中可信 0.6）——失败 Tool 不生成成功知识（B1 + TABLE 22）
   - 取消 Tool → 不生成任何知识（用户中止无结论，架构 8 章）
   - 模型推测（无真实 Tool 证据）→ LLM 成功知识门控拒绝（B1 保持）
3. 失败降级测试：knowledge LLM 非法 category 降级（默认 fact + audit）、
   结构化字段非法值剥离 + audit、R5 敏感复核覆盖结构化字段。
4. 评测输出：KnowledgeExtractionOutput + to_knowledge_evaluation_record()
   + export_knowledge_records() JSONL（E 轨 §3.3 知识评测口径）。

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
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Literal, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipeline.fingerprint import content_fingerprint
from pipeline.sensitive import detect_sensitivity, is_high_or_critical
from providers.knowledge_rules import (
    KNOWLEDGE_CATEGORIES as _KNOWLEDGE_CATEGORIES,
    KNOWLEDGE_CATEGORY_FAILURE,
    build_failure_experience,
    classify_knowledge_category,
    is_success_tool_result,
    tool_failure_confidence,
    tool_status_knowledge_policy,
    tool_success_confidence,
)
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


@dataclass(init=False)
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
    # DRIFT-001（Schema 漂移治理，2026-09-03）：统一采集时间 Canonical 字段为
    # captured_at；collected_at 仅为 legacy transport/read alias（见下方 __init__
    # 与只读 property），禁止 Provider 内继续产生新 collected_at 写字段。
    captured_at: datetime = field(default_factory=lambda: datetime.now().astimezone())

    def __init__(
        self,
        session_id: str,
        user_text: str,
        assistant_text: str,
        tool_results: Optional[List[ToolResult]] = None,
        source: Literal["chat", "tool_result", "manual_config"] = "chat",
        source_event_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        captured_at: Optional[datetime] = None,
        collected_at: Optional[datetime] = None,
    ) -> None:
        """DRIFT-001：Canonical 写字段 captured_at；collected_at 仅 legacy 输入/读别名。

        兼容边界（REWORK R1）：
        - 新 Canonical 写路径：显式传 captured_at（唯一真源）。
        - legacy 构造/传输 payload（含 collected_at）兼容：collected_at 归一为
          captured_at；两字段同给且不一致时按冻结纪律拒绝（fail-closed），
          不允许静默覆盖或另立第二套采集时间字段。
        """
        if (
            captured_at is not None
            and collected_at is not None
            and collected_at != captured_at
        ):
            raise ValueError(
                "DRIFT-001 conflict: collected_at 与 captured_at 同时提供且不一致，"
                "拒绝写入（captured_at 为 Canonical 唯一真值；collected_at 仅 legacy alias）"
            )
        self.session_id = session_id
        self.user_text = user_text
        self.assistant_text = assistant_text
        self.tool_results = tool_results
        self.source = source
        self.source_event_id = source_event_id
        self.occurred_at = (
            occurred_at if occurred_at is not None else datetime.now().astimezone()
        )
        # legacy 仅提供 collected_at 时归一为 captured_at（保持 Canonical 唯一写字段）
        self.captured_at = (
            captured_at
            if captured_at is not None
            else (
                collected_at
                if collected_at is not None
                else datetime.now().astimezone()
            )
        )

    @property
    def collected_at(self) -> datetime:
        """DRIFT-001：legacy 只读 alias → captured_at（Canonical 采集时间唯一真值）。

        读路径归一；写路径禁止（无 setter）。新 Canonical 写一律使用 captured_at。
        """
        return self.captured_at

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
    # HIGH-03（PR #36 R4 严格类型）：required float 必须 strict——
    # 禁止 bool（True→1.0/False→0.0）与字符串数字（"0.9"→0.9）自动转换后进入候选
    confidence: float = Field(strict=True, ge=0.0, le=1.0)
    explicitness: Explicitness = "explicit"  # E 轨 §2.5
    is_temporary: bool = False  # TABLE 20：临时指令 vs 长期偏好
    should_persist: bool = True  # E 轨 §3.2
    evidence: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)  # R3: 系统可信 provenance，禁止 LLM 生成/覆盖
    # B2-mini: 可信级标记——候选仅为 candidate，系统强制设置，LLM 不能改成 verified
    memory_status: Literal["candidate"] = "candidate"


# 知识类别（E 轨 Schema §2.6 六值 + 架构 TABLE 21 六类）
# Day8 契约演进：Day3 五值（fact/procedure/case/template/constraint）→ 六值；
# procedure → workflow 命名对齐 E 轨（架构 TABLE 21 ProcedureMemory）；
# 新增 failure_experience（架构 TABLE 21 FailureMemory）。
KnowledgeCategory = Literal[
    "fact", "workflow", "case", "template", "constraint", "failure_experience"]


class KnowledgeCandidate(BaseModel):
    """知识候选 v0.2（Day3 契约字段 + Day8 六类结构化 + D6 审计字段 + B2 可信级标记）。

    Day8 契约演进（见 docs/day8/01_task_card.md）：
    - category: Day3 五值 → E 轨 §2.6 六值（procedure → workflow；新增 failure_experience）
    - 新增六类结构化字段（架构 TABLE 21 必须保留的结构，全部可选向后兼容）：
      evidence（证据）/ steps+expected_result（workflow）/ problem+outcome+
      reproducible（case）/ template_body+parameters（template）/ priority
      （constraint）/ failure_reason+avoid_condition+alternative（failure）
    """

    model_config = ConfigDict(extra="forbid")

    fact: str = Field(min_length=1)
    category: KnowledgeCategory = "fact"
    conditions: Optional[str] = None
    evidence: Optional[str] = None  # 架构 TABLE 21 证据（R3 系统可信来源，禁止 LLM 伪造）
    source_event_id: str = Field(min_length=1)  # R3: 系统可信 provenance，禁止 LLM 生成/覆盖
    # HIGH-03（PR #36 R4 严格类型）：与 PreferenceCandidate 一致，required float strict
    confidence: float = Field(strict=True, ge=0.0, le=1.0)
    # B2-mini: 可信级标记——候选仅为 candidate，系统强制设置，LLM 不能改成 verified
    memory_status: Literal["candidate"] = "candidate"
    # ── 六类结构化字段（架构 TABLE 21；全可选） ──
    steps: Optional[str] = None            # workflow：前置条件/步骤/流程
    expected_result: Optional[str] = None  # workflow：期望结果
    problem: Optional[str] = None          # case：问题
    outcome: Optional[str] = None          # case：结果
    reproducible: Optional[str] = None     # case：是否复现
    template_body: Optional[str] = None    # template：模板正文
    parameters: Optional[str] = None       # template：参数
    priority: Optional[str] = None         # constraint：优先级
    failure_reason: Optional[str] = None       # failure：失败原因
    avoid_condition: Optional[str] = None      # failure：避免条件
    alternative: Optional[str] = None          # failure：替代方案


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

    - category/scope/explicitness 非枚举或 None → 默认值 + audit（MEDIUM-05 方案 A）
    - is_temporary/should_persist 非 bool 或 None → 剥离（用 Pydantic 默认值）+ audit

    仅作用于偏好路径的可选字段；必需字段（key/value/evidence/confidence）
    缺失或类型错误仍由 Pydantic 校验拒绝（R4：非法候选不进入业务真源）。
    confidence 为契约 required 字段（Day3 契约 + E 轨 §3.2 confidence_score），
    非法值（非数值/越界/缺失/非 strict float）一律 candidate-level reject，
    不做默认值替换（PR #36 HIGH-02/HIGH-03：不得把非法 required 字段重新
    制造成合法业务值）。
    """
    out = dict(raw)
    for fname, valid, default in (
            ("category", _VALID_CATEGORIES, "presentation"),
            ("scope", _VALID_SCOPES, "session"),
            ("explicitness", _VALID_EXPLICITNESS, "explicit")):
        if fname not in out:
            continue  # 字段缺失：Pydantic 默认值即可，非降级对象
        v = out[fname]
        # MEDIUM-05：显式 None 视为非法 optional 值 → 降级默认值 + audit（与
        # “可选字段非法值→默认值/剥离+audit”文档契约一致）；字段缺失不降级
        # isinstance(v, str) 防止 list/dict 等 unhashable 值在集合成员检查时抛 TypeError
        if v is None or not isinstance(v, str) or v not in valid:
            out[fname] = default
            audit.append({"kind": kind, "event_id": trusted_id,
                          "error": f"field-degraded:{fname}"})
    for fname in ("is_temporary", "should_persist"):
        if fname not in out:
            continue  # 字段缺失：Pydantic 默认值即可，非降级对象
        v = out[fname]
        if v is None or not isinstance(v, bool):
            out.pop(fname, None)
            audit.append({"kind": kind, "event_id": trusted_id,
                          "error": f"field-degraded:{fname}"})
    return out


# 知识路径可选字段（D8：category 枚举 + 结构化字符串字段，非法值 → 降级/剥离 + audit）
_KNOWLEDGE_OPTIONAL_STR_FIELDS = (
    "conditions", "evidence", "steps", "expected_result", "problem",
    "outcome", "reproducible", "template_body", "parameters", "priority",
    "failure_reason", "avoid_condition", "alternative",
)


def _degrade_knowledge_fields(raw: Dict[str, Any], kind: str,
                              trusted_id: str,
                              audit: List[Dict[str, Any]]) -> Dict[str, Any]:
    """知识候选可选字段非法值降级（D8，对齐 D7 偏好字段降级语义）。

    - category 非六值枚举或 None → 默认 fact + audit（MEDIUM-05 方案 A）
    - 结构化字段（evidence/steps/…）非 str 或 None → 剥离（Pydantic 默认 None）+ audit

    必需字段（fact/confidence）缺失或类型错误仍候选级拒绝（R4 保持）；
    confidence 为契约 required 字段，非法值一律 reject，不做默认值替换
    （PR #36 HIGH-02/HIGH-03 语义，与偏好路径一致）。
    """
    out = dict(raw)
    v = out.get("category")
    if "category" in out and (v is None or not isinstance(v, str)
                               or v not in _KNOWLEDGE_CATEGORIES):
        out["category"] = "fact"
        audit.append({"kind": kind, "event_id": trusted_id,
                      "error": "field-degraded:category"})
    for fname in _KNOWLEDGE_OPTIONAL_STR_FIELDS:
        if fname not in out:
            continue  # 字段缺失：Pydantic 默认值即可，非降级对象
        fv = out[fname]
        if fv is None or not isinstance(fv, str):
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
    """规则路径：按 Tool 状态分派知识抽取（D8，B1 红线 + 架构 TABLE 17/22）。

    - success   → 六类成功知识（category 由内容识别，高可信 0.85）
    - failure   → 仅 failure_experience（失败原因/环境/避免条件/替代方案，中可信 0.6）
    - cancelled → 不生成任何知识（用户中止无结论）

    R5 安全：Tool result/error 若含 high/critical 敏感原文 → 拒绝进入候选。
    """
    candidates: List[KnowledgeCandidate] = []
    if not event.tool_results:
        return candidates
    for tr in event.tool_results:
        policy = tool_status_knowledge_policy(tr.status)
        if policy == "skip":
            continue  # 取消/未知状态：不沉淀任何知识（B1 + 架构 8 章）
        if policy == "failure":
            # 失败 Tool：仅失败经验知识（非成功知识，TABLE 21 FailureMemory）
            raw = build_failure_experience(
                tool_name=tr.tool_name, error=tr.error, arguments=tr.arguments,
                source_event_id=source_event_id)
            # R5：失败原因/条件含高敏原文 → 拒绝（凭据类错误信息不落知识）
            if _contains_high_sensitivity(
                    f"{raw['fact']} {raw.get('conditions') or ''}"):
                continue
            candidates.append(KnowledgeCandidate(**raw))
            continue
        # success：成功知识（六类识别 + 证据 + 适用条件）
        fact = (tr.result or "").strip()
        if not fact or len(fact) < 8:
            continue
        # R5 防御性敏感复核：Tool 结果含高敏原文（API Key/JWT 等）→ 拒绝
        if _contains_high_sensitivity(fact):
            continue
        candidates.append(KnowledgeCandidate(
            fact=fact,
            category=classify_knowledge_category(fact),
            conditions=f"tool={tr.tool_name}",
            evidence=tr.result[:200],  # 架构 TABLE 21 证据（截断防超长；R3 系统可信来源）
            source_event_id=source_event_id,
            confidence=tool_success_confidence(),  # 真实 Tool 成功结果高可信（TABLE 17）
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
    """事件内容文本（user_text + assistant_text + Tool 结果），用于缓存键指纹。

    D8：包含 tool arguments（failure_experience 的 conditions 内嵌参数摘要，
    同 tool 同名/同 error 但参数不同的事件不得串缓存键——Review 修复）。
    """
    parts = [event.user_text or "", event.assistant_text or ""]
    for tr in event.tool_results or []:
        arg_text = ""
        if tr.arguments:
            arg_text = ",".join(
                f"{k}={v}" for k, v in list(tr.arguments.items())[:5])
        parts.append(
            f"{tr.tool_name}:{tr.status}:{tr.result or ''}:{tr.error or ''}:{arg_text}")
    return "\n".join(parts)


def _preference_cache_key(event: TurnFinalizedEvent) -> Tuple[str, str, str]:
    """偏好抽取缓存键：kind + 可信 source_event_id + 内容指纹。"""
    return ("preference", event.trusted_source_event_id,
            content_fingerprint(_event_content_text(event)))


# ── LRU 抽取缓存（D7） ──


class PreferenceExtractionCache:
    """LRU 抽取结果缓存（键 = kind + source_event_id + 内容指纹）。

    线程安全。D10 REWORK：
    - generation 代次：每次失效/清空递增，set() 检查代次拒绝 stale write
    - event_tombstones：event-only deletion 阻止 MISS→in-flight→completion 写回
    - clear() 递增代次而非清空 tombstone，解决 FULL_RESET 旧请求恢复问题
    """

    _MISS = object()

    def __init__(self, capacity: int = 256,
                 ttl_seconds: Optional[float] = None) -> None:
        assert capacity > 0, "cache capacity must be > 0"
        self._capacity = capacity
        self._ttl = ttl_seconds
        self._data: "OrderedDict[Tuple[str, str, str], Tuple[float, List[PreferenceCandidate]]]" = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()
        self._generation = 0
        self._event_tombstones: Set[str] = set()

    @property
    def generation(self) -> int:
        return self._generation

    def get(self, key: Tuple[str, str, str]) -> Optional[List[Any]]:
        with self._lock:
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

    def set(self, key: Tuple[str, str, str], candidates: List[Any],
            generation: Optional[int] = None) -> bool:
        """写入缓存。返回 True=成功，False=被 generation/event-tombstone 拒绝。

        Args:
            generation: 捕获时的代次。若提供且与当前代次不匹配，拒绝写入。
        """
        with self._lock:
            if generation is not None and self._generation != generation:
                return False
            if key[1] in self._event_tombstones:
                return False
            self._data[key] = (time.monotonic(),
                               [c.model_copy(deep=True) for c in candidates])
            self._data.move_to_end(key)
            while len(self._data) > self._capacity:
                self._data.popitem(last=False)
            return True

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._event_tombstones.clear()
            self._generation += 1
            self._hits = 0
            self._misses = 0

    def invalidate_by_event(self, event_id: str) -> int:
        removed = 0
        with self._lock:
            self._generation += 1
            self._event_tombstones.add(event_id)
            keys_to_delete = [k for k in self._data if k[1] == event_id]
            for k in keys_to_delete:
                del self._data[k]
                removed += 1
            return removed

    def invalidate_by_content(self, content_fingerprint: str) -> int:
        removed = 0
        with self._lock:
            self._generation += 1
            keys_to_delete = [k for k in self._data if k[2] == content_fingerprint]
            for k in keys_to_delete:
                del self._data[k]
                removed += 1
            return removed

    @property
    def stats(self) -> Dict[str, int]:
        with self._lock:
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


class KnowledgeExtractionOutput(BaseModel):
    """一次知识提取的完整输出（D8，供 E 轨 D8 知识评测与可观测性）。"""

    model_config = ConfigDict(extra="forbid")

    event_id: str  # 可信 source_event_id（R3）
    provider_mode: ProviderMode
    candidates: List[KnowledgeCandidate]
    cache_hit: bool = False
    llm_timeout: bool = False
    duration_ms: float = 0.0


def to_knowledge_evaluation_record(candidate: KnowledgeCandidate) -> Dict[str, Any]:
    """单知识候选 → 字段级统一评测结果格式（E 轨 §3.3 知识评测口径）。

    字段与 E 轨 Schema §3.3 / 架构 TABLE 21 对齐：fact（content_summary 语义）/
    category（knowledge_type）/conditions/evidence/source_event_id/confidence/
    memory_status + 六类结构化字段——供知识检索/冲突评测 Gold Label 比对。
    """
    return {
        "fact": candidate.fact,
        "category": candidate.category,
        "conditions": candidate.conditions,
        "evidence": candidate.evidence,
        "source_event_id": candidate.source_event_id,
        "confidence": candidate.confidence,
        "memory_status": candidate.memory_status,
        "steps": candidate.steps,
        "expected_result": candidate.expected_result,
        "problem": candidate.problem,
        "outcome": candidate.outcome,
        "reproducible": candidate.reproducible,
        "template_body": candidate.template_body,
        "parameters": candidate.parameters,
        "priority": candidate.priority,
        "failure_reason": candidate.failure_reason,
        "avoid_condition": candidate.avoid_condition,
        "alternative": candidate.alternative,
    }


def export_knowledge_records(events: List[TurnFinalizedEvent],
                             provider: "ExtractionProvider",
                             path: str) -> int:
    """批量提取并导出 JSONL 知识评测记录（每行一个 KnowledgeExtractionOutput）。"""
    written = 0
    with open(path, "w", encoding="utf-8") as f:
        for ev in events:
            out = provider.extract_knowledge_with_meta(ev)
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
        # [TD-A-D7-LLM-HANG-DEGRADE 已解决] 挂死恢复机制：
        # in-flight 任务持续超过 hang_threshold 仍未完成 → 判定 LLM 永久挂死，
        # 重建 executor（释放挂死 worker）恢复 LLM 路径，避免整个进程生命周期内
        # 永久 busy-skip（台账验收标准：接入真实 LLM 前必须提供恢复能力之一）。
        self._llm_hang_threshold_ms = 60000.0  # 默认 60s：远大于单次超时（5s），
        #                              只针对真正挂死（非慢任务），避免误重建
        self._hang_recovered = 0  # 统计：挂死恢复次数（可观测性）
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

        D10 REWORK HIGH-3：捕获 generation，set() 失败时返回空候选
        （stale result 不向下游传播）。
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

        gen = self._cache.generation
        rule_candidates = _extract_preferences_rules(event, trusted_id)
        llm_candidates: List[PreferenceCandidate] = []
        llm_timeout = False
        if self._llm is not None:
            llm_candidates, llm_timeout = self._run_llm(
                "preference", event, trusted_id)
        merged = self._merge_rule_and_llm(
            rule_candidates, llm_candidates, trusted_id)
        write_ok = self._cache.set(cache_key, merged, generation=gen)

        if not write_ok:
            return PreferenceExtractionOutput(
                event_id=trusted_id,
                provider_mode=self._provider_mode,
                candidates=[],
                cache_hit=False,
                llm_timeout=llm_timeout,
                duration_ms=(time.monotonic() - start) * 1000.0,
            )

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
        D8: 规则路径按 Tool 状态分派（成功→六类；失败→failure_experience；
        取消→跳过）；LLM 门控保持（无 success Tool 时 LLM 成功知识拒绝）。
        """
        return self.extract_knowledge_with_meta(event).candidates

    def extract_knowledge_with_meta(
        self, event: TurnFinalizedEvent
    ) -> KnowledgeExtractionOutput:
        """提取知识候选 + 元信息（D8：缓存命中/模式/超时/耗时）。

        D10 REWORK HIGH-3：捕获 generation，set() 失败时返回空候选。
        """
        start = time.monotonic()
        trusted_id = event.trusted_source_event_id
        cache_key = ("knowledge", trusted_id,
                     content_fingerprint(_event_content_text(event)))

        cached = self._cache.get(cache_key)
        if cached is not None:
            return KnowledgeExtractionOutput(
                event_id=trusted_id,
                provider_mode=self._provider_mode,
                candidates=cached,
                cache_hit=True,
                duration_ms=(time.monotonic() - start) * 1000.0,
            )

        gen = self._cache.generation
        rule_candidates = _extract_knowledge_rules(event, trusted_id)
        llm_timeout = False
        if self._llm is None:
            write_ok = self._cache.set(cache_key, rule_candidates, generation=gen)
            return KnowledgeExtractionOutput(
                event_id=trusted_id,
                provider_mode=self._provider_mode,
                candidates=rule_candidates if write_ok else [],
                cache_hit=False,
                duration_ms=(time.monotonic() - start) * 1000.0,
            )

        # B1 门控：必须有真实 success Tool evidence 才允许 knowledge LLM 提取
        success_tools = [
            tr for tr in (event.tool_results or [])
            if is_success_tool_result(tr.status, tr.result)]
        if not success_tools:
            self._audit.append({
                "kind": "knowledge",
                "event_id": trusted_id,
                "error": "no-success-tool-evidence: llm knowledge rejected",
            })
            write_ok = self._cache.set(cache_key, rule_candidates, generation=gen)
            return KnowledgeExtractionOutput(
                event_id=trusted_id,
                provider_mode=self._provider_mode,
                candidates=rule_candidates if write_ok else [],
                cache_hit=False,
                duration_ms=(time.monotonic() - start) * 1000.0,
            )

        # [TD-A-D6-LLM-TOOL-INPUT 已解决] 候选级 ToolResult 绑定：
        # LLM 输入 = 具体 success ToolResult.result 拼接（含 tool 名），
        # 建立 candidate → ToolResult 的 provenance 基础（架构 TABLE 22：
        # Tool 事实高于模型自述——抽取以真实 Tool 结果为事实基础）。
        tool_context = "\n".join(
            f"[tool:{tr.tool_name} success]\n{tr.result}"
            for tr in success_tools)

        llm_candidates, llm_timeout = self._run_llm(
            "knowledge", event, trusted_id, tool_context=tool_context)
        merged = rule_candidates + llm_candidates
        write_ok = self._cache.set(cache_key, merged, generation=gen)
        return KnowledgeExtractionOutput(
            event_id=trusted_id,
            provider_mode=self._provider_mode,
            candidates=merged if write_ok else [],
            cache_hit=False,
            llm_timeout=llm_timeout,
            duration_ms=(time.monotonic() - start) * 1000.0,
        )

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

    def _in_flight_timeout(self) -> bool:
        """[TD-A-D7-LLM-HANG-DEGRADE] in-flight 是否已挂死超过阈值。"""
        started = getattr(self, "_in_flight_started", None)
        if started is None:
            return False
        return (time.monotonic() - started) * 1000.0 > self._llm_hang_threshold_ms

    def _rebuild_executor(self, kind: str, trusted_id: str) -> None:
        """[TD-A-D7-LLM-HANG-DEGRADE] 重建 LLM executor（释放挂死 worker）。

        - 旧 executor 挂死 worker 无法 join（任务永不结束）→ shutdown(wait=False)
        - 新 executor 替换 self._executor，后续 submit 在新池执行
        - in_flight 引用清除（不再阻塞新调用）
        """
        try:
            self._executor.shutdown(wait=False)
        except Exception:  # noqa: BLE001 - 重建路径尽力而为
            pass
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="llm-extract")
        self._in_flight = None
        self._in_flight_started = None
        self._audit.append({"kind": kind, "event_id": trusted_id,
                            "error": "llm-executor-rebuilt"})

    def _run_llm(self, kind: str,
                 event: TurnFinalizedEvent,
                 trusted_source_event_id: str,
                 tool_context: Optional[str] = None) -> Tuple[List[Any], bool]:
        """调用注入的 LLM 抽取器，输出经 Pydantic 校验。

        降级语义（Day3 契约 + 台账 D7-A）：
        - LLM 超时（超过 llm_timeout_ms）→ 空候选 + audit(timeout)（真实降级，
          不阻塞；后台线程结果被丢弃）
        - LLM 抛异常 → 空列表（真实降级，不阻塞）
        - 输出非 list / 元素非 dict / 必需字段校验失败 → 进审计（R4：
          不返回非法候选；可选字段非法值 → 字段级降级）
        - 敏感候选（R5）→ 进审计，不进入正常返回

        Args:
            kind: "preference" | "knowledge"
            event: Turn 事件。
            trusted_source_event_id: R3 可信事件 ID。
            tool_context: [TD-A-D6-LLM-TOOL-INPUT 已解决] knowledge 路径的
                候选级 ToolResult 上下文——具体 success ToolResult.result 的
                拼接文本，绑定 LLM 输入（不再仅靠事件级门控的
                user_text/assistant_text）。preference 路径传 None。

        Returns:
            (合法候选列表, 是否发生 LLM 超时)
        """
        assert self._llm is not None

        def _invoke() -> Any:
            if tool_context:
                # TD-A-D6-LLM-TOOL-INPUT：输入绑定具体 success ToolResult.result
                # （架构 TABLE 22：Tool 事实高于模型自述——LLM 抽取以真实
                # Tool 结果为事实基础，而非模型自述）
                return self._llm(kind, tool_context)
            return self._llm(kind, event.user_text or event.assistant_text or "")

        if self._closed:
            return [], False  # Provider 已关闭：LLM 降级为空（规则路径仍可用）

        # 上一次 LLM 调用超时后仍在运行 → 跳过本次调用（避免在单 worker 池中排队拖死），
        # 记 audit；挂起任务完成后自动恢复。
        if self._in_flight is not None and not self._in_flight.done():
            # [TD-A-D7-LLM-HANG-DEGRADE] 挂死检测：in-flight 持续超过阈值
            # → 重建 executor 释放挂死 worker，恢复 LLM 路径（而非永久 busy-skip）
            if self._in_flight_timeout():
                self._rebuild_executor(kind, trusted_source_event_id)
                self._audit.append({"kind": kind,
                                    "event_id": trusted_source_event_id,
                                    "error": "llm-hang-recovered"})
                self._hang_recovered += 1
            else:
                self._audit.append({"kind": kind,
                                    "event_id": trusted_source_event_id,
                                    "error": "llm-busy-skip"})
            return [], False

        try:
            future = self._executor.submit(_invoke)
            self._in_flight = future
            self._in_flight_started = time.monotonic()
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
        D8: knowledge 路径同时剥离 LLM 提供的 evidence——evidence 为系统可信
            证据来源（架构 TABLE 22：Tool 事实高于模型自述），LLM 不得伪造证据。
        """
        if not isinstance(raw, dict):
            self._audit.append({"kind": kind, "event_id": trusted_source_event_id,
                                "error": "not-dict"})
            return None

        # R3: 从 LLM 输出剥离 source_event_id（禁止伪造 provenance）
        raw = {k: v for k, v in raw.items() if k != "source_event_id"}
        # B2: 剥离 LLM 提供的 memory_status（LLM 不能自封 verified），系统强制 candidate
        raw = {k: v for k, v in raw.items() if k != "memory_status"}
        # D8 Review 修复（R3 强化）：knowledge 路径剥离 LLM 提供的 evidence——
        # evidence 为系统可信证据来源（架构 TABLE 22：Tool 事实高于模型自述），
        # LLM 自述不得充当证据；规则路径证据由系统从真实 ToolResult 附加。
        if kind == "knowledge":
            raw = {k: v for k, v in raw.items() if k != "evidence"}
        # D7: 偏好路径可选字段非法值降级（候选仍可返回；audit 记录）
        if kind == "preference":
            raw = _degrade_optional_fields(raw, kind, trusted_source_event_id,
                                           self._audit)
        # D8: 知识路径可选字段非法值降级（category 默认 fact；结构化字段剥离 + audit）
        elif kind == "knowledge":
            raw = _degrade_knowledge_fields(raw, kind, trusted_source_event_id,
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
        # preference 复核 value+evidence；knowledge 复核 fact+conditions+
        # 全部结构化字段（D8：防止敏感原文藏在 evidence/失败原因/模板正文等）。
        if kind == "preference":
            check_text = f"{cand.value} {cand.evidence}"
        else:
            structured_parts = [
                getattr(cand, f) for f in _KNOWLEDGE_OPTIONAL_STR_FIELDS
                if getattr(cand, f, None)
            ]
            check_text = " ".join(
                [cand.fact, cand.conditions or ""] + list(structured_parts))
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
