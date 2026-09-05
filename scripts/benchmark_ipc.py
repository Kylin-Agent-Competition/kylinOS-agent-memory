#!/usr/bin/env python3
"""D13A UDS Gateway round-trip benchmark。

计时从 ``sendall`` 前开始，直到收到完整的长度前缀响应结束；不调用 Registry
或 handler。服务端必须由操作者预先启动，避免 benchmark 自己改变服务生命周期。
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import stat
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

_REPO = Path(__file__).resolve().parents[1]
_SERVICE = _REPO / "memory-service"
if str(_SERVICE) not in sys.path:
    sys.path.insert(0, str(_SERVICE))
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from bench_utils import (ResourceSampler, append_jsonl, benchmark_summary,
                          resource_metrics, write_json, write_jsonl)
from gateway import protocol


def resource_sample_identity(pid: Optional[int]) -> dict[str, Any]:
    """声明 CPU/RSS 采样归属，避免由运行命令反推资源数据来源。"""
    return {
        "resource_sample_target": "gateway_service" if pid is not None else "benchmark_client",
        "resource_sample_pid": pid if pid is not None else os.getpid(),
    }


def validate_ipc_service_identity(pid: Optional[int], socket_path: str) -> list[str]:
    """确认 PID 确实持有目标 UDS 的 listening socket。

    ``kill -0`` 只能证明某个 PID 存活，不能证明它是被测 Gateway。Linux
    的 ``/proc/net/unix`` 将路径映射到 socket inode，再与目标进程的 fd
    链接交叉核验；无法完成任一步骤都 fail-closed。
    """
    errors: list[str] = []
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return ["PID 必须为正整数"]
    if not socket_path:
        return ["UDS socket 路径不能为空"]
    socket_file = Path(socket_path)
    try:
        if not stat.S_ISSOCK(socket_file.stat().st_mode):
            errors.append("目标路径不是 UDS socket")
    except OSError as exc:
        errors.append(f"无法读取 UDS socket: {exc}")
    proc_unix = Path("/proc/net/unix")
    proc_fds = Path(f"/proc/{pid}/fd")
    try:
        lines = proc_unix.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [*errors, f"无法读取 /proc/net/unix: {exc}"]
    inode: Optional[str] = None
    for line in lines[1:]:
        fields = line.split()
        # Num RefCount Protocol Flags Type St Inode Path
        if len(fields) >= 8 and fields[5] == "01" and fields[7] == socket_path:
            inode = fields[6]
            break
    if inode is None:
        errors.append("目标 UDS 未在 /proc/net/unix 中登记为 listening socket")
        return errors
    try:
        fd_paths = list(proc_fds.iterdir())
    except OSError as exc:
        return [*errors, f"无法读取目标 PID 的 fd: {exc}"]
    expected = f"socket:[{inode}]"
    for fd_path in fd_paths:
        try:
            if os.readlink(fd_path) == expected:
                return errors
        except OSError:
            continue
    errors.append("PID 未持有目标 UDS listening socket")
    return errors


def _request(socket_path: str, *, method: str, payload: dict[str, Any], request_no: int,
             deadline_ms: int) -> dict[str, Any]:
    request = {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "request_id": f"day13a-{uuid.uuid4().hex}-{request_no}",
        "trace_id": f"day13a-trace-{uuid.uuid4().hex}",
        "method": method,
        "deadline_ms": deadline_ms,
        "payload": payload,
    }
    started = time.monotonic()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(deadline_ms / 1000.0 + 5.0)
            sock.connect(socket_path)
            sock.sendall(protocol.encode(request))
            buf = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    raise ConnectionError("gateway closed before a complete response")
                buf += chunk
                try:
                    response, _ = protocol.decode_packet(buf)
                    break
                except protocol.IncompletePacket:
                    continue
        if (response.get("request_id") != request["request_id"]
                or response.get("trace_id") != request["trace_id"]):
            raise ValueError("gateway response correlation mismatch")
        ok = response.get("status") == "ok"
        error = None if ok else {
            "code": response.get("error_code"),
            "message": str(response.get("message", ""))[:200],
        }
    except Exception as exc:  # noqa: BLE001 - retain transport failures as samples
        ok = False
        error = {"type": type(exc).__name__, "message": str(exc)[:200]}
    row: dict[str, Any] = {
        "request": request_no,
        "concurrency": None,
        "method": method,
        "latency_ms": round((time.monotonic() - started) * 1000.0, 3),
        "ok": ok,
    }
    if error:
        row["error"] = error
    return row


def _run_round(socket_path: str, *, method: str, payload: dict[str, Any], requests: int,
               concurrency: int, deadline_ms: int) -> list[dict[str, Any]]:
    def worker(item: tuple[int, dict[str, Any]]) -> dict[str, Any]:
        request_no, item_payload = item
        row = _request(socket_path, method=method, payload=item_payload,
                       request_no=request_no, deadline_ms=deadline_ms)
        row["concurrency"] = concurrency
        return row

    payloads = []
    for request_no in range(requests):
        request_payload = dict(payload)
        if method == "echo":
            request_payload["request"] = request_no
        elif method == "memory.retrieve":
            request_payload["query"] = f"day13a-ipc-query-{request_no:06d}"
        payloads.append((request_no, request_payload))
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        rows = list(executor.map(worker, payloads))
    return sorted(rows, key=lambda row: int(row["request"]))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="D13A UDS Gateway round-trip benchmark")
    parser.add_argument("--socket", required=True, help="真实 UDS Gateway socket 路径")
    parser.add_argument("--method", choices=("echo", "health", "memory.retrieve"), default="echo")
    parser.add_argument("--payload", default="{}", help="额外 payload JSON object")
    parser.add_argument("--requests", type=int, default=2000)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 4, 8, 16])
    parser.add_argument("--warmup", type=int, default=50)
    parser.add_argument("--deadline-ms", type=int, default=10000)
    parser.add_argument("--pid", type=int,
                        help="可选：要采样的 Gateway 服务 PID；默认采样 benchmark 客户端")
    parser.add_argument("--validate-service-identity", action="store_true",
                        help="只验证 PID 是否持有目标 UDS listening socket")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if (args.requests <= 0 or args.warmup < 0 or args.deadline_ms <= 0
            or args.pid is not None and args.pid <= 0
            or any(c <= 0 for c in args.concurrency)):
        parser.error("requests/concurrency/deadline-ms 必须为正数，warmup 不得为负")
    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as exc:
        parser.error(f"payload 不是合法 JSON: {exc}")
    if not isinstance(payload, dict):
        parser.error("payload 必须是 JSON object")
    if not hasattr(socket, "AF_UNIX"):
        print("当前平台不支持 AF_UNIX，无法执行真实 IPC benchmark", file=sys.stderr)
        return 2
    if not Path(args.socket).exists():
        print(f"UDS socket 不存在：{args.socket}", file=sys.stderr)
        return 2
    if args.validate_service_identity:
        if args.pid is None:
            print("--validate-service-identity 必须同时提供 --pid", file=sys.stderr)
            return 2
        identity_errors = validate_ipc_service_identity(args.pid, args.socket)
        if identity_errors:
            for error in identity_errors:
                print(f"IPC 服务身份校验失败：{error}", file=sys.stderr)
            return 2
        print(json.dumps({
            "socket": args.socket,
            "resource_sample_pid": args.pid,
            "resource_sample_target": "gateway_service",
            "resource_sample_identity_valid": True,
        }, ensure_ascii=False))
        return 0
    identity_errors: list[str] = []
    if args.pid is not None:
        identity_errors = validate_ipc_service_identity(args.pid, args.socket)
        if identity_errors:
            for error in identity_errors:
                print(f"IPC 服务身份校验失败：{error}", file=sys.stderr)
            return 2
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.settimeout(1.0)
            probe.connect(args.socket)
    except OSError as exc:
        print(f"无法连接真实 UDS Gateway：{exc}", file=sys.stderr)
        return 2

    all_rows: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}
    resource_rows: list[dict[str, Any]] = []
    for concurrency in args.concurrency:
        if args.warmup:
            _run_round(args.socket, method=args.method, payload=payload,
                       requests=args.warmup, concurrency=concurrency,
                       deadline_ms=args.deadline_ms)
        sampler = ResourceSampler(pid=args.pid)
        sampler.start()
        started = time.monotonic()
        rows = _run_round(args.socket, method=args.method, payload=payload,
                          requests=args.requests, concurrency=concurrency,
                          deadline_ms=args.deadline_ms)
        wall_seconds = time.monotonic() - started
        resources = sampler.stop()
        resource_rows.extend({**row, "benchmark": "ipc", "concurrency": concurrency}
                             for row in resources)
        successful = [row["latency_ms"] / 1000.0 for row in rows if row["ok"]]
        summaries[str(concurrency)] = benchmark_summary(
            name="ipc", requests=len(rows),
            errors=sum(1 for row in rows if not row["ok"]),
            wall_seconds=wall_seconds, latencies_s=successful,
            resources=resource_metrics(resources), concurrency=concurrency,
            method=args.method,
        )
        all_rows.extend(rows)
        print(
            f"[ipc method={args.method} concurrency={concurrency}] requests={len(rows)} "
            f"errors={summaries[str(concurrency)]['errors']} "
            f"throughput={summaries[str(concurrency)]['throughput_req_s']:.3f} req/s "
            f"P50={summaries[str(concurrency)]['p50_ms']:.3f}ms "
            f"P95={summaries[str(concurrency)]['p95_ms']:.3f}ms "
            f"P99={summaries[str(concurrency)]['p99_ms']:.3f}ms",
            flush=True,
        )

    output = {
        "benchmark": "ipc",
        "formal_run": True,
        # 当前 memory.retrieve handler 返回 empty context；它只说明 Gateway IPC
        # 路径的基线，不可引用为知识检索主链的延迟或比赛 500ms 达标证据。
        "measurement_scope": (
            "gateway_empty_context_ipc_baseline"
            if args.method == "memory.retrieve"
            else "gateway_ipc_round_trip_baseline"
        ),
        "knowledge_retrieval_latency_eligible": False,
        "socket": args.socket,
        "method": args.method,
        "requests": args.requests,
        "warmup": args.warmup,
        "concurrency": args.concurrency,
        "rounds": summaries,
        **resource_sample_identity(args.pid),
        "resource_sample_identity_valid": args.pid is not None and not identity_errors,
    }
    if args.pid is not None:
        identity_errors = validate_ipc_service_identity(args.pid, args.socket)
        if identity_errors:
            output["resource_sample_identity_valid"] = False
            output["resource_sample_identity_errors"] = identity_errors
    if args.output_dir:
        write_jsonl(args.output_dir / "raw" / "ipc.jsonl", all_rows)
        append_jsonl(args.output_dir / "raw" / "resources.jsonl", resource_rows)
        write_json(args.output_dir / "ipc.summary.json", output)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if identity_errors:
        return 2
    return 2 if all_rows and all(not row["ok"] for row in all_rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
