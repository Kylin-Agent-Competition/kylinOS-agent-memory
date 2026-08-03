#!/usr/bin/env python3
"""
V6 麒麟 VM 全自动部署与测试脚本
================================
使用 Paramiko SSH 连接到麒麟虚拟机，上传文件、构建、启动服务、执行测试并收集证据。

凭据通过环境变量 KYLIN_VM_USER / KYLIN_VM_PASSWORD 传入，不硬编码。
"""
import os
import sys
import time
import traceback
from datetime import datetime, timezone

import paramiko

# ---- 连接配置 (从环境变量读取，无默认值以避免凭据泄露) ----
HOST = os.environ.get("KYLIN_VM_HOST", "127.0.0.1")
PORT = int(os.environ.get("KYLIN_VM_PORT", "2222"))
USER = os.environ.get("KYLIN_VM_USER", "")
PASSWORD = os.environ.get("KYLIN_VM_PASSWORD", "")
REMOTE_BASE = os.environ.get("KYLIN_VM_REMOTE_BASE", "")

if not USER or not PASSWORD:
    print("ERROR: 请设置环境变量 KYLIN_VM_USER 和 KYLIN_VM_PASSWORD", file=sys.stderr)
    print("  示例: export KYLIN_VM_USER=youruser KYLIN_VM_PASSWORD=yourpass", file=sys.stderr)
    sys.exit(1)

if not REMOTE_BASE:
    REMOTE_BASE = f"/home/{USER}/kylin-memory-echo"

# 本地文件路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ECHO_DIR = os.path.join(PROJECT_ROOT, "os-agent-integration", "echo")
SYSTEMD_DIR = os.path.join(PROJECT_ROOT, "packaging", "systemd")
EVIDENCE_OUT_DIR = os.path.join(PROJECT_ROOT, "evidence", "gate0_echo")

FILES_TO_UPLOAD = [
    (os.path.join(ECHO_DIR, "memory_echo_server.py"), "bin/kylin-memory-echo-server"),
    (os.path.join(ECHO_DIR, "echo_client.cpp"), "echo_client.cpp"),
    (os.path.join(ECHO_DIR, "CMakeLists.txt"), "CMakeLists.txt"),
    (os.path.join(ECHO_DIR, "kysec_authorize.sh"), "share/kysec_authorize.sh"),
    (os.path.join(ECHO_DIR, "test_rollback.sh"), "share/test_rollback.sh"),
    (os.path.join(SYSTEMD_DIR, "kylin-memory-echo.service"), "share/kylin-memory-echo.service"),
    (os.path.join(EVIDENCE_OUT_DIR, "v6_full_test.py"), "evidence/v6_full_test.py"),
]

LOG_FILE = os.path.join(EVIDENCE_OUT_DIR, "v6_deploy_test_log.txt")

# 全局失败累积
_global_failures = 0


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    line = f"[{ts}] {msg}"
    safe_line = line.encode("ascii", errors="replace").decode("ascii")
    print(safe_line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def connect_ssh():
    log("Connecting to Kylin VM SSH...")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD,
              allow_agent=False, look_for_keys=False, timeout=20)
    log(f"Connected: {USER}@{HOST}:{PORT}")
    return c


