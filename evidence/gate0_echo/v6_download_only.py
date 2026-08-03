#!/usr/bin/env python3
"""V6 Pure download: pull evidence files from Kylin VM

凭据通过环境变量 KYLIN_VM_USER / KYLIN_VM_PASSWORD 传入，不硬编码。

用法:
  python3 v6_download_only.py [--output-dir evidence/gate0_echo/v6_final_results]
"""
import argparse
import os
import sys

import paramiko

HOST = os.environ.get("KYLIN_VM_HOST", "127.0.0.1")
PORT = int(os.environ.get("KYLIN_VM_PORT", "2222"))
USER = os.environ.get("KYLIN_VM_USER", "")
PASSWORD = os.environ.get("KYLIN_VM_PASSWORD", "")

if not USER or not PASSWORD:
    print("ERROR: 请设置环境变量 KYLIN_VM_USER 和 KYLIN_VM_PASSWORD", file=sys.stderr)
    sys.exit(1)

REMOTE_BASE = os.environ.get("KYLIN_VM_REMOTE_BASE", f"/home/{USER}/kylin-memory-echo")

DEFAULT_OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6_final_results")
parser = argparse.ArgumentParser(description="V6 证据下载")
parser.add_argument("--output-dir", default=DEFAULT_OUTPUT, help=f"证据输出目录 (默认: {DEFAULT_OUTPUT})")
EVIDENCE_LOCAL = parser.parse_args().output_dir

_failures = 0


def main():
    global _failures
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD,
              allow_agent=False, look_for_keys=False, timeout=20)
    print("Connected")

    # Check what's on remote
    _, stdout, _ = c.exec_command(f"ls -la {REMOTE_BASE}/evidence/gate0_echo_v6/ 2>&1", timeout=10)
    print("Remote evidence dir:")
    print(stdout.read().decode())

    # Check server logs
    _, stdout, _ = c.exec_command(f"ls -la {REMOTE_BASE}/logs/ 2>&1", timeout=10)
    print("Remote logs dir:")
    print(stdout.read().decode())

    # Download all
    os.makedirs(EVIDENCE_LOCAL, exist_ok=True)
    sftp = c.open_sftp()

    for remote_dir, local_dir in [
        (f"{REMOTE_BASE}/evidence/gate0_echo_v6", EVIDENCE_LOCAL),
        (f"{REMOTE_BASE}/logs", EVIDENCE_LOCAL),
    ]:
        try:
            for fname in sftp.listdir(remote_dir):
                remote_path = f"{remote_dir}/{fname}"
                local_path = os.path.join(local_dir, fname)
                sftp.get(remote_path, local_path)
                size = os.path.getsize(local_path)
                if size == 0:
                    print(f"  WARN: {fname} downloaded but is EMPTY (0 bytes) - possible transfer failure")
                    _failures += 1
                else:
                    print(f"  OK: {fname} ({size} bytes)")
        except Exception as e:
            print(f"  SKIP {remote_dir}: {e}")
            _failures += 1

    sftp.close()
    c.close()

    print(f"\nTotal files in {EVIDENCE_LOCAL}:")
    total_bytes = 0
    for f in sorted(os.listdir(EVIDENCE_LOCAL)):
        sz = os.path.getsize(os.path.join(EVIDENCE_LOCAL, f))
        total_bytes += sz
        print(f"  {f} ({sz} bytes)")
    print(f"Total: {total_bytes} bytes")

    return 1 if _failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())