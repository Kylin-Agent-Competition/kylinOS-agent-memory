"""
test_exception_mapping.py

轨道 A — BridgeError → Python 异常映射测试（Day4）

验证 kylin_embedding 模块的异常层次结构与错误码映射规则。
仅在 kylin_embedding 已编译的环境（麒麟 VM）运行；缺失时给出明确跳过说明。
"""

import sys
from pathlib import Path

failures = 0


def check(cond, name):
    global failures
    if cond:
        print(f"  [PASS] {name}")
    else:
        print(f"  [FAIL] {name}")
        failures += 1


def main():
    print("=== test_exception_mapping ===")

    try:
        import kylin_embedding as kb
    except ImportError:
        print("  [SKIP] kylin_embedding 未编译，跳过（需麒麟 VM 构建）")
        return 0

    # 1. 异常类型层次：所有子类继承 BridgeError
    for name in [
        "BridgeSoNotFoundError", "BridgeLoadError", "BridgeSymbolError",
        "BridgeSessionError", "BridgeEmbedError", "BridgeSdkError",
        "BridgeTimeoutError", "BridgeCancelledError", "BridgeModelError",
    ]:
        exc_cls = getattr(kb, name, None)
        check(exc_cls is not None, f"异常类型 {name} 存在")
        if exc_cls is not None:
            check(issubclass(exc_cls, kb.BridgeError), f"{name} 继承 BridgeError")

    # 2. 未加载时调用 embed → BridgeLoadError（映射自 ERR_DLOPEN_FAILED）
    try:
        bridge = kb.EmbeddingBridge()
        bridge.embed("hello")
        check(False, "未加载时 embed 应抛异常")
    except kb.BridgeLoadError:
        check(True, "未加载时 embed → BridgeLoadError")
    except kb.BridgeError as exc:
        check(False, f"未加载时 embed 抛错但类型不符: {type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001
        check(False, f"未加载时 embed 抛非 Bridge 异常: {type(exc).__name__}: {exc}")

    # 3. so 不存在 → BridgeSoNotFoundError
    try:
        params = kb.BridgeInitParams()
        params.so_path = "/tmp/definitely_not_exist.so.1"
        bridge2 = kb.EmbeddingBridge(params)
        bridge2.load()
        check(False, "so 不存在时 load 应抛异常")
    except kb.BridgeSoNotFoundError:
        check(True, "so 不存在时 load → BridgeSoNotFoundError")
    except kb.BridgeError as exc:
        check(False, f"so 不存在时 load 抛错但类型不符: {type(exc).__name__}")

    # 4. BridgeInitParams 默认 so_path 是 x86_64 路径
    params = kb.BridgeInitParams()
    check("libkysdk-coreai-embedding" in params.so_path,
          f"默认 so_path 含核心库名（实际: {params.so_path}）")

    print(f"=== 结果: {'PASS' if failures == 0 else 'FAIL'} ({failures} failures) ===")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
