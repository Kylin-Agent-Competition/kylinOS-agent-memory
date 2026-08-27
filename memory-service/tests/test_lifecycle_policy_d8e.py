"""
test_lifecycle_policy_d8e.py — Day8 E 轨知识短中长期生命周期业务决策策略单元测试

对齐任务卡：day8-e-03-lifecycle-policy-v1
（新增纯业务生命周期策略，在 memory_status 作为唯一优先生命周期真源的
 前提下，输出 short/medium/long 提升、降级、过期与归档请求的可解释决策，
 并将所有次数和时间阈值配置化而非写死）。

覆盖范围（对齐已批准方案）：
- 模块可导入；5 个公开类型可引用；__all__ 集合精确匹配。
- LifecycleAction 六值完整；PolicyConfig 全部必填无默认值；
  模型单独推测不得作为提升要求档；负时长 / 未知字段拒绝。
- LifecycleSnapshot 不含 is_active / is_outdated / should_decay 过渡字段
  （extra="forbid" 拒绝传入），memory_status 为唯一优先真源。
- 提升：SHORT_TERM→MEDIUM_TERM、MEDIUM_TERM→LONG_TERM 由配置化可信证据
  阈值触发；模型单独推测、LONG_TERM/EPHEMERAL 无路径、CANDIDATE、
  access_count=None 均不自动提升。
- 降级：LONG_TERM→MEDIUM_TERM、MEDIUM_TERM→SHORT_TERM 由不活跃/低使用/
  置信度衰减触发；SHORT_TERM 无降级路径；last_accessed_at=None 以
  created_at 为最后活动。
- 过期：ACTIVE 且 age >= expire_after_age → EXPIRE（target_memory_status=
  EXPIRED），含边界（== / 低于）。
- 归档：REMOVED / EXPIRED 冷期 → ARCHIVE_REQUEST；EXPIRED 未冷 → HOLD；
  MemoryStatus 枚举不含 ARCHIVED。
- 非 ACTIVE fail-closed：CANDIDATE/SUPERSEDED/DEPRECATED 不因高 confidence
  自动恢复 ACTIVE。
- 阈值边界（at / just-below）全覆盖；优先级（PROMOTE 先于 EXPIRE 先于
  DEMOTE）验证。
- 无效输入：snapshot/now 类型非法 → REJECT(invalid_input)。
- 确定性：同输入两次 decide 的 model_dump() 完全相等。
- reason_code 纪律：13 值权威集合全部可达、不含注入内容。
- 策略不读取过渡字段做最终决策。

明确不在本测试范围内：
- 不测试 SQLite 持久化、迁移、删除、归档执行或 Vector 重建。
- 不测试 Repository / TTL Worker / 事务 / Outbox / 后台线程。
- 不修改 domain/enums.py、pipeline/schemas.py 或任何共享枚举。
- 不新增 MemoryStatus.ARCHIVED 或其他共享生命周期枚举值。

测试纪律：
- 不使用 Mock、skip、xfail 或弱化断言。
- 测试数据仅使用合成用户 ID（user_demo_d8e_03）、合成知识 ID（kn_d8e_03_*）
  与脱敏/虚构内容，不写入任何真实凭据。
- 本文件内所有阈值均为合成验证值，非正式业务冻结值（正式值由部署配置注入）。
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.enums import MemoryStatus  # noqa: E402
from pipeline.schemas import MemoryType  # noqa: E402
from service.conflict_resolution_policy import EvidenceTier  # noqa: E402
import service.lifecycle_policy as lcp  # noqa: E402
from service.lifecycle_policy import (  # noqa: E402
    LifecycleAction,
    LifecycleDecision,
    LifecyclePolicy,
    LifecycleSnapshot,
    PolicyConfig,
)

# ── 合成数据基座（不含任何真实用户数据/密钥；阈值为合成验证值） ──

USER = "user_demo_d8e_03"
# T0 创建（距 NOW 26 天 12 小时）；T_LAST 最后访问（距 NOW 7 天 12 小时）
T0 = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
T_LAST = datetime(2026, 8, 20, 0, 0, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)

# 固定 reason_code 权威集合（13 值，策略层所有可达判定码）
EXPECTED_REASON_CODES = {
    "invalid_input",
    "candidate_requires_confirmation",
    "superseded_no_auto_recovery",
    "deprecated_no_auto_recovery",
    "expired_pending_archive",
    "removed_cold_data",
    "expired_cold_data",
    "age_threshold_reached",
    "inactivity_threshold",
    "low_usage_threshold",
    "confidence_decay_threshold",
    "credible_evidence_threshold",
    "no_threshold_met",
}


def make_config():
    """构造合成测试阈值（非冻结业务值；正式冻结值由部署配置注入）。"""
    return PolicyConfig(
        promote_min_confidence=0.8,
        promote_min_access_count=5,
        promote_min_age=timedelta(days=7),
        promote_required_evidence_tier=EvidenceTier.CONSISTENT_BEHAVIOR_MULTIPLE,
        demote_inactivity_period=timedelta(days=30),
        demote_max_access_count=2,
        demote_max_confidence=0.3,
        expire_after_age=timedelta(days=90),
        archive_after_expired=timedelta(days=30),
    )


def make_snapshot(**overrides):
    """构造合成 LifecycleSnapshot（真实 Pydantic 模型，合成/脱敏数据）。"""
    data = {
        "knowledge_id": "kn_d8e_03_01",
        "user_id": USER,
        "memory_type": MemoryType.SHORT_TERM,
        "memory_status": MemoryStatus.ACTIVE,
        "evidence_tier": EvidenceTier.TOOL_EXECUTION_RESULT,
        "confidence_score": 0.9,
        "access_count": 10,
        "last_accessed_at": T_LAST,
        "created_at": T0,
        "updated_at": T0,
    }
    data.update(overrides)
    return LifecycleSnapshot(**data)


POLICY = LifecyclePolicy(make_config())


# ── 模块与类型结构 ──


def test_module_importable_and_types_exposed():
    """模块可导入；5 个公开类型可引用；__all__ 集合精确匹配。"""
    assert isinstance(POLICY, LifecyclePolicy)
    for name in (
        "LifecycleAction",
        "LifecycleSnapshot",
        "PolicyConfig",
        "LifecycleDecision",
        "LifecyclePolicy",
    ):
        assert hasattr(lcp, name)
    assert set(lcp.__all__) == {
        "LifecycleAction",
        "LifecycleSnapshot",
        "PolicyConfig",
        "LifecycleDecision",
        "LifecyclePolicy",
    }


def test_lifecycle_action_six_values():
    """action 为固定六值枚举，不依赖自然语言随机生成。"""
    assert {m.value for m in LifecycleAction} == {
        "promote",
        "demote",
        "expire",
        "archive_request",
        "hold",
        "reject",
    }


def test_policy_config_no_defaults():
    """PolicyConfig 全部字段必填、无默认值（阈值必须显式注入）。"""
    for name, field in PolicyConfig.model_fields.items():
        assert field.is_required(), name


def test_policy_config_model_inference_rejected_for_promotion():
    """模型单独推测不得作为自动提升的可信证据要求档。"""
    cfg = make_config().model_dump()
    cfg["promote_required_evidence_tier"] = EvidenceTier.MODEL_INFERENCE
    with pytest.raises(ValidationError):
        PolicyConfig(**cfg)


def test_policy_config_negative_timedelta_rejected():
    """负时长阈值拒绝（NonNegTimedelta >= 0）。"""
    cfg = make_config().model_dump()
    cfg["demote_inactivity_period"] = timedelta(days=-1)
    with pytest.raises(ValidationError):
        PolicyConfig(**cfg)


def test_policy_config_extra_field_rejected():
    """未知配置字段 → ValidationError（extra="forbid"）。"""
    cfg = make_config().model_dump()
    cfg["unexpected_field"] = 1
    with pytest.raises(ValidationError):
        PolicyConfig(**cfg)


# ── 快照不含过渡字段 ──


def test_snapshot_no_transitional_fields():
    """is_active / is_outdated / should_decay 传入快照 → ValidationError。"""
    for field in ("is_active", "is_outdated", "should_decay"):
        with pytest.raises(ValidationError):
            make_snapshot(**{field: True})


def test_snapshot_extra_field_rejected():
    """未知快照字段 → ValidationError（extra="forbid"）。"""
    with pytest.raises(ValidationError):
        make_snapshot(unexpected_field="x")


# ── 提升（PROMOTE） ──


def test_promote_short_to_medium_credible_evidence():
    """SHORT_TERM + 全部可信证据条件满足 → PROMOTE(credible_evidence_threshold)。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            knowledge_id="kn_d8e_03_p_s2m",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.PROMOTE
    assert res.reason_code == "credible_evidence_threshold"
    assert res.target_memory_type is MemoryType.MEDIUM_TERM
    assert res.target_memory_status is None


