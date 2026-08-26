"""
test_embedding_d10.py — 轨道 A Day10 精准遗忘与删除一致性测试

台账 R52（A 轨 D10）：删除后 Provider 缓存和临时数据不恢复目标正文

覆盖：
1. Embedding 缓存按内容指纹失效 + tombstone stale-write 防护
2. Extraction 缓存按事件 ID / 内容指纹失效 + tombstone 防护
3. CacheInvalidator 删除事件处理（幂等/失败重试/按用户/全量）
4. 真实竞态测试：owner + coalesced 双路径 stale write-back 防护
5. Extraction/LLM 路径 stale write-back 防护
6. 异常重试：FailOnce 模拟失效失败后重试
7. 并发删除与读取 + 真实 Extraction cache 接线
"""

import threading
import time

import pytest

from embedding.cache_invalidator import CacheInvalidator, DeletionEvent, ForgetMode, TargetType
from embedding.embedding_cache import EmbeddingQueryCache, raw_text_hash
from embedding.embedding_service import EmbeddingService
from providers import EmbeddingResult, ProviderError, ProviderErrorCode
from providers.extraction_provider import PreferenceExtractionCache


# ── helpers ──

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


# ── 1. EmbeddingQueryCache tombstone stale-write 防护 ──

def test_embedding_cache_tombstone_blocks_stale_write():
    """删除后旧 Provider 返回时 set() 被 tombstone 拒绝。"""
    c = EmbeddingQueryCache(capacity=64)
    text = "stale write-back test"
    content_hash = raw_text_hash(text)
    key = c.make_key(text, 768)

    # 模拟：cache miss → Provider in-flight → deletion → Provider 返回
    c.set(key, {"vector": [1.0], "dimension": 768})
    assert c.get(key) is not None

    c.invalidate_by_content(content_hash)
    assert c.get(key) is None

    # 旧 Provider 返回，尝试写回 → tombstone 拒绝
    result = c.set(key, {"vector": [1.0], "dimension": 768})
    assert result is False
    assert c.get(key) is None


def test_embedding_cache_tombstone_allows_fresh_write():
    """tombstone 只阻止失效内容的写回，新内容不受影响。"""
    c = EmbeddingQueryCache(capacity=64)
    key1 = c.make_key("deleted text", 768)
    key2 = c.make_key("fresh text", 768)

    c.invalidate_by_content(raw_text_hash("deleted text"))
    assert c.set(key1, {"vector": [1.0], "dimension": 768}) is False
    assert c.set(key2, {"vector": [2.0], "dimension": 768}) is True
    assert c.get(key2) is not None


def test_embedding_cache_clear_clears_tombstones():
    """clear() 清空 tombstone，后续写入恢复正常。"""
    c = EmbeddingQueryCache(capacity=64)
    key = c.make_key("test", 768)
    c.invalidate_by_content(raw_text_hash("test"))
    assert c.set(key, {"vector": [1.0], "dimension": 768}) is False
    c.clear()
    assert c.set(key, {"vector": [1.0], "dimension": 768}) is True


# ── 2. Extraction cache tombstone stale-write 防护 ──

def test_extraction_cache_tombstone_blocks_stale_write():
    from pipeline.fingerprint import content_fingerprint
    c = PreferenceExtractionCache(capacity=64)
    fp = content_fingerprint("stale extraction")
    key = ("preference", "evt_001", fp)
    from providers.extraction_provider import PreferenceCandidate
    cand = PreferenceCandidate(key="k1", value="v1", confidence=0.9,
                                evidence="e1", source_event_id="evt_001")

    c.set(key, [cand])
    assert c.get(key) is not None

    c.invalidate_by_content(fp)
    assert c.get(key) is None

    result = c.set(key, [cand])
    assert result is False
    assert c.get(key) is None


