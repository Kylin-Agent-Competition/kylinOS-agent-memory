"""
test_extraction_provider.py — 轨道 A Day6 ExtractionProvider 测试（R3/R4/R5/H1 修复后）

覆盖：
1. H1: Day3 契约单参数接口 extract_preferences(event) / extract_knowledge(event)
2. 规则路径：显式偏好提取（真实规则）；成功 Tool → 知识；失败/取消 Tool 不产知识
3. R3: source_event_id 系统可信——LLM 无法伪造/覆盖
4. R4: 非法 LLM 输出不进入正常 candidates（进 audit）
5. R5: 敏感 Tool result / user_text 不进入候选（防御性敏感复核）
6. LLM 异常/超时 → 空候选列表（Day3 契约降级）
7. 审计不含正文原文（最小审计）
"""

from providers.extraction_provider import (
    ExtractionProvider,
    KnowledgeCandidate,
    PreferenceCandidate,
    ToolResult,
    TurnFinalizedEvent,
)


def _turn(user_text="", assistant_text="", tool_results=None, source="chat",
          source_event_id=None):
    return TurnFinalizedEvent(
        session_id="sess_e1",
        user_text=user_text,
        assistant_text=assistant_text,
        tool_results=tool_results,
        source=source,
        source_event_id=source_event_id,
    )


# ── H1: 契约单参数接口 ──

def test_contract_signature_single_arg():
    """Day3 契约：extract_preferences(event) / extract_knowledge(event) 单参数。"""
    p = ExtractionProvider()
    ev = _turn(user_text="我喜欢简洁的回答")
    cands = p.extract_preferences(ev)  # 单参数
    assert isinstance(cands, list)
    assert all(isinstance(c, PreferenceCandidate) for c in cands)
    kc = p.extract_knowledge(_turn(tool_results=[ToolResult(
        tool_name="t", arguments={}, status="success", result="目录存在")]))
    assert isinstance(kc, list)


# ── 规则路径：偏好 ──

def test_rules_extract_explicit_preference():
    p = ExtractionProvider()
    ev = _turn(user_text="我喜欢简洁的回答，以后都控制在三句话内",
               source_event_id="evt_e1")
    cands = p.extract_preferences(ev)
    assert len(cands) >= 1
    assert any("三句话" in c.value for c in cands)
    assert all(c.source_event_id == "evt_e1" for c in cands)  # R3


def test_rules_empty_user_text_no_candidates():
    p = ExtractionProvider()
    ev = _turn(user_text="", assistant_text="好的")
    assert p.extract_preferences(ev) == []


def test_rules_trusted_source_event_id_fallback():
    """R3: source_event_id 缺失时用 turn:{session_id} 兜底。"""
    p = ExtractionProvider()
    ev = _turn(user_text="我喜欢中文")  # 未传 source_event_id
    cands = p.extract_preferences(ev)
    assert len(cands) >= 1
    assert all(c.source_event_id == "turn:sess_e1" for c in cands)


# ── 规则路径：知识 ──

def test_rules_tool_success_produces_knowledge():
    p = ExtractionProvider()
    ev = _turn(tool_results=[ToolResult(
        tool_name="file_search", arguments={}, status="success",
        result="/opt/kylin/data 目录存在且可读")], source_event_id="evt_e1")
    cands = p.extract_knowledge(ev)
    assert len(cands) == 1
    assert cands[0].category == "fact"
    assert cands[0].conditions == "tool=file_search"
    assert cands[0].confidence > 0.8
    assert cands[0].source_event_id == "evt_e1"  # R3


def test_rules_tool_failure_no_knowledge():
    """失败 Tool 不生成成功知识（架构 8 章红线）。"""
    p = ExtractionProvider()
    ev = _turn(tool_results=[
        ToolResult(tool_name="install", arguments={}, status="failure",
                   error="dependency not found")])
    assert p.extract_knowledge(ev) == []


def test_rules_tool_cancelled_no_knowledge():
    p = ExtractionProvider()
    ev = _turn(tool_results=[
        ToolResult(tool_name="cmd", arguments={}, status="cancelled", result=None)])
    assert p.extract_knowledge(ev) == []


def test_rules_empty_tool_result_skipped():
    p = ExtractionProvider()
    ev = _turn(tool_results=[ToolResult(
        tool_name="x", arguments={}, status="success", result="")])
    assert p.extract_knowledge(ev) == []


# ── R5: 敏感内容防御性拒绝（规则路径） ──

def test_sensitive_tool_result_not_in_knowledge_fact():
    """R5: 含 API Key 的 Tool success result 不得进入 KnowledgeCandidate.fact。"""
    p = ExtractionProvider()
    ev = _turn(tool_results=[ToolResult(
        tool_name="config", arguments={}, status="success",
        result="部署完成，API key is sk-live-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6")],
        source_event_id="evt_r5")
    cands = p.extract_knowledge(ev)
    # 敏感原文不得进入任何候选
    assert all("sk-live-" not in (c.fact or "") for c in cands)
    assert len(cands) == 0  # 唯一候选被拒绝


def test_sensitive_user_text_not_in_preference_evidence():
    """R5: 含 JWT 的 user_text 不得进入 PreferenceCandidate.evidence。"""
    p = ExtractionProvider()
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    ev = _turn(user_text=f"请记住我的令牌 {jwt} 以后都用它",
               source_event_id="evt_r5b")
    cands = p.extract_preferences(ev)
    for c in cands:
        assert jwt not in c.evidence
        assert jwt not in c.value
    # 该偏好候选整体被拒绝（含敏感）
    assert all(jwt not in c.evidence for c in cands)


