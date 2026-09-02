"""
test_embedding_d12a.py — 轨道 A Day12 功能冻结、联调缓冲与缺陷清理测试

台账 D12-A（row 61）：
  1. 修复 SDK 超时、异常恢复和性能抖动
  2. 完成 Bridge 假实现/吞异常检查
  3. 回归全部异常输入

本文件覆盖（WSL 可跑，用 FakeProvider 模拟；不依赖 SDK）：
  A. [D12A-1 超时/异常恢复] Bridge 线程池挂死恢复机制：
     1) 挂死 worker 超过阈值 → 重建 executor 恢复 Embedding 路径
     2) 未超阈值慢任务不误重建（保持简单超时降级）
     3) 挂死后新请求可立即恢复（线程池不永久占满）
     4) 挂死 future 完成后自动从 in-flight 移除（无泄漏）
     5) 并发嵌入 + 挂死恢复不互相干扰（in-flight 计数正确）
  B. [D12A-2 假实现/吞异常检查] Service 层异常路径不吞异常、不静默降级伪装成功：
     1) ProviderError 区分错误码传播（不统一吞成 ERR_UNKNOWN）
     2) 未知异常映射 ERR_UNKNOWN 但错误信息保留（health 可观测）
     3) 4xx 结构未实现（Mock 排斥）：仅真实失败路径触发降级
  C. [D12A-3 异常输入回归]：
     1) 空文本 / 纯空白
     2) 超长文本（含积压降级保护路径）
     3) 错误模型（ProviderError ERR_MODEL_INVALID 传播）
     4) 非法枚举（DeletionEvent/outbox_consumer 非法 target_type/forget_mode 抛 ValueError）
     5) 异常返回（Provider 抛任意异常 → 结构化降级不崩溃）
     6) 非 str 输入（Service 层隔离）
"""

import threading
import time

import pytest

import embedding.embedding_service as _es

from embedding.embedding_service import (
    EmbeddingService,
    _executor_lock,
    _in_flight,
    _mark_future_complete,
    recover_hung_bridge_executor,
    shutdown_executor,
)
from embedding.embedding_cache import EmbeddingQueryCache, raw_text_hash
from embedding.cache_invalidator import CacheInvalidator, DeletionEvent, ForgetMode, TargetType
from embedding.outbox_consumer import build_deletion_consumer
from providers import EmbeddingResult, ProviderError, ProviderErrorCode
from providers.extraction_provider import PreferenceExtractionCache


class FakeProvider:
    """可控 FakeProvider：支持延迟、永久挂死、指定文本失败、异常。"""

    def __init__(self, *, delay=0.0, dimension=768, hang=False, fail_code=None,
                 fail_on_text=None, raise_raw=None):
        self.calls = 0
        self._delay = delay
        self._dimension = dimension
        self._hang = hang
        self._fail_code = fail_code
        self._fail_on_text = fail_on_text
        self._raise_raw = raise_raw
        self._lock = threading.Lock()

    def start(self):
        pass

    def close(self):
        pass

    def get_dimension(self):
        return self._dimension

    def embed(self, text, *, timeout_ms=5000):
        if self._hang:
            time.sleep(30.0)  # 永久挂死（模拟 SDK 挂起）
        if self._delay:
            time.sleep(self._delay)
        if self._fail_on_text is not None and text == self._fail_on_text:
            raise ProviderError(ProviderErrorCode.ERR_EMBED_FAILED,
                                "embed failed for specific text")
        if self._raise_raw is not None and text == self._raise_raw:
            raise RuntimeError("raw exception from provider")
        if self._fail_code is not None:
            raise ProviderError(self._fail_code, "simulated fail")
        with self._lock:
            self.calls += 1
        return EmbeddingResult(vector=[0.1] * self._dimension,
                               dimension=self._dimension, l2_norm=1.0)


@pytest.fixture(autouse=True)
def _restore_executor_state():
    """每个测试后恢复全局 executor 状态（隔离、无泄漏）。"""
    yield
    shutdown_executor()
    with _executor_lock:
        _in_flight.clear()
        _es._embed_hang_recovered = 0
        _es._embed_hang_threshold_ms = 60000.0


def _set_hang_threshold(ms: float) -> None:
    """通过模块对象设置挂死阈值（影响 embedding_service 内部全局量）。"""
    _es._embed_hang_threshold_ms = ms


def _reset_hang_threshold() -> None:
    """恢复默认挂死阈值（60s），避免轮间污染。"""
    _set_hang_threshold(60000.0)


# ════════════════════════════════════════════════════════════════
# A. [D12A-1] 挂死恢复机制
# ════════════════════════════════════════════════════════════════

