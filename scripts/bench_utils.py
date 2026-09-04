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
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence


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


def formal_environment_errors(environment: Mapping[str, Any]) -> list[str]:
    """返回使一次 D13A 正式运行不可复现的 Git 溯源缺陷。

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
    if not _command_succeeded(commands.get("git_rev_parse_HEAD")):
        errors.append("git rev-parse HEAD 失败")
    if not _command_succeeded(commands.get("git_status_porcelain")):
        errors.append("git status --porcelain 失败")
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
        "embedding_sdk_so_sha256": _file_sha256(sdk_so_path),
        "embedding_sdk_so_soname": sdk_so_soname,
        "embedding_model_version": os.environ.get("KYLIN_EMBEDDING_MODEL_VERSION") or None,
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


def merge_run(run_dir: Path | str) -> dict[str, Any]:
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
    run_blockers = formal_environment_errors(environment)
    outbox = read_json(root / "outbox.summary.json", {"status": "not_run"})
    index_measurement = outbox.get("index_backlog_measurement") if isinstance(outbox, Mapping) else None
    if not isinstance(index_measurement, Mapping) or index_measurement.get("status") != "measured":
        run_blockers.append("未测量真实索引积压")
    result: dict[str, Any] = {
        "schema_version": "day13a.v1",
        "generated_at": utc_now(),
        "git_commit": environment.get("git_commit"),
        "formal_run_eligible": not run_blockers,
        "formal_run_blockers": run_blockers,
        "environment": environment,
        "embedding": read_json(root / "embedding.summary.json", {"status": "not_run"}),
        "bridge": read_json(root / "bridge.summary.json", {"status": "not_run"}),
        "ipc": ipc,
        "outbox": outbox,
        "artifacts": {
            "raw": sorted(str(path.relative_to(root)) for path in root.rglob("*.jsonl")),
        },
    }
    write_json(root / "summary.json", result)
    return result


def merge_collection(collection_dir: Path | str) -> dict[str, Any]:
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
        environment = summary.get("environment")
        environment = environment if isinstance(environment, Mapping) else {}
        blockers.extend(f"{run_id}: {error}" for error in formal_environment_errors(environment))
        outbox = summary.get("outbox")
        index_measurement = outbox.get("index_backlog_measurement") if isinstance(outbox, Mapping) else None
        if not isinstance(index_measurement, Mapping) or index_measurement.get("status") != "measured":
            blockers.append(f"{run_id}: 未测量真实索引积压")
    if len(commits) != 1:
        blockers.append("全部运行必须绑定唯一、非空的 Git commit")
    result = {
        "schema_version": "day13a.collection.v1",
        "generated_at": utc_now(),
        "run_count": len(runs),
        "git_commits": commits,
        "formal_baseline_complete": not blockers,
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
    args = parser.parse_args(argv)
    if args.merge_collection is not None:
        result = merge_collection(args.merge_collection)
        if not result["formal_baseline_complete"]:
            print(json.dumps({
                "formal_baseline_complete": False,
                "blockers": result["formal_baseline_blockers"],
            }, ensure_ascii=False), file=sys.stderr)
            return 2
        return 0
    if args.merge_run is not None:
        merge_run(args.merge_run)
        return 0
    if args.validate_formal_environment is not None:
        errors = formal_environment_errors(read_json(args.validate_formal_environment, {}))
        if errors:
            print(json.dumps({"formal_environment_valid": False, "blockers": errors}, ensure_ascii=False), file=sys.stderr)
            return 2
        return 0
    if args.output is None:
        parser.error("--output is required unless --merge-run is used")
    write_json(args.output, environment_snapshot(args.repo_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
