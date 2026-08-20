"""
test_business_boundaries_d4e.py — Day4 E 轨 Service/Security 边界骨架单元测试

覆盖范围（对齐任务 day4-e-02-service-security-boundaries-v1）：
- A. service / security 包可导入，且 contracts 模块带骨架标记
     （D4_SKELETON / NOT_IPC_CONTRACT / NOT_PERSISTENCE_CONTRACT）。
- B. 只暴露骨架类型（__all__ 精确匹配，无额外公开可调用业务函数）。
- C. Service 引用 Task1 Domain 对象（DomainEntity 引用四类）但**不复导出**。
- D. 依赖边界：service / security 不直接依赖 sqlite3 / embedding / providers /
     faiss / chromadb（security 还不得直接依赖 pipeline）。
- E. ServiceOperation / SecurityPolicy 仅为协议签名骨架（签名 + 类型提示，
     不依赖源码文本判断）。
- F. 最小构造无副作用：骨架类型可构造；空 user_id / extra 字段被拒绝；
     新枚举值集与既有业务枚举值集无交集（语义正交）。
- G. 仓库唯一正式 Evaluation 位置为根目录 evaluation/，
     memory-service/evaluation/ 不存在。

测试纪律：
- 不使用 Mock、skip、xfail 或固定 PASS 结果。
- 测试数据仅使用合成用户 ID（user_demo_*）、占位规则 ID（SEC-UI-01）与脱敏内容。
"""

import inspect
import sys
import types
import typing
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import security  # noqa: E402
import service  # noqa: E402
from domain import Conflict, ForgetPlan, Knowledge, Preference  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

SERVICE_ALL = {
    "ServiceRequestContext",
    "OperationOutcomeStatus",
    "OperationOutcome",
    "DomainEntity",
    "ServiceOperation",
}
SECURITY_ALL = {"SecurityDecisionType", "SecurityDecision", "SecurityPolicy"}


# ── A. 包可导入与骨架标记 ──


def test_service_package_importable():
    assert service is not None
    assert isinstance(service.__all__, list)


def test_security_package_importable():
    assert security is not None
    assert isinstance(security.__all__, list)


def test_service_contracts_marked_skeleton():
    doc = service.contracts.__doc__ or ""
    for marker in ("D4_SKELETON", "NOT_IPC_CONTRACT", "NOT_PERSISTENCE_CONTRACT"):
        assert marker in doc


def test_security_contracts_marked_skeleton():
    doc = security.contracts.__doc__ or ""
    for marker in ("D4_SKELETON", "NOT_IPC_CONTRACT", "NOT_PERSISTENCE_CONTRACT"):
        assert marker in doc


# ── B. 只暴露骨架类型 ──


def test_service_all_only_skeleton_types():
    assert set(service.__all__) == SERVICE_ALL


def test_security_all_only_skeleton_types():
    assert set(security.__all__) == SECURITY_ALL


def test_service_no_extra_public_callables():
    extra = [n for n in dir(service) if not n.startswith("_") and n not in SERVICE_ALL]
    # 允许 module（如子模块 contracts），但不允许任何未声明公开业务函数
    assert not [n for n in extra if callable(getattr(service, n))], extra


def test_security_no_extra_public_callables():
    extra = [n for n in dir(security) if not n.startswith("_") and n not in SECURITY_ALL]
    assert not [n for n in extra if callable(getattr(security, n))], extra


# ── C. Service 引用 Domain 但不复导出 ──


def test_service_contracts_references_domain_objects():
    for name in ("Preference", "Knowledge", "Conflict", "ForgetPlan"):
        assert hasattr(service.contracts, name), f"service.contracts 应可引用 {name}"


def test_service_does_not_re_export_domain():
    assert {"Preference", "Knowledge", "Conflict", "ForgetPlan"} & set(service.__all__) == set()


def test_domain_entity_alias_targets_domain_classes():
    args = typing.get_args(service.contracts.DomainEntity)
    assert set(args) == {Preference, Knowledge, Conflict, ForgetPlan}


# ── D. 依赖边界（不依赖 SQLite / Vector / IPC / Provider / 宿主 Runtime） ──


def test_service_no_direct_forbidden_dependency():
    forbidden = {"sqlite3", "embedding", "providers", "faiss", "chromadb"}
    direct_modules = {
        name
        for name, value in vars(service.contracts).items()
        if isinstance(value, types.ModuleType)
    }
    assert direct_modules & forbidden == set()


