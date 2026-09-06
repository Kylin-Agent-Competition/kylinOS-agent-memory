"""
preference_rules.py — 轨道 A Day7 偏好规则（架构 v1 TABLE 19/20 + E 轨 Schema §2.5/§2.9/§3.2）

纯函数模块，规则路径独立工作（无 LLM 时六类偏好可识别、临时/长期可区分、
scope 可推导）。对齐基线：
- 架构 v1 TABLE 19 偏好六类：presentation / tool_selection / workflow /
  safety / environment / scene_specific
- 架构 v1 TABLE 20：临时指令（"这次只用三句话回答"→ session/短时）vs
  长期偏好（"以后所有会议总结都控制在三段内"→ meeting 场景长期偏好版本）
- E 轨 Schema v0.1 §2.5 expression_type（explicit/implicit）、
  §2.9 preference_scope（global/topic/tool/session/time_window）、
  §3.2 Preference 对象（is_temporary/should_persist）

设计要点：
1. 类别识别：关键词/正则命中 → 六类之一；优先级从具体到通用
   （scene_specific > tool_selection > safety > environment > workflow > presentation）；
   未命中默认 presentation（回答风格兜底）。
2. 临时/长期：含长期词（以后/总是/每次/永远/今后）→ 长期；
   含临时词（这次/本次/现在/今天/暂时）且无长期词 → 临时；
   均无 → 默认长期候选（显式偏好应持久化，由评测调优）。
3. scope 推导：time_window > session > tool > topic > global；
   "以后所有会议总结…" → topic（meeting 场景长期偏好版本，TABLE 20 原语）；
   无任何标记 → 保守默认 session（候选阶段，D 轨/评测决定是否提升）。
4. 所有函数确定性：同一输入 → 同一输出。
"""

from __future__ import annotations

import re
from typing import List, Tuple

# ── 偏好类别（架构 TABLE 19 六类） ──

PREFERENCE_CATEGORY_PRESENTATION = "presentation"
PREFERENCE_CATEGORY_TOOL_SELECTION = "tool_selection"
PREFERENCE_CATEGORY_WORKFLOW = "workflow"
PREFERENCE_CATEGORY_SAFETY = "safety"
PREFERENCE_CATEGORY_ENVIRONMENT = "environment"
PREFERENCE_CATEGORY_SCENE_SPECIFIC = "scene_specific"

PREFERENCE_CATEGORIES: Tuple[str, ...] = (
    PREFERENCE_CATEGORY_PRESENTATION,
    PREFERENCE_CATEGORY_TOOL_SELECTION,
    PREFERENCE_CATEGORY_WORKFLOW,
    PREFERENCE_CATEGORY_SAFETY,
    PREFERENCE_CATEGORY_ENVIRONMENT,
    PREFERENCE_CATEGORY_SCENE_SPECIFIC,
)

# 类别识别模式（正则，命中任一即归该类；检查顺序 = 优先级，具体 → 通用）
_CATEGORY_PATTERNS: List[Tuple[str, List[re.Pattern]]] = [
    # scene_specific：具体场景（会议/邮件/周报/总结/学习/写作/课堂/面试）
    (PREFERENCE_CATEGORY_SCENE_SPECIFIC, [
        re.compile(r"会议|周报|报告|总结|课堂|面试"),
        re.compile(r"学习|写作|写作文|邮件|发邮件|回复邮件|工作汇报"),
    ]),
    # tool_selection：工具选择
    (PREFERENCE_CATEGORY_TOOL_SELECTION, [
        re.compile(r"(?i)优先(使用|用|选)?|首选|代替|替代|改用|换用"),
        re.compile(r"(?i)(git|命令行|终端|vim|编辑器|浏览器|搜索工具|翻译工具|计算器)"),
        re.compile(r"用.{0,8}(工具|软件|应用|命令)"),
    ]),
    # safety：高风险操作确认
    (PREFERENCE_CATEGORY_SAFETY, [
        re.compile(r"确认|谨慎|安全|风险|危险|权限|提醒|同意|高权限|慎重"),
    ]),
    # environment：环境/路径/平台
    (PREFERENCE_CATEGORY_ENVIRONMENT, [
        re.compile(r"目录|路径|环境|平台|项目|服务器|部署|开发环境|配置文件"),
    ]),
    # workflow：操作顺序/流程
    (PREFERENCE_CATEGORY_WORKFLOW, [
        re.compile(r"先[^，。！？]{0,12}再"),
        re.compile(r"步骤|流程|操作顺序|执行顺序|按.{0,6}(顺序|流程)"),
    ]),
    # presentation：回答风格（通用兜底）
    (PREFERENCE_CATEGORY_PRESENTATION, [
        re.compile(r"回答|语言|中文|英文|简洁|简单|详细|详尽|格式|风格|语气|口吻|专业"),
        re.compile(r"长度|字数|三句话|一段|分点|列出|表格|精简"),
    ]),
]


