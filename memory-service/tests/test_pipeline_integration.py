"""
test_pipeline_integration.py — 轨道 A Day6 管线端到端测试

覆盖：EventPipeline 全链路（清洗→敏感→指纹→评分→门控）+ 确定性。
"""

from datetime import datetime, timezone

from pipeline.pipeline import EventPipeline
from pipeline.quality import QualityScorer

NOW = datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc)


def _raw(**overrides):
    base = {
        "event_id": "evt_p1",
        "user_id": "user_demo_01",
        "actor_id": "user_default",
        "source_type": "chat",
        "event_type": "user_message",
        "consent_scope": "memory_only",
        "idempotency_key": "idem_p1",
        "occurred_at": "2026-08-09T10:00:00+08:00",
        "captured_at": "2026-08-09T10:00:05Z",
        "session_id": "sess_p1",
        "turn_id": "turn_07",
        "content_summary": "用户说：请把文件按修改时间排序",
        "has_structured_payload": True,
    }
    base.update(overrides)
    return base


def test_pipeline_full_flow():
    pipe = EventPipeline(scorer=QualityScorer(now=NOW))
    result = pipe.process(_raw())
    # 清洗
    assert result.event.event_id == "evt_p1"
    assert result.event.occurred_at.utcoffset().total_seconds() == 0
    # 指纹已填充
    assert result.event.content_fingerprint is not None
    # 评分 + 门控
    assert result.quality.overall > 0.6
    assert result.eligible_for_extraction is True


def test_pipeline_sensitive_upgrade():
    """正文含敏感信息 → 等级提升 + 标记。"""
    pipe = EventPipeline(scorer=QualityScorer(now=NOW))
    result = pipe.process(_raw(content_summary="连接信息 api_key=sk-secret1234567890"))
    assert result.sensitivity_updated is True
    assert result.event.is_sensitive_matched is True
    assert result.event.sensitivity.value in ("high", "critical")


def test_pipeline_low_quality_not_eligible():
    """低质量事件不进入提取（架构 6.2 第 6 步）。"""
    pipe = EventPipeline(scorer=QualityScorer(now=NOW))
    result = pipe.process(_raw(
        source_type="recollect", event_type="system_message",
        content_summary=None, raw_payload_ref=None, has_structured_payload=False))
    assert result.eligible_for_extraction is False
    assert result.event.processing_status.value == "cleaned"  # 只保留最小审计


def test_pipeline_deterministic():
    pipe = EventPipeline(scorer=QualityScorer(now=NOW))
    a = pipe.process(_raw())
    b = pipe.process(_raw())
    assert a.event.model_dump() == b.event.model_dump()
    assert a.quality.model_dump() == b.quality.model_dump()


def test_pipeline_duplicate_detection_across_events():
    """同正文两事件 → 同指纹 → 判重命中（重复写入防护）。"""
    from pipeline.fingerprint import is_duplicate
    pipe = EventPipeline(scorer=QualityScorer(now=NOW))
    r1 = pipe.process(_raw(event_id="evt_a", idempotency_key="idem_a"))
    r2 = pipe.process(_raw(event_id="evt_b", idempotency_key="idem_b"))
    assert r1.event.content_fingerprint == r2.event.content_fingerprint
    assert is_duplicate(r2.event.content_fingerprint, {r1.event.content_fingerprint})