def test_extraction_cache_invalidate_by_event_adds_tombstone():
    from pipeline.fingerprint import content_fingerprint
    c = PreferenceExtractionCache(capacity=64)
    fp = content_fingerprint("evt content")
    key = ("preference", "evt_001", fp)
    from providers.extraction_provider import PreferenceCandidate
    cand = PreferenceCandidate(key="k1", value="v1", confidence=0.9,
                                evidence="e1", source_event_id="evt_001")
    c.set(key, [cand])

    c.invalidate_by_event("evt_001")
    assert c.get(key) is None

    result = c.set(key, [cand])
    assert result is False


# ── 3. CacheInvalidator 核心修复 ──

def test_handle_deletion_processed_after_success():
    """processed 必须在全部失效成功后登记。"""
    emb_cache = EmbeddingQueryCache(capacity=64)
    ext_cache = PreferenceExtractionCache(capacity=64)
    invalidator = CacheInvalidator(emb_cache, ext_cache)

    event = DeletionEvent(event_id="del_001", user_id="user_1",
                          content_hashes=["hash1"])
    result = invalidator.handle_deletion(event)
    assert result["ok"] is True
    assert result["dedup"] is False

    stats = invalidator.stats
    assert stats["processed_events"] == 1
    assert stats["events_processed"] == 1


def test_handle_deletion_idempotent_after_success():
    """成功后再调用相同 event_id → dedup。"""
    invalidator = CacheInvalidator(EmbeddingQueryCache(), PreferenceExtractionCache())
    event = DeletionEvent(event_id="del_001", user_id="user_1",
                          content_hashes=["hash1"])
    r1 = invalidator.handle_deletion(event)
    assert r1["dedup"] is False
    r2 = invalidator.handle_deletion(event)
    assert r2["dedup"] is True


class FailOnceCache:
    """模拟失效一次失败、第二次成功的缓存（用于测试重试）。"""
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
    """失效失败时同 event_id 可重试，成功后再调用才 dedup。"""
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


def test_invalidate_all_clears_internal_state():
    invalidator = CacheInvalidator(EmbeddingQueryCache(), PreferenceExtractionCache())
    event = DeletionEvent(event_id="del_001", user_id="user_1",
                          content_hashes=["hash1"])
    invalidator.handle_deletion(event)
    assert invalidator.stats["processed_events"] == 1

    invalidator.invalidate_all()
    stats = invalidator.stats
    assert stats["processed_events"] == 0
    assert stats["events_processed"] == 0
    assert stats["tracked_users"] == 0


# ── 4. 真实竞态测试：stale write-back 防护 ──

def test_stale_write_back_owner_request_blocked():
    """owner request: cache miss → deletion → Provider returns → write blocked."""
    c = EmbeddingQueryCache(capacity=64)
    text = "race condition text"
    content_hash = raw_text_hash(text)
    key = c.make_key(text, 768)

    done = threading.Event()

    def slow_embed():
        time.sleep(0.2)
        return {"vector": [1.0], "dimension": 768}

    # 模拟：cache miss（从未 set）
    assert c.get(key) is None

    # 启动慢 Provider 调用
    provider_result = [None]

    def provider_thread():
        provider_result[0] = slow_embed()
        done.set()

    t = threading.Thread(target=provider_thread)
    t.start()

    time.sleep(0.05)  # 确保 Provider 已进入 in-flight
    c.invalidate_by_content(content_hash)  # deletion

    done.wait(timeout=2.0)
    t.join()

    # Provider 返回后尝试写回 → tombstone 拒绝
    result = c.set(key, provider_result[0])
    assert result is False
    assert c.get(key) is None


