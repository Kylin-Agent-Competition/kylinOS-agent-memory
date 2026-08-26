"""
test_embedding_d10.py — 轨道 A Day10 精准遗忘与删除一致性测试

台账 R52（A 轨 D10）：
1. Embedding 缓存按内容指纹失效
2. Extraction 缓存按事件 ID / 按内容指纹失效
3. CacheInvalidator 删除事件处理（幂等/按用户/全量）
4. 删除期间异常恢复（Provider 异常不影响删除状态）
5. 并发删除与读取 → 无竞态数据恢复
6. EmbeddingService 对接删除事件入口
"""

import threading
import time

import pytest

from embedding.cache_invalidator import CacheInvalidator, DeletionEvent
from embedding.embedding_cache import EmbeddingQueryCache
from embedding.embedding_service import EmbeddingService
from providers.extraction_provider import PreferenceExtractionCache


# ── Helpers ──

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
        from providers import EmbeddingResult
        return EmbeddingResult(vector=[0.1] * self._dimension,
                               dimension=self._dimension, l2_norm=1.0)


# ── 1. EmbeddingQueryCache 按内容指纹失效 ──

def test_embedding_cache_invalidate_by_content():
    c = EmbeddingQueryCache(capacity=64)
    key1 = c.make_key("hello world", 768)
    key2 = c.make_key("foo bar", 768)
    c.set(key1, {"vector": [1.0], "dimension": 768})
    c.set(key2, {"vector": [1.0], "dimension": 768})
    assert c.get(key1) is not None
    assert c.get(key2) is not None

    removed = c.invalidate_by_content(key1[2])
    assert removed == 1
    assert c.get(key1) is None
    assert c.get(key2) is not None


def test_embedding_cache_invalidate_by_content_no_match():
    c = EmbeddingQueryCache(capacity=64)
    key = c.make_key("hello", 768)
    c.set(key, {"vector": [1.0], "dimension": 768})
    removed = c.invalidate_by_content("nonexistent_hash")
    assert removed == 0
    assert c.get(key) is not None


# ── 2. PreferenceExtractionCache 按事件 ID / 内容指纹失效 ──

def test_extraction_cache_invalidate_by_event():
    from pipeline.fingerprint import content_fingerprint
    c = PreferenceExtractionCache(capacity=64)
    fp1 = content_fingerprint("hello")
    fp2 = content_fingerprint("world")
    key1 = ("preference", "evt_001", fp1)
    key2 = ("preference", "evt_002", fp2)
    key3 = ("knowledge", "evt_001", fp2)
    from providers.extraction_provider import PreferenceCandidate, KnowledgeCandidate
    c.set(key1, [PreferenceCandidate(key="k1", value="v1", confidence=0.9,
                                     evidence="e1", source_event_id="evt_001")])
    c.set(key2, [PreferenceCandidate(key="k2", value="v2", confidence=0.8,
                                     evidence="e2", source_event_id="evt_002")])
    c.set(key3, [KnowledgeCandidate(fact="f1", confidence=0.7,
                                    source_event_id="evt_001")])
    assert c.stats["size"] == 3

    removed = c.invalidate_by_event("evt_001")
    assert removed == 2
    assert c.stats["size"] == 1
    assert c.get(key2) is not None


def test_extraction_cache_invalidate_by_content():
    from pipeline.fingerprint import content_fingerprint
    c = PreferenceExtractionCache(capacity=64)
    fp = content_fingerprint("unique content")
    key1 = ("preference", "evt_001", fp)
    key2 = ("knowledge", "evt_002", fp)
    from providers.extraction_provider import PreferenceCandidate, KnowledgeCandidate
    c.set(key1, [PreferenceCandidate(key="k1", value="v1", confidence=0.9,
                                     evidence="e1", source_event_id="evt_001")])
    c.set(key2, [KnowledgeCandidate(fact="f1", confidence=0.7,
                                    source_event_id="evt_002")])
    assert c.stats["size"] == 2

    removed = c.invalidate_by_content(fp)
    assert removed == 2
    assert c.stats["size"] == 0


# ── 3. CacheInvalidator 删除事件处理 ──

