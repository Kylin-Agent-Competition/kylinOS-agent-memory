"""
test_pipeline_fingerprint.py — 轨道 A Day6 内容指纹/重复检测测试
"""

from pipeline.cleaner import EventCleaner
from pipeline.fingerprint import (
    content_fingerprint,
    event_duplicate_key,
    fill_event_fingerprint,
    fingerprint_event,
    is_duplicate,
)

cleaner = EventCleaner()


def _event(**overrides):
    raw = {
        "event_id": "evt_f1",
        "user_id": "user_demo_01",
        "actor_id": "user_default",
        "source_type": "chat",
        "event_type": "user_message",
        "consent_scope": "memory_only",
        "idempotency_key": "idem_f1",
        "occurred_at": "2026-08-09T10:00:00+08:00",
        "captured_at": "2026-08-09T10:00:05Z",
        "session_id": "sess_f1",
        "turn_id": "turn_07",
        "content_summary": "用户说：请把文件按修改时间排序",
    }
    raw.update(overrides)
    return cleaner.clean(raw)


# ── content_fingerprint ──

def test_fingerprint_normalizes_whitespace_and_case():
    a = content_fingerprint("  Hello   World  ")
    b = content_fingerprint("hello world")
    assert a == b  # 归一化后相同


def test_fingerprint_deterministic():
    assert content_fingerprint("同一正文") == content_fingerprint("同一正文")


def test_fingerprint_sha256_length():
    fp = content_fingerprint("x")
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)


# ── is_duplicate ──

def test_is_duplicate_detects_existing():
    fp = content_fingerprint("重复内容")
    seen = {fp}
    assert is_duplicate(fp, seen) is True


def test_is_duplicate_not_existing():
    fp = content_fingerprint("新内容")
    seen = {content_fingerprint("其他内容")}
    assert is_duplicate(fp, seen) is False


# ── event_duplicate_key（E 轨 Schema：idempotency_key 优先） ──

def test_duplicate_key_uses_idempotency():
    ev = _event()
    key = event_duplicate_key(ev)
    assert key == "user_demo_01:idem_f1"


def test_duplicate_key_distinct_users():
    """同 idempotency_key 不同 user → 不同键（用户隔离）。"""
    a = event_duplicate_key(_event(user_id="u1"))
    b = event_duplicate_key(_event(user_id="u2"))
    assert a != b


# ── fingerprint_event / fill_event_fingerprint ──

def test_fill_event_fingerprint_stable():
    ev = _event()
    fp1 = fill_event_fingerprint(ev)
    fp2 = fill_event_fingerprint(ev)
    assert fp1.content_fingerprint == fp2.content_fingerprint
    assert fp1.content_fingerprint == fingerprint_event(ev)
    # 不修改原对象（纯函数）
    assert ev.content_fingerprint is None


def test_fill_event_fingerprint_duplicate_detection():
    """同正文事件 → 同指纹 → 判重命中。"""
    ev1 = _event(content_summary="请把文件按修改时间排序")
    ev2 = _event(content_summary="请把文件按修改时间排序")
    fp1 = fill_event_fingerprint(ev1).content_fingerprint
    fp2 = fill_event_fingerprint(ev2).content_fingerprint
    assert fp1 == fp2
    assert is_duplicate(fp2, {fp1}) is True


def test_fingerprint_fallback_without_content():
    """无正文时用标识字段组合，同事件稳定。"""
    ev1 = _event(content_summary=None, raw_payload_ref=None)
    ev2 = _event(content_summary=None, raw_payload_ref=None)
    assert fingerprint_event(ev1) == fingerprint_event(ev2)
