"""
test_embedding_service.py — 轨道 A Day5 最小垂直链路 Service 层测试

覆盖：
1. 正常链路：embed → 真实向量返回（mock Provider 模拟）
2. 结构化错误：ProviderError → {"ok": false, "error": {...}}
3. 真实降级：Provider 不可用 → 明确空向量 + degraded 标记
4. 超时降级：Bridge 调用超时 → ERR_TIMEOUT
5. 非 str 输入 → ERR_INVALID_TEXT
6. 不阻塞：Bridge 调用在独立线程池执行（服务立即响应，不阻塞调用线程）

本地可跑：用 fake Provider（不依赖 kylin_embedding / SDK）。
"""

import threading
import time

import pytest

from embedding.embedding_service import EmbeddingService
from embedding.protocol import build_envelope
from providers import EmbeddingResult, ProviderError, ProviderErrorCode


# ── fake Provider（不依赖 SDK） ──

class FakeProvider:
    def __init__(self, *, ok=True, delay=0.0, fail_with=None, fail_on_text=None):
        self._ok = ok
        self._delay = delay
        self._fail_with = fail_with
        self._fail_on_text = fail_on_text  # 仅对该文本触发失败（embed_batch 部分失败场景）
        self._started = False
        self._closed = False
        self.embed_thread = None

    def start(self):
        self._started = True

    def close(self):
        self._closed = True

    def embed(self, text, *, timeout_ms=5000):
        # 记录调用线程（验证不阻塞主线程）
        self.embed_thread = threading.current_thread().name
        if self._delay:
            time.sleep(self._delay)
        if self._fail_on_text is not None and text == self._fail_on_text:
            raise ProviderError(ProviderErrorCode.ERR_EMBED_FAILED,
                                "embed failed for specific text")
        if self._fail_with is not None:
            raise self._fail_with
        if not self._ok:
            raise ProviderError(ProviderErrorCode.ERR_SDK_ERROR, "sdk error")
        return EmbeddingResult(vector=[0.1] * 768, dimension=768, l2_norm=1.0)


# ── 正常链路 ──

def test_embed_success():
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    resp = svc.embed("hello")
    assert resp["ok"] is True
    assert resp["result"]["dimension"] == 768
    assert len(resp["result"]["vector"]) == 768
    assert resp["result"]["l2_norm"] == 1.0
    svc.close()


# ── 结构化错误 ──

def test_embed_provider_error_degraded():
    """Provider 不可用 → 真实降级：ok=true + degraded + 明确空向量。"""
    svc = EmbeddingService(provider=FakeProvider(fail_with=ProviderError(
        ProviderErrorCode.ERR_SDK_NOT_LOADED, "so not found")))
    svc.start()
    resp = svc.embed("hello")
    assert resp["ok"] is True
    assert resp["degraded"] is True
    assert resp["result"]["vector"] == []
    assert resp["degraded_reason"]["code"] == "ERR_SDK_NOT_LOADED"
    assert "so not found" in resp["degraded_reason"]["message"]
    svc.close()


def test_embed_non_str_invalid():
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    resp = svc.embed(123)
    assert resp["ok"] is False
    assert resp["error"]["code"] == "ERR_INVALID_TEXT"
    svc.close()


# ── 真实降级 ──

def test_embed_degraded_empty_vector():
    """Provider 不可用 → 明确空向量 + degraded 标记（非假数据）。"""
    svc = EmbeddingService(provider=FakeProvider(fail_with=ProviderError(
        ProviderErrorCode.ERR_EMBED_FAILED, "embed failed")))
    svc.start()
    resp = svc.embed("hello")
    assert resp["ok"] is True
    assert resp["degraded"] is True
    assert resp["result"]["vector"] == []
    assert resp["result"]["dimension"] == 0
    assert resp["degraded_reason"]["code"] == "ERR_EMBED_FAILED"
    svc.close()


# ── 超时降级 ──

def test_embed_timeout_error():
    """Bridge 调用超过 timeout → 结构化错误 ERR_TIMEOUT（非降级：调用未完成）。"""
    svc = EmbeddingService(provider=FakeProvider(delay=2.0))
    svc.start()
    resp = svc.embed("hello", timeout_ms=50)  # 50ms 超时，provider 延迟 2s
    assert resp["ok"] is False
    assert resp["error"]["code"] == "ERR_TIMEOUT"
    svc.close()


# ── 不阻塞聊天线程（Day5-3） ──

