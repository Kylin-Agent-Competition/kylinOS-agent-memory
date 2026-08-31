"""
test_d11a_all.py — D11A 全量测试（复制到 VM 内直接跑）

用法（麒麟 VM 内）：
  cd /mnt/shared && PYTHONPATH=memory-service python3.12 scripts/test_d11a_all.py
"""
import sys
import time
import threading
from typing import Any, Dict, List, Optional

sys.path.insert(0, "memory-service")

from providers import EmbeddingResult, ProviderError, ProviderErrorCode
from providers.embedding_provider import ModelInfo
from embedding.embedding_service import EmbeddingService
from embedding.embedding_cache import EmbeddingQueryCache, EmbeddingCoalescer, raw_text_hash
from embedding.embedding_metrics import EmbeddingBacklogTracker
from embedding.cache_invalidator import CacheInvalidator, DeletionEvent, ForgetMode, TargetType
from providers.extraction_provider import PreferenceExtractionCache
from embedding.outbox_consumer import build_deletion_consumer

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")

# ============================================================
# Fake Provider
# ============================================================
class FakeProvider:
    def __init__(self, delay=0.0, dimension=768, fail=False, fail_on_text=None):
        self.calls = 0
        self._delay = delay
        self._dimension = dimension
        self._fail = fail
        self._fail_on_text = fail_on_text
        self._lock = threading.Lock()

    def start(self):
        pass
    def close(self):
        pass
    def get_dimension(self):
        return self._dimension
    def model_info(self):
        return ModelInfo(name="d11a-test-model", dimension=self._dimension, loaded=True, ondevice=True)
    def embed(self, text, *, timeout_ms=5000):
        if self._delay:
            time.sleep(self._delay)
        if self._fail:
            raise ProviderError(ProviderErrorCode.ERR_SDK_ERROR, "sdk error")
        if self._fail_on_text and text == self._fail_on_text:
            raise ProviderError(ProviderErrorCode.ERR_EMBED_FAILED, "embed failed for specific text")
        with self._lock:
            self.calls += 1
        return EmbeddingResult(vector=[0.1]*self._dimension, dimension=self._dimension, l2_norm=1.0)


# ============================================================
# 1. health() 增强测试
# ============================================================
print("\n=== 1. health() 增强测试 ===")

svc = EmbeddingService(provider=FakeProvider())
svc.start()
h = svc.health()["result"]

check("health 包含 model 分项", "model" in h)
check("model.name 非空", bool(h["model"].get("name")))
check("model.dimension == 768", h["model"].get("dimension") == 768)
check("model.loaded == True", h["model"].get("loaded") is True)

check("health 包含 errors 分项", "errors" in h)
check("errors.count 初始为 0", h["errors"]["count"] == 0)
check("errors.last_code 初始为空", h["errors"]["last_code"] == "")

check("health 包含 provider_lifecycle", "provider_lifecycle" in h)
check("health 包含 cache_invalidator", "cache_invalidator" in h)
check("health 包含 backlog", "backlog" in h)
check("sdk_missing == False", h["sdk_missing"] is False)

svc.close()


# ============================================================
# 2. 错误追踪测试
# ============================================================
print("\n=== 2. 错误追踪测试 ===")

class FailingProvider:
    def __init__(self):
        self.calls = 0
    def start(self):
        pass
    def close(self):
        pass
    def get_dimension(self):
        return 768
    def model_info(self):
        return ModelInfo(name="test", dimension=768, loaded=True, ondevice=True)
    def embed(self, text, *, timeout_ms=5000):
        self.calls += 1
        raise ProviderError(ProviderErrorCode.ERR_SDK_ERROR, "simulated sdk error")

svc2 = EmbeddingService(provider=FailingProvider())
svc2.start()

r1 = svc2.embed("text1")
check("错误返回 degraded", r1.get("degraded") is True)

