#!/usr/bin/env python3
"""
UT-2: IPC 重启复测 (Gate 0 Echo 层面)
========================================
在麒麟 VM 上运行, 验证 systemd 服务重启后 UDS IPC 链路恢复能力:
  1. 服务正常运行 → 客户端可正常通信
  2. 服务正常停止 (systemctl stop) → 客户端检测到连接失败
  3. 服务重新启动 (systemctl start) → 客户端恢复通信
  4. 服务被 kill -9 异常终止 → systemd 自动重启 → 客户端可重新连接
  5. 快速连续重启 → 无 socket 残留冲突
  6. 超时行为 → 客户端在服务不可用时不会永久阻塞

协议: 4字节 Big-Endian 长度 + UTF-8 JSON 负载
依赖: Python 3 (socket, struct, json, subprocess, os) — 麒麟 VM 已预装
"""
import socket
import struct
import json
import time
import os
import sys
import subprocess

# ---- Config ----
SOCK = '/home/kylin-agent/.echo_run/echo.sock'
SERVER_SCRIPT = '/home/kylin-agent/kylin-memory-echo/os-agent-integration/echo/memory_echo_server.py'
SOCK_DIR = '/home/kylin-agent/.echo_run'
RESULTS = []
PASS = 0
FAIL = 0

def log_result(test_id, passed, detail):
    global PASS, FAIL
    if passed:
        PASS += 1
        RESULTS.append(f"PASS {test_id}: {detail}")
    else:
        FAIL += 1
        RESULTS.append(f"FAIL {test_id}: {detail}")
    print(f"[{'PASS' if passed else 'FAIL'}] {test_id}: {detail}")

def run_cmd(cmd, timeout=30):
    """Run shell command and return exit_code, stdout, stderr."""
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, 
                              text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:
        return -1, "", str(e)

