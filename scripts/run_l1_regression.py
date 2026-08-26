#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D4D L1 回归：同步 VM 仓库到最新 HEAD，跑 test_db_d4d.py + test_migrations_d4d.py，
确认新增两条回归通过，并跑全量 D4D L1 得到准确计数（用于更新 PR body）。

SSH: 127.0.0.1:2222 / kylin-agent，密码来自环境变量 KYLIN_VM_PASSWORD（禁止硬编码）。
执行：
  C:\\Users\\jackb\\AppData\\Local\\Programs\\Python\\Python313\\python.exe scripts\\run_l1_regression.py
"""
import io, os, sys, time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import paramiko

PW = os.environ.get("KYLIN_VM_PASSWORD")
if not PW:
    print("FATAL: KYLIN_VM_PASSWORD environment variable is required but not set.", file=sys.stderr)
    sys.exit(1)

HOST, PORT, USER = "127.0.0.1", 2222, "kylin-agent"
HOME = "/home/kylin-agent"
REPO = f"{HOME}/kylinOS-agent-memory"
VENV_PY = f"{HOME}/d4d-venv/bin/python"
BRANCH = "feat/d4d-ipc-db-outbox"
EXPECTED_COMMIT = "eda2f5d"  # 本地 origin/feat/d4d-ipc-db-outbox 的最新 HEAD

LOCAL_EV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evidence", "l1")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())


def exec_cmd(cmd, timeout=600):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    chan = stdout.channel
    chan.settimeout(10)
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


def step(title):
    print("\n" + "=" * 68)
    print(f"STEP: {title}")
    print("=" * 68)


def main():
    ssh.connect(HOST, port=PORT, username=USER, password=PW, timeout=25)
    print("[OK] 已连接麒麟 VM")

    # 1. 同步仓库到最新 HEAD
    step("1. git fetch + reset --hard 到 origin/feat/d4d-ipc-db-outbox")
    ec, out, err = exec_cmd(f"git -C {REPO} fetch origin 2>&1", timeout=600)
    print(out.strip() or "(fetch 无输出)")
    if ec != 0:
        print(f"[FATAL] git fetch 失败: {err}")
        sys.exit(1)

    ec, out, _ = exec_cmd(f"git -C {REPO} log --oneline -1 origin/{BRANCH} 2>&1")
    remote_head = out.strip()
    print(f"[INFO] origin/{BRANCH} 最新: {remote_head}")

    ec, out, err = exec_cmd(f"git -C {REPO} reset --hard origin/{BRANCH} 2>&1")
    print(out.strip())

    ec, out, _ = exec_cmd(f"git -C {REPO} rev-parse HEAD 2>&1")
    head = out.strip()
    print(f"[INFO] 当前 HEAD: {head}")
    if not head.startswith(EXPECTED_COMMIT):
        print(f"[WARN] 当前 HEAD {head} 与预期 {EXPECTED_COMMIT} 不一致，请核对！")
    else:
        print(f"[OK] HEAD 与本地 origin 一致（{EXPECTED_COMMIT}）")

    ec, out, _ = exec_cmd(f"git -C {REPO} status --short 2>&1 | head -20")
    print(f"[INFO] 工作区状态（应干净）:\n{out}")

    # 2. 确认依赖
    step("2. 确认 venv 依赖")
    ec, out, err = exec_cmd(
        f"{VENV_PY} -c \"import sqlalchemy, alembic, pydantic, pytest; "
        "print('sqlalchemy', sqlalchemy.__version__, 'alembic', alembic.__version__, "
        "'pydantic', pydantic.__version__, 'pytest', pytest.__version__)\" 2>&1"
    )
    print(out.strip())

    # 3. 跑指定两个测试文件（-v 确认新增两条回归）
    step("3. pytest test_db_d4d.py + test_migrations_d4d.py (-v)")
    cmd2 = (
        f"cd {REPO} && PYTHONPATH={REPO}/memory-service {VENV_PY} -m pytest "
        f"memory-service/tests/test_db_d4d.py memory-service/tests/test_migrations_d4d.py -v 2>&1"
    )
    ec, out_two, err_two = exec_cmd(cmd2, timeout=600)
    print(out_two)
    if err_two:
        print(f"[STDERR] {err_two}")

    # 4. 跑全量 D4D L1（得到准确计数）
    step("4. pytest 全量 test_*_d4d.py（计数）")
    cmd_full = (
        f"cd {REPO} && PYTHONPATH={REPO}/memory-service {VENV_PY} -m pytest "
        f"memory-service/tests/test_*_d4d.py 2>&1"
    )
    ec, out_full, err_full = exec_cmd(cmd_full, timeout=600)
    print(out_full)
    if err_full:
        print(f"[STDERR] {err_full}")

    # 5. 落盘本地证据
    step("5. 落盘本地证据")
    os.makedirs(LOCAL_EV, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    meta = (
        f"=== L1 回归（麒麟 VM）===\n"
        f"tested_commit: {head}\n"
        f"command: PYTHONPATH=memory-service python -m pytest memory-service/tests/test_db_d4d.py memory-service/tests/test_migrations_d4d.py -v\n"
        f"date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    log = meta + "\n\n# ===== 两个文件 -v =====\n" + out_two + "\n\n# ===== 全量 =====\n" + out_full
    with open(os.path.join(LOCAL_EV, f"l1_regression_{ts}.log"), "w", encoding="utf-8") as f:
        f.write(log)
    print(f"[OK] 证据已落盘: {os.path.join(LOCAL_EV, f'l1_regression_{ts}.log')}")

    ssh.close()
    print("\nDONE")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n[FATAL] 脚本异常: {type(exc).__name__}: {exc}")
        try:
            ssh.close()
        except Exception:
            pass
        sys.exit(1)
