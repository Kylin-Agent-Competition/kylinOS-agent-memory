"""
test_pipeline_sensitive.py — 轨道 A Day6 敏感信息识别测试
"""

import pytest

from pipeline.schemas import SensitivityLevel
from pipeline.sensitive import detect_sensitivity, is_high_or_critical


def test_clean_text_none():
    level, matched = detect_sensitivity("用户查询了文件排序方式")
    assert level == SensitivityLevel.NONE
    assert matched is False


def test_detect_api_key_critical():
    level, matched = detect_sensitivity("使用 api_key=sk-abc123def456ghi789 配置服务")
    assert level == SensitivityLevel.CRITICAL
    assert matched is True


def test_detect_jwt_critical():
    level, matched = detect_sensitivity(
        "token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U")
    assert level == SensitivityLevel.CRITICAL
    assert matched is True


def test_detect_phone_medium():
    level, matched = detect_sensitivity("联系电话 13800138000 已登记")
    assert matched is True
    assert level in (SensitivityLevel.MEDIUM, SensitivityLevel.HIGH)


def test_plain_device_or_document_terms_are_not_identity_data():
    """Bare labels are not personal identifiers; actual values remain covered below."""
    level, matched = detect_sensitivity("学习环境固定安静，减少手机干扰；身份证件妥善保管。")
    assert level == SensitivityLevel.NONE
    assert matched is False


def test_detect_password_critical():
    level, matched = detect_sensitivity("password=sup3rSecret")
    assert level == SensitivityLevel.CRITICAL
    assert matched is True


def test_detect_id_card():
    level, matched = detect_sensitivity("身份证号 11010119900307789X")
    assert matched is True


def test_detect_sensitive_path():
    level, matched = detect_sensitivity("读取 /etc/shadow 内容")
    assert matched is True


def test_empty_text_none():
    level, matched = detect_sensitivity("")
    assert level == SensitivityLevel.NONE
    assert matched is False


def test_none_text_none():
    level, matched = detect_sensitivity(None)
    assert level == SensitivityLevel.NONE
    assert matched is False


def test_is_high_or_critical():
    assert is_high_or_critical(SensitivityLevel.HIGH) is True
    assert is_high_or_critical(SensitivityLevel.CRITICAL) is True
    assert is_high_or_critical(SensitivityLevel.LOW) is False
    assert is_high_or_critical(SensitivityLevel.MEDIUM) is False