def test_stale_write_back_coalesced_waiter_blocked():
    """coalesced waiter: 同文本并发请求合并，删除后写回被 tombstone 拒绝。"""
    c = EmbeddingQueryCache(capacity=64)
    text = "coalesced race"
    content_hash = raw_text_hash(text)
    key = c.make_key(text, 768)

    from embedding.embedding_cache import EmbeddingCoalescer
    coalescer = EmbeddingCoalescer()
    coalesce_key = content_hash

    import concurrent.futures

    def slow_embed():
        time.sleep(0.3)
        return {"vector": [1.0], "dimension": 768}

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(slow_embed)
        coalescer.register(coalesce_key, future)

        # deletion 发生（在 Future 完成前）
        c.invalidate_by_content(content_hash)

        # 合并等待者获取 Future 结果
        existing, merged = coalescer.get_or_create(coalesce_key)
        assert merged is True
        result = existing.result(timeout=2.0)
        coalescer.release(coalesce_key, existing)

        # 写回 → tombstone 拒绝
        write_ok = c.set(key, result)
        assert write_ok is False
        assert c.get(key) is None


def test_stale_write_back_extraction_path_blocked():
    """Extraction 路径：cache miss → rules/LLM 计算 → deletion → set() 被拒绝。"""
    from pipeline.fingerprint import content_fingerprint
    c = PreferenceExtractionCache(capacity=64)
    fp = content_fingerprint("extraction race")
    key = ("preference", "evt_race", fp)
    from providers.extraction_provider import PreferenceCandidate
    cand = PreferenceCandidate(key="k1", value="v1", confidence=0.9,
                                evidence="e1", source_event_id="evt_race")

    def slow_compute():
        time.sleep(0.2)
        return [cand]

    done = threading.Event()
    result_holder = [None]

    def compute_thread():
        result_holder[0] = slow_compute()
        done.set()

    t = threading.Thread(target=compute_thread)
    t.start()

    time.sleep(0.05)
    c.invalidate_by_content(fp)

    done.wait(timeout=2.0)
    t.join()

    result = c.set(key, result_holder[0])
    assert result is False
    assert c.get(key) is None


# ── 5. CacheInvalidator stateless 验证 ──

def test_invalidator_stats():
    invalidator = CacheInvalidator(EmbeddingQueryCache(), PreferenceExtractionCache())
    assert invalidator.stats["events_processed"] == 0
    assert invalidator.stats["tracked_users"] == 0

    invalidator.handle_deletion(DeletionEvent(
        event_id="del_001", user_id="user_1", content_hashes=["hash1"]))
    invalidator.handle_deletion(DeletionEvent(
        event_id="del_002", user_id="user_1", content_hashes=["hash2"]))

    stats = invalidator.stats
    assert stats["events_processed"] == 2
    assert stats["tracked_users"] == 1


# ── 6. DeletionEvent 枚举验证 ──

def test_deletion_event_uses_enums():
    event = DeletionEvent(
        event_id="del_001", user_id="user_1",
        target_type=TargetType.PREFERENCE,
        forget_mode=ForgetMode.SINGLE_ITEM)
    assert event.target_type == TargetType.PREFERENCE
    assert event.forget_mode == ForgetMode.SINGLE_ITEM


# ── 7. EmbeddingService 接线验证 ──

def test_service_set_extraction_provider():
    p = FakeProvider()
    s = EmbeddingService(provider=p)
    s.start()
    s.embed("cache me")
    assert s.cache.stats["size"] == 1

    from providers.extraction_provider import ExtractionProvider
    ep = ExtractionProvider()
    s.set_extraction_provider(ep)
    assert s.invalidator is not None

    key = s.cache.make_key("cache me", 768)
    event = DeletionEvent(event_id="del_001", user_id="user_1",
                          content_hashes=[key[2]])
    result = s.handle_deletion_event(event)
    assert result["ok"] is True
    assert s.cache.get(key) is None
    s.close()


def test_service_handle_deletion_event_before_set():
    s = EmbeddingService()
    event = DeletionEvent(event_id="del_001", user_id="user_1",
                          content_hashes=["hash1"])
    result = s.handle_deletion_event(event)
    assert result["ok"] is False


def test_health_includes_invalidator_stats():
    p = FakeProvider()
    s = EmbeddingService(provider=p)
    s.start()
    from providers.extraction_provider import ExtractionProvider
    s.set_extraction_provider(ExtractionProvider())
    h = s.health()["result"]
    assert "cache_invalidator" in h
    s.close()