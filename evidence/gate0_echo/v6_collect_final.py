#!/usr/bin/env python3
"""V6 最终证据收集: 上传修复后的测试、运行、下载证据"""
import os, sys, time
import paramiko

HOST, PORT, USER, PASSWORD = "127.0.0.1", 2222, "REDACTED_VM_USER", "REDACTED_VM_PASSWORD"
REMOTE_BASE = "/home/REDACTED_VM_USER/kylin-memory-echo"
EVIDENCE_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6_final_results")

def run(c, cmd, timeout=30):
    _, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return exit_code, out, err

def sftp_put(c, local, remote):
    sftp = c.open_sftp()
    sftp.put(local, remote, confirm=True)
    sftp.close()
    print(f"  UPLOADED: {os.path.basename(local)}")

def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD, allow_agent=False, look_for_keys=False, timeout=20)
    print("Connected to VM")

    # 1. Upload fixed v6_full_test.py
    local_test = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6_full_test.py")
    remote_test = f"{REMOTE_BASE}/evidence/v6_full_test.py"
    sftp_put(c, local_test, remote_test)
    run(c, f"chmod +x {remote_test}")

    # 2. Ensure server is running
    run(c, "pkill -f kylin-memory-echo-server 2>/dev/null; sleep 0.5; rm -f /tmp/kylin-memory-echo/echo.sock", timeout=5)
    run(c, f"bash -c 'cd {REMOTE_BASE} && nohup python3 bin/kylin-memory-echo-server > logs/server_stdout.log 2> logs/server_stderr.log' </dev/null >/dev/null 2>&1 &", timeout=5)
    time.sleep(2)
    ec, out, _ = run(c, "pgrep -f kylin-memory-echo-server", timeout=5)
    print(f"  Server PID: {out.strip()}")
    ec, out, _ = run(c, "ls /tmp/kylin-memory-echo/echo.sock 2>&1")
    print(f"  Socket: {out.strip()}")

    # 3. Run evidence collection (skip KYSEC since already done)
    print("\nRunning v6_full_test.py ...")
    ec, out, err = run(c, f"cd {REMOTE_BASE} && python3 evidence/v6_full_test.py --output-dir evidence/gate0_echo_v6", timeout=120)
    print(f"  Exit code: {ec}")
    print(f"  Output:\n{out[:1500]}")
    if err:
        print(f"  Stderr: {err[:500]}")

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
    finally:
        sftp.close()

    # Download server logs too
    for log_name in ["server_stdout.log", "server_stderr.log"]:
        try:
            sftp = c.open_sftp()
            sftp.get(f"{REMOTE_BASE}/logs/{log_name}", os.path.join(EVIDENCE_LOCAL, log_name))
            sftp.close()
            print(f"  DOWNLOADED: {log_name}")
        except:
            pass

    # Cleanup
    run(c, "pkill -f kylin-memory-echo-server 2>/dev/null || true", timeout=5)
    run(c, "rm -f /tmp/kylin-memory-echo/echo.sock", timeout=5)
    c.close()

    print(f"\nEvidence saved to: {EVIDENCE_LOCAL}")
    for f in sorted(os.listdir(EVIDENCE_LOCAL)):
        print(f"  {f} ({os.path.getsize(os.path.join(EVIDENCE_LOCAL, f))} bytes)")

if __name__ == "__main__":
    main()