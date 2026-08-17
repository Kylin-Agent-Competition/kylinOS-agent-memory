"""
test_td_a_005_09.py — TD-A-005-09 SDK 缺失降级回归测试（本地可跑，无 KYLIN_L2 依赖）

覆盖：EmbeddingService 构造时 EmbeddingProvider() 失败（SDK 缺失）→
降级 provider 兜底：embed → ok+degraded 空向量；health → bridge_loaded=false。
"""

import sys

sys.path.insert(0, ".")

from embedding.embedding_service import EmbeddingService


def test_td_005_09_sdk_missing_degrades(monkeypatch):
    """EmbeddingProvider 构造失败（SDK 缺失）→ 降级 provider 兜底，不崩溃。"""

    def boom(*args, **kwargs):
        raise RuntimeError("kylin_embedding 模块不可用")

    monkeypatch.setattr("providers.embedding_provider.EmbeddingProvider", boom)
    s = EmbeddingService()
    s.start()
    r = s.embed("测试文本")
    assert r["ok"] is True
    assert r["degraded"] is True
    assert r["result"]["vector"] == []
    assert r["result"]["dimension"] == 0
    assert r["degraded_reason"]["code"] == "ERR_SDK_NOT_LOADED"
    h = s.health()["result"]
    assert h["bridge_loaded"] is False
    s.close()


def test_td_005_09_provider_injectable():
    """server 注入点（TD-A-005-09 ①）：可注入替代 Provider。"""
    class FakeProvider:
        def __init__(self):
            self.calls = 0

        def start(self):
            pass

        def close(self):
            pass

        def get_dimension(self):
            return 768

        def embed(self, text, *, timeout_ms=5000):
            self.calls += 1
            from providers import EmbeddingResult
            return EmbeddingResult(vector=[0.1] * 768, dimension=768, l2_norm=1.0)

    fp = FakeProvider()
    s = EmbeddingService(provider=fp)
    s.start()
    r = s.embed("注入测试")
    assert r["ok"] is True
    assert r.get("cache_hit") is not True  # 首次 miss（无 cache_hit 键或 False）
    assert fp.calls == 1
    s.close()


def test_td_005_09_sdk_missing_health():
    """SDK 缺失时 health 返回 bridge_loaded=false（服务端结构化降级响应）。"""
    def boom(*args, **kwargs):
        raise RuntimeError("sdk missing")

    import pytest
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("providers.embedding_provider.EmbeddingProvider", boom)
    s = EmbeddingService()
    s.start()
    h = s.health()["result"]
    assert h["service"] == "ok"  # 服务本身可启动
    assert h["bridge_loaded"] is False
    assert h["provider"] == "ready"  # 降级 provider 视为就绪（可响应）
    s.close()


def test_td_005_09_so_missing_at_start(monkeypatch):
    """TD-A-005-09 真实场景：kylin_embedding 模块在但 .so 缺失 → start() 不抛。

    EmbeddingProvider 构造成功（模块可导入），但 start() 时 .so 不存在
    （BridgeSoNotFoundError → ERR_SDK_NOT_LOADED）→ 服务切换降级 provider，
    embed → ok+degraded 空向量；health → bridge_loaded=false。
    """
    from providers import ProviderError, ProviderErrorCode

    class SoMissingProvider:
        def __init__(self):
            self._bridge = None

        def start(self):
            raise ProviderError(ProviderErrorCode.ERR_SDK_NOT_LOADED,
                                "so not found: libkysdk-coreai-embedding.so.1")

        def close(self):
            pass

        def get_dimension(self):
            return 0

        def embed(self, text, *, timeout_ms=5000):
            raise ProviderError(ProviderErrorCode.ERR_SDK_NOT_LOADED, "so missing")

    s = EmbeddingService(provider=SoMissingProvider())
    s.start()  # 之前会抛；现在应切换降级不抛
    assert s._sdk_missing is True
    r = s.embed("测试文本")
    assert r["ok"] is True and r["degraded"] is True
    assert r["result"]["vector"] == []
    h = s.health()["result"]
    assert h["bridge_loaded"] is False
    s.close()
