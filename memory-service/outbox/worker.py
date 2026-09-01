"""worker.py — D4D Outbox Worker 骨架（FR-DB-004 / 附录 B 单一真相源）

行为（附录 B）：
  1. 独立线程，每 outbox.poll_interval_s 秒轮询
  2. 取 next_retry_at <= now AND attempts <= max_retries，按 next_retry_at 排序
  3. 逐条处理：
     4a. 成功 → Outbox DELETE
     4b. 失败 → attempts+1、next_retry_at = now + 2^attempts * 30s（指数退避）、last_error
     4c. attempts > max_retries → Dead Letter（保留记录，next_retry_at=NULL，ERROR 日志）
  4. 每轮顺带清理过期幂等缓存（DELETE ... LIMIT 100，借 idx_idempotency_expires）
  5. 写串行化：所有写经进程内单写锁（业务线程与 Worker 共用）

Vector/Embedding 消费（附录 C）待 D4-D 技术确认（R-9）：本任务以注入点表达——
  process_event(payload) 回调未注册时按失败处理（真实结果：无法消费 → 退避/进 DL），
  不假装成功；接线后替换为真实 Embedding → Vector INSERT。
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from db import repositories as repo
from db.engine import DatabaseLockedError, get_write_lock, is_locked_error
from observability.json_logging import sanitize_message
from observability.request_context import clear_request_context, set_request_context

logger = logging.getLogger(__name__)

# 退避基数（附录 B：next_retry_at = now + 2^attempts * 30s）
RETRY_BASE_SECONDS = 30

# 消费回调类型：payload dict → 成功返回 None，失败抛异常
EventConsumer = Callable[[Dict[str, Any]], None]

# SQLite "no such table" 属于持久性 schema 错误：表缺失不会随重试恢复，
# Worker 对其无限重试会形成死循环。识别后应停止线程而非继续轮询。
_SCHEMA_MISSING_MARKERS = (
    "no such table",
    "no such column",
)


def _is_schema_missing(exc: BaseException) -> bool:
    """判定异常是否为持久性 schema 缺失（表/列不存在）。

    这类错误不会因重试而恢复（非 transient），Worker 应 fail-fast 停止，
    而非对 `no such table` 无限重试（死循环）。
    """
    msg = str(exc).lower()
    return any(marker in msg for marker in _SCHEMA_MISSING_MARKERS)


class OutboxWorker:
    """Outbox Worker（独立线程，单写锁串行化，不引入额外消息队列）。"""

    def __init__(
        self,
        engine: Engine,
        *,
        poll_interval_s: int = 1,
        max_retries: int = 3,
        consumer: Optional[EventConsumer] = None,
    ) -> None:
        self._engine = engine
        self._poll_interval_s = poll_interval_s
        self._max_retries = max_retries
        self._consumer = consumer  # Vector 接入（R-9）前保持 None（见模块 docstring）
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = get_write_lock()
        self._processed = 0
        self._dead_letters = 0
        self._fatal_error: Optional[str] = None  # 持久性 schema 缺失等致命错误（防死循环）

    # ── 生命周期 ──

    def start(self) -> None:
        """启动 Worker 线程（幂等：已启动则忽略）。"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="outbox-worker", daemon=True
        )
        self._thread.start()
        logger.info("Outbox Worker 启动（poll=%ss, max_retries=%d）", self._poll_interval_s, self._max_retries)

    def stop(self, *, join_timeout: float = 5.0) -> None:
        """停止 Worker（等待当前轮询结束）。"""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=join_timeout)
        logger.info("Outbox Worker 停止（processed=%d, dead_letters=%d）", self._processed, self._dead_letters)

    def metrics(self) -> Dict[str, Any]:
        """诊断指标（FR-FB-003：backlog / oldest_pending_age / index_sync_lag）。"""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with self._engine.connect() as conn:
                backlog = repo.outbox_backlog(conn, now_iso=now_iso)
        except OperationalError as exc:
            if is_locked_error(exc):
                logger.warning("metrics busy 降级")
            backlog = {"backlog": -1, "dead_letter": -1, "oldest_pending_created_at": None}
        return {**backlog, "processed": self._processed, "dead_letters": self._dead_letters,
                "fatal_error": self._fatal_error}

    # ── 内部实现 ──

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._poll_once()
            except DatabaseLockedError:
                logger.warning("Worker 轮询遇 SQLITE_BUSY（busy_timeout 到期），跳过本轮")
            except Exception as exc:  # noqa: BLE001
                if _is_schema_missing(exc):
                    # 持久性 schema 缺失：重试不会恢复 → 停止线程防死循环
                    self._fatal_error = f"schema missing: {exc}"
                    logger.error(
                        "Worker 轮询致命错误（schema 缺失，停止线程防死循环）: %s", exc
                    )
                    self._stop.set()
                    break
                logger.error("Worker 轮询异常: %s", exc)
            self._stop.wait(self._poll_interval_s)

    def _poll_once(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:  # 单写锁：与业务线程写串行化（FR-DB-004）
            with self._engine.begin() as conn:
                # 顺带：过期幂等缓存清理（LIMIT 100，附录 B 步骤 4 附注）
                cleaned = repo.cleanup_expired_idempotency(conn, now_iso=now_iso)
                if cleaned:
                    logger.info("幂等缓存过期清理 %d 行", cleaned)

                pending = repo.claim_pending_outbox(
                    conn, now_iso=now_iso, max_retries=self._max_retries
                )
                for event in pending:
                    self._process_event(conn, event, now_iso)

    def _process_event(self, conn, event: Dict[str, Any], now_iso: str) -> None:
        event_id = int(event["id"])
        aggregate_id = event["aggregate_id"]
        event_type = event["event_type"]
        attempts = int(event["attempts"])

        # M4：解析 payload 取 trace_id/event_id，建立 Worker 线程请求上下文，
        # 使成功/重试/DL 日志携带二者（跨线程与 Gateway/DAO 关联）
        payload: Any = event["payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception as exc:  # noqa: BLE001 payload 损坏按失败处理
                self._fail(
                    conn,
                    event_id=event_id,
                    attempts=attempts,
                    now_iso=now_iso,
                    last_error=f"invalid payload json: {exc}"[:500],
                )
                return
        payload_trace_id = ""
        payload_event_id = ""
        if isinstance(payload, dict):
            payload_trace_id = str(payload.get("trace_id", ""))
            payload_event_id = str(payload.get("event_id", ""))

        set_request_context(
            request_id="",
            trace_id=payload_trace_id,
            method=f"outbox:{event_type}",
            event_id=payload_event_id,
        )
        try:
            if self._consumer is None:
                # Vector 接入未确认（R-9）：无法消费 → 按失败处理（真实结果，不假装成功）
                self._fail(
                    conn,
                    event_id=event_id,
                    attempts=attempts,
                    now_iso=now_iso,
                    last_error="no consumer registered (vector integration pending, R-9)",
                )
                return
            self._consumer(payload)

            # 成功（附录 B 4a）
            repo.mark_outbox_success(conn, outbox_id=event_id)
            self._processed += 1
            logger.info(
                "Outbox 事件完成 id=%d type=%s agg=%s", event_id, event_type, aggregate_id
            )
        except Exception as exc:  # noqa: BLE001
            self._fail(
                conn,
                event_id=event_id,
                attempts=attempts,
                now_iso=now_iso,
                last_error=f"{type(exc).__name__}: {exc}"[:500],  # 错误摘要，不含 PII
            )
            return
        finally:
            # M4：无论成功/失败/早退都清理线程上下文（防泄漏/串号）
            clear_request_context()

    def _fail(self, conn, *, event_id: int, attempts: int, now_iso: str, last_error: str) -> None:
        # M4.5：last_error 统一经 sanitize_message 脱敏后存库/写日志，
        # 防止异常参数携带外部引用原文（source_reference）泄漏进 outbox.last_error/日志
        last_error = sanitize_message(last_error)
        new_attempts = attempts + 1
        if new_attempts > self._max_retries:
            # Dead Letter（附录 B 4c）：保留记录，next_retry_at=NULL，ERROR 日志
            repo.mark_outbox_dead_letter(conn, outbox_id=event_id, attempts=new_attempts, last_error=last_error)
            self._dead_letters += 1
            logger.error(
                "Outbox Dead Letter id=%d attempts=%d last_error=%s",
                event_id, new_attempts, last_error,
            )
            return
        # 退避（附录 B 4b）
        next_retry = datetime.now(timezone.utc) + timedelta(
            seconds=RETRY_BASE_SECONDS * (2 ** new_attempts)
        )
        repo.mark_outbox_failure(
            conn,
            outbox_id=event_id,
            attempts=new_attempts,
            next_retry_at=next_retry.isoformat(),
            last_error=last_error,
        )
        logger.warning(
            "Outbox 重试 id=%d attempts=%d next_retry_at=%s",
            event_id, new_attempts, next_retry.isoformat(),
        )