def test_promote_medium_to_long_credible_evidence():
    """MEDIUM_TERM + 全部可信证据条件满足 → PROMOTE，target=LONG_TERM。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.MEDIUM_TERM,
            knowledge_id="kn_d8e_03_p_m2l",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.PROMOTE
    assert res.reason_code == "credible_evidence_threshold"
    assert res.target_memory_type is MemoryType.LONG_TERM


def test_promote_model_only_inference_blocked():
    """模型单独推测 + 高 confidence 不触发自动提升（fail-closed）。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
            confidence_score=0.99,
            access_count=100,
            knowledge_id="kn_d8e_03_p_model",
        ),
        now=NOW,
    )
    assert res.action is not LifecycleAction.PROMOTE
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "no_threshold_met"


def test_promote_long_term_no_path():
    """LONG_TERM 无提升路径：即使全部证据条件满足也不 PROMOTE。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.LONG_TERM,
            evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
            confidence_score=0.99,
            access_count=100,
            knowledge_id="kn_d8e_03_p_lt",
        ),
        now=NOW,
    )
    assert res.action is not LifecycleAction.PROMOTE
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "no_threshold_met"


def test_promote_ephemeral_no_path():
    """EPHEMERAL 无提升路径：即使全部证据条件满足也不 PROMOTE。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.EPHEMERAL,
            evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
            confidence_score=0.99,
            access_count=100,
            knowledge_id="kn_d8e_03_p_ep",
        ),
        now=NOW,
    )
    assert res.action is not LifecycleAction.PROMOTE
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "no_threshold_met"


