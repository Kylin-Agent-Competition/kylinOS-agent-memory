"""
knowledge_rules.py — 轨道 A Day8 知识规则（架构 v1 TABLE 21/22/31/17 + E 轨 Schema §2.6/§3.3）

纯函数模块，规则路径独立工作（无 LLM 时六类知识可识别、成功/失败/取消
Tool 不同策略、证据与适用条件保留）。对齐基线：
- 架构 v1 TABLE 21 知识六类：FactMemory（环境事实/版本/路径/配置）、
  ProcedureMemory（步骤和工作流）、CaseMemory（历史问题和解决案例）、
  TemplateMemory（Prompt/命令/文档模板）、ConstraintMemory（安全/技术/
  交付边界）、FailureMemory（失败尝试和不可用方案）
- 架构 v1 TABLE 22：Tool 事实高于模型自述——只有 ToolExecutionEvent.status=success
  且结果字段通过质量校验，才可沉淀"该操作在此环境成功"的知识
- 架构 v1 TABLE 31 ToolExecutionEvent 字段：tool_name/arguments/status/result/
  error/side_effect/user_confirmed/rollback_status/source_trace_id
- 架构 v1 TABLE 17 来源可信度：真实 Tool 成功结果=高（事实/案例/参数经验）；
  Tool 失败/取消=中（失败案例/风险偏好）；模型自身推测=低（候选解释，
  不得作为事实真源）
- E 轨 Schema v0.1 §2.6 knowledge_type 六值（workflow/case/template/fact/
  constraint/failure_experience）、§3.3 Knowledge 对象（content_summary/
  source_event_id/confidence_score/primary_category）

设计要点：
1. 类别识别：关键词/正则命中 → 六类之一；优先级从具体到通用
   （failure > constraint > template > case > procedure > fact）；未命中默认 fact。
2. 抽取策略（B1 红线 + TABLE 17）：
   - 成功 Tool（status=success）→ 成功知识（fact/procedure/case/template/constraint），
     置信度 0.85（真实 Tool 成功结果=高可信）
   - 失败 Tool（status=failure）→ 仅 failure_experience（失败原因/环境/避免条件/
     替代方案），置信度 0.6（中可信）——失败 Tool 不生成成功知识
   - 取消 Tool（status=cancelled）→ 不生成任何知识（用户中止无结论，架构 8 章）
   - 模型推测（无真实 Tool 证据）→ 不进入规则路径（由 Provider B1 门控拒绝）
3. 证据与适用条件保留：evidence/source_event_id 为系统可信 provenance（R3），
   conditions 记录适用条件（tool 名/环境/场景）。
4. 所有函数确定性：同一输入 → 同一输出。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# ── 知识类别（E 轨 Schema §2.6 六值 + 架构 TABLE 21 六类） ──

KNOWLEDGE_CATEGORY_FACT = "fact"                      # FactMemory：环境事实/版本/路径/配置
KNOWLEDGE_CATEGORY_PROCEDURE = "workflow"             # ProcedureMemory：步骤和工作流（E 轨 §2.6 workflow）
KNOWLEDGE_CATEGORY_CASE = "case"                      # CaseMemory：历史问题和解决案例
KNOWLEDGE_CATEGORY_TEMPLATE = "template"              # TemplateMemory：Prompt/命令/文档模板
KNOWLEDGE_CATEGORY_CONSTRAINT = "constraint"          # ConstraintMemory：安全/技术/交付边界
KNOWLEDGE_CATEGORY_FAILURE = "failure_experience"     # FailureMemory：失败尝试和不可用方案

KNOWLEDGE_CATEGORIES: Tuple[str, ...] = (
    KNOWLEDGE_CATEGORY_FACT,
    KNOWLEDGE_CATEGORY_PROCEDURE,
    KNOWLEDGE_CATEGORY_CASE,
    KNOWLEDGE_CATEGORY_TEMPLATE,
    KNOWLEDGE_CATEGORY_CONSTRAINT,
    KNOWLEDGE_CATEGORY_FAILURE,
)

# 类别识别模式（正则，命中任一即归该类；检查顺序 = 优先级，具体 → 通用）
_CATEGORY_PATTERNS: List[Tuple[str, List[re.Pattern]]] = [
    # failure_experience：失败/错误/不可用（最高优先级——失败语义必须独立识别）
    (KNOWLEDGE_CATEGORY_FAILURE, [
        re.compile(r"失败|出错|报错|错误|异常|不可用|无法|不能|没能|失败原因|错误码"),
        re.compile(r"(?i)fail|error|exception|unavailable|cannot|unable|failed"),
    ]),
    # constraint：安全/技术/交付边界（必须/禁止/限制/不超过/务必）
    (KNOWLEDGE_CATEGORY_CONSTRAINT, [
        re.compile(r"必须|禁止|不允许|不得|限制|不超过|不多于|至少|务必|强制|要求"),
        re.compile(r"(?i)must|must not|forbidden|required|mandatory|limited"),
    ]),
    # template：模板/格式/大纲/结构
    (KNOWLEDGE_CATEGORY_TEMPLATE, [
        re.compile(r"模板|格式|大纲|结构|样式|范文|范例|版式|标题格式"),
        re.compile(r"(?i)template|format|outline|layout"),
    ]),
    # case：历史问题/解决案例/经验
    (KNOWLEDGE_CATEGORY_CASE, [
        re.compile(r"案例|经验|遇到(过)?|解决(了|过)?|处理(过)?|之前.{0,10}问题|复现"),
        re.compile(r"(?i)case|example|experience|issue|problem"),
    ]),
    # procedure/workflow：步骤/流程/顺序（先…再…，允许中间出现中文逗号）
    (KNOWLEDGE_CATEGORY_PROCEDURE, [
        re.compile(r"步骤|流程|顺序|操作顺序|先[^。！？]{0,16}再|工作流|流程是"),
        re.compile(r"(?i)steps?|workflow|procedure|sequence"),
    ]),
    # fact：事实性知识（兜底：环境/路径/配置/版本/位置）
    (KNOWLEDGE_CATEGORY_FACT, [
        re.compile(r"路径|目录|配置|版本|位于|安装在|端口|地址|环境是|版本号"),
        re.compile(r"(?i)path|directory|version|installed|located|port"),
    ]),
]


def classify_knowledge_category(text: str) -> str:
    """知识类别识别（架构 TABLE 21 + E 轨 §2.6 六值）。

    按优先级（failure > constraint > template > case > procedure > fact）
    返回首个命中类别；未命中 → fact（事实性知识兜底）。
    """
    if not text:
        return KNOWLEDGE_CATEGORY_FACT
    for category, patterns in _CATEGORY_PATTERNS:
        for pat in patterns:
            if pat.search(text):
                return category
    return KNOWLEDGE_CATEGORY_FACT


# ── Tool 状态常量（架构 TABLE 31 ToolExecutionEvent.status） ──

TOOL_STATUS_SUCCESS = "success"
TOOL_STATUS_FAILURE = "failure"
TOOL_STATUS_CANCELLED = "cancelled"


def is_success_tool_result(status: str, result: Optional[str]) -> bool:
    """B1：是否真实成功 Tool 结果（status=success 且 result 非空）。"""
    return status == TOOL_STATUS_SUCCESS and bool(result and result.strip())


def tool_status_knowledge_policy(status: str) -> str:
    """Tool 状态 → 知识抽取策略（B1 红线 + TABLE 17）。

    - success      → "success"       生成成功知识（六类，高可信 0.85）
    - failure      → "failure"       仅 failure_experience（失败经验，中可信 0.6）
    - cancelled    → "skip"          不生成任何知识（用户中止无结论）
    - 其他/未知    → "skip"          保守跳过（未知状态不沉淀知识）
    """
    if status == TOOL_STATUS_SUCCESS:
        return "success"
    if status == TOOL_STATUS_FAILURE:
        return "failure"
    if status == TOOL_STATUS_CANCELLED:
        return "skip"
    return "skip"


# ── 失败经验结构化（架构 TABLE 21 FailureMemory 必须保留的结构） ──


def build_failure_experience(
    *,
    tool_name: str,
    error: Optional[str],
    arguments: Optional[Dict[str, Any]] = None,
    source_event_id: str,
) -> Dict[str, Any]:
    """失败 Tool → failure_experience 候选结构（TABLE 21 FailureMemory）。

    必须保留：失败原因（error）、环境（tool_name + arguments 摘要）、
    避免条件（从错误信息推导的保守表述）、替代方案（未知 → None）。
    置信度 0.6（架构 TABLE 17：Tool 失败/取消=中可信，用于失败案例/风险偏好）。
    """
    reason = (error or "").strip()
    if not reason:
        reason = f"{tool_name} 执行失败（无错误详情）"
    env_parts = [f"tool={tool_name}"]
    if arguments:
        arg_summary = ",".join(
            f"{k}={v}" for k, v in list(arguments.items())[:5])
        if arg_summary:
            env_parts.append(f"args={arg_summary}")
    conditions = ";".join(env_parts)
    # 避免条件：保守描述（"避免在相同条件下重复 {tool_name}"），确定性输出
    avoid = f"避免在相同条件（{conditions}）下重复执行 {tool_name}"
    return {
        "fact": f"{tool_name} 执行失败：{reason}",
        "category": KNOWLEDGE_CATEGORY_FAILURE,
        "conditions": conditions,
        "evidence": error or reason,          # 失败证据 = 错误详情（系统可信，非模型生成）
        "failure_reason": reason,             # TABLE 21 失败原因
        "avoid_condition": avoid,             # TABLE 21 避免条件
        "alternative": None,                  # TABLE 21 替代方案（未知，不臆造）
        "source_event_id": source_event_id,
        "confidence": 0.6,                    # TABLE 17 中可信
    }


# ── 规则路径置信度基线（架构 TABLE 17 来源可信度） ──


def tool_success_confidence() -> float:
    """真实 Tool 成功结果置信度（TABLE 17：高）。"""
    return 0.85


def tool_failure_confidence() -> float:
    """Tool 失败/取消置信度（TABLE 17：中——仅用于 failure_experience）。"""
    return 0.6
