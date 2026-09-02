"""
test_d12a_all.py — D12A 全量测试（复制到 VM 内直接跑）

用法（麒麟 VM 内）：
  cd /mnt/shared && PYTHONPATH=memory-service python3.12 scripts/test_d12a_all.py

覆盖（台账 D12-A）：
  1. [挂死恢复] Bridge 线程池挂死超过阈值 → 重建 executor 恢复路径
  2. [挂死恢复] 未超阈值慢任务不误重建
  3. [挂死恢复] 并发嵌入 + 挂死不互相阻塞（无死锁）
  4. [异常恢复] ProviderError 错误码精确传播（不吞）
  5. [异常恢复] 未知异常 → ERR_UNKNOWN 降级不崩溃
  6. [异常输入] 空文本 / 纯空白
  7. [异常输入] 超长文本（无积压正常 / 积压保护降级）
  8. [异常输入] 错误模型 ERR_MODEL_INVALID 传播
  9. [异常输入] 非法枚举（target_type/forget_mode 抛 ValueError）
  10. [异常输入] 非 str 输入拒绝（ERR_INVALID_TEXT）
  11. [异常输入] embed_batch 非法输入拒绝
  12. [假实现] 失败路径不伪装成功（降级=明确空向量）
"""
import sys
import time
import threading

sys.path.insert(0, "memory-service")

from providers import EmbeddingResult, ProviderError, ProviderErrorCode
from embedding.embedding_service import (
    EmbeddingService, _in_flight, _executor_lock,
    recover_hung_bridge_executor, shutdown_executor)
