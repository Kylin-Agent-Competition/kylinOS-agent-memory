"""repositories.py — D4D DAO 层（FRZ-DB-001/003/005、附录 A）

职责：
  - 5 张核心表的基础 CRUD（conversations/turns/memory_entries/outbox/idempotency_cache）
  - 幂等写入（附录 A 单一真相源）：查缓存 → 命中返回缓存；未命中 → 执行业务 +
    同事务写缓存；并发冲突（复合 PK 唯一约束）→ 回查返回首次缓存，不视为错误
  - SQLITE_BUSY（busy_timeout 到期）→ 抛 DatabaseLockedError，由调用方降级，
    不向聊天链路上抛（FR-DB-003）
  - 跨用户隔离：所有查询强制 user_id 过滤（Repository 层约束，[02 §16.6]）
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import Engine, and_, delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from db.engine import DatabaseLockedError, is_locked_error
from db.schema import (
    conversations,
    idempotency_cache,
    memory_entries,
    outbox,
    turns,
)

logger = logging.getLogger(__name__)

# 幂等 TTL（冻结 FRZ-IPC-005 / FRZ-DB-005）：24h
IDEMPOTENCY_TTL = timedelta(hours=24)

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
    """按 session_id upsert conversation，返回 id（幂等：重复调用返回已有 id）。"""
    started_at = started_at or _now_iso()
    existing = conn.execute(
        select(conversations.c.id).where(conversations.c.session_id == session_id)
    ).first()
    if existing is not None:
        return int(existing[0])
    res = conn.execute(
        insert(conversations)
        .values(user_id=user_id, session_id=session_id, started_at=started_at)
    )
    return int(res.lastrowid)


def get_conversation(conn, *, session_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        select(conversations).where(conversations.c.session_id == session_id)
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
) -> int:
    """插入 turn，返回 id。original_user_text 保存用户原文（隔离语义）。"""
    res = conn.execute(
        insert(turns).values(
            session_id=session_id,
            turn_index=turn_index,
            original_user_text=original_user_text,
            model_request=model_request,
            model_response=model_response,
            is_end=is_end,
            created_at=created_at or _now_iso(),
        )
    )
    return int(res.lastrowid)


def get_turn(conn, *, turn_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        select(turns).where(turns.c.id == turn_id)
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
) -> int:
    """插入 memory_entry（content 序列化为 JSON 文本），返回 id。"""
    now = _now_iso()
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
        )
    )
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
    conn.execute(delete(outbox).where(outbox.c.id == outbox_id))


def mark_outbox_failure(
    conn, *, outbox_id: int, attempts: int, next_retry_at: str, last_error: str
) -> None:
    """处理失败：attempts++ / 退避 / last_error（附录 B 步骤 4b）。"""
    conn.execute(
        update(outbox)
        .where(outbox.c.id == outbox_id)
        .values(attempts=attempts, next_retry_at=next_retry_at, last_error=last_error)
    )


def mark_outbox_dead_letter(conn, *, outbox_id: int, attempts: int, last_error: str) -> None:
    """Dead Letter：保留记录，attempts 记录最终次数，next_retry_at=NULL，不丢事件（附录 B 4c）。"""
    conn.execute(
        update(outbox)
        .where(outbox.c.id == outbox_id)
        .values(attempts=attempts, next_retry_at=None, last_error=last_error)
    )


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
    conn.execute(
        delete(idempotency_cache).where(
            and_(
                idempotency_cache.c.user_id == user_id,
                idempotency_cache.c.session_id == session_id,
                idempotency_cache.c.idempotency_key == idempotency_key,
            )
        )
    )


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


# ── 幂等执行（附录 A：检查 → 执行 → 缓存，同事务） ──


def execute_idempotent(
    conn,
    *,
    user_id: str,
    session_id: str,
    idempotency_key: str,
    business_fn,
) -> Tuple[Dict[str, Any], bool]:
    """幂等执行器（附录 A 单一真相源）。

    Args:
        business_fn: 无参可调用，返回 (response_dict)；副作用（SQLite+Outbox）必须
            在传入的同一 conn 事务中执行，保证与缓存写入同事务。

    Returns:
        (response, from_cache)：from_cache=True 表示命中缓存未执行副作用。

    Raises:
        IntegrityError: 并发未命中双写冲突（UoW 捕获后回查，不视为错误）。
    """
    cached = get_idempotency_cache(
        conn, user_id=user_id, session_id=session_id, idempotency_key=idempotency_key
    )
    if cached is not None:
        if cached["expires_at"] > datetime.now(timezone.utc).isoformat():
            return json.loads(cached["response"]), True
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
        response=response,
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
