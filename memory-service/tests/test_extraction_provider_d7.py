"""
test_extraction_provider_d7.py — 轨道 A Day7 ExtractionProvider 深化测试

覆盖（docs/day7/01_task_card.md）：
1. 规则深化：偏好六类 / 临时-长期（TABLE 20）/ scope（E 轨 §2.9）/ 类别键 / explicitness
2. 缓存：LRU 命中/深拷贝/空结果缓存/不同事件不串键/统计
3. 超时：LLM 超时 → 空候选 + audit(timeout)（Day3 契约降级，不阻塞）
4. 非法字段降级：可选字段坏值 → 默认值 + audit；必需字段缺失 → R4 候选级拒绝
5. 规则 + LLM 协同：合并去重（同 key 规则优先）
6. 评测输出：PreferenceExtractionOutput / to_evaluation_record / export_preference_records
7. 契约保持：extract_preferences(event) 单参数；close() 后规则路径仍可用
"""

import json
import time

from providers.extraction_provider import (
    ExtractionProvider,
    PreferenceCandidate,
    PreferenceExtractionCache,
    PreferenceExtractionOutput,
    export_preference_records,
    to_evaluation_record,
)


def _turn(user_text="", assistant_text="", tool_results=None, source="chat",
          source_event_id=None):
    from providers.extraction_provider import TurnFinalizedEvent
    return TurnFinalizedEvent(
        session_id="sess_d7",
        user_text=user_text,
        assistant_text=assistant_text,
        tool_results=tool_results,
        source=source,
        source_event_id=source_event_id,
    )


# ── 1. 规则深化（架构 TABLE 19/20 + E 轨 §2.9/§3.2） ──

def test_d7_rule_temporary_example():
    """TABLE 20 临时要求：scope 限定当前会话，不产生正式长期偏好。"""
    p = ExtractionProvider()
    cands = p.extract_preferences(
        _turn(user_text="这次我希望回答控制在三句话内", source_event_id="evt_d7a"))
    assert len(cands) == 1
    c = cands[0]
    assert c.is_temporary is True
    assert c.should_persist is False
    assert c.scope == "session"
    assert c.explicitness == "explicit"
    assert c.category == "presentation"
    assert c.key == "response.length"
    assert c.confidence == 0.6  # 临时指令置信度基线


def test_d7_rule_long_term_example():
    """TABLE 20 长期偏好原句：meeting 场景 topic 长期版本。"""
    p = ExtractionProvider()
    cands = p.extract_preferences(
        _turn(user_text="以后所有会议总结都控制在三段内", source_event_id="evt_d7b"))
    assert len(cands) == 1
    c = cands[0]
    assert c.is_temporary is False
    assert c.should_persist is True
    assert c.scope == "topic"
    assert c.category == "scene_specific"
    assert c.key == "scene.meeting.preference"
    assert c.confidence == 0.75  # 长期显式置信度基线
    assert c.source_event_id == "evt_d7b"  # R3


def test_d7_rule_global_language():
    p = ExtractionProvider()
    cands = p.extract_preferences(
        _turn(user_text="以后都用中文回答", source_event_id="evt_d7c"))
    assert len(cands) == 1
    c = cands[0]
    assert c.scope == "global"
    assert c.key == "response.language"
    assert c.is_temporary is False
    assert c.should_persist is True


def test_d7_rule_tool_selection():
    p = ExtractionProvider()
    cands = p.extract_preferences(
        _turn(user_text="我偏好优先使用 git 命令行工具", source_event_id="evt_d7d"))
    assert len(cands) >= 1
    c = cands[0]
    assert c.category == "tool_selection"
    assert c.scope == "tool"
    assert c.key == "tool_selection.preference"


def test_d7_rule_contract_signature_kept():
    """Day3 契约保持：extract_preferences(event) 单参数。"""
    p = ExtractionProvider()
    cands = p.extract_preferences(_turn(user_text="我喜欢简洁的回答"))
    assert isinstance(cands, list)
    assert all(isinstance(c, PreferenceCandidate) for c in cands)


# ── 2. 缓存（D7） ──

