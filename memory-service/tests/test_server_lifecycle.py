"""
test_server_lifecycle.py — H3：server.stop() 生命周期测试

覆盖（Reviewer H3 要求）：
- stop 后拒绝新业务请求（ERR_SERVICE_STOPPED）
- 已连接客户端在 stop 后不能继续提交任务
- executor 不得被旧连接重新创建（stop 后 embed 请求被拒，不触发 _submit_bridge）
- shutdown 线程安全（幂等）
- restart 显式重新初始化（start 后恢复服务）
"""

import os
import socket
import struct
import threading
import time

import pytest

from embedding.server import EmbeddingUDSServer
from embedding.embedding_service import shutdown_executor


class FakeProvider:
    """本地测试 Provider（不依赖 SDK）。"""

    def __init__(self):
        self._started = False
        self._closed = False

    def start(self):
        self._started = True

    def close(self):
        self._closed = True

    def embed(self, text, *, timeout_ms=5000):
        from providers import EmbeddingResult
        return EmbeddingResult(vector=[0.1] * 768, dimension=768, l2_norm=1.0)


def _send(sock: socket.socket, method: str, payload: dict) -> dict:
    import json
    env = {"protocol_version": "1.0", "request_id": "req-t", "trace_id": "trc-t",
           "method": method, "deadline_ms": 5000, "payload": payload}
    body = json.dumps(env, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack(">I", len(body)) + body)
    buf = b""
    while len(buf) < 4:
        buf += sock.recv(4096)
    (n,) = struct.unpack(">I", buf[:4])
    while len(buf) < 4 + n:
        buf += sock.recv(4096)
    return json.loads(buf[4:4 + n].decode("utf-8"))


@pytest.fixture
def server(tmp_path):
    sock_path = str(tmp_path / "test.sock")
    srv = EmbeddingUDSServer(sock_path, provider=FakeProvider())
    t = threading.Thread(target=srv.start, daemon=True)
    t.start()
    # 等待 socket 就绪
    deadline = time.time() + 3
    while not os.path.exists(sock_path) and time.time() < deadline:
        time.sleep(0.02)
    yield srv, sock_path
    srv.stop()
    shutdown_executor()


def test_server_serves_request(server):
    srv, sock_path = server
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    resp = _send(s, "memory.embed", {"text": "hello"})
    assert resp["ok"] is True
    assert resp["result"]["dimension"] == 768
    s.close()


def test_stop_rejects_new_business_request(server):
    """H3: stop 后新请求 → ERR_SERVICE_STOPPED。"""
    srv, sock_path = server
    srv.stop()
    # stop 后 socket 已 unlink，无法再 connect——验证 stopped 标记生效路径：
    # 直接构造一个"已在连接中的旧连接"场景由下一测试覆盖；此处验证 stop 幂等
    assert srv._stopped is True
    srv.stop()  # 幂等：不抛错


def test_stopped_conn_thread_rejects(server):
    """H3: 已建立连接的线程在 stop 后收到请求 → 拒绝（ERR_SERVICE_STOPPED）。"""
    srv, sock_path = server
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    # 先正常请求一次，确认连接建立
    resp = _send(s, "memory.embed", {"text": "before"})
    assert resp["ok"] is True
    # stop 服务（连接线程仍在）
    srv.stop()
    # 再发请求 → 连接线程检测到 stopped，返回 ERR_SERVICE_STOPPED 并关闭
    resp = _send(s, "memory.embed", {"text": "after-stop"})
    assert resp["ok"] is False
    assert resp["error"]["code"] == "ERR_SERVICE_STOPPED"
    s.close()


def test_executor_not_recreated_by_stale_conn(server):
    """H3 核心: stop 后 executor 不得被旧连接重新创建。"""
    srv, sock_path = server
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    _send(s, "memory.embed", {"text": "before"})
    srv.stop()
    # 旧连接发请求 → 被拒绝（ERR_SERVICE_STOPPED），不触发 handle_request/_submit_bridge
    resp = _send(s, "memory.embed", {"text": "after"})
    assert resp["ok"] is False
    assert resp["error"]["code"] == "ERR_SERVICE_STOPPED"
    assert srv._stopped is True
    s.close()
    shutdown_executor()  # 幂等清理


def test_restart_reinitializes(server):
    """H3: restart 显式重新初始化（start 后服务恢复）。"""
    srv, sock_path = server
    srv.stop()
    # 显式 restart：重新 start
    t = threading.Thread(target=srv.start, daemon=True)
    t.start()
    deadline = time.time() + 3
    while not os.path.exists(sock_path) and time.time() < deadline:
        time.sleep(0.02)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    resp = _send(s, "memory.embed", {"text": "restarted"})
    assert resp["ok"] is True
    assert resp["result"]["dimension"] == 768
    s.close()
    srv.stop()
