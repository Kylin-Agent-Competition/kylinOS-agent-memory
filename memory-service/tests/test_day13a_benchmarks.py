"""D13A benchmark 工具的本地可重复冒烟测试。"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SERVICE = REPO / "memory-service"
SCRIPTS = REPO / "scripts"
for path in (SERVICE, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from bench_utils import benchmark_summary, merge_collection, merge_run, percentile  # noqa: E402
from benchmark_embedding import main as embedding_main  # noqa: E402
from benchmark_ipc import main as ipc_main  # noqa: E402
from benchmark_outbox import main as outbox_main  # noqa: E402
from db.engine import create_db_engine, init_schema  # noqa: E402
from gateway.handlers import register_default_handlers  # noqa: E402
from gateway.registry import HandlerRegistry  # noqa: E402
from gateway.server import UDSGatewayServer  # noqa: E402


def test_percentile_and_summary_use_successful_samples() -> None:
    assert percentile([1, 2, 3, 4], 0.50) == 3.0
    summary = benchmark_summary(
        name="test", requests=3, errors=1, wall_seconds=1.0,
        latencies_s=[0.001, 0.002], resources={},
    )
    assert summary["p50_ms"] == 2.0
    assert summary["throughput_req_s"] == 3.0


def test_merge_collection_indexes_all_completed_runs(tmp_path: Path) -> None:
    for run_id in ("run_01", "run_02", "run_03"):
        run_dir = tmp_path / run_id
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(
            json.dumps({"git_commit": "abc123", "run_id": run_id}), encoding="utf-8"
        )
    result = merge_collection(tmp_path)
    assert result["run_count"] == 3
    assert result["git_commits"] == ["abc123"]
    assert len(result["runs"]) == 3


def test_merge_run_collects_both_ipc_methods(tmp_path: Path) -> None:
    (tmp_path / "environment.json").write_text(
        json.dumps({"git_commit": "abc123"}), encoding="utf-8"
    )
    for method in ("echo", "memory_retrieve"):
        method_dir = tmp_path / f"ipc_{method}"
        method_dir.mkdir()
        (method_dir / "ipc.summary.json").write_text(
            json.dumps({"method": method, "formal_run": True}), encoding="utf-8"
        )
        (method_dir / "raw").mkdir()
        (method_dir / "raw" / "ipc.jsonl").write_text("{}\n", encoding="utf-8")
    result = merge_run(tmp_path)
    assert set(result["ipc"]["methods"]) == {"echo", "memory_retrieve"}
    artifacts = {path.replace("\\", "/") for path in result["artifacts"]["raw"]}
    assert "ipc_echo/raw/ipc.jsonl" in artifacts


def test_embedding_fake_writes_raw_and_summary(tmp_path: Path) -> None:
    output = tmp_path / "embedding"
    assert embedding_main([
        "--fake", "--texts", "4", "--concurrency", "1", "2", "--warmup", "1",
        "--output-dir", str(output), "--json",
    ]) == 0
    summary = json.loads((output / "embedding.summary.json").read_text(encoding="utf-8"))
    assert summary["formal_run"] is False
    assert set(summary["rounds"]) == {"1", "2"}
    raw = (output / "raw" / "embedding.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(raw) == 8
    assert (output / "raw" / "resources.jsonl").exists()


@pytest.fixture()
def gateway(tmp_path: Path):
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("当前平台不支持 AF_UNIX")
    engine = create_db_engine(str(tmp_path / "gateway.db"))
    init_schema(engine)
    registry = HandlerRegistry()
    register_default_handlers(registry)
    socket_path = str(tmp_path / "gateway.sock")
    server = UDSGatewayServer(socket_path, registry, engine=engine)
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not Path(socket_path).exists():
        time.sleep(0.01)
    if not Path(socket_path).exists():
        server.stop()
        raise RuntimeError("gateway socket not ready")
    yield socket_path
    server.stop()


def test_ipc_uses_real_uds_round_trip(gateway: str, tmp_path: Path) -> None:
    output = tmp_path / "ipc"
    assert ipc_main([
        "--socket", gateway, "--method", "echo", "--requests", "4",
        "--concurrency", "1", "2", "--warmup", "1", "--output-dir", str(output),
    ]) == 0
    summary = json.loads((output / "ipc.summary.json").read_text(encoding="utf-8"))
    assert summary["rounds"]["1"]["errors"] == 0
    assert summary["rounds"]["2"]["errors"] == 0
    assert len((output / "raw" / "ipc.jsonl").read_text(encoding="utf-8").splitlines()) == 8


def test_outbox_stress_drains_real_worker(tmp_path: Path) -> None:
    output = tmp_path / "outbox"
    assert outbox_main([
        "--db", str(tmp_path / "outbox.db"), "--events", "20", "--producer-batch", "5",
        "--consumer-delay-ms", "0.1", "--poll-interval-ms", "5", "--sample-interval-ms", "10",
        "--drain-timeout-s", "5", "--output-dir", str(output),
    ]) == 0
    summary = json.loads((output / "outbox.summary.json").read_text(encoding="utf-8"))
    assert summary["events_submitted"] == 20
    assert summary["events_processed"] == 20
    assert summary["max_backlog"] == 20
    assert summary["dead_letters"] == 0
    assert (output / "raw" / "outbox.jsonl").exists()
