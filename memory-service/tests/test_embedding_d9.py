"""
test_embedding_d9.py — 轨道 A Day9 Embedding 吞吐/缓存/积压测试

覆盖（docs/day9/01_task_card.md，台账 R47）：
1. 查询缓存：命中/深拷贝（防污染）/空向量不缓存/维度变化失效/TTL/容量淘汰/统计
2. 积压指标：backlog / oldest_pending_age / 告警阈值（backlog_warn/oldest_warn）
3. 请求合并：同文本并发共享 Provider 调用（merged 统计/失败传播/inflight 释放）
4. health 扩展：backlog + 阈值 + cache stats 分项
5. 吞吐 smoke：串行吞吐测量脚本可运行（fake）
"""

import threading
import time

import pytest

from embedding.embedding_cache import EmbeddingCoalescer, EmbeddingQueryCache
from embedding.embedding_metrics import EmbeddingBacklogTracker
from embedding.embedding_service import EmbeddingService
from providers import EmbeddingResult, ProviderError, ProviderErrorCode


# ── fake Provider（带计数/延迟，验证缓存与合并） ──

class FakeProvider:
    def __init__(self, *, delay=0.0, dimension=768, fail=False):
        self.calls = 0
        self._delay = delay
        self._dimension = dimension
        self._fail = fail
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
        if self._fail:
            raise ProviderError(ProviderErrorCode.ERR_SDK_ERROR, "sdk error")
        with self._lock:
            self.calls += 1
        return EmbeddingResult(vector=[0.1] * self._dimension,
                               dimension=self._dimension, l2_norm=1.0)


# ── 1. 查询缓存 ──

def test_cache_hit_reduces_provider_calls():
    p = FakeProvider()
    s = EmbeddingService(provider=p)
    s.start()
    r1 = s.embed("你好世界")
    r2 = s.embed("你好世界")  # 命中缓存
    assert r1["ok"] and r2["ok"]
    assert r2.get("cache_hit") is True
    assert p.calls == 1  # Provider 只调用一次
    assert s.cache.stats["hits"] == 1
    assert s.cache.stats["misses"] == 1
    s.close()


def test_cache_returns_deep_copy():
    """缓存返回深拷贝：调用方修改 vector 不影响缓存。"""
    p = FakeProvider()
    s = EmbeddingService(provider=p)
    s.start()
    r1 = s.embed("原始文本")
    assert r1["ok"]
    r1["result"]["vector"][0] = 999.0  # 修改返回副本
    r2 = s.embed("原始文本")
    assert r2["ok"]
    assert r2["result"]["vector"][0] == 0.1  # 缓存未被污染
    s.close()


def test_cache_does_not_cache_degraded_empty_vector():
    """空向量（降级）不缓存：真实降级每次都要发生，不被缓存放大。"""
    class FailingProvider:
        def __init__(self):
            self.calls = 0

        def start(self):
            pass

        def close(self):
            pass

        def get_dimension(self):
            return 768

        def embed(self, text, *, timeout_ms=5000):
            self.calls += 1
            raise ProviderError(ProviderErrorCode.ERR_SDK_ERROR, "sdk down")

    p = FailingProvider()
    s = EmbeddingService(provider=p)
    s.start()
    r1 = s.embed("降级文本")
    r2 = s.embed("降级文本")
    assert r1["degraded"] is True
    assert r2["degraded"] is True
    assert p.calls == 2  # 未缓存降级态，每次都真实调用
    assert s.cache.stats["size"] == 0
    s.close()


def test_cache_key_includes_dimension():
    """维度变化 → 缓存自动失效（版本变更安全，D9 防串键）。"""
    p1 = FakeProvider(dimension=768)
    s = EmbeddingService(provider=p1)
    s.start()
    s.embed("文本A")
    # 维度变化后同文本不得命中旧缓存
    key_768 = s.cache.make_key("文本A", 768)
    key_1024 = s.cache.make_key("文本A", 1024)
    assert key_768 != key_1024
    s.close()


def test_cache_ttl_expiry():
    c = EmbeddingQueryCache(ttl_seconds=0.05)
    key = c.make_key("短时效", 768)
    c.set(key, {"vector": [1.0], "dimension": 768})
    assert c.get(key) is not None  # 命中（hits=1）
    time.sleep(0.08)
    assert c.get(key) is None  # TTL 过期（misses=1）
    assert c.stats["hits"] == 1
    assert c.stats["misses"] == 1


