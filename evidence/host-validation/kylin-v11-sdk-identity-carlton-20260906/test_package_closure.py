"""Self-verification for the INDEPENDENT_KYLIN_HOST_VALIDATION evidence package.

Modes (selected purely by checksums.txt presence):

- SEAL: checksums.txt is missing. The package is re-sealed deterministically from
  the current full file set (stable sort, ``<sha256>  <relative_path>`` lines).
- VERIFY: checksums.txt exists. Every entry is verified read-only against the
  current full file set. Any content drift FAILS; checksums.txt is never silently
  rewritten in this mode.

Raw integrity: any ``raw/<name>`` file that is missing, or whose hash does not
match SOURCE_SHA256_EXPECTED, is re-copied in bytes mode from the read-only source
evidence root. The source hash must equal SOURCE_SHA256_EXPECTED and the target
hash must equal both; otherwise the test FAILS (fail-closed, no new hashes adopted).

L0 and L1 use the exact same invocation and must exit 0 with no skips:

    python3 -m pytest evidence/host-validation/kylin-v11-sdk-identity-carlton-20260906/test_package_closure.py -q
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent

# Read-only source evidence root on the Windows Desktop (never modified by this task).
SOURCE_EVIDENCE_ROOT = Path("/mnt/c/Users/Carlton Benzol/Desktop/d14d-env-prepared-20260906-r2")

# Supervisor read-only verified SOURCE_SHA256_EXPECTED (matches the source bytes
# byte-for-byte). Never auto-adopted: if a source file does not match, the test FAILS.
SOURCE_SHA256_EXPECTED = {
    "r2_clean_gate.log": "ee9e83e4dc9bc46ec4da36a4ac0d173ae1d20bcf999e377b293d510bcab16e02",
    "r2_clean_gate_strict.log": "7fded644f2e153ea3f2f98782a2aeee4f208084bdc028d41bb3dd681d586bb10",
    "r2_dependencies.log": "0f1cfd1db598e306f814b2c87842632bc996f5bfcc8e26a6f1fbe0ea5a7424a6",
    "r2_environment.log": "8e5e898428c3ebaa775833c7bcd927295cc774f53dfcf16020af40d63e64893b",
    "r2_final_clean_gate.log": "dbbd708d7d2400cf871ef812d699b9913031022f2bee13c017c75b19915703da",
    "r2_host_final_state.log": "a9a43892c03f8d248d776f8d8b10ebbc53bd106c188e02fed4ec90add41a6098",
    "r2_host_final_state_after_gate.log": "45d5ccb00a704d1b40b22c34e3f05ac71e548fb1d71b6ca8d629d9fc297ce3a0",
    "r2_host_snapshot_identity.log": "27ab15d918345437c884db676567ef0b825a16448c37f4e6b353608d830c5720",
    "r2_os-release.raw": "e5952e5be208da49268b7ff5e85176f82e0f8b45d2eadafbc83ab79f222617cc",
    "r2_runtime_residue_gate.log": "fbaaaf8e67a2c8e97cf7058c066382baee38bf2c69945a8f8e8338c30fdeac2b",
}

EXPECTED_RAW_FILES = sorted(SOURCE_SHA256_EXPECTED)

# Exact expected file set: 12 derived + 10 raw. Any other regular file FAILS.
EXPECTED_FILES = sorted(
    [
        ".gitattributes",
        "README.md",
        "EVIDENCE_INDEX.md",
        "evidence_scope.md",
        "source_inventory.json",
        "environment.json",
        "dependency_identity.json",
        "snapshot_identity.json",
        "clean_state_summary.json",
        "provenance.json",
        "checksums.txt",
        "test_package_closure.py",
    ]
    + ["raw/" + name for name in EXPECTED_RAW_FILES]
)

DERIVED_JSON_FILES = [
    "source_inventory.json",
    "environment.json",
    "dependency_identity.json",
    "snapshot_identity.json",
    "clean_state_summary.json",
    "provenance.json",
]

# Content documents that must not carry out-of-scope positive claims or the
# dependency-count substrings (environment.json is the only allowed carrier of
# the environment-level package count).
CONTENT_DOCS = [
    ".gitattributes",
    "README.md",
    "EVIDENCE_INDEX.md",
    "evidence_scope.md",
    "source_inventory.json",
    "environment.json",
    "dependency_identity.json",
    "snapshot_identity.json",
    "clean_state_summary.json",
    "provenance.json",
]

# Substrings that must never appear in dependency_identity.json, and in any
# content doc other than environment.json (the sole allowed carrier): the
# environment-level installed package count (2401).
BANNED_COUNT_SUBSTRINGS = ["installed_package_count", "INSTALLED_PACKAGE_COUNT", "2401"]

# Out-of-scope positive claim forms that must never appear in content docs.
BANNED_CLAIM_SUBSTRINGS = [
    "L3_READY=YES",
    "L3_READY: YES",
    "L3_READY=PASS",
    "RELEASE_READY=YES",
    "RELEASE_READY: YES",
    "D13D_FROZEN=YES",
    "D13D_FROZEN: YES",
    "FORMAL_D14D_L3=YES",
    "FORMAL_D14D_L3: YES",
    "AUTHORITATIVE_D14D_PHASE0=YES",
    "AUTHORITATIVE_D14D_PHASE0: YES",
    "HOST_VERIFIED=YES",
    "HOST_VERIFIED: YES",
    "HOST_VERIFIED=PASS",
    "FINAL_FROZEN",
    "authoritatative",
]

CHECKS_LIMITS = "NOT_CAPTURED_IN_ARCHIVED_RAW"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_regular_files(root: Path) -> dict[str, str]:
    """Return {relative_posix_path: sha256} for every regular file under root,
    excluding checksums.txt itself and any __pycache__ directories."""
    files: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            full = Path(dirpath) / fn
            rel = full.relative_to(root).as_posix()
            if rel == "checksums.txt":
                continue
            files[rel] = _sha256_file(full)
    return files


def _copy_bytes_heal(name: str) -> None:
    """Copy raw/<name> in bytes mode from the read-only source root.

    Asserts source SHA == SOURCE_SHA256_EXPECTED == target SHA (fail-closed:
    never adopt a new hash)."""
    expected = SOURCE_SHA256_EXPECTED[name]
    source = SOURCE_EVIDENCE_ROOT / "raw" / name
    if not source.is_file():
        raise AssertionError(
            f"raw source missing (fail-closed): {source}"
        )
    source_sha = _sha256_file(source)
    if source_sha != expected:
        raise AssertionError(
            f"raw source SHA mismatch (fail-closed, no new hash adopted): {name} "
            f"expected {expected} got {source_sha}"
        )
    target = PACKAGE_ROOT / "raw" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    target_sha = _sha256_file(target)
    if target_sha != expected:
        raise AssertionError(
            f"raw target SHA mismatch after byte copy (fail-closed): {name} "
            f"expected {expected} got {target_sha}"
        )


def _ensure_raw_files() -> None:
    for name in EXPECTED_RAW_FILES:
        target = PACKAGE_ROOT / "raw" / name
        if not target.is_file() or _sha256_file(target) != SOURCE_SHA256_EXPECTED[name]:
            _copy_bytes_heal(name)
        assert _sha256_file(target) == SOURCE_SHA256_EXPECTED[name]


def _load_json(rel: str) -> dict:
    return json.loads((PACKAGE_ROOT / rel).read_text(encoding="utf-8"))


def _assert_content_doc_hygiene() -> None:
    for rel in CONTENT_DOCS:
        text = (PACKAGE_ROOT / rel).read_text(encoding="utf-8")
        if rel != "environment.json":
            for banned in BANNED_COUNT_SUBSTRINGS:
                if banned in text:
                    raise AssertionError(f"{rel} must not contain {banned!r}")
        for banned in BANNED_CLAIM_SUBSTRINGS:
            if banned in text:
                raise AssertionError(f"{rel} must not contain out-of-scope claim {banned!r}")
        # HOST_VERIFIED may appear only as part of HOST_VERIFIED_SCOPE.
        if text.count("HOST_VERIFIED") != text.count("HOST_VERIFIED_SCOPE"):
            raise AssertionError(f"{rel}: HOST_VERIFIED only allowed inside HOST_VERIFIED_SCOPE")
    env_text = (PACKAGE_ROOT / "environment.json").read_text(encoding="utf-8")
    for required in ("installed_package_count", "2401"):
        if required not in env_text:
            raise AssertionError(f"environment.json must contain {required!r}")
    dep_text = (PACKAGE_ROOT / "dependency_identity.json").read_text(encoding="utf-8")
    for banned in BANNED_COUNT_SUBSTRINGS:
        if banned in dep_text:
            raise AssertionError(f"dependency_identity.json must not contain {banned!r}")


def _assert_classification_and_identity() -> None:
    provenance = _load_json("provenance.json")
    assert provenance["created_at_utc"] == "NOT_CAPTURED_IN_PACKAGING_LOG"
    assert provenance["evidence_class"] == "INDEPENDENT_KYLIN_HOST_VALIDATION"
    assert provenance["authoritative_d14d_phase0"] == "NO"
    assert provenance["formal_d14d_l3"] == "NO"
    assert provenance["l3_ready"] == "NO"
    assert provenance["host_verified_scope"] == "LIMITED_TO_RECORDED_FACTS"
    assert provenance["release_ready"] == "NO"
    assert provenance["d13d_frozen"] == "NO"
    assert provenance["raw_file_count"] == 10
    assert provenance["derived_file_count"] == 12
    assert provenance["packaging_branch"] == "docs/carlton-kylin-host-evidence"
    assert re.fullmatch(r"[0-9a-f]{40}", provenance["packaging_repository_head"])
    assert provenance["authoritative_d14d_root"] == "evidence/phase0/d14d-env-prepared-20260906-r3/"
    assert provenance["source_evidence_root"].endswith("d14d-env-prepared-20260906-r2")

    environment = _load_json("environment.json")
    guest = environment["guest"]
    assert guest["hostname"] == "Carlton-pc"
    assert guest["user"] == "Carlton"
    assert guest["uid"] == 1000
    assert guest["gid"] == 1000
    assert guest["kernel"] == "6.6.0-63-generic"
    assert guest["arch"] == "x86_64"
    assert guest["python"] == "Python 3.12.3"
    assert guest["systemd"].startswith("systemd 255")
    osr = environment["os_release"]
    assert osr["name"] == "Kylin"
    assert osr["pretty_name"] == "Kylin V11"
    assert osr["version_id"] == "v11"
    assert osr["kylin_release_id"] == "2603"
    assert environment["installed_package_count"] == 2401
    assert "localized_display_text_note" in osr

    dependency = _load_json("dependency_identity.json")
    sdk = dependency["sdk_identity"]
    assert sdk["package_version"] == "1.2.0.0-0k0.4"
    assert sdk["canonical_so"] == "/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0"
    assert sdk["soname"] == "libkysdk-coreai-embedding.so.1"
    assert sdk["sha256"] == "028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48"
    assert sdk["size_bytes"] == 366624
    assert sdk["d14a_match"] == "MATCHES_D14A_FROZEN_SDK_IDENTITY"
    assert dependency["target_packages"]["kylin-ai-subsystem"]["version"] == "1.2.0.0-0k0.3"
    assert dependency["target_packages"]["kylin-ai-parser-extension"]["status"] == "NOT_INSTALLED"
    runtime = dependency["runtime_identity"]
    assert runtime["package_version"] == "1.2.0.4-0k0.1"
    assert runtime["sha256"] == "b3f83fc90966394e7397979945f324a4691a208a1b944ed1c2488b20b296e225"
    assert runtime["size_bytes"] == 3174000
    model = dependency["model_identity"]
    assert model["gte_base_onnx_sha256"] == "cef0fc76165ee5bb4f3da5ab6b9b6e6fdfdd278d3077f2db2d4a6cde4d4c32b1"
    comparison = dependency["comparison_with_authoritative_d14d_r3"]
    assert comparison["subsystem_carlton"] == "1.2.0.0-0k0.3"
    assert comparison["subsystem_authoritative_r3"] == "1.3.0.1-0k0.1"
    assert comparison["parser_carlton"] == "NOT_INSTALLED"
    assert comparison["parser_authoritative_r3"] == "1.2.0.0-0k0.4"
    assert comparison["difference_kept_verbatim"] is True

    snapshot = _load_json("snapshot_identity.json")
    assert snapshot["virtualbox_version"] == "7.2.8r173730"
    assert snapshot["vm"]["name"] == "Kylin-Desktop-V11-2603-SDK"
    assert snapshot["vm"]["uuid"] == "23a31c42-63bb-482f-8856-e8a9f04176c8"
    assert snapshot["snapshot"]["name"] == "d14d-clean-base-20260906-r2"
    assert snapshot["snapshot"]["uuid"] == "b2af169e-8bfc-46a8-9120-6348095eccf3"
    capture_events = snapshot["capture_events"]
    assert len(capture_events) == 3
    captured_states = {event["captured_state"] for event in capture_events}
    assert "POWERED_OFF_AT_R2" in captured_states
    assert "RUNNING_AT_R2_SNAPSHOT_CAPTURE" in captured_states
    for event in capture_events:
        assert event["exit_code"] == CHECKS_LIMITS

    clean = _load_json("clean_state_summary.json")
    events = clean["chronological_events"]
    assert len(events) == 7
    classifications = [event["classification"] for event in events]
    assert classifications[0] == "PASS_RESULT_CAPTURED"
    assert classifications[4] == "FAIL_CLOSED_ERROR_CAPTURED"
    assert "ALLOWLIST_AWARE_PASS_RESULT_CAPTURED" in classifications
    assert all(event["exit_code"] == CHECKS_LIMITS for event in events)
    assert events[4]["evidence_file"] == "raw/r2_clean_gate_strict.log"
    assert events[5]["evidence_file"] == "raw/r2_final_clean_gate.log"
    timestamps = [event["timestamp"] for event in events]
    assert all(timestamp != "NOT_CAPTURED" for timestamp in timestamps)
    assert timestamps == sorted(timestamps)

    inventory = _load_json("source_inventory.json")
    assert len(inventory["files"]) == 10
    for entry in inventory["files"]:
        rel = entry["relative_path"]
        assert rel.startswith("raw/")
        name = rel[len("raw/"):]
        assert name in SOURCE_SHA256_EXPECTED
        assert entry["sha256"] == SOURCE_SHA256_EXPECTED[name]
        assert entry["size_bytes"] == (PACKAGE_ROOT / rel).stat().st_size
        assert entry["sha256"] == _sha256_file(PACKAGE_ROOT / rel)

    for rel in DERIVED_JSON_FILES:
        _load_json(rel)

    readme = (PACKAGE_ROOT / "README.md").read_text(encoding="utf-8")
    scope = (PACKAGE_ROOT / "evidence_scope.md").read_text(encoding="utf-8")
    assert "INDEPENDENT_KYLIN_HOST_VALIDATION" in readme
    assert "INDEPENDENT_KYLIN_HOST_VALIDATION" in scope
    assert "NON_AUTHORITATIVE_FOR_D14D" in readme
    assert "NON_AUTHORITATIVE_FOR_D14D" in scope
    assert "LIMITED_TO_RECORDED_FACTS" in readme
    assert "evidence/phase0/d14d-env-prepared-20260906-r3/" in readme
    assert "evidence/phase0/d14d-env-prepared-20260906-r3/" in scope
    assert "sha256sum -c checksums.txt" in readme
    assert "包根目录" in readme  # self-check execution directory instruction
    assert (PACKAGE_ROOT / ".gitattributes").read_text(encoding="utf-8").count("* binary") >= 1


def _parse_checksums() -> tuple[list[str], dict[str, str]]:
    """Return (sorted entry paths, {relpath: sha256}) parsed from checksums.txt."""
    text = (PACKAGE_ROOT / "checksums.txt").read_text(encoding="utf-8")
    entries: dict[str, str] = {}
    for line in text.splitlines():
        m = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if m is None:
            raise AssertionError(f"bad checksums.txt line: {line!r}")
        digest, rel = m.group(1), m.group(2)
        if rel in entries:
            raise AssertionError(f"duplicate checksums.txt entry: {rel}")
        entries[rel] = digest
    return sorted(entries), entries


def _seal_checksums(files: dict[str, str]) -> None:
    lines = [f"{files[rel]}  {rel}" for rel in sorted(files)]
    (PACKAGE_ROOT / "checksums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _verify_checksums(files: dict[str, str]) -> None:
    sorted_paths, entries = _parse_checksums()
    if set(entries) != set(files):
        missing = sorted(set(files) - set(entries))
        extra = sorted(set(entries) - set(files))
        raise AssertionError(
            f"checksums closure drift (no silent rewrite): "
            f"missing entries={missing} extra entries={extra}"
        )
    drift = sorted(rel for rel in files if entries[rel] != files[rel])
    if drift:
        raise AssertionError(
            f"checksums content drift (no silent rewrite): {drift}"
        )
    if sorted_paths != sorted(files):
        raise AssertionError("checksums.txt entries are not in stable sorted order")


def test_package_closure() -> None:
    _ensure_raw_files()

    files = _collect_regular_files(PACKAGE_ROOT)
    # _collect_regular_files intentionally excludes checksums.txt itself
    # (checksums.txt covers every regular file except itself).
    expected_sealed = set(EXPECTED_FILES) - {"checksums.txt"}
    if set(files) != expected_sealed:
        unexpected = sorted(set(files) - expected_sealed)
        missing = sorted(expected_sealed - set(files))
        raise AssertionError(
            f"unexpected file set: unexpected={unexpected} missing={missing}"
        )

    _assert_classification_and_identity()
    _assert_content_doc_hygiene()

    checksums_path = PACKAGE_ROOT / "checksums.txt"
    if checksums_path.exists():
        _verify_checksums(files)
        _, entries = _parse_checksums()
    else:
        _seal_checksums(files)
        entries = dict((rel, digest) for rel, digest in files.items())
    assert checksums_path.is_file()

    # Closure invariant: REGULAR_FILE_COUNT == CHECKSUM_ENTRY_COUNT + 1
    # (checksums.txt covers every regular file except itself).
    regular_file_count = 0
    for dirpath, dirnames, filenames in os.walk(PACKAGE_ROOT):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        regular_file_count += len(filenames)
    assert regular_file_count == 22
    assert regular_file_count == len(entries) + 1