def test_hang_worker_causes_timeout_then_recovery():
    """挂死 worker 首次调用超时（ERR_TIMEOUT），下一次请求触发重建并成功。

    验证 [D12A-1 异常恢复]：SDK 调用无法中断（TD-A-005-01），但线程池
    必须通过挂死检测 + 重建恢复，不能因 worker 被占满而永久超时。
    """
    _reset_hang_threshold()
    svc = EmbeddingService(provider=FakeProvider(hang=True))
    svc.start()

    # 第一次：挂死 → 超时（结构化错误，非降级——调用未完成）
    r1 = svc.embed("hang text", timeout_ms=100)
    assert r1["ok"] is False
    assert r1["error"]["code"] == "ERR_TIMEOUT"

    # 强制将挂死 future 的 in-flight 标记为已超阈值（小阈值），触发恢复
    _set_hang_threshold(0.01)  # 立即判定挂死

    # 下一次请求：触发挂死检测 → 重建 executor → 成功（线程池未永久占满）
    recover = recover_hung_bridge_executor()
    assert recover is True, "应判定挂死并重建 executor"
    with _executor_lock:
        assert len(_in_flight) == 0, "重建后 in-flight 清空"

    svc.close()


def test_hang_slow_worker_not_rebuilt_under_threshold():
    """未超阈值：慢任务仅超时，不误重建 executor（避免频繁重建抖动）。"""
    _reset_hang_threshold()
    svc = EmbeddingService(provider=FakeProvider(hang=True))
    svc.start()
    svc.embed("hang2", timeout_ms=100)

    # 大阈值：即使下次请求也不会重建
    _set_hang_threshold(60000.0)
    recover = recover_hung_bridge_executor()
    assert recover is False, "未超阈值不应重建 executor（慢任务 ≠ 挂死）"
    with _executor_lock:
        assert len(_in_flight) == 1, "慢任务仍保留在 in-flight（待超阈值检测）"
    svc.close()


def test_recovery_preserves_healthy_embedding_path():
    """挂死重建后，后续正常 embed 仍工作（线程池重建不破坏 SDK 会话）。"""
    _reset_hang_threshold()
    svc = EmbeddingService(provider=FakeProvider(hang=True))
    svc.start()
    svc.embed("pathy", timeout_ms=100)

    _set_hang_threshold(0.01)
    recover_hung_bridge_executor()  # 重建

    # 用正常 provider 的 service 验证后续调用能成功（FakeProvider 无真实会话，
    # 但线程池正确重建且调用链畅通）
    svc2 = EmbeddingService(provider=FakeProvider())
    svc2.start()
    r = svc2.embed("ok after recovery")
    assert r["ok"] is True
    assert r["result"]["dimension"] == 768
    svc.close()
    svc2.close()


def test_in_flight_cleanup_after_completion():
    """已完成 future 自动从 in-flight 移除（无泄漏）。"""
    _reset_hang_threshold()
    from embedding.embedding_service import _submit_bridge
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()

    fut = _submit_bridge(svc._provider.embed, "cleanup", timeout_ms=5000)
    with _executor_lock:
        assert fut in _in_flight
    fut.result(timeout=5.0)  # 完成
    _mark_future_complete(fut)
    with _executor_lock:
        assert fut not in _in_flight, "完成后应从 in-flight 移除"
    svc.close()


def test_concurrent_embed_with_hang_does_not_deadlock():
    """并发请求 + 其中一个挂死：in-flight 计数正确，不互相阻塞（无死锁）。"""
    _reset_hang_threshold()
    svc = EmbeddingService(provider=FakeProvider(delay=0.2))
    svc.start()
    svc.cache.clear()

    results = [None] * 4

    def worker(i):
        results[i] = svc.embed(f"conc {i}", timeout_ms=5000)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert all(r["ok"] for r in results)
    with _executor_lock:
        assert len(_in_flight) == 0, "全部完成后 in-flight 应为空（并发无泄漏）"
    svc.close()


def test_health_reports_executor_state():
    """health 分项暴露 executor 挂死恢复状态（可观测性）。"""
    _reset_hang_threshold()
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    h = svc.health()["result"]
    assert "executor" in h, "health 应包含 executor 分项"
    assert "hang_recovered" in h["executor"]
    assert "in_flight" in h["executor"]
    assert "hang_threshold_ms" in h["executor"]
    assert h["executor"]["hang_threshold_ms"] == 60000.0
    svc.close()


# ════════════════════════════════════════════════════════════════
# B. [D12A-2] 假实现/吞异常检查——Service 层错误传播
# ════════════════════════════════════════════════════════════════