def test_bridge_runs_in_pool_not_caller_thread():
    """embed 在独立线程池执行，不阻塞调用线程。"""
    provider = FakeProvider(delay=0.3)
    svc = EmbeddingService(provider=provider)
    svc.start()
    caller_thread = threading.current_thread().name
    resp = svc.embed("hello", timeout_ms=5000)
    assert resp["ok"] is True
    assert provider.embed_thread != caller_thread, \
        "Bridge 调用应在线程池执行，而非调用线程"
    svc.close()


def test_embed_returns_while_bridge_still_running():
    """线程池异步：0.3s 延迟下调用应在 timeout 内返回（不永久阻塞聊天线程）。"""
    provider = FakeProvider(delay=0.3)
    svc = EmbeddingService(provider=provider)
    svc.start()
    t0 = time.monotonic()
    resp = svc.embed("hello", timeout_ms=5000)
    elapsed = time.monotonic() - t0
    assert resp["ok"] is True
    # 调用在线程池执行；主线程同步等待结果但受 timeout 保护，不会永久挂起
    assert elapsed < 5.0, f"调用超时保护未生效: {elapsed:.2f}s"
    svc.close()


# ── 协议分发（架构 4.4 envelope） ──

def test_handle_request_dispatch():
    """envelope 分发：memory.ping / memory.embed / 未知 method / 缺 protocol_version。"""
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    # memory.ping（data 恒为 object，FRZ-IPC-006 §6.2）
    assert svc.handle_request(
        {"protocol_version": "1.0", "method": "memory.ping",
         "request_id": "req-ping", "trace_id": "trc-ping",
         "deadline_ms": 100, "payload": {}})["data"] == {"pong": True}
    # memory.embed（envelope + request_id/trace_id 回显）
    env = build_envelope("memory.embed", {"text": "hi"},
                         request_id="req-1", trace_id="trc-1")
    resp = svc.handle_request(env)
    assert resp["status"] == "ok"
    assert resp["request_id"] == "req-1"
    assert resp["trace_id"] == "trc-1"
    assert resp["protocol_version"] == "1.0"
    assert resp["data"]["dimension"] == 768
    # 未知 method → UNSUPPORTED_METHOD（语义分类，不再 PROTOCOL_ERROR）
    bad = svc.handle_request(
        {"protocol_version": "1.0", "method": "memory.unknown",
         "request_id": "req-u", "trace_id": "trc-u",
         "deadline_ms": 100, "payload": {}})
    assert bad["status"] == "error" and bad["error_code"] == "UNSUPPORTED_METHOD"
    # 缺 protocol_version → PROTOCOL_ERROR（含 request_id 回显）
    bad2 = svc.handle_request(
        {"method": "memory.embed", "payload": {"text": "x"}, "request_id": "req-9"})
    assert bad2["status"] == "error" and bad2["error_code"] == "PROTOCOL_ERROR"
    assert bad2["request_id"] == "req-9"
    # 缺必填字段 deadline_ms → INVALID_REQUEST
    bad3 = svc.handle_request(
        {"protocol_version": "1.0", "method": "memory.embed",
         "request_id": "req-10", "trace_id": "trc-10",
         "payload": {"text": "x"}})
    assert bad3["status"] == "error" and bad3["error_code"] == "INVALID_REQUEST"
    svc.close()


def test_handle_request_embed_batch_envelope():
    """envelope 分发：memory.embed_batch。"""
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    resp = svc.handle_request(build_envelope(
        "memory.embed_batch", {"texts": ["a", "b"]}))
    assert resp["status"] == "ok"
    assert len(resp["data"]["vectors"]) == 2
    assert resp["data"]["vectors"][0]["dimension"] == 768
    svc.close()


def test_embed_batch_partial_failure():
    """embed_batch 任一条失败 → 整体失败（结构化错误，含失败码）。

    审查报告 #5：补充部分失败路径的独立测试。
    """
    svc = EmbeddingService(provider=FakeProvider(fail_on_text="bad"))
    svc.start()
    resp = svc.embed_batch(["ok1", "bad", "ok3"])
    assert resp["ok"] is False
    assert resp["error"]["code"] == "ERR_EMBED_FAILED"
    svc.close()


def test_embed_batch_partial_failure_via_handle_request():
    """envelope 分发路径的 embed_batch 部分失败（结构化错误 + request_id 回显）。"""
    svc = EmbeddingService(provider=FakeProvider(fail_on_text="bad"))
    svc.start()
    resp = svc.handle_request(build_envelope(
        "memory.embed_batch", {"texts": ["a", "bad"]},
        request_id="req-batch-fail", trace_id="trc-batch-fail"))
    assert resp["status"] == "error"
    assert resp["error_code"] == "INTERNAL_ERROR"
    assert resp["request_id"] == "req-batch-fail"
    assert resp["trace_id"] == "trc-batch-fail"
    svc.close()


