"""
test_conflict_resolution_policy_d8e.py — Day8 E 轨知识冲突六档证据优先级裁决策略单元测试

对齐任务卡：day8-e-02-conflict-resolution-policy-v1
（新增纯业务冲突裁决策略，按既有六档证据可信优先级对同用户知识冲突给出
 可解释、固定 reason_code 的保留/共存/延后决策，并保证真实 Tool 事实
 高于模型自述；跨 user_id fail-closed；同档不可决 DEFER）。

覆盖范围（对齐已批准方案）：
- 模块可导入；5 个公开类型可引用；__all__ 集合精确匹配。
- EvidenceTier 六档值完整（声明顺序即优先级顺序）；DecisionAction 五值
  完整——action/reason_code 不依赖自然语言随机生成。
- 六档优先级全对（15 对 × 双向）：任意高档来源均不会被低档来源覆盖。
- 真实 Tool 事实（Tier 3）胜模型自述（Tier 6），双向验证。
- 用户最新显式配置（Tier 1 同档）仅依据可信时间字段 recorded_at 决胜
  （含不同时区时间事实归一化比较）。
- 同一优先级不可决 → DEFER（Tier 1 时间相等/时间缺失；Tier 2-6 同档）。
- 同用户不同 scope → COEXIST(scope_distinguishable)；同 scope / 单侧
  scope=None → 不输出 COEXIST，进入证据比较。
- 跨 user_id → fail-closed REJECT(cross_user_blocked)。
- 类型准入：None / dict / 非 ConflictSide → REJECT(invalid_input)。
- 确定性：同输入两次 resolve 的 model_dump() 完全相等。
- reason_code 全部属于固定权威集合，不含用户正文/密钥/Token。

明确不在本测试范围内：
- 不测试语义相似度/向量相似度/contradiction/temporal_inconsistency
  检测阈值（属 B/上游能力，本策略不实现）。
- 不测试 SQLite memory_conflict 持久化、事务、Outbox、Vector、FTS5。
- 不修改 domain/conflict.py、domain/enums.py 或共享枚举。

测试纪律：
- 不使用 Mock、skip、xfail 或弱化断言。
- 测试数据仅使用合成用户 ID（user_demo_d8e）、合成知识 ID（kn_d8e_*）
  与脱敏/虚构内容，不写入任何真实凭据。
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import service.conflict_resolution_policy as crp  # noqa: E402
from service.conflict_resolution_policy import (  # noqa: E402
    ConflictDecision,
    ConflictResolutionPolicy,
    ConflictSide,
    DecisionAction,
    EvidenceTier,
)

# ── 合成数据基座（不含任何真实用户数据/密钥） ──

USER = "user_demo_d8e"
T0 = datetime(2026, 8, 25, 9, 0, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 8, 25, 10, 0, 0, tzinfo=timezone.utc)
POLICY = ConflictResolutionPolicy()

# 六档优先级（声明顺序 = 优先级从高到低，与 _TIER_PRIORITY 数值语义一致）
TIER_ORDER = [
    EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
    EvidenceTier.USER_CONFIRMED,
    EvidenceTier.TOOL_EXECUTION_RESULT,
    EvidenceTier.CONSISTENT_BEHAVIOR_MULTIPLE,
    EvidenceTier.BEHAVIOR_INFERENCE_SINGLE,
    EvidenceTier.MODEL_INFERENCE,
]

# 固定 reason_code 权威集合（策略层所有可达判定码）
EXPECTED_REASON_CODES = {
    "invalid_input",
    "cross_user_blocked",
    "scope_distinguishable",
    "evidence_tier_priority",
    "latest_explicit_config_wins",
    "same_tier_undecidable",
}


def make_side(
    knowledge_id="kn_d8e_01",
    user_id=USER,
    evidence_tier=EvidenceTier.MODEL_INFERENCE,
    scope=None,
    recorded_at=None,
):
    """构造合成 ConflictSide（真实 Pydantic 模型，合成/脱敏数据）。"""
    return ConflictSide(
        knowledge_id=knowledge_id,
        user_id=user_id,
        evidence_tier=evidence_tier,
        scope=scope,
        recorded_at=recorded_at,
    )


# ── 模块与类型结构 ──


def test_module_importable_and_types_exposed():
    """模块可导入；5 个公开类型可引用；__all__ 集合精确匹配。"""
    assert isinstance(POLICY, ConflictResolutionPolicy)
    for name in (
        "EvidenceTier",
        "DecisionAction",
        "ConflictSide",
        "ConflictDecision",
        "ConflictResolutionPolicy",
    ):
        assert hasattr(crp, name)
    assert set(crp.__all__) == {
        "EvidenceTier",
        "DecisionAction",
        "ConflictSide",
        "ConflictDecision",
        "ConflictResolutionPolicy",
    }


def test_evidence_tier_six_values():
    """六档证据优先级完整：6 值集合精确匹配，声明顺序即优先级顺序。"""
    assert {m.value for m in EvidenceTier} == {
        "user_explicit_config_latest",
        "user_confirmed",
        "tool_execution_result",
        "consistent_behavior_multiple",
        "behavior_inference_single",
        "model_inference",
    }
    assert list(EvidenceTier) == TIER_ORDER


def test_decision_action_five_values():
    """action 为固定五值枚举，不依赖自然语言随机生成。"""
    assert {m.value for m in DecisionAction} == {
        "keep_left",
        "keep_right",
        "coexist",
        "defer",
        "reject",
    }


def test_resolve_returns_structured_decision():
    """resolve() 返回 ConflictDecision 且 action/reason_code 固定稳定。"""
    res = POLICY.resolve(
        make_side(evidence_tier=EvidenceTier.TOOL_EXECUTION_RESULT),
        make_side(evidence_tier=EvidenceTier.MODEL_INFERENCE),
    )
    assert isinstance(res, ConflictDecision)
    assert isinstance(res.action, DecisionAction)
    assert isinstance(res.reason_code, str)
    assert res.reason_code in EXPECTED_REASON_CODES


# ── 六档优先级全对（15 对 × 双向）：任意高档来源均不会被低档覆盖 ──

HIGH_LOW_PAIRS = [
    (high, low)
    for i, high in enumerate(TIER_ORDER)
    for low in TIER_ORDER[i + 1 :]
]


@pytest.mark.parametrize("high, low", HIGH_LOW_PAIRS)
def test_higher_tier_always_wins(high, low):
    """高档侧无论在 left 还是 right 均胜出（evidence_tier_priority）。"""
    # 高档在 left：KEEP_LEFT
    res = POLICY.resolve(
        make_side(knowledge_id="kn_d8e_high_left", evidence_tier=high),
        make_side(knowledge_id="kn_d8e_low_right", evidence_tier=low),
    )
    assert res.action is DecisionAction.KEEP_LEFT
    assert res.reason_code == "evidence_tier_priority"
    assert res.winner_id == "kn_d8e_high_left"
    # 高档在 right：KEEP_RIGHT
    res = POLICY.resolve(
        make_side(knowledge_id="kn_d8e_low_left", evidence_tier=low),
        make_side(knowledge_id="kn_d8e_high_right", evidence_tier=high),
    )
    assert res.action is DecisionAction.KEEP_RIGHT
    assert res.reason_code == "evidence_tier_priority"
    assert res.winner_id == "kn_d8e_high_right"


def test_tool_result_beats_model_inference():
    """真实 Tool 事实与模型自述冲突时输出真实 Tool 胜出，固定 reason_code。"""
    tool = make_side(
        knowledge_id="kn_d8e_tool",
        evidence_tier=EvidenceTier.TOOL_EXECUTION_RESULT,
    )
    model = make_side(
        knowledge_id="kn_d8e_model",
        evidence_tier=EvidenceTier.MODEL_INFERENCE,
    )
    res = POLICY.resolve(tool, model)
    assert res.action is DecisionAction.KEEP_LEFT
    assert res.reason_code == "evidence_tier_priority"
    assert res.winner_id == "kn_d8e_tool"
    res = POLICY.resolve(model, tool)
    assert res.action is DecisionAction.KEEP_RIGHT
    assert res.reason_code == "evidence_tier_priority"
    assert res.winner_id == "kn_d8e_tool"


# ── 用户最新显式配置：仅依据可信时间字段决胜 ──


def test_latest_explicit_config_wins_by_time():
    """Tier 1 vs Tier 1：T1 > T0 → 保留 T1 侧（latest_explicit_config_wins）。"""
    older = make_side(
        knowledge_id="kn_d8e_cfg_older",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        recorded_at=T0,
    )
    newer = make_side(
        knowledge_id="kn_d8e_cfg_newer",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        recorded_at=T1,
    )
    res = POLICY.resolve(newer, older)
    assert res.action is DecisionAction.KEEP_LEFT
    assert res.reason_code == "latest_explicit_config_wins"
    assert res.winner_id == "kn_d8e_cfg_newer"
    res = POLICY.resolve(older, newer)
    assert res.action is DecisionAction.KEEP_RIGHT
    assert res.reason_code == "latest_explicit_config_wins"
    assert res.winner_id == "kn_d8e_cfg_newer"


def test_latest_config_wins_with_timezone_normalization():
    """可信时间事实统一归一为 aware UTC 后比较（复用 AwareDatetime）。"""
    # 18:00+08:00 == 10:00 UTC > 09:30 UTC → 东八区侧较新
    beijing_side = make_side(
        knowledge_id="kn_d8e_cfg_beijing",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        recorded_at=datetime(2026, 8, 25, 18, 0, 0, tzinfo=timezone(timedelta(hours=8))),
    )
    utc_side = make_side(
        knowledge_id="kn_d8e_cfg_utc",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        recorded_at=datetime(2026, 8, 25, 9, 30, 0, tzinfo=timezone.utc),
    )
    res = POLICY.resolve(beijing_side, utc_side)
    assert res.action is DecisionAction.KEEP_LEFT
    assert res.reason_code == "latest_explicit_config_wins"
    assert res.winner_id == "kn_d8e_cfg_beijing"
    res = POLICY.resolve(utc_side, beijing_side)
    assert res.action is DecisionAction.KEEP_RIGHT
    assert res.winner_id == "kn_d8e_cfg_beijing"


def test_same_explicit_config_time_defers():
    """Tier 1 vs Tier 1 时间相同 → DEFER(same_tier_undecidable)。"""
    a = make_side(
        knowledge_id="kn_d8e_cfg_a",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        recorded_at=T1,
    )
    b = make_side(
        knowledge_id="kn_d8e_cfg_b",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        recorded_at=T1,
    )
    res = POLICY.resolve(a, b)
    assert res.action is DecisionAction.DEFER
    assert res.reason_code == "same_tier_undecidable"
    assert res.winner_id is None


def test_explicit_config_missing_time_defers():
    """Tier 1 任一侧 recorded_at=None → DEFER（时间事实缺失不可决胜）。"""
    tier1 = {"evidence_tier": EvidenceTier.USER_EXPLICIT_CONFIG_LATEST}
    with_time = make_side(
        knowledge_id="kn_d8e_cfg_t",
        recorded_at=T1,
        **tier1,
    )
    without_time = make_side(knowledge_id="kn_d8e_cfg_nt", **tier1)
    # 两侧均缺失
    res = POLICY.resolve(
        make_side(knowledge_id="kn_d8e_cfg_m1", **tier1),
        make_side(knowledge_id="kn_d8e_cfg_m2", **tier1),
    )
    assert res.action is DecisionAction.DEFER
    assert res.reason_code == "same_tier_undecidable"
    # 仅一侧缺失（双向）
    for left, right in ((with_time, without_time), (without_time, with_time)):
        res = POLICY.resolve(left, right)
        assert res.action is DecisionAction.DEFER
        assert res.reason_code == "same_tier_undecidable"
        assert res.winner_id is None


# ── 同一优先级不可决 → DEFER（Tier 2-6 同档；recorded_at 不参与决胜） ──

NON_EXPLICIT_TIERS = [
    EvidenceTier.USER_CONFIRMED,
    EvidenceTier.TOOL_EXECUTION_RESULT,
    EvidenceTier.CONSISTENT_BEHAVIOR_MULTIPLE,
    EvidenceTier.BEHAVIOR_INFERENCE_SINGLE,
    EvidenceTier.MODEL_INFERENCE,
]


@pytest.mark.parametrize("tier", NON_EXPLICIT_TIERS)
def test_same_tier_non_explicit_defers(tier):
    """Tier 2-6 各自同档 → DEFER；即便时间不同也不得用时间/置信度决胜。"""
    a = make_side(
        knowledge_id="kn_d8e_st_a",
        evidence_tier=tier,
        recorded_at=T1,
    )
    b = make_side(
        knowledge_id="kn_d8e_st_b",
        evidence_tier=tier,
        recorded_at=T0,
    )
    res = POLICY.resolve(a, b)
    assert res.action is DecisionAction.DEFER
    assert res.reason_code == "same_tier_undecidable"
    assert res.winner_id is None


# ── 作用域可区分 → COEXIST（不得无条件覆盖） ──


def test_different_scopes_coexist():
    """同用户不同 scope（均非 None）→ COEXIST(scope_distinguishable)。

    即使两侧档位相差悬殊（Tier 1 vs Tier 6），作用域可区分也优先共存。
    """
    a = make_side(
        knowledge_id="kn_d8e_scope_a",
        evidence_tier=EvidenceTier.MODEL_INFERENCE,
        scope="topic:demo_a",
    )
    b = make_side(
        knowledge_id="kn_d8e_scope_b",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        scope="topic:demo_b",
    )
    res = POLICY.resolve(a, b)
    assert res.action is DecisionAction.COEXIST
    assert res.reason_code == "scope_distinguishable"
    assert res.winner_id is None


def test_same_scope_proceeds_to_evidence():
    """scope 相等 → 不输出 COEXIST，进入证据档比较。"""
    res = POLICY.resolve(
        make_side(
            knowledge_id="kn_d8e_ss_low",
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
            scope="topic:demo_same",
        ),
        make_side(
            knowledge_id="kn_d8e_ss_high",
            evidence_tier=EvidenceTier.TOOL_EXECUTION_RESULT,
            scope="topic:demo_same",
        ),
    )
    assert res.action is DecisionAction.KEEP_RIGHT
    assert res.reason_code == "evidence_tier_priority"
    assert res.winner_id == "kn_d8e_ss_high"


def test_one_scope_none_proceeds_to_evidence():
    """单侧 scope=None → 不输出 COEXIST，进入证据档比较。"""
    res = POLICY.resolve(
        make_side(
            knowledge_id="kn_d8e_os_low",
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
        ),
        make_side(
            knowledge_id="kn_d8e_os_high",
            evidence_tier=EvidenceTier.USER_CONFIRMED,
            scope="topic:demo_x",
        ),
    )
    assert res.action is DecisionAction.KEEP_RIGHT
    assert res.reason_code == "evidence_tier_priority"
    assert res.winner_id == "kn_d8e_os_high"


# ── 跨用户隔离：fail-closed ──


def test_cross_user_fail_closed():
    """不同 user_id 的两条记录不得进入普通冲突裁决 → REJECT。"""
    res = POLICY.resolve(
        make_side(
            knowledge_id="kn_d8e_u1",
            evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        ),
        make_side(
            knowledge_id="kn_d8e_u2",
            user_id="user_demo_other",
            evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        ),
    )
    assert res.action is DecisionAction.REJECT
    assert res.reason_code == "cross_user_blocked"
    assert res.winner_id is None


# ── 类型准入：fail-closed ──


def test_invalid_input_rejected():
    """None / dict / 非 ConflictSide → REJECT(invalid_input)。"""
    side = make_side()
    for bad in (
        None,
        {},
        {"knowledge_id": "kn_d8e_fake", "user_id": USER},
        "not-a-conflict-side",
    ):
        for left, right in ((bad, side), (side, bad), (bad, bad)):
            res = POLICY.resolve(left, right)
            assert res.action is DecisionAction.REJECT
            assert res.reason_code == "invalid_input"
            assert res.winner_id is None


# ── 确定性 ──


def test_decision_deterministic():
    """同输入两次 resolve → model_dump() 完全相等（无状态、纯函数式）。"""
    a = make_side(
        knowledge_id="kn_d8e_det_a",
        evidence_tier=EvidenceTier.TOOL_EXECUTION_RESULT,
    )
    b = make_side(
        knowledge_id="kn_d8e_det_b",
        evidence_tier=EvidenceTier.MODEL_INFERENCE,
    )
    # KEEP_*
    assert POLICY.resolve(a, b).model_dump() == POLICY.resolve(a, b).model_dump()
    # REJECT（跨用户）
    c = make_side(
        knowledge_id="kn_d8e_det_c",
        user_id="user_demo_other",
        evidence_tier=EvidenceTier.MODEL_INFERENCE,
    )
    assert POLICY.resolve(a, c).model_dump() == POLICY.resolve(a, c).model_dump()
    # COEXIST（不同 scope）
    s1 = make_side(
        knowledge_id="kn_d8e_det_s1",
        evidence_tier=EvidenceTier.MODEL_INFERENCE,
        scope="topic:demo_det1",
    )
    s2 = make_side(
        knowledge_id="kn_d8e_det_s2",
        evidence_tier=EvidenceTier.MODEL_INFERENCE,
        scope="topic:demo_det2",
    )
    assert POLICY.resolve(s1, s2).model_dump() == POLICY.resolve(s1, s2).model_dump()
    # DEFER（Tier 1 时间相同）
    e1 = make_side(
        knowledge_id="kn_d8e_det_e1",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        recorded_at=T1,
    )
    e2 = make_side(
        knowledge_id="kn_d8e_det_e2",
        evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
        recorded_at=T1,
    )
    assert POLICY.resolve(e1, e2).model_dump() == POLICY.resolve(e1, e2).model_dump()


# ── reason_code 纪律：固定集合、不含用户正文/密钥/Token ──


def test_reason_code_fixed_set_no_user_content():
    """reason_code 全部属于固定集合；注入内容不出现在任何结果字段。

    密钥/正文类内容只能通过输入字段注入（此处注入两侧 scope 与落败侧
    knowledge_id），策略输出不得携带任何注入内容到结果字段
    （winner_id 仅回显获胜侧结构化 knowledge_id 审计引用，非用户正文拼接）。
    """
    secret_like = "sk-demo-abcdefghijklmnopqrstuvwxyz123456"
    a = make_side(
        knowledge_id=f"kn_d8e_secret_loser_{secret_like}",
        evidence_tier=EvidenceTier.MODEL_INFERENCE,
        scope=f"topic:{secret_like}",
    )
    b = make_side(
        knowledge_id="kn_d8e_clean_b",
        evidence_tier=EvidenceTier.USER_CONFIRMED,
        scope=f"topic:{secret_like}",
    )
    res = POLICY.resolve(a, b)
    assert res.action is DecisionAction.KEEP_RIGHT
    assert res.reason_code in EXPECTED_REASON_CODES
    assert res.reason_code == "evidence_tier_priority"
    # 注入内容不得出现在 reason_code / action，也不得因拼接正文进入任何结果字段
    assert secret_like not in res.reason_code
    for value in res.model_dump().values():
        if isinstance(value, str):
            assert secret_like not in value


# ── reason_code 全部可达 ──


def test_all_reason_codes_reachable():
    """全部 6 个固定 reason_code 均可达（与权威集合完全一致、稳定可测）。"""
    seen = set()

    def run(left, right):
        seen.add(POLICY.resolve(left, right).reason_code)

    # invalid_input
    run(None, make_side())
    # cross_user_blocked
    run(
        make_side(),
        make_side(knowledge_id="kn_d8e_other_user", user_id="user_demo_other"),
    )
    # scope_distinguishable
    run(
        make_side(knowledge_id="kn_d8e_rc_a", scope="topic:demo_a"),
        make_side(knowledge_id="kn_d8e_rc_b", scope="topic:demo_b"),
    )
    # evidence_tier_priority
    run(
        make_side(
            knowledge_id="kn_d8e_rc_tool",
            evidence_tier=EvidenceTier.TOOL_EXECUTION_RESULT,
        ),
        make_side(
            knowledge_id="kn_d8e_rc_model",
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
        ),
    )
    # latest_explicit_config_wins
    run(
        make_side(
            knowledge_id="kn_d8e_rc_new",
            evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
            recorded_at=T1,
        ),
        make_side(
            knowledge_id="kn_d8e_rc_old",
            evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
            recorded_at=T0,
        ),
    )
    # same_tier_undecidable
    run(
        make_side(
            knowledge_id="kn_d8e_rc_st_a",
            evidence_tier=EvidenceTier.USER_CONFIRMED,
        ),
        make_side(
            knowledge_id="kn_d8e_rc_st_b",
            evidence_tier=EvidenceTier.USER_CONFIRMED,
        ),
    )

    assert seen == EXPECTED_REASON_CODES