h2 = svc2.health()["result"]
check("错误计数为 1", h2["errors"]["count"] >= 1)
check("last_code 为 ERR_SDK_ERROR", "ERR_SDK_ERROR" in h2["errors"]["last_code"])
check("last_message 非空", bool(h2["errors"]["last_message"]))
check("last_time_seconds_ago >= 0", h2["errors"]["last_time_seconds_ago"] >= 0)

svc2.close()


# ============================================================
# 3. Embedding 缓存 + Generation 代次
# ============================================================
print("\n=== 3. 缓存 + Generation 代次 ===")

c = EmbeddingQueryCache(capacity=64)
key = c.make_key("test", 768)
gen = c.generation
check("初始 generation 为 0", gen == 0)

c.set(key, {"vector": [0.1]*768, "dimension": 768}, generation=gen)
check("fresh write 成功", c.get(key) is not None)

c.invalidate_by_content(raw_text_hash("test"))
check("失效后缓存为空", c.get(key) is None)

c.set(key, {"vector": [0.1]*768, "dimension": 768}, generation=gen)
check("stale write 被拒绝", c.get(key) is None)

gen2 = c.generation
c.set(key, {"vector": [0.1]*768, "dimension": 768}, generation=gen2)
check("fresh write 成功(新代次)", c.get(key) is not None)

c.clear()
check("clear 后缓存为空", c.get(key) is None)
check("clear 后 generation 递增", c.generation > gen2)


# ============================================================
# 4. CacheInvalidator 功能测试
# ============================================================
print("\n=== 4. CacheInvalidator 功能测试 ===")

emb_cache = EmbeddingQueryCache(capacity=64)
ext_cache = PreferenceExtractionCache(capacity=64)
invalidator = CacheInvalidator(emb_cache, ext_cache)

key = emb_cache.make_key("invalidate test", 768)
emb_cache.set(key, {"vector": [0.1]*768, "dimension": 768})
check("缓存写入成功", emb_cache.get(key) is not None)

event = DeletionEvent(
    event_id="test_001", user_id="user_1",
    content_hashes=[raw_text_hash("invalidate test")],
    forget_mode=ForgetMode.SINGLE_ITEM)
result = invalidator.handle_deletion(event)
check("删除事件处理成功", result["ok"] is True)
check("embedding 已失效", result["embedding_invalidated"] >= 1)
check("缓存已清空", emb_cache.get(key) is None)

r2 = invalidator.handle_deletion(event)
check("幂等去重成功", r2["dedup"] is True)

stats = invalidator.stats
check("events_processed == 1", stats["events_processed"] == 1)
check("embedding_invalidated >= 1", stats["embedding_invalidated"] >= 1)


# ============================================================
# 5. Service 接线 + handle_deletion_event
# ============================================================
print("\n=== 5. Service 接线 + handle_deletion_event ===")

svc3 = EmbeddingService(provider=FakeProvider())
svc3.start()
svc3.embed("wire test")
check("invalidate 未接线时返回错误", svc3.handle_deletion_event(event).get("ok") is False)

from providers.extraction_provider import ExtractionProvider
svc3.set_extraction_provider(ExtractionProvider())
check("set_extraction_provider 后 invalidator 已就绪", svc3.invalidator is not None)

h3 = svc3.health()["result"]
check("health 含 cache_invalidator 统计", "cache_invalidator" in h3)
check("cache_invalidator 含 events_processed", "events_processed" in h3["cache_invalidator"])

svc3.close()


# ============================================================
# 6. outbox_consumer 模块测试
# ============================================================
print("\n=== 6. outbox_consumer 模块测试 ===")

svc4 = EmbeddingService(provider=FakeProvider())
svc4.start()
svc4.set_extraction_provider(ExtractionProvider())

consumer = build_deletion_consumer(svc4)
check("consumer 创建成功", consumer is not None)