def test_cache_hit_returns_same_candidates():
    p = ExtractionProvider()
    ev = _turn(user_text="以后都用中文回答", source_event_id="evt_cache1")
    out1 = p.extract_preferences_with_meta(ev)
    assert out1.cache_hit is False
    assert out1.provider_mode == "rules"
    out2 = p.extract_preferences_with_meta(ev)
    assert out2.cache_hit is True
    assert [c.model_dump() for c in out1.candidates] == \
        [c.model_dump() for c in out2.candidates]


def test_cache_returns_deep_copy():
    """调用方修改返回候选不得污染缓存。"""
    p = ExtractionProvider()
    ev = _turn(user_text="以后都用中文回答", source_event_id="evt_cache2")
    out1 = p.extract_preferences_with_meta(ev)
    out1.candidates[0].value = "被外部修改"
    out2 = p.extract_preferences_with_meta(ev)
    assert out2.cache_hit is True
    assert "被外部修改" not in out2.candidates[0].value


def test_cache_empty_result_cached():
    """空结果也缓存（避免重复 LLM 调用）。"""
    p = ExtractionProvider()
    ev = _turn(user_text="今天天气不错", source_event_id="evt_cache3")
    out1 = p.extract_preferences_with_meta(ev)
    assert out1.candidates == []
    out2 = p.extract_preferences_with_meta(ev)
    assert out2.cache_hit is True
    assert out2.candidates == []


def test_cache_key_differs_by_event_content():
    """不同事件（不同内容指纹）不互相命中。"""
    p = ExtractionProvider()
    ev_a = _turn(user_text="以后都用中文回答", source_event_id="evt_cache4")
    ev_b = _turn(user_text="以后都用英文回答", source_event_id="evt_cache4")  # 同 ID 不同内容
    p.extract_preferences_with_meta(ev_a)
    out_b = p.extract_preferences_with_meta(ev_b)
    assert out_b.cache_hit is False  # 内容不同 → 缓存键不同


def test_cache_stats_and_capacity():
    cache = PreferenceExtractionCache(capacity=2)
    p = ExtractionProvider(cache=cache)
    for i, text in enumerate(["以后都用中文回答", "我喜欢简洁的回答", "请总是用英语"]):
        p.extract_preferences_with_meta(
            _turn(user_text=text, source_event_id=f"evt_cap{i}"))
    stats = cache.stats
    assert stats["size"] == 2  # LRU 淘汰最旧
    assert stats["misses"] >= 3
    assert stats["hits"] == 0


def test_cache_ttl_expiry():
    cache = PreferenceExtractionCache(ttl_seconds=0.05)
    p = ExtractionProvider(cache=cache)
    ev = _turn(user_text="以后都用中文回答", source_event_id="evt_ttl")
    p.extract_preferences_with_meta(ev)
    time.sleep(0.08)
    out2 = p.extract_preferences_with_meta(ev)
    assert out2.cache_hit is False  # TTL 过期 → 重新提取


# ── 3. 超时（Day3 契约降级） ──

def test_llm_timeout_returns_empty_and_audits():
    """LLM 超时 → 空候选 + audit(timeout)，不阻塞。"""
    def slow_llm(kind, text):
        time.sleep(1.0)
        return [{"key": "response.language", "value": "中文",
                 "confidence": 0.9, "evidence": "e"}]
    p = ExtractionProvider(llm_extractor=slow_llm, llm_timeout_ms=50)
    start = time.monotonic()
    out = p.extract_preferences_with_meta(
        _turn(user_text="", source_event_id="evt_to"))  # 规则路径空，隔离验证超时降级
    elapsed = time.monotonic() - start
    assert out.llm_timeout is True
    assert elapsed < 0.5  # 不等待 LLM 完成（50ms 超时）
    # 超时 → LLM 候选为空（真实降级，非固定样例）
    assert out.candidates == []
    assert any(a["error"] == "timeout" for a in p.audit)
    p.close()


def test_llm_timeout_knowledge_degrades():
    def slow_llm(kind, text):
        time.sleep(1.0)
        return [{"fact": "f", "category": "fact", "confidence": 0.9}]
    from providers.extraction_provider import ToolResult
    p = ExtractionProvider(llm_extractor=slow_llm, llm_timeout_ms=50)
    ev = _turn(assistant_text="工具执行成功",
               tool_results=[ToolResult(tool_name="x", arguments={},
                                        status="success", result="配置已更新")],
               source_event_id="evt_to_k")
    cands = p.extract_knowledge(ev)
    assert all(c.fact != "f" for c in cands)  # LLM 超时被降级
    p.close()