def test_sensitive_content_rejected_direct_call():
    """R5: 直接调用 ExtractionProvider（绕过 Pipeline）仍安全阻断。"""
    p = ExtractionProvider()
    ev = _turn(user_text="密码是 P@ssw0rd123456 请记住",
               source_event_id="evt_r5c")
    cands = p.extract_preferences(ev)
    assert all("P@ssw0rd" not in c.evidence for c in cands)
    assert all("P@ssw0rd" not in c.value for c in cands)


# ── LLM 路径：合法候选（R3） ──

def test_llm_valid_candidates_kept_with_trusted_id():
    """R3: 合法候选保留，source_event_id 系统强制。"""
    def llm(kind, text):
        return [{"key": "language", "value": "中文", "confidence": 0.9,
                 "evidence": "用户要求"}]
    p = ExtractionProvider(llm_extractor=llm)
    cands = p.extract_preferences(_turn(user_text="我喜欢中文", source_event_id="evt_llm1"))
    assert len(cands) >= 1
    assert all(c.source_event_id == "evt_llm1" for c in cands)


def test_llm_cannot_forge_source_event_id():
    """R3 负向: LLM 试图伪造 source_event_id → 被系统可信值覆盖。"""
    def llm(kind, text):
        return [{"key": "language", "value": "中文", "confidence": 0.9,
                 "evidence": "e", "source_event_id": "ATTACKER-FORGED-ID"}]
    p = ExtractionProvider(llm_extractor=llm)
    cands = p.extract_preferences(_turn(user_text="我喜欢中文", source_event_id="evt_trusted"))
    assert len(cands) >= 1
    for c in cands:
        assert c.source_event_id == "evt_trusted"
        assert c.source_event_id != "ATTACKER-FORGED-ID"


# ── R4: 非法 LLM 输出隔离（不进入正常 candidates） ──

def test_llm_invalid_missing_field_goes_to_audit_only():
    """R4: 缺必需字段的 LLM 输出 → 不返回候选（仅进 audit）。"""
    def llm(kind, text):
        return [{"key": "language"}]  # 缺 value/confidence/evidence
    p = ExtractionProvider(llm_extractor=llm)
    cands = p.extract_preferences(_turn(source_event_id="evt_r4a"))
    # 非法候选不得出现在正常返回中
    assert cands == []
    # 审计记录存在
    assert len(p.audit) >= 1
    assert "validation" in p.audit[0]["error"]


def test_llm_invalid_wrong_type_goes_to_audit_only():
    def llm(kind, text):
        return [{"key": 123, "value": "x", "confidence": "high",
                 "evidence": "e"}]  # key 非 str / confidence 非 float
    p = ExtractionProvider(llm_extractor=llm)
    assert p.extract_preferences(_turn(source_event_id="evt_r4b")) == []
    assert len(p.audit) >= 1


def test_llm_not_list_returns_empty():
    def llm(kind, text):
        return {"not": "a list"}
    p = ExtractionProvider(llm_extractor=llm)
    assert p.extract_preferences(_turn(source_event_id="evt_r4c")) == []
    assert len(p.audit) == 1


def test_llm_element_not_dict_skipped():
    def llm(kind, text):
        return ["just-a-string"]
    p = ExtractionProvider(llm_extractor=llm)
    assert p.extract_preferences(_turn(source_event_id="evt_r4d")) == []
    assert len(p.audit) == 1


# ── R5: LLM 路径敏感复核 ──

def test_llm_sensitive_candidate_rejected():
    """R5: LLM 输出的候选含敏感原文 → 拒绝进 audit，不进入返回。"""
    def llm(kind, text):
        return [{"key": "cred", "value": "token abc123def456ghi789jkl012",
                 "confidence": 0.9, "evidence": "e"}]
    p = ExtractionProvider(llm_extractor=llm)
    cands = p.extract_preferences(_turn(source_event_id="evt_r5llm"))
    assert cands == []
    assert any("sensitive" in a["error"] for a in p.audit)


# ── LLM 异常/超时降级（Day3 契约） ──

def test_llm_exception_returns_empty():
    def llm(kind, text):
        raise TimeoutError("llm timed out")
    p = ExtractionProvider(llm_extractor=llm)
    # 降级：返回空候选列表，不阻塞
    assert p.extract_preferences(_turn()) == []
    assert p.extract_knowledge(_turn()) == []


# ── 无 LLM：规则路径独立 ──

def test_no_llm_rules_only():
    p = ExtractionProvider()  # llm_extractor=None
    ev = _turn(user_text="请总是用简洁的语言回答")
    cands = p.extract_preferences(ev)
    assert len(cands) >= 1


# ── 审计不含正文原文 ──

def test_audit_does_not_contain_raw_text():
    """审计不含正文原文（最小审计）。"""
    def llm(kind, text):
        return [{"key": "k"}]
    p = ExtractionProvider(llm_extractor=llm)
    p.extract_preferences(_turn(user_text="这是敏感正文不要落审计", source_event_id="evt_aud"))
    for item in p.audit:
        assert "敏感正文不要落审计" not in str(item)
