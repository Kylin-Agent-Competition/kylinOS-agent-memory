"""D10-B：Vector 账本生产迁移验收。"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "migrations"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["KYLIN_MEMORY_DB"] = str(db_path)
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(MIGRATIONS_DIR / "alembic.ini"), *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def test_upgrade_head_creates_d10b_vector_ledger_tables(tmp_path):
    """生产迁移必须创建代次、索引项和幂等回执三张账本表。"""
    db_path = tmp_path / "d10b-migrate.db"
    result = _run_alembic(db_path, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(str(db_path))
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    generation_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(vector_index_generations)")
    }
    receipt_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(vector_index_receipts)")
    }
    conn.close()

    assert {
        "vector_index_generations",
        "vector_index_entries",
        "vector_index_receipts",
    } <= tables
    assert {
        "scope_id",
        "generation",
        "collection_name",
        "source_watermark",
        "record_digest",
        "is_serving",
    } <= generation_columns
    assert {"operation", "idempotency_key", "payload_hash", "result_json"} <= receipt_columns
