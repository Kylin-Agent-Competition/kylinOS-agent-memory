"""
test_embedding_service_real.py — 轨道 A Day5 真实 SDK 最小垂直链路测试

验证（麒麟 VM 真实 .so）：
1. EmbeddingService 接真实 EmbeddingProvider（进程级单例，Day4）
   → embed 返回真实 768 维向量
2. embed_batch 顺序调用真实 SDK
3. UDS 协议 encode/decode 与 Service 集成（本地协议已测，这里验证端到端）
4. Provider 不可用（so 不存在）→ 真实降级（空向量 + degraded）

依赖：kylin_embedding 已编译（/mnt/shared/cpp-bridge/build），KYLIN_L2=1。
pytest 风格；麒麟 L1/L2 缺模块必须失败，WSL 允许 skip。
"""

import os
import sys
from pathlib import Path

import pytest

# 允许直接以仓库根为 cwd 运行
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
# memory-service 在 PYTHONPATH 中（providers / embedding 包）
_MS = _REPO / "memory-service"
if str(_MS) not in sys.path:
    sys.path.insert(0, str(_MS))

IS_L2_HOST = os.environ.get("KYLIN_L2") == "1"

try:
    import kylin_embedding  # noqa: F401 - 确保真实模块可导入
except ImportError as exc:  # pragma: no cover
    kylin_embedding = None
    _IMPORT_ERROR = exc


def _require_module():
    if kylin_embedding is None:
        if IS_L2_HOST:
            pytest.fail(f"麒麟 L2 环境缺少 kylin_embedding: {_IMPORT_ERROR}")
        pytest.skip(f"kylin_embedding 未编译（WSL 可跳过）: {_IMPORT_ERROR}")


@pytest.fixture(autouse=True)
def _module_guard():
    _require_module()


@pytest.fixture()
def service():
    """真实 EmbeddingService（进程级单例 Provider）。"""
    from embedding.embedding_service import EmbeddingService
    svc = EmbeddingService()
    svc.start()
    yield svc
    svc.close()


def test_real_embed_returns_768_dim(service):
    """真实 SDK：embed 返回 768 维向量。"""
    resp = service.embed("hello world")
    assert resp["ok"] is True
    # 成功路径无 degraded 字段（仅失败/降级路径返回 degraded）
    assert "degraded" not in resp, f"成功路径不应降级: {resp}"
    assert resp["result"]["dimension"] == 768
    assert len(resp["result"]["vector"]) == 768
    assert abs(resp["result"]["l2_norm"] - 1.0) < 1e-3


def test_real_embed_chinese(service):
    """真实 SDK：中文文本向量化。"""
    resp = service.embed("你好世界")
    assert resp["ok"] is True
    assert resp["result"]["dimension"] == 768


def test_real_embed_empty_string(service):
    """真实 SDK：空串（Day2 已验证返回 768 维）。"""
    resp = service.embed("")
    assert resp["ok"] is True
    assert resp["result"]["dimension"] == 768


def test_real_embed_batch(service):
    """真实 SDK：batch 顺序调用。"""
    resp = service.embed_batch(["a", "bb", "ccc"])
    assert resp["ok"] is True
    assert len(resp["result"]) == 3
    for r in resp["result"]:
        assert r["dimension"] == 768


def test_real_service_handle_request_ping(service):
    """协议分发（架构 4.4 envelope）：memory.ping。"""
    resp = service.handle_request({"protocol_version": "1.0", "method": "memory.ping"})
    assert resp["status"] == "ok"
    assert resp["data"] == "pong"


def test_real_service_handle_request_embed(service):
    """协议分发（envelope）：memory.embed。"""
    from embedding.protocol import build_envelope
    env = build_envelope("memory.embed", {"text": "test"},
                         request_id="req-real", trace_id="trc-real")
    resp = service.handle_request(env)
    assert resp["status"] == "ok"
    assert resp["data"]["dimension"] == 768
    assert resp["request_id"] == "req-real"
    assert resp["trace_id"] == "trc-real"


def test_real_service_health(service):
    """memory.health：真实 Provider 下返回分项状态。"""
    resp = service.handle_request({"protocol_version": "1.0", "method": "memory.health"})
    assert resp["status"] == "ok"
    assert resp["data"]["service"] == "ok"
    assert resp["data"]["bridge_loaded"] is True


def test_degraded_when_so_missing():
    """Provider 不可用（so 不存在）→ 真实降级（空向量 + degraded）。

    注意：进程级单例会复用已加载的 Bridge（Day4 P0-1），无法在同一进程内
    切换 so_path。此测试验证降级逻辑本身（用独立 Service + 假 Provider），
    真实"so 不存在"路径已在 test_embedding_service.py 的 mock 版覆盖。
    """
    from embedding.embedding_service import EmbeddingService

    class FailProvider:
        def start(self):
            pass

        def close(self):
            pass

        def embed(self, text, *, timeout_ms=5000):
            from providers import ProviderError, ProviderErrorCode
            raise ProviderError(ProviderErrorCode.ERR_SDK_NOT_LOADED, "so not found")

    svc = EmbeddingService(provider=FailProvider())
    svc.start()
    resp = svc.embed("hello")
    assert resp["ok"] is True
    assert resp["degraded"] is True
    assert resp["result"]["vector"] == []
    assert resp["result"]["dimension"] == 0
    assert resp["degraded_reason"]["code"] == "ERR_SDK_NOT_LOADED"
    svc.close()


# ── TD-A-005-09：SDK 缺失降级（2026-08-16） ──

def test_td_005_09_sdk_missing_degrades(monkeypatch):
    """TD-A-005-09：EmbeddingProvider 构造失败（SDK 缺失）→ 降级 provider 兜底。

    验证：
    1. EmbeddingService() 不再构造即抛（可启动）
    2. embed → ok+degraded 空向量（ERR_SDK_NOT_LOADED）
    3. health → bridge_loaded=false
    """
    from embedding.embedding_service import EmbeddingService

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


def test_td_005_09_sdk_missing_no_crash_on_server(monkeypatch):
    """TD-A-005-09：UDS server 注入降级 provider 可启动（不崩溃）。"""
    from embedding.embedding_service import EmbeddingService

    class FakeSdkMissing:
        def start(self): pass
        def close(self): pass
        def get_dimension(self): return 0
        def embed(self, text, *, timeout_ms=5000):
            from providers import ProviderError, ProviderErrorCode
            raise ProviderError(ProviderErrorCode.ERR_SDK_NOT_LOADED, "so missing")

    s = EmbeddingService(provider=FakeSdkMissing())
    s.start()
    r = s.embed("测试")
    assert r["degraded"] is True
    s.close()
