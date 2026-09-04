"""
test_schema_drift_a.py — 轨道 A Schema 漂移反向门禁测试（D12 治理，DRIFT-001 等）

对齐：麒麟OS_Agent_业务字段漂移修复与跨轨自检方案_v1.0
- A 轨自检任务（§6 A 轨）与 Batch 2（A Provider/Candidate 收口）：
  - TurnFinalizedEvent.collected_at 为 legacy 只读 alias；Canonical 写字段为
    captured_at；禁止 Provider 内继续产生新 collected_at 写字段。
  - 候选 DTO 短名字段（key/value/scope/confidence/fact/category）仅为
    Candidate DTO 表示，进入 Domain 时必须唯一映射到 Canonical 字段
    （preference_key/value/preference_scope/confidence_score/
    content_summary/knowledge_type）。
  - 禁止新增第二套业务状态/枚举（event_status / lifecycle_status /
    verified 等）；memory_status=candidate 由系统强制，不允许 LLM 覆写。

测试纪律（对齐既有跨轨契约门禁）：
- 不使用 Mock、skip、xfail 固定 PASS。
- 仅合成数据，不引入真实用户数据。
- 测试失败 = Schema 漂移回归，属于 CODE_FAILURE；不得删除断言使其变绿。
"""

import dataclasses
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.extraction_provider import (  # noqa: E402
    KnowledgeCandidate,
    PreferenceCandidate,
    TurnFinalizedEvent,
)
from service.candidate_governance import CandidateGovernanceService  # noqa: E402
from service.contracts import ServiceRequestContext  # noqa: E402
from pipeline.schemas import MemorySourceEvent, MemoryType, SourceBusinessStatus  # noqa: E402


def _make_ctx(user_id="user_demo_a") -> ServiceRequestContext:
    """构造可信业务上下文（仅合成用户）。"""
    return ServiceRequestContext(
        user_id=user_id,
        actor_id="actor_demo",
        trace_id="trace_drift",
        session_id="sess_drift",
    )


def _make_event() -> MemorySourceEvent:
    """构造合成 MemorySourceEvent（Canonical 字段，drift 测试专用）。"""
    now = datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
    return MemorySourceEvent(
        event_id="evt_drift_001",
        user_id="user_demo_a",
        actor_id="actor_demo",
        source_type="tool_result",
        schema_version="0.1",
        event_type="agent_response",
        consent_scope="memory_only",
        idempotency_key="idem_drift",
        source_business_status=SourceBusinessStatus.SUCCESS,
        occurred_at=now,
        captured_at=now,
        session_id="sess_drift",
        tool_call_id="tool_drift_001",
    )


# ── DRIFT-001：captured_at 为 Canonical 写字段，collected_at 仅 legacy 只读 ──


def test_turn_finalized_event_uses_captured_at_as_write_field():
    """TurnFinalizedEvent 必须以 captured_at 作为可写字段（Canonical 真源）。"""
    assert "captured_at" in {
        f.name for f in dataclasses.fields(TurnFinalizedEvent)
    }, "TurnFinalizedEvent 必须声明 captured_at 写字段（DRIFT-001）"
    assert "collected_at" not in {
        f.name for f in dataclasses.fields(TurnFinalizedEvent)
    }, "collected_at 不得作为 dataclass 写字段（仅允许只读 property）"


def test_turn_finalized_event_collected_at_is_readonly_alias():
    """collected_at 为只读 legacy alias，值等于 captured_at。"""
    ev = TurnFinalizedEvent(
        session_id="sess_drift",
        user_text="你好",
        assistant_text="好的",
    )
    assert ev.collected_at == ev.captured_at, "collected_at 必须归一为 captured_at"
    assert isinstance(ev.collected_at, datetime)
    # 尝试写 collected_at 必须失败（property 无 setter → dataclass 冻结语义）
    with pytest_raises(AttributeError):
        ev.collected_at = datetime.now(timezone.utc)


def test_turn_finalized_event_accepts_captured_at_constructor():
    """新 Canonical 写路径：构造时显式传入 captured_at。"""
    ts = datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
    ev = TurnFinalizedEvent(
        session_id="sess_drift",
        user_text="你好",
        assistant_text="好的",
        captured_at=ts,
    )
    assert ev.captured_at == ts
    assert ev.collected_at == ts


# ── DRIFT-008/009/015/016：候选短名字段必须经治理层唯一映射到 Canonical ──


def test_preference_candidate_short_fields_map_to_canonical_domain():
    """PreferenceCandidate key/value/scope/confidence 经 Governance 唯一映射。"""
    candidate = PreferenceCandidate(
        key="response.language",
        value="zh-CN",
        category="presentation",
        scope="global",
        confidence=0.7,
        explicitness="explicit",
        is_temporary=False,
        should_persist=True,
        evidence="用户声明中文偏好",
        source_event_id="evt_drift_001",
        memory_status="candidate",
    )
    domain = CandidateGovernanceService().admit_with_event(
        candidate,
        _make_event(),
        _make_ctx(),
        entity_id="pref_drift_001",
    )
    # Domain 必须使用 Canonical 字段名（preference_key/preference_value/
    # preference_scope/confidence_score），而非候选短名
    assert domain.preference_key == "response.language"
    assert domain.preference_value == "zh-CN"
    assert domain.preference_scope.value == "global"
    assert domain.confidence_score == 0.7
    assert domain.memory_status.value == "candidate"


