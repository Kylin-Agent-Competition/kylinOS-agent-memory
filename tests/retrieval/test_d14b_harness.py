"""D14B formal-regression harness L0/L1 contracts.

These tests exercise the published CLI seams only.  They never create a
formal evidence root and do not access a Vector/FTS5 service.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPOSITORY_ROOT / "scripts"
SHA = "a" * 40
OTHER_SHA = "b" * 40
HASH = "c" * 64


def write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def run_script(script_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script_name), *args],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def handoffs(tmp_path: Path, commit: str = SHA) -> tuple[Path, Path, Path]:
    package = {
        "package_version": "0.1.0-d14a",
        "package_tar_sha256": HASH,
        "package_manifest_sha256": HASH,
    }
    vm = {
        "vm_name": "Kylin-V11-2603-BTrack-Base",
        "vm_uuid": "11111111-1111-1111-1111-111111111111",
        "snapshot_name": "d14d-clean-base",
        "snapshot_uuid": "22222222-2222-2222-2222-222222222222",
        "environment_id": "d14d-l3",
    }
    d13d = write_json(
        tmp_path / "d13d.json",
        {
            "freeze_status": "FROZEN",
            "tested_commit": commit,
            "freeze_reference": "https://evidence.example.invalid/d13d-seal",
        },
    )
    d14d = write_json(
        tmp_path / "d14d.json",
        {
            "release_status": "L3_READY",
            "tested_commit": commit,
            "evidence_reference": "https://evidence.example.invalid/d14d-g9",
            "package": package,
            "vm": vm,
        },
    )
    manifest = write_json(tmp_path / "manifest.json", {"source_commit": commit, **package})
    return d13d, d14d, manifest


def preflight(
    tmp_path: Path, d13d: Path, d14d: Path, manifest: Path, *extra: str
) -> subprocess.CompletedProcess[str]:
    return run_script(
        "run_d14b_preflight.py",
        "--expected-tested-commit",
        SHA,
        "--d13d-handoff",
        str(d13d),
        "--d14d-handoff",
        str(d14d),
        "--package-manifest",
        str(manifest),
        "--repo-root",
        str(tmp_path / "not-reached-on-invalid-input"),
        "--evidence-root",
        str(tmp_path / "new-evidence"),
        *extra,
    )


def test_preflight_rejects_commit_mismatch(tmp_path: Path) -> None:
    d13d, d14d, manifest = handoffs(tmp_path)
    payload = json.loads(d13d.read_text(encoding="utf-8"))
    payload["tested_commit"] = OTHER_SHA
    write_json(d13d, payload)

    completed = preflight(tmp_path, d13d, d14d, manifest)

    assert completed.returncode != 0
    assert "tested_commit" in completed.stderr


def test_preflight_rejects_non_frozen_d13d(tmp_path: Path) -> None:
    d13d, d14d, manifest = handoffs(tmp_path)
    payload = json.loads(d13d.read_text(encoding="utf-8"))
    payload["freeze_status"] = "PREPARED"
    write_json(d13d, payload)

    completed = preflight(tmp_path, d13d, d14d, manifest)

    assert completed.returncode != 0
    assert "FROZEN" in completed.stderr


def test_preflight_rejects_non_l3_ready_d14d(tmp_path: Path) -> None:
    d13d, d14d, manifest = handoffs(tmp_path)
    payload = json.loads(d14d.read_text(encoding="utf-8"))
    payload["release_status"] = "ENV_PREPARED"
    write_json(d14d, payload)

    completed = preflight(tmp_path, d13d, d14d, manifest)

    assert completed.returncode != 0
    assert "L3_READY" in completed.stderr


def test_preflight_rejects_an_unlocatable_freeze_reference(tmp_path: Path) -> None:
    d13d, d14d, manifest = handoffs(tmp_path)
    payload = json.loads(d13d.read_text(encoding="utf-8"))
    payload["freeze_reference"] = "not-an-artifact-or-url"
    write_json(d13d, payload)
    repo = tmp_path / "repo"
    repo.mkdir()

    completed = run_script(
        "run_d14b_preflight.py",
        "--expected-tested-commit",
        SHA,
        "--d13d-handoff",
        str(d13d),
        "--d14d-handoff",
        str(d14d),
        "--package-manifest",
        str(manifest),
        "--repo-root",
        str(repo),
        "--evidence-root",
        str(tmp_path / "new-evidence"),
    )

    assert completed.returncode != 0
    assert "freeze_reference" in completed.stderr


def test_preflight_rejects_existing_evidence_root(tmp_path: Path) -> None:
    existing = tmp_path / "existing-evidence"
    existing.mkdir()
    d13d, d14d, manifest = handoffs(tmp_path)

    completed = run_script(
        "run_d14b_preflight.py",
        "--expected-tested-commit",
        SHA,
        "--d13d-handoff",
        str(d13d),
        "--d14d-handoff",
        str(d14d),
        "--package-manifest",
        str(manifest),
        "--repo-root",
        str(tmp_path / "not-reached-on-invalid-root"),
        "--evidence-root",
        str(existing),
    )

    assert completed.returncode != 0
    assert "evidence" in completed.stderr.lower()


def test_preflight_accepts_a_clean_matching_handoff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    for arguments in (
        ["git", "init", "-q", str(repo)],
        ["git", "-C", str(repo), "config", "user.email", "d14b@example.invalid"],
        ["git", "-C", str(repo), "config", "user.name", "D14B test"],
    ):
        subprocess.run(arguments, check=True, capture_output=True, text=True)
    (repo / "README.md").write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "initial"], check=True, capture_output=True, text=True)
    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    d13d, d14d, manifest = handoffs(tmp_path, commit)

    completed = run_script(
        "run_d14b_preflight.py",
        "--expected-tested-commit",
        commit,
        "--d13d-handoff",
        str(d13d),
        "--d14d-handoff",
        str(d14d),
        "--package-manifest",
        str(manifest),
        "--repo-root",
        str(repo),
        "--evidence-root",
        str(tmp_path / "new-evidence"),
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "PASS"


def snapshot(results: list[dict[str, object]]) -> dict[str, object]:
    return {
        "tested_commit": SHA,
        "checkpoint": "baseline",
        "user_id": "d14b-controlled-user",
        "sqlite": {"stable_ids": ["a", "b"], "active_version_ids": ["v1", "v2"]},
        "fts5": {"queries": [{"query_id": "q1", "results": results}]},
        "vector": {"queries": [{"query_id": "q1", "results": results}]},
        "rrf": {"queries": [{"query_id": "q1", "results": results}]},
    }


def compare(tmp_path: Path, before: dict[str, object], after: dict[str, object]) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    before_path = write_json(tmp_path / "before.json", before)
    after_path = write_json(tmp_path / "after.json", after)
    output = tmp_path / "comparison.json"
    completed = run_script(
        "compare_d14b_retrieval_snapshots.py",
        "--before",
        str(before_path),
        "--after",
        str(after_path),
        "--output",
        str(output),
    )
    return completed, json.loads(output.read_text(encoding="utf-8"))


def test_snapshot_detects_missing_id(tmp_path: Path) -> None:
    expected = [{"stable_id": "a", "user_id": "d14b-controlled-user", "version_id": "v1", "rank": 1}]
    completed, report = compare(tmp_path, snapshot(expected), snapshot([]))

    assert completed.returncode != 0
    assert report["missing_ids"]


def test_snapshot_detects_duplicate_id(tmp_path: Path) -> None:
    duplicate = [
        {"stable_id": "a", "user_id": "d14b-controlled-user", "version_id": "v1", "rank": 1},
        {"stable_id": "a", "user_id": "d14b-controlled-user", "version_id": "v1", "rank": 2},
    ]
    completed, report = compare(tmp_path, snapshot(duplicate[:1]), snapshot(duplicate))

    assert completed.returncode != 0
    assert report["duplicate_ids"]


def test_snapshot_detects_cross_user_hit(tmp_path: Path) -> None:
    foreign = [{"stable_id": "a", "user_id": "foreign-user", "version_id": "v1", "rank": 1}]
    completed, report = compare(tmp_path, snapshot([]), snapshot(foreign))

    assert completed.returncode != 0
    assert report["cross_user_hits"]


def test_snapshot_detects_stale_version(tmp_path: Path) -> None:
    stale = [{"stable_id": "a", "user_id": "d14b-controlled-user", "version_id": "stale", "rank": 1}]
    completed, report = compare(tmp_path, snapshot([]), snapshot(stale))

    assert completed.returncode != 0
    assert report["stale_version_hits"]


def test_snapshot_comparison_exact_stable_case(tmp_path: Path) -> None:
    stable = [{"stable_id": "a", "user_id": "d14b-controlled-user", "version_id": "v1", "rank": 1}]
    completed, report = compare(tmp_path, snapshot(stable), snapshot(stable))

    assert completed.returncode == 0, completed.stderr
    assert report["status"] == "PASS"


def test_evidence_manifest_hash_closure(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    payload = root / "baseline.json"
    payload.write_text('{"status":"PREPARED"}\n', encoding="utf-8")
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    (root / "SHA256SUMS").write_text(f"{digest}  baseline.json\n", encoding="utf-8")

    valid = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert valid.returncode == 0, valid.stderr

    (root / "unexpected.log").write_text("unexpected\n", encoding="utf-8")
    invalid = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert invalid.returncode != 0
    assert "未登记" in invalid.stderr
