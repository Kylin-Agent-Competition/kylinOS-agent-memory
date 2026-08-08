"""
test_provider_failure_recovery.py — 轨道 A Day4 P1-3 失败恢复策略测试

覆盖（mock 假 Bridge，不依赖真实 .so，WSL 可跑）：
  1. .so 不存在（load 前失败）→ 重置 Singleton，新实例可恢复
  2. 初始化 embed 失败（load 后失败）→ 保留 Bridge，同实例重试
  3. 初始化 embed 失败 → 新实例（共享单例）状态一致
  4. dlsym 失败（P1-1 错误分类）→ 首次 ERR_SDK_NOT_LOADED + fatal 终态，
     重试/新实例稳定 ERR_FATAL_FAILURE（不重新 dlopen）
  5. init_session 失败（P1-1 错误分类）→ 首次 ERR_SESSION_FAILED + fatal 终态，
     重试稳定 ERR_FATAL_FAILURE（不触发 destroy→create）
  6. Bridge destroy 终态 → ERR_SESSION_DESTROYED 端到端映射

P1-2（本轮）：不再在模块 import 阶段修改 sys.modules["kylin_embedding"]。
假模块通过 pytest fixture 注入，teardown 恢复真实模块与 providers 模块缓存，
消除测试顺序依赖与假绿风险（全量 pytest memory-service/tests/ 时
test_load_idempotent.py 等必须使用真实构建的 kylin_embedding）。
"""

import sys
import types
from pathlib import Path

import pytest

# 加载真实 providers 包路径（不导入、不修改 sys.modules——P1-2）
_MS = Path(__file__).resolve().parents[1]  # memory-service/
sys.path.insert(0, str(_MS))

# 模块级占位：由 fake_kylin fixture 在测试期间设置（P1-2 不做模块级注入）
_fake_mod = None


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
        if self._fatal:
            # 真实 Bridge：fatal 终态后任何 load 均稳定返回 ERR_FATAL_FAILURE
            raise _fake_mod.BridgeFatalError('fatal failure, restart required')
        if 'nonexist' in self.so_path:
            # load 前失败（.so 不存在）→ 可安全重置单例
            raise _fake_mod.BridgeSoNotFoundError('so not found')
        if 'dlsymfail' in self.so_path:
            # P1-1: dlsym 缺失 → BridgeSymbolError（保留原始原因）+ fatal 终态
            self._fatal = True
            raise _fake_mod.BridgeSymbolError(
                'required symbol missing (fatal: dlclose 已执行，不可重试)')
        self._loaded = True

    def create_session(self):
        if self._fatal:
            # fatal 终态后任何操作 → BridgeFatalError（restart required）
            raise _fake_mod.BridgeFatalError('fatal failure, restart required')
        if 'initfail' in self.so_path:
            # P1-1: init_session 失败 → BridgeSessionError（保留原始原因）+ fatal 终态
            self._fatal = True
            raise _fake_mod.BridgeSessionError(
                'init_session failed (fatal: destroy 已执行，不可重试)')
        self._session = True

    def embed(self, text, timeout_ms=0):
        if 'embedfail' in self.so_path:
            raise _fake_mod.BridgeEmbedError('embed failed')
        if not self._session:
            raise _fake_mod.BridgeSessionError('no session')
        return type('V', (), {'dimension': 768, 'data': [0.0] * 768, 'l2_norm': 1.0})()

    def destroy_session(self):
        self._session = False
        self._destroyed = True