def test_knowledge_candidate_short_fields_map_to_canonical_domain():
    """KnowledgeCandidate fact/category/confidence 经 Governance 唯一映射。"""
    candidate = KnowledgeCandidate(
        fact="部署前先执行冒烟测试",
        category="workflow",
        evidence="真实 Tool 证据",
        source_event_id="evt_drift_001",
        confidence=0.85,
        memory_status="candidate",
    )
    domain = CandidateGovernanceService().admit_with_event(
        candidate,
        _make_event(),
        _make_ctx(),
        entity_id="knl_drift_001",
        memory_type=MemoryType.MEDIUM_TERM,
    )
    # Domain 使用 Canonical：content_summary/knowledge_type/confidence_score
    assert domain.content_summary == "部署前先执行冒烟测试"
    assert domain.knowledge_type.value == "workflow"
    assert domain.confidence_score == 0.85
    assert domain.memory_status.value == "candidate"


# ── DRIFT-014：memory_status 唯一业务真值，禁止第二套状态字段 ──


def test_candidate_memory_status_literal_single_source():
    """候选模型 memory_status 必须恒为 Literal['candidate']（B2，禁止 verified）。"""
    from typing import Literal, get_args

    pref_ann = PreferenceCandidate.model_fields["memory_status"].annotation
    knl_ann = KnowledgeCandidate.model_fields["memory_status"].annotation
    assert set(get_args(pref_ann)) == {"candidate"}
    assert set(get_args(knl_ann)) == {"candidate"}
    # 显式防止 LLM 可自封的其他状态值混入
    assert Literal["candidate"] in (pref_ann,)
    assert get_args(pref_ann) == ("candidate",)
    assert get_args(knl_ann) == ("candidate",)


def test_candidate_models_have_no_second_status_field():
    """候选模型不得新增 event_status/lifecycle_status/verified 等第二套状态字段。"""
    forbidden = {"event_status", "lifecycle_status", "verified"}
    for model in (PreferenceCandidate, KnowledgeCandidate):
        fields = set(model.model_fields)
        assert not (fields & forbidden), (
            f"{model.__name__} 出现第二套业务状态字段: {fields & forbidden}"
        )


# ── DRIFT-001 REWORK-R1：legacy collected_at 输入归一 + 双字段冲突拒绝 ──


def test_legacy_collected_at_constructor_normalizes_to_captured_at():
    """REWORK-R1：legacy 构造输入 collected_at=ts 归一为 captured_at（不抛 TypeError）。"""
    ts = datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
    ev = TurnFinalizedEvent(
        session_id="sess_drift",
        user_text="你好",
        assistant_text="好的",
        collected_at=ts,
    )
    assert ev.captured_at == ts
    assert ev.collected_at == ts


def test_legacy_payload_with_collected_at_normalizes_via_kwargs_unpack():
    """REWORK-R1：legacy transport payload（含 collected_at 键）经 **payload 构造归一。"""
    ts = datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
    payload = {
        "session_id": "sess_drift",
        "user_text": "你好",
        "assistant_text": "好的",
        "collected_at": ts,
    }
    ev = TurnFinalizedEvent(**payload)
    assert ev.captured_at == ts
    assert ev.collected_at == ts


def test_both_collected_at_and_captured_at_equal_accepted():
    """REWORK-R1：两字段同给且一致 → 接受（alias 一致，无冲突）。"""
    ts = datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
    ev = TurnFinalizedEvent(
        session_id="sess_drift",
        user_text="你好",
        assistant_text="好的",
        captured_at=ts,
        collected_at=ts,
    )
    assert ev.captured_at == ts


def test_both_collected_at_and_captured_at_conflict_rejected():
    """REWORK-R1：两字段同给且不一致 → 冻结纪律拒绝（fail-closed）。"""
    ts1 = datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
    ts2 = datetime(2026, 9, 3, 8, 0, 1, tzinfo=timezone.utc)
    with pytest_raises(ValueError):
        TurnFinalizedEvent(
            session_id="sess_drift",
            user_text="你好",
            assistant_text="好的",
            captured_at=ts1,
            collected_at=ts2,
        )


# ── DRIFT-001 REWORK-R3：A 轨 providers 反向门禁扩展（AST/allowlist） ──


def _providers_dir() -> Path:
    """memory-service/providers 目录（A 轨受控 Provider 模块）。"""
    return Path(__file__).resolve().parents[1] / "providers"


def _scan_providers_for_collected_at_write() -> list:
    """AST 扫描 memory-service/providers/*.py 的可写 collected_at 声明/赋值。

    违规（Schema 漂移回归）：
    - 类级 `collected_at: <类型> = ...`（dataclass/Pydantic 可写字段声明）；
    - 任意 `<obj>.collected_at = ...` 写路径。
    TurnFinalizedEvent 的只读 `def collected_at` property 属合法读别名，不在此列。
    """
    import ast

    offenders = []
    providers = _providers_dir()
    for path in sorted(providers.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for stmt in node.body:
                    if (
                        isinstance(stmt, ast.AnnAssign)
                        and isinstance(stmt.target, ast.Name)
                        and stmt.target.id == "collected_at"
                    ):
                        offenders.append(
                            f"{path.name}:{stmt.lineno}: 类级可写字段 collected_at"
                        )
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if (
                        isinstance(t, ast.Attribute)
                        and t.attr == "collected_at"
                    ):
                        offenders.append(
                            f"{path.name}:{node.lineno}: 可写路径 {type(t.value).__name__}.collected_at"
                        )
    return offenders


def test_providers_have_no_writable_collected_at_field():
    """REWORK-R3：memory-service/providers 不得重新出现可写 collected_at 业务字段。"""
    offenders = _scan_providers_for_collected_at_write()
    assert not offenders, (
        "Schema 漂移回归：A 轨 providers 出现可写 collected_at：\n"
        + "\n".join(offenders)
    )


def pytest_raises(exc_type):
    """最小断言辅助（不依赖 pytest fixture 导入顺序）。"""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        try:
            yield
        except exc_type:
            return
        raise AssertionError(f"expected {exc_type.__name__}")

    return _cm()