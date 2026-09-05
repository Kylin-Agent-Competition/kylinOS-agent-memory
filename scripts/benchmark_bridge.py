#!/usr/bin/env python3
"""D13A C++/Python ``EmbeddingBridge.embed`` benchmark。

该脚本不经过 EmbeddingService 或 UDS，只测 pybind11 → C++ Bridge → SDK 路径。
没有编译好的 ``kylin_embedding`` 时明确失败；不会以 fake 结果冒充正式基线。
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from bench_utils import (ResourceSampler, append_jsonl, benchmark_summary,
                          file_sha256, resource_metrics, write_json, write_jsonl)


def _run_requests(bridge: Any, texts: list[str], concurrency: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    lock = threading.Lock()

    def worker(item: tuple[int, str]) -> None:
        request, text = item
        started = time.monotonic()
        try:
            result = bridge.embed(text, 10000)
            ok = int(result.dimension) > 0 and len(result.data) == int(result.dimension)
            error = None if ok else {"message": "invalid embedding result"}
        except Exception as exc:  # noqa: BLE001
            ok = False
            error = {"type": type(exc).__name__, "message": str(exc)[:200]}
        row: dict[str, Any] = {
            "request": request,
            "concurrency": concurrency,
            "latency_ms": round((time.monotonic() - started) * 1000.0, 3),
            "ok": ok,
        }
        if error:
            row["error"] = error
        with lock:
            rows.append(row)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        list(executor.map(worker, enumerate(texts)))
    return sorted(rows, key=lambda row: int(row["request"]))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="D13A direct EmbeddingBridge benchmark")
    parser.add_argument("--texts", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 4, 8])
    parser.add_argument("--warmup", type=int, default=50)
    parser.add_argument("--so-path", help="可选，覆盖 BridgeInitParams.so_path")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.texts <= 0 or args.warmup < 0 or any(c <= 0 for c in args.concurrency):
        parser.error("texts/concurrency 必须为正数，warmup 不得为负")

    try:
        import kylin_embedding as module
    except ImportError as exc:
        print(f"kylin_embedding 不可用：{exc}", file=sys.stderr)
        return 2

    params = module.BridgeInitParams()
    if args.so_path:
        params.so_path = args.so_path
    bridge = module.EmbeddingBridge(params)
    bridge.load()
    bridge.create_session()

    summaries: dict[str, Any] = {}
    all_rows: list[dict[str, Any]] = []
    resource_rows: list[dict[str, Any]] = []
    try:
        for concurrency in args.concurrency:
            warmup = [f"day13a-warmup-c{concurrency:02d}-{i:04d}" for i in range(args.warmup)]
            if warmup:
                _run_requests(bridge, warmup, concurrency)
            texts = [f"day13a-bridge-c{concurrency:02d}-{i:04d}" for i in range(args.texts)]
            sampler = ResourceSampler()
            sampler.start()
            started = time.monotonic()
            rows = _run_requests(bridge, texts, concurrency)
            wall_seconds = time.monotonic() - started
            resources = sampler.stop()
            resource_rows.extend({**row, "benchmark": "bridge", "concurrency": concurrency}
                                  for row in resources)
            successful = [row["latency_ms"] / 1000.0 for row in rows if row["ok"]]
            summaries[str(concurrency)] = benchmark_summary(
                name="bridge", requests=len(rows),
                errors=sum(1 for row in rows if not row["ok"]),
                wall_seconds=wall_seconds, latencies_s=successful,
                resources=resource_metrics(resources), concurrency=concurrency,
            )
            all_rows.extend(rows)
            print(
                f"[bridge concurrency={concurrency}] requests={len(rows)} "
                f"errors={summaries[str(concurrency)]['errors']} "
                f"throughput={summaries[str(concurrency)]['throughput_req_s']:.3f} req/s "
                f"P50={summaries[str(concurrency)]['p50_ms']:.3f}ms "
                f"P95={summaries[str(concurrency)]['p95_ms']:.3f}ms "
                f"P99={summaries[str(concurrency)]['p99_ms']:.3f}ms",
                flush=True,
            )
    finally:
        bridge.destroy_session()

    output = {
        "benchmark": "bridge",
        "formal_run": True,
        "texts": args.texts,
        "warmup": args.warmup,
        "concurrency": args.concurrency,
        "rounds": summaries,
        "sdk_so_path": str(params.so_path),
        "sdk_so_sha256": file_sha256(str(params.so_path)),
        "sdk_loaded": bool(getattr(bridge, "loaded", False)),
    }
    if args.output_dir:
        write_jsonl(args.output_dir / "raw" / "bridge.jsonl", all_rows)
        append_jsonl(args.output_dir / "raw" / "resources.jsonl", resource_rows)
        write_json(args.output_dir / "bridge.summary.json", output)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
