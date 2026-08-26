#!/usr/bin/env python3
"""
Kylin Memory Echo Server — UDS 最小验证服务端
================================================
监听 /tmp/kylin-memory-echo/echo.sock ，实现长度前缀JSON协议。
支持 method 路由: echo / health / memory.retrieve

用途: Gate 0 验证 Kaiming 进程可通过 UDS 与自定义 Memory Service 通信
协议: 4字节 Big-Endian 长度 + UTF-8 JSON 负载
架构: 单连接阻塞式 (Gate 0 Spike)，accept() 后处理一个客户端即退出 accept 循环
"""

import argparse
import json
import os
import signal
import socket
import struct
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

# ---- Logging (must be defined before config to avoid forward reference) ----
def log(level: str, msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    print(f"[{ts}] [{level}] {msg}", file=sys.stderr, flush=True)

# ---- Argument Parsing ----
parser = argparse.ArgumentParser(description="Kylin Memory Echo Server")
parser.add_argument("--socket", type=str, default=None, help="Override socket path")
parser.add_argument("--dev", action="store_true", help="Development mode: allow /tmp fallback")
args = parser.parse_args()

# ---- Configuration ----
# ALIGN-005：Memory Service 标准 socket 路径为 $XDG_RUNTIME_DIR/kylin-memory/memory.sock
# （冻结声明 §二）；本 echo server 为 Gate 0 独立验证服务，其 socket 属"实现细节"，
# 保留独立路径（systemd=/run/kylin-memory-echo/echo.sock，dev=/tmp/kylin-memory-echo/echo.sock），
# 待 Phase 2 统一 Gateway 时合并。
# Priority: --socket CLI arg > dev mode /tmp > RUNTIME_DIRECTORY env (systemd) > default /run
if args.socket:
    SOCKET_PATH = args.socket
    SOCKET_DIR = os.path.dirname(SOCKET_PATH)
elif args.dev:
    # dev mode: always use /tmp (no root required, no RuntimeDirectory dependency)
    SOCKET_DIR = "/tmp/kylin-memory-echo"
    SOCKET_PATH = os.path.join(SOCKET_DIR, "echo.sock")
else:
    SOCKET_DIR = os.environ.get("RUNTIME_DIRECTORY", "/run/kylin-memory-echo")
    if not os.path.isdir(SOCKET_DIR):
        log("FATAL", f"RUNTIME_DIRECTORY ({SOCKET_DIR}) does not exist. "
                      "Use --dev flag to allow /tmp fallback in development.")
        sys.exit(1)
    SOCKET_PATH = os.path.join(SOCKET_DIR, "echo.sock")

BACKLOG = 5
MAX_MESSAGE_BYTES = 65536  # 64KB max message
PROTOCOL_VERSION = "1.0"
CLIENT_TIMEOUT = 30.0  # client read/write timeout (seconds), prevent permanent blocking

ERROR_CODE_MAP = {
    "UNKNOWN_METHOD": "UNSUPPORTED_METHOD",
    "INVALID_MESSAGE": "INVALID_REQUEST",
    "PROTOCOL_ERROR": "PROTOCOL_ERROR",
    "INTERNAL_ERROR": "INTERNAL_ERROR",
    "Handler error": "INTERNAL_ERROR",
    "Protocol error": "PROTOCOL_ERROR",
}

def safe_error_code(raw_error: str) -> str:
    """Map internal error strings to stable, non-leaking error codes."""
    for pattern, code in ERROR_CODE_MAP.items():
        if pattern in raw_error:
            return code
    return "INTERNAL_ERROR"

def ensure_socket_dir():
    os.makedirs(SOCKET_DIR, mode=0o700, exist_ok=True)


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """接收恰好 n 字节"""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Client disconnected")
        buf += chunk
    return buf


def recv_message(sock: socket.socket) -> dict:
    """接收长度前缀 JSON 消息"""
    raw_len = recv_exact(sock, 4)
    msg_len = struct.unpack(">I", raw_len)[0]
    if msg_len == 0 or msg_len > MAX_MESSAGE_BYTES:
        raise ValueError(f"Invalid message length: {msg_len}")
    raw_body = recv_exact(sock, msg_len)
    body = json.loads(raw_body.decode("utf-8"))
    return body


def send_message(sock: socket.socket, payload: dict):
    """发送长度前缀 JSON 消息"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = struct.pack(">I", len(body))
    sock.sendall(header + body)


def build_response(request: dict, status: str, data: Optional[dict] = None) -> dict:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request.get("request_id", ""),
        "trace_id": request.get("trace_id", ""),
        "status": status,
        "data": data or {},
        "server_ts": datetime.now(timezone.utc).isoformat(),
    }


def handle_echo(request: dict) -> dict:
    """echo: 回显 payload 中的 message 字段"""
    msg = request.get("payload", {}).get("message", "(empty)")
    return {"echo": msg, "received_at": datetime.now(timezone.utc).isoformat()}


def handle_health(request: dict) -> dict:
    """health: 返回服务状态"""
    return {
        "status": "healthy",
        "uptime_seconds": time.time() - start_time,
        "socket_path": SOCKET_PATH,
        "pid": os.getpid(),
    }


def handle_memory_retrieve(request: dict) -> dict:
    """memory.retrieve: 返回空上下文（模拟）"""
    return {
        "contexts": [],
        "total_found": 0,
        "elapsed_ms": 0.0,
        "fallback": False,
    }


# evidence.record API 已移除 (P0-4, PR21 R3 Review)
# 证据应由独立 Runner 在测试结束后根据真实命令、退出码和日志生成，
# 不得由服务端接受调用者自报结果直接写入证据文件。

METHOD_ROUTER = {
    "echo": handle_echo,
    "health": handle_health,
    "memory.retrieve": handle_memory_retrieve,
}


def handle_client(sock: socket.socket, addr: str):
    """处理单个客户端连接"""
    try:
        # 设置超时，防止恶意/故障客户端永久阻塞服务端
        sock.settimeout(CLIENT_TIMEOUT)
        request = recv_message(sock)
        method = request.get("method", "")
        log("INFO", f"Request method={method} request_id={request.get('request_id', '?')}")

        handler = METHOD_ROUTER.get(method)
        if handler is None:
            log("WARN", f"Unknown method: {method}")
            response = build_response(request, "error", {
                "error_code": "UNSUPPORTED_METHOD",
                "message": "Requested method is not supported by this service"
            })
        else:
            try:
                data = handler(request)
                response = build_response(request, "ok", data)
            except Exception as e:
                log("ERROR", f"Handler error: {e}\n{traceback.format_exc()}")
                response = build_response(request, "error", {
                    "error_code": safe_error_code(str(e)),
                    "message": "Request processing failed"
                })

        send_message(sock, response)
        log("INFO", f"Response sent: status={response['status']}")
    except socket.timeout:
        log("ERROR", f"Client read/write timeout ({CLIENT_TIMEOUT}s), closing connection")
    except Exception as e:
        log("ERROR", f"Client handler error: {e}\n{traceback.format_exc()}")
        try:
            error_resp = {
                "protocol_version": PROTOCOL_VERSION,
                "request_id": "",
                "trace_id": "",
                "status": "error",
                "data": {
                    "error_code": safe_error_code(str(e)),
                    "message": "Protocol error occurred while processing request"
                },
                "server_ts": datetime.now(timezone.utc).isoformat(),
            }
            send_message(sock, error_resp)
        except Exception:
            pass
    finally:
        try:
            sock.close()
        except Exception:
            pass


def cleanup():
    """清理 socket 文件"""
    try:
        os.unlink(SOCKET_PATH)
    except FileNotFoundError:
        pass


start_time = time.time()

def main():
    global start_time
    start_time = time.time()

    ensure_socket_dir()
    cleanup()  # 清理残留 socket

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined]  # Linux-only, Windows Pylance false positive
    server.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o700)  # 仅 owner 可访问
    server.listen(BACKLOG)

    log("INFO", f"Echo server listening on {SOCKET_PATH} (pid={os.getpid()})")

    def signal_handler(signum, frame):
        log("INFO", f"Received signal {signum}, shutting down...")
        server.close()
        cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        while True:
            client, addr = server.accept()
            log("INFO", f"Client connected")
            handle_client(client, "")
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        cleanup()
        log("INFO", "Server stopped")


if __name__ == "__main__":
    main()