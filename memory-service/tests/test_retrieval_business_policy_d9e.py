"""
test_retrieval_business_policy_d9e.py — Day9 E 标准 Memory Context 检索业务策略骨架测试

对齐任务卡：day9-e-03-retrieval-business-policy-skeleton-v1
（E 轨业务层标准检索策略骨架：把 active/current 业务约束转换为 B 轨既有契约
 RetrievalFilter / RerankPolicy 可消费的确定性输入，保留权重注入点但不冻结
 最终权重）。

覆盖范围（对齐已批准方案）：
- L0 静态：
  - 模块可导入；__all__ 与公开符号精确匹配；
  - POLICY_VERSION / STANDARD_ALLOWED_MEMORY_STATUSES /
    STANDARD_CONFLICT_POLICY / REASON_CODES 常量稳定；
  - build_weighted_rerank_policy 两个权重参数签名级无默认值；
  - build_standard_filter 返回 B 轨 RetrievalFilter 实例（复用而非复制）。
- L1 单元：
  - 构造入口与合法性：空/纯空白 user_id → ValueError；naive as_of →
    pydantic ValidationError 传播；options 收窄项（knowledge_types /
    memory_types / allowed_sensitivity）正确合并；同输入两次构造
    model_dump() 完全相等（确定性）；
  - 放宽通道封死：StandardKnowledgeContextOptions extra="forbid" 拒绝
    allowed_memory_statuses / conflict_policy / object_types 等未知字段；
    构造结果恒 allowed_memory_statuses==["active"]、
    conflict_policy=="exclude_unresolved"；
  - 逐状态准入：MemoryStatus 六值全覆盖——active 正向通过，candidate /
    superseded / deprecated / expired / removed 各自独立 reason_code 负向
    拒绝；未知字符串（"forgotten"、"active "、""）→ rejected_unknown_status
    fail-closed；reason_code ∈ 固定 frozenset 且不拼接正文/载荷。
- L1 集成（直接调用 B 轨 fuse_retrieval 公开入口，证明业务过滤进入融合流程）：
  - active + is_current + resolved → 进入融合结果（正向通过）；
  - 负向五状态（均 is_current=True，排除 current-version 干扰）→ 输出为空；
  - unresolved conflict fail-closed：active 但 conflict_state="unresolved" → 为空；
  - cross-user / current-version 未被绕过：bob 记录对 alice 过滤器 → 空；
    stale v1 + current v2 → 仅 v2；双 current → 失败封闭为空；
  - 敏感度仅收窄：默认 allowed_sensitivity=[] 行为与 B 轨一致；收窄
    ["internal"] 后非 internal 记录被丢弃；
  - 权重默认与注入：默认路径 rerank_policy=DEFAULT_RERANK_POLICY（None）→
    explanation algorithm_version=="rrf-v1" 且 rrf_score==final_score；
    build_weighted_rerank_policy(fts5_weight=0.5, vector_weight=2.0) 注入后
    排序改变且 explanation 为 weighted-rrf/v1；非法权重（0/负数/字符串）→
    RerankPolicy 原生校验 ValueError 传播（复用校验，不复制）；
  - 诊断不含正文：ContextStatusDecision.model_dump() 无 content 等字段。

明确不在本测试范围内：
- 不测试 SQLite / FTS5 / Vector SDK / IPC / Gateway / Outbox / 迁移。
- 不测试真实麒麟宿主能力；runtime_required=false，不声明 HOST_VERIFIED。
- 不修改 retrieval/** / db/** / domain/enums.py / service/__init__.py /
  B 轨既有测试（回归文件仅合跑验证）。

测试纪律：
- 不使用 Mock、skip、xfail 或弱化断言（含 B 轨 fail-closed 语义）。
- 仅使用合成用户 ID（user_demo_d9e_03）与脱敏/虚构知识正文。
- 测试中的权重（0.5/2.0）为合成验证值，非冻结最终权重；
  deprecated 负向口径来源：任务卡 + D9 Gold boundary 语义（本测试按任务卡断言）。
"""

