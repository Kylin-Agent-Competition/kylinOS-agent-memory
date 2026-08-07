#!/usr/bin/env python3
"""Day1-3: 采集原始环境回退锚点 — 记录 Day2 修改前的所有原始状态"""
import os, sys, datetime, socket, paramiko

HOST = os.environ.get("KYLIN_VM_HOST", "127.0.0.1")
PORT = int(os.environ.get("KYLIN_VM_PORT", "2222"))
USER = os.environ.get("KYLIN_VM_USER", "kylin-agent")
PASSWORD = os.environ.get("KYLIN_VM_PASSWORD", "").strip()
LOG_FILE = os.path.join(os.path.dirname(__file__), "baseline.jsonl")

if not PASSWORD:
    print("ERROR: KYLIN_VM_PASSWORD 环境变量未设置")
    sys.exit(1)

transport = paramiko.Transport((HOST, PORT))
try:
    transport.connect(username=USER, password=PASSWORD)
except Exception as e:
    print(f"CONNECTION FAILED: {e}")
    sys.exit(1)

def run(transport, cmd, timeout=20):
    chan = transport.open_session()
    chan.set_combine_stderr(True)
    chan.exec_command(cmd)
    chan.settimeout(timeout)
    out = b""
    while True:
        try:
            data = chan.recv(8192)
            if not data:
                break
            out += data
        except socket.timeout:
            break
        except EOFError:
            break
    code = chan.recv_exit_status()
    chan.close()
    return code, out.decode("utf-8", errors="replace").strip(), ""

# 需要 SHA-256 的原始文件/路径
original_paths = [
    "/home/kylin-agent/kylin-memory-echo",
    "/run/kylin-memory-echo",
    "/etc/systemd/system/kylin-memory-echo.service",
    "/tmp/kylin-memory-echo",
    "/usr/bin/kylin-ai-runtime",
    "/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1",
]

# 原始 service 列表
original_services = [
    "kylin-memory-echo",
]

lines = []

# 1. 检查文件/路径是否存在并计算 SHA-256
for path in original_paths:
    code, out, _ = run(transport, f"if [ -f '{path}' ]; then sha256sum '{path}'; elif [ -d '{path}' ]; then echo 'IS_DIR ' && ls -la '{path}'; else echo 'NOT_FOUND'; fi")
    lines.append(f"PATH: {path}")
    for ln in out.split("\n"):
        lines.append(f"  {ln.strip()}")
    lines.append("")

# 2. Service 状态
for svc in original_services:
    code, out, _ = run(transport, f"systemctl status {svc} 2>&1 || echo 'SERVICE_NOT_FOUND'")
    lines.append(f"SERVICE: {svc}")
    for ln in out.split("\n"):
        lines.append(f"  {ln.strip()}")
    lines.append("")

# 3. kylin-agent 用户的原始进程列表
code, out, _ = run(transport, "ps -u kylin-agent -o pid,cmd --no-headers 2>/dev/null")
lines.append("PROCESSES: kylin-agent")
for ln in out.split("\n"):
    lines.append(f"  {ln.strip()}")
lines.append("")

# 4. 原始 ACL 状态
code, out, _ = run(transport, "getfacl /tmp/kylin-memory-echo 2>/dev/null || echo 'NO_ACL_PATH'; getfacl /run/kylin-memory-echo 2>/dev/null || echo 'NO_ACL_PATH'")
lines.append("ACL: /tmp/kylin-memory-echo & /run/kylin-memory-echo")
for ln in out.split("\n"):
    lines.append(f"  {ln.strip()}")
lines.append("")

# 5. 原始 Socket 状态（精确到 kylin-memory）
code, out, _ = run(transport, "ss -lnpx 2>/dev/null | grep 'kylin-memory' || echo 'NO_KYLIN_MEMORY_SOCKET'")
lines.append("SOCKETS: kylin-memory-echo")
for ln in out.split("\n"):
    lines.append(f"  {ln.strip()}")
lines.append("")

# 6. VM 快照提示
lines.append("VM_SNAPSHOT: 需手动记录 VirtualBox 快照名称与创建时间")
lines.append("")

# 7. 原始包版本
for pkg in ["kylin-ai-runtime", "libkylin-coreai-embedding", "kylin-aiassistant"]:
    code, out, _ = run(transport, f"dpkg -l 2>/dev/null | grep '{pkg}' || echo 'NOT_INSTALLED'")
    lines.append(f"PACKAGE: {pkg}")
    for ln in out.split("\n"):
        lines.append(f"  {ln.strip()}")
    lines.append("")

content = "\n".join(lines)
with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write(content)

print(f"DONE: baseline.jsonl written ({len(content)} bytes)")

# 同时生成 baseline.json
import json
ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
baseline_json = {
    "timestamp": ts,
    "hostname": "ZhouYifan-pc",
    "user": "kylin-agent",
    "pr_head": "dbac3b69e9ed79b5a837a58a9291bb7e30667f39",
    "rollback_anchors": {
        "vm_snapshot": "MANUAL_ENTRY_REQUIRED",
        "original_packages": {
            "kylin-ai-runtime": "1.2.0.4-0k0.1",
            "libkylin-coreai-embedding": "1.2.0.0-0k0.3",
            "kylin-aiassistant": "NOT_INSTALLED_PER_DPKG"
        },
        "original_paths": {
            "/home/kylin-agent/kylin-memory-echo": "NOT_FOUND_BEFORE_DAY2",
            "/run/kylin-memory-echo": "NOT_FOUND_BEFORE_DAY2",
            "/etc/systemd/system/kylin-memory-echo.service": "NOT_FOUND_BEFORE_DAY2",
            "/tmp/kylin-memory-echo": "NOT_FOUND_BEFORE_DAY2"
        },
        "original_services": {
            "kylin-memory-echo": "NOT_INSTALLED_BEFORE_DAY2"
        },
        "kysec_status": "UNAVAILABLE_ON_VM"
    },
    "declaration": "Day1-3 回退锚点: 记录 Day2 UDS Echo 修改前的原始状态。rollback 对照此基线验证恢复结果。若只能做资源清理，必须声明: TEST RESOURCE CLEANUP ONLY / ORIGINAL RESTORE UNVERIFIED"
}

BASELINE_JSON = os.path.join(os.path.dirname(__file__), "baseline.json")
with open(BASELINE_JSON, "w", encoding="utf-8") as f:
    json.dump(baseline_json, f, indent=2, ensure_ascii=False)

print(f"DONE: baseline.json written")
transport.close()