# ── 4. 非法字段降级（D7：可选字段坏值 → 默认值 + audit；R4 必需字段不变） ──

def _llm_returning(**overrides):
    def llm(kind, text):
        base = {"key": "response.language", "value": "中文",
                "confidence": 0.9, "evidence": "e"}
        base.update(overrides)
        return [base]
    return llm


def test_field_degrade_confidence_invalid():
    """confidence 非数值 → 默认 0.5 + audit(field-degraded:confidence)，候选保留。"""
    p = ExtractionProvider(llm_extractor=_llm_returning(confidence="high"))
    # user_text 触发规则候选（response.conciseness），LLM 用不同 key 隔离验证降级
    cands = p.extract_preferences(
        _turn(user_text="我喜欢简洁的回答", source_event_id="evt_fd1"))
    lang = [c for c in cands if c.key == "response.language"]
    assert len(lang) == 1
    assert lang[0].confidence == 0.5
    assert any("field-degraded:confidence" in a["error"] for a in p.audit)


def test_field_degrade_scope_out_of_enum():
    """scope=project（Day3 旧值，不在 E 轨五值）→ 降级 session + audit。"""
    p = ExtractionProvider(llm_extractor=_llm_returning(scope="project"))
    cands = p.extract_preferences(
        _turn(user_text="我喜欢简洁的回答", source_event_id="evt_fd2"))
    lang = [c for c in cands if c.key == "response.language"]
    assert len(lang) == 1
    assert lang[0].scope == "session"
    assert any("field-degraded:scope" in a["error"] for a in p.audit)


def test_field_degrade_category_and_explicitness():
    """category 非法 → presentation；explicitness=inferred（旧词汇）→ explicit。"""
    p = ExtractionProvider(llm_extractor=_llm_returning(
        category="unknown", explicitness="inferred"))
    cands = p.extract_preferences(
        _turn(user_text="我喜欢简洁的回答", source_event_id="evt_fd3"))
    lang = [c for c in cands if c.key == "response.language"]
    assert len(lang) == 1
    assert lang[0].category == "presentation"
    assert lang[0].explicitness == "explicit"
    assert any("field-degraded:category" in a["error"] for a in p.audit)
    assert any("field-degraded:explicitness" in a["error"] for a in p.audit)


def test_field_degrade_bool_invalid():
    """is_temporary 非 bool → 剥离（Pydantic 默认 False）+ audit。"""
    p = ExtractionProvider(llm_extractor=_llm_returning(is_temporary="yes"))
    cands = p.extract_preferences(
        _turn(user_text="我喜欢简洁的回答", source_event_id="evt_fd4"))
    lang = [c for c in cands if c.key == "response.language"]
    assert len(lang) == 1
    assert lang[0].is_temporary is False
    assert any("field-degraded:is_temporary" in a["error"] for a in p.audit)


def test_field_degrade_required_field_still_rejected():
    """R4 保持：必需字段（key）缺失 → 候选级拒绝，仅进 audit。"""
    def llm(kind, text):
        return [{"value": "中文", "confidence": 0.9, "evidence": "e"}]  # 缺 key
    p = ExtractionProvider(llm_extractor=llm)
    cands = p.extract_preferences(_turn(user_text="", source_event_id="evt_fd5"))  # 规则空，隔离 R4
    assert cands == []  # 非法候选不进入正常返回
    assert any("validation" in a["error"] for a in p.audit)


# ── 5. 规则 + LLM 协同（合并去重，规则优先） ──

def test_coop_keeps_distinct_keys():
    def llm(kind, text):
        return [{"key": "response.detail", "value": "更详细一些",
                 "confidence": 0.8, "evidence": "e"}]
    p = ExtractionProvider(llm_extractor=llm)
    cands = p.extract_preferences(
        _turn(user_text="我喜欢简洁的回答", source_event_id="evt_coop1"))
    keys = {c.key for c in cands}
    assert "response.conciseness" in keys  # 规则候选
    assert "response.detail" in keys  # LLM 候选（不同 key → 保留）
    assert p.extract_preferences_with_meta(
        _turn(user_text="我喜欢简洁的回答", source_event_id="evt_coop1")).provider_mode == "coop"


