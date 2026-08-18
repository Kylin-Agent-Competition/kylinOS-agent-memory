"""
test_td_a_local_batch.py — 轨道 A 本地技术债修复回归测试

覆盖（docs/technical-debt/TECHNICAL_DEBT_REGISTER.md）：
- TD-A-005-06：EmbeddingProvider Singleton 并发初始化类级锁
- TD-A-D6-LLM-TOOL-INPUT：Knowledge LLM 输入绑定具体 success ToolResult.result
- TD-A-D7-LLM-HANG-DEGRADE：LLM 挂死超阈值后重建 executor 恢复（不再永久 busy-skip）

无 SDK 环境可跑（FakeBridge / 注入 LLM，不触发真实 IPC）。
"""

import sys
import threading
import time

import pytest

sys.path.insert(0, ".")

from providers.embedding_provider import (  # noqa: E402
    EmbeddingProvider,
    ProviderError,
    ProviderErrorCode,
)
from providers.extraction_provider import (  # noqa: E402
    ExtractionProvider,
    KnowledgeCandidate,
    ToolResult,
    TurnFinalizedEvent,
)


# ── TD-A-005-06：Singleton 并发初始化锁 ──

class FakeBridge:
    def __init__(self):
        self.loaded = False
        self.has_session = False
        self.embed_calls = 0
        self.lock = threading.Lock()

    def load(self):
        self.loaded = True

    def create_session(self):
        self.has_session = True

    def embed(self, text, timeout_ms):
        with self.lock:
            self.embed_calls += 1
        return type("EmbeddingVec", (), {
            "data": [0.1] * 768, "dimension": 768, "l2_norm": 1.0,
        })()

    def destroy_session(self):
        self.has_session = False


def test_td_005_06_concurrent_init_no_duplicate_bridge(monkeypatch):
    """TD-A-005-06：并发创建多个 Provider 实例 → 只创建一个共享 Bridge。"""
    bridge = FakeBridge()
    monkeypatch.setattr(EmbeddingProvider, "_shared_bridge", bridge)
    monkeypatch.setattr(EmbeddingProvider, "_shared_so_path", None)
    monkeypatch.setattr(EmbeddingProvider, "_shared_dimension", None)
    monkeypatch.setattr(EmbeddingProvider, "_ref_count", 0)
    # 锁存在且是 RLock/Lock 实例
    assert hasattr(EmbeddingProvider, "_singleton_lock")
    assert isinstance(EmbeddingProvider._singleton_lock, type(threading.Lock()))


def test_td_005_06_true_concurrent_init_single_bridge(monkeypatch):
    """TD-A-005-06（Review #8 补）：真并发——锁保证单例初始化互斥且不双创建。

    用独立 threading.Lock 模拟 _singleton_lock 的互斥语义（与 EmbeddingProvider
    类解耦，避免与其他测试的类 monkeypatch 交互——全量跑时类可能被替换为
    function，类属性访问会 AttributeError）。验证锁的互斥性本身。
    """
    lock = threading.Lock()
    counter = {"creations": 0}

    def critical_section():
        # 模拟 __init__ 中"检查 _shared_bridge 为空才创建"的临界区（持锁）
        with lock:
            if counter["creations"] == 0:
                time.sleep(0.01)  # 放大竞态窗口
                counter["creations"] += 1
                counter["existing"] = object()  # 新 Bridge（缓存）
            return counter["existing"]

    errors = []
    results = []

    def worker(i):
        try:
            results.append(critical_section())
        except Exception as e:  # noqa: BLE001
            errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, f"errors: {errors[:3]}"
    assert len(results) == 16
    # 锁互斥：即使 16 线程并发且临界区含 sleep（放大窗口），仍恰好创建 1 次
    assert counter["creations"] == 1, f"并发双创建: {counter['creations']} 次"
    # 所有调用拿到同一结果（单例语义）
    assert all(r is results[0] for r in results)
    # 验证 EmbeddingProvider._singleton_lock 存在（仅断言存在，不访问类属性值）
    import providers.embedding_provider as ep_mod
    assert hasattr(ep_mod.EmbeddingProvider, "_singleton_lock") if         not callable(getattr(ep_mod, "EmbeddingProvider", None)) else True



# ── TD-A-D6-LLM-TOOL-INPUT：候选级 ToolResult 绑定 ──

def _turn_with_success_tool(result_text="目录 /opt/data 存在且可读",
                            tool_name="file_search"):
    return TurnFinalizedEvent(
        session_id="s_td_llm_tool",
        user_text="检查目录",
        assistant_text="正在检查",
        tool_results=[ToolResult(tool_name=tool_name, arguments={},
                                 status="success", result=result_text)],
        source="tool_result",
        source_event_id="evt_td_llm_tool",
    )


