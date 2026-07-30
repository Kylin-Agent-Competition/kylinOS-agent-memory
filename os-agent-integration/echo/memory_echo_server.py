#!/usr/bin/env python3
"""
麒麟 OS Agent 记忆系统 · Gate 0 SPIKE
Kaiming → 自定义 UDS Echo Server

监听 $XDG_RUNTIME_DIR/kylin-memory/memory.sock（默认 fallback /tmp/kylin-memory/memory.sock）
协议：长度前缀 JSON（4 字节大端长度 + JSON 负载）
"""

import os
import sys
import json
import struct
import signal
import socket
import logging
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────────────
SOCKET_PATH = os.environ.get(
    "KYLIN_MEMORY_SOCK",
    os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "kylin-memory", "memory.sock"),
)

# ── 日志 ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("memory_echo")

# ── 请求处理 ──────────────────────────────────────────────────
def handle_client(conn: socket.socket) -> None:
    """逐条读取长度前缀 JSON 请求并 Echo 响应"""
    client_addr = conn.getpeername() if hasattr(conn, "getpeername") else "?"
    logger.info("client connected: %s", client_addr)
    buf = bytearray()
    try:
        while True:
            # 读取 4 字节长度头
            while len(buf) < 4:
                chunk = conn.recv(4 - len(buf))
                if not chunk:
                    logger.info("client disconnected (EOF before header)")
                    return
                buf.extend(chunk)

            payload_len = struct.unpack(">I", buf[:4])[0]
            if payload_len > 1_000_000:  # 1 MB 上限
                logger.error("payload too large: %d bytes, closing", payload_len)
                return

            # 读取 JSON 负载
            buf = buf[4:]  # 移掉长度头
            while len(buf) < payload_len:
                chunk = conn.recv(payload_len - len(buf))
                if not chunk:
                    logger.info("client disconnected (EOF before payload)")
                    return
                buf.extend(chunk)

            payload_bytes = bytes(buf[:payload_len])
            buf = buf[payload_len:]  # 剩余留给下一条

            # 解析 JSON
            try:
                request = json.loads(payload_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                logger.warning("invalid JSON: %s", e)
                error_resp = json.dumps({"error": f"invalid JSON: {e}"}, ensure_ascii=False)
                send_response(conn, error_resp)
                continue

            req_id = request.get("request_id", "?")
            method = request.get("method", "?")
            logger.info("request id=%s method=%s payload=%s", req_id, method, json.dumps(request, ensure_ascii=False))

            # Echo 响应
            response = {
                "protocol_version": "1.0",
                "request_id": req_id,
                "status": "ok",
                "echo": {
                    "method": method,
                    "received_payload": request.get("payload", {}),
                },
            }
            send_response(conn, json.dumps(response, ensure_ascii=False))
    except (BrokenPipeError, ConnectionResetError):
        logger.info("client disconnected (pipe/reset)")
    finally:
        try:
            conn.close()
        except OSError:
            pass
        logger.info("connection closed")


def send_response(conn: socket.socket, body: str) -> None:
    """发送长度前缀 JSON 响应"""
    data = body.encode("utf-8")
    header = struct.pack(">I", len(data))
    conn.sendall(header + data)


# ── 主入口 ────────────────────────────────────────────────────
def main() -> None:
    # 确保目录存在
    sock_dir = os.path.dirname(SOCKET_PATH)
    os.makedirs(sock_dir, exist_ok=True)
    # 设置目录权限（麒麟上为 user:user 700）
    os.chmod(sock_dir, 0o700)

    # 清理旧 socket
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    server.listen(5)
    os.chmod(SOCKET_PATH, 0o600)

    logger.info("Memory Echo Server listening on %s", SOCKET_PATH)

    def shutdown(signum, frame):
        logger.info("shutting down (signal %d)", signum)
        server.close()
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        conn, _ = server.accept()
        # 单线程串行处理（SPIKE 阶段）
        handle_client(conn)


if __name__ == "__main__":
    main()