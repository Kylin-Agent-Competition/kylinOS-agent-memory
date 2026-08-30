"""PR-2 迁移测试：ADR-011 20260826_add_trace_id（trace_id/host_turn_id 列 + 往返）"""

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
    return tmp_path / "migrate_pr2.db"


def test_upgrade_head_has_trace_columns(db_path):
    """upgrade head → turns.trace_id/host_turn_id + memory_entries.trace_id + 部分唯一索引。"""
    result = _run_alembic(db_path, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(str(db_path))
    turns_cols = {r[1] for r in conn.execute("PRAGMA table_info(turns)")}
    mem_cols = {r[1] for r in conn.execute("PRAGMA table_info(memory_entries)")}
    idxs = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()

    assert "trace_id" in turns_cols
    assert "host_turn_id" in turns_cols
    assert "trace_id" in mem_cols
    assert "idx_turns_host_turn_id" in idxs


def test_host_turn_id_partial_unique_index(db_path):
    """部分唯一索引：非空 (session_id, host_turn_id) 唯一；NULL 可重复（ADR-011）。"""
    assert _run_alembic(db_path, "upgrade", "head").returncode == 0

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO conversations (user_id, session_id, started_at) VALUES ('u1','s1','2026-08-27T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO turns (session_id, turn_index, original_user_text, is_end, created_at, trace_id, host_turn_id) "
        "VALUES ('s1', 1, 'a', 0, '2026-08-27T00:00:00+00:00', 't1', 'H-1')"
    )
    # 同 (session_id, host_turn_id) 重复 → IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO turns (session_id, turn_index, original_user_text, is_end, created_at, trace_id, host_turn_id) "
            "VALUES ('s1', 2, 'b', 0, '2026-08-27T00:00:00+00:00', 't2', 'H-1')"
        )
    # host_turn_id NULL 允许多行（部分索引不约束 NULL）
    conn.execute(
        "INSERT INTO turns (session_id, turn_index, original_user_text, is_end, created_at, trace_id, host_turn_id) "
        "VALUES ('s1', 3, 'c', 0, '2026-08-27T00:00:00+00:00', 't3', NULL)"
    )
    conn.execute(
        "INSERT INTO turns (session_id, turn_index, original_user_text, is_end, created_at, trace_id, host_turn_id) "
        "VALUES ('s1', 4, 'd', 0, '2026-08-27T00:00:00+00:00', 't4', NULL)"
    )
    conn.close()


def test_downgrade_returns_001_schema(db_path):
    """downgrade 到 001：列/索引/触发器/FTS 与基线等价（表重建回滚，禁 DROP COLUMN）。"""
    assert _run_alembic(db_path, "upgrade", "head").returncode == 0
    result = _run_alembic(db_path, "downgrade", "001_initial_schema")
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(str(db_path))
    turns_cols = {r[1] for r in conn.execute("PRAGMA table_info(turns)")}
    mem_cols = {r[1] for r in conn.execute("PRAGMA table_info(memory_entries)")}
    idxs = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.close()

    # ADR-011 列已移除（表重建回滚）
    assert "trace_id" not in turns_cols
    assert "host_turn_id" not in turns_cols
    assert "trace_id" not in mem_cols
    # 冻结索引/触发器保留
    assert {"idx_turns_session", "idx_memory_user_type", "idx_memory_deleted"} <= idxs
    assert "idx_turns_host_turn_id" not in idxs
    assert {"memory_fts_ai", "memory_fts_au_content", "memory_fts_au_deleted", "memory_fts_ad"} <= triggers
    assert fk == []


def test_downgrade_preserves_data_and_fts(db_path):
    """downgrade 表重建保留数据；FTS 触发器重建后回填一致（ADR-011）。"""
    assert _run_alembic(db_path, "upgrade", "head").returncode == 0

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO conversations (user_id, session_id, started_at) VALUES ('u1','s1','2026-08-27T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO turns (session_id, turn_index, original_user_text, is_end, created_at, trace_id, host_turn_id) "
        "VALUES ('s1', 1, '银河麒麟', 0, '2026-08-27T00:00:00+00:00', 't1', 'H-1')"
    )
    conn.execute(
        "INSERT INTO memory_entries (user_id, entry_type, content, confidence, version, is_deleted, created_at, updated_at, trace_id) "
        "VALUES ('u1', 'knowledge', '{\"text\":\"麒麟桌面系统\"}', 0.9, 1, 0, '2026-08-27T00:00:00+00:00', '2026-08-27T00:00:00+00:00', 't1')"
    )
    conn.commit()
    conn.close()

    result = _run_alembic(db_path, "downgrade", "001_initial_schema")
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(str(db_path))
    turns = conn.execute("SELECT turn_index, original_user_text FROM turns").fetchall()
    mem = conn.execute("SELECT entry_type, content FROM memory_entries").fetchall()
    fts_hits = conn.execute(
        "SELECT count(*) FROM memory_fts WHERE memory_fts MATCH '麒麟桌面系统'"
    ).fetchone()[0]
    conn.close()

    assert turns == [(1, "银河麒麟")]  # 数据保留（trace_id 列丢弃）
    assert len(mem) == 1
    assert fts_hits == 1  # FTS 回填一致