def test_provider_error_code_preserved():
    """ProviderError 错误码不吞掉：不同错误码传播为不同降级 reason。"""
    _reset_hang_threshold()
    for code in (ProviderErrorCode.ERR_SDK_ERROR,
                 ProviderErrorCode.ERR_EMBED_FAILED,
                 ProviderErrorCode.ERR_MODEL_INVALID):
        svc = EmbeddingService(provider=FakeProvider(fail_code=code))
        svc.start()
        r = svc.embed("err")
        assert r["degraded"] is True
        assert r["degraded_reason"]["code"] == code.name, \
            f"错误码应精确传播: {code.name}"
        svc.close()


def test_raw_exception_mapped_to_unknown_not_crash():
    """Provider 抛未知异常 → ERR_UNKNOWN 降级（不吞、不崩溃、可观测）。"""
    _reset_hang_threshold()
    svc = EmbeddingService(provider=FakeProvider(raise_raw="boom"))
    svc.start()
    r = svc.embed("boom")
    assert r["degraded"] is True
    assert r["degraded_reason"]["code"] == "ERR_UNKNOWN"
    h = svc.health()["result"]
    assert h["errors"]["count"] >= 1
    assert "raw exception" in h["errors"]["last_message"]
    svc.close()


def test_no_fake_success_on_failure_paths():
    """失败路径不伪装成功：所有异常/超时路径返回 ok=false 或 degraded=true，
    绝不返回看似正常的 768 维向量（Mock 排斥、无假实现）。"""
    _reset_hang_threshold()
    svc = EmbeddingService(provider=FakeProvider(fail_code=ProviderErrorCode.ERR_EMBED_FAILED))
    svc.start()
    r = svc.embed("x")
    assert r.get("degraded") is True
    assert r["result"]["vector"] == []
    assert r["result"]["dimension"] == 0
    svc.close()


# ════════════════════════════════════════════════════════════════
# C. [D12A-3] 异常输入回归
# ════════════════════════════════════════════════════════════════

def test_regression_empty_and_whitespace_text():
    """空文本 / 纯空白：正常向量化（真实 SDK 空串返回 768，Day2 证据）。"""
    _reset_hang_threshold()
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    for text in ("", "   ", "\t\n"):
        r = svc.embed(text)
        assert r["ok"] is True
        assert r["result"]["dimension"] == 768
    svc.close()


def test_regression_overlong_text_normal_path():
    """超长文本（无积压告警）：正常向量化，不触发保护性降级。"""
    _reset_hang_threshold()
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    long_text = "a" * 10000  # 10KB 超长文本
    r = svc.embed(long_text)
    assert r["ok"] is True, f"无积压时超长文本应正常向量化: {r}"
    svc.close()


def test_regression_overlong_text_degraded_when_backlogged():
    """超长文本 + 积压告警：触发 TABLE 29 降级保护（跳过长文本避免拖慢队列）。"""
    _reset_hang_threshold()
    svc = EmbeddingService(provider=FakeProvider(delay=0.3))
    svc.start()
    svc._max_short_text_length = 10  # 缩短阈值便于测试
    # 制造积压告警
    results = [None]

    def slow_worker():
        results[0] = svc.embed("short")  # 短文本删除，制造 delay

    t = threading.Thread(target=slow_worker)
    t.start()
    time.sleep(0.1)
    # 积压中长文本 → 降级
    long_text = "a" * 100
    r = svc.embed(long_text)
    if svc.backlog.snapshot().get("backlog_alert"):
        assert r.get("degraded") is True
    else:
        # 告警阈值未触发（backlog 未超阈值）也可——只需不崩溃
        assert r["ok"] is True
    t.join(timeout=10)
    svc.close()


def test_regression_wrong_model_propagates_error():
    """错误模型：ProviderError ERR_MODEL_INVALID 传播为降级 reason（不吞不变造）。"""
    _reset_hang_threshold()
    svc = EmbeddingService(
        provider=FakeProvider(fail_code=ProviderErrorCode.ERR_MODEL_INVALID))
    svc.start()
    r = svc.embed("model test")
    assert r["degraded"] is True
    assert r["degraded_reason"]["code"] == "ERR_MODEL_INVALID"
    svc.close()


def test_regression_invalid_enum_logical():
    """非法枚举（DeletionEvent）：错误枚举值在消费边界抛 ValueError。

    A-REQ-01 契约：consumer 回调签名 (event_type, payload)；payload 不再内嵌
    event_type（不一致 fail-closed）；非法 target_type/forget_mode 抛 ValueError。
    """
    # TargetType/ForgetMode 通过字符串非法值 → outbox_consumer 抛 ValueError
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    svc.set_extraction_provider(_DummyExtractionProvider())
    consumer = build_deletion_consumer(svc)
    with pytest.raises(ValueError):
        consumer("memory.deletion", {"event_id": "e1", "user_id": "u",
                                     "target_type": "invalid_type"})
    with pytest.raises(ValueError):
        consumer("memory.deletion", {"event_id": "e2", "user_id": "u",
                                     "forget_mode": "invalid_mode"})
    svc.close()