def _make_fake_module():
    """构建假 kylin_embedding 模块（pybind 模块 API 的 mock 版本）。"""
    fake_mod = types.ModuleType('kylin_embedding')
    fake_mod.BridgeInitParams = type('BridgeInitParams', (), {
        '__init__': lambda self: setattr(self, 'so_path', ''),
    })
    fake_mod.EmbeddingBridge = _FakeBridge
    # 与 pybind 注册的异常层次一致的专用异常（类名匹配 Provider 映射表）
    fake_mod.BridgeSoNotFoundError = type('BridgeSoNotFoundError', (RuntimeError,), {})
    fake_mod.BridgeLoadError = type('BridgeLoadError', (RuntimeError,), {})
    fake_mod.BridgeSymbolError = type('BridgeSymbolError', (RuntimeError,), {})
    fake_mod.BridgeSessionError = type('BridgeSessionError', (RuntimeError,), {})
    fake_mod.BridgeSessionDestroyedError = type(
        'BridgeSessionDestroyedError', (RuntimeError,), {})
    fake_mod.BridgeFatalError = type('BridgeFatalError', (RuntimeError,), {})
    fake_mod.BridgeEmbedError = type('BridgeEmbedError', (RuntimeError,), {})
    fake_mod.BridgeSdkError = type('BridgeSdkError', (RuntimeError,), {})
    return fake_mod


@pytest.fixture
def fake_kylin(monkeypatch):
    """注入假 kylin_embedding 模块；teardown 无条件恢复模块状态。

    P1-2 / P1-1(R4)：消除模块 import 阶段的全局污染——
    - 仅在测试运行期注入（不在收集/模块导入期）；
    - teardown 无条件清除测试期间产生的全部 providers*，再恢复 fixture
      开始前保存的原模块（即使开始时 providers 尚未导入，也不会残留
      FakeBridge 绑定，后续测试不会静默复用）；
    - 恢复 sys.modules["kylin_embedding"]（monkeypatch 自动）；
    - 保证任意收集顺序下后续测试（如 test_load_idempotent.py）使用真实
      构建的 kylin_embedding，不会静默使用 FakeBridge。
    """
    global _fake_mod
    # 1. fixture 开始前保存原 kylin_embedding 与 providers*（P1-1 R4）
    saved = {
        'kylin_embedding': sys.modules.get('kylin_embedding'),
    }
    for name in list(sys.modules):
        if name == 'providers' or name.startswith('providers.'):
            saved[name] = sys.modules.pop(name)

    # 2. 注入 fake kylin_embedding 并重新导入 providers（绑定 FakeBridge）
    fake_mod = _make_fake_module()
    _fake_mod = fake_mod
    monkeypatch.setitem(sys.modules, 'kylin_embedding', fake_mod)

    import providers  # noqa: F401  # 用假模块重新导入
    from providers import EmbeddingProvider, ProviderError  # noqa: E402
    yield EmbeddingProvider, ProviderError, fake_mod

    # 3. teardown（P1-1 R4 完整隔离）：
    #    a) 无条件清除测试期间当前存在的全部 providers*（含测试期新产生的）
    for name in list(sys.modules):
        if name == 'providers' or name.startswith('providers.'):
            sys.modules.pop(name, None)
    #    b) 恢复 fixture 开始前保存的原 providers* / kylin_embedding
    for name, mod in saved.items():
        if mod is not None:
            sys.modules[name] = mod
        else:
            sys.modules.pop(name, None)
    #    c) kylin_embedding 由 monkeypatch 自动恢复为真实模块（或 None）
    _fake_mod = None


@pytest.fixture(autouse=True)
def _provider_env(fake_kylin):
    """每个测试前设置模块级引用并重置进程级单例（测试顺序独立，P1-3 要求）。"""
    global EmbeddingProvider, ProviderError, ProviderErrorCode  # noqa: PLW0603
    EmbeddingProvider, ProviderError, _ = fake_kylin
    from providers import ProviderErrorCode  # noqa: E402
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
    with pytest.raises(ProviderError) as ei:
        bad.start()
    assert ei.value.code == ProviderErrorCode.ERR_SDK_NOT_LOADED, \
        f".so 不存在应映射 ERR_SDK_NOT_LOADED, 实际 {ei.value.code}"
    assert EmbeddingProvider._shared_bridge is None, 'load 前失败应重置单例'

    good = EmbeddingProvider(so_path=None)
    good.start()
    assert good.embed('x').dimension == 768
    good.close()


