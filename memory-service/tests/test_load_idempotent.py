"""
test_load_idempotent.py — 轨道 A Day4 生命周期与幂等性测试

验证（麒麟 VM 真实 .so，P0-1 进程级单例生命周期模型）:

生命周期模型（P0-1，进程级 Singleton）：
  1. SDK 动态库在进程生命周期内只加载一次（不执行 dlclose）。
  2. session 进程内只创建一次，不销毁重建——
     麒麟实测 SDK 不允许同一进程 destroy_session → create_session
     （会阻塞挂起），因此 close() 只释放引用，session 保持存活到进程退出。
  3. 所有 EmbeddingProvider 共享同一个 Bridge 实例（进程级单例）。

测试路径（P0-1 验收标准四类）:
  1. start → close
  2. with EmbeddingProvider(): pass
  3. start → embed → close → start → embed → close（复用 session）
  4. 多个 Provider 顺序创建、启动、关闭

以上路径均不得出现 Abort / 崩溃 / 挂起 / Double Free / Use After Free。

pytest 风格（P0-4）：正式可被 pytest 收集。
环境区分：麒麟 L1/L2（KYLIN_L2=1）缺 kylin_embedding 必须失败；WSL 允许 skip。
"""

import os
import sys
from pathlib import Path

import pytest

# memory-service/tests/ 下：parents[1] = memory-service/，直接加入即可
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

IS_L2_HOST = os.environ.get("KYLIN_L2") == "1"

try:
    import kylin_embedding as kb
except ImportError as exc:  # pragma: no cover
    kb = None
    _IMPORT_ERROR = exc


def _require_module():
    if kb is None:
        if IS_L2_HOST:
            pytest.fail(f"麒麟 L2 环境缺少 kylin_embedding 模块: {_IMPORT_ERROR}")
        pytest.skip(f"kylin_embedding 未编译（WSL 非宿主环境可跳过）: {_IMPORT_ERROR}")


@pytest.fixture(autouse=True)
def _module_guard():
    _require_module()


# ── Provider 层生命周期（进程级单例，P0-1 验收） ──

def _new_provider():
    """创建 Provider 实例（内部共享进程级单例 Bridge）。"""
    from providers import EmbeddingProvider
    return EmbeddingProvider()


def test_start_close():
    """路径 1: start → close（session 保持存活，不销毁）"""
    p = _new_provider()
    p.start()
    assert p._bridge.has_session is True
    p.close()
    # P0-1 单例模型：close 后 session 仍存活（进程退出时统一释放）
    assert p._bridge.has_session is True


def test_context_manager_pass():
    """路径 2: with EmbeddingProvider(): pass"""
    with _new_provider():
        pass


def test_start_embed_close_restart():
    """路径 3: start → embed → close → start → embed → close（复用 session）"""
    p = _new_provider()
    p.start()
    r1 = p.embed("test")
    assert r1.dimension == 768
    p.close()
    # 再次 start：复用已有 session（不重建，避免 SDK 挂起）
    p.start()
    r2 = p.embed("test")
    assert r2.dimension == 768
    p.close()


def test_multiple_providers_sequential():
    """路径 4: 多个 Provider 顺序创建、启动、关闭（共享单例）"""
    for i in range(3):
        p = _new_provider()
        p.start()
        r = p.embed(f"text-{i}")
        assert r.dimension == 768
        p.close()
        del p


def test_close_without_start():
    """未 start 直接 close 应安全（引用计数不减小）"""
    p = _new_provider()
    p.close()
    p.close()


def test_context_manager_exception():
    """Context Manager 内发生异常：__exit__ 仍执行 close 且不掩盖原始异常"""
    with pytest.raises(ValueError):
        with _new_provider() as p:
            p.embed("ok")
            raise ValueError("业务异常")
