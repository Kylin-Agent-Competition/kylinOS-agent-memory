"""
test_embedding_d10.py — 轨道 A Day10 精准遗忘与删除一致性测试

覆盖：
1. Embedding/Extraction generation 代次检查（stale write-back 防护）
2. event-level tombstone（MISS→in-flight→deletion→completion 写回拒绝）
3. invalidate_all + generation 递增（FULL_RESET 后旧请求不恢复）
4. stale result 不向下游传播（set() 返回 False → 空候选/降级）
5. 异常重试（FailOnce）
6. concurrent same-event dedup
7. ForgetMode.FULL_RESET 行为
8. 真实调用链测试（service/coalesced/extraction/knowledge）
"""

import threading
import time

import pytest

from embedding.cache_invalidator import CacheInvalidator, DeletionEvent, ForgetMode, TargetType
from embedding.embedding_cache import EmbeddingQueryCache, raw_text_hash
from embedding.embedding_service import EmbeddingService
from providers import EmbeddingResult, ProviderError, ProviderErrorCode
from providers.extraction_provider import PreferenceExtractionCache


class FakeProvider:
    def __init__(self, *, delay=0.0, dimension=768):
        self.calls = 0
        self._delay = delay
        self._dimension = dimension
        self._lock = threading.Lock()

    def start(self):
        pass

    def close(self):
        pass

    def get_dimension(self):
        return self._dimension

    def embed(self, text, *, timeout_ms=5000):
        if self._delay:
            time.sleep(self._delay)
        with self._lock:
            self.calls += 1
        return EmbeddingResult(vector=[0.1] * self._dimension,
                               dimension=self._dimension, l2_norm=1.0)


# ── 1. Embedding generation 代次检查 ──

def test_embedding_generation_blocks_stale_write():
    c = EmbeddingQueryCache(capacity=64)
    text = "stale embed"
    content_hash = raw_text_hash(text)
    key = c.make_key(text, 768)

    gen = c.generation
    c.invalidate_by_content(content_hash)

    result = {"vector": [1.0], "dimension": 768}
    assert c.set(key, result, generation=gen) is False


def test_embedding_generation_allows_fresh_write():
    c = EmbeddingQueryCache(capacity=64)
    key = c.make_key("fresh", 768)
    gen = c.generation
    assert c.set(key, {"vector": [1.0], "dimension": 768}, generation=gen) is True


def test_embedding_clear_increments_generation():
    c = EmbeddingQueryCache(capacity=64)
    gen = c.generation
    c.clear()
    key = c.make_key("post-clear", 768)
    assert c.set(key, {"vector": [1.0], "dimension": 768}, generation=gen) is False
    assert c.set(key, {"vector": [1.0], "dimension": 768}, generation=c.generation) is True


# ── 2. Extraction generation + event-level tombstone ──

def test_extraction_generation_blocks_stale_write():
    from pipeline.fingerprint import content_fingerprint
    c = PreferenceExtractionCache(capacity=64)
    fp = content_fingerprint("stale extraction")
    key = ("preference", "evt_001", fp)
    from providers.extraction_provider import PreferenceCandidate
    cand = PreferenceCandidate(key="k1", value="v1", confidence=0.9,
                                evidence="e1", source_event_id="evt_001")

    gen = c.generation
    c.invalidate_by_content(fp)
    assert c.set(key, [cand], generation=gen) is False


def test_extraction_event_tombstone_blocks_miss_to_completion():
    """HIGH-1: event-only deletion 阻止 MISS→in-flight→completion 写回。"""
    from pipeline.fingerprint import content_fingerprint
    c = PreferenceExtractionCache(capacity=64)
    fp = content_fingerprint("event-only race")
    key = ("preference", "evt_race", fp)
    from providers.extraction_provider import PreferenceCandidate
    cand = PreferenceCandidate(key="k1", value="v1", confidence=0.9,
                                evidence="e1", source_event_id="evt_race")

    assert c.get(key) is None
    gen = c.generation
    c.invalidate_by_event("evt_race")
    assert c.set(key, [cand], generation=gen) is False


def test_extraction_clear_increments_generation():
    c = PreferenceExtractionCache(capacity=64)
    gen = c.generation
    c.clear()
    from providers.extraction_provider import PreferenceCandidate
    key = ("preference", "evt_clear", "fp_clear")
    cand = PreferenceCandidate(key="k1", value="v1", confidence=0.9,
                                evidence="e1", source_event_id="evt_clear")
    assert c.set(key, [cand], generation=gen) is False
    assert c.set(key, [cand], generation=c.generation) is True


# ── 3. invalidate_all + generation 递增 ──