import inspect
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.enums import MemoryStatus  # noqa: E402
from retrieval.contracts import (  # noqa: E402
    Channel,
    KnowledgeIndexMetadata,
    KnowledgeFilter,
    ObjectType,
    RerankPolicy,
    RetrievalFilter,
    RetrievalHit,
    ScoreSemantics,
)
from retrieval.fusion import TruthRecord, fuse_retrieval  # noqa: E402
import service.retrieval_business_policy as rbp  # noqa: E402
from service.retrieval_business_policy import (  # noqa: E402
    DEFAULT_RERANK_POLICY,
    POLICY_VERSION,
    REASON_ADMITTED_STANDARD_CONTEXT,
    REASON_CODES,
    REASON_REJECTED_CANDIDATE,
    REASON_REJECTED_DEPRECATED,
    REASON_REJECTED_EXPIRED,
    REASON_REJECTED_REMOVED,
    REASON_REJECTED_SUPERSEDED,
    STANDARD_ALLOWED_MEMORY_STATUSES,
    STANDARD_CONFLICT_POLICY,
    ContextStatusDecision,
    KnowledgeContextPolicy,
    StandardKnowledgeContextOptions,
    build_weighted_rerank_policy,
)

# ── 合成数据基座（不含任何真实用户数据/密钥；正文为脱敏虚构内容） ──

USER = "user_demo_d9e_03"
NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)


def _hit(memory_id, version_id="v1", channel=Channel.FTS5, rank=1, user_id=USER, raw_score=0.0):
    return RetrievalHit(
        memory_id=memory_id,
        version_id=version_id,
        user_id=user_id,
        channel=channel,
        rank=rank,
        raw_score=raw_score,
        score_semantics=(
            ScoreSemantics.BM25
            if channel is Channel.FTS5
            else ScoreSemantics.SDK_SCORE_UNVERIFIED
        ),
        provider="d9e-test",
        retrieved_at=NOW,
        filter_fingerprint="hmac-sha256:k1:" + "a" * 64,
    )


def _truth(
    memory_id,
    version_id="v1",
    user_id=USER,
    status="active",
    sensitivity="internal",
    content="synthetic-knowledge-body-v1",
    conflict_state="resolved",
    is_current=True,
):
    """构造 knowledge 回源真值行；knowledge.memory_status 恒与 memory_status 一致。"""
    return TruthRecord(
        memory_id=memory_id,
        version_id=version_id,
        user_id=user_id,
        object_type=ObjectType.KNOWLEDGE,
        memory_type="long_term",
        memory_status=status,
        content=content,
        sensitivity=sensitivity,
        conflict_state=conflict_state,
        is_current=is_current,
        knowledge=KnowledgeIndexMetadata(
            knowledge_type="workflow",
            source_event_id="d9e-fixture",
            memory_status=status,
        ),
    )


def _policy(*, user_id=USER, as_of=NOW, options=None):
    """经标准策略构造入口生成 B 轨 RetrievalFilter（本文件唯一 filter 来源）。"""
    return KnowledgeContextPolicy().build_standard_filter(
        user_id=user_id, as_of=as_of, options=options
    )


# ── L0 静态：模块结构、常量、签名、复用证明 ──


def test_module_importable_and_all_exact():
    """模块可导入；__all__ 与公开符号集合精确匹配。"""
    assert set(rbp.__all__) == {
        "POLICY_VERSION",
        "STANDARD_ALLOWED_MEMORY_STATUSES",
        "STANDARD_CONFLICT_POLICY",
        "REASON_CODES",
        "REASON_ADMITTED_STANDARD_CONTEXT",
        "REASON_REJECTED_CANDIDATE",
        "REASON_REJECTED_SUPERSEDED",
        "REASON_REJECTED_DEPRECATED",
        "REASON_REJECTED_EXPIRED",
        "REASON_REJECTED_REMOVED",
        "REASON_REJECTED_UNKNOWN",
        "ContextStatusDecision",
        "StandardKnowledgeContextOptions",
        "KnowledgeContextPolicy",
        "build_weighted_rerank_policy",
        "DEFAULT_RERANK_POLICY",
    }


