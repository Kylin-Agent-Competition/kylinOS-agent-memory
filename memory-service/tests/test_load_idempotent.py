"""
test_load_idempotent.py — 轨道 A Day4 load() 成功幂等性测试（麒麟 VM）

验证:
  1. load() 成功（真实 .so）
  2. 再次 load() 返回成功（幂等，不重复 dlopen）
  3. create_session() 后再次 create_session() 幂等

需麒麟 VM 真实 SDK（kylin_embedding 已编译 + Runtime 运行）。
"""

import sys
from pathlib import Path

# memory-service/tests/ 下：parents[1] = memory-service/，直接加入即可
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

failures = 0


def check(cond, name):
    global failures
    if cond:
        print(f"  [PASS] {name}")
    else:
        print(f"  [FAIL] {name}")
        failures += 1


def main():
    print("=== test_load_idempotent ===")

    try:
        import kylin_embedding as kb
    except ImportError:
        print("  [SKIP] kylin_embedding 未编译（需麒麟 VM）")
        return 0

    bridge = kb.EmbeddingBridge()

    # 1. 首次 load 成功
    bridge.load()
    check(bridge.loaded, "首次 load() 成功，loaded=True")

    # 2. 二次 load 幂等（不抛异常）
    try:
        bridge.load()
        check(True, "二次 load() 幂等成功（不抛异常）")
    except Exception as exc:  # noqa: BLE001
        check(False, f"二次 load() 抛异常: {type(exc).__name__}: {exc}")
    check(bridge.loaded, "二次 load() 后 loaded 仍为 True")

    # 3. create_session 成功
    bridge.create_session()
    check(bridge.has_session, "create_session() 成功，has_session=True")

    # 4. 二次 create_session 幂等
    try:
        bridge.create_session()
        check(True, "二次 create_session() 幂等成功（不抛异常）")
    except Exception as exc:  # noqa: BLE001
        check(False, f"二次 create_session() 抛异常: {type(exc).__name__}: {exc}")

    # 5. 清理
    bridge.destroy_session()
    check(not bridge.has_session, "destroy_session() 后 has_session=False")

    print(f"=== 结果: {'PASS' if failures == 0 else 'FAIL'} ({failures} failures) ===")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