def test_security_no_direct_forbidden_dependency():
    forbidden = {"sqlite3", "embedding", "providers", "faiss", "chromadb", "pipeline"}
    direct_modules = {
        name
        for name, value in vars(security.contracts).items()
        if isinstance(value, types.ModuleType)
    }
    assert direct_modules & forbidden == set()


# ── E. Protocol 仅签名骨架 ──


def test_service_operation_is_protocol_skeleton():
    params = inspect.signature(service.ServiceOperation.execute).parameters
    assert "self" in params
    assert "ctx" in params
    hints = typing.get_type_hints(service.ServiceOperation.execute)
    assert hints["ctx"] is service.ServiceRequestContext
    assert hints["return"] is service.OperationOutcome


def test_security_policy_is_protocol_skeleton():
    params = inspect.signature(security.SecurityPolicy.evaluate).parameters
    assert "self" in params
    assert "user_id" in params
    assert "rule_id" in params
    hints = typing.get_type_hints(security.SecurityPolicy.evaluate)
    assert hints["return"] is security.SecurityDecision


# ── F. 最小构造无副作用 ──


def test_service_request_context_constructible():
    ctx = service.ServiceRequestContext(
        user_id="user_demo_01", actor_id="actor_demo_01"
    )
    assert ctx.user_id == "user_demo_01"
    assert ctx.actor_id == "actor_demo_01"


def test_service_request_context_optional_fields():
    ctx = service.ServiceRequestContext(
        user_id="user_demo_01", actor_id="actor_demo_01"
    )
    assert ctx.trace_id is None
    assert ctx.session_id is None


def test_service_request_context_empty_user_id_rejected():
    with pytest.raises(ValidationError):
        service.ServiceRequestContext(user_id="", actor_id="actor_demo_01")


def test_service_request_context_extra_field_rejected():
    with pytest.raises(ValidationError):
        service.ServiceRequestContext(
            user_id="user_demo_01", actor_id="actor_demo_01", unexpected="x"
        )


def test_operation_outcome_constructible():
    outcome = service.OperationOutcome(status=service.OperationOutcomeStatus.OK)
    assert outcome.status is service.OperationOutcomeStatus.OK


def test_operation_outcome_status_values():
    actual = {m.value for m in service.OperationOutcomeStatus}
    assert actual == {"ok", "degraded", "blocked", "rejected"}
    # 语义正交：不得与既有业务生命周期/消解/遗忘状态枚举值集交叉
    from domain import (
        ForgetPlanStatus,
        MemoryStatus,
        ResolutionStatus,
    )

    existing = {
        m.value
        for cls in (MemoryStatus, ForgetPlanStatus, ResolutionStatus)
        for m in cls
    }
    assert actual & existing == set()


def test_security_decision_constructible():
    decision = security.SecurityDecision(
        user_id="user_demo_01",
        rule_id="SEC-UI-01",
        decision=security.SecurityDecisionType.DENY,
        reason="cross-user",
    )
    assert decision.user_id == "user_demo_01"
    assert decision.rule_id == "SEC-UI-01"
    assert decision.decision is security.SecurityDecisionType.DENY
    assert decision.reason == "cross-user"


def test_security_decision_isolation_violation_default_false():
    decision = security.SecurityDecision(
        user_id="user_demo_01",
        rule_id="SEC-UI-01",
        decision=security.SecurityDecisionType.ALLOW,
    )
    assert decision.isolation_violation is False


def test_security_decision_type_values():
    actual = {m.value for m in security.SecurityDecisionType}
    assert actual == {"allow", "deny", "redact", "escalate"}


def test_security_decision_extra_field_rejected():
    with pytest.raises(ValidationError):
        security.SecurityDecision(
            user_id="user_demo_01",
            rule_id="SEC-UI-01",
            decision=security.SecurityDecisionType.ALLOW,
            unexpected="x",
        )


# ── G. Evaluation 唯一位置 ──


def test_root_evaluation_dir_exists():
    assert (REPO_ROOT / "evaluation").is_dir()


def test_no_memory_service_evaluation_dir():
    assert not (REPO_ROOT / "memory-service" / "evaluation").exists()