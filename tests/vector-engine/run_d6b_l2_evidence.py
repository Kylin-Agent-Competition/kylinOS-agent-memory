#!/usr/bin/env python3
"""D6-B L2 外层证据编排器：记录精确命令与真实退出码。"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_RUNNER = REPO_ROOT / "tests" / "vector-engine" / "run_d6_vector_schema_filter_l2.sh"
PROVIDER_RUNNER = REPO_ROOT / "memory-service" / "tests" / "retrieval" / "run_d6_real_vector_provider_l2.py"
PROVIDER_SOURCE = REPO_ROOT / "memory-service" / "retrieval" / "real_vector_provider.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _command_output(*args: str) -> str:
    try:
        completed = subprocess.run(args, text=True, capture_output=True, check=False)
    except OSError as exc:
        return f"unavailable:{exc.__class__.__name__}"
    if completed.returncode != 0:
        return f"unavailable:exit-{completed.returncode}"
    return completed.stdout.strip()


def _required_command_output(*args: str) -> str:
    output = _command_output(*args)
    if not output or output.startswith("unavailable:"):
        raise ValueError(f"required evidence command failed: {shlex.join(args)} ({output or 'empty output'})")
    return output


def _emit_metadata(binary: Path, tested_commit: str, remote_ref: str, remote_commit: str) -> None:
    print(f"D6B_EVIDENCE_META command={shlex.join([sys.executable, *sys.argv])}", flush=True)
    print(
        f"D6B_EVIDENCE_META git_branch={_required_command_output('git', '-C', str(REPO_ROOT), 'branch', '--show-current')}",
        flush=True,
    )
    print(f"D6B_EVIDENCE_META tested_commit={tested_commit}", flush=True)
    print(f"D6B_EVIDENCE_META remote_ref={remote_ref}", flush=True)
    print(f"D6B_EVIDENCE_META remote_commit={remote_commit}", flush=True)
    print(f"D6B_EVIDENCE_META os={platform.platform()}", flush=True)
    print(
        "D6B_EVIDENCE_META packages="
        + _required_command_output("dpkg-query", "-W", "-f=${Package}=${Version};", "kylin-ai-vector-engine", "libkysdk-vector-engine-client"),
        flush=True,
    )
    for label, path in (
        ("cli_sha256", binary),
        ("bridge_sha256", REPO_ROOT / "tests" / "vector-engine" / "vector_bridge_cli.cpp"),
        ("cli_runner_sha256", CLI_RUNNER),
        ("provider_runner_sha256", PROVIDER_RUNNER),
        ("provider_sha256", PROVIDER_SOURCE),
        ("evidence_runner_sha256", Path(__file__).resolve()),
    ):
        print(f"D6B_EVIDENCE_META {label}={_sha256(path)}", flush=True)


def _run(name: str, command: list[str], *, env: dict[str, str]) -> int:
    print(f"D6B_EVIDENCE command_name={name}", flush=True)
    print(f"D6B_EVIDENCE command={shlex.join(command)}", flush=True)
    try:
        completed = subprocess.run(command, env=env, check=False)
    except OSError as exc:
        print(f"D6B_EVIDENCE command_name={name} exit_code=127 error={exc.__class__.__name__}", flush=True)
        return 127
    print(f"D6B_EVIDENCE command_name={name} exit_code={completed.returncode}", flush=True)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--bash", default="bash")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--collection-prefix", default=f"d6b_evidence_{os.getpid()}")
    parser.add_argument("--tested-commit", required=True)
    args = parser.parse_args()

    binary = Path(args.binary)
    if not binary.is_absolute() or not os.access(binary, os.X_OK):
        raise ValueError("--binary must be an executable absolute path")
    if not args.collection_prefix.startswith("d6b_"):
        raise ValueError("--collection-prefix must use the d6b_ prefix")
    actual_commit = _command_output("git", "-C", str(REPO_ROOT), "rev-parse", "HEAD")
    if actual_commit != args.tested_commit:
        raise ValueError(f"working tree HEAD {actual_commit} does not match --tested-commit {args.tested_commit}")
    if _command_output("git", "-C", str(REPO_ROOT), "status", "--porcelain"):
        raise ValueError("working tree must be clean before L2 evidence execution")
    branch = _command_output("git", "-C", str(REPO_ROOT), "branch", "--show-current")
    if not branch or branch.startswith("unavailable:"):
        raise ValueError("L2 evidence execution requires a checked-out branch")
    remote_ref = f"refs/heads/{branch}"
    remote_commit = _required_command_output("git", "-C", str(REPO_ROOT), "ls-remote", "origin", remote_ref).split()[0]
    if remote_commit != args.tested_commit:
        raise ValueError(f"remote ref {remote_ref} is {remote_commit}, expected {args.tested_commit}")

    _emit_metadata(binary, args.tested_commit, remote_ref, remote_commit)
    environment = os.environ.copy()
    cli_exit = _run(
        "cli_runner",
        [args.bash, str(CLI_RUNNER), "--binary", str(binary), "--collection", f"{args.collection_prefix}_cli"],
        env=environment,
    )
    provider_exit = _run(
        "provider_runner",
        [args.python, str(PROVIDER_RUNNER), "--cli", str(binary), "--collection", f"{args.collection_prefix}_provider"],
        env=environment,
    )
    return cli_exit if cli_exit else provider_exit


if __name__ == "__main__":
    raise SystemExit(main())
