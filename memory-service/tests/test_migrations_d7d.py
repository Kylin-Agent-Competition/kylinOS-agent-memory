"""D7D Migration：版本表、current 唯一约束与安全回退。"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "migrations"


def _run_alembic(db_path: str, *args: str) -> subprocess.CompletedProcess:
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


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "d7d-migrate.db"


def test_upgrade_head_creates_version_tables_and_current_unique_index(db_path):
    result = _run_alembic(db_path, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(str(db_path))
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    triggers = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    version_columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_versions)")}
    item_columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_items)")}
    conn.close()

    assert {"memory_items", "memory_versions", "memory_version_receipts"} <= tables
    assert {
        "uq_memory_versions_item_version",
        "uq_memory_versions_current",
        "uq_memory_version_receipts_idempotency",
        "uq_memory_version_receipts_evidence",
        "idx_memory_versions_status",
    } <= indexes
    assert {
        "memory_versions_bi_chain",
        "memory_versions_bu_chain",
        "memory_versions_bu_immutable",
        "memory_versions_bd_immutable",
        "memory_items_bi_current_pointer",
        "memory_items_bu_current_pointer",
        "memory_versions_ai_current_pointer",
        "memory_versions_au_current_pointer_on",
        "memory_versions_au_current_pointer_off",
        "memory_version_receipts_bi_consistency",
        "memory_version_receipts_bu_immutable",
        "memory_version_receipts_bd_immutable",
    } <= triggers
    assert {
        "memory_item_id", "version", "previous_version_id", "rollback_of_version_id",
        "evidence_fingerprint", "idempotency_key", "request_fingerprint", "is_current",
    } <= version_columns
    assert "current_version_id" in item_columns


def test_empty_schema_can_downgrade_to_previous_revision_and_reupgrade(db_path):
    assert _run_alembic(db_path, "upgrade", "head").returncode == 0
    result = _run_alembic(db_path, "downgrade", "20260826_add_trace_id")
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(str(db_path))
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    conn.close()
    assert "memory_items" not in tables
    assert "memory_versions" not in tables
    assert "memory_version_receipts" not in tables
    assert revision == "20260826_add_trace_id"
    assert _run_alembic(db_path, "upgrade", "head").returncode == 0


def test_upgrade_preserves_existing_d4d_memory_entries(db_path):
    assert _run_alembic(db_path, "upgrade", "20260826_add_trace_id").returncode == 0
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO memory_entries (user_id, entry_type, content, confidence, version, is_deleted, created_at, updated_at, trace_id) "
        "VALUES ('u1', 'preference', '{\"key\":\"response.language\"}', 0.9, 1, 0, "
        "'2026-08-31T00:00:00+00:00', '2026-08-31T00:00:00+00:00', 'tr-1')"
    )
    conn.commit()
    conn.close()

    result = _run_alembic(db_path, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    conn = sqlite3.connect(str(db_path))
    assert conn.execute("SELECT count(*) FROM memory_entries").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM memory_versions").fetchone()[0] == 0
    conn.close()


def test_downgrade_refuses_to_discard_existing_version_history(db_path):
    assert _run_alembic(db_path, "upgrade", "head").returncode == 0
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO memory_items (user_id, preference_key, preference_scope, created_at, updated_at) "
        "VALUES ('u1', 'response.language', 'global', '2026-08-31T00:00:00+00:00', '2026-08-31T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO memory_versions (memory_item_id, version, preference_value, memory_status, "
        "evidence_fingerprint, request_fingerprint, is_current, created_at) "
        "VALUES (1, 1, '中文', 'active', 'ev-1', 'req-1', 1, '2026-08-31T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    result = _run_alembic(db_path, "downgrade", "20260826_add_trace_id")
    assert result.returncode != 0
    assert "拒绝回退" in result.stderr

    conn = sqlite3.connect(str(db_path))
    assert conn.execute("SELECT count(*) FROM memory_versions").fetchone()[0] == 1
    conn.close()
