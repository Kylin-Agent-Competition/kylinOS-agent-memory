"""
run_smoke.py — 轨道 A Day4 麒麟 VM 集成冒烟测试

在麒麟 VM 上验证 Bridge/Provider 最小真实调用：
  1. 编译 kylin_embedding 模块后，导入并 start()
  2. embed("你好世界") → 验证 dim=768, L2≈1.0
  3. embed("") 空字符串 → 验证不崩溃
  4. embed_batch 顺序批处理 → 验证数量与顺序
  5. get_dimension() / model_info()

前置条件（麒麟 VM）:
  - kylin-ai-runtime 已启动
  - kylin_embedding 模块已构建并加入 PYTHONPATH
  - LD_LIBRARY_PATH 含 /usr/lib/kylin-ai/depends

用法:
  PYTHONPATH=<repo>/memory-service:<repo>/cpp-bridge/build \
  LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH \
  python run_smoke.py
"""

import sys
from pathlib import Path

# memory-service/tests/ 下：parents[1] = memory-service/，直接加入即可
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers import EmbeddingProvider  # noqa: E402

failures = 0


def check(cond, name):
    global failures
    if cond:
        print(f"  [PASS] {name}")
    else:
        print(f"  [FAIL] {name}")
        failures += 1


def main():
    print("=== Day4 麒麟 VM Embedding 集成冒烟测试 ===")

    with EmbeddingProvider() as provider:
        # 1. 中文短句
        r1 = provider.embed("你好世界")
        check(r1.dimension == 768, f"中文 dim=768 (实际 {r1.dimension})")
        check(abs(r1.l2_norm - 1.0) < 1e-4, f"中文 L2≈1.0 (实际 {r1.l2_norm:.6f})")
        check(len(r1.vector) == 768, f"vector 长度 768 (实际 {len(r1.vector)})")

        # 2. 空字符串
        r2 = provider.embed("")
        check(r2.dimension == 768, f"空字符串 dim=768 (实际 {r2.dimension})")

        # 3. 批量
        texts = ["你好世界", "Hello world", ""]
        batch = provider.embed_batch(texts)
        check(len(batch) == 3, f"batch 返回 3 条 (实际 {len(batch)})")
        check(all(r.dimension == 768 for r in batch), "batch 全部 dim=768")
        # 确定性：batch 与单条结果近似一致（量化模型可能有微小浮点差异）
        def vec_close(a, b, tol=1e-5):
            return len(a.vector) == len(b.vector) and all(
                abs(x - y) < tol for x, y in zip(a.vector, b.vector))
        check(vec_close(batch[0], r1), "batch[0] 与单条 r1 近似一致")
        check(vec_close(batch[2], r2), "batch[2] 与单条 r2 近似一致")

        # 4. 维度与模型信息
        dim = provider.get_dimension()
        check(dim == 768, f"get_dimension=768 (实际 {dim})")

        info = provider.model_info()
        check(info.dimension == 768, f"model_info.dimension=768")
        check(info.ondevice is True, "model_info.ondevice=ASSUMED True")

    print(f"=== 结果: {'PASS' if failures == 0 else 'FAIL'} ({failures} failures) ===")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
