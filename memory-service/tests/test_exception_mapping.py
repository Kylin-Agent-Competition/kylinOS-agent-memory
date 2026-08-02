"""
test_exception_mapping.py

轨道 A — BridgeError → Python 异常映射测试（Day4）

验证 kylin_embedding 模块的异常层次结构与错误码映射规则。
pytest 风格（P0-4）：正式可被 pytest 收集。

环境区分（P0-4）：
- WSL 非宿主环境：kylin_embedding 缺失 → pytest.mark.skip（允许跳过）。
- 麒麟 L1/L2 环境：kylin_embedding 缺失 → 必须失败。
  由环境变量 KYLIN_L2=1 标记麒麟宿主环境；未设置时视为非宿主（WSL），允许跳过。
"""

import os

import pytest

# 环境标记：麒麟 L1/L2 宿主（KYLIN_L2=1）时，kylin_embedding 缺失必须失败
IS_L2_HOST = os.environ.get("KYLIN_L2") == "1"

try:
    import kylin_embedding as kb
except ImportError as exc:  # pragma: no cover
    kb = None
    _IMPORT_ERROR = exc


def _require_module():
    """麒麟 L2 环境缺失 kylin_embedding 必须失败；WSL 允许 skip。"""
    if kb is None:
        if IS_L2_HOST:
            pytest.fail(f"麒麟 L2 环境缺少 kylin_embedding 模块: {_IMPORT_ERROR}")
        pytest.skip(f"kylin_embedding 未编译（WSL 非宿主环境可跳过）: {_IMPORT_ERROR}")


@pytest.fixture(autouse=True)
def _module_guard():
    _require_module()


# ── 1. 异常类型层次 ──

@pytest.mark.parametrize("name", [
    "BridgeSoNotFoundError", "BridgeLoadError", "BridgeSymbolError",
    "BridgeSessionError", "BridgeEmbedError", "BridgeSdkError",
    "BridgeTimeoutError", "BridgeCancelledError", "BridgeModelError",
])
def test_exception_type_exists(name):
    exc_cls = getattr(kb, name, None)
    assert exc_cls is not None, f"异常类型 {name} 应存在"


@pytest.mark.parametrize("name", [
    "BridgeSoNotFoundError", "BridgeLoadError", "BridgeSymbolError",
    "BridgeSessionError", "BridgeEmbedError", "BridgeSdkError",
    "BridgeTimeoutError", "BridgeCancelledError", "BridgeModelError",
])
def test_exception_inherits_bridge_error(name):
    exc_cls = getattr(kb, name)
    assert issubclass(exc_cls, kb.BridgeError), f"{name} 应继承 BridgeError"


# ── 2. 未加载时 embed → BridgeLoadError ──

def test_embed_without_load_raises_load_error():
    with pytest.raises(kb.BridgeLoadError):
        bridge = kb.EmbeddingBridge()
        bridge.embed("hello")


# ── 3. so 不存在 → BridgeSoNotFoundError ──

def test_load_missing_so_raises_not_found():
    params = kb.BridgeInitParams()
    params.so_path = "/tmp/definitely_not_exist.so.1"
    bridge = kb.EmbeddingBridge(params)
    with pytest.raises(kb.BridgeSoNotFoundError):
        bridge.load()


# ── 4. BridgeInitParams 默认 so_path ──

def test_default_so_path_contains_core_lib():
    params = kb.BridgeInitParams()
    assert "libkysdk-coreai-embedding" in params.so_path
