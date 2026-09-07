"""L1 tests for D13D Phase 3 preflight fail-closed semantics."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_d13d_phase3_prep.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_d13d_phase3_prep", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


def _result(name: str, *, stdout: str = "", exit_code: int = 0):
    return {"name": name, "command": name, "exit_code": exit_code, "stdout": stdout, "stderr": ""}


def _pass_results() -> list[dict]:
    return [
        _result("guest_repo_head", stdout="a" * 40),
        _result("guest_repo_status"),
        _result("d13e_artifact_hashes"),
        _result(
            "trust_root_stat",
            stdout=(
                "root root 700 /etc/kylin-memory/trust\n"
                "root root 644 /etc/kylin-memory/trust/D13E_TRUST_ROOTS_V1.json\n"
                "root root 644 /etc/kylin-memory/trust/d13e-review-public.pem\n"
                "root root 644 /etc/kylin-memory/trust/d13d-execution-public.pem\n"
            ),
        ),
        _result("trust_root_symlinks"),
        _result("trust_root_hashes"),
    ]


def test_preflight_semantic_pass_has_no_reasons():
    assert MODULE.evaluate_preflight(_pass_results()) == []


def test_preflight_blocks_dirty_guest_worktree():
    results = _pass_results()
    results[1]["stdout"] = " M production.py\n"

    reasons = MODULE.evaluate_preflight(results)

    assert "guest repository worktree is dirty" in reasons


def test_preflight_blocks_trust_root_symlink():
    results = _pass_results()
    results[4]["stdout"] = "/etc/kylin-memory/trust/d13d-execution-public.pem\n"

    reasons = MODULE.evaluate_preflight(results)

    assert "trust root contains symlinks" in reasons


def test_preflight_blocks_non_root_or_writable_trust_metadata():
    results = _pass_results()
    results[3]["stdout"] = results[3]["stdout"].replace(
        "root root 700 /etc/kylin-memory/trust",
        "kylin-agent kylin-agent 772 /etc/kylin-memory/trust",
    )

    reasons = MODULE.evaluate_preflight(results)

    assert "trust root owner is not root: /etc/kylin-memory/trust" in reasons
    assert "trust root group writable: /etc/kylin-memory/trust 772" in reasons
    assert "trust root other writable: /etc/kylin-memory/trust 772" in reasons


def test_preflight_blocks_head_mismatch_only_when_expected_head_is_given():
    assert MODULE.evaluate_preflight(_pass_results()) == []

    reasons = MODULE.evaluate_preflight(_pass_results(), expected_head="b" * 40)

    assert "guest repository HEAD does not match expected-head" in reasons


def test_preflight_blocks_failed_required_command():
    results = _pass_results()
    results[2]["exit_code"] = 2

    reasons = MODULE.evaluate_preflight(results)

    assert "command failed: d13e_artifact_hashes" in reasons


def test_preflight_blocks_failed_nonsemantic_collection_command():
    results = _pass_results()
    results[0]["name"] = "service_active"
    results[0]["exit_code"] = 3

    reasons = MODULE.evaluate_preflight(results)

    assert "command failed: service_active" in reasons


def test_runtime_import_constructs_ssh_client(monkeypatch):
    calls = []

    class FakeClient:
        def set_missing_host_key_policy(self, policy):
            calls.append(("set_policy", policy))

        def connect(self, *args, **kwargs):
            calls.append(("connect", args, kwargs))

        def close(self):
            calls.append(("close",))

    class FakeParamiko:
        SSHClient = FakeClient
        AutoAddPolicy = object

    monkeypatch.setitem(sys.modules, "paramiko", FakeParamiko)

    client = MODULE._ssh_client()

    assert isinstance(client, FakeClient)
    assert calls[0][0] == "set_policy"


def test_preflight_compares_sha256_anchor_fail_closed(tmp_path):
    expected = (
        "a" * 64 + "  /home/kylin-agent/kylinOS-agent-memory/evaluation/d13e/artifact\n" +
        "b" * 64 + "  /etc/kylin-memory/trust/D13E_TRUST_ROOTS_V1.json\n"
    )
    anchor = tmp_path / "expected.SHA256SUMS"
    anchor.write_text(expected, encoding="utf-8")
    results = _pass_results()
    results[2]["stdout"] = "a" * 64 + "  /home/kylin-agent/kylinOS-agent-memory/evaluation/d13e/artifact\n"
    results[5]["stdout"] = "b" * 64 + "  /etc/kylin-memory/trust/D13E_TRUST_ROOTS_V1.json\n"

    assert MODULE.evaluate_preflight(results, expected_hash_anchor=anchor) == []

    mismatched = results.copy()
    mismatched[2]["stdout"] = "c" * 64 + "  /home/kylin-agent/kylinOS-agent-memory/evaluation/d13e/artifact\n"

    reasons = MODULE.evaluate_preflight(mismatched, expected_hash_anchor=anchor)

    assert "sha256 mismatch: /home/kylin-agent/kylinOS-agent-memory/evaluation/d13e/artifact" in reasons