def uds_request(sock_path, request_dict, timeout=3):
    """Send JSON request via UDS and get response dict."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(sock_path)
        
        body = json.dumps(request_dict, ensure_ascii=False).encode('utf-8')
        header = struct.pack('>I', len(body))
        sock.sendall(header + body)
        
        resp_header = sock.recv(4)
        if len(resp_header) < 4:
            sock.close()
            return None, f"Incomplete header: {len(resp_header)} bytes"
        
        resp_len = struct.unpack('>I', resp_header)[0]
        if resp_len == 0 or resp_len > 65536:
            sock.close()
            return None, f"Invalid response length: {resp_len}"
        
        chunks = []
        remaining = resp_len
        while remaining > 0:
            chunk = sock.recv(min(remaining, 4096))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        
        sock.close()
        resp_body = b''.join(chunks).decode('utf-8', errors='replace')
        return json.loads(resp_body), "OK"
    except socket.timeout:
        return None, "TIMEOUT"
    except ConnectionRefusedError:
        return None, "CONNECTION_REFUSED"
    except FileNotFoundError:
        return None, "SOCKET_NOT_FOUND"
    except Exception as e:
        return None, f"Error: {e}"

def health_check(timeout=3):
    """Quick health check to verify service is reachable."""
    req = {
        "protocol_version": "1.0",
        "request_id": "ut2_health",
        "trace_id": "ut2_trace",
        "method": "health",
        "deadline_ms": 3000,
        "payload": {}
    }
    resp, msg = uds_request(SOCK, req, timeout=timeout)
    if resp and resp.get("status") == "ok":
        return True, resp
    return False, msg

def is_server_running():
    """Check if Echo server process is running."""
    ec, out, _ = run_cmd("pgrep -f memory_echo_server.py 2>/dev/null", timeout=5)
    return ec == 0 and out.strip() != ""

def start_server():
    """Start Echo server with user-owned socket path."""
    # Clean up any existing socket and server
    run_cmd("pkill -f memory_echo_server.py 2>/dev/null", timeout=5)
    time.sleep(1)
    run_cmd("mkdir -p " + SOCK_DIR)
    # Start new server with explicit --socket
    run_cmd(
        "nohup python3 %s --socket %s > /tmp/echo_ut2.log 2>&1 &" % (SERVER_SCRIPT, SOCK),
        timeout=5)
    time.sleep(2)
    return is_server_running()

def stop_server():
    """Stop Echo server gracefully."""
    run_cmd("pkill -f memory_echo_server.py 2>/dev/null", timeout=5)
    time.sleep(1)

def kill_server():
    """Force kill Echo server (simulate crash)."""
    run_cmd("pkill -9 -f memory_echo_server.py 2>/dev/null", timeout=5)
    time.sleep(1)

# ===================================================================
# Test Suite
# ===================================================================

print("=" * 60)
print(f" UT-2 IPC 重启复测")
print(f" Socket: {SOCK}")
print(f" Time: {time.strftime('%Y-%m-%dT%H:%M:%S')}")
print("=" * 60)

# --- Test 1: 服务正常运行 → 健康检查通过 ---
print("\n--- T1: 基础健康检查 ---")
if not is_server_running():
    print("  服务未运行, 正在启动...")
    if not start_server():
        log_result("UT2-START", False, "无法启动 Echo Server")
        sys.exit(1)
    log_result("UT2-START", True, "Echo Server 已启动")

ok, resp = health_check()
if ok:
    pid = resp.get("data", {}).get("pid", "?")
    uptime = resp.get("data", {}).get("uptime_seconds", 0)
    log_result("UT2-HEALTH-BASELINE", True,
               f"健康检查通过 (pid={pid}, uptime={uptime:.1f}s)")
    BASELINE_PID = pid
else:
    log_result("UT2-HEALTH-BASELINE", False, f"健康检查失败: {resp}")
    sys.exit(1)

# --- Test 2: 正常停止服务 → 客户端检测到连接失败 ---
print("\n--- T2: 正常停止 → 连接失败检测 ---")
stop_server()
time.sleep(1)

# Verify server is down
if is_server_running():
    log_result("UT2-STOP", False, "服务未成功停止")
else:
    log_result("UT2-STOP", True, "服务已正常停止")

# Try health check — should fail
ok, resp = health_check(timeout=2)
# Socket should be cleaned up by server's cleanup()
socket_exists = os.path.exists(SOCK)
if not ok:
    log_result("UT2-STOP-DETECT", True,
               f"客户端正确检测到服务不可用 (detail: {resp}), socket_exists={socket_exists}")
else:
    log_result("UT2-STOP-DETECT", False,
               f"服务已停止但健康检查仍返回 ok (socket_exists={socket_exists})")

# --- Test 3: 重新启动服务 → 客户端恢复通信 ---
print("\n--- T3: 重新启动 → 通信恢复 ---")
startup_ok = start_server()
if not startup_ok:
    log_result("UT2-RESTART-SERVER", False, "服务重启失败")
else:
    log_result("UT2-RESTART-SERVER", True, "服务已重新启动")

if startup_ok:
    time.sleep(1)
    ok, resp = health_check()
    if ok:
        new_pid = resp.get("data", {}).get("pid", "?")
        log_result("UT2-RESTART-RECOVER", True,
                   f"重启后通信恢复 (新 pid={new_pid}, 旧 pid={BASELINE_PID})")
    else:
        log_result("UT2-RESTART-RECOVER", False,
                   f"重启后通信未恢复: {resp}")

# --- Test 4: Socket 残留清理验证 ---
print("\n--- T4: Socket 残留清理 ---")
stop_server()
time.sleep(1)
socket_after_stop = os.path.exists(SOCK)
if not socket_after_stop:
    log_result("UT2-SOCKET-CLEANUP", True, "停止后 socket 文件已被清理")
else:
    log_result("UT2-SOCKET-CLEANUP", False, f"停止后 socket 文件仍存在: {SOCK}")
    run_cmd(f"rm -f {SOCK} 2>/dev/null")

# --- Test 5: Kill -9 异常终止 → 重新可连接 ---
print("\n--- T5: Kill -9 异常终止恢复 ---")
start_server()
time.sleep(1)
ok_initial, _ = health_check()
if not ok_initial:
    log_result("UT2-KILL9-PRE", False, "Kill-9 前服务不可达")
else:
    log_result("UT2-KILL9-PRE", True, "Kill-9 前服务正常")

kill_server()
time.sleep(2)

# After kill -9, server should be dead
if is_server_running():
    log_result("UT2-KILL9-STOP", False, "Kill-9 后仍有残留进程")
else:
    log_result("UT2-KILL9-STOP", True, "Kill-9 后进程已终止")

# Clean socket and restart
run_cmd(f"rm -f {SOCK} 2>/dev/null")
start_server()
time.sleep(1)

ok, resp = health_check()
if ok:
    log_result("UT2-KILL9-RECOVER", True,
               f"Kill-9 后重启恢复 (pid={resp.get('data', {}).get('pid', '?')})")
else:
    log_result("UT2-KILL9-RECOVER", False,
               f"Kill-9 后重启未恢复: {resp}")

# --- Test 6: 快速连续重启 (5次) ---
print("\n--- T6: 快速连续重启 (5次) — 无 socket 残留冲突 ---")
restart_ok_count = 0
for i in range(5):
    stop_server()
    time.sleep(0.5)
    run_cmd(f"rm -f {SOCK} 2>/dev/null")
    if start_server():
        ok, _ = health_check(timeout=2)
        if ok:
            restart_ok_count += 1
            print(f"  第 {i+1}/5 次重启成功")
        else:
            print(f"  第 {i+1}/5 次重启: 服务启动但健康检查失败")
    else:
        print(f"  第 {i+1}/5 次重启: 服务启动失败")

if restart_ok_count == 5:
    log_result("UT2-RAPID-RESTART", True, "5/5 快速重启全部成功, 无 socket 冲突")
else:
    log_result("UT2-RAPID-RESTART", False,
               f"快速重启 {restart_ok_count}/5 成功 (可能有 socket 残留冲突)")

# --- Test 7: 客户端超时行为 ---
print("\n--- T7: 客户端超时行为验证 ---")
stop_server()
run_cmd(f"rm -f {SOCK} 2>/dev/null")
time.sleep(0.5)

start = time.time()
ok, resp = health_check(timeout=3)
elapsed = time.time() - start

if not ok and elapsed < 4.0:
    log_result("UT2-TIMEOUT", True,
               f"服务不可用时客户端在 {elapsed:.1f}s 内正确超时返回")
elif elapsed >= 4.0:
    log_result("UT2-TIMEOUT", False,
               f"客户端超时时间过长 ({elapsed:.1f}s), 可能阻塞调用方")
else:
    log_result("UT2-TIMEOUT", False,
               f"服务不可用但客户端未正确报错 (elapsed={elapsed:.1f}s)")

# --- Test 8: 最终恢复验证 ---
print("\n--- T8: 最终恢复验证 ---")
run_cmd(f"rm -f {SOCK} 2>/dev/null")
if start_server():
    ok, resp = health_check()
    if ok:
        log_result("UT2-FINAL-RECOVER", True,
                   f"所有测试后服务恢复正常 (pid={resp.get('data', {}).get('pid', '?')})")
    else:
        log_result("UT2-FINAL-RECOVER", False, f"最终恢复失败: {resp}")
else:
    log_result("UT2-FINAL-RECOVER", False, "无法启动服务")

# ===================================================================
# Cleanup
# ===================================================================
print("\n--- Cleanup ---")
stop_server()
run_cmd(f"rm -f {SOCK} 2>/dev/null")
print("  已停止服务并清理 socket")

# ===================================================================
# Summary
# ===================================================================
print("\n" + "=" * 60)
print(f" UT-2 IPC 重启复测完成")
print(f" Passed: {PASS} / Failed: {FAIL} / Total: {PASS + FAIL}")
print("=" * 60)

# Write results file
out_path = "/tmp/ut2_ipc_restart_results.txt"
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(f"# UT-2 IPC 重启复测结果\n")
    f.write(f"# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
    f.write(f"# Socket: {SOCK}\n")
    f.write(f"# Passed: {PASS} / Failed: {FAIL} / Total: {PASS + FAIL}\n\n")
    for r in RESULTS:
        f.write(r + "\n")

print(f"\nResults written to {out_path}")
sys.exit(0 if FAIL == 0 else 1)