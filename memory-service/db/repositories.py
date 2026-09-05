"""repositories.py — D4D DAO 层（FRZ-DB-001/003/005、附录 A）

职责：
  - 5 张核心表的基础 CRUD（conversations/turns/memory_entries/outbox/idempotency_cache）
  - 幂等写入（附录 A 单一真相源）：查缓存 → 命中返回缓存；未命中 → 执行业务 +
    同事务写缓存；并发冲突（复合 PK 唯一约束）→ 回查返回首次缓存，不视为错误
  - SQLITE_BUSY（busy_timeout 到期）→ 抛 DatabaseLockedError，由调用方降级，
    不向聊天链路上抛（FR-DB-003）
  - 写操作（INSERT/UPDATE/DELETE）统一经 _wrap_locked 转 DatabaseLockedError
    （PR#52 Issue 9）；只读查询（WAL 快照读）不产生 SQLITE_BUSY，无需包装
  - 跨用户隔离：所有查询强制 user_id 过滤（Repository 层约束，[02 §16.6]）
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, delete, exists, func, insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from db.engine import DatabaseLockedError, is_locked_error
from db.schema import (
    conversations,
    forget_audit,
    forget_plan,
    idempotency_cache,
    memory_entries,
    memory_conflict,
    memory_conflict_member,
    memory_relation,
    memory_items,
    memory_version_receipts,
    memory_versions,
    outbox,
    source_events,
    turns,
)

logger = logging.getLogger(__name__)

# 幂等 TTL（冻结 FRZ-IPC-005 / FRZ-DB-005）：24h
IDEMPOTENCY_TTL = timedelta(hours=24)

# 幂等缓存 wrapper 键（ADR-010 冻结缓存内部结构，不改 DDL）
FINGERPRINT_KEY = "_request_fingerprint"


class IdempotencyConflictError(Exception):
    """幂等冲突：相同三元组 + 不同请求指纹（ADR-010）→ INVALID_REQUEST。

    语义：不同事件误复用同一 idempotency_key 时禁止被静默吞掉。
    """


class ConversationOwnershipError(Exception):
    """会话所有权冲突：session_id 已存在但属于其它 user（B1 跨用户污染）。

    语义：用户 B 复用用户 A 的 session_id 写入时，禁止命中/篡改 A 的 conversation
    或 turn（[02 §16.6] 跨用户隔离）。UoW 回滚 → 无 Turn/Outbox/幂等缓存残留，
    由 handler 层转 RequestValidationError → INVALID_REQUEST（不回显标识）。
    """


class PreferenceVersionIdempotencyConflictError(Exception):
    """同一版本链重用幂等键但请求指纹不一致，拒绝静默覆盖。"""


class PreferenceVersionEvidenceConflictError(Exception):
    """同一版本链复用证据指纹却试图写入不同值，拒绝制造矛盾历史。"""


class PreferenceVersionNotFoundError(Exception):
    """版本不存在、非本用户所有，或不是允许回滚的历史版本。"""


class EventIdentityConflict(Exception):
    """同 event_id 但 immutable identity 不一致（ADR-013/014 HIGH-01）。

    语义：同 event_id + immutable identity 不一致（含跨用户复用 event_id）→
    handler 转 INVALID_REQUEST，不回显标识、不回读他人事件（MEDIUM-03）。
    """

# outbox 事件类型（业务入队用）
EVENT_TURN_FINALIZED = "turn.finalized"
EVENT_MEMORY_UPSERTED = "memory.upserted"
EVENT_FORGET_EXECUTED = "forget.executed"
EVENT_MEMORY_RELATION_CHANGED = "memory.relation.changed"
EVENT_MEMORY_CONFLICT_CHANGED = "memory.conflict.changed"
EVENT_MEMORY_LIFECYCLE_CHANGED = "memory.lifecycle.changed"
EVENT_MEMORY_LIFECYCLE_ARCHIVE_REQUESTED = "memory.lifecycle.archive_requested"

_RELATION_TYPES = {"version", "evidence", "derived"}
_CONFLICT_TYPES = {"contradiction", "temporal_inconsistency", "source_conflict", "preference_conflict", "scope_ambiguity"}
_RESOLUTION_STATUSES = {"detected", "analyzing", "resolved_auto", "resolved_manual", "deferred", "unresolvable"}
_DECISION_ACTIONS = {"keep_left", "keep_right", "coexist", "defer", "reject"}
_MEMORY_STATUSES = {"active", "candidate", "superseded", "deprecated", "expired", "removed"}
_MEMORY_TYPES = {"short_term", "medium_term", "long_term", "ephemeral"}
_EVIDENCE_TIERS = {"user_explicit_config_latest", "user_confirmed", "tool_execution_result", "consistent_behavior_multiple", "behavior_inference_single", "model_inference"}
_KNOWLEDGE_TYPES = {"workflow", "case", "template", "fact", "constraint", "failure_experience"}


# ── D10D 精准遗忘持久化（ADR-015/019） ──

DELETE_MODE_SOFT = "soft"
DELETE_MODE_HARD = "hard"
# selector 明文生命周期（HIGH-01）：Preview 完成后清除/置安全占位
CLEARED = "<CLEARED>"
# 删除类事件 Outbox 优先级（ADR-015：0=普通 / 1=删除类 forget.* / 2=预留 urgent）
FORGET_PRIORITY = 1
# 确认凭据 TTL（ADR-019 §4.7：默认 300s；参数化登记 TD-D，本版硬编码）
CONFIRMATION_TOKEN_TTL_SECONDS = 300


class ForgetPlanNotFoundError(Exception):
    """遗忘计划不存在或不属于当前用户 → INVALID_REQUEST（跨用户隔离）。"""


class ConfirmationCredentialError(Exception):
    """确认凭据无效/过期/已消费/绑定不符 → INVALID_REQUEST（零副作用）。"""


class UnsupportedForgetScopeError(Exception):
    """本期不支持的遗忘作用域/目标类别/执行模式 → fail-closed（INVALID_REQUEST）。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_confirmation_token(token: str) -> str:
    """确认凭据 SHA-256 哈希（明文不落库，ADR-019 §4.7）。"""
    return _sha256(token)