def test_downgrade_upgrade_roundtrip_fts_matchers(db_path):
    """往返 2.3：downgrade 后软删不入 FTS；再 upgrade head 仍保持一致（NFR-5）。"""
    assert _run_alembic(db_path, "upgrade", "head").returncode == 0

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO conversations (user_id, session_id, started_at) VALUES ('u1','s1','2026-08-27T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO turns (session_id, turn_index, original_user_text, is_end, created_at, trace_id, host_turn_id) "
        "VALUES ('s1', 1, '基座', 0, '2026-08-27T00:00:00+00:00', 't1', 'H-1')"
    )
    conn.execute(
        "INSERT INTO memory_entries (user_id, entry_type, content, confidence, version, is_deleted, created_at, updated_at, trace_id) "
        "VALUES ('u1', 'knowledge', '{\"text\":\"麒麟桌面系统\"}', 0.9, 1, 0, '2026-08-27T00:00:00+00:00', '2026-08-27T00:00:00+00:00', 't1')"
    )
    conn.execute(
        "INSERT INTO memory_entries (user_id, entry_type, content, confidence, version, is_deleted, created_at, updated_at, trace_id) "
        "VALUES ('u1', 'knowledge', '{\"text\":\"机密软删内容ABC\"}', 0.9, 1, 1, '2026-08-27T00:00:00+00:00', '2026-08-27T00:00:00+00:00', 't1')"
    )
    conn.commit()
    conn.close()

    # downgrade → 软删 MATCH 0
    assert _run_alembic(db_path, "downgrade", "001_initial_schema").returncode == 0
    conn = sqlite3.connect(str(db_path))
    deleted_before = conn.execute(
        "SELECT count(*) FROM memory_fts WHERE memory_fts MATCH '机密软删内容ABC'"
    ).fetchone()[0]
    conn.close()
    assert deleted_before == 0

    # upgrade head → 仍为 0（软删行始终不入 FTS）
    assert _run_alembic(db_path, "upgrade", "head").returncode == 0
    conn = sqlite3.connect(str(db_path))
    deleted_after = conn.execute(
        "SELECT count(*) FROM memory_fts WHERE memory_fts MATCH '机密软删内容ABC'"
    ).fetchone()[0]
    fts_total = conn.execute("SELECT count(*) FROM memory_fts").fetchone()[0]
    normal_total = conn.execute(
        "SELECT count(*) FROM memory_entries WHERE is_deleted = 0"
    ).fetchone()[0]
    conn.close()
    assert deleted_after == 0
    assert fts_total == normal_total


def test_upgrade_downgrade_upgrade_roundtrip_pr2(db_path):
    """往返 upgrade → downgrade 001 → upgrade head（可迁移性，NFR-5）。"""
    assert _run_alembic(db_path, "upgrade", "head").returncode == 0
    assert _run_alembic(db_path, "downgrade", "001_initial_schema").returncode == 0
    result = _run_alembic(db_path, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(str(db_path))
    turns_cols = {r[1] for r in conn.execute("PRAGMA table_info(turns)")}
    conn.close()
    assert {"trace_id", "host_turn_id"} <= turns_cols


def test_downgrade_excludes_soft_deleted_from_fts(db_path):
    """B2：downgrade 后软删除记忆不得重新进入 FTS（MATCH 不可命中）。"""
    assert _run_alembic(db_path, "upgrade", "head").returncode == 0

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO conversations (user_id, session_id, started_at) VALUES ('u1','s1','2026-08-27T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO turns (session_id, turn_index, original_user_text, is_end, created_at, trace_id, host_turn_id) "
        "VALUES ('s1', 1, '基座', 0, '2026-08-27T00:00:00+00:00', 't1', 'H-1')"
    )
    # 正常记录（is_deleted=0）
    conn.execute(
        "INSERT INTO memory_entries (user_id, entry_type, content, confidence, version, is_deleted, created_at, updated_at, trace_id) "
        "VALUES ('u1', 'knowledge', '{\"text\":\"麒麟桌面系统\"}', 0.9, 1, 0, '2026-08-27T00:00:00+00:00', '2026-08-27T00:00:00+00:00', 't1')"
    )
    # 软删除记录（is_deleted=1）
    conn.execute(
        "INSERT INTO memory_entries (user_id, entry_type, content, confidence, version, is_deleted, created_at, updated_at, trace_id) "
        "VALUES ('u1', 'knowledge', '{\"text\":\"软删机密内容XYZ\"}', 0.9, 1, 1, '2026-08-27T00:00:00+00:00', '2026-08-27T00:00:00+00:00', 't1')"
    )
    conn.commit()
    conn.close()

    result = _run_alembic(db_path, "downgrade", "001_initial_schema")
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(str(db_path))
    # 正常记录 MATCH 命中 1
    fts_normal = conn.execute(
        "SELECT count(*) FROM memory_fts WHERE memory_fts MATCH '麒麟桌面系统'"
    ).fetchone()[0]
    # 软删记录 MATCH 命中 0（不得重新索引）
    fts_deleted = conn.execute(
        "SELECT count(*) FROM memory_fts WHERE memory_fts MATCH '软删机密内容XYZ'"
    ).fetchone()[0]
    # memory_fts 行数 = 非软删行数
    fts_total = conn.execute("SELECT count(*) FROM memory_fts").fetchone()[0]
    normal_total = conn.execute(
        "SELECT count(*) FROM memory_entries WHERE is_deleted = 0"
    ).fetchone()[0]
    conn.close()

    assert fts_normal == 1
    assert fts_deleted == 0
    assert fts_total == normal_total
