"""
test_provider_failure_recovery.py — 轨道 A Day4 P1-3 失败恢复策略测试

覆盖（mock 假 Bridge，不依赖真实 .so，WSL 可跑）：
  1. .so 不存在（load 前失败）→ 重置 Singleton，新实例可恢复
  2. 初始化 embed 失败（load 后失败）→ 保留 Bridge，同实例重试
  3. 初始化 embed 失败 → 新实例（共享单例）状态一致
  4. fatal 失败（dlsym/init_session 失败已 dlclose/destroy）→ 不可恢复终态

pytest 风格：正式可被 pytest 收集，不依赖 kylin_embedding。
"""

import sys
from pathlib import Path

import pytest

# 加载真实 providers 模块（用 mock 的 kylin_embedding 替代）
_MS = Path(__file__).resolve().parents[1]  # memory-service/
sys.path.insert(0, str(_MS))


class _FakeBridge:
    """模拟 kylin_embedding.EmbeddingBridge 的可控假实现。"""

    def __init__(self, params):
        self.so_path = params.so_path
        self._loaded = False
        self._session = False
        self._destroyed = False
        self._fatal = False

    # 状态（pybind property 风格）
    @property
    def loaded(self):
        return self._loaded

    @property
    def has_session(self):
        return self._session

    @property
    def session_destroyed(self):
        return self._destroyed

    @property
    def fatal_failure(self):
        return self._fatal

    def load(self):
        if 'nonexist' in self.so_path:
            raise RuntimeError('dlopen failed')  # load 前失败
        if 'fatal' in self.so_path:
            self._fatal = True
            raise RuntimeError('fatal: dlsym failed after dlclose')
        self._loaded = True

    def create_session(self):
        if self._fatal:
            raise RuntimeError('fatal: restart required')
        if 'initfail' in self.so_path:
            self._destroyed = True
            raise RuntimeError('fatal: init_session failed after destroy')
        self._session = True

    def embed(self, text, timeout_ms=0):
        if 'embedfail' in self.so_path:
            raise RuntimeError('embed failed')
        if not self._session:
            raise RuntimeError('no session')
        return type('V', (), {'dimension': 768, 'data': [0.0] * 768, 'l2_norm': 1.0})()

    def destroy_session(self):
        self._session = False
        self._destroyed = True


# ── mock kylin_embedding 模块 ──
import types

_fake_mod = types.ModuleType('kylin_embedding')
_fake_mod.BridgeInitParams = type('BridgeInitParams', (), {
    '__init__': lambda self: setattr(self, 'so_path', ''),
})
_fake_mod.EmbeddingBridge = _FakeBridge
# P1-1: 模拟 pybind 的专用异常（BridgeSessionDestroyedError）
_fake_mod.BridgeSessionDestroyedError = type(
    'BridgeSessionDestroyedError', (RuntimeError,), {})
sys.modules['kylin_embedding'] = _fake_mod

# 重新加载 providers（用 mock 模块）
from providers import EmbeddingProvider, ProviderError  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_singleton():
    """每个测试前重置进程级单例（测试顺序独立，P1-3 要求）。"""
    EmbeddingProvider._shared_bridge = None
    EmbeddingProvider._shared_so_path = None
    EmbeddingProvider._shared_dimension = None
    EmbeddingProvider._ref_count = 0
    yield
    EmbeddingProvider._shared_bridge = None
    EmbeddingProvider._shared_so_path = None
    EmbeddingProvider._shared_dimension = None
    EmbeddingProvider._ref_count = 0


def test_so_not_found_recovers_with_new_instance():
    """.so 不存在（load 前失败）→ 重置单例，新实例用正确路径恢复。"""
    bad = EmbeddingProvider(so_path='/tmp/nonexist.so')
    with pytest.raises(ProviderError):
        bad.start()
    assert EmbeddingProvider._shared_bridge is None, 'load 前失败应重置单例'

    good = EmbeddingProvider(so_path=None)
    good.start()
    assert good.embed('x').dimension == 768
    good.close()