def test_standard_constants_stable():
    """策略/冲突/负向集合常量稳定，负向集合与冻结枚举减 active 精确对应。"""
    assert rbp.POLICY_VERSION == "knowledge-context-policy/v1"
    assert rbp.STANDARD_ALLOWED_MEMORY_STATUSES == ("active",)
    assert rbp.STANDARD_CONFLICT_POLICY == "exclude_unresolved"
    assert rbp.REASON_CODES == frozenset({
        "admitted_standard_context",
        "rejected_candidate_status",
        "rejected_superseded_status",
        "rejected_deprecated_status",
        "rejected_expired_status",
        "rejected_removed_status",
        "rejected_unknown_status",
    })
    frozen_values = {status.value for status in MemoryStatus}
    assert set(rbp.STANDARD_ALLOWED_MEMORY_STATUSES).issubset(frozen_values)
    assert frozen_values - set(rbp.STANDARD_ALLOWED_MEMORY_STATUSES) == {
        "candidate",
        "superseded",
        "deprecated",
        "expired",
        "removed",
    }


def test_weighted_policy_signature_has_no_default_weights():
    """build_weighted_rerank_policy 两个权重参数签名级无默认值（不冻结权重）。"""
    sig = inspect.signature(rbp.build_weighted_rerank_policy)
    assert "fts5_weight" in sig.parameters
    assert "vector_weight" in sig.parameters
    assert sig.parameters["fts5_weight"].default is inspect.Parameter.empty
    assert sig.parameters["vector_weight"].default is inspect.Parameter.empty


def test_build_weighted_rerank_policy_returns_b_track_rerank_policy():
    """权重注入点产出 B 轨 RerankPolicy（复用而非复制）。"""
    policy = build_weighted_rerank_policy(fts5_weight=0.5, vector_weight=2.0)
    assert isinstance(policy, RerankPolicy)
    assert policy.version == "weighted-rrf/v1"
    assert policy.channel_weights == {Channel.FTS5: 0.5, Channel.VECTOR: 2.0}


# ── L1 单元：构造入口与合法性 ──


def test_build_standard_filter_returns_b_track_filter_pinned_fields():
    """构造入口产出合法 RetrievalFilter，关键字段钉死且确定性。"""
    flt = _policy()
    assert isinstance(flt, RetrievalFilter)
    assert flt.object_types == [ObjectType.KNOWLEDGE]
    assert flt.allowed_memory_statuses == ["active"]
    assert flt.conflict_policy == "exclude_unresolved"
    assert flt.user_id == USER
    assert flt.as_of == NOW
    # 同输入两次构造完全相等（确定性；策略内禁止 datetime.now()）
    assert flt.model_dump() == _policy().model_dump()


def test_build_standard_filter_options_narrowing_merges():
    """options 收窄项正确合并进 filter：knowledge_types/memory_types/sensitivity。"""
    options = StandardKnowledgeContextOptions(
        knowledge=KnowledgeFilter(knowledge_types=["fact", "constraint"]),
        memory_types=["long_term"],
        allowed_sensitivity=["internal"],
    )
    flt = _policy(options=options)
    # KnowledgeFilter 去重排序：["constraint","fact"]
    assert flt.knowledge.knowledge_types == ["constraint", "fact"]
    assert flt.memory_types == ["long_term"]
    assert flt.allowed_sensitivity == ["internal"]


@pytest.mark.parametrize("bad_user_id", ["", "   ", "\t\n"])
def test_build_standard_filter_rejects_blank_user_id(bad_user_id):
    """空/纯空白 user_id → 确定性 ValueError（策略层最小约束）。"""
    with pytest.raises(ValueError, match="user_id 不得为空或纯空白"):
        _policy(user_id=bad_user_id)


def test_build_standard_filter_rejects_naive_as_of():
    """naive as_of → B 轨 RetrievalFilter 时区校验错误原样传播。"""
    with pytest.raises(ValidationError):
        KnowledgeContextPolicy().build_standard_filter(
            user_id=USER, as_of=datetime(2026, 8, 31, 12, 0, 0)
        )


@pytest.mark.parametrize(
    "relax_field",
    [
        {"allowed_memory_statuses": ["active", "candidate"]},
        {"conflict_policy": "resolve"},
        {"object_types": [ObjectType.PREFERENCE]},
    ],
)
def test_options_forbid_relaxation_fields(relax_field):
    """放宽通道封死：options extra="forbid" 结构上拒绝状态/冲突/对象类型字段。"""
    with pytest.raises(ValidationError):
        StandardKnowledgeContextOptions(**relax_field)


# ── L1 单元：逐状态准入决策 ──


def test_admit_active_status_passes():
    """active 正向通过，reason_code 固定，policy_version 稳定。"""
    decision = KnowledgeContextPolicy().admit_memory_status("active")
    assert isinstance(decision, ContextStatusDecision)
    assert decision.admitted is True
    assert decision.reason_code == REASON_ADMITTED_STANDARD_CONTEXT
    assert decision.policy_version == POLICY_VERSION


