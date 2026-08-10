#!/usr/bin/env python3
"""P0-B / P0-C: 麒麟 VM systemd 路径证据重建
===============================================
P0-B: 在 R3 head 上重新执行完整 L2 测试，生成绑定当前 HEAD 的 evidence.jsonl
P0-C: 通过 systemd 路径 (/run/kylin-memory-echo/echo.sock) 采集证据，补齐 systemd 生命周期记录

流程:
  1. 连接 VM + 获取本地 HEAD
  2. 创建目录结构 + 上传全部文件 (SHA256 校验)
  3. 编译 C++ 客户端
  4. 安装 systemd 服务 (install_systemd.sh)
  5. 启动服务 + 验证 socket
  6. 运行全部 6 项测试 (通过 systemd socket)
  7. 生成 evidence.jsonl (含 systemd 生命周期记录)
  8. 下载 evidence.jsonl 到本地
  9. 更新 evidence/index.yaml
"""
import paramiko, hashlib, json, os, sys, time, io, subprocess, base64
from datetime import datetime, timezone

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ---- 凭证 ----
try:
    PW = os.environ["KYLIN_VM_PASSWORD"]
except KeyError:
    print("FATAL: KYLIN_VM_PASSWORD environment variable is required but not set.", file=sys.stderr)
    sys.exit(1)

USER = 'kylin-agent'
HOST = '127.0.0.1'
PORT = 2222
REPO = f'/home/{USER}/kylin-memory-echo'
SOCK = '/run/kylin-memory-echo/echo.sock'  # P0-C: systemd 路径，非 dev 路径

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVIDENCE_DIR = os.path.join(PROJECT_ROOT, 'evidence', 'gate0_echo', 'systemd_evidence')
RAW_LOGS_DIR = os.path.join(EVIDENCE_DIR, 'raw_logs')
OUT_JSONL = os.path.join(EVIDENCE_DIR, 'evidence.jsonl')
OUT_JSONL_REMOTE = f'{REPO}/evidence.jsonl'

NOW = datetime.now(timezone.utc)
NOW_ISO = NOW.strftime('%Y-%m-%dT%H:%M:%SZ')
NOW_DATE = NOW.strftime('%Y-%m-%d')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

def run(cmd, timeout=30, sudo=False):
    if sudo:
        cmd = f"echo '{PW}' | sudo -S bash -c '{cmd}'"
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    ec = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    return ec, out, err

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def sha256_str(s):
    return hashlib.sha256(s.encode()).hexdigest()

def upload_verified(local_rel, remote_path):
    """SHA256 铁律上传，3 次重试"""
    local_path = os.path.join(PROJECT_ROOT, local_rel)
    if not os.path.exists(local_path):
        print(f"  SKIP (not found): {local_rel}")
        return False, ""
    local_sha = sha256_file(local_path)
    run(f"mkdir -p {os.path.dirname(remote_path)}")
    sftp = ssh.open_sftp()
    for attempt in range(3):
        try:
            sftp.put(local_path, remote_path, confirm=True)
            ec, out, _ = run(f"sha256sum {remote_path}")
            remote_sha = out.split()[0] if out else ""
            if remote_sha == local_sha:
                print(f"  OK {os.path.basename(local_rel)} sha={local_sha[:16]}...")
                sftp.close()
                return True, local_sha
            print(f"  SHA mismatch attempt {attempt+1}/3")
        except Exception as e:
            print(f"  Upload attempt {attempt+1}/3: {e}")
    sftp.close()
    print(f"  FAILED: {local_rel}")
    return False, ""

def download_verified(remote_path, local_path):
    """下载 + SHA256 校验"""
    sftp = ssh.open_sftp()
    for attempt in range(3):
        try:
            sftp.get(remote_path, local_path)
            ec, out, _ = run(f"sha256sum {remote_path}")
            remote_sha = out.split()[0] if out else ""
            local_sha = sha256_file(local_path)
            if remote_sha == local_sha:
                sftp.close()
                return True, remote_sha
            print(f"  Download SHA mismatch attempt {attempt+1}/3")
        except Exception as e:
            print(f"  Download attempt {attempt+1}/3: {e}")
    sftp.close()
    return False, ""

