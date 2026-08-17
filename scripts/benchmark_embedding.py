#!/usr/bin/env python
"""benchmark_embedding.py — 轨道 A Day9 Embedding 串行/低并发吞吐测量脚本

台账 R47（A 轨 D9）：测量 Embedding 串行/低并发吞吐 → Embedding 吞吐基线
+ 积压治理策略。可复现（固定样本/固定并发/输出原始数据 + 汇总）。

用法：
  # 本地（无 SDK，用 fake provider 冒烟）：
  PYTHONPATH=memory-service python scripts/benchmark_embedding.py --fake --texts 50

  # 麒麟 VM（真实 SDK）：
  cd /mnt/shared && PYTHONPATH=/mnt/shared/memory-service \
    LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH \
    /tmp/day8-venv/bin/python scripts/benchmark_embedding.py --texts 100 --concurrency 1 4 8

输出：stdout 原始数据（每轮 per-request 耗时）+ JSON 汇总（P50/P95/P99/吞吐）
      可 tee 到 evidence/l1/day9_embedding_throughput.log 落盘。

指标语义（架构 TABLE 29 延迟预算：Embedding 查询 ≤180ms）：
  - 串行吞吐（req/s）：单连接顺序调用的吞吐
  - 低并发吞吐（req/s）：2/4/8 并发下吞吐（线程池 max_workers=2 上限约束）
  - P50/P95/P99：单请求耗时分布（判断是否逼近 180ms 预算）
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

# 保证从仓库任意目录运行时都能 import memory-service 包
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MSVC = os.path.join(_REPO, "memory-service")
if _MSVC not in sys.path:
    sys.path.insert(0, _MSVC)

# ── provider 选择：真实 SDK（默认）或 fake（冒烟） ──

def _make_provider(fake: bool):
    if not fake:
        from providers import EmbeddingProvider
        return EmbeddingProvider()
    from providers import EmbeddingResult

    class FakeProvider:
        def __init__(self):
            self._calls = 0

        def start(self):
            pass

        def close(self):
            pass

        def get_dimension(self):
            return 768

        def embed(self, text, *, timeout_ms=5000):
            time.sleep(0.002)  # 模拟 ~2ms SDK 调用
            self._calls += 1
            return EmbeddingResult(vector=[0.1] * 768, dimension=768, l2_norm=1.0)

    return FakeProvider()


def _run_serial(service, texts: List[str], concurrency: int) -> List[float]:
    """指定并发下跑一批 embed，返回 per-request 耗时（秒）。"""
    latencies: List[float] = []
    lock = threading.Lock()

    def worker(t: str) -> None:
        start = time.monotonic()
        r = service.embed(t, timeout_ms=10000)
        dur = time.monotonic() - start
        if not r.get("ok"):
            raise RuntimeError(f"embed failed: {r}")
        with lock:
            latencies.append(dur)

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        list(ex.map(worker, texts))
    return latencies


def _percentile(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = max(0, min(len(sorted_vals) - 1, int(len(sorted_vals) * pct)))
    return sorted_vals[idx]


def main() -> int:
    parser = argparse.ArgumentParser(description="Day9 Embedding 吞吐测量")
    parser.add_argument("--texts", type=int, default=100,
                        help="每轮文本数（默认 100）")
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1],
                        help="并发档位，如 1 4 8（默认 1=串行）")
    parser.add_argument("--fake", action="store_true",
                        help="用 fake provider 冒烟（无 SDK 环境）")
    parser.add_argument("--json", action="store_true",
                        help="仅输出 JSON 汇总（供脚本解析）")
    args = parser.parse_args()

    from embedding.embedding_service import EmbeddingService

    provider = _make_provider(args.fake)
    service = EmbeddingService(provider=provider)
    service.start()

    summary = {"texts": args.texts, "rounds": {}}
    for conc in args.concurrency:
        # Review 修复：每轮生成唯一文本（含轮次序号）——若各轮复用同一批 texts，
        # 第 2 轮起全部缓存命中（P50≈0ms、吞吐虚高），测的不是 Provider 吞吐。
        texts = [f"day9-benchmark-文本-{conc:02d}-{i:04d}"
                 for i in range(args.texts)]
        wall_start = time.monotonic()
        latencies = _run_serial(service, texts, conc)
        wall_seconds = time.monotonic() - wall_start
        latencies.sort()
        n = len(latencies)
        # Review 修复：并发>1 时吞吐 = n / 轮次墙钟时长（不是 per-request 之和，
        # 后者在并发下虚高）。P50/P95/P99 仍基于 per-request 耗时（延迟分布）。
        throughput = n / wall_seconds if wall_seconds > 0 else 0.0
        p50 = _percentile(latencies, 0.50)
        p95 = _percentile(latencies, 0.95)
        p99 = _percentile(latencies, 0.99)
        summary["rounds"][str(conc)] = {
            "concurrency": conc,
            "requests": n,
            "total_seconds": round(wall_seconds, 4),
            "throughput_req_s": round(throughput, 2),
            "p50_ms": round(p50 * 1000, 2),
            "p95_ms": round(p95 * 1000, 2),
            "p99_ms": round(p99 * 1000, 2),
        }
        if not args.json:
            print(f"\n[concurrency={conc}] {n} requests, "
                  f"wall={wall_seconds:.4f}s, throughput={throughput:.2f} req/s, "
                  f"P50={p50*1000:.2f}ms P95={p95*1000:.2f}ms P99={p99*1000:.2f}ms",
                  flush=True)

    service.close()

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("\n== JSON 汇总 ==")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
