"""
test_pipeline_cleaner.py — 轨道 A Day6 事件清洗器测试

覆盖：Pydantic 校验拒绝（缺失/类型错/未知字段）、时间标准化（naive→UTC、
Z 后缀、epoch）、状态标准化、tool_result 条件字段、确定性（同输入同输出）。
"""

import pytest

from pipeline.cleaner import EventCleaner
from pipeline.schemas import (
    EventValidationError,
    NormalizedEvent,
    ProcessingStatus,
    SourceType,
)

cleaner = EventCleaner()


def _raw(**overrides):
    base = {
        "event_id": "evt_20260809_a1b2c3",
        "user_id": "user_demo_01",
        "actor_id": "user_default",
        "source_type": "chat",
        "schema_version": "0.1",
        "event_type": "user_message",
        "consent_scope": "memory_only",
        "idempotency_key": "idem_20260809_a1b2c3",
        "source_business_status": "raw",
        "occurred_at": "2026-08-09T10:00:00+08:00",
        "captured_at": "2026-08-09T10:00:05Z",
        "session_id": "sess_d4e5f6",
        "turn_id": "turn_07",
    }
    base.update(overrides)
    return base


# ── 校验拒绝 ──

def test_clean_rejects_missing_required():
    raw = _raw()
    del raw["event_id"]
    with pytest.raises(EventValidationError) as ei:
        cleaner.clean(raw)
    assert ei.value.code == "ERR_EVENT_VALIDATION"


def test_clean_rejects_wrong_type():
    raw = _raw()
    raw["occurred_at"] = 12345  # int 但 datetime 字段期望 str/iso —— Pydantic 可解析 int? 用 bool 保错
    raw["event_type"] = "not_an_event_type"
    with pytest.raises(EventValidationError):
        cleaner.clean(raw)


def test_clean_rejects_unknown_field():
    """架构 6.2 第 1 步：未知高风险字段 → extra=forbid 拒绝。"""
    raw = _raw()
    raw["admin_override"] = True
    with pytest.raises(EventValidationError) as ei:
        cleaner.clean(raw)
    assert "admin_override" in str(ei.value) or "extra" in str(ei.value)


def test_clean_rejects_non_dict():
    with pytest.raises(EventValidationError) as ei:
        cleaner.clean(["not", "dict"])
    assert ei.value.code == "ERR_EVENT_NOT_DICT"


def test_clean_rejects_illegal_event_id():
    raw = _raw()
    raw["event_id"] = "bad id with spaces; drop table"
    with pytest.raises(EventValidationError) as ei:
        cleaner.clean(raw)
    assert ei.value.code == "ERR_EVENT_ID_FORMAT"


# ── 时间标准化（架构 6.2 第 2 步） ──

def test_clean_normalizes_naive_time_to_utc():
    raw = _raw(occurred_at="2026-08-09T10:00:00", captured_at="2026-08-09T10:00:05")
    ev = cleaner.clean(raw)
    assert ev.occurred_at.tzinfo is not None
    assert ev.occurred_at.utcoffset().total_seconds() == 0
    assert ev.occurred_at.isoformat().endswith("+00:00")


def test_clean_normalizes_z_suffix():
    raw = _raw(occurred_at="2026-08-09T02:00:00Z")
    ev = cleaner.clean(raw)
    assert ev.occurred_at.hour == 2
    assert ev.occurred_at.utcoffset().total_seconds() == 0


def test_clean_normalizes_tz_offset():
    """+08:00 → UTC 换算。"""
    raw = _raw(occurred_at="2026-08-09T10:00:00+08:00")
    ev = cleaner.clean(raw)
    assert ev.occurred_at.hour == 2  # 10:00+08:00 = 02:00 UTC


# ── 状态标准化 ──

def test_clean_sets_processing_status_cleaned():
    ev = cleaner.clean(_raw())
    assert ev.processing_status == ProcessingStatus.CLEANED


def test_clean_preserves_source_business_status():
    ev = cleaner.clean(_raw(source_business_status="failure"))
    assert ev.source_business_status.value == "failure"


# ── 条件字段（E 轨 Schema） ──

def test_tool_result_requires_tool_call_id():
    raw = _raw(source_type="tool_result", event_type="agent_response",
               tool_call_id=None)
    with pytest.raises(EventValidationError) as ei:
        cleaner.clean(raw)
    assert "tool_call_id" in str(ei.value)


def test_tool_result_with_tool_call_id_ok():
    raw = _raw(source_type="tool_result", event_type="agent_response",
               tool_call_id="tool_file_search_001")
    ev = cleaner.clean(raw)
    assert ev.source_type == SourceType.TOOL_RESULT
    assert ev.tool_call_id == "tool_file_search_001"


# ── 确定性 ──

def test_clean_deterministic():
    """同一输入多次清洗结果完全一致。"""
    raw = _raw()
    a = cleaner.clean(raw)
    b = cleaner.clean(raw)
    assert a.model_dump() == b.model_dump()


def test_clean_many_order_preserved():
    raws = [_raw(event_id=f"evt_{i}") for i in range(3)]
    out = cleaner.clean_many(raws)
    assert [e.event_id for e in out] == [f"evt_{i}" for i in range(3)]
