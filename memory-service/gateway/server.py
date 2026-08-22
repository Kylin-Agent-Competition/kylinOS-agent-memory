"""server.py — D4D IPC Gateway UDS 服务器（FRZ-IPC-001~007）

职责：
  - UDS + 长度前缀 JSON（冻结：64KB / protocol_version "1.0"）
  - 请求校验（必填字段 / deadline_ms / 版本）
  - Handler Registry 路由分发；未注册方法 → UNSUPPORTED_METHOD
  - 内部异常统一经 safe_error_code 映射（禁止泄漏 traceback）
  - deadline 语义：server_processing_time > deadline_ms → TIMEOUT
  - 停止后拒绝新连接请求（H3 模式，与 embedding/server.py 对齐）
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from typing import Any, Dict, Optional

from gateway import protocol as proto
from gateway.handlers import _UnsupportedStoreError
from gateway.protocol import (
    ERROR_CODE_INTERNAL_ERROR,
    ERROR_CODE_TIMEOUT,
    ERROR_CODE_UNSUPPORTED_METHOD,
    IncompletePacket,
    ProtocolError,
    RequestValidationError,
    build_error_response,
    build_response,
    decode_packet,
    encode,
    safe_error_code,
    validate_request,
)
from gateway.registry import HandlerRegistry, RequestContext, UnsupportedMethodError

logger = logging.getLogger(__name__)


class UDSGatewayServer:
    """UDS 服务器（单连接阻塞式读，多线程 accept；重连语义见 TD-IPC-004）。"""

    def __init__(
        self,
        socket_path: str,
        registry: HandlerRegistry,
        *,
        engine=None,
        default_deadline_ms: int = 5000,
    ) -> None:
        self._socket_path = socket_path
        self._registry = registry
        self._engine = engine
        self._default_deadline_ms = default_deadline_ms
        self._server_sock: Optional[socket.socket] = None
        self._running = False
        self._stopped = False
        self._conn_threads: list[threading.Thread] = []
        self._conn_lock = threading.Lock()
        # 注入 health handler 的 engine / methods 上下文
        self._extras: Dict[str, Any] = {
            "engine": engine,
            "methods": registry.methods(),
        }

    # ── 生命周期 ──

    def start(self) -> None:
        """启动 UDS 服务器（阻塞式 accept 循环，供独立线程调用）。"""
        if os.path.exists(self._socket_path):
            logger.warning("残留 socket 文件，先清理: %s", self._socket_path)
            os.unlink(self._socket_path)
        parent = os.path.dirname(self._socket_path)
        if parent:
            os.makedirs(parent, exist_ok=True, mode=0o700)

        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.bind(self._socket_path)
        os.chmod(self._socket_path, 0o600)
        self._server_sock.listen(8)
        self._running = True
        self._stopped = False
        logger.info("IPC Gateway 启动: %s", self._socket_path)

        try:
            while self._running:
                try:
                    conn, _ = self._server_sock.accept()
                except OSError:
                    if not self._running:
                        break
                    raise
                t = threading.Thread(
                    target=self._handle_connection, args=(conn,), daemon=True
                )
                with self._conn_lock:
                    self._conn_threads.append(t)
                t.start()
        finally:
            self._close_server_sock()

    def stop(self) -> None:
        """停止服务器（拒绝新请求 + join 连接线程 + unlink socket 文件）。

        unlink 语义（修复 TD-IPC 技术债）：Linux/麒麟下已关闭 listening socket
        的 socket 文件若未删除，停后 connect() 仍成功、请求在收发阶段被 ECONNRESET
        拒绝——对外表现为"文件在但服务已停"。stop() 统一在关闭 server sock 后
        unlink，使停后 connect() 立即失败，与 embedding/server.py 行为对齐。
        容错：文件不存在/已由 start() 清理时静默通过（需幂等）。
        """
        self._running = False
        self._stopped = True
        self._close_server_sock()
        if os.path.exists(self._socket_path):
            try:
                os.unlink(self._socket_path)
            except OSError as exc:
                logger.warning("unlink socket 失败(继续 stop): %s", exc)
        with self._conn_lock:
            threads = list(self._conn_threads)
        for t in threads:
            t.join(timeout=2.0)
        logger.info("IPC Gateway 已停止")

    def _close_server_sock(self) -> None:
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None

    # ── 连接处理 ──

    def _handle_connection(self, conn: socket.socket) -> None:
        try:
            buf = b""
            while True:
                if self._stopped:
                    logger.info("服务器已停止，拒绝新请求")
                    break
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
                while True:
                    try:
                        msg, buf = decode_packet(buf)
                    except IncompletePacket:
                        break
                    except ProtocolError as exc:
                        self._send_error(
                            conn, request_id="", trace_id="",
                            error_code=exc.error_code, message=str(exc),
                        )
                        return
                    self._dispatch(conn, msg)
        except OSError as exc:
            logger.debug("连接结束: %s", exc)
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _dispatch(self, conn: socket.socket, msg: Dict[str, Any]) -> None:
        start = time.monotonic()
        request_id = str(msg.get("request_id", ""))
        trace_id = str(msg.get("trace_id", ""))
        method = str(msg.get("method", ""))

        try:
            validate_request(msg)
            deadline_ms = int(msg["deadline_ms"])
        except ProtocolError as exc:
            self._send_error(
                conn, request_id=request_id, trace_id=trace_id,
                error_code=exc.error_code, message=str(exc),
            )
            return
        except RequestValidationError as exc:
            self._send_error(
                conn, request_id=request_id, trace_id=trace_id,
                error_code=exc.error_code, message=str(exc),
            )
            return

        try:
            handler = self._registry.route(method)
        except UnsupportedMethodError as exc:
            self._send_error(
                conn, request_id=request_id, trace_id=trace_id,
                error_code=exc.error_code, message=str(exc),
            )
            return

        ctx = RequestContext(
            request_id=request_id,
            trace_id=trace_id,
            method=method,
            deadline_ms=deadline_ms,
            idempotency_key=msg.get("idempotency_key"),
            extras=self._extras,
        )

        try:
            data = handler(msg.get("payload", {}), ctx)
        except _UnsupportedStoreError as exc:
            self._send_error(
                conn, request_id=request_id, trace_id=trace_id,
                error_code=exc.error_code, message="memory.store not implemented",
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("handler 内部错误 method=%s", method)
            self._send_error(
                conn, request_id=request_id, trace_id=trace_id,
                error_code=ERROR_CODE_INTERNAL_ERROR,
                message=safe_error_code(str(exc)),
            )
            return

        elapsed_ms = (time.monotonic() - start) * 1000
        if elapsed_ms > deadline_ms:
            # FRZ-IPC-004 §4.2：超时 → TIMEOUT
            self._send_error(
                conn, request_id=request_id, trace_id=trace_id,
                error_code=ERROR_CODE_TIMEOUT,
                message=f"deadline exceeded: {elapsed_ms:.0f}ms > {deadline_ms}ms",
            )
            return

        resp = build_response(
            request_id=request_id,
            trace_id=trace_id,
            status="ok",
            data=data,
        )
        self._send(conn, resp)

    def _send_error(self, conn, *, request_id: str, trace_id: str, error_code: str, message: str) -> None:
        resp = build_error_response(
            request_id=request_id,
            trace_id=trace_id,
            error_code=error_code,
            message=message,
        )
        self._send(conn, resp)

    def _send(self, conn: socket.socket, resp: Dict[str, Any]) -> None:
        try:
            conn.sendall(encode(resp))
        except OSError as exc:
            logger.debug("发送失败: %s", exc)
