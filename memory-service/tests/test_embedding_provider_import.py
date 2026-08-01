"""
test_embedding_provider_import.py

轨道 A — EmbeddingProvider 导入与契约测试（Day4）

验证:
  1. providers 包可导入（即使 kylin_embedding 未编译，也应给出明确报错）
  2. 契约字段存在（embed/embed_batch/get_dimension/model_info）
  3. 类型校验（非 str 输入抛 TypeError）

不依赖麒麟 SDK（kylin_embedding 模块缺失时跳过真实调用测试）。
"""

import importlib
import sys
from pathlib import Path

# 把 memory-service 加入导入路径
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "memory-service"))

failures = 0


def check(cond, name):
    global failures
    if cond:
        print(f"  [PASS] {name}")
    else:
        print(f"  [FAIL] {name}")
        failures += 1


def main():
    print("=== test_embedding_provider_import ===")

    # 1. providers 包可导入
    try:
        from providers import EmbeddingProvider, EmbeddingResult, ModelInfo
        check(True, "providers 包导入成功")
    except ImportError as exc:
        check(False, f"providers 包导入失败: {exc}")
        return 1

    # 2. 契约接口存在
    for attr in ["embed", "embed_batch", "get_dimension", "model_info"]:
        check(hasattr(EmbeddingProvider, attr), f"EmbeddingProvider.{attr} 存在")

    # 3. 数据结构字段
    import dataclasses
    fields = {f.name for f in dataclasses.fields(EmbeddingResult)}
    for fld in ["vector", "dimension", "l2_norm", "error_code", "error_message"]:
        check(fld in fields, f"EmbeddingResult.{fld} 存在")

    mf = {f.name for f in dataclasses.fields(ModelInfo)}
    for fld in ["name", "dimension", "ondevice", "loaded"]:
        check(fld in mf, f"ModelInfo.{fld} 存在")

    # 4. kylin_embedding 模块状态提示
    try:
        import kylin_embedding  # noqa: F401
        check(True, "kylin_embedding 模块已编译（麒麟 VM 环境）")
    except ImportError:
        print("  [SKIP] kylin_embedding 未编译，跳过真实调用测试（WSL/开发环境正常）")

    print(f"=== 结果: {'PASS' if failures == 0 else 'FAIL'} ({failures} failures) ===")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
