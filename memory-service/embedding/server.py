"""
server.py — 轨道 A Day5 最小垂直链路 UDS 服务器

以 Unix Domain Socket 提供 embed 服务（长度前缀 JSON 协议），
内部调用 EmbeddingService（真实 EmbeddingProvider）。

职责边界（Day5）：
- 仅实现最小链路：UDS 接收 → 协议解码 → EmbeddingService → 结构化响应
- Bridge 调用在 EmbeddingService 内部线程池执行（不阻塞聊天线程）
- 不可用时返回结构化错误/降级（见 embedding_service.py）

使用（麒麟 VM 或本地）:
  PYTHONPATH=memory-service python -m embedding.server --socket /tmp/kylin-memory-embed.sock
"""

from __future__ import annotations

import argparse
import os
import socket
import threading
from typing import Optional

from embedding.embedding_service import EmbeddingService
from embedding.protocol import (
    IncompletePacket,
    ProtocolError,
    decode_packet,
    encode,
)


class EmbeddingUDSServer:
    """UDS + 长度前缀 JSON 最小链路服务器。"""

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._service = EmbeddingService()
        self._server_sock: Optional[socket.socket] = None
        self._running = False

    def start(self) -> None:
        """启动 UDS 服务器（阻塞式 accept 循环）。"""
        if os.path.exists(self._socket_path):
            os.unlink(self._socket_path)

        self._service.start()
        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.bind(self._socket_path)
        self._server_sock.listen(8)
        self._running = True
        print(f"[server] listening on {self._socket_path}", flush=True)

        while self._running:
            try:
                conn, _ = self._server_sock.accept()
            except OSError:
                break
            # 每连接独立线程：连接间不互相阻塞
            t = threading.Thread(target=self._handle_conn, args=(conn,), daemon=True)
            t.start()

    def stop(self) -> None:
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
        self._service.close()
        if os.path.exists(self._socket_path):
            os.unlink(self._socket_path)

    # ── 连接处理 ──

    def _handle_conn(self, conn: socket.socket) -> None:
        buf = b""
        try:
            with conn:
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    try:
                        msg, buf = decode_packet(buf)
                    except IncompletePacket:
                        continue
                    except ProtocolError as exc:
                        conn.sendall(encode({"ok": False,
                                             "error": {"code": "ERR_PROTOCOL",
                                                       "message": str(exc)}}))
                        break
                    resp = self._service.handle_request(msg)
                    conn.sendall(encode(resp))
        except OSError:
            pass

    def __enter__(self) -> "EmbeddingUDSServer":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Day5 最小垂直链路 UDS 服务器")
    parser.add_argument("--socket", default="/tmp/kylin-memory-embed.sock",
                        help="UDS socket path")
    args = parser.parse_args()

    server = EmbeddingUDSServer(args.socket)
    try:
        server.start()
    except KeyboardInterrupt:
        print("\n[server] shutting down", flush=True)
    finally:
        server.stop()


if __name__ == "__main__":
    main()
