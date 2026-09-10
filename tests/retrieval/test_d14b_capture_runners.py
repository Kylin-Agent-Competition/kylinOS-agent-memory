"""L1 smoke contracts for the four pinned D14B production capture runners."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, insert

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPOSITORY_ROOT / "scripts"
TESTED_COMMIT = "a" * 40
USER_ID = "d14b-controlled-user-a"


def run_script(script_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script_name), *args],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )


def write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def make_capture_handoff(tmp_path: Path) -> Path:
    channels = {
        "sqlite": "capture_d14b_sqlite_truth.py",
        "fts5": "capture_d14b_fts5_results.py",
        "vector": "capture_d14b_vector_results.py",
        "rrf": "capture_d14b_rrf_results.py",
    }
    captures = {
        channel: {
            "runner_path": f"scripts/{filename}",
            "runner_sha256": hashlib.sha256(
                (SCRIPTS / filename).read_bytes()
            ).hexdigest(),
            "command_id": f"d14b-{channel}-v1",
        }
        for channel, filename in channels.items()
    }
    return write_json(
        tmp_path / "d14b-capture-handoff.json",
        {"tested_commit": TESTED_COMMIT, "captures": captures},
    )


def seed_production_schema(db_path: Path) -> dict[str, int]:
    sys.path.insert(0, str(REPOSITORY_ROOT / "memory-service"))
    from db.engine import init_schema
    from db.schema import memory_entries, memory_relation, vector_index_entries, vector_index_generations

    engine = create_engine(f"sqlite:///{db_path.resolve().as_posix()}")
    init_schema(engine)
    now = datetime.now(timezone.utc).isoformat()
    records = [
        ("d14b-a-keep", "control keep alpha"),
        ("d14b-a-delete-target", "control delete target"),
    ]
    ids: dict[str, int] = {}
    with engine.begin() as connection:
        for knowledge_id, value in records:
            result = connection.execute(
                insert(memory_entries).values(
                    user_id=USER_ID,
                    entry_type="knowledge",
                    content=json.dumps({"value": value}, ensure_ascii=False),
                    confidence=0.95,
                    version=1,
                    row_revision=1,
                    is_deleted=0,
                    created_at=now,
                    updated_at=now,
                    knowledge_id=knowledge_id,
                    knowledge_type="workflow",
                    memory_status="active",
                    memory_type="long_term",
                )
            )
            entry_id = int(result.inserted_primary_key[0])
            ids[knowledge_id] = entry_id
            connection.execute(
                insert(memory_relation).values(
                    user_id=USER_ID,
                    relation_id=f"evidence:{knowledge_id}:event-{entry_id}",
                    relation_type="evidence",
                    left_endpoint_type="knowledge",
                    left_endpoint_id=knowledge_id,
                    right_endpoint_type="source_event",
                    right_endpoint_id=f"event-{entry_id}",
                    is_primary=1,
                    created_at=now,
                )
            )
        connection.execute(
            insert(vector_index_generations).values(
                scope_id=f"user:{USER_ID}",
                generation="generation-1",
                collection_name="d14b-test-collection",
                status="ready",
                schema_version="vector-retrieval/v1",
                record_count=2,
                is_serving=1,
                created_at=now,
                activated_at=now,
            )
        )
        for entry_id in ids.values():
            connection.execute(
                insert(vector_index_entries).values(
                    scope_id=f"user:{USER_ID}",
                    generation="generation-1",
                    user_id=USER_ID,
                    memory_entry_id=entry_id,
                    version_id="v1",
                    is_active=1,
                )
            )
    engine.dispose()
    return ids


def make_fake_vector_cli(tmp_path: Path) -> str:
    client_script = tmp_path / "fake_vector_cli.py"
    client_script.write_text(
        '\n'.join(
            [
                "import json",
                "print(json.dumps({",
                '    "ok": True,',
                '    "hits": [',
                '        {"id": 1, "user_id": "d14b-controlled-user-a", "version_id": "v1", "score": 0.98},',
                '        {"id": 2, "user_id": "d14b-controlled-user-a", "version_id": "v1", "score": 0.94},',
                "    ],",
                "}))",
            ]
        ),
        encoding="utf-8",
    )
    if os.name == "nt":
        wrapper = tmp_path / "fake_vector_cli.cmd"
        wrapper.write_text(
            f'@echo off\n"{sys.executable}" "{client_script}" %*\n',
            encoding="utf-8",
        )
        return str(wrapper)
    wrapper = tmp_path / "fake_vector_cli"
    wrapper.write_text(
        f"#!/bin/sh\nexec '{sys.executable}' '{client_script}' \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return str(wrapper)


def make_queries_file(tmp_path: Path) -> Path:
    return write_json(
        tmp_path / "queries.json",
        {
            "queries": [
                {
                    "query_id": "d14b-q-user-a",
                    "user_id": USER_ID,
                    "match": "control",
                    "limit": 10,
                    "top_n": 10,
                    "vector": [0.1] * 768,
                }
            ]
        },
    )


def test_production_capture_runners_generate_provenant_checkpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    ids = seed_production_schema(db_path)
    capture_handoff = make_capture_handoff(tmp_path)
    queries = make_queries_file(tmp_path)
    vector_cli = make_fake_vector_cli(tmp_path)

    common = [
        "--db-path",
        str(db_path),
        "--user-id",
        USER_ID,
        "--tested-commit",
        TESTED_COMMIT,
        "--capture-handoff",
        str(capture_handoff),
    ]
    truth = tmp_path / "sqlite-truth.json"
    truth_receipt = tmp_path / "sqlite-truth.receipt.json"
    fts5 = tmp_path / "fts5-results.json"
    fts5_receipt = tmp_path / "fts5-results.receipt.json"
    vector = tmp_path / "vector-results.json"
    vector_receipt = tmp_path / "vector-results.receipt.json"
    rrf = tmp_path / "rrf-results.json"
    rrf_receipt = tmp_path / "rrf-results.receipt.json"

    sqlite_run = run_script(
        "capture_d14b_sqlite_truth.py",
        *common,
        "--output",
        str(truth),
        "--receipt-output",
        str(truth_receipt),
    )
    assert sqlite_run.returncode == 0, sqlite_run.stderr
    assert json.loads(truth.read_text(encoding="utf-8")) == {
        "stable_ids": [
            f"d14b-a-delete-target-v1",
            f"d14b-a-keep-v1",
        ],
        "active_version_ids": ["v1"],
    }

    fts5_run = run_script(
        "capture_d14b_fts5_results.py",
        *common,
        "--queries-file",
        str(queries),
        "--output",
        str(fts5),
        "--receipt-output",
        str(fts5_receipt),
    )
    assert fts5_run.returncode == 0, fts5_run.stderr
    fts5_results = json.loads(fts5.read_text(encoding="utf-8"))["queries"][0]["results"]
    assert {item["stable_id"] for item in fts5_results} == {
        "d14b-a-delete-target-v1",
        "d14b-a-keep-v1",
    }

    vector_run = run_script(
        "capture_d14b_vector_results.py",
        *common,
        "--queries-file",
        str(queries),
        "--vector-cli",
        vector_cli,
        "--dimension",
        "768",
        "--output",
        str(vector),
        "--receipt-output",
        str(vector_receipt),
    )
    assert vector_run.returncode == 0, vector_run.stderr
    vector_results = json.loads(vector.read_text(encoding="utf-8"))["queries"][0]["results"]
    assert {item["stable_id"] for item in vector_results} == {
        "d14b-a-delete-target-v1",
        "d14b-a-keep-v1",
    }

    rrf_run = run_script(
        "capture_d14b_rrf_results.py",
        *common,
        "--fts5-results",
        str(fts5),
        "--vector-results",
        str(vector),
        "--sensitivity",
        "none",
        "--conflict-state",
        "none",
        "--output",
        str(rrf),
        "--receipt-output",
        str(rrf_receipt),
    )
    assert rrf_run.returncode == 0, rrf_run.stderr
    rrf_results = json.loads(rrf.read_text(encoding="utf-8"))["queries"][0]["results"]
    assert {item["stable_id"] for item in rrf_results} == set(
        f"d14b-a-{name}-v1" for name in ("keep", "delete-target")
    )

    checkpoint = tmp_path / "baseline.json"
    assemble_run = run_script(
        "capture_d14b_retrieval_snapshot.py",
        "--tested-commit",
        TESTED_COMMIT,
        "--checkpoint",
        "baseline",
        "--user-id",
        USER_ID,
        "--captured-at-utc",
        "2026-09-09T00:00:00Z",
        "--capture-handoff",
        str(capture_handoff),
        "--sqlite-truth",
        str(truth),
        "--sqlite-receipt",
        str(truth_receipt),
        "--fts5-results",
        str(fts5),
        "--fts5-receipt",
        str(fts5_receipt),
        "--vector-results",
        str(vector),
        "--vector-receipt",
        str(vector_receipt),
        "--rrf-results",
        str(rrf),
        "--rrf-receipt",
        str(rrf_receipt),
        "--output",
        str(checkpoint),
    )
    assert assemble_run.returncode == 0, assemble_run.stderr
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert payload["sqlite"]["stable_ids"] == [
        "d14b-a-delete-target-v1",
        "d14b-a-keep-v1",
    ]
    assert payload["capture_sources"]["sqlite"]["runner_path"] == "scripts/capture_d14b_sqlite_truth.py"
    assert set(ids) == {"d14b-a-keep", "d14b-a-delete-target"}
