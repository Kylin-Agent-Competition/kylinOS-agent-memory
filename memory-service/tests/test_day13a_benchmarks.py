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

from bench_utils import (  # noqa: E402
    benchmark_summary,
    formal_environment_errors,
    merge_collection,
    merge_run,
    percentile,
    validate_run_completeness,
)
from benchmark_embedding import main as embedding_main  # noqa: E402
from benchmark_ipc import main as ipc_main  # noqa: E402
from benchmark_outbox import main as outbox_main  # noqa: E402
from db.engine import create_db_engine, init_schema  # noqa: E402
from gateway.handlers import register_default_handlers  # noqa: E402
from gateway.registry import HandlerRegistry  # noqa: E402
from gateway.server import UDSGatewayServer  # noqa: E402


def _formal_environment(*, commit: str = "abc123") -> dict:
    return {
        "git_commit": commit,
        "git_branch": "perf/D13A-baseline-load",
        "git_dirty": False,
        "embedding_sdk_so_path": "/usr/lib/libkysdk-coreai-embedding.so.1.0.0",
        "embedding_sdk_so_is_file": True,
        "embedding_sdk_so_sha256": "a" * 64,
        "embedding_model_version": "ensemble-embd_gte-base_uint8-text",
        "commands": {
            "git_rev_parse_HEAD": {"returncode": 0},
            "git_status_porcelain": {"returncode": 0},
        },
    }


def _rounds(concurrency: tuple[int, ...]) -> dict:
    return {
        str(level): {
            "requests": 1,
            "p50_ms": 1.0,
            "p95_ms": 1.0,
            "p99_ms": 1.0,
            "success_throughput_req_s": 1.0,
            "success_rate": 1.0,
            "error_rate": 0.0,
        }
        for level in concurrency
    }


def _complete_run(*, index_status: str = "measured") -> dict:
    return {
        "git_commit": "abc123",
        "environment": _formal_environment(),
        "embedding": {"formal_run": True, "rounds": _rounds((1, 4, 8))},
        "bridge": {"formal_run": True, "rounds": _rounds((1, 4, 8))},
        "ipc": {
            "formal_run": True,
            "methods": {
                "echo": {
                    "formal_run": True,
                    "measurement_scope": "gateway_ipc_round_trip_baseline",
                    "rounds": _rounds((1, 4, 8, 16)),
                },
                "memory_retrieve": {
                    "formal_run": True,
                    "measurement_scope": "gateway_empty_context_ipc_baseline",
                    "knowledge_retrieval_latency_eligible": False,
                    "rounds": _rounds((1, 4, 8, 16)),
                },
            },
        },
        "outbox": {
            "formal_run": True,
            "measurement_scope": "outbox_queue_backlog_drain",
            "events_submitted": 1,
            "events_processed": 1,
            "dead_letters": 0,
            "index_backlog_measurement": {"status": index_status},
        },
    }


def test_percentile_and_summary_distinguish_attempts_from_successes() -> None:
    assert percentile([1, 2, 3, 4], 0.50) == 2.0
    summary = benchmark_summary(
        name="test", requests=3, errors=1, wall_seconds=1.0,
        latencies_s=[0.001, 0.002], resources={},
    )
    assert summary["p50_ms"] == 1.0
    assert summary["attempt_rate_req_s"] == 3.0
    assert summary["success_throughput_req_s"] == 2.0
    assert summary["throughput_req_s"] == 2.0
    assert summary["success_rate"] == pytest.approx(2 / 3)
    assert summary["error_rate"] == pytest.approx(1 / 3)


def test_formal_environment_requires_verifiable_clean_git_state() -> None:
    assert formal_environment_errors(
        _formal_environment(),
        expected_commit="abc123",
        expected_branch="perf/D13A-baseline-load",
    ) == []
    errors = formal_environment_errors({
        **_formal_environment(),
        "git_commit": None,
        "git_branch": None,
        "git_dirty": None,
        "commands": {
            "git_rev_parse_HEAD": {"returncode": 128},
            "git_status_porcelain": {"returncode": 128},
        },
    }, expected_commit="abc123", expected_branch="perf/D13A-baseline-load")
    assert "git_commit 缺失或不可验证" in errors
    assert "git_branch 缺失或不可验证" in errors
    assert "git_dirty 不是已验证的 clean 状态" in errors
    assert "git rev-parse HEAD 失败" in errors
    assert "git status --porcelain 失败" in errors


def test_formal_environment_requires_frozen_expected_identity() -> None:
    assert "expected_git_commit 缺失或不可验证" in formal_environment_errors(
        _formal_environment(), expected_branch="perf/D13A-baseline-load"
    )
    assert "expected_git_branch 缺失或不可验证" in formal_environment_errors(
        _formal_environment(), expected_commit="abc123"
    )


