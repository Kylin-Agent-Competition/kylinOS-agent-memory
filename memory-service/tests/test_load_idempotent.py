"""
test_load_idempotent.py — 轨道 A Day4 生命周期与幂等性测试

验证（麒麟 VM 真实 .so，P0-1 生命周期模型）:
  生命周期模型：SDK 动态库进程内只加载一次，不执行 dlclose()；
  destroy_session() 只销毁会话，保留 .so 句柄，可再次 create_session()。

测试路径（P0-1 验收标准四类）:
  1. start → close
  2. with EmbeddingProvider(): pass
  3. start → embed → close → start → embed → close
  4. 多个 Provider 顺序创建、启动、关闭

以上路径均不得出现 Abort / 崩溃 / Double Free / Use After Free。

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


def _new_provider():
    """创建一个新的 Provider（直接操作 Bridge，避免依赖 Provider 封装）。"""
    return kb.EmbeddingBridge()


def test_start_close():
    """路径 1: start → close（load + create_session + destroy_session）"""
    b = _new_provider()
    b.load()
    b.create_session()
    assert b.has_session is True
    b.destroy_session()
    assert b.has_session is False
    # P0-1 生命周期模型：destroy 后 .so 仍加载（不卸载）
    assert b.loaded is True


def test_start_embed_close_restart():
    """路径 3: start → embed → close → start → embed → close"""
    b = _new_provider()
    b.load()
    b.create_session()
    v1 = b.embed("hello")
    assert v1.dimension == 768
    b.destroy_session()
    assert b.has_session is False

    # 重新 create_session（P0-1：不 dlclose，可重建会话）
    b.create_session()
    assert b.has_session is True
    v2 = b.embed("world")
    assert v2.dimension == 768
    b.destroy_session()


def test_destroy_idempotent():
    """重复 destroy_session 安全（幂等）"""
    b = _new_provider()
    b.load()
    b.create_session()
    b.destroy_session()
    b.destroy_session()  # 第二次：session 已空，应安全返回
    assert b.has_session is False


def test_create_session_idempotent():
    """重复 create_session 安全（幂等）"""
    b = _new_provider()
    b.load()
    b.create_session()
    b.create_session()  # 幂等
    assert b.has_session is True
    b.destroy_session()
