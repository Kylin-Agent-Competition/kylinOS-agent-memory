#!/usr/bin/env python3
"""
UNTESTED test runner — UT-1 + UT-2 via SSH on Kylin VM
Uses direct paramiko (same pattern as collect_uds_test.py).
Socket path uses home dir to avoid /tmp root permission issues.
"""
import paramiko
import sys
import os
import time
import hashlib

# Config
HOST = '127.0.0.1'
PORT = 2222
USER = 'kylin-agent'
PASSWORD = os.environ.get("KYLIN_VM_PASSWORD", "")
SOCKET_DIR = '/home/kylin-agent/.echo_run'
SOCKET_PATH = SOCKET_DIR + '/echo.sock'
OUT_DIR = os.path.join(os.path.dirname(__file__), 'ut_results')
os.makedirs(OUT_DIR, exist_ok=True)
BASE = os.path.dirname(__file__)
UT1 = os.path.join(BASE, 'test_ut1_original_text_isolation.py')
UT2 = os.path.join(BASE, 'test_ut2_ipc_restart_recovery.py')

ssh = None
sftp = None

def log(msg):
    ts = time.strftime('%H:%M:%S')
    safe = msg.encode('gbk', errors='replace').decode('gbk', errors='replace')
    print("[%s] %s" % (ts, safe), flush=True)

def run(cmd, timeout=60, sudo=False):
    if sudo:
        cmd = "echo '%s' | sudo -S bash -c '%s'" % (PASSWORD, cmd)
    _, so, se = ssh.exec_command(cmd, timeout=timeout)
    ec = so.channel.recv_exit_status()
    out = so.read().decode('utf-8', errors='replace').strip()
    err = se.read().decode('utf-8', errors='replace').strip()
    return ec, out, err

def upload(local, remote):
    with open(local, 'rb') as f:
        lsha = hashlib.sha256(f.read()).hexdigest()
    for i in range(3):
        try:
            sftp.put(local, remote)
            ec, o, _ = run("sha256sum %s | awk '{print $1}'" % remote)
            if o.strip() == lsha:
                log("  Upload OK: %s" % os.path.basename(local))
                return True
        except Exception as e:
            log("  Upload attempt %d failed: %s" % (i+1, e))
    log("  Upload FAILED: %s" % os.path.basename(local))
    return False

def download(remote, local):
    for i in range(3):
        try:
            sftp.get(remote, local)
            if os.path.getsize(local) > 0:
                log("  Download OK: %s (%d bytes)" % (os.path.basename(local), os.path.getsize(local)))
                return True
        except Exception as e:
            log("  Download attempt %d failed: %s" % (i+1, e))
    return False

