"""Alembic 迁移环境（D4D）。

数据库 URL 动态来源（优先级）：
  1. 环境变量 KYLIN_MEMORY_DB
  2. 默认 ~/.local/share/kylin-memory/kylin_memory.db
target_metadata 引用 db.schema.metadata（单一真相，与 001_initial_schema.py 一致）。
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

# 让 `import db.schema` 可解析（仓库根下 memory-service/ 是 Python 包根）
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "memory-service"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.schema import metadata  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def _db_url() -> str:
    """确定 SQLite URL：环境变量 > 默认路径。"""
    db_path = os.environ.get("KYLIN_MEMORY_DB")
    if not db_path:
        db_path = str(Path("~/.local/share/kylin-memory/kylin_memory.db").expanduser())
    return f"sqlite:///{db_path}"


def run_migrations_offline() -> None:
    """离线模式（只生成 SQL，不连库）。"""
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=False,  # 冻结：禁止 autogenerate 默认 batch
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式（连接 SQLite 执行迁移）。"""
    engine = create_engine(_db_url())

    # WAL + busy_timeout（R-8 语义：busy_timeout 到期降级，不无限阻塞）
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=False,  # 冻结：禁止 autogenerate 默认 batch
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
