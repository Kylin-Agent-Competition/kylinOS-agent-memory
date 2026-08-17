"""
test_preference_rules.py — 轨道 A Day7 偏好规则单元测试（providers/preference_rules.py）

覆盖（架构 TABLE 19/20 + E 轨 Schema §2.5/§2.9/§3.2）：
1. 偏好六类识别（presentation/tool_selection/workflow/safety/environment/scene_specific）
2. 临时指令 vs 长期偏好（TABLE 20：is_temporary/should_persist）
3. scope 推导（E 轨 §2.9 五值：global/topic/tool/session/time_window）
4. 类别键派生（E 轨 §3.2 preference_key）
5. 显式/隐式判定（E 轨 §2.5 expression_type）
6. 规则路径置信度基线 + 确定性（同一输入 → 同一输出）
"""

from providers.preference_rules import (
    PREFERENCE_CATEGORY_ENVIRONMENT,
    PREFERENCE_CATEGORY_PRESENTATION,
    PREFERENCE_CATEGORY_SAFETY,
    PREFERENCE_CATEGORY_SCENE_SPECIFIC,
    PREFERENCE_CATEGORY_TOOL_SELECTION,
    PREFERENCE_CATEGORY_WORKFLOW,
    classify_preference_category,
    classify_temporality,
    derive_preference_key,
    derive_preference_scope,
    has_long_term_marker,
    has_temporary_marker,
    is_explicit_expression,
    rule_confidence,
)


# ── 偏好六类识别（架构 TABLE 19） ──

def test_category_presentation():
    assert classify_preference_category("请用简洁的语言回答") == PREFERENCE_CATEGORY_PRESENTATION
    assert classify_preference_category("我喜欢详细的回答") == PREFERENCE_CATEGORY_PRESENTATION


def test_category_tool_selection():
    assert classify_preference_category("优先使用 git 命令行工具") == PREFERENCE_CATEGORY_TOOL_SELECTION
    assert classify_preference_category("以后都改用浏览器打开") == PREFERENCE_CATEGORY_TOOL_SELECTION


def test_category_workflow():
    assert classify_preference_category("先查询再执行，按这个流程来") == PREFERENCE_CATEGORY_WORKFLOW
    assert classify_preference_category("记住这个操作顺序") == PREFERENCE_CATEGORY_WORKFLOW


def test_category_safety():
    assert classify_preference_category("删除文件前必须先确认") == PREFERENCE_CATEGORY_SAFETY
    assert classify_preference_category("高风险操作要提醒我") == PREFERENCE_CATEGORY_SAFETY


def test_category_environment():
    assert classify_preference_category("开发环境用 /opt/kylin 目录") == PREFERENCE_CATEGORY_ENVIRONMENT
    assert classify_preference_category("记住部署服务器的路径") == PREFERENCE_CATEGORY_ENVIRONMENT


def test_category_scene_specific():
    assert classify_preference_category("以后所有会议总结都控制在三段内") == PREFERENCE_CATEGORY_SCENE_SPECIFIC
    assert classify_preference_category("写邮件要正式一点") == PREFERENCE_CATEGORY_SCENE_SPECIFIC


def test_category_default_presentation():
    """未命中任何类别 → 默认 presentation（回答风格兜底）。"""
    assert classify_preference_category("随便") == PREFERENCE_CATEGORY_PRESENTATION
    assert classify_preference_category("") == PREFERENCE_CATEGORY_PRESENTATION


# ── 临时指令 vs 长期偏好（TABLE 20） ──

def test_temporality_temporary_marker():
    """临时指令：这次/本次/现在/今天。"""
    assert has_temporary_marker("这次只用三句话回答")
    assert has_temporary_marker("本次会议总结简短一点")
    assert not has_temporary_marker("以后都用中文")


def test_temporality_long_term_marker():
    """长期偏好标记：以后/总是/每次/永远。"""
    assert has_long_term_marker("以后所有会议总结都控制在三段内")
    assert has_long_term_marker("请总是用简洁的语言回答")
    assert not has_long_term_marker("这次只用一个段落")


def test_classify_temporality_table20_example():
    """架构 TABLE 20 原例：
    - "这次只用三句话回答" → 临时（不产生正式长期偏好）
    - "以后所有会议总结都控制在三段内" → 长期（meeting 场景长期偏好版本）
    """
    assert classify_temporality("这次只用三句话回答") == (True, False)
    assert classify_temporality("以后所有会议总结都控制在三段内") == (False, True)


