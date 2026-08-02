#!/usr/bin/env python3
"""V6 Pure download: pull evidence files from Kylin VM"""
import os, sys
import paramiko

HOST, PORT, USER, PASSWORD = "127.0.0.1", 2222, "REDACTED_VM_USER", "REDACTED_VM_PASSWORD"
REMOTE_BASE = "/home/REDACTED_VM_USER/kylin-memory-echo"
EVIDENCE_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6_final_results")

def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD, allow_agent=False, look_for_keys=False, timeout=20)
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
                print(f"  OK: {fname} ({size} bytes)")
        except Exception as e:
            print(f"  SKIP {remote_dir}: {e}")

    sftp.close()
    c.close()

    print(f"\nTotal files in {EVIDENCE_LOCAL}:")
    total_bytes = 0
    for f in sorted(os.listdir(EVIDENCE_LOCAL)):
        sz = os.path.getsize(os.path.join(EVIDENCE_LOCAL, f))
        total_bytes += sz
        print(f"  {f} ({sz} bytes)")
    print(f"Total: {total_bytes} bytes")

if __name__ == "__main__":
    main()