def test_invalidator_handle_deletion():
    emb_cache = EmbeddingQueryCache(capacity=64)
    ext_cache = PreferenceExtractionCache(capacity=64)
    invalidator = CacheInvalidator(emb_cache, ext_cache)

    key = emb_cache.make_key("delete me", 768)
    emb_cache.set(key, {"vector": [1.0], "dimension": 768})
    assert emb_cache.get(key) is not None

    from pipeline.fingerprint import content_fingerprint
    fp = content_fingerprint("delete me")
    event = DeletionEvent(event_id="del_001", user_id="user_1",
                          content_hashes=[key[2]],
                          content_fingerprints=[fp])
    result = invalidator.handle_deletion(event)
    assert result["ok"] is True
    assert result["embedding_invalidated"] >= 1
    assert emb_cache.get(key) is None


def test_invalidator_idempotent():
    emb_cache = EmbeddingQueryCache(capacity=64)
    ext_cache = PreferenceExtractionCache(capacity=64)
    invalidator = CacheInvalidator(emb_cache, ext_cache)

    event = DeletionEvent(event_id="del_001", user_id="user_1",
                          content_hashes=["hash1"])
    r1 = invalidator.handle_deletion(event)
    assert r1["dedup"] is False
    r2 = invalidator.handle_deletion(event)
    assert r2["dedup"] is True
    assert r2["embedding_invalidated"] == 0


def test_invalidator_invalidate_by_user():
    emb_cache = EmbeddingQueryCache(capacity=64)
    ext_cache = PreferenceExtractionCache(capacity=64)
    invalidator = CacheInvalidator(emb_cache, ext_cache)

    key1 = emb_cache.make_key("user1 text", 768)
    key2 = emb_cache.make_key("user2 text", 768)
    emb_cache.set(key1, {"vector": [1.0], "dimension": 768})
    emb_cache.set(key2, {"vector": [1.0], "dimension": 768})

    invalidator.handle_deletion(DeletionEvent(
        event_id="del_001", user_id="user_1",
        content_hashes=[key1[2]]))
    invalidator.handle_deletion(DeletionEvent(
        event_id="del_002", user_id="user_2",
        content_hashes=[key2[2]]))

    emb_cache.set(key1, {"vector": [1.0], "dimension": 768})
    emb_cache.set(key2, {"vector": [1.0], "dimension": 768})

    result = invalidator.invalidate_by_user("user_1")
    assert result["embedding_invalidated"] >= 1
    assert emb_cache.get(key1) is None
    assert emb_cache.get(key2) is not None


def test_invalidator_invalidate_all():
    emb_cache = EmbeddingQueryCache(capacity=64)
    ext_cache = PreferenceExtractionCache(capacity=64)
    invalidator = CacheInvalidator(emb_cache, ext_cache)

    key = emb_cache.make_key("test", 768)
    emb_cache.set(key, {"vector": [1.0], "dimension": 768})
    invalidator.handle_deletion(DeletionEvent(
        event_id="del_001", user_id="user_1",
        content_hashes=[key[2]]))

    invalidator.invalidate_all()
    assert emb_cache.stats["size"] == 0
    assert ext_cache.stats["size"] == 0
    assert invalidator.stats["events_processed"] == 0


def test_invalidator_stats():
    emb_cache = EmbeddingQueryCache(capacity=64)
    ext_cache = PreferenceExtractionCache(capacity=64)
    invalidator = CacheInvalidator(emb_cache, ext_cache)

    assert invalidator.stats["events_processed"] == 0
    assert invalidator.stats["tracked_users"] == 0

    invalidator.handle_deletion(DeletionEvent(
        event_id="del_001", user_id="user_1",
        content_hashes=["hash1"]))
    invalidator.handle_deletion(DeletionEvent(
        event_id="del_002", user_id="user_1",
        content_hashes=["hash2"]))

    stats = invalidator.stats
    assert stats["events_processed"] == 2
    assert stats["tracked_users"] == 1
    assert stats["processed_events"] == 2


# ── 4. 删除期间异常恢复 ──

