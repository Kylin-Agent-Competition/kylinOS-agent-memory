"""
test_embedding_provider_import.py

轨道 A — EmbeddingProvider 导入与契约测试（Day4）

验证:
  1. providers 包可导入（即使 kylin_embedding 未编译，也应给出明确报错）
  2. 契约字段存在（embed/embed_batch/get_dimension/model_info）
  3. 类型校验（非 str 输入抛 ProviderError.ERR_INVALID_TEXT）

pytest 风格（P0-4）：正式可被 pytest 收集。
本文件不依赖麒麟 SDK（纯契约/导入检查，WSL 可运行）。
"""

import dataclasses
import sys
from pathlib import Path

import pytest

# 把 memory-service 加入导入路径
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "memory-service"))


@pytest.fixture()
def provider_module():
    from providers import EmbeddingProvider, EmbeddingResult, ModelInfo, ProviderError
    return EmbeddingProvider, EmbeddingResult, ModelInfo, ProviderError


def test_providers_package_importable(provider_module):
    assert provider_module is not None


def test_provider_contract_methods_exist(provider_module):
    EmbeddingProvider, _, _, _ = provider_module
    for attr in ["embed", "embed_batch", "get_dimension", "model_info"]:
        assert hasattr(EmbeddingProvider, attr), f"EmbeddingProvider.{attr} 应存在"


def test_embedding_result_fields(provider_module):
    _, EmbeddingResult, _, _ = provider_module
    fields = {f.name for f in dataclasses.fields(EmbeddingResult)}
    for fld in ["vector", "dimension", "l2_norm", "error_code", "error_message"]:
        assert fld in fields, f"EmbeddingResult.{fld} 应存在"


def test_model_info_fields(provider_module):
    _, _, ModelInfo, _ = provider_module
    fields = {f.name for f in dataclasses.fields(ModelInfo)}
    for fld in ["name", "dimension", "ondevice", "loaded"]:
        assert fld in fields, f"ModelInfo.{fld} 应存在"


def test_provider_error_code_enum(provider_module):
    _, _, _, ProviderError = provider_module
    from providers import ProviderErrorCode
    # Day3 契约的 6 个 Provider 错误码必须存在
    for code in ["ERR_SDK_NOT_LOADED", "ERR_SESSION_FAILED", "ERR_EMBED_FAILED",
                 "ERR_SDK_ERROR", "ERR_TIMEOUT", "ERR_INVALID_TEXT"]:
        assert hasattr(ProviderErrorCode, code), f"ProviderErrorCode.{code} 应存在"
    # ProviderError 异常可实例化
    err = ProviderError(ProviderErrorCode.ERR_INVALID_TEXT, "test")
    assert err.code == ProviderErrorCode.ERR_INVALID_TEXT


def test_embed_non_str_raises_provider_error(provider_module):
    """非 str 输入应抛 ProviderError.ERR_INVALID_TEXT（P1-1，应用层校验）。"""
    EmbeddingProvider, _, _, ProviderError = provider_module
    from providers import ProviderErrorCode
    provider = EmbeddingProvider.__new__(EmbeddingProvider)  # 绕过 __init__（无需 SDK）
    try:
        provider.embed(123)
        pytest.fail("非 str 输入应抛 ProviderError")
    except ProviderError as exc:
        assert exc.code == ProviderErrorCode.ERR_INVALID_TEXT

