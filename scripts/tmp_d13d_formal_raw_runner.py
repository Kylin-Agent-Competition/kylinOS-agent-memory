#!/usr/bin/env python3
"""Host-side orchestration for the D13D Phase 3 formal 17-sample raw run.

The runtime repository is cloned from a bundle at the selected tested commit
inside a fresh VM isolation root.  The remote runner dispatches all samples and
writes canonical raw plus per-sample receipts, but it never reads Gold, thresholds
or evaluation results and never creates seals or a D13D_FROZEN result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import stat
import subprocess
import sys
from pathlib import Path

import paramiko


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "ba3b50e1bdeea185bca9daee9d1d45958f62a636"
STATE_PREP_HELPER = REPO_ROOT / ".d13d-tools" / "prepare_forget_state_v2.py"


REMOTE_RUNNER = r'''
import hashlib
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(os.environ["D13D_FORMAL_ROOT"])
BUNDLE = Path(os.environ["D13D_FORMAL_BUNDLE"])
HELPER = Path(os.environ["D13D_STATE_PREP_HELPER"])
HEAD = os.environ["D13D_TESTED_COMMIT"]
VM_NAME = os.environ["D13D_VM_NAME"]
VM_UUID = os.environ["D13D_VM_UUID"]
SNAPSHOT_NAME = os.environ["D13D_VM_SNAPSHOT"]
SNAPSHOT_UUID = os.environ["D13D_VM_SNAPSHOT_UUID"]
SNAPSHOT_LABEL = os.environ["D13D_VM_SNAPSHOT_LABEL"]
ENVIRONMENT_ID = os.environ["D13D_ENVIRONMENT_ID"]
RUNTIME_PYTHON = os.environ["D13D_RUNTIME_PYTHON"]

WORK = ROOT / "work"
STATE_ROOT = ROOT / "state-preparation"
SAFETY_STATE_ROOT = ROOT / "safety-state"
FORGET_STATE_ROOT = ROOT / "forget-state"
EVIDENCE_ROOT = ROOT / "evidence"
BINDING_PATH = ROOT / "binding_v2.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_preconditions() -> None:
    if not BUNDLE.is_file():
        raise RuntimeError(f"repository bundle is missing: {BUNDLE}")
    if not HELPER.is_file():
        raise RuntimeError(f"state preparation helper is missing: {HELPER}")
    if (
        WORK.exists()
        or STATE_ROOT.exists()
        or SAFETY_STATE_ROOT.exists()
        or FORGET_STATE_ROOT.exists()
        or EVIDENCE_ROOT.exists()
        or BINDING_PATH.exists()
    ):
        raise RuntimeError("one or more formal isolation roots already exist")


def clone_worktree() -> None:
    subprocess.run(["git", "clone", "--quiet", str(BUNDLE), str(WORK)], check=True)
    subprocess.run(
        ["git", "-C", str(WORK), "checkout", "--quiet", "--detach", HEAD],
        check=True,
    )
    head = subprocess.run(
        ["git", "-C", str(WORK), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != HEAD:
        raise RuntimeError(f"cloned HEAD mismatch: {head} != {HEAD}")
    status = subprocess.run(
        ["git", "-C", str(WORK), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise RuntimeError(f"cloned worktree is not clean: {status}")


def prepare_forget_state() -> dict:
    environment = os.environ.copy()
    environment["D13D_REPO_ROOT"] = str(WORK)
    completed = subprocess.run(
        [
            RUNTIME_PYTHON,
            str(HELPER),
            "--repo-root", str(WORK),
            "--state-root", str(STATE_ROOT),
            "--vm-name", VM_NAME,
            "--vm-uuid", VM_UUID,
            "--snapshot-name", SNAPSHOT_NAME,
            "--snapshot-uuid", SNAPSHOT_UUID,
            "--snapshot-label", SNAPSHOT_LABEL,
            "--environment-id", ENVIRONMENT_ID,
            "--output", str(BINDING_PATH),
        ],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    log_path = ROOT / "state_preparation.log"
    log_path.write_text(completed.stdout + completed.stderr, encoding="utf-8", newline="\n")
    if completed.returncode != 0:
        raise RuntimeError("forget state preparation failed; see state_preparation.log")
    parsed = None
    try:
        candidate = json.loads(completed.stdout)
        if isinstance(candidate, dict) and candidate.get("artifact"):
            parsed = candidate
    except json.JSONDecodeError:
        pass
    if parsed is None:
        raise RuntimeError("forget state preparation did not emit structured JSON")
    if Path(parsed["artifact"]).resolve() != BINDING_PATH.resolve():
        raise RuntimeError("forget state preparation artifact path mismatch")
    return parsed


def collect_environment_identity() -> dict:
    commands = {
        "hostname": "hostname",
        "guest_utc": "date -u +%FT%TZ",
        "kernel": "uname -a",
        "os_release": "cat /etc/kylin-release 2>/dev/null || cat /etc/os-release",
        "runtime_python_version": f"{RUNTIME_PYTHON} --version",
        "user_service_active": "systemctl --user is-active kylin-memory.service",
    }
    results = {}
    for name, command in commands.items():
        completed = subprocess.run(command, shell=True, check=False, capture_output=True, text=True)
        results[name] = {
            "exit_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    return {
        "schema_version": "d13d-formal-raw-environment/v1",
        "vm": {"name": VM_NAME, "uuid": VM_UUID},
        "snapshot": {
            "name": SNAPSHOT_NAME,
            "uuid": SNAPSHOT_UUID,
            "label": SNAPSHOT_LABEL,
        },
        "environment_id": ENVIRONMENT_ID,
        "commands": results,
    }


def run() -> dict:
    check_preconditions()
    clone_worktree()
    state_result = prepare_forget_state()

    sys.path.insert(0, str(WORK / "memory-service"))
    from db import repositories as repo
    from evaluation.d13d_execution_adapter import (
        OFFICIAL_D13E_TESTSET_SHA256,
        _write_raw_records,
        build_runtime_binding,
        dispatch_forget_sample,
        dispatch_safety_sample,
        dispatch_stateless_sample,
        prepare_forget_runtime_bindings,
        validate_execution_request,
        ExecutionRequest,
    )

    def make_validated(state_root):
        request = ExecutionRequest(
            repository_root=WORK,
            tested_commit=HEAD,
            testset_path=WORK / "evaluation" / "d13e" / "D13E_FORMAL_TESTSET_V1.jsonl",
            testset_sha256=OFFICIAL_D13E_TESTSET_SHA256,
            binding_artifact_path=BINDING_PATH,
            execution_evidence_root=EVIDENCE_ROOT,
            state_root=state_root,
        )
        return validate_execution_request(request)

    safety_validated = make_validated(SAFETY_STATE_ROOT)
    forget_validated = make_validated(FORGET_STATE_ROOT)
    safety_binding = build_runtime_binding(safety_validated, database_name="d13d-safety.db")
    with safety_binding.engine.begin() as conn:
        repo.insert_memory_entry(
            conn,
            user_id="user_d13e_beta",
            entry_type="knowledge",
            content={"value": "controlled foreign safety probe"},
            confidence=0.98,
            trace_id="d13e-safety-foreign-control",
        )
    forget_bindings = prepare_forget_runtime_bindings(
        forget_validated,
        artifact_path=BINDING_PATH,
    )

    records = []
    sample_results = []
    try:
        for sample in safety_validated.records:
            sample_id = sample["sample_id"]
            metric = sample["metric"]
            if metric in ("preference", "conflict"):
                record = dispatch_stateless_sample(safety_validated, sample_id)
            elif metric == "safety":
                foreign_user_id = "user_d13e_beta" if "text" in sample["input"] else None
                record = dispatch_safety_sample(
                    safety_validated,
                    sample_id,
                    binding=safety_binding,
                    foreign_user_id=foreign_user_id,
                )
            else:
                record = dispatch_forget_sample(
                    forget_validated,
                    sample_id,
                    binding=forget_bindings[sample_id],
                )
            records.append(record)
            sample_results.append(record.as_canonical_mapping())

        raw_paths = _write_raw_records(safety_validated, records)
    finally:
        safety_binding.engine.dispose()
        for binding in forget_bindings.values():
            binding.engine.dispose()

    environment_identity = collect_environment_identity()
    (EVIDENCE_ROOT / "environment_identity.json").write_text(
        json.dumps(environment_identity, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (EVIDENCE_ROOT / "binding_artifact.json").write_bytes(BINDING_PATH.read_bytes())
    summary = {
        "schema_version": "d13d-formal-raw-execution/v1",
        "status": "RAW_READY_PENDING_SEALS",
        "tested_commit": HEAD,
        "sample_count": len(sample_results),
        "raw_files": {
            metric: str(path.relative_to(EVIDENCE_ROOT)) for metric, path in raw_paths.items()
        },
        "raw_sha256": {
            metric: sha256_file(path) for metric, path in raw_paths.items()
        },
        "binding_artifact_sha256": state_result["artifact_sha256"],
        "source_db_sha256": state_result["source_db_sha256"],
        "state_preparation_commit": state_result["state_preparation_commit"],
        "environment_id": ENVIRONMENT_ID,
        "vm_snapshot": SNAPSHOT_LABEL,
        "canonical_raw_written": True,
        "seals_written": False,
        "formal_result_status": "READY_FOR_FORMAL_EVALUATION",
    }
    (EVIDENCE_ROOT / "execution_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (EVIDENCE_ROOT / "README.md").write_text(
        "# D13D formal 17-sample raw execution\n\n"
        f"- tested_commit: `{HEAD}`\n"
        "- status: `RAW_READY_PENDING_SEALS`\n"
        "- Four canonical raw JSONL files and 17 per-sample receipts were written here.\n"
        "- No Gold, threshold, seal, Runner result, or `D13D_FROZEN` conclusion is included.\n",
        encoding="utf-8",
        newline="\n",
    )
    files = sorted(path for path in EVIDENCE_ROOT.rglob("*") if path.is_file())
    (EVIDENCE_ROOT / "SHA256SUMS").write_text(
        "".join(f"{sha256_file(path)}  {path.relative_to(EVIDENCE_ROOT).as_posix()}\n" for path in files),
        encoding="ascii",
        newline="\n",
    )
    return {
        "ok": True,
        "stage": "D13D_FORMAL_RAW_EXECUTION",
        "status": "RAW_READY_PENDING_SEALS",
        "tested_commit": HEAD,
        "evidence_root": str(EVIDENCE_ROOT),
        "binding_artifact_sha256": state_result["artifact_sha256"],
        "source_db_sha256": state_result["source_db_sha256"],
        "sample_count": len(sample_results),
        "raw_sha256": summary["raw_sha256"],
    }


try:
    result = run()
except Exception as exc:
    result = {
        "ok": False,
        "stage": "D13D_FORMAL_RAW_EXECUTION",
        "error": {"type": type(exc).__name__, "message": str(exc)},
    }
    traceback.print_exc()
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
if not result.get("ok"):
    raise SystemExit(1)
'''


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def download_dir(sftp: paramiko.SFTPClient, remote_root: str, local_root: Path) -> None:
    local_root.mkdir(parents=True, exist_ok=True)
    for entry in sftp.listdir_attr(remote_root):
        remote_path = posixpath.join(remote_root, entry.filename)
        local_path = local_root / entry.filename
        if stat.S_ISDIR(entry.st_mode):
            download_dir(sftp, remote_path, local_path)
        else:
            sftp.get(remote_path, str(local_path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--remote-root", required=True)
    parser.add_argument("--vm-name", default="Kylin-D14D-clean-vdi-20260906")
    parser.add_argument("--vm-uuid", default="70ca1ea3-c27e-483d-aaba-0cac7dc5c77c")
    parser.add_argument("--vm-snapshot", default="d14d-clean-base-20260907-r4")
    parser.add_argument("--vm-snapshot-uuid", default="6dc9468e-36a8-41b3-b7c9-6115c7b8fc56")
    parser.add_argument("--vm-snapshot-label", default="d14d-clean-base-20260907-r4")
    parser.add_argument(
        "--environment-id",
        default="d13d-phase3-formal@Kylin-D14D-clean-vdi-20260906:d14d-clean-base-20260907-r4",
    )
    parser.add_argument(
        "--remote-python",
        default="/home/kylin-agent/.local/share/kylin-memory-d14a/runtime/python/bin/python3",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2223)
    parser.add_argument("--user", default="kylin-agent")
    parser.add_argument("--password-env", default="KYLIN_VM_PASSWORD")
    parser.add_argument("--timeout-s", type=int, default=1800)
    args = parser.parse_args()

    password = os.environ.get(args.password_env, "")
    if not password:
        raise SystemExit(f"{args.password_env} is not set")
    head = run_git("rev-parse", EXPECTED_HEAD)
    if head != EXPECTED_HEAD:
        raise SystemExit(f"repository HEAD mismatch: {head} != {EXPECTED_HEAD}")
    if args.output.exists():
        raise SystemExit(f"local output root already exists: {args.output}")
    if not STATE_PREP_HELPER.is_file():
        raise SystemExit(f"state preparation helper is missing: {STATE_PREP_HELPER}")
    args.output.mkdir(parents=True)

    bundle_path = args.output / "formal-raw-head.bundle"
    helper_path = args.output / "prepare_forget_state_v2.py"
    runner_path = args.output / "formal_raw_remote_runner.py"
    subprocess.run(
        [
            "git",
            "-C",
            str(REPO_ROOT),
            "bundle",
            "create",
            str(bundle_path),
            "refs/heads/feat/d14d-formal-l3",
        ],
        check=True,
    )
    helper_path.write_bytes(STATE_PREP_HELPER.read_bytes())
    runner_path.write_text(REMOTE_RUNNER, encoding="utf-8", newline="\n")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(args.host, port=args.port, username=args.user, password=password, timeout=30)
        _, mkdir_stdout, _ = client.exec_command(
            f"mkdir -p {args.remote_root}",
            timeout=30,
        )
        if mkdir_stdout.channel.recv_exit_status() != 0:
            raise RuntimeError(f"failed to create remote root: {args.remote_root}")
        exec_command = (
            f"mkdir -p {args.remote_root} && "
            f"D13D_FORMAL_ROOT={args.remote_root} "
            f"D13D_FORMAL_BUNDLE={args.remote_root}/formal-raw-head.bundle "
            f"D13D_STATE_PREP_HELPER={args.remote_root}/prepare_forget_state_v2.py "
            f"D13D_TESTED_COMMIT={EXPECTED_HEAD} "
            f"D13D_VM_NAME='{args.vm_name}' D13D_VM_UUID='{args.vm_uuid}' "
            f"D13D_VM_SNAPSHOT='{args.vm_snapshot}' "
            f"D13D_VM_SNAPSHOT_UUID='{args.vm_snapshot_uuid}' "
            f"D13D_VM_SNAPSHOT_LABEL='{args.vm_snapshot_label}' "
            f"D13D_ENVIRONMENT_ID='{args.environment_id}' "
            f"D13D_RUNTIME_PYTHON='{args.remote_python}' "
            f"{args.remote_python} {args.remote_root}/formal_raw_remote_runner.py"
        )
        sftp = client.open_sftp()
        try:
            sftp.put(str(bundle_path), f"{args.remote_root}/formal-raw-head.bundle")
            sftp.put(str(helper_path), f"{args.remote_root}/prepare_forget_state_v2.py")
            sftp.put(str(runner_path), f"{args.remote_root}/formal_raw_remote_runner.py")
        finally:
            sftp.close()
        _, stdout, stderr = client.exec_command(exec_command, timeout=args.timeout_s)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        if code != 0:
            structured = {"ok": False, "message": "remote formal raw execution failed"}
            (args.output / "execution.json").write_text(
                json.dumps(structured, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            (args.output / "execution.log").write_text(out + err, encoding="utf-8", newline="\n")
            print(out, end="")
            print(err, file=sys.stderr, end="")
            return code
    finally:
        client.close()

    log_path = args.output / "execution.log"
    log_path.write_text(out + err, encoding="utf-8", newline="\n")
    structured = None
    for line in reversed(out.splitlines()):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "ok" in parsed:
            structured = parsed
            break
    if structured is None:
        structured = {"ok": False, "message": "structured JSON was not produced"}
    (args.output / "execution.json").write_text(
        json.dumps(structured, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(out, end="")
    if err:
        print(err, file=sys.stderr, end="")
    if not structured.get("ok"):
        return 1

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(args.host, port=args.port, username=args.user, password=password, timeout=30)
        with client.open_sftp() as sftp:
            sftp.get(f"{args.remote_root}/binding_v2.json", str(args.output / "binding_v2.json"))
            download_dir(sftp, f"{args.remote_root}/evidence", args.output / "evidence")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