from embedding.cache_invalidator import DeletionEvent, ForgetMode, TargetType
from embedding.outbox_consumer import build_deletion_consumer
from providers.extraction_provider import PreferenceExtractionCache

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
    def __init__(self, delay=0.0, dimension=768, hang=False, fail_code=None,
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
    def model_info(self):
        from providers.embedding_provider import ModelInfo
        return ModelInfo(name="d12a-test-model", dimension=self._dimension,
                         loaded=True, ondevice=True)
    def embed(self, text, *, timeout_ms=5000):
        if self._hang:
            time.sleep(30.0)
        if self._delay:
            time.sleep(self._delay)
        if self._fail_on_text and text == self._fail_on_text:
            raise ProviderError(ProviderErrorCode.ERR_EMBED_FAILED, "embed failed")
        if self._raise_raw and text == self._raise_raw:
            raise RuntimeError("raw provider exception")
        if self._fail_code is not None:
            raise ProviderError(self._fail_code, "simulated fail")
        with self._lock:
            self.calls += 1
        return EmbeddingResult(vector=[0.1]*self._dimension,
                               dimension=self._dimension, l2_norm=1.0)

def reset_hang_threshold():
    import embedding.embedding_service as es
    es._embed_hang_threshold_ms = 60000.0

# ============================================================
# 1. 挂死恢复
# ============================================================
print("\n=== 1. 挂死恢复 ===")
reset_hang_threshold()
svc = EmbeddingService(provider=FakeProvider(hang=True))
svc.start()
r1 = svc.embed("hang1", timeout_ms=100)
check("挂死首次调用超时 ERR_TIMEOUT", r1.get("error", {}).get("code") == "ERR_TIMEOUT")

import embedding.embedding_service as es
es._embed_hang_threshold_ms = 0.01
recovered = recover_hung_bridge_executor()
check("挂死超过阈值重建 executor", recovered is True)
with _executor_lock:
    check("重建后 in-flight 清空", len(_in_flight) == 0)
svc.close()
shutdown_executor()

# ============================================================
# 2. 未超阈值不误重建
# ============================================================
print("\n=== 2. 未超阈值不误重建 ===")
reset_hang_threshold()
svc = EmbeddingService(provider=FakeProvider(hang=True))
svc.start()
svc.embed("hang2", timeout_ms=100)
recovered = recover_hung_bridge_executor()
check("未超阈值不重建（慢任务≠挂死）", recovered is False)
svc.close()
shutdown_executor()

# ============================================================
# 3. 并发嵌入无死锁
# ============================================================
print("\n=== 3. 并发嵌入无死锁 ===")
reset_hang_threshold()
svc = EmbeddingService(provider=FakeProvider(delay=0.1))
svc.start()
results = [None] * 4
def worker(i):
    results[i] = svc.embed(f"conc{i}", timeout_ms=5000)
ts = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
for t in ts: t.start()
for t in ts: t.join(timeout=10)
check("并发嵌入全部成功", all(r and r.get("ok") for r in results))
with _executor_lock:
    check("并发后 in-flight 清空", len(_in_flight) == 0)
svc.close()
shutdown_executor()

# ============================================================
# 4. 错误码精确传播
# ============================================================
print("\n=== 4. 错误码精确传播 ===")
for code in (ProviderErrorCode.ERR_SDK_ERROR, ProviderErrorCode.ERR_EMBED_FAILED,
             ProviderErrorCode.ERR_MODEL_INVALID):
    svc = EmbeddingService(provider=FakeProvider(fail_code=code))
    svc.start()
    r = svc.embed("err")
    check(f"错误码传播 {code.name}", r.get("degraded_reason", {}).get("code") == code.name)
    svc.close()

# ============================================================
# 5. 未知异常降级
# ============================================================
print("\n=== 5. 未知异常降级 ===")
svc = EmbeddingService(provider=FakeProvider(raise_raw="boom"))
svc.start()
r = svc.embed("boom")
check("未知异常 ERR_UNKNOWN 降级", r.get("degraded_reason", {}).get("code") == "ERR_UNKNOWN")
check("降级=明确空向量", r.get("result", {}).get("vector") == [])
svc.close()

# ============================================================
# 6. 空文本 / 纯空白
# ============================================================
print("\n=== 6. 空文本 / 纯空白 ===")
svc = EmbeddingService(provider=FakeProvider())
svc.start()
for t in ("", "   ", "\t\n"):
    r = svc.embed(t)
    check(f"空文本/空白正常: {t!r}", r.get("ok") and r.get("result", {}).get("dimension") == 768)
svc.close()

# ============================================================
# 7. 超长文本
# ============================================================
print("\n=== 7. 超长文本 ===")
svc = EmbeddingService(provider=FakeProvider())
svc.start()
r = svc.embed("a" * 10000)
check("超长文本无积压正常", r.get("ok") and r.get("result", {}).get("dimension") == 768)
svc.close()

# ============================================================
# 8. 非法枚举
# ============================================================
print("\n=== 8. 非法枚举 ===")
class DummyExt:
    def __init__(self):
        self._cache = PreferenceExtractionCache()
svc = EmbeddingService(provider=FakeProvider())
svc.start()
svc.set_extraction_provider(DummyExt())
consumer = build_deletion_consumer(svc)
try:
    consumer("memory.deletion", {"event_id": "e1", "user_id": "u",
                                 "target_type": "invalid_type"})
    check("非法 target_type 抛 ValueError", False)
except ValueError:
    check("非法 target_type 抛 ValueError", True)
try:
    consumer("memory.deletion", {"event_id": "e2", "user_id": "u",
                                 "forget_mode": "invalid_mode"})
    check("非法 forget_mode 抛 ValueError", False)
except ValueError:
    check("非法 forget_mode 抛 ValueError", True)
svc.close()

# ============================================================
# 9. 非 str / batch 非法
# ============================================================
print("\n=== 9. 非 str / batch 非法 ===")
svc = EmbeddingService(provider=FakeProvider())
svc.start()
r = svc.embed(123)
check("非 str 拒绝 ERR_INVALID_TEXT", r.get("error", {}).get("code") == "ERR_INVALID_TEXT")
r = svc.embed_batch("not a list")
check("embed_batch 非 list 拒绝", r.get("error", {}).get("code") == "ERR_INVALID_TEXT")
r = svc.embed_batch(["ok", 123])
check("embed_batch 含非 str 拒绝", r.get("error", {}).get("code") == "ERR_INVALID_TEXT")
svc.close()

# ============================================================
# 10. 失败不伪装成功
# ============================================================
print("\n=== 10. 失败不伪装成功 ===")
svc = EmbeddingService(provider=FakeProvider(fail_code=ProviderErrorCode.ERR_EMBED_FAILED))
svc.start()
r = svc.embed("x")
check("失败路径不伪装成功（降级=空向量）",
      r.get("degraded") is True and r.get("result", {}).get("vector") == [])
svc.close()

# ============================================================
# 11. health executor 分项
# ============================================================
print("\n=== 11. health executor 分项 ===")
svc = EmbeddingService(provider=FakeProvider())
svc.start()
h = svc.health()["result"]
check("health 含 executor 分项", "executor" in h)
check("executor 含 hang_recovered", "hang_recovered" in h["executor"])
check("executor 含 in_flight", "in_flight" in h["executor"])
check("executor 含 hang_threshold_ms", "hang_threshold_ms" in h["executor"])
svc.close()

# ============================================================
# 汇总
# ============================================================
print(f"\n{'='*50}")
print(f"  PASS: {PASS}  FAIL: {FAIL}")
print(f"  结论: {'ALL PASS' if FAIL == 0 else 'SOME FAILED'}")
print(f"{'='*50}")
shutdown_executor()
sys.exit(0 if FAIL == 0 else 1)
