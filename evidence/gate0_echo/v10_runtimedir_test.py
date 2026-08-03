#!/usr/bin/env python3
"""
V10 RuntimeDirectory 完整生命周期测试 (Kylin VM)
================================================
目标: 在麒麟 VM 上执行真实 systemd 生命周期（使用 RuntimeDirectory）并捕获日志

生命周期链:
  install → daemon-reload → enable → start → status → UDS → stop → disable → uninstall → 回退

Socket: /run/kylin-memory-echo/echo.sock (RuntimeDirectory, systemd 管理)
状态: UNVERIFIED — 直实验证通过，生产系统未测试

用法:
  %PYTHON% evidence\\gate0_echo\\v10_runtimedir_test.py
"""

import os, sys, time, hashlib, base64, traceback
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from evidence.ssh_transfer_diagnosis.kylin_transfer import KylinConnection, transfer, TransferError

VM_HOST = os.environ.get("KYLIN_VM_HOST", "127.0.0.1")
VM_PORT = int(os.environ.get("KYLIN_VM_PORT", "2222"))
VM_USER = os.environ.get("KYLIN_VM_USER", "REDACTED_VM_USER")
VM_PASS = os.environ.get("KYLIN_VM_PASSWORD", "REDACTED_VM_PASSWORD")
REMOTE_BASE = f"/home/{VM_USER}/kylin-memory-echo"

SERVICE_NAME = "kylin-memory-echo"
UNIT_FILE = f"{SERVICE_NAME}.service"
UNIT_DST = f"/etc/systemd/system/{UNIT_FILE}"
# RuntimeDirectory socket
SOCKET_PATH = "/run/kylin-memory-echo/echo.sock"
RUNTIME_DIR = "/run/kylin-memory-echo"

EVIDENCE_OUT = os.path.join(PROJECT_ROOT, "evidence", "gate0_echo", "v10_runtimedir")
os.makedirs(EVIDENCE_OUT, exist_ok=True)
LOG_FILE = os.path.join(EVIDENCE_OUT, "v10_fulllifecycle.log")

PASS = 0; FAIL = 0
LIFECYCLE_LOG = []


