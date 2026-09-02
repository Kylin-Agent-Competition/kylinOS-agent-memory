"""TD-030：TruthRecord 构造边界拒绝倒置有效期（L0 回归）。

覆盖：倒置窗口拒绝；相等边界（空半开区间）允许；单侧开放允许；
正常半开区间允许；naive datetime 拒绝（既有规则锁定）；UTC 归一化保留。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from retrieval.contracts import ObjectType
from retrieval.fusion import TruthRecord

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


def _truth(*, valid_from=None, valid_to=None):
    return TruthRecord(
        memory_id="m1",
        version_id="v1",
        user_id="alice",
        object_type=ObjectType.KNOWLEDGE,
        memory_type=None,
        memory_status="active",
        content="x",
        sensitivity="internal",
        conflict_state="resolved",
        valid_from=valid_from,
        valid_to=valid_to,
    )


def test_inverted_window_rejected():
    with pytest.raises(ValueError, match="valid_from 不能晚于 valid_to"):
        _truth(valid_from=NOW, valid_to=NOW - timedelta(days=1))


def test_equal_bounds_allowed():
    rec = _truth(valid_from=NOW, valid_to=NOW)
    assert rec.valid_from == NOW
    assert rec.valid_to == NOW


def test_single_sided_open_allowed():
    _truth(valid_from=NOW)
    _truth(valid_to=NOW + timedelta(days=1))


def test_no_bounds_allowed():
    _truth()


def test_normal_half_open_allowed():
    rec = _truth(valid_from=NOW, valid_to=NOW + timedelta(days=1))
    assert rec.valid_to > rec.valid_from


def test_naive_datetime_rejected():
    with pytest.raises(ValueError, match="必须带时区"):
        _truth(valid_from=datetime(2026, 8, 22, 12, 0, 0))


def test_utc_normalization_preserved():
    offset = timezone(timedelta(hours=8))
    local_naive = datetime(2026, 8, 22, 20, 0, 0, tzinfo=offset)  # == 12:00 UTC
    rec = _truth(valid_from=local_naive)
    assert rec.valid_from == NOW
    assert rec.valid_from.tzinfo is not None