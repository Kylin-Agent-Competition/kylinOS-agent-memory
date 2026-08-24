"""
server.py — 轨道 A Day5 最小垂直链路 UDS 服务器

以 Unix Domain Socket 提供 embed 服务（长度前缀 JSON 协议），
内部调用 EmbeddingService（真实 EmbeddingProvider）。

职责边界（Day5）：
- 仅实现最小链路：UDS 接收 → 协议解码 → EmbeddingService → 结构化响应
- Bridge 调用在 EmbeddingService 内部线程池执行（不阻塞聊天线程）
- 不可用时返回结构化错误/降级（见 embedding_service.py）

使用（麒麟 VM 或本地）:
  PYTHONPATH=memory-service python -m embedding.server --socket /tmp/kylin-memory/embedding.sock
"""

from __future__ import annotations

import argparse
import os
import socket
import threading
from typing import Optional

from embedding.embedding_service import EmbeddingService, map_error_code, shutdown_executor
from embedding.protocol import (
    IncompletePacket,
    ProtocolError,
    build_error_envelope,
    decode_packet,
    encode,
)


def _error_response(code: str, message: str) -> dict:
    """协议层错误响应（FRZ-IPC-006 冻结 envelope + FRZ-IPC-002 冻结错误码）。

    与 embedding_service._envelope_error 共用 build_error_envelope 单一实现，
    避免 server.py 与 embedding_service.py 两套 envelope 逻辑漂移。
    """
    return build_error_envelope(map_error_code(code), message)


def _default_socket_path() -> str:
    """默认 socket 路径（ALIGN-005 返工）：embedding 子服务独立 socket。

    不得默认占用正式 Memory Service 入口 `$XDG_RUNTIME_DIR/kylin-memory/memory.sock`
    （该 socket 归 Phase 2 统一 Gateway / Memory Service 所有）；embedding 独立
    socket 属子服务实现细节，默认 `$XDG_RUNTIME_DIR/kylin-memory/embedding.sock`。
    """
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return os.path.join(runtime_dir, "kylin-memory", "embedding.sock")
    return "/tmp/kylin-memory/embedding.sock"


# L2-A3：对已存在目录收敛 0700 时，跳过系统/共享目录（避免 chmod 破坏 /tmp、/run 等）
_EXCLUDED_CHMOD_DIRS = frozenset({
    "/", "/tmp", "/var", "/var/tmp", "/run", "/run/user", "/dev",
    "/etc", "/opt", "/usr", "/home", "/root", "/mnt", "/media", "/srv",
})