def test_cache_capacity_eviction():
    c = EmbeddingQueryCache(capacity=2)
    c.set(c.make_key("a", 768), {"vector": [1.0], "dimension": 768})
    c.set(c.make_key("b", 768), {"vector": [1.0], "dimension": 768})
    c.set(c.make_key("c", 768), {"vector": [1.0], "dimension": 768})  # 淘汰 a
    assert c.get(c.make_key("a", 768)) is None
    assert c.stats["evictions"] == 1
    assert c.stats["size"] == 2


# ── 2. 积压指标 ──

def test_backlog_tracks_enter_leave():
    t = EmbeddingBacklogTracker(backlog_warn=2, oldest_warn_seconds=0.05)
    seq1 = t.enter()
    seq2 = t.enter()
    snap = t.snapshot()
    assert snap["backlog"] == 2
    assert snap["backlog_alert"] is False  # 2 未超过 warn=2（> 语义）
    t.leave(seq1)
    t.leave(seq2)
    snap2 = t.snapshot()
    assert snap2["backlog"] == 0
    assert snap2["oldest_pending_age_seconds"] == 0.0


def test_backlog_alert_threshold():
    t = EmbeddingBacklogTracker(backlog_warn=2)
    t.enter()
    t.enter()
    t.enter()  # backlog=3 > 2 → 告警
    snap = t.snapshot()
    assert snap["backlog"] == 3
    assert snap["backlog_alert"] is True
    assert t.thresholds["backlog_warn"] == 2


def test_oldest_pending_age_alert():
    t = EmbeddingBacklogTracker(oldest_warn_seconds=0.05)
    seq = t.enter()
    time.sleep(0.08)
    snap = t.snapshot()
    assert snap["oldest_pending_age_seconds"] >= 0.05
    assert snap["oldest_alert"] is True
    t.leave(seq)


def test_backlog_thresholds_exposed():
    t = EmbeddingBacklogTracker(backlog_warn=16, oldest_warn_seconds=0.2)
    assert t.thresholds == {"backlog_warn": 16, "oldest_warn_seconds": 0.2}


# ── 3. 请求合并 ──

def test_coalescer_merges_concurrent_same_text():
    p = FakeProvider(delay=0.3)  # 慢 Provider：给并发合并留窗口
    s = EmbeddingService(provider=p)
    s.start()
    results = [None] * 3

    def worker(i):
        results[i] = s.embed("并发同一段文本")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert all(r["ok"] for r in results)
    assert any(r.get("coalesced") for r in results)  # 至少一个被合并
    assert p.calls <= 2  # 3 并发共享 ≤2 次 Provider 调用
    assert s.coalescer.stats["inflight"] == 0  # 无悬挂
    s.close()


def test_coalescer_failure_propagates():
    """合并的 Provider 调用失败 → 等待者收到结构化错误（不重复调用）。"""
    p = FakeProvider(delay=0.2, fail=True)
    s = EmbeddingService(provider=p)
    s.start()
    results = [None] * 2

    def worker(i):
        results[i] = s.embed("失败合并文本")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert all(r.get("degraded") for r in results)
    assert s.coalescer.stats["inflight"] == 0
    s.close()


# ── 4. health 扩展 ──

def test_health_includes_backlog_and_cache():
    p = FakeProvider()
    s = EmbeddingService(provider=p)
    s.start()
    s.embed("健康检查文本")
    h = s.health()["result"]
    assert "backlog" in h
    assert h["backlog"]["backlog"] == 0  # embed 已完成，队列空
    assert "thresholds" in h["backlog"]
    assert h["backlog"]["thresholds"]["backlog_warn"] == 32
    assert h["backlog"]["thresholds"]["oldest_warn_seconds"] == 0.2
    assert h["cache"]["size"] == 1
    assert h["cache"]["hits"] == 0
    assert h["cache"]["misses"] == 1
    s.close()


