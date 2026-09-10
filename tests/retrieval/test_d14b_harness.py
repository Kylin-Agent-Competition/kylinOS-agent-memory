"""D14B formal-regression harness L0/L1 contracts.

These tests exercise the published CLI seams only.  They never create a
formal evidence root and do not access a Vector/FTS5 service.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.verify_d14b_evidence_manifest import REQUIRED_CHECKPOINTS

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


def test_committed_formal_handoffs_are_preflight_contract_compatible(tmp_path: Path) -> None:
    d13d_path = REPOSITORY_ROOT / "release/handoff/d13d-handoff.json"
    d14d_path = REPOSITORY_ROOT / "release/handoff/d14d-handoff.json"
    d14d = json.loads(d14d_path.read_text(encoding="utf-8"))
    package_manifest = write_json(
        tmp_path / "package-manifest.json",
        {"source_commit": d14d["tested_commit"], **d14d["package"]},
    )

    completed = run_script(
        "run_d14b_preflight.py",
        "--expected-tested-commit", d14d["tested_commit"],
        "--d13d-handoff", str(d13d_path),
        "--d14d-handoff", str(d14d_path),
        "--package-manifest", str(package_manifest),
        "--tested-repo-root", str(REPOSITORY_ROOT),
        "--control-root", str(REPOSITORY_ROOT),
        "--evidence-root", str(tmp_path / "new-evidence"),
    )

    assert completed.returncode != 0
    assert "tested worktree HEAD 与 tested_commit 不一致" in completed.stderr


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
        "--tested-repo-root",
        str(tmp_path / "not-reached-on-invalid-input"),
        "--control-root",
        str(tmp_path / "not-reached-on-invalid-input"),
        "--evidence-root",
        str(tmp_path / "new-evidence"),
        *extra,
    )


def make_clean_git_repo(path: Path) -> tuple[Path, str]:
    repo = path / "repo"
    repo.mkdir(parents=True)
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
    return repo, commit


def run_preflight_with_repo(
    *, repo: Path, commit: str, d13d: Path, d14d: Path, manifest: Path, evidence_root: Path
) -> subprocess.CompletedProcess[str]:
    return run_script(
        "run_d14b_preflight.py",
        "--expected-tested-commit",
        commit,
        "--d13d-handoff",
        str(d13d),
        "--d14d-handoff",
        str(d14d),
        "--package-manifest",
        str(manifest),
        "--tested-repo-root",
        str(repo),
        "--control-root",
        str(repo),
        "--evidence-root",
        str(evidence_root),
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


def test_preflight_rejects_package_tar_sha_mismatch(tmp_path: Path) -> None:
    d13d, d14d, manifest = handoffs(tmp_path)
    payload = json.loads(d14d.read_text(encoding="utf-8"))
    payload["package"]["package_tar_sha256"] = "d" * 64
    write_json(d14d, payload)

    completed = preflight(tmp_path, d13d, d14d, manifest)

    assert completed.returncode != 0
    assert "package identity" in completed.stderr


def test_preflight_rejects_package_manifest_sha_mismatch(tmp_path: Path) -> None:
    d13d, d14d, manifest = handoffs(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["package_manifest_sha256"] = "d" * 64
    write_json(manifest, payload)

    completed = preflight(tmp_path, d13d, d14d, manifest)

    assert completed.returncode != 0
    assert "package identity" in completed.stderr


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
        "--tested-repo-root",
        str(repo),
        "--control-root",
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
        "--tested-repo-root",
        str(tmp_path / "not-reached-on-invalid-root"),
        "--control-root",
        str(tmp_path / "not-reached-on-invalid-root"),
        "--evidence-root",
        str(existing),
    )

    assert completed.returncode != 0
    assert "evidence" in completed.stderr.lower()


def test_preflight_accepts_a_clean_matching_handoff(tmp_path: Path) -> None:
    case = make_preflight_suite(tmp_path)

    completed = run_script(
        "run_d14b_preflight.py",
        "--expected-tested-commit", case["commit"],
        "--d13d-handoff", str(case["d13d"]),
        "--d14d-handoff", str(case["d14d"]),
        "--package-manifest", str(case["manifest"]),
        "--tested-repo-root", str(case["tested_repo_root"]),
        "--control-root", str(case["repo_root"]),
        "--evidence-root", str(case["evidence_root"]),
        "--capture-handoff", str(case["capture_handoff"]),
        "--package-tar", str(case["package_tar"]),
        "--actual-package-manifest", str(case["actual_package_manifest"]),
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "PASS"


def test_preflight_rejects_a_dirty_worktree(tmp_path: Path) -> None:
    repo, commit = make_clean_git_repo(tmp_path)
    d13d, d14d, manifest = handoffs(tmp_path, commit)
    (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    completed = run_preflight_with_repo(
        repo=repo,
        commit=commit,
        d13d=d13d,
        d14d=d14d,
        manifest=manifest,
        evidence_root=tmp_path / "new-evidence",
    )

    assert completed.returncode != 0
    assert "非干净" in completed.stderr


def test_preflight_rejects_a_head_mismatch(tmp_path: Path) -> None:
    repo, _ = make_clean_git_repo(tmp_path)
    d13d, d14d, manifest = handoffs(tmp_path)

    completed = run_preflight_with_repo(
        repo=repo,
        commit=SHA,
        d13d=d13d,
        d14d=d14d,
        manifest=manifest,
        evidence_root=tmp_path / "new-evidence",
    )

    assert completed.returncode != 0
    assert "HEAD" in completed.stderr


def test_preflight_rejects_a_runner_hash_mismatch(tmp_path: Path) -> None:
    repo, _ = make_clean_git_repo(tmp_path)
    runner = repo / "runner.sh"
    runner.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "runner.sh"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "runner"], check=True, capture_output=True, text=True)
    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    d13d, d14d, manifest = handoffs(tmp_path, commit)
    payload = json.loads(d14d.read_text(encoding="utf-8"))
    payload["runner"] = {"path": "runner.sh", "sha256": "d" * 64}
    write_json(d14d, payload)

    completed = run_preflight_with_repo(
        repo=repo,
        commit=commit,
        d13d=d13d,
        d14d=d14d,
        manifest=manifest,
        evidence_root=tmp_path / "new-evidence",
    )

    assert completed.returncode != 0
    assert "runner SHA-256" in completed.stderr


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


def test_capture_assembles_read_only_channel_artifacts_into_a_checkpoint(tmp_path: Path) -> None:
    case = make_capture_case(tmp_path)
    output = tmp_path / "checkpoint.json"

    completed = run_capture(case, output)

    assert completed.returncode == 0, completed.stderr
    checkpoint = json.loads(output.read_text(encoding="utf-8"))
    assert checkpoint["tested_commit"] == SHA
    assert checkpoint["sqlite"] == {"stable_ids": ["a"], "active_version_ids": ["v1"]}
    assert checkpoint["capture_sources"]["sqlite_truth"]["artifact_sha256"] == case["hashes"]["sqlite_truth"]

def test_capture_rejects_an_existing_checkpoint_without_overwriting_it(tmp_path: Path) -> None:
    truth = write_json(tmp_path / "sqlite-truth.json", {"stable_ids": ["a"], "active_version_ids": ["v1"]})
    channel_result = {"queries": [{"query_id": "q1", "results": []}]}
    fts5 = write_json(tmp_path / "fts5.json", channel_result)
    vector = write_json(tmp_path / "vector.json", channel_result)
    rrf = write_json(tmp_path / "rrf.json", channel_result)
    output = tmp_path / "checkpoint.json"
    output.write_text("preserve-existing-evidence\n", encoding="utf-8")

    completed = run_script(
        "capture_d14b_retrieval_snapshot.py",
        "--tested-commit", SHA,
        "--checkpoint", "baseline",
        "--user-id", "d14b-controlled-user",
        "--captured-at-utc", "2026-09-08T00:00:00Z",
        "--sqlite-truth", str(truth),
        "--fts5-results", str(fts5),
        "--vector-results", str(vector),
        "--rrf-results", str(rrf),
        "--output", str(output),
    )

    assert completed.returncode != 0
    assert output.read_text(encoding="utf-8") == "preserve-existing-evidence\n"


def test_evidence_manifest_hash_closure(tmp_path: Path) -> None:
    root, _ = make_formal_lifecycle_evidence_root(tmp_path)

    valid = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert valid.returncode == 0, valid.stderr

    (root / "unexpected.log").write_text("unexpected\n", encoding="utf-8")
    invalid = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert invalid.returncode != 0
    assert "未登记" in invalid.stderr


def test_evidence_manifest_rejects_missing_duplicate_unsafe_and_mismatched_entries(tmp_path: Path) -> None:
    root, _ = make_formal_lifecycle_evidence_root(tmp_path)
    payload = root / REQUIRED_CHECKPOINTS["baseline"]
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()

    cases = {
        "missing": f"{digest}  missing.json\n",
        "duplicate": f"{digest}  baseline.json\n{digest}  baseline.json\n",
        "absolute": f"{digest}  C:/absolute.json\n",
        "traversal": f"{digest}  ../escape.json\n",
        "sha_mismatch": f"{'0' * 64}  baseline.json\n",
    }
    for name, manifest in cases.items():
        (root / "SHA256SUMS").write_text(manifest, encoding="utf-8")
        completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
        assert completed.returncode != 0, name


def mk_snapshot(
    truth_ids: list[str], versions: list[str], results: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "tested_commit": SHA,
        "checkpoint": "checkpoint",
        "user_id": "d14b-controlled-user",
        "sqlite": {"stable_ids": truth_ids, "active_version_ids": versions},
        "fts5": {"queries": [{"query_id": "q1", "results": results}]},
        "vector": {"queries": [{"query_id": "q1", "results": results}]},
        "rrf": {"queries": [{"query_id": "q1", "results": results}]},
    }


BASE_RESULT = {"stable_id": "a", "user_id": "d14b-controlled-user", "version_id": "v1", "rank": 1}


def test_snapshot_fails_when_non_topk_stable_id_disappears(tmp_path: Path) -> None:
    """before/after retrieval identical, but truth loses a non-Top-K stable id."""
    result = [BASE_RESULT]
    before = mk_snapshot(["a", "b", "c"], ["v1"], result)
    after = mk_snapshot(["a", "b"], ["v1"], result)

    completed, report = compare(tmp_path, before, after)

    assert completed.returncode != 0
    assert report["sqlite_missing_stable_ids"] == ["c"]
    assert report["missing_ids"] == []
    assert report["status"] == "FAIL"


def test_snapshot_fails_when_non_topk_stable_id_appears(tmp_path: Path) -> None:
    result = [BASE_RESULT]
    before = mk_snapshot(["a", "b"], ["v1"], result)
    after = mk_snapshot(["a", "b", "c"], ["v1"], result)

    completed, report = compare(tmp_path, before, after)

    assert completed.returncode != 0
    assert report["sqlite_unexpected_stable_ids"] == ["c"]
    assert report["status"] == "FAIL"


def test_snapshot_fails_when_active_version_disappears(tmp_path: Path) -> None:
    result = [BASE_RESULT]
    before = mk_snapshot(["a"], ["v1", "v2"], result)
    after = mk_snapshot(["a"], ["v1"], result)

    completed, report = compare(tmp_path, before, after)

    assert completed.returncode != 0
    assert report["sqlite_missing_active_version_ids"] == ["v2"]
    assert report["status"] == "FAIL"


def test_snapshot_fails_when_active_version_appears(tmp_path: Path) -> None:
    result = [BASE_RESULT]
    before = mk_snapshot(["a"], ["v1"], result)
    after = mk_snapshot(["a"], ["v1", "v2"], result)

    completed, report = compare(tmp_path, before, after)

    assert completed.returncode != 0
    assert report["sqlite_unexpected_active_version_ids"] == ["v2"]
    assert report["status"] == "FAIL"


def test_snapshot_fails_on_duplicate_before_baseline(tmp_path: Path) -> None:
    duplicate = [BASE_RESULT, dict(BASE_RESULT)]
    snapshot = mk_snapshot(["a"], ["v1"], duplicate)

    completed, report = compare(tmp_path, snapshot, snapshot)

    assert completed.returncode != 0
    assert any(entry.get("side") == "before" for entry in report["duplicate_ids"])


def test_snapshot_fails_on_cross_user_before_baseline(tmp_path: Path) -> None:
    cross_user = [dict(BASE_RESULT, user_id="d14b-other-user")]
    snapshot = mk_snapshot(["a"], ["v1"], cross_user)

    completed, report = compare(tmp_path, snapshot, snapshot)

    assert completed.returncode != 0
    assert any(entry.get("side") == "before" for entry in report["cross_user_hits"])


def test_snapshot_fails_on_stale_version_before_baseline(tmp_path: Path) -> None:
    stale = [dict(BASE_RESULT, version_id="v9")]
    snapshot = mk_snapshot(["a"], ["v1"], stale)

    completed, report = compare(tmp_path, snapshot, snapshot)

    assert completed.returncode != 0
    assert any(entry.get("side") == "before" for entry in report["stale_version_hits"])


def test_snapshot_fails_on_ghost_before_baseline(tmp_path: Path) -> None:
    ghost = [dict(BASE_RESULT, stable_id="zz")]
    snapshot = mk_snapshot(["a"], ["v1"], ghost)

    completed, report = compare(tmp_path, snapshot, snapshot)

    assert completed.returncode != 0
    assert any(entry.get("side") == "before" for entry in report["ghost_hits"])


def test_compare_rejects_existing_output_without_overwriting(tmp_path: Path) -> None:
    snapshot = mk_snapshot(["a"], ["v1"], [BASE_RESULT])
    before_path = write_json(tmp_path / "before.json", snapshot)
    after_path = write_json(tmp_path / "after.json", snapshot)
    output = tmp_path / "comparison.json"
    output.write_text("fixed-bytes-sentinel\n", encoding="utf-8")

    completed = run_script(
        "compare_d14b_retrieval_snapshots.py",
        "--before", str(before_path),
        "--after", str(after_path),
        "--output", str(output),
    )

    assert completed.returncode != 0
    assert "不得覆盖" in completed.stderr
    assert output.read_text(encoding="utf-8") == "fixed-bytes-sentinel\n"

# ─────────────────────────── P1-3 / P2-1 provenance & package tests ──────────

def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def make_capture_case(
    tmp_path: Path,
    *,
    missing_handoff: bool = False,
    omit_receipts: tuple[str, ...] = (),
    handoff_channels: tuple[str, ...] = ("sqlite_truth", "fts5", "vector", "rrf"),
    receipt_overrides: dict[str, dict[str, object]] | None = None,
    tamper_artifact: str | None = None,
) -> dict[str, object]:
    channel_result = {
        "queries": [
            {
                "query_id": "q1",
                "results": [
                    {"stable_id": "a", "user_id": "d14b-controlled-user", "version_id": "v1", "rank": 1}
                ],
            }
        ]
    }
    truth = {"stable_ids": ["a"], "active_version_ids": ["v1"]}
    artifacts = {
        "sqlite_truth": write_json(tmp_path / "sqlite-truth.json", truth),
        "fts5": write_json(tmp_path / "fts5.json", channel_result),
        "vector": write_json(tmp_path / "vector.json", channel_result),
        "rrf": write_json(tmp_path / "rrf.json", channel_result),
    }
    hashes = {ch: sha256_bytes(path.read_bytes()) for ch, path in artifacts.items()}
    handoff_path: Path | None = None
    if not missing_handoff:
        handoff_path = write_json(
            tmp_path / "capture-handoff.json",
            {
                "tested_commit": SHA,
                "captures": {
                    ch: {
                        "runner_path": f"runner_{ch}.py",
                        "runner_sha256": HASH,
                        "command_id": f"d14b-{ch}-v1",
                    }
                    for ch in handoff_channels
                },
            },
        )

    receipts: dict[str, Path] = {}
    for ch in ("sqlite_truth", "fts5", "vector", "rrf"):
        if ch in omit_receipts:
            receipts[ch] = tmp_path / f"{ch}.receipt.json"
            continue
        overrides = (receipt_overrides or {}).get(ch, {})
        receipt = {
            "channel": ch,
            "tested_commit": overrides.get("tested_commit", SHA),
            "command_id": overrides.get("command_id", f"d14b-{ch}-v1"),
            "runner_path": overrides.get("runner_path", f"runner_{ch}.py"),
            "runner_sha256": overrides.get("runner_sha256", HASH),
            "artifact_path": artifacts[ch].name,
            "artifact_sha256": hashes[ch],
            "captured_at_utc": "2026-09-08T00:00:00Z",
        }
        if ch == "rrf":
            receipt["fts5_input_sha256"] = hashes["fts5"]
            receipt["vector_input_sha256"] = hashes["vector"]
        receipts[ch] = write_json(tmp_path / f"{ch}.receipt.json", receipt)
    if tamper_artifact is not None:
        path = artifacts[tamper_artifact]
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    return {
        "artifacts": artifacts,
        "hashes": hashes,
        "handoff": handoff_path,
        "receipts": receipts,
    }


def run_capture(case: dict[str, object], output: Path) -> subprocess.CompletedProcess[str]:
    args: list[str] = [
        "--tested-commit", SHA,
        "--checkpoint", "baseline",
        "--user-id", "d14b-controlled-user",
        "--captured-at-utc", "2026-09-08T00:00:00Z",
    ]
    if case["handoff"] is not None:
        args += ["--capture-handoff", str(case["handoff"])]
    artifacts = case["artifacts"]
    receipts = case["receipts"]
    args += ["--sqlite-truth", str(artifacts["sqlite_truth"])]
    args += ["--fts5-results", str(artifacts["fts5"])]
    args += ["--vector-results", str(artifacts["vector"])]
    args += ["--rrf-results", str(artifacts["rrf"])]
    args += ["--sqlite-receipt", str(receipts["sqlite_truth"])]
    args += ["--fts5-receipt", str(receipts["fts5"])]
    args += ["--vector-receipt", str(receipts["vector"])]
    args += ["--rrf-receipt", str(receipts["rrf"])]
    args += ["--output", str(output)]
    return run_script("capture_d14b_retrieval_snapshot.py", *args)


def test_capture_requires_capture_handoff(tmp_path: Path) -> None:
    case = make_capture_case(tmp_path, missing_handoff=True)
    completed = run_capture(case, tmp_path / "checkpoint.json")
    assert completed.returncode != 0
    assert "capture-handoff" in completed.stderr


def test_capture_requires_a_receipt_for_every_channel(tmp_path: Path) -> None:
    case = make_capture_case(tmp_path, omit_receipts=("sqlite_truth", "fts5", "vector", "rrf"))
    completed = run_capture(case, tmp_path / "checkpoint.json")
    assert completed.returncode != 0
    assert "receipt" in completed.stderr


def test_capture_accepts_valid_handoff_and_receipts(tmp_path: Path) -> None:
    case = make_capture_case(tmp_path)
    output = tmp_path / "checkpoint.json"
    completed = run_capture(case, output)
    assert completed.returncode == 0, completed.stderr
    checkpoint = json.loads(output.read_text(encoding="utf-8"))
    assert checkpoint["sqlite"] == {"stable_ids": ["a"], "active_version_ids": ["v1"]}


def test_capture_rejects_receipt_tested_commit_mismatch(tmp_path: Path) -> None:
    case = make_capture_case(tmp_path, receipt_overrides={"fts5": {"tested_commit": OTHER_SHA}})
    completed = run_capture(case, tmp_path / "checkpoint.json")
    assert completed.returncode != 0
    assert "tested_commit" in completed.stderr


def test_capture_rejects_receipt_runner_sha_mismatch(tmp_path: Path) -> None:
    case = make_capture_case(tmp_path, receipt_overrides={"vector": {"runner_sha256": "d" * 64}})
    completed = run_capture(case, tmp_path / "checkpoint.json")
    assert completed.returncode != 0
    assert "runner_sha256" in completed.stderr


def test_capture_rejects_receipt_command_id_mismatch(tmp_path: Path) -> None:
    case = make_capture_case(tmp_path, receipt_overrides={"rrf": {"command_id": "wrong-command"}})
    completed = run_capture(case, tmp_path / "checkpoint.json")
    assert completed.returncode != 0
    assert "command_id" in completed.stderr


def test_capture_rejects_tampered_artifact_bytes(tmp_path: Path) -> None:
    case = make_capture_case(tmp_path, tamper_artifact="sqlite_truth")
    completed = run_capture(case, tmp_path / "checkpoint.json")
    assert completed.returncode != 0
    assert "artifact_sha256" in completed.stderr


def make_preflight_suite(tmp_path: Path) -> dict[str, object]:
    tested_repo, tested_commit = make_clean_git_repo(tmp_path / "tested")
    repo, _ = make_clean_git_repo(tmp_path)
    runner_shas: dict[str, str] = {}
    for channel in ("sqlite_truth", "fts5", "vector", "rrf"):
        runner = repo / f"runner_{channel}.py"
        runner.write_text(f"#!/usr/bin/env python3\n# {channel} runner\n", encoding="utf-8")
        runner_shas[channel] = sha256_bytes(runner.read_bytes())
    query_spec = repo / "d14b-queries.json"
    query_spec.write_text(
        json.dumps({"queries": [{"query_id": "q1", "match": "control", "vector": [0.0]}]}),
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "runners"], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    )
    commit = tested_commit
    commit = tested_commit

    capture_handoff = write_json(
        tmp_path / "capture-handoff.json",
        {
            "tested_commit": tested_commit,
            "captures": {
                channel: {
                    "runner_path": f"runner_{channel}.py",
                    "runner_sha256": runner_shas[channel],
                    "command_id": f"d14b-{channel}-v1",
                    }
                for channel in ("sqlite_truth", "fts5", "vector", "rrf")
            },
            "source_bindings": {
                "sqlite_truth": {"production_db_path": "/home/kylin-agent/.local/share/kylin-memory/kylin_memory.db"},
                "fts5": {
                    "production_db_path": "/home/kylin-agent/.local/share/kylin-memory/kylin_memory.db",
                    "query_spec_path": "d14b-queries.json",
                    "query_spec_sha256": sha256_bytes(query_spec.read_bytes()),
                },
                "vector": {
                    "production_db_path": "/home/kylin-agent/.local/share/kylin-memory/kylin_memory.db",
                    "query_spec_path": "d14b-queries.json",
                    "query_spec_sha256": sha256_bytes(query_spec.read_bytes()),
                    "vector_cli_path": "/opt/kylin/bin/vector_cli",
                    "vector_cli_sha256": HASH,
                },
                "rrf": {"production_db_path": "/home/kylin-agent/.local/share/kylin-memory/kylin_memory.db"},
            },
        },
    )

    package_tar = tmp_path / "package.tar.gz"
    package_tar.write_bytes(b"frozen-package-tar-bytes\n")
    tar_sha = sha256_bytes(package_tar.read_bytes())
    actual_manifest = tmp_path / "package_manifest.json"
    manifest_value = {
        "source_commit": commit,
        "package_version": "0.1.0-d14a",
        "package_tar_sha256": tar_sha,
    }
    actual_manifest.write_text(json.dumps(manifest_value), encoding="utf-8")
    manifest_sha = sha256_bytes(actual_manifest.read_bytes())
    manifest_value["package_manifest_sha256"] = manifest_sha
    actual_manifest.write_text(json.dumps(manifest_value), encoding="utf-8")
    manifest_sha = sha256_bytes(actual_manifest.read_bytes())

    package = {
        "package_version": "0.1.0-d14a",
        "package_tar_sha256": tar_sha,
        "package_manifest_sha256": manifest_sha,
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
        {"freeze_status": "FROZEN", "tested_commit": commit,
         "freeze_reference": "https://evidence.example.invalid/d13d-seal"},
    )
    d14d = write_json(
        tmp_path / "d14d.json",
        {"release_status": "L3_READY", "tested_commit": commit,
         "evidence_reference": "https://evidence.example.invalid/d14d-g9",
         "package": package, "vm": vm},
    )
    manifest = write_json(tmp_path / "manifest.json", {"source_commit": commit, **package})
    return {
        "repo_root": repo,
        "tested_repo_root": tested_repo,
        "commit": commit,
        "d13d": d13d,
        "d14d": d14d,
        "manifest": manifest,
        "capture_handoff": capture_handoff,
        "package_tar": package_tar,
        "actual_package_manifest": actual_manifest,
        "evidence_root": tmp_path / "new-evidence",
        "runner_paths": {channel: repo / f"runner_{channel}.py" for channel in ("sqlite_truth", "fts5", "vector", "rrf")},
    }


def resync_package_manifest_sha(case: dict[str, object]) -> None:
    """Point the handoff identity at the (modified) actual manifest bytes so a
    test can exercise a semantic mismatch instead of the byte gate."""
    new_sha = sha256_bytes(case["actual_package_manifest"].read_bytes())
    for key in ("d14d", "manifest"):
        payload = json.loads(case[key].read_text(encoding="utf-8"))
        if key == "d14d":
            payload["package"]["package_manifest_sha256"] = new_sha
        else:
            payload["package_manifest_sha256"] = new_sha
        write_json(case[key], payload)


def run_preflight_suite(
    case: dict[str, object], *, extra: tuple[str, ...] = ()
) -> subprocess.CompletedProcess[str]:
    return run_script(
        "run_d14b_preflight.py",
        "--expected-tested-commit", str(case["commit"]),
        "--d13d-handoff", str(case["d13d"]),
        "--d14d-handoff", str(case["d14d"]),
        "--package-manifest", str(case["manifest"]),
        "--tested-repo-root", str(case["tested_repo_root"]),
        "--control-root", str(case["repo_root"]),
        "--evidence-root", str(case["evidence_root"]),
        "--capture-handoff", str(case["capture_handoff"]),
        "--package-tar", str(case["package_tar"]),
        "--actual-package-manifest", str(case["actual_package_manifest"]),
        *extra,
    )


def test_preflight_rejects_missing_capture_handoff(tmp_path: Path) -> None:
    case = make_preflight_suite(tmp_path)
    completed = run_script(
        "run_d14b_preflight.py",
        "--expected-tested-commit", str(case["commit"]),
        "--d13d-handoff", str(case["d13d"]),
        "--d14d-handoff", str(case["d14d"]),
        "--package-manifest", str(case["manifest"]),
        "--tested-repo-root", str(case["tested_repo_root"]),
        "--control-root", str(case["repo_root"]),
        "--evidence-root", str(case["evidence_root"]),
    )
    assert completed.returncode != 0
    assert "capture-handoff" in completed.stderr


def test_preflight_rejects_missing_one_channel_runner(tmp_path: Path) -> None:
    case = make_preflight_suite(tmp_path)
    handoff = json.loads(case["capture_handoff"].read_text(encoding="utf-8"))
    del handoff["captures"]["rrf"]
    write_json(case["capture_handoff"], handoff)

    completed = run_preflight_suite(case)

    assert completed.returncode != 0
    assert "rrf" in completed.stderr


def test_preflight_rejects_missing_runner_file(tmp_path: Path) -> None:
    case = make_preflight_suite(tmp_path)
    handoff = json.loads(case["capture_handoff"].read_text(encoding="utf-8"))
    handoff["captures"]["sqlite_truth"]["runner_path"] = "missing_runner.py"
    write_json(case["capture_handoff"], handoff)

    completed = run_preflight_suite(case)

    assert completed.returncode != 0
    assert "不可定位" in completed.stderr


def test_preflight_rejects_runner_sha_mismatch_in_handoff(tmp_path: Path) -> None:
    case = make_preflight_suite(tmp_path)
    handoff = json.loads(case["capture_handoff"].read_text(encoding="utf-8"))
    handoff["captures"]["fts5"]["runner_sha256"] = "d" * 64
    write_json(case["capture_handoff"], handoff)

    completed = run_preflight_suite(case)

    assert completed.returncode != 0
    assert "runner_sha256" in completed.stderr


def test_preflight_rejects_tampered_package_tar(tmp_path: Path) -> None:
    case = make_preflight_suite(tmp_path)
    case["package_tar"].write_bytes(b"tampered-tar\n")

    completed = run_preflight_suite(case)

    assert completed.returncode != 0
    assert "tar SHA-256" in completed.stderr


def test_preflight_rejects_tampered_package_manifest(tmp_path: Path) -> None:
    case = make_preflight_suite(tmp_path)
    case["actual_package_manifest"].write_text('{"tampered": true}\n', encoding="utf-8")

    completed = run_preflight_suite(case)

    assert completed.returncode != 0
    assert "manifest SHA-256" in completed.stderr


def test_preflight_rejects_package_manifest_source_commit_mismatch(tmp_path: Path) -> None:
    case = make_preflight_suite(tmp_path)
    manifest = json.loads(case["actual_package_manifest"].read_text(encoding="utf-8"))
    manifest["source_commit"] = OTHER_SHA
    case["actual_package_manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    resync_package_manifest_sha(case)
    completed = run_preflight_suite(case)
    assert completed.returncode != 0
    assert "source_commit" in completed.stderr


def test_preflight_rejects_package_manifest_version_mismatch(tmp_path: Path) -> None:
    case = make_preflight_suite(tmp_path)
    manifest = json.loads(case["actual_package_manifest"].read_text(encoding="utf-8"))
    manifest["package_version"] = "9.9.9"
    case["actual_package_manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    resync_package_manifest_sha(case)
    completed = run_preflight_suite(case)
    assert completed.returncode != 0
    assert "package_version" in completed.stderr

# ─────────────────── R3 provenance retention + docs/CLI smoke ──────────────

def test_checkpoint_records_handoff_and_receipt_provenance(tmp_path: Path) -> None:
    case = make_capture_case(tmp_path)
    output = tmp_path / "checkpoint.json"
    completed = run_capture(case, output)
    assert completed.returncode == 0, completed.stderr
    checkpoint = json.loads(output.read_text(encoding="utf-8"))
    sources = checkpoint["capture_sources"]
    assert sources["capture_handoff_sha256"] == sha256_bytes(case["handoff"].read_bytes())
    for channel in ("sqlite_truth", "fts5", "vector", "rrf"):
        entry = sources[channel]
        assert entry["artifact_sha256"] == sha256_bytes(case["artifacts"][channel].read_bytes())
        assert entry["receipt_sha256"] == sha256_bytes(case["receipts"][channel].read_bytes())
        assert entry["command_id"] == f"d14b-{channel}-v1"
        assert entry["runner_sha256"] == HASH


def write_evidence_manifest(root: Path) -> None:
    entries = [
        f"{sha256_bytes(path.read_bytes())}  {path.relative_to(root).as_posix()}"
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS"
    ]
    (root / "SHA256SUMS").write_text("\n".join(entries) + "\n", encoding="utf-8")


def symlink_or_skip(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link)
    except OSError as error:
        pytest.skip(f"当前平台不允许创建 symlink: {error}")


def make_formal_lifecycle_evidence_root(
    tmp_path: Path,
) -> tuple[Path, dict[str, dict[str, Path]]]:
    root = tmp_path / "evidence"
    (root / "provenance").mkdir(parents=True)
    handoff = root / "provenance" / "d14b-capture-handoff.json"
    captures = {
        channel: {
            "command_id": f"d14b-{channel}-v1",
            "runner_path": f"runner_{channel}.py",
            "runner_sha256": HASH,
        }
        for channel in ("sqlite_truth", "fts5", "vector", "rrf")
    }
    handoff.write_text(json.dumps({"tested_commit": SHA, "captures": captures}), encoding="utf-8")
    receipt_names = {
        "sqlite_truth": "sqlite-truth.receipt.json",
        "fts5": "fts5-results.receipt.json",
        "vector": "vector-results.receipt.json",
        "rrf": "rrf-results.receipt.json",
    }
    receipts: dict[str, dict[str, Path]] = {}
    for checkpoint_id, relative_path in REQUIRED_CHECKPOINTS.items():
        checkpoint = root / relative_path
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        receipt_dir = checkpoint.parent / "provenance" / checkpoint_id
        receipt_dir.mkdir(parents=True)
        checkpoint_receipts: dict[str, Path] = {}
        sources: dict[str, object] = {
            "capture_handoff_sha256": sha256_bytes(handoff.read_bytes()),
        }
        for channel in ("sqlite_truth", "fts5", "vector", "rrf"):
            receipt = receipt_dir / receipt_names[channel]
            artifact = root / f"{checkpoint_id}-{channel}.artifact.json"
            artifact.write_text(json.dumps({"channel": channel}), encoding="utf-8")
            receipt.write_text(
                json.dumps({
                    "tested_commit": SHA,
                    **captures[channel],
                    "artifact_sha256": sha256_bytes(artifact.read_bytes()),
                }),
                encoding="utf-8",
            )
            if channel == "rrf":
                payload = json.loads(receipt.read_text(encoding="utf-8"))
                payload["fts5_input_sha256"] = sha256_bytes(
                    (root / f"{checkpoint_id}-fts5.artifact.json").read_bytes()
                )
                payload["vector_input_sha256"] = sha256_bytes(
                    (root / f"{checkpoint_id}-vector.artifact.json").read_bytes()
                )
                receipt.write_text(json.dumps(payload), encoding="utf-8")
            checkpoint_receipts[channel] = receipt
            sources[channel] = {
                "receipt_sha256": sha256_bytes(receipt.read_bytes()),
                **captures[channel],
                "artifact_sha256": sha256_bytes(artifact.read_bytes()),
            }
            if channel == "rrf":
                sources[channel]["fts5_input_sha256"] = sha256_bytes(
                    (root / f"{checkpoint_id}-fts5.artifact.json").read_bytes()
                )
                sources[channel]["vector_input_sha256"] = sha256_bytes(
                    (root / f"{checkpoint_id}-vector.artifact.json").read_bytes()
                )
        checkpoint.write_text(
            json.dumps({
                "tested_commit": SHA,
                "checkpoint": checkpoint_id,
                "captured_at_utc": "2026-09-09T00:00:00Z",
                "user_id": "d14b-controlled-user",
                "capture_sources": sources,
                "sqlite": {},
                "fts5": {},
                "vector": {},
                "rrf": {},
            }),
            encoding="utf-8",
        )
        receipts[checkpoint_id] = checkpoint_receipts
    write_evidence_manifest(root)
    return root, receipts


def test_evidence_verifier_rejects_missing_required_receipt_even_with_regenerated_manifest(
    tmp_path: Path,
) -> None:
    root, receipts = make_formal_lifecycle_evidence_root(tmp_path)

    completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert completed.returncode == 0, completed.stderr

    receipts["baseline"]["fts5"].unlink()
    write_evidence_manifest(root)
    missing = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert missing.returncode != 0


def test_evidence_verifier_rejects_missing_handoff_even_with_regenerated_manifest(
    tmp_path: Path,
) -> None:
    root, _ = make_formal_lifecycle_evidence_root(tmp_path)

    (root / "provenance" / "d14b-capture-handoff.json").unlink()
    write_evidence_manifest(root)

    completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert completed.returncode != 0
    assert "handoff" in completed.stderr


def test_evidence_verifier_rejects_tampered_receipt_with_regenerated_manifest(
    tmp_path: Path,
) -> None:
    root, receipts = make_formal_lifecycle_evidence_root(tmp_path)

    receipt = json.loads(receipts["baseline"]["vector"].read_text(encoding="utf-8"))
    receipt["artifact_sha256"] = "d" * 64
    write_json(receipts["baseline"]["vector"], receipt)
    write_evidence_manifest(root)

    completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert completed.returncode != 0
    assert "receipt SHA-256" in completed.stderr


def test_evidence_verifier_rejects_tampered_handoff_with_regenerated_manifest(
    tmp_path: Path,
) -> None:
    root, _ = make_formal_lifecycle_evidence_root(tmp_path)

    handoff = root / "provenance" / "d14b-capture-handoff.json"
    payload = json.loads(handoff.read_text(encoding="utf-8"))
    payload["tested_commit"] = OTHER_SHA
    write_json(handoff, payload)
    write_evidence_manifest(root)

    completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert completed.returncode != 0
    assert "handoff SHA-256" in completed.stderr


def test_evidence_verifier_rejects_runner_metadata_semantic_mismatch(
    tmp_path: Path,
) -> None:
    root, receipts = make_formal_lifecycle_evidence_root(tmp_path)

    receipt = json.loads(receipts["baseline"]["rrf"].read_text(encoding="utf-8"))
    receipt["runner_sha256"] = "d" * 64
    write_json(receipts["baseline"]["rrf"], receipt)
    checkpoint = root / REQUIRED_CHECKPOINTS["baseline"]
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    payload["capture_sources"]["rrf"]["receipt_sha256"] = sha256_bytes(receipts["baseline"]["rrf"].read_bytes())
    write_json(checkpoint, payload)
    write_evidence_manifest(root)

    completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert completed.returncode != 0
    assert "runner_sha256" in completed.stderr


def test_evidence_verifier_rejects_rrf_parent_artifact_substitution(
    tmp_path: Path,
) -> None:
    root, receipts = make_formal_lifecycle_evidence_root(tmp_path)

    receipt = json.loads(receipts["baseline"]["rrf"].read_text(encoding="utf-8"))
    receipt["fts5_input_sha256"] = "d" * 64
    write_json(receipts["baseline"]["rrf"], receipt)
    checkpoint = root / REQUIRED_CHECKPOINTS["baseline"]
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    payload["capture_sources"]["rrf"]["fts5_input_sha256"] = "d" * 64
    payload["capture_sources"]["rrf"]["receipt_sha256"] = sha256_bytes(
        receipts["baseline"]["rrf"].read_bytes()
    )
    write_json(checkpoint, payload)
    write_evidence_manifest(root)

    completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert completed.returncode != 0
    assert "fts5_input_sha256" in completed.stderr


def test_evidence_verifier_rejects_weakened_checkpoint_schema_even_with_regenerated_manifest(
    tmp_path: Path,
) -> None:
    root, receipts = make_formal_lifecycle_evidence_root(tmp_path)
    checkpoint = root / REQUIRED_CHECKPOINTS["baseline"]
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    del payload["capture_sources"]
    write_json(checkpoint, payload)
    for receipt in receipts["baseline"].values():
        receipt.unlink()
    write_evidence_manifest(root)

    completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert completed.returncode != 0


def test_evidence_verifier_rejects_missing_required_lifecycle_checkpoint(tmp_path: Path) -> None:
    root, _ = make_formal_lifecycle_evidence_root(tmp_path)
    (root / REQUIRED_CHECKPOINTS["rebuild_after"]).unlink()
    write_evidence_manifest(root)

    completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert completed.returncode != 0
    assert "rebuild_after" in completed.stderr


def test_evidence_verifier_rejects_checkpoint_id_mismatch(tmp_path: Path) -> None:
    root, _ = make_formal_lifecycle_evidence_root(tmp_path)
    checkpoint = root / REQUIRED_CHECKPOINTS["delete_before"]
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    payload["checkpoint"] = "baseline"
    write_json(checkpoint, payload)
    write_evidence_manifest(root)

    completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert completed.returncode != 0
    assert "固定路径" in completed.stderr


def test_evidence_verifier_rejects_checkpoint_tested_commit_drift(tmp_path: Path) -> None:
    root, _ = make_formal_lifecycle_evidence_root(tmp_path)
    checkpoint = root / REQUIRED_CHECKPOINTS["reboot_after"]
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    payload["tested_commit"] = OTHER_SHA
    write_json(checkpoint, payload)
    write_evidence_manifest(root)

    completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert completed.returncode != 0
    assert "tested_commit" in completed.stderr


def test_evidence_verifier_rejects_missing_checkpoint_channel(tmp_path: Path) -> None:
    root, _ = make_formal_lifecycle_evidence_root(tmp_path)
    checkpoint = root / REQUIRED_CHECKPOINTS["delete_after"]
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    del payload["rrf"]
    write_json(checkpoint, payload)
    write_evidence_manifest(root)

    completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert completed.returncode != 0
    assert "rrf" in completed.stderr


def test_evidence_verifier_rejects_non_object_capture_sources(tmp_path: Path) -> None:
    root, _ = make_formal_lifecycle_evidence_root(tmp_path)
    checkpoint = root / REQUIRED_CHECKPOINTS["service_restart_after"]
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    payload["capture_sources"] = None
    write_json(checkpoint, payload)
    write_evidence_manifest(root)

    completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert completed.returncode != 0
    assert "capture_sources" in completed.stderr


def test_evidence_verifier_rejects_symlinked_evidence_file(tmp_path: Path) -> None:
    root, _ = make_formal_lifecycle_evidence_root(tmp_path)
    target = root / "target.json"
    target.write_text('{"target": true}\n', encoding="utf-8")
    symlink_or_skip(root / "linked.json", target)
    write_evidence_manifest(root)

    completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert completed.returncode != 0
    assert "symlink" in completed.stderr


def test_evidence_verifier_rejects_symlinked_manifest(tmp_path: Path) -> None:
    root, _ = make_formal_lifecycle_evidence_root(tmp_path)
    manifest = root / "SHA256SUMS"
    target = tmp_path / "manifest-target.txt"
    target.write_bytes(manifest.read_bytes())
    manifest.unlink()
    symlink_or_skip(manifest, target)

    completed = run_script("verify_d14b_evidence_manifest.py", "--evidence-root", str(root))
    assert completed.returncode != 0
    assert "SHA256SUMS" in completed.stderr


def test_formal_docs_are_in_sync_with_preflight_cli(tmp_path: Path) -> None:
    docs = (
        REPOSITORY_ROOT / "docs/day14/15_d14b_l3_formal_harness_contract_20260907.md",
        REPOSITORY_ROOT / "docs/day14/16_d14b_formal_execution_runbook.md",
    )
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        for flag in (
            "--expected-tested-commit",
            "--d13d-handoff",
            "--d14d-handoff",
            "--package-manifest",
            "--tested-repo-root",
            "--control-root",
            "--evidence-root",
            "--capture-handoff",
            "--package-tar",
            "--actual-package-manifest",
        ):
            assert flag in text, f"{doc.name} missing {flag}"
    help_run = run_script("run_d14b_preflight.py", "--help")
    assert help_run.returncode == 0
    for flag in (
        "--capture-handoff",
        "--package-tar",
        "--actual-package-manifest",
        "--evidence-root",
    ):
        assert flag in help_run.stdout


def test_formal_docs_capture_examples_match_current_cli(tmp_path: Path) -> None:
    docs = (
        REPOSITORY_ROOT / "docs/day14/15_d14b_l3_formal_harness_contract_20260907.md",
        REPOSITORY_ROOT / "docs/day14/16_d14b_formal_execution_runbook.md",
    )
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        for flag in (
            "--capture-handoff",
            "--sqlite-receipt",
            "--fts5-receipt",
            "--vector-receipt",
            "--rrf-receipt",
        ):
            assert flag in text, f"{doc.name} missing {flag}"
    help_run = run_script("capture_d14b_retrieval_snapshot.py", "--help")
    assert help_run.returncode == 0
    for flag in (
        "--capture-handoff",
        "--sqlite-receipt",
        "--fts5-receipt",
        "--vector-receipt",
        "--rrf-receipt",
    ):
        assert flag in help_run.stdout


def test_formal_docs_list_all_required_lifecycle_checkpoint_paths(tmp_path: Path) -> None:
    docs = (
        REPOSITORY_ROOT / "docs/day14/15_d14b_l3_formal_harness_contract_20260907.md",
        REPOSITORY_ROOT / "docs/day14/16_d14b_formal_execution_runbook.md",
    )
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        for relative_path in REQUIRED_CHECKPOINTS.values():
            assert relative_path in text, f"{doc.name} missing required checkpoint path: {relative_path}"


def test_preflight_docs_evidence_root_lines_continue(tmp_path: Path) -> None:
    docs = (
        REPOSITORY_ROOT / "docs/day14/15_d14b_l3_formal_harness_contract_20260907.md",
        REPOSITORY_ROOT / "docs/day14/16_d14b_formal_execution_runbook.md",
    )
    canonical = "  --evidence-root <absolute-new-root> \\"
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        assert canonical in text, f"{doc.name}: preflight --evidence-root 行必须存在且以 \\ 续行"
