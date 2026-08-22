"""D4D 迁移测试：FR-DB-002 / ADR-007（upgrade head → .schema 断言 → downgrade base）"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "migrations"


def _run_alembic(db_path: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["KYLIN_MEMORY_DB"] = str(db_path)
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(MIGRATIONS_DIR / "alembic.ini"), *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "migrate.db"


def test_upgrade_head_schema(db_path):
    """alembic upgrade head → 5 表 + 4 冻结索引 + 1 辅助索引 + FTS5 + 触发器。"""
    result = _run_alembic(db_path, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    conn.close()

    assert {
        "conversations", "turns", "memory_entries", "outbox", "idempotency_cache", "memory_fts",
    } <= tables
    assert {
        "idx_turns_session", "idx_memory_user_type", "idx_memory_deleted",
        "idx_outbox_pending", "idx_idempotency_expires",
    } <= indexes
    assert {"memory_fts_ai", "memory_fts_au_content", "memory_fts_au_deleted", "memory_fts_ad"} <= triggers


def test_upgrade_schema_columns(db_path):
    """列名/类型/约束与冻结文档逐列对照（FRZ-DB-001）。"""
    _run_alembic(db_path, "upgrade", "head")

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    # PRAGMA table_info 返回 (cid, name, type, notnull, dflt_value, pk)
    cols = {r[1]: (r[2], r[3], r[4]) for r in conn.execute("PRAGMA table_info(memory_entries)")}
    # 关键列：entry_type 约束 / confidence Float ∈[0,1] / version 乐观锁 / is_deleted
    assert cols["entry_type"][0] == "VARCHAR"
    assert cols["confidence"][0] == "FLOAT"
    assert cols["version"][0] == "INTEGER"
    assert cols["is_deleted"][0] == "INTEGER"

    # idempotency_cache 复合 PK（ADR-006）
    pk = conn.execute("PRAGMA table_info(idempotency_cache)").fetchall()
    pk_cols = [r[1] for r in pk if r[5] > 0]
    assert pk_cols == ["user_id", "session_id", "idempotency_key"]
    conn.close()


def test_downgrade_base_clean(db_path):
    """downgrade base → 全部表/索引/触发器移除。"""
    assert _run_alembic(db_path, "upgrade", "head").returncode == 0
    result = _run_alembic(db_path, "downgrade", "base")
    assert result.returncode == 0, result.stderr

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    # 只允许 alembic_version 保留；sqlite_sequence 为 AUTOINCREMENT 内部表，随 conversations 删除后残留属 SQLite 行为
    names = {r[0] for r in tables}
    assert names <= {"alembic_version", "sqlite_sequence"}


def test_upgrade_then_downgrade_then_upgrade(db_path):
    """往返：upgrade → downgrade → upgrade（可迁移性 NFR-5）。"""
    assert _run_alembic(db_path, "upgrade", "head").returncode == 0
    assert _run_alembic(db_path, "downgrade", "base").returncode == 0
    result = _run_alembic(db_path, "upgrade", "head")
    assert result.returncode == 0, result.stderr
