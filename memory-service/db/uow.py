"""uow.py — D4D Unit of Work（FR-DB-003：业务写 + Outbox 入队同一事务）

契约要点：
  - 业务写 + Outbox 入队同一事务提交（冻结文档 §3.3）
  - 幂等检查与响应缓存写入同事务（附录 A）
  - 写串行化：begin() 时获取进程级单写锁（FR-DB-004），commit/rollback 释放
  - SQLITE_BUSY（busy_timeout 到期）→ DatabaseLockedError，调用方降级
"""

from __future__ import annotations

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
        request_fingerprint: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], bool]:
        """幂等执行：查缓存 → 命中返回；未命中 → 同事务执行 + 写缓存。

        ADR-010：提供 request_fingerprint 时写缓存走 wrapper（_request_fingerprint），
        命中比对指纹，不一致 → IdempotencyConflictError（转 INVALID_REQUEST）。

        Returns:
            (response, from_cache)。

        Raises:
            IdempotencyConflictError: 相同三元组 + 不同请求指纹（ADR-010）。
            ConcurrentIdempotencyConflict: 并发双写冲突（回查缓存后返回首次结果）。
        """
        try:
            return repo.execute_idempotent(
                self.conn,
                user_id=user_id,
                session_id=session_id,
                idempotency_key=idempotency_key,
                business_fn=business_fn,
                request_fingerprint=request_fingerprint,
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
                return repo._unwrap_response(cached["response"], request_fingerprint), True
            raise
        except OperationalError as exc:
            if is_locked_error(exc):
                raise DatabaseLockedError("database is locked (busy_timeout)") from exc
            raise

    # ── 便捷业务组合（D4-D 骨架：turn 落库 + Outbox 同事务；ADR-010 Upsert） ──

    def save_turn_with_outbox(
        self,
        *,
        user_id: str,
        session_id: str,
        turn_index: Optional[int] = None,
        original_user_text: Optional[str] = None,
        model_request: Optional[str] = None,
        model_response: Optional[str] = None,
        is_end: int = 0,
        event_type: str = repo.EVENT_TURN_FINALIZED,
        extra_payload: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        host_turn_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Turn 落库 + Outbox 入队（同一事务提交；ADR-010 Upsert 语义）。

        Upsert 匹配键：(session_id, host_turn_id)（ADR-011 部分唯一索引）。
        - 不存在 → INSERT：turn_index 服务端计算（1+MAX，事件不携带）；
        - 存在 → UPDATE/refinalize：保持首次值（turn_index/original_user_text/
          created_at），仅更新 trace_id + is_end，Outbox 再次入队（refinalize:true）。

        Args:
            turn_index: INSERT 时提供则用给定值，否则服务端计算；UPDATE 忽略。
            original_user_text: INSERT 时必填（resolver 解析结果或直接给定）；
                UPDATE/refinalize 不调 resolver，保持首次值（ADR-010）。
            trace_id: IPC envelope 顶级 trace_id（唯一真源，ADR-010）。
            host_turn_id: 宿主字符串 ID（Upsert 匹配键，与 db_turn_id 区分）。

        Returns:
            dict 供幂等缓存/调用方使用：
            {conversation_id, turn_id, db_turn_id, host_turn_id, refinalize}。
        """
        conv_id = repo.upsert_conversation(self.conn, user_id=user_id, session_id=session_id)
        existing = None
        if host_turn_id is not None:
            existing = repo.find_turn_by_host(
                self.conn, session_id=session_id, host_turn_id=host_turn_id, user_id=user_id
            )

        refinalize = existing is not None
        if existing is None:
            # INSERT 路径：服务端计算 turn_index（ADR-010 唯一来源）
            if turn_index is None:
                turn_index = repo.next_turn_index(self.conn, session_id=session_id)
            if original_user_text is None:
                # 禁止编造正文/以空串替代：INSERT 必须提供正文（resolver 已解析）
                raise ValueError(
                    "original_user_text is required on INSERT (resolver result)"
                )
            turn_id = repo.insert_turn(
                self.conn,
                session_id=session_id,
                turn_index=turn_index,
                original_user_text=original_user_text,
                model_request=model_request,
                model_response=model_response,
                is_end=is_end,
                trace_id=trace_id,
                host_turn_id=host_turn_id,
            )
        else:
            # UPDATE/refinalize：保持首次值，仅更新 trace_id/is_end（不调 resolver）
            turn_id = int(existing["id"])
            repo.update_turn_refinalize(
                self.conn, turn_id=turn_id, trace_id=trace_id or "", is_end=is_end
            )

        payload = {
            "conversation_id": conv_id,
            "turn_id": turn_id,
            "is_end": is_end,
            **(extra_payload or {}),
        }
        if trace_id is not None:
            payload["trace_id"] = trace_id  # checklist 5.4：outbox payload 携带 trace_id
        if host_turn_id is not None:
            payload["host_turn_id"] = host_turn_id
            payload["refinalize"] = refinalize  # ADR-010：重投/refinalize 标记
        repo.enqueue_outbox(
            self.conn,
            aggregate_type="turn",
            aggregate_id=str(turn_id),
            event_type=event_type,
            payload=payload,
        )
        return {
            "conversation_id": conv_id,
            "turn_id": turn_id,
            "db_turn_id": turn_id,
            "host_turn_id": host_turn_id,
            "refinalize": refinalize,
        }
