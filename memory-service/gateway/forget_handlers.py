"""forget_handlers.py — D10D forget.preview / forget.execute IPC 写方法（ADR-019）

FRZ-IPC-007 扩展：新增两个写方法 `forget.preview` / `forget.execute`（preview/execute
分离是 [02 §10.1] 红线）。激活状态 `CANDIDATE / BLOCKED_BY_HOST_MAPPING`：
production 默认**不注册** → `UNSUPPORTED_METHOD`；仅 test/validation profile 显式注册
（对齐 ADR-010/014 activation 方案 A+B）。

固定编排顺序（ADR-019 §4.9，严禁重排）：
  - forget.preview：payload 结构预检（复用 ForgetPlan Domain 校验 forget_mode 互斥 +
    delete_mode 值域）→ trusted identity precheck（先于幂等查找，cache-bypass 防护）→
    UoW.preview_forget_plan 单事务（解析 → 落计划 → 凭据哈希 → 清 selector → 缓存响应）→
    响应回传凭据明文一次。
  - forget.execute：payload 结构预检 → trusted identity precheck → UoW.execute_forget_plan
    单事务（凭据校验/消费 → 软删 dispatcher → executed_count → 凭据置 NULL → 审计 → 终态）。

错误语义（契约 §八 / ADR-019 §4.10，复用冻结域不新增错误码）：所有 D 轨遗忘异常统一
转 RequestValidationError → INVALID_REQUEST（safe_message 固定英文，不回显正文/凭据/敏感）。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from db import repositories as repo
from db.uow import UnitOfWork
from domain import ForgetMode, ForgetPlan, ForgetPlanStatus, TargetType
from gateway.protocol import RequestValidationError
from gateway.registry import HandlerRegistry, RequestContext

logger = logging.getLogger(__name__)

_FORGET_MODES = {m.value for m in ForgetMode}
_TARGET_TYPES = {t.value for t in TargetType}
_DELETE_MODES = {repo.DELETE_MODE_SOFT, repo.DELETE_MODE_HARD}


def _preview_payload_to_plan(payload: Dict[str, Any]) -> Dict[str, Any]:
    """forget.preview payload → 校验后的结构化字段（复用 E 轨 ForgetPlan Domain）。

    校验失败抛 RequestValidationError（→ INVALID_REQUEST，safe）。delete_mode 非
    ForgetPlan 字段（extra=forbid），单独校验 soft/hard。
    """
    if not isinstance(payload, dict):
        raise RequestValidationError("payload must be object")
    required = ("forget_plan_id", "user_id", "forget_mode", "target_selector", "target_type")
    for f in required:
        if f not in payload or payload[f] is None:
            raise RequestValidationError(f"missing required field: {f}")
    for f in ("forget_plan_id", "user_id", "forget_mode", "target_selector", "target_type"):
        if not isinstance(payload[f], str) or not payload[f].strip():
            raise RequestValidationError(f"invalid_blank: {f}")

    forget_mode = payload["forget_mode"]
    if forget_mode not in _FORGET_MODES:
        raise RequestValidationError(f"invalid_value: forget_mode={forget_mode!r}")
    target_type = payload["target_type"]
    if target_type not in _TARGET_TYPES:
        raise RequestValidationError(f"invalid_value: target_type={target_type!r}")

    if "requires_confirmation" not in payload or not isinstance(payload["requires_confirmation"], bool):
        raise RequestValidationError("missing required field: requires_confirmation")

    is_cascade = payload.get("is_cascade", False)
    if is_cascade is not None and not isinstance(is_cascade, bool):
        raise RequestValidationError("invalid_type: is_cascade")
    is_cascade = bool(is_cascade)

    delete_mode = payload.get("delete_mode", repo.DELETE_MODE_SOFT)
    if delete_mode not in _DELETE_MODES:
        raise RequestValidationError(f"invalid_value: delete_mode={delete_mode!r}")

    # 复用 ForgetPlan Domain 校验 forget_mode 与 selector 互斥（SEC-FORGET-03）；
    # status=PENDING、resolved_target_ids=None（Preview 前）。
    conditional = {}
    for f in ("target_id", "target_session_id", "target_topic", "target_time_range"):
        if payload.get(f) is not None:
            if not isinstance(payload.get(f), str) or not payload.get(f).strip():
                raise RequestValidationError(f"invalid_blank: {f}")
            conditional[f] = payload[f]
    try:
        ForgetPlan(
            forget_plan_id=payload["forget_plan_id"],
            user_id=payload["user_id"],
            forget_mode=forget_mode,
            target_selector=payload["target_selector"],
            target_type=target_type,
            status=ForgetPlanStatus.PENDING,
            is_cascade=is_cascade,
            has_vector_cleanup=False,
            requires_confirmation=payload["requires_confirmation"],
            created_at=datetime.now(timezone.utc),
            **conditional,
        )
    except ValueError as exc:
        raise RequestValidationError("forget plan validation failed") from exc

    return {
        "forget_plan_id": payload["forget_plan_id"],
        "user_id": payload["user_id"],
        "forget_mode": forget_mode,
        "target_selector": payload["target_selector"],
        "target_type": target_type,
        "target_id": payload.get("target_id"),
        "target_session_id": payload.get("target_session_id"),
        "target_topic": payload.get("target_topic"),
        "target_time_range": payload.get("target_time_range"),
        "requires_confirmation": payload["requires_confirmation"],
        "is_cascade": is_cascade,
        "delete_mode": delete_mode,
    }


def _preview_request_fingerprint(fields: Dict[str, Any]) -> str:
    """forget.preview privacy-safe request_fingerprint（ADR-019 §4.8）。

    target_selector / target_topic 为自由文本（可能含敏感正文），一律取固定安全占位
    <SENSITIVE-OMITTED>，不由敏感正文派生确定性 SHA-256（防低熵离线枚举旁路）。
    进入指纹的结构字段：forget_plan_id/user_id/forget_mode/target_type/target_id/
    target_session_id/target_time_range/requires_confirmation/is_cascade/delete_mode。
    """
    fp_fields: Dict[str, Any] = {
        "forget_plan_id": fields["forget_plan_id"],
        "user_id": fields["user_id"],
        "forget_mode": fields["forget_mode"],
        "target_type": fields["target_type"],
        "target_selector": repo.SENSITIVE_OMITTED,
        "target_id": fields.get("target_id"),
        "target_session_id": fields.get("target_session_id"),
        "target_topic": repo.SENSITIVE_OMITTED,
        "target_time_range": fields.get("target_time_range"),
        "requires_confirmation": fields.get("requires_confirmation"),
        "is_cascade": fields.get("is_cascade"),
        "delete_mode": fields.get("delete_mode"),
    }
    canon = {k: (v if v is not None else "<absent>") for k, v in fp_fields.items()}
    canonical = json.dumps(canon, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"forget.preview\n{canonical}".encode("utf-8")).hexdigest()


def _execute_request_fingerprint(forget_plan_id: str, user_id: str) -> str:
    """forget.execute privacy-safe request_fingerprint（confirmation_token 不进入）。"""
    fields = {"forget_plan_id": forget_plan_id, "user_id": user_id}
    canonical = json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"forget.execute\n{canonical}".encode("utf-8")).hexdigest()


def _execute_payload_precheck(payload: Dict[str, Any]) -> Dict[str, str]:
    """forget.execute payload 结构预检（forget_plan_id/user_id/confirmation_token 必填）。"""
    if not isinstance(payload, dict):
        raise RequestValidationError("payload must be object")
    for f in ("forget_plan_id", "user_id", "confirmation_token"):
        if f not in payload or payload[f] is None:
            raise RequestValidationError(f"missing required field: {f}")
    for f in ("forget_plan_id", "user_id", "confirmation_token"):
        if not isinstance(payload[f], str) or not payload[f].strip():
            raise RequestValidationError(f"invalid_blank: {f}")
    return {
        "forget_plan_id": payload["forget_plan_id"],
        "user_id": payload["user_id"],
        "confirmation_token": payload["confirmation_token"],
    }


def register_forget_handlers(
    registry: HandlerRegistry,
    *,
    uow_factory: Callable[[], UnitOfWork],
    trusted_identity: Optional[Any] = None,
) -> None:
    """显式注册 forget.preview / forget.execute（ADR-019 activation 方案 A+B 测试态 seam）。

    production `register_default_handlers` 不含它们；test/validation profile 调用本函数。
    trusted_identity 为 None（仅声明内部自洽）；提供时在幂等缓存查找前 fail-close 比对
    （cache-bypass 防护，对齐 ADR-014 v5）。
    """

    def _identity_precheck(declared_user_id: Optional[str]) -> None:
        """trusted identity precheck（先于任何 user-scoped 幂等查找，HIGH-01）。"""
        if trusted_identity is None:
            return
        ti_user_id = (
            trusted_identity.user_id
            if hasattr(trusted_identity, "user_id")
            else trusted_identity()
        )
        if ti_user_id != declared_user_id:
            raise RequestValidationError("trusted identity mismatch")

    def preview_handler(payload: Dict[str, Any], ctx: RequestContext) -> Dict[str, Any]:
        fields = _preview_payload_to_plan(payload)
        # trace_id 一致性（payload 若带 trace_id 必须等于 envelope）
        if payload.get("trace_id") is not None and payload["trace_id"] != ctx.trace_id:
            raise RequestValidationError("inconsistent_value: trace_id")
        # 幂等键权威 = envelope 顶层 idempotency_key（唯一真源，payload 不携带第二真源）
        idem_key = ctx.idempotency_key
        if idem_key is None:
            raise RequestValidationError("missing idempotency_key")
        # trusted identity precheck（先于幂等缓存查找，cache-bypass 防护）
        _identity_precheck(fields["user_id"])

        fp = _preview_request_fingerprint(fields)
        user_id = fields["user_id"]
        try:
            with uow_factory() as uow:
                # preview 单事务（解析 + 落计划 + 凭据哈希 + 清 selector）；不支持作用域 fail-closed
                response, _from_cache = uow.preview_forget_plan(
                    user_id=user_id,
                    idempotency_key=idem_key,
                    request_fingerprint=fp,
                    forget_plan_id=fields["forget_plan_id"],
                    forget_mode=fields["forget_mode"],
                    target_selector=fields["target_selector"],
                    target_type=fields["target_type"],
                    target_id=fields["target_id"],
                    target_session_id=fields["target_session_id"],
                    target_topic=fields["target_topic"],
                    target_time_range=fields["target_time_range"],
                    requires_confirmation=fields["requires_confirmation"],
                    is_cascade=fields["is_cascade"],
                    delete_mode=fields["delete_mode"],
                )
        except repo.UnsupportedForgetScopeError as exc:
            raise RequestValidationError(str(exc.reason)) from exc
        except (repo.ForgetPlanNotFoundError, repo.ConfirmationCredentialError) as exc:
            raise RequestValidationError(str(exc)) from exc
        return response

    def execute_handler(payload: Dict[str, Any], ctx: RequestContext) -> Dict[str, Any]:
        fields = _execute_payload_precheck(payload)
        idem_key = ctx.idempotency_key
        if idem_key is None:
            raise RequestValidationError("missing idempotency_key")
        _identity_precheck(fields["user_id"])

        fp = _execute_request_fingerprint(fields["forget_plan_id"], fields["user_id"])
        user_id = fields["user_id"]
        try:
            with uow_factory() as uow:
                response, _from_cache = uow.execute_forget_plan(
                    user_id=user_id,
                    idempotency_key=idem_key,
                    request_fingerprint=fp,
                    forget_plan_id=fields["forget_plan_id"],
                    confirmation_token=fields["confirmation_token"],
                    trace_id=ctx.trace_id,
                )
        except repo.UnsupportedForgetScopeError as exc:
            raise RequestValidationError(str(exc.reason)) from exc
        except (repo.ForgetPlanNotFoundError, repo.ConfirmationCredentialError) as exc:
            raise RequestValidationError(str(exc)) from exc
        return response

    registry.register("forget.preview", preview_handler)
    registry.register("forget.execute", execute_handler)
