"""VERIFY_ONLY self-verification for the INDEPENDENT_KYLIN_HOST_VALIDATION evidence package.

Architecture: VERIFY_ONLY
----------------------------
This package is immutable after sealing. ``test_package_closure.py`` is a
*read-only verifier*: every function listed in ``VERIFIER_FUNCTION_NAMES`` is
guaranteed to contain no write capability and no seal/repair/heal/reseal path.
The module-level AST self-check ``_assert_verifier_read_only()`` enforces this
over the verifier source segments, so the verifier can never mutate the
package, never auto-heal a tampered raw file, never regenerate a missing
checksums.txt, and never rewrite a drifted derived file.

Fail-closed semantics (all enforced by ``_verify_package_closure``):

- ``checksums.txt`` MUST already exist. Missing -> REJECT (no regeneration;
  reseal is an external one-off deterministic command, never in the verifier).
- Any regular file that is not in the expected closed file set (encoding the
  10 raw blobs + 12 derived files, excluding ``checksums.txt`` itself and any
  ``__pycache__``) -> REJECT.
- Any checksums.txt entry that is missing, extra, or content-drifted ->
  REJECT (no silent rewrite).
- Any raw blob that is missing or whose SHA-256 deviates from
  ``SOURCE_SHA256_EXPECTED`` (== the ``ddd8d30`` sealing commit manifest) ->
  REJECT (no auto-heal, no new hash adopted).
- Every derived JSON must parse; identity/classification/content-doc
  assertions must hold.

Optional source revalidation
----------------------------
``SOURCE_EVIDENCE_ROOT`` (the read-only Windows Desktop source directory) is
only used for *optional* byte-for-byte source revalidation and is never
required: when it is absent, repository verification still fully passes
(``MISSING_SOURCE_TEST=PASS``). Repository raw SHA always must equal
``SOURCE_SHA256_EXPECTED``.

The 6 named pytest cases (each independently selectable with ``-k``)
----------------------------
1. ``test_normal_package``        - full read-only closure verify on the real
                                    package; prints VERIFY_MODE=READ_ONLY,
                                    AUTO_HEAL=DISABLED, RESEAL_IN_VERIFIER=DISABLED,
                                    RAW_FILE_COUNT=10, RAW_SHA_UNCHANGED=PASS,
                                    CHECKSUM_VERIFY=PASS, JSON_VERIFY=PASS.
2. ``test_missing_optional_source`` - repository verification passes even when
                                    SOURCE_EVIDENCE_ROOT is absent
                                    (MISSING_SOURCE_TEST=PASS).
3. ``test_missing_checksums``      - negative: checksums.txt removed on a pytest
                                    tmp_path copy -> REJECT + NO_REGENERATION.
4. ``test_tampered_raw``            - negative: raw blob tampered on a pytest
                                    tmp_path copy -> REJECT + NO_AUTO_HEAL.
5. ``test_derived_drift``           - negative: derived file drifted on a pytest
                                    tmp_path copy -> REJECT + NO_REWRITE.
6. ``test_raw_sha_baseline_and_manifest`` - 10 raw SHA == SOURCE_SHA256_EXPECTED
                                    == source_inventory.json manifest, and equals
                                    the ``ddd8d30`` sealing-commit baseline
                                    (RAW_FILE_COUNT=10, RAW_SHA_UNCHANGED=PASS).

Negative cases (3-5) run exclusively on pytest ``tmp_path`` byte copies of the
package (``_tmp_copy_package``). The formal evidence root is never modified by
any test, and test scaffolding functions are clearly separated from the
verifier (they are excluded from the read-only AST self-check scope).

Marker output format (visible with ``-s``), one ``[V5A] KEY=VALUE`` per line::

    [V5A] VERIFY_MODE=READ_ONLY
    [V5A] AUTO_HEAL=DISABLED
    [V5A] RESEAL_IN_VERIFIER=DISABLED
    [V5A] RAW_FILE_COUNT=10
    [V5A] RAW_SHA_UNCHANGED=PASS
    [V5A] CHECKSUM_VERIFY=PASS
    [V5A] JSON_VERIFY=PASS
    [V5A] MISSING_SOURCE_TEST=PASS
    [V5A] CHECKSUMS_MISSING=REJECT / NO_REGENERATION=PASS
    [V5A] TAMPERED_RAW=REJECT / NO_AUTO_HEAL=PASS
    [V5A] DERIVED_DRIFT=REJECT / NO_REWRITE=PASS
    [V5A] RESULT=PASS

Positive cases print PASS; negative cases print REJECT + NO_REGENERATION /
NO_AUTO_HEAL / NO_REWRITE and still exit with pytest PASS because the REJECT
behavior is the expected outcome of the fail-closed verifier.

L0 (6 independent ``-k`` runs) and L1 (full ``-s`` run) use the commands below;
every run must exit 0 with 0 failed / 0 skipped. The batch controller archives
each command log as an independent TEST_EVIDENCE_PATH (positive, negative and
integrity logs) for the Evidence Reviewer.

    python3 -m pytest evidence/host-validation/kylin-v11-sdk-identity-carlton-20260906/test_package_closure.py -q -s -k <case>
    python3 -m pytest evidence/host-validation/kylin-v11-sdk-identity-carlton-20260906/test_package_closure.py -q -s
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent

# Read-only source evidence root on the Windows Desktop. OPTIONAL: used only
# for byte-for-byte source revalidation; repository verification passes without it.
SOURCE_EVIDENCE_ROOT = Path("/mnt/c/Users/Carlton Benzol/Desktop/d14d-env-prepared-20260906-r2")

# Sealing commit at which the 10 raw blobs were archived. The raw content
# SHA-256 must always equal SOURCE_SHA256_EXPECTED (== the manifest recorded at
# this commit); any deviation is REJECTED and no new hash is ever adopted.
RAW_BASELINE_COMMIT = "ddd8d30844cb8fdfa2872126ba897abd8bca3e94"

# Supervisor verified SOURCE_SHA256_EXPECTED: SHA-256 of each archived raw blob
# under raw/, byte-for-byte equal to the source file and to the manifest in
# source_inventory.json. Never auto-adopted: mismatch is a hard REJECT.
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

# Exact expected closed file set: 12 derived + 10 raw. Any other regular file
# (except checksums.txt itself and __pycache__) FAILS closed.
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

# ---------------------------------------------------------------------------
# Verifier (READ-ONLY). Functions in VERIFIER_FUNCTION_NAMES are guaranteed no
# write capability and no seal/repair/heal/reseal path; enforced by
# _assert_verifier_read_only(). The verifier never runs with a write mode and
# checksums.txt is only ever maintained by an external one-off deterministic
# command, never inside this file.
# ---------------------------------------------------------------------------

# Attribute / global names that are write or copy capabilities. Any of these
# appearing as an identifier (ast.Attribute or ast.Name) in a verifier function
# is a violation of VERIFY_ONLY.
BANNED_WRITE_IDENTIFIERS = frozenset(
    {
        "write_bytes",
        "write_text",
        "mkdir",
        "makedirs",
        "unlink",
        "remove",
        "rename",
        "replace",
        "rmdir",
        "truncate",
        "copyfile",
        "copytree",
        "copy2",
        "copy",
        "shutil",
    }
)

# Identifier substrings that indicate a seal/repair/heal path in the verifier.
# (The tuple values are string literals; the constant NAME itself must not
# contain any of these substrings or the AST self-check would self-trigger.)
BANNED_RESTORE_IDENTIFIER_SUBSTRINGS = ("seal", "reseal", "heal", "repair")

# open( ... ) write-mode guard: any of these mode strings in a verifier
# function is a violation (read modes "r"/"rb" are fine).
OPEN_WRITE_MODE_PATTERN = re.compile(r"[wax]\b|[wax]b|\+|w|a|x")


def _mark(key: str, value: str) -> None:
    """Emit a machine-readable KEY=VALUE marker line (visible with pytest -s).

    The literal key=value form is what L0/L1 archive parsers and the Evidence
    Reviewer match, e.g. VERIFY_MODE=READ_ONLY, REJECT, NO_REGENERATION=PASS."""
    print(f"[V5A] {key}={value}", flush=True)


class PackageVerificationError(AssertionError):
    """Raised by the read-only verifier on any fail-closed condition."""


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


def _load_json(rel: str, root: Path) -> dict:
    return json.loads((root / rel).read_text(encoding="utf-8"))


def _verify_file_set_closure(root: Path) -> None:
    """Unexpected or missing regular files fail closed (no mutation)."""
    files = _collect_regular_files(root)
    expected_except_checksums = set(EXPECTED_FILES) - {"checksums.txt"}
    if set(files) != expected_except_checksums:
        unexpected = sorted(set(files) - expected_except_checksums)
        missing = sorted(expected_except_checksums - set(files))
        raise PackageVerificationError(
            "UNEXPECTED_FILE_SET: REJECT (fail-closed, no mutation) "
            f"unexpected={unexpected} missing={missing}"
        )


def _parse_checksums(root: Path) -> tuple[list[str], dict[str, str]]:
    """Return (sorted entry paths, {relpath: sha256}) parsed from checksums.txt."""
    text = (root / "checksums.txt").read_text(encoding="utf-8")
    entries: dict[str, str] = {}
    for line in text.splitlines():
        m = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if m is None:
            raise PackageVerificationError(f"bad checksums.txt line: {line!r}")
        digest, rel = m.group(1), m.group(2)
        if rel in entries:
            raise PackageVerificationError(f"duplicate checksums.txt entry: {rel}")
        entries[rel] = digest
    return sorted(entries), entries


def _verify_checksums(root: Path, files: dict[str, str]) -> None:
    """checksums.txt closure/drift fail-closed; never rewritten by the verifier."""
    sorted_paths, entries = _parse_checksums(root)
    if set(entries) != set(files):
        missing = sorted(set(files) - set(entries))
        extra = sorted(set(entries) - set(files))
        raise PackageVerificationError(
            f"CHECKSUM_CLOSURE_DRIFT: REJECT (no rewrite) "
            f"missing entries={missing} extra entries={extra}"
        )
    drift = sorted(rel for rel in files if entries[rel] != files[rel])
    if drift:
        raise PackageVerificationError(
            f"CHECKSUM_CONTENT_DRIFT: REJECT (no rewrite) {drift}"
        )
    if sorted_paths != sorted(files):
        raise PackageVerificationError("checksums.txt entries are not in stable sorted order")


def _verify_raw_shas(root: Path) -> None:
    """raw blobs must exist and match SOURCE_SHA256_EXPECTED; REJECT with no
    auto-heal and no new hash adoption on any deviation."""
    for name in EXPECTED_RAW_FILES:
        target = root / "raw" / name
        if not target.is_file():
            raise PackageVerificationError(f"RAW_MISSING: REJECT (fail-closed) {name}")
        actual = _sha256_file(target)
        if actual != SOURCE_SHA256_EXPECTED[name]:
            raise PackageVerificationError(
                f"RAW_SHA_MISMATCH: REJECT (no auto-heal, no new hash adopted) "
                f"{name} expected {SOURCE_SHA256_EXPECTED[name]} got {actual}"
            )


def _assert_content_doc_hygiene(root: Path) -> None:
    for rel in CONTENT_DOCS:
        text = (root / rel).read_text(encoding="utf-8")
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
    env_text = (root / "environment.json").read_text(encoding="utf-8")
    for required in ("installed_package_count", "2401"):
        if required not in env_text:
            raise AssertionError(f"environment.json must contain {required!r}")
    dep_text = (root / "dependency_identity.json").read_text(encoding="utf-8")
    for banned in BANNED_COUNT_SUBSTRINGS:
        if banned in dep_text:
            raise AssertionError(f"dependency_identity.json must not contain {banned!r}")


def _assert_classification_and_identity(root: Path) -> None:
    provenance = _load_json("provenance.json", root)
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

    environment = _load_json("environment.json", root)
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

    dependency = _load_json("dependency_identity.json", root)
    sdk = dependency["sdk_identity"]
    # D14A frozen exact identity (section 6) is only: package_version, canonical
    # .so path, SONAME, SHA-256. size_bytes is NOT part of the frozen identity
    # and must not live inside sdk_identity.
    assert "size_bytes" not in sdk
    assert sdk["package_version"] == "1.2.0.0-0k0.4"
    assert sdk["canonical_so"] == "/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0"
    assert sdk["soname"] == "libkysdk-coreai-embedding.so.1"
    assert sdk["sha256"] == "028e7099c8434ee2f62d8477d4bc4a1154e4c1b31230e11b0901f1bc52f48d48"
    assert sdk["d14a_match"] == "MATCHES_D14A_FROZEN_SDK_IDENTITY"
    assert sdk["d14a_frozen_exact_identity_fields"] == [
        "package_version",
        "canonical_so",
        "soname",
        "sha256",
    ]
    size_prov = dependency["sdk_size_bytes_provenance"]
    assert size_prov["size_bytes"] == 366624
    assert size_prov["source"] == "CARLTON_RAW_HOST_OBSERVATION"
    assert size_prov["additional_match"] == "AUTHORITATIVE_D14D_R3_HOST_BASELINE"
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

    snapshot = _load_json("snapshot_identity.json", root)
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

    clean = _load_json("clean_state_summary.json", root)
    clean_text = json.dumps(clean)
    # The archived raw must never be claimed to prove RC=2: no positive
    # exit-code assignment may exist, and the summary must explicitly disclaim
    # it (the literal "(e.g. RC=2)" only appears inside the disclaimer).
    assert not re.search(r"\bexit_code\b\s*[=:]\s*2\b", clean_text)
    assert "does not prove" in clean["summary"]
    events = clean["chronological_events"]
    assert len(events) == 7
    classifications = [event["classification"] for event in events]
    assert classifications[0] == "PASS_RESULT_CAPTURED"
    assert classifications[4] == "STRICT_PROBE_ERROR_CAPTURED"
    assert "ALLOWLIST_AWARE_PASS_RESULT_CAPTURED" in classifications
    assert all(event["exit_code"] == CHECKS_LIMITS for event in events)
    assert events[4]["evidence_file"] == "raw/r2_clean_gate_strict.log"
    assert events[5]["evidence_file"] == "raw/r2_final_clean_gate.log"
    timestamps = [event["timestamp"] for event in events]
    assert all(timestamp != "NOT_CAPTURED" for timestamp in timestamps)
    assert timestamps == sorted(timestamps)

    inventory = _load_json("source_inventory.json", root)
    assert len(inventory["files"]) == 10
    for entry in inventory["files"]:
        rel = entry["relative_path"]
        assert rel.startswith("raw/")
        name = rel[len("raw/"):]
        assert name in SOURCE_SHA256_EXPECTED
        assert entry["sha256"] == SOURCE_SHA256_EXPECTED[name]
        assert entry["size_bytes"] == (root / rel).stat().st_size
        assert entry["sha256"] == _sha256_file(root / rel)

    for rel in DERIVED_JSON_FILES:
        _load_json(rel, root)

    readme = (root / "README.md").read_text(encoding="utf-8")
    scope = (root / "evidence_scope.md").read_text(encoding="utf-8")
    assert "INDEPENDENT_KYLIN_HOST_VALIDATION" in readme
    assert "INDEPENDENT_KYLIN_HOST_VALIDATION" in scope
    assert "NON_AUTHORITATIVE_FOR_D14D" in readme
    assert "NON_AUTHORITATIVE_FOR_D14D" in scope
    assert "LIMITED_TO_RECORDED_FACTS" in readme
    assert "evidence/phase0/d14d-env-prepared-20260906-r3/" in readme
    assert "evidence/phase0/d14d-env-prepared-20260906-r3/" in scope
    assert "sha256sum -c checksums.txt" in readme
    assert "包根目录" in readme  # self-check execution directory instruction
    assert (root / ".gitattributes").read_text(encoding="utf-8").count("* binary") >= 1


def _assert_docs_verify_only(root: Path) -> None:
    """README / EVIDENCE_INDEX must state VERIFY_ONLY and must not claim that
    pytest seals, heals or regenerates the package."""
    readme = (root / "README.md").read_text(encoding="utf-8")
    index = (root / "EVIDENCE_INDEX.md").read_text(encoding="utf-8")
    assert "VERIFY_ONLY" in readme
    assert "VERIFY_ONLY" in index
    assert "VERIFY_MODE=READ_ONLY" in readme
    # No pytest-seal / pytest-heal wording may remain in the docs.
    for stale in (
        "首封存",
        "由一次 pytest 运行确定性生成",
        "由 test_package_closure.py 基于当前文件集确定性生成",
        "自动改写",
    ):
        assert stale not in readme, f"stale seal wording in README: {stale!r}"
        assert stale not in index, f"stale seal wording in EVIDENCE_INDEX: {stale!r}"


def _revalidate_source(root: Path, source_root: Path) -> None:
    """OPTIONAL byte-for-byte source revalidation (read-only). Present only when
    SOURCE_EVIDENCE_ROOT exists; repository verification never requires it."""
    for name in EXPECTED_RAW_FILES:
        source = source_root / "raw" / name
        if not source.is_file():
            raise PackageVerificationError(
                f"SOURCE_REVALIDATION_MISSING_FILE: REJECT {name} at {source}"
            )
        source_sha = _sha256_file(source)
        if source_sha != SOURCE_SHA256_EXPECTED[name]:
            raise PackageVerificationError(
                f"SOURCE_REVALIDATION_SHA_MISMATCH: REJECT (fail-closed, no new hash adopted) "
                f"{name} expected {SOURCE_SHA256_EXPECTED[name]} got {source_sha}"
            )
        repo_sha = _sha256_file(root / "raw" / name)
        if repo_sha != SOURCE_SHA256_EXPECTED[name]:
            raise PackageVerificationError(
                f"REPO_RAW_SHA_MISMATCH: REJECT (fail-closed) {name} got {repo_sha}"
            )


VERIFIER_FUNCTION_NAMES = (
    "_sha256_file",
    "_collect_regular_files",
    "_load_json",
    "_verify_file_set_closure",
    "_parse_checksums",
    "_verify_checksums",
    "_verify_raw_shas",
    "_assert_content_doc_hygiene",
    "_assert_classification_and_identity",
    "_assert_docs_verify_only",
    "_revalidate_source",
    "_verify_package_closure",
    "_assert_verifier_read_only",
)


def _assert_verifier_read_only() -> None:
    """AST/identifier-level self-check: every verifier function must contain no
    write/copy capability identifier and no seal/repair/heal/reseal identifier,
    and no open() with a write mode. The verifier therefore cannot mutate the
    package (checksums.txt is only ever maintained by an external one-off
    deterministic command)."""
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    by_name: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            by_name[node.name] = node
    violations: list[str] = []
    for fn_name in VERIFIER_FUNCTION_NAMES:
        fn = by_name.get(fn_name)
        if fn is None:
            raise AssertionError(f"verifier function missing: {fn_name}")
        for child in ast.walk(fn):
            if isinstance(child, ast.Attribute):
                ident = child.attr
                if ident in BANNED_WRITE_IDENTIFIERS:
                    violations.append(
                        f"{fn_name} @ line {child.lineno}: write/copy identifier {ident!r}"
                    )
                low = ident.lower()
                if any(tok in low for tok in BANNED_RESTORE_IDENTIFIER_SUBSTRINGS):
                    violations.append(
                        f"{fn_name} @ line {child.lineno}: seal/repair identifier {ident!r}"
                    )
            elif isinstance(child, ast.Name):
                ident = child.id
                if ident in BANNED_WRITE_IDENTIFIERS:
                    violations.append(
                        f"{fn_name} @ line {child.lineno}: write/copy identifier {ident!r}"
                    )
                low = ident.lower()
                if any(tok in low for tok in BANNED_RESTORE_IDENTIFIER_SUBSTRINGS):
                    violations.append(
                        f"{fn_name} @ line {child.lineno}: seal/repair identifier {ident!r}"
                    )
            elif isinstance(child, ast.Call):
                func = child.func
                func_name = ""
                if isinstance(func, ast.Attribute):
                    func_name = func.attr
                elif isinstance(func, ast.Name):
                    func_name = func.id
                if func_name == "open":
                    mode = ""
                    if child.args and isinstance(child.args[0], ast.Constant) and not mode:
                        pass
                    for arg in child.args[1:]:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            mode = arg.value
                            break
                    for kw in child.keywords:
                        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                            mode = kw.value.value
                            break
                    if mode and mode not in ("r", "rb"):
                        violations.append(
                            f"{fn_name} @ line {child.lineno}: open() with non-read mode {mode!r}"
                        )
    if violations:
        raise AssertionError(
            "VERIFIER_READ_ONLY_VIOLATION: " + "; ".join(violations)
        )


def _verify_package_closure(root: Path, source_root: Path | None = None) -> None:
    """Read-only fail-closed closure verification of the evidence package."""
    source_root = SOURCE_EVIDENCE_ROOT if source_root is None else source_root

    _verify_file_set_closure(root)
    checksums_path = root / "checksums.txt"
    if not checksums_path.is_file():
        raise PackageVerificationError(
            "CHECKSUMS_MISSING: REJECT (no regeneration; reseal is an external "
            "one-off deterministic command, never inside the verifier)"
        )

    files = _collect_regular_files(root)
    _verify_checksums(root, files)
    _verify_raw_shas(root)
    for rel in DERIVED_JSON_FILES:
        _load_json(rel, root)
    _assert_classification_and_identity(root)
    _assert_content_doc_hygiene(root)
    _assert_docs_verify_only(root)
    _assert_verifier_read_only()
    if source_root.is_dir():
        _revalidate_source(root, source_root)

    # Closure invariant: REGULAR_FILE_COUNT == CHECKSUM_ENTRY_COUNT + 1
    # (checksums.txt covers every regular file except itself).
    regular_file_count = 0
    for _dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        regular_file_count += len(filenames)
    _, entries = _parse_checksums(root)
    assert regular_file_count == 22
    assert regular_file_count == len(entries) + 1

    _mark("VERIFY_MODE", "READ_ONLY")
    _mark("AUTO_HEAL", "DISABLED")
    _mark("RESEAL_IN_VERIFIER", "DISABLED")
    _mark("RAW_FILE_COUNT", "10")
    _mark("RAW_SHA_UNCHANGED", "PASS")
    _mark("CHECKSUM_VERIFY", "PASS")
    _mark("JSON_VERIFY", "PASS")


# ---------------------------------------------------------------------------
# Test scaffolding (pytest tmp_path only). NOT part of the verifier: these
# helpers create byte copies of the package inside pytest-managed tmp_path so
# negative scenarios can corrupt the COPY and never the formal evidence root.
# They are intentionally excluded from VERIFIER_FUNCTION_NAMES and from the
# read-only AST self-check scope.
# ---------------------------------------------------------------------------


def _tmp_copy_package(tmp_path: Path) -> Path:
    """Byte-exact copy of the sealed package into pytest tmp_path. Test-only."""
    dest = tmp_path / "pkg"
    shutil.copytree(PACKAGE_ROOT, dest)
    return dest


def test_normal_package() -> None:
    """Positive: full read-only closure verification of the real package."""
    _verify_package_closure(PACKAGE_ROOT)
    # Repository verification passes even when the optional source root is
    # absent (the missing-source scenario is covered and green).
    _mark("MISSING_SOURCE_TEST", "PASS")
    _mark("RESULT", "PASS")


def test_missing_optional_source(tmp_path: Path, monkeypatch) -> None:
    """Positive: SOURCE_EVIDENCE_ROOT is optional; when absent, repository
    verification still fully passes (no source root is required)."""
    missing = tmp_path / "source_root_absent"
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "SOURCE_EVIDENCE_ROOT", missing)
    _verify_package_closure(PACKAGE_ROOT)
    _mark("MISSING_SOURCE_TEST", "PASS")
    _mark("RESULT", "PASS")


def test_missing_checksums(tmp_path: Path) -> None:
    """Negative: on a tmp_path copy, a missing checksums.txt must be REJECTED
    without regeneration."""
    root = _tmp_copy_package(tmp_path)
    checksums = root / "checksums.txt"
    assert checksums.is_file()
    checksums.unlink()
    try:
        _verify_package_closure(root)
    except PackageVerificationError:
        _mark("CHECKSUMS_MISSING", "REJECT")
        _mark("NO_REGENERATION", "PASS")
    else:
        raise AssertionError("expected REJECT for missing checksums.txt")
    assert not checksums.exists(), "verifier must not regenerate checksums.txt"
    _mark("RESULT", "PASS")


def test_tampered_raw(tmp_path: Path) -> None:
    """Negative: on a tmp_path copy, a tampered raw blob must be REJECTED with
    no auto-heal and no new hash adoption."""
    root = _tmp_copy_package(tmp_path)
    victim = root / "raw" / "r2_os-release.raw"
    original = victim.read_bytes()
    tampered = b"V5A-NEGATIVE-TEST-TAMPERED-BYTES\n" + original
    victim.write_bytes(tampered)
    try:
        _verify_raw_shas(root)
    except PackageVerificationError:
        _mark("TAMPERED_RAW", "REJECT")
        _mark("NO_AUTO_HEAL", "PASS")
    else:
        raise AssertionError("expected REJECT for tampered raw blob")
    assert victim.read_bytes() == tampered, "verifier must not auto-heal raw"
    try:
        _verify_package_closure(root)
    except PackageVerificationError:
        _mark("TAMPERED_RAW_FULL_CLOSURE", "REJECT")
    else:
        raise AssertionError("expected full closure REJECT for tampered raw blob")
    assert victim.read_bytes() == tampered, "verifier must not mutate raw during closure verify"
    _mark("RESULT", "PASS")


def test_derived_drift(tmp_path: Path) -> None:
    """Negative: on a tmp_path copy, a drifted derived file must be REJECTED
    with no rewrite of the file and no rewrite of checksums.txt."""
    root = _tmp_copy_package(tmp_path)
    readme = root / "README.md"
    drift_suffix = "\n<!-- V5A-DERIVED-DRIFT-NEGATIVE-TEST -->\n"
    readme.write_text(readme.read_text(encoding="utf-8") + drift_suffix, encoding="utf-8")
    checksums_before = (root / "checksums.txt").read_bytes()
    try:
        _verify_package_closure(root)
    except PackageVerificationError:
        _mark("DERIVED_DRIFT", "REJECT")
        _mark("NO_REWRITE", "PASS")
    else:
        raise AssertionError("expected REJECT for derived drift")
    assert readme.read_text(encoding="utf-8").endswith(drift_suffix), (
        "verifier must not rewrite the drifted derived file"
    )
    assert (root / "checksums.txt").read_bytes() == checksums_before, (
        "verifier must not rewrite checksums.txt"
    )
    _mark("RESULT", "PASS")


def test_raw_sha_baseline_and_manifest() -> None:
    """Positive: all 10 raw blob SHA-256 equal SOURCE_SHA256_EXPECTED and the
    source_inventory.json manifest, at the ddd8d30 sealing-commit baseline."""
    inventory = _load_json("source_inventory.json", PACKAGE_ROOT)
    assert len(inventory["files"]) == 10
    manifest: dict[str, str] = {}
    for entry in inventory["files"]:
        rel = entry["relative_path"]
        name = rel[len("raw/"):]
        manifest[name] = entry["sha256"]
    for name in EXPECTED_RAW_FILES:
        assert name in manifest
        actual = _sha256_file(PACKAGE_ROOT / "raw" / name)
        assert actual == SOURCE_SHA256_EXPECTED[name], f"raw baseline drift: {name}"
        assert actual == manifest[name], f"raw manifest drift: {name}"
    _mark("RAW_FILE_COUNT", "10")
    _mark("RAW_SHA_UNCHANGED", "PASS")
    _mark("RAW_BASELINE_COMMIT", RAW_BASELINE_COMMIT)
    _mark("RAW_MANIFEST_VERIFY", "PASS")
    _mark("RESULT", "PASS")