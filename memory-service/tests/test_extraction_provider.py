"""
test_extraction_provider.py — 轨道 A Day6 ExtractionProvider 测试

覆盖：
1. 规则路径：显式偏好提取（真实规则）
2. 规则路径：Tool 成功结果 → 知识；失败/取消 Tool 不生成成功知识（架构 8 章）
3. LLM 路径：Pydantic 非法输出降级（非 dict / 缺字段 / 类型错 → validation_failed，
   不进入业务真源）
4. LLM 异常/超时 → 空候选列表（Day3 契约降级）
5. 无 LLM 注入时规则路径独立工作
"""

from providers.extraction_provider import (
    ExtractionProvider,
    KnowledgeCandidate,
    PreferenceCandidate,
    ToolResult,
    TurnFinalizedEvent,
)


def _turn(user_text="", assistant_text="", tool_results=None, source="chat"):
    return TurnFinalizedEvent(
        session_id="sess_e1",
        user_text=user_text,
        assistant_text=assistant_text,
        tool_results=tool_results,
        source=source,
    )


# ── 规则路径：偏好 ──

def test_rules_extract_explicit_preference():
    p = ExtractionProvider()
    ev = _turn(user_text="我喜欢简洁的回答，以后都控制在三句话内")
    cands = p.extract_preferences(ev, "evt_e1")
    assert len(cands) >= 1
    assert all(c.validation_failed is False for c in cands)
    assert any("三句话" in c.value for c in cands)


def test_rules_empty_user_text_no_candidates():
    p = ExtractionProvider()
    ev = _turn(user_text="", assistant_text="好的")
    assert p.extract_preferences(ev, "evt_e1") == []


# ── 规则路径：知识 ──

def test_rules_tool_success_produces_knowledge():
    p = ExtractionProvider()
    ev = _turn(tool_results=[ToolResult(
        tool_name="file_search", arguments={}, status="success",
        result="/opt/kylin/data 目录存在且可读")])
    cands = p.extract_knowledge(ev, "evt_e1")
    assert len(cands) == 1
    assert cands[0].category == "fact"
    assert cands[0].conditions == "tool=file_search"
    assert cands[0].confidence > 0.8


def test_rules_tool_failure_no_knowledge():
    """失败 Tool 不生成成功知识（架构 8 章红线）。"""
    p = ExtractionProvider()
    ev = _turn(tool_results=[
        ToolResult(tool_name="install", arguments={}, status="failure",
                   error="dependency not found"),
    ])
    assert p.extract_knowledge(ev, "evt_e1") == []


def test_rules_tool_cancelled_no_knowledge():
    p = ExtractionProvider()
    ev = _turn(tool_results=[
        ToolResult(tool_name="cmd", arguments={}, status="cancelled", result=None),
    ])
    assert p.extract_knowledge(ev, "evt_e1") == []


def test_rules_empty_tool_result_skipped():
    p = ExtractionProvider()
    ev = _turn(tool_results=[ToolResult(
        tool_name="x", arguments={}, status="success", result="")])
    assert p.extract_knowledge(ev, "evt_e1") == []


# ── LLM 路径：Pydantic 非法输出降级 ──

def test_llm_valid_candidates_kept():
    def llm(kind, text):
        return [{"key": "language", "value": "中文", "confidence": 0.9,
                 "evidence": "用户要求", "source_event_id": "evt_e1"}]
    p = ExtractionProvider(llm_extractor=llm)
    cands = p.extract_preferences(_turn(user_text="我喜欢中文"), "evt_e1")
    valid = [c for c in cands if not c.validation_failed]
    assert len(valid) >= 1


def test_llm_invalid_missing_field_flags_audit():
    """缺必需字段 → validation_failed=True，不进入业务真源。"""
    def llm(kind, text):
        return [{"key": "language"}]  # 缺 value/confidence/evidence
    p = ExtractionProvider(llm_extractor=llm)
    cands = p.extract_preferences(_turn(), "evt_e1")
    failed = [c for c in cands if c.validation_failed]
    assert len(failed) == 1
    assert failed[0].validation_error is not None
    # 审计记录存在且不含正文原文
    assert len(p.audit) >= 1
    assert "value" in p.audit[0]["error"]


def test_llm_invalid_wrong_type_flags():
    def llm(kind, text):
        return [{"key": 123, "value": "x", "confidence": "high",
                 "evidence": "e", "source_event_id": "s"}]  # key 非 str / confidence 非 float
    p = ExtractionProvider(llm_extractor=llm)
    cands = p.extract_knowledge(_turn(), "evt_e1")
    # knowledge 模型缺 fact → 必失败；此处用 preference 验证类型错
    cands2 = p.extract_preferences(_turn(), "evt_e1")
    failed = [c for c in cands2 if c.validation_failed]
    assert len(failed) == 1


def test_llm_not_list_returns_empty():
    def llm(kind, text):
        return {"not": "a list"}
    p = ExtractionProvider(llm_extractor=llm)
    assert p.extract_preferences(_turn(), "evt_e1") == []
    assert len(p.audit) == 1


def test_llm_element_not_dict_skipped():
    def llm(kind, text):
        return ["just-a-string"]
    p = ExtractionProvider(llm_extractor=llm)
    assert p.extract_preferences(_turn(), "evt_e1") == []
    assert len(p.audit) == 1


# ── LLM 异常/超时降级（Day3 契约） ──

def test_llm_exception_returns_empty():
    def llm(kind, text):
        raise TimeoutError("llm timed out")
    p = ExtractionProvider(llm_extractor=llm)
    # 降级：返回空候选列表，不阻塞
    assert p.extract_preferences(_turn(), "evt_e1") == []
    assert p.extract_knowledge(_turn(), "evt_e1") == []


# ── 无 LLM：规则路径独立 ──

def test_no_llm_rules_only():
    p = ExtractionProvider()  # llm_extractor=None
    ev = _turn(user_text="请总是用简洁的语言回答")
    cands = p.extract_preferences(ev, "evt_e1")
    assert len(cands) >= 1
    assert all(c.validation_failed is False for c in cands)


def test_audit_does_not_contain_raw_text():
    """审计不含正文原文（最小审计）。"""
    def llm(kind, text):
        return [{"key": "k"}]
    p = ExtractionProvider(llm_extractor=llm)
    p.extract_preferences(_turn(user_text="这是敏感正文不要落审计"), "evt_e1")
    for item in p.audit:
        assert "敏感正文不要落审计" not in str(item)