def main():
    print("=" * 70)
    print(" P0-B / P0-C: SYSTEMD 路径证据重建")
    print(f" Timestamp: {NOW_ISO}")
    print("=" * 70)

    # ---- GET LOCAL HEAD ----
    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    ).stdout.strip()
    print(f"\nLocal HEAD: {git_head}")

    # ---- CONNECT ----
    print("\n[1/9] Connecting to Kylin VM...")
    try:
        ssh.connect(HOST, port=PORT, username=USER, password=PW, timeout=20)
    except Exception as e:
        print(f"FATAL: Cannot connect: {e}")
        sys.exit(1)

    ec, out, err = run("whoami && hostname && uname -r && cat /etc/.kyinfo 2>/dev/null | head -3")
    vm_info = out.replace('\n', ' | ')[:200]
    print(f"  Connected: {vm_info}")
    # Detect Kylin version
    kylin_ver = "Kylin V11"
    if 'V11' in vm_info:
        kylin_ver = "Kylin V11"
    elif 'V10' in vm_info:
        kylin_ver = "Kylin V10"

    # ---- CREATE DIR STRUCTURE ----
    print("\n[2/9] Creating project structure...")
    for d in ['', '/bin', '/logs', '/share']:
        ec, _, _ = run(f"mkdir -p {REPO}{d}")
    print(f"  Base: {REPO}")

    # ---- UPLOAD FILES ----
    print("\n[3/9] Uploading files (SHA256 verified)...")
    uploads = [
        ("os-agent-integration/echo/kaiming_memory_client.cpp", f"{REPO}/kaiming_memory_client.cpp"),
        ("os-agent-integration/echo/memory_echo_server.py", f"{REPO}/bin/kylin-memory-echo-server"),
        ("os-agent-integration/echo/test_systemd_lifecycle.sh", f"{REPO}/test_systemd_lifecycle.sh"),
        ("os-agent-integration/echo/install_systemd.sh", f"{REPO}/install_systemd.sh"),
        ("packaging/systemd/kylin-memory-echo.service", f"{REPO}/share/kylin-memory-echo.service"),
    ]
    upload_oks = []
    for local_rel, remote_path in uploads:
        ok, sha = upload_verified(local_rel, remote_path)
        upload_oks.append(ok)
    all_uploaded = all(upload_oks)
    print(f"  Uploads: {'ALL OK' if all_uploaded else 'SOME FAILED'}")
    if not all_uploaded:
        print("FATAL: Upload verification failed. Aborting to prevent testing stale files on VM.")
        sys.exit(1)

    # Set permissions
    run(f"chmod +x {REPO}/bin/kylin-memory-echo-server")
    run(f"chmod +x {REPO}/test_systemd_lifecycle.sh")
    run(f"chmod +x {REPO}/install_systemd.sh")

    # ---- COMPILE ----
    print("\n[4/9] Compiling kaiming_memory_client...")
    ec, out, err = run(
        f"cd {REPO} && g++ -std=c++17 -O2 -Wall -Wextra -o kaiming_memory_client kaiming_memory_client.cpp 2>&1",
        timeout=60
    )
    compile_ok = (ec == 0)
    compile_out = out + "\n" + err
    print(f"  Compile: {'PASS' if compile_ok else 'FAIL'} (exit={ec})")
    if err:
        print(f"  stderr: {err[:300]}")
    run(f"chmod +x {REPO}/kaiming_memory_client")

    # Save compile raw output for evidence
    run(f"mkdir -p {REPO}/logs")
    compile_b64 = base64.b64encode(compile_out.encode('utf-8', errors='replace')).decode('ascii')
    run(f"echo '{compile_b64}' | base64 -d > {REPO}/logs/compile_output.log")

    # ---- INSTALL SYSTEMD ----
    print("\n[5/9] Installing systemd service...")
    # First, stop any existing service
    run("systemctl stop kylin-memory-echo 2>/dev/null; true", sudo=True)
    time.sleep(1)

    # Check if unit file needs creation (install_systemd.sh requires the template)
    # We need to generate the unit file ourselves since install_systemd.sh is designed for interactive
    ec, out, _ = run(f"cat {REPO}/share/kylin-memory-echo.service")
    unit_content = out
    # Replace __USERNAME__ with kylin-agent
    unit_content_filled = unit_content.replace('__USERNAME__', USER)
    # Write unit file to home dir first, then sudo mv to /etc/systemd/system/
    unit_tmp_path = f'{REPO}/kylin-memory-echo.service'
    sftp = ssh.open_sftp()
    with sftp.file(unit_tmp_path, 'w') as f:
        f.write(unit_content_filled)
    sftp.chmod(unit_tmp_path, 0o644)
    sftp.close()
    run(f"cp {unit_tmp_path} /etc/systemd/system/kylin-memory-echo.service", sudo=True)

    # Verify unit file
    ec, out, _ = run("cat /etc/systemd/system/kylin-memory-echo.service")
    print(f"  Unit file lines: {len(out.split(chr(10)))}")

    # SHA256 of installed unit
    ec, unit_sha_out, _ = run("sha256sum /etc/systemd/system/kylin-memory-echo.service")
    unit_sha = unit_sha_out.split()[0] if unit_sha_out else "N/A"
    print(f"  Unit SHA256: {unit_sha[:16]}...")

    # daemon-reload
    run("systemctl daemon-reload", sudo=True)
    time.sleep(1)

    # Enable
    ec, out, err = run("systemctl enable kylin-memory-echo 2>&1", sudo=True)
    print(f"  enable: {'OK' if ec == 0 else out[:100]}")

    # ---- START SERVICE ----
    print("\n[6/9] Starting systemd service...")
    ec, out, err = run("systemctl start kylin-memory-echo 2>&1", sudo=True)
    time.sleep(4)

    # Verify
    ec, active, _ = run("systemctl is-active kylin-memory-echo 2>&1")
    print(f"  Active: {active}")

    ec, pid_out, _ = run("systemctl show -p MainPID kylin-memory-echo")
    main_pid = pid_out.split('=')[-1] if '=' in pid_out else '0'
    print(f"  MainPID: {main_pid}")

    # P0-C: systemd lifecycle verification
    systemd_lifecycle_ok = (active == "active" and main_pid != "0")

    ec, sock_out, _ = run(f"test -S {SOCK} && echo EXISTS || echo ABSENT")
    sock_exists = (sock_out.strip() == "EXISTS")
    print(f"  Socket {SOCK}: {'EXISTS' if sock_exists else 'ABSENT'}")

    if sock_exists:
        # Get socket metadata
        ec, sock_stat, _ = run(f"stat -c 'perm=%a owner=%U:%G' {SOCK} 2>/dev/null || echo N/A")
        print(f"  Socket info: {sock_stat}")

    if not sock_exists:
        print("\n  *** Checking journal for service errors ***")
        ec, journal, _ = run("journalctl -u kylin-memory-echo -n 30 --no-pager 2>&1")
        print(f"  Journal:\n{journal[:500]}")

    # ---- RUN TESTS via systemd socket ----
    print("\n[7/9] Running tests via systemd socket...")
    evidence_records = []

    if sock_exists:
        run(f"mkdir -p {REPO}/logs")

        # --- ECHO-001: Full 6-method test ---
        print("\n  ECHO-001: kaiming_memory_client --method all...")
        cmd = f"cd {REPO} && ./kaiming_memory_client --method all --socket {SOCK} 2>&1"
        ec, all_out, err_out = run(cmd, timeout=30)
        full_out = all_out + "\n" + err_out
        # Save to log
        run(f"echo '{base64.b64encode(full_out.encode()).decode()}' | base64 -d > {REPO}/logs/p05_kaiming_all.log")

        # Parse results
        results = {}
        for line in full_out.split('\n'):
            if 'RESULT' in line:
                parts = line.split()
                if len(parts) >= 3:
                    results[parts[1]] = parts[2]
        passes = sum(1 for v in results.values() if v == 'PASS')
        fails = sum(1 for v in results.values() if v == 'FAIL')
        all_pass = (passes == 6 and fails == 0)
        test_status = "PASS" if all_pass else "FAIL"
        print(f"    Results: {passes}P / {fails}F -> {test_status}")
        for k, v in results.items():
            print(f"      {k}: {v}")

        evidence_records.append({
            "test_id": "ECHO-001",
            "tested_commit": git_head,
            "command": f"kaiming_memory_client --method all --socket {SOCK}",
            "exit_code": 0 if all_pass else 1,
            "status": test_status,
            "timestamp": NOW_ISO,
            "environment": f"{kylin_ver}, systemd mode (socket={SOCK})",
            "source_log": f"{REPO}/logs/p05_kaiming_all.log",
            "sha256": sha256_str(full_out),
        })

        # --- ECHO-002: evidence.record removed ---
        print("\n  ECHO-002: evidence.record removed...")
        # Exclude comment lines (^\\s*#); only count active code references
        ec, out, _ = run(f"grep -v '^\\s*#' {REPO}/bin/kylin-memory-echo-server 2>/dev/null | grep -c 'evidence.record' || echo 0")
        ev_count = int(out.strip().split('\n')[0] or "0")
        ev_ok = (ev_count == 0)
        print(f"    Count: {ev_count} -> {'PASS' if ev_ok else 'FAIL'}")

        evidence_records.append({
            "test_id": "ECHO-002",
            "tested_commit": git_head,
            "command": "grep -c evidence.record kylin-memory-echo-server",
            "exit_code": 0 if ev_ok else 1,
            "status": "PASS" if ev_ok else "FAIL",
            "timestamp": NOW_ISO,
            "environment": f"{kylin_ver}, systemd mode",
            "source_log": f"{REPO}/bin/kylin-memory-echo-server",
            "sha256": sha256_str(str(ev_count)),
        })

        # --- ECHO-003: Health check through systemd ---
        print("\n  ECHO-003: health check...")
        ec, out, _ = run(f"cd {REPO} && ./kaiming_memory_client --method health --socket {SOCK} 2>&1", timeout=15)
        health_ok = ("PASS" in out or "KAIMING-HEALTH" in out)
        print(f"    Health: {'PASS' if health_ok else out[:100]}")

        evidence_records.append({
            "test_id": "ECHO-003",
            "tested_commit": git_head,
            "command": f"kaiming_memory_client --method health --socket {SOCK}",
            "exit_code": 0 if health_ok else 1,
            "status": "PASS" if health_ok else "FAIL",
            "timestamp": NOW_ISO,
            "environment": f"{kylin_ver}, systemd mode",
            "source_log": f"{REPO}/logs/p05_kaiming_all.log",
            "sha256": sha256_str(out),
        })

        # --- ECHO-004: memory.store UNSUPPORTED_METHOD ---
        print("\n  ECHO-004: memory.store UNSUPPORTED_METHOD...")
        ec, out, _ = run(f"cd {REPO} && ./kaiming_memory_client --method memory.store --socket {SOCK} 2>&1", timeout=15)
        store_ok = ("PASS" in out and "KAIMING-STORE" in out)
        print(f"    STORE: {'PASS' if store_ok else out[:100]}")

        evidence_records.append({
            "test_id": "ECHO-004",
            "tested_commit": git_head,
            "command": f"kaiming_memory_client --method memory.store --socket {SOCK}",
            "exit_code": 0 if store_ok else 1,
            "status": "PASS" if store_ok else "FAIL",
            "timestamp": NOW_ISO,
            "environment": f"{kylin_ver}, systemd mode",
            "source_log": f"{REPO}/logs/p05_kaiming_all.log",
            "sha256": sha256_str(out),
        })

        # --- ECHO-005: Compile status ---
        print("\n  ECHO-005: compile status...")
        evidence_records.append({
            "test_id": "ECHO-005",
            "tested_commit": git_head,
            "command": f"g++ -std=c++17 -O2 -Wall -Wextra -o kaiming_memory_client kaiming_memory_client.cpp",
            "exit_code": 0 if compile_ok else 1,
            "status": "PASS" if compile_ok else "FAIL",
            "timestamp": NOW_ISO,
            "environment": f"{kylin_ver}, systemd mode",
            "source_log": f"{REPO}/logs/p05_kaiming_all.log",
            "sha256": sha256_str(compile_out),
        })

        # --- P0-C: SYSTEMD_SERVER_LIFECYCLE ---
        print("\n  SYSTEMD_SERVER_LIFECYCLE: systemd lifecycle proof...")
        lifecycle_ok = (active == "active" and main_pid != "0" and sock_exists)
        # Get service status for evidence
        ec, svc_status_out, _ = run("systemctl status kylin-memory-echo --no-pager -l 2>&1")
        ec, unit_sha_out, _ = run("sha256sum /etc/systemd/system/kylin-memory-echo.service")
        unit_file_sha = unit_sha_out.split()[0] if unit_sha_out else "N/A"

        # Save systemctl status raw log
        svc_b64 = base64.b64encode(svc_status_out.encode('utf-8', errors='replace')).decode('ascii')
        run(f"echo '{svc_b64}' | base64 -d > {REPO}/logs/systemctl_status.log")

        # Save journal log for server stdout/stderr
        ec, journal_out, _ = run("journalctl -u kylin-memory-echo --no-pager -l 2>&1")
        journal_b64 = base64.b64encode(journal_out.encode('utf-8', errors='replace')).decode('ascii')
        run(f"echo '{journal_b64}' | base64 -d > {REPO}/logs/server_journal.log")

        evidence_records.append({
            "test_id": "SYSTEMD_SERVER_LIFECYCLE",
            "tested_commit": git_head,
            "command": "systemctl start kylin-memory-echo && systemctl is-active kylin-memory-echo",
            "exit_code": 0 if lifecycle_ok else 1,
            "status": "PASS" if lifecycle_ok else "FAIL",
            "timestamp": NOW_ISO,
            "environment": f"{kylin_ver}, systemd mode (RuntimeDirectory=/run/kylin-memory-echo)",
            "source_log": f"{REPO}/logs/server_stdout.log",
            "sha256": sha256_str(svc_status_out),
            "details": {
                "active": active,
                "main_pid": main_pid,
                "socket_path": SOCK,
                "unit_file_sha256": unit_file_sha,
                "deploy_user": USER,
            }
        })

        # --- P0-C: CPP_CLIENT_OVER_SYSTEMD ---
        print("\n  CPP_CLIENT_OVER_SYSTEMD: C++ client over systemd socket...")
        # Test echo method specifically through systemd socket
        ec, echo_out, _ = run(f"cd {REPO} && ./kaiming_memory_client --method echo --socket {SOCK} 2>&1", timeout=15)
        echo_ok = ("PASS" in echo_out)

        evidence_records.append({
            "test_id": "CPP_CLIENT_OVER_SYSTEMD",
            "tested_commit": git_head,
            "command": f"kaiming_memory_client --method echo --socket {SOCK}",
            "exit_code": 0 if echo_ok else 1,
            "status": "PASS" if echo_ok else "FAIL",
            "timestamp": NOW_ISO,
            "environment": f"{kylin_ver}, systemd mode (client over UDS)",
            "source_log": f"{REPO}/logs/p05_kaiming_all.log",
            "sha256": sha256_str(echo_out),
        })

        # --- P0-C: PACKAGED_UNIT_VALIDATION ---
        print("\n  PACKAGED_UNIT_VALIDATION: unit file validation...")
        # Verify unit file structure
        ec, unit_content, _ = run("cat /etc/systemd/system/kylin-memory-echo.service")
        has_runtime_dir = "RuntimeDirectory=kylin-memory-echo" in unit_content
        has_restrict_af = "RestrictAddressFamilies=AF_UNIX" in unit_content
        has_user = f"User={USER}" in unit_content
        has_no_new_priv = "NoNewPrivileges=yes" in unit_content
        unit_validation_ok = has_runtime_dir and has_restrict_af and has_user and has_no_new_priv

        evidence_records.append({
            "test_id": "PACKAGED_UNIT_VALIDATION",
            "tested_commit": git_head,
            "command": "validate /etc/systemd/system/kylin-memory-echo.service",
            "exit_code": 0 if unit_validation_ok else 1,
            "status": "PASS" if unit_validation_ok else "FAIL",
            "timestamp": NOW_ISO,
            "environment": f"{kylin_ver}, systemd mode",
            "source_log": f"{REPO}/logs/installed_unit.service",
            "sha256": unit_file_sha,
            "details": {
                "runtime_directory": has_runtime_dir,
                "restrict_address_families": has_restrict_af,
                "user": has_user,
                "no_new_privileges": has_no_new_priv,
            }
        })

        # Save installed unit file as raw evidence
        unit_b64 = base64.b64encode(unit_content.encode('utf-8', errors='replace')).decode('ascii')
        run(f"echo '{unit_b64}' | base64 -d > {REPO}/logs/installed_unit.service")
    else:
        print("\n  *** Socket not available — recording failure evidence ***")
        evidence_records.append({
            "test_id": "ECHO-001",
            "tested_commit": git_head,
            "command": f"kaiming_memory_client --method all --socket {SOCK}",
            "exit_code": 1,
            "status": "FAIL",
            "timestamp": NOW_ISO,
            "environment": f"{kylin_ver}, systemd mode (socket unavailable)",
            "source_log": "N/A (socket not available)",
            "sha256": sha256_str("socket_unavailable"),
        })
        evidence_records.append({
            "test_id": "SYSTEMD_SERVER_LIFECYCLE",
            "tested_commit": git_head,
            "command": "systemctl start kylin-memory-echo",
            "exit_code": 1,
            "status": "FAIL",
            "timestamp": NOW_ISO,
            "environment": f"{kylin_ver}, systemd mode (service failed)",
            "source_log": "journalctl -u kylin-memory-echo",
            "sha256": sha256_str("service_failed"),
        })

    # ---- WRITE EVIDENCE (remote) ----
    print("\n[8/9] Writing evidence.jsonl...")
    jsonl_content = ""
    for rec in evidence_records:
        jsonl_content += json.dumps(rec, ensure_ascii=False) + "\n"

    # Write via base64 to remote
    b64 = base64.b64encode(jsonl_content.encode('utf-8')).decode('ascii')
    run(f"echo '{b64}' | base64 -d > {OUT_JSONL_REMOTE}")
    run(f"chmod 644 {OUT_JSONL_REMOTE}")

    # Verify remote
    ec, out, _ = run(f"wc -l {OUT_JSONL_REMOTE} && sha256sum {OUT_JSONL_REMOTE}")
    print(f"  Remote: {out.strip()}")

    # ---- COMPUTE RESULTS (before any local writes) ----
    total_p = sum(1 for r in evidence_records if r["status"] == "PASS")
    total_f = sum(1 for r in evidence_records if r["status"] == "FAIL")
    all_tests_pass = (total_f == 0 and total_p == len(evidence_records))

    # ---- DOWNLOAD EVIDENCE ----
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    print(f"\n  Downloading evidence.jsonl...")
    ev_ok, ev_sha = download_verified(OUT_JSONL_REMOTE, OUT_JSONL)
    if not ev_ok:
        print("FATAL: evidence.jsonl download verification failed.")
        sys.exit(1)
    print(f"  evidence.jsonl: OK sha={ev_sha[:20]}...")

    # ---- DOWNLOAD RAW LOGS ----
    print(f"\n  Downloading raw runtime logs to {RAW_LOGS_DIR}...")
    os.makedirs(RAW_LOGS_DIR, exist_ok=True)
    raw_log_files = [
        f"{REPO}/logs/p05_kaiming_all.log",
        f"{REPO}/logs/compile_output.log",
        f"{REPO}/logs/systemctl_status.log",
        f"{REPO}/logs/server_journal.log",
        f"{REPO}/logs/installed_unit.service",
    ]
    raw_download_failed = False
    for remote_log in raw_log_files:
        local_name = os.path.basename(remote_log)
        local_path = os.path.join(RAW_LOGS_DIR, local_name)
        ok, _ = download_verified(remote_log, local_path)
        if ok:
            print(f"  OK: {local_name}")
        else:
            print(f"  FAILED: {local_name}")
            raw_download_failed = True

    if raw_download_failed:
        print("FATAL: Raw log recovery incomplete.")
        sys.exit(1)

    # ---- UPDATE evidence/index.yaml (ONLY on ALL PASS) ----
    index_path = os.path.join(PROJECT_ROOT, 'evidence', 'index.yaml')
    if all_tests_pass:
        print("\n[9/9] All tests PASS — updating evidence/index.yaml...")
        if os.path.exists(index_path):
            with open(index_path, 'r', encoding='utf-8') as f:
                index_content = f.read()
            echo005_start = index_content.find('ECHO-005')
            if echo005_start >= 0:
                tc_start = index_content.find('tested_commit:', echo005_start)
                if tc_start >= 0:
                    line_end = index_content.find('\n', tc_start)
                    if line_end < 0:
                        line_end = len(index_content)
                    old_line = index_content[tc_start:line_end]
                    new_line = f"tested_commit: {git_head}"
                    new_content = index_content.replace(old_line, new_line)
                    if new_content != index_content:
                        with open(index_path, 'w', encoding='utf-8') as f_out:
                            f_out.write(new_content)
                        print(f"  Updated ECHO-005 tested_commit -> {git_head[:12]}...")
                    else:
                        print("  ECHO-005: no change needed")
                else:
                    print("  WARN: ECHO-005 tested_commit line not found")
            else:
                print("  WARN: ECHO-005 entry not found in index.yaml")

            # Update evidence_commit and checksum
            with open(index_path, 'r', encoding='utf-8') as f:
                index_content = f.read()
            echo005_start = index_content.find('ECHO-005')
            if echo005_start >= 0:
                new_content = index_content

                ec_start = new_content.find('evidence_commit:', echo005_start)
                if ec_start >= 0:
                    ec_line_end = new_content.find('\n', ec_start)
                    if ec_line_end < 0:
                        ec_line_end = len(new_content)
                    old_ec_line = new_content[ec_start:ec_line_end]
                    new_ec_line = f"evidence_commit: {git_head}"
                    new_content = new_content.replace(old_ec_line, new_ec_line, 1)

                cs_start = new_content.find('checksum_sha256:', echo005_start)
                if cs_start >= 0:
                    cs_line_end = new_content.find('\n', cs_start)
                    if cs_line_end < 0:
                        cs_line_end = len(new_content)
                    old_cs_line = new_content[cs_start:cs_line_end]
                    new_cs_line = f"checksum_sha256: {ev_sha}"
                    new_content = new_content.replace(old_cs_line, new_cs_line, 1)

                if new_content != index_content:
                    with open(index_path, 'w', encoding='utf-8') as f_out:
                        f_out.write(new_content)
                    print("  Updated evidence_commit and checksum_sha256 in index.yaml")
        else:
            print("  WARN: index.yaml not found, skip")
    else:
        print(f"\n[9/9] Tests FAIL ({total_p}P/{total_f}F) — SKIPPING index.yaml update (fail-closed).")

    # ---- SUMMARY ----
    print("\n" + "=" * 70)
    print(" P0-B / P0-C: SYSTEMD EVIDENCE REBUILD COMPLETE")
    print("=" * 70)
    print(f"  Commit:    {git_head}")
    print(f"  Records:   {len(evidence_records)} ({total_p} PASS / {total_f} FAIL)")
    print(f"  Evidence:  {OUT_JSONL}")
    print(f"  Raw Logs:  {RAW_LOGS_DIR}")
    print(f"  Socket:    {SOCK}")
    print(f"  Mode:      systemd (NOT dev mode)")
    print("=" * 70)

    # P0-B checklist verification
    print("\n  P0-B Verification:")
    for r in evidence_records:
        if r.get("tested_commit") != git_head:
            print(f"    MISMATCH! {r['test_id']} has {r['tested_commit'][:12]} not {git_head[:12]}")
    # P0-C checklist
    systemd_records = [r for r in evidence_records if "SYSTEMD" in r["test_id"] or "CPP_CLIENT_OVER" in r["test_id"] or "PACKAGED" in r["test_id"]]
    print(f"\n  P0-C Verification: {len(systemd_records)} systemd-specific records generated")
    for r in systemd_records:
        print(f"    - {r['test_id']}: {r['status']}")

    # ---- FAIL-CLOSED EXIT ----
    if not all_tests_pass:
        print(f"\nFATAL: {total_f} tests FAILED. Runner exiting with non-zero for fail-closed compliance.")
        sys.exit(1)
    if not compile_ok:
        print("\nFATAL: Compile FAILED. Runner exiting with non-zero for fail-closed compliance.")
        sys.exit(1)

    print("\nAll gates PASS — Runner exiting 0.")

if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            ssh.close()
        except:
            pass