def classify_preference_category(text: str) -> str:
    """偏好类别识别（架构 TABLE 19 六类）。

    按优先级（scene_specific > tool_selection > safety > environment >
    workflow > presentation）返回首个命中类别；未命中 → presentation。
    """
    if not text:
        return PREFERENCE_CATEGORY_PRESENTATION
    for category, patterns in _CATEGORY_PATTERNS:
        for pat in patterns:
            if pat.search(text):
                return category
    return PREFERENCE_CATEGORY_PRESENTATION


# ── 临时指令 vs 长期偏好（架构 TABLE 20 + E 轨 §3.2 is_temporary/should_persist） ──

_TEMPORARY_PATTERNS = [
    re.compile(r"这次|本次|现在|当前|今天|暂时|这一(次|回)|这轮|just"),
    re.compile(r"(?i)this time|for now|this turn"),
]
_LONG_TERM_PATTERNS = [
    re.compile(r"以后|今后|从今往后|总是|每次|永远|一直|请总是|之后都|always"),
    re.compile(r"(?i)every time|from now on|always"),
]


def has_long_term_marker(text: str) -> bool:
    """是否含长期偏好标记（以后/总是/每次/永远…）。"""
    if not text:
        return False
    return any(p.search(text) for p in _LONG_TERM_PATTERNS)


def has_temporary_marker(text: str) -> bool:
    """是否含临时指令标记（这次/本次/现在/今天/暂时…）。"""
    if not text:
        return False
    return any(p.search(text) for p in _TEMPORARY_PATTERNS)


def classify_temporality(text: str) -> Tuple[bool, bool]:
    """临时/长期判定 → (is_temporary, should_persist)。

    - 含长期词 → 长期（is_temporary=False, should_persist=True）
    - 含临时词且无长期词 → 临时（is_temporary=True, should_persist=False）
    - 均无 → 默认长期候选（显式偏好应持久化，TABLE 20 语义）
    """
    if has_long_term_marker(text):
        return False, True
    if has_temporary_marker(text):
        return True, False
    return False, True


# ── scope 推导（E 轨 Schema §2.9 五值） ──

_SCOPE_TIME_WINDOW = re.compile(r"工作日|周末|上班时间|下班后|晚上|白天|假期|非工作日")
_SCOPE_SESSION = re.compile(r"这次|本次|现在|当前|今天|这一(次|回)|这轮")
_SCOPE_TOOL = re.compile(r"(?i)(git|命令行|终端|vim|编辑器|浏览器|搜索工具|翻译工具|工具|软件|应用)")
_SCOPE_TOPIC = re.compile(r"会议|周报|报告|总结|学习|写作|邮件|课堂|面试|工作汇报")
_SCOPE_GLOBAL = re.compile(r"以后|今后|从今往后|总是|每次|永远|一直|请总是|always|every time")


def derive_preference_scope(text: str) -> str:
    """偏好作用域推导（E 轨 §2.9：global/topic/tool/session/time_window）。

    优先级：time_window > session > tool > topic > global；
    "以后所有会议总结都控制在三段内" → topic（TABLE 20：meeting 场景
    长期偏好版本）；无任何标记 → 保守默认 session（候选阶段）。
    """
    if not text:
        return "session"
    if _SCOPE_TIME_WINDOW.search(text):
        return "time_window"
    if _SCOPE_SESSION.search(text):
        return "session"
    if _SCOPE_TOOL.search(text):
        return "tool"
    if _SCOPE_TOPIC.search(text):
        return "topic"
    if _SCOPE_GLOBAL.search(text):
        return "global"
    return "session"


# ── 显式/隐式判定（E 轨 §2.5 expression_type） ──

# 显式偏好表述正则（与 extraction_provider 共享语义）：
# - 通用显式词：我喜欢/我偏好/我习惯/请总是/总是/以后/尽量/希望/偏好/更倾向/
#   prefer/like to/always/make sure/i want…；覆盖架构 TABLE 20 长期例
#   "以后所有会议总结都控制在三段内"（"以后" 而非仅 "以后都"）。
# - 显式工具选择偏好标记（D13D Phase 2 pref-003 裁定 A / production PR）：
#   优先使用/优先用/优先选择/首选/默认使用/默认用。此类句子不含通用显式词但明确表达
#   工具选择偏好（如 "优先使用 git 命令行工具"）；若不在显式 admission 覆盖，
#   会落入要求时态限定词的 fallback 指令式模式并产生 false negative。
#   注意：不收录裸 "优先"，避免 "优先保证安全…" 等非工具选择表达被误判为显式偏好。
PREFERENCE_EXPLICIT_PATTERN = re.compile(
    r"(?i)(优先使用|优先用|优先选择|首选|默认使用|默认用|"
    r"我喜欢|我偏好|我习惯|请总是|总是|以后|尽量|希望|偏好|更倾向|prefer|like to|always|"
    r"make sure|i want)\s*[:：]?\s*(.{2,60}?)(?=[，。！？.!?；;]|$)"
)


