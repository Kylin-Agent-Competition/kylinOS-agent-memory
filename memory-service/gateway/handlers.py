"""handlers.py — D4D 内置 handler（FRZ-IPC-007 路由表）

活跃方法：echo / health / memory.retrieve（真实空上下文，非假数据）
memory.store 未实现 → UNSUPPORTED_METHOD（Gate 0 预期）
turn.finalized：ADR-010 写方法（FRZ-IPC-007 新增，CANDIDATE/BLOCKED_BY_HOST_MAPPING）——
production 默认不注册（activation 方案 A+B），仅显式注册 seam 供测试/验证 profile 使用。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from db import repositories as repo
from db.engine import db_health_check
from db.uow import UnitOfWork
from gateway.protocol import ERROR_CODE_UNSUPPORTED_METHOD, RequestValidationError
from gateway.registry import HandlerRegistry, RequestContext
from observability.request_context import set_request_context
from service.source_resolver import ResolvedContent, SourceResolver

logger = logging.getLogger(__name__)


def echo_handler(payload: Dict[str, Any], ctx: RequestContext) -> Dict[str, Any]:
    """echo：回显 payload（调试/连通性验证，ECHO-003）。"""
    return {"echo": payload}


def health_handler(payload: Dict[str, Any], ctx: RequestContext) -> Dict[str, Any]:
    """health：服务状态 + DB 可达性探测 + Outbox backlog（真实指标，非假数据）。

    data.status 为真实业务探针状态（M5）：
      - DB 不可达 → degraded
      - metrics 抛错 / 返回哨兵 backlog=-1（busy）→ degraded
      - Worker 未注入（无 Outbox Worker）→ degraded（写入管道不可用）
      - 全绿 → ok
    envelope status 由 server 保持 "ok"（请求已被处理 ack），与 data.status 语义分离。
    """
    engine = ctx.extras.get("engine")
    db_ok = db_health_check(engine) if engine is not None else False
    status = "ok" if db_ok else "degraded"
    data: Dict[str, Any] = {
        "status": status,
        "db": "ok" if db_ok else "unreachable",
        "methods": ctx.extras.get("methods", []),
    }
    # T3.1：Outbox backlog / oldest_pending / dead_letter（worker.metrics() 现成）
    metrics_fn = ctx.extras.get("worker_metrics")
    if metrics_fn is not None:
        try:
            data["outbox"] = metrics_fn()
        except Exception as exc:  # noqa: BLE001
            # DB/Outbox 故障降级不抛错（busy/dead → degraded 返回）
            logger.warning("health outbox metrics 降级: %s", exc)
            data["outbox"] = {"backlog": -1, "dead_letter": -1, "oldest_pending_created_at": None}
            status = "degraded"
        else:
            # M5：哨兵/busy（backlog=-1）→ degraded（DB 层可感知的指标不可用）
            if data["outbox"].get("backlog") == -1:
                status = "degraded"
    else:
        # M5：Worker 未注入（未启动）→ 写管道不可用 → degraded
        if status == "ok":
            status = "degraded"
    data["status"] = status
    return data


def memory_retrieve_handler(payload: Dict[str, Any], ctx: RequestContext) -> Dict[str, Any]:
    """memory.retrieve：返回真实空上下文（检索主链后续接入，禁止假数据）。"""
    # 契约：FR-FB-001 降级路径（L2 连接失败 / L1 超时）均返回空 context；
    # 主链未接入前返回真实空结果，不构造虚假记忆。
    # PR#52 Issue 1：日志禁止记录用户正文/PII（query 为用户对话正文）。
    # 只记 method/request_id，不落 query 内容（与 logging_setup 安全声明一致）。
    logger.info(
        "memory.retrieve method=%s request_id=%s（主链未接入，返回空上下文）",
        ctx.method,
        ctx.request_id,
    )
    return {"context": [], "degraded": False, "reason": "retrieval main chain pending"}


def memory_store_handler(payload: Dict[str, Any], ctx: RequestContext) -> Dict[str, Any]:
    """memory.store：未实现 → UNSUPPORTED_METHOD（FRZ-IPC-007，Gate 0 预期）。"""
    raise _UnsupportedStoreError()


class _UnsupportedStoreError(Exception):
    """memory.store 未实现（转 UNSUPPORTED_METHOD）。"""

    error_code = ERROR_CODE_UNSUPPORTED_METHOD


def register_default_handlers(registry: HandlerRegistry) -> None:
    """注册冻结路由表的默认 handler（echo/health/memory.retrieve/store）。

    ADR-010 activation 方案 A+B：production 默认**不注册** `turn.finalized`——
    未注册即 UNSUPPORTED_METHOD，杜绝「协议 SUPPORTED 但生产必然 INTERNAL_ERROR」
    的矛盾（resolver BLOCKED_BY_HOST_MAPPING）。测试/验证 profile 走
    `register_turn_finalized_handler` 显式注册。
    """
    registry.register("echo", echo_handler)
    registry.register("health", health_handler)
    registry.register("memory.retrieve", memory_retrieve_handler)
    registry.register("memory.store", memory_store_handler)
    # 供 health handler 使用（方法列表由 server 注入 extras）
    registry._methods_hint = list(registry.methods())  # type: ignore[attr-defined]


# ═══════════════════════════════════════════════════════════════════
# turn.finalized（ADR-010：FRZ-IPC-007 写方法，CANDIDATE/BLOCKED_BY_HOST_MAPPING）
# ═══════════════════════════════════════════════════════════════════


class ResolverUnavailableError(Exception):
    """resolver 未注入（production 状态，转 INTERNAL_ERROR，safe）。"""


class ResolverFailureError(Exception):
    """resolver 解析失败/无结果（转 INTERNAL_ERROR；禁止编造正文/空串替代）。"""


class _TurnFinalizedValidator:
    """ADR-010 payload 校验（事件契约 v1 TurnFinalizedEvent 候选字段 → IPC 映射契约）。

    校验失败统一抛 RequestValidationError（→ INVALID_REQUEST，safe_message 固定英文，
    不回显原值）。
    """

    # 必填 metadata 字段（ADR-010 映射契约）
    REQUIRED_METADATA = (
        "schema_version", "event_id", "user_id", "session_id",
        "turn_id", "idempotency_key", "occurred_at", "collected_at",
        "source_reference",
    )
    # 必填事件字段
    REQUIRED_EVENT = ("is_final", "finalized_at")

    @classmethod
    def validate(cls, payload: Dict[str, Any], ctx: RequestContext) -> Dict[str, Any]:
        """校验并规范化 payload；返回 {metadata, event, idempotency_key}。"""
        if not isinstance(payload, dict):
            raise RequestValidationError("payload must be object")
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            raise RequestValidationError("missing required field: metadata")

        # ── metadata 必填 + 类型 ──
        for f in cls.REQUIRED_METADATA:
            if f not in metadata or metadata[f] is None:
                raise RequestValidationError(f"missing required field: metadata.{f}")
        for f in ("schema_version", "event_id", "user_id", "session_id", "turn_id", "idempotency_key", "occurred_at", "collected_at", "source_reference"):
            if not isinstance(metadata[f], str):
                raise RequestValidationError(f"invalid_type: metadata.{f}")

        # M3.1：必填 ID/引用拒空与纯空白（" "/"" 一律 invalid_blank）
        for f in ("event_id", "user_id", "session_id", "turn_id", "idempotency_key", "source_reference"):
            if not metadata[f].strip():
                raise RequestValidationError(f"invalid_blank: metadata.{f}")
        if not metadata["schema_version"].strip():
            raise RequestValidationError("invalid_blank: metadata.schema_version")

        # schema_version：严格 `1.<minor 整数>`（M3.2），如 "1.0.0"/"1."/"1.abc" → 拒绝
        schema_version = metadata["schema_version"]
        if not re.fullmatch(r"1\.\d+", schema_version.strip()):
            raise RequestValidationError("unsupported_schema_version")

        # 时间戳（invalid_timestamp → INVALID_REQUEST；M3.3 必须带时区）
        for f in ("occurred_at", "collected_at"):
            cls._require_iso_ts(metadata[f], f"metadata.{f}")

        # ── idempotency_key 权威合并（ADR-010：envelope 顶级 → payload.metadata） ──
        env_key = ctx.idempotency_key
        meta_key = metadata["idempotency_key"]
        if env_key is not None and env_key != meta_key:
            raise RequestValidationError("inconsistent_value: idempotency_key")
        idem_key = env_key if env_key is not None else meta_key

        # ── trace_id 唯一真源：envelope 顶级；payload.metadata.trace_id 若提供必须相等 ──
        if metadata.get("trace_id") is not None and metadata["trace_id"] != ctx.trace_id:
            raise RequestValidationError("inconsistent_value: trace_id")

        # ── 事件字段 ──
        for f in cls.REQUIRED_EVENT:
            if f not in payload:
                raise RequestValidationError(f"missing required field: {f}")
        if payload["is_final"] is not True:
            # 必须显式为 true，不得用缺省 false 掩盖缺字段
            raise RequestValidationError("invalid_value: is_final must be true")
        if not isinstance(payload["finalized_at"], str):
            raise RequestValidationError("invalid_type: finalized_at")
        cls._require_iso_ts(payload["finalized_at"], "finalized_at")

        # 可选字段类型
        for f, t in (
            ("final_message_id", str),
            ("finalization_reason", str),
            ("stop_reason", str),
            ("retry_of_turn_id", str),
        ):
            if f in payload and payload[f] is not None and not isinstance(payload[f], t):
                raise RequestValidationError(f"invalid_type: {f}")
        if "retry_of_turn_id" in payload and payload["retry_of_turn_id"] is not None:
            if payload["retry_of_turn_id"] == metadata["turn_id"]:
                raise RequestValidationError("invalid_value: retry_of_turn_id must not equal turn_id")
        tool_call_ids = payload.get("tool_call_ids")
        if tool_call_ids is not None:
            if not isinstance(tool_call_ids, list) or not all(isinstance(x, str) for x in tool_call_ids):
                raise RequestValidationError("invalid_type: tool_call_ids")
            if len(set(tool_call_ids)) != len(tool_call_ids):
                raise RequestValidationError("duplicate_value: tool_call_ids")

        return {
            "metadata": metadata,
            "event": payload,
            "idempotency_key": idem_key,
        }

    @staticmethod
    def _require_iso_ts(value: str, field: str) -> None:
        # M3.3：必须可解析且带时区（拒绝无时区的 "2026-08-27T10:00:00" 及纯日期串）
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            raise RequestValidationError(f"invalid_timestamp: {field}") from None
        if dt.tzinfo is None:
            raise RequestValidationError(f"invalid_timestamp: {field} (timezone required)")


def _canonical_ts(value: Optional[str]) -> Optional[str]:
    """时间戳规范化：UTC 毫秒 ISO 8601（参与指纹 hash；不可解析按原值）。"""
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")
    except (ValueError, TypeError):
        return value


def request_fingerprint(
    *, method: str, metadata: Dict[str, Any], event: Dict[str, Any]
) -> str:
    """ADR-010 `_request_fingerprint`：sha256(规范化 method + 业务语义字段)。

    进入指纹：event_id / host_turn_id / source_reference / is_final / finalized_at /
    occurred_at / final_message_id / finalization_reason / stop_reason /
    retry_of_turn_id / tool_call_ids（排序）；
    不进入：trace_id / request_id / deadline_ms（传输字段）、collected_at（采集时间）。
    absent 与 null 等价（统一规范化为「缺失」占位）。
    """
    fields: Dict[str, Any] = {
        "event_id": metadata.get("event_id"),
        "host_turn_id": metadata.get("turn_id"),
        "source_reference": metadata.get("source_reference"),
        "is_final": event.get("is_final"),
        "finalized_at": _canonical_ts(event.get("finalized_at")),
        "occurred_at": _canonical_ts(metadata.get("occurred_at")),
        "final_message_id": event.get("final_message_id"),
        "finalization_reason": event.get("finalization_reason"),
        "stop_reason": event.get("stop_reason"),
        "retry_of_turn_id": event.get("retry_of_turn_id"),
        "tool_call_ids": sorted(set(event.get("tool_call_ids") or [])),
    }
    canon = {k: (v if v is not None else "<absent>") for k, v in fields.items()}
    canonical = json.dumps(canon, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"{method}\n{canonical}".encode("utf-8")).hexdigest()


def register_turn_finalized_handler(
    registry: HandlerRegistry,
    *,
    uow_factory: Callable[[], UnitOfWork],
    resolver: SourceResolver,
) -> None:
    """显式注册 `turn.finalized`（ADR-010 activation 方案 A+B 测试态 seam）。

    production `register_default_handlers` 不含它；测试/验证 profile 调用本函数
    注册并注入 in-memory resolver。handler 失败语义：
    - payload 校验失败 → INVALID_REQUEST（RequestValidationError）
    - resolver 缺失/失败 → INTERNAL_ERROR（safe，禁止编造正文）
    - 幂等冲突（同三元组不同指纹）→ INVALID_REQUEST（IdempotencyConflictError）
    """

    def handler(payload: Dict[str, Any], ctx: RequestContext) -> Dict[str, Any]:
        validated = _TurnFinalizedValidator.validate(payload, ctx)
        metadata = validated["metadata"]
        user_id = metadata["user_id"]
        session_id = metadata["session_id"]
        host_turn_id = metadata["turn_id"]
        source_reference = metadata["source_reference"]
        idem_key = validated["idempotency_key"]
        trace_id = ctx.trace_id  # envelope 顶级（唯一真源，ADR-010）

        # M4：校验通过后 Set event_id 到线程请求上下文（DAO 层/日志自动携带；
        # server.py 的 finally 已负责清理，此处仅补充下半场业务上下文）
        set_request_context(
            request_id=ctx.request_id,
            trace_id=trace_id,
            method=ctx.method,
            event_id=metadata.get("event_id", ""),
        )

        fp = request_fingerprint(
            method="turn.finalized", metadata=metadata, event=validated["event"]
        )

        def _business(uow: UnitOfWork) -> Dict[str, Any]:
            # B1 前置所有权校验：session_id 已存在但属其它用户 → 拒绝
            # （同一线程内先由 DAO 层兜底，此处 handler 层前置 + 固定 safe_message）
            conv = repo.get_conversation_with_user(uow.conn, session_id=session_id)
            if conv is not None and conv["user_id"] != user_id:
                raise RequestValidationError("session ownership conflict")
            existing = None
            if host_turn_id is not None:
                existing = repo.find_turn_by_host(
                    uow.conn, session_id=session_id, host_turn_id=host_turn_id, user_id=user_id
                )
            original_user_text: Optional[str] = None
            if existing is None:
                # INSERT：必须调 resolver（成功写正文；失败 INTERNAL_ERROR，禁止编造）
                if resolver is None:
                    raise ResolverUnavailableError(
                        "source resolver not available (BLOCKED_BY_HOST_MAPPING)"
                    )
                resolved: Optional[ResolvedContent] = resolver.resolve(source_reference)
                if resolved is None or not resolved.original_user_text:
                    raise ResolverFailureError(
                        "resolver failed to resolve original_user_text"
                    )
                original_user_text = resolved.original_user_text
            # UPDATE/refinalize 不调 resolver（保持首次正文，ADR-010 字段矩阵）
            result = uow.save_turn_with_outbox(
                user_id=user_id,
                session_id=session_id,
                turn_index=None,  # INSERT 时服务端计算
                original_user_text=original_user_text,
                is_end=1,
                event_type=repo.EVENT_TURN_FINALIZED,
                trace_id=trace_id,
                host_turn_id=host_turn_id,
                extra_payload={
                    # occurred_at/collected_at/finalized_at 随 outbox payload 元数据入队
                    # （不落 turns 列，FRZ-DB-001）；M3.4：统一走 _canonical_ts 规范化
                    # 为 UTC 毫秒 ISO 8601，避免等价时间表达在 outbox 中不一致
                    "occurred_at": _canonical_ts(metadata.get("occurred_at")),
                    "collected_at": _canonical_ts(metadata.get("collected_at")),
                    "finalized_at": _canonical_ts(validated["event"].get("finalized_at")),
                },
            )
            # ADR-010 响应：{db_turn_id, host_turn_id, conversation_id}
            return {
                "db_turn_id": result["db_turn_id"],
                "host_turn_id": result["host_turn_id"],
                "conversation_id": result["conversation_id"],
            }

        try:
            with uow_factory() as uow:
                response, _from_cache = uow.execute_idempotent(
                    user_id=user_id,
                    session_id=session_id,
                    idempotency_key=idem_key,
                    business_fn=lambda: _business(uow),
                    request_fingerprint=fp,
                )
        except repo.ConversationOwnershipError as exc:
            # B1 双层防御兜底：DAO 层所有权校验兜异常 → INVALID_REQUEST
            # （sane_message 固定英文，不回显 conversation_id/db_turn_id 等标识）
            raise RequestValidationError(str(exc)) from exc
        return response

    registry.register("turn.finalized", handler)