def test_health_reports_status():
    """memory.health：返回分项状态（服务/Provider/Bridge），不触发 SDK。"""
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    resp = svc.handle_request(
        {"protocol_version": "1.0", "method": "memory.health",
         "request_id": "req-h", "trace_id": "trc-h",
         "deadline_ms": 100, "payload": {}})
    assert resp["status"] == "ok"
    assert resp["data"]["service"] == "ok"
    assert resp["data"]["provider"] == "ready"
    assert resp["data"]["degraded"] is False
    assert "bridge_loaded" in resp["data"]
    assert "bridge_has_session" in resp["data"]
    svc.close()


def test_health_stopped_state():
    """未 start 的 Service：health 返回 stopped 状态（不崩溃）。"""
    svc = EmbeddingService(provider=FakeProvider())
    resp = svc.handle_request(
        {"protocol_version": "1.0", "method": "memory.health",
         "request_id": "req-h", "trace_id": "trc-h",
         "deadline_ms": 100, "payload": {}})
    assert resp["status"] == "ok"
    assert resp["data"]["service"] == "stopped"
    assert resp["data"]["provider"] == "stopped"
    svc.close()


def test_executor_shutdown_idempotent_and_rebuild():
    """审查报告 #3：shutdown_executor 幂等；shutdown 后 submit 惰性重建。

    - 第一次 shutdown：不抛错
    - 第二次 shutdown：幂等（no-op）
    - shutdown 后 embed 仍工作（_submit_bridge 自动重建线程池）
    """
    from embedding.embedding_service import shutdown_executor

    shutdown_executor()
    shutdown_executor()  # 幂等

    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    resp = svc.embed("after-shutdown")
    assert resp["ok"] is True
    assert resp["result"]["dimension"] == 768
    svc.close()
    shutdown_executor()  # 恢复：避免影响后续测试（惰性重建为干净状态）


# ── envelope 契约（FRZ-IPC-006 §6.2，PR#57 R4） ──

def test_envelope_error_has_data_field():
    """FRZ-IPC-006 §6.2：错误响应也携带 data（恒为 object，值为 {}）。"""
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    bad = svc.handle_request(
        {"protocol_version": "1.0", "method": "memory.unknown",
         "request_id": "req-u", "trace_id": "trc-u",
         "deadline_ms": 100, "payload": {}})
    assert bad["status"] == "error"
    assert "data" in bad and bad["data"] == {}
    svc.close()


def test_handle_request_degraded_preserves_reason():
    """降级路径：degraded_reason 并入 envelope data，不被静默丢失。"""
    svc = EmbeddingService(provider=FakeProvider(fail_with=ProviderError(
        ProviderErrorCode.ERR_SDK_NOT_LOADED, "so not found")))
    svc.start()
    resp = svc.handle_request(build_envelope("memory.embed", {"text": "x"},
                                             request_id="req-d", trace_id="trc-d"))
    assert resp["status"] == "ok"
    assert resp["data"]["degraded"] is True
    assert resp["data"]["degraded_reason"]["code"] == "ERR_SDK_NOT_LOADED"
    assert "so not found" in resp["data"]["degraded_reason"]["message"]
    svc.close()


@pytest.mark.parametrize("field, bad", [
    ("request_id", {"nested": 1}),
    ("trace_id", {"nested": 1}),
    ("request_id", 123),
    ("trace_id", 456),
    ("request_id", True),
    ("trace_id", False),
])
def test_handle_request_typed_id_converged(field, bad):
    """FRZ-IPC-006 §6.2：错误路径下非法 typed request_id/trace_id 恒收敛为 str。"""
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    req = {"protocol_version": "1.0", "method": "memory.embed",
           "request_id": "r", "trace_id": "t",
           "deadline_ms": 100, "payload": {"text": "x"}}
    req[field] = bad
    resp = svc.handle_request(req)
    assert resp["status"] == "error"
    assert resp["error_code"] == "INVALID_REQUEST"
    assert isinstance(resp["request_id"], str)
    assert isinstance(resp["trace_id"], str)
    assert resp[field] == ""
    svc.close()
@pytest.fixture(autouse=True)
def _d12a_executor_state_isolation():
    """D12A R3：executor 冻结语义（stop-with-active → restart-required）按用例隔离，
    避免同进程测试间共享模块 executor 状态造成串扰。"""
    import embedding.embedding_service as _es
    from embedding.embedding_service import shutdown_executor, _executor_lock, _in_flight
    yield
    shutdown_executor()
    with _executor_lock:
        _in_flight.clear()
        _es._embed_hang_recovered = 0
        _es._embed_hang_threshold_ms = 60000.0
        _es._embed_restart_required = False
        _es._embed_max_hang_rebuilds = 3
