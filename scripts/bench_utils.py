#!/usr/bin/env python3
"""D13A 公共 benchmark 工具。

这里集中处理三件容易漂移的事情：延迟分位数、进程资源采样和运行环境快照。
脚本只写运行目录，不修改业务数据库；真实 SDK/VM 的结果由调用者显式提供。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence


_REQUIRED_EMBEDDING_CONCURRENCY = (1, 4, 8)
_REQUIRED_IPC_CONCURRENCY = (1, 4, 8, 16)
_SDK_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


def percentile(values: Iterable[float], fraction: float) -> float:
    """返回 nearest-rank 分位数；空输入返回 ``0.0``。"""
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be between 0 and 1")
    # nearest-rank: rank = ceil(p * n)，再换算成从 0 开始的下标。
    # 对 p=0 保持首项语义，避免 rank=0 导致负下标。
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path | str, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path | str, rows: Iterable[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def append_jsonl(path: Path | str, rows: Iterable[Mapping[str, Any]]) -> None:
    """追加 JSONL，供多个 benchmark 共享 ``raw/resources.jsonl``。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def read_json(path: Path | str, default: Any = None) -> Any:
    target = Path(path)
    if not target.exists():
        return default
    return json.loads(target.read_text(encoding="utf-8"))


def _read_proc_status_rss_mb(pid: int) -> Optional[float]:
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2:
                return float(parts[1]) / 1024.0
    return None


def _read_proc_cpu_seconds(pid: int) -> Optional[float]:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    # comm may contain spaces and parentheses; the fields after the final ')'
    # have the stable layout required here (utime=14, stime=15).
    try:
        fields = stat[stat.rfind(")") + 2 :].split()
        ticks = os.sysconf("SC_CLK_TCK")
        return (int(fields[11]) + int(fields[12])) / float(ticks)
    except (IndexError, ValueError, OSError):
        return None


def _rss_mb(pid: int) -> Optional[float]:
    rss = _read_proc_status_rss_mb(pid)
    if rss is not None:
        return rss
    try:
        import psutil  # type: ignore

        return float(psutil.Process(pid).memory_info().rss) / (1024.0 * 1024.0)
    except (ImportError, OSError, ValueError):
        return None


class ResourceSampler:
    """以固定周期采样当前进程（或指定 pid）的 RSS 和 CPU。"""

    def __init__(self, *, pid: Optional[int] = None, interval_s: float = 0.1) -> None:
        if interval_s <= 0:
            raise ValueError("interval_s must be positive")
        self.pid = pid or os.getpid()
        self.interval_s = interval_s
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._previous_cpu: Optional[float] = None
        self._previous_time: Optional[float] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._sample()
        self._thread = threading.Thread(target=self._run, name="day13a-resource-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> list[dict[str, Any]]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_s * 4))
        self._sample()
        return list(self.samples)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_s):
            self._sample()

    def _sample(self) -> None:
        now = time.monotonic()
        cpu_seconds = _read_proc_cpu_seconds(self.pid)
        cpu_percent: Optional[float] = None
        if cpu_seconds is not None and self._previous_cpu is not None and self._previous_time is not None:
            elapsed = now - self._previous_time
            if elapsed > 0:
                cpu_percent = max(0.0, (cpu_seconds - self._previous_cpu) / elapsed * 100.0)
        self._previous_cpu = cpu_seconds
        self._previous_time = now
        self.samples.append({
            "timestamp": utc_now(),
            "elapsed_monotonic_s": now,
            "rss_mb": _rss_mb(self.pid),
            "cpu_percent": cpu_percent,
        })


def resource_metrics(samples: Sequence[Mapping[str, Any]]) -> dict[str, Optional[float]]:
    rss = [float(row["rss_mb"]) for row in samples if row.get("rss_mb") is not None]
    cpu = [float(row["cpu_percent"]) for row in samples if row.get("cpu_percent") is not None]
    return {
        "rss_start_mb": round(rss[0], 3) if rss else None,
        "rss_peak_mb": round(max(rss), 3) if rss else None,
        "rss_end_mb": round(rss[-1], 3) if rss else None,
        "cpu_avg_percent": round(statistics.fmean(cpu), 3) if cpu else None,
        "cpu_peak_percent": round(max(cpu), 3) if cpu else None,
    }


