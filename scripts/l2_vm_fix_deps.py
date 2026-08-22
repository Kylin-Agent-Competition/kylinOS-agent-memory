#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D4D L2 麒麟 VM 依赖修复（方案 A）：确认 Python 版本 -> 安装 Miniconda py311 -> 重建 venv -> 安装依赖 -> 验证。
SSH: 127.0.0.1:2222 / kylin-agent，密码来自环境变量 KYLIN_VM_PASSWORD（禁止硬编码）。
"""
import io, os, sys, time

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import paramiko

try:
    PW = os.environ["KYLIN_VM_PASSWORD"]
except KeyError:
    print("FATAL: KYLIN_VM_PASSWORD environment variable is required but not set.", file=sys.stderr)
    sys.exit(1)

HOST, PORT, USER = "127.0.0.1", 2222, "kylin-agent"
REPO = "/home/kylin-agent/kylinOS-agent-memory"
REQ = f"{REPO}/memory-service/requirements.txt"
CONDA_PREFIX = "/home/kylin-agent/miniconda3"
PY311 = f"{CONDA_PREFIX}/envs/py311/bin/python"
VENV = "/home/kylin-agent/d4d-venv"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

def exec_cmd(cmd, timeout=300, quiet=False):
    """执行远程命令，持续读取直到结束。返回 (exit_code, stdout_str, stderr_str)。"""
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    # 轮询读取，避免大输出阻塞
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
    out = "".join(out_buf)
    err = "".join(err_buf)
    if not quiet:
        if out.strip():
            print(f"[VM] {out.strip()}")
        if err.strip():
            print(f"[VM-ERR] {err.strip()}")
    return ec, out, err

def step(title):
    print("\n" + "=" * 64)
    print(f"STEP: {title}")
    print("=" * 64)

def main():
    print("=" * 64)
    print(" D4D L2 VM 依赖修复 — 方案 A（Miniconda + Python 3.11）")
    print("=" * 64)

    ssh.connect(HOST, port=PORT, username=USER, password=PW, timeout=25)
    print("[OK] 已连接麒麟 VM")

    # ── Step 0: 确认根因（Python 版本） ──
    step("0. 确认 VM Python / pip 版本")
    ec, out, _ = exec_cmd("python3 --version; python3 -m pip --version 2>&1 || echo NO_PIP")
    pv = ""
    for line in out.splitlines():
        if line.lower().startswith("python"):
            pv = line.strip()
    print(f"[INFO] 系统 python3: {pv or '未知'}")
    is_py36 = " 3.6" in pv or pv.startswith("Python 3.6")
    print(f"[INFO] 判定为 Python 3.6（SQLAlchemy2/pydantic2 不兼容根因）: {'是' if is_py36 else '否，继续排查/直接安装'}")

    # ── Step 1: 检查仓库 ──
    step("1. 检查 ~/kylinOS-agent-memory 仓库")
    ec, out, _ = exec_cmd(f"test -d {REPO}/.git && git -C {REPO} log --oneline -1 || echo NO_REPO")
    if "NO_REPO" in out:
        print("[WARN] 仓库不存在，先按手册第 0 步 clone")
        ec, out, err = exec_cmd(
            "git clone --branch feat/d4d-ipc-db-outbox "
            "https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory.git "
            f"{REPO} && git -C {REPO} log --oneline -1", timeout=600)
    else:
        print(f"[INFO] 仓库存在: {out.strip()}")

    # ── Step 2: 安装 Miniconda（若未装） ──
    step("2. 安装 Miniconda（仅首次）")
    ec, out, _ = exec_cmd(f"test -x {CONDA_PREFIX}/bin/conda && echo CONDA_OK || echo NO_CONDA")
    if "CONDA_OK" not in out:
        print("[INFO] 未检测到 conda，下载 Miniconda（约 100MB，可能较慢）...")
        ec, out, err = exec_cmd(
            "cd ~ && wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh "
            "-O miniconda.sh && echo WGET_OK || (curl -fsSL "
            "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o miniconda.sh && echo CURL_OK)",
            timeout=900)
        if "WGET_OK" not in out and "CURL_OK" not in out:
            print("[FATAL] Miniconda 下载失败，请检查 VM 外网连通性")
            print("[HINT] 可尝试在 VM 手动下载后重跑本脚本（脚本检测到 conda 会跳过下载）")
            sys.exit(1)
        print("[INFO] 下载完成，静默安装到 ~/miniconda3 ...")
        ec, out, err = exec_cmd(
            f"bash ~/miniconda.sh -b -p {CONDA_PREFIX} && {CONDA_PREFIX}/bin/conda --version",
            timeout=600)
    else:
        print(f"[INFO] conda 已存在: {out.strip()}")

    # ── Step 3: 创建 py311 环境（若不存在） ──
    step("3. 准备 Python 3.11 环境")
    ec, out, _ = exec_cmd(f"test -x {PY311} && echo PY311_OK || echo NO_PY311")
    if "PY311_OK" not in out:
        print("[INFO] 创建 py311 环境 ...")
        exec_cmd(f"{CONDA_PREFIX}/bin/conda create -y -n py311 python=3.11", timeout=900)
    ec, out, _ = exec_cmd(f"{PY311} --version")

    # ── Step 4: 重建 venv（保持手册命令路径不变） ──
    step("4. 用 Python 3.11 重建 ~/d4d-venv")
    exec_cmd(f"{PY311} -m venv --clear {VENV}", timeout=300)
    exec_cmd(f"{VENV}/bin/pip install --upgrade pip setuptools wheel", timeout=600)

    # ── Step 5: 安装依赖 ──
    step(f"5. 安装 {REQ}")
    ec, out, err = exec_cmd(f"{VENV}/bin/pip install -r {REQ}", timeout=900)
    if ec != 0:
        print("[FATAL] pip install 失败，尝试清华镜像重试 ...")
        exec_cmd(
            f"{VENV}/bin/pip install -r {REQ} -i https://pypi.tuna.tsinghua.edu.cn/simple",
            timeout=900)

    # ── Step 6: 验证 ──
    step("6. 验证安装结果")
    ec, out, _ = exec_cmd(
        f"{VENV}/bin/python -c \"import sqlalchemy, alembic, pydantic; "
        "print('sqlalchemy', sqlalchemy.__version__); print('alembic', alembic.__version__); "
        "print('pydantic', pydantic.__version__)\"")
    ok = ("sqlalchemy 2.0" in out or "sqlalchemy 2.1" in out) and "alembic 1" in out and "pydantic 2" in out
    print("\n" + "=" * 64)
    if ok:
        print("RESULT: ✅ 依赖版本正常，可继续手册第 2 步 Alembic 迁移验收")
    else:
        print("RESULT: ❌ 仍有异常，请将上方完整输出与 python --version 一并交由宿主核对")
    print("=" * 64)

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