@pytest.mark.parametrize(
    "status, expected_reason",
    [
        ("candidate", "rejected_candidate_status"),
        ("superseded", "rejected_superseded_status"),
        ("deprecated", "rejected_deprecated_status"),
        ("expired", "rejected_expired_status"),
        ("removed", "rejected_removed_status"),
    ],
)
def test_admit_rejects_non_active_frozen_statuses(status, expected_reason):
    """五负向状态各自独立 reason_code 拒绝，fail-closed。"""
    decision = KnowledgeContextPolicy().admit_memory_status(status)
    assert decision.admitted is False
    assert decision.reason_code == expected_reason
    assert decision.policy_version == POLICY_VERSION


@pytest.mark.parametrize("unknown_status", ["forgotten", "active ", "ACTIVE", ""])
def test_admit_unknown_status_fails_closed(unknown_status):
    """未知字符串 → rejected_unknown_status，不猜测归属。"""
    decision = KnowledgeContextPolicy().admit_memory_status(unknown_status)
    assert decision.admitted is False
    assert decision.reason_code == "rejected_unknown_status"
    assert decision.policy_version == POLICY_VERSION


def test_memory_status_full_coverage_and_reason_discipline():
    """六值 MemoryStatus 全覆盖；reason_code 恒命中固定映射且属于固定 frozenset。"""
    policy = KnowledgeContextPolicy()
    decisions = [policy.admit_memory_status(status.value) for status in MemoryStatus]
    assert {d.memory_status for d in decisions} == {
        status.value for status in MemoryStatus
    }
    # reason_code 必须全部命中固定权威集合（封闭性：不存在动态拼接新码）
    assert {d.reason_code for d in decisions} <= REASON_CODES
    # 固定映射：active 放行，其余五值各自独立、与固定 reason_code 精确对应
    expected_code = {
        "active": REASON_ADMITTED_STANDARD_CONTEXT,
        "candidate": REASON_REJECTED_CANDIDATE,
        "superseded": REASON_REJECTED_SUPERSEDED,
        "deprecated": REASON_REJECTED_DEPRECATED,
        "expired": REASON_REJECTED_EXPIRED,
        "removed": REASON_REJECTED_REMOVED,
    }
    assert {d.memory_status: d.reason_code for d in decisions} == expected_code
    assert len([d for d in decisions if d.admitted]) == 1


def test_reason_code_has_no_payload_injection():
    """reason_code 封闭性：任意输入（含未知/空白漂移取值）输出必命中固定集合。

    固定 reason_code 按设计内嵌被拒状态的固定关键字（如 rejected_superseded_status
    中的 superseded），因此注入红线是：①输出恒属于 REASON_CODES 固定集合；
    ②未知输入的任意载荷不得被反射为集合之外的新码。
    """
    policy = KnowledgeContextPolicy()
    for status in ["forgotten", "active ", "ACTIVE", "", "candidate", "superseded"]:
        decision = policy.admit_memory_status(status)
        assert decision.reason_code in REASON_CODES
    injected = policy.admit_memory_status("forgotten")
    assert injected.reason_code == "rejected_unknown_status"
    assert "forgotten" not in injected.reason_code


def test_admit_memory_status_is_deterministic():
    """同输入两次判定 model_dump() 完全相等。"""
    policy = KnowledgeContextPolicy()
    first = policy.admit_memory_status("superseded")
    second = policy.admit_memory_status("superseded")
    assert first.model_dump() == second.model_dump()


def test_decision_has_no_content_fields():
    """决策模型不含 candidate 正文/证据字段（诊断不暴露正文）。"""
    decision = KnowledgeContextPolicy().admit_memory_status("active")
    assert set(decision.model_dump().keys()) == {
        "memory_status",
        "admitted",
        "reason_code",
        "policy_version",
    }


# ── L1 集成：fuse_retrieval 公开入口（证明过滤真实进入融合流程） ──


