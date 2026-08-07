#!/usr/bin/env python3
"""SSH 认证诊断 — 测试多个用户名"""
import os, sys, paramiko

HOST = os.environ.get("KYLIN_VM_HOST", "127.0.0.1")
PORT = int(os.environ.get("KYLIN_VM_PORT", "2222"))
PW = os.environ.get("KYLIN_VM_PASSWORD", "").strip()

if not PW:
    print("ERROR: KYLIN_VM_PASSWORD 环境变量未设置")
    sys.exit(1)

users = ["kylin-agent", "kylin", "ZhouYifan"]

for user in users:
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(HOST, port=PORT, username=user, password=PW, timeout=5)
        print(f"SUCCESS: {user}")
        # Run whoami to verify
        _, stdout, _ = c.exec_command("whoami", timeout=5)
        out = stdout.read().decode().strip()
        print(f"  whoami: {out}")
        c.close()
        break
    except Exception as e:
        print(f"FAIL: {user} -> {type(e).__name__}: {e}")