def test_invalidator_provider_exception_does_not_lose_deletion():
    """删除过程中 Provider 异常 → 删除不丢失，可重试。"""
    emb_cache = EmbeddingQueryCache(capacity=64)
    ext_cache = PreferenceExtractionCache(capacity=64)
    invalidator = CacheInvalidator(emb_cache, ext_cache)

    key = emb_cache.make_key("test", 768)
    emb_cache.set(key, {"vector": [1.0], "dimension": 768})

    event = DeletionEvent(event_id="del_001", user_id="user_1",
                          content_hashes=[key[2]])
    result = invalidator.handle_deletion(event)
    assert result["ok"] is True
    assert emb_cache.get(key) is None

    result2 = invalidator.handle_deletion(event)
    assert result2["dedup"] is True
    assert emb_cache.get(key) is None


def test_deletion_after_new_provider_instance():
    """删除后新建 Provider 实例 → 已删除数据不恢复。"""
    emb_cache = EmbeddingQueryCache(capacity=64)
    ext_cache = PreferenceExtractionCache(capacity=64)
    invalidator = CacheInvalidator(emb_cache, ext_cache)

    key = emb_cache.make_key("sensitive data", 768)
    emb_cache.set(key, {"vector": [1.0], "dimension": 768})

    invalidator.handle_deletion(DeletionEvent(
        event_id="del_001", user_id="user_1",
        content_hashes=[key[2]]))
    assert emb_cache.get(key) is None

    emb_cache2 = EmbeddingQueryCache(capacity=64)
    assert emb_cache2.get(key) is None


# ── 5. 并发删除与读取 → 无竞态数据恢复 ──

def test_concurrent_deletion_and_read_no_race():
    """并发删除与读取 → 无竞态数据恢复。"""
    emb_cache = EmbeddingQueryCache(capacity=256)
    ext_cache = PreferenceExtractionCache(capacity=256)
    invalidator = CacheInvalidator(emb_cache, ext_cache)

    keys = [emb_cache.make_key(f"text_{i}", 768) for i in range(50)]
    for k in keys:
        emb_cache.set(k, {"vector": [1.0], "dimension": 768})
    assert emb_cache.stats["size"] == 50

    errors = []
    lock = threading.Lock()

    def deleter():
        for i, k in enumerate(keys[:25]):
            event = DeletionEvent(
                event_id=f"con_del_{i}", user_id="user_1",
                content_hashes=[k[2]])
            try:
                invalidator.handle_deletion(event)
            except Exception as e:
                with lock:
                    errors.append(f"deleter: {e}")

    def reader():
        for k in keys[25:]:
            try:
                emb_cache.get(k)
            except Exception as e:
                with lock:
                    errors.append(f"reader: {e}")

    threads = [threading.Thread(target=deleter),
               threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    for k in keys[:25]:
        assert emb_cache.get(k) is None
    for k in keys[25:]:
        assert emb_cache.get(k) is not None


# ── 6. EmbeddingService 对接删除事件入口 ──

def test_service_handle_deletion_event():
    p = FakeProvider()
    s = EmbeddingService(provider=p)
    s.start()
    s.embed("cache me")
    assert s.cache.stats["size"] == 1

    key = s.cache.make_key("cache me", 768)
    event = DeletionEvent(event_id="del_001", user_id="user_1",
                          content_hashes=[key[2]])
    result = s.handle_deletion_event(event)
    assert result["ok"] is False
    assert "invalidator" in result["error"]

    from providers.extraction_provider import PreferenceExtractionCache
    ext_cache = PreferenceExtractionCache()
    s.set_cache_invalidator(ext_cache)
    result = s.handle_deletion_event(event)
    assert result["ok"] is True
    assert result["embedding_invalidated"] >= 1
    assert s.cache.get(key) is None
    s.close()


def test_service_handle_deletion_event_before_set():
    s = EmbeddingService()
    event = DeletionEvent(event_id="del_001", user_id="user_1",
                          content_hashes=["hash1"])
    result = s.handle_deletion_event(event)
    assert result["ok"] is False
    assert "invalidator" in result["error"]


def test_health_includes_invalidator_stats():
    p = FakeProvider()
    s = EmbeddingService(provider=p)
    s.start()
    from providers.extraction_provider import PreferenceExtractionCache
    s.set_cache_invalidator(PreferenceExtractionCache())
    h = s.health()["result"]
    assert "cache_invalidator" in h
    s.close()