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


def make_capture_handoff(
    tmp_path: Path,
    *,
    db_path: Path | None = None,
    queries_file: Path | None = None,
    vector_cli: Path | None = None,
) -> Path:
    channels = {
        "sqlite_truth": "capture_d14b_sqlite_truth.py",
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
        {
            "tested_commit": TESTED_COMMIT,
            "captures": captures,
            "source_bindings": {
                "sqlite_truth": {"production_db_path": str(db_path or "")},
                "fts5": {
                    "production_db_path": str(db_path or ""),
                    "query_spec_path": str(queries_file or ""),
                    "query_spec_sha256": (
                        hashlib.sha256(queries_file.read_bytes()).hexdigest()
                        if queries_file
                        else ""
                    ),
                },
                "vector": {
                    "production_db_path": str(db_path or ""),
                    "query_spec_path": str(queries_file or ""),
                    "query_spec_sha256": (
                        hashlib.sha256(queries_file.read_bytes()).hexdigest()
                        if queries_file
                        else ""
                    ),
                    "vector_cli_path": str(vector_cli or ""),
                    "vector_cli_sha256": (
                        hashlib.sha256(vector_cli.read_bytes()).hexdigest()
                        if vector_cli
                        else ""
                    ),
                },
                "rrf": {"production_db_path": str(db_path or "")},
            },
        },
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
    tmp_path.mkdir(parents=True, exist_ok=True)
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
    queries = make_queries_file(tmp_path)
    vector_cli = make_fake_vector_cli(tmp_path)
    capture_handoff = make_capture_handoff(
        tmp_path,
        db_path=db_path,
        queries_file=queries,
        vector_cli=Path(vector_cli),
    )

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
    assert payload["capture_sources"]["sqlite_truth"]["runner_path"] == "scripts/capture_d14b_sqlite_truth.py"
    assert set(ids) == {"d14b-a-keep", "d14b-a-delete-target"}


def run_sqlite_capture(common: list[str], output: Path, receipt: Path):
    return run_script(
        "capture_d14b_sqlite_truth.py",
        *common,
        "--output",
        str(output),
        "--receipt-output",
        str(receipt),
    )


def run_vector_capture(
    common: list[str],
    queries: Path,
    vector_cli: str,
    output: Path,
    receipt: Path,
):
    return run_script(
        "capture_d14b_vector_results.py",
        *common,
        "--queries-file",
        str(queries),
        "--vector-cli",
        vector_cli,
        "--dimension",
        "768",
        "--output",
        str(output),
        "--receipt-output",
        str(receipt),
    )


def run_rrf_capture(common: list[str], fts5: Path, vector: Path, output: Path, receipt: Path):
    return run_script(
        "capture_d14b_rrf_results.py",
        *common,
        "--fts5-results",
        str(fts5),
        "--vector-results",
        str(vector),
        "--output",
        str(output),
        "--receipt-output",
        str(receipt),
    )


def make_pinned_capture_case(tmp_path: Path) -> dict[str, object]:
    db_path = tmp_path / "memory.db"
    seed_production_schema(db_path)
    queries = make_queries_file(tmp_path)
    vector_cli = make_fake_vector_cli(tmp_path)
    capture_handoff = make_capture_handoff(
        tmp_path,
        db_path=db_path,
        queries_file=queries,
        vector_cli=Path(vector_cli),
    )
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
    return {
        "common": common,
        "db_path": db_path,
        "queries": queries,
        "vector_cli": vector_cli,
        "capture_handoff": capture_handoff,
    }


def test_capture_rejects_existing_artifact_without_deleting_it(tmp_path: Path) -> None:
    case = make_pinned_capture_case(tmp_path)
    output = tmp_path / "sqlite-truth.json"
    receipt = tmp_path / "sqlite-truth.receipt.json"
    output.write_text("preserve-existing-artifact\n", encoding="utf-8")

    completed = run_sqlite_capture(case["common"], output, receipt)

    assert completed.returncode != 0
    assert "artifact 输出已存在" in completed.stderr
    assert output.read_text(encoding="utf-8") == "preserve-existing-artifact\n"
    assert not receipt.exists()


def test_capture_rejects_existing_receipt_without_deleting_it(tmp_path: Path) -> None:
    case = make_pinned_capture_case(tmp_path)
    output = tmp_path / "sqlite-truth.json"
    receipt = tmp_path / "sqlite-truth.receipt.json"
    receipt.write_text("preserve-existing-receipt\n", encoding="utf-8")

    completed = run_sqlite_capture(case["common"], output, receipt)

    assert completed.returncode != 0
    assert "receipt 输出已存在" in completed.stderr
    assert receipt.read_text(encoding="utf-8") == "preserve-existing-receipt\n"
    assert not output.exists()


def test_capture_rejects_a_repeated_command_without_changing_first_output(tmp_path: Path) -> None:
    case = make_pinned_capture_case(tmp_path)
    output = tmp_path / "sqlite-truth.json"
    receipt = tmp_path / "sqlite-truth.receipt.json"

    first = run_sqlite_capture(case["common"], output, receipt)
    assert first.returncode == 0, first.stderr
    artifact_bytes = output.read_bytes()
    receipt_bytes = receipt.read_bytes()

    repeat = run_sqlite_capture(case["common"], output, receipt)

    assert repeat.returncode != 0
    assert "artifact 输出已存在" in repeat.stderr
    assert output.read_bytes() == artifact_bytes
    assert receipt.read_bytes() == receipt_bytes


def test_capture_rejects_an_unapproved_vector_cli(tmp_path: Path) -> None:
    case = make_pinned_capture_case(tmp_path)
    approved_cli = str(case["vector_cli"])
    unapproved_cli = make_fake_vector_cli(tmp_path / "unapproved")

    completed = run_vector_capture(
        case["common"],
        case["queries"],
        unapproved_cli,
        tmp_path / "vector.json",
        tmp_path / "vector.receipt.json",
    )

    assert completed.returncode != 0
    assert "vector_cli_path" in completed.stderr
    assert not (tmp_path / "vector.json").exists()
    assert approved_cli != unapproved_cli


def test_capture_rejects_tampered_vector_cli_bytes(tmp_path: Path) -> None:
    case = make_pinned_capture_case(tmp_path)
    vector_cli = Path(case["vector_cli"])
    original_bytes = vector_cli.read_bytes()
    vector_cli.write_bytes(original_bytes + b"# tampered\n")

    completed = run_vector_capture(
        case["common"],
        case["queries"],
        str(vector_cli),
        tmp_path / "vector.json",
        tmp_path / "vector.receipt.json",
    )

    assert completed.returncode != 0
    assert "vector_cli_sha256" in completed.stderr
    assert not (tmp_path / "vector.json").exists()


def test_capture_rejects_wrong_production_db_path(tmp_path: Path) -> None:
    case = make_pinned_capture_case(tmp_path)
    wrong_db = tmp_path / "wrong-memory.db"
    wrong_db.write_bytes(b"not the pinned database\n")
    common = list(case["common"])
    common[common.index(str(case["db_path"]))] = str(wrong_db)

    completed = run_sqlite_capture(
        common,
        tmp_path / "sqlite-truth.json",
        tmp_path / "sqlite-truth.receipt.json",
    )

    assert completed.returncode != 0
    assert "production_db_path" in completed.stderr
    assert not (tmp_path / "sqlite-truth.json").exists()


def test_capture_rejects_query_spec_bytes_drift(tmp_path: Path) -> None:
    case = make_pinned_capture_case(tmp_path)
    queries = Path(case["queries"])
    original = queries.read_bytes()
    payload = json.loads(original.decode("utf-8"))
    payload["queries"][0]["match"] = "drifted"
    queries.write_text(json.dumps(payload), encoding="utf-8")

    completed = run_script(
        "capture_d14b_fts5_results.py",
        *case["common"],
        "--queries-file",
        str(queries),
        "--output",
        str(tmp_path / "fts5.json"),
        "--receipt-output",
        str(tmp_path / "fts5.receipt.json"),
    )

    assert completed.returncode != 0
    assert "query_spec_sha256" in completed.stderr
    assert not (tmp_path / "fts5.json").exists()


def make_rrf_parent_assembler_case(tmp_path: Path) -> tuple[dict[str, Path], dict[str, Path], Path]:
    channel_result = {
        "queries": [{"query_id": "q1", "results": []}],
    }
    truth = {"stable_ids": ["a"], "active_version_ids": ["v1"]}
    artifacts = {
        "sqlite_truth": write_json(tmp_path / "sqlite-truth.json", truth),
        "fts5": write_json(tmp_path / "fts5.json", channel_result),
        "vector": write_json(tmp_path / "vector.json", channel_result),
        "rrf": write_json(tmp_path / "rrf.json", channel_result),
    }
    hashes = {
        channel: hashlib.sha256(path.read_bytes()).hexdigest()
        for channel, path in artifacts.items()
    }
    handoff = write_json(
        tmp_path / "capture-handoff.json",
        {
            "tested_commit": TESTED_COMMIT,
            "captures": {
                channel: {
                    "runner_path": f"runner_{channel}.py",
                    "runner_sha256": "d" * 64,
                    "command_id": f"d14b-{channel}-v1",
                }
                for channel in ("sqlite_truth", "fts5", "vector", "rrf")
            },
        },
    )
    receipts: dict[str, Path] = {}
    for channel in artifacts:
        receipt = {
            "channel": channel,
            "tested_commit": TESTED_COMMIT,
            "command_id": f"d14b-{channel}-v1",
            "runner_path": f"runner_{channel}.py",
            "runner_sha256": "d" * 64,
            "artifact_path": artifacts[channel].name,
            "artifact_sha256": hashes[channel],
            "captured_at_utc": "2026-09-09T00:00:00Z",
        }
        if channel == "rrf":
            receipt["fts5_input_sha256"] = "e" * 64
            receipt["vector_input_sha256"] = hashes["vector"]
        receipts[channel] = write_json(tmp_path / f"{channel}.receipt.json", receipt)
    return artifacts, receipts, handoff


def test_assembler_rejects_rrf_parent_artifact_substitution(tmp_path: Path) -> None:
    artifacts, receipts, handoff = make_rrf_parent_assembler_case(tmp_path)
    output = tmp_path / "checkpoint.json"

    completed = run_script(
        "capture_d14b_retrieval_snapshot.py",
        "--tested-commit", TESTED_COMMIT,
        "--checkpoint", "baseline",
        "--user-id", USER_ID,
        "--captured-at-utc", "2026-09-09T00:00:00Z",
        "--capture-handoff", str(handoff),
        "--sqlite-truth", str(artifacts["sqlite_truth"]),
        "--fts5-results", str(artifacts["fts5"]),
        "--vector-results", str(artifacts["vector"]),
        "--rrf-results", str(artifacts["rrf"]),
        "--sqlite-receipt", str(receipts["sqlite_truth"]),
        "--fts5-receipt", str(receipts["fts5"]),
        "--vector-receipt", str(receipts["vector"]),
        "--rrf-receipt", str(receipts["rrf"]),
        "--output", str(output),
    )

    assert completed.returncode != 0
    assert "fts5_input_sha256" in completed.stderr
    assert not output.exists()