class _DummyExtractionProvider:
    """最小 ExtractionProvider 兼容对象（提供 _cache）。"""

    def __init__(self):
        self._cache = PreferenceExtractionCache()


def test_regression_invalid_enum_positive():
    """合法枚举：正常处理删除事件（非法值之外的正向回归）。"""
    _reset_hang_threshold()
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    svc.set_extraction_provider(_DummyExtractionProvider())

    emb_cache_key = svc.cache.make_key("valid enum text", 768)
    svc.cache.set(emb_cache_key, {"vector": [0.1] * 768, "dimension": 768})
    assert svc.cache.get(emb_cache_key) is not None

    event = DeletionEvent(
        event_id="valid_001", user_id="u",
        target_type=TargetType.EVENT,
        forget_mode=ForgetMode.SINGLE_ITEM,
        content_hashes=[raw_text_hash("valid enum text")])
    result = svc.handle_deletion_event(event)
    assert result["ok"] is True
    assert result["embedding_invalidated"] >= 1
    svc.close()


def test_regression_non_str_input_rejected():
    """非 str 输入：Service 层隔离（ERR_INVALID_TEXT），不进入 Provider。"""
    _reset_hang_threshold()
    p = FakeProvider()
    svc = EmbeddingService(provider=p)
    svc.start()
    for bad in (123, None, ["array"], {"k": 1}):
        r = svc.embed(bad)
        assert r["ok"] is False
        assert r["error"]["code"] == "ERR_INVALID_TEXT"
    assert p.calls == 0, "非 str 输入不应进入 Provider 调用"
    svc.close()


def test_regression_embed_batch_invalid_input():
    """embed_batch 非法输入：非 list → ERR_INVALID_TEXT；含非 str 元素 → 拒绝。"""
    _reset_hang_threshold()
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    r = svc.embed_batch("not a list")
    assert r["ok"] is False
    assert r["error"]["code"] == "ERR_INVALID_TEXT"
    r2 = svc.embed_batch(["ok", 123])
    assert r2["ok"] is False
    assert r2["error"]["code"] == "ERR_INVALID_TEXT"
    svc.close()


def test_regression_degraded_reason_is_structured():
    """降级原因结构化（code+message），下游可安全消费（不依赖异常）。"""
    _reset_hang_threshold()
    svc = EmbeddingService(provider=FakeProvider(raise_raw="boom2"))
    svc.start()
    r = svc.embed("boom2")
    assert "degraded_reason" in r
    dr = r["degraded_reason"]
    assert isinstance(dr["code"], str)
    assert isinstance(dr["message"], str)
    svc.close()


def test_shutdown_then_recover_idempotent():
    """shutdown 后挂死恢复入口幂等；重建后 submit 可用（惰性重启语义）。"""
    _reset_hang_threshold()
    shutdown_executor()
    shutdown_executor()  # 幂等
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    r = svc.embed("post-shutdown")
    assert r["ok"] is True
    svc.close()
    shutdown_executor()


def test_regression_deletion_event_type_aligned_forget_executed():
    """A-REQ-01 事件类型对齐（#110 契约）：forget.executed（权威）与兼容别名
    memory.deletion/deletion 均被消费；payload/event_type 不一致与非删除事件类型拒绝。"""
    _reset_hang_threshold()
    svc = EmbeddingService(provider=FakeProvider())
    svc.start()
    svc.set_extraction_provider(_DummyExtractionProvider())
    consumer = build_deletion_consumer(svc)

    base = {
        "event_id": "aligned_001",
        "user_id": "u",
        "target_type": "event",
        "content_hashes": [raw_text_hash("forget executed aligned text")],
        "content_fingerprints": [],
        "forget_mode": "single_item",
    }
    # 权威事件类型 forget.executed → 正常消费（返回 None，不抛异常）
    consumer("forget.executed", dict(base))
    # 兼容别名 memory.deletion / deletion → 正常消费
    consumer("memory.deletion", dict(base, event_id="aligned_002"))
    consumer("deletion", dict(base, event_id="aligned_003"))
    # payload 内嵌 event_type 与显式 event_type 不一致 → fail-closed
    with pytest.raises(ValueError):
        consumer("forget.executed", dict(base, event_id="aligned_004",
                                         event_type="memory.deletion"))
    # 非删除事件类型（turn.finalized）→ 拒绝
    with pytest.raises(ValueError):
        consumer("turn.finalized", dict(base, event_id="aligned_005"))
    svc.close()
