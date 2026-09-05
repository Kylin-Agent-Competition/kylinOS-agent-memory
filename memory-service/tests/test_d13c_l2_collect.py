"""Unit coverage for the D13C VM evidence collector's pure safety helpers."""

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "d13c_l2_collect.py"
SPEC = importlib.util.spec_from_file_location("d13c_l2_collect", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


def test_redact_hides_confirmation_credentials_recursively():
    value = {"confirmation_token": "secret", "nested": [{"token": "also-secret"}], "safe": "ok"}
    assert collector.redact(value) == {"confirmation_token": "<REDACTED>", "nested": [{"token": "<REDACTED>"}], "safe": "ok"}


def test_percentile_uses_nearest_rank_and_validates_input():
    assert collector.percentile([10, 20, 30, 40], 50) == 20
    assert collector.percentile([10, 20, 30, 40], 95) == 40
    try:
        collector.percentile([], 50)
    except ValueError as exc:
        assert "must not be empty" in str(exc)
    else:
        raise AssertionError("empty sample set must fail")