def test_promote_candidate_blocked():
    """memory_status=CANDIDATE + 高 confidence/高 usage → 不提升。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            memory_status=MemoryStatus.CANDIDATE,
            confidence_score=0.99,
            access_count=100,
            evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
            knowledge_id="kn_d8e_03_p_cand",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "candidate_requires_confirmation"
    assert res.target_memory_type is None
    assert res.target_memory_status is None


def test_promote_access_count_none_blocked():
    """access_count=None（无使用证据）→ 不自动提升（fail-closed）。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            access_count=None,
            confidence_score=0.99,
            evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
            knowledge_id="kn_d8e_03_p_none_acc",
        ),
        now=NOW,
    )
    assert res.action is not LifecycleAction.PROMOTE
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "no_threshold_met"


# ── 降级（DEMOTE） ──


def test_demote_long_to_medium_inactivity():
    """LONG_TERM + inactivity >= 阈值 → DEMOTE(inactivity_threshold)。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.LONG_TERM,
            last_accessed_at=NOW - timedelta(days=40),
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
            knowledge_id="kn_d8e_03_d_l2m",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.DEMOTE
    assert res.reason_code == "inactivity_threshold"
    assert res.target_memory_type is MemoryType.MEDIUM_TERM
    assert res.target_memory_status is None


def test_demote_medium_to_short_low_usage():
    """MEDIUM_TERM + access_count <= 阈值 → DEMOTE(low_usage_threshold)。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.MEDIUM_TERM,
            access_count=1,
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
            confidence_score=0.9,
            last_accessed_at=T_LAST,
            knowledge_id="kn_d8e_03_d_m2s",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.DEMOTE
    assert res.reason_code == "low_usage_threshold"
    assert res.target_memory_type is MemoryType.SHORT_TERM


