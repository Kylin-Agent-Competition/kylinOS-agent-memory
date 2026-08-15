"""
test_knowledge_extraction_d8.py — 轨道 A Day8 知识结构化抽取测试

覆盖（docs/day8/01_task_card.md，台账 R42）：
1. 六类知识识别（架构 TABLE 21 + E 轨 §2.6）：
   fact / workflow / case / template / constraint / failure_experience
2. 不同 Tool 状态抽取策略（B1 红线 + 架构 TABLE 17/22）：
   - success Tool → 六类成功知识（高可信 0.85）
   - failure Tool → 仅 failure_experience（失败原因/环境/避免条件/替代方案，
     中可信 0.6）——不生成成功知识
   - cancelled Tool → 不生成任何知识
   - timeout/partial/未知状态 → 保守跳过（不沉淀知识）
   - 模型推测（无真实 success Tool 证据）→ LLM 成功知识门控拒绝（B1）
3. 失败降级测试：
   - knowledge LLM 非法 category → 默认 fact + audit
   - knowledge 结构化字段非法值 → 剥离 + audit
   - LLM 超时/异常 → 空候选 + audit（不阻塞）
   - R5 敏感复核覆盖结构化字段（evidence/failure_reason/template_body 等）
4. 评测输出：KnowledgeExtractionOutput / to_knowledge_evaluation_record /
   export_knowledge_records（E 轨 §3.3 口径）
5. 契约保持：extract_knowledge(event) 单参数；缓存/超时包装与偏好一致
"""

import json
import time

from providers.extraction_provider import (
    ExtractionProvider,
    KnowledgeCandidate,
    KnowledgeExtractionOutput,
    ToolResult,
    export_knowledge_records,
    to_knowledge_evaluation_record,
)


def _turn(user_text="", assistant_text="", tool_results=None, source="chat",
          source_event_id=None):
    from providers.extraction_provider import TurnFinalizedEvent
    return TurnFinalizedEvent(
        session_id="sess_d8",
        user_text=user_text,
        assistant_text=assistant_text,
        tool_results=tool_results,
        source=source,
        source_event_id=source_event_id,
    )


# ── 1. 六类知识识别（架构 TABLE 21 + E 轨 §2.6） ──

def test_d8_knowledge_category_fact():
    """FactMemory：环境事实/路径/版本 → fact。"""
    from providers.knowledge_rules import classify_knowledge_category
    assert classify_knowledge_category(
        "/opt/kylin/data 目录存在且可读") == "fact"
    assert classify_knowledge_category(
        "Python 3.12 安装在 /usr/bin/python3") == "fact"


def test_d8_knowledge_category_workflow():
    """ProcedureMemory：步骤/流程/先…再 → workflow。"""
    from providers.knowledge_rules import classify_knowledge_category
    assert classify_knowledge_category(
        "先备份配置文件，再执行升级命令") == "workflow"
    assert classify_knowledge_category(
        "操作顺序：停止服务 → 更新包 → 启动服务") == "workflow"


def test_d8_knowledge_category_case():
    """CaseMemory：历史问题/解决案例 → case。"""
    from providers.knowledge_rules import classify_knowledge_category
    assert classify_knowledge_category(
        "之前遇到过磁盘满的问题，通过清理日志解决") == "case"


def test_d8_knowledge_category_template():
    """TemplateMemory：模板/格式/结构 → template。"""
    from providers.knowledge_rules import classify_knowledge_category
    assert classify_knowledge_category(
        "周报模板：本周进展、下周计划、风险") == "template"


def test_d8_knowledge_category_constraint():
    """ConstraintMemory：必须/禁止/限制 → constraint。"""
    from providers.knowledge_rules import classify_knowledge_category
    assert classify_knowledge_category(
        "生产环境禁止直接执行删除命令") == "constraint"


def test_d8_knowledge_category_failure():
    """FailureMemory：失败/错误/不可用 → failure_experience（最高优先级）。"""
    from providers.knowledge_rules import classify_knowledge_category
    assert classify_knowledge_category(
        "升级失败：依赖包不存在，错误码 404") == "failure_experience"


# ── 2. 不同 Tool 状态抽取策略（B1 + 架构 TABLE 17/22） ──

def test_d8_success_tool_six_category_with_evidence():
    """success Tool → 六类成功知识 + evidence（架构 TABLE 21 证据字段）。"""
    p = ExtractionProvider()
    ev = _turn(tool_results=[ToolResult(
        tool_name="file_search", arguments={}, status="success",
        result="/opt/kylin/data 目录存在且可读")], source_event_id="evt_d8s1")
    cands = p.extract_knowledge(ev)
    assert len(cands) == 1
    c = cands[0]
    assert c.category == "fact"
    assert c.evidence == "/opt/kylin/data 目录存在且可读"  # TABLE 21 证据
    assert c.conditions == "tool=file_search"
    assert c.confidence == 0.85  # TABLE 17 真实 Tool 成功=高
    assert c.source_event_id == "evt_d8s1"  # R3
    assert c.memory_status == "candidate"  # B2


