"""
test_load_idempotent.py — 轨道 A Day4 load() 成功幂等性测试

验证（麒麟 VM 真实 .so）:
  1. load() 成功
  2. 再次 load() 返回成功（幂等，不重复 dlopen）
  3. create_session() 后再次 create_session() 幂等
  4. destroy_session() 清理

pytest 风格（P0-4）：正式可被 pytest 收集。
环境区分：麒麟 L1/L2（KYLIN_L2=1）缺 kylin_embedding 必须失败；WSL 允许 skip。

注意：全部断言放在**单个测试函数**内、使用**单个 EmbeddingBridge 实例**。
原因：SDK 在 dlopen→dlclose→再次 dlopen 的重载路径上会触发崩溃
（麒麟 VM 实测 Fatal Python error: Aborted），因此不能每个断言单独
创建 fixture；单实例顺序执行与 Day2 宿主实测路径一致。
另外：create_session 后必须完成至少一次 embed 再 destroy（对齐 run_smoke
稳定路径），否则 SDK 半初始化状态 dlclose 会 abort（麒麟 VM 实测）。
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


def test_load_and_session_idempotent():
    """单实例顺序验证 load/create_session 幂等与 destroy 清理。

    对应 Day2 宿主实测路径（同一进程一次 dlopen/dlclose），避免重载崩溃。
    """
    bridge = kb.EmbeddingBridge()

    # 1. 首次 load 成功
    bridge.load()
    assert bridge.loaded is True, "首次 load() 后 loaded=True"

    # 2. 二次 load 幂等（不重复 dlopen，不抛异常）
    bridge.load()
    assert bridge.loaded is True, "二次 load() 后 loaded 仍为 True"

    # 3. create_session 成功
    bridge.create_session()
    assert bridge.has_session is True, "create_session() 后 has_session=True"

    # 4. 二次 create_session 幂等
    bridge.create_session()
    assert bridge.has_session is True, "二次 create_session() 幂等"

    # 4.5 真实 embed 一次（对齐 run_smoke 已验证的稳定路径）
    # 麒麟实测：create_session 后未 embed 就 destroy 会触发 SDK 崩溃
    # （Fatal Python error: Aborted）；先完成一次真实调用再清理可避免。
    vec = bridge.embed("")
    assert vec.dimension == 768, f"embed 返回维度 768（实际 {vec.dimension}）"

    # 5. destroy 清理
    bridge.destroy_session()
    assert bridge.has_session is False, "destroy_session() 后 has_session=False"
