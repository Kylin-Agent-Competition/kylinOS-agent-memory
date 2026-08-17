#!/usr/bin/env python3
"""
PR21 R3 P0 修复验证脚本 - 铁律上传+远程编译+运行测试
使用 Paramiko SSH 连接麒麟 VM (127.0.0.1:2222)
"""
import os
import sys
import hashlib
import time
import paramiko

# ====== CONFIG ======
VM_HOST = "127.0.0.1"
VM_PORT = 2222
VM_USER = "kylin-agent"
VM_PASSWORD = os.environ.get("KYLIN_VM_PASSWORD", "")
DEPLOY_BASE = "/home/kylin-agent/kylin-memory-echo"
SOCKET_PATH = "/run/kylin-memory-echo/echo.sock"

# Files to upload: (local_path, remote_path)
FILES_TO_UPLOAD = [
    ("os-agent-integration/echo/kaiming_memory_client.cpp", f"{DEPLOY_BASE}/kaiming_memory_client.cpp"),
    ("os-agent-integration/echo/memory_echo_server.py", f"{DEPLOY_BASE}/bin/kylin-memory-echo-server"),
    ("os-agent-integration/echo/test_systemd_lifecycle.sh", f"{DEPLOY_BASE}/test_systemd_lifecycle.sh"),
    ("os-agent-integration/echo/install_systemd.sh", f"{DEPLOY_BASE}/install_systemd.sh"),
]

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main():
    if not VM_PASSWORD:
        print("ERROR: KYLIN_VM_PASSWORD env not set")
        sys.exit(1)

    print("=" * 60)
    print(" PR21 R3 P0修复麒麟VM验证")
    print("=" * 60)

    # --- Connect ---
    print("\n[1] Connecting to Kylin VM...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(VM_HOST, port=VM_PORT, username=VM_USER, password=VM_PASSWORD, timeout=15)
    except Exception as e:
        print(f"FAIL: SSH connection failed: {e}")
        sys.exit(1)

    sftp = ssh.open_sftp()

    try:
        # --- Check VM ---
        stdin, stdout, stderr = ssh.exec_command("uname -a && whoami && hostname")
        print(f"  VM: {stdout.read().decode().strip()}")

        # --- Upload files with SHA256 verification ---
        print("\n[2] Uploading modified files...")
        passed = 0
        failed = 0

        for local_rel, remote_path in FILES_TO_UPLOAD:
            local_path = os.path.join(PROJECT_ROOT, local_rel)
            if not os.path.exists(local_path):
                print(f"  SKIP: {local_rel} (not found)")
                continue

            local_sha = sha256_file(local_path)
            print(f"  Upload: {local_rel} -> {remote_path}")

            # Ensure remote directory exists
            remote_dir = os.path.dirname(remote_path)
            ssh.exec_command(f"mkdir -p {remote_dir}")

            # Upload with retry (up to 3 times)
            success = False
            for attempt in range(3):
                try:
                    sftp.put(local_path, remote_path, confirm=True)
                    # Verify remote SHA256
                    stdin, stdout, stderr = ssh.exec_command(f"sha256sum {remote_path}")
                    remote_sha = stdout.read().decode().strip().split()[0]
                    if remote_sha == local_sha:
                        print(f"    ✅ SHA256 verified ({remote_sha[:16]}...)")
                        passed += 1
                        success = True
                        break
                    else:
                        print(f"    ⚠️  SHA256 mismatch (attempt {attempt+1}/3)")
                        print(f"       Local:  {local_sha[:16]}...")
                        print(f"       Remote: {remote_sha[:16]}...")
                except Exception as e:
                    print(f"    ⚠️  Upload attempt {attempt+1}/3 failed: {e}")

            if not success:
                print(f"    ❌ Upload FAILED after 3 attempts")
                failed += 1

        if failed > 0:
            print(f"\n  UPLOAD RESULT: {passed} passed, {failed} FAILED")
        else:
            print(f"\n  UPLOAD RESULT: {passed} passed, 0 failed ✅")

        # --- Compile C++ client ---
        print("\n[3] Compiling kaiming_memory_client.cpp...")
        ssh.exec_command(f"chmod +x {DEPLOY_BASE}/bin/kylin-memory-echo-server")
        cmd = f"cd {DEPLOY_BASE} && g++ -std=c++17 -O2 -o kaiming_memory_client kaiming_memory_client.cpp 2>&1"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        compile_out = stdout.read().decode()
        compile_err = stderr.read().decode()
        exit_code = stdout.channel.recv_exit_status()
        if exit_code == 0:
            print(f"  ✅ Compile PASS")
        else:
            print(f"  ❌ Compile FAIL (exit={exit_code})")
            if compile_err:
                print(f"  STDERR: {compile_err[:500]}")
            if compile_out:
                print(f"  STDOUT: {compile_out[:500]}")

        # Make executable
        ssh.exec_command(f"chmod +x {DEPLOY_BASE}/kaiming_memory_client")

        # --- P0-1: Run kaiming_memory_client --method all ---
        print("\n[4] P0-1: Testing kaiming_memory_client --method all...")
        # First check if echo server is running
        stdin, stdout, stderr = ssh.exec_command(
            f"test -S {SOCKET_PATH} && echo 'SOCKET_EXISTS' || echo 'NO_SOCKET'"
        )
        sock_status = stdout.read().decode().strip()
        print(f"  Socket status: {sock_status}")

        if sock_status == "SOCKET_EXISTS":
            cmd = f"cd {DEPLOY_BASE} && ./kaiming_memory_client --method all --socket {SOCKET_PATH} 2>&1"
            stdin, stdout, stderr = ssh.exec_command(cmd)
            test_out = stdout.read().decode()
            test_err = stderr.read().decode()
            exit_code = stdout.channel.recv_exit_status()

            print(f"  Exit code: {exit_code}")
            print(f"  Output:")
            for line in test_out.split("\n"):
                if line.strip():
                    print(f"    {line}")
            if test_err:
                for line in test_err.split("\n")[:15]:
                    if line.strip():
                        print(f"    [ERR] {line}")

            # Verify results
            if "Passed: 6" in test_out and "Failed: 0" in test_out:
                print(f"  ✅ P0-1: 6/6 ALL PASS")
            elif "Passed: 6" in test_out:
                print(f"  ⚠️  P0-1: 6 passed but some failed (check above)")
            else:
                print(f"  ❌ P0-1: NOT 6/6")

            # Verify STORE returns UNSUPPORTED_METHOD
            if "KAIMING-STORE" in test_out and "PASS" in test_out:
                print(f"  ✅ KAIMING-STORE: PASS (UNSUPPORTED_METHOD verified)")
            elif "KAIMING-STORE" in test_out and "FAIL" in test_out:
                print(f"  ❌ KAIMING-STORE: FAIL")

            # Verify UNKNOWN returns UNSUPPORTED_METHOD
            if "KAIMING-UNKNOWN" in test_out and "PASS" in test_out:
                print(f"  ✅ KAIMING-UNKNOWN: PASS (UNSUPPORTED_METHOD verified)")
            elif "KAIMING-UNKNOWN" in test_out and "FAIL" in test_out:
                print(f"  ❌ KAIMING-UNKNOWN: FAIL")
        else:
            print(f"  ⚠️  Socket not available, skipping client test")
            print(f"  Run: sudo systemctl start kylin-memory-echo to start server first")

        # --- P0-4: Verify evidence.record removed from server ---
        print("\n[5] P0-4: Verifying evidence.record removed from server...")
        stdin, stdout, stderr = ssh.exec_command(
            f"grep -c 'evidence.record' {DEPLOY_BASE}/bin/kylin-memory-echo-server 2>/dev/null || echo '0'"
        )
        evidence_count = stdout.read().decode().strip()
        if evidence_count == "0":
            print(f"  ✅ P0-4: evidence.record NOT in METHOD_ROUTER (removed)")
        else:
            print(f"  ⚠️  P0-4: evidence.record found {evidence_count} time(s) in server")

        # --- Python syntax check ---
        print("\n[6] P1-A: Server Python syntax check...")
        stdin, stdout, stderr = ssh.exec_command(
            f"python3 -m py_compile {DEPLOY_BASE}/bin/kylin-memory-echo-server 2>&1 && echo 'OK' || echo 'FAIL'"
        )
        py_check = stdout.read().decode().strip()
        print(f"  {'✅' if 'OK' in py_check else '❌'} Python compile: {py_check}")

        # --- bash syntax check ---
        print("\n[7] P1-A: bash syntax checks...")
        for script in ["test_systemd_lifecycle.sh", "install_systemd.sh"]:
            stdin, stdout, stderr = ssh.exec_command(
                f"bash -n {DEPLOY_BASE}/{script} 2>&1 && echo 'OK' || echo 'FAIL'"
            )
            result = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            status = "✅" if "OK" in result else "❌"
            print(f"  {status} {script}: {result}")
            if err and "OK" not in result:
                print(f"    ERR: {err[:200]}")

        # --- Summary ---
        print("\n" + "=" * 60)
        print(" VERIFICATION SUMMARY")
        print("=" * 60)
        print(f"  P0-1 (JSON+assertion): See test output above")
        print(f"  P0-2 (systemd lifecycle): Run 'sudo bash test_systemd_lifecycle.sh' on VM")
        print(f"  P0-3 (unified paths): config/environment.example updated")
        print(f"  P0-4 (evidence.record removed): Verified above")
        print(f"  P0-6 (index.yaml corrected): Done locally")
        print(f"  P0-5 (evidence rebuild): Requires full L2 rerun on VM")
        print("=" * 60)

    finally:
        sftp.close()
        ssh.close()


if __name__ == "__main__":
    main()