def test_demote_confidence_decay():
    """confidence <= 阈值 → DEMOTE(confidence_decay_threshold)。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.MEDIUM_TERM,
            confidence_score=0.2,
            access_count=10,
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
            knowledge_id="kn_d8e_03_d_conf",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.DEMOTE
    assert res.reason_code == "confidence_decay_threshold"
    assert res.target_memory_type is MemoryType.SHORT_TERM


def test_demote_short_term_no_path():
    """SHORT_TERM 无降级路径：即使不活跃/低使用/低置信也不 DEMOTE。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            confidence_score=0.2,
            access_count=1,
            last_accessed_at=NOW - timedelta(days=40),
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
            knowledge_id="kn_d8e_03_d_st",
        ),
        now=NOW,
    )
    assert res.action is not LifecycleAction.DEMOTE
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "no_threshold_met"


def test_demote_last_accessed_none_uses_created_at():
    """last_accessed_at=None → 以 created_at 为最后活动计算 inactivity。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.MEDIUM_TERM,
            last_accessed_at=None,
            created_at=NOW - timedelta(days=40),
            updated_at=NOW - timedelta(days=40),
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
            access_count=10,
            confidence_score=0.9,
            knowledge_id="kn_d8e_03_d_no_last",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.DEMOTE
    assert res.reason_code == "inactivity_threshold"
    assert res.target_memory_type is MemoryType.SHORT_TERM


# ── 过期（EXPIRE） ──


def test_expire_age_threshold():
    """ACTIVE + age >= expire_after_age → EXPIRE(age_threshold_reached)。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            created_at=NOW - timedelta(days=100),
            updated_at=NOW - timedelta(days=100),
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
            knowledge_id="kn_d8e_03_x_age",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.EXPIRE
    assert res.reason_code == "age_threshold_reached"
    assert res.target_memory_status is MemoryStatus.EXPIRED
    assert res.target_memory_type is None


def test_expire_boundary_exactly_at_threshold():
    """age == expire_after_age → EXPIRE（inclusive 边界）。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            created_at=NOW - timedelta(days=90),
            updated_at=NOW - timedelta(days=90),
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
            knowledge_id="kn_d8e_03_x_bound",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.EXPIRE
    assert res.reason_code == "age_threshold_reached"
    assert res.target_memory_status is MemoryStatus.EXPIRED


def test_expire_below_threshold_no_expire():
    """age < expire_after_age → 不 EXPIRE。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            created_at=NOW - timedelta(days=89),
            updated_at=NOW - timedelta(days=89),
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
            knowledge_id="kn_d8e_03_x_below",
        ),
        now=NOW,
    )
    assert res.action is not LifecycleAction.EXPIRE
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "no_threshold_met"


# ── 归档（ARCHIVE_REQUEST） ──