def test_classify_temporality_no_marker_defaults_long_term():
    """无时间限定词：显式偏好默认持久化候选。"""
    assert classify_temporality("我喜欢中文") == (False, True)


# ── scope 推导（E 轨 §2.9 五值） ──

def test_scope_session():
    assert derive_preference_scope("这次只用三句话回答") == "session"


def test_scope_topic_table20_example():
    """TABLE 20："以后所有会议总结…" → topic（meeting 场景长期偏好版本）。"""
    assert derive_preference_scope("以后所有会议总结都控制在三段内") == "topic"


def test_scope_global():
    assert derive_preference_scope("以后都用中文回答") == "global"
    assert derive_preference_scope("请总是用简洁的语言回答") == "global"


def test_scope_tool():
    assert derive_preference_scope("优先使用 git 命令行工具") == "tool"


def test_scope_time_window():
    assert derive_preference_scope("周末用简洁风格回复") == "time_window"
    assert derive_preference_scope("工作日要详细回答") == "time_window"


def test_scope_default_session():
    """无任何作用域标记 → 保守默认 session（候选阶段）。"""
    assert derive_preference_scope("我喜欢详细回答") == "session"
    assert derive_preference_scope("") == "session"


# ── 类别键派生（E 轨 §3.2 preference_key） ──

def test_key_presentation_subkeys():
    assert derive_preference_key(PREFERENCE_CATEGORY_PRESENTATION, "以后都用中文回答") == "response.language"
    assert derive_preference_key(PREFERENCE_CATEGORY_PRESENTATION, "请简洁回答") == "response.conciseness"
    assert derive_preference_key(PREFERENCE_CATEGORY_PRESENTATION, "回答要详细") == "response.detail"
    assert derive_preference_key(PREFERENCE_CATEGORY_PRESENTATION, "控制在三句话内") == "response.length"
    assert derive_preference_key(PREFERENCE_CATEGORY_PRESENTATION, "语气正式一些") == "response.style"


def test_key_presentation_default_style():
    assert derive_preference_key(PREFERENCE_CATEGORY_PRESENTATION, "随便说说") == "response.style"


def test_key_scene_specific():
    assert derive_preference_key(PREFERENCE_CATEGORY_SCENE_SPECIFIC,
                                 "会议总结要简洁") == "scene.meeting.preference"
    assert derive_preference_key(PREFERENCE_CATEGORY_SCENE_SPECIFIC,
                                 "写邮件正式一点") == "scene.email.preference"
    assert derive_preference_key(PREFERENCE_CATEGORY_SCENE_SPECIFIC, "随便") == "scene.preference"


def test_key_other_categories():
    assert derive_preference_key(PREFERENCE_CATEGORY_TOOL_SELECTION, "优先 git") == "tool_selection.preference"
    assert derive_preference_key(PREFERENCE_CATEGORY_SAFETY, "先确认") == "safety.confirmation"
    assert derive_preference_key(PREFERENCE_CATEGORY_WORKFLOW, "先查再改") == "workflow.preference"
    assert derive_preference_key(PREFERENCE_CATEGORY_ENVIRONMENT, "用 /opt") == "environment.preference"


# ── 显式/隐式判定（E 轨 §2.5） ──

def test_explicitness():
    assert is_explicit_expression("我喜欢简洁的回答")
    assert is_explicit_expression("以后都用中文")
    assert not is_explicit_expression("今天天气不错")
    assert not is_explicit_expression("")


# ── 规则置信度基线 ──

def test_rule_confidence():
    assert rule_confidence(is_temporary=True, has_long_term_marker=False) == 0.6
    assert rule_confidence(is_temporary=False, has_long_term_marker=True) == 0.75
    assert rule_confidence(is_temporary=False, has_long_term_marker=False) == 0.7


# ── 确定性（同一输入 → 同一输出） ──

def test_rules_deterministic():
    text = "以后所有会议总结都控制在三段内"
    assert classify_preference_category(text) == classify_preference_category(text)
    assert derive_preference_scope(text) == derive_preference_scope(text)
    assert classify_temporality(text) == classify_temporality(text)
    assert derive_preference_key(classify_preference_category(text), text) == \
        derive_preference_key(classify_preference_category(text), text)