def test_coop_dedup_rule_wins():
    """LLM 与规则完全重复（key+value+scope）→ LLM 副本丢弃 + audit。"""
    def llm(kind, text):
        return [{"key": "response.conciseness", "value": "简洁的回答",
                 "confidence": 0.99, "evidence": "e"}]
    p = ExtractionProvider(llm_extractor=llm)
    cands = p.extract_preferences(
        _turn(user_text="我喜欢简洁的回答", source_event_id="evt_coop2"))
    assert len(cands) == 1  # 规则优先，LLM 副本被去重
    assert cands[0].confidence == 0.7  # 规则置信度保留（LLM 0.99 被丢弃）
    assert any(a["error"] == "dedup-rule-wins" for a in p.audit)


def test_coop_conflict_rule_wins():
    """LLM 同 key 不同 value → 规则优先，LLM 冲突候选丢弃 + audit。"""
    def llm(kind, text):
        return [{"key": "response.conciseness", "value": "要详细！",
                 "confidence": 0.9, "evidence": "e"}]
    p = ExtractionProvider(llm_extractor=llm)
    cands = p.extract_preferences(
        _turn(user_text="我喜欢简洁的回答", source_event_id="evt_coop3"))
    assert len(cands) == 1
    assert "简洁" in cands[0].value  # 规则 value 保留
    assert any(a["error"] == "conflict-rule-wins" for a in p.audit)


# ── 6. 评测输出（D7：偏好字段级评测统一结果格式） ──

def test_with_meta_output_shape():
    p = ExtractionProvider()
    out = p.extract_preferences_with_meta(
        _turn(user_text="以后都用中文回答", source_event_id="evt_eval1"))
    assert isinstance(out, PreferenceExtractionOutput)
    assert out.event_id == "evt_eval1"
    assert out.provider_mode == "rules"
    assert out.cache_hit is False
    assert out.duration_ms >= 0.0


def test_to_evaluation_record_fields():
    """字段级统一评测格式与 E 轨 §3.2 口径一致。"""
    p = ExtractionProvider()
    cands = p.extract_preferences(
        _turn(user_text="以后所有会议总结都控制在三段内", source_event_id="evt_eval2"))
    rec = to_evaluation_record(cands[0])
    for field in ("key", "value", "category", "scope", "confidence",
                  "explicitness", "is_temporary", "should_persist",
                  "evidence", "source_event_id", "memory_status"):
        assert field in rec
    assert rec["scope"] == "topic"
    assert rec["category"] == "scene_specific"
    assert rec["memory_status"] == "candidate"


def test_export_preference_records_jsonl(tmp_path):
    p = ExtractionProvider()
    events = [
        _turn(user_text="以后都用中文回答", source_event_id="evt_exp1"),
        _turn(user_text="今天天气不错", source_event_id="evt_exp2"),  # 空结果也导出
    ]
    path = tmp_path / "pref_records.jsonl"
    n = export_preference_records(events, p, str(path))
    assert n == 2
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        obj = json.loads(line)
        assert obj["provider_mode"] == "rules"
        assert "candidates" in obj
        assert "cache_hit" in obj


def test_export_records_are_evaluation_ready(tmp_path):
    """导出的候选行可直接用于 E 轨偏好评测（字段级比对）。"""
    p = ExtractionProvider()
    path = tmp_path / "eval.jsonl"
    export_preference_records(
        [_turn(user_text="以后所有会议总结都控制在三段内", source_event_id="evt_exp3")],
        p, str(path))
    obj = json.loads(path.read_text(encoding="utf-8").strip())
    assert len(obj["candidates"]) == 1
    cand = obj["candidates"][0]
    assert cand["scope"] == "topic"
    assert cand["is_temporary"] is False
    assert cand["should_persist"] is True
    assert cand["category"] == "scene_specific"
    assert cand["memory_status"] == "candidate"


# ── 7. close() 幂等 + 规则路径仍可用 ──

def test_close_idempotent_rules_still_work():
    p = ExtractionProvider(llm_extractor=lambda k, t: [])
    p.close()
    p.close()  # 幂等
    # 规则路径在 close 后仍独立工作
    cands = p.extract_preferences(_turn(user_text="我喜欢简洁的回答", source_event_id="evt_cl"))
    assert len(cands) >= 1