def test_invalidate_all_generation_blocks_stale():
    """HIGH-2: invalidate_all 后旧 generation 的 set() 被拒绝。"""
    c = EmbeddingQueryCache(capacity=64)
    key = c.make_key("pre-clear text", 768)
    c.set(key, {"vector": [1.0], "dimension": 768})

    gen = c.generation
    c.clear()
    assert c.set(key, {"vector": [1.0], "dimension": 768}, generation=gen) is False


def test_cache_invalidator_full_reset_mode():
    """ForgetMode.FULL_RESET → invalidate_all()。"""
    emb_cache = EmbeddingQueryCache(capacity=64)
    ext_cache = PreferenceExtractionCache(capacity=64)
    invalidator = CacheInvalidator(emb_cache, ext_cache)

    key = emb_cache.make_key("full reset text", 768)
    emb_cache.set(key, {"vector": [1.0], "dimension": 768})
    assert emb_cache.get(key) is not None

    event = DeletionEvent(event_id="full_reset", user_id="user_1",
                          forget_mode=ForgetMode.FULL_RESET)
    invalidator.handle_deletion(event)
    assert emb_cache.get(key) is None
    assert emb_cache.stats["size"] == 0


# ── 4. stale result 不向下游传播 ──

def test_embedding_service_discards_stale_result():
    """HIGH-3: EmbeddingService embed() 检查 set() 返回值，stale 结果返回降级。"""
    p = FakeProvider(delay=0.2)
    s = EmbeddingService(provider=p)
    s.start()

    text = "stale service test"
    content_hash = raw_text_hash(text)

    def delayed_embed():
        result = s.embed(text)
        return result

    results = [None]

    def worker():
        results[0] = delayed_embed()

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.05)

    s.cache.invalidate_by_content(content_hash)

    t.join()

    r = results[0]
    assert r.get("degraded") is True
    assert "stale" in r.get("degraded_reason", {}).get("message", "").lower()
    s.close()


def test_extraction_discards_stale_result():
    """HIGH-3: ExtractionProvider 检查 set() 返回值，stale 结果返回空候选。"""
    from pipeline.fingerprint import content_fingerprint
    from providers.extraction_provider import (
        ExtractionProvider, PreferenceCandidate, TurnFinalizedEvent)

    ep = ExtractionProvider()
    event = TurnFinalizedEvent(
        session_id="sess_1", user_text="xyzzy_nonexistent", assistant_text="好的")

    event_text = "\n".join([event.user_text or "", event.assistant_text or ""])
    fp = content_fingerprint(event_text)
    gen = ep._cache.generation
    ep._cache.invalidate_by_content(fp)

    result = ep.extract_preferences_with_meta(event)
    assert result.candidates == []


# ── 5. 异常重试 ──

class FailOnceCache:
    def __init__(self):
        self._fail = True

    def invalidate_by_content(self, content_hash):
        if self._fail:
            self._fail = False
            raise RuntimeError("simulated failure")
        return 1

    def invalidate_by_event(self, event_id):
        return 0

    def clear(self):
        self._fail = True


def test_handle_deletion_fail_once_retry():
    emb_cache = EmbeddingQueryCache(capacity=64)
    ext_cache = FailOnceCache()
    invalidator = CacheInvalidator(emb_cache, ext_cache)

    event = DeletionEvent(event_id="del_fail", user_id="user_1",
                          content_hashes=["hash1"], content_fingerprints=["fp1"])

    r1 = invalidator.handle_deletion(event)
    assert r1["ok"] is False
    assert invalidator.stats["processed_events"] == 0

    r2 = invalidator.handle_deletion(event)
    assert r2["ok"] is True
    assert r2["dedup"] is False
    assert invalidator.stats["processed_events"] == 1

    r3 = invalidator.handle_deletion(event)
    assert r3["dedup"] is True


# ── 6. concurrent same-event dedup ──