def test_d8_success_tool_classifies_workflow():
    """success Tool 结果含步骤 → workflow 类别（非硬编码 fact）。"""
    p = ExtractionProvider()
    ev = _turn(tool_results=[ToolResult(
        tool_name="upgrade", arguments={}, status="success",
        result="先备份配置文件，再执行升级命令，最后验证版本")],
        source_event_id="evt_d8s2")
    cands = p.extract_knowledge(ev)
    assert len(cands) == 1
    assert cands[0].category == "workflow"


def test_d8_failure_tool_only_failure_experience():
    """failure Tool → 仅 failure_experience（非成功知识，TABLE 21 FailureMemory）。"""
    p = ExtractionProvider()
    ev = _turn(tool_results=[ToolResult(
        tool_name="install", arguments={"pkg": "vim"}, status="failure",
        error="dependency not found")], source_event_id="evt_d8f1")
    cands = p.extract_knowledge(ev)
    assert len(cands) == 1
    c = cands[0]
    assert c.category == "failure_experience"
    assert c.failure_reason == "dependency not found"  # TABLE 21 失败原因
    assert "tool=install" in c.conditions  # TABLE 21 环境
    assert c.avoid_condition  # TABLE 21 避免条件
    assert c.alternative is None  # TABLE 21 替代方案（未知不臆造）
    assert c.confidence == 0.6  # TABLE 17 失败=中可信


def test_d8_failure_tool_does_not_produce_success_knowledge():
    """B1：失败 Tool 绝不生成 fact/case 等成功知识。"""
    p = ExtractionProvider()
    ev = _turn(tool_results=[ToolResult(
        tool_name="config", arguments={}, status="failure",
        error="perm denied")], source_event_id="evt_d8f2")
    cands = p.extract_knowledge(ev)
    assert all(c.category == "failure_experience" for c in cands)
    assert all("成功" not in c.fact for c in cands)


def test_d8_cancelled_tool_no_knowledge():
    """cancelled Tool → 不生成任何知识（用户中止无结论，架构 8 章）。"""
    p = ExtractionProvider()
    ev = _turn(tool_results=[ToolResult(
        tool_name="cmd", arguments={}, status="cancelled", result=None)],
        source_event_id="evt_d8c1")
    assert p.extract_knowledge(ev) == []


def test_d8_timeout_partial_unknown_skip():
    """timeout/partial/未知状态 → 保守跳过（漏记非错记，B1 + TD 语义）。"""
    p = ExtractionProvider()
    for status in ("timeout", "partial", "unknown", "pending"):
        ev = _turn(tool_results=[ToolResult(
            tool_name="t", arguments={}, status=status, result="部分结果")],
            source_event_id=f"evt_d8skip_{status}")
        assert p.extract_knowledge(ev) == [], status


def test_d8_mixed_tool_results_success_and_failure():
    """同事件混合 success+failure：成功知识 + 失败经验共存，类别互不混淆。"""
    p = ExtractionProvider()
    ev = _turn(tool_results=[
        ToolResult(tool_name="search", arguments={}, status="success",
                   result="/opt/data 目录存在且可读"),
        ToolResult(tool_name="install", arguments={}, status="failure",
                   error="dependency not found"),
        ToolResult(tool_name="cleanup", arguments={}, status="cancelled"),
    ], source_event_id="evt_d8mix")
    cands = p.extract_knowledge(ev)
    cats = {c.category for c in cands}
    assert "fact" in cats  # success → 成功知识
    assert "failure_experience" in cats  # failure → 失败经验
    assert "cancelled" not in cats  # cancelled → 无知识


# ── 3. 失败降级测试（D8） ──

def test_d8_llm_invalid_category_degrades_to_fact():
    """knowledge LLM 输出非法 category → 降级默认 fact + audit（可选字段降级）。"""
    def llm(kind, text):
        return [{"fact": "工具执行完成", "category": "not-a-category",
                 "confidence": 0.9}]
    p = ExtractionProvider(llm_extractor=llm)
    ev = _turn(assistant_text="工具执行成功",
               tool_results=[ToolResult(tool_name="x", arguments={},
                                        status="success", result="工具执行完成")],
               source_event_id="evt_d8deg1")
    cands = p.extract_knowledge(ev)
    assert any(c.category == "fact" for c in cands)
    assert any("field-degraded:category" in a["error"] for a in p.audit)


