import os
import platform
import sys


def _parse_os_release(path: str = "/etc/os-release") -> dict[str, str]:
    data: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                value = value[1:-1]
            data[key] = value
    return data


def test_kylin_runtime_baseline() -> None:
    # 1. /etc/os-release 真实可读
    assert os.path.isfile("/etc/os-release")
    info = _parse_os_release()
    assert info, "parsed /etc/os-release is empty"

    # 2. 麒麟系发行版识别（只读，不放宽到非麒麟）
    kylin_indicators = (
        info.get("ID", ""),
        info.get("ID_LIKE", ""),
        info.get("NAME", ""),
        info.get("PRETTY_NAME", ""),
    )
    assert any("kylin" in field.lower() for field in kylin_indicators), (
        f"current /etc/os-release is not Kylin-like: {info!r}"
    )

    # 3. CPU 架构为 x86_64
    assert platform.machine() == "x86_64", (
        f"expected x86_64, got {platform.machine()!r}"
    )

    # 4. Python 运行环境可用且满足项目技术路线（>=3.10）
    assert sys.version_info >= (3, 10), (
        f"expected Python >=3.10, got {sys.version_info!r}"
    )
    assert sys.executable and os.path.exists(sys.executable), (
        f"sys.executable invalid: {sys.executable!r}"
    )
    # 触发一次真实导入，证明解释器可执行（只读，无副作用）
    import json  # noqa: F401
