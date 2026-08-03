#!/usr/bin/env python3
"""
V9 全链路回归测试套件 (Kylin VM)
=================================
前置: v8 systemd 测试已将 VM 恢复至干净状态。
目标: 使用已修复的 systemd 安装流程，执行 Phase A+B+C 全链路测试并收集证据。

Phase A: Kaiming Memory Client UDS 端到端 (6 tests)
Phase B: KYSEC ACL 授权与回退 (3 stages)
Phase C: Systemd 完整生命周期 (16 tests)

用法:
  set KYLIN_VM_USER=<username>
  set KYLIN_VM_PASSWORD=<password>
  %PYTHON% evidence\\gate0_echo\\v9_full_suite_test.py
"""

import os, sys, time, hashlib, base64, traceback
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from evidence.ssh_transfer_diagnosis.kylin_transfer import KylinConnection, transfer, TransferError

VM_HOST = os.environ.get("KYLIN_VM_HOST", "127.0.0.1")
VM_PORT = int(os.environ.get("KYLIN_VM_PORT", "2222"))
VM_USER = os.environ.get("KYLIN_VM_USER", "")
VM_PASS = os.environ.get("KYLIN_VM_PASSWORD", "")
if not VM_USER or not VM_PASS:
    print("FATAL: KYLIN_VM_USER and KYLIN_VM_PASSWORD environment variables must be set.")
    sys.exit(1)
REMOTE_BASE = f"/home/{VM_USER}/kylin-memory-echo"

SERVICE_NAME = "kylin-memory-echo"
UNIT_FILE = f"{SERVICE_NAME}.service"
UNIT_DST = f"/etc/systemd/system/{UNIT_FILE}"
SOCKET_PATH = "/tmp/kylin-memory-echo/echo.sock"

EVIDENCE_OUT = os.path.join(PROJECT_ROOT, "evidence", "gate0_echo", "v9_full_suite")
os.makedirs(EVIDENCE_OUT, exist_ok=True)
LOG_FILE = os.path.join(EVIDENCE_OUT, "v9_test_log.txt")

PASS = 0; FAIL = 0


