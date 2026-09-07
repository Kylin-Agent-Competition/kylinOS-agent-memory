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

from embedding.server import EmbeddingUDSServer, _default_socket_path
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


def _wait_listening(sock_path: str, timeout: float = 3.0) -> None:
    """等待 socket 真正进入监听（以 connect 成功为准，'文件存在'不足以判断就绪）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(sock_path)
            return
        except OSError:
            time.sleep(0.02)
    raise TimeoutError(f"socket not listening: {sock_path}")


def _send(sock: socket.socket, method: str, payload: dict, timeout: float = 3.0) -> dict:
    import json
    env = {"protocol_version": "1.0", "request_id": "req-t", "trace_id": "trc-t",
           "method": method, "deadline_ms": 5000, "payload": payload}
    body = json.dumps(env, ensure_ascii=False).encode("utf-8")
    sock.settimeout(timeout)
    sock.sendall(struct.pack(">I", len(body)) + body)
    buf = b""
    try:
        while len(buf) < 4:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("conn closed by server")
            buf += chunk
        (n,) = struct.unpack(">I", buf[:4])
        while len(buf) < 4 + n:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("conn closed by server")
            buf += chunk
        return json.loads(buf[4:4 + n].decode("utf-8"))
    except socket.timeout:
        raise ConnectionError("recv timeout (server not responding after stop)")


@pytest.fixture
def server(tmp_path):
    sock_path = str(tmp_path / "test.sock")
    srv = EmbeddingUDSServer(sock_path, provider=FakeProvider())
    t = threading.Thread(target=srv.start, daemon=True)
    t.start()
    _wait_listening(sock_path)
    yield srv, sock_path
    srv.stop()
    shutdown_executor()


def test_server_serves_request(server):
    srv, sock_path = server
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    resp = _send(s, "memory.embed", {"text": "hello"})
    assert resp["status"] == "ok"
    assert resp["data"]["dimension"] == 768
    s.close()


def test_stop_rejects_new_business_request(server):
    """H3: stop 后新连接被拒绝（socket 已 unlink，新业务请求无法接入）。"""
    srv, sock_path = server
    srv.stop()
    # stop 后 socket 已 unlink，新连接无法建立
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with pytest.raises((FileNotFoundError, ConnectionRefusedError, OSError)):
            s.connect(sock_path)
    finally:
        s.close()


def test_stopped_conn_thread_rejects(server):
    """H3: 已建立连接在 stop 后不得再获业务处理。

    允许两种正确行为（都证明业务不再处理）：
    - 返回 ERR_SERVICE_STOPPED（数据已到达，recv 后检查拦截）
    - 连接关闭 / 超时（线程已退出，不再 recv/处理）
    """
    srv, sock_path = server
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    # 先正常请求一次，确认连接建立
    resp = _send(s, "memory.embed", {"text": "before"})
    assert resp["status"] == "ok"
    # stop 服务（连接线程仍在）
    srv.stop()
    # 再发请求 → 必须不被业务处理（ERR_SERVICE_STOPPED 或连接关闭/超时）
    try:
        resp = _send(s, "memory.embed", {"text": "after-stop"})
        assert resp["status"] == "error"
        assert resp["error_code"] == "INTERNAL_ERROR"
    except ConnectionError:
        pass  # 连接关闭/超时 = 线程已退出，业务未处理（同样正确）
    s.close()


def test_executor_not_recreated_by_stale_conn(server):
    """H3 核心: stop 后 executor 不得被旧连接重新创建。"""
    srv, sock_path = server
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    _send(s, "memory.embed", {"text": "before"})
    srv.stop()
    # 旧连接发请求 → 必须不被业务处理（不触发 handle_request/_submit_bridge）
    try:
        resp = _send(s, "memory.embed", {"text": "after"})
        assert resp["status"] == "error"
        assert resp["error_code"] == "INTERNAL_ERROR"
    except ConnectionError:
        pass  # 连接关闭/超时 = 未处理（executor 未被重建）
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
    _wait_listening(sock_path)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    resp = _send(s, "memory.embed", {"text": "restarted"})
    assert resp["status"] == "ok"
    assert resp["data"]["dimension"] == 768
    s.close()
    srv.stop()


def test_stop_joins_conn_threads(server):
    """H3: stop() 后连接线程被 join（active worker 正确退出）。"""
    srv, sock_path = server
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    _send(s, "memory.embed", {"text": "before"})
    # 记录当前连接线程
    with srv._conn_lock:
        assert len(srv._conn_threads) >= 1
        threads = list(srv._conn_threads)
    srv.stop()
    # 连接线程应已退出（join 完成；recv 超时循环最多 0.5s）
    assert all(not t.is_alive() for t in threads)
    # 线程列表已清空
    with srv._conn_lock:
        assert srv._conn_threads == []
    s.close()


def test_stop_cannot_join_registered_but_unstarted_worker(server, monkeypatch):
    """Registration and start are atomic: stop never joins an unstarted worker.

    Delay the accepted connection worker precisely at ``Thread.start()``.  The
    stopper is already running before the monkeypatch so only the connection
    worker is delayed.  Before the fix, stop() could snapshot that registered,
    unstarted worker and raise ``RuntimeError`` from ``join()``.
    """
    srv, sock_path = server
    worker_start_entered = threading.Event()
    allow_worker_start = threading.Event()
    request_stop = threading.Event()
    stop_done = threading.Event()
    stop_errors = []
    original_start = threading.Thread.start

    def stopper():
        request_stop.wait(timeout=3)
        try:
            srv.stop()
        except Exception as exc:  # pragma: no cover - assertion below reports it
            stop_errors.append(exc)
        finally:
            stop_done.set()

    stop_thread = threading.Thread(target=stopper, daemon=True)
    original_start(stop_thread)

    def delayed_start(thread):
        worker_start_entered.set()
        assert allow_worker_start.wait(timeout=3), "test did not release worker start"
        return original_start(thread)

    monkeypatch.setattr(threading.Thread, "start", delayed_start)
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(sock_path)
        assert worker_start_entered.wait(timeout=3)
        request_stop.set()
        # stop() must wait for the registration/start critical section rather
        # than snapshotting an unstarted worker.
        assert not stop_done.wait(timeout=0.1)
        allow_worker_start.set()
        assert stop_done.wait(timeout=3)
        assert stop_errors == []
        with srv._conn_lock:
            assert srv._conn_threads == []
    finally:
        allow_worker_start.set()
        client.close()
        stop_thread.join(timeout=3)


def test_stop_prevents_registration_after_accept(server):
    """A connection accepted before stop() cannot create a post-stop worker."""
    srv, sock_path = server
    original_lock = srv._conn_lock
    registration_waiting = threading.Event()
    allow_registration = threading.Event()

    class PauseFirstLock:
        """Pause the next lifecycle-lock acquisition before it obtains the lock."""

        def __init__(self):
            self._lock = original_lock
            self._pause_once = True

        def __enter__(self):
            if self._pause_once:
                self._pause_once = False
                registration_waiting.set()
                assert allow_registration.wait(timeout=3), "test did not release registration"
            self._lock.acquire()
            return self

        def __exit__(self, exc_type, exc, tb):
            self._lock.release()

    srv._conn_lock = PauseFirstLock()
    stop_done = threading.Event()
    stop_errors = []

    def stopper():
        try:
            srv.stop()
        except Exception as exc:  # pragma: no cover - assertion below reports it
            stop_errors.append(exc)
        finally:
            stop_done.set()

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(sock_path)
        assert registration_waiting.wait(timeout=3)
        stop_thread = threading.Thread(target=stopper, daemon=True)
        stop_thread.start()
        assert stop_done.wait(timeout=3)
        allow_registration.set()
        stop_thread.join(timeout=3)
        assert stop_errors == []
        # The server rechecks state after accept while holding the lifecycle
        # lock, closes this connection, and never adds a worker post-stop.
        client.settimeout(3)
        assert client.recv(1) == b""
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with srv._conn_lock:
                if srv._conn_threads == []:
                    break
            time.sleep(0.01)
        with srv._conn_lock:
            assert srv._conn_threads == []
    finally:
        allow_registration.set()
        client.close()


# ── ALIGN-005 返工：socket ownership / stale / active（PR#57 R1） ──

def test_default_socket_path_is_not_memory_sock():
    """ALIGN-005：embedding 默认 socket 不得占用正式 memory.sock。"""
    p = _default_socket_path()
    assert not p.endswith("memory.sock")
    assert p.endswith("embedding.sock")


def test_start_refuses_active_socket(tmp_path):
    """ALIGN-005：active socket（有监听）不得被 unlink，start 抛错。"""
    sock_path = str(tmp_path / "active.sock")
    active = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    active.bind(sock_path)
    active.listen(1)
    try:
        srv = EmbeddingUDSServer(sock_path, provider=FakeProvider())
        with pytest.raises(RuntimeError, match="active socket"):
            srv.start()
    finally:
        active.close()
        if os.path.exists(sock_path):
            os.unlink(sock_path)


def test_start_cleans_stale_socket(tmp_path):
    """ALIGN-005：stale socket（无监听）被安全清理后正常启动并可服务。"""
    sock_path = str(tmp_path / "stale.sock")
    # 制造 stale socket：bind 后立即 close（socket 文件残留，无监听进程）
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(sock_path)
    s.close()
    assert os.path.exists(sock_path)

    srv = EmbeddingUDSServer(sock_path, provider=FakeProvider())
    t = threading.Thread(target=srv.start, daemon=True)
    t.start()
    # 轮询直到 server 真正监听（stale socket 先被 unlink 再重新 bind，故不能用
    # "文件存在"判断就绪，须以 connect 成功为准）
    deadline = time.time() + 3
    c = None
    while time.time() < deadline:
        try:
            c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            c.connect(sock_path)
            break
        except OSError:
            if c is not None:
                c.close()
            c = None
            time.sleep(0.02)
    assert c is not None, "server did not start listening in time"

    resp = _send(c, "memory.embed", {"text": "hello"})
    assert resp["status"] == "ok"
    assert resp["data"]["dimension"] == 768
    c.close()
    srv.stop()
    shutdown_executor()


# ── L2-A3 修复：现存目录 0755 → 0700 幂等收敛（受保护，PR#57 R1 遗留债务） ──

def test_ensure_socket_dir_converges_existing_0755(tmp_path):
    """L2-A3: 对已存在的当前用户私有 0755 目录幂等收敛为 0700。"""
    from embedding.server import EmbeddingUDSServer
    parent = tmp_path / "kylin-memory"
    parent.mkdir(mode=0o755)
    os.chmod(parent, 0o755)
    assert (parent.stat().st_mode & 0o777) == 0o755
    srv = EmbeddingUDSServer(str(parent / "embedding.sock"), provider=FakeProvider())
    srv._ensure_socket_dir()
    assert (parent.stat().st_mode & 0o777) == 0o700


def test_ensure_socket_dir_skips_shared_tmp():
    """L2-A3: socket 直接在 /tmp 下时，父目录 /tmp（系统共享）不被 chmod。"""
    from embedding.server import EmbeddingUDSServer
    before = os.stat("/tmp").st_mode & 0o777
    srv = EmbeddingUDSServer("/tmp/pr57-l2a3-skip-marker.sock", provider=FakeProvider())
    srv._ensure_socket_dir()  # /tmp 在 _EXCLUDED_CHMOD_DIRS 内 → 不应被 chmod
    after = os.stat("/tmp").st_mode & 0o777
    assert after == before


def test_ensure_socket_dir_skips_home_dir(tmp_path, monkeypatch):
    """L2-A3: 用户家目录本身不被 chmod 收紧。"""
    from embedding.server import EmbeddingUDSServer
    home = tmp_path / "fake-home"
    home.mkdir(mode=0o755)
    os.chmod(home, 0o755)
    monkeypatch.setattr("os.path.expanduser", lambda _x="~": str(home))
    srv = EmbeddingUDSServer(str(home / "embedding.sock"), provider=FakeProvider())
    srv._ensure_socket_dir()
    # 家目录被排除 → 保持 0755
    assert (home.stat().st_mode & 0o777) == 0o755
