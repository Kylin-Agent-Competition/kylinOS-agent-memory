#!/usr/bin/env python3
"""D13A 真实 ``memory.upserted`` 索引积压 benchmark。

Unlike ``benchmark_outbox.py``, this workload traverses the production-shaped
chain: SQLite outbox -> OutboxWorker -> index consumer -> SqliteVectorProvider
-> VectorCliClient -> the configured Vector Engine. The benchmark fails closed
when the CLI is unavailable or when any event is dead-lettered.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
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

from bench_utils import ResourceSampler, append_jsonl, resource_metrics, utc_now, write_json
from db import repositories as repo
from db.engine import create_db_engine, init_schema
from db.schema import vector_index_entries, vector_index_generations
from outbox.router import build_outbox_router
from outbox.worker import OutboxWorker
from retrieval.real_vector_provider import VectorCliClient
from retrieval.sqlite_vector_provider import SqliteVectorProvider


KEY_ID = "d9d-internal"
KEY = b"kylin-memory-d9d-internal"


def _cli_available(cli_path: str) -> bool:
    candidate = Path(cli_path)
    return (candidate.is_file() and os.access(candidate, os.X_OK)) or shutil.which(cli_path) is not None


def _timeline_row(worker: OutboxWorker, rows: list[dict[str, Any]], started: float, phase: str) -> None:
    metrics = worker.metrics()
    rows.append({
        "timestamp": utc_now(),
        "phase": phase,
        "elapsed_s": round(time.monotonic() - started, 6),
        "backlog": metrics.get("backlog"),
        "processed": metrics.get("processed"),
        "dead_letters": metrics.get("dead_letters"),
        "index_sync_lag_seconds": metrics.get("index_sync_lag_seconds"),
    })


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="D13A real index backlog benchmark")
    parser.add_argument("--db", type=Path, required=True, help="专用 SQLite DB 路径")
    parser.add_argument("--cli", required=True, help="真实 vector_cli 可执行文件")
    parser.add_argument("--dimension", type=int, required=True)
    parser.add_argument("--events", type=int, default=5000)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--poll-interval-ms", type=float, default=20.0)
    parser.add_argument("--sample-interval-ms", type=float, default=100.0)
    parser.add_argument("--drain-timeout-s", type=float, default=300.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if (
        args.events <= 0
        or args.max_retries < 0
        or args.dimension <= 0
        or args.poll_interval_ms <= 0
        or args.sample_interval_ms <= 0
        or args.drain_timeout_s <= 0
    ):
        parser.error("events/max-retries/dimension/interval/timeout 参数不合法")
    if not _cli_available(args.cli):
        print(f"真实 vector_cli 不可执行，拒绝伪造 index backlog 结果: {args.cli}", file=sys.stderr)
        return 2

    args.db.parent.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    engine = create_db_engine(str(args.db))
    init_schema(engine)
    client = VectorCliClient(args.cli, expected_dimension=args.dimension)
    provider = SqliteVectorProvider(
        engine,
        vector_client=client,
        digest_keys={KEY_ID: KEY},
        dimension=args.dimension,
    )
    worker = OutboxWorker(
        engine,
        poll_interval_s=args.poll_interval_ms / 1000.0,
        max_retries=args.max_retries,
        consumer=build_outbox_router(vector_provider=provider).route,
    )
    initial = worker.metrics()
    if initial.get("backlog") != 0:
        print(f"拒绝在非空 backlog 上运行: {initial}", file=sys.stderr)
        return 2

    generation = f"d13a-{time.time_ns()}-{os.getpid()}"
    user_id = "day13a-index-benchmark"
    digest = "hmac-sha256:d9d-internal:" + "0" * 64
    timeline: list[dict[str, Any]] = []
    sampler = ResourceSampler(interval_s=args.sample_interval_ms / 1000.0)
    sampler.start()
    started = time.monotonic()
    submitted = 0
    producer_errors = 0
    try:
        # Memory rows and their outbox events are created in one transaction,
        # matching the application's business-write + outbox atomicity.
        with engine.begin() as conn:
            for index in range(args.events):
                memory_id = repo.insert_memory_entry(
                    conn,
                    user_id=user_id,
                    entry_type="knowledge",
                    content={"index_text": f"D13A index backlog record {index}"},
                    confidence=1.0,
                    trace_id=f"d13a-index-{index}",
                )
                repo.enqueue_outbox(
                    conn,
                    aggregate_type="memory",
                    aggregate_id=str(memory_id),
                    event_type=repo.EVENT_MEMORY_UPSERTED,
                    payload={
                        "event_id": f"d13a-index-{index}",
                        "trace_id": f"d13a-index-{index}",
                        "memory_id": str(memory_id),
                        "version_id": "v1",
                        "user_id": user_id,
                        "vector": [1.0] + [0.0] * (args.dimension - 1),
                        "object_type": "knowledge",
                        "index_text_hash": digest,
                        "index_generation": generation,
                        "source_watermark_value": index + 1,
                        "idempotency_key": f"memory:{memory_id}:v1",
                    },
                )
        submitted = args.events
        _timeline_row(worker, timeline, started, "produce")
    except Exception as exc:  # noqa: BLE001 - benchmark reports producer failure
        producer_errors = args.events - submitted
        print(f"真实 index producer 失败: {type(exc).__name__}: {exc}", file=sys.stderr)

    max_backlog = max((int(row.get("backlog") or 0) for row in timeline), default=0)
    worker_started = time.monotonic()
    worker.start()
    deadline = worker_started + args.drain_timeout_s
    try:
        while time.monotonic() < deadline:
            _timeline_row(worker, timeline, started, "drain")
            latest = timeline[-1]
            if latest.get("backlog") == 0:
                break
            time.sleep(min(args.sample_interval_ms / 1000.0, 0.1))
        _timeline_row(worker, timeline, started, "drain")
        final = timeline[-1]
    finally:
        worker.stop()
        resources = sampler.stop()

    drain_seconds = time.monotonic() - worker_started
    with engine.connect() as conn:
        indexed_count = len(conn.execute(
            vector_index_entries.select().with_only_columns(vector_index_entries.c.memory_entry_id).where(
                vector_index_entries.c.generation == generation,
                vector_index_entries.c.is_active == 1,
            )
        ).fetchall())
        generation_row = conn.execute(
            vector_index_generations.select().where(
                vector_index_generations.c.scope_id == f"user:{user_id}",
                vector_index_generations.c.generation == generation,
            )
        ).mappings().one_or_none()
    processed = int(final.get("processed") or 0)
    dead_letters = int(final.get("dead_letters") or 0)
    final_backlog = int(final["backlog"]) if final.get("backlog") is not None else -1
    backend_verified = generation_row is not None and indexed_count == submitted
    result = {
        "benchmark": "real_index_backlog_drain",
        "formal_run": True,
        "measurement_scope": "outbox_queue_backlog_drain",
        "chain": [
            "memory.upserted",
            "OutboxWorker",
            "index_consumer",
            "SqliteVectorProvider",
            "VectorCliClient",
            "Vector Engine",
        ],
        "events_submitted": submitted,
        "events_processed": processed,
        "producer_errors": producer_errors,
        "max_retries": args.max_retries,
        "dead_letters": dead_letters,
        "initial_backlog": int(initial.get("backlog") or 0),
        "max_backlog": max_backlog,
        "final_backlog": final_backlog,
        "drain_time_seconds": round(drain_seconds, 3),
        "index_sync_lag_seconds": final.get("index_sync_lag_seconds"),
        "vector_backend": {
            "provider": "VectorCliClient",
            "verified": backend_verified,
            "indexed_active_records": indexed_count,
            "generation": generation,
        },
        "index_backlog_measurement": {
            "status": "measured" if backend_verified and not producer_errors and dead_letters == 0 and final.get("backlog") == 0 else "invalid",
            "chain_verified": backend_verified,
            "events_submitted": submitted,
            "events_processed": processed,
            "dead_letters": dead_letters,
            "final_backlog": final_backlog,
        },
        **resource_metrics(resources),
    }
    append_jsonl(args.output_dir / "raw" / "index_backlog.jsonl", timeline)
    write_json(args.output_dir / "index_backlog.summary.json", result)
    outbox_path = args.output_dir / "outbox.summary.json"
    if outbox_path.exists():
        with outbox_path.open("r", encoding="utf-8") as handle:
            outbox = json.load(handle)
        outbox["index_backlog_measurement"] = result["index_backlog_measurement"]
        outbox["index_backlog"] = result
        write_json(outbox_path, outbox)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["index_backlog_measurement"]["status"] == "measured" else 2


if __name__ == "__main__":
    raise SystemExit(main())
