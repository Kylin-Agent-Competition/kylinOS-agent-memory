#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 3 步 3.3 socket/journal 专项诊断：进程状态 + 应用日志 + journal + 手动前台运行。
SSH: 127.0.0.1:2222 / kylin-agent，密码来自环境变量 KYLIN_VM_PASSWORD。
"""
import io, os, sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import paramiko

try:
    PW = os.environ["KYLIN_VM_PASSWORD"]
except KeyError:
    print("FATAL: KYLIN_VM_PASSWORD environment variable is required but not set.", file=sys.stderr)
    sys.exit(1)

HOME = "/home/kylin-agent"
REPO = f"{HOME}/kylinOS-agent-memory"
VENV_PY = f"{HOME}/d4d-venv/bin/python"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())


def exec_cmd(cmd, timeout=120):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    chan = stdout.channel
    chan.settimeout(5)
    out_buf, err_buf = [], []
    while True:
        try:
            chunk = chan.recv(65536)
            if not chunk:
                break
            out_buf.append(chunk.decode("utf-8", errors="replace"))
        except Exception:
            if chan.exit_status_ready():
                break
            continue
    while chan.recv_ready():
        out_buf.append(chan.recv(65536).decode("utf-8", errors="replace"))
    while chan.recv_stderr_ready():
        err_buf.append(chan.recv_stderr(65536).decode("utf-8", errors="replace"))
    ec = chan.recv_exit_status()
    return ec, "".join(out_buf), "".join(err_buf)


def main():
    ssh.connect("127.0.0.1", port=2222, username="kylin-agent", password=PW, timeout=25)
    print("[OK] connected\n")

    # 1. 进程状态（R/D/S/阻塞点）
    print("=" * 64)
    print("1. systemd 服务进程状态")
    print("=" * 64)
    ec, out, _ = exec_cmd(
        "export XDG_RUNTIME_DIR=/run/user/1000; "
        "pid=$(systemctl --user show kylin-memory -p ExecMainPID --value); "
        "echo PID=$pid; "
        "ps -o pid,ppid,stat,etime,cmd -p $pid 2>&1; "
        "cat /proc/$pid/wchan 2>&1; echo; "
        "ls -la /proc/$pid/fd 2>&1 | head -20")
    print(out)

    # 2. 应用日志文件
    print("=" * 64)
    print("2. 应用日志文件 ~/.local/state/kylin-memory/memory-service.log")
    print("=" * 64)
    ec, out, _ = exec_cmd(
        "ls -la ~/.local/state/kylin-memory/ 2>&1; "
        "tail -50 ~/.local/state/kylin-memory/memory-service.log 2>&1")
    print(out)

    # 3. 最近 journal（确认 00:38 轮是否有日志）
    print("=" * 64)
    print("3. journalctl --since 2026-08-22 00:37")
    print("=" * 64)
    ec, out, _ = exec_cmd("journalctl --user -u kylin-memory --since '2026-08-22 00:37' --no-pager 2>&1")
    print(out if out.strip() else "(无输出)")

    # 4. systemctl status 完整
    print("=" * 64)
    print("4. systemctl status -l 完整")
    print("=" * 64)
    ec, out, _ = exec_cmd("export XDG_RUNTIME_DIR=/run/user/1000; systemctl --user status kylin-memory -l --no-pager 2>&1")
    print(out)

    # 5. 手动前台运行（no-outbox）看卡点（timeout 10s）
    print("=" * 64)
    print("5. 手动前台运行 app.py --no-outbox（timeout 10s）")
    print("=" * 64)
    ec, out, _ = exec_cmd(
        f"rm -f /tmp/kylin-memory-vfy/diag_sys.sock; "
        f"cd {REPO}/memory-service && timeout 10 {VENV_PY} app.py "
        f"--socket /tmp/kylin-memory-vfy/diag_sys.sock "
        f"--db /tmp/kylin-memory-vfy/diag_sys.db --no-outbox 2>&1; echo EXIT=$?; "
        f"ls -la /tmp/kylin-memory-vfy/diag_sys.sock 2>&1",
        timeout=20)
    print(out)

    # 6. 手动前台运行（带 outbox）看卡点（timeout 10s）
    print("=" * 64)
    print("6. 手动前台运行 app.py（带 outbox，timeout 10s）")
    print("=" * 64)
    ec, out, _ = exec_cmd(
        f"rm -f /tmp/kylin-memory-vfy/diag_sys.sock; "
        f"cd {REPO}/memory-service && timeout 10 {VENV_PY} app.py "
        f"--socket /tmp/kylin-memory-vfy/diag_sys.sock "
        f"--db /tmp/kylin-memory-vfy/diag_sys.db 2>&1; echo EXIT=$?; "
        f"ls -la /tmp/kylin-memory-vfy/diag_sys.sock 2>&1",
        timeout=20)
    print(out)

    ssh.close()
    print("\nDONE")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[FATAL] {type(exc).__name__}: {exc}")
        try:
            ssh.close()
        except Exception:
            pass
        sys.exit(1)