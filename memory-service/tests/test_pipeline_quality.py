"""
test_pipeline_quality.py — 轨道 A Day6 质量评分测试

覆盖六维评分：completeness/validity/reliability/freshness/consistency/
extractability + overall + 提取门控（低质量不进入提取）。
"""

import math
from datetime import datetime, timedelta, timezone

from pipeline.cleaner import EventCleaner
from pipeline.quality import FRESHNESS_HALF_LIFE, QualityScorer

cleaner = EventCleaner()
NOW = datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc)


def _event(**overrides):
    raw = {
        "event_id": "evt_q1",
        "user_id": "user_demo_01",
        "actor_id": "user_default",
        "source_type": "chat",
        "event_type": "user_message",
        "consent_scope": "memory_only",
        "idempotency_key": "idem_q1",
        "occurred_at": "2026-08-09T10:00:00+08:00",
        "captured_at": "2026-08-09T10:00:05Z",
        "session_id": "sess_q1",
        "turn_id": "turn_07",
        "content_summary": "用户查询文件排序方式",
    }
    raw.update(overrides)
    return cleaner.clean(raw)


def test_score_full_event_high():
    scorer = QualityScorer(now=NOW)
    ev = _event(has_structured_payload=True)
    s = scorer.score(ev)
    assert s.completeness == 1.0
    assert s.validity >= 0.5
    assert s.reliability > 0.4  # chat 基线 0.45
    # occurred_at 10:00+08:00 = 02:00 UTC，NOW=12:00 UTC → 差 10h
    # freshness = exp(-ln2 * 36000/604800) = 2^(-36000/604800) ≈ 0.9596
    assert abs(s.freshness - 0.9596) < 1e-3
    assert s.consistency == 1.0
    assert s.extractability == 1.0
    assert s.overall > 0.6
    assert s.eligible_for_extraction is True


def test_score_low_quality_not_eligible():
    """低质量事件不进入提取（架构 6.2 第 6 步）。"""
    scorer = QualityScorer(now=NOW)
    # 空内容 + 低可信来源 + 无结构化载荷
    ev = _event(content_summary=None, raw_payload_ref=None,
                has_structured_payload=False, source_type="recollect",
                event_type="system_message")
    s = scorer.score(ev)
    assert s.completeness < 1.0
    assert s.extractability == 0.2
    assert s.reliability < 0.5  # recollect 基线 0.3
    assert s.eligible_for_extraction is False


def test_freshness_decay():
    """新鲜度指数衰减：越久远越低。"""
    scorer = QualityScorer(now=NOW)
    old = NOW - timedelta(seconds=FRESHNESS_HALF_LIFE)
    ev_new = _event(occurred_at=NOW.isoformat(), captured_at=NOW.isoformat())
    ev_old = _event(occurred_at=old.isoformat(), captured_at=(old + timedelta(seconds=5)).isoformat())
    f_new = scorer.score(ev_new).freshness
    f_old = scorer.score(ev_old).freshness
    assert f_new > f_old
    # 标准半衰期语义（M1）：一个半衰期后 freshness = 0.5
    assert abs(f_old - 0.5) < 1e-3


def test_tool_failure_reliability_penalty():
    """Tool 失败/取消降可信度（失败知识不沉淀为成功知识）。"""
    scorer = QualityScorer(now=NOW)
    ev_ok = _event(source_type="tool_result", event_type="agent_response",
                   tool_call_id="t1", source_business_status="success")
    ev_fail = _event(source_type="tool_result", event_type="agent_response",
                     tool_call_id="t2", source_business_status="failed")
    r_ok = scorer.score(ev_ok).reliability
    r_fail = scorer.score(ev_fail).reliability
    assert r_ok > r_fail
    assert abs(r_ok - 0.9) < 1e-3
    assert abs(r_fail - 0.45) < 1e-3


def test_invalid_type_combo_low_consistency():
    scorer = QualityScorer(now=NOW)
    ev = _event(source_type="chat", event_type="system_message")  # 非标准组合
    assert scorer.score(ev).consistency == 0.4


def test_occurred_after_captured_penalty():
    """occurred_at 晚于 captured_at → validity 扣分。"""
    scorer = QualityScorer(now=NOW)
    ev = _event(occurred_at="2026-08-09T10:00:10Z", captured_at="2026-08-09T10:00:05Z")
    assert scorer.score(ev).validity < 1.0


def test_score_deterministic_and_bounds():
    scorer = QualityScorer(now=NOW)
    ev = _event()
    a = scorer.score(ev)
    b = scorer.score(ev)
    assert a.model_dump() == b.model_dump()
    for v in (a.completeness, a.validity, a.reliability, a.freshness,
              a.consistency, a.extractability, a.overall):
        assert 0.0 <= v <= 1.0