def test_fusion_admits_active_current_knowledge():
    """active + is_current + resolved → 通过策略 filter 进入融合结果（正向）。"""
    hits = [_hit("mem-ok", "v1", Channel.FTS5, 1)]
    truth = {(USER, "mem-ok", "v1"): _truth("mem-ok", status="active")}
    out = fuse_retrieval(fts5_hits=hits, vector_hits=[], truth=truth, flt=_policy())
    assert [candidate.memory_id for candidate in out] == ["mem-ok"]
    assert out[0].memory_status == "active"
    assert out[0].conflict_state == "resolved"


@pytest.mark.parametrize(
    "status",
    ["candidate", "superseded", "deprecated", "expired", "removed"],
)
def test_fusion_rejects_non_active_statuses(status):
    """负向五状态（均 is_current=True）→ 融合输出为空（业务过滤真实生效）。"""
    hits = [_hit(f"mem-{status}", "v1", Channel.FTS5, 1)]
    truth = {
        (USER, f"mem-{status}", "v1"): _truth(f"mem-{status}", status=status)
    }
    out = fuse_retrieval(fts5_hits=hits, vector_hits=[], truth=truth, flt=_policy())
    assert out == []


def test_fusion_unresolved_conflict_fails_closed():
    """active 但 conflict_state="unresolved" → 输出为空（B 轨硬过滤未被绕过）。"""
    hits = [_hit("mem-conf", "v1", Channel.FTS5, 1)]
    truth = {
        (USER, "mem-conf", "v1"): _truth(
            "mem-conf", status="active", conflict_state="unresolved"
        )
    }
    out = fuse_retrieval(fts5_hits=hits, vector_hits=[], truth=truth, flt=_policy())
    assert out == []


def test_fusion_cross_user_is_not_bypassed():
    """bob 记录对 alice 过滤器 → 输出为空（跨用户硬过滤未被策略绕过）。"""
    bob = "user_demo_d9e_03_bob"
    hits = [_hit("mem-bob", "v1", Channel.FTS5, 1, user_id=bob)]
    truth = {(bob, "mem-bob", "v1"): _truth("mem-bob", user_id=bob)}
    out = fuse_retrieval(fts5_hits=hits, vector_hits=[], truth=truth, flt=_policy())
    assert out == []


def test_fusion_keeps_only_current_version():
    """stale v1 + current v2 → 仅 current v2 返回（current-version 未被绕过）。"""
    hits = [
        _hit("mem-cv", "v1", Channel.FTS5, 2),
        _hit("mem-cv", "v2", Channel.FTS5, 1),
    ]
    truth = {
        (USER, "mem-cv", "v1"): _truth("mem-cv", version_id="v1", is_current=False),
        (USER, "mem-cv", "v2"): _truth("mem-cv", version_id="v2", is_current=True),
    }
    out = fuse_retrieval(fts5_hits=hits, vector_hits=[], truth=truth, flt=_policy())
    assert [candidate.version_id for candidate in out] == ["v2"]


def test_fusion_double_current_fails_closed():
    """双 current 版本 → 失败封闭为空（异常真源状态下不猜测版本）。"""
    hits = [
        _hit("mem-dc", "v1", Channel.FTS5, 1),
        _hit("mem-dc", "v2", Channel.FTS5, 2),
    ]
    truth = {
        (USER, "mem-dc", "v1"): _truth("mem-dc", version_id="v1", is_current=True),
        (USER, "mem-dc", "v2"): _truth("mem-dc", version_id="v2", is_current=True),
    }
    out = fuse_retrieval(fts5_hits=hits, vector_hits=[], truth=truth, flt=_policy())
    assert out == []


def test_knowledge_type_narrowing_constrains_fusion():
    """options knowledge_types 收窄真实约束融合（进一步过滤生效）。"""
    options = StandardKnowledgeContextOptions(
        knowledge=KnowledgeFilter(knowledge_types=["fact"])
    )
    hits = [_hit("mem-wf", "v1", Channel.FTS5, 1)]
    truth = {(USER, "mem-wf", "v1"): _truth("mem-wf")}  # truth knowledge_type="workflow"
    out = fuse_retrieval(
        fts5_hits=hits, vector_hits=[], truth=truth, flt=_policy(options=options)
    )
    assert out == []


def test_default_sensitivity_does_not_add_constraint():
    """默认 allowed_sensitivity=[] → 与 B 轨默认行为一致（不额外约束）。"""
    hits = [_hit("mem-pub", "v1", Channel.FTS5, 1)]
    truth = {(USER, "mem-pub", "v1"): _truth("mem-pub", sensitivity="public")}
    out = fuse_retrieval(fts5_hits=hits, vector_hits=[], truth=truth, flt=_policy())
    assert [candidate.memory_id for candidate in out] == ["mem-pub"]


