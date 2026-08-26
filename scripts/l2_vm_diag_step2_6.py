#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L2 失败项诊断 v2：第 2 步 alembic 调用方式试探 + 第 6 步 UDS stop 语义。
SSH: 127.0.0.1:2222 / kylin-agent，密码来自环境变量 KYLIN_VM_PASSWORD。
"""
import base64, hashlib, io, os, sys

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
VENV_ALEMBIC = f"{HOME}/d4d-venv/bin/alembic"
VFY_DIR = "/tmp/kylin-memory-vfy"
DB = f"{VFY_DIR}/kylin_memory.db"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())


def exec_cmd(cmd, timeout=300):
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


def write_remote_b64(remote_path, content):
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    local_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    ec, out, err = exec_cmd(
        f"echo {b64} | base64 -d > {remote_path} && "
        f"remote_sha=$(sha256sum {remote_path} | cut -d' ' -f1) && "
        f"test \"$remote_sha\" = \"{local_sha}\" && echo WRITE_OK || echo WRITE_MISMATCH")
    if "WRITE_OK" not in out:
        raise RuntimeError(f"写远程文件失败: {remote_path}\n{out}\n{err}")
    print(f"[OK] 写入并校验 {remote_path} ({local_sha[:12]})")


def main():
    ssh.connect("127.0.0.1", port=2222, username="kylin-agent", password=PW, timeout=25)
    print("[OK] connected\n")
    exec_cmd(f"mkdir -p {VFY_DIR}")

    # ── 第 2 步诊断：试探 alembic 调用方式 ──
    print("=" * 64)
    print("DIAG 第 2 步: alembic 调用方式试探")
    print("=" * 64)

    # 方式 A（手册原样）：cd migrations && alembic upgrade head —— 已知失败，重验一次
    ec, out, _ = exec_cmd(
        f"export KYLIN_MEMORY_DB={DB} && cd {REPO}/migrations && "
        f"{VENV_ALEMBIC} upgrade head 2>&1; echo EXIT=$?")
    print(f"[A] cd migrations && alembic upgrade head -> EXIT={out.strip().splitlines()[-1] if out.strip() else '?'}")
    for line in out.strip().splitlines():
        if "FAILED" in line or "Path" in line:
            print(f"    {line.strip()}")

    # 方式 B（推荐）：仓库根 + -c 指定配置
    ec, out, _ = exec_cmd(
        f"export KYLIN_MEMORY_DB={DB} && cd {REPO} && "
        f"{VENV_ALEMBIC} -c migrations/alembic.ini upgrade head 2>&1; echo EXIT=$?")
    print(f"[B] cd {REPO} && alembic -c migrations/alembic.ini upgrade head")
    print(out[-2000:] if len(out) > 2000 else out)

    # ---- 若 B 成功，检查 schema ----
    ec, out, _ = exec_cmd(f'sqlite3 "{DB}" ".tables" 2>&1')
    print("--- .tables ---")
    print(out)

    # ── 第 6 步诊断：UDS stop() 后 connect 行为 ──
    print("=" * 64)
    print("DIAG 第 6 步: UDS stop() 后 connect 行为复测")
    print("=" * 64)
    diag_uds = r'''# -*- coding: utf-8 -*-
import socket, sys, threading, time, os, stat
sys.path.insert(0, "/home/kylin-agent/kylinOS-agent-memory/memory-service")
from db.engine import create_db_engine, init_schema
from gateway.handlers import register_default_handlers
from gateway.protocol import encode
from gateway.registry import HandlerRegistry
from gateway.server import UDSGatewayServer

SOCK = "/tmp/kylin-memory-vfy/diag.sock"
DB = "/tmp/kylin-memory-vfy/diag_uds.db"
engine = create_db_engine(DB)
init_schema(engine)
reg = HandlerRegistry()
register_default_handlers(reg)
server = UDSGatewayServer(SOCK, reg, engine=engine, default_deadline_ms=5000)
t = threading.Thread(target=server.start, daemon=True)
t.start()
time.sleep(0.6)
print("before stop >> _server_sock:", server._server_sock is not None,
      "_running:", server._running, "_stopped:", server._stopped)
print("socket file exists:", os.path.exists(SOCK))

server.stop()
time.sleep(0.3)
print("after stop  >> _server_sock:", server._server_sock is not None,
      "_running:", server._running, "_stopped:", server._stopped)
print("socket file exists:", os.path.exists(SOCK))
if os.path.exists(SOCK):
    st = os.stat(SOCK)
    print("  mode:", oct(stat.S_IMODE(st.st_mode)), "is_socket:", stat.S_ISSOCK(st.st_mode))

try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1)
    s.connect(SOCK)
    print("CONNECT_OK (unexpected) -> 停止后仍可连接（缺陷/竞态）")
    s.close()
except OSError as exc:
    print(f"CONNECT_REJECTED errno={exc.errno} ({exc.strerror}) -> 符合预期")
except Exception as exc:
    print(f"OTHER {type(exc).__name__}: {exc}")
'''
    write_remote_b64(f"{VFY_DIR}/diag_uds.py", diag_uds)
    ec, out, err = exec_cmd(f"{VENV_PY} {VFY_DIR}/diag_uds.py", timeout=60)
    print(out)
    if err.strip():
        print(err)

    ssh.close()


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