def test_archive_removed():
    """memory_status=REMOVED → ARCHIVE_REQUEST(removed_cold_data)。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.LONG_TERM,
            memory_status=MemoryStatus.REMOVED,
            knowledge_id="kn_d8e_03_a_rm",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.ARCHIVE_REQUEST
    assert res.reason_code == "removed_cold_data"
    assert res.target_memory_type is None
    assert res.target_memory_status is None


def test_archive_expired_cold():
    """EXPIRED + (now-updated_at) >= 归档冷期 → ARCHIVE_REQUEST(expired_cold_data)。"""
    res = POLICY.decide(
        make_snapshot(
            memory_status=MemoryStatus.EXPIRED,
            updated_at=NOW - timedelta(days=40),
            knowledge_id="kn_d8e_03_a_cold",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.ARCHIVE_REQUEST
    assert res.reason_code == "expired_cold_data"


def test_expired_not_cold_hold():
    """EXPIRED + 未达归档冷期 → HOLD(expired_pending_archive)。"""
    res = POLICY.decide(
        make_snapshot(
            memory_status=MemoryStatus.EXPIRED,
            updated_at=NOW - timedelta(days=10),
            knowledge_id="kn_d8e_03_a_warm",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "expired_pending_archive"
    assert res.target_memory_type is None
    assert res.target_memory_status is None


def test_archive_no_new_archived_status():
    """MemoryStatus 枚举不含 ARCHIVED（domain/enums.py 六值冻结回归）。"""
    assert "archived" not in {m.value for m in MemoryStatus}


# ── 非 ACTIVE fail-closed ──


def test_candidate_no_auto_recovery_high_confidence():
    """CANDIDATE + 极高 confidence/最高证据档 → 不自动恢复 ACTIVE。"""
    res = POLICY.decide(
        make_snapshot(
            memory_status=MemoryStatus.CANDIDATE,
            confidence_score=0.99,
            evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
            access_count=100,
            knowledge_id="kn_d8e_03_nr_cand",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "candidate_requires_confirmation"
    assert res.target_memory_type is None
    assert res.target_memory_status is None


def test_superseded_no_auto_recovery():
    """SUPERSEDED → HOLD(superseded_no_auto_recovery)。"""
    res = POLICY.decide(
        make_snapshot(
            memory_status=MemoryStatus.SUPERSEDED,
            confidence_score=0.99,
            knowledge_id="kn_d8e_03_nr_sup",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "superseded_no_auto_recovery"
    assert res.target_memory_type is None
    assert res.target_memory_status is None


def test_deprecated_no_auto_recovery():
    """DEPRECATED → HOLD(deprecated_no_auto_recovery)。"""
    res = POLICY.decide(
        make_snapshot(
            memory_status=MemoryStatus.DEPRECATED,
            confidence_score=0.99,
            knowledge_id="kn_d8e_03_nr_dep",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "deprecated_no_auto_recovery"
    assert res.target_memory_type is None
    assert res.target_memory_status is None


# ── 阈值边界（at / just-below / above） ──


def test_promote_access_count_boundary():
    """access_count == promote_min_access_count → PROMOTE；== min-1 → 不。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            access_count=5,
            knowledge_id="kn_d8e_03_b_ac_eq",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.PROMOTE
    assert res.reason_code == "credible_evidence_threshold"
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            access_count=4,
            knowledge_id="kn_d8e_03_b_ac_lt",
        ),
        now=NOW,
    )
    assert res.action is not LifecycleAction.PROMOTE
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "no_threshold_met"


def test_promote_confidence_boundary():
    """confidence == promote_min_confidence → PROMOTE；< min → 不。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            confidence_score=0.8,
            knowledge_id="kn_d8e_03_b_cf_eq",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.PROMOTE
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            confidence_score=0.79,
            knowledge_id="kn_d8e_03_b_cf_lt",
        ),
        now=NOW,
    )
    assert res.action is not LifecycleAction.PROMOTE
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "no_threshold_met"


def test_promote_age_boundary():
    """age == promote_min_age → PROMOTE；< min → 不。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            created_at=NOW - timedelta(days=7),
            updated_at=NOW - timedelta(days=7),
            knowledge_id="kn_d8e_03_b_age_eq",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.PROMOTE
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            created_at=NOW - timedelta(days=7) + timedelta(seconds=1),
            updated_at=NOW - timedelta(days=7) + timedelta(seconds=1),
            knowledge_id="kn_d8e_03_b_age_lt",
        ),
        now=NOW,
    )
    assert res.action is not LifecycleAction.PROMOTE
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "no_threshold_met"


def test_demote_inactivity_boundary():
    """inactivity == demote_inactivity_period → DEMOTE；< period → 不。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.LONG_TERM,
            last_accessed_at=NOW - timedelta(days=30),
            knowledge_id="kn_d8e_03_b_inact_eq",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.DEMOTE
    assert res.reason_code == "inactivity_threshold"
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.LONG_TERM,
            last_accessed_at=NOW - timedelta(days=30) + timedelta(seconds=1),
            knowledge_id="kn_d8e_03_b_inact_lt",
        ),
        now=NOW,
    )
    assert res.action is not LifecycleAction.DEMOTE
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "no_threshold_met"


def test_demote_low_usage_boundary():
    """access_count == demote_max_access_count → DEMOTE；> max → 不。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.MEDIUM_TERM,
            access_count=2,
            knowledge_id="kn_d8e_03_b_lu_eq",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.DEMOTE
    assert res.reason_code == "low_usage_threshold"
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.MEDIUM_TERM,
            access_count=3,
            knowledge_id="kn_d8e_03_b_lu_gt",
        ),
        now=NOW,
    )
    assert res.action is not LifecycleAction.DEMOTE
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "no_threshold_met"