def test_formal_environment_binds_expected_identity_and_sdk_provenance() -> None:
    environment = _formal_environment()
    assert formal_environment_errors(
        environment,
        expected_commit="abc123",
        expected_branch="perf/D13A-baseline-load",
    ) == []

    errors = formal_environment_errors(
        {**environment, "embedding_sdk_so_sha256": None},
        expected_commit="different",
        expected_branch="main",
    )
    assert "git_commit 与预期 commit 不一致" in errors
    assert "git_branch 与预期 branch 不一致" in errors
    assert "embedding_sdk_so_sha256 缺失或格式非法" in errors


@pytest.mark.parametrize(
    ("mutate", "expected_error"),
    [
        (lambda summary: summary.pop("embedding"), "embedding 缺失"),
        (lambda summary: summary.pop("bridge"), "bridge 缺失"),
        (lambda summary: summary["ipc"]["methods"].pop("echo"), "ipc.echo 缺失"),
        (
            lambda summary: summary["ipc"]["methods"]["memory_retrieve"].pop(
                "knowledge_retrieval_latency_eligible"
            ),
            "ipc.memory_retrieve 必须明确不可作为知识检索延迟",
        ),
        (
            lambda summary: summary["embedding"]["rounds"].pop("8"),
            "embedding 缺少并发档位 8",
        ),
        (lambda summary: summary.pop("outbox"), "outbox 缺失"),
        (
            lambda summary: summary["outbox"].update(
                {"index_backlog_measurement": {"status": "not_measured"}}
            ),
            "未测量真实索引积压",
        ),
    ],
)
def test_full_run_requires_each_core_benchmark(
    mutate, expected_error: str
) -> None:
    summary = _complete_run()
    mutate(summary)
    assert expected_error in validate_run_completeness(summary, mode="full")


def test_partial_run_can_be_complete_without_real_index_measurement() -> None:
    assert validate_run_completeness(
        _complete_run(index_status="not_measured"),
        mode="partial",
        expected_commit="abc123",
        expected_branch="perf/D13A-baseline-load",
    ) == []


def test_merge_collection_indexes_all_completed_runs(tmp_path: Path) -> None:
    for run_id in ("run_01", "run_02", "run_03"):
        run_dir = tmp_path / run_id
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(
            json.dumps({**_complete_run(), "run_id": run_id}), encoding="utf-8"
        )
    result = merge_collection(
        tmp_path,
        expected_commit="abc123",
        expected_branch="perf/D13A-baseline-load",
    )
    assert result["run_count"] == 3
    assert result["git_commits"] == ["abc123"]
    assert len(result["runs"]) == 3
    assert result["formal_baseline_complete"] is True


def test_merge_collection_reports_partial_completion_separately(tmp_path: Path) -> None:
    for run_id in ("run_01", "run_02", "run_03"):
        run_dir = tmp_path / run_id
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(
            json.dumps({**_complete_run(index_status="not_measured"), "run_id": run_id}),
            encoding="utf-8",
        )
    result = merge_collection(
        tmp_path,
        mode="partial",
        expected_commit="abc123",
        expected_branch="perf/D13A-baseline-load",
    )
    assert result["collection_complete"] is True
    assert result["formal_baseline_complete"] is False
    assert result["collection_status"] == "partial"


def test_merge_collection_marks_unverifiable_or_non_index_runs_incomplete(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_01"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps({
            "git_commit": None,
            "environment": {
                "git_commit": None,
                "git_branch": None,
                "git_dirty": None,
                "commands": {
                    "git_rev_parse_HEAD": {"returncode": 128},
                    "git_status_porcelain": {"returncode": 128},
                },
            },
            "outbox": {"index_backlog_measurement": {"status": "not_measured"}},
        }), encoding="utf-8"
    )
    result = merge_collection(tmp_path)
    assert result["formal_baseline_complete"] is False
    assert "正式基线必须至少包含 3 轮运行" in result["formal_baseline_blockers"]
    assert "run_01: environment: git_commit 缺失或不可验证" in result["formal_baseline_blockers"]
    assert "run_01: embedding 缺失" in result["formal_baseline_blockers"]
    assert "run_01: 未测量真实索引积压" in result["formal_baseline_blockers"]
    assert "全部运行必须绑定唯一、非空的 Git commit" in result["formal_baseline_blockers"]


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
    assert result["formal_run_eligible"] is False
    assert "未测量真实索引积压" in result["formal_run_blockers"]
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
    assert summary["measurement_scope"] == "gateway_ipc_round_trip_baseline"
    assert summary["knowledge_retrieval_latency_eligible"] is False
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
    assert summary["measurement_scope"] == "outbox_queue_backlog_drain"
    assert summary["index_backlog_measurement"]["status"] == "not_measured"
    assert (output / "raw" / "outbox.jsonl").exists()