def main():
    global ssh, sftp
    log("=" * 60)
    log(" UT-1 / UT-2 runner starting")
    log("=" * 60)

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=15)
        sftp = ssh.open_sftp()
        log("SSH connected: %s@%s:%d" % (USER, HOST, PORT))
    except Exception as e:
        log("SSH FAILED: %s" % e)
        sys.exit(1)

    try:
        ec, out, _ = run('uname -a')
        log("Env: %s" % out[:120])
        ec, out, _ = run('echo $HOME')
        home = out.strip()
        log("HOME=%s" % home)

        # Find repo
        for c in [home+'/kylin-memory-echo', '/home/kylin-agent/kylin-memory-echo', '/home/ZhouYifan/kylin-memory-echo']:
            ec, out, _ = run('ls %s/os-agent-integration/echo/memory_echo_server.py 2>&1' % c)
            if ec == 0:
                REPO = c
                log("Repo: %s" % REPO)
                break
        else:
            log("Repo not found")
            sys.exit(1)

        SERVER = REPO + '/os-agent-integration/echo/memory_echo_server.py'

        # Upload test scripts
        log("\n--- Upload ---")
        run('mkdir -p /tmp/untested_tests')
        upload(UT1, '/tmp/untested_tests/test_ut1.py')
        upload(UT2, '/tmp/untested_tests/test_ut2.py')
        run('chmod +x /tmp/untested_tests/test_ut*.py')

        # Start Echo Server with user-owned socket path
        log("\n--- Start Echo ---")
        run('pkill -f memory_echo_server.py 2>/dev/null; sleep 1')
        run('mkdir -p %s' % SOCKET_DIR)
        run('nohup python3 %s --socket %s > /tmp/echo_ut.log 2>&1 &' % (SERVER, SOCKET_PATH))
        time.sleep(2)

        ec, out, _ = run('pgrep -f memory_echo_server.py')
        if out.strip():
            log("Server PID: %s" % out.strip())
        else:
            ec, o, _ = run('cat /tmp/echo_ut.log 2>&1')
            log("Server FAIL log: %s" % o[:300])
        ec, out, _ = run('ls -la %s 2>&1' % SOCKET_PATH)
        log("Socket: %s" % out[:150])

        # Run UT-1
        log("\n" + "=" * 60)
        log(" UT-1: original text isolation")
        log("=" * 60)
        ec, out, err = run('python3 /tmp/untested_tests/test_ut1.py 2>&1', timeout=30)
        log("UT-1 ec=%d" % ec)
        log("UT-1 output:\n%s" % out)
        if err:
            log("UT-1 stderr: %s" % err[:300])

        download('/tmp/ut1_original_text_isolation_results.txt', os.path.join(OUT_DIR, 'ut1_results.txt'))
        with open(os.path.join(OUT_DIR, 'ut1_output.log'), 'w', encoding='utf-8') as f:
            f.write("Exit: %d\n\nSTDOUT:\n%s\n\nSTDERR:\n%s" % (ec, out, err))
        p1 = out.count('[PASS]')
        f1 = out.count('[FAIL]')
        log("UT-1: %d PASS / %d FAIL" % (p1, f1))

        # Run UT-2
        log("\n" + "=" * 60)
        log(" UT-2: IPC restart recovery")
        log("=" * 60)
        ec, out, err = run('python3 /tmp/untested_tests/test_ut2.py 2>&1', timeout=120)
        log("UT-2 ec=%d" % ec)
        log("UT-2 output:\n%s" % out)
        if err:
            log("UT-2 stderr: %s" % err[:300])

        download('/tmp/ut2_ipc_restart_results.txt', os.path.join(OUT_DIR, 'ut2_results.txt'))
        with open(os.path.join(OUT_DIR, 'ut2_output.log'), 'w', encoding='utf-8') as f:
            f.write("Exit: %d\n\nSTDOUT:\n%s\n\nSTDERR:\n%s" % (ec, out, err))
        p2 = out.count('[PASS]')
        f2 = out.count('[FAIL]')
        log("UT-2: %d PASS / %d FAIL" % (p2, f2))

        # Summary
        log("\n" + "=" * 60)
        log(" SUMMARY")
        log("=" * 60)
        log(" UT-1 (isolation): %dP / %dF" % (p1, f1))
        log(" UT-2 (IPC ipc):   %dP / %dF" % (p2, f2))
        log(" Total:            %dP / %dF" % (p1+p2, f1+f2))
        log(" Results: %s" % OUT_DIR)

        with open(os.path.join(OUT_DIR, 'SUMMARY.md'), 'w', encoding='utf-8') as f:
            f.write("# UNTESTED Results\n\n")
            f.write("## UT-1: original text isolation\n  P=%d F=%d\n\n" % (p1, f1))
            f.write("## UT-2: IPC restart recovery\n  P=%d F=%d\n\n" % (p2, f2))
            f.write("## UT-3: IPC-001 matrix fix -> HOST_VERIFIED/E4 (ECHO-003)\n\n")
            f.write("## UT-4: AGT-005 matrix fix -> PARTIAL/E4 (R1+R2, origin isolation=UT-1)\n")

        run('pkill -f memory_echo_server.py 2>/dev/null')

    except Exception as e:
        log("EXCEPTION: %s" % e)
        import traceback
        traceback.print_exc()
    finally:
        if sftp:
            sftp.close()
        if ssh:
            ssh.close()
        log("SSH closed")

if __name__ == '__main__':
    main()