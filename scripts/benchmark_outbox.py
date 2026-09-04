#!/usr/bin/env python3
"""D13A Outbox 高压积压与 drain benchmark。

测试真实 SQLite ``outbox`` 表和 ``OutboxWorker``。脚本使用新的/空的显式 DB
路径，不清理既有数据库；若启动前 backlog 非零则 fail-closed。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_REPO = Path(__file__).resolve().parents[1]
_SERVICE = _REPO / "memory-service"
_SCRIPTS = Path(__file__).resolve().parent
for path in (_SERVICE, _SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from bench_utils import ResourceSampler, append_jsonl, resource_metrics, utc_now, write_json, write_jsonl
from db.engine import create_db_engine, init_schema
from db import repositories as repo
from outbox.worker import OutboxWorker


def _record(worker: OutboxWorker, resource_samples: list[dict[str, Any]], *, phase: str,
            rows: list[dict[str, Any]], elapsed_s: float) -> dict[str, Any]:
    metrics = worker.metrics()
    resource = resource_samples[-1] if resource_samples else {}
    row = {
        "timestamp": utc_now(),
        "phase": phase,
        "elapsed_since_producer_start_s": round(elapsed_s, 6),
        "backlog": metrics.get("backlog"),
        "processed": metrics.get("processed"),
        "dead_letters": metrics.get("dead_letters"),
        "index_sync_lag": metrics.get("index_sync_lag"),
        "index_sync_lag_seconds": metrics.get("index_sync_lag_seconds"),
        "rss_mb": resource.get("rss_mb"),
        "cpu_percent": resource.get("cpu_percent"),
    }
    rows.append(row)
    return row


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="D13A Outbox backlog stress benchmark")
    parser.add_argument("--db", type=Path, required=True, help="专用 SQLite DB 路径（不会删除已有 DB）")
    parser.add_argument("--events", type=int, default=5000)
    parser.add_argument("--producer-batch", type=int, default=250)
    parser.add_argument("--consumer-delay-ms", type=float, default=1.0)
    parser.add_argument("--poll-interval-ms", type=float, default=20.0)
    parser.add_argument("--sample-interval-ms", type=float, default=100.0)
    parser.add_argument("--drain-timeout-s", type=float, default=120.0)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if (args.events <= 0 or args.producer_batch <= 0 or args.consumer_delay_ms < 0
            or args.poll_interval_ms <= 0 or args.sample_interval_ms <= 0
            or args.drain_timeout_s <= 0):
        parser.error("events/batch/interval/timeout 参数不合法")

    args.db.parent.mkdir(parents=True, exist_ok=True)
    engine = create_db_engine(str(args.db))
    init_schema(engine)
    worker = OutboxWorker(
        engine,
        poll_interval_s=args.poll_interval_ms / 1000.0,
        max_retries=0,
        consumer=lambda _event_type, _payload: time.sleep(args.consumer_delay_ms / 1000.0),
    )
    initial = worker.metrics()
    if initial.get("backlog") != 0:
        print(f"拒绝在非空 backlog 上运行：{initial}", file=sys.stderr)
        return 2

    resource_sampler = ResourceSampler(interval_s=args.sample_interval_ms / 1000.0)
    resource_sampler.start()
    timeline: list[dict[str, Any]] = []
    submitted = 0
    producer_errors = 0
    producer_started = time.monotonic()
    try:
        # 先以批次快速灌入，提交后立即记录 backlog；随后再启动真实 Worker，
        # 让生产阶段明确形成可观测峰值，并避免与 SQLite 单写锁抢占生产样本。
        for offset in range(0, args.events, args.producer_batch):
            count = min(args.producer_batch, args.events - offset)
            try:
                with engine.begin() as conn:
                    for index in range(count):
                        event_no = offset + index
                        repo.enqueue_outbox(
                            conn,
                            aggregate_type="turn",
                            aggregate_id=f"day13a-{event_no:08d}",
                            event_type=repo.EVENT_TURN_FINALIZED,
                            payload={
                                "event_id": f"day13a-{event_no:08d}",
                                "trace_id": "day13a-outbox",
                                "created_at": datetime.now(timezone.utc).isoformat(),
                            },
                        )
            except Exception as exc:  # noqa: BLE001 - retain producer error count
                producer_errors += count
                print(f"Outbox producer batch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            else:
                submitted += count
            _record(worker, resource_sampler.samples, phase="produce", rows=timeline,
                    elapsed_s=time.monotonic() - producer_started)
        producer_seconds = time.monotonic() - producer_started
        max_backlog = max((int(row.get("backlog") or 0) for row in timeline), default=0)
        max_row = next((row for row in timeline if row.get("backlog") == max_backlog), None)
        worker_started = time.monotonic()
        worker.start()
        deadline = worker_started + args.drain_timeout_s
        last_sample = 0.0
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now - last_sample >= args.sample_interval_ms / 1000.0:
                _record(worker, resource_sampler.samples, phase="drain", rows=timeline,
                        elapsed_s=time.monotonic() - producer_started)
                last_sample = now
            if timeline[-1].get("backlog") == 0:
                break
            time.sleep(min(args.sample_interval_ms / 1000.0, 0.1))
        final = _record(worker, resource_sampler.samples, phase="drain", rows=timeline,
                        elapsed_s=time.monotonic() - producer_started)
        drain_seconds = time.monotonic() - worker_started
        if final.get("backlog") != 0:
            print(f"Outbox drain 超时，最终 metrics={final}", file=sys.stderr)
            return 2
    finally:
        worker.stop()
        resources = resource_sampler.stop()

    processed = int(final.get("processed") or 0)
    output = {
        "benchmark": "outbox_queue_backlog_drain",
        "formal_run": True,
        "measurement_scope": "outbox_queue_backlog_drain",
        "index_backlog_measurement": {
            "status": "not_measured",
            "reason": (
                "当前 workload 写入 turn.finalized，并使用可控 sleep consumer；"
                "未经过 memory.upserted → index consumer → Vector/Embedding backend。"
            ),
        },
        "db": str(args.db),
        "events_submitted": submitted,
        "events_processed": processed,
        "errors": producer_errors + int(final.get("dead_letters") or 0),
        "producer_throughput": round(submitted / producer_seconds, 3)
        if producer_seconds > 0 else 0.0,
        "consumer_throughput": round(processed / drain_seconds, 3)
        if drain_seconds > 0 else 0.0,
        "max_backlog": max_backlog,
        "time_to_max_backlog_seconds": round(
            float(max_row["elapsed_since_producer_start_s"]), 3
        ) if max_row is not None else None,
        "drain_time_seconds": round(drain_seconds, 3),
        "dead_letters": int(final.get("dead_letters") or 0),
        "index_sync_lag": final.get("index_sync_lag"),
        "index_sync_lag_seconds": final.get("index_sync_lag_seconds"),
        **resource_metrics(resources),
    }
    # 保留任务清单中的字段名，同时提供带单位的明确别名。
    output["time_to_max_backlog"] = output["time_to_max_backlog_seconds"]
    if args.output_dir:
        write_jsonl(args.output_dir / "raw" / "outbox.jsonl", timeline)
        append_jsonl(
            args.output_dir / "raw" / "resources.jsonl",
            ({**row, "benchmark": "outbox"} for row in resources),
        )
        write_json(args.output_dir / "outbox.summary.json", output)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
