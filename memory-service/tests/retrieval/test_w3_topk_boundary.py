"""W3：Top-K 边界行为（L1 纯函数/契约测试）。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from retrieval.contracts import ObjectType, RetrievalFilter
from retrieval.fusion import TruthRecord, fuse_retrieval
from retrieval.validation import validate_top_n

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


def test_validate_top_n_rejects_non_positive():
    # W3-1：top_n=0 / 负数拒绝。
    with pytest.raises(ValueError):
        validate_top_n(0)
    with pytest.raises(ValueError):
        validate_top_n(-1)


def test_validate_top_n_accepts_positive():
    assert validate_top_n(1) == 1
    assert validate_top_n(1000) == 1000


def test_validate_top_n_max_bound():
    # max_top_n 超限时拒绝。
    with pytest.raises(ValueError):
        validate_top_n(11, max_top_n=10)
    assert validate_top_n(10, max_top_n=10) == 10
