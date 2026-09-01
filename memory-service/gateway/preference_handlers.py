"""preference_handlers.py — D7C 偏好 IPC 方法（D 轨契约变更，随 D7C PR #87 落地）

新增活跃方法（FRZ-IPC-007 扩展，原 CANDIDATE_SYNC，本 PR 实现）：
  preference.list / preference.create / preference.update /
  preference.rollback / preference.history

对齐 D7D #90 落库 API（origin/main@c1ee840）：
  save_preference_version / get_current_preference_version /
  list_preference_versions / rollback_preference_version / list_preference_items

边界（如实声明）：
  - 本模块只消费 D7D 持久化结果；memory_status 显式传入时校验六值枚举，
    未传入时按 D3 §7.9 安全默认推导（临时/不持久化 → candidate，否则 active）；
    E 轨 preference_version_policy 的业务决策后续可在 handler 层前置定型，
    本模块不实现 E 轨策略。
  - 所有方法强制 user_id 隔离：payload 校验 + Repository 层双层防御。
  - 幂等/证据去重由 D7D memory_version_receipts 承担：相同 idempotency_key +
    request_fingerprint 重放返回同一版本 created=False；同证据不同值失败关闭。
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from db import repositories as repo
from db.uow import UnitOfWork
from gateway.protocol import RequestValidationError
from gateway.registry import HandlerRegistry, RequestContext

logger = logging.getLogger(__name__)

# D7D 冻结枚举（对齐 schema.py CheckConstraint / domain.enums）
ALLOWED_SCOPES = ("global", "topic", "tool", "session", "time_window")
ALLOWED_MEMORY_STATUS = ("active", "superseded", "deprecated", "expired", "removed", "candidate")

# 安全映射：D7D 领域异常 → INVALID_REQUEST（FRZ-IPC-002）
_SAFE_MESSAGES = {
    "not_found": "preference version not found or not owned by user",
    "idempotency_conflict": "idempotency key reused with different request",
    "evidence_conflict": "evidence fingerprint reused with different value",
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _request_fingerprint(method: str, canonical: Dict[str, Any]) -> str:
    """ADR-010 风格请求指纹：规范化 method + 业务语义字段。"""
    body = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return _sha256(f"{method}:{body}")


def _evidence_fingerprint(
    *,
    user_id: str,
    preference_key: str,
    preference_scope: str,
    preference_value: str,
    evidence_event_ids: Optional[List[str]] = None,
) -> str:
    """证据指纹：优先按 evidence_event_ids（排序去重）定型；
    无事件证据时退化为 (user,key,scope,value) 稳定指纹，保证幂等重放可判定。"""
    if evidence_event_ids:
        ids = sorted({str(x) for x in evidence_event_ids if str(x).strip()})
        if ids:
            return _sha256("evidence:" + "|".join(ids))
    return _sha256(f"pref:{user_id}:{preference_key}:{preference_scope}:{preference_value}")


def _require_nonempty(payload: Dict[str, Any], *fields: str) -> None:
    for field in fields:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise RequestValidationError(f"missing or blank required field: {field}")


def _require_scope(payload: Dict[str, Any]) -> str:
    scope = payload.get("preference_scope")
    if scope not in ALLOWED_SCOPES:
        raise RequestValidationError("invalid preference_scope")
    return scope


def _require_user_id(payload: Dict[str, Any], ctx: RequestContext) -> str:
    _require_nonempty(payload, "user_id")
    user_id = str(payload["user_id"])
    # 双层防御：envelope 上下文若有 user_id 且不一致 → 拒绝（当前 envelope 未强制携带）
    if ctx.user_id is not None and ctx.user_id != user_id:
        raise RequestValidationError("user_id mismatch with request context")
    return user_id


def _resolve_memory_status(payload: Dict[str, Any]) -> str:
    """解析 memory_status。

    - [I-1] 显式类型校验：字符串 "false" 不得被 bool() 自动转为 True（MEDIUM-2 返工）。
    - D3 §7.9：is_temporary=true 或 should_persist=false 时，memory_status 只能为
      candidate/expired，不得晋升 active（HIGH-01 返工：即使显式传入 memory_status
      也必须与临时/持久化生命周期标志做冲突校验）。
    - 未显式传入时按 D3 §7.9 安全默认推导（临时/不持久化 → candidate，否则 active）。
    """
    is_temporary = payload.get("is_temporary", False)
    should_persist = payload.get("should_persist", True)
    if not isinstance(is_temporary, bool) or not isinstance(should_persist, bool):
        raise RequestValidationError("is_temporary/should_persist must be boolean")
    temporary_lifecycle = is_temporary or not should_persist

    raw = payload.get("memory_status")
    if raw is not None:
        if raw not in ALLOWED_MEMORY_STATUS:
            raise RequestValidationError("invalid memory_status")
        if temporary_lifecycle and raw not in ("candidate", "expired"):
            raise RequestValidationError(
                "memory_status conflicts with is_temporary/should_persist (D3 §7.9)"
            )
        return raw
    return "candidate" if temporary_lifecycle else "active"


def _resolve_idempotency_key(payload: Dict[str, Any], ctx: RequestContext) -> Optional[str]:
    key = payload.get("idempotency_key") or ctx.idempotency_key
    if key is not None and (not isinstance(key, str) or not key.strip()):
        raise RequestValidationError("invalid idempotency_key")
    return key


def _project_version(row: Dict[str, Any], preference_key: str, preference_scope: str) -> Dict[str, Any]:
    """版本行 → IPC item 投影（剔除内部证据/幂等字段，避免泄漏指纹）。"""
    return {
        "preference_version_id": int(row["id"]),
        "preference_key": preference_key,
        "preference_scope": preference_scope,
        "version": int(row["version"]),
        "preference_value": row["preference_value"],
        "memory_status": row["memory_status"],
        "is_current": bool(row["is_current"]),
        "previous_version_id": row["previous_version_id"],
        "rollback_of_version_id": row["rollback_of_version_id"],
        "created_at": row["created_at"],
    }


def _write_fingerprints(
    method: str,
    payload: Dict[str, Any],
    user_id: str,
    preference_key: str,
    preference_scope: str,
    preference_value: str,
) -> Dict[str, Any]:
    memory_status = _resolve_memory_status(payload)
    canonical = {
        "user_id": user_id,
        "preference_key": preference_key,
        "preference_scope": preference_scope,
        "preference_value": preference_value,
        "memory_status": memory_status,
    }
    return {
        "request_fingerprint": _request_fingerprint(method, canonical),
        "evidence_fingerprint": _evidence_fingerprint(
            user_id=user_id,
            preference_key=preference_key,
            preference_scope=preference_scope,
            preference_value=preference_value,
            evidence_event_ids=payload.get("evidence_event_ids"),
        ),
        "memory_status": memory_status,
    }


def _run_guarded(fn: Callable[[], Any]) -> Any:
    """D7D 领域异常 → INVALID_REQUEST 安全映射。"""
    try:
        return fn()
    except repo.PreferenceVersionNotFoundError as exc:
        raise RequestValidationError(_SAFE_MESSAGES["not_found"]) from exc
    except repo.PreferenceVersionIdempotencyConflictError as exc:
        raise RequestValidationError(_SAFE_MESSAGES["idempotency_conflict"]) from exc
    except repo.PreferenceVersionEvidenceConflictError as exc:
        raise RequestValidationError(_SAFE_MESSAGES["evidence_conflict"]) from exc


# ── preference.create ───────────────────────────────────────────────────────


def preference_create_handler(payload: Dict[str, Any], ctx: RequestContext, uow_factory: Callable[[], UnitOfWork]) -> Dict[str, Any]:
    """创建/追加偏好版本（CREATE / UPDATE / NO_OP 由 D7D Repository 判定）。"""
    user_id = _require_user_id(payload, ctx)
    _require_nonempty(payload, "preference_key", "preference_value")
    preference_key = str(payload["preference_key"])
    preference_scope = _require_scope(payload)
    preference_value = str(payload["preference_value"])
    idem_key = _resolve_idempotency_key(payload, ctx)
    fps = _write_fingerprints(
        "preference.create", payload, user_id, preference_key, preference_scope, preference_value
    )

    def _business() -> Dict[str, Any]:
        with uow_factory() as uow:
            row = repo.save_preference_version(
                uow.conn,
                user_id=user_id,
                preference_key=preference_key,
                preference_scope=preference_scope,
                preference_value=preference_value,
                memory_status=fps["memory_status"],
                evidence_fingerprint=fps["evidence_fingerprint"],
                idempotency_key=idem_key,
                request_fingerprint=fps["request_fingerprint"],
            )
            return row

    row = _run_guarded(_business)
    created = bool(row.get("created", True))
    return {
        "item": _project_version(row, preference_key, preference_scope),
        "created": created,
        "action": "create" if created else "no_op",
    }


# ── preference.update ───────────────────────────────────────────────────────


def preference_update_handler(payload: Dict[str, Any], ctx: RequestContext, uow_factory: Callable[[], UnitOfWork]) -> Dict[str, Any]:
    """更新偏好值（UPDATE / NO_OP）。要求目标 (user,key,scope) 已存在。"""
    user_id = _require_user_id(payload, ctx)
    _require_nonempty(payload, "preference_key", "new_value")
    preference_key = str(payload["preference_key"])
    preference_scope = _require_scope(payload)
    new_value = str(payload["new_value"])
    idem_key = _resolve_idempotency_key(payload, ctx)
    fps = _write_fingerprints(
        "preference.update", payload, user_id, preference_key, preference_scope, new_value
    )

    def _business() -> Dict[str, Any]:
        with uow_factory() as uow:
            current = repo.get_current_preference_version(
                uow.conn,
                user_id=user_id,
                preference_key=preference_key,
                preference_scope=preference_scope,
            )
            if current is None:
                raise RequestValidationError("preference not found for update")
            row = repo.save_preference_version(
                uow.conn,
                user_id=user_id,
                preference_key=preference_key,
                preference_scope=preference_scope,
                preference_value=new_value,
                memory_status=fps["memory_status"],
                evidence_fingerprint=fps["evidence_fingerprint"],
                idempotency_key=idem_key,
                request_fingerprint=fps["request_fingerprint"],
            )
            return row

    row = _run_guarded(_business)
    created = bool(row.get("created", True))
    return {
        "item": _project_version(row, preference_key, preference_scope),
        "created": created,
        "action": "update" if created else "no_op",
    }


# ── preference.rollback ─────────────────────────────────────────────────────


def preference_rollback_handler(payload: Dict[str, Any], ctx: RequestContext, uow_factory: Callable[[], UnitOfWork]) -> Dict[str, Any]:
    """回滚到历史版本（追加新 current，不改写历史）。"""
    user_id = _require_user_id(payload, ctx)
    _require_nonempty(payload, "preference_key")
    preference_key = str(payload["preference_key"])
    preference_scope = _require_scope(payload)
    target_version = payload.get("target_version")
    if not isinstance(target_version, int) or target_version < 1:
        raise RequestValidationError("target_version must be positive int")
    idem_key = _resolve_idempotency_key(payload, ctx)

    def _business() -> Dict[str, Any]:
        with uow_factory() as uow:
            history = repo.list_preference_versions(
                uow.conn,
                user_id=user_id,
                preference_key=preference_key,
                preference_scope=preference_scope,
            )
            target = next((r for r in history if int(r["version"]) == target_version), None)
            if target is None:
                raise repo.PreferenceVersionNotFoundError("target version not found")
            row = repo.rollback_preference_version(
                uow.conn,
                user_id=user_id,
                preference_version_id=int(target["id"]),
                idempotency_key=idem_key,
                request_fingerprint=_request_fingerprint(
                    "preference.rollback",
                    {
                        "user_id": user_id,
                        "preference_key": preference_key,
                        "preference_scope": preference_scope,
                        "target_version": target_version,
                    },
                ),
            )
            fresh_history = repo.list_preference_versions(
                uow.conn,
                user_id=user_id,
                preference_key=preference_key,
                preference_scope=preference_scope,
            )
            return row, fresh_history

    row, fresh_history = _run_guarded(_business)
    created = bool(row.get("created", True))
    return {
        "item": _project_version(row, preference_key, preference_scope),
        "created": created,
        "action": "rollback" if created else "no_op",
        "history": [_project_version(r, preference_key, preference_scope) for r in fresh_history],
    }


# ── preference.history ──────────────────────────────────────────────────────


def preference_history_handler(payload: Dict[str, Any], ctx: RequestContext, uow_factory: Callable[[], UnitOfWork]) -> Dict[str, Any]:
    """返回 (user,key,scope) 全版本链（含 superseded），供 UI 渲染历史列表。"""
    user_id = _require_user_id(payload, ctx)
    _require_nonempty(payload, "preference_key")
    preference_key = str(payload["preference_key"])
    preference_scope = _require_scope(payload)

    with uow_factory() as uow:
        rows = repo.list_preference_versions(
            uow.conn,
            user_id=user_id,
            preference_key=preference_key,
            preference_scope=preference_scope,
        )
    return {
        "items": [_project_version(r, preference_key, preference_scope) for r in rows],
    }


# ── preference.list ─────────────────────────────────────────────────────────


def preference_list_handler(payload: Dict[str, Any], ctx: RequestContext, uow_factory: Callable[[], UnitOfWork]) -> Dict[str, Any]:
    """按用户列出偏好条目（可选按 key / scope 过滤），附带 current 版本。"""
    user_id = _require_user_id(payload, ctx)
    preference_key = payload.get("preference_key")
    preference_scope = payload.get("preference_scope")
    include_history = bool(payload.get("include_history", False))
    if preference_key is not None and (not isinstance(preference_key, str) or not preference_key.strip()):
        raise RequestValidationError("invalid preference_key")
    if preference_scope is not None and preference_scope not in ALLOWED_SCOPES:
        raise RequestValidationError("invalid preference_scope")

    with uow_factory() as uow:
        items = repo.list_preference_items(
            uow.conn,
            user_id=user_id,
            preference_key=preference_key,
            preference_scope=preference_scope,
        )
        result: List[Dict[str, Any]] = []
        for item in items:
            key = str(item["preference_key"])
            scope = str(item["preference_scope"])
            current = repo.get_current_preference_version(
                uow.conn, user_id=user_id, preference_key=key, preference_scope=scope
            )
            entry: Dict[str, Any] = {
                "memory_item_id": int(item["id"]),
                "preference_key": key,
                "preference_scope": scope,
                "current_version_id": item["current_version_id"],
                "current": _project_version(current, key, scope) if current is not None else None,
                "created_at": item["created_at"],
                "updated_at": item["updated_at"],
            }
            if include_history:
                history = repo.list_preference_versions(
                    uow.conn, user_id=user_id, preference_key=key, preference_scope=scope
                )
                entry["history"] = [_project_version(r, key, scope) for r in history]
            result.append(entry)
    return {"items": result}


# ── 注册 ────────────────────────────────────────────────────────────────────


def register_preference_handlers(registry: HandlerRegistry, uow_factory: Callable[[], UnitOfWork]) -> None:
    """注册 D7C 偏好 IPC 方法（D 轨契约变更，随本 PR 落地）。

    `preference.*` 仍是 CANDIDATE_SYNC：production 默认不注册；仅由
    app.py 的 --register-preference-handlers 显式激活（验证/演示 profile）。
    uow_factory 由 app.py 在激活时注入。
    """
    registry.register("preference.list", lambda p, c: preference_list_handler(p, c, uow_factory))
    registry.register("preference.create", lambda p, c: preference_create_handler(p, c, uow_factory))
    registry.register("preference.update", lambda p, c: preference_update_handler(p, c, uow_factory))
    registry.register("preference.rollback", lambda p, c: preference_rollback_handler(p, c, uow_factory))
    registry.register("preference.history", lambda p, c: preference_history_handler(p, c, uow_factory))
