#!/usr/bin/env python3
"""
D4 麒麟 VM 完整验证：杀旧进程 -> 启新服务 -> 跑6项测试 -> 生成证据
使用 C++ 客户端 kaiming_memory_client 执行协议验证
"""
import os, sys, json, hashlib, time, paramiko, re
from datetime import datetime, timezone, timedelta

SGT = timezone(timedelta(hours=8))
VM_HOST = "127.0.0.1"
VM_PORT = 2222
VM_USER = "kylin-agent"
VM_PASSWORD = os.environ.get("KYLIN_VM_PASSWORD", "")
DEPLOY_BASE = "/home/kylin-agent/kylin-memory-echo"
SOCKET = "/tmp/kylin-memory-echo/echo.sock"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(PROJECT_ROOT, "evidence", "gate0_echo", "d4_results", "d4_run.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

log_fh = open(LOG_PATH, "w", encoding="utf-8")

def console(msg):
    safe = msg.encode('ascii', errors='replace').decode('ascii')
    print(safe)
    sys.stdout.flush()

def file_log(msg):
    log_fh.write(msg + "\n")
    log_fh.flush()

def sha256_local(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def run_cmd(client, cmd, timeout=20):
    file_log(f"  CMD: {cmd[:120]}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    ec = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    if out:
        file_log(f"  OUT ({len(out)}b): {out[:500]}")
    if err:
        file_log(f"  ERR ({len(err)}b): {err[:500]}")
    return ec, out, err

def upload_file(client, local_rel, remote):
    local_full = os.path.join(PROJECT_ROOT, local_rel)
    local_hash = sha256_local(local_full)
    console(f"  Upload: {local_rel} sha256={local_hash[:16]}...")
    file_log(f"  Upload: {local_rel} sha256={local_hash[:16]}...")
    for attempt in range(1, 4):
        try:
            sftp = client.open_sftp()
            remote_dir = os.path.dirname(remote)
            try:
                sftp.stat(remote_dir)
            except FileNotFoundError:
                client.exec_command(f"mkdir -p {remote_dir}", timeout=5)
            sftp.put(local_full, remote, confirm=True)
            sftp.close()
            stdin, stdout, stderr = client.exec_command(f"sha256sum {remote}", timeout=10)
            rh = stdout.read().decode().strip().split()[0]
            if rh == local_hash:
                console(f"    OK (attempt {attempt})")
                file_log(f"    OK (attempt {attempt})")
                return True
            else:
                console(f"    MISMATCH (attempt {attempt})!")
                file_log(f"    MISMATCH (attempt {attempt}): local={local_hash[:12]} remote={rh[:12]}")
        except Exception as e:
            console(f"    ERROR (attempt {attempt}): {e}")
            file_log(f"    ERROR (attempt {attempt}): {e}")
        time.sleep(1)
    console(f"    FAILED after 3 attempts!")
    file_log(f"    FAILED after 3 attempts!")
    return False

def parse_cpp_results(output):
    """Parse C++ client output lines like 'RESULT TEST_NAME PASS' or 'RESULT TEST_NAME FAIL'"""
    results = {}
    for line in output.splitlines():
        m = re.match(r'RESULT\s+(\S+)\s+(\S+)', line)
        if m:
            name = m.group(1)
            passed = m.group(2) == "PASS"
            results[name] = passed
    return results

def main():
    if not VM_PASSWORD:
        console("ERROR: KYLIN_VM_PASSWORD env not set")
        return 1

    head_commit = os.popen("git rev-parse HEAD").read().strip()
    ts = datetime.now(SGT).strftime("%Y%m%dT%H%M%S+08")

    console("=" * 70)
    console(f" D4 Final Test - HEAD: {head_commit}")
    console(f" Time: {ts}")
    console("=" * 70)
    file_log("=" * 70)
    file_log(f" D4 Final Test - HEAD: {head_commit}")
    file_log(f" Time: {ts}")
    file_log("=" * 70)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(VM_HOST, port=VM_PORT, username=VM_USER, password=VM_PASSWORD, timeout=15)
    console("Connected to VM")
    file_log("Connected to VM")

    # PHASE 1: Upload
    console("\n[PHASE 1] Upload files...")
    file_log("\n[PHASE 1] Upload files...")
    files = [
        ("os-agent-integration/echo/kaiming_memory_client.cpp", f"{DEPLOY_BASE}/kaiming_memory_client.cpp"),
        ("os-agent-integration/echo/memory_echo_server.py", f"{DEPLOY_BASE}/bin/kylin-memory-echo-server"),
    ]
    for local, remote in files:
        if not upload_file(client, local, remote):
            console(f"FATAL: upload failed for {local}")
            client.close()
            log_fh.close()
            return 1

    # PHASE 2: Restart server
    console("\n[PHASE 2] Restart server...")
    file_log("\n[PHASE 2] Restart server...")
    run_cmd(client, "pkill -f kylin-memory-echo-server 2>/dev/null; sleep 1; echo KILL_DONE")
    run_cmd(client, f"rm -f {SOCKET} 2>/dev/null; echo SOCKET_CLEANED")

    console("  Starting new server...")
    file_log("  Starting new server...")
    client.exec_command(
        f"cd {DEPLOY_BASE} && nohup python3 bin/kylin-memory-echo-server --dev > logs/server_d4.log 2>&1 &",
        timeout=5
    )
    time.sleep(3)
    ec, out, _ = run_cmd(client, "tail -3 /home/kylin-agent/kylin-memory-echo/logs/server_d4.log 2>&1")
    for line in (out or "").splitlines():
        if "listening on" in line.lower():
            console(f"  Server: {line.strip()}")

    # PHASE 3: Compile C++ client with correct socket path
    console("\n[PHASE 3] Compile C++ client...")
    file_log("\n[PHASE 3] Compile C++ client...")
    # Patch default socket path to match actual path
    ec, out, err = run_cmd(client,
        f"cd {DEPLOY_BASE} && sed -i 's|/run/kylin-memory-echo/echo.sock|{SOCKET}|g' kaiming_memory_client.cpp && "
        f"g++ -std=c++17 -O2 -Wall -Wextra -o kaiming_memory_client kaiming_memory_client.cpp 2>&1",
        timeout=30
    )
    if ec != 0:
        console(f"  Compile failed: {err[:200]}")
        file_log(f"  Compile failed: {err[:500]}")
    else:
        console("  Compile OK")
        file_log("  Compile OK")

    # PHASE 4: Run all tests via C++ client
    console("\n[PHASE 4] Run Kaiming C++ client --method all...")
    file_log("\n[PHASE 4] Run Kaiming C++ client --method all...")
    test_start = datetime.now(SGT).isoformat()

    ec, out, err = run_cmd(client,
        f"cd {DEPLOY_BASE} && ./kaiming_memory_client --method all --socket {SOCKET} 2>&1",
        timeout=60
    )

    console(f"  C++ client exit code: {ec}")
    console(f"  Output:\n{out}")
    file_log(f"  Exit code: {ec}")
    file_log(f"  Full output:\n{out}")
    if err:
        file_log(f"  Full stderr:\n{err}")

    test_end = datetime.now(SGT).isoformat()

    # Parse results
    raw_results = parse_cpp_results(out)
    file_log(f"\n  Parsed results: {raw_results}")

    # Map C++ test names to checklist names
    name_map = {
        "KAIMING-ECHO": "KAIMING-ECHO",
        "KAIMING-HEALTH": "HEALTH",
        "KAIMING-RETRIEVE": "RETRIEVE",
        "KAIMING-STORE": "STORE",
        "KAIMING-UNKNOWN": "UNKNOWN",
        "KAIMING-RAPID": "RAPID",
    }

    pf = {}
    matched = 0
    for cpp_name, checklist_name in name_map.items():
        if cpp_name in raw_results:
            pf[checklist_name] = raw_results[cpp_name]
            matched += 1
        else:
            pf[checklist_name] = False
            console(f"  Missing result for {checklist_name} (C++ name: {cpp_name})")
            file_log(f"  Missing result for {checklist_name} (C++ name: {cpp_name})")

    total = len(pf)
    passed = sum(1 for v in pf.values() if v)
    all_pass = (passed == total)

    console("\n[PHASE 5] Results:")
    file_log("\n[PHASE 5] Results:")
    for name, ok in pf.items():
        line = f"  {'[PASS]' if ok else '[FAIL]'} {name}"
        console(line)
        file_log(line)

    summary = f"  Overall: {passed}/{total} PASS ({matched} matched from C++) | HEAD: {head_commit}"
    console(summary)
    file_log(summary)

    # PHASE 6: Evidence
    console("\n[PHASE 6] Generate evidence...")
    file_log("\n[PHASE 6] Generate evidence...")
    evidence_dir = os.path.join(PROJECT_ROOT, "evidence", "gate0_echo", "d4_results")

    ev_entry = {
        "test_id": "D4-R3-VERIFY",
        "timestamp": ts,
        "tested_commit": head_commit,
        "evidence_commit": head_commit,
        "vm_host": f"{VM_USER}@{VM_HOST}:{VM_PORT}",
        "vm_kylin": "Kylin-Desktop V11 x86_64",
        "test_method": "C++ kaiming_memory_client --method all",
        "results": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "all_pass": all_pass,
            "pass_fail_map": pf,
            "raw_cpp_results": raw_results,
            "cpp_exit_code": ec
        },
        "test_duration": f"{test_start} -> {test_end}"
    }

    ev_path = os.path.join(evidence_dir, "evidence.jsonl")
    with open(ev_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(ev_entry, ensure_ascii=False) + "\n")
    console(f"  evidence.jsonl: {ev_path}")

    result_path = os.path.join(evidence_dir, "d4_r3_full_result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({
            "evidence": ev_entry,
            "pass_fail": pf,
            "raw_cpp_output": out,
            "raw_cpp_stderr": err
        }, f, ensure_ascii=False, indent=2)
    console(f"  full result: {result_path}")

    # FINAL
    console("\n" + "=" * 70)
    file_log("\n" + "=" * 70)
    if all_pass:
        console(" RESULT: ALL 6/6 PASS")
        file_log(" RESULT: ALL 6/6 PASS")
    else:
        console(f" RESULT: {passed}/{total} PASS ({total-passed} failures)")
        file_log(f" RESULT: {passed}/{total} PASS ({total-passed} failures)")
    console("=" * 70)
    file_log("=" * 70)

    client.close()
    log_fh.close()

    if all_pass:
        console(f"\nSUCCESS! Evidence at: {ev_path}")
        return 0
    else:
        console(f"\nFAILURES: See log at {LOG_PATH}")
        return 1

if __name__ == "__main__":
    sys.exit(main())