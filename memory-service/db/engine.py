"""engine.py — D4D SQLite 连接管理（FRZ-DB-003）

契约要点：
  - WAL 模式 / busy_timeout / 单写多读（R-8：数值由 D4-D 定，语义边界冻结）
  - 写串行化：进程内单写锁（业务线程与 Outbox Worker 共用），避免 SQLITE_BUSY
  - busy_timeout 到期 → SQLITE_BUSY（SQLAlchemy OperationalError: database is locked）
    → DAO 层必须捕获并转换为 L1/L2 降级（空上下文 + 日志），不得上抛阻塞聊天
  - 业务写 + Outbox 入队同一事务（UoW 层实现，见 uow.py）
"""

from __future__ import annotations

import logging
import os
import threading

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import OperationalError

from db.schema import FTS_TRIGGERS_DDL, FTS5_DDL, VERSION_TRIGGERS_DDL, metadata

logger = logging.getLogger(__name__)

# R-8 实现数值（语义边界冻结，数值不冻结）：
_BUSY_TIMEOUT_MS = 5000  # 5s：到期触发降级，不得无限阻塞
_WAL_MODE = "WAL"
_FOREIGN_KEYS = "ON"


class DatabaseLockedError(Exception):
    """SQLite busy_timeout 到期（SQLITE_BUSY）。

    DAO/UoW 捕获后转换为 L1/L2 降级：返回空上下文 + 日志，不向聊天链路上抛。
    """


class WriteLock:
    """进程内单写锁（单写者模型，FR-DB-004）。

    所有 SQLite 写操作（业务线程 + Worker）必须经本锁串行化；
    读操作可并行（WAL 快照读）。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def acquire(self) -> None:
        self._lock.acquire()

    def release(self) -> None:
        self._lock.release()

    def __enter__(self) -> "WriteLock":
        self._lock.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self._lock.release()


# 进程级单例写锁（业务与 Worker 共用，避免多写者触发 BUSY）
_write_lock = WriteLock()


def get_write_lock() -> WriteLock:
    """获取进程级单写锁。"""
    return _write_lock


def _restrict_db_file_permissions(db_path: str) -> None:
    """显式收紧 DB 文件权限为 0600（D6-D L2 权限契约，MEDIUM-02）。

    SQLite 以默认 umask 创建文件（通常 0644）；DB 含敏感用户数据，需在
    创建/初始化后显式收紧为仅属主可读写。`-wal`/`-shm` 伴随文件随连接
    生命周期动态重建，不强制收紧（以 DB 主文件为准）。

    `chmod` 失败仅 warning 不阻断启动——避免只读文件系统/无权限环境崩溃，
    权限问题由部署/权限检查兜底发现。
    """
    try:
        os.chmod(db_path, 0o600)
    except OSError as exc:
        logger.warning("收紧 DB 文件权限 0600 失败（不阻断启动）: %s (%s)", db_path, exc)


def create_db_engine(db_path: str, *, busy_timeout_ms: int = _BUSY_TIMEOUT_MS) -> Engine:
    """创建 SQLite 引擎并应用 PRAGMA（WAL / busy_timeout / foreign_keys）。

    Args:
        db_path: SQLite 文件路径（配置 database.path，父目录已确保可创建）。
        busy_timeout_ms: busy_timeout 毫秒（R-8 语义：到期必须降级）。

    Returns:
        SQLAlchemy Engine（check_same_thread=False：Worker 线程与业务线程共用连接池）。
    """
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": busy_timeout_ms / 1000.0},
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute(f"PRAGMA journal_mode={_WAL_MODE}")
        cur.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        cur.execute(f"PRAGMA foreign_keys={_FOREIGN_KEYS}")
        cur.close()
        # D6-D MEDIUM-02：每次连接建立后 DB 文件已存在，显式收紧 0600
        # （SQLite 惰性建文件，chmod 必须待文件创建后执行；幂等，失败仅 warning）
        _restrict_db_file_permissions(db_path)

    # 既有文件路径也立即收紧（幂等；若文件尚未创建则仅 warning，由 connect 事件补）
    _restrict_db_file_permissions(db_path)

    return engine


def is_locked_error(exc: BaseException) -> bool:
    """判断异常是否为 SQLITE_BUSY（busy_timeout 到期）。"""
    if isinstance(exc, DatabaseLockedError):
        return True
    if isinstance(exc, OperationalError) and "database is locked" in str(exc):
        return True
    return False


def init_schema(engine: Engine, *, fts: bool = True) -> None:
    """建表 + FTS5 + 触发器（测试/开发快速建库；生产走 Alembic 迁移）。"""
    metadata.create_all(engine)
    with engine.begin() as conn:
        for trigger_ddl in VERSION_TRIGGERS_DDL:
            conn.exec_driver_sql(trigger_ddl)
        if not fts:
            return
        exists = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_fts'"
        ).first()
        if not exists:
            conn.exec_driver_sql(FTS5_DDL)
        for trigger_ddl in FTS_TRIGGERS_DDL:
            conn.exec_driver_sql(trigger_ddl)


def has_alembic_version(engine: Engine) -> bool:
    """判断 `alembic_version` 表是否存在（生产迁移已执行的证据，FR-DB-002）。

    `init_schema()`（create_all）不会创建该表；只有 `alembic upgrade head`
    才会写入它。生产模式（`--no-migrate`）启动时用它校验唯一迁移入口已生效，
    消除 create_all 与 Alembic 双 schema truth source 分叉（PR#52 Issue 6）。
    """
    with engine.connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).first()
    return row is not None


def db_health_check(engine: Engine) -> bool:
    """health handler 用：真实可达性探测（SELECT 1），失败返回 False。"""
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("db health check failed: %s", exc)
        return False
