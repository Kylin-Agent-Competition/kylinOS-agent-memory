#!/usr/bin/env python3
"""V6 最终证据收集: 上传修复后的测试、运行、下载证据

凭据通过环境变量 KYLIN_VM_USER / KYLIN_VM_PASSWORD 传入，不硬编码。
"""
import hashlib
import os
import sys
import time

import paramiko

HOST = os.environ.get("KYLIN_VM_HOST", "127.0.0.1")
PORT = int(os.environ.get("KYLIN_VM_PORT", "2222"))
USER = os.environ.get("KYLIN_VM_USER", "")
PASSWORD = os.environ.get("KYLIN_VM_PASSWORD", "")

if not USER or not PASSWORD:
    print("ERROR: 请设置环境变量 KYLIN_VM_USER 和 KYLIN_VM_PASSWORD", file=sys.stderr)
    sys.exit(1)

REMOTE_BASE = os.environ.get("KYLIN_VM_REMOTE_BASE", f"/home/{USER}/kylin-memory-echo")
EVIDENCE_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6_final_results")

# 全局失败计数
_failures = 0


def run(c, cmd, timeout=30):
    _, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return exit_code, out, err


def sftp_put(c, local, remote):
    """Ironclad upload with SHA256 verification + retry"""
    import time
    
    l_sha = hashlib.sha256()
    with open(local, "rb") as lf:
        for chunk in iter(lambda: lf.read(65536), b""):
            l_sha.update(chunk)
    l_sha = l_sha.hexdigest()
    
    for attempt in range(3):
        sftp = c.open_sftp()
        try:
            sftp.put(local, remote, confirm=True)
        finally:
            sftp.close()
        
        time.sleep(0.3)
        _, out, _ = run(c, f"sha256sum '{remote}' 2>/dev/null || echo 'MISSING'", timeout=5)
        if "MISSING" not in out:
            r_sha = out.split()[0]
            if l_sha == r_sha:
                print(f"  UPLOADED+VERIFIED: {os.path.basename(local)} ({l_sha[:16]}...)")
                return
            else:
                print(f"  [RETRY {attempt+1}/3] SHA mismatch: local={l_sha[:16]}... remote={r_sha[:16]}...")
        else:
            print(f"  [RETRY {attempt+1}/3] remote SHA unavailable for {os.path.basename(local)}")
        
        if attempt < 2:
            time.sleep(1.0 * (attempt + 1))
    
    raise RuntimeError(f"UPLOAD FAILED after 3 retries: {os.path.basename(local)} SHA={l_sha[:16]}...")


def main():
    global _failures
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD,
              allow_agent=False, look_for_keys=False, timeout=20)
    print("Connected to VM")

    # 1. Upload fixed v6_full_test.py
    local_test = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6_full_test.py")
    remote_test = f"{REMOTE_BASE}/evidence/v6_full_test.py"
    sftp_put(c, local_test, remote_test)
    ec, _, _ = run(c, f"chmod +x {remote_test}")
    if ec != 0:
        _failures += 1

    # 2. Ensure server is running
    run(c, "pkill -f kylin-memory-echo-server 2>/dev/null; sleep 0.5; rm -f /tmp/kylin-memory-echo/echo.sock", timeout=5)
    run(c, f"bash -c 'cd {REMOTE_BASE} && nohup python3 bin/kylin-memory-echo-server > logs/server_stdout.log 2> logs/server_stderr.log' </dev/null >/dev/null 2>&1 &", timeout=5)
    time.sleep(2)
    ec, out, _ = run(c, "pgrep -f kylin-memory-echo-server", timeout=5)
    print(f"  Server PID: {out.strip()}")
    if ec != 0:
        _failures += 1

    ec, out, _ = run(c, "ls /tmp/kylin-memory-echo/echo.sock 2>&1")
    print(f"  Socket: {out.strip()}")
    if ec != 0:
        _failures += 1

    # 3. Run evidence collection (skip KYSEC since already done)
    print("\nRunning v6_full_test.py ...")
    ec, out, err = run(c, f"cd {REMOTE_BASE} && python3 evidence/v6_full_test.py --output-dir evidence/gate0_echo_v6", timeout=120)
    print(f"  Exit code: {ec}")
    print(f"  Output:\n{out[:1500]}")
    if err:
        print(f"  Stderr: {err[:500]}")
    if ec != 0:
        _failures += 1

    # 4. Download evidence
    os.makedirs(EVIDENCE_LOCAL, exist_ok=True)
    evidence_remote = f"{REMOTE_BASE}/evidence/gate0_echo_v6"
    sftp = c.open_sftp()
    try:
        for fname in sftp.listdir(evidence_remote):
            sftp.get(f"{evidence_remote}/{fname}", os.path.join(EVIDENCE_LOCAL, fname))
            print(f"  DOWNLOADED: {fname}")
    except Exception as e:
        print(f"  Download error: {e}")
        _failures += 1
    finally:
        sftp.close()

    # Download server logs too
    for log_name in ["server_stdout.log", "server_stderr.log"]:
        try:
            sftp = c.open_sftp()
            sftp.get(f"{REMOTE_BASE}/logs/{log_name}", os.path.join(EVIDENCE_LOCAL, log_name))
            sftp.close()
            print(f"  DOWNLOADED: {log_name}")
        except Exception:
            pass

    # Cleanup
    run(c, "pkill -f kylin-memory-echo-server 2>/dev/null || true", timeout=5)
    run(c, "rm -f /tmp/kylin-memory-echo/echo.sock", timeout=5)
    c.close()

    print(f"\nEvidence saved to: {EVIDENCE_LOCAL}")
    for f in sorted(os.listdir(EVIDENCE_LOCAL)):
        print(f"  {f} ({os.path.getsize(os.path.join(EVIDENCE_LOCAL, f))} bytes)")

    return 1 if _failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())