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
import secrets
import uuid
from contextlib import AbstractContextManager
from datetime import datetime, timedelta, timezone
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
        response_for_cache_fn: Optional[
            Callable[[Dict[str, Any]], Dict[str, Any]]
        ] = None,
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
                response_for_cache_fn=response_for_cache_fn,
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

    # ── D10D 精准遗忘（ADR-015/019：preview/execute 单事务封装） ──

    @staticmethod
    def _assert_execute_supported(plan: Dict[str, Any]) -> None:
        """Execute 前 fail-closed 门禁（契约 §四.4~§四.6；红线 §四）。

        delete_mode=hard / is_cascade=true / topic / time_window / full_reset /
        target_type in (event, all) → Runtime 未闭环，一律拒绝（不自动降级软删后报成功）。
        """
        if plan["delete_mode"] == repo.DELETE_MODE_HARD:
            raise repo.UnsupportedForgetScopeError(
                "hard delete runtime not implemented (fail-closed)"
            )
        if int(plan["is_cascade"]) == 1:
            raise repo.UnsupportedForgetScopeError(
                "cascade runtime not implemented (fail-closed)"
            )
        if plan["forget_mode"] in ("topic", "time_window", "full_reset"):
            raise repo.UnsupportedForgetScopeError(
                f"forget_mode={plan['forget_mode']} runtime fail-closed"
            )
        if plan["target_type"] in ("event", "all"):
            raise repo.UnsupportedForgetScopeError(
                f"target_type={plan['target_type']} runtime fail-closed"
            )

    def preview_forget_plan(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        request_fingerprint: str,
        forget_plan_id: str,
        forget_mode: str,
        target_selector: str,
        target_type: str,
        target_id: Optional[str],
        target_session_id: Optional[str],
        target_topic: Optional[str],
        target_time_range: Optional[str],
        requires_confirmation: bool,
        is_cascade: bool,
        delete_mode: str,
    ) -> Tuple[Dict[str, Any], bool]:
        """forget.preview 单事务：解析 → 落计划 → 凭据哈希 → 清 selector → 缓存响应。

        ADR-019 §4.9：确定性解析（不支持作用域 fail-closed）→ execute_idempotent
        单事务（insert pending → update awaiting_confirmation + token hash + 清 selector）。
        确认凭据明文只在响应中回传一次（D4 决策），服务端只存 SHA-256。
        """
        from service.forgetting import resolve_forget_targets

        def _business() -> Dict[str, Any]:
            resolved = resolve_forget_targets(
                self.conn,
                user_id=user_id,
                forget_mode=forget_mode,
                target_type=target_type,
                target_id=target_id,
                target_session_id=target_session_id,
            )
            affected_count = len(resolved)
            selection_hash = repo.compute_selection_hash(resolved)
            token_plaintext = secrets.token_hex(32)  # 32B 一次性凭据
            token_hash = repo.hash_confirmation_token(token_plaintext)
            token_expires_at = (
                datetime.now(timezone.utc)
                + timedelta(seconds=repo.CONFIRMATION_TOKEN_TTL_SECONDS)
            ).isoformat()

            repo.insert_forget_plan(
                self.conn,
                user_id=user_id,
                forget_plan_id=forget_plan_id,
                forget_mode=forget_mode,
                target_selector=target_selector,
                target_type=target_type,
                target_id=target_id,
                target_session_id=target_session_id,
                target_topic=target_topic,
                target_time_range=target_time_range,
                requires_confirmation=requires_confirmation,
                is_cascade=is_cascade,
                delete_mode=delete_mode,
            )
            repo.update_forget_plan_preview(
                self.conn,
                user_id=user_id,
                forget_plan_id=forget_plan_id,
                resolved_target_ids=resolved,
                affected_count=affected_count,
                selection_hash=selection_hash,
                confirmation_token_hash=token_hash,
                token_expires_at=token_expires_at,
            )
            return {
                "forget_plan_id": forget_plan_id,
                "status": "awaiting_confirmation",
                "resolved_target_ids": resolved,
                "affected_count": affected_count,
                "selection_hash": selection_hash,
                "confirmation_token": token_plaintext,
                "credential_ttl_seconds": repo.CONFIRMATION_TOKEN_TTL_SECONDS,
                # credential_ref = 凭据 SHA-256 哈希前缀（非敏感引用，ADR-019 §4.3
                # 冻结字段；仅供调用方自检，不得作为 execute 凭据使用）。
                "credential_ref": token_hash[:16],
                "requires_confirmation": requires_confirmation,
                "is_cascade": is_cascade,
                "delete_mode": delete_mode,
            }

        def _without_confirmation_token(response: Dict[str, Any]) -> Dict[str, Any]:
            safe_response = dict(response)
            safe_response.pop("confirmation_token", None)
            safe_response["credential_replayable"] = False
            return safe_response

        response, from_cache = self.execute_idempotent(
            user_id=user_id,
            session_id="",
            idempotency_key=idempotency_key,
            business_fn=_business,
            request_fingerprint=request_fingerprint,
            response_for_cache_fn=_without_confirmation_token,
        )
        if from_cache:
            raise repo.ConfirmationCredentialError(
                "confirmation credential is only returned once"
            )
        return response, False

    def execute_forget_plan(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        request_fingerprint: str,
        forget_plan_id: str,
        confirmation_token: str,
        trace_id: str,
    ) -> Tuple[Dict[str, Any], bool]:
        """forget.execute 单事务：凭据校验/消费 → 软删 dispatcher → 审计 → 终态 + Outbox。

        MEDIUM-03：executed_count != affected_count 不得进入 completed（漏删不得报完成）。
        forget.executed 以 priority=1 入队（ADR-015 删除类高优先级）。
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        def _business() -> Dict[str, Any]:
            plan = repo.get_forget_plan_by_id(
                self.conn, user_id=user_id, forget_plan_id=forget_plan_id
            )
            if plan is None:
                raise repo.ConfirmationCredentialError(
                    "forget plan not found or not owned by user"
                )
            # fail-closed 门禁（先于凭据消费；异常 → 事务整体回滚，零副作用）
            self._assert_execute_supported(plan)
            # 凭据校验（绑定/过期/未消费）+ 消费（置 NULL + status→executing）
            repo.consume_confirmation_token(
                self.conn,
                user_id=user_id,
                forget_plan_id=forget_plan_id,
                confirmation_token_plaintext=confirmation_token,
                now_iso=now_iso,
            )

            target_type = plan["target_type"]
            resolved_target_ids = json.loads(plan["resolved_target_ids"] or "[]")
            affected_count = int(plan["affected_count"] or 0)

            executed_count, version_ids = repo.soft_delete_resolved_targets(
                self.conn,
                user_id=user_id,
                target_type=target_type,
                resolved_target_ids=resolved_target_ids,
                forget_plan_id=forget_plan_id,
            )

            executed_at = datetime.now(timezone.utc).isoformat()
            terminal_status = "completed" if executed_count == affected_count else "failed"
            repo.update_forget_plan_terminal(
                self.conn,
                user_id=user_id,
                forget_plan_id=forget_plan_id,
                status=terminal_status,
                executed_count=executed_count,
                executed_at=executed_at,
                affected_count=affected_count,
            )

            audit_id = f"fa_{uuid.uuid4().hex}"
            repo.insert_forget_audit(
                self.conn,
                audit_id=audit_id,
                forget_plan_id=forget_plan_id,
                user_id=user_id,
                forget_mode=plan["forget_mode"],
                target_type=target_type,
                delete_mode=plan["delete_mode"],
                is_cascade=bool(plan["is_cascade"]),
                affected_count=affected_count,
                selection_hash=plan["selection_hash"],
                confirmation_ref=repo._sha256(
                    f"conf:{forget_plan_id}:{executed_at}"
                )[:16],
                status=terminal_status,
                result_code=terminal_status,
                trace_id=trace_id,
                sensitivity_max=None,
                executed_at=executed_at,
            )

            repo.enqueue_outbox(
                self.conn,
                aggregate_type="forget",
                aggregate_id=forget_plan_id,
                event_type=repo.EVENT_FORGET_EXECUTED,
                payload={
                    "event_id": audit_id,
                    "user_id": user_id,
                    "forget_plan_id": forget_plan_id,
                    "target_type": target_type,
                    "forget_mode": plan["forget_mode"],
                    "resolved_target_ids": resolved_target_ids,
                    "version_ids": version_ids,
                    "selection_hash": plan["selection_hash"],
                    "confirmation_ref": repo._sha256(
                        f"conf:{forget_plan_id}:{executed_at}"
                    )[:16],
                    "trace_id": trace_id,
                },
                priority=repo.FORGET_PRIORITY,
            )

            return {
                "forget_plan_id": forget_plan_id,
                "status": terminal_status,
                "affected_count": affected_count,
                "executed_count": executed_count,
                "delete_mode": plan["delete_mode"],
                "has_vector_cleanup": False,  # TD-033：仅标记，不实现清理
                "executed_at": executed_at,
                "audit_id": audit_id,
            }

        return self.execute_idempotent(
            user_id=user_id,
            session_id="",
            idempotency_key=idempotency_key,
            business_fn=_business,
            request_fingerprint=request_fingerprint,
        )