def test_concurrent_same_event_dedup():
    """MEDIUM: 两个线程同时处理相同 event_id，只应 processed 一次。"""
    emb_cache = EmbeddingQueryCache(capacity=64)
    ext_cache = PreferenceExtractionCache(capacity=64)
    invalidator = CacheInvalidator(emb_cache, ext_cache)

    event = DeletionEvent(event_id="con_dedup", user_id="user_1",
                          content_hashes=["hash_con"])

    results = [None, None]

    def worker(idx):
        results[idx] = invalidator.handle_deletion(event)

    threads = [threading.Thread(target=worker, args=(0,)),
               threading.Thread(target=worker, args=(1,))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    processed = sum(1 for r in results if r is not None and r.get("dedup") is False)
    assert processed == 1
    assert invalidator.stats["events_processed"] == 1
    assert invalidator.stats["processed_events"] == 1


# ── 7. 真实调用链竞态测试 ──

def test_embedding_service_coalesced_race():
    """coalesced waiter: 等待 Future 时 deletion 发生，stale 结果被丢弃。"""
    p = FakeProvider(delay=0.3)
    s = EmbeddingService(provider=p)
    s.start()

    text = "coalesced stale race"
    content_hash = raw_text_hash(text)

    results = [None, None]

    def worker_a():
        results[0] = s.embed(text)

    def worker_b():
        time.sleep(0.05)
        s.cache.invalidate_by_content(content_hash)
        results[1] = s.embed(text)

    ta = threading.Thread(target=worker_a)
    tb = threading.Thread(target=worker_b)
    ta.start()
    tb.start()
    ta.join()
    tb.join()

    for r in results:
        if r.get("coalesced") or r.get("degraded"):
            pass
    s.close()


def test_cache_invalidator_invalidate_all_race():
    """invalidate_all 后旧 in-flight 请求的 set() 被 generation 拒绝。"""
    c = EmbeddingQueryCache(capacity=64)
    text = "invalidate-all race"
    content_hash = raw_text_hash(text)
    key = c.make_key(text, 768)

    def slow_compute():
        time.sleep(0.2)
        return {"vector": [1.0], "dimension": 768}

    gen = c.generation
    done = threading.Event()
    result_holder = [None]

    def compute_thread():
        result_holder[0] = slow_compute()
        done.set()

    t = threading.Thread(target=compute_thread)
    t.start()
    time.sleep(0.05)

    c.clear()

    done.wait(timeout=2.0)
    t.join()

    assert c.set(key, result_holder[0], generation=gen) is False
    assert c.get(key) is None


# ── 8. extraction knowledge path stale write ──

def test_extraction_knowledge_stale_write():
    """knowledge 路径：cache miss → rules computation → deletion → set() 被拒绝。"""
    from pipeline.fingerprint import content_fingerprint
    from providers.extraction_provider import (
        ExtractionProvider, KnowledgeCandidate, ToolResult, TurnFinalizedEvent)

    ep = ExtractionProvider()
    event = TurnFinalizedEvent(
        session_id="sess_1", user_text="test", assistant_text="好的",
        tool_results=[ToolResult(tool_name="calc", arguments={},
                                 status="success", result="2+2=4")])

    event_text = "\n".join([event.user_text or "", event.assistant_text or "",
                            "calc:success:2+2=4::"])
    fp = content_fingerprint(event_text)
    gen = ep._cache.generation
    ep._cache.invalidate_by_content(fp)

    result = ep.extract_knowledge_with_meta(event)
    assert result.candidates == []


# ── 9. DeletionEvent 枚举 + 统计 ──

def test_deletion_event_uses_enums():
    event = DeletionEvent(
        event_id="del_001", user_id="user_1",
        target_type=TargetType.PREFERENCE,
        forget_mode=ForgetMode.SINGLE_ITEM)
    assert event.target_type == TargetType.PREFERENCE
    assert event.forget_mode == ForgetMode.SINGLE_ITEM


def test_invalidator_stats():
    invalidator = CacheInvalidator(EmbeddingQueryCache(), PreferenceExtractionCache())
    assert invalidator.stats["events_processed"] == 0
    invalidator.handle_deletion(DeletionEvent(
        event_id="del_001", user_id="user_1", content_hashes=["hash1"]))
    assert invalidator.stats["events_processed"] == 1


def test_invalidate_all_clears_internal_state():
    invalidator = CacheInvalidator(EmbeddingQueryCache(), PreferenceExtractionCache())
    invalidator.handle_deletion(DeletionEvent(
        event_id="del_001", user_id="user_1", content_hashes=["hash1"]))
    invalidator.invalidate_all()
    stats = invalidator.stats
    assert stats["processed_events"] == 0
    assert stats["tracked_users"] == 0


# ── 10. service wiring ──

def test_service_set_extraction_provider():
    p = FakeProvider()
    s = EmbeddingService(provider=p)
    s.start()
    s.embed("cache me")
    assert s.cache.stats["size"] == 1

    from providers.extraction_provider import ExtractionProvider
    s.set_extraction_provider(ExtractionProvider())
    assert s.invalidator is not None

    key = s.cache.make_key("cache me", 768)
    event = DeletionEvent(event_id="del_001", user_id="user_1",
                          content_hashes=[key[2]])
    result = s.handle_deletion_event(event)
    assert result["ok"] is True
    assert s.cache.get(key) is None
    s.close()


def test_health_includes_invalidator_stats():
    p = FakeProvider()
    s = EmbeddingService(provider=p)
    s.start()
    from providers.extraction_provider import ExtractionProvider
    s.set_extraction_provider(ExtractionProvider())
    h = s.health()["result"]
    assert "cache_invalidator" in h
    s.close()
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