class EmbeddingUDSServer:
    """UDS + 长度前缀 JSON 最小链路服务器。"""

    def __init__(self, socket_path: str, provider: Optional[object] = None) -> None:
        self._socket_path = socket_path
        # provider 注入点（TD-A-005-09 修复路径）：测试/降级场景可注入替代 Provider；
        # 为 None 时使用默认 EmbeddingProvider（进程级单例）
        self._service = EmbeddingService(provider=provider)
        self._server_sock: Optional[socket.socket] = None
        self._running = False
        self._stopped = False  # H3: stop 后拒绝新业务请求（防旧连接重建 executor）
        self._conn_threads: list = []  # H3: 连接线程跟踪（stop 时 join，active worker 正确退出）
        self._conn_lock = threading.Lock()

    def _ensure_socket_dir(self) -> None:
        """安全创建 socket 父目录（per-user 隔离，0700，对已存在目录幂等收敛）。

        L2-A3 修复：`os.makedirs(mode=0700)` 只对**新建**目录生效；对已存在的
        父目录，仅当其为**当前用户私有且非系统/共享/家目录**时才幂等收敛为 0700，
        避免 chmod 破坏共享目录（如 /tmp、/run 等）或用户家目录。
        """
        parent = os.path.dirname(self._socket_path)
        if not parent:
            return
        os.makedirs(parent, mode=0o700, exist_ok=True)
        try:
            st = os.stat(parent)
        except OSError:
            return
        if not (os.path.isdir(parent) and st.st_uid == os.getuid()):
            return  # 非当前用户所有（如 /tmp 归 root）→ 不 chmod
        normalized = os.path.normpath(parent)
        if normalized in _EXCLUDED_CHMOD_DIRS or normalized == os.path.normpath(
                os.path.expanduser("~")):
            return  # 系统/共享目录或用户家目录 → 不 chmod
        try:
            os.chmod(parent, 0o700)
        except OSError:
            pass  # 权限受限/目录消失时忽略；祖先目录本身 0700 仍可隔离

    def _remove_stale_socket(self) -> None:
        """仅清理 stale socket；active socket（有监听进程）拒绝 unlink。

        ALIGN-005 返工核心：不再无条件 `exists → unlink → bind`。若 socket 已被
        活跃进程监听（connect 成功），直接抛错，避免独立 Embedding Server 抢占
        正式 Memory Service 的 socket ownership。
        """
        if not os.path.exists(self._socket_path):
            return
        if self._is_socket_active(self._socket_path):
            raise RuntimeError(
                f"active socket already listening: {self._socket_path}; "
                "refusing to unlink (avoid stealing socket ownership)")
        os.unlink(self._socket_path)

    @staticmethod
    def _is_socket_active(path: str) -> bool:
        """探测 socket 是否被活跃监听（能 connect 即 active，connect 失败即 stale）。"""
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.settimeout(0.2)
            probe.connect(path)
            return True
        except OSError:
            return False
        finally:
            probe.close()

    def start(self) -> None:
        """启动 UDS 服务器（阻塞式 accept 循环）。"""
        self._ensure_socket_dir()
        self._remove_stale_socket()

        self._service.start()
        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.bind(self._socket_path)
        self._server_sock.listen(8)
        self._running = True
        self._stopped = False  # H3: restart 时重置停止标记
        print(f"[server] listening on {self._socket_path}", flush=True)

        while self._running:
            try:
                conn, _ = self._server_sock.accept()
            except OSError:
                break
            # 每连接独立线程：连接间不互相阻塞
            t = threading.Thread(target=self._handle_conn, args=(conn,), daemon=True)
            with self._conn_lock:
                self._conn_threads.append(t)
            t.start()

    def stop(self) -> None:
        self._running = False
        self._stopped = True  # H3: 先置停止标记，拒绝后续业务请求
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
        self._service.close()
        # 审查报告 #3：服务停止时释放 Bridge 线程池资源（幂等；再次 start 会惰性重建）
        shutdown_executor()
        # H3: join 已建立的连接线程（recv 超时 0.5s → 最多等待 2s），
        # 确保 active worker 正确退出；残留线程因 _stopped=True 无法再提交任务
        with self._conn_lock:
            threads, self._conn_threads = list(self._conn_threads), []
        for t in threads:
            t.join(timeout=2.0)
        if os.path.exists(self._socket_path):
            os.unlink(self._socket_path)

    # ── 连接处理 ──

    def _handle_conn(self, conn: socket.socket) -> None:
        buf = b""
        try:
            with conn:
                # H3: 超时 recv——stop 后能及时退出（active worker 正确退出）
                conn.settimeout(0.5)
                while True:
                    try:
                        chunk = conn.recv(4096)
                    except socket.timeout:
                        # 超时：若已停止则退出，否则继续等待
                        if self._stopped:
                            break
                        continue
                    except OSError:
                        break
                    if not chunk:
                        break
                    # H3: recv 后检查——服务可能已在 recv 阻塞期间停止，
                    # 旧连接不得继续提交任务（防 executor 被旧连接重建）
                    if self._stopped:
                        try:
                            conn.sendall(encode(_error_response(
                                "ERR_SERVICE_STOPPED", "server is stopped")))
                        except OSError:
                            pass
                        break
                    buf += chunk
                    try:
                        msg, buf = decode_packet(buf)
                    except IncompletePacket:
                        continue
                    except ProtocolError as exc:
                        conn.sendall(encode(_error_response("ERR_PROTOCOL", str(exc))))
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
    parser.add_argument("--socket", default=_default_socket_path(),
                        help="UDS socket path（默认 ALIGN-005 标准路径）")
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
