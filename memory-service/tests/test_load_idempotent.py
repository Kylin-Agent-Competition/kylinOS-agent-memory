"""
test_load_idempotent.py — 轨道 A Day4 load() 成功幂等性测试

验证（麒麟 VM 真实 .so）:
  1. load() 成功
  2. 再次 load() 返回成功（幂等，不重复 dlopen）
  3. create_session() 后再次 create_session() 幂等

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


@pytest.fixture()
def bridge():
    b = kb.EmbeddingBridge()
    b.load()  # 先加载真实 .so（create_session 依赖 handle_）
    yield b
    try:
        b.destroy_session()
    except Exception:  # noqa: BLE001 - 清理失败不影响测试结果
        pass


def test_first_load_success(bridge):
    bridge.load()
    assert bridge.loaded is True


def test_second_load_idempotent(bridge):
    bridge.load()
    bridge.load()  # 不应抛异常
    assert bridge.loaded is True


def test_create_session_success(bridge):
    bridge.create_session()
    assert bridge.has_session is True


def test_second_create_session_idempotent(bridge):
    bridge.create_session()
    bridge.create_session()  # 不应抛异常
    assert bridge.has_session is True


def test_destroy_session_clears(bridge):
    bridge.create_session()
    bridge.destroy_session()
    assert bridge.has_session is False