def _command(
    command: Sequence[str],
    cwd: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command), cwd=cwd, env=dict(env) if env is not None else None,
            check=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        return {
            "command": list(command),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except OSError as exc:
        return {"command": list(command), "returncode": None, "stdout": "", "stderr": str(exc)}


def _command_output(command: Mapping[str, Any] | Any) -> str:
    return str(command.get("stdout", "")).strip() if isinstance(command, Mapping) else ""


def _command_succeeded(command: Mapping[str, Any] | Any) -> bool:
    return isinstance(command, Mapping) and command.get("returncode") == 0


def _file_sha256(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    target = Path(path)
    if not target.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with target.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _shared_object_soname(path: Optional[str]) -> Optional[str]:
    if not path or not Path(path).is_file():
        return None
    output = _command(["readelf", "-d", path])
    if output.get("returncode") != 0:
        return None
    for line in _command_output(output).splitlines():
        if "SONAME" in line and "[" in line and "]" in line:
            return line.split("[", 1)[1].split("]", 1)[0]
    return None


def _linux_memory_total_mb() -> Optional[float]:
    try:
        text = Path("/proc/meminfo").read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            return round(float(parts[1]) / 1024.0, 3)
    return None


def _cpu_details(lscpu_output: str) -> tuple[Optional[str], Optional[int]]:
    values: dict[str, str] = {}
    for line in lscpu_output.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    model = values.get("Model name") or values.get("Model")
    try:
        sockets = int(values.get("Socket(s)", "1"))
        cores_per_socket = int(values.get("Core(s) per socket", "0"))
        physical = sockets * cores_per_socket if cores_per_socket else None
    except ValueError:
        physical = None
    return model, physical


def formal_sdk_environment_errors(environment: Mapping[str, Any]) -> list[str]:
    """返回使 SDK 二进制身份不可复现的缺陷。

    收集端在 VM 上通过实际文件计算 hash；汇总端只验证被捕获的、可复算的
    身份字段，避免离线复审时错误地依赖本机路径是否存在。
    """
    errors: list[str] = []
    sdk_path = environment.get("embedding_sdk_so_path")
    if not isinstance(sdk_path, str) or not sdk_path:
        errors.append("embedding_sdk_so_path 缺失或不可验证")
    if environment.get("embedding_sdk_so_is_file") is not True:
        errors.append("embedding_sdk_so_path 未确认是常规文件")
    sdk_hash = environment.get("embedding_sdk_so_sha256")
    if not isinstance(sdk_hash, str) or not _SDK_SHA256_RE.fullmatch(sdk_hash):
        errors.append("embedding_sdk_so_sha256 缺失或格式非法")
    model_version = environment.get("embedding_model_version")
    model_hash = environment.get("embedding_model_sha256")
    if not isinstance(model_version, str) or not model_version:
        if not isinstance(model_hash, str) or not _SDK_SHA256_RE.fullmatch(model_hash):
            errors.append("embedding_model_version 或 embedding_model_sha256 必须可验证")
    return errors


def formal_environment_errors(
    environment: Mapping[str, Any],
    *,
    expected_commit: Optional[str] = None,
    expected_branch: Optional[str] = None,
) -> list[str]:
    """返回使一次 D13A 正式运行不可复现的 Git/SDK 身份缺陷。

    Git 命令失败时不能把 unknown 归约为 clean；该函数同时供 runner 与
    collection 汇总使用，保证两处都是 fail-closed。
    """
    errors: list[str] = []
    commit = environment.get("git_commit")
    branch = environment.get("git_branch")
    commands = environment.get("commands")
    commands = commands if isinstance(commands, Mapping) else {}
    if not isinstance(commit, str) or not commit:
        errors.append("git_commit 缺失或不可验证")
    if not isinstance(branch, str) or not branch:
        errors.append("git_branch 缺失或不可验证")
    if environment.get("git_dirty") is not False:
        errors.append("git_dirty 不是已验证的 clean 状态")
    if not isinstance(expected_commit, str) or not expected_commit:
        errors.append("expected_git_commit 缺失或不可验证")
    if not isinstance(expected_branch, str) or not expected_branch:
        errors.append("expected_git_branch 缺失或不可验证")
    if not _command_succeeded(commands.get("git_rev_parse_HEAD")):
        errors.append("git rev-parse HEAD 失败")
    if not _command_succeeded(commands.get("git_status_porcelain")):
        errors.append("git status --porcelain 失败")
    if isinstance(expected_commit, str) and expected_commit and commit != expected_commit:
        errors.append("git_commit 与预期 commit 不一致")
    if isinstance(expected_branch, str) and expected_branch and branch != expected_branch:
        errors.append("git_branch 与预期 branch 不一致")
    errors.extend(formal_sdk_environment_errors(environment))
    return errors


def environment_snapshot(repo_root: Path | str) -> dict[str, Any]:
    """收集可复现所需的代码、系统、Python 和 SDK 线索。"""
    root = Path(repo_root).resolve()
    sdk_version = os.environ.get("KYLIN_EMBEDDING_SDK_VERSION")
    runtime_version = os.environ.get("KYLIN_EMBEDDING_RUNTIME_VERSION")
    try:
        import importlib.metadata

        sdk_version = sdk_version or importlib.metadata.version("kylin-embedding")
    except Exception:
        pass
    try:
        import kylin_embedding  # type: ignore

        runtime_version = runtime_version or str(getattr(kylin_embedding, "__version__", "")) or None
    except Exception:
        pass

    sdk_so_path = os.environ.get("KYLIN_EMBEDDING_SDK_SO_PATH") or os.environ.get("DAY13A_SDK_SO")
    sdk_so_soname = _shared_object_soname(sdk_so_path)
    # 某些麒麟 SDK 没有 Python package metadata；SONAME 仍是可比较的版本线索。
    sdk_version = sdk_version or sdk_so_soname
    runtime_version = runtime_version or sdk_so_soname
    uname = _command(["uname", "-a"])
    locale_env = dict(os.environ)
    locale_env["LC_ALL"] = "C"
    locale_env["LANG"] = "C"
    lscpu = _command(["lscpu"], env=locale_env)
    free = _command(["free", "-m"])
    git_head = _command(["git", "rev-parse", "HEAD"], cwd=root)
    git_branch = _command(["git", "branch", "--show-current"], cwd=root)
    git_status = _command(["git", "status", "--porcelain"], cwd=root)
    cpu_model, physical_cores = _cpu_details(lscpu["stdout"])
    return {
        "captured_at": utc_now(),
        "git_commit": _command_output(git_head) if _command_succeeded(git_head) else None,
        "git_branch": _command_output(git_branch) if _command_succeeded(git_branch) else None,
        "git_dirty": bool(_command_output(git_status)) if _command_succeeded(git_status) else None,
        "hostname": platform.node(),
        "os_name": platform.system(),
        "os_version": platform.version(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "cpu_model": cpu_model or platform.processor() or None,
        "physical_cores": physical_cores,
        "logical_cores": os.cpu_count(),
        "memory_total_mb": _linux_memory_total_mb(),
        "python_version": platform.python_version(),
        "embedding_sdk_version": sdk_version,
        "embedding_runtime_version": runtime_version,
        "embedding_sdk_so_path": sdk_so_path,
        "embedding_sdk_so_is_file": bool(sdk_so_path and Path(sdk_so_path).is_file()),
        "embedding_sdk_so_sha256": _file_sha256(sdk_so_path),
        "embedding_sdk_so_soname": sdk_so_soname,
        "embedding_model_version": os.environ.get("KYLIN_EMBEDDING_MODEL_VERSION") or None,
        "embedding_model_sha256": os.environ.get("KYLIN_EMBEDDING_MODEL_SHA256") or None,
        "bridge_build_type": os.environ.get("KYLIN_EMBEDDING_BUILD_TYPE", "Release"),
        "commands": {
            "git_rev_parse_HEAD": git_head,
            "git_branch_show_current": git_branch,
            "git_status_porcelain": git_status,
            "uname_a": uname,
            "lscpu": lscpu,
            "free_m": free,
            "python_version": _command([sys.executable, "--version"]),
        },
    }


def benchmark_summary(
    *,
    name: str,
    requests: int,
    errors: int,
    wall_seconds: float,
    latencies_s: Iterable[float],
    resources: Mapping[str, Any],
    **extra: Any,
) -> dict[str, Any]:
    latencies = list(latencies_s)
    if requests < 0 or errors < 0 or errors > requests:
        raise ValueError("requests/errors 必须满足 0 <= errors <= requests")
    successful_requests = requests - errors
    attempt_rate = requests / wall_seconds if wall_seconds > 0 else 0.0
    success_throughput = successful_requests / wall_seconds if wall_seconds > 0 else 0.0
    result: dict[str, Any] = {
        "benchmark": name,
        "requests": requests,
        "successful_requests": successful_requests,
        "errors": errors,
        "wall_seconds": round(wall_seconds, 6),
        "attempt_rate_req_s": round(attempt_rate, 3),
        "success_throughput_req_s": round(success_throughput, 3),
        "throughput_req_s": round(success_throughput, 3),
        "throughput_semantics": "successful_requests_per_wall_second",
        "success_rate": round(successful_requests / requests, 6) if requests else 0.0,
        "error_rate": round(errors / requests, 6) if requests else 0.0,
        "p50_ms": round(percentile(latencies, 0.50) * 1000.0, 3),
        "p95_ms": round(percentile(latencies, 0.95) * 1000.0, 3),
        "p99_ms": round(percentile(latencies, 0.99) * 1000.0, 3),
        **dict(resources),
        **extra,
    }
    return result


def _round_completeness_errors(
    summary: Any,
    *,
    label: str,
    required_concurrency: Sequence[int],
) -> list[str]:
    if not isinstance(summary, Mapping):
        return [f"{label} 缺失"]
    if summary.get("formal_run") is not True:
        return [f"{label}.formal_run 不是 true"]
    rounds = summary.get("rounds")
    if not isinstance(rounds, Mapping):
        return [f"{label}.rounds 缺失"]
    errors: list[str] = []
    required_metrics = (
        "requests", "p50_ms", "p95_ms", "p99_ms",
        "success_throughput_req_s", "success_rate", "error_rate",
    )
    for concurrency in required_concurrency:
        round_summary = rounds.get(str(concurrency))
        if not isinstance(round_summary, Mapping):
            errors.append(f"{label} 缺少并发档位 {concurrency}")
            continue
        requests = round_summary.get("requests")
        if not isinstance(requests, int) or isinstance(requests, bool) or requests <= 0:
            errors.append(f"{label} 并发档位 {concurrency} requests 非正整数")
        for metric in required_metrics[1:]:
            value = round_summary.get(metric)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"{label} 并发档位 {concurrency} 缺少指标 {metric}")
    return errors


def validate_run_completeness(
    summary: Mapping[str, Any],
    *,
    mode: str = "full",
    expected_commit: Optional[str] = None,
    expected_branch: Optional[str] = None,
) -> list[str]:
    """验证一次 D13A 运行是否具备指定模式的完整证据。

    ``partial`` 仍要求所有非索引核心 benchmark 与环境身份，只允许真实索引
    积压尚未测量；``full`` 额外要求真实索引积压已测量。
    """
    if mode not in {"partial", "full"}:
        raise ValueError("mode 必须为 partial 或 full")
    errors: list[str] = []
    environment = summary.get("environment")
    environment = environment if isinstance(environment, Mapping) else {}
    errors.extend(
        f"environment: {error}"
        for error in formal_environment_errors(
            environment,
            expected_commit=expected_commit,
            expected_branch=expected_branch,
        )
    )
    if summary.get("git_commit") != environment.get("git_commit"):
        errors.append("summary.git_commit 与 environment.git_commit 不一致")
    errors.extend(_round_completeness_errors(
        summary.get("embedding"),
        label="embedding",
        required_concurrency=_REQUIRED_EMBEDDING_CONCURRENCY,
    ))
    errors.extend(_round_completeness_errors(
        summary.get("bridge"),
        label="bridge",
        required_concurrency=_REQUIRED_EMBEDDING_CONCURRENCY,
    ))

    ipc = summary.get("ipc")
    ipc = ipc if isinstance(ipc, Mapping) else {}
    methods = ipc.get("methods")
    methods = methods if isinstance(methods, Mapping) else {}
    echo = methods.get("echo")
    memory_retrieve = methods.get("memory_retrieve")
    errors.extend(_round_completeness_errors(
        echo, label="ipc.echo", required_concurrency=_REQUIRED_IPC_CONCURRENCY,
    ))
    if isinstance(echo, Mapping) and echo.get("measurement_scope") != "gateway_ipc_round_trip_baseline":
        errors.append("ipc.echo measurement_scope 不正确")
    errors.extend(_round_completeness_errors(
        memory_retrieve,
        label="ipc.memory_retrieve",
        required_concurrency=_REQUIRED_IPC_CONCURRENCY,
    ))
    if isinstance(memory_retrieve, Mapping):
        if memory_retrieve.get("measurement_scope") != "gateway_empty_context_ipc_baseline":
            errors.append("ipc.memory_retrieve measurement_scope 不正确")
        if memory_retrieve.get("knowledge_retrieval_latency_eligible") is not False:
            errors.append("ipc.memory_retrieve 必须明确不可作为知识检索延迟")

    outbox = summary.get("outbox")
    if not isinstance(outbox, Mapping):
        errors.append("outbox 缺失")
    else:
        if outbox.get("formal_run") is not True:
            errors.append("outbox.formal_run 不是 true")
        if outbox.get("measurement_scope") != "outbox_queue_backlog_drain":
            errors.append("outbox measurement_scope 不正确")
        submitted = outbox.get("events_submitted")
        if not isinstance(submitted, int) or isinstance(submitted, bool) or submitted <= 0:
            errors.append("outbox.events_submitted 非正整数")
        for field in ("events_processed", "dead_letters"):
            value = outbox.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"outbox.{field} 缺失或非法")
        index_measurement = outbox.get("index_backlog_measurement")
        if mode == "full" and (
            not isinstance(index_measurement, Mapping)
            or index_measurement.get("status") != "measured"
        ):
            errors.append("未测量真实索引积压")
    return errors


def merge_run(
    run_dir: Path | str,
    *,
    mode: str = "full",
    expected_commit: Optional[str] = None,
    expected_branch: Optional[str] = None,
) -> dict[str, Any]:
    root = Path(run_dir)
    environment = read_json(root / "environment.json", {})
    ipc = read_json(root / "ipc.summary.json")
    method_runs = {
        path.parent.name.removeprefix("ipc_"): summary
        for path in sorted(root.glob("ipc_*/ipc.summary.json"))
        if (summary := read_json(path)) is not None
    }
    if method_runs:
        ipc = {"benchmark": "ipc", "formal_run": True, "methods": method_runs}
    if ipc is None:
        ipc = {"status": "not_run"}
    outbox = read_json(root / "outbox.summary.json", {"status": "not_run"})
    result: dict[str, Any] = {
        "schema_version": "day13a.v1",
        "generated_at": utc_now(),
        "git_commit": environment.get("git_commit"),
        "environment": environment,
        "embedding": read_json(root / "embedding.summary.json", {"status": "not_run"}),
        "bridge": read_json(root / "bridge.summary.json", {"status": "not_run"}),
        "ipc": ipc,
        "outbox": outbox,
        "artifacts": {
            "raw": sorted(str(path.relative_to(root)) for path in root.rglob("*.jsonl")),
        },
    }
    run_blockers = validate_run_completeness(
        result,
        mode=mode,
        expected_commit=expected_commit,
        expected_branch=expected_branch,
    )
    result["baseline_mode"] = mode
    result["expected_git_commit"] = expected_commit
    result["expected_git_branch"] = expected_branch
    result["formal_run_eligible"] = not run_blockers and mode == "full"
    result["run_complete"] = not run_blockers
    result["formal_run_blockers"] = run_blockers
    write_json(root / "summary.json", result)
    return result


def merge_collection(
    collection_dir: Path | str,
    *,
    mode: str = "full",
    expected_commit: Optional[str] = None,
    expected_branch: Optional[str] = None,
) -> dict[str, Any]:
    """汇总 ``run_01``…``run_N``，形成 D13A 根目录单一索引。"""
    root = Path(collection_dir)
    runs: list[dict[str, Any]] = []
    for run_dir in sorted(path for path in root.glob("run_*") if path.is_dir()):
        summary = read_json(run_dir / "summary.json")
        if summary is not None:
            runs.append({"run_id": run_dir.name, "summary": summary})
    commits = sorted({
        str(item["summary"].get("git_commit"))
        for item in runs
        if item["summary"].get("git_commit")
    })
    blockers: list[str] = []
    if len(runs) < 3:
        blockers.append("正式基线必须至少包含 3 轮运行")
    for item in runs:
        run_id = item["run_id"]
        summary = item["summary"]
        blockers.extend(
            f"{run_id}: {error}"
            for error in validate_run_completeness(
                summary,
                mode=mode,
                expected_commit=expected_commit,
                expected_branch=expected_branch,
            )
        )
    if len(commits) != 1:
        blockers.append("全部运行必须绑定唯一、非空的 Git commit")
    collection_complete = not blockers
    result = {
        "schema_version": "day13a.collection.v1",
        "generated_at": utc_now(),
        "run_count": len(runs),
        "git_commits": commits,
        "baseline_mode": mode,
        "expected_git_commit": expected_commit,
        "expected_git_branch": expected_branch,
        "collection_complete": collection_complete,
        "collection_status": (
            "complete" if mode == "full" and collection_complete
            else "partial" if mode == "partial" and collection_complete
            else "incomplete"
        ),
        "formal_baseline_complete": mode == "full" and collection_complete,
        "formal_baseline_blockers": blockers,
        "runs": runs,
    }
    write_json(root / "summary.json", result)
    return result


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="D13A environment/summary helper")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--merge-run", type=Path)
    parser.add_argument("--merge-collection", type=Path)
    parser.add_argument("--validate-formal-environment", type=Path)
    parser.add_argument("--mode", choices=("partial", "full"), default="full")
    parser.add_argument("--expected-commit")
    parser.add_argument("--expected-branch")
    args = parser.parse_args(argv)
    if args.merge_collection is not None:
        result = merge_collection(
            args.merge_collection,
            mode=args.mode,
            expected_commit=args.expected_commit,
            expected_branch=args.expected_branch,
        )
        if not result["collection_complete"]:
            print(json.dumps({
                "collection_complete": False,
                "formal_baseline_complete": result["formal_baseline_complete"],
                "blockers": result["formal_baseline_blockers"],
            }, ensure_ascii=False), file=sys.stderr)
            return 2
        return 0
    if args.merge_run is not None:
        result = merge_run(
            args.merge_run,
            mode=args.mode,
            expected_commit=args.expected_commit,
            expected_branch=args.expected_branch,
        )
        if not result["run_complete"]:
            print(json.dumps({
                "run_complete": False,
                "formal_run_eligible": result["formal_run_eligible"],
                "blockers": result["formal_run_blockers"],
            }, ensure_ascii=False), file=sys.stderr)
            return 2
        return 0
    if args.validate_formal_environment is not None:
        errors = formal_environment_errors(
            read_json(args.validate_formal_environment, {}),
            expected_commit=args.expected_commit,
            expected_branch=args.expected_branch,
        )
        if errors:
            print(json.dumps({"formal_environment_valid": False, "blockers": errors}, ensure_ascii=False), file=sys.stderr)
            return 2
        return 0
    if args.output is None:
        parser.error("--output is required unless --merge-run is used")
    snapshot = environment_snapshot(args.repo_root)
    snapshot["expected_git_commit"] = args.expected_commit
    snapshot["expected_git_branch"] = args.expected_branch
    write_json(args.output, snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
