"""
test_pipeline_schema_enums.py — R1：Schema/Enum 对齐 D3 业务契约测试

覆盖（Reviewer R1 要求）：
- source_business_status 八值合法：raw/completed/success/partial/failed/cancelled/timeout/ignored
- 非法枚举值拒绝（含旧的 "failure" 必须拒绝）
- sensitivity 五级合法：none/low/medium/high/critical
- memory_type 四值合法：short_term/medium_term/long_term/ephemeral
- processing_status 对齐 D3 契约五值（pending/extracting/extracted/embedded/stored）
- should_ignore 字段存在 + ignored 状态必须 should_ignore=true（D3 安全契约 §7.7）
"""

import pytest

from pipeline.cleaner import EventCleaner
from pipeline.schemas import (
    EventValidationError,
    MemorySourceEvent,
    ProcessingStatus,
    SourceBusinessStatus,
)

cleaner = EventCleaner()


def _raw(**overrides):
    base = {
        "event_id": "evt_enum_01",
        "user_id": "user_demo_01",
        "actor_id": "user_default",
        "source_type": "chat",
        "event_type": "user_message",
        "consent_scope": "memory_only",
        "idempotency_key": "idem_enum_01",
        "source_business_status": "raw",
        "occurred_at": "2026-08-09T10:00:00+08:00",
        "captured_at": "2026-08-09T10:00:05Z",
        "session_id": "sess_enum_01",
        "turn_id": "turn_01",
    }
    base.update(overrides)
    return base


# ── source_business_status 八值合法 ──

@pytest.mark.parametrize("status", [
    "raw", "completed", "success", "partial", "failed", "cancelled", "timeout", "ignored",
])
def test_source_business_status_eight_values_valid(status):
    """D3 契约八值均可合法清洗。"""
    raw = _raw(source_business_status=status)
    if status == "ignored":
        raw["should_ignore"] = True  # ignored 必须带 should_ignore=true
    ev = cleaner.clean(raw)
    assert ev.source_business_status.value == status


def test_legacy_failure_rejected():
    """旧值 "failure" 必须拒绝（契约值为 failed）。"""
    with pytest.raises(EventValidationError):
        cleaner.clean(_raw(source_business_status="failure"))


def test_invalid_status_rejected():
    with pytest.raises(EventValidationError):
        cleaner.clean(_raw(source_business_status="unknown_status"))


# ── sensitivity 五级合法 ──

@pytest.mark.parametrize("level", ["none", "low", "medium", "high", "critical"])
def test_sensitivity_five_levels_valid(level):
    ev = cleaner.clean(_raw(sensitivity=level))
    assert ev.sensitivity.value == level


def test_sensitivity_none_is_default():
    """默认 sensitivity=none（D3 契约）。"""
    ev = cleaner.clean(_raw())
    assert ev.sensitivity.value == "none"


def test_invalid_sensitivity_rejected():
    with pytest.raises(EventValidationError):
        cleaner.clean(_raw(sensitivity="ultra"))


# ── memory_type 四值合法 ──

@pytest.mark.parametrize("mt", ["short_term", "medium_term", "long_term", "ephemeral"])
def test_memory_type_four_values_valid(mt):
    ev = cleaner.clean(_raw(memory_type=mt))
    assert ev.memory_type.value == mt


def test_invalid_memory_type_rejected():
    with pytest.raises(EventValidationError):
        cleaner.clean(_raw(memory_type="permanent"))


# ── processing_status 对齐 D3 契约五值 ──

@pytest.mark.parametrize("ps", ["pending", "extracting", "extracted", "embedded", "stored"])
def test_processing_status_contract_values(ps):
    """processing_status 取值集合含 D3 契约五值（技术候选）。"""
    assert ProcessingStatus(ps).value == ps


def test_legacy_cleaned_rejected():
    """旧值 "cleaned" 不再存在于契约枚举。"""
    with pytest.raises(ValueError):
        ProcessingStatus("cleaned")


# ── should_ignore（D3 安全契约 §7.7） ──

def test_should_ignore_field_exists():
    """MemorySourceEvent 必须含 should_ignore 字段。"""
    assert "should_ignore" in MemorySourceEvent.model_fields


def test_ignored_status_requires_should_ignore():
    """source_business_status=ignored 但 should_ignore=false → 拒绝（契约 §7.7）。"""
    with pytest.raises(EventValidationError) as ei:
        cleaner.clean(_raw(source_business_status="ignored"))
    assert "should_ignore" in str(ei.value)


def test_ignored_status_with_should_ignore_ok():
    ev = cleaner.clean(_raw(source_business_status="ignored", should_ignore=True))
    assert ev.source_business_status == SourceBusinessStatus.IGNORED
    assert ev.should_ignore is True


def test_should_ignore_propagates_to_normalized():
    """should_ignore 从输入事件传递到清洗输出。"""
    ev = cleaner.clean(_raw(should_ignore=True))
    assert ev.should_ignore is True
