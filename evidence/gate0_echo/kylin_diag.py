#!/usr/bin/env python3
"""Kylin VM 诊断脚本 — 检查当前状态用于 P0-B / P0-C 修复"""
import os, sys, io, paramiko

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PW = os.environ.get("KYLIN_VM_PASSWORD", "")
if not PW:
    print("FATAL: KYLIN_VM_PASSWORD 未设置", file=sys.stderr)
    sys.exit(1)

def exec_cmd(ssh, cmd):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return out, err

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("127.0.0.1", port=2222, username="kylin-agent", password=PW, timeout=15)

try:
    out, err = exec_cmd(ssh, "cat /etc/.kyinfo 2>/dev/null; echo '==='; uname -m; echo '==='; uname -r")
    print("=== SYSTEM ===")
    print(out)

    out, err = exec_cmd(ssh, "cd /home/kylin-agent/kylinOS-agent-memory && git log --oneline -10")
    print("=== GIT LOG ===")
    print(out)

    out, err = exec_cmd(ssh, "cd /home/kylin-agent/kylinOS-agent-memory && git rev-parse HEAD")
    print("=== GIT HEAD ===")
    print(out)

    out, err = exec_cmd(ssh, "cd /home/kylin-agent/kylinOS-agent-memory && git status --short")
    print("=== GIT STATUS ===")
    print(out)

    out, err = exec_cmd(ssh, "systemctl status kylin-memory-echo 2>&1 | head -20")
    print("=== SYSTEMD STATUS ===")
    print(out)

    out, err = exec_cmd(ssh, "systemctl is-active kylin-memory-echo 2>&1")
    print("=== SYSTEMD ACTIVE ===")
    print(out)

    out, err = exec_cmd(ssh, "ls -la /run/kylin-memory-echo/ 2>&1; echo '==='; ls -la /tmp/kylin-memory-echo/ 2>&1")
    print("=== SOCKET PATHS ===")
    print(out)

    out, err = exec_cmd(ssh, "ls -la /home/kylin-agent/kylinOS-agent-memory/evidence/gate0_echo/ 2>&1")
    print("=== EVIDENCE DIR ===")
    print(out)

    out, err = exec_cmd(ssh, "cat /home/kylin-agent/kylinOS-agent-memory/evidence/gate0_echo/evidence.jsonl 2>&1")
    print("=== EVIDENCE.JSONL ===")
    print(out)

    out, err = exec_cmd(ssh, "ls -la /etc/systemd/system/kylin-memory-echo.service 2>&1; echo '==='; ls -la /home/kylin-agent/kylinOS-agent-memory/os-agent-integration/echo/ 2>&1")
    print("=== DEPLOY FILES ===")
    print(out)

    out, err = exec_cmd(ssh, "which python3 && python3 --version")
    print("=== PYTHON ===")
    print(out)

    out, err = exec_cmd(ssh, "python3 -c 'import socket; print(socket.AF_UNIX)' 2>&1")
    print("=== PYTHON UNIX SOCKET ===")
    print(out)

    print("\n=== DONE ===")
finally:
    ssh.close()