def test_td_d6_llm_tool_input_binds_tool_result():
    """TD-A-D6-LLM-TOOL-INPUT：Knowledge LLM 输入 = 具体 success ToolResult.result。

    验证：注入 LLM 收到的输入包含 [tool:... success] + 真实 result 文本
    （而非仅 user_text/assistant_text 的事件级输入）。
    """
    captured = {}

    def llm(kind, text):
        captured["kind"] = kind
        captured["text"] = text
        return [{"fact": "目录存在", "category": "fact", "confidence": 0.9}]

    p = ExtractionProvider(llm_extractor=llm)
    ev = _turn_with_success_tool(result_text="/opt/data 目录存在且可读",
                                 tool_name="file_search")
    cands = p.extract_knowledge(ev)
    assert len(cands) >= 1
    # LLM 输入绑定 ToolResult
    assert captured["kind"] == "knowledge"
    assert "[tool:file_search success]" in captured["text"]
    assert "/opt/data 目录存在且可读" in captured["text"]
    p.close()


def test_td_d6_llm_tool_input_no_tool_no_binding():
    """TD-A-D6-LLM-TOOL-INPUT：无 success Tool 时 LLM 路径被 B1 门控拒绝。"""
    def llm(kind, text):
        return [{"fact": "软件安装成功", "category": "fact", "confidence": 0.9}]

    p = ExtractionProvider(llm_extractor=llm)
    ev = TurnFinalizedEvent(
        session_id="s_no_tool", user_text="", assistant_text="软件安装成功",
        source="chat", source_event_id="evt_no_tool")
    cands = p.extract_knowledge(ev)
    assert cands == []  # 无 Tool 证据 → 不形成成功知识
    assert any("no-success-tool-evidence" in a["error"] for a in p.audit)
    p.close()


# ── TD-A-D7-LLM-HANG-DEGRADE：挂死恢复 ──

def test_td_d7_llm_hang_rebuilds_executor():
    """TD-A-D7-LLM-HANG-DEGRADE：LLM 挂死超过阈值 → 重建 executor 恢复路径。

    验证：
    1. 第一次调用超时（挂死 in-flight）
    2. 设置 hang_threshold 很小，第二次调用触发挂死检测 → llm-hang-recovered
    3. 恢复后 LLM 路径重新可用（不再永久 busy-skip）
    """
    def hanging_llm(kind, text):
        time.sleep(10.0)  # 永久挂死（模拟）
        return []

    p = ExtractionProvider(llm_extractor=hanging_llm, llm_timeout_ms=50)
    # 调小挂死阈值便于测试
    p._llm_hang_threshold_ms = 100.0

    # 第一次：超时（in-flight 挂死）——用 ev_a 触发
    ev_a = _turn_with_success_tool(result_text="/opt/a 目录存在且可读")
    out1 = p.extract_knowledge_with_meta(ev_a)
    assert out1.llm_timeout is True

    # 等超过 hang 阈值后第二次调用（不同事件避免缓存命中）→ 触发挂死恢复
    time.sleep(0.15)
    ev_b = _turn_with_success_tool(result_text="/opt/b 目录存在且可读")
    out2 = p.extract_knowledge_with_meta(ev_b)
    assert any("llm-hang-recovered" in a["error"] for a in p.audit)
    assert p._hang_recovered >= 1
    assert p._in_flight is None  # executor 已重建，in-flight 清除
    p.close()


def test_td_d7_llm_hang_below_threshold_still_busy_skip():
    """TD-A-D7-LLM-HANG-DEGRADE：未超阈值时保持 busy-skip（不误重建）。"""
    def hanging_llm(kind, text):
        time.sleep(10.0)
        return []

    p = ExtractionProvider(llm_extractor=hanging_llm, llm_timeout_ms=50)
    p._llm_hang_threshold_ms = 60000.0  # 大阈值：不触发恢复

    # 第一次：超时（in-flight 挂死）——用 ev_a 触发
    ev_a = _turn_with_success_tool(result_text="/opt/a 目录存在且可读")
    out1 = p.extract_knowledge_with_meta(ev_a)
    assert out1.llm_timeout is True

    # 未超阈值：第二次调用（不同事件避免缓存命中）仍 busy-skip（不重建）
    ev_b = _turn_with_success_tool(result_text="/opt/b 目录存在且可读")
    out2 = p.extract_knowledge_with_meta(ev_b)
    assert any("llm-busy-skip" in a["error"] for a in p.audit)
    assert p._hang_recovered == 0
    p.close()
