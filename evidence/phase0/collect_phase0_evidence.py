#!/usr/bin/env python3
"""Phase 0 协议对齐 — 麒麟 VM 现状证据收集（重点 ALIGN-005 UDS 路径 + 服务运行状态）。

收集内容：
1. 系统身份与 XDG_RUNTIME_DIR
2. 4 套 socket 路径现状（echo systemd/dev、embedding、KMA_SOCKET_PATH）
3. echo / embedding 服务运行状态与进程
4. 冻结目标路径 $XDG_RUNTIME_DIR/kylin-memory/memory.sock 现状
5. 相关目录/文件权限

输出：evidence/phase0/phase0_vm_evidence.jsonl + 摘要打印
"""
import os
import sys
import datetime
import json

import paramiko

HOST = os.environ.get("KYLIN_VM_HOST", "127.0.0.1")
PORT = int(os.environ.get("KYLIN_VM_PORT", "2222"))
USER = os.environ.get("KYLIN_VM_USER", "kylin-agent")
PASSWORD = os.environ.get("KYLIN_VM_PASSWORD", "").strip()

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSONL = os.path.join(OUT_DIR, "phase0_vm_evidence.jsonl")
OUT_SUMMARY = os.path.join(OUT_DIR, "phase0_vm_evidence.md")


def main():
    if not PASSWORD:
        print("ERROR: KYLIN_VM_PASSWORD 未设置")
        sys.exit(1)

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20)
    print(f"[OK] SSH connected {USER}@{HOST}:{PORT}")

    def run(cmd, timeout=30):
        _, o, e = c.exec_command(cmd, timeout=timeout)
        out = o.read().decode(errors="replace")
        err = e.read().decode(errors="replace")
        ec = o.channel.recv_exit_status()
        return ec, out, err

    records = []

    def record(name, cmd, timeout=30):
        ec, out, err = run(cmd, timeout)
        rec = {
            "ts": datetime.datetime.now().isoformat(),
            "name": name,
            "cmd": cmd,
            "exit": ec,
            "out": out,
            "err": err,
        }
        records.append(rec)
        print(f"  [{name}] exit={ec}")

    # 1. 系统身份与 XDG
    record("system_identity", "uname -a; echo '---'; id; echo '---'; echo XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR")
    record("os_release", "cat /etc/.kyinfo 2>/dev/null || cat /etc/os-release 2>/dev/null | head -5")

    # 2. 冻结目标路径现状
    record("frozen_socket_path", "echo XDG=$XDG_RUNTIME_DIR; ls -la $XDG_RUNTIME_DIR/kylin-memory 2>&1 || echo NO_KDIR; ls -la $XDG_RUNTIME_DIR/kylin-memory/memory.sock 2>&1 || echo NO_MEMORY_SOCK")

    # 3. echo systemd 路径
    record("echo_systemd_path", "ls -la /run/kylin-memory-echo 2>&1 || echo NOT_FOUND; ls -la /run/kylin-memory-echo/echo.sock 2>&1 || echo NO_SOCK")

    # 4. echo dev 路径
    record("echo_dev_path", "ls -la /tmp/kylin-memory-echo 2>&1 || echo NOT_FOUND; ls -la /tmp/kylin-memory-echo/echo.sock 2>&1 || echo NO_SOCK")

    # 5. embedding 路径
    record("embedding_path", "ls -la /tmp/kylin-memory-embed.sock 2>&1 || echo NOT_FOUND")

    # 6. KMA 路径
    record("kma_path", "ls -la /tmp/kylin-memory-service.sock 2>&1 || echo NOT_FOUND")

    # 7. 所有 kylin-memory 相关 socket
    record("all_sockets", "ss -lnpx 2>/dev/null | grep -i kylin || echo NO_KYLIN_SOCKET_LISTENING")

    # 8. 服务状态
    record("echo_service_status", "systemctl status kylin-memory-echo 2>&1 | head -20 || echo NOT_FOUND")

    # 9. 进程
    record("processes", "ps -u kylin-agent -o pid,cmd --no-headers 2>/dev/null | grep -iE 'echo|embed|memory' || echo NO_RELEVANT_PROCESS")

    # 10. 部署目录
    record("deploy_dir", "ls -la /home/kylin-agent/kylin-memory-echo 2>&1 | head -30 || echo NOT_FOUND")

    c.close()

    # 落盘 jsonl
    with open(OUT_JSONL, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 生成 markdown 摘要
    lines = ["# Phase 0 麒麟 VM 现状证据（2026-08-24）", ""]
    for rec in records:
        lines.append(f"## {rec['name']}")
        lines.append(f"```\n# exit={rec['exit']}\n{rec['out']}".rstrip() + f"\n```")
        lines.append("")
    with open(OUT_SUMMARY, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n[OK] evidence -> {OUT_JSONL}")
    print(f"[OK] summary  -> {OUT_SUMMARY}")


if __name__ == "__main__":
    main()
