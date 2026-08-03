#!/usr/bin/env python3
"""V7 测试执行器 - 在麒麟VM上运行全链路测试并下载证据

用法:
  python3 v7_run_tests.py [--output-dir evidence/gate0_echo/v7_evidence]
"""
import argparse, paramiko, os, sys, time, json

HOST = os.environ.get('KYLIN_VM_HOST', '127.0.0.1')
PORT = int(os.environ.get('KYLIN_VM_PORT', '2222'))
USER = os.environ.get('KYLIN_VM_USER', '')
PASS = os.environ.get('KYLIN_VM_PASSWORD', '')
if not USER or not PASS:
    print("FATAL: KYLIN_VM_USER and KYLIN_VM_PASSWORD environment variables must be set.")
    sys.exit(1)
REMOTE = f'/home/{USER}/kylin-memory-echo'
LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EVIDENCE = os.path.join(LOCAL_DIR, 'v7_evidence')
EVIDENCE_DIR = argparse.ArgumentParser(description='V7 测试执行器').parse_args().__dict__.get(
    'output_dir',
    sys.argv[sys.argv.index('--output-dir') + 1] if '--output-dir' in sys.argv else None
) or DEFAULT_EVIDENCE

os.makedirs(EVIDENCE_DIR, exist_ok=True)

def log(msg):
    print(f'[V7] {msg}', flush=True)

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
log('Connected to Kylin VM')

# ---- Step 1: Compile kaiming client ----
log('Step 1: Compile kaiming_memory_client...')
chan = c.get_transport().open_session(timeout=30)
chan.exec_command(f'cd {REMOTE} && g++ -std=c++17 -O2 kaiming_memory_client.cpp -o bin/kaiming_memory_client 2>&1')
exit_code = chan.recv_exit_status()
stdout = chan.recv(65536).decode('utf-8', errors='replace')
stderr = chan.recv_stderr(65536).decode('utf-8', errors='replace')
chan.close()
log(f'  Compile exit={exit_code} stdout={stdout.strip()[:200]} stderr={stderr.strip()[:200]}')

# ---- Step 2: Start server ----
log('Step 2: Start Echo Server...')
chan = c.get_transport().open_session(timeout=15)
chan.exec_command(f'pkill -f kylin-memory-echo-server 2>/dev/null; rm -f /tmp/kylin-memory-echo/echo.sock; sleep 1; cd {REMOTE} && nohup python3 bin/kylin-memory-echo-server > logs/server_stdout.log 2>&1 & sleep 3; pgrep -f kylin-memory-echo-server')
exit_code = chan.recv_exit_status()
stdout = chan.recv(65536).decode('utf-8', errors='replace')
chan.close()
pid = stdout.strip()
log(f'  Server PID: {pid}')

if not pid:
    chan2 = c.get_transport().open_session(timeout=5)
    chan2.exec_command(f'cat {REMOTE}/logs/server_stderr.log')
    chan2.recv_exit_status()
    log(f'  Server STDERR: {chan2.recv(65536).decode("utf-8","replace")[:500]}')
    chan2.close()
    c.close()
    sys.exit(1)

# ---- Step 3: Phase A - Kaiming client tests ----
log('Step 3: Phase A - Kaiming UDS tests...')
chan = c.get_transport().open_session(timeout=30)
chan.exec_command(f'{REMOTE}/bin/kaiming_memory_client --method all 2>&1')
chan.recv_exit_status()
out = chan.recv(131072).decode('utf-8', errors='replace')
chan.close()

a_pass = 0
a_fail = 0
for line in out.split('\n'):
    if 'PASS' in line:
        log(f'  {line.strip()[:150]}')
        if 'RESULT' in line and 'FAIL' not in line:
            a_pass += 1
    if 'FAIL' in line and 'RESULT' in line:
        log(f'  {line.strip()[:150]}')
        a_fail += 1
log(f'  Phase A: {a_pass} PASS, {a_fail} FAIL')

# Save output
with open(os.path.join(EVIDENCE_DIR, 'phase_a_kaiming_output.txt'), 'w', encoding='utf-8') as f:
    f.write(out)

# ---- Step 4: Phase B - KYSEC tests ----
log('Step 4: Phase B - KYSEC full test (sudo)...')
chan = c.get_transport().open_session(timeout=90)
chan.exec_command(f'cd {REMOTE} && sudo bash share/test_kysec_full.sh 2>&1')
chan.recv_exit_status()
out = chan.recv(262144).decode('utf-8', errors='replace')
chan.close()