def test_demote_confidence_boundary():
    """confidence == demote_max_confidence → DEMOTE；> max → 不。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.MEDIUM_TERM,
            confidence_score=0.3,
            knowledge_id="kn_d8e_03_b_cd_eq",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.DEMOTE
    assert res.reason_code == "confidence_decay_threshold"
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.MEDIUM_TERM,
            confidence_score=0.31,
            knowledge_id="kn_d8e_03_b_cd_gt",
        ),
        now=NOW,
    )
    assert res.action is not LifecycleAction.DEMOTE
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "no_threshold_met"


def test_archive_cold_boundary():
    """归档冷期 == archive_after_expired → ARCHIVE；< → HOLD。"""
    res = POLICY.decide(
        make_snapshot(
            memory_status=MemoryStatus.EXPIRED,
            updated_at=NOW - timedelta(days=30),
            knowledge_id="kn_d8e_03_a_bound_eq",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.ARCHIVE_REQUEST
    assert res.reason_code == "expired_cold_data"
    res = POLICY.decide(
        make_snapshot(
            memory_status=MemoryStatus.EXPIRED,
            updated_at=NOW - timedelta(days=30) + timedelta(seconds=1),
            knowledge_id="kn_d8e_03_a_bound_lt",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.HOLD
    assert res.reason_code == "expired_pending_archive"


# ── 优先级 ──


def test_promote_preempts_expire():
    """全提升条件满足 + age >= expire_after_age → PROMOTE（不 EXPIRE）。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.SHORT_TERM,
            created_at=NOW - timedelta(days=100),
            updated_at=NOW - timedelta(days=100),
            evidence_tier=EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
            confidence_score=0.99,
            access_count=100,
            knowledge_id="kn_d8e_03_pr_pe",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.PROMOTE
    assert res.reason_code == "credible_evidence_threshold"
    assert res.target_memory_type is MemoryType.MEDIUM_TERM


