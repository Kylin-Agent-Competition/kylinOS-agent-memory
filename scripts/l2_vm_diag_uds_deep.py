#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UDS stop 语义深化复测：多次循环 stop→connect + sendall 探测 + VM server.py 对比。
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
VFY_DIR = "/tmp/kylin-memory-vfy"

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

    # ── VM server.py 的 stop() / unlink / _close_server_sock 源码 ──
    print("=" * 64)
    print("VM server.py: stop() 相关实现")
    print("=" * 64)
    ec, out, _ = exec_cmd(
        f"sed -n '104,122p' {REPO}/memory-service/gateway/server.py")
    print(out)

    ec, out, _ = exec_cmd(
        f"grep -n 'unlink' {REPO}/memory-service/gateway/server.py || echo NO_UNLINK_IN_STOP")
    print(out)

    # ── 深化复测：5 轮 stop→connect + sendall 探测 ──
    print("=" * 64)
    print("深化复测：5 轮 stop→connect，connect OK 后 sendall 探测")
    print("=" * 64)
    deep = r'''# -*- coding: utf-8 -*-
import socket, sys, threading, time, os
sys.path.insert(0, "/home/kylin-agent/kylinOS-agent-memory/memory-service")
from db.engine import create_db_engine, init_schema
from gateway.handlers import register_default_handlers
from gateway.protocol import encode
from gateway.registry import HandlerRegistry
from gateway.server import UDSGatewayServer

def run_once(i):
    SOCK = "/tmp/kylin-memory-vfy/deep%s.sock" % i
    DB = "/tmp/kylin-memory-vfy/deep_uds_%s.db" % i
    engine = create_db_engine(DB)
    init_schema(engine)
    reg = HandlerRegistry()
    register_default_handlers(reg)
    server = UDSGatewayServer(SOCK, reg, engine=engine, default_deadline_ms=5000)
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    time.sleep(0.4)
    server.stop()
    time.sleep(0.2)
    print(f"--- round {i}: socket file exists={os.path.exists(SOCK)} "
          f"running={server._running} stopped={server._stopped} ---")
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(SOCK)
        print(f"round {i}: CONNECT_OK")
        # 探测：能发数据且能收到响应吗
        try:
            s.sendall(encode({"protocol_version": "1.0", "request_id": "r", "trace_id": "t",
                              "method": "health", "deadline_ms": 2000, "payload": {}}))
            s.settimeout(1.0)
            try:
                data = s.recv(64)
                print(f"round {i}: recv -> {len(data)} bytes ({data[:40]!r})")
            except socket.timeout:
                print(f"round {i}: recv -> TIMEOUT（连接排队但无响应）")
            except OSError as exc:
                print(f"round {i}: recv -> OSError {exc.errno} {exc}")
        except OSError as exc:
            print(f"round {i}: send -> OSError {exc.errno} {exc}")
        s.close()
    except OSError as exc:
        print(f"round {i}: CONNECT_REJECTED errno={exc.errno} ({exc.strerror})")
    engine.dispose()

for i in range(5):
    run_once(i)
'''
    write_remote_b64(f"{VFY_DIR}/deep_uds.py", deep)
    ec, out, err = exec_cmd(f"{VENV_PY} {VFY_DIR}/deep_uds.py", timeout=90)
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