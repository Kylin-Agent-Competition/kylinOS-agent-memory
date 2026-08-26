"""uow.py — D4D Unit of Work（FR-DB-003：业务写 + Outbox 入队同一事务）

契约要点：
  - 业务写 + Outbox 入队同一事务提交（冻结文档 §3.3）
  - 幂等检查与响应缓存写入同事务（附录 A）
  - 写串行化：begin() 时获取进程级单写锁（FR-DB-004），commit/rollback 释放
  - SQLITE_BUSY（busy_timeout 到期）→ DatabaseLockedError，调用方降级
"""

from __future__ import annotations

import json
import logging
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError, OperationalError

from db import repositories as repo
from db.engine import DatabaseLockedError, get_write_lock, is_locked_error

logger = logging.getLogger(__name__)


class UnitOfWork(AbstractContextManager["UnitOfWork"]):
    """SQLite 单事务工作单元（单写锁保护，业务写 + Outbox 同事务）。"""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._conn = None
        self._lock = get_write_lock()

    # ── 上下文管理 ──

    def __enter__(self) -> "UnitOfWork":
        self._lock.acquire()
        try:
            self._conn = self._engine.connect()
            self._tx = self._conn.begin()
        except Exception:
            self._lock.release()
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        try:
            if exc_type is None:
                self._tx.commit()
            else:
                try:
                    self._tx.rollback()
                except Exception:  # noqa: BLE001
                    logger.warning("rollback 失败（连接可能已失效）")
            return False  # 异常继续上抛（由调用方决定降级）
        finally:
            try:
                self._conn.close()
            finally:
                self._lock.release()

    @property
    def conn(self):
        """当前事务连接（DAO 函数首参）。"""
        if self._conn is None:
            raise RuntimeError("UoW 未进入事务上下文")
        return self._conn

    # ── 高层操作（幂等写入，附录 A） ──

    def execute_idempotent(
        self,
        *,
        user_id: str,
        session_id: str,
        idempotency_key: str,
        business_fn: Callable[[], Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], bool]:
        """幂等执行：查缓存 → 命中返回；未命中 → 同事务执行 + 写缓存。

        Returns:
            (response, from_cache)。

        Raises:
            ConcurrentIdempotencyConflict: 并发双写冲突（回查缓存后返回首次结果）。
        """
        try:
            return repo.execute_idempotent(
                self.conn,
                user_id=user_id,
                session_id=session_id,
                idempotency_key=idempotency_key,
                business_fn=business_fn,
            )
        except IntegrityError:
            # 并发未命中双写：复合 PK 唯一约束兜底 → 回查首次缓存，不视为错误（附录 A）
            logger.info("幂等并发冲突（复合 PK 兜底），回查缓存返回首次结果")
            cached = repo.get_idempotency_cache(
                self.conn,
                user_id=user_id,
                session_id=session_id,
                idempotency_key=idempotency_key,
            )
            if cached is not None and cached["expires_at"] > datetime.now(timezone.utc).isoformat():
                return json.loads(cached["response"]), True
            raise
        except OperationalError as exc:
            if is_locked_error(exc):
                raise DatabaseLockedError("database is locked (busy_timeout)") from exc
            raise

    # ── 便捷业务组合（D4-D 骨架：turn 落库 + Outbox 同事务） ──

    def save_turn_with_outbox(
        self,
        *,
        user_id: str,
        session_id: str,
        turn_index: int,
        original_user_text: str,
        model_request: Optional[str] = None,
        model_response: Optional[str] = None,
        is_end: int = 0,
        event_type: str = repo.EVENT_TURN_FINALIZED,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Turn 落库 + Outbox 入队（同一事务提交）。

        返回 dict 供幂等缓存/调用方使用：{conversation_id, turn_id}。
        """
        conv_id = repo.upsert_conversation(self.conn, user_id=user_id, session_id=session_id)
        turn_id = repo.insert_turn(
            self.conn,
            session_id=session_id,
            turn_index=turn_index,
            original_user_text=original_user_text,
            model_request=model_request,
            model_response=model_response,
            is_end=is_end,
        )
        payload = {
            "conversation_id": conv_id,
            "turn_id": turn_id,
            "is_end": is_end,
            **(extra_payload or {}),
        }
        repo.enqueue_outbox(
            self.conn,
            aggregate_type="turn",
            aggregate_id=str(turn_id),
            event_type=event_type,
            payload=payload,
        )
        return {"conversation_id": conv_id, "turn_id": turn_id}
