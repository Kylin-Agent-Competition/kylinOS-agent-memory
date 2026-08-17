#!/usr/bin/env python3
"""Phase 4: End-to-end deployment verification"""
import paramiko
import sys, os, time, json

PW = os.environ.get("KYLIN_VM_PASSWORD", "")
REPO = '/home/kylin-agent/kylin-memory-echo'
SOCK = '/run/kylin-memory-echo/echo.sock'
OUT_DIR = os.path.join(os.path.dirname(__file__), 'final')
os.makedirs(OUT_DIR, exist_ok=True)

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('127.0.0.1', port=2222, username='kylin-agent', password=PW, timeout=15)
    print("Connected", flush=True)
    
    def run(cmd, timeout=60):
        _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
        ec = stdout.channel.recv_exit_status()
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        return ec, out, err
    
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    
    # D4: echo_client test
    print("D4...", flush=True)
    ec, out, _ = run(f'{REPO}/build/echo_client --socket {SOCK} 2>&1', timeout=30)
    client_log = f"# Client Test Log - {ts}\n\n## D4 echo_client (ec={ec})\n{out}\n\n"
    
    # D5: kaiming_memory_client test
    print("D5...", flush=True)
    ec2, out2, _ = run(f'{REPO}/build/kaiming_memory_client --method all --socket {SOCK} 2>&1', timeout=30)
    client_log += f"## D5 kaiming_memory_client (ec={ec2})\n{out2}\n"
    
    with open(os.path.join(OUT_DIR, 'client.log'), 'w', encoding='utf-8') as f:
        f.write(client_log)
    print(f"client.log written ({len(client_log)} bytes)", flush=True)
    
    # D6: systemd lifecycle
    print("D6...", flush=True)
    lifecycle = f"# Systemd Lifecycle Log - {ts}\n\n"
    
    # Current status
    ec, out, _ = run('systemctl status kylin-memory-echo --no-pager -l 2>&1', timeout=15)
    lifecycle += f"## Current Status (ec={ec})\n{out}\n\n"
    
    # Stop -> Start -> Test
    ec, out, _ = run(f"echo '{PW}' | sudo -S systemctl stop kylin-memory-echo 2>&1", timeout=15)
    lifecycle += f"## Stop (ec={ec})\n{out}\n\n"
    time.sleep(1)
    
    ec, out, _ = run(f"echo '{PW}' | sudo -S systemctl start kylin-memory-echo 2>&1", timeout=15)
    lifecycle += f"## Start (ec={ec})\n{out}\n\n"
    time.sleep(2)
    
    ec, out, _ = run(f'{REPO}/build/kaiming_memory_client --method health --socket {SOCK} 2>&1', timeout=15)
    lifecycle += f"## Health check after restart (ec={ec})\n{out}\n\n"
    
    # Socket check
    ec, out, _ = run(f'ls -la {SOCK} 2>&1')
    lifecycle += f"## Socket after restart (ec={ec})\n{out}\n\n"
    
    # Journal
    ec, out, _ = run('journalctl -u kylin-memory-echo --no-pager -n 20 2>&1', timeout=15)
    lifecycle += f"## Journal last 20 (ec={ec})\n{out}\n"
    
    with open(os.path.join(OUT_DIR, 'systemd_lifecycle.log'), 'w', encoding='utf-8') as f:
        f.write(lifecycle)
    print(f"systemd_lifecycle.log written ({len(lifecycle)} bytes)", flush=True)
    
    # D7: KYSEC ACL
    print("D7...", flush=True)
    kysec_log = f"# KYSEC ACL Log - {ts}\n\n"
    for tool in ['kysec_set', 'kysec_get', 'getfattr']:
        ec, out, _ = run(f'which {tool} 2>&1 || echo NOT_FOUND')
        kysec_log += f"  {tool}: {'FOUND' if 'NOT_FOUND' not in out else 'NOT_FOUND'}\n"
    
    for label, path in [
        ('echo_client', f'{REPO}/build/echo_client'),
        ('kaiming_client', f'{REPO}/build/kaiming_memory_client'),
    ]:
        ec, out, _ = run(f'getfattr -n security.exectl "{path}" 2>&1 || echo NO_ATTR')
        kysec_log += f"  {label} security.exectl: {out.strip()}\n"
    
    # Check KYSEC module
    ec, out, _ = run(f"echo '{PW}' | sudo -S ls /sys/kernel/security/kysec/ 2>&1")
    kysec_log += f"\nKYSEC dir: ec={ec}\n{out}\n"
    
    with open(os.path.join(OUT_DIR, 'kysec_acl.log'), 'w', encoding='utf-8') as f:
        f.write(kysec_log)
    print(f"kysec_acl.log written", flush=True)
    
    # D8: Rollback
    print("D8...", flush=True)
    rollback = f"# Rollback Log - {ts}\n\n"
    ec, out, _ = run(f"echo '{PW}' | sudo -S systemctl stop kylin-memory-echo 2>&1", timeout=15)
    rollback += f"## Stop service (ec={ec})\n{out}\n\n"
    
    # Check cleanup
    ec, out, _ = run(f'ls -la {SOCK} 2>&1; ls -la /tmp/kylin-memory-echo/ 2>&1')
    rollback += f"## Socket dirs after stop (ec={ec})\n{out}\n\n"
    
    ec, out, _ = run('ps aux | grep memory_echo | grep -v grep || echo "No echo process"')
    rollback += f"## Processes after stop (ec={ec})\n{out}\n\n"
    
    with open(os.path.join(OUT_DIR, 'rollback.log'), 'w', encoding='utf-8') as f:
        f.write(rollback)
    print(f"rollback.log written", flush=True)
    
    # Final summary
    print("\nFiles created:", flush=True)
    for f in ['client.log', 'systemd_lifecycle.log', 'kysec_acl.log', 'rollback.log']:
        path = os.path.join(OUT_DIR, f)
        if os.path.exists(path):
            print(f"  {f}: {os.path.getsize(path)} bytes", flush=True)
    
    ssh.close()
    print("\nDone.", flush=True)

if __name__ == '__main__':
    main()