def run_ssh(c: paramiko.SSHClient, cmd: str, timeout: int = 30, background: bool = False):
    """Execute remote command, return (exit_code, stdout, stderr)"""
    # 避免记录 sudo 密码传递命令
    log_cmd = cmd
    if "echo " in cmd[:20] and "| sudo" in cmd:
        log_cmd = f"sudo <redacted> {cmd.split('| sudo', 1)[1] if '| sudo' in cmd else cmd}"
    log(f"  EXEC: {log_cmd[:120]}")
    if background:
        wrapped = f"bash -c '{cmd}' </dev/null >/dev/null 2>&1 &"
        _, stdout, stderr = c.exec_command(wrapped, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        return exit_code, "", ""
    else:
        _, stdout, stderr = c.exec_command(cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if exit_code != 0:
            log(f"  EXIT={exit_code}, stderr: {err[:200]}")
        return exit_code, out, err


def sftp_upload(c: paramiko.SSHClient, local_path: str, remote_path: str):
    sftp = c.open_sftp()
    remote_dir = os.path.dirname(remote_path)
    try:
        sftp.stat(remote_dir)
    except FileNotFoundError:
        run_ssh(c, f"mkdir -p {remote_dir}")
    log(f"  UPLOAD: {os.path.basename(local_path)} -> {remote_path}")
    sftp.put(local_path, remote_path, confirm=True)
    sftp.close()


def phase1_upload_all(c):
    log("\n========== Phase 1: Upload Files ==========")
    run_ssh(c, f"mkdir -p {REMOTE_BASE}/bin {REMOTE_BASE}/share {REMOTE_BASE}/evidence {REMOTE_BASE}/logs")
    for local, remote_rel in FILES_TO_UPLOAD:
        remote = f"{REMOTE_BASE}/{remote_rel}"
        sftp_upload(c, local, remote)
    run_ssh(c, f"chmod +x {REMOTE_BASE}/bin/kylin-memory-echo-server")
    run_ssh(c, f"chmod +x {REMOTE_BASE}/share/*.sh 2>/dev/null; true")
    run_ssh(c, f"chmod +x {REMOTE_BASE}/evidence/*.py 2>/dev/null; true")
    log("Upload complete")


def phase2_build(c):
    global _global_failures
    log("\n========== Phase 2: Build ==========")
    exit_code, out, err = run_ssh(
        c,
        f"cd {REMOTE_BASE} && g++ -std=c++17 -O2 -Wall echo_client.cpp -o bin/echo_client",
        timeout=30
    )
    if exit_code == 0:
        log("  [PASS] C++ client compiled successfully")
    else:
        log(f"  [FAIL] Compilation error: {err[-300:]}")
        _global_failures += 1

    exit_code, out, err = run_ssh(c, f"file {REMOTE_BASE}/bin/echo_client")
    log(f"  Binary: {out.strip()}")


def phase3_start_server(c):
    global _global_failures
    log("\n========== Phase 3: Start Server ==========")
    run_ssh(c, "pkill -f kylin-memory-echo-server 2>/dev/null; sleep 0.5; rm -f /tmp/kylin-memory-echo/echo.sock", timeout=5)
    run_ssh(
        c,
        f"cd {REMOTE_BASE} && nohup python3 bin/kylin-memory-echo-server > logs/server_stdout.log 2> logs/server_stderr.log",
        timeout=5, background=True
    )
    time.sleep(2)

    exit_code, out, err = run_ssh(c, "pgrep -a -f kylin-memory-echo-server", timeout=5)
    if "kylin-memory-echo-server" in out:
        log(f"  [PASS] Server started: {out.strip()}")
    else:
        log("  [FAIL] Server not running. Checking stderr:")
        _, err_out, _ = run_ssh(c, f"tail -20 {REMOTE_BASE}/logs/server_stderr.log")
        log(f"    {err_out}")
        _global_failures += 1

    exit_code, out, err = run_ssh(c, "ls -la /tmp/kylin-memory-echo/", timeout=5)
    log(f"  Socket dir: {out.strip()[:200]}")


def phase4_uds_test(c):
    global _global_failures
    log("\n========== Phase 4: UDS Echo Tests ==========")

    # Python inline client test
    py_script = '''import json, struct, socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect("/tmp/kylin-memory-echo/echo.sock")
req = json.dumps({"protocol_version":"1.0","request_id":"py001","trace_id":"trc001","method":"echo","deadline_ms":5000,"payload":{"message":"HelloKylin"}}).encode()
s.sendall(struct.pack(">I", len(req)) + req)
raw_len = s.recv(4)
resp_len = struct.unpack(">I", raw_len)[0]
raw = b""
while len(raw) < resp_len:
    raw += s.recv(resp_len - len(raw))
resp = json.loads(raw.decode())
print("STATUS:", resp.get("status"))
print("ECHO:", resp.get("data",{}).get("echo"))
s.close()
'''
    exit_code, out, err = run_ssh(c, f"python3 -c '{py_script}'", timeout=15)
    if exit_code == 0 and "ECHO: HelloKylin" in out:
        log(f"  [PASS] echo (Python): {out.strip()[:200]}")
    else:
        log(f"  [FAIL] echo (Python): exit={exit_code}, {out.strip()[:200]}")
        _global_failures += 1

    # C++ client tests
    tests = [
        ("echo", f"{REMOTE_BASE}/bin/echo_client --method echo --message 'HelloCPP'"),
        ("health", f"{REMOTE_BASE}/bin/echo_client --method health"),
        ("memory.retrieve", f"{REMOTE_BASE}/bin/echo_client --method memory.retrieve --message 'DesignPatterns'"),
    ]
    for name, cmd in tests:
        exit_code, out, err = run_ssh(c, cmd, timeout=15)
        if exit_code == 0:
            log(f"  [PASS] {name}: {out.strip()[:150]}")
        else:
            log(f"  [FAIL] {name}: exit={exit_code}, {out.strip()[:150]}")
            _global_failures += 1


def phase5_kysec(c):
    global _global_failures
    log("\n========== Phase 5: KYSEC Authorization ==========")

    # Status - 通过 sudo 执行但不在日志中暴露密码
    exit_code, out, err = run_ssh(
        c,
        f"sudo bash {REMOTE_BASE}/share/kysec_authorize.sh status",
        timeout=15
    )
    log(f"  KYSEC Status (first 500 chars):\n{out[:500]}")
    if exit_code != 0:
        _global_failures += 1

    # Authorize
    exit_code, out, err = run_ssh(
        c,
        f"sudo bash {REMOTE_BASE}/share/kysec_authorize.sh authorize",
        timeout=20
    )
    log(f"  KYSEC Authorize: exit={exit_code}")
    if exit_code != 0:
        _global_failures += 1

    # Verify UDS still accessible after authorization
    exit_code, out, err = run_ssh(
        c,
        f"{REMOTE_BASE}/bin/echo_client --method echo --message 'AfterKYSEC'",
        timeout=10
    )
    if exit_code == 0:
        log(f"  [PASS] UDS after KYSEC: exit={exit_code}")
    else:
        log(f"  [FAIL] UDS after KYSEC: exit={exit_code}")
        _global_failures += 1


def phase6_rollback(c):
    global _global_failures
    log("\n========== Phase 6: Rollback & Recovery ==========")
    run_ssh(c, "pkill -f kylin-memory-echo-server 2>/dev/null || true", timeout=5)
    time.sleep(1)
    run_ssh(c, "rm -f /tmp/kylin-memory-echo/echo.sock", timeout=5)

    exit_code, out, err = run_ssh(c, "ls /tmp/kylin-memory-echo/ 2>&1 || echo 'empty_or_missing'", timeout=5)
    log(f"  Socket cleanup: {out.strip()}")

    exit_code, out, err = run_ssh(
        c,
        f"sudo bash {REMOTE_BASE}/share/kysec_authorize.sh rollback",
        timeout=20
    )
    log(f"  KYSEC Rollback: exit={exit_code}")
    if exit_code != 0:
        _global_failures += 1

    exit_code, out, err = run_ssh(c, "pgrep -f kylin-memory-echo-server || echo 'no_process'", timeout=5)
    log(f"  Process check: {out.strip()}")


def phase7_evidence(c):
    global _global_failures
    log("\n========== Phase 7: Evidence Collection ==========")
    run_ssh(c, "pkill -f kylin-memory-echo-server 2>/dev/null; sleep 0.5; rm -f /tmp/kylin-memory-echo/echo.sock", timeout=5)
    run_ssh(c, f"cd {REMOTE_BASE} && nohup python3 bin/kylin-memory-echo-server > logs/server_stdout.log 2> logs/server_stderr.log", timeout=5, background=True)
    time.sleep(2)

    exit_code, out, err = run_ssh(
        c,
        f"cd {REMOTE_BASE} && python3 evidence/v6_full_test.py --output-dir evidence/gate0_echo_v6",
        timeout=120
    )
    log(f"  V6 test exit={exit_code}")
    log(f"  Output (last 2000):\n{out[-2000:]}")
    if exit_code != 0:
        _global_failures += 1

    # Download evidence
    evidence_remote = f"{REMOTE_BASE}/evidence/gate0_echo_v6"
    evidence_local = os.path.join(EVIDENCE_OUT_DIR, "v6_results")
    os.makedirs(evidence_local, exist_ok=True)

    sftp = c.open_sftp()
    try:
        for fname in sftp.listdir(evidence_remote):
            rp = f"{evidence_remote}/{fname}"
            lp = os.path.join(evidence_local, fname)
            sftp.get(rp, lp)
            log(f"  DOWNLOADED: {fname}")
    finally:
        sftp.close()

    for log_name in ["server_stdout.log", "server_stderr.log"]:
        try:
            sftp = c.open_sftp()
            sftp.get(f"{REMOTE_BASE}/logs/{log_name}", os.path.join(evidence_local, log_name))
            sftp.close()
            log(f"  DOWNLOADED: {log_name}")
        except Exception as e:
            log(f"  SKIP {log_name}: {e}")


def phase8_cleanup(c):
    log("\n========== Final: Cleanup ==========")
    run_ssh(c, "pkill -f kylin-memory-echo-server 2>/dev/null || true", timeout=5)
    run_ssh(c, "rm -f /tmp/kylin-memory-echo/echo.sock", timeout=5)
    log("Cleanup done")


def main():
    global _global_failures
    log("=" * 60)
    log(" V6 Kylin Memory Echo - Full Deploy & Test")
    log(f" Start: {datetime.now(timezone.utc).isoformat()}")
    log("=" * 60)

    c = None
    try:
        c = connect_ssh()

        exit_code, out, err = run_ssh(c, "uname -a")
        log(f"System: {out.strip()}")
        exit_code, out, err = run_ssh(c, "cat /etc/os-release | head -3")
        log(f"OS: {out.strip()}")

        phase1_upload_all(c)
        phase2_build(c)
        phase3_start_server(c)
        phase4_uds_test(c)
        phase5_kysec(c)
        phase6_rollback(c)
        phase7_evidence(c)
        phase8_cleanup(c)

        if _global_failures > 0:
            log("\n" + "=" * 60)
            log(f" [FAIL] {_global_failures} test phase(s) had failures")
            log(f" Evidence dir: {os.path.join(EVIDENCE_OUT_DIR, 'v6_results')}")
            log("=" * 60)
            return 1

        log("\n" + "=" * 60)
        log(" [PASS] All tests completed!")
        log(f" Evidence dir: {os.path.join(EVIDENCE_OUT_DIR, 'v6_results')}")
        log("=" * 60)

    except Exception as e:
        log(f"\n [FAIL] Test failed: {e}")
        log(traceback.format_exc())
        return 1
    finally:
        if c:
            c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())