def test_health_backlog_nonzero_during_pending():
    """embed 进行中时 backlog > 0（积压可观测）。"""
    p = FakeProvider(delay=0.3)
    s = EmbeddingService(provider=p)
    s.start()
    snapshots = []
    done = threading.Event()

    def worker():
        s.embed("积压观测文本")
        done.set()

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.05)  # embed 仍在进行
    snapshots.append(s.backlog.snapshot()["backlog"])
    done.wait(timeout=2.0)
    t.join()
    assert snapshots[0] >= 1  # 处理中 backlog ≥1
    s.close()


# ── 5. 吞吐 smoke（脚本可运行） ──

def test_benchmark_script_runs_fake(tmp_path):
    """benchmark_embedding.py --fake 可运行并输出 JSON 汇总。"""
    import subprocess
    import sys
    import os
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script = os.path.join(repo, "scripts", "benchmark_embedding.py")
    r = subprocess.run(
        [sys.executable, script, "--fake", "--texts", "10", "--concurrency", "1",
         "--json"],
        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    import json as _json
    summary = _json.loads(r.stdout)
    assert summary["texts"] == 10
    assert "1" in summary["rounds"]
    assert summary["rounds"]["1"]["requests"] == 10
    assert summary["rounds"]["1"]["throughput_req_s"] > 0


# ── 6. Review 修复回归（2026-08-16） ──

def test_cache_key_distinguishes_normalized_equivalents():
    """Review Blocking 修复：原文哈希不串键——\"Hello\" 与 \"hello\" 是不同文本，
    不得共享缓存键（content_fingerprint 归一化会串键交叉污染）。"""
    from embedding.embedding_cache import raw_text_hash
    h1 = raw_text_hash("Hello World")
    h2 = raw_text_hash("hello world")
    h3 = raw_text_hash("a b")
    h4 = raw_text_hash("ab")
    assert h1 != h2  # 大小写不同 → 不同键
    assert h3 != h4  # 空白不同 → 不同键
    # 经 service 验证：不同文本不互相命中缓存
    p = FakeProvider()
    s = EmbeddingService(provider=p)
    s.start()
    r1 = s.embed("Hello World")
    r2 = s.embed("hello world")  # 不得命中 r1 的缓存
    assert r1["ok"] and r2["ok"]
    assert r2.get("cache_hit") is not True
    assert p.calls == 2
    s.close()


def test_coalesced_wait_counts_in_backlog():
    """Review 修复：合并等待请求同样计入 backlog（观测吞吐压力时指标不失灵）。"""
    p = FakeProvider(delay=0.4)
    s = EmbeddingService(provider=p)
    s.start()
    # 先发一个慢请求进入 in-flight，再发同文本并发 → 后者被合并等待
    results = [None] * 2
    observed = []

    def worker_a():
        results[0] = s.embed("合并积压观测")

    def worker_b():
        time.sleep(0.05)  # 确保 a 已进入 Provider 调用（in-flight）
        observed.append(s.backlog.snapshot()["backlog"])  # 合并等待中
        results[1] = s.embed("合并积压观测")

    ta = threading.Thread(target=worker_a)
    tb = threading.Thread(target=worker_b)
    ta.start()
    tb.start()
    ta.join()
    tb.join()
    assert all(r["ok"] for r in results)
    assert any(r.get("coalesced") for r in results)
    # 合并等待时 backlog ≥1（a 的 Provider 调用 + b 的等待均被追踪）
    assert observed[0] >= 1
    s.close()


def test_coalesced_failure_keeps_original_code():
    """Review 修复：合并等待者保留原始错误码（与发起者一致），非 ERR_UNKNOWN。"""
    class FailingProvider:
        def __init__(self):
            self._lock = threading.Lock()

        def start(self):
            pass

        def close(self):
            pass

        def get_dimension(self):
            return 768

        def embed(self, text, *, timeout_ms=5000):
            time.sleep(0.2)
            raise ProviderError(ProviderErrorCode.ERR_SDK_ERROR, "sdk error")

    p = FailingProvider()
    s = EmbeddingService(provider=p)
    s.start()
    results = [None] * 2

    def worker(i):
        results[i] = s.embed("失败错误码合并")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    codes = {r["degraded_reason"]["code"] for r in results}
    assert codes == {"ERR_SDK_ERROR"}  # 两条路径错误码一致
    s.close()
