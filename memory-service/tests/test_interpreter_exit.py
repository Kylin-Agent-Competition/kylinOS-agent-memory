"""
test_interpreter_exit.py — 轨道 A Day4 P2：Python 解释器退出析构路径验证

验证（麒麟 VM 真实 .so）：进程正常退出时，共享 Bridge 析构
（destroy_session + dlclose）无 Abort、挂起或 core dump。

方式：子进程运行一段"start → embed → 正常退出"的脚本，
父进程断言子进程退出码为 0 且无 core dump / Abort 输出。

麒麟 L1/L2 缺 kylin_embedding 必须失败；WSL 允许 skip。
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

IS_L2_HOST = os.environ.get("KYLIN_L2") == "1"

try:
    import kylin_embedding  # noqa: F401
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


# 子进程脚本：启动 → embed → 正常退出（验证析构路径）
_CHILD = r"""
import sys
sys.path.insert(0, {ms!r})
from providers import EmbeddingProvider
p = EmbeddingProvider()
p.start()
r = p.embed("exit-test")
assert r.dimension == 768
p.close()
print("CHILD_OK")
"""


def test_interpreter_exit_no_abort():
    """解释器正常退出时 Bridge 析构无 Abort/挂起/core dump。"""
    ms_path = str(Path(__file__).resolve().parents[1])  # memory-service/
    # 确保子进程能找到 kylin_embedding 和 providers
    env = dict(os.environ)
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") + os.pathsep + ms_path
    child = _CHILD.format(ms=ms_path)

    try:
        proc = subprocess.run(
            [sys.executable, "-c", child],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("子进程超时挂起（解释器退出析构路径阻塞）")

    assert proc.returncode == 0, \
        f"子进程异常退出 rc={proc.returncode}, stderr={proc.stderr[-500:]}"
    assert "CHILD_OK" in proc.stdout, f"子进程未正常完成: {proc.stdout[-300:]}"
    # Abort/core dump 特征：rc 非 0 + stderr 含 abort/terminate/core
    assert "Aborted" not in proc.stderr, f"出现 Abort: {proc.stderr[-500:]}"
    assert "terminate called" not in proc.stderr, \
        f"出现 terminate: {proc.stderr[-500:]}"