def test_expire_preempts_demote():
    """age >= expire + inactivity >= period + 不满足提升 → EXPIRE（不 DEMOTE）。"""
    res = POLICY.decide(
        make_snapshot(
            memory_type=MemoryType.MEDIUM_TERM,
            created_at=NOW - timedelta(days=100),
            updated_at=NOW - timedelta(days=100),
            last_accessed_at=NOW - timedelta(days=40),
            evidence_tier=EvidenceTier.MODEL_INFERENCE,
            confidence_score=0.9,
            access_count=10,
            knowledge_id="kn_d8e_03_pr_ed",
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.EXPIRE
    assert res.reason_code == "age_threshold_reached"
    assert res.target_memory_status is MemoryStatus.EXPIRED
    assert res.target_memory_type is None


# ── 无效输入 ──


def test_invalid_snapshot_rejected():
    """None / dict / 非 LifecycleSnapshot → REJECT(invalid_input)。"""
    for bad in (
        None,
        {},
        {"knowledge_id": "kn_d8e_03_fake", "user_id": USER},
        "not-a-snapshot",
    ):
        res = POLICY.decide(bad, now=NOW)
        assert res.action is LifecycleAction.REJECT
        assert res.reason_code == "invalid_input"
        assert res.target_memory_type is None
        assert res.target_memory_status is None


def test_invalid_now_rejected():
    """now=None / str → REJECT(invalid_input)。"""
    snap = make_snapshot()
    for bad_now in (None, "2026-08-27T12:00:00Z"):
        res = POLICY.decide(snap, now=bad_now)
        assert res.action is LifecycleAction.REJECT
        assert res.reason_code == "invalid_input"
        assert res.target_memory_type is None
        assert res.target_memory_status is None


def test_now_naive_datetime_normalized_utc():
    """naive now 补 UTC 后与显式 UTC 决策一致（与 AwareDatetime 语义一致）。"""
    naive_now = datetime(2026, 8, 27, 12, 0, 0)
    snap = make_snapshot(
        memory_type=MemoryType.SHORT_TERM,
        knowledge_id="kn_d8e_03_naive",
    )
    assert POLICY.decide(snap, now=naive_now).model_dump() == POLICY.decide(
        snap, now=NOW
    ).model_dump()


# ── 确定性 ──


def test_decision_deterministic():
    """同 (snapshot, now, config) 两次 decide → model_dump() 完全相等。"""
    snap = make_snapshot(
        memory_type=MemoryType.MEDIUM_TERM,
        confidence_score=0.2,
        access_count=1,
        knowledge_id="kn_d8e_03_det",
    )
    assert POLICY.decide(snap, now=NOW).model_dump() == POLICY.decide(
        snap, now=NOW
    ).model_dump()
    snap2 = make_snapshot(
        memory_status=MemoryStatus.REMOVED,
        knowledge_id="kn_d8e_03_det2",
    )
    assert POLICY.decide(snap2, now=NOW).model_dump() == POLICY.decide(
        snap2, now=NOW
    ).model_dump()


# ── reason_code 纪律：固定集合、不含用户正文/密钥/Token ──


def test_reason_code_fixed_set_no_user_content():
    """reason_code 全部属于固定集合；注入内容不出现在任何结果字段。

    密钥/正文类内容只能通过输入字段注入（此处注入 knowledge_id），决策
    结果（action/reason_code/target_*）不得携带注入内容。
    """
    secret_like = "sk-demo-abcdefghijklmnopqrstuvwxyz123456"
    res = POLICY.decide(
        make_snapshot(
            knowledge_id=f"kn_d8e_03_{secret_like}",
            memory_type=MemoryType.SHORT_TERM,
        ),
        now=NOW,
    )
    assert res.action is LifecycleAction.PROMOTE
    assert res.reason_code in EXPECTED_REASON_CODES
    assert secret_like not in res.reason_code
    for value in res.model_dump().values():
        if isinstance(value, str):
            assert secret_like not in value
    # 非 ACTIVE fail-closed 分支同样不得泄漏注入内容
    res2 = POLICY.decide(
        make_snapshot(
            knowledge_id=f"kn_d8e_03_{secret_like}",
            memory_status=MemoryStatus.CANDIDATE,
        ),
        now=NOW,
    )
    assert res2.action is LifecycleAction.HOLD
    assert res2.reason_code in EXPECTED_REASON_CODES
    assert secret_like not in res2.reason_code
    for value in res2.model_dump().values():
        if isinstance(value, str):
            assert secret_like not in value


# ── reason_code 全部可达 ──


def test_all_reason_codes_reachable():
    """全部 13 个固定 reason_code 均可达（与权威集合完全一致、稳定可测）。"""
    seen = set()

    # invalid_input
    seen.add(POLICY.decide(None, now=NOW).reason_code)
    # candidate_requires_confirmation
    seen.add(
        POLICY.decide(
            make_snapshot(
                memory_status=MemoryStatus.CANDIDATE,
                knowledge_id="kn_d8e_03_rc_cand",
            ),
            now=NOW,
        ).reason_code
    )
    # superseded_no_auto_recovery
    seen.add(
        POLICY.decide(
            make_snapshot(
                memory_status=MemoryStatus.SUPERSEDED,
                knowledge_id="kn_d8e_03_rc_sup",
            ),
            now=NOW,
        ).reason_code
    )
    # deprecated_no_auto_recovery
    seen.add(
        POLICY.decide(
            make_snapshot(
                memory_status=MemoryStatus.DEPRECATED,
                knowledge_id="kn_d8e_03_rc_dep",
            ),
            now=NOW,
        ).reason_code
    )
    # expired_pending_archive
    seen.add(
        POLICY.decide(
            make_snapshot(
                memory_status=MemoryStatus.EXPIRED,
                updated_at=NOW - timedelta(days=10),
                knowledge_id="kn_d8e_03_rc_ep",
            ),
            now=NOW,
        ).reason_code
    )
    # removed_cold_data
    seen.add(
        POLICY.decide(
            make_snapshot(
                memory_status=MemoryStatus.REMOVED,
                knowledge_id="kn_d8e_03_rc_rm",
            ),
            now=NOW,
        ).reason_code
    )
    # expired_cold_data
    seen.add(
        POLICY.decide(
            make_snapshot(
                memory_status=MemoryStatus.EXPIRED,
                updated_at=NOW - timedelta(days=40),
                knowledge_id="kn_d8e_03_rc_ec",
            ),
            now=NOW,
        ).reason_code
    )
    # age_threshold_reached
    seen.add(
        POLICY.decide(
            make_snapshot(
                memory_type=MemoryType.SHORT_TERM,
                created_at=NOW - timedelta(days=100),
                updated_at=NOW - timedelta(days=100),
                evidence_tier=EvidenceTier.MODEL_INFERENCE,
                knowledge_id="kn_d8e_03_rc_age",
            ),
            now=NOW,
        ).reason_code
    )
    # inactivity_threshold
    seen.add(
        POLICY.decide(
            make_snapshot(
                memory_type=MemoryType.LONG_TERM,
                last_accessed_at=NOW - timedelta(days=40),
                evidence_tier=EvidenceTier.MODEL_INFERENCE,
                knowledge_id="kn_d8e_03_rc_inact",
            ),
            now=NOW,
        ).reason_code
    )
    # low_usage_threshold
    seen.add(
        POLICY.decide(
            make_snapshot(
                memory_type=MemoryType.MEDIUM_TERM,
                access_count=1,
                evidence_tier=EvidenceTier.MODEL_INFERENCE,
                knowledge_id="kn_d8e_03_rc_lu",
            ),
            now=NOW,
        ).reason_code
    )
    # confidence_decay_threshold
    seen.add(
        POLICY.decide(
            make_snapshot(
                memory_type=MemoryType.MEDIUM_TERM,
                confidence_score=0.2,
                evidence_tier=EvidenceTier.MODEL_INFERENCE,
                knowledge_id="kn_d8e_03_rc_cd",
            ),
            now=NOW,
        ).reason_code
    )
    # credible_evidence_threshold
    seen.add(
        POLICY.decide(
            make_snapshot(
                memory_type=MemoryType.SHORT_TERM,
                knowledge_id="kn_d8e_03_rc_prom",
            ),
            now=NOW,
        ).reason_code
    )
    # no_threshold_met
    seen.add(
        POLICY.decide(
            make_snapshot(
                memory_type=MemoryType.SHORT_TERM,
                evidence_tier=EvidenceTier.MODEL_INFERENCE,
                knowledge_id="kn_d8e_03_rc_hold",
            ),
            now=NOW,
        ).reason_code
    )

    assert seen == EXPECTED_REASON_CODES
    assert len(seen) == 13


# ── 不依赖过渡字段 ──


def test_policy_uses_memory_status_not_transitional():
    """策略以 memory_status 为真源：快照无过渡字段；仅 memory_status 差异
    决定 fail-closed 路径。"""
    # LifecycleSnapshot 字段中不得出现过渡字段
    assert not any(
        f in LifecycleSnapshot.model_fields
        for f in ("is_active", "is_outdated", "should_decay")
    )
    # 相同业务字段下仅 memory_status 不同 → 决策路径由 memory_status 决定
    common = {
        "memory_type": MemoryType.SHORT_TERM,
        "confidence_score": 0.99,
        "access_count": 100,
        "evidence_tier": EvidenceTier.USER_EXPLICIT_CONFIG_LATEST,
    }
    res_active = POLICY.decide(
        make_snapshot(memory_status=MemoryStatus.ACTIVE, **common, knowledge_id="kn_d8e_03_ns_a"),
        now=NOW,
    )
    res_candidate = POLICY.decide(
        make_snapshot(memory_status=MemoryStatus.CANDIDATE, **common, knowledge_id="kn_d8e_03_ns_c"),
        now=NOW,
    )
    assert res_active.action is LifecycleAction.PROMOTE
    assert res_candidate.action is LifecycleAction.HOLD
    assert res_candidate.reason_code == "candidate_requires_confirmation"
    assert isinstance(res_active, LifecycleDecision)