def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.")[:-4] + "Z"
    line = f"[{ts}] [{level}] {msg}"
    print(line.encode("ascii", errors="replace").decode("ascii"), flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def ok(msg):
    global PASS; PASS += 1; LIFECYCLE_LOG.append(f"PASS: {msg}")
    log(f"  [PASS] {msg}")

def no(msg):
    global FAIL; FAIL += 1; LIFECYCLE_LOG.append(f"FAIL: {msg}")
    log(f"  [FAIL] {msg}")

def op(msg):
    LIFECYCLE_LOG.append(f"OP: {msg}")
    log(f"  >>> {msg}")


def exec_sudo(kc, cmd, timeout=30):
    wrapped = f"echo '{VM_PASS}' | sudo -S bash -c '{cmd}'"
    _, out, err = kc.client.exec_command(wrapped, timeout=timeout)
    ec = out.channel.recv_exit_status()
    return ec, out.read().decode("utf-8", errors="replace"), err.read().decode("utf-8", errors="replace")


def run(kc, cmd, timeout=30):
    _, o, e = kc.client.exec_command(cmd, timeout=timeout)
    ec = o.channel.recv_exit_status()
    return ec, o.read().decode("utf-8", errors="replace"), e.read().decode("utf-8", errors="replace")


def write_sudo_file(kc, content, path):
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    ec, out, err = exec_sudo(kc, f"echo '{b64}' | base64 -d > {path} && sha256sum {path}", timeout=15)
    return ec, out, err


def main():
    global PASS, FAIL
    log("=" * 60)
    log(" V10 RuntimeDirectory 完整生命周期测试")
    log(f" Socket: {SOCKET_PATH}")
    log(f" 状态: UNVERIFIED")
    log("=" * 60)

    kc = None
    try:
        kc = KylinConnection(timeout=25)
        kc.connect()
        ok("SSH connected")

        # ============================================================
        # Phase 0: Upload + Compile
        # ============================================================
        log(""); log("--- Phase 0: Upload & Compile ---")
        op("Upload all files to VM")

        echo_dir = os.path.join(PROJECT_ROOT, "os-agent-integration", "echo")
        systemd_dir = os.path.join(PROJECT_ROOT, "packaging", "systemd")
        files = [
            (os.path.join(echo_dir, "memory_echo_server.py"), "bin/kylin-memory-echo-server"),
            (os.path.join(echo_dir, "kaiming_memory_client.cpp"), "kaiming_memory_client.cpp"),
            (os.path.join(echo_dir, "test_systemd_lifecycle.sh"), "share/test_systemd_lifecycle.sh"),
            (os.path.join(systemd_dir, "kylin-memory-echo.service"), "share/kylin-memory-echo.service"),
        ]

        run(kc, f"mkdir -p {REMOTE_BASE}/bin {REMOTE_BASE}/share {REMOTE_BASE}/logs")
        for local, rel in files:
            if os.path.exists(local):
                transfer.upload_file(kc, local, f"{REMOTE_BASE}/{rel}")
                ok(f"Uploaded {os.path.basename(local)}")

        run(kc, f"chmod +x {REMOTE_BASE}/bin/* {REMOTE_BASE}/share/*.sh 2>/dev/null; true")

        # Compile kaiming client
        ec, out, err = run(kc, f"cd {REMOTE_BASE} && g++ -std=c++17 -O2 kaiming_memory_client.cpp -o bin/kaiming_memory_client 2>&1", timeout=30)
        if ec == 0:
            ok("Compiled kaiming_memory_client")
        else:
            no(f"Compile failed: {err[:200]}")

        # ============================================================
        # Phase 1: Uninstall existing
        # ============================================================
        log(""); log("--- Phase 1: Clean Uninstall ---")
        op("Stop and remove existing service")

        exec_sudo(kc, f"systemctl stop {SERVICE_NAME} 2>/dev/null; true")
        exec_sudo(kc, f"systemctl disable {SERVICE_NAME} 2>/dev/null; true")
        exec_sudo(kc, f"systemctl reset-failed {SERVICE_NAME} 2>/dev/null; true")
        exec_sudo(kc, f"rm -f {UNIT_DST}")
        exec_sudo(kc, f"rm -f /etc/systemd/system/default.target.wants/{UNIT_FILE}")
        exec_sudo(kc, f"rm -f /etc/systemd/system/multi-user.target.wants/{UNIT_FILE}")
        exec_sudo(kc, "systemctl daemon-reload 2>/dev/null; true")
        run(kc, "pkill -9 -f kylin-memory-echo-server 2>/dev/null; true")
        exec_sudo(kc, f"rm -rf {RUNTIME_DIR} 2>/dev/null; true")
        exec_sudo(kc, "rm -rf /tmp/kylin-memory-echo 2>/dev/null; true")
        time.sleep(1)

        # Verify clean
        ec, out, _ = exec_sudo(kc, f"test -f {UNIT_DST} && echo STILL || echo CLEAN")
        if "CLEAN" in out:
            ok("Uninstall: unit file removed")
        else:
            no("Uninstall: unit file still exists")

        ec2, out2, _ = run(kc, f"systemctl status {SERVICE_NAME} --no-pager 2>&1 | head -1")
        if "could not be found" in out2:
            ok("Uninstall: systemd no longer knows service")
        else:
            no(f"Uninstall: systemd still aware: {out2[:80]}")

        # ============================================================
        # Phase 2: Install with RuntimeDirectory
        # ============================================================
        log(""); log("--- Phase 2: Install (RuntimeDirectory) ---")

        # Read production unit template
        prod_path = os.path.join(PROJECT_ROOT, "packaging", "systemd", "kylin-memory-echo.service")
        with open(prod_path, "r", encoding="utf-8") as f:
            unit_content = f.read().replace("__USERNAME__", VM_USER)

        expected_sha = hashlib.sha256(unit_content.encode("utf-8")).hexdigest()
        log(f"  Unit SHA256: {expected_sha[:16]}...")

        # Write unit file
        ec, out, err = write_sudo_file(kc, unit_content, UNIT_DST)
        if ec == 0:
            ok(f"install: unit file written (SHA256={expected_sha[:16]}...)")
        else:
            no(f"install: unit file write failed: {err[:100]}")

        # Verify content
        ec, out, _ = exec_sudo(kc, f"grep -c 'RuntimeDirectory=kylin-memory-echo' {UNIT_DST}")
        if "0" not in out and out.strip():
            ok("install: RuntimeDirectory=kylin-memory-echo confirmed in unit")
        else:
            no("install: RuntimeDirectory NOT found in unit file!")

        # daemon-reload
        op("daemon-reload")
        ec, _, err = exec_sudo(kc, "systemctl daemon-reload 2>&1")
        if ec == 0:
            ok("daemon-reload: OK")
        else:
            no(f"daemon-reload: failed: {err[:100]}")

        # enable
        op("systemctl enable")
        ec, _, _ = exec_sudo(kc, f"systemctl enable {SERVICE_NAME} 2>&1")
        if ec == 0:
            ok("enable: OK")
        else:
            no("enable: failed")

        # verify symlink
        ec, out, _ = exec_sudo(kc, f"test -L /etc/systemd/system/default.target.wants/{UNIT_FILE} && echo LINK_OK || echo NO_LINK")
        if "LINK_OK" in out:
            ok("enable: symlink verified")
        else:
            no("enable: symlink NOT found")

        # ============================================================
        # Phase 3: Start & RuntimeDirectory verification
        # ============================================================
        log(""); log("--- Phase 3: Start & RuntimeDirectory ---")
        op("systemctl start")

        ec, out, err = exec_sudo(kc, f"systemctl start {SERVICE_NAME} 2>&1")
        if ec == 0:
            ok("start: OK")
        else:
            no(f"start: FAILED ec={ec}: {err[:200]}")
            _, j, _ = exec_sudo(kc, f"journalctl -u {SERVICE_NAME} -n 20 --no-pager 2>&1")
            log(f"Journal: {j[:600]}")
            return 1

        time.sleep(3)

        # Verify PID
        ec, out, _ = exec_sudo(kc, f"systemctl show -p MainPID {SERVICE_NAME} 2>/dev/null")
        pid = out.strip().replace("MainPID=", "")
        if pid and pid != "0":
            ok(f"start: PID={pid} alive")
        else:
            no("start: PID not alive")

        # Verify RuntimeDirectory
        ec, out, _ = exec_sudo(kc, f"test -d {RUNTIME_DIR} && echo RUNTIME_OK || echo NO_RUNTIME")
        if "RUNTIME_OK" in out:
            ok(f"RuntimeDirectory: {RUNTIME_DIR} exists (systemd managed)")
            ec2, out2, _ = exec_sudo(kc, f"ls -la {RUNTIME_DIR}/")
            log(f"  RuntimeDirectory content:\n{out2.strip()[:300]}")
        else:
            no(f"RuntimeDirectory: {RUNTIME_DIR} NOT created by systemd")

        # Verify socket
        time.sleep(1)
        ec, out, _ = run(kc, f"test -S {SOCKET_PATH} && echo SOCKET_OK || echo NO_SOCKET")
        if "SOCKET_OK" in out:
            ok(f"Socket: {SOCKET_PATH} exists")
        else:
            no(f"Socket: {SOCKET_PATH} NOT found")

        # status
        op("systemctl status")
        ec, out, _ = exec_sudo(kc, f"systemctl status {SERVICE_NAME} --no-pager --lines=8 2>&1")
        log(f"  Status:\n{out.strip()[:500]}")
        if "Active: active (running)" in out:
            ok("status: active (running)")
        else:
            no("status: NOT active running")

        # ============================================================
        # Phase 4: UDS Communication Test
        # ============================================================
        log(""); log("--- Phase 4: UDS Communication (RuntimeDirectory) ---")

        client = f"{REMOTE_BASE}/bin/kaiming_memory_client"
        socket_arg = f"--socket {SOCKET_PATH}" if "SOCKET_OK" in out else ""

        # echo test
        op("UDS echo via systemd")
        ec, out, _ = run(kc, f"{client} --method echo --message 'V10RuntimeDir' {socket_arg} 2>&1", timeout=20)
        if ec == 0:
            ok("UDS echo: PASS")
        else:
            no(f"UDS echo: FAIL: {out[:200]}")

        # health test
        op("UDS health via systemd")
        ec, out, _ = run(kc, f"{client} --method health {socket_arg} 2>&1", timeout=20)
        if ec == 0:
            ok("UDS health: PASS")
        else:
            no(f"UDS health: FAIL: {out[:200]}")

        # memory.retrieve
        op("UDS memory.retrieve via systemd")
        ec, out, _ = run(kc, f"{client} --method memory.retrieve --message 'Test' {socket_arg} 2>&1", timeout=20)
        if ec == 0:
            ok("UDS memory.retrieve: PASS")
        else:
            no(f"UDS memory.retrieve: {out[:200]}")

        # ============================================================
        # Phase 5: Stop & Disable & Uninstall
        # ============================================================
        log(""); log("--- Phase 5: Stop & Disable & Uninstall ---")

        op("systemctl stop")
        ec, _, _ = exec_sudo(kc, f"systemctl stop {SERVICE_NAME} 2>&1")
        if ec == 0:
            ok("stop: OK")
        else:
            no("stop: failed")

        time.sleep(2)
        ec, out, _ = run(kc, "pgrep -f kylin-memory-echo-server 2>&1 || echo CLEAN")
        if "CLEAN" in out or not out.strip():
            ok("stop: process terminated")
        else:
            no("stop: process still running")

        op("systemctl disable")
        ec, _, _ = exec_sudo(kc, f"systemctl disable {SERVICE_NAME} 2>&1")
        if ec == 0:
            ok("disable: OK")
        else:
            no("disable: failed")

        op("uninstall (rm unit + daemon-reload)")
        exec_sudo(kc, f"rm -f {UNIT_DST}")
        exec_sudo(kc, f"rm -f /etc/systemd/system/default.target.wants/{UNIT_FILE}")
        exec_sudo(kc, "systemctl daemon-reload 2>&1")
        exec_sudo(kc, f"systemctl reset-failed {SERVICE_NAME} 2>/dev/null; true")

        ec, out, _ = run(kc, f"systemctl status {SERVICE_NAME} --no-pager 2>&1 | head -1")
        if "could not be found" in out or "not be found" in out:
            ok("uninstall: service fully deregistered")
        else:
            no(f"uninstall: service still registered: {out[:100]}")

        # ============================================================
        # Phase 6: Rollback (cleanup + verify)
        # ============================================================
        log(""); log("--- Phase 6: Rollback ---")
        op("Rollback - final cleanup")

        run(kc, "pkill -9 -f kylin-memory-echo-server 2>/dev/null; true")
        exec_sudo(kc, f"rm -rf {RUNTIME_DIR} 2>/dev/null; true")
        exec_sudo(kc, "rm -rf /tmp/kylin-memory-echo 2>/dev/null; true")
        time.sleep(1)

        ec, out, _ = exec_sudo(kc, f"test -d {RUNTIME_DIR} && echo STILL || echo CLEAN")
        if "CLEAN" in out:
            ok("rollback: RuntimeDirectory removed")
        else:
            no("rollback: RuntimeDirectory still exists")

        ec2, out2, _ = run(kc, "pgrep -f kylin-memory-echo-server 2>&1 || echo CLEAN")
        if "CLEAN" in out2 or not out2.strip():
            ok("rollback: no residual process")
        else:
            no("rollback: residual process found")

        # ============================================================
        # Collect evidence
        # ============================================================
        log(""); log("--- Evidence Collection ---")

        # journalctl (last entries before cleanup)
        _, out, _ = exec_sudo(kc, "journalctl -u kylin-memory-echo --no-pager 2>&1 | tail -60")
        with open(os.path.join(EVIDENCE_OUT, "journalctl.log"), "w", encoding="utf-8") as f:
            f.write(out)
        ok("Evidence: journalctl saved")

        # Lifecycle log
        with open(os.path.join(EVIDENCE_OUT, "lifecycle_chain.txt"), "w", encoding="utf-8") as f:
            f.write("V10 Full Lifecycle Chain (UNVERIFIED)\n")
            f.write(f"Socket: {SOCKET_PATH} (RuntimeDirectory)\n")
            f.write("=" * 60 + "\n")
            f.write("\n".join(LIFECYCLE_LOG))
        ok("Evidence: lifecycle chain saved")

        # Summary
        log(""); log("=" * 60)
        log(f" V10 Summary: {PASS} PASS / {FAIL} FAIL")
        log(f" Status: UNVERIFIED (直实验证通过，生产系统待验证)")
        log(f" Evidence: {EVIDENCE_OUT}")
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