def test_d8_llm_invalid_structured_field_stripped():
    """knowledge 结构化字段非法值（非 str）→ 剥离 + audit（候选仍返回）。"""
    def llm(kind, text):
        return [{"fact": "先备份再升级", "category": "workflow",
                 "confidence": 0.9, "steps": ["step1", "step2"]}]  # list 非法
    p = ExtractionProvider(llm_extractor=llm)
    ev = _turn(assistant_text="工具执行成功",
               tool_results=[ToolResult(tool_name="x", arguments={},
                                        status="success", result="先备份再升级")],
               source_event_id="evt_d8deg2")
    cands = p.extract_knowledge(ev)
    assert len(cands) == 1
    assert cands[0].steps is None  # 剥离非法 list
    assert any("field-degraded:steps" in a["error"] for a in p.audit)


def test_d8_llm_required_fields_still_rejected():
    """R4：knowledge 必需字段（fact/confidence）缺失/类型错误仍候选级拒绝。"""
    def llm(kind, text):
        return [{"category": "fact"}]  # 缺 fact/confidence
    p = ExtractionProvider(llm_extractor=llm)
    ev = _turn(assistant_text="工具执行成功",
               tool_results=[ToolResult(tool_name="x", arguments={},
                                        status="success", result="工具执行完成")],
               source_event_id="evt_d8r4")
    assert all(c.fact != "" for c in p.extract_knowledge(ev))
    assert any("validation" in a["error"] for a in p.audit)


def test_d8_llm_timeout_knowledge_degrades():
    """LLM 超时 → 空候选 + audit(timeout)（Day3 契约降级，不阻塞）。"""
    def slow_llm(kind, text):
        time.sleep(1.0)
        return [{"fact": "f", "category": "fact", "confidence": 0.9}]
    p = ExtractionProvider(llm_extractor=slow_llm, llm_timeout_ms=50)
    ev = _turn(assistant_text="工具执行成功",
               tool_results=[ToolResult(tool_name="x", arguments={},
                                        status="success", result="配置已更新")],
               source_event_id="evt_d8to")
    out = p.extract_knowledge_with_meta(ev)
    assert all(c.fact != "f" for c in out.candidates)  # LLM 超时被降级
    assert out.llm_timeout is True
    assert any(a["error"] == "timeout" for a in p.audit)
    p.close()


def test_d8_sensitive_in_failure_reason_rejected():
    """R5：LLM 候选的 failure_reason 含高敏原文（token）→ 候选拒绝进审计。

    场景：success Tool 存在（B1 门控放行 LLM），但 LLM 输出的
    failure_experience 候选在结构化字段携带敏感原文 → 敏感复核必须
    覆盖结构化字段（D8 增强）。
    """
    def llm(kind, text):
        return [{"fact": "安装失败", "category": "failure_experience",
                 "confidence": 0.6,
                 "failure_reason": "auth failed token a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"}]
    p = ExtractionProvider(llm_extractor=llm)
    ev = _turn(assistant_text="安装失败",
               tool_results=[ToolResult(tool_name="x", arguments={},
                                        status="success", result="配置已更新")],
               source_event_id="evt_d8r5")
    cands = p.extract_knowledge(ev)
    assert all("a1b2c3d4" not in (c.failure_reason or "") for c in cands)
    assert all("a1b2c3d4" not in (c.fact or "") for c in cands)
    assert any("sensitive-content-rejected" in a["error"] for a in p.audit)


# ── B1：模型推测门控（架构 TABLE 22：Tool 事实高于模型自述） ──

def test_d8_no_tool_evidence_llm_success_rejected():
    """模型自述成功（无 Tool 证据）→ 不形成成功知识（B1 + TABLE 22）。"""
    def llm(kind, text):
        return [{"fact": "软件安装成功", "category": "fact", "confidence": 0.9}]
    p = ExtractionProvider(llm_extractor=llm)
    ev = _turn(user_text="", assistant_text="软件已经成功安装",
               source_event_id="evt_d8b1")
    cands = p.extract_knowledge(ev)
    assert cands == []
    assert any("no-success-tool-evidence" in a["error"] for a in p.audit)


# ── 4. 评测输出（E 轨 §3.3 口径） ──

def test_d8_to_knowledge_evaluation_record_fields():
    """to_knowledge_evaluation_record 覆盖 E 轨 §3.3 字段级口径。"""
    from providers.knowledge_rules import build_failure_experience
    raw = build_failure_experience(
        tool_name="install", error="dep not found",
        source_event_id="evt_d8ev")
    cand = KnowledgeCandidate(**raw)
    rec = to_knowledge_evaluation_record(cand)
    for field in ("fact", "category", "conditions", "evidence",
                  "source_event_id", "confidence", "memory_status",
                  "failure_reason", "avoid_condition", "alternative",
                  "steps", "expected_result", "problem", "outcome",
                  "reproducible", "template_body", "parameters", "priority"):
        assert field in rec, field
    assert rec["category"] == "failure_experience"
    assert rec["memory_status"] == "candidate"
    assert rec["confidence"] == 0.6


