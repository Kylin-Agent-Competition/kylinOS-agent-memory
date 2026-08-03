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

# ---- 配置 ----
# 优先使用 RuntimeDirectory（systemd 管理），fallback 到 /tmp
SOCKET_DIR = os.environ.get("RUNTIME_DIRECTORY", "/run/kylin-memory-echo")
if not os.path.isdir(SOCKET_DIR):
    SOCKET_DIR = "/tmp/kylin-memory-echo"
SOCKET_PATH = os.path.join(SOCKET_DIR, "echo.sock")
BACKLOG = 5
MAX_MESSAGE_BYTES = 65536  # 64KB 最大消息
PROTOCOL_VERSION = "1.0"
CLIENT_TIMEOUT = 30.0  # 客户端读写超时（秒），防永久阻塞

# ---- 日志 ----
def log(level: str, msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    print(f"[{ts}] [{level}] {msg}", file=sys.stderr, flush=True)


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
            response = build_response(request, "error", {"error": f"Unknown method: {method}"})
        else:
            try:
                data = handler(request)
                response = build_response(request, "ok", data)
            except Exception as e:
                log("ERROR", f"Handler error: {e}")
                response = build_response(request, "error", {"error": str(e)})

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
                "data": {"error": f"Protocol error: {e}"},
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