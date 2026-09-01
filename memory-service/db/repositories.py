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

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from db.engine import DatabaseLockedError, is_locked_error
from db.schema import (
    conversations,
    idempotency_cache,
    memory_entries,
    memory_items,
    memory_version_receipts,
    memory_versions,
    outbox,
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

# outbox 事件类型（业务入队用）
EVENT_TURN_FINALIZED = "turn.finalized"
EVENT_MEMORY_UPSERTED = "memory.upserted"
EVENT_FORGET_EXECUTED = "forget.executed"


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
) -> int:
    """插入 memory_entry（content 序列化为 JSON 文本），返回 id。

    ADR-011：trace_id nullable 列透传（IPC envelope 唯一真源）。
    """
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
                is_deleted=0,
                created_at=now,
                updated_at=now,
                trace_id=trace_id,
            )
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return int(res.lastrowid)


def soft_delete_memory_entry(
    conn, *, entry_id: int, user_id: str, current_version: int
) -> int:
    """乐观锁软删除：is_deleted 0→1 + version+1（FTS 由触发器同步删除）。

    Returns:
        受影响行数；0 = 版本冲突（调用方重试或放弃，FRZ-DB-001 乐观锁规范）。
    """
    try:
        res = conn.execute(
            update(memory_entries)
            .where(
                and_(
                    memory_entries.c.id == entry_id,
                    memory_entries.c.user_id == user_id,
                    memory_entries.c.version == current_version,
                    memory_entries.c.is_deleted == 0,
                )
            )
            .values(is_deleted=1, version=current_version + 1, updated_at=_now_iso())
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
) -> int:
    """Outbox 入队（必须在业务写同一事务内调用，UoW 保证原子性）。"""
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
            )
        )
    except OperationalError as exc:
        raise _wrap_locked(exc) from exc
    return int(res.lastrowid)


def claim_pending_outbox(conn, *, now_iso: str, max_retries: int, limit: int = 100) -> List[Dict[str, Any]]:
    """Worker 轮询：取 next_retry_at <= now 且 attempts <= max_retries 的事件。"""
    try:
        rows = conn.execute(
            select(outbox)
            .where(
                and_(
                    outbox.c.next_retry_at <= now_iso,
                    outbox.c.attempts <= max_retries,
                )
            )
            .order_by(outbox.c.next_retry_at)
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

    SQLite 支持 DELETE ... LIMIT，但 SQLAlchemy 2.0 通用 Delete 无 .limit()
    （MySQL 方言专有），故用原生 SQL 表达（冻结文档附录 B 附注）。
    """
    try:
        res = conn.exec_driver_sql(
            "DELETE FROM idempotency_cache WHERE expires_at < ? LIMIT ?",
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
) -> Tuple[Dict[str, Any], bool]:
    """幂等执行器（附录 A 单一真相源 + ADR-010 请求指纹）。

    Args:
        business_fn: 无参可调用，返回 (response_dict)；副作用（SQLite+Outbox）必须
            在传入的同一 conn 事务中执行，保证与缓存写入同事务。
        request_fingerprint: ADR-010 `_request_fingerprint`（sha256 规范化
            method+业务语义字段）。提供时写缓存走 wrapper；命中时比对指纹，
            不一致抛 IdempotencyConflictError（转 INVALID_REQUEST）。

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
    write_idempotency_cache(
        conn,
        user_id=user_id,
        session_id=session_id,
        idempotency_key=idempotency_key,
        response=_wrap_response(response, request_fingerprint),
    )
    return response, False


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
