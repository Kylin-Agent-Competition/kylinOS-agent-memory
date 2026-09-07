"""D8-D migration truth gate: direct-SQL fail-closed checks on a real Alembic DB.

ADR-017/批准草案 §14.3 requires the SQLite truth layer itself (not just the
Repository) to reject forged ``legacy_unmapped``, missing/invalid
version/row_revision, nulled structured knowledge fields, eligibility/evidence
inconsistencies and ``is_deleted``/``memory_status`` mismatch.  These tests run
``alembic upgrade head`` and then execute raw SQL against the migrated file.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "migrations"
TS = "2026-09-03T00:00:00+00:00"


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


def _insert(
    conn: sqlite3.Connection,
    *,
    user_id: str = "u-gate",
    entry_type: str = "knowledge",
    content: str = "{}",
    confidence: float = 0.9,
    version: int = 1,
    row_revision: object = 1,
    is_deleted: int = 0,
    knowledge_id: object = "k-gate",
    knowledge_type: object = "fact",
    conditions: object = None,
    lifecycle_eligibility: object = "eligible",
    memory_status: object = "candidate",
    memory_type: object = "short_term",
    evidence_tier: object = "user_explicit_config_latest",
) -> None:
    conn.execute(
        "INSERT INTO memory_entries ("
        " user_id, entry_type, content, confidence, version, row_revision,"
        " is_deleted, created_at, updated_at, knowledge_id, knowledge_type,"
        " conditions, lifecycle_eligibility, memory_status, memory_type, evidence_tier"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            user_id, entry_type, content, confidence, version, row_revision,
            is_deleted, TS, TS, knowledge_id, knowledge_type, conditions,
            lifecycle_eligibility, memory_status, memory_type, evidence_tier,
        ),
    )


@pytest.fixture()
def conn(tmp_path):
    db_path = tmp_path / "d8d-truth-gate.db"
    result = _run_alembic(db_path, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    connection = sqlite3.connect(str(db_path), isolation_level=None)
    yield connection
    connection.close()


def test_insert_gate_rejects_direct_sql_negative_cases(conn):
    """Alembic 后真实数据库：迁移后非法新行 MUST FAIL（§14.3 direct SQL）。"""
    cases = [
        dict(version=0),
        dict(version=-1),
        dict(row_revision=None),
        dict(row_revision=0),
        dict(knowledge_id=None),
        dict(knowledge_type=None),
        dict(lifecycle_eligibility="legacy_unmapped"),  # 伪造 legacy
        dict(lifecycle_eligibility="eligible", evidence_tier=None),
        dict(lifecycle_eligibility="evidence_unmapped", evidence_tier="user_confirmed"),
        dict(is_deleted=1, memory_status="candidate"),
        dict(entry_type="preference", memory_status="candidate", lifecycle_eligibility=None),
    ]
    for overrides in cases:
        with pytest.raises(sqlite3.IntegrityError, match="d8d"):
            _insert(conn, **overrides)

    # 合法新行不受影响。
    _insert(conn, knowledge_id="k-valid")
    count = conn.execute(
        "SELECT count(*) FROM memory_entries WHERE knowledge_id='k-valid'"
    ).fetchone()[0]
    assert count == 1


def test_update_gate_rejects_forgery_nulled_fields_and_bad_revision(conn):
    """UPDATE 不得把 mapped knowledge 伪造为 legacy、置空必填字段或降 revision。"""
    _insert(conn, knowledge_id="k-gate")
    conn.execute(
        "UPDATE memory_entries SET memory_status='active', row_revision=2, updated_at=? WHERE knowledge_id='k-gate'",
        (TS,),
    )

    negative_updates = [
        ("UPDATE memory_entries SET knowledge_type=NULL, updated_at=? WHERE knowledge_id='k-gate'", ()),
        ("UPDATE memory_entries SET lifecycle_eligibility='legacy_unmapped', updated_at=? WHERE knowledge_id='k-gate'", ()),
        ("UPDATE memory_entries SET version=0, updated_at=? WHERE knowledge_id='k-gate'", ()),
        ("UPDATE memory_entries SET row_revision=0, updated_at=? WHERE knowledge_id='k-gate'", ()),
        ("UPDATE memory_entries SET evidence_tier=NULL, updated_at=? WHERE knowledge_id='k-gate'", ()),
        ("UPDATE memory_entries SET is_deleted=1, updated_at=? WHERE knowledge_id='k-gate'", ()),
    ]
    for sql, extra in negative_updates:
        with pytest.raises(sqlite3.IntegrityError, match="d8d"):
            conn.execute(sql, extra + (TS,))

    row = conn.execute(
        "SELECT version, row_revision, memory_status, lifecycle_eligibility FROM memory_entries WHERE knowledge_id='k-gate'"
    ).fetchone()
    assert row == (1, 2, "active", "eligible")


def test_d8d_member_index_and_triggers_exist_on_migrated_db(conn):
    triggers = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'memory_entries_d8d_%'"
        )
    }
    assert triggers == {"memory_entries_d8d_insert_gate", "memory_entries_d8d_update_gate"}
    index = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_memory_conflict_member_knowledge'"
    ).fetchone()
    assert index is not None