def compute_selection_hash(resolved_target_ids: List[str]) -> str:
    """selection_hash 仅由结构化 resolved_target_ids 派生（D5 决策，非正文）。"""
    canonical = json.dumps(
        sorted(resolved_target_ids), ensure_ascii=False, separators=(",", ":")
    )
    return _sha256(f"selection:{canonical}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wrap_locked(exc: BaseException) -> BaseException:
    """把 SQLITE_BUSY 统一转 DatabaseLockedError。"""
    if is_locked_error(exc):
        logger.warning("SQLite busy_timeout 到期（SQLITE_BUSY），转入降级路径: %s", exc)
        return DatabaseLockedError("database is locked (busy_timeout)")
    return exc


# ── conversations ──


def upsert_conversation(
    conn, *, user_id: str, session_id: str, started_at: Optional[str] = None
) -> int:
    """按 session_id upsert conversation，返回 id（幂等：重复调用返回已有 id）。

    跨用户隔离（B1 修复，[02 §16.6]）：命中既有 conversation 时必须校验其
    user_id 与调用方一致；不一致抛 ConversationOwnershipError，禁止复用其它
    用户的会话（所有权边界 = conversation.user_id）。不修改冻结表结构。
    """
    started_at = started_at or _now_iso()
    existing = conn.execute(
        select(conversations).where(conversations.c.session_id == session_id)
    ).mappings().first()
    if existing is not None:
        if existing["user_id"] != user_id:
            raise ConversationOwnershipError(
                "session ownership conflict (conversation belongs to another user)"
            )
        return int(existing["id"])
    try:
        res = conn.execute(
            insert(conversations)
            .values(user_id=user_id, session_id=session_id, started_at=started_at)
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return int(res.lastrowid)


def get_conversation_with_user(
    conn, *, session_id: str
) -> Optional[Dict[str, Any]]:
    """按 session_id 查 conversation（不限定 user，供 handler 所有权前置校验）。

    与 `get_conversation`（限定 user_id）区别：本函数返回任意用户持有的会话，
    用于检测「会话已存在但属于其它用户」的跨用户冲突（B1）。
    """
    row = conn.execute(
        select(conversations).where(conversations.c.session_id == session_id)
    ).mappings().first()
    return dict(row) if row else None


def get_conversation(conn, *, session_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """按 session_id + user_id 查询（跨用户隔离，Repository 层强制过滤）。"""
    row = conn.execute(
        select(conversations).where(
            and_(conversations.c.session_id == session_id, conversations.c.user_id == user_id)
        )
    ).mappings().first()
    return dict(row) if row else None


# ── turns ──


def insert_turn(
    conn,
    *,
    session_id: str,
    turn_index: int,
    original_user_text: str,
    model_request: Optional[str] = None,
    model_response: Optional[str] = None,
    is_end: int = 0,
    created_at: Optional[str] = None,
    trace_id: Optional[str] = None,
    host_turn_id: Optional[str] = None,
) -> int:
    """插入 turn，返回 id。original_user_text 保存用户原文（隔离语义）。

    ADR-011：trace_id（IPC envelope 唯一真源）/ host_turn_id（Upsert 匹配键）
    nullable 列透传落库。
    """
    try:
        res = conn.execute(
            insert(turns).values(
                session_id=session_id,
                turn_index=turn_index,
                original_user_text=original_user_text,
                model_request=model_request,
                model_response=model_response,
                is_end=is_end,
                created_at=created_at or _now_iso(),
                trace_id=trace_id,
                host_turn_id=host_turn_id,
            )
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return int(res.lastrowid)


def find_turn_by_host(
    conn, *, session_id: str, host_turn_id: str, user_id: str
) -> Optional[Dict[str, Any]]:
    """按 ADR-010 Upsert 匹配键 (session_id, host_turn_id) 查既有 turn。

    跨用户隔离（B1 修复，[02 §16.6]）：JOIN conversations 并强制
    `conversations.user_id == user_id`，保证只定位**当前用户**的 turn，
    防止用户 B 以 `uB/s1/H-1` 命中用户 A 的既有 turn 走 UPDATE/refinalize 分支
    篡改 A 的数据。

    Returns:
        turns 行 dict；不存在（或不属于该用户）返回 None。host_turn_id 为宿主
        字符串 ID，与 DB turns.id（db_turn_id）显式区分。
    """
    row = conn.execute(
        select(turns)
        .join(conversations, conversations.c.session_id == turns.c.session_id)
        .where(
            and_(
                turns.c.session_id == session_id,
                turns.c.host_turn_id == host_turn_id,
                conversations.c.user_id == user_id,
            )
        )
        .order_by(turns.c.id.asc())
        .limit(1)
    ).mappings().first()
    return dict(row) if row else None


def next_turn_index(conn, *, session_id: str) -> int:
    """服务端计算 turn_index：同一会话内 1 + MAX(turn_index)（ADR-010）。

    事件不携带 turn_index；重投/refinalize 不重算（保持首次值），
    仅 INSERT 路径调用。
    """
    current = conn.execute(
        select(func.max(turns.c.turn_index)).where(turns.c.session_id == session_id)
    ).scalar()
    return 1 + int(current or 0)


def update_turn_refinalize(
    conn,
    *,
    turn_id: int,
    trace_id: str,
    is_end: int = 1,
) -> int:
    """UPDATE/refinalize 路径：更新 trace_id（指向最终写入链路），保持首次值不动。

    ADR-010 字段矩阵：UPDATE 仅更新 trace_id（最新请求）；
    turn_index / original_user_text / created_at / is_end 保持首次值；
    不调用 resolver（正文已在首次 INSERT 落库）。

    Returns:
        受影响行数。
    """
    try:
        res = conn.execute(
            update(turns)
            .where(turns.c.id == turn_id)
            .values(trace_id=trace_id, is_end=is_end)
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return int(res.rowcount)


def get_turn(conn, *, turn_id: int, user_id: str) -> Optional[Dict[str, Any]]:
    """按 turn_id + user_id 查询（跨用户隔离，Repository 层强制过滤）。

    turns 表无 user_id 列，经 conversations.session_id JOIN 强制隔离，
    防止 turn_id 可枚举时跨用户读取 original_user_text（PII）[02 §16.6]。
    """
    row = conn.execute(
        select(turns)
        .join(conversations, conversations.c.session_id == turns.c.session_id)
        .where(and_(turns.c.id == turn_id, conversations.c.user_id == user_id))
    ).mappings().first()
    return dict(row) if row else None


# ── memory_entries ──


def insert_memory_entry(
    conn,
    *,
    user_id: str,
    entry_type: str,
    content: Dict[str, Any],
    source_turn_id: Optional[int] = None,
    confidence: float = 0.0,
    trace_id: Optional[str] = None,
    topic_key: Optional[str] = None,
) -> int:
    """插入 memory_entry（content 序列化为 JSON 文本），返回 id。

    ADR-011：trace_id nullable 列透传（IPC envelope 唯一真源）。
    """
    if topic_key is not None:
        _require_nonempty(topic_key=topic_key)
    now = _now_iso()
    try:
        res = conn.execute(
            insert(memory_entries).values(
                user_id=user_id,
                entry_type=entry_type,
                content=json.dumps(content, ensure_ascii=False),
                source_turn_id=source_turn_id,
                confidence=confidence,
                version=1,
                row_revision=1,
                is_deleted=0,
                created_at=now,
                updated_at=now,
                trace_id=trace_id,
                topic_key=topic_key,
            )
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return int(res.lastrowid)


def soft_delete_memory_entry(
    conn, *, entry_id: int, user_id: str, current_version: Optional[int] = None,
    current_row_revision: Optional[int] = None,
) -> int:
    """乐观锁软删除：D8D 后仅 row_revision 是 CAS token。

    Returns:
        受影响行数；0 = 版本冲突（调用方重试或放弃，FRZ-DB-001 乐观锁规范）。
    """
    entry = _get_memory_entry(conn, entry_id=entry_id, user_id=user_id)
    if entry is None:
        return 0
    expected = current_row_revision if current_row_revision is not None else current_version
    if expected is None:
        raise ValueError("current_row_revision is required")
    if int(entry.get("row_revision") or 0) != int(expected):
        return 0
    values: Dict[str, Any] = {
        "is_deleted": 1,
        "row_revision": int(expected) + 1,
        "updated_at": _now_iso(),
    }
    if entry["entry_type"] == "knowledge":
        values["memory_status"] = "removed"
    try:
        res = conn.execute(
            update(memory_entries)
            .where(
                and_(
                    memory_entries.c.id == entry_id,
                    memory_entries.c.user_id == user_id,
                    memory_entries.c.row_revision == expected,
                    memory_entries.c.is_deleted == 0,
                )
            )
            .values(**values)
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return int(res.rowcount)


def list_memory_entries(
    conn,
    *,
    user_id: str,
    entry_type: Optional[str] = None,
    include_deleted: bool = False,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """按 user_id 强制过滤（跨用户隔离）；默认排除软删除记录。"""
    stmt = select(memory_entries).where(memory_entries.c.user_id == user_id)
    if entry_type is not None:
        stmt = stmt.where(memory_entries.c.entry_type == entry_type)
    if not include_deleted:
        stmt = stmt.where(memory_entries.c.is_deleted == 0)
    stmt = stmt.order_by(memory_entries.c.id.desc()).limit(limit)
    try:
        rows = conn.execute(stmt).mappings().all()
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return [dict(r) for r in rows]


# ── D7D preference version persistence ──


def _require_nonempty(**fields: str) -> None:
    """拒绝空白标识和值，避免把无归属或无语义的记录写入版本真源。"""
    invalid = [name for name, value in fields.items() if not isinstance(value, str) or not value.strip()]
    if invalid:
        raise ValueError(f"D7D required fields must be non-empty: {', '.join(sorted(invalid))}")


def _get_preference_item(
    conn, *, user_id: str, preference_key: str, preference_scope: str
) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        select(memory_items).where(
            and_(
                memory_items.c.user_id == user_id,
                memory_items.c.preference_key == preference_key,
                memory_items.c.preference_scope == preference_scope,
            )
        )
    ).mappings().first()
    return dict(row) if row else None


def _get_or_create_preference_item(
    conn, *, user_id: str, preference_key: str, preference_scope: str
) -> Dict[str, Any]:
    item = _get_preference_item(
        conn, user_id=user_id, preference_key=preference_key, preference_scope=preference_scope
    )
    if item is not None:
        return item

    now = _now_iso()
    try:
        result = conn.execute(
            insert(memory_items).values(
                user_id=user_id,
                preference_key=preference_key,
                preference_scope=preference_scope,
                created_at=now,
                updated_at=now,
            )
        )
    except IntegrityError:
        item = _get_preference_item(
            conn, user_id=user_id, preference_key=preference_key, preference_scope=preference_scope
        )
        if item is not None:
            return item
        raise
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return {
        "id": int(result.lastrowid),
        "user_id": user_id,
        "preference_key": preference_key,
        "preference_scope": preference_scope,
        "current_version_id": None,
        "created_at": now,
        "updated_at": now,
    }


def _item_owner(conn, memory_item_id: int) -> str:
    owner = conn.execute(
        select(memory_items.c.user_id).where(memory_items.c.id == memory_item_id)
    ).scalar_one()
    return str(owner)


def _version_row(conn, *, version_id: int, user_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        select(memory_versions)
        .join(memory_items, memory_versions.c.memory_item_id == memory_items.c.id)
        .where(and_(memory_versions.c.id == version_id, memory_items.c.user_id == user_id))
    ).mappings().first()
    return dict(row) if row else None


def _current_version_for_item(conn, *, memory_item_id: int) -> Optional[Dict[str, Any]]:
    current_version_id = conn.execute(
        select(memory_items.c.current_version_id).where(memory_items.c.id == memory_item_id)
    ).scalar_one()
    if current_version_id is None:
        return None
    row = conn.execute(
        select(memory_versions).where(
            and_(
                memory_versions.c.id == current_version_id,
                memory_versions.c.memory_item_id == memory_item_id,
                memory_versions.c.is_current == 1,
            )
        )
    ).mappings().first()
    return dict(row) if row else None


def _latest_version_number(conn, *, memory_item_id: int) -> int:
    value = conn.execute(
        select(func.max(memory_versions.c.version)).where(
            memory_versions.c.memory_item_id == memory_item_id
        )
    ).scalar()
    return int(value or 0)


def _receipt_version(
    conn, *, receipt: Dict[str, Any], user_id: str
) -> Dict[str, Any]:
    version = _version_row(conn, version_id=int(receipt["memory_version_id"]), user_id=user_id)
    assert version is not None
    return {**version, "created": False}


def _return_existing_idempotent(
    conn, *, memory_item_id: int, idempotency_key: Optional[str], request_fingerprint: str
) -> Optional[Dict[str, Any]]:
    if idempotency_key is None:
        return None
    row = conn.execute(
        select(memory_version_receipts).where(
            and_(
                memory_version_receipts.c.memory_item_id == memory_item_id,
                memory_version_receipts.c.idempotency_key == idempotency_key,
            )
        )
    ).mappings().first()
    if row is None:
        return None
    existing = dict(row)
    if existing["request_fingerprint"] != request_fingerprint:
        raise PreferenceVersionIdempotencyConflictError("同一幂等键对应的请求指纹不一致")
    return existing


def _return_existing_evidence_or_fail(
    conn,
    *,
    memory_item_id: int,
    evidence_fingerprint: str,
    preference_value: str,
    memory_status: str,
) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        select(memory_version_receipts)
        .where(
            and_(
                memory_version_receipts.c.memory_item_id == memory_item_id,
                memory_version_receipts.c.evidence_fingerprint == evidence_fingerprint,
            )
        )
    ).mappings().first()
    if row is None:
        return None
    existing = dict(row)
    if (
        existing["preference_value"] != preference_value
        or existing["memory_status"] != memory_status
    ):
        raise PreferenceVersionEvidenceConflictError(
            "同一证据指纹不能写入不同的偏好值或生命周期状态"
        )
    return existing


def _record_operation_receipt(
    conn,
    *,
    memory_item_id: int,
    memory_version_id: int,
    operation_kind: str,
    preference_value: str,
    memory_status: str,
    evidence_fingerprint: str,
    idempotency_key: Optional[str],
    request_fingerprint: str,
    created_at: str,
) -> None:
    conn.execute(
        insert(memory_version_receipts).values(
            memory_item_id=memory_item_id,
            memory_version_id=memory_version_id,
            operation_kind=operation_kind,
            preference_value=preference_value,
            memory_status=memory_status,
            evidence_fingerprint=evidence_fingerprint,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            created_at=created_at,
        )
    )


def _append_preference_version(
    conn,
    *,
    memory_item_id: int,
    preference_value: str,
    memory_status: str,
    evidence_fingerprint: str,
    idempotency_key: Optional[str],
    request_fingerprint: str,
    rollback_of_version_id: Optional[int] = None,
    no_op_on_same_value: bool = True,
    deduplicate_evidence: bool = True,
) -> Dict[str, Any]:
    replay = _return_existing_idempotent(
        conn,
        memory_item_id=memory_item_id,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if replay is not None:
        return _receipt_version(conn, receipt=replay, user_id=_item_owner(conn, memory_item_id))

    if deduplicate_evidence:
        evidence_replay = _return_existing_evidence_or_fail(
            conn,
            memory_item_id=memory_item_id,
            evidence_fingerprint=evidence_fingerprint,
            preference_value=preference_value,
            memory_status=memory_status,
        )
        if evidence_replay is not None:
            return _receipt_version(conn, receipt=evidence_replay, user_id=_item_owner(conn, memory_item_id))

    current = _current_version_for_item(conn, memory_item_id=memory_item_id)
    if (
        no_op_on_same_value
        and current is not None
        and current["preference_value"] == preference_value
        and current["memory_status"] == memory_status
    ):
        _record_operation_receipt(
            conn,
            memory_item_id=memory_item_id,
            memory_version_id=int(current["id"]),
            operation_kind="no_op",
            preference_value=preference_value,
            memory_status=memory_status,
            evidence_fingerprint=evidence_fingerprint,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            created_at=_now_iso(),
        )
        return {**current, "created": False}

    previous_version_id = int(current["id"]) if current is not None else None
    now = _now_iso()
    try:
        result = conn.execute(
            insert(memory_versions).values(
                memory_item_id=memory_item_id,
                version=_latest_version_number(conn, memory_item_id=memory_item_id) + 1,
                previous_version_id=previous_version_id,
                rollback_of_version_id=rollback_of_version_id,
                preference_value=preference_value,
                memory_status=memory_status,
                evidence_fingerprint=evidence_fingerprint,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                # 既有 current 时先追加非 current 后继；触发器据此仅允许旧版本
                # 原子转为 superseded，再激活该后继，防止直接 SQL 清空 current。
                is_current=0 if current is not None else 1,
                created_at=now,
            )
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    version_id = int(result.lastrowid)
    if current is not None:
        try:
            conn.execute(
                update(memory_versions)
                .where(memory_versions.c.id == current["id"])
                .values(is_current=0, memory_status="superseded")
            )
        except OperationalError as exc:
            raise _wrap_locked(exc) from exc
    conn.execute(
        update(memory_items)
        .where(memory_items.c.id == memory_item_id)
        .values(updated_at=now)
    )
    version = _version_row(conn, version_id=version_id, user_id=_item_owner(conn, memory_item_id))
    assert version is not None
    _record_operation_receipt(
        conn,
        memory_item_id=memory_item_id,
        memory_version_id=version_id,
        operation_kind="rollback" if rollback_of_version_id is not None else "write",
        preference_value=preference_value,
        memory_status=memory_status,
        evidence_fingerprint=evidence_fingerprint,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        created_at=now,
    )
    return {**version, "created": True}


def save_preference_version(
    conn,
    *,
    user_id: str,
    preference_key: str,
    preference_scope: str,
    preference_value: str,
    memory_status: str,
    evidence_fingerprint: str,
    idempotency_key: Optional[str],
    request_fingerprint: str,
) -> Dict[str, Any]:
    """创建或更新偏好版本，不原地覆盖历史。"""
    _require_nonempty(
        user_id=user_id,
        preference_key=preference_key,
        preference_scope=preference_scope,
        preference_value=preference_value,
        memory_status=memory_status,
        evidence_fingerprint=evidence_fingerprint,
        request_fingerprint=request_fingerprint,
    )
    if idempotency_key is not None:
        _require_nonempty(idempotency_key=idempotency_key)
    item = _get_or_create_preference_item(
        conn, user_id=user_id, preference_key=preference_key, preference_scope=preference_scope
    )
    return _append_preference_version(
        conn,
        memory_item_id=int(item["id"]),
        preference_value=preference_value,
        memory_status=memory_status,
        evidence_fingerprint=evidence_fingerprint,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )


def get_preference_version(
    conn, *, user_id: str, preference_version_id: int
) -> Optional[Dict[str, Any]]:
    """按用户读取单个版本；跨用户 ID 不可枚举读取。"""
    return _version_row(conn, version_id=preference_version_id, user_id=user_id)


def get_current_preference_version(
    conn, *, user_id: str, preference_key: str, preference_scope: str
) -> Optional[Dict[str, Any]]:
    item = _get_preference_item(
        conn, user_id=user_id, preference_key=preference_key, preference_scope=preference_scope
    )
    if item is None:
        return None
    return _current_version_for_item(conn, memory_item_id=int(item["id"]))


def list_preference_versions(
    conn, *, user_id: str, preference_key: str, preference_scope: str
) -> List[Dict[str, Any]]:
    item = _get_preference_item(
        conn, user_id=user_id, preference_key=preference_key, preference_scope=preference_scope
    )
    if item is None:
        return []
    rows = conn.execute(
        select(memory_versions)
        .where(memory_versions.c.memory_item_id == item["id"])
        .order_by(memory_versions.c.version)
    ).mappings().all()
    return [dict(row) for row in rows]


def list_preference_items(
    conn,
    *,
    user_id: str,
    preference_key: Optional[str] = None,
    preference_scope: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """按用户列出偏好条目（可选按 key / scope 过滤），供 UI 枚举当前偏好。

    D7C preference.list 消费：只返回当前用户（user_id 强制过滤）的
    memory_items 行，跨用户不可见。每个条目附带 current_version_id 指针；
    current 版本详情 / 全版本链由 get_current_preference_version /
    list_preference_versions 提供。
    """
    _require_nonempty(user_id=user_id)
    conditions = [memory_items.c.user_id == user_id]
    if preference_key is not None:
        _require_nonempty(preference_key=preference_key)
        conditions.append(memory_items.c.preference_key == preference_key)
    if preference_scope is not None:
        _require_nonempty(preference_scope=preference_scope)
        conditions.append(memory_items.c.preference_scope == preference_scope)
    rows = conn.execute(
        select(memory_items)
        .where(and_(*conditions))
        .order_by(memory_items.c.preference_key, memory_items.c.preference_scope)
    ).mappings().all()
    return [dict(row) for row in rows]


def rollback_preference_version(
    conn,
    *,
    user_id: str,
    preference_version_id: int,
    idempotency_key: Optional[str],
    request_fingerprint: str,
) -> Dict[str, Any]:
    """将历史版本的值追加为新 current 版本，不覆盖旧版本。"""
    _require_nonempty(user_id=user_id, request_fingerprint=request_fingerprint)
    if idempotency_key is not None:
        _require_nonempty(idempotency_key=idempotency_key)
    target = _version_row(conn, version_id=preference_version_id, user_id=user_id)
    if target is None:
        raise PreferenceVersionNotFoundError("目标版本不存在或不属于当前用户")
    current = _current_version_for_item(conn, memory_item_id=int(target["memory_item_id"]))
    if current is None or int(target["id"]) == int(current["id"]) or target["version"] >= current["version"]:
        raise PreferenceVersionNotFoundError("只能回滚到同一版本链中的历史版本")
    return _append_preference_version(
        conn,
        memory_item_id=int(target["memory_item_id"]),
        preference_value=str(target["preference_value"]),
        # 历史版本在被替换后状态为 superseded；回滚把其值追加为新的 current，
        # 新版本按 D7E 版本计划恢复 active，而不是复制历史标记。
        memory_status="active",
        # rollback 的业务目标可以重复选择；它不是普通写入证据的跨操作唯一身份。
        # 每次新请求使用独立回执证据，真正重放仍由 idempotency_key +
        # request_fingerprint 决定，避免旧 rollback 回执吞掉后续合法 rollback。
        evidence_fingerprint=f"rollback:{target['id']}:{uuid.uuid4().hex}",
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        rollback_of_version_id=int(target["id"]),
        no_op_on_same_value=False,
        deduplicate_evidence=False,
    )


# ── outbox ──


def enqueue_outbox(
    conn,
    *,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: Dict[str, Any],
    next_retry_at: Optional[str] = None,
    priority: int = 0,
) -> int:
    """Outbox 入队（必须在业务写同一事务内调用，UoW 保证原子性）。

    ADR-015：priority 可选（默认 0=普通索引任务；forget.* 删除类 = 1）。
    """
    try:
        res = conn.execute(
            insert(outbox).values(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                payload=json.dumps(payload, ensure_ascii=False),
                attempts=0,
                next_retry_at=next_retry_at or _now_iso(),
                last_error=None,
                created_at=_now_iso(),
                priority=priority,
            )
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return int(res.lastrowid)


def claim_pending_outbox(conn, *, now_iso: str, max_retries: int, limit: int = 100) -> List[Dict[str, Any]]:
    """Worker 轮询：取 next_retry_at <= now 且 attempts <= max_retries 的事件。

    ADR-015：按 priority DESC → next_retry_at ASC 取数（遗忘/撤回任务优先于
    普通索引任务，[02 §11.3]）。
    """
    try:
        rows = conn.execute(
            select(outbox)
            .where(
                and_(
                    outbox.c.next_retry_at <= now_iso,
                    outbox.c.attempts <= max_retries,
                )
            )
            .order_by(
                func.coalesce(outbox.c.priority, 0).desc(),
                outbox.c.next_retry_at.asc(),
            )
            .limit(limit)
        ).mappings().all()
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return [dict(r) for r in rows]


def mark_outbox_success(conn, *, outbox_id: int) -> None:
    """处理成功：删除事件（附录 B 步骤 4a）。"""
    try:
        conn.execute(delete(outbox).where(outbox.c.id == outbox_id))
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc


def mark_outbox_failure(
    conn, *, outbox_id: int, attempts: int, next_retry_at: str, last_error: str
) -> None:
    """处理失败：attempts++ / 退避 / last_error（附录 B 步骤 4b）。"""
    try:
        conn.execute(
            update(outbox)
            .where(outbox.c.id == outbox_id)
            .values(attempts=attempts, next_retry_at=next_retry_at, last_error=last_error)
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc


def mark_outbox_dead_letter(conn, *, outbox_id: int, attempts: int, last_error: str) -> None:
    """Dead Letter：保留记录，attempts 记录最终次数，next_retry_at=NULL，不丢事件（附录 B 4c）。"""
    try:
        conn.execute(
            update(outbox)
            .where(outbox.c.id == outbox_id)
            .values(attempts=attempts, next_retry_at=None, last_error=last_error)
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc


def cleanup_expired_idempotency(conn, *, now_iso: str, limit: int = 100) -> int:
    """幂等缓存过期清理（Worker 每轮顺带，借 idx_idempotency_expires）。

    使用子查询限制删除行数，避免依赖 SQLite 可选的
    ``SQLITE_ENABLE_UPDATE_DELETE_LIMIT`` 编译选项；SQLAlchemy 2.0 通用
    Delete 也没有跨方言的 ``.limit()``。
    """
    try:
        res = conn.exec_driver_sql(
            "DELETE FROM idempotency_cache "
            "WHERE (user_id, session_id, idempotency_key) IN ("
            "SELECT user_id, session_id, idempotency_key "
            "FROM idempotency_cache WHERE expires_at < ? "
            "ORDER BY expires_at LIMIT ?)",
            (now_iso, limit),
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return int(res.rowcount)


# ── idempotency_cache（附录 A 单一真相源） ──


def get_idempotency_cache(
    conn, *, user_id: str, session_id: str, idempotency_key: str
) -> Optional[Dict[str, Any]]:
    """查幂等缓存（命中且未过期 → 返回缓存行）。"""
    try:
        row = conn.execute(
            select(idempotency_cache).where(
                and_(
                    idempotency_cache.c.user_id == user_id,
                    idempotency_cache.c.session_id == session_id,
                    idempotency_cache.c.idempotency_key == idempotency_key,
                )
            )
        ).mappings().first()
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    if row is None:
        return None
    row = dict(row)
    # 命中但已过期 → 由调用方删除后继续执行
    return row


def delete_idempotency_cache(
    conn, *, user_id: str, session_id: str, idempotency_key: str
) -> None:
    """删除幂等缓存行（命中但过期后由调用方删除）。"""
    try:
        conn.execute(
            delete(idempotency_cache).where(
                and_(
                    idempotency_cache.c.user_id == user_id,
                    idempotency_cache.c.session_id == session_id,
                    idempotency_cache.c.idempotency_key == idempotency_key,
                )
            )
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc


def write_idempotency_cache(
    conn,
    *,
    user_id: str,
    session_id: str,
    idempotency_key: str,
    response: Dict[str, Any],
) -> None:
    """写幂等缓存（TTL=24h）。复合 PK 冲突 → IntegrityError，由 UoW 捕获回查。"""
    now = datetime.now(timezone.utc)
    try:
        conn.execute(
            insert(idempotency_cache).values(
                user_id=user_id,
                session_id=session_id,
                idempotency_key=idempotency_key,
                response=json.dumps(response, ensure_ascii=False),
                created_at=now.isoformat(),
                expires_at=(now + IDEMPOTENCY_TTL).isoformat(),
            )
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc


def _wrap_response(response: Dict[str, Any], request_fingerprint: Optional[str]) -> Dict[str, Any]:
    """幂等缓存 wrapper（ADR-010）：提供指纹时包 wrapper，否则原样返回。"""
    if request_fingerprint is None:
        return response
    return {FINGERPRINT_KEY: request_fingerprint, "response": response}


def _unwrap_response(
    stored: str, request_fingerprint: Optional[str]
) -> Dict[str, Any]:
    """幂等缓存 unwrap（ADR-010）。

    - 缓存行无 `_request_fingerprint`（legacy）→ 直接返回 response（向后兼容）；
    - 缓存行有指纹且调用方提供指纹：比对，不一致 → IdempotencyConflictError；
    - 缓存行有指纹但调用方未提供（legacy 调用方）→ 直接返回 response（不破坏既有调用）。
    """
    parsed = json.loads(stored)
    if not isinstance(parsed, dict) or FINGERPRINT_KEY not in parsed:
        return parsed
    cached_fp = parsed[FINGERPRINT_KEY]
    if request_fingerprint is not None and cached_fp != request_fingerprint:
        raise IdempotencyConflictError(
            "idempotency key reused with different request fingerprint"
        )
    return parsed["response"]


# ── 幂等执行（附录 A：检查 → 执行 → 缓存，同事务；ADR-010 指纹 wrapper/unwrap） ──


def execute_idempotent(
    conn,
    *,
    user_id: str,
    session_id: str,
    idempotency_key: str,
    business_fn,
    request_fingerprint: Optional[str] = None,
    response_for_cache_fn=None,
) -> Tuple[Dict[str, Any], bool]:
    """幂等执行器（附录 A 单一真相源 + ADR-010 请求指纹）。

    Args:
        business_fn: 无参可调用，返回 (response_dict)；副作用（SQLite+Outbox）必须
            在传入的同一 conn 事务中执行，保证与缓存写入同事务。
        request_fingerprint: ADR-010 `_request_fingerprint`（sha256 规范化
            method+业务语义字段）。提供时写缓存走 wrapper；命中时比对指纹，
            不一致抛 IdempotencyConflictError（转 INVALID_REQUEST）。
        response_for_cache_fn: 可选的持久化前转换函数。业务调用方仍收到原始
            response，缓存只保存一次性凭据剔除后的安全子集。

    Returns:
        (response, from_cache)：from_cache=True 表示命中缓存未执行副作用。

    Raises:
        IdempotencyConflictError: 相同三元组 + 不同请求指纹（ADR-010）。
        IntegrityError: 并发未命中双写冲突（UoW 捕获后回查，不视为错误）。
    """
    cached = get_idempotency_cache(
        conn, user_id=user_id, session_id=session_id, idempotency_key=idempotency_key
    )
    if cached is not None:
        if cached["expires_at"] > datetime.now(timezone.utc).isoformat():
            return _unwrap_response(cached["response"], request_fingerprint), True
        # 命中但已过期 → 删除后继续执行
        delete_idempotency_cache(
            conn, user_id=user_id, session_id=session_id, idempotency_key=idempotency_key
        )

    response = business_fn()
    response_for_cache = (
        response_for_cache_fn(response) if response_for_cache_fn is not None else response
    )
    write_idempotency_cache(
        conn,
        user_id=user_id,
        session_id=session_id,
        idempotency_key=idempotency_key,
        response=_wrap_response(response_for_cache, request_fingerprint),
    )
    return response, False


# ── source_events（ADR-013，D6-D 多源事件持久化） ──

SENSITIVE_OMITTED = "<SENSITIVE-OMITTED>"
NO_CONTENT = "<no-content>"
_IDENTITY_WS = re.compile(r"\s+")

# 指纹去重窗口（ADR-013：默认 24h；参数化登记 TD-D6D-001，本版硬编码）
DEDUP_FINGERPRINT_WINDOW_HOURS = 24


def _normalize_identity_text(text: Optional[str]) -> Optional[str]:
    """内容身份归一化（去首尾空白、折叠内部空白、Unicode 大小写折叠）。"""
    if text is None:
        return None
    return _IDENTITY_WS.sub(" ", str(text).strip()).casefold()


def event_content_identity(
    *, content_summary: Optional[str], raw_payload_ref: Optional[str]
) -> str:
    """归一化 event_content_identity（ADR-013 v4）：content_summary → raw_payload_ref → <no-content>。

    不含敏感判定——敏感事件是否纳入身份由调用方决定（immutable identity 排除 content；
    request_fingerprint 用 <SENSITIVE-OMITTED> 占位）。
    """
    norm = _normalize_identity_text(content_summary)
    if norm:
        return norm
    norm = _normalize_identity_text(raw_payload_ref)
    if norm:
        return norm
    return NO_CONTENT


def _canonical_utc_ms(value: Any) -> str:
    """时间戳统一 canonicalization：aware UTC ISO8601 毫秒（ADR-013 身份组成）。"""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return value  # 不可解析原样（仅防御；正常路径已被 Pydantic 校验）
    else:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def event_identity_fingerprint(
    *,
    user_id: str,
    actor_id: str,
    source_type: str,
    event_type: str,
    occurred_at: str,
    content_identity: Optional[str],
) -> str:
    """派生 immutable event identity 指纹（ADR-013 v4，比较用，不落库）。

    字段集：user_id + actor_id + source_type + event_type + occurred_at(UTC ms) +
    event_content_identity（content_identity=None 时排除，敏感事件简并为非内容字段）。
    """
    parts = [user_id, actor_id, source_type, event_type, occurred_at]
    if content_identity is not None:
        parts.append(content_identity)
    canonical = "\x1f".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_event_identity(event, *, sensitive: bool) -> str:
    """从 NormalizedEvent 计算 immutable identity 指纹（敏感事件 content 不参与）。"""
    content_identity = None
    if not sensitive:
        content_identity = event_content_identity(
            content_summary=event.content_summary,
            raw_payload_ref=event.raw_payload_ref,
        )
    return event_identity_fingerprint(
        user_id=event.user_id,
        actor_id=event.actor_id,
        source_type=event.source_type.value,
        event_type=event.event_type.value,
        occurred_at=_canonical_utc_ms(event.occurred_at),
        content_identity=content_identity,
    )


def compute_row_identity(row: Dict[str, Any]) -> str:
    """从 source_events 行计算 immutable identity 指纹（敏感事件 content 不参与）。"""
    sensitive = (
        bool(row["is_sensitive_matched"])
        or row["sensitivity"] in ("high", "critical")
        or row["consent_scope"] == "none"
        or bool(row["should_ignore"])
    )
    content_identity = None
    if not sensitive:
        content_identity = event_content_identity(
            content_summary=row.get("content_summary"),
            raw_payload_ref=row.get("raw_payload_ref"),
        )
    return event_identity_fingerprint(
        user_id=str(row["user_id"]),
        actor_id=str(row["actor_id"]),
        source_type=str(row["source_type"]),
        event_type=str(row["event_type"]),
        occurred_at=_canonical_utc_ms(row["occurred_at"]),
        content_identity=content_identity,
    )


def get_source_event_by_event_id(
    conn, *, user_id: str, event_id: str
) -> Optional[Dict[str, Any]]:
    """按 user_id + event_id 点查（跨用户隔离，Repository 层强制过滤）。"""
    row = conn.execute(
        select(source_events).where(
            and_(source_events.c.user_id == user_id, source_events.c.event_id == event_id)
        )
    ).mappings().first()
    return dict(row) if row else None


def find_dedup_group_head(
    conn,
    *,
    user_id: str,
    content_fingerprint: str,
    source_type: str,
    now_iso: Optional[str] = None,
    window_hours: int = DEDUP_FINGERPRINT_WINDOW_HOURS,
) -> Optional[Dict[str, Any]]:
    """指纹点查：同 user + fingerprint + source_type 且 captured_at 在窗口内的首次同指纹事件。

    索引点查 O(logN+k)（ADR-013 性能红线）；窗口关闭（window_hours=0）→ 返回 None
    （退化为仅 event_id 幂等）。敏感事件 content_fingerprint=NULL 不入本查询（HIGH-03）。
    """
    if content_fingerprint is None or window_hours <= 0:
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat(
        timespec="milliseconds"
    )
    row = conn.execute(
        select(source_events)
        .where(
            and_(
                source_events.c.user_id == user_id,
                source_events.c.content_fingerprint == content_fingerprint,
                source_events.c.source_type == source_type,
                source_events.c.captured_at >= cutoff,
            )
        )
        .order_by(source_events.c.id.asc())
        .limit(1)
    ).mappings().first()
    return dict(row) if row else None


def insert_source_event(
    conn,
    *,
    user_id: str,
    event_id: str,
    actor_id: str,
    session_id: str,
    turn_id: Optional[str],
    tool_call_id: Optional[str],
    source_type: str,
    event_type: str,
    schema_version: str,
    trace_id: Optional[str],
    source_reference: Optional[str],
    raw_payload_ref: Optional[str],
    content_summary: Optional[str],
    idempotency_key: str,
    consent_scope: str,
    source_business_status: str,
    sensitivity: str,
    is_sensitive_matched: int,
    should_ignore: int,
    payload_security_checked: int,
    memory_type: Optional[str],
    requires_embedding: int,
    has_structured_payload: int,
    language_tag: Optional[str],
    occurred_at: str,
    captured_at: str,
    content_fingerprint: Optional[str],
    dedup_group: Optional[str],
    duplicate_of: Optional[int],
    admission_decision: str,
    admission_reason_code: str,
    processing_status: str,
    created_at: str,
    updated_at: str,
) -> int:
    """插入 source_events 行，返回 id。

    跨用户 event_id IntegrityError（当前 user 未查到，但 INSERT 触发 UNIQUE(event_id)）
    → 直接 EventIdentityConflict（fail-close，不回查/不返回他人事件，MEDIUM-03）。
    """
    try:
        res = conn.execute(
            insert(source_events).values(
                user_id=user_id,
                event_id=event_id,
                actor_id=actor_id,
                session_id=session_id,
                turn_id=turn_id,
                tool_call_id=tool_call_id,
                source_type=source_type,
                event_type=event_type,
                schema_version=schema_version,
                trace_id=trace_id,
                source_reference=source_reference,
                raw_payload_ref=raw_payload_ref,
                content_summary=content_summary,
                idempotency_key=idempotency_key,
                consent_scope=consent_scope,
                source_business_status=source_business_status,
                sensitivity=sensitivity,
                is_sensitive_matched=is_sensitive_matched,
                should_ignore=should_ignore,
                payload_security_checked=payload_security_checked,
                memory_type=memory_type,
                requires_embedding=requires_embedding,
                has_structured_payload=has_structured_payload,
                language_tag=language_tag,
                occurred_at=occurred_at,
                captured_at=captured_at,
                content_fingerprint=content_fingerprint,
                dedup_group=dedup_group,
                duplicate_of=duplicate_of,
                admission_decision=admission_decision,
                admission_reason_code=admission_reason_code,
                processing_status=processing_status,
                created_at=created_at,
                updated_at=updated_at,
            )
        )
    except IntegrityError:
        # UNIQUE(event_id) 冲突：当前 user 下已查不到，判定被其它 ownership 占用 → fail-close
        raise EventIdentityConflict(
            "event_id already owned by another identity"
        ) from None
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return int(res.lastrowid)


def list_source_events(
    conn,
    *,
    user_id: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """按 user + 时间线（id 升序）分页列出事件（审计用，跨用户隔离）。"""
    stmt = (
        select(source_events)
        .where(source_events.c.user_id == user_id)
        .order_by(source_events.c.id.asc())
        .limit(limit)
    )
    try:
        rows = conn.execute(stmt).mappings().all()
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return [dict(r) for r in rows]


def find_pending_eligible(conn, *, user_id: str) -> List[Dict[str, Any]]:
    """D9-D 消费资格谓词（ADR-013 MEDIUM-02）：pending + allow_extraction + duplicate_of IS NULL。

    仅满足三条件的事件可进入 Extraction 调度；REJECT/AUDIT_ONLY/content duplicate 不返回。
    """
    stmt = (
        select(source_events)
        .where(
            and_(
                source_events.c.user_id == user_id,
                source_events.c.processing_status == "pending",
                source_events.c.admission_decision == "allow_extraction",
                source_events.c.duplicate_of.is_(None),
            )
        )
        .order_by(source_events.c.id.asc())
    )
    try:
        rows = conn.execute(stmt).mappings().all()
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return [dict(r) for r in rows]


# ── 指标（诊断页：backlog / oldest_pending_age / index_sync_lag） ──


def outbox_backlog(conn, *, now_iso: str) -> Dict[str, Any]:
    """backlog 统计（FR-FB-003 诊断页暴露）。"""
    pending = conn.execute(
        select(func.count())
        .select_from(outbox)
        .where(and_(outbox.c.next_retry_at.is_not(None), outbox.c.attempts <= 3))
    ).scalar()
    dead = conn.execute(
        select(func.count())
        .select_from(outbox)
        .where(outbox.c.next_retry_at.is_(None))
    ).scalar()
    oldest = conn.execute(
        select(outbox.c.created_at)
        .where(and_(outbox.c.next_retry_at.is_not(None), outbox.c.attempts <= 3))
        .order_by(outbox.c.created_at.asc())
        .limit(1)
    ).scalar()
    return {
        "backlog": int(pending or 0),
        "dead_letter": int(dead or 0),
        "oldest_pending_created_at": oldest,
    }


def latest_memory_change_ts(conn) -> Optional[str]:
    """memory_entries 最新变更时间戳（updated_at/created_at 最大值）。

    index_sync_lag 口径（D9D 任务卡 §4.2 冻结）：latest committed memory change
    timestamp = memory_entries 最新 updated_at/created_at 的最大值。
    空表返回 None。
    """
    latest_created = conn.execute(
        select(func.max(memory_entries.c.created_at))
    ).scalar()
    latest_updated = conn.execute(
        select(func.max(memory_entries.c.updated_at))
    ).scalar()
    candidates = [ts for ts in (latest_created, latest_updated) if ts is not None]
    return max(candidates) if candidates else None


# ── forget_plan / forget_audit（ADR-015/019：精准遗忘持久化） ──


def insert_forget_plan(
    conn,
    *,
    user_id: str,
    forget_plan_id: str,
    forget_mode: str,
    target_selector: Optional[str],
    target_type: str,
    target_id: Optional[str],
    target_session_id: Optional[str],
    target_topic: Optional[str],
    target_time_range: Optional[str],
    requires_confirmation: bool,
    is_cascade: bool,
    delete_mode: str,
) -> None:
    """插入遗忘计划行（status='pending'；Preview 前明文 selector 仅短期存在）。"""
    now = _now_iso()
    try:
        conn.execute(
            insert(forget_plan).values(
                user_id=user_id,
                forget_plan_id=forget_plan_id,
                forget_mode=forget_mode,
                target_selector=target_selector,
                target_type=target_type,
                target_id=target_id,
                target_session_id=target_session_id,
                target_topic=target_topic,
                target_time_range=target_time_range,
                status="pending",
                requires_confirmation=1 if requires_confirmation else 0,
                is_cascade=1 if is_cascade else 0,
                delete_mode=delete_mode,
                has_vector_cleanup=0,
                created_at=now,
                updated_at=now,
            )
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc


def get_forget_plan_by_id(
    conn, *, user_id: str, forget_plan_id: str
) -> Optional[Dict[str, Any]]:
    """按 user_id + forget_plan_id 点查（跨用户隔离，Repository 层强制过滤）。"""
    row = conn.execute(
        select(forget_plan).where(
            and_(
                forget_plan.c.user_id == user_id,
                forget_plan.c.forget_plan_id == forget_plan_id,
            )
        )
    ).mappings().first()
    return dict(row) if row else None


def update_forget_plan_preview(
    conn,
    *,
    user_id: str,
    forget_plan_id: str,
    resolved_target_ids: List[str],
    affected_count: int,
    selection_hash: str,
    confirmation_token_hash: str,
    token_expires_at: str,
) -> None:
    """Preview 完成：写解析快照 + 凭据哈希 + 清除 selector 明文 + status→awaiting_confirmation。

    HIGH-01：target_selector / target_topic 置 <CLEARED>，持久层仅存结构化
    resolved_target_ids + selection_hash；凭据只存 SHA-256 哈希。
    """
    try:
        conn.execute(
            update(forget_plan)
            .where(
                and_(
                    forget_plan.c.user_id == user_id,
                    forget_plan.c.forget_plan_id == forget_plan_id,
                )
            )
            .values(
                resolved_target_ids=json.dumps(resolved_target_ids, ensure_ascii=False),
                affected_count=affected_count,
                selection_hash=selection_hash,
                confirmation_token=confirmation_token_hash,
                token_expires_at=token_expires_at,
                target_selector=CLEARED,
                target_topic=CLEARED,
                status="awaiting_confirmation",
                updated_at=_now_iso(),
            )
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc


def consume_confirmation_token(
    conn,
    *,
    user_id: str,
    forget_plan_id: str,
    confirmation_token_plaintext: str,
    now_iso: str,
) -> Dict[str, Any]:
    """校验确认凭据绑定 + 过期 + 未消费；消费 = confirmation_token 置 NULL + status→executing（同事务）。

    ADR-019 §4.7：绑定 user_id + forget_plan_id + selection_hash（凭据哈希存于
    计划行，selection_hash 同行不可变，绑定天然成立）；拒绝用户不匹配/计划不匹配/
    过期/已消费。失败零副作用（仅读取/校验）。
    """
    plan = get_forget_plan_by_id(conn, user_id=user_id, forget_plan_id=forget_plan_id)
    if plan is None:
        raise ConfirmationCredentialError("forget plan not found or not owned by user")
    if plan["status"] != "awaiting_confirmation":
        raise ConfirmationCredentialError("forget plan is not awaiting confirmation")
    stored_hash = plan.get("confirmation_token")
    if stored_hash is None:
        raise ConfirmationCredentialError("confirmation credential already consumed")
    if plan.get("token_expires_at") is None or plan["token_expires_at"] <= now_iso:
        raise ConfirmationCredentialError("confirmation credential expired")
    if hash_confirmation_token(confirmation_token_plaintext) != stored_hash:
        raise ConfirmationCredentialError("confirmation credential mismatch")
    try:
        conn.execute(
            update(forget_plan)
            .where(
                and_(
                    forget_plan.c.user_id == user_id,
                    forget_plan.c.forget_plan_id == forget_plan_id,
                )
            )
            .values(confirmation_token=None, status="executing", updated_at=_now_iso())
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return plan


def update_forget_plan_terminal(
    conn,
    *,
    user_id: str,
    forget_plan_id: str,
    status: str,
    executed_count: int,
    executed_at: str,
    affected_count: int,
) -> None:
    """终态收口：executing→completed/failed/rolled_back。

    MEDIUM-03 红线：executed_count != affected_count 禁止进入 completed（漏删不得报完成）。
    """
    if status == "completed" and executed_count != affected_count:
        raise ValueError(
            "executed_count must equal affected_count to enter completed (MEDIUM-03)"
        )
    try:
        conn.execute(
            update(forget_plan)
            .where(
                and_(
                    forget_plan.c.user_id == user_id,
                    forget_plan.c.forget_plan_id == forget_plan_id,
                )
            )
            .values(
                executed_count=executed_count,
                executed_at=executed_at,
                status=status,
                updated_at=_now_iso(),
            )
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc


def insert_forget_audit(
    conn,
    *,
    audit_id: str,
    forget_plan_id: str,
    user_id: str,
    forget_mode: str,
    target_type: Optional[str],
    delete_mode: str,
    is_cascade: bool,
    affected_count: Optional[int],
    selection_hash: Optional[str],
    confirmation_ref: Optional[str],
    status: str,
    result_code: Optional[str],
    trace_id: Optional[str],
    sensitivity_max: Optional[str],
    executed_at: Optional[str],
) -> int:
    """最小审计（零正文）写入；terminal 必填 executed_at（v0.3/MEDIUM-01）。

    红线：不含正文/摘要/原始 selector/Token 原文/敏感错误详情。
    """
    if status in ("completed", "failed", "rolled_back") and executed_at is None:
        raise ValueError("terminal audit requires executed_at (MEDIUM-01)")
    now = _now_iso()
    try:
        res = conn.execute(
            insert(forget_audit).values(
                audit_id=audit_id,
                forget_plan_id=forget_plan_id,
                user_id=user_id,
                forget_mode=forget_mode,
                target_type=target_type,
                delete_mode=delete_mode,
                is_cascade=1 if is_cascade else 0,
                affected_count=affected_count,
                selection_hash=selection_hash,
                confirmation_ref=confirmation_ref,
                status=status,
                result_code=result_code,
                trace_id=trace_id,
                sensitivity_max=sensitivity_max,
                created_at=now,
                executed_at=executed_at,
            )
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return int(res.lastrowid)


# ── 软删主路径 dispatcher（ADR-015 §4.4；契约 §四.4） ──


def _get_memory_entry(
    conn, *, entry_id: int, user_id: str
) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        select(memory_entries).where(
            and_(
                memory_entries.c.id == entry_id,
                memory_entries.c.user_id == user_id,
            )
        )
    ).mappings().first()
    return dict(row) if row else None


def _get_preference_item_by_id(
    conn, *, user_id: str, memory_item_id: int
) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        select(memory_items).where(
            and_(
                memory_items.c.id == memory_item_id,
                memory_items.c.user_id == user_id,
            )
        )
    ).mappings().first()
    return dict(row) if row else None


def soft_delete_preference_item(
    conn, *, user_id: str, memory_item_id: int, forget_plan_id: str
) -> Optional[int]:
    """D7D memory_status='removed' 机制：追加 removed 版本（复用既有 Repository 语义）。

    Returns:
        新版本 id；目标不存在/跨用户/无 current 版本 → None（漏删，不计入 executed_count）。
    """
    item = _get_preference_item_by_id(
        conn, user_id=user_id, memory_item_id=memory_item_id
    )
    if item is None:
        return None
    current = _current_version_for_item(conn, memory_item_id=memory_item_id)
    if current is None:
        return None
    if current["memory_status"] == "removed":
        return int(current["id"])  # 已是 removed（幂等）
    preference_value = str(current["preference_value"])
    fingerprint = _sha256(f"forget:{user_id}:{memory_item_id}:{forget_plan_id}")
    result = _append_preference_version(
        conn,
        memory_item_id=memory_item_id,
        preference_value=preference_value,
        memory_status="removed",
        evidence_fingerprint=fingerprint,
        idempotency_key=None,
        request_fingerprint=fingerprint,
    )
    return int(result["id"])


def soft_delete_resolved_targets(
    conn,
    *,
    user_id: str,
    target_type: str,
    resolved_target_ids: List[str],
    forget_plan_id: str,
) -> Tuple[int, List[str]]:
    """软删主路径：按 target_type 分发到既有权威软删状态。

    - knowledge → memory_entries.is_deleted=1（复用乐观锁；FTS 由触发器同步移除）
    - preference → D7D memory_status='removed'
    - event/all → Runtime fail-closed（source_events 无 is_deleted 列，消费者在 pipeline/）

    Returns:
        (executed_count, version_ids)。executed_count 反映真实处理数：目标不存在/
        跨用户/版本冲突不计入（上层据此 executed_count != affected_count → 不进 completed）。
    """
    if target_type == "knowledge":
        executed = 0
        for raw in resolved_target_ids:
            try:
                entry_id = int(raw)
            except (TypeError, ValueError):
                continue
            entry = _get_memory_entry(conn, entry_id=entry_id, user_id=user_id)
            if entry is None:
                continue  # 不存在/跨用户 → 漏删
            if entry["is_deleted"] == 1:
                executed += 1  # 已是删除态（幂等）
                continue
            executed += soft_delete_memory_entry(
                conn,
                entry_id=entry_id,
                user_id=user_id,
                # ``version`` is the stable retrieval/index identity.  D8D
                # lifecycle mutations intentionally advance only
                # ``row_revision``; passing ``version`` here would make a
                # later forget CAS fail after any lifecycle transition.
                current_row_revision=int(entry["row_revision"]),
            )
        return executed, []
    if target_type == "preference":
        executed = 0
        version_ids: List[str] = []
        for raw in resolved_target_ids:
            try:
                item_id = int(raw)
            except (TypeError, ValueError):
                continue
            version_id = soft_delete_preference_item(
                conn,
                user_id=user_id,
                memory_item_id=item_id,
                forget_plan_id=forget_plan_id,
            )
            if version_id is not None:
                executed += 1
                version_ids.append(str(version_id))
        return executed, version_ids
    if target_type == "all":
        executed = 0
        version_ids: List[str] = []
        for raw in resolved_target_ids:
            try:
                kind, raw_id = raw.split(":", 1)
            except (AttributeError, ValueError) as exc:
                raise UnsupportedForgetScopeError("full_reset target must be tagged") from exc
            if kind == "knowledge":
                count, _ = soft_delete_resolved_targets(
                    conn,
                    user_id=user_id,
                    target_type="knowledge",
                    resolved_target_ids=[raw_id],
                    forget_plan_id=forget_plan_id,
                )
            elif kind == "preference":
                count, versions = soft_delete_resolved_targets(
                    conn,
                    user_id=user_id,
                    target_type="preference",
                    resolved_target_ids=[raw_id],
                    forget_plan_id=forget_plan_id,
                )
                version_ids.extend(versions)
            else:
                raise UnsupportedForgetScopeError("full_reset target has unknown type")
            executed += count
        return executed, version_ids
    raise UnsupportedForgetScopeError(
        f"soft delete not supported for target_type={target_type!r}"
    )


# ── D8D relation / conflict / lifecycle persistence (ADR-017) ──


def _d8d_nonempty(**fields: str) -> None:
    invalid = [name for name, value in fields.items() if not isinstance(value, str) or not value.strip()]
    if invalid:
        raise ValueError(f"D8D required fields must be non-empty: {', '.join(sorted(invalid))}")


def _knowledge_row(conn, *, user_id: str, knowledge_id: str, eligible_only: bool = False) -> Optional[Dict[str, Any]]:
    stmt = select(memory_entries).where(and_(memory_entries.c.user_id == user_id, memory_entries.c.entry_type == "knowledge", memory_entries.c.knowledge_id == knowledge_id))
    if eligible_only:
        stmt = stmt.where(memory_entries.c.lifecycle_eligibility == "eligible")
    row = conn.execute(stmt).mappings().first()
    return dict(row) if row else None


def _source_event_row(conn, *, user_id: str, event_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(select(source_events).where(and_(source_events.c.user_id == user_id, source_events.c.event_id == event_id))).mappings().first()
    return dict(row) if row else None


def _d8d_outbox(conn, *, aggregate_id: str, event_type: str, payload: Dict[str, Any]) -> int:
    """Write only structural metadata to outbox; callers must never supply content."""
    forbidden = {"content", "conflict_summary", "evidence", "original_user_text"}
    if forbidden.intersection(payload):
        raise ValueError("D8D outbox payload must not contain content")
    res = conn.execute(insert(outbox).values(aggregate_type="memory", aggregate_id=aggregate_id, event_type=event_type, payload=json.dumps(payload, sort_keys=True), attempts=0, created_at=_now_iso(), priority=0))
    return int(res.lastrowid)


def insert_knowledge_entry(
    conn, *, user_id: str, knowledge_id: str, knowledge_type: str, source_event_id: str,
    content: Dict[str, Any], confidence: float, conditions: Optional[str] = None,
    trace_id: Optional[str] = None, topic_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist a new trusted knowledge item and its primary evidence edge atomically.

    The evidence tier is derived solely from the same-user admitted source event;
    callers cannot promote a weak/failed source by passing their own tier.
    """
    _d8d_nonempty(user_id=user_id, knowledge_id=knowledge_id, knowledge_type=knowledge_type, source_event_id=source_event_id)
    if topic_key is not None:
        _d8d_nonempty(topic_key=topic_key)
    if knowledge_type not in _KNOWLEDGE_TYPES:
        raise ValueError("invalid knowledge_type")
    event = _source_event_row(conn, user_id=user_id, event_id=source_event_id)
    if event is None or event["admission_decision"] != "allow_extraction":
        raise ValueError("knowledge source event is not admitted")
    status, source_type = event["source_business_status"], event["source_type"]
    if status == "failed" and knowledge_type != "failure_experience":
        raise ValueError("failed source may only persist failure_experience")
    if status in {"partial", "cancelled", "timeout", "ignored"}:
        raise ValueError("source business status cannot persist knowledge")
    eligible = source_type in {"manual_config", "tool_result"} and status in {"success", "completed"}
    tier = "user_explicit_config_latest" if source_type == "manual_config" and eligible else ("tool_execution_result" if eligible else None)
    lifecycle_eligibility = "eligible" if tier else "evidence_unmapped"
    now = _now_iso()
    try:
        # Canonical idempotent replay (ADR-017 §3.1.1): a retried logical ingress
        # with the same user/knowledge/source and identical immutable inputs must
        # return the existing canonical identity without re-inserting the entry,
        # re-creating the primary evidence relation, or emitting a second Outbox
        # event.  Any drift in immutable inputs is fail-closed.
        existing = conn.execute(
            select(memory_entries).where(and_(
                memory_entries.c.user_id == user_id,
                memory_entries.c.entry_type == "knowledge",
                memory_entries.c.knowledge_id == knowledge_id,
            ))
        ).mappings().first()
        if existing is not None:
            edge = conn.execute(
                select(memory_relation).where(and_(
                    memory_relation.c.user_id == user_id,
                    memory_relation.c.relation_type == "evidence",
                    memory_relation.c.is_primary == 1,
                    memory_relation.c.left_endpoint_type == "knowledge",
                    memory_relation.c.left_endpoint_id == knowledge_id,
                    memory_relation.c.right_endpoint_type == "source_event",
                ))
            ).mappings().first()
            if edge is None:
                raise ValueError("canonical primary evidence relation is missing")
            if edge["right_endpoint_id"] != source_event_id:
                raise ValueError("knowledge replay source event conflict")
            stored_content = json.loads(existing["content"])
            if (
                existing["knowledge_type"] != knowledge_type
                or existing["conditions"] != conditions
                or existing["confidence"] != confidence
                or stored_content != content
            ):
                raise ValueError("knowledge replay immutable input conflict")
            return {
                "memory_entry_id": int(existing["id"]),
                "memory_id": str(existing["id"]),
                "version_id": f"v{int(existing['version'])}",
                "knowledge_id": knowledge_id,
                "evidence_tier": existing["evidence_tier"],
                "lifecycle_eligibility": existing["lifecycle_eligibility"],
                "replayed": True,
            }
        res = conn.execute(insert(memory_entries).values(user_id=user_id, entry_type="knowledge", content=json.dumps(content, ensure_ascii=False), confidence=confidence, version=1, row_revision=1, is_deleted=0, created_at=now, updated_at=now, trace_id=trace_id, knowledge_id=knowledge_id, knowledge_type=knowledge_type, conditions=conditions, topic_key=topic_key, lifecycle_eligibility=lifecycle_eligibility, memory_status="candidate", memory_type="short_term", evidence_tier=tier, last_accessed_at=None, access_count=None))
        entry_id = int(res.lastrowid)
        relation_id = f"evidence:{knowledge_id}:{source_event_id}"
        insert_relation(conn, user_id=user_id, relation_id=relation_id, relation_type="evidence", left_endpoint_type="knowledge", left_endpoint_id=knowledge_id, right_endpoint_type="source_event", right_endpoint_id=source_event_id, is_primary=True, emit_outbox=False)
        # The canonical evidence edge is created as part of this same business
        # write.  Emit its structural change event in the same transaction,
        # while keeping user content and evidence payloads out of Outbox.
        _d8d_outbox(
            conn,
            aggregate_id=knowledge_id,
            event_type=EVENT_MEMORY_RELATION_CHANGED,
            payload={
                "user_id": user_id,
                "knowledge_id": knowledge_id,
                "relation_id": relation_id,
                "occurred_at": now,
            },
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return {"memory_entry_id": entry_id, "memory_id": str(entry_id), "version_id": "v1", "knowledge_id": knowledge_id, "evidence_tier": tier, "lifecycle_eligibility": lifecycle_eligibility}


def insert_relation(
    conn, *, user_id: str, relation_id: str, relation_type: str,
    left_endpoint_type: str, left_endpoint_id: str, right_endpoint_type: str,
    right_endpoint_id: str, is_primary: bool = False, emit_outbox: bool = True,
) -> Dict[str, Any]:
    _d8d_nonempty(user_id=user_id, relation_id=relation_id, relation_type=relation_type, left_endpoint_type=left_endpoint_type, left_endpoint_id=left_endpoint_id, right_endpoint_type=right_endpoint_type, right_endpoint_id=right_endpoint_id)
    if relation_type not in _RELATION_TYPES or left_endpoint_type not in {"knowledge", "source_event"} or right_endpoint_type not in {"knowledge", "source_event"}:
        raise ValueError("invalid relation enum")
    allowed = {"version": ("knowledge", "knowledge"), "derived": ("knowledge", "knowledge"), "evidence": ("knowledge", "source_event")}
    if (left_endpoint_type, right_endpoint_type) != allowed[relation_type]:
        raise ValueError("invalid relation endpoint direction")
    if left_endpoint_type == right_endpoint_type and left_endpoint_id == right_endpoint_id:
        raise ValueError("self relation is forbidden")
    if _knowledge_row(conn, user_id=user_id, knowledge_id=left_endpoint_id) is None:
        raise ValueError("left knowledge endpoint is not owned by user")
    right_exists = _knowledge_row(conn, user_id=user_id, knowledge_id=right_endpoint_id) if right_endpoint_type == "knowledge" else _source_event_row(conn, user_id=user_id, event_id=right_endpoint_id)
    if right_exists is None:
        raise ValueError("right endpoint is not owned by user")
    now = _now_iso()
    res = conn.execute(insert(memory_relation).values(user_id=user_id, relation_id=relation_id, relation_type=relation_type, left_endpoint_type=left_endpoint_type, left_endpoint_id=left_endpoint_id, right_endpoint_type=right_endpoint_type, right_endpoint_id=right_endpoint_id, is_primary=1 if is_primary else 0, created_at=now))
    if emit_outbox:
        _d8d_outbox(conn, aggregate_id=left_endpoint_id, event_type=EVENT_MEMORY_RELATION_CHANGED, payload={"user_id": user_id, "knowledge_id": left_endpoint_id, "relation_id": relation_id, "occurred_at": now})
    return {"id": int(res.lastrowid), "relation_id": relation_id}


def get_relation_by_id(conn, *, user_id: str, relation_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(select(memory_relation).where(and_(memory_relation.c.user_id == user_id, memory_relation.c.relation_id == relation_id))).mappings().first()
    return dict(row) if row else None


def list_relations(conn, *, user_id: str, knowledge_id: Optional[str] = None, relation_type: Optional[str] = None) -> List[Dict[str, Any]]:
    stmt = select(memory_relation).where(memory_relation.c.user_id == user_id)
    if knowledge_id is not None:
        stmt = stmt.where(((memory_relation.c.left_endpoint_type == "knowledge") & (memory_relation.c.left_endpoint_id == knowledge_id)) | ((memory_relation.c.right_endpoint_type == "knowledge") & (memory_relation.c.right_endpoint_id == knowledge_id)))
    if relation_type is not None:
        if relation_type not in _RELATION_TYPES:
            raise ValueError("invalid relation_type")
        stmt = stmt.where(memory_relation.c.relation_type == relation_type)
    return [dict(row) for row in conn.execute(stmt.order_by(memory_relation.c.created_at, memory_relation.c.relation_id)).mappings().all()]


def insert_conflict(
    conn, *, user_id: str, conflict_id: str, conflict_type: str, left_knowledge_id: str,
    right_knowledge_id: str, resolution_status: str, is_auto_resolvable: bool,
    detected_at: str, involved_knowledge_ids: Optional[List[str]] = None,
    resolution_strategy: Optional[str] = None, resolution_confidence: Optional[float] = None,
    resolved_at: Optional[str] = None, resolved_by: Optional[str] = None,
    decision_action: Optional[str] = None, winner_id: Optional[str] = None,
    reason_code: Optional[str] = None,
) -> Dict[str, Any]:
    _d8d_nonempty(user_id=user_id, conflict_id=conflict_id, conflict_type=conflict_type, left_knowledge_id=left_knowledge_id, right_knowledge_id=right_knowledge_id, resolution_status=resolution_status, detected_at=detected_at)
    if conflict_type not in _CONFLICT_TYPES or resolution_status not in _RESOLUTION_STATUSES or left_knowledge_id == right_knowledge_id:
        raise ValueError("invalid conflict")
    if resolution_confidence is not None and not 0 <= resolution_confidence <= 1:
        raise ValueError("invalid resolution_confidence")
    if resolution_status in {"resolved_auto", "resolved_manual"} and (not resolved_at or not resolved_by):
        raise ValueError("resolved conflict requires resolved_at and resolved_by")
    _validate_conflict_decision(
        decision_action=decision_action,
        winner_id=winner_id,
        left_knowledge_id=left_knowledge_id,
        right_knowledge_id=right_knowledge_id,
    )
    members = involved_knowledge_ids
    if members is not None and len(members) > 32:
        raise ValueError("at most 32 involved knowledge ids")
    all_ids = [left_knowledge_id, right_knowledge_id] + (members or [])
    if any(_knowledge_row(conn, user_id=user_id, knowledge_id=knowledge_id) is None for knowledge_id in all_ids):
        raise ValueError("conflict endpoint is not owned by user")
    now = _now_iso()
    # The Domain summary is intentionally discarded: persisted/returned form is an allowlisted system code.
    res = conn.execute(insert(memory_conflict).values(user_id=user_id, conflict_id=conflict_id, conflict_type=conflict_type, left_knowledge_id=left_knowledge_id, right_knowledge_id=right_knowledge_id, conflict_summary=f"conflict:{conflict_type}", involved_present=0 if members is None else 1, resolution_status=resolution_status, is_auto_resolvable=1 if is_auto_resolvable else 0, detected_at=detected_at, resolution_strategy=resolution_strategy, resolution_confidence=resolution_confidence, resolved_at=resolved_at, resolved_by=resolved_by, winner_id=winner_id, decision_action=decision_action, reason_code=reason_code, created_at=now, updated_at=now))
    for ordinal, (knowledge_id, role) in enumerate([(left_knowledge_id, "left"), (right_knowledge_id, "right")] + [(item, "involved") for item in members or []]):
        conn.execute(insert(memory_conflict_member).values(user_id=user_id, conflict_id=conflict_id, knowledge_id=knowledge_id, ordinal=ordinal, role=role, created_at=now))
    _d8d_outbox(conn, aggregate_id=conflict_id, event_type=EVENT_MEMORY_CONFLICT_CHANGED, payload={"user_id": user_id, "conflict_id": conflict_id, "occurred_at": now})
    return {"id": int(res.lastrowid), "conflict_id": conflict_id}


def get_conflict_by_id(conn, *, user_id: str, conflict_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(select(memory_conflict).where(and_(memory_conflict.c.user_id == user_id, memory_conflict.c.conflict_id == conflict_id))).mappings().first()
    return dict(row) if row else None


def _validate_conflict_decision(
    *, decision_action: Optional[str], winner_id: Optional[str],
    left_knowledge_id: str, right_knowledge_id: str,
) -> None:
    """Single Decision validator shared by insert/update (ADR-017 audit truth).

    ``winner_id`` may only appear for a keep decision and must name the side
    actually kept; coexist/defer/reject must not carry a winner.
    """
    if decision_action is None:
        if winner_id is not None:
            raise ValueError("only keep decisions may have a winner")
        return
    if decision_action not in _DECISION_ACTIONS:
        raise ValueError("invalid decision_action")
    if decision_action == "keep_left":
        if winner_id != left_knowledge_id:
            raise ValueError("winner_id must match keep side")
    elif decision_action == "keep_right":
        if winner_id != right_knowledge_id:
            raise ValueError("winner_id must match keep side")
    elif winner_id is not None:
        raise ValueError("only keep decisions may have a winner")


def list_conflicts_by_knowledge(conn, *, user_id: str, knowledge_id: str) -> List[Dict[str, Any]]:
    # Conflict truth membership is the member table: an involved-only participant
    # (neither left nor right) must surface in the same scoped conflict set.
    rows = conn.execute(
        select(memory_conflict).where(and_(
            memory_conflict.c.user_id == user_id,
            exists(
                select(1).where(and_(
                    memory_conflict_member.c.user_id == memory_conflict.c.user_id,
                    memory_conflict_member.c.conflict_id == memory_conflict.c.conflict_id,
                    memory_conflict_member.c.knowledge_id == knowledge_id,
                ))
            ),
        )).order_by(memory_conflict.c.detected_at, memory_conflict.c.conflict_id)
    ).mappings().all()
    return [dict(row) for row in rows]


def resolve_conflict_state(conn, *, user_id: str, knowledge_id: str) -> str:
    if _knowledge_row(conn, user_id=user_id, knowledge_id=knowledge_id, eligible_only=True) is None:
        return "none"
    unresolved = conn.execute(
        select(func.count()).select_from(memory_conflict).where(and_(
            memory_conflict.c.user_id == user_id,
            memory_conflict.c.resolution_status.not_in(["resolved_auto", "resolved_manual"]),
            exists(
                select(1).where(and_(
                    memory_conflict_member.c.user_id == memory_conflict.c.user_id,
                    memory_conflict_member.c.conflict_id == memory_conflict.c.conflict_id,
                    memory_conflict_member.c.knowledge_id == knowledge_id,
                ))
            ),
        ))
    ).scalar_one()
    return "unresolved" if unresolved else "resolved"


def update_conflict_resolution(conn, *, user_id: str, conflict_id: str, resolution_status: str, decision_action: Optional[str], winner_id: Optional[str], reason_code: Optional[str], resolved_at: Optional[str], resolved_by: Optional[str]) -> int:
    row = get_conflict_by_id(conn, user_id=user_id, conflict_id=conflict_id)
    if row is None:
        return 0
    if resolution_status not in _RESOLUTION_STATUSES:
        raise ValueError("invalid resolution_status")
    if resolution_status in {"resolved_auto", "resolved_manual"} and (not resolved_at or not resolved_by):
        raise ValueError("resolved conflict requires resolved_at and resolved_by")
    _validate_conflict_decision(
        decision_action=decision_action,
        winner_id=winner_id,
        left_knowledge_id=row["left_knowledge_id"],
        right_knowledge_id=row["right_knowledge_id"],
    )
    now = _now_iso()
    result = conn.execute(update(memory_conflict).where(and_(memory_conflict.c.user_id == user_id, memory_conflict.c.conflict_id == conflict_id)).values(resolution_status=resolution_status, decision_action=decision_action, winner_id=winner_id, reason_code=reason_code, resolved_at=resolved_at, resolved_by=resolved_by, updated_at=now))
    if result.rowcount:
        _d8d_outbox(conn, aggregate_id=conflict_id, event_type=EVENT_MEMORY_CONFLICT_CHANGED, payload={"user_id": user_id, "conflict_id": conflict_id, "occurred_at": now})
    return int(result.rowcount)


def get_lifecycle_memory(conn, *, user_id: str, knowledge_id: str) -> Optional[Dict[str, Any]]:
    return _knowledge_row(conn, user_id=user_id, knowledge_id=knowledge_id, eligible_only=True)


def update_lifecycle_memory(conn, *, user_id: str, knowledge_id: str, expected_row_revision: int, memory_status: Optional[str] = None, memory_type: Optional[str] = None) -> int:
    if memory_status is None and memory_type is None:
        raise ValueError("lifecycle mutation is empty")
    if memory_status is not None and memory_status not in _MEMORY_STATUSES:
        raise ValueError("invalid memory_status")
    if memory_type is not None and memory_type not in _MEMORY_TYPES:
        raise ValueError("invalid memory_type")
    row = get_lifecycle_memory(conn, user_id=user_id, knowledge_id=knowledge_id)
    if row is None or int(row["row_revision"]) != expected_row_revision:
        return 0
    if memory_status == "active" and row["memory_status"] in {"removed", "expired"}:
        raise ValueError("terminal lifecycle state cannot auto-recover")
    values: Dict[str, Any] = {"row_revision": expected_row_revision + 1, "updated_at": _now_iso()}
    if memory_status is not None:
        values["memory_status"] = memory_status
        if memory_status == "removed":
            values["is_deleted"] = 1
    if memory_type is not None:
        values["memory_type"] = memory_type
    result = conn.execute(update(memory_entries).where(and_(memory_entries.c.user_id == user_id, memory_entries.c.knowledge_id == knowledge_id, memory_entries.c.row_revision == expected_row_revision, memory_entries.c.version == row["version"])).values(**values))
    return int(result.rowcount)