def test_sensitivity_narrowing_applies():
    """收窄 allowed_sensitivity=["internal"] → 非 internal 记录被丢弃。"""
    options = StandardKnowledgeContextOptions(allowed_sensitivity=["internal"])
    hits = [
        _hit("mem-int", "v1", Channel.FTS5, 1),
        _hit("mem-pub", "v1", Channel.FTS5, 2),
    ]
    truth = {
        (USER, "mem-int", "v1"): _truth("mem-int", sensitivity="internal"),
        (USER, "mem-pub", "v1"): _truth("mem-pub", sensitivity="public"),
    }
    out = fuse_retrieval(
        fts5_hits=hits, vector_hits=[], truth=truth, flt=_policy(options=options)
    )
    assert [candidate.memory_id for candidate in out] == ["mem-int"]


def test_fusion_default_rerank_policy_is_none_rrf_v1():
    """默认路径 DEFAULT_RERANK_POLICY=None → rrf-v1 等权，rrf_score==final_score。"""
    assert DEFAULT_RERANK_POLICY is None
    hits = [
        _hit("mem-default", "v1", Channel.FTS5, 1),
        _hit("mem-default", "v1", Channel.VECTOR, 1),
    ]
    truth = {(USER, "mem-default", "v1"): _truth("mem-default")}
    out = fuse_retrieval(
        fts5_hits=hits,
        vector_hits=[],
        truth=truth,
        flt=_policy(),
        rerank_policy=DEFAULT_RERANK_POLICY,
    )
    assert len(out) == 1
    assert out[0].explanation["algorithm_version"] == "rrf-v1"
    assert out[0].rrf_score == out[0].final_score


def test_weighted_policy_changes_ordering_and_explanation():
    """注入 weighted-rrf/v1（fts5=0.5, vector=2.0）→ 排序改变且 explanation 更新。

    合成排序事实：
    - rrf-v1 等权：mem-a(FTS5 r1, VEC r3) score≈0.032266 >
      mem-b(FTS5 r2, VEC r2) score≈0.032258 → [mem-a, mem-b]；
    - weighted(0.5, 2.0)：mem-a≈0.039943 < mem-b≈0.040323 → [mem-b, mem-a]。
    """
    hits = [
        _hit("mem-a", "v1", Channel.FTS5, 1),
        _hit("mem-a", "v1", Channel.VECTOR, 3),
        _hit("mem-b", "v1", Channel.FTS5, 2),
        _hit("mem-b", "v1", Channel.VECTOR, 2),
    ]
    truth = {
        (USER, "mem-a", "v1"): _truth("mem-a"),
        (USER, "mem-b", "v1"): _truth("mem-b"),
    }
    default_out = fuse_retrieval(fts5_hits=hits, vector_hits=[], truth=truth, flt=_policy())
    assert [candidate.memory_id for candidate in default_out] == ["mem-a", "mem-b"]

    weighted = build_weighted_rerank_policy(fts5_weight=0.5, vector_weight=2.0)
    weighted_out = fuse_retrieval(
        fts5_hits=hits,
        vector_hits=[],
        truth=truth,
        flt=_policy(),
        rerank_policy=weighted,
    )
    assert [candidate.memory_id for candidate in weighted_out] == ["mem-b", "mem-a"]
    assert weighted_out[0].explanation["algorithm_version"] == "weighted-rrf/v1"
    assert weighted_out[0].explanation["weighted_rrf"]["channel_weights"] == {
        "fts5": 0.5,
        "vector": 2.0,
    }


@pytest.mark.parametrize(
    "fts5_weight, vector_weight",
    [
        (0.0, 1.0),  # 零权重
        (1.0, -1.0),  # 负权重
        (0.0, 0.0),  # 双零
        ("0.5", 1.0),  # 字符串类型
    ],
)
def test_invalid_weights_propagate_rerank_policy_validation(fts5_weight, vector_weight):
    """非法权重（0/负数/字符串）→ RerankPolicy 原生校验 ValueError 传播。"""
    with pytest.raises(ValueError):
        build_weighted_rerank_policy(
            fts5_weight=fts5_weight, vector_weight=vector_weight
        )