b_pass_count = out.count('✅')
b_fail_count = out.count('❌')
log(f'  Phase B: {b_pass_count} PASS, {b_fail_count} FAIL')
for line in out.split('\n'):
    if '✅' in line or '❌' in line:
        log(f'  {line.strip()[:150]}')

with open(os.path.join(EVIDENCE_DIR, 'phase_b_kysec_output.txt'), 'w', encoding='utf-8') as f:
    f.write(out)

# ---- Step 5: Phase C - Systemd lifecycle ----
log('Step 5: Phase C - Systemd lifecycle (sudo)...')
# First restart server for systemd test
chan = c.get_transport().open_session(timeout=90)
chan.exec_command(f'cd {REMOTE} && sudo bash share/test_systemd_lifecycle.sh 2>&1')
chan.recv_exit_status()
out = chan.recv(262144).decode('utf-8', errors='replace')
chan.close()

c_pass_count = out.count('✅')
c_fail_count = out.count('❌')
log(f'  Phase C: {c_pass_count} PASS, {c_fail_count} FAIL')
for line in out.split('\n'):
    if '✅' in line or '❌' in line:
        log(f'  {line.strip()[:150]}')

with open(os.path.join(EVIDENCE_DIR, 'phase_c_systemd_output.txt'), 'w', encoding='utf-8') as f:
    f.write(out)

# ---- Step 6: Download logs ----
log('Step 6: Download remote logs...')
sftp = c.open_sftp()
for log_file in ['server_stdout.log', 'server_stderr.log']:
    try:
        local_log = os.path.join(EVIDENCE_DIR, log_file)
        sftp.get(f'{REMOTE}/logs/{log_file}', local_log)
        size = os.path.getsize(local_log)
        if size == 0:
            log(f'  WARN: {log_file} is EMPTY after download')
        else:
            log(f'  Downloaded {log_file} ({size} bytes)')
    except:
        log(f'  Skip {log_file}')

# Get latest KYSEC log
try:
    chan = c.get_transport().open_session(timeout=5)
    chan.exec_command(f'ls -t {REMOTE}/logs/test_kysec_full_*.log 2>/dev/null | head -1')
    chan.recv_exit_status()
    kysec_log = chan.recv(4096).decode('utf-8', errors='replace').strip()
    chan.close()
    if kysec_log:
        local_log = os.path.join(EVIDENCE_DIR, 'test_kysec_full.log')
        sftp.get(kysec_log, local_log)
        size = os.path.getsize(local_log)
        log(f'  Downloaded KYSEC log ({size} bytes)' + (' [WARN: EMPTY]' if size == 0 else ''))
except:
    pass

# Get latest systemd log
try:
    chan = c.get_transport().open_session(timeout=5)
    chan.exec_command(f'ls -t {REMOTE}/logs/test_systemd_lifecycle_*.log 2>/dev/null | head -1')
    chan.recv_exit_status()
    sysd_log = chan.recv(4096).decode('utf-8', errors='replace').strip()
    chan.close()
    if sysd_log:
        local_log = os.path.join(EVIDENCE_DIR, 'test_systemd_lifecycle.log')
        sftp.get(sysd_log, local_log)
        size = os.path.getsize(local_log)
        log(f'  Downloaded systemd log ({size} bytes)' + (' [WARN: EMPTY]' if size == 0 else ''))
except:
    pass

sftp.close()
c.close()

# ---- Summary ----
log('')
log('=' * 60)
log('V7 Kaiming-UDS 端到端全链路测试汇总')
log('=' * 60)
log(f'  Phase A (Kaiming UDS):      {a_pass}P/{a_fail}F -> {"PASS" if a_fail==0 and a_pass>0 else "FAIL"}')
log(f'  Phase B (KYSEC 授权回退):    {b_pass_count}P/{b_fail_count}F -> {"PASS" if b_fail_count==0 else "FAIL"}')
log(f'  Phase C (Systemd 生命周期):  {c_pass_count}P/{c_fail_count}F -> {"PASS" if c_fail_count==0 else "FAIL"}')
log(f'')
log(f'  证据目录: {EVIDENCE_DIR}')
log('=' * 60)