def test_init_embed_failure_retry_same_instance():
    """初始化 embed 失败（load 后）→ 保留单例，同实例重试不 AttributeError。"""
    p = EmbeddingProvider(so_path='/tmp/embedfail.so')
    with pytest.raises(ProviderError):
        p.start()
    assert EmbeddingProvider._shared_bridge is not None, 'load 后失败不重置单例'
    assert p._bridge is not None, '同实例 _bridge 非 None（可重试）'
    # 重试仍失败（embed 持续失败），但不 AttributeError
    with pytest.raises(ProviderError):
        p.start()


def test_init_embed_failure_new_instance_same_state():
    """初始化 embed 失败 → 新实例（共享单例）状态一致（不污染）。"""
    p1 = EmbeddingProvider(so_path='/tmp/embedfail.so')
    with pytest.raises(ProviderError):
        p1.start()
    # 新实例：so_path 仍锁定 embedfail，配置冲突路径正常
    p2 = EmbeddingProvider(so_path='/tmp/embedfail.so')
    assert p2._bridge is p1._bridge, '新实例共享同一 Bridge'
    with pytest.raises(ProviderError):
        p2.start()


def test_fatal_failure_no_retry():
    """fatal 失败（dlsym/init_session 已 dlclose/destroy）→ 进程级不可恢复。

    P1-High 方案 A 验收：fatal 后不得重置单例（重置会让新实例重新 dlopen，
    形成 dlclose→dlopen 危险序列）；同实例与新实例重试都必须稳定失败。
    """
    p = EmbeddingProvider(so_path='/tmp/fatal.so')
    with pytest.raises(ProviderError):
        p.start()
    # fatal 后单例保留（不得重置，避免新实例重新 dlopen）
    assert EmbeddingProvider._shared_bridge is not None, 'fatal 后不得重置单例'
    assert p._bridge.fatal_failure is True, 'Bridge 应处于 fatal 终态'
    # 同实例重试：fatal 后不再重试（稳定失败，不触发危险生命周期）
    with pytest.raises(ProviderError):
        p.start()
    # 新实例：共享同一 fatal Bridge，重试同样稳定失败（不创建新 Bridge 重新 dlopen）
    p2 = EmbeddingProvider(so_path='/tmp/fatal.so')
    assert p2._bridge is p._bridge, '新实例必须共享同一 fatal Bridge（不得新建）'
    with pytest.raises(ProviderError):
        p2.start()


def test_bridge_destroyed_maps_to_session_destroyed():
    """端到端（P1-1）：Bridge destroy 终态 → ProviderErrorCode.ERR_SESSION_DESTROYED。

    模拟：load → create → embed → destroy → 再次 embed 返回 ERR_SESSION_DESTROYED。
    验证 Provider 能区分销毁终态（而非 ERR_SESSION_FAILED）。
    """
    from providers import ProviderErrorCode

    class DestroyBridge(_FakeBridge):
        """模拟 pybind 的 BridgeSessionDestroyedError 行为。"""

        def __init__(self, params):
            super().__init__(params)
            self._destroyed = False

        @property
        def session_destroyed(self):
            return self._destroyed

        def embed(self, text, timeout_ms=0):
            if self._destroyed:
                # 模拟 pybind 的 BridgeSessionDestroyedError（类名匹配 Provider 映射表）
                raise _fake_mod.BridgeSessionDestroyedError('session destroyed')
            return super().embed(text, timeout_ms)

        def destroy_session(self):
            self._destroyed = True
            return super().destroy_session()

    # 替换 mock 模块的 Bridge 为 DestroyBridge，验证映射
    _fake_mod.EmbeddingBridge = DestroyBridge
    try:
        p = EmbeddingProvider(so_path='/tmp/normal.so')
        p.start()
        assert p.embed('x').dimension == 768
        # 直接销毁底层 session（模拟 Bridge destroy 终态）
        p._bridge.destroy_session()
        with pytest.raises(ProviderError) as ei:
            p.embed('x')
        assert ei.value.code == ProviderErrorCode.ERR_SESSION_DESTROYED, \
            f"销毁终态应映射 ERR_SESSION_DESTROYED, 实际 {ei.value.code}"
    finally:
        _fake_mod.EmbeddingBridge = _FakeBridge
