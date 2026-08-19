"""
test_td_a_005_03_05.py — 轨道 A 技术债修复回归测试

覆盖（docs/technical-debt/TECHNICAL_DEBT_REGISTER.md）：
- TD-A-005-03：get_dimension() 无副作用——start() 后不触发空串 embed
- TD-A-005-05：model_info().loaded 精确化——仅 READY 状态 loaded=True，
  未就绪/已关闭 loaded=False

用 FakeBridge 注入验证（无 SDK 环境可跑，不触发真实 IPC）。
"""

import sys

import pytest

sys.path.insert(0, ".")

from providers.embedding_provider import (  # noqa: E402
    EmbeddingProvider,
    ProviderError,
    ProviderErrorCode,
)


class FakeBridge:
    """最小 Fake Bridge：记录 embed 调用次数，模拟 SDK 行为。"""

    def __init__(self):
        self.loaded = False
        self.has_session = False
        self.embed_calls = 0

    def load(self):
        self.loaded = True

    def create_session(self):
        self.has_session = True

    def embed(self, text, timeout_ms):
        self.embed_calls += 1
        return type("EmbeddingVec", (), {
            "data": [0.1] * 768,
            "dimension": 768,
            "l2_norm": 1.0,
        })()

    def get_default_model_name(self):
        # [TD-A-005-04 Wontfix] FakeBridge 模拟返回模型名（SDK get_model_list 外部不可调用）
        return "fake-real-model-001"

    def destroy_session(self):
        self.has_session = False


@pytest.fixture()
def fake_bridge(monkeypatch):
    bridge = FakeBridge()
    # 注入 Fake Bridge（绕过 kylin_embedding import 与共享单例）
    monkeypatch.setattr(EmbeddingProvider, "_shared_bridge", bridge)
    monkeypatch.setattr(EmbeddingProvider, "_shared_so_path", None)
    monkeypatch.setattr(EmbeddingProvider, "_shared_dimension", None)
    return bridge


def test_td_005_03_get_dimension_no_embed_after_start(monkeypatch, fake_bridge):
    """TD-A-005-03：start() 后 get_dimension() 不再触发 embed（消除 IPC 副作用）。

    验证：start() 内部初始化 embed 1 次；随后 get_dimension() 0 次额外 embed；
    model_info() 的 get_dimension 也不触发。
    """
    # 让 start() 走真实生命周期（不 mock start）
    monkeypatch.setattr(EmbeddingProvider, "_ref_count", 0)
    p = EmbeddingProvider.__new__(EmbeddingProvider)
    p._bridge = fake_bridge
    p._dimension = None
    from providers.embedding_provider import _ProviderLifecycle
    p._lifecycle = _ProviderLifecycle.UNINITIALIZED

    p.start()
    assert fake_bridge.embed_calls == 1  # 仅 start 初始化 embed

    dim = p.get_dimension()
    assert dim == 768
    assert fake_bridge.embed_calls == 1  # get_dimension 无副作用

    info = p.model_info()
    assert info.dimension == 768
    assert fake_bridge.embed_calls == 1  # model_info 也不触发

    p.close()


def test_td_005_03_get_dimension_defensive_before_start(monkeypatch, fake_bridge):
    """TD-A-005-03：未 start() 前调用 get_dimension() 保留防御 fallback（兼容）。"""
    monkeypatch.setattr(EmbeddingProvider, "_shared_dimension", None)
    p = EmbeddingProvider.__new__(EmbeddingProvider)
    p._bridge = fake_bridge
    from providers.embedding_provider import _ProviderLifecycle
    p._lifecycle = _ProviderLifecycle.UNINITIALIZED
    # 防御路径：_shared_dimension None → 触发一次空串 embed
    monkeypatch.setattr(EmbeddingProvider, "_shared_dimension", None)
    # 需要 embed 通过（未 start 时 embed 会因生命周期检查拒绝，这里直接设 READY）
    monkeypatch.setattr(p, "_lifecycle", _ProviderLifecycle.READY)
    dim = p.get_dimension()
    assert dim == 768
    assert fake_bridge.embed_calls == 1  # 防御 fallback 触发一次


def test_td_005_05_loaded_false_when_not_ready(monkeypatch, fake_bridge):
    """TD-A-005-05：未就绪（INITIALIZING）时 model_info().loaded=False（精确化）。"""
    from providers.embedding_provider import _ProviderLifecycle
    monkeypatch.setattr(EmbeddingProvider, "_shared_dimension", 768)
    p = EmbeddingProvider.__new__(EmbeddingProvider)
    p._bridge = fake_bridge
    p._lifecycle = _ProviderLifecycle.INITIALIZING
    info = p.model_info()
    assert info.loaded is False  # 精确状态：未 READY 不 loaded


def test_td_005_05_loaded_false_when_closed(monkeypatch, fake_bridge):
    """TD-A-005-05：已关闭（CLOSED）时 model_info().loaded=False（精确化）。"""
    from providers.embedding_provider import _ProviderLifecycle
    monkeypatch.setattr(EmbeddingProvider, "_shared_dimension", 768)
    p = EmbeddingProvider.__new__(EmbeddingProvider)
    p._bridge = fake_bridge
    p._lifecycle = _ProviderLifecycle.CLOSED
    info = p.model_info()
    assert info.loaded is False


def test_td_005_05_loaded_true_when_ready(monkeypatch, fake_bridge):
    """TD-A-005-05：READY 时 model_info().loaded=True（精确状态）。"""
    from providers.embedding_provider import _ProviderLifecycle
    monkeypatch.setattr(EmbeddingProvider, "_shared_dimension", 768)
    p = EmbeddingProvider.__new__(EmbeddingProvider)
    p._bridge = fake_bridge
    p._lifecycle = _ProviderLifecycle.READY
    info = p.model_info()
    assert info.loaded is True


def test_td_005_04_real_model_name_from_bridge(monkeypatch, fake_bridge):
    """TD-A-005-04：READY 时 model_info().name = Bridge 缓存值（SDK 日志确认，非 Provider 硬编码）。"""
    from providers.embedding_provider import _ProviderLifecycle
    monkeypatch.setattr(EmbeddingProvider, "_shared_dimension", 768)
    p = EmbeddingProvider.__new__(EmbeddingProvider)
    p._bridge = fake_bridge
    p._lifecycle = _ProviderLifecycle.READY
    info = p.model_info()
    assert info.name == "fake-real-model-001"  # 真实模型名（不再硬编码）


def test_td_005_04_fallback_when_bridge_returns_empty(monkeypatch, fake_bridge):
    """TD-A-005-04：Bridge 查询失败/返回空 → 回退 Day2 默认模型名（不崩溃）。"""
    from providers.embedding_provider import _ProviderLifecycle

    class NoModelBridge(FakeBridge):
        def get_default_model_name(self):
            return ""  # 模拟符号缺失/查询失败

    monkeypatch.setattr(EmbeddingProvider, "_shared_dimension", 768)
    p = EmbeddingProvider.__new__(EmbeddingProvider)
    p._bridge = NoModelBridge()
    p._lifecycle = _ProviderLifecycle.READY
    info = p.model_info()
    assert info.name == "ensemble-embd_gte-base_uint8-text"  # 回退默认名
