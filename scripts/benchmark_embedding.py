#!/usr/bin/env python
"""D13A Embedding Service/Provider 性能基线脚本。

默认使用真实 SDK，测试矩阵为 1000 请求、并发 1/4/8；可复现（固定样本、
warm-up、原始数据 + 汇总）。

用法：
  # 本地（无 SDK，用 fake provider 冒烟）：
  PYTHONPATH=memory-service:scripts python scripts/benchmark_embedding.py --fake --texts 50

  # 麒麟 VM（真实 SDK）：
  cd /mnt/shared && PYTHONPATH=/mnt/shared/memory-service \
    LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends:$LD_LIBRARY_PATH \
    /tmp/day13a-venv/bin/python scripts/benchmark_embedding.py --texts 1000 --concurrency 1 4 8 --warmup 50

输出：stdout JSON 汇总；提供 --output-dir 时保存每条请求和资源样本 JSONL。

指标语义（架构 TABLE 29 延迟预算：Embedding 查询 ≤180ms）：
  - 串行吞吐（req/s）：单连接顺序调用的吞吐
  - 并发吞吐（req/s）：各并发档位的墙钟吞吐
  - P50/P95/P99：单请求耗时分布（判断是否逼近 180ms 预算）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from bench_utils import (ResourceSampler, append_jsonl, benchmark_summary,
                          resource_metrics, write_json, write_jsonl)

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


def _run_serial(service, texts: List[str], concurrency: int) -> List[dict]:
    """指定并发下跑一批 embed，保留每条请求的成功与耗时。"""
    rows: List[dict] = []
    lock = threading.Lock()

    def worker(item) -> None:
        request, t = item
        start = time.monotonic()
        try:
            r = service.embed(t, timeout_ms=10000)
            ok = bool(r.get("ok")) and not bool(r.get("degraded"))
            error = None if ok else r.get("error") or r.get("degraded_reason")
        except Exception as exc:  # noqa: BLE001 - 保存失败样本而非中断整个轮次
            ok = False
            error = {"type": type(exc).__name__, "message": str(exc)[:200]}
        row = {
            "request": request,
            "concurrency": concurrency,
            "latency_ms": round((time.monotonic() - start) * 1000.0, 3),
            "ok": ok,
        }
        if error:
            row["error"] = error
        with lock:
            rows.append(row)

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        list(ex.map(worker, enumerate(texts)))
    return sorted(rows, key=lambda row: int(row["request"]))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="D13A Embedding P50/P95/P99 benchmark")
    parser.add_argument("--texts", type=int, default=1000,
                        help="正式请求数（默认 1000）")
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 4, 8],
                        help="并发档位（默认 1 4 8）")
    parser.add_argument("--warmup", type=int, default=50,
                        help="每档 warm-up 请求数（默认 50）")
    parser.add_argument("--fake", action="store_true",
                        help="用 fake provider 冒烟（无 SDK 环境）")
    parser.add_argument("--output-dir", type=Path,
                        help="运行目录；保存 raw/embedding.jsonl 与摘要")
    parser.add_argument("--json", action="store_true",
                        help="仅输出 JSON 汇总（供脚本解析）")
    args = parser.parse_args(argv)

    if args.texts <= 0 or args.warmup < 0 or any(c <= 0 for c in args.concurrency):
        parser.error("texts/concurrency 必须为正数，warmup 不得为负")

    from embedding.embedding_service import EmbeddingService

    provider = _make_provider(args.fake)
    service = EmbeddingService(provider=provider)
    service.start()

    summary = {
        "benchmark": "embedding",
        "formal_run": not args.fake,
        "texts": args.texts,
        "warmup": args.warmup,
        "concurrency": args.concurrency,
        "rounds": {},
    }
    all_rows = []
    resource_rows = []
    for conc in args.concurrency:
        warmup = [f"day13a-warmup-c{conc:02d}-{i:04d}" for i in range(args.warmup)]
        if warmup:
            _run_serial(service, warmup, conc)
        # Review 修复：每轮生成唯一文本（含轮次序号）——若各轮复用同一批 texts，
        # 第 2 轮起全部缓存命中（P50≈0ms、吞吐虚高），测的不是 Provider 吞吐。
        texts = [f"day13a-benchmark-文本-{conc:02d}-{i:04d}"
                 for i in range(args.texts)]
        wall_start = time.monotonic()
        sampler = ResourceSampler()
        sampler.start()
        lat_rows = _run_serial(service, texts, conc)
        wall_seconds = time.monotonic() - wall_start
        sampled_resources = sampler.stop()
        resources = resource_metrics(sampled_resources)
        resource_rows.extend({**row, "benchmark": "embedding", "concurrency": conc}
                             for row in sampled_resources)
        latencies = [float(row["latency_ms"]) / 1000.0
                     for row in lat_rows if row["ok"]]
        round_summary = benchmark_summary(
            name="embedding", requests=len(lat_rows),
            errors=sum(1 for row in lat_rows if not row["ok"]),
            wall_seconds=wall_seconds, latencies_s=latencies,
            resources=resources, concurrency=conc,
        )
        summary["rounds"][str(conc)] = round_summary
        all_rows.extend(lat_rows)
        if not args.json:
            print(f"\n[concurrency={conc}] {round_summary['requests']} requests, "
                  f"wall={wall_seconds:.4f}s, throughput={round_summary['throughput_req_s']:.3f} req/s, "
                  f"P50={round_summary['p50_ms']:.3f}ms P95={round_summary['p95_ms']:.3f}ms "
                  f"P99={round_summary['p99_ms']:.3f}ms",
                  flush=True)

    service.close()

    if args.output_dir:
        write_jsonl(args.output_dir / "raw" / "embedding.jsonl", all_rows)
        append_jsonl(args.output_dir / "raw" / "resources.jsonl", resource_rows)
        write_json(args.output_dir / "embedding.summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