def test_init_embed_failure_retry_same_instance():
    """初始化 embed 失败（load 后）→ 保留单例，同实例重试不 AttributeError。"""
    p = EmbeddingProvider(so_path='/tmp/embedfail.so')
    with pytest.raises(ProviderError) as ei:
        p.start()
    assert ei.value.code == ProviderErrorCode.ERR_EMBED_FAILED, \
        f"embed 失败应映射 ERR_EMBED_FAILED, 实际 {ei.value.code}"
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


def test_dlsym_failure_fatal_no_retry():
    """P1-1：dlsym 失败 → ERR_SDK_NOT_LOADED（保留原始原因）+ fatal 终态。

    首次失败保留 ERR_DLSYM_FAILED 语义（契约：dlsym → ERR_SDK_NOT_LOADED）；
    fatal 后同实例/新实例重试 → ERR_FATAL_FAILURE（restart required），
    且不得重置单例（重置会让新实例重新 dlopen，形成 dlclose→dlopen 危险序列）。
    """
    p = EmbeddingProvider(so_path='/tmp/dlsymfail.so')
    with pytest.raises(ProviderError) as ei:
        p.start()
    assert ei.value.code == ProviderErrorCode.ERR_SDK_NOT_LOADED, \
        f"dlsym 失败应映射 ERR_SDK_NOT_LOADED, 实际 {ei.value.code}"
    # fatal 后单例保留（不得重置，避免新实例重新 dlopen）
    assert EmbeddingProvider._shared_bridge is not None, 'fatal 后不得重置单例'
    assert p._bridge.fatal_failure is True, 'Bridge 应处于 fatal 终态'
    # 同实例重试：fatal 终态稳定错误 ERR_FATAL_FAILURE
    with pytest.raises(ProviderError) as ei2:
        p.start()
    assert ei2.value.code == ProviderErrorCode.ERR_FATAL_FAILURE, \
        f"fatal 后重试应映射 ERR_FATAL_FAILURE, 实际 {ei2.value.code}"
    # 新实例：共享同一 fatal Bridge，重试同样稳定失败（不创建新 Bridge 重新 dlopen）
    p2 = EmbeddingProvider(so_path='/tmp/dlsymfail.so')
    assert p2._bridge is p._bridge, '新实例必须共享同一 fatal Bridge（不得新建）'
    with pytest.raises(ProviderError) as ei3:
        p2.start()
    assert ei3.value.code == ProviderErrorCode.ERR_FATAL_FAILURE


def test_initfail_maps_to_session_failed_then_fatal():
    """P1-1：init_session 失败 → ERR_SESSION_FAILED（保留原始原因）+ fatal 终态。

    首次失败保留 ERR_SESSION_INIT 语义（契约：init_session → ERR_SESSION_FAILED）；
    fatal 后重试 → ERR_FATAL_FAILURE（restart required，不触发 destroy→create）。
    """
    p = EmbeddingProvider(so_path='/tmp/initfail.so')
    with pytest.raises(ProviderError) as ei:
        p.start()
    assert ei.value.code == ProviderErrorCode.ERR_SESSION_FAILED, \
        f"init_session 失败应映射 ERR_SESSION_FAILED, 实际 {ei.value.code}"
    assert EmbeddingProvider._shared_bridge is not None, 'fatal 后不得重置单例'
    assert p._bridge.fatal_failure is True, 'Bridge 应处于 fatal 终态'
    # 同实例重试：fatal 终态稳定错误 ERR_FATAL_FAILURE
    with pytest.raises(ProviderError) as ei2:
        p.start()
    assert ei2.value.code == ProviderErrorCode.ERR_FATAL_FAILURE, \
        f"fatal 后重试应映射 ERR_FATAL_FAILURE, 实际 {ei2.value.code}"


def test_bridge_destroyed_maps_to_session_destroyed():
    """端到端（P1-1）：Bridge destroy 终态 → ProviderErrorCode.ERR_SESSION_DESTROYED。

    模拟：load → create → embed → destroy → 再次 embed 返回 ERR_SESSION_DESTROYED。
    验证 Provider 能区分销毁终态（而非 ERR_SESSION_FAILED）。
    """
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

    # 替换假模块的 Bridge 为 DestroyBridge，验证映射
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
