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
import logging
import os
import socket
import threading
from typing import Optional

from embedding.embedding_service import EmbeddingService, map_error_code, shutdown_executor
from embedding.outbox_consumer import build_deletion_consumer
from embedding.protocol import (
    IncompletePacket,
    ProtocolError,
    build_error_envelope,
    decode_packet,
    encode,
)

logger = logging.getLogger(__name__)


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
                # Keep registration and start atomic with respect to stop().
                # Otherwise stop() can snapshot an unstarted thread and join()
                # raises RuntimeError during the narrow startup window.
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


def _ensure_outbox_schema(engine) -> None:
    """A-REQ-01 前置校验：目标 DB 必须已含 outbox / idempotency_cache 表。

    该 schema（含 outbox 表）由主 Memory Service（app.py）或 Alembic 管理
    （FR-DB-002 单一真源），本进程不 init_schema。若表缺失，OutboxWorker 会在
    轮询时对 `no such table` 无限重试（死循环），故在此 fail-fast 给出清晰指引。
    """
    from sqlalchemy import inspect

    insp = inspect(engine)
    missing = [t for t in ("outbox", "idempotency_cache") if not insp.has_table(t)]
    if missing:
        raise RuntimeError(
            "A-REQ-01 目标 DB 缺少表 %s：请先由主 Memory Service 建库 "
            "（app.py 或 `alembic upgrade head`）再启动删除 consumer。db=%s"
            % (", ".join(missing), engine.url)
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Day5 最小垂直链路 UDS 服务器")
    parser.add_argument("--socket", default=_default_socket_path(),
                        help="UDS socket path（默认 ALIGN-005 标准路径）")
    parser.add_argument(
        "--register-deletion-consumer",
        action="store_true",
        help="（A-REQ-01 production wiring）启动 OutboxWorker 并注册删除事件 consumer，"
        "消费 `forget.executed`/`memory.deletion` 事件以失效 Embedding/抽取缓存；"
        "需 --db 指向共享 Outbox 数据库；production 默认不注册（未接线 → 事件进 retry/DL）",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="共享 Memory Service SQLite 路径（--register-deletion-consumer 时必填；"
        "覆盖环境变量 KYLIN_MEMORY_DB）",
    )
    args = parser.parse_args()

    server = EmbeddingUDSServer(args.socket)

    # A-REQ-01：生产删除 consumer 接线（真正消费 outbox 删除事件 → CacheInvalidator）
    # 架构归属：EmbeddingService + CacheInvalidator 位于本进程，故在此接线而非 app.py。
    # consumer 依赖 EmbeddingService.invalidator（经 set_extraction_provider 接线）。
    deletion_worker = None
    if args.register_deletion_consumer:
        import os as _os

        from db.engine import create_db_engine
        from outbox.worker import OutboxWorker

        db_path = args.db or _os.environ.get("KYLIN_MEMORY_DB")
        if not db_path:
            print(
                "[A-REQ-01] --register-deletion-consumer 需要 --db 指向共享 "
                "Memory Service 数据库（或设 KYLIN_MEMORY_DB）",
                flush=True,
            )
            return 2
        engine = create_db_engine(db_path)
        # 注意：不在此 init_schema/create_all——schema（含 outbox 表）由主
        # Memory Service（app.py）或 Alembic 管理（FR-DB-002 单一真源），
        # 避免双 schema truth source 分叉（PR#52 Issue 6）。
        # 但需校验 outbox/idempotency_cache 表已存在，否则 Worker 会对
        # `no such table` 无限重试（死循环）→ fail-fast 给清晰指引。
        try:
            _ensure_outbox_schema(engine)
        except RuntimeError as exc:
            print(f"[A-REQ-01] {exc}", flush=True)
            return 2
        # 接线 ExtractionProvider（创建 CacheInvalidator）：
        # 用最小可用的 ExtractionProvider 以提供抽取缓存（无 LLM 凭证时仅规则路径）
        try:
            from providers.extraction_provider import ExtractionProvider
        except Exception:  # noqa: BLE001 - 无 LLM/抽取依赖时降级为空 invalidator 占位
            ExtractionProvider = None  # type: ignore[assignment]
        if ExtractionProvider is not None:
            server._service.set_extraction_provider(ExtractionProvider())
        consumer = build_deletion_consumer(server._service)
        deletion_worker = OutboxWorker(
            engine,
            poll_interval_s=1,
            max_retries=3,
            consumer=consumer,
        )
        deletion_worker.start()
        logger.info(
            "A-REQ-01 删除 consumer 已接线（db=%s），OutboxWorker 已启动", db_path
        )

    try:
        server.start()
    except KeyboardInterrupt:
        print("\n[server] shutting down", flush=True)
    finally:
        server.stop()
        if deletion_worker is not None:
            deletion_worker.stop()


if __name__ == "__main__":
    main()