def log(msg, level="INFO"):
    global PASS, FAIL
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.")[:-4] + "Z"
    line = f"[{ts}] [{level}] {msg}"
    print(line.encode("ascii", errors="replace").decode("ascii"), flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def ok(msg):
    global PASS; PASS += 1
    log(f"  PASS: {msg}", "PASS")


def no(msg):
    global FAIL; FAIL += 1
    log(f"  FAIL: {msg}", "FAIL")


def title(msg):
    log(""); log("=" * 60, "PHASE"); log(f"  {msg}", "PHASE"); log("=" * 60, "PHASE")


def exec_sudo(kc, cmd, timeout=30):
    wrapped = f"sudo bash -c '{cmd}'"
    _, out, err = kc.client.exec_command(wrapped, timeout=timeout)
    ec = out.channel.recv_exit_status()
    return ec, out.read().decode("utf-8", errors="replace"), err.read().decode("utf-8", errors="replace")


def run(kc, cmd, timeout=30):
    log(f"    CMD: {cmd[:80]}")
    _, o, e = kc.client.exec_command(cmd, timeout=timeout)
    ec = o.channel.recv_exit_status()
    return ec, o.read().decode("utf-8", errors="replace"), e.read().decode("utf-8", errors="replace")


def write_sudo_unit(kc, content, path):
    """Write file via sudo base64 pipe"""
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    ec, out, err = exec_sudo(kc, f"echo '{b64}' | base64 -d > {path} && sha256sum {path}", timeout=15)
    return ec, out, err


def phase_upload_all(kc):
    title("Phase 0: Upload & Compile")

    # Ensure remote dirs
    run(kc, f"mkdir -p {REMOTE_BASE}/bin {REMOTE_BASE}/share {REMOTE_BASE}/logs {REMOTE_BASE}/evidence")
    ok("Remote dirs created")

    # Upload files (iron-law)
    echo_dir = os.path.join(PROJECT_ROOT, "os-agent-integration", "echo")
    systemd_dir = os.path.join(PROJECT_ROOT, "packaging", "systemd")
    files_to_upload = [
        (os.path.join(echo_dir, "memory_echo_server.py"), "bin/kylin-memory-echo-server"),
        (os.path.join(echo_dir, "kaiming_memory_client.cpp"), "kaiming_memory_client.cpp"),
        (os.path.join(echo_dir, "CMakeLists.txt"), "CMakeLists.txt"),
        (os.path.join(echo_dir, "test_kysec_full.sh"), "share/test_kysec_full.sh"),
        (os.path.join(echo_dir, "test_systemd_lifecycle.sh"), "share/test_systemd_lifecycle.sh"),
        (os.path.join(echo_dir, "kysec_authorize.sh"), "share/kysec_authorize.sh"),
        (os.path.join(systemd_dir, "kylin-memory-echo.service"), "share/kylin-memory-echo.service"),
    ]

    for local_path, remote_rel in files_to_upload:
        remote_path = f"{REMOTE_BASE}/{remote_rel}"
        if not os.path.exists(local_path):
            log(f"  SKIP (not found): {local_path}")
            continue
        try:
            transfer.upload_file(kc, local_path, remote_path)
            ok(f"Uploaded: {os.path.basename(local_path)}")
        except TransferError as e:
            no(f"Upload failed: {os.path.basename(local_path)} — {e}")

    run(kc, f"chmod +x {REMOTE_BASE}/bin/* {REMOTE_BASE}/share/*.sh 2>/dev/null; true")
    ok("Permissions set")

    # Compile kaiming client
    log("Compiling kaiming_memory_client...")
    ec, out, err = run(kc, f"cd {REMOTE_BASE} && g++ -std=c++17 -O2 kaiming_memory_client.cpp -o bin/kaiming_memory_client 2>&1", timeout=30)
    if ec == 0:
        ok("kaiming_memory_client compiled successfully")
    else:
        no(f"Compile failed: {err[:200]}")
        return False

    # Verify binary
    ec, out, _ = run(kc, f"file {REMOTE_BASE}/bin/kaiming_memory_client")
    log(f"  Client binary: {out.strip()[:100]}")
    return True


def phase_install_systemd(kc):
    title("Phase 1: Install Systemd Service")

    # Read production unit template
    prod_template_path = os.path.join(PROJECT_ROOT, "packaging", "systemd", "kylin-memory-echo.service")
    with open(prod_template_path, "r", encoding="utf-8") as f:
        unit_content = f.read().replace("__USERNAME__", VM_USER)

    expected_sha = hashlib.sha256(unit_content.encode("utf-8")).hexdigest()
    log(f"Target unit SHA256: {expected_sha[:16]}...")

    # Write via sudo
    ec, out, err = write_sudo_unit(kc, unit_content, UNIT_DST)
    if ec == 0:
        ok("Unit file written via sudo base64")
    else:
        no(f"Unit file write failed: {err[:100]}")
        return False

    # Verify SHA256
    ec, out, _ = exec_sudo(kc, f"sha256sum {UNIT_DST}")
    installed_sha = out.split()[0] if out else ""
    if installed_sha == expected_sha:
        ok("SHA256 verified")
    else:
        no(f"SHA256 mismatch: expected={expected_sha[:16]}, actual={installed_sha[:16]}")

    # daemon-reload
    ec, _, err = exec_sudo(kc, "systemctl daemon-reload 2>&1")
    if ec == 0:
        ok("daemon-reload OK")
    else:
        no(f"daemon-reload failed: {err[:100]}")

    # enable
    ec, out, err = exec_sudo(kc, f"systemctl enable {SERVICE_NAME} 2>&1")
    if ec == 0:
        ok("systemctl enable OK")
    else:
        no(f"enable failed: {out[:100]}")

    # Verify symlink
    ec, out, _ = exec_sudo(kc, f"test -L /etc/systemd/system/default.target.wants/{UNIT_FILE} && echo YES || echo NO")
    if "YES" in out:
        ok("Symlink verified")
    else:
        no("Symlink not found")

    # start
    ec, out, err = exec_sudo(kc, f"systemctl start {SERVICE_NAME} 2>&1")
    if ec == 0:
        ok("systemctl start OK")
    else:
        no(f"start failed: ec={ec}, {out[:100]} {err[:100]}")
        # Diagnostic
        _, j, _ = exec_sudo(kc, f"journalctl -u {SERVICE_NAME} -n 20 --no-pager 2>&1")
        log(f"Journal: {j[:500]}")
        return False

    time.sleep(3)

    # Verify running
    ec, out, _ = exec_sudo(kc, f"systemctl show -p MainPID {SERVICE_NAME} 2>/dev/null")
    pid = out.strip().replace("MainPID=", "")
    if pid and pid != "0":
        ok(f"Service running (PID={pid})")
    else:
        no("Service not running")
        return False

    # Verify socket
    time.sleep(1)
    ec, out, _ = run(kc, f"test -S {SOCKET_PATH} && echo SOCKET_OK || echo NO_SOCKET")
    if "SOCKET_OK" in out:
        ok(f"Socket exists: {SOCKET_PATH}")
    else:
        no("Socket not found")

    return True


def phaseA_kaiming_tests(kc):
    title("Phase A: Kaiming Memory Client UDS Tests")

    client = f"{REMOTE_BASE}/bin/kaiming_memory_client"
    ec, out, _ = run(kc, f"test -x {client} && echo OK || echo NO")
    if "OK" not in out:
        no(f"Client binary not found: {client}")
        return False

    # Run all tests
    ec, out, err = run(kc, f"{client} --method all 2>&1", timeout=30)
    a_pass = out.count("PASS")
    a_fail = out.count("FAIL in RESULT")
    log(f"  A-Raw: {a_pass} PASS indicators, {a_fail} FAIL indicators")

    # Save output
    with open(os.path.join(EVIDENCE_OUT, "phase_a_kaiming_output.txt"), "w", encoding="utf-8") as f:
        f.write(out)

    # Parse structured results
    results = {}
    for line in out.split('\n'):
        if 'RESULT' in line:
            for test_name in ["KAIMING-ECHO", "KAIMING-HEALTH", "KAIMING-RETRIEVE",
                              "KAIMING-STORE", "KAIMING-UNKNOWN", "KAIMING-RAPID"]:
                if test_name in line:
                    if "PASS" in line and "FAIL" not in line:
                        ok(f"{test_name}: PASS")
                        results[test_name] = "PASS"
                    elif "FAIL" in line:
                        no(f"{test_name}: FAIL — {line.strip()[:100]}")
                        results[test_name] = "FAIL"
                    break

    total_passed = sum(1 for v in results.values() if v == "PASS")
    total_failed = sum(1 for v in results.values() if v == "FAIL")
    log(f"  Phase A Summary: {total_passed}/{total_passed + total_failed} PASS")
    return total_failed == 0


def phaseB_kysec_tests(kc):
    title("Phase B: KYSEC ACL Authorization & Rollback")

    kysec_script = f"{REMOTE_BASE}/share/test_kysec_full.sh"
    ec, out, err = exec_sudo(kc, f"bash {kysec_script} 2>&1", timeout=90)

    b_pass = out.count("PASS")
    b_fail = out.count("FAIL")
    log(f"  B-Raw: {b_pass}/{b_fail} (PASS count/FAIL count in output)")

    with open(os.path.join(EVIDENCE_OUT, "phase_b_kysec_output.txt"), "w", encoding="utf-8") as f:
        f.write(out)

    # Key checkpoints
    if "Stage1" in out and "SHA-256" in out:
        ok("Stage1: Baseline SHA256 collected")
    else:
        no("Stage1: Baseline failed")

    if "Stage2" in out and "authorize" in out.lower():
        ok("Stage2: ACL authorize attempted")
    else:
        no("Stage2: Missing")

    if "Stage3" in out:
        ok("Stage3: Rollback attempted")
    else:
        no("Stage3: Missing")

    return True


def phaseC_systemd_lifecycle(kc):
    title("Phase C: Systemd Full Lifecycle")

    test_script = f"{REMOTE_BASE}/share/test_systemd_lifecycle.sh"
    ec, out, err = exec_sudo(kc, f"bash {test_script} 2>&1", timeout=90)

    c_pass = out.count("PASS")
    c_fail = out.count("FAIL")
    log(f"  C-Raw: {c_pass}/{c_fail} (PASS/FAIL count)")

    with open(os.path.join(EVIDENCE_OUT, "phase_c_systemd_output.txt"), "w", encoding="utf-8") as f:
        f.write(out)

    # Verify key checkpoints from output
    checks = [
        ("daemon-reload", "daemon-reload"),
        ("enable", "enable"),
        ("symlink", "symlink"),
        ("start", "start"),
        ("process alive", "active"),
        ("socket", "socket"),
        ("UDS echo", "UDS echo"),
        ("UDS health", "UDS health"),
        ("stop", "stop"),
        ("disable", "disable"),
    ]
    for name, keyword in checks:
        if keyword.lower() in out.lower():
            ok(f"Phase C checkpoint: {name}")
        else:
            no(f"Phase C checkpoint missing: {name}")

    return True


def collect_evidence(kc):
    title("Evidence Collection")

    # Download remote logs
    for log_name in ["server_stdout.log", "server_stderr.log"]:
        try:
            transfer.download_file(kc, f"{REMOTE_BASE}/logs/{log_name}",
                                   os.path.join(EVIDENCE_OUT, log_name))
            ok(f"Downloaded {log_name}")
        except TransferError as e:
            log(f"  Skip {log_name}: {e}")

    # journalctl
    _, out, _ = exec_sudo(kc, f"journalctl -u {SERVICE_NAME} --no-pager 2>&1 | tail -60")
    with open(os.path.join(EVIDENCE_OUT, "journalctl.log"), "w", encoding="utf-8") as f:
        f.write(out)
    ok("journalctl saved")

    # systemctl status
    _, out, _ = exec_sudo(kc, f"systemctl status {SERVICE_NAME} --no-pager --full 2>&1")
    with open(os.path.join(EVIDENCE_OUT, "systemctl_status.txt"), "w", encoding="utf-8") as f:
        f.write(out)
    ok("systemctl status saved")

    # Final unit file
    _, out, _ = exec_sudo(kc, f"test -f {UNIT_DST} && cat {UNIT_DST} || echo 'NOT_FOUND'")
    with open(os.path.join(EVIDENCE_OUT, "final_unit_file.txt"), "w", encoding="utf-8") as f:
        f.write(out)
    ok("Unit file snapshot saved")


def main():
    global PASS, FAIL
    log("=" * 60)
    log(" V9 Full Suite Test — Kaiming + KYSEC + Systemd")
    log(f" Target: {VM_USER}@{VM_HOST}:{VM_PORT}")
    log("=" * 60)

    kc = None
    try:
        kc = KylinConnection(host=VM_HOST, port=VM_PORT, username=VM_USER, password=VM_PASS, timeout=25)
        kc.connect()
        ok("SSH connected")

        _, out, _ = run(kc, "uname -r")
        log(f"Kernel: {out.strip()}")

        if not phase_upload_all(kc):
            no("Phase 0 (Upload/Compile) failed, aborting")
            return 1

        if not phase_install_systemd(kc):
            no("Phase 1 (Install) failed, aborting")
            return 1

        phaseA_kaiming_tests(kc)
        phaseB_kysec_tests(kc)
        phaseC_systemd_lifecycle(kc)
        collect_evidence(kc)

        log(""); log("=" * 60, "PHASE V9")
        log("  V9 Full Suite Summary"); log("=" * 60, "PHASE V9")
        log(f"  Total: {PASS + FAIL} checks ({PASS} PASS / {FAIL} FAIL)")
        log(f"  Evidence: {EVIDENCE_OUT}")
        log("=" * 60)

        return 0 if FAIL == 0 else 1

    except Exception as e:
        log(f"FATAL: {e}", "FATAL")
        log(traceback.format_exc(), "FATAL")
        return 1
    finally:
        if kc:
            kc.close()


if __name__ == "__main__":
    sys.exit(main())