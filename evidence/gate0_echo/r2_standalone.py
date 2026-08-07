#!/usr/bin/env python3
"""R2 standalone verification — writes to file to avoid GBK issues"""
import paramiko, time, os
pw = 'Zyf790043'
repo = '/home/kylin-agent/kylin-memory-echo'
build = f'{repo}/os-agent-integration/echo/build'
kaiming = f'{build}/kaiming_memory_client'
sock = '/tmp/kylin-memory-echo/echo.sock'
server = f'{repo}/os-agent-integration/echo/memory_echo_server.py'
out_dir = os.path.join(os.path.dirname(__file__), 'day2_results')
os.makedirs(out_dir, exist_ok=True)

results = []

def add(s): results.append(s); print(s)

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('127.0.0.1', port=2222, username='kylin-agent', password=pw, timeout=10)

def run(cmd, timeout=60, sudo=False):
    if sudo: cmd = f"echo '{pw}' | sudo -S bash -c '{cmd}'"
    _, so, se = c.exec_command(cmd, timeout=timeout)
    ec = so.channel.recv_exit_status()
    return ec, so.read().decode(errors='replace'), se.read().decode(errors='replace')

add("=== R2 Verification ===")
add(f"Time: {time.strftime('%Y-%m-%dT%H:%M:%S')}")

# Cleanup & start server
run("pkill -9 -f memory_echo_server.py 2>/dev/null", sudo=True)
time.sleep(1)
run(f"rm -rf /run/kylin-memory-echo /tmp/kylin-memory-echo 2>/dev/null", sudo=True)
run("mkdir -p /tmp/kylin-memory-echo")
run(f"nohup python3 {server} --dev > /tmp/echo_r2b.log 2>&1 &")
time.sleep(2)

ec, _, _ = run("pgrep -f memory_echo_server.py")
add(f"Server: {'RUNNING' if ec == 0 else 'DEAD'}")

ec, out, _ = run(f"ls -la {sock} 2>&1")
add(f"Socket: {out[:200]}")

# Run all 6 tests
add("")
add("--- kaiming_memory_client --method all ---")
ec, out, err = run(f"{kaiming} --method all --socket {sock} 2>&1", timeout=60)
add(f"exit_code: {ec}")
add(out[-4000:])

# Key checks
pass_count = out.count("RESULT KAIMING-") - out.count("FAIL") 
passes = [l for l in out.split('\n') if 'PASS' in l and 'RESULT' in l]
fails = [l for l in out.split('\n') if 'FAIL' in l and 'RESULT' in l]

add("")
add("=== Summary ===")
for p in passes: add(f"  PASS: {p.strip()}")
for f in fails: add(f"  FAIL: {f.strip()}")
add(f"Total: {len(passes)} PASS / {len(fails)} FAIL")

has_error_message = 'error_message' in out
has_message = '"message"' in out
add(f"")
add(f"error_message field present: {has_error_message}")
add(f"message field present: {has_message}")

ec, svc, _ = run("cat /tmp/echo_r2b.log 2>&1")
proto_err = 'PROTOCOL_ERROR' in svc
add(f"Service PROTOCOL_ERROR: {proto_err}")

# Check if store FAIL is expected (echo not implemented)
store_line = [l for l in out.split('\n') if 'STORE' in l and 'FAIL' in l]
add(f"STORE FAIL type: {store_line[0] if store_line else 'N/A'}")

# Write results
path = os.path.join(out_dir, '_R2_FINAL.log')
with open(path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
add(f"\nWritten: {path}")

run("pkill -f memory_echo_server.py 2>/dev/null", sudo=True)
c.close()