#!/usr/bin/env python3
"""R2+R3 修复后重新验证 — 写入文件规避GBK"""
import paramiko, sys, os, time, hashlib, subprocess
cwd = os.path.dirname(__file__)
OUT = os.path.join(cwd, 'day2_results')
os.makedirs(OUT, exist_ok=True)

pw = os.environ.get("KYLIN_VM_PASSWORD", "")
def exec_cmd(ssh, cmd, sudo=False, timeout=120):
    if sudo: cmd = f"echo '{pw}' | sudo -S bash -c '{cmd}'"
    _, so, se = ssh.exec_command(cmd, timeout=timeout)
    ec = so.channel.recv_exit_status()
    return ec, so.read().decode(errors='replace'), se.read().decode(errors='replace')

def write_file(name, text):
    p = os.path.join(OUT, name)
    with open(p, 'w', encoding='utf-8') as f: f.write(text)
    return p

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('127.0.0.1', port=2222, username='kylin-agent', password=pw, timeout=15)
sftp = ssh.open_sftp()

repo = '/home/kylin-agent/kylin-memory-echo'
echo_dir = f'{repo}/os-agent-integration/echo'
build_dir = f'{echo_dir}/build'

# Upload latest local files
print("Uploading latest files...")
local_base = os.path.abspath(os.path.join(cwd, '..', '..', 'os-agent-integration', 'echo'))
for f in ['kaiming_memory_client.cpp', 'echo_client.cpp', 'CMakeLists.txt', 'test_systemd_lifecycle.sh', 'memory_echo_server.py']:
    local = os.path.join(local_base, f)
    remote = f'{echo_dir}/{f}'
    if os.path.exists(local):
        sftp.put(local, remote)
        print(f'  Uploaded: {f}')
    else:
        print(f'  MISSING: {local}')

# Rebuild
print("Rebuilding...")
exec_cmd(ssh, f'rm -rf {build_dir}')
ec, out, err = exec_cmd(ssh, f'cd {echo_dir} && cmake -S . -B build 2>&1', timeout=120)
ec2, out2, err2 = exec_cmd(ssh, f'cd {echo_dir} && cmake --build build 2>&1', timeout=180)

# Copy kaiming_client to bin/ for systemd test
exec_cmd(ssh, f'mkdir -p {repo}/bin && chmod +x {build_dir}/kaiming_memory_client')
ec3, out3, err3 = exec_cmd(ssh, f'cp -f {build_dir}/kaiming_memory_client {repo}/bin/kaiming_memory_client && ls -la {repo}/bin/kaiming_memory_client')

report = []
report.append("# R2+R3 修复后重新验证")
report.append(f"# Time: {time.strftime('%Y-%m-%dT%H:%M:%S')}")
report.append("")

# ============ R2: KAIMING-STORE ============
report.append("## R2: KAIMING-STORE")
report.append("")
report.append(f"CMake config: ec={ec}, build: ec={ec2}, bin copy: ec={ec3}")
report.append("")

# Start echo server
exec_cmd(ssh, "pkill -f memory_echo_server.py 2>/dev/null; sleep 1", sudo=True)
exec_cmd(ssh, f'mkdir -p /tmp/kylin-memory-echo')
exec_cmd(ssh, f'nohup python3 {echo_dir}/memory_echo_server.py --dev > /tmp/echo_r2.log 2>&1 &')
time.sleep(2)

ec, _, _ = exec_cmd(ssh, "pgrep -f memory_echo_server.py")
report.append(f"Echo PID: {'running' if ec == 0 else 'NOT RUNNING'}")

# Run all 6 tests
ec, out, err = exec_cmd(ssh, f'{build_dir}/kaiming_memory_client --method all --socket /tmp/kylin-memory-echo/echo.sock 2>&1', timeout=60)
report.append(f"")
report.append(f"### --method all 输出")
report.append(f"```")
report.append(out[-3000:])
report.append(f"```")
report.append(f"exit_code: {ec}")

# Check error_message field specifically
has_err_msg = 'error_message' in out
has_msg = '"message"' in out
report.append(f"")
report.append(f"- 'error_message' in response: {has_err_msg}")
report.append(f"- 'message' in response: {has_msg}")

# Check service log for PROTOCOL_ERROR
ec, svc_log, _ = exec_cmd(ssh, "cat /tmp/echo_r2.log 2>&1")
proto_err = 'PROTOCOL_ERROR' in svc_log
extra_data = 'Extra data' in svc_log
report.append(f"- Service log PROTOCOL_ERROR: {proto_err}")
report.append(f"- Service log Extra data: {extra_data}")
report.append(f"```")
report.append(svc_log[-1500:])
report.append(f"```")

exec_cmd(ssh, "pkill -f memory_echo_server.py 2>/dev/null", sudo=True)

# ============ R3: Systemd lifecycle ============
report.append("")
report.append("## R3: Systemd lifecycle")
report.append("")

ec, out, err = exec_cmd(ssh, f'cd {echo_dir} && sudo bash test_systemd_lifecycle.sh 2>&1', timeout=300, sudo=True)
report.append(f"### Lifecycle test output")
report.append(f"```")
report.append(out[-5000:])
report.append(f"```")
report.append(f"STDERR: {err[:1000]}")
report.append(f"exit_code: {ec}")

# Check Step 8 specifically
step8_ok = 'UDS echo' in out and 'PASS' in out.split('UDS echo')[1][:50] if 'UDS echo' in out else False
report.append(f"- Step 8 UDS echo PASS: {step8_ok}")

# Check Step 11 specifically
step11_ok = '已确认注销服务' in out
report.append(f"- Step 11 '已确认注销服务': {step11_ok}")

# Gather pass/fail summary
import re
pass_m = re.search(r'通过:\s*(\d+)', out)
fail_m = re.search(r'失败:\s*(\d+)', out)
if pass_m and fail_m:
    report.append(f"- Pass/Fail: {pass_m.group(1)}/{fail_m.group(1)}")

# Write report
rp = write_file('_R2_R3_VERIFY.log', '\n'.join(report))
print(f"\nReport written: {rp}")

sftp.close()
ssh.close()
print("Done.")