def test_d8_knowledge_extraction_output_meta():
    """extract_knowledge_with_meta → KnowledgeExtractionOutput（缓存/模式/耗时）。"""
    p = ExtractionProvider()
    ev = _turn(tool_results=[ToolResult(
        tool_name="x", arguments={}, status="success",
        result="/opt/data 目录存在且可读")], source_event_id="evt_d8meta")
    out1 = p.extract_knowledge_with_meta(ev)
    assert isinstance(out1, KnowledgeExtractionOutput)
    assert out1.cache_hit is False
    assert out1.provider_mode == "rules"
    assert out1.duration_ms >= 0.0
    out2 = p.extract_knowledge_with_meta(ev)  # 缓存命中
    assert out2.cache_hit is True
    assert len(out2.candidates) == len(out1.candidates)


def test_d8_export_knowledge_records_jsonl(tmp_path):
    """export_knowledge_records 写出 JSONL（每行 KnowledgeExtractionOutput）。"""
    p = ExtractionProvider()
    events = [
        _turn(tool_results=[ToolResult(
            tool_name="a", arguments={}, status="success",
            result="/opt/a 目录存在且可读")], source_event_id="evt_d8exp1"),
        _turn(tool_results=[ToolResult(
            tool_name="b", arguments={}, status="failure",
            error="timeout")], source_event_id="evt_d8exp2"),
    ]
    path = str(tmp_path / "knowledge_records.jsonl")
    written = export_knowledge_records(events, p, path)
    assert written == 2
    with open(path, encoding="utf-8") as f:
        lines = [json.loads(l) for l in f if l.strip()]
    assert len(lines) == 2
    cats = {c["category"] for line in lines for c in line["candidates"]}
    assert "fact" in cats
    assert "failure_experience" in cats


# ── 5. 契约保持 ──

def test_d8_contract_single_arg_and_cache():
    """extract_knowledge(event) 单参数契约保持；缓存键含内容指纹。"""
    p = ExtractionProvider()
    ev = _turn(tool_results=[ToolResult(
        tool_name="x", arguments={}, status="success",
        result="/opt/data 目录存在且可读")], source_event_id="evt_d8c")
    assert isinstance(p.extract_knowledge(ev), list)
    assert p.cache_stats["size"] >= 1  # 已写缓存


def test_d8_close_after_rules_still_work():
    """close() 后规则路径仍独立工作（knowledge 同偏好）。"""
    p = ExtractionProvider()
    p.close()
    ev = _turn(tool_results=[ToolResult(
        tool_name="x", arguments={}, status="failure",
        error="dep not found")], source_event_id="evt_d8close")
    cands = p.extract_knowledge(ev)
    assert len(cands) == 1
    assert cands[0].category == "failure_experience"


# ── 6. Review 修复回归（2026-08-16） ──

def test_d8_llm_cannot_forge_evidence():
    """R3 强化（Review 修复）：knowledge LLM 提供的 evidence 被剥离（系统可信来源）。

    架构 TABLE 22：Tool 事实高于模型自述——LLM 自述不得充当知识证据。
    """
    def llm(kind, text):
        return [{"fact": "工具执行成功", "category": "fact", "confidence": 0.9,
                 "evidence": "LLM 自述成功不可信"}]
    p = ExtractionProvider(llm_extractor=llm)
    ev = _turn(assistant_text="工具执行成功",
               tool_results=[ToolResult(tool_name="x", arguments={},
                                        status="success", result="工具执行完成")],
               source_event_id="evt_d8forge")
    cands = p.extract_knowledge(ev)
    llm_cands = [c for c in cands
                 if "LLM 自述成功不可信" not in (c.evidence or "")]
    assert all(c.evidence is None or "工具执行完成" in c.evidence
               for c in llm_cands)


def test_d8_cache_key_includes_tool_arguments():
    """Review 修复：缓存键含 tool arguments——同 tool 同名/同 error 但参数不同
    的失败事件不得串缓存键（failure_experience 的 conditions 内嵌参数摘要）。"""
    p = ExtractionProvider()
    ev_a = _turn(tool_results=[ToolResult(
        tool_name="install", arguments={"pkg": "vim"}, status="failure",
        error="dep not found")], source_event_id="evt_d8cache_a")
    ev_b = _turn(tool_results=[ToolResult(
        tool_name="install", arguments={"pkg": "nginx"}, status="failure",
        error="dep not found")], source_event_id="evt_d8cache_b")
    ca = p.extract_knowledge(ev_a)
    cb = p.extract_knowledge(ev_b)
    assert len(ca) == 1 and len(cb) == 1
    assert "pkg=vim" in ca[0].conditions
    assert "pkg=nginx" in cb[0].conditions
    assert ca[0].conditions != cb[0].conditions  # 未串键