def is_explicit_expression(text: str) -> bool:
    """是否为显式偏好表达（E 轨 §2.5 explicit）。"""
    return bool(text) and bool(PREFERENCE_EXPLICIT_PATTERN.search(text))


# ── 指令式/临时偏好表达（架构 TABLE 20 临时例） ──

# 指令式表达正则：仅覆盖不含显式偏好词、但表达了明确指令/要求的临时表达。
# 结构：时态限定词（这次/本次/现在/当前/今天，必选）+ 指令动词 + 宾语。
# 覆盖 TABLE 20 原句：“这次只用三句话回答”。
# 设计约束（PR #36 HIGH-01 + MEDIUM-08）：
# - 非硬编码特判：按“时态限定 + 指令动词”通用模式匹配，可推广到同类临时指令；
# - 仅在 PREFERENCE_EXPLICIT_PATTERN 未命中时由主链启用（避免与显式词重复候选）；
# - 指令词集合限定为“数量/长度/形式”类动词；
# - MEDIUM-08 收紧：时态限定词为**必选**——通用“不要/别/保持”等不得单独成为
#   偏好判定依据（如“不要慌，再试一次”/“别问了”/“保持联系”不再误抽取）。
PREFERENCE_INSTRUCTION_PATTERN = re.compile(
    r"(?i)(?:这次|本次|现在|当前|今天)\s*"
    r"(?:只用|控制在|保持|限定在|不超过|不多于|至多|最多|至少|不少于|"
    r"不要|别|改用|换成|分点|列成表格|按表格|按列表)"
    r"\s*(.{2,40}?)(?=[，。！？.!?；;]|$)"
)


# ── 类别键派生（key 为业务语义标识，E 轨 §3.2 preference_key） ──

_PRESENTATION_KEYS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"语言|中文|英文|英语|中文回答|english"), "response.language"),
    (re.compile(r"简洁|简单|精简"), "response.conciseness"),
    (re.compile(r"详细|详尽|具体"), "response.detail"),
    (re.compile(r"长度|字数|三句话|一段|分点|多段"), "response.length"),
    (re.compile(r"格式|风格|语气|口吻|专业|正式|礼貌"), "response.style"),
]

_SCENE_KEYWORDS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"会议|周报|报告|总结"), "meeting"),
    (re.compile(r"学习|课堂|面试"), "study"),
    (re.compile(r"写作|写作文"), "writing"),
    (re.compile(r"邮件|发邮件|回复邮件"), "email"),
    (re.compile(r"工作汇报"), "work"),
]


def _detect_scene(text: str) -> str:
    for pat, scene in _SCENE_KEYWORDS:
        if pat.search(text):
            return scene
    return ""


def derive_preference_key(category: str, text: str) -> str:
    """偏好类别键派生（E 轨 §3.2 preference_key 业务语义标识）。

    - presentation：子键（response.language / response.conciseness /
      response.detail / response.length / response.style），未匹配 → response.style
    - scene_specific：scene.<scene>.preference（meeting/study/writing/email/work）
    - 其余类别：<category>.preference
    """
    if category == PREFERENCE_CATEGORY_PRESENTATION:
        for pat, key in _PRESENTATION_KEYS:
            if pat.search(text):
                return key
        return "response.style"
    if category == PREFERENCE_CATEGORY_SCENE_SPECIFIC:
        scene = _detect_scene(text)
        return f"scene.{scene}.preference" if scene else "scene.preference"
    if category == PREFERENCE_CATEGORY_SAFETY:
        return "safety.confirmation"  # TABLE 19 safety：高风险操作前必须确认
    return f"{category}.preference"


# ── 规则路径置信度基线（E 轨 §3.2 confidence_score：待 A/E 评测调优） ──


def rule_confidence(*, is_temporary: bool, has_long_term_marker: bool) -> float:
    """规则路径置信度基线（显式表述）。

    - 临时指令：0.6（短时效，TABLE 20 不产生正式长期偏好）
    - 长期显式：0.75（跨会话持续意图）
    - 默认显式：0.7（E 轨评测后可调）
    """
    if is_temporary:
        return 0.6
    if has_long_term_marker:
        return 0.75
    return 0.7
