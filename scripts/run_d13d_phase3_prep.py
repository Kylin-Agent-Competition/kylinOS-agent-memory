#!/usr/bin/env python3
"""Collect a read-only D13D Phase 3 preflight into a non-formal evidence root.

This tool never runs a formal Runner, creates raw records, or writes seals.
It only records whether the isolated Kylin VM is ready for later preparation
work such as G5/G6 provider and bridge bring-up.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
from typing import Any

import paramiko


HOST = "127.0.0.1"
PORT = 2222
USER = "kylin-agent"
TRUST_ROOT = "/etc/kylin-memory/trust"
TRUST_FILES = (
    "D13E_TRUST_ROOTS_V1.json",
    "d13e-review-public.pem",
    "d13d-execution-public.pem",
)
ARTIFACTS = (
    "evaluation/d13e/D13E_FORMAL_TESTSET_V1.jsonl",
    "evaluation/d13e/D13E_GOLD_V1.jsonl",
    "evaluation/d13e/D13E_FORMAL_THRESHOLDS_V1.json",
    "evaluation/d13e/D13E_FORMAL_MANIFEST_V1.json",
    "scripts/run_d13e_formal_eval.py",
)


def commands(guest_repo: str) -> list[tuple[str, str]]:
    repo = pathlib.PurePosixPath(guest_repo)
    trust_paths = [TRUST_ROOT] + [f"{TRUST_ROOT}/{name}" for name in TRUST_FILES]
    artifact_paths = [f"{repo / path}" for path in ARTIFACTS]
    return [
        ("guest_utc", "date -u +%FT%TZ"),
        ("hostname", "hostname"),
        ("identity", "id -un; id -u"),
        ("kernel", "uname -a"),
        (
            "os_release",
            "cat /etc/kylin-release 2>/dev/null || cat /etc/os-release",
        ),
        ("guest_repo_head", f"git -C {repo} rev-parse HEAD"),
        ("guest_repo_branch", f"git -C {repo} branch --show-current"),
        ("guest_repo_status", f"git -C {repo} status --porcelain"),
        (
            "service_active",
            "systemctl --user is-active kylin-memory.service",
        ),
        (
            "service_unit",
            "systemctl --user cat kylin-memory.service",
        ),
        (
            "service_socket_stat",
            'stat -c "%a %U:%G %n" "$XDG_RUNTIME_DIR/kylin-memory/memory.sock"',
        ),
        ("python_version", "python3 --version"),
        ("sqlite_version", "sqlite3 --version"),
        (
            "vector_client_package",
            "dpkg-query -W -f='${Package} ${Version}\\n' libkysdk-vector-engine-client",
        ),
        (
            "vector_client_header_candidates",
            "dpkg-query -L libkysdk-vector-engine-client | grep -E '(Database\\.h|include)'",
        ),
        (
            "vector_client_dynamic_symbols",
            "nm -D /usr/lib/x86_64-linux-gnu/libkysdk-vector-engine-client.so.1 "
            "| grep -E '(Database|open|close|upsert|search|delete)'",
        ),
        ("d13e_artifact_hashes", "sha256sum " + " ".join(artifact_paths)),
        ("trust_root_stat", "sudo -n stat -c '%U %G %a %n' " + " ".join(trust_paths)),
        (
            "trust_root_symlinks",
            f"sudo -n find {TRUST_ROOT} -maxdepth 1 -type l -print",
        ),
        (
            "trust_root_hashes",
            "sudo -n sha256sum " + " ".join(f"{TRUST_ROOT}/{name}" for name in TRUST_FILES),
        ),
    ]


def run_remote(
    client: paramiko.SSHClient,
    entries: list[tuple[str, str]],
    *,
    timeout_s: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name, command in entries:
        _, stdout, stderr = client.exec_command(command, timeout=timeout_s)
        exit_code = stdout.channel.recv_exit_status()
        results.append(
            {
                "name": name,
                "command": command,
                "exit_code": exit_code,
                "stdout": stdout.read().decode("utf-8", errors="replace"),
                "stderr": stderr.read().decode("utf-8", errors="replace"),
            }
        )
    return results


def write_commands_log(root: pathlib.Path, results: list[dict[str, Any]]) -> None:
    with (root / "commands.log").open("w", encoding="utf-8", newline="\n") as fh:
        for result in results:
            fh.write(f"===== {result['name']} =====\n")
            fh.write(f"command={result['command']}\n")
            fh.write(f"exit_code={result['exit_code']}\n")
            fh.write("--- stdout ---\n")
            fh.write(result["stdout"])
            fh.write("--- stderr ---\n")
            fh.write(result["stderr"])


def write_checksums(root: pathlib.Path, files: list[pathlib.Path]) -> None:
    with (root / "SHA256SUMS").open("w", encoding="ascii", newline="\n") as fh:
        for path in sorted(files):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            fh.write(f"{digest}  {path.relative_to(root).as_posix()}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_root", type=pathlib.Path, nargs="?")
    parser.add_argument("--guest-repo", default="/home/kylin-agent/kylinOS-agent-memory")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--password-env", default="KYLIN_VM_PASSWORD")
    parser.add_argument("--timeout-s", type=int, default=30)
    parser.add_argument(
        "--list-commands",
        action="store_true",
        help="print the read-only command list and exit without connecting",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    entries = commands(args.guest_repo)
    if args.list_commands:
        for name, command in entries:
            print(f"{name}\t{command}")
        return 0

    if args.output_root is None:
        print("ERROR: output_root is required unless --list-commands is used", file=sys.stderr)
        return 2

    password = os.environ.get(args.password_env, "")
    if not password:
        print(f"ERROR: {args.password_env} is not set", file=sys.stderr)
        return 2
    if args.output_root.exists():
        print(f"ERROR: output root already exists: {args.output_root}", file=sys.stderr)
        return 2
    if args.timeout_s < 1:
        print("ERROR: --timeout-s must be positive", file=sys.stderr)
        return 2

    args.output_root.mkdir(parents=False, exist_ok=False)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(args.host, port=args.port, username=USER, password=password, timeout=20)
        results = run_remote(client, entries, timeout_s=args.timeout_s)
    finally:
        client.close()

    status = "PASS" if all(result["exit_code"] == 0 for result in results) else "BLOCKED"
    created_at = dt.datetime.now(dt.timezone.utc).isoformat()
    payload = {
        "schema_version": "d13d-phase3-prep/v1",
        "scope": "PREPARATION / NON-FORMAL",
        "status": status,
        "created_at_utc": created_at,
        "guest_repo": args.guest_repo,
        "formal_execution_performed": False,
        "limitations": [
            "This preflight is not formal evidence.",
            "It does not select tested_commit, create raw, sign a seal, run Runner, or freeze D13D.",
            "A failed or unavailable command leaves the whole preflight BLOCKED.",
        ],
        "commands": results,
    }
    preflight_path = args.output_root / "environment_preflight.json"
    preflight_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    write_commands_log(args.output_root, results)
    readme_path = args.output_root / "README.md"
    readme_path.write_text(
        "# D13D Phase 3 preparation preflight\n\n"
        f"- scope: `PREPARATION / NON-FORMAL`\n"
        f"- created_at_utc: `{created_at}`\n"
        f"- status: `{status}`\n\n"
        "This directory is not a formal execution evidence root and must not be used as one.\n",
        encoding="utf-8",
        newline="\n",
    )
    write_checksums(args.output_root, [preflight_path, args.output_root / "commands.log", readme_path])
    print(f"WROTE {args.output_root} status={status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("ERROR: interrupted", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:  # noqa: BLE001 - host-side prep tool keeps errors actionable
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