svc4.embed("outbox consumer test")
payload = {
    "event_type": "memory.deletion",
    "event_id": "consumer_test_001",
    "user_id": "test_user",
    "content_hashes": [raw_text_hash("outbox consumer test")],
    "content_fingerprints": [],
    "target_type": "event",
    "forget_mode": "single_item",
}
try:
    consumer(payload)
    check("consumer 调用成功", True)
except Exception as e:
    check("consumer 调用异常", False, str(e))

svc4.close()

# 负路径测试
print("\n--- 6.1 outbox_consumer 负路径测试 ---")

svc5 = EmbeddingService(provider=FakeProvider())
svc5.start()

# 未接线
consumer_no_inv = build_deletion_consumer(svc5)
try:
    consumer_no_inv({"event_type": "memory.deletion", "event_id": "neg_test", "user_id": "u"})
    check("未接线应抛 RuntimeError", False)
except RuntimeError:
    check("未接线抛 RuntimeError", True)

svc5.set_extraction_provider(ExtractionProvider())

# 缺 event_id
consumer_ok = build_deletion_consumer(svc5)
try:
    consumer_ok({"event_type": "memory.deletion", "user_id": "u"})
    check("缺 event_id 应抛 ValueError", False)
except ValueError:
    check("缺 event_id 抛 ValueError", True)

# 未知 event_type
try:
    consumer_ok({"event_type": "unknown.type", "event_id": "neg_test", "user_id": "u"})
    check("未知 event_type 应抛 ValueError", False)
except ValueError:
    check("未知 event_type 抛 ValueError", True)

svc5.close()


# ============================================================
# 7. 累积指标追踪
# ============================================================
print("\n=== 7. 累积指标追踪 ===")

t = EmbeddingBacklogTracker(backlog_warn=2, oldest_warn_seconds=0.05)
check("初始 backlog 为 0", t.snapshot()["backlog"] == 0)

seq1 = t.enter()
seq2 = t.enter()
check("enter 后 backlog 为 2", t.snapshot()["backlog"] == 2)

t.leave(seq1)
t.leave(seq2)
check("leave 后 backlog 为 0", t.snapshot()["backlog"] == 0)

t2 = EmbeddingBacklogTracker(backlog_warn=2)
t2.enter()
t2.enter()
t2.enter()
check("backlog_alert 为 True", t2.snapshot()["backlog_alert"] is True)


# ============================================================
# 8. 请求合并（Coalescer）
# ============================================================
print("\n=== 8. 请求合并 ===")

coalescer = EmbeddingCoalescer()
check("初始 inflight 为 0", coalescer.stats["inflight"] == 0)
check("初始 merged 为 0", coalescer.stats["merged"] == 0)


# ============================================================
# 9. 并发竞态（generation 阻止 stale write）
# ============================================================
print("\n=== 9. 并发竞态 ===")

c2 = EmbeddingQueryCache(capacity=64)
text = "race text"
content_hash = raw_text_hash(text)
key = c2.make_key(text, 768)

gen = c2.generation
done = threading.Event()
result_holder = [None]

def compute():
    time.sleep(0.1)
    result_holder[0] = {"vector": [1.0]*768, "dimension": 768}
    done.set()

t = threading.Thread(target=compute)
t.start()
time.sleep(0.02)
c2.invalidate_by_content(content_hash)
done.wait(timeout=2.0)
t.join()

c2.set(key, result_holder[0], generation=gen)
check("stale write 被 generation 拒绝", c2.get(key) is None)
c2.set(key, result_holder[0], generation=c2.generation)
check("fresh write 成功", c2.get(key) is not None)


# ============================================================
# 汇总
# ============================================================
print(f"\n{'='*50}")
print(f"  PASS: {PASS}  FAIL: {FAIL}")
print(f"  结论: {'ALL PASS' if FAIL == 0 else 'SOME FAILED'}")
print(f"{'='*50}")
sys.exit(0 if FAIL == 0 else 1)